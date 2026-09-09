#!/usr/bin/env python3
"""Read-only retail census and pinned BASE/TU playcall patch receipts.

Outputs only derived JSON receipts and our authored TOML patch. Optional TU
reconstruction requires an existing local Xenia source tree, cc, cryptography,
and libxxhash. Its game image is written only to the explicitly supplied path
outside the repository. No network, emulator or game launch is involved.
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mod_editor.core import apf2k8_audibles as audible
from mod_editor.core import apf2k8_playcall_patch as patcher
from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core.apf2k8_playbook_route_writer import read_master_play_body
from tools.apf_stfs_roster_extract import _StfsReader, HASHES_PER_TABLE, BLOCK_SIZE

TU_SHA256 = "5f71cdf4ec679f8e33fd95e02ff2b67981fbf918d4d03a2099576734c5cfb42b"
XEXP_SHA256 = "14e272063536656d2aae9b4743fdcebb927566722dc1e2f34fe75029e1e8ada6"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def u32(data, offset):
    return struct.unpack_from(">I", data, offset)[0]


def digest(data):
    return hashlib.sha256(data).hexdigest()


class _PinnedLiveReader(_StfsReader):
    """LIVE parent table status is not a data-block allocation status.

    Retain top/parent/data SHA-1 and every other STFS check. Only allow this
    exception for the hash-pinned TU, without relaxing the roster extractor.
    """
    def __init__(self, data):
        require(digest(data) == TU_SHA256, "Unrecognized title update package")
        super().__init__(data)

    def _level_zero_table(self, block):
        if self.top_level == 0:
            return self.top_table
        parent = self.top_entries[block // HASHES_PER_TABLE]
        address = (self.first_table_address + self._first_level_backing_block(block)*BLOCK_SIZE
                   + ((parent.status & 0x40) << 6))
        data = self.data[address:address+BLOCK_SIZE]
        require(len(data) == BLOCK_SIZE and hashlib.sha1(data).digest() == parent.digest,
                "LIVE parent table SHA-1 differs")
        return data


# Original minimal memory adapter for the already installed Xenia libmspack.
# No game data, keys, or third-party decompressor implementation are embedded.
LZX_SHIM = r'''
#include <stdlib.h>
#include <string.h>
#include "mspack.h"
#include "lzx.h"
typedef struct { unsigned char *p; int n, pos; } Mem;
static int rd(struct mspack_file *f, void *p, int n) {
 Mem *m=(Mem*)f; if(n>m->n-m->pos)n=m->n-m->pos;
 memcpy(p,m->p+m->pos,n);m->pos+=n;return n;
}
static int wr(struct mspack_file *f, void *p, int n) {
 Mem *m=(Mem*)f; if(n>m->n-m->pos)n=m->n-m->pos;
 memcpy(m->p+m->pos,p,n);m->pos+=n;return n;
}
static void *al(struct mspack_system *s,size_t n){return calloc(n,1);}
static void fr(void *p){free(p);}
static void cp(void *s,void*d,size_t n){memcpy(d,s,n);}
void xenia_log(const char *fmt,...) {}
int delta(void *src,int size,void *dest,int len,int win,void *old){
 if(len<0 || len>win || win!=32768)return -3;
 struct mspack_system sys={0};sys.read=rd;sys.write=wr;sys.alloc=al;sys.free=fr;sys.copy=cp;
 Mem in={src,size,0},out={dest,len,0};
 struct lzxd_stream *s=lzxd_init(&sys,(void*)&in,(void*)&out,15,0,0x8000,len,0);
 if(!s)return -1;
 memset(s->window,0,win);memcpy(s->window+win-len,old,len);s->ref_data_size=win;
 int r=lzxd_decompress(s,len);lzxd_free(s);return r?r:(out.pos==len?0:-2);
}
'''


def _module_hash(header, flat):
    """Mirror Xenia UserModule::CalculateHash AFTER SetupLibraryImports.

    The pinned title imports only kernel libraries. Variables lie outside code;
    all 334 code thunks become sc 2; blr; nop; nop. No title is executed.
    """
    image = bytearray(flat)
    opts = dict(struct.unpack_from(">II", header, 24+i*8) for i in range(u32(header,20)))
    security = u32(header,16)
    n = u32(header,security+0x180)
    code = [i for i in range(n) if u32(header,security+0x184+24*i)&15 == 1]
    start, end = min(code)*65536, (max(code)+1)*65536
    libraries = opts[0x103FF]
    off = libraries+12+u32(header,libraries+4)
    thunks = 0
    while off < libraries+u32(header,libraries):
        count = struct.unpack_from(">H",header,off+0x26)[0]
        for i in range(count):
            address = u32(header,off+0x28+i*4)-patcher.IMAGE_BASE
            word = u32(image,address)
            if word>>24 == 1:
                image[address:address+16] = struct.pack(">4I",0x44000042,0x4E800020,0x60000000,0x60000000)
                thunks += 1
            else:
                require(not start <= address < end, "Unexpected variable import in code")
        size = u32(header,off)
        require(size > 0, "Empty import library")
        off += size
    require(thunks == 334, "Unexpected import thunk count")
    library = ctypes.util.find_library("xxhash")
    require(library is not None, "Local libxxhash is required for Xenia module identity")
    lib = ctypes.CDLL(library)
    lib.XXH3_64bits.argtypes = [ctypes.c_void_p,ctypes.c_size_t]
    lib.XXH3_64bits.restype = ctypes.c_uint64
    payload = bytes(image[start:end])
    return f"{lib.XXH3_64bits(payload,len(payload)):016X}"


def reconstruct_tu(base_image, base_xex, package, xenia_source):
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    require(digest(base_image) == patcher.PROFILES[0].sha256, "Wrong base flat image")
    reader = _PinnedLiveReader(package)
    entries = reader.directory_entries()
    require(len(entries) == 1 and entries[0].path == "default.xexp", "Unexpected TU directory")
    delta_xex = reader.extract(entries[0])
    require(digest(delta_xex) == XEXP_SHA256, "Wrong extracted delta XEX")
    opts = dict(struct.unpack_from(">II",delta_xex,24+i*8) for i in range(u32(delta_xex,20)))
    fmt, desc = opts[0x3FF], opts[0x5FF]
    require(struct.unpack_from(">IHHI",delta_xex,fmt) == (36,1,3,32768), "Unexpected XEXP format")
    original_header = base_xex[:u32(base_xex,8)]
    security = u32(original_header,16)
    require(hashlib.sha1(original_header[security+8:security+0x108]).digest() == delta_xex[desc+12:desc+32],
            "Delta source signature digest differs")
    require(_module_hash(original_header,base_image) == patcher.PROFILES[0].module_hash,
            "Base Xenia hash reproduction failed")
    header = bytearray(original_header)
    image = bytearray(base_image)
    source = Path(xenia_source)
    loader = source / "src/xenia/cpu/xex_module.cc"
    key_match = re.search(r"xe_xex2_retail_key\[16\] = \{([^}]+)",loader.read_text())
    require(key_match is not None, "Local Xenia retail loader key constant not found")
    key = bytes(int(x,16) for x in re.findall(r"0x([0-9A-Fa-f]{2})",key_match.group(1)))
    def aes(key, data):
        decoder = Cipher(algorithms.AES(key),modes.CBC(bytes(16))).decryptor()
        return decoder.update(data)+decoder.finalize()
    def session(h, key):
        offset = u32(h,16)+0x150
        return aes(key,bytes(h[offset:offset+16]))
    original_key = session(header,key)
    counter = 0
    with tempfile.TemporaryDirectory(prefix="apf-tudelta-") as work:
        work = Path(work)
        shim, binary = work/"adapter.c", work/"adapter.so"
        shim.write_text(LZX_SHIM)
        mspack = source/"third_party/mspack"
        subprocess.run(["cc","-shared","-fPIC","-O2","-I",str(mspack),str(shim),
                        str(mspack/"lzxd.c"),"-o",str(binary)],check=True,capture_output=True)
        lib = ctypes.CDLL(str(binary))
        lib.delta.argtypes = [ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_void_p]
        def apply(data, target):
            nonlocal counter
            off = 0
            while off+12 <= len(data):
                old,new,length,compressed = struct.unpack_from(">IIHH",data,off)
                off += 12
                if not (old|new|length|compressed):
                    break
                require(max(old+length,new+length) <= len(target), "Delta outside image")
                if compressed == 0:
                    target[new:new+length] = bytes(length)
                elif compressed == 1:
                    target[new:new+length] = target[old:old+length]
                else:
                    require(off+compressed <= len(data) and length <= 32768,"Truncated/oversized delta")
                    output = ctypes.create_string_buffer(length)
                    code = lib.delta(data[off:off+compressed],compressed,output,length,32768,
                                     bytes(target[old:old+length]))
                    require(code == 0,f"LZX delta failed with code {code}")
                    target[new:new+length] = output.raw
                    off += compressed
                counter += 1
        target,hs,hn,hd,ims,imn,imd = struct.unpack_from(">7I",delta_xex,desc+48)
        require((target,hs,hn,hd,ims,imn,imd) == (0x7000,0,0x7000,0,0,0x3380000,0), "Unexpected delta layout")
        apply(delta_xex[desc+76:desc+u32(delta_xex,desc)],header)
        del header[target:]
        new_key = session(header,key)
        require(aes(new_key,delta_xex[desc+32:desc+48]) == original_key, "Delta key source mismatch")
        payload = aes(session(delta_xex,new_key),delta_xex[u32(delta_xex,8):])
        size, block_hash = u32(delta_xex,fmt+12), delta_xex[fmt+16:fmt+36]
        pos, blocks = 0, 0
        while size:
            block = payload[pos:pos+size]
            require(len(block) == size and size >= 24 and hashlib.sha1(block).digest() == block_hash,
                    "Decrypted delta block SHA-1 mismatch")
            apply(block[24:],image)
            pos += size; size,block_hash = u32(block,0), block[4:24]; blocks += 1
    require(digest(image) == patcher.PROFILES[1].sha256, "Reconstructed TU image SHA-256 mismatch")
    require(_module_hash(header,image) == patcher.PROFILES[1].module_hash, "Reconstructed TU module identity differs")
    return bytes(image), {"package_sha256": digest(package), "xexp_sha256": digest(delta_xex),
                          "image_sha256": digest(image), "delta_blocks_sha1_verified": blocks,
                          "delta_records": counter, "stfs_data_blocks_verified": len(reader._verified_data_blocks),
                          "base_module_hash_reproduced": patcher.PROFILES[0].module_hash,
                          "tu_module_hash_reproduced": patcher.PROFILES[1].module_hash,
                          "rsa_signature_verified": False, "status": "unwitnessed"}


def no_overlap_receipt(entry_bytes, entry):
    """Independently walk the emitted H7A descriptors, not just round-trip."""
    memory = splb.apf_texture_patch.BytesReader(entry_bytes)
    record = splb.apf_inner.parse_iff(memory,entry)
    matches = 0
    for block in record.blocks:
        if not block.is_compressed:
            continue
        stored = memory.read(entry,block.start_offset,block.stored_length)
        stream = stored[splb.apf_inner.H7A_HEADER_SIZE:]
        shift = block.wrapper.shift
        cursor, produced = 0, 0
        while produced < block.uncompressed_length:
            descriptor = stream[cursor]; cursor += 1
            for bit in range(8):
                if produced == block.uncompressed_length:
                    break
                if descriptor >> bit & 1:
                    word = int.from_bytes(stream[cursor:cursor+2],"big"); cursor += 2
                    distance, length = word & ((1<<shift)-1), (word>>shift)+3
                    require(0 < length <= distance <= produced,"H7A overlapping/out-of-range match")
                    produced += length; matches += 1
                else:
                    cursor += 1; produced += 1
                require(cursor <= len(stream) and produced <= block.uncompressed_length,"H7A stream overrun")
    return {"matches_checked": matches,"overlapping_matches": 0}


def retail_census(index):
    catalog = audible.play_catalog(read_master_play_body(index))
    archive = splb.apf_outer.parse_archive(index)
    results = []
    for outer in audible.CPU_OFFENSE_BOOKS:
        plan, compiled = audible.build_audible_fix(index,outer)
        require(compiled is not None,"Retail audible result unexpectedly has no edits")
        after = splb.parse_book(plan.replacement,outer)
        require(not audible.plan_audibles(after,catalog).changes,"Audible fixer is not idempotent")
        receipt = {"outer_index":outer,"book_name":compiled.report['book_name'],
                   "input_body_sha256":digest(splb.read_book(index,outer).body),
                   "output_body_sha256":digest(plan.replacement),
                   "balanced_before":plan.report['balanced_before'],"balanced_after":plan.report['balanced_after'],
                   "record_count":len(plan.report['before']),"moves":len(plan.changes),
                   "impossible_records":plan.report['impossible_records'],
                   "before":plan.report['before'],"after":plan.report['after'],
                   "personnel_availability":compiled.report['personnel_availability'],
                   "output_entry_size":len(compiled.entry_bytes),
                   "output_entry_sha256":compiled.report['output_entry_sha256'],
                   "verification":compiled.report['verification'],
                   "h7a_round_trip_exact":compiled.report['claims']['h7a_round_trip_exact'],
                   "fixed_outer_allocation_preserved":compiled.report['claims']['fixed_outer_allocation_preserved'],
                   "h7a_no_overlap":no_overlap_receipt(compiled.entry_bytes,archive.entries[outer]),
                   "idempotent_replan":True,"status":"unwitnessed"}
        results.append(receipt)
        print(f"{outer} {receipt['book_name']}: {receipt['balanced_before']} -> {receipt['balanced_after']} / "
              f"{receipt['record_count']} balanced, {receipt['moves']} moves, "
              f"{len(receipt['impossible_records'])} impossible; allocation={receipt['output_entry_size']}; "
              "H7A/reparse/no-overlap/idempotence PASS")
    return results


def compact_receipt(report):
    """Small shareable census: selectors, counts, hashes; no retail payloads."""
    kinds = ("run", "pass", "unknown", "special_or_defense")
    compact = {"schema":"astra_apf_playcall_compact/v1", "status":"unwitnessed",
               "count_order":list(kinds),
               "record_columns":["record", "formation", "category", "entries", "available",
                                 "audible_before", "audible_after", "tag_play_ids_before", "tag_play_ids_after"],
               "personnel_columns":["category", "row", "advertised_before", "advertised_after",
                                    "records_before", "records_after", "ordinary_before", "ordinary_after", "stock_te"],
               "books":[], "patches":report["patches"]}
    for book in report["books"]:
        item = {k:v for k,v in book.items() if k not in ("before", "after", "personnel_availability")}
        item["records"] = [
            [a["record_index"],a["formation_index"],a["category_index"],a["entry_count"],
             [a["available"][k] for k in kinds], [b["counts"][k] for k in kinds],
             [a["counts"][k] for k in kinds],
             [[s["tag"],s["play_index"]] for s in b["slots"]],
             [[s["tag"],s["play_index"]] for s in a["slots"]]]
            for b,a in zip(book["before"],book["after"])]
        before, after = (book["personnel_availability"][k] for k in ("before", "after"))
        item["personnel"] = [
            [a["category_index"],a["personnel_row"],b["advertised"],a["advertised"],
             len(b["record_indices"]),len(a["record_indices"]),
             b["ordinary_play_instances"],a["ordinary_play_instances"],a["te_offense"]]
            for b,a in zip(before["categories"],after["categories"])]
        item["personnel_boundaries"] = {phase:{k:values[k] for k in (
            "answerable_personnel_rows", "normalization_restores_category_indices",
            "hidden_populated_record_indices", "duplicate_formation_record_indices",
            "cached_play_count", "cached_plays_without_records", "stored_plays_missing_from_cache")}
            for phase,values in (("before",before),("after",after))}
        compact["books"].append(item)
    if "title_update" in report:
        compact["title_update"] = report["title_update"]
    return compact


def receipt_json(value, depth=0):
    """Indent objects while keeping census array rows on one reviewable line."""
    if isinstance(value, dict):
        pad = "  " * (depth + 1)
        return "{\n" + ",\n".join(pad+json.dumps(k)+": "+receipt_json(v,depth+1)
                                   for k,v in value.items()) + "\n" + "  "*depth + "}"
    if isinstance(value, list) and value and isinstance(value[0], (dict,list)):
        pad = "  " * (depth + 1)
        return "[\n" + ",\n".join(pad+receipt_json(v,depth+1) for v in value) + "\n" + "  "*depth + "]"
    return json.dumps(value,separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index",type=Path,required=True)
    ap.add_argument("--base-image",type=Path,required=True)
    ap.add_argument("--report",type=Path,required=True)
    ap.add_argument("--compact-report",type=Path,help="Optional shareable per-record census and hashes")
    ap.add_argument("--patch-dir",type=Path,required=True)
    ap.add_argument("--base-xex",type=Path)
    ap.add_argument("--tu-package",type=Path)
    ap.add_argument("--xenia-source",type=Path)
    ap.add_argument("--tu-output",type=Path)
    args = ap.parse_args()
    image = args.base_image.read_bytes()
    patcher.compile_patch(image)
    report = {"schema":"astra_apf_playcall_audit/v1","status":"unwitnessed",
              "books":retail_census(args.index),"patches":[]}
    args.patch_dir.mkdir(parents=True,exist_ok=True)
    report['patches'].append(patcher.write_patch(args.base_image,args.patch_dir/"54540807-base-pass-fetch-te.patch.toml"))
    if args.tu_package:
        require(all((args.base_xex,args.xenia_source,args.tu_output)),"TU audit requires --base-xex, --xenia-source, --tu-output")
        output = args.tu_output.resolve()
        require(not output.is_relative_to(ROOT),"Reconstructed retail image must remain outside the repository")
        require(not output.exists(),"TU image output must be a new file")
        tu, receipt = reconstruct_tu(image,args.base_xex.read_bytes(),args.tu_package.read_bytes(),args.xenia_source)
        output.write_bytes(tu)
        report['title_update'] = receipt
        report['patches'].append(patcher.write_patch(output,args.patch_dir/"54540807-tu-1-1-pass-fetch-te.patch.toml"))
        print("TU reconstruction: 12 block hashes, 3779 deltas, BASE/TU Xenia identities PASS")
    args.report.write_text(json.dumps(report,indent=2)+"\n")
    if args.compact_report:
        compact = compact_receipt(report)
        encoded = receipt_json(compact)+"\n"
        require(json.loads(encoded) == compact,"Compact receipt failed JSON reparse")
        args.compact_report.write_text(encoded)
    print(f"Derived receipt: {args.report}")


if __name__ == "__main__":
    main()

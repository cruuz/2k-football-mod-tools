#!/usr/bin/env python3
"""Read-only r64 selector/reference census for the pinned USA executable.

Scans every four-byte window, including unaligned windows, for every address
inside the fifteen page families and sixteen sheet/list spans. Raw integer
matches remain candidates, not proof of pointers and never allocation advice.
The optional Ghidra function index supplies instruction boundaries and reader
callers; Capstone decodes their actual bytes. Output contains metadata only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mod_editor.core import nfl2k5_position_pools as pools
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage

# Complete native functions used to establish the dispatch and cache behavior.
READERS = (0x27CDF0, 0x1749D0, 0x1746C0, 0x174140, 0x170910, 0x1706C0,
           0x174CB0, 0x174CE0, 0x174D30, 0x172930, 0x1728A0, 0x172680,
           0x16F620, 0x16F630, 0x171330, 0x362E10, 0x362FC0,
           0x35FD40, 0x35FD80, 0x35F140, 0x31DD90, 0x31DE30,
           0x2B8D90, 0x2B8E20, 0x31AB20, 0x31AB80, 0x3213E0, 0x321520,
           0x36F720, 0x36F750, 0xC3CB0, 0xC3D30, 0x242670, 0x242520,
           0x12F160, 0x364C00)


# These entry points are absent from this corpus's function list. Bounds come
# from the native returns/jump-table boundary, independently disassembled here.
EXTRA_RANGES = {0x174CE0: 0x4D, 0x2B8D90: 0x72, 0x2B8E20: 0xE0,
                0x3213E0: 0x136, 0x321520: 0x0E, 0x36F750: 0x38, 0x364C00: 0x158}


def census(payload, *, corpus=None):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    from capstone.x86 import X86_OP_IMM, X86_OP_MEM
    if hashlib.sha256(payload).hexdigest() != RETAIL_SHA256:
        raise ValueError("reference proof requires the pinned USA retail XBE")
    image = XbeImage(payload)
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    functions, ranges = {}, []
    if corpus:
        with (Path(corpus) / "functions.tsv").open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                if not row["address"].startswith("0x"):
                    continue
                address = int(row["address"], 16)
                functions[address] = row
                for span in re.split("[;,]", row["body_ranges"]):
                    start, end = span.split("-")
                    ranges.append((int(start, 16), int(end, 16) + 1, address))

    for address, size in EXTRA_RANGES.items():
        if address not in functions:
            functions[address] = {"name": f"native_{address:08x}", "callers": "see page bindings", "callees": "see disassembly"}
            ranges.append((address, address + size, address))
    # XAPILIB call window absent from the corpus, bounded by push/call/add.
    ranges.append((0x3E7A52, 0x3E7A5F, 0x3E7A52))

    def file_va(off):
        for section in image.sections:
            if section.raw <= off < section.raw + section.raw_size:
                return section.start + off - section.raw, section.name
        return 0x10000 + off, "header_or_unmapped_file_bytes"

    def refs(target):
        at, result = 0, []
        needle = struct.pack("<I", target)
        while (at := payload.find(needle, at)) >= 0:
            va, section = file_va(at)
            result.append({"source": hex(va), "section": section, "file_offset": hex(at)})
            at += 1
        return result

    spans = []
    for name, va, _olb, stride, pages in pools.FILTER_TABLES:
        spans.append((min(pages), max(pages) + stride, name, "page_family"))
        spans.append((va - 0xF4, va + 4 * (len(pages) + 1), name, "sheet_and_list"))
    lo, hi = min(s[0] for s in spans), max(s[1] for s in spans)
    candidates = []
    for alignment in range(4):
        view = memoryview(payload)[alignment:len(payload) - ((len(payload) - alignment) % 4)]
        for i, (target,) in enumerate(struct.iter_unpack("<I", view)):
            if not lo <= target < hi:
                continue
            matches = [f"{name}:{kind}" for start, end, name, kind in spans if start <= target < end]
            if not matches:
                continue
            off = alignment + i * 4
            va, section = file_va(off)
            row = {"source": hex(va), "target": hex(target), "section": section,
                   "file_offset": hex(off), "spans": matches, "kind": "raw_integer_candidate"}
            # Corpus-bounded decode distinguishes e8+displacement matches and
            # opcode/operand overlaps from actual absolute address operands.
            owners = [(a, b, fn) for a, b, fn in ranges if a <= va < b]
            for a, b, fn in owners:
                for ins in md.disasm(image.read(a, b - a), a):
                    if ins.address <= va < ins.address + ins.size:
                        operands = [(op.imm & 0xFFFFFFFF) for op in ins.operands if op.type == X86_OP_IMM]
                        operands += [(op.mem.disp & 0xFFFFFFFF) for op in ins.operands if op.type == X86_OP_MEM]
                        row.update(function=hex(fn), instruction=f"{ins.address:#x}: {ins.mnemonic} {ins.op_str}",
                                   kind="decoded_address_operand" if target in operands else "instruction_encoding_overlap")
                        break
                if "instruction" in row:
                    break
            candidates.append(row)
    candidates.sort(key=lambda r: int(r["file_offset"], 16))

    tables = []
    for name, va, olb, stride, pages in pools.FILTER_TABLES:
        site = next(s for s in pools.filter_list_sites() if s.va == va)
        if image.read(va, site.size) != site.befores[0]:
            raise ValueError(f"unexpected table: {name}")
        sheet_refs = refs(va - 0xF4)
        frames = []
        for ref in sheet_refs:
            frame = int(ref["source"], 16)
            frame_refs = refs(frame)
            for frame_ref in frame_refs:
                descriptor = int(frame_ref["source"], 16) - 0x14
                frames.append({"frame": hex(frame), "descriptor": hex(descriptor),
                               "descriptor_refs": refs(descriptor)})
        page_rows = []
        for page in pages:
            name_ptr = struct.unpack("<I", image.read(page + 8, 4))[0]
            page_rows.append({"page": hex(page), "name": pools._string_at(payload, name_ptr),
                              "enum": struct.unpack("<I", image.read(page + 0x20, 4))[0],
                              "count": hex(struct.unpack("<I", image.read(page + 0x30, 4))[0]),
                              "getter": hex(struct.unpack("<I", image.read(page + 0x48, 4))[0]),
                              "page_sha256": hashlib.sha256(image.read(page, stride)).hexdigest(),
                              "absolute_base_candidates": refs(page)})
        selected = [r for r in candidates if any(s.startswith(name + ":") for s in r["spans"])]
        tables.append({"name": name, "table": hex(va), "sheet": hex(va - 0xF4),
                       "olb_name_field": hex(olb), "descriptor_stride": stride, "list_stride": 4,
                       "rows_before": len(pages), "rows_after": len(pages) - 1,
                       "span_size": site.size, "before": site.befores[0].hex(), "after": site.after.hex(),
                       "sheet_refs": sheet_refs, "frames": frames, "pages": page_rows,
                       "raw_candidate_count": len(selected),
                       "list_interior_candidates": [r for r in selected if va <= int(r["target"], 16) < va + site.size]})
    readers = []
    for address in READERS:
        row = functions.get(address)
        if row is None:
            continue
        chunks = []
        for a, b, fn in ranges:
            if fn == address:
                raw = image.read(a, b - a)
                chunks.append({"start": hex(a), "end": hex(b), "sha256": hashlib.sha256(raw).hexdigest(),
                               "instructions": [f"{i.address:#x}: {i.mnemonic} {i.op_str}" for i in md.disasm(raw, a)]})
        readers.append({"address": hex(address), "name": row["name"], "callers": row["callers"],
                        "callees": row["callees"], "chunks": chunks})
    return {"schema": "nfl2k5_olb_row_proof/v1", "retail_sha256": RETAIL_SHA256,
            "scan": "every four-byte file window, all alignments, including all interior target bytes",
            "tables": tables, "readers": readers, "raw_candidates": candidates,
            "boundary": "Static candidate census plus native fixture; no runtime witness, allocation or oracle exemption"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xbe", type=Path)
    parser.add_argument("--corpus", type=Path, help="read-only Ghidra functions directory")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.xbe.stat().st_size > 16 * 1024 * 1024:
        parser.error("expected a bounded XBE, not a disc or archive pack")
    result = census(args.xbe.read_bytes(), corpus=args.corpus)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"{len(result['tables'])} selectors, {len(result['raw_candidates'])} raw candidates, "
          f"{len(result['readers'])} disassembled readers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

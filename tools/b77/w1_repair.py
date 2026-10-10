#!/usr/bin/env python3
"""W1 (beta 77): wet uniforms stay readable in rain. Copy-only repair of the v0.5 disc in two parts.

  xbe   default.xbe: the rain light rig's ambient head (20 bytes at 0x4E7830, .rdata) and the rain fog row's start and end
        (8 bytes at 0xA8680C, .data) plus the two section SHA-1 header digests those bytes sit in.
  kits  The 70 shipped 2026 kit packages (xx[HA]0.IFF and 23[HA]10..12.IFF): the _mud palette of TSET chunks 1, 2 and 3
        (jersey, pants, sleeve) goes from 0.60 x clean (darken_60) to 0.93 x clean (wet_93, retail's white jersey is 0.936).
        Only the three compressed chunk spans of each package change, each rebuilt into its own fixed-size span.

Every owned range must hold the exact v0.5 bytes or the exact new bytes (idempotent, composes with other jobs' edits to
other bytes). Foreign bytes are refused. Receipts prove every byte outside the owned ranges is identical.

  w1_repair.py xbe  --input-xbe X --output-xbe Y --receipt R
  w1_repair.py kits --input <v0.5 xiso or extracted vc_53450030> --output DIR --receipt R [--dry-run]
  w1_repair.py derive-kits --input <v0.5 xiso> --manifest NEW.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools" / "b765")]

V05_XBE_SHA256 = "2b0fbbbb89b5c72aaed7c454bf6e78dd2c97f1e417e2d761e515907ed81471ab"
XBE_SITES = (
    # label, VA, v0.5 bytes, new bytes
    ("rain_rig_ambient_head", 0x4E7830,
     bytes.fromhex("8fc2753f4160653fa8c66b3f0000803f16d9ce3e"),
     bytes.fromhex("3333733f04566e3f04566e3f0000803fdd24063f")),
    ("rain_fog_start_end", 0xA8680C,
     bytes.fromhex("00803b450080bb45"),
     bytes.fromhex("00409c4500f05246")),
)
KIT_MANIFEST = Path(__file__).with_name("w1_kit_spans.json")
KIT_MANIFEST_SCHEMA = "b77/w1/kit-mud-spans/v1"
RECEIPT_SCHEMA = "b77/w1/repair-receipt/v1"
WET_NUM, WET_DEN = 93, 100


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


# --- default.xbe ---------------------------------------------------------------------------------------------------

def repair_xbe(payload: bytes, *, expected_input_sha256: str | None = None):
    from mod_editor.core.nfl2k5_bump_strength import _sections, _section_for_offset, section_digest
    from mod_editor.core.nfl2k5_cave_oracle import XbeImage
    before_hash = sha(payload)
    if expected_input_sha256 is not None:
        require(len(expected_input_sha256) == 64 and all(c in "0123456789abcdef" for c in expected_input_sha256),
                "expected input hash must be a lowercase SHA-256")
        accepted = {expected_input_sha256}
    else:
        accepted = {V05_XBE_SHA256}
    image, sections = XbeImage(payload), _sections(payload)
    out, ranges, touched = bytearray(payload), [], set()
    for label, va, before, after in XBE_SITES:
        at = image.offset(va, len(before))
        got = payload[at:at + len(before)]
        require(got in (before, after), f"{label}: unexpected bytes at {va:#x}; refusing")
        section = _section_for_offset(sections, at)
        out[at:at + len(after)] = after
        touched.add(section.index)
        ranges.append(dict(label=label, va=f"{va:#x}", offset=at, size=len(after), section=section.index,
                           before=got.hex(), after=after.hex()))
    for section in sections:
        if section.index in touched:
            require(section.stored_digest == section_digest(payload, section) or before_hash not in accepted,
                    "invalid input section digest")
            at = section.header_offset + 36
            out[at:at + 20] = section_digest(out, section)
            ranges.append(dict(label=f"section_{section.index}_sha1", offset=at, size=20,
                               before=payload[at:at + 20].hex(), after=bytes(out[at:at + 20]).hex()))
    result = bytes(out)
    ordered = sorted(ranges, key=lambda r: r["offset"])
    cursor, before_outside, after_outside = 0, hashlib.sha256(), hashlib.sha256()
    for row in ordered:
        start, end = row["offset"], row["offset"] + row["size"]
        require(start >= cursor, "overlapping repair scope")
        require(payload[cursor:start] == result[cursor:start], "outside-scope byte changed")
        before_outside.update(payload[cursor:start]); after_outside.update(result[cursor:start])
        cursor = end
    require(payload[cursor:] == result[cursor:], "outside-scope tail changed")
    before_outside.update(payload[cursor:]); after_outside.update(result[cursor:])
    receipt = dict(schema=RECEIPT_SCHEMA, part="xbe", disc_files=["default.xbe"], before_sha256=before_hash,
                   after_sha256=sha(result), size=len(result), already_applied=result == payload,
                   changed_bytes=sum(a != b for a, b in zip(payload, result)), ranges=ordered,
                   outside_scope_identical=True, outside_scope_bytes=len(payload) - sum(r["size"] for r in ranges),
                   outside_before_sha256=before_outside.hexdigest(), outside_after_sha256=after_outside.hexdigest(),
                   canonical_v05_input=before_hash == V05_XBE_SHA256, new_code_caves=[], save_changes=False,
                   gameplay_witnessed=False)
    return result, receipt


# --- kit mud palettes ----------------------------------------------------------------------------------------------

def wet(value: int) -> int:
    return (value * WET_NUM + WET_DEN // 2) // WET_DEN


def dark(value: int) -> int:
    return (value * 3 + 2) // 5


def rewrite_chunk(span: bytes):
    """One compressed TSET chunk span -> (new span, receipt). Mud palette entries equal to darken_60 of the clean palette
    become wet_93; entries already wet_93 stay; anything else refuses. Returns the original span object when nothing
    changes. The new span has exactly the old length."""
    from nfl_txtr import HEADER, Chunk, decode_chunk, rebuild_compressed_chunk_fixed_span
    import u1_audit as U
    kind, stored, system, video, magic, scratch, r0, r1 = HEADER.unpack_from(span)
    require(kind == b"TSET" and len(span) == HEADER.size + stored, "not a whole TSET span")
    chunk = Chunk(0, 0, "TSET", stored, system, video, magic, scratch, r0, r1)
    decoded, info = decode_chunk(span, chunk)
    require(info is not None, "TSET span is not compressed")
    count = struct.unpack_from("<I", decoded, 4)[0]
    textures = {}
    for i in range(count):
        t = U.tset_texture(decoded, i)
        textures[t.name] = t
    new = bytearray(decoded)
    pairs, changed_entries = [], 0
    for name, t in textures.items():
        if name.endswith("_mud") or name + "_mud" not in textures:
            continue
        m = textures[name + "_mud"]
        base_c, base_m = 256 + t.palette_offset, 256 + m.palette_offset
        for k in range(256):
            c = decoded[base_c + 4 * k:base_c + 4 * k + 4]
            have = decoded[base_m + 4 * k:base_m + 4 * k + 4]
            d60 = bytes((dark(c[0]), dark(c[1]), dark(c[2]), c[3]))
            w93 = bytes((wet(c[0]), wet(c[1]), wet(c[2]), c[3]))
            require(have in (d60, w93), f"{name}_mud entry {k} is neither darken_60 nor wet_93 of the clean palette")
            if have != w93:
                new[base_m + 4 * k:base_m + 4 * k + 4] = w93
                changed_entries += 1
        pairs.append(name)
    if changed_entries == 0:
        return span, dict(textures=pairs, changed_entries=0)
    rebuilt, rebuild_info = rebuild_compressed_chunk_fixed_span(span, bytes(new))
    require(len(rebuilt) == len(span), "rebuilt span size changed")
    back, _ = decode_chunk(rebuilt, chunk)
    require(back == bytes(new), "rebuilt span does not decode to the wet palette")
    return rebuilt, dict(textures=pairs, changed_entries=changed_entries)


def kit_selectors():
    jobs = []
    for path in sorted((ROOT / "data/nfl2k5_teams_2026").glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if "kits" in doc:
            for side in ("home", "away"):
                jobs.append(doc["kits"][side]["selector"])
    for style in (10, 11, 12):
        for side in "HA":
            jobs.append(f"23{side}{style}")
    require(len(jobs) == 70 and len(set(jobs)) == 70, "expected the 70 shipped 2026 sets")
    return sorted(jobs)


def _entry_for(index, bump, selector):
    nid = zlib.crc32((selector + ".IFF").encode("utf-16le")) & 0xFFFFFFFF
    for entry in index.entries:
        if entry.name_id == nid:
            return entry
    raise ValueError(f"kit absent: {selector}.IFF")


def _read_resource(image, index, entry):
    chunks = []
    for ordinal, offset, length in index.sub_extents(entry, 0, entry.size):
        chunks.append(image.read_pack(ordinal, offset, length))
    return b"".join(chunks)


def derive_kits(source: Path) -> dict:
    from mod_editor.core import nfl2k5_bump_texture_writer as bump
    from nfl_txtr import HEADER, parse_chunks
    spans = []
    with bump._Image.open(source, writable=False) as image:
        index = bump._parsed_index(image)
        for selector in kit_selectors():
            entry = _entry_for(index, bump, selector)
            package = _read_resource(image, index, entry)
            for chunk in parse_chunks(package, allow_trailing=True):
                if chunk.kind != "TSET" or chunk.index not in (1, 2, 3):
                    continue
                span = package[chunk.offset:chunk.offset + HEADER.size + chunk.stored_size]
                new_span, receipt = rewrite_chunk(span)
                require(new_span is not span and len(new_span) == len(span), f"{selector} chunk {chunk.index}: nothing to change")
                parts = index.sub_extents(entry, chunk.offset, len(span))
                require(len(parts) == 1, f"{selector} chunk {chunk.index} crosses a pack")
                spans.append(dict(selector=selector, chunk=chunk.index, resource_offset=chunk.offset, length=len(span),
                                  pack=parts[0][0], pack_offset=parts[0][1], textures=receipt["textures"],
                                  changed_entries=receipt["changed_entries"],
                                  before_sha256=sha(span), after_sha256=sha(new_span)))
    return dict(schema=KIT_MANIFEST_SCHEMA, rule=dict(mud="wet_93", gain=WET_NUM / WET_DEN, from_mode="darken_60"), spans=spans)


def repair_kits(source: Path, output: Path | None, dry_run: bool) -> dict:
    from mod_editor.core import nfl2k5_bump_texture_writer as bump
    from nfl_outer import PACK_NAMES
    from u1_repair import publish_batch, refuse_links
    manifest = json.loads(KIT_MANIFEST.read_text(encoding="utf-8"))
    require(manifest["schema"] == KIT_MANIFEST_SCHEMA and len(manifest["spans"]) == 210, "unsupported kit manifest")
    refuse_links(source)
    if output is not None:
        refuse_links(output)
        require(source.resolve() != output.resolve(), "source and output must differ")
    by_pack: dict[int, list[dict]] = {}
    with bump._Image.open(source, writable=False) as image:
        index = bump._parsed_index(image)
        for row in manifest["spans"]:
            entry = _entry_for(index, bump, row["selector"])
            parts = index.sub_extents(entry, row["resource_offset"], row["length"])
            require(len(parts) == 1 and parts[0][0] == row["pack"] and parts[0][1] == row["pack_offset"],
                    f"{row['selector']}: kit moved; refusing")
            by_pack.setdefault(row["pack"], []).append(row)
        packs, receipts = [], {}
        for ordinal, rows in sorted(by_pack.items()):
            size = image.pack_size(ordinal)
            original = image.read_pack(ordinal, 0, size)
            result = bytearray(original)
            occupied, spans_receipt = [], []
            for row in sorted(rows, key=lambda r: r["pack_offset"]):
                at, length = row["pack_offset"], row["length"]
                have = original[at:at + length]
                require(sha(have) in (row["before_sha256"], row["after_sha256"]),
                        f"{row['selector']} chunk {row['chunk']}: unexpected span bytes; refusing")
                if sha(have) == row["before_sha256"]:
                    new_span, _ = rewrite_chunk(have)
                    require(sha(new_span) == row["after_sha256"], f"{row['selector']} chunk {row['chunk']}: rebuild differs from the pinned span")
                else:
                    new_span = have
                result[at:at + length] = new_span
                occupied.append((at, at + length))
                spans_receipt.append(dict(selector=row["selector"], chunk=row["chunk"], pack_offset=at, length=length,
                                          before_sha256=row["before_sha256"], after_sha256=row["after_sha256"],
                                          already_applied=have == new_span))
            cursor, untouched = 0, hashlib.sha256()
            for start, end in occupied + [(len(original), len(original))]:
                require(start >= cursor and original[cursor:start] == result[cursor:start], "outside-scope bytes changed")
                untouched.update(original[cursor:start])
                cursor = end
            result = bytes(result)
            receipts[f"vc_53450030/{PACK_NAMES[ordinal]}"] = dict(
                before_sha256=sha(original), after_sha256=sha(result), size=size, spans=spans_receipt,
                owned_bytes=sum(e - s for s, e in occupied), outside_scope_sha256=untouched.hexdigest(),
                outside_scope_identical=True, readback=not dry_run)
            packs.append((PACK_NAMES[ordinal], result))
        index_copied = 0 not in by_pack
        if output is not None and not dry_run:
            outputs = [(output / name, data) for name, data in packs]
            if index_copied:
                outputs.insert(0, (output / "0", image.read_index_range(0, image.index_size)))
            publish_batch(outputs)
    return dict(schema=RECEIPT_SCHEMA, part="kits", disc_files=receipts, index_copied_unchanged=index_copied,
                manifest_sha256=sha(KIT_MANIFEST.read_bytes()), dry_run=dry_run, gameplay_witnessed=False)


def write_new(path: Path, data: bytes) -> None:
    if path.exists():
        require(not path.is_symlink() and path.read_bytes() == data, f"output exists with different bytes: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.link(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    px = sub.add_parser("xbe")
    px.add_argument("--input-xbe", required=True, type=Path)
    px.add_argument("--output-xbe", required=True, type=Path)
    px.add_argument("--receipt", required=True, type=Path)
    px.add_argument("--expected-input-sha256")
    pk = sub.add_parser("kits")
    pk.add_argument("--input", required=True, type=Path)
    pk.add_argument("--output", type=Path)
    pk.add_argument("--receipt", required=True, type=Path)
    pk.add_argument("--dry-run", action="store_true")
    pd = sub.add_parser("derive-kits")
    pd.add_argument("--input", required=True, type=Path)
    pd.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.cmd == "xbe":
            require(args.input_xbe.resolve() != args.output_xbe.resolve(), "output must be a separate copy")
            fixed, receipt = repair_xbe(args.input_xbe.read_bytes(), expected_input_sha256=args.expected_input_sha256)
            write_new(args.output_xbe, fixed)
            write_new(args.receipt, (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
            print(json.dumps({k: receipt[k] for k in ("before_sha256", "after_sha256", "changed_bytes", "already_applied")}, indent=2))
        elif args.cmd == "kits":
            require(args.dry_run or args.output is not None, "--output is required unless --dry-run")
            receipt = repair_kits(args.input, args.output, args.dry_run)
            write_new(args.receipt, (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
            print(json.dumps({"receipt": str(args.receipt), "packs": len(receipt["disc_files"]), "scope_verified": True}))
        else:
            require(not args.manifest.exists(), "manifest target exists")
            doc = derive_kits(args.input)
            args.manifest.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
            print(f"wrote {args.manifest}: {len(doc['spans'])} spans")
    except (OSError, ValueError) as exc:
        parser.exit(2, f"w1 repair refused: {exc}\n")


if __name__ == "__main__":
    main()

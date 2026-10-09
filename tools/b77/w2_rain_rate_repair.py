#!/usr/bin/env python3
"""W2 (beta 77): make rain less frequent on the v0.5 disc by rewriting the owned precipitation floats of the main ROST.

Owned bytes: the 4-byte precipitation-percent floats (row +0x44 + 4 x slot) of the outdoor stadium rows of the main
roster resource (outer entry 5, a resource inside pack 0). Nothing else in the ROST, the pack or the disc is written.
The site list is a pinned manifest (w2_rain_rate_sites.json, derived from the v0.5 ROST with
mod_editor.core.nfl2k5_weather.less_rain_percent); every site must hold the exact v0.5 value or the exact new value, so
the repair is idempotent and composes with other jobs' edits to other ROST bytes.

  w2_rain_rate_repair.py --input <v0.5 xiso or extracted vc_53450030> --output <new dir> --receipt <new json>
  w2_rain_rate_repair.py --derive <rost.bin> <manifest.json>      (regenerates the manifest from a v0.5 ROST)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_bump_texture_writer as bump
from mod_editor.core import nfl2k5_weather as weather
from nfl_outer import PACK_NAMES

MANIFEST = Path(__file__).with_name("w2_rain_rate_sites.json")
MANIFEST_SHA256 = "5403eccf5cff2769026c774e3777d6092b921698e3534f9cb2c8d30ddaf65b30"
ROST_ENTRY = 5
V05_ROST_SHA256 = "b3dd88e2b51824b368e78f99f17d7aea7d64b26316c60fee5c0767f31261f501"
SCHEMA = "b77/w2/rain-rate-sites/v1"
RECEIPT_SCHEMA = "b77/w2/rain-rate-receipt/v1"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def derive_sites(rost: bytes) -> dict:
    """The owned floats for this (v0.5) ROST: offsets inside the resource, before and after bytes."""
    catalog = weather.inspect_resource(rost, strict=False)
    sites = []
    for row in catalog["rows"]:
        if row["indoor"]:
            continue
        for slot, values in enumerate(row["months"]):
            at = row["offset"] + weather.FIELDS["precipitation_pct"][0] + 4 * slot
            before = bytes(rost[at:at + 4])
            percent = struct.unpack("<f", before)[0]
            after_pct = min(100.0, weather.less_rain_percent(percent, values["temperature_f"]))
            after = struct.pack("<f", after_pct)
            if after != before:
                sites.append(dict(offset=at, row=row["index"], asset_code=row["asset_code"], stadium=row["stadium"],
                                  month=values["month"], temperature_f=values["temperature_f"],
                                  before_percent=percent, after_percent=struct.unpack("<f", after)[0],
                                  before=before.hex(), after=after.hex()))
    return dict(schema=SCHEMA, rost_sha256=sha(rost), rost_size=len(rost), sites=sites,
                rule=dict(rain_cut=weather.RAIN_CUT, rain_line_f=weather.RAIN_LINE_F,
                          tod_offsets_f=weather.TOD_OFFSETS_F, tod_weights=weather.TOD_WEIGHTS))


def load_manifest(path: Path = MANIFEST) -> dict:
    raw = path.read_bytes()
    require(path != MANIFEST or sha(raw) == MANIFEST_SHA256, "site manifest changed; refusing")
    doc = json.loads(raw)
    require(doc.get("schema") == SCHEMA and doc["rost_sha256"] == V05_ROST_SHA256, "unsupported site manifest")
    return doc


def apply_sites(rost: bytes, manifest: dict) -> tuple[bytes, dict]:
    require(len(rost) == manifest["rost_size"], "ROST size changed; refusing")
    out = bytearray(rost)
    rows, last_end = [], -1
    for site in sorted(manifest["sites"], key=lambda s: s["offset"]):
        at = site["offset"]
        require(at >= last_end and at + 4 <= len(rost), "overlapping or out-of-range site")
        last_end = at + 4
        before, after = bytes.fromhex(site["before"]), bytes.fromhex(site["after"])
        have = bytes(rost[at:at + 4])
        require(have in (before, after), f"unexpected bytes at ROST+{at:#x} ({site['asset_code']} month {site['month']}); refusing")
        out[at:at + 4] = after
        rows.append(dict(offset=at, row=site["row"], asset_code=site["asset_code"], month=site["month"],
                         before=have.hex(), after=after.hex(), already_applied=have == after))
    out = bytes(out)
    owned = {s["offset"] + i for s in manifest["sites"] for i in range(4)}
    require(all(a == b for i, (a, b) in enumerate(zip(rost, out)) if i not in owned), "outside-scope ROST bytes changed")
    require(len(out) == len(rost), "ROST size changed")
    return out, dict(owned_ranges=len(rows), owned_bytes=4 * len(rows), sites=rows,
                     changed_bytes=sum(a != b for a, b in zip(rost, out)))


def publish_batch(items):
    sys.path.insert(0, str(ROOT / "tools" / "b765"))
    from u1_repair import publish_batch as publish
    publish(items)


def repair_pack(source: Path, output: Path) -> dict:
    manifest = load_manifest()
    from u1_repair import refuse_links  # noqa: E402  (tools/b765 is put on sys.path by publish_batch)
    refuse_links(source)
    refuse_links(output)
    require(source.resolve() != output.resolve(), "source and output must differ")
    with bump._Image.open(source, writable=False) as image:
        index = bump._parsed_index(image)
        entry = index.entries[ROST_ENTRY]
        require(entry.size == manifest["rost_size"], "main ROST size changed")
        parts = index.sub_extents(entry, 0, entry.size)
        require(len(parts) == 1, "ROST spans more than one pack; needs segmented handling")
        ordinal, offset, length = parts[0]
        size = image.pack_size(ordinal)
        original = image.read_pack(ordinal, 0, size)
        rost = original[offset:offset + length]
        new_rost, rost_receipt = apply_sites(rost, manifest)
        patched = bytearray(original)
        patched[offset:offset + length] = new_rost
        patched = bytes(patched)
        owned = sorted(offset + s["offset"] + i for s in manifest["sites"] for i in range(4))
        ownedset = set(owned)
        outside_same = original[:offset] == patched[:offset] and original[offset + length:] == patched[offset + length:]
        diff = [i for i in range(offset, offset + length) if original[i] != patched[i]]
        require(outside_same and all(i in ownedset for i in diff), "scope proof failed")
        outputs = [(output / PACK_NAMES[ordinal], patched)]
        if ordinal != 0:
            outputs.insert(0, (output / "0", image.read_index_range(0, image.index_size)))
        publish_batch(outputs)
        return {"schema": RECEIPT_SCHEMA, "disc_file": f"vc_53450030/{PACK_NAMES[ordinal]}",
                "pack_before_sha256": sha(original), "pack_after_sha256": sha(patched), "pack_size": size,
                "rost_pack_offset": offset, "rost_size": length, "rost_before_sha256": sha(rost),
                "rost_after_sha256": sha(new_rost), "outside_rost_identical": True,
                "changed_bytes_in_pack": len(diff), "owned_bytes": len(owned),
                "manifest_sha256": sha(MANIFEST.read_bytes()), "rost": rost_receipt, "readback": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--derive", nargs=2, metavar=("ROST_BIN", "MANIFEST_JSON"))
    args = parser.parse_args()
    if args.derive:
        rost = Path(args.derive[0]).read_bytes()
        require(sha(rost) == V05_ROST_SHA256, "--derive needs the v0.5 ROST")
        target = Path(args.derive[1])
        require(not target.exists(), "manifest target exists")
        target.write_text(json.dumps(derive_sites(rost), indent=1) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {target}")
        return
    require(args.input and args.output and args.receipt, "--input, --output and --receipt are required")
    sys.path.insert(0, str(ROOT / "tools" / "b765"))
    receipt = repair_pack(args.input, args.output)
    require(not args.receipt.exists() and args.receipt.resolve().parent != args.output.resolve(), "receipt path must be new and outside the output")
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"receipt": str(args.receipt), "scope_verified": True, "changed_bytes_in_pack": receipt["changed_bytes_in_pack"]}))


if __name__ == "__main__":
    main()

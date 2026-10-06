#!/usr/bin/env python3
"""Field-scoped SOFTDRINK v0.4 commentary repair; writes a separate disc-file set.

Run after jobs adding players.  For a stacked input pass its exact hashes from the previous
repair receipt via --expected-pack-sha256/--expected-xbe-sha256.  No disc image is copied here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_prospect_names as pn
from mod_editor.core.nfl2k5_bump_strength import _sections, _section_for_offset, section_digest

V04_PACK_SHA256 = "01e4e49d47dcc41fb54a3c0404fb988df9fe842bf7efdd46288a50190b233e21"
V04_XBE_SHA256 = "5a9dc534b50c7f13b5124bfff9e39c99f96f62be4cc1de33309895c330c75f29"
FIXED_PACK_SHA256 = "71f89c6c74d45fe2a4bcf81c48bf5d714c9c86ffc17e91d9c37405190888d9d3"
FIXED_XBE_SHA256 = "777377f5a71c11c087d137e489a5189e18cc38de2d11540018076abcd9ddc057"
ROSTER_PACK_OFFSET = 0x393000
ROSTER_RESOURCE_SIZE = 0x90F80


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def scope_receipt(before: bytes, after: bytes, spans: list[tuple[int, int]]) -> dict:
    if len(before) != len(after):
        raise ValueError("repair changed file size")
    restored = bytearray(after)
    for off, size in spans:
        if off < 0 or size < 0 or off + size > len(before):
            raise ValueError("invalid repair scope")
        restored[off:off + size] = before[off:off + size]
    if restored != before:
        raise ValueError("repair changed bytes outside declared scope")
    return {"before_sha256": sha(before), "after_sha256": sha(after), "size": len(after),
            "scope": [{"offset": off, "size": size} for off, size in spans],
            "outside_scope_identical": True,
            "outside_scope_restored_sha256": sha(restored)}


def repair_roster_resource(resource: bytes) -> tuple[bytes, dict]:
    if resource[:4] != b"ROST" or len(resource) not in (rr.RESOURCE_SIZE, 0x92060):
        raise ValueError("not a supported main ROST resource")
    body, receipt = rr.repair_commentary_body(resource[rr.RESOURCE_HEADER_SIZE:])
    after = resource[:rr.RESOURCE_HEADER_SIZE] + body
    spans = [(rr.RESOURCE_HEADER_SIZE + e["offset"], 2) for e in receipt["edits"]]
    return after, {**scope_receipt(resource, after, spans), "commentary": receipt}


def repair_pack_zero(pack: bytes) -> tuple[bytes, dict]:
    """Find outer entry 5; change only its current player-record pbp_id words."""
    if len(pack) < 0xCC:
        raise ValueError("truncated outer archive")
    count, reserved, populated = struct.unpack_from("<3I", pack)
    if not 6 <= count <= 100000 or reserved or not 1 <= populated <= 36:
        raise ValueError("unexpected archive header")
    _name, size, blocks = struct.unpack_from("<3I", pack, 0x9C + 5 * 12)
    offset = blocks * 0x800
    if offset != ROSTER_PACK_OFFSET or size not in (ROSTER_RESOURCE_SIZE, 0x92060):
        raise ValueError("unexpected main roster allocation")
    if offset + size > len(pack):
        raise ValueError("roster escapes pack zero")
    resource, rec = repair_roster_resource(pack[offset:offset + size])
    out = bytearray(pack)
    out[offset:offset + size] = resource
    spans = [(offset + s["offset"], s["size"]) for s in rec["scope"]]
    after = bytes(out)
    return after, {**scope_receipt(pack, after, spans), "disc_file": "vc_53450030/0",
                   "outer_entry": 5, "roster_pack_offset": offset,
                   "record_field": "pbp_id", "record_field_offset": 4,
                   "record_field_size": 2, "roster": rec}


def repair_xbe(payload: bytes) -> tuple[bytes, dict]:
    """Upgrade the existing 27-byte generator cave; no cave or hook allocation changes."""
    boundary = pn.xbe_boundary(payload)
    if boundary is None:
        raise ValueError("expected the SOFTDRINK modern-name cave")
    after, receipt = pn.xbe_apply(payload, boundary)
    immediate = pn._offset(payload, pn.HOST_VA) + 22
    text = _section_for_offset(_sections(payload), immediate)
    spans = [(immediate, 1), (text.header_offset + 36, 20)]
    if section_digest(after, text) != after[text.header_offset + 36:text.header_offset + 56]:
        raise ValueError("XBE text digest does not match repaired section")
    return after, {**scope_receipt(payload, after, spans), "disc_file": "default.xbe",
                   "instruction_va": pn.HOST_VA + 22, "generator": receipt}


def checked_input(path: Path, expected: str | None, canonical: tuple[str, str]) -> bytes:
    data = path.read_bytes()
    allowed = (expected,) if expected is not None else canonical
    if sha(data) not in allowed:
        raise ValueError(f"unexpected input hash for {path.name}: {sha(data)}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-zero", required=True, type=Path)
    parser.add_argument("--xbe", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--expected-pack-sha256")
    parser.add_argument("--expected-xbe-sha256")
    args = parser.parse_args()
    pack = checked_input(args.pack_zero, args.expected_pack_sha256,
                         (V04_PACK_SHA256, FIXED_PACK_SHA256))
    xbe = checked_input(args.xbe, args.expected_xbe_sha256,
                        (V04_XBE_SHA256, FIXED_XBE_SHA256))
    fixed_pack, pack_rec = repair_pack_zero(pack)
    fixed_xbe, xbe_rec = repair_xbe(xbe)
    # Both inputs and all destination files are validated before any write.
    outputs = [(args.out_dir / "vc_53450030" / "0", fixed_pack),
               (args.out_dir / "default.xbe", fixed_xbe)]
    for path, data in outputs:
        if path.resolve() in (args.pack_zero.resolve(), args.xbe.resolve()):
            raise ValueError("output must be a separate copy")
        if path.exists() and path.read_bytes() != data:
            raise ValueError(f"destination exists with different bytes: {path}")
    for path, data in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
        if sha(path.read_bytes()) != sha(data):
            raise ValueError(f"write verification failed: {path}")
    result = {"job": "c1", "files": [pack_rec, xbe_rec], "gameplay_witness": False,
              "composition": "only current player pbp_id words and existing generator immediate/text digest"}
    (args.out_dir / "c1_scope_receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"pack": pack_rec["after_sha256"], "xbe": xbe_rec["after_sha256"],
                      "players_changed": pack_rec["roster"]["commentary"]["players_changed"]}))


if __name__ == "__main__":
    main()

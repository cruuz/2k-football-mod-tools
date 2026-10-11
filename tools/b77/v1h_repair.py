#!/usr/bin/env python3
"""Repair the pinned SOFTDRINK 2K28 v0.6 MyCareer Fast Forward handoff.

Writes a new default.xbe and a byte-scope receipt. The v1f defensive-menu
repair changes playbook resources, so apply this executable to the v1f disc.
No input file is modified. Other executables require a rebuild from source.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tools.b77.g2_repair import read, scope_receipt, sha, write_new

V06_SHA256 = "f67e6fc1cb76c9ea1f1ad504e4a6491ff126483d66a9da8ddb92950bbaf740ba"
REPAIRED_SHA256 = "b544c801652d7060d85e8d8e581eb3d554f2bee9488ebeba68e91bb6c1cdc80c"


def repair(payload: bytes) -> tuple[bytes, dict]:
    digest = sha(payload)
    if digest not in (V06_SHA256, REPAIRED_SHA256):
        raise ValueError(f"unrecognized v0.6 executable: {digest}")
    if space.status(payload) != "applied":
        raise ValueError("invalid allocator seals")
    image = XbeImage(payload)
    code, state = mode.legacy.allocations(payload)
    requests = space._read_scale_directory(payload)
    content, labels = mode.code_for(code["va"], state["va"])
    spans = [(code["raw"], code["size"])]
    buf = bytearray(payload)
    buf[code["raw"]:code["raw"] + code["size"]] = content
    # Relinking the owner's template also moves its native hook destinations.
    # The whole input pin admits the shipped revision, including its hooks.
    for name, va, before, after in mode.sites(code["va"], state["va"], season_birth_dates=True):
        at = image.offset(va, len(after))
        spans.append((at, len(after)))
        buf[at:at + len(after)] = after
    spans += [(space.SCALE_DIRECTORY + 12, 32),
              (space.DIRECTORY + len(space.SCALE_TAG) + 8, 32)]
    space._seal_scaleout(buf, requests)
    for section in _sections(buf):
        lo, size = section.raw_offset, section.raw_size
        if payload[lo:lo + size] != buf[lo:lo + size]:
            at = section.header_offset + 36
            spans.append((at, 20))
            buf[at:at + 20] = section_digest(bytes(buf), section)
    result = bytes(buf)
    if sha(result) != REPAIRED_SHA256 or mode.status(result) != "applied":
        raise ValueError("repair template differs from the validated revision")
    if space.status(result) != "applied" or space._read_scale_directory(result) != requests:
        raise ValueError("allocator postcondition failed")
    allocations = space.layout(payload)["allocations"]
    if space.layout(result)["allocations"] != allocations:
        raise ValueError("an owner allocation moved")
    preserved = []
    for row in allocations:
        if (row["owner"] == mode.OWNER and row["kind"] == "code") or row["owner"] == space.DIRECTORY_OWNER:
            continue
        at, size = row["raw"], row["size"]
        if payload[at:at + size] != result[at:at + size]:
            raise ValueError(f"changed another reservation: {row['owner']}")
        preserved.append(dict(owner=row["owner"], kind=row["kind"],
                              va=hex(row["va"]), size=size, sha256=sha(result[at:at + size])))
    receipt = dict(schema="b77/v1h_native_repair/v1",
                   status="already_applied" if result == payload else "repaired",
                   file="default.xbe", scope=scope_receipt(payload, result, sorted(set(spans))),
                   code=code, primary_state=state, extra_state_va=hex(mode.EXTRA_VA),
                   code_padding=code["va"] + mode.TAG_OFFSET - labels["content_end"],
                   preserved_reservations=preserved,
                   stack_with="v1f defensive-menu playbook repair")
    return result, receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xbe", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    target = args.out_dir / "default.xbe"
    if args.xbe.resolve() in (target.resolve(), args.receipt.resolve()):
        parser.error("input and outputs must be different files")
    result, receipt = repair(read(args.xbe))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_new(target, result)
    write_new(args.receipt, (json.dumps(receipt, indent=2) + "\n").encode())
    print(json.dumps(dict(status=receipt["status"], output=str(target), sha256=sha(result))))


if __name__ == "__main__":
    main()

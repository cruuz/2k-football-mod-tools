#!/usr/bin/env python3
"""Job f5 (beta 77): native repair of the SOFTDRINK 2K28 v0.5 disc files for the Player Card honors page.

Two independent parts; each writes a fixed COPY and a receipt, never the source:

  default.xbe   installs the late allocator owner ``nfl2k5_honors`` (code 2,560 + RW 16 bytes, appended as the LAST late
                owner with ``extend_scaleout``; with the b77 allocator the code goes into the 8 KiB MyCareer footprint
                gap and the RW block to the top of the legacy RW page whenever the image's directory promotes MyCareer,
                otherwise after the other late owners) and its seven retail sites: the card's pad loop (0x320D7B), enter
                action (0x320210), two draw calls (0x320B75, 0x320B7A), the season-awards tail (0x116E5F), the game commit
                (0x1356B4) and the history fold (0x14F168). Run AFTER tools/b77/f4_repair.py: the default input is F4's
                fixed executable (stacked inputs such as i1's v4 need --approved-input-sha256). The bare v0.5
                executable is accepted only with --allow-without-letter-grades. The install must leave every owner that
                reads "applied" in the input "applied" (b77-f5b: defensive_try pins the history engine the fold site
                lies in and tolerates exactly this edit, see nfl2k5_honors.fold_site_edit); otherwise it is refused.
  vc_53450030/0 writes the sourced honors (data/nfl2k5_honors_2026.json) into the main ROST resource's career-stat
                pool (outer entry 5, body at +0x20): only the pool, the players' +0x2C stream pointers and the used
                count change. Slots follow the roster's own years pro, so it runs before or after F12; the default
                accepted inputs are the v0.5 pack and F12's fixed pack.

Every changed byte is proved inside the declared scope (the owner's pages, the seven sites, the .text section
digest, the allocator's own directory and seals; or the ROST pool, pointers and used count). Deterministic and
idempotent: a fixed file run again is reported as already repaired and copied unchanged. Unknown inputs are refused
unless their SHA-256 is approved with --approved-input-sha256.

  python3 tools/b77/f5_repair.py --xbe F4.xbe OUT.xbe --pack0 PACK0 OUT_PACK0 --receipt f5_receipt.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_honors as honors  # noqa: E402
from mod_editor.core import nfl2k5_honors_history as hh  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core.nfl2k5_bump_strength import _sections  # noqa: E402

TOOL = "tools/b77/f5_repair.py"
SCHEMA = "nfl2k5_b77_f5_repair/v1"
V05_XBE_SHA256 = "2b0fbbbb89b5c72aaed7c454bf6e78dd2c97f1e417e2d761e515907ed81471ab"
F4_XBE_SHA256 = "78b99479d7c52b6b3f9e380b9734b3a801fae4b8f83a341449959ba4fdb8579b"
V05_PACK0_SHA256 = "b2c48dd3a3e8c7b5e75a596f83b9f6ef64e6c7c00b613611ed5e9e88b790fd72"
F12_PACK0_SHA256 = "f47a9bf5063dd13127869c95c260ac50be5ca89a571daa3795ff037eb154d57f"
ROST_OUTER_INDEX, OUTER_ENTRY_TABLE, RESOURCE_HEADER, BODY_SIZE = 5, 0x9C, 0x20, 0x90F60


class RepairRefused(ValueError):
    """The input is not one this writer owns; nothing was written."""


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RepairRefused(message)


def changed_ranges(before: bytes, after: bytes) -> list[list[int]]:
    ranges, start = [], None
    for i, (a, b) in enumerate(zip(before, after)):
        if a != b and start is None:
            start = i
        elif a == b and start is not None:
            ranges.append([start, i])
            start = None
    if start is not None:
        ranges.append([start, len(before)])
    return ranges


def _inside(ranges, scope) -> bool:
    return all(any(lo <= a and b <= hi for lo, hi in scope) for a, b in ranges)


# --- default.xbe -----------------------------------------------------------------------------------------------------
def xbe_scope(payload: bytes) -> list[tuple[int, int, str]]:
    """File ranges the honors install may change: owner pages, sites, .text digest, allocator directory and seals."""

    found = honors.allocations(payload)
    out = [(r["raw"], r["raw"] + r["size"], f"owner {r['kind']} page") for r in found.values()]
    for label, va, before, _after in honors.sites(found["code"]["va"]):
        off = va - 0x10000          # .text: file offset = VA - 0x10000
        out.append((off, off + len(before), f"site {label}"))
    for s in _sections(payload):
        out.append((s.header_offset + 36, s.header_offset + 56, f"section digest {s.index}"))
    out.append((space.SCALE_DIRECTORY, space.SCALE_DIRECTORY + space.PAGE, "allocator directory page"))
    out.append((space.DIRECTORY, space.LIB_COPY, "allocator header directory"))
    out.append((space.META_START, space.META_START + 56 * len(space._scale_regions()), "scale-out section descriptors"))
    return out


# Owners whose installation reads the history engine or shares the late-owner run with this one (b77-f5b).
COEXISTING = ("nfl2k5_defensive_try", "nfl2k5_letter_grades", "nfl2k5_letter_grades_progress", "nfl2k5_k128",
              "nfl2k5_period_goalposts", "nfl2k5_team_column", "nfl2k5_my_career", "nfl2k5_progression")


def owner_states(payload: bytes) -> dict[str, str]:
    import importlib
    out = {}
    for name in COEXISTING:
        try:
            out[name] = str(importlib.import_module(f"mod_editor.core.{name}").status(payload))
        except Exception as exc:  # a status that cannot be read is reported, never assumed applied
            out[name] = "unreadable:" + type(exc).__name__
    return out


def repair_xbe(source: bytes, *, approved=(), allow_without_letter_grades=False) -> tuple[bytes, dict]:
    from mod_editor.core import nfl2k5_letter_grades as letter_grades
    state = honors.status(source)
    require(state in ("retail", "applied"), f"the executable's honors state is {state}")
    if state == "applied":
        return source, {"status": "already_repaired", "sha256": sha(source)}
    digest = sha(source)
    known = {F4_XBE_SHA256: "F4 fixed v0.5 executable"}
    if allow_without_letter_grades:
        known[V05_XBE_SHA256] = "v0.5 executable (without F4)"
    require(digest in known or digest in approved,
            f"unexpected default.xbe {digest}: run tools/b77/f4_repair.py first, or approve this stacked input")
    lg = letter_grades.status(source)
    require(lg == "applied" or allow_without_letter_grades,
            f"letter grades are {lg}: apply F4 first (the honors owner is placed after it)")
    before_states = owner_states(source)
    fixed, receipt = honors.apply(source)
    after_states = owner_states(fixed)
    broken = sorted(name for name, state in before_states.items() if state == "applied" and after_states[name] != "applied")
    require(not broken, f"the install broke other owners: {broken}")
    scope = xbe_scope(fixed)
    ranges = changed_ranges(source, fixed)
    require(len(fixed) == len(source), "the executable size changed")
    require(_inside(ranges, [(lo, hi) for lo, hi, _n in scope]), "a change falls outside the declared scope")
    again, again_receipt = honors.apply(fixed)
    require(again == fixed and again_receipt["already_applied"], "the install is not idempotent")
    return fixed, {"status": "repaired", "input": known.get(digest, "approved stacked input"),
                   "before_sha256": digest, "after_sha256": sha(fixed), "changed_bytes": sum(b - a for a, b in ranges),
                   "changed_ranges": [[hex(a), hex(b)] for a, b in ranges],
                   "declared_scope": [[hex(lo), hex(hi), name] for lo, hi, name in scope],
                   "letter_grades": letter_grades.status(fixed), "honors": honors.status(fixed),
                   "coexisting_owners": {"before": before_states, "after": after_states},
                   "allocations": {k: {"va": hex(v["va"]), "raw": hex(v["raw"]), "size": v["size"]}
                                   for k, v in honors.allocations(fixed).items()},
                   "sites": receipt["sites"]}


# --- vc_53450030/0 ---------------------------------------------------------------------------------------------------
def locate_rost(pack: bytes) -> int:
    count, reserved, populated = struct.unpack_from("<3I", pack)
    require(6 <= count <= 100000 and not reserved and 1 <= populated <= 36, "unexpected outer archive header")
    _name, size, blocks = struct.unpack_from("<3I", pack, OUTER_ENTRY_TABLE + ROST_OUTER_INDEX * 12)
    offset = blocks * 0x800
    require(offset + size <= len(pack) and pack[offset:offset + 4] == b"ROST", "outer entry 5 is not a ROST resource")
    require(size >= RESOURCE_HEADER + BODY_SIZE, "the ROST resource is smaller than the main roster")
    return offset + RESOURCE_HEADER


def repair_pack(source: bytes, data: dict, *, approved=()) -> tuple[bytes, dict]:
    start = locate_rost(source)
    body = source[start:start + BODY_SIZE]
    fixed_body, receipt = hh.apply_body(body, data)
    if not receipt["changed"]:
        return source, {"status": "already_repaired", "sha256": sha(source), "already_present": receipt["already_present"]}
    digest = sha(source)
    known = {V05_PACK0_SHA256: "v0.5 PACK0", F12_PACK0_SHA256: "F12 fixed v0.5 PACK0"}
    require(digest in known or digest in approved, f"unexpected vc_53450030/0 {digest}: approve this stacked input")
    fixed = source[:start] + fixed_body + source[start + BODY_SIZE:]
    ranges = changed_ranges(source, fixed)
    require(all(start <= a and b <= start + BODY_SIZE for a, b in ranges), "a change falls outside the ROST body")
    again, again_receipt = hh.apply_body(fixed_body, data)
    require(again == fixed_body and not again_receipt["changed"], "the honors write is not idempotent")
    return fixed, {"status": "repaired", "input": known.get(digest, "approved stacked input"), "before_sha256": digest,
                   "after_sha256": sha(fixed), "rost_body_offset": hex(start),
                   "rost_body_before_sha256": sha(body), "rost_body_after_sha256": sha(fixed_body),
                   "changed_bytes": sum(b - a for a, b in ranges),
                   "changed_span": [hex(ranges[0][0]), hex(ranges[-1][1])] if ranges else None,
                   "scope": "ROST career-stat pool, players' +0x2C stream pointers, root +0x40 used count",
                   "added": receipt["added"], "already_present": receipt["already_present"],
                   "skipped": receipt["skipped"], "players": receipt["players"],
                   "pool_used_before": receipt["used_before"], "pool_used_after": receipt["used_after"],
                   "pool_capacity": receipt["capacity"], "data_sha256": sha(json.dumps(data, sort_keys=True).encode())}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--xbe", nargs=2, type=Path, metavar=("SOURCE", "OUTPUT"))
    parser.add_argument("--pack0", nargs=2, type=Path, metavar=("SOURCE", "OUTPUT"))
    parser.add_argument("--data", type=Path, default=hh.DEFAULT_DATA)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--approved-input-sha256", action="append", default=[])
    parser.add_argument("--allow-without-letter-grades", action="store_true")
    args = parser.parse_args(argv)
    if not (args.xbe or args.pack0):
        parser.error("choose --xbe and/or --pack0")
    receipt = {"schema": SCHEMA, "tool": TOOL}
    outputs = []
    try:
        if args.xbe:
            source = args.xbe[0].read_bytes()
            require(len(source) <= 16 * 1024 * 1024, "choose default.xbe")
            fixed, receipt["default.xbe"] = repair_xbe(source, approved=set(args.approved_input_sha256),
                                                       allow_without_letter_grades=args.allow_without_letter_grades)
            outputs.append((args.xbe[1], fixed))
        if args.pack0:
            data = hh.load(args.data)
            source = args.pack0[0].read_bytes()
            fixed, receipt["vc_53450030/0"] = repair_pack(source, data, approved=set(args.approved_input_sha256))
            receipt["vc_53450030/0"]["data_file"] = str(args.data)
            outputs.append((args.pack0[1], fixed))
    except RepairRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    for path, payload in outputs:
        require(not path.exists(), f"{path} exists; choose a new output")
        with path.open("xb") as stream:
            stream.write(payload)
    args.receipt.write_text(json.dumps(receipt, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: (v.get("status"), v.get("after_sha256", v.get("sha256"))) if isinstance(v, dict) else v
                      for k, v in receipt.items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

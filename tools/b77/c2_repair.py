#!/usr/bin/env python3
"""Native C2 repair of the v0.5 disc: no player is announced as "double zero", and the numbers called are the numbers worn.

Beta 77, job c2 (Noah, 2026-10-07: "the 00 is on the replays").  Reads three disc files (``vc_53450030/0``,
``vc_53450030/E``, ``vc_53450030/F``), writes repaired copies of them and a receipt.  No input is modified and no disc image is
opened.  The change is the Studio's ``nfl2k5_commentary_final`` pass, applied to exactly the bytes this job owns:

* **pack E and pack F, the ESPN 25th Anniversary team-season rosters** (one-team ROST resources found by content in the outer
  directory read from pack 0): the u16 play-by-play id at record +0x04 of populated players.  v0.5 holds the recorded
  "double zero" id 9100 on 144 players (and another 8 ids with no recorded clip, and 5 numbers that are not the stored
  uniform number), copied from the main roster of the day.  The rule is c1's (``nfl2k5_roster_records.commentary_id``).
* **pack 0, the 35 shared historic rosters** the retail Anniversary moments use: the same u16, 1,271 players whose stored id
  still names the retail placeholder's number instead of the real player's.
* **pack 0, outer entry 3, the ``players`` commentary cue table (SPCI)**: the one id 9100 in its sorted id array becomes 9199
  (low byte 0x8C -> 0xEF at table offset 0xB2E, pack offset 0x3121BE), so that the recorded "double zero" clips cannot be
  reached by *any* stored id.  Older saves, franchises and saved weekly highlights embed their own roster copies that no disc
  repair touches; with the id gone from the table the game's resolver falls back to the live uniform number for them.

The main roster resource and ``default.xbe`` are not touched (c1 owns the former).  Everything else in the three files is
identical (checked by a scope receipt).  Sizes are unchanged.

The packs are shared with other b77 jobs.  Stacked input: pass that job's output hashes with
``--approved-input-sha256 <hash>`` (repeatable).  An input that already carries the repair is a recorded no-op.  A resource
that is not a readable roster, a cue table that is not the pinned retail or applied table, or an unknown pack hash is refused.
EXPERIMENTAL / UNWITNESSED in a played game.

  python3 tools/b77/c2_repair.py --pack0 P0 --pack-e PE --pack-f PF --out-dir OUT [--native-proof --xbe XBE]
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
for _entry in (str(ROOT), str(ROOT / "tools")):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)
from mod_editor.core import platform_compat
from mod_editor.core import nfl2k5_commentary_final as final  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from nfl_outer import ALIGNMENT, HEADER_SIZE, PACK_SLOT_COUNT  # noqa: E402

TOOL = "tools/b77/c2_repair.py"
SCHEMA = "nfl2k5_b77_c2_repair/v1"
PACK_NAMES = {0: "0", 14: "E", 15: "F"}
V05_PACK_SHA256 = {0: "b2c48dd3a3e8c7b5e75a596f83b9f6ef64e6c7c00b613611ed5e9e88b790fd72",
                   14: "88bb34f38971cd43636e1036c9bb4b21fee91979bbbebf4dac036f3887da559b",
                   15: "e295e5f186289ce8ce8ccdab7816cc4ed8944f1379d13871add76fe7b343ed43"}
# the f12 (years pro) outputs that this repair composes with, in either order
F12_PACK_SHA256 = {14: "22b0b8c4364223aaf1d8b78603ec8980cc494563926cc958b3df551b27c3ed66",
                   15: "f17a06080711e59179e0f3f78b6c63db3d9ed49baae3bf4a5afc788ec46119c1"}
# this repair's own outputs on the pinned v0.5 packs (an exact replay is a recorded no-op)
C2_PACK_SHA256 = {0: "a609c6c8b1fe0ec83f0bb57a7bb5358ecbc03ac46ef35f163bb505ae7f2fc018",
                  14: "1245cbeffe8dd818d1c580ad04c4f549f6a9214bc9b447092f47c37ca0e98c23",
                  15: "33e0693f4272efb094b64f2f39576bb2e8c610ae2471f7ae6bb0284513d04428"}
CHUNK = 8 * 1024 * 1024
TEAM_SIZE_LIMIT = final.MAX_RESOURCE


class RepairRefused(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RepairRefused(message)


def open_read(path: Path) -> int:
    return os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    fd = open_read(path)
    try:
        while True:
            block = os.read(fd, CHUNK)
            if not block:
                return digest.hexdigest()
            digest.update(block)
    finally:
        os.close(fd)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pread(fd: int, size: int, offset: int) -> bytes:
    data = platform_compat.pread(fd, size, offset)
    require(len(data) == size, f"short read of {size} bytes at 0x{offset:x}")
    return data


def read_directory(pack0_head: bytes) -> tuple[list[tuple[int, int, int, int]], list[tuple[int, int]]]:
    """(entries, packs): entries are (index, name_id, virtual_offset, size); packs are (virtual_start, size) by ordinal."""
    require(len(pack0_head) >= HEADER_SIZE, "truncated outer archive header")
    count, reserved, populated = struct.unpack_from("<3I", pack0_head)
    require(6 <= count <= 100000 and not reserved and 1 <= populated <= PACK_SLOT_COUNT, "unexpected outer archive header")
    require(len(pack0_head) >= HEADER_SIZE + 12 * count, "the pack 0 bytes do not cover the outer directory")
    blocks = struct.unpack_from(f"<{PACK_SLOT_COUNT}I", pack0_head, 12)
    packs, virtual = [], 0
    for ordinal in range(populated):
        packs.append((virtual, blocks[ordinal] * ALIGNMENT))
        virtual += blocks[ordinal] * ALIGNMENT
    entries = []
    for index in range(count):
        name_id, size, offset_blocks = struct.unpack_from("<III", pack0_head, HEADER_SIZE + 12 * index)
        entries.append((index, name_id, offset_blocks * ALIGNMENT, size))
    return entries, packs


def plan_edits(paths: dict[int, Path]) -> tuple[dict[int, list[tuple[int, bytes]]], dict]:
    """The exact (offset, new bytes) writes per pack, from the unmodified inputs. Nothing is written."""
    fds = {ordinal: open_read(path) for ordinal, path in paths.items()}
    try:
        head = pread(fds[0], HEADER_SIZE, 0)
        entries, packs = read_directory(head + pread(fds[0], 12 * struct.unpack_from("<I", head)[0], HEADER_SIZE))
        for ordinal, path in paths.items():
            require(ordinal < len(packs) and path.stat().st_size == packs[ordinal][1],
                    f"pack {PACK_NAMES[ordinal]} is not the size the outer directory declares")
        edits: dict[int, list[tuple[int, bytes]]] = {ordinal: [] for ordinal in paths}
        resources, scanned = [], 0
        for index, name_id, virtual, size in entries:
            for ordinal, (start, span) in enumerate(packs):
                if ordinal in fds and start <= virtual and virtual + size <= start + span:
                    break
            else:
                continue
            local = virtual - start
            if not rr.RESOURCE_HEADER_SIZE < size < TEAM_SIZE_LIMIT or pread(fds[ordinal], 4, local) != b"ROST":
                continue
            scanned += 1
            raw = pread(fds[ordinal], size, local)
            try:
                _fixed, receipt = rr.repair_commentary_resource(raw)
            except (ValueError, IndexError, KeyError, struct.error) as exc:
                raise RepairRefused(f"outer entry {index}: not a readable roster ({exc})") from exc
            if not receipt["players_changed"]:
                continue
            for edit in receipt["edits"]:
                edits[ordinal].append((local + rr.RESOURCE_HEADER_SIZE + edit["offset"], struct.pack("<H", edit["after"])))
            resources.append({"outer_entry": index, "name_id": name_id, "pack": PACK_NAMES[ordinal], "pack_offset": local,
                              "size": size, "players_changed": receipt["players_changed"],
                              "before_sha256": sha(raw), "after_sha256": sha(_fixed),
                              "ids": [[e["name"], e["jersey"], e["before"], e["after"]] for e in receipt["edits"]]})
        # the commentary cue table: outer entry 3 of pack 0 (found by content inside the entry)
        require(len(entries) > final.SPCI_OUTER_INDEX, "the outer directory has no entry 3")
        _i, name_id, virtual, size = entries[final.SPCI_OUTER_INDEX]
        require(packs[0][0] <= virtual and virtual + size <= packs[0][0] + packs[0][1], "outer entry 3 is not inside pack 0")
        entry3 = pread(fds[0], size, virtual - packs[0][0])
        at = final.find_table(entry3)
        table, cue = final.patch_table(entry3[at: at + final.SPCI_SIZE])
        if not cue["already_applied"]:
            offset = virtual - packs[0][0] + at + final.EXPECTED_ID_OFFSET
            edits[0].append((offset, table[final.EXPECTED_ID_OFFSET: final.EXPECTED_ID_OFFSET + 2]))
        cue = {**cue, "outer_entry": final.SPCI_OUTER_INDEX, "name_id": name_id,
               "pack_offset_of_table": virtual - packs[0][0] + at,
               "pack_offset_of_id": virtual - packs[0][0] + at + final.EXPECTED_ID_OFFSET}
        return edits, {"resources": resources, "rosters_scanned": scanned, "cue": cue}
    finally:
        for fd in fds.values():
            os.close(fd)


def copy_with_edits(source: Path, target: Path, edits: list[tuple[int, bytes]]) -> dict:
    """Copy ``source`` to a NEW file, apply the edits, and prove the copy differs from the source only inside them."""
    require(not target.exists(), f"refusing to replace an existing output: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    src, dst = open_read(source), os.open(target, os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o644)
    try:
        position = 0
        while True:
            block = os.read(src, CHUNK)
            if not block:
                break
            written = 0
            while written < len(block):
                written += os.write(dst, block[written:])
            position += len(block)
        for offset, data in sorted(edits):
            require(platform_compat.pwrite(dst, data, offset) == len(data), "short write")
        os.fsync(dst)
        # scope proof: stream both files; the copy must equal the source with exactly the declared edits applied
        declared = sorted(edits)
        digest_in, digest_out = hashlib.sha256(), hashlib.sha256()
        changed, cursor = 0, 0
        os.lseek(src, 0, os.SEEK_SET)
        os.lseek(dst, 0, os.SEEK_SET)
        while True:
            a, b = os.read(src, CHUNK), os.read(dst, CHUNK)
            require(len(a) == len(b), "output size differs from the input")
            if not a:
                break
            digest_in.update(a)
            digest_out.update(b)
            if a != b:
                expected = bytearray(a)
                for offset, data in declared:
                    lo, hi = max(offset, cursor), min(offset + len(data), cursor + len(a))
                    if lo < hi:
                        changed += sum(x != y for x, y in zip(a[lo - cursor:hi - cursor], b[lo - cursor:hi - cursor]))
                        expected[lo - cursor:hi - cursor] = data[lo - offset:hi - offset]
                require(bytes(expected) == b, f"bytes changed outside the declared edits near 0x{cursor:x}")
            cursor += len(a)
        return {"before_sha256": digest_in.hexdigest(), "after_sha256": digest_out.hexdigest(), "size": cursor,
                "declared_edits": len(edits), "declared_bytes": sum(len(d) for _o, d in edits),
                "changed_bytes": changed, "outside_scope_identical": True}
    finally:
        os.close(src)
        os.close(dst)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pack0", type=Path, required=True, help="vc_53450030/0")
    parser.add_argument("--pack-e", type=Path, required=True, help="vc_53450030/E")
    parser.add_argument("--pack-f", type=Path, required=True, help="vc_53450030/F")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--approved-input-sha256", action="append", default=[],
                        help="sha256 of a composed input pack (another job's output); repeatable")
    parser.add_argument("--dry-run", action="store_true", help="plan and print the receipt; write nothing")
    parser.add_argument("--native-proof", action="store_true",
                        help="run the game's resolver (Unicorn) over the repaired records; needs --xbe")
    parser.add_argument("--xbe", type=Path, help="the disc's default.xbe, only for --native-proof")
    args = parser.parse_args()
    paths = {0: args.pack0, 14: args.pack_e, 15: args.pack_f}
    out_dir = args.out_dir.resolve()
    for path in paths.values():
        require(path.resolve().parent != out_dir and path.is_file(), f"input missing or the output directory is the input's: {path}")
    known = {ordinal: {V05_PACK_SHA256[ordinal]} | ({F12_PACK_SHA256[ordinal]} if ordinal in F12_PACK_SHA256 else set())
             | ({C2_PACK_SHA256[ordinal]} if C2_PACK_SHA256.get(ordinal) else set()) for ordinal in paths}
    inputs = {}
    for ordinal, path in paths.items():
        digest = sha_file(path)
        composed = digest not in known[ordinal]
        require(not composed or digest in args.approved_input_sha256,
                f"unexpected pack {PACK_NAMES[ordinal]} sha256 {digest}; pass --approved-input-sha256 for an exact composed input")
        inputs[ordinal] = digest
    edits, plan = plan_edits(paths)
    receipt = {"schema": SCHEMA, "tool": TOOL, "job": "c2", "gameplay_witness": False,
               "state": "applied" if any(edits.values()) else "already_applied",
               "approved_composed_input": [PACK_NAMES[o] for o, d in inputs.items() if d not in known[o]],
               "input_sha256": {PACK_NAMES[o]: d for o, d in inputs.items()},
               "rosters_scanned": plan["rosters_scanned"], "cue": plan["cue"],
               "players_changed": sum(r["players_changed"] for r in plan["resources"]),
               "resources_changed": len(plan["resources"]), "resources": plan["resources"], "files": {}}
    if args.dry_run:
        receipt["files"] = {PACK_NAMES[o]: {"declared_edits": len(e)} for o, e in edits.items()}
        print(json.dumps({k: v for k, v in receipt.items() if k != "resources"}, indent=2))
        return 0
    for ordinal, path in paths.items():
        target = out_dir / "vc_53450030" / PACK_NAMES[ordinal]
        proof = copy_with_edits(path, target, edits[ordinal])
        receipt["files"][PACK_NAMES[ordinal]] = {"disc_file": f"vc_53450030/{PACK_NAMES[ordinal]}", **proof,
                                                 "edit_spans": [[o, len(d)] for o, d in sorted(edits[ordinal])]}
    # read-back: the repaired packs hold no pending edit
    again, check = plan_edits({ordinal: out_dir / "vc_53450030" / PACK_NAMES[ordinal] for ordinal in paths})
    require(not any(again.values()) and check["cue"]["already_applied"], "read-back still finds pending edits")
    if args.native_proof:
        require(args.xbe is not None, "--native-proof needs --xbe")
        sys.path.insert(0, str(ROOT / "tests" / "mod_editor"))
        import c2_native_probe  # noqa: PLC0415
        receipt["native_proof"] = c2_native_probe.audit_packs({o: out_dir / "vc_53450030" / PACK_NAMES[o] for o in paths},
                                                              args.xbe)
        require(receipt["native_proof"]["double_zero_players"] == 0 and receipt["native_proof"]["wrong_number_players"] == 0,
                "the native resolver still finds double-zero or wrong-number players")
    (out_dir / "c2_scope_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"state": receipt["state"], "players_changed": receipt["players_changed"],
                      "resources_changed": receipt["resources_changed"],
                      "after_sha256": {k: v["after_sha256"] for k, v in receipt["files"].items()}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

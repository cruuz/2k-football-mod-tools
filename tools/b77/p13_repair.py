#!/usr/bin/env python3
"""Native PLAY repair for SOFTDRINK 2K28 v0.5: end-arounds, RB screens and back routes.

Input is one extracted fixed-size PACK0 PLAY entry, never a disc or archive.
Every offensive formation-play link is passed through the Studio's own repair
rules (``nfl2k5_playbook_lint.normalize_offense_play``), the same code the
complete-offense compiler now runs, so a Studio rebuild and this repair agree
play for play. Only plays whose eleven chains reproduce a SOFTDRINK template
byte for byte are rebuilt; everything else stays exact.

Owned bytes per entry: the node-count word (+0x40 of the body), new chains
appended into the verified zero tail of the node pool, and the descriptor and
relative chain pointer (8 bytes) of each changed assignment slot. Every other
byte is proved identical (outside-scope SHA-256). Unknown input hashes are
refused unless the integrator passes the explicit stacked input hash; the
template, zero-tail and native-validator guards still apply. Deterministic and
idempotent; outputs and receipts are created exclusively.

No gameplay witness is claimed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import nfl2k5_play_codec as codec
from mod_editor.core import nfl2k5_play_library as lib
from mod_editor.core import nfl2k5_playbook_inspector as inspector
from mod_editor.core import nfl2k5_playbook_lint as lint
from mod_editor.core.nfl2k5_formation_play_writer import NODE_CAPACITY

SCHEMA = "b77.p13.play-execution-repair.v1"
MANIFEST = Path(__file__).with_name("p13_repair_manifest.json")
HEADER = inspector.RESOURCE_HEADER_SIZE
RESOURCE_SIZE = inspector.RESOURCE_HEADER_SIZE + inspector.BODY_SIZE


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _ranges(before: bytes, after: bytes, scopes):
    merged = []
    for start, end, label in sorted(scopes):
        if merged and start < merged[-1][1]:
            raise ValueError("Overlapping repair scopes")
        merged.append((start, end, label))
    old_out, new_out, cursor = hashlib.sha256(), hashlib.sha256(), 0
    rows = []
    for start, end, label in merged:
        old_out.update(before[cursor:start]); new_out.update(after[cursor:start])
        rows.append(dict(file_offset=hex(start), size=end - start, label=label,
                         before_sha256=sha(before[start:end]), after_sha256=sha(after[start:end])))
        cursor = end
    old_out.update(before[cursor:]); new_out.update(after[cursor:])
    if len(before) != len(after) or old_out.digest() != new_out.digest():
        raise ValueError("Unexpected byte outside the declared repair scopes")
    return rows, old_out.hexdigest()


def plan(payload: bytes) -> dict:
    """{play index: (new authored chains, receipts, formations)} for every rebuilt play."""
    out: dict[int, tuple] = {}
    for view in lint.resource_views(payload):
        fixed, receipts = lint.normalize_offense_play(view.positions, view.codes, view.chains)
        if fixed is None:
            continue
        new_bytes = lint._as_bytes(fixed)
        if view.play in out:
            if out[view.play][0] != new_bytes:
                raise ValueError(f"Play {view.play} is shared by formations that need different repairs")
            out[view.play][2].append(view.formation)
            continue
        out[view.play] = (new_bytes, receipts, [view.formation], view.play_name)
    return out


def _repair(payload: bytes) -> tuple[bytes, dict]:
    if len(payload) != RESOURCE_SIZE:
        raise ValueError("Expected one fixed-size PLAY resource")
    book = inspector.parse_playbook_resource(payload)
    body = payload[HEADER:]
    edits = plan(payload)
    result = bytearray(payload)
    # Existing complete assignment chains may be shared (exact start and length).
    existing: dict[bytes, int] = {}
    for p in book.plays:
        for a in p.assignments:
            start = inspector.NODE_BASE + a.chain_start_index * inspector.NODE_SIZE
            raw = body[start:start + a.declared_length * inspector.NODE_SIZE]
            existing.setdefault(raw, start)
    cursor = book.node_count
    appended: dict[bytes, int] = {}
    scopes = []
    rows = []
    for play_index in sorted(edits):
        new_chains, receipts, formations, name = edits[play_index]
        flags, old_assignments = lib.play_chains(body, play_index)
        changed = [s for s in range(11) if [bytes(n) for n in old_assignments[s][1]] != new_chains[s]]
        if not changed:
            continue
        for s in range(11):
            canonical = codec.build_descriptor(flags, old_assignments, s, old_assignments[s][0] >> 24)
            if canonical != old_assignments[s][0]:
                raise ValueError(f"Play {play_index} slot {s} has noncanonical descriptor bits")
        starts = {}
        for s in changed:
            raw = b"".join(new_chains[s])
            if raw in existing:
                starts[s] = existing[raw]
                continue
            if raw not in appended:
                need = len(new_chains[s])
                if cursor + need > NODE_CAPACITY:
                    raise ValueError("No zero node-pool capacity left for the repair")
                start = inspector.NODE_BASE + cursor * inspector.NODE_SIZE
                if any(result[HEADER + start:HEADER + start + len(raw)]):
                    raise ValueError("Unexpected nonzero node-pool allocation tail")
                result[HEADER + start:HEADER + start + len(raw)] = raw
                appended[raw] = start
                cursor += need
            starts[s] = appended[raw]
        assignments = [(d, list(n)) for d, n in old_assignments]
        for s in changed:
            assignments[s] = ((old_assignments[s][0] & 0xFF000000) | len(new_chains[s]), list(new_chains[s]))
        for _ in range(2):
            for s in changed:
                assignments[s] = (codec.build_descriptor(flags, assignments, s, old_assignments[s][0] >> 24),
                                  assignments[s][1])
        codec.validate_sync(assignments)
        problem = codec.validate_play(flags, assignments)
        if problem:
            raise ValueError(f"Native validator port rejects repaired play {play_index}: {problem}")
        slot_rows = []
        for s in changed:
            field = inspector.PLAY_BASE + play_index * inspector.PLAY_SIZE + 8 + s * 8
            struct.pack_into("<I", result, HEADER + field, assignments[s][0])
            struct.pack_into("<i", result, HEADER + field + 4, starts[s] - (field + 4) + 1)
            scopes.append((HEADER + field, HEADER + field + 8,
                           f"play {play_index} slot {s} descriptor and relative chain pointer"))
            slot_rows.append(dict(slot=s, before_descriptor=hex(old_assignments[s][0]),
                                  after_descriptor=hex(assignments[s][0]),
                                  before_nodes=[bytes(n).hex() for n in old_assignments[s][1]],
                                  after_nodes=[n.hex() for n in new_chains[s]],
                                  chain_start_offset=hex(starts[s]),
                                  shared_existing_chain=b"".join(new_chains[s]) in existing))
        rows.append(dict(play_index=play_index, play=name, formations=formations, rules=receipts, slots=slot_rows))
    if cursor != book.node_count:
        struct.pack_into("<I", result, HEADER + 0x40, cursor)
        scopes.extend([(HEADER + 0x40, HEADER + 0x44, "node pool count"),
                       (HEADER + inspector.NODE_BASE + book.node_count * inspector.NODE_SIZE,
                        HEADER + inspector.NODE_BASE + cursor * inspector.NODE_SIZE,
                        "rebuilt assignment chains in the verified zero tail")])
    final = bytes(result)
    parsed = inspector.parse_playbook_resource(final)
    if inspector.menu_link_problems(final) != inspector.menu_link_problems(payload):
        raise ValueError("Unexpected PLAY menu problem after the repair")
    for row in rows:
        for srow in row["slots"]:
            chain = parsed.assignment_chain(parsed.plays[row["play_index"]].assignments[srow["slot"]])
            if [n.raw_hex for n in chain.nodes] != srow["after_nodes"]:
                raise ValueError("Repaired assignment did not reparse exactly")
    for p in parsed.plays:
        f2, chains = lib.play_chains(final[HEADER:], p.index)
        problem = codec.validate_play(f2, chains)
        if problem and not codec.validate_play(*lib.play_chains(body, p.index)):
            raise ValueError(f"Play {p.index} no longer validates: {problem}")
    if plan(final):
        raise ValueError("Repair is not idempotent")
    receipt_scopes, outside = _ranges(payload, final, scopes) if scopes else ([], sha(payload))
    return final, dict(plays=rows, appended_chains=len(appended), old_node_count=book.node_count,
                       new_node_count=cursor, scopes=receipt_scopes, outside_scope_sha256=outside)


def repair_resource(payload: bytes, entry_id: int, *, expected_input_sha256: str | None = None):
    manifest = json.loads(MANIFEST.read_text())
    row = manifest["books"].get(str(entry_id))
    if row is None:
        raise ValueError("Unknown SOFTDRINK PLAY entry id")
    before = sha(payload)
    accepted = {expected_input_sha256} if expected_input_sha256 else {row["before_sha256"], row["after_sha256"]}
    if before not in accepted:
        raise ValueError("Unexpected PLAY input SHA256")
    result, receipt = _repair(payload)
    if before in (row["before_sha256"], row["after_sha256"]) and sha(result) != row["after_sha256"]:
        raise ValueError("Known PLAY repair output SHA256 mismatch")
    receipt.update(schema=SCHEMA, disc_file="media/pack0.bin", pack0_entry_id=entry_id, book=row["book"],
                   size=len(payload), before_sha256=before, after_sha256=sha(result),
                   status="applied" if result != payload else "already_applied",
                   changed_bytes=sum(a != b for a, b in zip(payload, result)),
                   outside_scope_identical=True, gameplay_witness=False)
    return result, receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--entry-id", required=True, type=int)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--expected-input-sha256")
    args = parser.parse_args()
    if args.source.is_symlink() or not args.source.is_file():
        parser.error("Source must be a regular non-symlink extracted PLAY resource")
    if (args.output.exists() or args.output.is_symlink() or args.receipt.exists() or args.receipt.is_symlink()
            or args.output.absolute() == args.receipt.absolute()):
        parser.error("Choose distinct new output and receipt paths")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(args.source, flags)
    with os.fdopen(fd, "rb") as stream:
        payload = stream.read(RESOURCE_SIZE + 1)
    try:
        result, receipt = repair_resource(payload, args.entry_id, expected_input_sha256=args.expected_input_sha256)
    except (ValueError, KeyError) as exc:
        parser.error(str(exc))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(args.output, flags, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(result)
    with args.receipt.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    print(json.dumps({k: receipt[k] for k in ("status", "before_sha256", "after_sha256", "changed_bytes")}))


if __name__ == "__main__":
    main()

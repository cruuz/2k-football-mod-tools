#!/usr/bin/env python3
"""Bounded PLAY-resource repair for authored deep-back flats in SOFTDRINK v0.4.

Resources are extracted PACK0 entries, never archives or discs. All 69 shipped
books are pinned. Only unsafe HB/FB Start->Flat assignments in the modern bank
receive an ordinary straight approach; stock Anniversary aliases stay exact.
An integrator may supply an explicit whole-resource hash for a stacked input;
the original two-node assignment geometry and zero allocation tail still guard
our byte ranges. Output creation is exclusive and input is never overwritten.
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
from mod_editor.core.nfl2k5_formation_play_writer import NODE_CAPACITY

MANIFEST = Path(__file__).with_name("d2b_checkdown_routes_manifest.json")


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _ranges(before: bytes, after: bytes, scopes):
    merged = []
    for start, end, label in sorted(scopes):
        if merged and start < merged[-1][1]:
            raise ValueError("Overlapping checkdown repair scopes")
        merged.append((start, end, label))
    old_out, new_out, cursor = hashlib.sha256(), hashlib.sha256(), 0
    rows = []
    for start, end, label in merged:
        old_out.update(before[cursor:start]); new_out.update(after[cursor:start])
        rows.append(dict(file_offset=hex(start), size=end-start, label=label,
                         before_sha256=sha(before[start:end]), after_sha256=sha(after[start:end])))
        cursor = end
    old_out.update(before[cursor:]); new_out.update(after[cursor:])
    if len(before) != len(after) or old_out.digest() != new_out.digest():
        raise ValueError("Unexpected byte outside checkdown repair scopes")
    return rows, old_out.hexdigest()


def _repair_resource(payload: bytes, entry_id: int):
    """Internal transformation; callers enforce the manifest/stacked hash gate."""
    if len(payload) != inspector.RESOURCE_HEADER_SIZE + inspector.BODY_SIZE:
        raise ValueError("Expected one fixed-size PLAY resource")
    book = inspector.parse_playbook_resource(payload)
    if entry_id >= 4000:
        return payload, dict(edits=[], appended_chains=0, old_node_count=book.node_count,
                             new_node_count=book.node_count, scopes=[], outside_scope_sha256=sha(payload))
    body = payload[inspector.RESOURCE_HEADER_SIZE:]
    edits = {}
    seen = {}
    for formation in book.formations:
        fr = lib.formation_record(body, formation.index)
        if fr.type_code >= 4:
            continue
        codes = lib.category_positions(body, lib.formation_category(body, formation.index))
        qb_slot = next((s for s, code in enumerate(codes) if code & 31 == lib.QB), None)
        if qb_slot is None:
            continue
        for link in formation.play_links:
            play = book.plays[link.play_index]
            qb_nodes = [codec.Node.from_bytes(bytes.fromhex(n.raw_hex))
                        for n in book.assignment_chain(play.assignments[qb_slot]).nodes]
            if not any(n.op == 6 for n in qb_nodes):
                continue
            # Full native 2f3d10 endpoint-store proves this minimum: the
            # encoded depth is relative to LOS, clamped against current depth.
            qb_depth = min([fr.slots[qb_slot].z[0]] +
                           [n.operands[2] for n in qb_nodes if n.op == 4])
            for slot, code in enumerate(codes):
                if code & 31 not in lib.BACK_KINDS:
                    continue
                assignment = play.assignments[slot]
                nodes = [codec.Node.from_bytes(bytes.fromhex(n.raw_hex))
                         for n in book.assignment_chain(assignment).nodes]
                if len(nodes) != 2 or [n.op for n in nodes] != [1, 18] or nodes[1].operands[0] != 5:
                    continue
                key = (play.index, slot)
                receiver_depth = fr.slots[slot].z[0]
                unsafe = receiver_depth + 1.75 * lib.YD <= qb_depth
                state = (unsafe, receiver_depth)
                if key in seen and seen[key] != state:
                    raise ValueError("Shared flat has conflicting formation depths")
                seen[key] = state
                if not unsafe:
                    continue
                # Refuse custom or conditional chains masquerading as the
                # generated Start->Flat contract. Preserve every old operand.
                if nodes[0].flags != 0 or nodes[1].flags != 6 or nodes[0].operands != [1, 3, 0, 0., 0., 0.] or nodes[1].operands[1] != 0 or nodes[1].operands[3] != 15:
                    raise ValueError("Unexpected authored deep-flat chain bytes")
                authored = codec.authored_chain(nodes)
                authored.insert(1, lib.seg(0, (-1.5 * lib.YD - receiver_depth) / lib.YD))
                rebuilt = [n.to_bytes() for n in codec.encode_chain(authored)]
                edits[key] = dict(play_index=play.index, play=play.name, slot=slot,
                                  formation=formation.name, receiver_depth_cm=receiver_depth,
                                  qb_drop_depth_cm=qb_depth, before_nodes=[n.to_bytes().hex() for n in nodes],
                                  after_nodes=[n.hex() for n in rebuilt], nodes=rebuilt)
    replacement = bytearray(payload)
    cursor = book.node_count
    allocations = {}
    scopes = []
    header = inspector.RESOURCE_HEADER_SIZE
    for key in sorted(edits):
        row = edits[key]
        raw_chain = b"".join(row.pop("nodes"))
        if raw_chain not in allocations:
            need = len(raw_chain) // inspector.NODE_SIZE
            if cursor + need > NODE_CAPACITY:
                raise ValueError("No zero node-pool capacity for checkdown repair")
            start = inspector.NODE_BASE + cursor * inspector.NODE_SIZE
            stop = start + len(raw_chain)
            if any(replacement[header+start:header+stop]):
                raise ValueError("Unexpected nonzero node-pool allocation tail")
            replacement[header+start:header+stop] = raw_chain
            allocations[raw_chain] = start
            cursor += need
        play_index, slot = key
        field = inspector.PLAY_BASE + play_index * inspector.PLAY_SIZE + 8 + slot * 8
        old_desc = book.plays[play_index].assignments[slot].descriptor_word
        _, old_assignments = lib.play_chains(body, play_index)
        canonical_old = codec.build_descriptor(book.plays[play_index].flags_or_id,
                                                old_assignments, slot, old_desc >> 24)
        if canonical_old != old_desc:
            raise ValueError("Unexpected authored deep-flat descriptor bits")
        assignments = [(desc, list(nodes)) for desc, nodes in old_assignments]
        assignments[slot] = (old_desc, [raw_chain[n:n+inspector.NODE_SIZE]
                                      for n in range(0, len(raw_chain), inspector.NODE_SIZE)])
        descriptor = codec.build_descriptor(book.plays[play_index].flags_or_id,
                                             assignments, slot, old_desc >> 24)
        assignments[slot] = (descriptor, assignments[slot][1])
        codec.validate_sync(assignments)
        problem = codec.validate_play(book.plays[play_index].flags_or_id, assignments)
        if problem:
            raise ValueError("Native validator rejects repaired checkdown: " + problem)
        struct.pack_into("<I", replacement, header+field, descriptor)
        struct.pack_into("<i", replacement, header+field+4, allocations[raw_chain] - (field+4) + 1)
        row.update(before_descriptor=hex(old_desc), after_descriptor=hex(descriptor),
                   chain_start_offset=hex(allocations[raw_chain]))
        scopes.append((header+field, header+field+8, f"play {play_index} slot {slot} descriptor and relative chain pointer"))
    if cursor != book.node_count:
        struct.pack_into("<I", replacement, header+0x40, cursor)
        scopes.extend([(header+0x40, header+0x44, "node pool count"),
                       (header+inspector.NODE_BASE+book.node_count*inspector.NODE_SIZE,
                        header+inspector.NODE_BASE+cursor*inspector.NODE_SIZE,
                        "new straight-then-flat chains in verified zero tail")])
    result = bytes(replacement)
    parsed = inspector.parse_playbook_resource(result)
    if inspector.menu_link_problems(result) != inspector.menu_link_problems(payload):
        raise ValueError("Unexpected PLAY menu problem after checkdown repair")
    for key, row in edits.items():
        chain = parsed.assignment_chain(parsed.plays[key[0]].assignments[key[1]])
        if [n.raw_hex for n in chain.nodes] != row["after_nodes"]:
            raise ValueError("Repaired PLAY assignment did not reparse exactly")
    receipt_scopes, outside = _ranges(payload, result, scopes)
    return result, dict(edits=list(edits.values()), appended_chains=len(allocations),
                        old_node_count=book.node_count, new_node_count=cursor,
                        scopes=receipt_scopes, outside_scope_sha256=outside)


def repair_resource(payload: bytes, entry_id: int, *, expected_input_sha256: str | None = None):
    manifest = json.loads(MANIFEST.read_text())
    row = manifest["books"].get(str(entry_id))
    if row is None:
        raise ValueError("Unknown shipped PLAY entry id")
    before = sha(payload)
    accepted = {expected_input_sha256} if expected_input_sha256 else {row["before_sha256"], row["after_sha256"]}
    if before not in accepted:
        raise ValueError("Unexpected PLAY input SHA256")
    result, receipt = _repair_resource(payload, entry_id)
    if before in (row["before_sha256"], row["after_sha256"]) and sha(result) != row["after_sha256"]:
        raise ValueError("Known PLAY repair output SHA256 mismatch")
    receipt.update(schema="b765.d2b.checkdown-routes.v1", disc_file="media/pack0.bin",
                   pack0_entry_id=entry_id, book=row["book"], size=len(payload),
                   before_sha256=before, after_sha256=sha(result),
                   status="applied" if result != payload else "already_applied",
                   changed_bytes=sum(a != b for a, b in zip(payload, result)), outside_scope_identical=True)
    return result, receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--entry-id", required=True, type=int)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--expected-input-sha256")
    args = parser.parse_args()
    if args.source.is_symlink() or not args.source.is_file():
        parser.error("Source must be a regular non-symlink extracted PLAY resource")
    if args.output.exists() or args.output.is_symlink() or args.receipt.exists() or args.receipt.is_symlink() or args.output.absolute() == args.receipt.absolute():
        parser.error("Choose distinct new output and receipt paths")
    with args.source.open("rb") as stream:
        payload = stream.read(inspector.RESOURCE_HEADER_SIZE + inspector.BODY_SIZE + 1)
    try:
        result, receipt = repair_resource(payload, args.entry_id, expected_input_sha256=args.expected_input_sha256)
    except (ValueError, KeyError) as exc:
        parser.error(str(exc))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(args.output, flags, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(result)
    with args.receipt.open("x") as stream:
        json.dump(receipt, stream, indent=2); stream.write("\n")
    print(json.dumps({k: receipt[k] for k in ("status", "before_sha256", "after_sha256", "changed_bytes")}))


if __name__ == "__main__":
    main()

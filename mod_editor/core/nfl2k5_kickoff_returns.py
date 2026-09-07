"""EXPERIMENTAL/UNWITNESSED local blocking for normal dynamic kickoff returns.

Fixed-size PLAY replacements compiled by the existing formation/play writer.
Normal return plays receive private chains; shared onside nodes stay untouched.
Use with kickoff_alignment and dynamic_kickoff. No executable allocation.
"""
from __future__ import annotations

import hashlib
import struct
from .errors import ValidationError
from . import nfl2k5_play_codec as codec
from . import nfl2k5_play_library as lib
from .nfl2k5_formation_play_writer import rule_play_request, compile_formation_play_creations
from .nfl2k5_playbook_inspector import parse_playbook_resource, RESOURCE_HEADER_SIZE

RETAIL_PINS = {
    "Return Left": "0b33b12ffcd78258fe70c59aea01c9a1147b1883579aded4e28b6fd9b3cc5179",
    "Return Middle": "68a3e357d99ff2316f5d39980f4c830ebe3a45264ba1208340e603d88d69710e",
    "Return Right": "3fced3af9602ef48eb5485e58d1f3d76c0dc26ae62574764e0b7ea3dba33700d",
}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _new_chains(chains):
    result = []
    for slot, (_desc, raw) in enumerate(chains):
        nodes = [codec.Node.from_bytes(n) for n in raw]
        if slot < 2:
            # Either deep player can field the ball. Keep the complete normal
            # receive/run branch; change only the non-carrier alternate branch.
            nodes = nodes[:3] + [codec.Node(0x11, 3, [4, 0, 1, 0, 2, 0, 0, 0])]
        else:
            # Start -> immediate local drive block, facing the approaching kick.
            # No 21-30 yard rush leg or returner follow-path on setup-zone men.
            nodes = nodes[:1] + [codec.Node(0x11, 6, [0, 0, 1, 0, 2, 0, 0, 0])]
        result.append([(n.op, tuple(n.operands), n.flags) for n in nodes])
    return result


def _inspect(raw):
    parsed = parse_playbook_resource(raw)
    forms = [f for f in parsed.formations if f.name == "Kick Return" and
             lib.formation_record(raw[RESOURCE_HEADER_SIZE:], f.index).type_code == 9]
    if len(forms) != 1:
        raise ValueError("expected one normal Kick Return formation")
    plays = parsed.plays_for_formation(forms[0])
    if len(plays) != 3 or {p.name for p in plays} != set(RETAIL_PINS):
        raise ValueError("normal return menu differs from the pinned three plays")
    body = raw[RESOURCE_HEADER_SIZE:]
    rows = []
    for p in plays:
        flags, chains = lib.play_chains(body, p.index)
        if p.family_id != 7:
            raise ValueError("normal return family differs")
        target = _new_chains(chains)
        expected = [[n.to_bytes() for n in codec.encode_chain(c)] for c in target]
        actual = [c[1] for c in chains]
        state = ("retail" if _sha(b"".join(b"".join(c) for c in actual)) == RETAIL_PINS[p.name]
                 else "applied" if actual == expected else "foreign")
        # Applied recognition also pins the preserved deep receive/run branch
        # and every Start; do not derive that expectation from foreign bytes.
        if state == "applied":
            start = bytes.fromhex("0100000001034080")
            receive = [start, bytes.fromhex("0904000031004080"), bytes.fromhex("150200000f402280")]
            if any(c[0] != start for c in actual) or any(c[:3] != receive for c in actual[:2]):
                state = "foreign"
            if lib.validate_chains(flags, chains, target):
                state = "foreign"
        rows.append((p, state, target))
    states = {row[1] for row in rows}
    return parsed, rows, next(iter(states)) if len(states) == 1 else "foreign"


def status(raw: bytes) -> str:
    try:
        return _inspect(raw)[2]
    except (ValueError, ValidationError, struct.error, IndexError, KeyError, TypeError):
        return "foreign"


def apply(raw: bytes) -> tuple[bytes, dict]:
    parsed, rows, state = _inspect(raw)
    if state == "foreign":
        raise ValueError("mixed/foreign normal kickoff return assignments")
    if state == "applied":
        return raw, {"status": "already_applied", "changed_bytes": 0, "edits": []}
    body = raw[RESOURCE_HEADER_SIZE:]
    requests = [rule_play_request(parsed.asset_id, body, p.index, chains, replace_index=p.index)
                for p, _state, chains in rows]
    compiled = compile_formation_play_creations(raw, play_requests=requests)
    out = compiled.replacement
    if status(out) != "applied" or len(out) != len(raw):
        raise ValueError("return assignments failed post-compile recognition")
    # Exact contiguous byte edits, resource-relative, suitable for streamed packs.
    edits, pos = [], 0
    while pos < len(raw):
        if raw[pos] == out[pos]:
            pos += 1
            continue
        start = pos
        while pos < len(raw) and raw[pos] != out[pos]:
            pos += 1
        edits.append({"offset": start, "before": raw[start:pos].hex(), "after": out[start:pos].hex()})
    return out, {"status": "applied", "source_sha256": _sha(raw), "replacement_sha256": _sha(out),
                 "changed_bytes": compiled.changed_byte_count, "edits": edits,
                 "plays": [{"index": p.index, "name": p.name} for p, _, _ in rows],
                 "nodes_added": compiled.report["new_node_count"] - compiled.report["old_node_count"],
                 "witnessed": False}

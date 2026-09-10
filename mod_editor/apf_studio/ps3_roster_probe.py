"""Read-only, bounded PS3 USERDATA versus Xbox 360 raw/STFS roster probe.

Reports structure and hashes, never player names or roster payload bytes.
Passing selected structural checks is not proof that a save loads in Xenia.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import zipfile

from .backend import ensure_tools_importable
from .save_roster_players import MAX_SOURCE_BYTES, inspect_bytes, _raw_payload, _layout

ensure_tools_importable()
import apf_save_custom_team_appearance as save_layout
import apf_save_playbook_assignments as labels

SCHEMA = "apf2k8_ps3_roster_probe/v1"
USER_OFFSET = 0x26D030


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_input(path: Path, member: str | None = None) -> bytes:
    if member is not None:
        with zipfile.ZipFile(path) as archive:
            matches = [i for i in archive.infolist() if i.filename == member]
            if len(matches) != 1 or not 0 < matches[0].file_size <= MAX_SOURCE_BYTES:
                raise ValueError("Missing/duplicate/oversize roster ZIP member")
            with archive.open(matches[0]) as stream:
                data = stream.read(MAX_SOURCE_BYTES + 1)
    else:
        with path.open("rb") as stream:
            data = stream.read(MAX_SOURCE_BYTES + 1)
    if not 0 < len(data) <= MAX_SOURCE_BYTES:
        raise ValueError("Roster source exceeds bounded range")
    return data


def _inspect(source: bytes) -> tuple[bytes, dict]:
    raw, signed, container, member = _raw_payload(source)
    if len(raw) < 324:
        raise ValueError("Truncated roster root")
    counts = [save_layout._root_count(raw, i) for i in range(40)]
    roots = []
    for index in range(40):
        field = 8 + index * 8
        stored = struct.unpack_from(">i", raw, field)[0]
        target = field + stored - 1
        roots.append({"index": index, "count": counts[index], "pointer_field": field,
                      "resolved_offset": target if 0 <= target < len(raw) else None,
                      "pointer_in_payload": 0 <= target < len(raw)})
    report = {"source_bytes": len(source), "payload_bytes": len(raw), "payload_sha256": _sha(raw),
              "container": container if signed else "raw", "container_member": member,
              "prefix_u32": struct.unpack_from(">I", raw)[0], "root_table": roots,
              "player_stride": 0x14C, "team_stride": 0x180}
    try:
        layout = save_layout._table_layout(raw)
        report["appearance_graph"] = {str(k): list(v) for k, v in layout.items()}
        report["appearance_graph_valid"] = True
    except (ValueError, RuntimeError) as exc:
        report["appearance_graph_valid"] = False
        report["appearance_error"] = str(exc)
    try:
        player_start, team_start, memberships = _layout(raw)
        report.update(player_graph_valid=True, player_start=player_start, team_start=team_start, membership_count=len(memberships))
    except ValueError as exc:
        report.update(player_graph_valid=False, player_graph_error=str(exc))
    try:
        doc = inspect_bytes(source)
        report["players_valid"] = True
        report["player_start"] = doc.player_start
        report["team_start"] = doc.team_start
        report["membership_count"] = len(doc.memberships)
        report["name_allocation_count"] = len(doc.text_allocations)
        report["name_allocation_offsets_sha256"] = _sha(json.dumps(
            [(a.target_offset, a.allocation_bytes) for a in doc.text_allocations]).encode())
    except ValueError as exc:
        report["players_valid"] = False
        report["players_error"] = str(exc)
    # Independently inspect all player name pointers even when the stricter
    # production parser rejects one. Do not loosen that parser to accept PS3.
    start = roots[0]["resolved_offset"]
    if start is not None and counts[0] <= 10000 and start + counts[0] * 0x14C <= len(raw):
        from .save_roster_players import PLAYER_TEXT_FIELDS_BY_ID
        text_fields = {}
        for name, spec in PLAYER_TEXT_FIELDS_BY_ID.items():
            pointer_offset = spec
            offsets, null_count = [], 0
            for index in range(counts[0]):
                field = start + index * 0x14C + pointer_offset
                stored = struct.unpack_from(">i", raw, field)[0]
                null_count += stored == 0
                target = field + stored - 1
                offsets.append(target)
            text_fields[name] = {"record_pointer_offset": pointer_offset,
                                 "zero_stored_pointer_count": null_count,
                                 "odd_target_count": sum(t % 2 for t in offsets),
                                 "out_of_bounds_count": sum(not 0 <= t < len(raw) for t in offsets),
                                 "target_offsets_sha256": _sha(json.dumps(offsets).encode())}
            odd = next((i for i, t in enumerate(offsets) if t % 2), None)
            if odd is not None:
                text_fields[name]["first_odd_target"] = {"player_index": odd,
                    "pointer_field": start + odd * 0x14C + pointer_offset, "target_offset": offsets[odd]}
        report["name_pointer_audit"] = text_fields
    try:
        parsed = labels.parse_save(raw)
        report["label_table"] = {"valid": True, "offset": parsed.layout.playbook_start,
                                 "count": len(parsed.playbooks), "stride": 12,
                                 "names_sha256": _sha(json.dumps([p.name for p in parsed.playbooks]).encode()),
                                 "rows_sha256": _sha(raw[parsed.layout.playbook_start:parsed.layout.playbook_start + 69 * 12])}
    except (ValueError, RuntimeError) as exc:
        report["label_table"] = {"valid": False, "stride": 12, "error": str(exc)}
    report["user_region"] = {"offset": USER_OFFSET, "present": len(raw) > USER_OFFSET,
                             "remaining_bytes": max(0, len(raw) - USER_OFFSET),
                             "sha256": _sha(raw[USER_OFFSET:]),
                             "user_marker_offsets": [i for i in range(USER_OFFSET, len(raw) - 7)
                                                     if raw[i:i + 8] == b"\x00U\x00S\x00E\x00R"]}
    return raw, report


def compare_rosters(ps3: bytes, xbox: bytes) -> dict:
    left, p = _inspect(ps3)
    right, x = _inspect(xbox)
    windows = []
    for offset in range(0, max(len(left), len(right)), 0x10000):
        a, b = left[offset:offset + 0x10000], right[offset:offset + 0x10000]
        count = sum(a != b for a, b in zip(a, b)) + abs(len(a) - len(b))
        if count:
            windows.append({"offset": offset, "different_bytes": count})
    compatible = (p["players_valid"] and x["players_valid"] and p["appearance_graph_valid"] and x["appearance_graph_valid"]
                  and p["label_table"]["valid"] and x["label_table"]["valid"] and len(left) == len(right))
    return {"schema": SCHEMA, "ps3": p, "xbox360": x,
            "same_size": len(left) == len(right), "byte_identical": left == right,
            "root_counts_equal": [r["count"] for r in p["root_table"]] == [r["count"] for r in x["root_table"]],
            "root_pointer_differences": [i for i in range(40) if left[8 + i * 8:12 + i * 8] != right[8 + i * 8:12 + i * 8]],
            "different_bytes": sum(w["different_bytes"] for w in windows), "difference_windows_64k": windows,
            "existing_parsers_accept_both": compatible, "converter_writer_authorized_by_evidence": left == right and compatible,
            "decision": "No converter writer: raw payload is not byte-identical and/or existing bounded parser rejects it." if left != right or not compatible else "Payload identity proved; only external container handoff remains.",
            "runtime": "UNWITNESSED: no Xenia or console load was performed"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ps3", type=Path)
    parser.add_argument("xbox", type=Path)
    parser.add_argument("--ps3-member")
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args(argv)
    report = compare_rosters(read_input(args.ps3, args.ps3_member), read_input(args.xbox))
    with args.receipt.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

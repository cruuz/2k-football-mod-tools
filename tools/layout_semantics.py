#!/usr/bin/env python3
"""Build a conservative cross-title LAYT semantic and lineage report.

The exhaustive inventory remains the byte/layout authority.  This pass adds
only relationships established by exact record identity, corpus-wide hash
checks, or canonical executable consumers.  It deliberately does not turn
float-looking words into coordinates without those consumers.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
import zlib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "vc_cross_title_layout_semantics/v1"
EXPECTED_INVENTORY_SCHEMA = "vc_cross_title_layout_inventory/v1"


class SemanticError(ValueError):
    """The upstream inventory did not satisfy a lineage invariant."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def word(record: dict[str, Any], index: int) -> int:
    return int(record["raw_words"][index], 16)


def f32(value: int) -> float:
    return struct.unpack(">f", value.to_bytes(4, "big"))[0]


def f32_text(value: int) -> str:
    return format(f32(value), ".9g")


def exposed_name(record: dict[str, Any]) -> str | None:
    if record["platform"] == "apf2k8":
        return record.get("primary_name")
    return record.get("instance_name")


def identity(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "platform": record["platform"],
        "outer_index": record["outer_index"],
        "inner_index": record["inner_index"],
        "layout_name": record["layout_name"],
        "record_index": record["record_index"],
        "record_offset": record["record_offset"],
        "record_type": record["record_type"],
        "exposed_name": exposed_name(record),
    }


def key_for(record: dict[str, Any]) -> tuple[str, str, int] | None:
    name = exposed_name(record)
    if not name:
        return None
    return (
        record["layout_name"].casefold(),
        name.casefold(),
        record["record_type"],
    )


def sorted_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        records,
        key=lambda row: (
            row["layout_name"].casefold(),
            row["outer_index"],
            row["inner_index"],
            row["record_index"],
        ),
    )


def bridge(
    kind: str,
    apf: dict[str, Any],
    nfl: dict[str, Any],
    *,
    note: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "evidence_kind": kind,
        "layout_name": apf["layout_name"],
        "record_type": apf["record_type"],
        "exposed_name": exposed_name(apf),
        "apf": identity(apf),
        "nfl": identity(nfl),
        "note": note,
    }
    if apf["record_type"] in (0, 1, 2):
        values = []
        for index, label in ((4, "x"), (5, "y"), (6, "z"), (7, "w")):
            if index >= len(apf["raw_words"]) or index >= len(nfl["raw_words"]):
                continue
            apf_value = word(apf, index)
            nfl_value = word(nfl, index)
            values.append(
                {
                    "component": label,
                    "record_offset": index * 4,
                    "apf_bits": f"0x{apf_value:08x}",
                    "nfl_bits": f"0x{nfl_value:08x}",
                    "apf_float": f32_text(apf_value),
                    "nfl_float": f32_text(nfl_value),
                    "bit_identical": apf_value == nfl_value,
                }
            )
        result["additive_transform_words"] = values
    if apf["record_type"] == 0:
        apf_default = word(apf, 12)
        nfl_default = word(nfl, 16)
        result["inherited_default_one_word"] = {
            "apf_offset": 0x30,
            "nfl_offset": 0x40,
            "apf_bits": f"0x{apf_default:08x}",
            "nfl_bits": f"0x{nfl_default:08x}",
            "bit_identical": apf_default == nfl_default,
            "semantic_name": None,
        }
    return result


def write_tsv(path: Path, bridges: list[dict[str, Any]]) -> None:
    fields = [
        "evidence_kind", "layout_name", "exposed_name", "record_type",
        "apf_outer_index", "apf_inner_index", "apf_record_index",
        "nfl_outer_index", "nfl_inner_index", "nfl_record_index",
        "x_apf", "x_nfl", "x_exact", "y_apf", "y_nfl", "y_exact",
        "z_apf", "z_nfl", "z_exact", "w_apf", "w_nfl", "w_exact",
        "default_one_exact", "note",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, dialect="excel-tab")
        writer.writeheader()
        for item in bridges:
            row: dict[str, Any] = {
                "evidence_kind": item["evidence_kind"],
                "layout_name": item["layout_name"],
                "exposed_name": item.get("exposed_name") or "",
                "record_type": item["record_type"],
                "apf_outer_index": item["apf"]["outer_index"],
                "apf_inner_index": item["apf"]["inner_index"],
                "apf_record_index": item["apf"]["record_index"],
                "nfl_outer_index": item["nfl"]["outer_index"],
                "nfl_inner_index": item["nfl"]["inner_index"],
                "nfl_record_index": item["nfl"]["record_index"],
                "default_one_exact": item.get("inherited_default_one_word", {}).get(
                    "bit_identical", ""
                ),
                "note": item["note"],
            }
            for component in item.get("additive_transform_words", []):
                label = component["component"]
                row[f"{label}_apf"] = component["apf_bits"]
                row[f"{label}_nfl"] = component["nfl_bits"]
                row[f"{label}_exact"] = component["bit_identical"]
            writer.writerow(row)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--inventory", type=Path,
        default=Path("reports/assets/cross_title_layout_inventory.json"),
    )
    result.add_argument(
        "--apf-trace", type=Path,
        default=Path("reports/assets/apf_layout_ghidra/layout_trace.txt"),
    )
    result.add_argument(
        "--apf-pseudo", type=Path,
        default=Path("reports/assets/apf_layout_ghidra/layout_focused_pseudo_c.c"),
    )
    result.add_argument(
        "--apf-disassembly", type=Path,
        default=Path("reports/assets/apf_layout_ghidra/layout_focused_disassembly.txt"),
    )
    result.add_argument(
        "--nfl-trace", type=Path,
        default=Path("reports/assets/nfl2k5_layout_ghidra/layout_trace.txt"),
    )
    result.add_argument(
        "--nfl-pseudo", type=Path,
        default=Path("reports/assets/nfl2k5_layout_ghidra/layout_focused_pseudo_c.c"),
    )
    result.add_argument(
        "--nfl-disassembly", type=Path,
        default=Path("reports/assets/nfl2k5_layout_ghidra/layout_focused_disassembly.txt"),
    )
    result.add_argument("--json", type=Path, required=True)
    result.add_argument("--tsv", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    if inventory.get("schema") != EXPECTED_INVENTORY_SCHEMA:
        raise SemanticError("unexpected layout inventory schema")
    records = inventory["records"]
    apf_records = [row for row in records if row["platform"] == "apf2k8"]
    nfl_records = [row for row in records if row["platform"] == "nfl2k5"]

    apf_keys: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    nfl_keys: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in apf_records:
        key = key_for(row)
        if key is not None:
            apf_keys[key].append(row)
    for row in nfl_records:
        key = key_for(row)
        if key is not None:
            nfl_keys[key].append(row)

    shared_keys = sorted(apf_keys.keys() & nfl_keys.keys())
    key_groups: list[dict[str, Any]] = []
    unique_bridges: list[dict[str, Any]] = []
    ordinal_bridges: list[dict[str, Any]] = []
    for key in shared_keys:
        apf_group = sorted_records(apf_keys[key])
        nfl_group = sorted_records(nfl_keys[key])
        group = {
            "layout_name_casefolded": key[0],
            "exposed_name_casefolded": key[1],
            "record_type": key[2],
            "apf_count": len(apf_group),
            "nfl_count": len(nfl_group),
            "apf_records": [identity(row) for row in apf_group],
            "nfl_records": [identity(row) for row in nfl_group],
            "unique_one_to_one": len(apf_group) == len(nfl_group) == 1,
        }
        if group["unique_one_to_one"]:
            unique_bridges.append(
                bridge(
                    "exact_name_key_unique", apf_group[0], nfl_group[0],
                    note="unique exact (layout, exposed name, type) key",
                )
            )
        elif (
            len(apf_group) == len(nfl_group)
            and [row["record_index"] for row in apf_group]
            == [row["record_index"] for row in nfl_group]
        ):
            group["same_record_index_sequence"] = True
            for apf, nfl in zip(apf_group, nfl_group):
                ordinal_bridges.append(
                    bridge(
                        "exact_name_key_same_index", apf, nfl,
                        note="ambiguous name key resolved only by equal record index sequence",
                    )
                )
        else:
            group["same_record_index_sequence"] = False
        key_groups.append(group)

    apf_layouts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    nfl_layouts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in apf_records:
        apf_layouts[row["layout_name"].casefold()].append(row)
    for row in nfl_records:
        nfl_layouts[row["layout_name"].casefold()].append(row)
    exact_layouts: list[dict[str, Any]] = []
    sequence_bridges: list[dict[str, Any]] = []
    for name in sorted(apf_layouts.keys() & nfl_layouts.keys()):
        apf_group = sorted(apf_layouts[name], key=lambda row: row["record_index"])
        nfl_group = sorted(nfl_layouts[name], key=lambda row: row["record_index"])
        exact = (
            len(apf_group) == len(nfl_group)
            and [row["record_type"] for row in apf_group]
            == [row["record_type"] for row in nfl_group]
            and [
                (exposed_name(row) or "").casefold() for row in apf_group
            ] == [
                (exposed_name(row) or "").casefold() for row in nfl_group
            ]
        )
        if not exact:
            continue
        exact_layouts.append(
            {
                "layout_name_casefolded": name,
                "record_count": len(apf_group),
                "record_types": [row["record_type"] for row in apf_group],
                "exposed_names": [exposed_name(row) for row in apf_group],
            }
        )
        for apf, nfl in zip(apf_group, nfl_group):
            sequence_bridges.append(
                bridge(
                    "exact_layout_sequence", apf, nfl,
                    note="whole layout has identical record count/type/exposed-name sequence",
                )
            )

    # Use records retained inside bridge identities only for presentation, but
    # calculate aggregate word counts from their source pairs.
    unique_source_pairs = [
        (apf_keys[(item["layout_name"].casefold(), item["exposed_name"].casefold(),
                   item["record_type"])][0],
         nfl_keys[(item["layout_name"].casefold(), item["exposed_name"].casefold(),
                   item["record_type"])][0])
        for item in unique_bridges
    ]
    unique_type0 = [(apf, nfl) for apf, nfl in unique_source_pairs if apf["record_type"] == 0]
    sequence_pairs = [
        (apf, nfl)
        for layout in exact_layouts
        for apf, nfl in zip(
            sorted(apf_layouts[layout["layout_name_casefolded"]], key=lambda row: row["record_index"]),
            sorted(nfl_layouts[layout["layout_name_casefolded"]], key=lambda row: row["record_index"]),
        )
    ]
    sequence_type0 = [(apf, nfl) for apf, nfl in sequence_pairs if apf["record_type"] == 0]
    sequence_type1 = [(apf, nfl) for apf, nfl in sequence_pairs if apf["record_type"] == 1]

    def pair_matches(pairs: list[tuple[dict[str, Any], dict[str, Any]]], ai: int, ni: int) -> int:
        return sum(word(apf, ai) == word(nfl, ni) for apf, nfl in pairs)

    apf_named = [row for row in apf_records if row.get("primary_name")]
    apf_crc_matches = [
        row for row in apf_named
        if word(row, 2) == (
            zlib.crc32(row["primary_name"].upper().encode("ascii")) & 0xffffffff
        )
    ]
    nfl_crc_matches = [
        row for row in nfl_records
        if word(row, 3) == (
            zlib.crc32(row["source_name"].upper().encode("utf-16le")) & 0xffffffff
        )
    ]
    if len(nfl_crc_matches) != len(nfl_records):
        raise SemanticError("NFL +0x0c source-name CRC invariant failed")

    apf_type0 = [row for row in apf_records if row["record_type"] == 0]
    legacy_owner = [row for row in apf_type0 if row.get("owner_name")]
    owner_equal = [
        row for row in legacy_owner
        if row["owner_name"].casefold() == row["layout_name"].casefold()
    ]
    owner_false = [row for row in legacy_owner if row not in owner_equal]

    def layout_entry(platform: str, name: str) -> dict[str, Any]:
        selected = [
            row for row in records
            if row["platform"] == platform and row["layout_name"].casefold() == name.casefold()
        ]
        if not selected:
            raise SemanticError(f"missing {platform} layout {name}")
        return {
            "platform": platform,
            "layout_name": selected[0]["layout_name"],
            "outer_index": selected[0]["outer_index"],
            "inner_index": selected[0]["inner_index"],
            "record_count": len(selected),
            "records": [
                {
                    "record_index": row["record_index"],
                    "record_type": row["record_type"],
                    "exposed_name": exposed_name(row),
                    "source_name": row.get("source_name"),
                }
                for row in sorted(selected, key=lambda row: row["record_index"])
            ],
        }

    transform_divergences = []
    for apf, nfl in unique_type0:
        for index, label in ((4, "x"), (5, "y"), (6, "z")):
            if word(apf, index) == word(nfl, index):
                continue
            transform_divergences.append(
                {
                    "layout_name": apf["layout_name"],
                    "exposed_name": exposed_name(apf),
                    "component": label,
                    "apf_bits": f"0x{word(apf, index):08x}",
                    "nfl_bits": f"0x{word(nfl, index):08x}",
                    "apf_float": f32_text(word(apf, index)),
                    "nfl_float": f32_text(word(nfl, index)),
                }
            )

    all_bridges = unique_bridges + ordinal_bridges + sequence_bridges
    summary = {
        "shared_exact_name_key_count": len(shared_keys),
        "unique_exact_name_bridge_count": len(unique_bridges),
        "ambiguous_exact_name_key_count": sum(
            not group["unique_one_to_one"] for group in key_groups
        ),
        "ambiguous_same_index_bridge_count": len(ordinal_bridges),
        "exact_whole_layout_sequence_count": len(exact_layouts),
        "exact_whole_layout_sequence_record_count": len(sequence_bridges),
        "exact_whole_layout_sequence_type_counts": dict(sorted(Counter(
            str(item["record_type"]) for item in sequence_bridges
        ).items())),
        "unique_type0_bridge_count": len(unique_type0),
        "unique_type0_x_bit_identical": pair_matches(unique_type0, 4, 4),
        "unique_type0_y_bit_identical": pair_matches(unique_type0, 5, 5),
        "unique_type0_z_bit_identical": pair_matches(unique_type0, 6, 6),
        "unique_type0_default_one_bit_identical": pair_matches(unique_type0, 12, 16),
        "sequence_type0_bridge_count": len(sequence_type0),
        "sequence_type0_x_bit_identical": pair_matches(sequence_type0, 4, 4),
        "sequence_type0_y_bit_identical": pair_matches(sequence_type0, 5, 5),
        "sequence_type0_z_bit_identical": pair_matches(sequence_type0, 6, 6),
        "sequence_type0_default_one_bit_identical": pair_matches(sequence_type0, 12, 16),
        "sequence_type1_bridge_count": len(sequence_type1),
        "sequence_type1_x_bit_identical": pair_matches(sequence_type1, 4, 4),
        "sequence_type1_y_bit_identical": pair_matches(sequence_type1, 5, 5),
        "nfl_source_name_crc_match_count": len(nfl_crc_matches),
        "nfl_source_name_crc_tested_count": len(nfl_records),
        "apf_exposed_name_crc_match_count": len(apf_crc_matches),
        "apf_exposed_name_crc_tested_count": len(apf_named),
        "apf_type0_serialized_bit29_set_count": sum(
            bool(word(row, 13) & 0x20000000) for row in apf_type0
        ),
        "apf_type0_record_count": len(apf_type0),
        "apf_field_4c_legacy_string_candidate_count": len(legacy_owner),
        "apf_field_4c_equals_layout_name_count": len(owner_equal),
        "apf_field_4c_false_string_candidate_count": len(owner_false),
    }

    report = {
        "schema": SCHEMA,
        "sources": {
            "inventory": str(args.inventory),
            "inventory_sha256": sha256_file(args.inventory),
            "apf_trace": str(args.apf_trace),
            "apf_trace_sha256": sha256_file(args.apf_trace),
            "apf_pseudo": str(args.apf_pseudo),
            "apf_pseudo_sha256": sha256_file(args.apf_pseudo),
            "apf_disassembly": str(args.apf_disassembly),
            "apf_disassembly_sha256": sha256_file(args.apf_disassembly),
            "nfl_trace": str(args.nfl_trace),
            "nfl_trace_sha256": sha256_file(args.nfl_trace),
            "nfl_pseudo": str(args.nfl_pseudo),
            "nfl_pseudo_sha256": sha256_file(args.nfl_pseudo),
            "nfl_disassembly": str(args.nfl_disassembly),
            "nfl_disassembly_sha256": sha256_file(args.nfl_disassembly),
        },
        "summary": summary,
        "field_semantics": {
            "record_types": {
                "0": "renderable/referenced UI object record with additive transform and runtime draw/timeline state",
                "1": "layout-level callback marker; NFL callback(current_record) ABI proved",
                "2": "directed child-layout reference",
                "3_apf_only": "timeline/transition descriptor with four 60 Hz counts, scalar, and mode",
            },
            "record_prefix": {
                "+0x00": "next record pointer after relocation",
                "+0x04": "record type",
                "apf_+0x08": "record lookup identifier; not universally generated from exposed name",
                "nfl_+0x0c": "record lookup identifier; CRC32(uppercase UTF-16LE source name) in 280/280 records",
            },
            "additive_transform_+0x10_to_+0x1c": {
                "status": "proven for NFL type 0/type 2; inherited APF vector strongly proved by executable accessor and exact lineage",
                "nfl_evidence": [
                    "0x00143720 adds type-0 +0x10/+0x14/+0x18 to parent values and calls 0x000379A0",
                    "0x000379A0 composes those three values into a 4x4 matrix translation column",
                    "0x00143A00 adds type-2 +0x10/+0x14/+0x18/+0x1c before recursive child traversal",
                    "0x00144000 and 0x00144020 set/access the four-word vector",
                ],
                "apf_evidence": [
                    "0x846EED58 returns selected record +0x10",
                    "0x8475AC48 subtracts the keyboard offset from returned-vector +0x04 (record +0x14)",
                    "71 unique type-0 bridges preserve x/y exactly and 64 preserve z exactly",
                ],
            },
            "type2_child_layout": {
                "status": "proven directed child reference, not a parent pointer",
                "evidence": [
                    "NFL 0x00143EA0 resolves type-2 +0x20 name into runtime +0x28",
                    "NFL 0x00143A00 recurses through type-2 runtime +0x28",
                    "APF 0x846EDBC8 recursively searches type-2 runtime +0x28",
                ],
            },
            "runtime_draw_gate": {
                "nfl": "type-0 runtime +0x38 is initialized from resolution success, checked by render path 0x00143720, and written by 0x00143FE0",
                "apf": "type-0 runtime flags +0x34 bit 29 is written by 0x846EEC98; 0x84686680 clears two replay overlays then enables exactly one",
                "serialized_warning": "this is runtime state, not a proved editable serialized visibility field",
            },
            "timeline": {
                "nfl": "0x00143CE0 updates type-0 runtime progress +0x54 and classifies phase +0x58 using mode +0x28 and thresholds +0x2c/+0x30",
                "apf": "0x846EDEA8 converts four type-3 frame counts at +0x20..+0x2c by 1/60 into a type-0 timeline; 0x846EDD30 updates its progress and phase bits",
            },
            "type1": {
                "status": "layout-level callback marker",
                "evidence": "NFL 0x00143A93..0x00143A9C loads callback pointer from layout +0x08, passes the current type-1 record in ECX, and calls with no stack arguments",
            },
            "event_dispatch": {
                "nfl": [
                    "0x00143EA0 installs four runtime callback-table pointers at layout +0x0c/+0x10/+0x14/+0x18 from a five-word caller descriptor",
                    "0x00143450 filters +0x0c table entries by record lookup ID and a secondary runtime ID before indirect dispatch",
                    "0x00143510 filters +0x10 entries by record lookup ID, timeline phase +0x58, and one of two dispatch classes",
                    "0x00143600 and 0x00143660 dispatch +0x14/+0x18 tables with record-ID filtering",
                ],
                "apf": "0x846ED638 and 0x846ED698 dispatch a runtime handler object at UI object +0x3c with a bounded stack message containing that object and three caller values",
                "status": "dispatch ABI proved; author-facing event names and table ownership remain unknown",
            },
            "apf_legacy_field_4c": {
                "status": "refuted as a universal owner/parent field",
                "equals_layout_name": len(owner_equal),
                "false_string_candidates": [
                    {
                        **identity(row),
                        "legacy_candidate": row["owner_name"],
                        "raw_word": row["raw_words"][19],
                    }
                    for row in owner_false
                ],
            },
            "inherited_default_one": {
                "apf_offset": 0x30,
                "nfl_offset": 0x40,
                "status": "bit-identical 0x3f800000 across every type-0 bridge and every title corpus record",
                "semantic_name": None,
                "warning": "no canonical consumer yet distinguishes scale, opacity, or another scalar",
            },
        },
        "main_menu_entries": {
            "apf": layout_entry("apf2k8", "layout_mainmenu"),
            "nfl_container": layout_entry("nfl2k5", "main_menu"),
            "nfl_navigation": layout_entry("nfl2k5", "main_navi"),
            "state_entry_status": "not proved",
            "state_entry_evidence": [
                "APF layout_mainmenu is a 7-child LAYT in frontend_sync.iff, but its 0x48c6d154 hash has no credible paired PPC immediate; reported halfword hits are distant collisions inside unresolved 0x84C559C0",
                "NFL 0x00e8b1e0 is the prefix of main_menu_sub rather than a standalone main_menu string; it has only data reference 0x00515678. Exact main_navi at 0x00e9d4a8 likewise has only data reference 0x00ad0154",
            ],
        },
        "writer_safety": {
            "safe": False,
            "blockers": [
                "APF lookup-ID generation is not derivable from the exposed name for 1052/1408 named records",
                "runtime-resolved pointers and draw/timeline state must not be serialized as authored values",
                "type-1 callback/event ABI and remaining per-type words are not proved",
                "string-pool ownership, capacity growth, reference counts, and complete hash domains are not proved",
            ],
        },
        "shared_name_key_groups": key_groups,
        "exact_whole_layout_sequences": exact_layouts,
        "unique_name_bridges": unique_bridges,
        "ambiguous_name_same_index_bridges": ordinal_bridges,
        "exact_layout_sequence_bridges": sequence_bridges,
        "unique_type0_transform_divergences": transform_divergences,
        "portme": [
            "PORTME: map proved callback-table slots and APF +0x3c handler dispatch to author-facing event names and ownership rules.",
            "PORTME: name the inherited +0x30/+0x40 default-one scalar from a canonical consumer.",
            "PORTME: trace APF lookup-ID generation and string-pool ownership before any writer.",
            "PORTME: identify the native main-menu state constructors/transitions; resource entries alone are not state functions.",
        ],
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_tsv(args.tsv, all_bridges)
    print(
        "LAYOUT_SEMANTICS_COMPLETE "
        f"keys={len(shared_keys)} unique={len(unique_bridges)} "
        f"ordinal={len(ordinal_bridges)} layouts={len(exact_layouts)}/"
        f"{len(sequence_bridges)} x={summary['unique_type0_x_bit_identical']}/"
        f"{len(unique_type0)} y={summary['unique_type0_y_bit_identical']}/"
        f"{len(unique_type0)} z={summary['unique_type0_z_bit_identical']}/"
        f"{len(unique_type0)}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, SemanticError, UnicodeError, struct.error) as exc:
        raise SystemExit(f"error: {exc}") from exc

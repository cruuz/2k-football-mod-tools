#!/usr/bin/env python3
"""Freeze APF's 2K6-tagged animation records, payloads, and runtime owners.

The report deliberately separates three claims:

* the 5,884-entry name/definition table has exact structure but no recovered
  direct code owner;
* every 2K6 name-field occurrence maps to a concrete in-XEX motion root; and
* selected payload groups also occur in code-initialized selector/config data.

No retail code is executed and no game binary is modified.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import struct


SCHEMA = "apf2k8_2k6_animation_runtime/v1"
EXPECTED_PE_SHA256 = (
    "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
)
IMAGE_BASE = 0x82000000
TABLE_FIRST = 0x84D75500
TABLE_RECORD_SIZE = 0x2C
TABLE_RECORD_COUNT = 5884
TABLE_AFTER_LAST = TABLE_FIRST + TABLE_RECORD_SIZE * TABLE_RECORD_COUNT
EXPECTED_TABLE_SHA256 = (
    "40f063e925420c21076ccedc868524f0c83ea7f0eede25624e0b7606cc6f4497"
)
SELECTOR_RECORD_SIZE = 0x24
UTF16_BE_ASCII = re.compile(rb"(?:\x00[\x20-\x7e]){4,}\x00\x00")
SELECTOR_CALL = re.compile(
    r"Function_848AEB78\(0xffffffff([0-9a-f]+),(0x[0-9a-f]+|[0-9]+)\);"
)


class RuntimeErrorReport(ValueError):
    """Raised when a pinned executable or recovered invariant differs."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeErrorReport(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pin(path: Path, logical_path: str | None = None) -> dict[str, object]:
    data = path.read_bytes()
    return {
        "path": logical_path if logical_path is not None else str(path),
        "size": len(data),
        "sha256": sha256(data),
    }


def hx(value: int) -> str:
    return f"0x{value:08X}"


def u32(image: bytes, address: int) -> int:
    offset = address - IMAGE_BASE
    require(0 <= offset <= len(image) - 4, f"out-of-image u32 {hx(address)}")
    return struct.unpack_from(">I", image, offset)[0]


def words(image: bytes, address: int, count: int) -> tuple[int, ...]:
    offset = address - IMAGE_BASE
    require(0 <= offset <= len(image) - count * 4, f"out-of-image words {hx(address)}")
    return struct.unpack_from(f">{count}I", image, offset)


def utf16_strings(image: bytes) -> dict[int, str]:
    return {
        IMAGE_BASE + match.start(): match.group()[1:-2:2].decode("ascii")
        for match in UTF16_BE_ASCII.finditer(image)
    }


def parse_lineage(path: Path) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    require(document.get("schema") == "apf2k8_2k6_animation_lineage/v1", (
        "2K6 lineage schema differs"
    ))
    identifiers = document.get("identifiers")
    require(isinstance(identifiers, list) and len(identifiers) == 519, (
        "2K6 lineage identifier count differs"
    ))
    by_name = {row["name"]: row for row in identifiers}
    require(len(by_name) == 519, "2K6 lineage names are not unique")
    return document, by_name


def parse_selector_calls(pseudo: str) -> list[tuple[int, int]]:
    calls = [
        (int(address, 16), int(count, 0))
        for address, count in SELECTOR_CALL.findall(pseudo)
    ]
    require(len(calls) == 54, "selector array call count differs")
    require(sum(count for _, count in calls) == 540, "selector row total differs")
    require((0x84DBC768, 30) in calls, "focused selector array call is missing")
    return calls


def build_report(args: argparse.Namespace) -> tuple[dict[str, object], list[dict[str, object]]]:
    image = args.apf_pe.read_bytes()
    require(sha256(image) == EXPECTED_PE_SHA256, "APF decompressed PE changed")
    require(TABLE_AFTER_LAST == 0x84DB4850, "table end arithmetic differs")
    table_bytes = image[TABLE_FIRST - IMAGE_BASE : TABLE_AFTER_LAST - IMAGE_BASE]
    require(sha256(table_bytes) == EXPECTED_TABLE_SHA256, "animation table bytes changed")

    strings = utf16_strings(image)
    lineage, lineage_by_name = parse_lineage(args.lineage)
    mocap = json.loads(args.mocap_report.read_text(encoding="utf-8"))
    require(mocap.get("schema") == "apf_mocap_inventory/v1", "mocap schema differs")
    require(mocap["proved_layout"]["serialized_root_size"] == 48, (
        "SingleMoCap root size differs"
    ))
    require(mocap["proved_layout"]["fixed_pointer_fields"] == [32, 36, 40, 44], (
        "SingleMoCap pointer fields differ"
    ))

    ghidra_trace = args.ghidra_trace.read_text(encoding="utf-8")
    ghidra_pseudo = args.ghidra_pseudo.read_text(encoding="utf-8")
    for marker in (
        "Program MD5: 217eea6084c3d03f0f1143802b1f5636",
        "Table: 0x84D75500..0x84DB4850 record_size=0x2C record_count=5884",
        "CODE_REFERENCE_COUNT 0",
        "CLASSIC_MATERIALIZATION_COUNT 0",
        "LINKED_CODE_REF 0x848AF59C->0x84DBC768",
        "LINKED_CODE_REF 0x848EA3EC->0x84DEB650",
        "RAW_SPAN 0x848AEB78..0x848AEC10",
        "RAW_SPAN 0x848FD440..0x848FD478",
        "0x848FDC04 raw=0x38800000 instruction=li r4,0x0",
        "0x848FDF78 raw=0x38800001 instruction=li r4,0x1",
    ):
        require(marker in ghidra_trace, f"Ghidra trace lacks {marker!r}")
    for marker in (
        "0x848AEB80:APF_AnimationSelectorArrayInit_Body",
        "0x848AF560:Function_848AF560",
        "refs=0x848D55DC(none,UNCONDITIONAL_CALL)",
        "Function_848AEB78(0xffffffff84dbc768,0x1e);",
        "0x848EA3B0:FUN_848ea3b0",
        "(&PTR_PTR_84deb650)[uVar1 * 0xb + param_2]",
        "0x848FD398:Function_848FD398",
    ):
        require(marker in ghidra_pseudo, f"Ghidra pseudo-C lacks {marker!r}")

    # Parse the exact 0x2c-byte name/definition table.
    records: list[dict[str, object]] = []
    mappings: list[dict[str, object]] = []
    aggregate_records: dict[int, list[dict[str, object]]] = defaultdict(list)
    for index in range(TABLE_RECORD_COUNT):
        address = TABLE_FIRST + index * TABLE_RECORD_SIZE
        value = words(image, address, 11)
        filename = strings.get(value[0])
        primary = strings.get(value[1])
        paired = strings.get(value[2]) if value[2] else None
        require(filename is not None and filename.strip().lower().endswith(".ani"), (
            f"record {index} lacks an .ani filename"
        ))
        require(primary is not None and primary.startswith("ANM_"), (
            f"record {index} lacks a primary ANM name"
        ))
        require(value[7:] == (0, 0, 0, 0), f"record {index} tail is nonzero")
        record = {
            "index": index,
            "address": address,
            "words": value,
            "filename": filename.strip(),
            "primary": primary,
            "paired": paired,
        }
        selected = False
        for name_field, root_field, role in ((1, 3, "primary"), (2, 4, "paired")):
            name = strings.get(value[name_field]) if value[name_field] else None
            if name is None or "2K6" not in name.upper():
                continue
            selected = True
            require(name in lineage_by_name, f"lineage lacks {name}")
            root = value[root_field]
            require(root != 0, f"{name} has no motion root")
            root_words = words(image, root, 12)
            require(root_words[0] >> 24 == 0x89, f"{name} root flags differ")
            require(all(IMAGE_BASE <= root_words[field // 4] < IMAGE_BASE + len(image)
                        for field in (0x20, 0x24, 0x28)), (
                f"{name} lacks bounded absolute motion streams"
            ))
            require(root_words[0x2C // 4] == 0, f"{name} optional root pointer differs")
            identifier = lineage_by_name[name]
            pointer_address = address + name_field * 4
            lineage_refs = {
                int(item, 16)
                for item in identifier["pointer_reference_addresses"].split(",")
            }
            require(pointer_address in lineage_refs, f"{name} reference join differs")
            duration = struct.unpack_from(">f", image, root - IMAGE_BASE + 0x10)[0]
            require(math.isfinite(duration) and duration > 0, f"{name} duration differs")
            aggregate = value[5]
            target_group = aggregate if aggregate else root
            mapping = {
                "mapping_index": len(mappings),
                "identifier_index": int(identifier["index"]),
                "name": name,
                "category": identifier["category"],
                "name_role": role,
                "name_virtual_address": value[name_field],
                "name_pointer_field_address": pointer_address,
                "record_index": index,
                "record_address": address,
                "animation_filename": filename.strip(),
                "animation_filename_virtual_address": value[0],
                "single_mocap_root_address": root,
                "single_mocap_flags": root_words[0],
                "single_mocap_sample_count_raw_u16": struct.unpack_from(
                    ">H", image, root - IMAGE_BASE + 4
                )[0],
                "single_mocap_duration": duration,
                "packed_stream_address": root_words[8],
                "root_stream_address": root_words[9],
                "event_stream_address": root_words[10],
                "variant_aggregate_address": aggregate,
                "variant_index": value[6],
                "runtime_target_group_address": target_group,
            }
            mappings.append(mapping)
        if selected:
            records.append(record)
            if value[5]:
                aggregate_records[value[5]].append(record)

    require(len(records) == 309, "2K6 definition record count differs")
    require(len(mappings) == 597, "2K6 name/root mapping count differs")
    require(len({row["name"] for row in mappings}) == 519, "2K6 unique mapping names differ")
    require(len({row["single_mocap_root_address"] for row in mappings}) == 597, (
        "2K6 roots are not one-to-one with name-field mappings"
    ))
    require(Counter(row["name_role"] for row in mappings) == {
        "primary": 309, "paired": 288,
    }, "2K6 name-field role counts differ")
    require(len({row["animation_filename"] for row in mappings}) == 225, (
        "2K6 .ani filename count differs"
    ))

    # +0x14 points to count + 0x10-byte member records. The primary root in
    # each 0x2c definition is exactly the member selected by +0x18.
    aggregate_rows: list[dict[str, object]] = []
    for aggregate, member_records in sorted(aggregate_records.items()):
        count = u32(image, aggregate)
        ordered = sorted(member_records, key=lambda row: row["words"][6])
        indices = [row["words"][6] for row in ordered]
        member_roots = [u32(image, aggregate + 4 + index * 0x10) for index in range(count)]
        definition_roots = [row["words"][3] for row in ordered]
        require(count in (2, 3), f"aggregate {hx(aggregate)} count differs")
        require(indices == list(range(count)), f"aggregate {hx(aggregate)} variants differ")
        require(member_roots == definition_roots, f"aggregate {hx(aggregate)} roots differ")
        aggregate_rows.append({
            "address": hx(aggregate),
            "member_count": count,
            "definition_record_addresses": [hx(row["address"]) for row in ordered],
            "primary_root_addresses": [hx(root) for root in member_roots],
        })
    require(len(aggregate_rows) == 75, "2K6 aggregate count differs")
    require(Counter(row["member_count"] for row in aggregate_rows) == {2: 66, 3: 9}, (
        "2K6 aggregate size distribution differs"
    ))

    # Recover the 54 arrays explicitly enumerated by 0x848AF560 and join their
    # +0 payload/config targets back to 2K6 definition groups.
    selector_calls = parse_selector_calls(ghidra_pseudo)
    selector_by_target: dict[int, list[dict[str, object]]] = defaultdict(list)
    selector_arrays: list[dict[str, object]] = []
    for array_index, (array, count) in enumerate(selector_calls):
        entries: list[dict[str, object]] = []
        for index in range(count):
            address = array + index * SELECTOR_RECORD_SIZE
            value = words(image, address, 9)
            entry = {
                "array_index": array_index,
                "array_address": hx(array),
                "array_count": count,
                "record_index": index,
                "record_address": hx(address),
                "target_address": hx(value[0]),
                "selector_code": hx(value[6]),
                "raw_words": [hx(word) for word in value],
            }
            entries.append(entry)
            if value[0]:
                selector_by_target[value[0]].append(entry)
        selector_arrays.append({
            "index": array_index,
            "address": hx(array),
            "record_count": count,
            "byte_length": count * SELECTOR_RECORD_SIZE,
        })

    for mapping in mappings:
        selector_entries = selector_by_target[mapping["runtime_target_group_address"]]
        mapping["selector_record_addresses"] = ",".join(
            entry["record_address"] for entry in selector_entries
        )
        mapping["selector_record_count"] = len(selector_entries)

    selector_links_by_address: dict[str, dict[str, object]] = {}
    for mapping in mappings:
        for entry in selector_by_target[mapping["runtime_target_group_address"]]:
            selector_links_by_address[entry["record_address"]] = entry
    selector_links = [selector_links_by_address[key] for key in sorted(selector_links_by_address)]
    linked_names = {row["name"] for row in mappings if row["selector_record_count"]}
    linked_records = {row["record_address"] for row in mappings if row["selector_record_count"]}
    linked_targets = {
        row["runtime_target_group_address"]
        for row in mappings if row["selector_record_count"]
    }
    require(len(selector_links) == 49, "2K6 selector link count differs")
    require(len(linked_targets) == 49, "2K6 selector target count differs")
    require(len(linked_records) == 106, "2K6 selector-linked definition count differs")
    require(len(linked_names) == 149, "2K6 selector-linked name count differs")

    # Two exact runtime-owner worked examples.
    first = next(row for row in mappings if row["name"] == "ANM_BLOCK_2K6_PASS_LOW_B(0)")
    require(first["record_address"] == 0x84D7E6C0, "first 2K6 record differs")
    require(first["single_mocap_root_address"] == 0x8409BB00, "first 2K6 root differs")
    require(first["variant_aggregate_address"] == 0x8409C820, "first aggregate differs")
    require(u32(image, 0x84DBC8AC) == 0x8409C820, "selector payload link differs")
    require((0x84DBC8AC - 0x84DBC768) // SELECTOR_RECORD_SIZE == 9, (
        "focused selector index differs"
    ))

    movement = next(
        row for row in mappings if row["name"] == "ANM_MOVEMENT_2K6_LM_READY_WALK_B"
    )
    require(movement["record_address"] == 0x84D9109C, "movement record differs")
    require(movement["single_mocap_root_address"] == 0x834DD0A8, "movement root differs")
    require(u32(image, 0x820BE30C) == 0x834DD0A8, "movement config root differs")
    require(u32(image, 0x84DEB6A0) == 0x820BE2FC, "master lookup slot 20 differs")
    require(u32(image, 0x84DEB6A4) == 0x820BE2FC, "master lookup slot 21 differs")

    # Convert integer addresses in the public mapping rows to fixed-width text.
    table_rows: list[dict[str, object]] = []
    for mapping in mappings:
        table_rows.append({
            key: hx(value) if key.endswith("_address") and isinstance(value, int) else value
            for key, value in mapping.items()
        })

    table_field_distribution = []
    for field in range(11):
        values = [record_words[field] for record_words in (
            words(image, TABLE_FIRST + index * TABLE_RECORD_SIZE, 11)
            for index in range(TABLE_RECORD_COUNT)
        )]
        table_field_distribution.append({
            "offset": f"+0x{field * 4:02X}",
            "zero_count": values.count(0),
            "nonzero_count": TABLE_RECORD_COUNT - values.count(0),
            "unique_value_count": len(set(values)),
        })

    report: dict[str, object] = {
        "schema": SCHEMA,
        "result": {
            "definition_table_record_count": TABLE_RECORD_COUNT,
            "definition_table_record_size": TABLE_RECORD_SIZE,
            "two_k6_definition_record_count": len(records),
            "two_k6_unique_identifier_count": len({row["name"] for row in mappings}),
            "two_k6_name_field_mapping_count": len(mappings),
            "two_k6_unique_animation_filename_count": len({
                row["animation_filename"] for row in mappings
            }),
            "two_k6_unique_single_mocap_root_count": len({
                row["single_mocap_root_address"] for row in mappings
            }),
            "all_two_k6_mappings_have_concrete_motion_roots": True,
            "selector_array_count": len(selector_arrays),
            "selector_array_record_count": sum(row["record_count"] for row in selector_arrays),
            "two_k6_selector_target_group_count": len(linked_targets),
            "two_k6_selector_linked_definition_count": len(linked_records),
            "two_k6_selector_linked_identifier_count": len(linked_names),
            "name_definition_table_direct_code_reference_count": 0,
            "name_definition_table_classic_materialization_count": 0,
            "at_least_one_two_k6_payload_has_code_owned_runtime_config": True,
            "worked_movement_config_reached_by_recovered_direct_lookup_calls": False,
            "runtime_execution_observed": False,
            "runtime_consumption_of_every_identifier_proved": False,
            "formal_nfl_2k6_product_identity_proved": False,
        },
        "definition_table": {
            "first": hx(TABLE_FIRST),
            "after_last": hx(TABLE_AFTER_LAST),
            "byte_length": len(table_bytes),
            "sha256": sha256(table_bytes),
            "adjacent_words": {
                hx(TABLE_AFTER_LAST): hx(u32(image, TABLE_AFTER_LAST)),
                hx(TABLE_AFTER_LAST + 4): hx(u32(image, TABLE_AFTER_LAST + 4)),
                "note": "the second word equals 5,884, but its owning structure/meaning is unproved",
            },
            "field_contract": {
                "+0x00": "UTF-16BE .ani source filename pointer",
                "+0x04": "primary animation identifier pointer",
                "+0x08": "paired animation identifier pointer or null",
                "+0x0C": "primary in-XEX motion root pointer or null",
                "+0x10": "paired in-XEX motion root pointer or null",
                "+0x14": "variant aggregate pointer or null",
                "+0x18": "variant index 0..3",
                "+0x1C..+0x28": "zero in all 5,884 records",
            },
            "field_distribution": table_field_distribution,
            "ownership": {
                "ghidra_code_references_into_range": 0,
                "tracked_classic_address_materializations_into_range_or_trailer": 0,
                "classification": (
                    "compiled name/definition metadata with no recovered direct consumer; "
                    "debug/enum-only is possible but not proved"
                ),
            },
        },
        "motion_payload_contract": {
            "root_size": 48,
            "absolute_pointer_fields": ["+0x20", "+0x24", "+0x28", "+0x2C"],
            "selected_root_flags_high_byte": "0x89",
            "selected_nonnull_stream_fields": ["+0x20", "+0x24", "+0x28"],
            "selected_optional_stream_field": "+0x2C is null in all 597 mappings",
            "variant_aggregate_count": len(aggregate_rows),
            "variant_aggregate_size_distribution": {"2": 66, "3": 9},
            "source_filename_boundary": (
                ".ani values are compiled source filenames, not proof of standalone files "
                "on the retail disc"
            ),
        },
        "selector_array_path": {
            "initializer": "0x848AF560",
            "direct_call_site": "0x848D55DC",
            "common_helper_entry": "0x848AEB78",
            "transient_recovered_helper_body": "0x848AEB80..0x848AEC0F",
            "record_stride": SELECTOR_RECORD_SIZE,
            "array_count": len(selector_arrays),
            "record_count": sum(row["record_count"] for row in selector_arrays),
            "worked": {
                "definition_record": "0x84D7E6C0",
                "identifier": "ANM_BLOCK_2K6_PASS_LOW_B(0)",
                "source_filename": "cb300_fa_ply_01.ani",
                "motion_root": "0x8409BB00",
                "variant_aggregate": "0x8409C820",
                "selector_array": "0x84DBC768",
                "selector_array_count": 30,
                "selector_record_index": 9,
                "selector_record": "0x84DBC8AC",
            },
            "boundary": (
                "the initializer enumerates the array and the helper body consumes 0x24-byte "
                "records, but retail execution of this exact row was not observed"
            ),
            "arrays": selector_arrays,
            "two_k6_links": selector_links,
        },
        "master_runtime_lookup_path": {
            "lookup_function": "0x848EA3B0",
            "direct_call_sites": ["0x848FD460", "0x848FDC0C", "0x848FDF80"],
            "recovered_direct_call_selector_domain": [0, 1, 2, 3, 4, 5, 6, 7],
            "master_pointer_array": "0x84DEB650",
            "index_equation": "clamp(((object->field_44->word_10 >> 4) & 3), 0, 2) * 11 + selector",
            "worked": {
                "definition_record": "0x84D9109C",
                "identifier": "ANM_MOVEMENT_2K6_LM_READY_WALK_B",
                "source_filename": "mr115_fa_ply_02.ani",
                "motion_root": "0x834DD0A8",
                "config_pointer": "0x820BE2FC",
                "config_motion_root_field": "0x820BE30C",
                "master_slots": ["0x84DEB6A0", "0x84DEB6A4"],
                "master_slot_indices": [20, 21],
            },
            "boundary": (
                "the lookup and three direct callers are code-owned, but those callers supply "
                "selectors only in 0..7; the worked 2K6 config occupies class-1 slots 9/10 "
                "(master indices 20/21), so no recovered direct call reaches it. Indirect "
                "callers remain unproved rather than assumed"
            ),
        },
        "aggregates": aggregate_rows,
        "mappings": table_rows,
        "interpretation": {
            "proved": (
                "All 597 2K6-tagged name-field occurrences map one-to-one to concrete in-XEX "
                "motion roots and .ani source filenames; 149 identifiers also join 49 target "
                "groups consumed by the selector-array initializer. A separate 2K6 movement "
                "payload sits in a code-owned lookup array, although recovered direct callers "
                "do not select its two slots."
            ),
            "name_table_boundary": (
                "The 5,884-record name/definition table itself has no recovered code reference "
                "or classic address materialization, so its strings may be generated metadata."
            ),
            "not_debug_only": (
                "The names alone could be metadata, but their payloads are not merely strings: "
                "they contain bounded motion roots and selected roots participate in code-owned "
                "selector/config paths."
            ),
            "product_boundary": (
                "This proves 2K6-era gameplay/animation lineage and surviving payloads, not a "
                "formal, complete, titled, or releasable NFL 2K6 product build."
            ),
        },
        "sources": {
            "apf_memory_image": pin(
                args.apf_pe, "derived/apf2k8/default.xex.pe-memory-image"
            ),
            "lineage_report": pin(
                args.lineage,
                "reports/cut_content/apf_nfl_lineage/apf_2k6_animation_lineage.json",
            ),
            "mocap_report": pin(
                args.mocap_report, "reports/assets/apf_mocap_inventory.json"
            ),
            "ghidra_trace": pin(
                args.ghidra_trace,
                "reports/cut_content/apf_nfl_lineage/apf_2k6_animation_runtime_ghidra/"
                "apf_2k6_animation_runtime_ghidra_trace.txt",
            ),
            "ghidra_pseudo_c": pin(
                args.ghidra_pseudo,
                "reports/cut_content/apf_nfl_lineage/apf_2k6_animation_runtime_ghidra/"
                "apf_2k6_animation_runtime_ghidra_pseudo_c.c",
            ),
            "generator": pin(Path(__file__), "tools/apf_2k6_animation_runtime.py"),
        },
        "portme": [
            "// PORTME(0x84D75500): recover any indirect/non-classic owner before calling the 5,884-record name table live.",
            "// PORTME(0x848AEB78): translate the shared-save wrapper and full selector-array initializer to compilable native source.",
            "// PORTME(0x848FDC0C): recover missing caller boundaries and prove the concrete selector values reaching every 2K6 config.",
            "// PORTME: require an exact formal product/build identifier before naming the retail executable a cancelled NFL 2K6 build.",
        ],
    }
    return report, table_rows


def write_tsv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(rows[0]), dialect="excel-tab", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apf-pe", type=Path, required=True)
    parser.add_argument("--lineage", type=Path, required=True)
    parser.add_argument("--mocap-report", type=Path, required=True)
    parser.add_argument("--ghidra-trace", type=Path, required=True)
    parser.add_argument("--ghidra-pseudo", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--tsv", type=Path, required=True)
    args = parser.parse_args()

    report, rows = build_report(args)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_tsv(args.tsv, rows)
    print(
        "APF_2K6_ANIMATION_RUNTIME_REPORT_COMPLETE "
        f"mappings={len(rows)} selector_links={report['result']['two_k6_selector_target_group_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

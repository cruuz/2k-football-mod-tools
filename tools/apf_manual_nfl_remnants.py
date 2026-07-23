#!/usr/bin/env python3
"""Prove the 15-page NFL 2K5 manual descendant shipped in APF 2K8.

The analysis is read-only.  It compares APF outer 499 ``manual.iff`` with NFL
2K5 outer 109, validates every APF MANU record pointer, separates mechanical
markup conversion from authored text edits, and records the compiled APF MANU
handler without claiming menu reachability.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
from pathlib import Path
import re
import struct
import sys
import zlib

import apf_inner
import apf_outer
import nfl_outer
from apf_reference_nfl_remnants import (
    EvidenceError,
    EXPECTED_APF_INDEX_SHA256,
    EXPECTED_NFL_INDEX_SHA256,
    EXPECTED_NFL_XBE_SHA256,
    accessor_values,
    directed_hausdorff,
    extract_text_runs,
    sha256_bytes,
    source_pin,
    utf16be_z,
)


SCHEMA = "vc_apf_manual_nfl_remnants/v1"
APF_OUTER_INDEX = 499
NFL_OUTER_INDEX = 109
APF_OUTER_ID = 0x53E0EB08
NFL_OUTER_ID = 0x87408605
MANU_TYPE_HASH = 0x4C997FFB
MAX_DECOMPRESSED = 32 * 1024 * 1024

PAGE_TITLES = [
    "CONTROL SUMMARY",
    "QUICK GAME ",
    "In-Game Pause Menu ",
    "THE CRIB|TM|",
    "FRANCHISE",
    "OFF-SEASON TASKS",
    "FIRST PERSON Football|TM|",
    "ESPN 25th ANNIVERSARY",
    "PRACTICE",
    "SITUATION",
    "TOURNAMENT",
    "Features",
    "Options",
    "Extras",
    "Xbox Live",
]


def u32be(data: bytes, offset: int, what: str) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise EvidenceError(f"{what}: u32be at 0x{offset:x} is out of bounds")
    return struct.unpack_from(">I", data, offset)[0]


def u32le(data: bytes, offset: int, what: str) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise EvidenceError(f"{what}: u32le at 0x{offset:x} is out of bounds")
    return struct.unpack_from("<I", data, offset)[0]


def align_up(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def read_apf_parts(
    record: apf_inner.IFFRecord, blocks: list[bytes], file_index: int
) -> list[bytes]:
    result: list[bytes] = []
    for part in record.files[file_index].parts:
        payload = blocks[part.block_index]
        if part.offset + part.length > len(payload):
            raise EvidenceError("APF MANU part exceeds decoded block")
        result.append(payload[part.offset : part.offset + part.length])
    return result


def validate_apf_manu_body(name: str, body: bytes) -> dict[str, object]:
    runs = extract_text_runs(body, "big")
    record_count = u32be(body, 0, f"{name} record count")
    if record_count != len(runs):
        raise EvidenceError(
            f"{name}: record count {record_count} != printable string count {len(runs)}"
        )
    table_start = 4
    stride = 12
    table_end = table_start + record_count * stride
    targets: list[int] = []
    for index in range(record_count):
        pointer_field = table_start + index * stride + 8
        raw = u32be(body, pointer_field, f"{name} record {index} text pointer")
        if raw == 0:
            raise EvidenceError(f"{name}: record {index} has a null text pointer")
        target = pointer_field + raw - 1
        if target < table_end or target >= len(body) or target & 1:
            raise EvidenceError(
                f"{name}: record {index} text pointer target 0x{target:x} is invalid"
            )
        utf16be_z(body, target, f"{name} record {index} text")
        targets.append(target)
    if len(set(targets)) != record_count:
        raise EvidenceError(f"{name}: MANU text pointer targets are not unique")
    return {
        "name": name,
        "body_size": len(body),
        "body_sha256": sha256_bytes(body),
        "record_count": record_count,
        "record_stride": stride,
        "record_table_offset": "0x4",
        "record_table_end": f"0x{table_end:x}",
        "nonzero_text_pointer_count": len(targets),
        "unique_text_pointer_target_count": len(set(targets)),
        "minimum_text_pointer_target": f"0x{min(targets):x}",
        "all_text_pointers_valid": True,
        "strings": runs,
    }


def parse_apf_manual(apf_index: Path) -> tuple[dict[str, object], dict[int, dict[str, object]]]:
    archive = apf_outer.parse_archive(apf_index)
    entry = archive.entries[APF_OUTER_INDEX]
    if entry.name_id != APF_OUTER_ID:
        raise EvidenceError("APF manual.iff outer ID changed")
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        blocks = [
            apf_inner.decode_block(reader, record, index, MAX_DECOMPRESSED)
            for index in range(record.block_count)
        ]

    manu_files = [file for file in record.files if file.type_name == "MANU"]
    scene_files = [file for file in record.files if file.type_name == "SCNE"]
    if len(manu_files) != 15 or len(scene_files) != 1 or scene_files[0].name != "open_book":
        raise EvidenceError("APF manual.iff resource composition changed")
    expected_names = {f"xenon-{index}" for index in range(1, 16)}
    if {file.name for file in manu_files} != expected_names:
        raise EvidenceError("APF xenon manual page-name set changed")
    if any(file.type_hash != MANU_TYPE_HASH for file in manu_files):
        raise EvidenceError("APF MANU type hash changed")

    pages: dict[int, dict[str, object]] = {}
    for file in manu_files:
        page_number = int(file.name.split("-")[1])
        parts = read_apf_parts(record, blocks, file.index)
        if len(parts) != 1:
            raise EvidenceError(f"{file.name}: expected one DRAM part")
        page = validate_apf_manu_body(file.name, parts[0])
        first = page["strings"][0].text
        expected_title = PAGE_TITLES[page_number - 1]
        if first != f"<title>{expected_title}":
            raise EvidenceError(
                f"{file.name}: title {first!r} != {expected_title!r}"
            )
        page["page_number"] = page_number
        page["title"] = expected_title.strip()
        page["inner_index"] = file.index
        pages[page_number] = page

    return {
        "outer_index": APF_OUTER_INDEX,
        "outer_id": f"0x{entry.name_id:08x}",
        "outer_size": entry.size,
        "filename": "manual.iff",
        "filename_hash_rule": "CRC32 uppercase ASCII",
        "resource_count": len(record.files),
        "manual_page_count": 15,
        "scene_count": 1,
        "physical_resource_order": [
            {"index": file.index, "name": file.name, "type": file.type_name}
            for file in record.files
        ],
        "logical_page_names": [f"xenon-{index}" for index in range(1, 16)],
        "open_book_inner_index": scene_files[0].index,
    }, pages


def parse_nfl_manual(nfl_index: Path) -> tuple[dict[str, object], dict[int, dict[str, object]]]:
    archive = nfl_outer.parse_archive(nfl_index)
    entry = archive.entries[NFL_OUTER_INDEX]
    if entry.name_id != NFL_OUTER_ID:
        raise EvidenceError("NFL manual.iff outer ID changed")
    outer = nfl_outer.read_entry_bytes(archive, entry, max_size=4 * 1024 * 1024)
    offset = 0
    pages: dict[int, dict[str, object]] = {}
    chunks: list[dict[str, object]] = []
    while offset < len(outer):
        if offset + 32 > len(outer):
            raise EvidenceError("NFL manual.iff has a truncated chunk")
        kind = outer[offset : offset + 4].decode("ascii")
        stored_size = u32le(outer, offset + 4, "NFL manual chunk size")
        total_size = 32 + stored_size
        if offset + total_size > len(outer):
            raise EvidenceError("NFL manual chunk exceeds outer entry")
        chunk = outer[offset : offset + total_size]
        chunks.append(
            {
                "index": len(chunks),
                "offset": offset,
                "kind": kind,
                "stored_size": stored_size,
                "total_size": total_size,
            }
        )
        if kind == "MANU":
            name_start = 0x40
            name_end = name_start
            while name_end + 1 < len(chunk) and chunk[name_end : name_end + 2] != b"\0\0":
                name_end += 2
            if name_end + 1 >= len(chunk):
                raise EvidenceError("NFL MANU page name is unterminated")
            name = chunk[name_start:name_end].decode("utf-16le")
            match = re.fullmatch(r"xb-(\d+)", name)
            if match is None:
                raise EvidenceError(f"unexpected NFL MANU page name {name!r}")
            page_number = int(match.group(1))
            body_start = align_up(name_end + 2, 4)
            body = chunk[body_start:]
            runs = extract_text_runs(body, "little")
            record_count = u32le(body, 0, f"{name} record count")
            if record_count != len(runs):
                raise EvidenceError(
                    f"{name}: count {record_count} != printable strings {len(runs)}"
                )
            title = runs[0].text
            if title != f"<title>{PAGE_TITLES[page_number - 1]}":
                raise EvidenceError(f"{name}: logical title changed")
            pages[page_number] = {
                "name": name,
                "page_number": page_number,
                "title": PAGE_TITLES[page_number - 1].strip(),
                "chunk_index": len(chunks) - 1,
                "chunk_offset": offset,
                "body_offset_in_chunk": body_start,
                "body_size": len(body),
                "body_sha256": sha256_bytes(body),
                "record_count": record_count,
                "strings": runs,
            }
        offset += total_size
    if offset != len(outer):
        raise EvidenceError("NFL manual.iff chunks do not close outer entry")
    if len(chunks) != 16 or [row["kind"] for row in chunks] != ["MANU"] * 15 + ["SCNE"]:
        raise EvidenceError("NFL manual.iff chunk composition changed")
    if set(pages) != set(range(1, 16)):
        raise EvidenceError("NFL xb-1..xb-15 page set changed")
    return {
        "outer_index": NFL_OUTER_INDEX,
        "outer_id": f"0x{entry.name_id:08x}",
        "outer_size": entry.size,
        "outer_sha256": sha256_bytes(outer),
        "filename": "manual.iff",
        "filename_hash_rule": "CRC32 uppercase UTF-16LE",
        "chunk_count": len(chunks),
        "manual_page_count": 15,
        "scene_count": 1,
        "logical_page_names": [f"xb-{index}" for index in range(1, 16)],
        "chunks": chunks,
    }, pages


def normalized_markup(text: str) -> str:
    """Normalize only two proved serializer/platform-markup substitutions."""

    return text.replace("|B|<br>", "<br>").replace("=>", "|RARROW|")


def classify_authored_difference(apf_text: str, nfl_text: str) -> str:
    if "|M_RIGHTSTICK|" in apf_text and "|RANALOG|" in nfl_text:
        return "xenon_control_token"
    if "40 hour" in apf_text and "60 hour" in nfl_text or (
        "40 hours" in apf_text and "60 hours" in nfl_text
    ):
        return "weekly_prep_hours_60_to_40"
    if apf_text.replace("|ANALOG|", "The |ANALOG|").replace(
        "|RANALOG|", "The |RANALOG|"
    ) == nfl_text:
        return "minor_article_cleanup"
    if "challenge" in apf_text.lower() and "challenge" in nfl_text.lower():
        return "xbox_live_challenge_copy"
    return "unclassified"


def compare_pages(
    apf_pages: dict[int, dict[str, object]],
    nfl_pages: dict[int, dict[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    page_rows: list[dict[str, object]] = []
    authored_diffs: list[dict[str, object]] = []
    total_apf = total_nfl = raw_matches = normalized_matches = 0
    all_apf_runs = []

    for page_number in range(1, 16):
        apf_runs = apf_pages[page_number]["strings"]
        nfl_runs = nfl_pages[page_number]["strings"]
        apf_text = [run.text for run in apf_runs]
        nfl_text = [run.text for run in nfl_runs]
        if len(apf_text) != len(nfl_text):
            raise EvidenceError(f"manual page {page_number} string cardinality differs")
        total_apf += len(apf_text)
        total_nfl += len(nfl_text)
        all_apf_runs.extend((page_number, run) for run in apf_runs)

        raw_matcher = difflib.SequenceMatcher(a=apf_text, b=nfl_text, autojunk=False)
        page_raw_matches = sum(
            i2 - i1
            for tag, i1, i2, _j1, _j2 in raw_matcher.get_opcodes()
            if tag == "equal"
        )
        normalized_apf = [normalized_markup(value) for value in apf_text]
        normalized_nfl = [normalized_markup(value) for value in nfl_text]
        normalized_matcher = difflib.SequenceMatcher(
            a=normalized_apf, b=normalized_nfl, autojunk=False
        )
        page_normalized_matches = sum(
            i2 - i1
            for tag, i1, i2, _j1, _j2 in normalized_matcher.get_opcodes()
            if tag == "equal"
        )
        raw_matches += page_raw_matches
        normalized_matches += page_normalized_matches

        for tag, i1, i2, j1, j2 in normalized_matcher.get_opcodes():
            if tag == "equal":
                continue
            if tag != "replace" or i2 - i1 != j2 - j1:
                raise EvidenceError(
                    f"manual page {page_number}: unexpected normalized diff shape {tag}"
                )
            for delta in range(i2 - i1):
                apf_run = apf_runs[i1 + delta]
                nfl_run = nfl_runs[j1 + delta]
                classification = classify_authored_difference(apf_run.text, nfl_run.text)
                if classification == "unclassified":
                    raise EvidenceError(
                        f"manual page {page_number}: unclassified authored difference"
                    )
                authored_diffs.append(
                    {
                        "page_number": page_number,
                        "page_title": PAGE_TITLES[page_number - 1].strip(),
                        "classification": classification,
                        "sequence_index": i1 + delta,
                        "apf_offset": f"0x{apf_run.offset:x}",
                        "nfl_offset": f"0x{nfl_run.offset:x}",
                        "apf_text": apf_run.text,
                        "nfl_text": nfl_run.text,
                    }
                )

        page_rows.append(
            {
                "page_number": page_number,
                "title": PAGE_TITLES[page_number - 1].strip(),
                "apf_name": f"xenon-{page_number}",
                "nfl_name": f"xb-{page_number}",
                "string_count": len(apf_text),
                "raw_exact_ordered_matches": page_raw_matches,
                "markup_normalized_exact_ordered_matches": page_normalized_matches,
                "authored_difference_count": len(apf_text) - page_normalized_matches,
                "apf_body_size": apf_pages[page_number]["body_size"],
                "nfl_body_size": nfl_pages[page_number]["body_size"],
            }
        )

    classification_counts: dict[str, int] = {}
    for row in authored_diffs:
        key = str(row["classification"])
        classification_counts[key] = classification_counts.get(key, 0) + 1
    expected_classifications = {
        "xenon_control_token": 2,
        "minor_article_cleanup": 2,
        "weekly_prep_hours_60_to_40": 3,
        "xbox_live_challenge_copy": 2,
    }
    if classification_counts != expected_classifications:
        raise EvidenceError(f"manual authored-difference classes changed: {classification_counts}")

    licensed_patterns = {
        "NFL_token": re.compile(r"\bNFL\b", re.IGNORECASE),
        "ESPN_token": re.compile(r"\bESPN\b", re.IGNORECASE),
        "ESPN_NFL_2K5": re.compile(r"ESPN NFL 2K5", re.IGNORECASE),
        "Franchise": re.compile(r"\bFranchise\b", re.IGNORECASE),
        "The_Crib": re.compile(r"The Crib", re.IGNORECASE),
        "First_Person_Football": re.compile(r"First Person Football", re.IGNORECASE),
        "Weekly_Prep": re.compile(r"Weekly Prep", re.IGNORECASE),
        "Xbox_Live": re.compile(r"Xbox Live", re.IGNORECASE),
    }
    licensed_rows: list[dict[str, object]] = []
    category_counts = {key: 0 for key in licensed_patterns}
    for page_number, run in all_apf_runs:
        categories = [
            key for key, pattern in licensed_patterns.items() if pattern.search(run.text)
        ]
        for category in categories:
            category_counts[category] += 1
        if categories:
            licensed_rows.append(
                {
                    "page_number": page_number,
                    "page_title": PAGE_TITLES[page_number - 1].strip(),
                    "offset": f"0x{run.offset:x}",
                    "categories": ",".join(categories),
                    "text": run.text,
                }
            )

    if (total_apf, total_nfl, raw_matches, normalized_matches, len(authored_diffs)) != (
        1553, 1553, 1414, 1544, 9
    ):
        raise EvidenceError("manual corpus totals changed")
    return {
        "apf_string_slot_count": total_apf,
        "nfl_string_slot_count": total_nfl,
        "page_string_cardinalities_exact_match": True,
        "raw_exact_ordered_string_matches": raw_matches,
        "raw_exact_match_fraction": raw_matches / total_apf,
        "mechanical_markup_normalizations": [
            {"nfl": "|B|<br>", "apf": "<br>"},
            {"nfl": "=>", "apf": "|RARROW|"},
        ],
        "markup_normalized_exact_ordered_string_matches": normalized_matches,
        "markup_normalized_exact_match_fraction": normalized_matches / total_apf,
        "authored_difference_string_count": len(authored_diffs),
        "authored_difference_class_counts": classification_counts,
        "licensed_category_string_counts": category_counts,
        "interpretation": (
            "all 15 NFL 2K5 manual pages were converted to Xenon resources; "
            "markup/control/online/Weekly-Prep edits prove an authored platform port"
        ),
    }, page_rows, authored_diffs, licensed_rows


def compare_open_book_geometry(apf_gltf: Path, nfl_gltf: Path) -> dict[str, object]:
    apf_doc = json.loads(apf_gltf.read_text())
    nfl_doc = json.loads(nfl_gltf.read_text())
    expected_nodes = ["book", "tab1", "tab2", "tab3", "tab4"]
    if [node["name"] for node in apf_doc["nodes"]] != expected_nodes:
        raise EvidenceError("APF manual open_book node order changed")
    if [node["name"] for node in nfl_doc["nodes"]] != expected_nodes:
        raise EvidenceError("NFL manual open_book node order changed")

    meshes: list[dict[str, object]] = []
    for name in expected_nodes:
        apf_mesh = next(mesh for mesh in apf_doc["meshes"] if mesh["name"] == name)
        nfl_mesh = next(mesh for mesh in nfl_doc["meshes"] if mesh["name"] == name)
        apf_primitives = apf_mesh["primitives"]
        nfl_primitives = nfl_mesh["primitives"]
        apf_position_accessors = {
            primitive["attributes"]["POSITION"] for primitive in apf_primitives
        }
        nfl_position_accessors = {
            primitive["attributes"]["POSITION"] for primitive in nfl_primitives
        }
        if len(apf_position_accessors) != 1 or len(nfl_position_accessors) != 1:
            raise EvidenceError("manual open_book mesh uses multiple POSITION accessors")
        apf_positions = accessor_values(apf_gltf, next(iter(apf_position_accessors)))
        nfl_positions = accessor_values(nfl_gltf, next(iter(nfl_position_accessors)))
        apf_index_count = sum(
            len(accessor_values(apf_gltf, primitive["indices"]))
            for primitive in apf_primitives
        )
        nfl_index_count = sum(
            len(accessor_values(nfl_gltf, primitive["indices"]))
            for primitive in nfl_primitives
        )
        if not all(isinstance(value, tuple) for value in apf_positions + nfl_positions):
            raise EvidenceError("manual open_book POSITION accessor is not vector data")
        hausdorff = max(
            directed_hausdorff(apf_positions, nfl_positions),
            directed_hausdorff(nfl_positions, apf_positions),
        )
        meshes.append(
            {
                "name": name,
                "apf_vertex_count": len(apf_positions),
                "nfl_vertex_count": len(nfl_positions),
                "apf_primitive_count": len(apf_primitives),
                "nfl_primitive_count": len(nfl_primitives),
                "apf_triangle_count": apf_index_count // 3,
                "nfl_triangle_count": nfl_index_count // 3,
                "unordered_vertex_hausdorff_distance": hausdorff,
            }
        )
    return {
        "node_order": expected_nodes,
        "node_order_exact_match": True,
        "meshes": meshes,
        "all_four_tabs_preserve_60_vertices_30_triangles": all(
            row["apf_vertex_count"] == row["nfl_vertex_count"] == 60
            and row["apf_triangle_count"] == row["nfl_triangle_count"] == 30
            for row in meshes[1:]
        ),
        "whole_scene_byte_identical_claimed": False,
    }


def write_tsv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in fields})


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apf-index", type=Path,
        default=root / "extracted/All-Pro Football 2K8 (USA)/0A",
    )
    parser.add_argument(
        "--nfl-index", type=Path,
        default=root / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0",
    )
    parser.add_argument(
        "--nfl-xbe", type=Path,
        default=root / "extracted/ESPN NFL 2K5 (USA)/default.xbe",
    )
    parser.add_argument(
        "--apf-gltf", type=Path,
        default=root / "assets/intermediate/apf2k8/models/0499_0006_open_book.gltf",
    )
    parser.add_argument(
        "--nfl-gltf", type=Path,
        default=root / "assets/intermediate/nfl2k5/models/0109_0015_open_book.gltf",
    )
    parser.add_argument(
        "--ghidra-trace", type=Path,
        default=root / "reports/cut_content/apf_nfl_lineage/manual_remnants/ghidra_trace.txt",
    )
    parser.add_argument(
        "--json-out", type=Path,
        default=root / "reports/cut_content/apf_nfl_lineage/manual_remnants.json",
    )
    parser.add_argument(
        "--pages-tsv-out", type=Path,
        default=root / "reports/cut_content/apf_nfl_lineage/manual_remnants_pages.tsv",
    )
    parser.add_argument(
        "--diff-tsv-out", type=Path,
        default=root / "reports/cut_content/apf_nfl_lineage/manual_remnants_authored_diff.tsv",
    )
    parser.add_argument(
        "--licensed-tsv-out", type=Path,
        default=root / "reports/cut_content/apf_nfl_lineage/manual_remnants_licensed_text.tsv",
    )
    parser.add_argument(
        "--claims-tsv-out", type=Path,
        default=root / "reports/cut_content/apf_nfl_lineage/manual_remnants_video_claims.tsv",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for path in (
        args.apf_index, args.nfl_index, args.nfl_xbe,
        args.apf_gltf, args.nfl_gltf, args.ghidra_trace,
    ):
        if not path.is_file():
            raise EvidenceError(f"required input is missing: {path}")

    apf, apf_pages = parse_apf_manual(args.apf_index)
    nfl, nfl_pages = parse_nfl_manual(args.nfl_index)
    lineage, page_rows, authored_diffs, licensed_rows = compare_pages(apf_pages, nfl_pages)
    geometry = compare_open_book_geometry(args.apf_gltf, args.nfl_gltf)

    xbe = args.nfl_xbe.read_bytes()
    literal = "manual.iff".encode("utf-16le")
    literal_offsets: list[int] = []
    cursor = 0
    while True:
        offset = xbe.find(literal, cursor)
        if offset < 0:
            break
        literal_offsets.append(offset)
        cursor = offset + 1
    if literal_offsets != [0x00B4BAD0]:
        raise EvidenceError(f"NFL manual.iff literal offsets changed: {literal_offsets}")

    trace = args.ghidra_trace.read_bytes()
    for witness in (
        b"0x4C997FFB", b"0x846B02B8", b"0x82008108",
        b"COMPILED_MANUAL_INITIALIZER", b"string=manual.iff",
        b"page_count=15", b"resource=xenon-15",
    ):
        if witness not in trace:
            raise EvidenceError(f"MANU Ghidra trace lacks {witness.decode()}")

    report = {
        "schema": SCHEMA,
        "scope": {
            "read_only_static_and_asset_analysis": True,
            "launches_game_or_emulator": False,
            "executes_translated_guest_code": False,
            "writes_game_images": False,
            "runtime_reachability_proved": False,
            "formal_nfl_2k6_product_identity_proved": False,
        },
        "sources": {
            "apf_index": source_pin(args.apf_index, EXPECTED_APF_INDEX_SHA256),
            "nfl_index": source_pin(args.nfl_index, EXPECTED_NFL_INDEX_SHA256),
            "nfl_xbe": source_pin(args.nfl_xbe, EXPECTED_NFL_XBE_SHA256),
            "apf_open_book_gltf": source_pin(args.apf_gltf),
            "nfl_open_book_gltf": source_pin(args.nfl_gltf),
            "ghidra_trace": source_pin(args.ghidra_trace),
        },
        "filename_identity": {
            "uppercase_name": "MANUAL.IFF",
            "apf_crc32_uppercase_ascii": f"0x{zlib.crc32(b'MANUAL.IFF') & 0xffffffff:08x}",
            "nfl_crc32_uppercase_utf16le": f"0x{zlib.crc32('MANUAL.IFF'.encode('utf-16le')) & 0xffffffff:08x}",
            "matches_apf_outer_id": (zlib.crc32(b"MANUAL.IFF") & 0xFFFFFFFF) == APF_OUTER_ID,
            "matches_nfl_outer_id": (
                zlib.crc32("MANUAL.IFF".encode("utf-16le")) & 0xFFFFFFFF
            ) == NFL_OUTER_ID,
            "nfl_xbe_utf16le_literal_count": len(literal_offsets),
            "nfl_xbe_utf16le_literal_offsets": [f"0x{value:08x}" for value in literal_offsets],
        },
        "apf": apf,
        "nfl": nfl,
        "manual_lineage": lineage,
        "page_titles": [value.strip() for value in PAGE_TITLES],
        "open_book_scene_lineage": geometry,
        "executable_evidence": {
            "manu_type_hash": "0x4c997ffb",
            "static_descriptor_hash_address": "0x82008108",
            "runtime_node_hash_address": "0x84d22ea4",
            "manu_runtime_page_accessor": "0x846b02b8",
            "compiled_initializer_slot": "0x820081e8",
            "compiled_manual_initializer": "0x846b0320",
            "manual_book_initializer_pdata_extent": "0x846af7b0..0x846afc88",
            "manual_package_string_address": "0x8450d6e8",
            "manual_package_string": "manual.iff",
            "open_book_resource_id_materialized_at": "0x846af848..0x846af854",
            "open_book_resource_id": "0x7211e214",
            "compiled_page_table_address": "0x84d25440",
            "compiled_page_table_count": 15,
            "compiled_page_table_exactly_names_xenon_1_through_15": True,
            "compiled_initializer_and_manu_dispatch_present": True,
            "retail_frontend_route_to_initializer_proved": False,
        },
        "development_inference": {
            "supported": (
                "the xb-* to xenon-* rename, Xbox-360 control edit, online-flow "
                "edit, and Weekly Prep 60-to-40-hour edits show an authored "
                "next-generation conversion of NFL 2K5-era feature documentation"
            ),
            "not_supported": (
                "these pages alone do not identify a formal product named NFL 2K6, "
                "prove a complete next-gen build, or make the documented modes reachable"
            ),
        },
        "claims": {
            "safe": [
                "APF ships all 15 NFL 2K5 manual pages as renamed xenon-* MANU resources.",
                "The manual documents Franchise, Off-Season Tasks, The Crib, First Person Football, ESPN 25th Anniversary, and Xbox Live.",
                "Mechanical and authored edits prove platform conversion rather than a raw untouched copy.",
                "APF retains a registered initializer that requests open_book and all 15 xenon-* MANU pages.",
            ],
            "not_proved": [
                "The shipped APF frontend can open the manual.",
                "The documented NFL modes are playable in retail APF.",
                "The conversion came from a formally titled or complete NFL 2K6 product.",
            ],
        },
        "portme": [
            "// PORTME: recover the APF menu/state owner that requests manual.iff/xenon-* or prove it orphaned.",
            "// PORTME: recover the indirect frontend/state owner of registered initializer 0x846B0320.",
            "// PORTME: map the remaining MANU record fields and renderer before building a reversible editor/viewer.",
        ],
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    # Remove heavyweight run objects from the local page dictionaries before
    # they can accidentally leak into a serializer in future revisions.
    write_tsv(
        args.pages_tsv_out,
        page_rows,
        [
            "page_number", "title", "apf_name", "nfl_name", "string_count",
            "raw_exact_ordered_matches", "markup_normalized_exact_ordered_matches",
            "authored_difference_count", "apf_body_size", "nfl_body_size",
        ],
    )
    write_tsv(
        args.diff_tsv_out,
        authored_diffs,
        [
            "page_number", "page_title", "classification", "sequence_index",
            "apf_offset", "nfl_offset", "apf_text", "nfl_text",
        ],
    )
    write_tsv(
        args.licensed_tsv_out,
        licensed_rows,
        ["page_number", "page_title", "offset", "categories", "text"],
    )
    write_tsv(
        args.claims_tsv_out,
        [
            {
                "grade": "A_proven",
                "claim": "Retail APF 2K8 ships all 15 NFL 2K5 in-game manual pages under xenon-1 through xenon-15.",
                "evidence": "exact manual.iff dual hash; 15 MANU + open_book composition; 1553 matching page slots; 1544 normalized exact strings",
                "boundary": "archive/data lineage; retail APF menu reachability is not proved",
            },
            {
                "grade": "A_proven",
                "claim": "The manual port was deliberately adapted for next-generation development.",
                "evidence": "xb-* renamed xenon-*; right-stick control wording changed; Weekly Prep 60 hours changed to 40 in three strings; online challenge copy changed",
                "boundary": "does not establish a formally titled or complete NFL 2K6 product",
            },
            {
                "grade": "boundary",
                "claim": "The Franchise/Crib/First-Person/ESPN pages do not make those modes playable in APF.",
                "evidence": "a registered initializer requests open_book and all 15 pages, but no retail frontend/state route to that initializer was proved",
                "boundary": "describe as shipped converted documentation, not an APF gameplay screenshot",
            },
        ],
        ["grade", "claim", "evidence", "boundary"],
    )
    print(
        "APF_MANUAL_NFL_REMNANTS_COMPLETE pages=15 strings=1553 "
        "raw_shared=1414 normalized_shared=1544 authored_diffs=9 runtime=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EvidenceError, apf_inner.FormatError, apf_outer.FormatError, nfl_outer.FormatError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)

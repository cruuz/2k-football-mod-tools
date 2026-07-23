#!/usr/bin/env python3
"""Build the APF 2K8 runtime pose-config construction inventory.

The focused Ghidra trace proves the consumer-side config layout, a separate
0x40-byte dynamic descriptor grammar, one secondary direct table use, and the
bounded absence of a direct installer for the main static sampler map.  It
does not prove a logical-channel or matrix-row to SCNE bone-name binding.

This tool deliberately preserves that negative result.  It joins the new
trace to the earlier pose/bone-binding inventory, but never assigns anatomy
from table shape, mirror symmetry, skeleton order, or adjacency.

// PORTME at 0x847C1470/0x847C14A4: recover the code or runtime capture that
//         installs config +0x24 map3 and +0x28 map2.
// PORTME at 0x820FC55C: bind matrix rows to SCNE names only after ownership is
//         proved by an installer or runtime capture.
// PORTME at 0x820FC584: prove whether 00 00 is row 21 or float alignment.
// PORTME at 0x8497B7B0: recover population of the alternate 0x40-byte records.
// PORTME at 0x84AC1668: prove ownership and named skeleton binding for the
//         secondary direct table path.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import struct
from typing import Any


SCHEMA = "apf_pose_config_builder/v1"
EXPECTED_XEX_MD5 = "217eea6084c3d03f0f1143802b1f5636"
EXPECTED_LANGUAGE = "PowerPC:BE:64:A2ALT-32addr"
EXPECTED_TRACE_SHA256 = (
    "7d7e5e6637b765f1f5a593b8797a9e4893769541321e423e4db518ef0bccbbf1"
)
EXPECTED_PSEUDO_SHA256 = (
    "1c12e8033a326a0eee43565fb78c6a7311cdb0973a792e096e8d03ad63a9f04d"
)
EXPECTED_UPSTREAM_SHA256 = {
    "pose_binding_inventory": (
        "0ccab8212bf99a1a1b0ba20fb146b2aa9575716be1ade3f493e6d7a5bda30b64"
    ),
    "pose_binding_logical_tsv": (
        "226a8d4247d5b437b0eef3aaa7a4ed2754e457f19892bef9a0b3f66b395b6fbe"
    ),
    "pose_binding_matrix_tsv": (
        "ba7f9201c00f6025fd8b89f72435bc2eea230132c8c3bfe6ba51bf86928ac113"
    ),
    "scene_inventory": (
        "2243b5a3eb4dfcdebdda055e1a6fd9399b12b2704338f80ae4529d8476e85a17"
    ),
    "function_manifest": (
        "9c5186fc9345d2079eebd9f7f3612043a9aa3a8d7a09a6950d3a37573b78de9e"
    ),
}

MAIN_MAP3_ADDRESS = 0x820FC510
MAIN_MAP2_ADDRESS = 0x820FC55C
MAIN_MAP2_END = 0x820FC588
MAIN_MAP3_GETTER = 0x84AA4190
MAIN_MAP2_GETTER = 0x84AA41A0
SECONDARY_MAP3_ADDRESS = 0x821006F0
SECONDARY_MAP2_ADDRESS = 0x82100738

EXPECTED_MAIN_MAP3 = [
    (0, 0, 0),
    (0, 1, 4),
    (0, 2, 5),
    (0, 3, 6),
    (0, 4, 1),
    (0, 5, 2),
    (0, 6, 3),
    (0, 7, 7),
    (0, 8, 13),
    (0, 9, 14),
    (0, 10, 15),
    (0, 11, 16),
    (0, 12, 12),
    (0, 13, 8),
    (0, 14, 9),
    (0, 15, 10),
    (0, 16, 11),
    (1, 17, 18),
    (1, 18, 17),
    (1, 19, 19),
    (1, 20, 22),
    (1, 21, 21),
    (1, 22, 20),
    (2, 23, 24),
    (2, 24, 23),
]

EXPECTED_MAIN_MAP2 = [
    (0, -1, "semantic"),
    (-1, -1, "semantic"),
    (1, 17, "semantic"),
    (2, -1, "semantic"),
    (3, -1, "semantic"),
    (-1, -1, "semantic"),
    (4, 18, "semantic"),
    (5, -1, "semantic"),
    (6, -1, "semantic"),
    (7, 19, "semantic"),
    (8, -1, "semantic"),
    (-1, -1, "semantic"),
    (9, 20, "semantic"),
    (10, -1, "semantic"),
    (11, -1, "semantic"),
    (12, 21, "semantic"),
    (13, -1, "semantic"),
    (-1, -1, "semantic"),
    (14, 22, "semantic"),
    (15, -1, "semantic"),
    (16, -1, "semantic"),
    (0, 0, "record_or_alignment_unproved"),
]

EXPECTED_SECONDARY_MAP3 = EXPECTED_MAIN_MAP3[:23] + [(0, 0, 0)]

EXPECTED_ACCESSORS = {
    0x84AA4190: ("0x820FC510", "main_map3"),
    0x84AA41A0: ("0x820FC55C", "main_map2"),
    0x84AA41B0: ("0x820FC588", "float_table"),
    0x84AA41C0: ("0x01F9FF80", "mask_value_a"),
    0x84AA41D0: ("0x0006007F", "mask_value_b"),
    0x84AA41E0: ("0x00000000", "zero_value"),
    0x84AA41E8: ("unchanged", "noop"),
    0x84AA41F0: ("void", "scale_nine_pose_floats"),
}

EXPECTED_TARGET_COUNTS = {
    0x820FC510: (0, 0, 1),
    0x820FC55C: (1, 0, 2),
    0x820FC588: (0, 0, 2),
    0x84AA4190: (0, 0, 0),
    0x84AA41A0: (2, 0, 0),
    0x84AA41B0: (0, 0, 0),
    0x84AA41C0: (0, 0, 0),
    0x84AA41D0: (0, 0, 0),
    0x84AA41E0: (0, 0, 0),
    0x84AA41E8: (0, 0, 4),
    0x84AA41F0: (0, 0, 0),
}

EXPECTED_SPANS = {
    "consumer_config_a": (0x847C1438, 0x847C14E0),
    "consumer_config_b": (0x847C9428, 0x847C94BC),
    "pose_storage_pointer": (0x847C0C20, 0x847C0C54),
    "static_map2_index_lookup": (0x84877698, 0x84877758),
    "static_map2_pair9_lookup": (0x84925BDC, 0x84925D04),
    "config_matrix_call": (0x84926064, 0x84926078),
    "dynamic_record_sample": (0x8497B88C, 0x8497B944),
    "dynamic_record_stride": (0x8497BA60, 0x8497BA74),
    "dynamic_record_destroy": (0x8497D590, 0x8497D604),
    "matrix_pool_allocator": (0x84AA4070, 0x84AA4124),
    "static_accessor_family": (0x84AA4190, 0x84AA4288),
    "secondary_hardcoded_config": (0x84AC1668, 0x84AC1760),
}

# These anchors are the minimum instruction-level facts consumed by the
# report.  VMX words that Ghidra cannot decode remain raw, address-bound data.
RAW_ANCHORS = {
    # Main config: map3, callback, map2, count.
    0x847C1470: 0x80CB0024,
    0x847C1478: 0x4BE78EA9,
    0x847C1480: 0x816B0044,
    0x847C1494: 0x4E800421,
    0x847C14A4: 0x80CB0028,
    0x847C14A8: 0x80AB001C,
    0x847C14AC: 0x4BE78025,
    0x847C9460: 0x80CB0024,
    0x847C9470: 0x816B0044,
    0x847C9494: 0x80CB0028,
    0x847C9498: 0x80AB001C,
    # +0x40 is a pointer; vectors are read from its +0x170/+0x180 storage.
    0x847C0C28: 0x816B0040,
    0x847C0C2C: 0x396B0170,
    0x847C0C30: 0x100058C3,
    0x847C0C40: 0x816B0040,
    0x847C0C44: 0x396B0180,
    0x847C0C48: 0x100058C3,
    # Alternate descriptor owner and sampling fields.
    0x8497B88C: 0x817F00D8,
    0x8497B8CC: 0x817F00DC,
    0x8497B8DC: 0x80CB0034,
    0x8497B8E0: 0x80AB0030,
    0x8497B8E4: 0x806B000C,
    0x8497B8E8: 0x4BCBEA39,
    0x8497B8F4: 0x816B003C,
    0x8497B908: 0x4E800421,
    0x8497B918: 0x80CB0038,
    0x8497B91C: 0x80AB002C,
    0x8497B920: 0x806B0018,
    0x8497B924: 0x4BCBDBAD,
    0x8497BA68: 0x3BDE0040,
    # Alternate descriptor lifetime and +0x1c owned pointer.
    0x8497D590: 0x817F00D8,
    0x8497D5A4: 0x817F00DC,
    0x8497D5AC: 0x814B0000,
    0x8497D5B8: 0x806B001C,
    0x8497D5C8: 0x806B001C,
    0x8497D5E0: 0x3BDE0040,
    0x8497D5FC: 0x939F00D8,
    0x8497D600: 0x939F00DC,
    # Two 0x540 regions per 0xad0 slot and an 0x50-byte cleared tail.
    0x84AA40A8: 0x1D2A0AD0,
    0x84AA40C8: 0x1D2A0AD0,
    0x84AA40D4: 0x394A0540,
    0x84AA40E0: 0x1D0A0AD0,
    0x84AA40F4: 0x39690A80,
    0x84AA40F8: 0x394B0050,
    0x84AA4108: 0x100958C3,
    # Leaf accessor family, including the non-callback nine-float scaler.
    0x84AA4190: 0x3D608210,
    0x84AA4194: 0x386BC510,
    0x84AA41A4: 0x386BC55C,
    0x84AA41B4: 0x386BC588,
    0x84AA41E8: 0x4E800020,
    0x84AA41F8: 0x896300D9,
    0x84AA4234: 0xC00BE120,
    0x84AA4284: 0x4E800020,
    # Secondary direct map3/map2 call path.
    0x84AC1688: 0x3B8B0738,
    0x84AC1694: 0x38DCFFB8,
    0x84AC16B8: 0x4BB78C69,
    0x84AC16E0: 0x4804E521,
    0x84AC16F0: 0x7F86E378,
    0x84AC16F4: 0x4BB77DDD,
    0x84AC170C: 0x4BB77BBD,
}


class ConfigError(RuntimeError):
    """Raised when one pinned evidence contract changes."""


def hex32(value: int) -> str:
    return f"0x{value & 0xFFFFFFFF:08X}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_sha256(path: Path, expected: str, label: str) -> str:
    actual = sha256_file(path)
    if actual != expected:
        raise ConfigError(f"{label} SHA-256 changed: expected {expected}, got {actual}")
    return actual


def parse_trace(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    identity: dict[str, str] = {}
    main_map3: list[tuple[int, int, int]] = []
    main_map2: list[tuple[int, int, str]] = []
    secondary_map3: list[tuple[int, int, int]] = []
    accessors: dict[int, tuple[str, str]] = {}
    targets: dict[int, dict[str, Any]] = {}
    spans: dict[str, dict[str, Any]] = {}
    current_span: dict[str, Any] | None = None
    direct_count: int | None = None
    direct_limit: str | None = None

    for line_number, line in enumerate(text.splitlines(), 1):
        if line.startswith("Program MD5: "):
            identity["md5"] = line.removeprefix("Program MD5: ")
        elif line.startswith("Program name: "):
            identity["name"] = line.removeprefix("Program name: ")
        elif line.startswith("Program language: "):
            identity["language"] = line.removeprefix("Program language: ")
        elif match := re.fullmatch(r"MAIN_MAP3 (\d+) (-?\d+) (-?\d+) (-?\d+)", line):
            index, mode, normal, mirrored = map(int, match.groups())
            if index != len(main_map3):
                raise ConfigError(f"line {line_number}: non-contiguous MAIN_MAP3")
            main_map3.append((mode, normal, mirrored))
        elif match := re.fullmatch(
            r"MAIN_MAP2 (\d+) (-?\d+) (-?\d+) ([a-z0-9_]+)", line
        ):
            index = int(match.group(1))
            if index != len(main_map2):
                raise ConfigError(f"line {line_number}: non-contiguous MAIN_MAP2")
            main_map2.append((int(match.group(2)), int(match.group(3)), match.group(4)))
        elif match := re.fullmatch(
            r"SECONDARY_MAP3 (\d+) (-?\d+) (-?\d+) (-?\d+)", line
        ):
            index, mode, normal, mirrored = map(int, match.groups())
            if index != len(secondary_map3):
                raise ConfigError(f"line {line_number}: non-contiguous SECONDARY_MAP3")
            secondary_map3.append((mode, normal, mirrored))
        elif match := re.fullmatch(
            r"ACCESSOR (0x[0-9A-F]+) return=([^ ]+) role=([a-z0-9_]+)", line
        ):
            accessors[int(match.group(1), 16)] = (match.group(2), match.group(3))
        elif match := re.fullmatch(
            r"TARGET (0x[0-9A-F]+) refs=(\d+) raw_aligned_pointer_hits=(\d+) "
            r"materializations=(\d+)",
            line,
        ):
            target = int(match.group(1), 16)
            targets[target] = {
                "reference_count": int(match.group(2)),
                "raw_aligned_pointer_hit_count": int(match.group(3)),
                "materialization_count": int(match.group(4)),
                "references": [],
                "pointers": [],
                "materializations": [],
            }
        elif match := re.fullmatch(
            r"TARGET_(REF|POINTER|MATERIALIZATION) (0x[0-9A-F]+) (.+)", line
        ):
            kind, target_text, value = match.groups()
            target = int(target_text, 16)
            if target not in targets:
                raise ConfigError(f"line {line_number}: evidence precedes TARGET")
            key = {
                "REF": "references",
                "POINTER": "pointers",
                "MATERIALIZATION": "materializations",
            }[kind]
            targets[target][key].append(value)
        elif match := re.fullmatch(r"DIRECT_MAIN_MAP3_INSTALLER_COUNT (\d+)", line):
            direct_count = int(match.group(1))
        elif line.startswith("DIRECT_MAIN_MAP3_INSTALLER_LIMIT "):
            direct_limit = line.removeprefix("DIRECT_MAIN_MAP3_INSTALLER_LIMIT ")
        elif match := re.fullmatch(
            r"SPAN ([a-z0-9_]+) (0x[0-9A-F]+) (0x[0-9A-F]+)", line
        ):
            if current_span is not None:
                raise ConfigError(f"line {line_number}: nested SPAN")
            name, start, end = match.groups()
            if name in spans:
                raise ConfigError(f"line {line_number}: duplicate SPAN {name}")
            current_span = {
                "name": name,
                "start": int(start, 16),
                "end": int(end, 16),
                "raw": {},
                "ghidra": {},
            }
            spans[name] = current_span
        elif match := re.fullmatch(r"RAW32 (0x[0-9A-F]+) (0x[0-9A-F]+)", line):
            if current_span is None:
                raise ConfigError(f"line {line_number}: RAW32 outside SPAN")
            address, word = (int(item, 16) for item in match.groups())
            if address in current_span["raw"]:
                raise ConfigError(f"line {line_number}: duplicate RAW32 {hex32(address)}")
            current_span["raw"][address] = word
        elif match := re.fullmatch(r"GHIDRA (0x[0-9A-F]+) (.*)", line):
            if current_span is None:
                raise ConfigError(f"line {line_number}: GHIDRA outside SPAN")
            address = int(match.group(1), 16)
            current_span["ghidra"][address] = match.group(2)
        elif match := re.fullmatch(r"END_SPAN ([a-z0-9_]+)", line):
            if current_span is None or current_span["name"] != match.group(1):
                raise ConfigError(f"line {line_number}: mismatched END_SPAN")
            current_span = None

    if current_span is not None:
        raise ConfigError(f"unterminated SPAN {current_span['name']}")
    if identity != {
        "md5": EXPECTED_XEX_MD5,
        "name": "default.xex",
        "language": EXPECTED_LANGUAGE,
    }:
        raise ConfigError(f"trace program identity changed: {identity!r}")
    if main_map3 != EXPECTED_MAIN_MAP3:
        raise ConfigError("main 25-row map3 changed")
    if main_map2 != EXPECTED_MAIN_MAP2:
        raise ConfigError("main 44-byte map2 extent changed")
    if secondary_map3 != EXPECTED_SECONDARY_MAP3:
        raise ConfigError("secondary 24-row map3 changed")
    if "MAIN_MAP2_EXTENT 0x820FC55C 0x820FC588 bytes=44" not in text:
        raise ConfigError("main map2 extent marker changed")
    if "SECONDARY_MAP3_EXTENT 0x821006F0 0x82100738 bytes=72" not in text:
        raise ConfigError("secondary map3 extent marker changed")
    if accessors != EXPECTED_ACCESSORS:
        raise ConfigError(f"static accessor family changed: {accessors!r}")
    if set(targets) != set(EXPECTED_TARGET_COUNTS):
        raise ConfigError("direct-installer search target set changed")
    for target, expected in EXPECTED_TARGET_COUNTS.items():
        actual = targets[target]
        counts = (
            actual["reference_count"],
            actual["raw_aligned_pointer_hit_count"],
            actual["materialization_count"],
        )
        if counts != expected:
            raise ConfigError(
                f"target {hex32(target)} counts changed: expected {expected}, got {counts}"
            )
        for key, count_key in (
            ("references", "reference_count"),
            ("pointers", "raw_aligned_pointer_hit_count"),
            ("materializations", "materialization_count"),
        ):
            if len(actual[key]) != actual[count_key]:
                raise ConfigError(f"target {hex32(target)} {key} detail count changed")

    # Derive the bounded negative result independently of the trace's summary.
    if targets[MAIN_MAP3_ADDRESS]["materializations"] != [
        "0x84AA4190->0x84AA4194(lis/addi)"
    ]:
        raise ConfigError("main map3 has a new direct materialization")
    if any(
        targets[MAIN_MAP3_ADDRESS][key]
        for key in ("references", "pointers")
    ):
        raise ConfigError("main map3 gained a direct reference or pointer")
    if any(
        targets[MAIN_MAP3_GETTER][key]
        for key in ("references", "pointers", "materializations")
    ):
        raise ConfigError("main map3 getter gained a direct installation edge")
    derived_direct_installer_count = 0
    if direct_count != derived_direct_installer_count:
        raise ConfigError("trace direct-installer summary disagrees with derived evidence")
    if direct_limit != "indirect_runtime_dispatch_or_external_installation_not_excluded":
        raise ConfigError("direct-installer search limitation changed")
    if targets[MAIN_MAP2_GETTER]["references"] != [
        "0x8487770C(none,UNCONDITIONAL_CALL)",
        "0x84925BDC(none,UNCONDITIONAL_CALL)",
    ]:
        raise ConfigError("main map2 getter caller set changed")

    if set(spans) != set(EXPECTED_SPANS):
        raise ConfigError(f"raw span set changed: {sorted(spans)}")
    all_raw: dict[int, int] = {}
    span_reports: list[dict[str, Any]] = []
    for name, (start, end) in EXPECTED_SPANS.items():
        span = spans[name]
        if (span["start"], span["end"]) != (start, end):
            raise ConfigError(f"{name} bounds changed")
        expected_addresses = list(range(start, end, 4))
        if sorted(span["raw"]) != expected_addresses:
            raise ConfigError(f"{name} RAW32 coverage changed")
        if sorted(span["ghidra"]) != expected_addresses:
            raise ConfigError(f"{name} GHIDRA listing coverage changed")
        overlap = set(all_raw).intersection(span["raw"])
        if overlap:
            raise ConfigError(f"raw spans overlap at {hex32(min(overlap))}")
        all_raw.update(span["raw"])
        body = b"".join(struct.pack(">I", span["raw"][address]) for address in expected_addresses)
        undecoded = sum(span["ghidra"][address] == "<no instruction>" for address in expected_addresses)
        span_reports.append(
            {
                "name": name,
                "start": hex32(start),
                "end_exclusive": hex32(end),
                "size": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
                "ghidra_undecoded_word_count": undecoded,
                "raw32_authoritative": True,
            }
        )
    for address, expected in RAW_ANCHORS.items():
        actual = all_raw.get(address)
        if actual != expected:
            raise ConfigError(
                f"RAW32 {hex32(address)}: expected {hex32(expected)}, "
                f"got {None if actual is None else hex32(actual)}"
            )

    return {
        "text": text,
        "identity": identity,
        "main_map3": main_map3,
        "main_map2": main_map2,
        "secondary_map3": secondary_map3,
        "accessors": accessors,
        "targets": targets,
        "direct_installer_count": derived_direct_installer_count,
        "direct_installer_limit": direct_limit,
        "raw_spans": span_reports,
    }


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream, dialect="excel-tab"))


def validate_upstream(
    pose_binding_path: Path,
    logical_tsv_path: Path,
    matrix_tsv_path: Path,
    scene_inventory_path: Path,
    function_manifest_path: Path,
    trace: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    paths = {
        "pose_binding_inventory": pose_binding_path,
        "pose_binding_logical_tsv": logical_tsv_path,
        "pose_binding_matrix_tsv": matrix_tsv_path,
        "scene_inventory": scene_inventory_path,
        "function_manifest": function_manifest_path,
    }
    hashes = {
        label: require_sha256(path, EXPECTED_UPSTREAM_SHA256[label], label)
        for label, path in paths.items()
    }

    binding = json.loads(pose_binding_path.read_text(encoding="utf-8"))
    if binding.get("schema") != "apf_pose_bone_binding/v1":
        raise ConfigError("upstream pose-binding schema changed")
    summary = binding.get("summary", {})
    expected_summary_subset = {
        "logical_map_record_count": 25,
        "logical_named_body_binding_count": 0,
        "matrix_byte_pair_count": 22,
        "matrix_semantic_pair_count": 21,
        "matrix_ambiguous_trailing_pair_count": 1,
        "matrix_named_body_binding_count": 0,
    }
    for key, expected in expected_summary_subset.items():
        if summary.get(key) != expected:
            raise ConfigError(f"upstream pose-binding summary {key} changed")

    logical = binding["logical_channels"]
    matrix = binding["matrix_rows"]
    if len(logical) != 25 or len(matrix) != 22:
        raise ConfigError("upstream pose-binding row counts changed")
    if any(row.get("bone_name") is not None for row in logical + matrix):
        raise ConfigError("upstream report contains a new named pose binding; audit required")
    for index, (mode, normal, mirrored) in enumerate(trace["main_map3"]):
        row = logical[index]
        if (
            row["logical_channel"],
            row["mode"],
            row["normal_packed_index"],
            row["mirrored_packed_index"],
        ) != (index, mode, normal, mirrored):
            raise ConfigError(f"upstream logical row {index} disagrees with trace")
    for index, (rotation, translation, extent) in enumerate(trace["main_map2"]):
        row = matrix[index]
        if (
            row["matrix_row"],
            row["rotation_logical_index"],
            row["translation_logical_index"],
            row["extent_status"],
        ) != (
            index,
            None if rotation < 0 else rotation,
            None if translation < 0 else translation,
            "semantic_pair" if extent == "semantic" else "record_or_two_byte_alignment_unproved",
        ):
            raise ConfigError(f"upstream matrix row {index} disagrees with trace")

    logical_tsv = read_tsv(logical_tsv_path)
    matrix_tsv = read_tsv(matrix_tsv_path)
    if len(logical_tsv) != 25 or len(matrix_tsv) != 22:
        raise ConfigError("upstream TSV row counts changed")
    if any(row.get("bone_name", "") for row in logical_tsv + matrix_tsv):
        raise ConfigError("upstream TSV contains a named pose binding; audit required")

    manifest = json.loads(function_manifest_path.read_text(encoding="utf-8"))
    expected_manifest = {
        "program_name": "default.xex",
        "executable_md5": EXPECTED_XEX_MD5,
        "language_id": EXPECTED_LANGUAGE,
        "function_count": 21347,
        "exported_function_count": 21347,
        "complete": True,
    }
    for key, expected in expected_manifest.items():
        if manifest.get(key) != expected:
            raise ConfigError(f"APF function manifest {key} changed")
    return binding, hashes


def validate_pseudo(path: Path) -> str:
    digest = require_sha256(path, EXPECTED_PSEUDO_SHA256, "focused pseudo-C")
    text = path.read_text(encoding="utf-8")
    required = (
        "/* 0x847C1438:",
        "/* 0x847C9428:",
        "/* 0x84AA4070:",
        "/* 0x8472AF58:",
        "const unsigned char *apf_player_map3(void) { return (const unsigned char *)0x820FC510; }",
        "const signed char *apf_player_map2(void) { return (const signed char *)0x820FC55C; }",
        "// PORTME at 0x8497B7B0:",
        "// PORTME at 0x84AC1668:",
        "// PORTME at 0x847C1470/0x847C14A4:",
        "// PORTME at 0x820FC55C:",
    )
    for marker in required:
        if marker not in text:
            raise ConfigError(f"focused pseudo-C lacks {marker!r}")
    if "halt_baddata();" not in text:
        raise ConfigError("focused pseudo-C no longer preserves VMX failure")
    return digest


def address_role(offset: int, role: str, evidence: list[str], status: str = "proved") -> dict[str, Any]:
    return {
        "offset": offset,
        "offset_hex": f"+0x{offset:02X}",
        "role": role,
        "status": status,
        "evidence_addresses": evidence,
    }


def build_report(
    trace_path: Path,
    pseudo_path: Path,
    pose_binding_path: Path,
    logical_tsv_path: Path,
    matrix_tsv_path: Path,
    scene_inventory_path: Path,
    function_manifest_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    trace_digest = require_sha256(trace_path, EXPECTED_TRACE_SHA256, "Ghidra trace")
    trace = parse_trace(trace_path)
    pseudo_digest = validate_pseudo(pseudo_path)
    binding, upstream_hashes = validate_upstream(
        pose_binding_path,
        logical_tsv_path,
        matrix_tsv_path,
        scene_inventory_path,
        function_manifest_path,
        trace,
    )

    logical_rows: list[dict[str, Any]] = []
    combined_rows: list[dict[str, Any]] = []
    for index, (mode, normal, mirrored) in enumerate(trace["main_map3"]):
        row = {
            "logical_channel": index,
            "mode": mode,
            "normal_packed_index": normal,
            "mirrored_packed_index": mirrored,
            "bone_name": None,
            "exact_named_binding_status": "unresolved_no_installer_or_runtime_capture",
        }
        logical_rows.append(row)
        combined_rows.append(
            {
                "domain": "logical_channel",
                "row_index": index,
                "mode": mode,
                "normal_packed_index": normal,
                "mirrored_packed_index": mirrored,
                "rotation_logical_index": None,
                "translation_logical_index": None,
                "extent_status": "semantic_sampler_record",
                "bone_name": None,
                "exact_named_binding_status": row["exact_named_binding_status"],
            }
        )

    matrix_rows: list[dict[str, Any]] = []
    for index, (rotation, translation, extent) in enumerate(trace["main_map2"]):
        extent_status = (
            "semantic_pair"
            if extent == "semantic"
            else "record_or_two_byte_alignment_unproved"
        )
        row = {
            "matrix_row": index,
            "rotation_logical_index": None if rotation < 0 else rotation,
            "translation_logical_index": None if translation < 0 else translation,
            "extent_status": extent_status,
            "bone_name": None,
            "exact_named_binding_status": "unresolved_no_installer_or_runtime_capture",
        }
        matrix_rows.append(row)
        combined_rows.append(
            {
                "domain": "matrix_row",
                "row_index": index,
                "mode": None,
                "normal_packed_index": None,
                "mirrored_packed_index": None,
                "rotation_logical_index": row["rotation_logical_index"],
                "translation_logical_index": row["translation_logical_index"],
                "extent_status": extent_status,
                "bone_name": None,
                "exact_named_binding_status": row["exact_named_binding_status"],
            }
        )

    accessor_rows = [
        {
            "address": hex32(address),
            "return": result,
            "role": role,
            "direct_reference_count": trace["targets"][address]["reference_count"],
            "direct_materialization_count": trace["targets"][address]["materialization_count"],
        }
        for address, (result, role) in sorted(trace["accessors"].items())
    ]
    target_rows = []
    for target, data in sorted(trace["targets"].items()):
        target_rows.append({"target": hex32(target), **data})

    report = {
        "schema": SCHEMA,
        "program": {
            "name": trace["identity"]["name"],
            "md5": trace["identity"]["md5"],
            "language": trace["identity"]["language"],
        },
        "inputs": {
            "ghidra_trace": {"path": str(trace_path), "sha256": trace_digest},
            "focused_pseudo_c": {"path": str(pseudo_path), "sha256": pseudo_digest},
            "pose_binding_inventory": {
                "path": str(pose_binding_path),
                "sha256": upstream_hashes["pose_binding_inventory"],
            },
            "pose_binding_logical_tsv": {
                "path": str(logical_tsv_path),
                "sha256": upstream_hashes["pose_binding_logical_tsv"],
            },
            "pose_binding_matrix_tsv": {
                "path": str(matrix_tsv_path),
                "sha256": upstream_hashes["pose_binding_matrix_tsv"],
            },
            "scene_inventory": {
                "path": str(scene_inventory_path),
                "sha256": upstream_hashes["scene_inventory"],
            },
            "function_manifest": {
                "path": str(function_manifest_path),
                "sha256": upstream_hashes["function_manifest"],
            },
        },
        "summary": {
            "main_logical_row_count": len(logical_rows),
            "main_matrix_byte_pair_count": len(matrix_rows),
            "main_matrix_semantic_row_count": 21,
            "main_matrix_ambiguous_trailing_pair_count": 1,
            "main_exact_named_logical_binding_count": 0,
            "main_exact_named_matrix_binding_count": 0,
            "static_accessor_count": len(accessor_rows),
            "direct_main_map3_installer_count": trace["direct_installer_count"],
            "secondary_direct_map3_row_count": len(trace["secondary_map3"]),
            "dynamic_descriptor_record_size": 0x40,
            "dynamic_descriptor_proved_field_count": 9,
            "matrix_pool_half_bytes": 0x540,
            "matrix_pool_matrix_capacity_at_64_byte_stride": 0x540 // 0x40,
        },
        "main_config_consumer_contract": {
            "concrete_consumers": ["0x847C1438", "0x847C9428"],
            "config_fields": [
                address_role(0x1C, "matrix_count", ["0x847C14A8", "0x847C9498"]),
                address_role(0x24, "sampler_map3_pointer", ["0x847C1470", "0x847C9460"]),
                address_role(0x28, "matrix_map2_pointer", ["0x847C14A4", "0x847C9494"]),
                address_role(
                    0x40,
                    "pose_storage_pointer",
                    ["0x847C0C28", "0x847C0C40"],
                ),
                address_role(0x44, "optional_post_sample_callback", ["0x847C1480", "0x847C9470"]),
            ],
            "pose_storage_pointer_evidence": {
                "pointee_offsets_read": [0x170, 0x180],
                "inline_storage_rejected": True,
                "reason": "+0x40 is loaded as a pointer before adding +0x170/+0x180; +0x44 is a distinct callback field",
            },
        },
        "main_static_tables": {
            "map3": {
                "address": hex32(MAIN_MAP3_ADDRESS),
                "getter": hex32(MAIN_MAP3_GETTER),
                "record_size": 3,
                "rows": logical_rows,
                "ownership_status": "sampler_shaped_static_table_active_installation_unproved",
            },
            "map2": {
                "address": hex32(MAIN_MAP2_ADDRESS),
                "end_exclusive": hex32(MAIN_MAP2_END),
                "getter": hex32(MAIN_MAP2_GETTER),
                "record_size": 2,
                "rows": matrix_rows,
                "ownership_status": "matrix_shaped_static_extent_active_installation_unproved",
            },
        },
        "static_accessor_family": accessor_rows,
        "direct_installer_search": {
            "status": "unresolved_indirect_installation_not_excluded",
            "bounded_searches": [
                "Ghidra direct references",
                "aligned big-endian initialized pointer words",
                "eight-instruction PPC lis/addi and lis/ori materialization window",
            ],
            "targets": target_rows,
            "materialization_window_limit": "syntactic bounded scan; overlapping eight-instruction windows may pair an earlier lis with a later accessor addi after intervening instructions",
            "derived_direct_main_map3_installer_count": trace["direct_installer_count"],
            "limit": trace["direct_installer_limit"],
            "main_map3_only_materialization": "0x84AA4190->0x84AA4194(lis/addi)",
            "main_map3_getter_direct_reference_count": 0,
            "main_map2_getter_direct_callers": ["0x8487770C", "0x84925BDC"],
            "conclusion": "no_direct_retail_xex_builder_or_installer_recovered",
        },
        "dynamic_descriptor_path": {
            "consumer_function": "0x8497B7B0",
            "owner_count_offset": 0xD8,
            "owner_record_pointer_offset": 0xDC,
            "record_size": 0x40,
            "fields": [
                address_role(0x00, "type_tag_used_by_destroy_path", ["0x8497D5AC"]),
                address_role(0x0C, "clip_or_single_mocap_pointer_passed_to_sampler", ["0x8497B8E4", "0x8497B93C"]),
                address_role(0x18, "matrix_output_pointer", ["0x8497B920"]),
                address_role(0x1C, "owned_auxiliary_pointer_destroyed_with_record", ["0x8497D5B8", "0x8497D5C8"]),
                address_role(0x2C, "matrix_count", ["0x8497B91C"]),
                address_role(0x30, "sampler_active_mask", ["0x8497B8E0"]),
                address_role(0x34, "sampler_map3_pointer", ["0x8497B8DC"]),
                address_role(0x38, "matrix_map2_pointer", ["0x8497B918"]),
                address_role(0x3C, "optional_post_sample_callback", ["0x8497B8F4"]),
            ],
            "lifetime": {
                "destroy_loop": "0x8497D590",
                "record_pointer_freed": True,
                "owner_fields_zeroed": ["+0xD8", "+0xDC"],
                "stride_evidence": ["0x8497BA68", "0x8497D5E0"],
            },
            "relationship_to_main_static_tables": "alternate_runtime_descriptor_grammar; population_and_main_table_ownership_unproved",
        },
        "secondary_direct_config": {
            "consumer_function": "0x84AC1668",
            "map3_address": hex32(SECONDARY_MAP3_ADDRESS),
            "map3_record_size": 3,
            "map3_rows": [
                {
                    "row": index,
                    "mode": mode,
                    "normal_packed_index": normal,
                    "mirrored_packed_index": mirrored,
                    "bone_name": None,
                }
                for index, (mode, normal, mirrored) in enumerate(trace["secondary_map3"])
            ],
            "map2_address": hex32(SECONDARY_MAP2_ADDRESS),
            "matrix_count_source_call": "0x84B0FC00",
            "sampler_call": "0x8463A320",
            "matrix_expander_call": "0x846394D0",
            "root_interval_call": "0x846392C8",
            "ownership_and_named_binding_status": "unresolved",
        },
        "player_matrix_pool_clue": {
            "allocator_function": "0x84AA4070",
            "slot_size": 0xAD0,
            "first_pointer_field": "+0x04",
            "second_pointer_field": "+0x08",
            "second_region_offset": 0x540,
            "cleared_tail_offset": 0xA80,
            "cleared_tail_size": 0x50,
            "matrix_stride": 0x40,
            "matrix_capacity_per_0x540_region": 21,
            "structural_agreement": "21 equals main map2 semantic-row count",
            "proof_limit": "no_installer_or_ownership_edge_ties_this_pool_to_main_map2",
        },
        "named_binding_result": {
            "logical_to_scne_exact_count": 0,
            "matrix_to_scne_exact_count": 0,
            "candidate_scne_name_join_row_count": binding["summary"]["bone_scale_scene_join_count"],
            "assignment_policy": "no_anatomy_inference; no_assignment_without_installer_or_runtime_capture",
        },
        "executable_evidence": {
            "raw_spans": trace["raw_spans"],
            "raw32_authority_rule": "RAW32 is authoritative where Ghidra has shared-save/VMX decode failures",
        },
        "worked": [
            "Proved main config +0x1C/+0x24/+0x28/+0x40/+0x44 consumer roles at exact addresses.",
            "Corrected +0x40 to a pose-storage pointer rather than inline records.",
            "Recovered the complete eight-entry leaf accessor family.",
            "Derived a bounded zero direct-installer result for the main map3 table.",
            "Proved an alternate 0x40-byte dynamic descriptor sample/destroy contract.",
            "Proved a separate live static map3/map2 call pattern at 0x84AC1668.",
            "Preserved zero exact body-row to SCNE-name assignments.",
        ],
        "failed": [
            "No direct retail-XEX builder or installer for the main map3/map2 config was recovered.",
            "Indirect runtime dispatch, external population, and data-driven installation are not excluded.",
            "No exact main logical-channel or matrix-row to SCNE bone-name binding is proved.",
            "The final main map2 00 00 remains record-versus-alignment ambiguous.",
            "The alternate dynamic descriptor population path remains unrecovered.",
            "Ghidra still cannot decode every VMX/shared-save word in the focused functions.",
        ],
        "portme": [
            "// PORTME at 0x847C1470/0x847C14A4: recover the main config map3/map2 installer or capture it at runtime.",
            "// PORTME at 0x847C0C28/0x847C0C40: recover pose-storage pointee ownership and complete layout.",
            "// PORTME at 0x820FC55C: bind matrix rows to named SCNE bones only after ownership is proved.",
            "// PORTME at 0x820FC584: prove row 21 versus two-byte alignment before 0x820FC588.",
            "// PORTME at 0x8497B7B0: recover construction/population of each 0x40-byte descriptor record.",
            "// PORTME at 0x84AC1668: prove the secondary table's owning skeleton and exact row names.",
            "// PORTME at 0x84AA4108: replace the retained VMX RAW32 pool clear with typed source after ABI recovery.",
            "// PORTME at 0x8472B0AC: resolve the shared-save/VMX decompiler failure in the player pool caller.",
            "// PORTME at 0x84AA41F0: do not treat the two-argument nine-float scaler as config +0x44 without a call-site proof.",
        ],
    }
    return report, combined_rows


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_bindings_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "domain",
        "row_index",
        "mode",
        "normal_packed_index",
        "mirrored_packed_index",
        "rotation_logical_index",
        "translation_logical_index",
        "extent_status",
        "bone_name",
        "exact_named_binding_status",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=fields, dialect="excel-tab", lineterminator="\n"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if row.get(key) is None else row.get(key) for key in fields})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--pseudo", type=Path, required=True)
    parser.add_argument("--pose-binding", type=Path, required=True)
    parser.add_argument("--logical-tsv", type=Path, required=True)
    parser.add_argument("--matrix-tsv", type=Path, required=True)
    parser.add_argument("--scene-inventory", type=Path, required=True)
    parser.add_argument("--function-manifest", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--bindings-tsv", type=Path, required=True)
    args = parser.parse_args()
    try:
        report, rows = build_report(
            args.trace,
            args.pseudo,
            args.pose_binding,
            args.logical_tsv,
            args.matrix_tsv,
            args.scene_inventory,
            args.function_manifest,
        )
        write_json(args.json, report)
        write_bindings_tsv(args.bindings_tsv, rows)
    except (ConfigError, OSError, KeyError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()

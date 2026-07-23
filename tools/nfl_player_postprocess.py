#!/usr/bin/env python3
"""Build an address-accounted NFL 2K5 player-postprocess inventory.

This pass decomposes the player-only local-matrix postprocessor at 0x00092140,
its hierarchy wrapper at 0x00093800, and the current-matrix postprocessor at
0x00093850.  It joins every numbered matrix slot to the shipped ``lo_body``
and ``hi_body`` SCNE transform names, expands the two scaling loops, records
every persistent matrix write, inventories every static constant, and parses
the canonical Ghidra trace into an ordered call ledger.

No anatomy is inferred.  Names come only from exact serialized SCNE records.
The opaque player-context fields at +0x18 and +0x2a remain offset labels.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import struct
from typing import Any, Iterable

from nfl_bone_binding import decode_selected, resource_key, scene_shapes
from nfl_outer import parse_archive, read_entry_range
from nfl_rest_orientation import xbe_reader
from nfl_scene_probe import decode_resource, parse_inventory


SCHEMA = "nfl2k5_player_postprocess/v1"
EXPECTED_XBE_MD5 = "444064a9ec984dd29d2c05a43f5c96e8"
LO_RESOURCE = (3, 113)
HI_RESOURCE = (3, 114)
SKEL_RESOURCE = (3, 116)
LO_COUNT = 25
HI_COUNT = 62
MATRIX_STRIDE = 0x40
HIGH_OFFSET = 0x640

TARGETS = (0x00092140, 0x00093800, 0x00093850)
HELPERS = (
    0x00020B20, 0x000210B0, 0x00031110,
    0x000379A0, 0x00037A10, 0x00037AF0, 0x00037BA0, 0x000384A0,
    0x0008D550, 0x0008D610, 0x0008D630, 0x0008D8C0, 0x0008D9D0,
    0x00090250, 0x00090320,
    0x00091A60, 0x00091AC0, 0x00091B70, 0x00091C80,
    0x00091D90, 0x00091E70, 0x00091F60,
)
CALLERS = (
    0x0005C530, 0x0012F670, 0x001D2B40, 0x001DFAA0,
    0x0025C740, 0x0028E360, 0x00343220, 0x0035B520,
)
FOCUSED = HELPERS + TARGETS + CALLERS

TARGET_SPANS = {
    0x00092140: (0x00092140, 0x000937F6),
    0x00093800: (0x00093800, 0x00093849),
    0x00093850: (0x00093850, 0x00093B39),
}

SCHEDULE_VA = 0x004EF898
PROFILE_VA = 0x004EF018
PROFILE_STRIDE = 0xD0

EXPECTED_SCHEDULE = (
    0, 1, 2, 3, 4, 1, 2, 1, 1, 1, 1, 1, 1,
    5, 6, 7, 8, 5, 6, 5, 5, 5, 5, 5, 5,
    0, 9, 10, 11, 12, 13, 14, 15, 15, 15, 15, 15, 17,
    14, 14, 15, 14, 15, 14,
    18, 19, 20, 20, 20, 20, 20, 22, 19, 19, 20, 20, 19, 19,
    23, 24, 5, 1,
)

EXPECTED_DIRECT_CALLS_93850 = {
    0x0005C5E3: 0x01FFFFFF,
    0x0012F996: 0x01FFFFFF,
    0x001D2D4F: 0x01FFFFFF,
    0x001DFADF: 0x00001800,
    0x0025C880: 0x01FFFFFF,
    0x0028E99D: 0x01FFE7FF,
    0x003432F5: 0x01FFFFFF,
    0x0035B647: 0x01FFFFFF,
}

EXPECTED_DIRECT_CALLS_93800 = (
    0x0005C5CC, 0x0012F97B, 0x001D2D3E, 0x0025C872,
    0x0028E98C, 0x003432E4, 0x0035B636,
)

# One row per non-remap persistent write group in 0x00092140.  Initial name
# remaps are generated separately.  All labels below are exact HI_res names;
# the code deliberately does not replace them with guessed anatomical roles.
LOCAL_EXTRA_WRITERS: dict[int, tuple[str, str, str]] = {
    5: ("0x00092397..0x000923ca", "axis rotation; axial scale; left multiply", "0x000384a0;0x00037af0;0x00031110"),
    6: ("0x00092252", "two-axis axial scale matrix", "0x00090250"),
    7: ("0x000923ef..0x00092422", "axis rotation; axial scale; left multiply", "0x000384a0;0x00037af0;0x00031110"),
    8: ("0x000927b4", "aligned-basis stretch composition", "0x00091e70"),
    9: ("0x000925bf", "left multiply source matrix by derived rotation", "0x00037a10;0x00031110"),
    10: ("0x0009263f", "derived axis-angle rotation", "0x00037a10"),
    11: ("0x00092a79..0x00092aaf", "axial scale then axis rotation", "0x00037af0;0x000384a0;0x00031110"),
    12: ("0x0009285c", "two-vector aligned-basis composition", "0x00091f60"),
    17: ("0x000924f2..0x00092525", "axis rotation; axial scale; left multiply", "0x000384a0;0x00037af0;0x00031110"),
    18: ("0x000922cc", "two-axis axial scale matrix", "0x00090250"),
    19: ("0x0009254a..0x0009257d", "axis rotation; axial scale; left multiply", "0x000384a0;0x00037af0;0x00031110"),
    20: ("0x0009290d", "aligned-basis stretch composition", "0x00091e70"),
    21: ("0x00092683", "left multiply source matrix by derived rotation", "0x00037a10;0x00031110"),
    22: ("0x00092703", "derived axis-angle rotation", "0x00037a10"),
    23: ("0x00092b3d..0x00092b73", "axial scale then axis rotation", "0x00037af0;0x000384a0;0x00031110"),
    24: ("0x000929b8", "two-vector aligned-basis composition", "0x00091f60"),
    25: ("0x00092bea..0x00092c80", "basis build, nonuniform basis scale, normalize, and left multiply", "0x00091c80;0x0008d8c0;0x00091ac0;0x00091b70;0x00031110"),
    33: ("0x00092d67", "derived axis-angle rotation", "0x00037a10"),
    34: ("0x00092d80..0x00092d8c", "copy matrix 33", "inline MOVAPS loop"),
    35: ("0x00092da3..0x00092daf", "copy matrix 33", "inline MOVAPS loop"),
    36: ("0x00092dc6..0x00092dd2", "copy matrix 33", "inline MOVAPS loop"),
    37: ("0x000921c8", "right multiply remapped matrix by low slot 16", "0x00031110"),
    38: ("0x0009345d", "derived axis-angle rotation", "0x000384a0"),
    39: ("0x00093483..0x000934bf", "axial scale then axis rotation", "0x00037af0;0x000384a0;0x00031110"),
    40: ("0x00093075", "two-vector aligned-basis composition", "0x00091f60"),
    41: ("0x0009329c", "axial scale", "0x00037af0"),
    42: ("0x00092fca", "two-vector aligned-basis composition", "0x00091f60"),
    43: ("0x000935af", "normalized two-basis nonuniform composition", "0x00091d90"),
    47: ("0x00092eb8", "derived axis-angle rotation", "0x00037a10"),
    48: ("0x00092ed0..0x00092edc", "copy matrix 47", "inline MOVAPS loop"),
    49: ("0x00092ef3..0x00092eff", "copy matrix 47", "inline MOVAPS loop"),
    50: ("0x00092f16..0x00092f22", "copy matrix 47", "inline MOVAPS loop"),
    51: ("0x000921dc", "right multiply remapped matrix by low slot 21", "0x00031110"),
    52: ("0x000937e8", "normalized two-basis nonuniform composition", "0x00091d90"),
    53: ("0x0009336d", "axial scale", "0x00037af0"),
    54: ("0x000931cb", "two-vector aligned-basis composition", "0x00091f60"),
    55: ("0x00093120", "two-vector aligned-basis composition", "0x00091f60"),
    56: ("0x0009369a", "derived axis-angle rotation", "0x000384a0"),
    57: ("0x000936c0..0x000936fc", "axial scale then axis rotation", "0x00037af0;0x000384a0;0x00031110"),
    60: ("0x00092b9f..0x00092bd5", "axial scale then axis rotation", "0x00037af0;0x000384a0;0x00031110"),
    61: ("0x00092adb..0x00092b11", "axial scale then axis rotation", "0x00037af0;0x000384a0;0x00031110"),
}

HELPER_ROLES = {
    0x00020B20: "x87 float-to-signed-int truncation",
    0x000210B0: "signed two-input rational angle-unit approximation",
    0x00031110: "row-major 4x4 destination = left * right",
    0x000379A0: "pre-translation folded into an affine matrix's translation row",
    0x00037A10: "axis/sine/cosine row-vector rotation matrix",
    0x00037AF0: "axis-parallel scale: I + (scale-1) outer(axis,axis)",
    0x00037BA0: "axis-perpendicular scale: scale*I + (1-scale) outer(axis,axis)",
    0x000384A0: "16-bit angle lookup followed by 0x00037a10",
    0x0008D550: "x87 float-to-signed-int truncation",
    0x0008D610: "x87 square root",
    0x0008D630: "refined reciprocal square root",
    0x0008D8C0: "scale four matrix columns by three supplied factors",
    0x0008D9D0: "multiply xyz vector by a matrix 3x3 and emit four lanes",
    0x00090250: "axis scale with independent parallel/perpendicular factors",
    0x00090320: "project/normalize and emit a signed sine/cosine pair",
    0x00091A60: "vec4 Euclidean length",
    0x00091AC0: "normalize vec4, mapping exact zero norm to zero",
    0x00091B70: "construct row basis from normalized cross products (layout A)",
    0x00091C80: "construct row basis from normalized cross products (layout B)",
    0x00091D90: "normalized two-basis nonuniform matrix composition",
    0x00091E70: "normalized two-basis one-lane ratio composition",
    0x00091F60: "two-vector axial alignment and matrix composition",
}

PORTMES = [
    "// PORTME: translate every 0x00092140 call group to structured portable C while preserving its exact ordering and float32 store boundaries.",
    "// PORTME: reproduce Xbox SSE rsqrt seed behavior in 0x0008D630 if bit-identical current-matrix output is required; the portable subset uses sqrtf semantics.",
    "// PORTME: identify player-context +0x18 bits 3..4 and +0x2A from independent object-schema evidence; offsets and arithmetic are proved, labels are not.",
    "// PORTME: make the 0x00091D90/0x00091E70/0x00091F60 scratch workspace reentrant instead of copying the original globals at 0x00B65110..0x00B6526F.",
    "// PORTME: keep player animation export disabled until 0x00092140 is value-equivalently implemented and validated with runtime captures.",
]


class PostprocessError(ValueError):
    """A pinned executable, trace, or asset invariant failed."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def hex32(value: int) -> str:
    return f"0x{value:08x}"


def f32_text(value: float) -> str:
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    return format(value, ".9g")


def load_ledger(path: Path) -> dict[int, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    result: dict[int, dict[str, str]] = {}
    for row in rows:
        try:
            address = int(row["address"], 16)
        except ValueError:
            continue
        result[address] = row
    for address in FOCUSED:
        if address not in result:
            raise PostprocessError(f"function ledger is missing {hex32(address)}")
        if result[address]["decompile_status"] != "success":
            raise PostprocessError(f"{hex32(address)} did not decompile successfully")
    return result


def function_contract(
    read: Any, ledger: dict[int, dict[str, str]], addresses: Iterable[int]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for address in addresses:
        row = ledger[address]
        end = int(row["end"], 16) + 1
        body = read(address, end - address)
        rows.append(
            {
                "start": hex32(address),
                "end_exclusive": hex32(end),
                "size": len(body),
                "sha256": sha256(body),
                "name": row["name"],
                "body_ranges": row["body_ranges"],
                "callers": row["callers"],
                "callees": row["callees"],
            }
        )
    return rows


def parse_trace(
    path: Path, ledger: dict[int, dict[str, str]]
) -> tuple[dict[int, list[str]], list[dict[str, Any]], dict[int, list[int]]]:
    text = path.read_text(encoding="utf-8")
    if f"Program MD5: {EXPECTED_XBE_MD5}" not in text:
        raise PostprocessError("Ghidra trace has the wrong executable MD5")
    marker = "FOCUSED_FUNCTION_INSTRUCTIONS\n"
    if marker not in text:
        raise PostprocessError("Ghidra trace lacks focused instructions")
    lines = text.split(marker, 1)[1].splitlines()
    instructions: dict[int, list[str]] = {}
    current: int | None = None
    for line in lines:
        match = re.match(r"FUNCTION (0x[0-9A-Fa-f]+):", line)
        if match:
            current = int(match.group(1), 16)
            instructions.setdefault(current, [])
            continue
        if current is not None and re.match(r"0x[0-9A-Fa-f]+ ", line):
            instructions[current].append(line)
    if set(FOCUSED) - set(instructions):
        missing = ", ".join(hex32(value) for value in set(FOCUSED) - set(instructions))
        raise PostprocessError(f"trace lacks focused functions: {missing}")

    calls: list[dict[str, Any]] = []
    calls_to: dict[int, list[int]] = {}
    for owner in FOCUSED:
        sequence = 0
        for line in instructions[owner]:
            match = re.match(r"(0x[0-9A-Fa-f]+) .*\bCALL (0x[0-9A-Fa-f]+)", line)
            if not match:
                continue
            sequence += 1
            callsite = int(match.group(1), 16)
            target = int(match.group(2), 16)
            calls_to.setdefault(target, []).append(callsite)
            target_row = ledger.get(target)
            calls.append(
                {
                    "owner": hex32(owner),
                    "owner_name": ledger[owner]["name"],
                    "owner_scope": (
                        "target" if owner in TARGETS else
                        "direct_helper" if owner in HELPERS else "direct_caller"
                    ),
                    "sequence": sequence,
                    "callsite": hex32(callsite),
                    "target": hex32(target),
                    "target_name": target_row["name"] if target_row else "unfocused_or_indirect",
                    "semantic_role": HELPER_ROLES.get(target, "control/integration call"),
                    "instruction": line.split(" owner=", 1)[0],
                }
            )
    # The two player switch arms at 0x0012f970..0x0012f99b are not members of
    # Ghidra's recovered 0x0012f670 Function body.  The Java trace emits that
    # contiguous range separately; retain its two postprocess calls under the
    # controlling function instead of silently losing them.
    for callsite, target in ((0x0012F97B, 0x00093800), (0x0012F996, 0x00093850)):
        if any(int(row["callsite"], 16) == callsite for row in calls):
            continue
        raw_line = next(
            (
                line for line in text.splitlines()
                if line.startswith(f"0x{callsite:08X} ") and
                f"CALL {hex32(target)}".lower() in line.lower()
            ),
            None,
        )
        if raw_line is None:
            raise PostprocessError(f"raw switch-arm call {hex32(callsite)} is missing")
        calls_to.setdefault(target, []).append(callsite)
        calls.append(
            {
                "owner": hex32(0x0012F670),
                "owner_name": ledger[0x0012F670]["name"],
                "owner_scope": "direct_caller_raw_switch_arm",
                "sequence": 0,
                "callsite": hex32(callsite),
                "target": hex32(target),
                "target_name": ledger[target]["name"],
                "semantic_role": "control/integration call",
                "instruction": raw_line.split(" owner=", 1)[0],
            }
        )

    focus_order = {address: index for index, address in enumerate(FOCUSED)}
    calls.sort(key=lambda row: (focus_order[int(row["owner"], 16)], int(row["callsite"], 16)))
    sequences: dict[int, int] = {}
    for row in calls:
        owner = int(row["owner"], 16)
        sequences[owner] = sequences.get(owner, 0) + 1
        row["sequence"] = sequences[owner]
    for target in calls_to:
        calls_to[target].sort()
    return instructions, calls, calls_to


def decode_assets(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[list[float]], dict[str, Any]]:
    archive = parse_archive(args.index)
    _, parsed = parse_inventory(args.resource_scan)
    resources = {resource_key(item): item for item in parsed}

    lo_resource, lo_output, lo_detail = decode_selected(
        archive, resources, *LO_RESOURCE
    )
    lo_scene, lo_shapes = scene_shapes(lo_resource, lo_output)
    if lo_scene != "lo_body" or len(lo_shapes) != 1:
        raise PostprocessError("unexpected lo_body scene/shape count")
    lo_shape = lo_shapes[0]
    if lo_shape["shape_name"] != "LO_res" or lo_shape["transform_count"] != LO_COUNT:
        raise PostprocessError("unexpected LO_res transform contract")

    hi_resource, hi_output, hi_detail = decode_selected(
        archive, resources, *HI_RESOURCE
    )
    hi_scene, hi_shapes = scene_shapes(hi_resource, hi_output)
    if hi_scene != "hi_body" or len(hi_shapes) != 1:
        raise PostprocessError("unexpected hi_body scene/shape count")
    hi_shape = hi_shapes[0]
    if hi_shape["shape_name"] != "HI_res" or hi_shape["transform_count"] != HI_COUNT:
        raise PostprocessError("unexpected HI_res transform contract")

    skel_resource = resources[SKEL_RESOURCE]
    skel_span = read_entry_range(
        archive,
        archive.entries[SKEL_RESOURCE[0]],
        skel_resource.chunk_offset,
        0x20 + skel_resource.stored_size,
    )
    skel_output, skel_detail = decode_resource(skel_span, skel_resource)
    if skel_resource.kind != "SKEL" or skel_output[0x0C:0x10] != b"SKEL":
        raise PostprocessError("unexpected skeleton resource marker")
    if len(skel_output) != 480:
        raise PostprocessError("unexpected skeleton decoded size")
    vectors = [
        list(struct.unpack_from("<4f", skel_output, 0x50 + index * 0x10))
        for index in range(LO_COUNT)
    ]
    for index, vector in enumerate(vectors):
        norm = math.sqrt(sum(value * value for value in vector[:3]))
        if abs(norm - 1.0) > 1e-6 or vector[3] != 0.0:
            raise PostprocessError(f"SKEL record {index} is not normalized xyz0")

    sources = {
        "lo_body": {
            "resource": list(LO_RESOURCE),
            "decoded_sha256": sha256(lo_output),
            "decode_detail": lo_detail,
            "shape_name": lo_shape["shape_name"],
            "transform_table_sha256": lo_shape["transform_table_sha256"],
        },
        "hi_body": {
            "resource": list(HI_RESOURCE),
            "decoded_sha256": sha256(hi_output),
            "decode_detail": hi_detail,
            "shape_name": hi_shape["shape_name"],
            "transform_table_sha256": hi_shape["transform_table_sha256"],
        },
        "skeleton": {
            "resource": list(SKEL_RESOURCE),
            "decoded_sha256": sha256(skel_output),
            "decode_detail": skel_detail,
            "record_offset": 0x50,
            "record_count": LO_COUNT,
            "record_stride": 0x10,
        },
    }
    return lo_shape["transforms"], hi_shape["transforms"], vectors, sources


def profile_table(read: Any) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    for profile in range(4):
        raw = read(PROFILE_VA + profile * PROFILE_STRIDE, PROFILE_STRIDE)
        values = struct.unpack("<52f", raw)
        rows = []
        for channel in range(LO_COUNT):
            rows.append(
                {
                    "logical_channel": channel,
                    "lower": values[2 + channel * 2],
                    "upper": values[3 + channel * 2],
                }
            )
        profiles.append(
            {
                "profile": profile,
                "va": hex32(PROFILE_VA + profile * PROFILE_STRIDE),
                "reference": values[0],
                "multiplier": values[1],
                "channels": rows,
                "raw_hex": raw.hex(),
                "sha256": sha256(raw),
            }
        )
    return profiles


def transform_rows(
    lo: list[dict[str, Any]], hi: list[dict[str, Any]], schedule: tuple[int, ...],
    profiles: list[dict[str, Any]], vectors: list[list[float]],
) -> list[dict[str, Any]]:
    lo_by_name = {str(row["name"]): int(row["index"]) for row in lo}
    if len(lo_by_name) != LO_COUNT:
        raise PostprocessError("LO_res transform names are not unique")
    rows: list[dict[str, Any]] = []
    for transform in hi:
        high_index = int(transform["index"])
        low_index = lo_by_name.get(str(transform["name"]))
        source = schedule[high_index]
        writer = LOCAL_EXTRA_WRITERS.get(high_index)
        if writer is not None:
            final_writer = writer[0]
            final_operation = writer[1]
        elif low_index is not None:
            final_writer = "0x00092190..0x0009219e"
            final_operation = "name-map 64-byte copy from low matrix"
        else:
            raise PostprocessError(
                f"HI_res index {high_index} {transform['name']!r} has no writer"
            )
        rows.append(
            {
                "high_index": high_index,
                "high_offset": hex32(high_index * MATRIX_STRIDE),
                "high_name": transform["name"],
                "high_parent_index": transform["parent_index"],
                "high_parent_name": (
                    hi[int(transform["parent_index"])]["name"]
                    if int(transform["parent_index"]) >= 0 else ""
                ),
                "initial_low_index": "" if low_index is None else low_index,
                "initial_low_name": "" if low_index is None else lo[low_index]["name"],
                "local_final_writer": final_writer,
                "local_final_operation": final_operation,
                "current_scale_source_index": source,
                "current_scale_source_name": lo[source]["name"],
                "skel_x": f32_text(vectors[source][0]),
                "skel_y": f32_text(vectors[source][1]),
                "skel_z": f32_text(vectors[source][2]),
                **{
                    f"profile_{profile['profile']}_lower": f32_text(
                        float(profile["channels"][source]["lower"])
                    )
                    for profile in profiles
                },
                **{
                    f"profile_{profile['profile']}_upper": f32_text(
                        float(profile["channels"][source]["upper"])
                    )
                    for profile in profiles
                },
            }
        )
    if len(rows) != HI_COUNT:
        raise PostprocessError("wrong high transform row count")
    return rows


def write_rows(
    lo: list[dict[str, Any]], hi: list[dict[str, Any]], schedule: tuple[int, ...]
) -> list[dict[str, Any]]:
    hi_by_name = {str(row["name"]): int(row["index"]) for row in hi}
    rows: list[dict[str, Any]] = []
    order = 0

    for low in lo:
        order += 1
        low_index = int(low["index"])
        high_index = hi_by_name.get(str(low["name"]))
        rows.append(
            {
                "order": order,
                "function": "0x00092140",
                "address": "0x00092170..0x000921b7",
                "phase": "local_name_remap",
                "condition": f"runtime map[low {low_index}] != 0xff",
                "destination_array": "high_local",
                "destination_index": "" if high_index is None else high_index,
                "destination_name": "" if high_index is None else hi[high_index]["name"],
                "source_array": "low_local",
                "source_index": low_index,
                "source_name": low["name"],
                "operation": (
                    "skip in shipped map (no exact HI_res name)" if high_index is None
                    else "copy all 16 float lanes"
                ),
                "helpers": "inline MOVAPS loop",
            }
        )

    for high_index in sorted(LOCAL_EXTRA_WRITERS):
        order += 1
        address, operation, helpers = LOCAL_EXTRA_WRITERS[high_index]
        rows.append(
            {
                "order": order,
                "function": "0x00092140",
                "address": address,
                "phase": "local_auxiliary_or_adjustment",
                "condition": "always",
                "destination_array": "high_local",
                "destination_index": high_index,
                "destination_name": hi[high_index]["name"],
                "source_array": "ordered operands in call ledger/raw trace",
                "source_index": "",
                "source_name": "",
                "operation": operation,
                "helpers": helpers,
            }
        )

    for low in lo:
        order += 1
        index = int(low["index"])
        rows.append(
            {
                "order": order,
                "function": "0x00093850",
                "address": "0x000938f7..0x00093958",
                "phase": "current_low_axis_scale",
                "condition": f"mask bit {index} set",
                "destination_array": "low_current",
                "destination_index": index,
                "destination_name": low["name"],
                "source_array": "SKEL/profile",
                "source_index": index,
                "source_name": low["name"],
                "operation": "axis-perpendicular scale matrix * current matrix",
                "helpers": "0x00037ba0;0x00031110",
            }
        )

    for high in hi:
        order += 1
        index = int(high["index"])
        source = schedule[index]
        rows.append(
            {
                "order": order,
                "function": "0x00093850",
                "address": "0x00093970..0x00093a6d",
                "phase": "current_high_pivot_scale",
                "condition": f"mask bit {source} set",
                "destination_array": "high_current",
                "destination_index": index,
                "destination_name": high["name"],
                "source_array": "low SKEL/profile channel",
                "source_index": source,
                "source_name": lo[source]["name"],
                "operation": "transform+normalize axis; current * (T(-p)*S*T(p))",
                "helpers": "0x0008d9d0;0x00091ac0;0x00037ba0;0x000379a0;0x00031110",
            }
        )

    order += 1
    rows.append(
        {
            "order": order,
            "function": "0x00093850",
            "address": "0x00093a73..0x00093b2a",
            "phase": "conditional_low_head_basis_scale",
            "condition": "global 0x00e601f0 != 0 and mask bit 12 set",
            "destination_array": "low_current",
            "destination_index": 12,
            "destination_name": lo[12]["name"],
            "source_array": "same matrix",
            "source_index": 12,
            "source_name": lo[12]["name"],
            "operation": "multiply the nine 3x3 basis lanes by f32 1.899999976158142",
            "helpers": "inline x87 loads/multiplies/stores",
        }
    )
    return rows


def constant_rows(
    read: Any, instructions: dict[int, list[str]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ranges = (
        ("fixed_angle_lut_f32", 0x004E53E8, 0x800, "f32"),
        ("signed_angle_coefficients_f32", 0x004E5C4C, 0x18, "f32"),
        ("projection_clamp_f32", 0x004E5C7C, 0x04, "f32"),
        ("common_zero_half_one_f32", 0x004E4180, 0x08, "f32"),
        ("common_one_f32", 0x004E419C, 0x04, "f32"),
        ("angle_scale_f32", 0x004E696C, 0x04, "f32"),
        ("blend_scale_f32", 0x004E6D5C, 0x04, "f32"),
        ("lower_clamp_f32", 0x004E88E4, 0x04, "f32"),
        ("current_scale_profiles_f32", PROFILE_VA, 4 * PROFILE_STRIDE, "f32"),
        ("current_high_schedule_u8", SCHEDULE_VA, HI_COUNT, "u8"),
        ("local_postprocess_constants_f32", 0x004EF8E0, 0x57C, "f32"),
    )
    relevant = set(TARGETS) | set(HELPERS)
    reference_map: dict[int, set[int]] = {}
    for owner in relevant:
        for line in instructions[owner]:
            callsite_match = re.match(r"0x([0-9A-Fa-f]+)", line)
            if callsite_match is None:
                continue
            site = int(callsite_match.group(1), 16)
            for token in re.findall(r"0x[0-9A-Fa-f]+", line):
                value = int(token, 16)
                if 0x00400000 <= value < 0x00600000:
                    reference_map.setdefault(value, set()).add(site)

    rows: list[dict[str, Any]] = []
    range_reports = []
    covered: set[int] = set()
    for category, start, size, data_type in ranges:
        raw = read(start, size)
        range_reports.append(
            {
                "category": category,
                "start": hex32(start),
                "size": size,
                "sha256": sha256(raw),
            }
        )
        step = 1 if data_type == "u8" else 4
        for offset in range(0, size, step):
            value_raw = raw[offset : offset + step]
            va = start + offset
            refs = sorted(reference_map.get(va, set()))
            covered.add(va)
            if data_type == "u8":
                value = str(value_raw[0])
                bits = f"0x{value_raw[0]:02x}"
            else:
                value = f32_text(struct.unpack("<f", value_raw)[0])
                bits = f"0x{struct.unpack('<I', value_raw)[0]:08x}"
            rows.append(
                {
                    "category": category,
                    "element": offset // step,
                    "va": hex32(va),
                    "data_type": data_type,
                    "bits": bits,
                    "value": value,
                    "direct_reference_count": len(refs),
                    "direct_references": ";".join(hex32(site) for site in refs),
                }
            )

    # Every read-only executable address referenced directly by the targets or
    # helpers must be in one of the pinned constant ranges.  Runtime globals,
    # functions, and the dynamic map are outside 0x00400000..0x005fffff or are
    # executable addresses below the first constant range.
    allowed_pointer_bases = set(covered)
    allowed_pointer_bases.update(
        start for _, start, _, _ in ranges
    )
    unresolved = sorted(
        value for value in reference_map
        if value >= 0x004E0000 and not any(
            start <= value < start + size for _, start, size, _ in ranges
        )
    )
    if unresolved:
        raise PostprocessError(
            "unaccounted static constant references: " +
            ", ".join(hex32(value) for value in unresolved)
        )
    return rows, {"ranges": range_reports, "direct_static_reference_count": len(reference_map)}


def helper_contracts() -> list[dict[str, Any]]:
    contracts = []
    for address in HELPERS:
        contract: dict[str, Any] = {
            "address": hex32(address),
            "role": HELPER_ROLES[address],
            "portable_status": "equation recovered; 0x00092140 integration remains PORTME",
        }
        if address == 0x00031110:
            contract["equation"] = "destination[r,c] = sum(left[r,k] * right[k,c], k=0..3)"
            contract["abi"] = "ECX=destination, EDX=left, stack+0=right; destination may alias either input"
        elif address == 0x00037AF0:
            contract["equation"] = "M3x3 = I + (scale - 1) * outer(axis, axis); affine translation=0"
        elif address == 0x00037BA0:
            contract["equation"] = "M3x3 = scale*I + (1 - scale) * outer(axis, axis); affine translation=0"
        elif address == 0x00090250:
            contract["equation"] = "M3x3 = perpendicular*I + (parallel-perpendicular)*outer(axis,axis)"
        elif address == 0x000379A0:
            contract["equation"] = "translation.xyz += vector.xyz * M3x3 (row-vector pre-translation)"
        elif address == 0x0008D9D0:
            contract["equation"] = "out[c] = x*M[0,c] + y*M[1,c] + z*M[2,c], c=0..3"
        elif address == 0x00091AC0:
            contract["equation"] = "out = input * refined_rsqrt(dot4(input,input)); exact zero -> [0,0,0,0]"
        elif address in (0x00091D90, 0x00091E70, 0x00091F60):
            contract["side_effect"] = "uses global scratch in 0x00b65110..0x00b6526f; original is not reentrant"
        contracts.append(contract)
    return contracts


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise PostprocessError(f"refusing to write empty TSV {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0])
    for row in rows:
        if list(row) != fieldnames:
            raise PostprocessError(f"inconsistent TSV fields for {path}")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    xbe = args.xbe.read_bytes()
    if hashlib.md5(xbe).hexdigest() != EXPECTED_XBE_MD5:
        raise PostprocessError("unexpected NFL 2K5 XBE MD5")
    header = json.loads(args.xbe_header.read_text(encoding="utf-8"))
    read = xbe_reader(xbe, header)
    ledger = load_ledger(args.ledger)
    functions = function_contract(read, ledger, FOCUSED)

    for address, (start, end) in TARGET_SPANS.items():
        row = next(item for item in functions if item["start"] == hex32(address))
        if int(row["start"], 16) != start or int(row["end_exclusive"], 16) != end:
            raise PostprocessError(f"target span mismatch at {hex32(address)}")

    instructions, calls, calls_to = parse_trace(args.ghidra_trace, ledger)
    if tuple(sorted(calls_to.get(0x00093800, []))) != EXPECTED_DIRECT_CALLS_93800:
        raise PostprocessError("0x00093800 direct-call set differs")
    actual_93850 = sorted(calls_to.get(0x00093850, []))
    if actual_93850 != sorted(EXPECTED_DIRECT_CALLS_93850):
        raise PostprocessError("0x00093850 direct-call set differs")
    if calls_to.get(0x00092140) != [0x00093816]:
        raise PostprocessError("0x00092140 caller differs")

    lo, hi, vectors, asset_sources = decode_assets(args)
    schedule_raw = read(SCHEDULE_VA, HI_COUNT)
    schedule = tuple(schedule_raw)
    if schedule != EXPECTED_SCHEDULE:
        raise PostprocessError("0x004ef898 schedule differs")
    profiles = profile_table(read)
    transforms = transform_rows(lo, hi, schedule, profiles, vectors)
    writes = write_rows(lo, hi, schedule)
    constants, constant_contract = constant_rows(read, instructions)

    low_names = [str(item["name"]) for item in lo]
    direct_call_rows = []
    for callsite, mask in EXPECTED_DIRECT_CALLS_93850.items():
        enabled = [index for index in range(LO_COUNT) if mask & (1 << index)]
        owner = next(
            (int(row["owner"], 16) for row in calls if int(row["callsite"], 16) == callsite),
            None,
        )
        if owner is None:
            raise PostprocessError(f"missing call owner for {hex32(callsite)}")
        direct_call_rows.append(
            {
                "callsite": hex32(callsite),
                "owner": hex32(owner),
                "owner_name": ledger[owner]["name"],
                "mask": hex32(mask),
                "enabled_count": len(enabled),
                "enabled_indices": ",".join(str(index) for index in enabled),
                "enabled_names": ",".join(low_names[index] for index in enabled),
            }
        )

    branch_lines = {
        hex32(target): [
            line.split(" owner=", 1)[0]
            for line in instructions[target]
            if re.match(r"0x[0-9A-Fa-f]+ J", line)
        ]
        for target in TARGETS
    }
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "executable": {
            "path": str(args.xbe),
            "md5": EXPECTED_XBE_MD5,
            "size": len(xbe),
            "sha256": sha256(xbe),
            "ledger_path": str(args.ledger),
            "ledger_sha256": sha256_file(args.ledger),
            "functions": functions,
        },
        "ghidra": {
            "trace_path": str(args.ghidra_trace),
            "trace_sha256": sha256_file(args.ghidra_trace),
            "pseudo_path": str(args.ghidra_pseudo),
            "pseudo_sha256": sha256_file(args.ghidra_pseudo),
            "focused_function_count": len(FOCUSED),
            "ordered_call_count": len(calls),
            "target_branches": branch_lines,
        },
        "asset_sources": asset_sources,
        "matrix_contract": {
            "low_shape": "lo_body/LO_res",
            "low_count": LO_COUNT,
            "high_shape": "hi_body/HI_res",
            "high_count": HI_COUNT,
            "matrix_stride": MATRIX_STRIDE,
            "high_array_offset": HIGH_OFFSET,
            "initial_map": "exact case-sensitive transform-name equality; lwrist/rwrist are the only unmatched low names",
            "all_high_matrices_have_a_local_writer": True,
            "all_high_matrices_have_a_current_scale_source": True,
        },
        "runtime_inputs": [
            {
                "location": "0x00b65b78",
                "type": "runtime SKEL object pointer",
                "reads": "0x00092140/0x00093850 consume the 25 vec4 records at object +0x10; 0x00093800 reads shape pointer +0x04",
            },
            {
                "location": "0x00b65bfc[25]",
                "type": "runtime u8 low-to-high transform-name map",
                "reads": "0x00092170..0x000921b7; 0xff skips, otherwise byte*0x40 is the high destination",
            },
            {
                "location": "0x00b65288",
                "type": "runtime high-shape lookup context",
                "reads": "0x0009381b supplies the 0x0002eb70 high-shape lookup",
            },
            {
                "location": "player_context+0x18",
                "type": "u32",
                "reads": "0x00093867; bits 3..4 select one of four 0xd0 profiles",
            },
            {
                "location": "player_context+0x2a",
                "type": "u8",
                "reads": "0x00093859; zero-extended then increased by 150",
            },
            {
                "location": "0x00e601f0",
                "type": "u32 global",
                "reads": "0x00093a73; nonzero permits the final matrix-12 basis scale when mask bit 12 is set",
            },
            {
                "location": "low/high matrix storage",
                "type": "25 + 62 row-major 4x4 f32 matrices",
                "reads": "all three targets; high begins exactly 0x640 bytes after low",
            },
            {
                "location": "0x004e53e8..0x004efe5b selected read-only ranges",
                "type": "f32/u8 tables",
                "reads": "every element and direct reference is enumerated in the constants TSV",
            },
        ],
        "function_0x00092140": {
            "abi": {
                "EAX": "high_local[62] destination at low_local + 0x640",
                "ECX": "low_local[25] source",
                "stack_0": "player-context value passed through wrapper but not read",
                "return": "RET 4",
            },
            "inputs": [
                "25 low 4x4 matrices",
                "runtime name map bytes at 0x00b65bfc[25]",
                "SKEL skeleton normalized vec4 records through global pointer 0x00b65b78",
                "static f32/vector tables 0x004ef8e0..0x004efe53",
            ],
            "persistent_output": "62 high local 4x4 matrices; every shipped HI_res slot receives a writer",
            "ordering": "25 name remaps; two low wrist-to-high hand multiplies; ordered auxiliary derivations in call/write TSVs",
            "condition_count": len(branch_lines[hex32(0x00092140)]),
            "conditions": [
                "0x00092178: map byte equals 0xff -> skip this low slot",
                "0x00092187/0x0009219e: guard and repeat the 64-byte mapped matrix copy",
                "0x000921b7: repeat until all 25 low slots have been visited",
                "0x000925db,0x0009269f,0x00092cde,0x00092e31: choose +1 for a nonnegative/unordered compared component and -1 for a negative component",
                "0x00092d77/0x00092d7b/0x00092d8c: guard/enter/repeat the matrix-33 to matrix-34 copy",
                "0x00092d99/0x00092daf: guard/repeat the matrix-33 to matrix-35 copy",
                "0x00092dbc/0x00092dd2: guard/repeat the matrix-33 to matrix-36 copy",
                "0x00092ec8/0x00092edc: guard/repeat the matrix-47 to matrix-48 copy",
                "0x00092ee9/0x00092eff: guard/repeat the matrix-47 to matrix-49 copy",
                "0x00092f0c/0x00092f22: guard/repeat the matrix-47 to matrix-50 copy",
            ],
            "portable_status": "instruction/helper decomposition complete; structured value-equivalent integration remains PORTME",
        },
        "function_0x00093800": {
            "abi": {
                "ECX": "player context, forwarded as unused stack value to 0x00092140",
                "EDX": "external root matrix",
                "stack_0": "low matrix array",
            },
            "order": [
                "0x00092140 builds high local matrices at low+0x640",
                "0x0002eb70 selects the high shape",
                "0x000233c0 expands high locals with the external root",
                "0x000233c0 expands low locals with the same external root",
            ],
        },
        "function_0x00093850": {
            "abi": {
                "ECX": "player context",
                "EDX": "25-bit update mask",
                "stack_0": "low current matrix array; high current array begins at +0x640",
                "return": "RET 4",
            },
            "input_fields": {
                "player_context+0x18_u32": "profile = (value >> 3) & 3; field meaning intentionally unnamed",
                "player_context+0x2a_u8": "scalar = byte + 150, clamped to [150,450]; field meaning intentionally unnamed",
                "global_0x00e601f0_u32": "nonzero enables the final conditional matrix-12 3x3 scale",
            },
            "skel_vectors": [
                {
                    "index": index,
                    "name": lo[index]["name"],
                    "values": vectors[index],
                    "xyz_norm": math.sqrt(sum(value * value for value in vectors[index][:3])),
                }
                for index in range(LO_COUNT)
            ],
            "conditions": [
                "0x000938a8: scalar >= 450 (or unordered) -> select 450",
                "0x000938bd: otherwise scalar <= 150 -> select 150",
                "0x000938c3/0x000938ce: join the two clamp assignments",
                "0x00093906: low-loop mask bit i clear -> skip low write",
                "0x00093958: repeat low loop while i < 25",
                "0x00093984: high-loop mask bit schedule[j] clear -> skip high write",
                "0x00093a6d: repeat high loop while j < 62",
                "0x00093a7b: global 0x00e601f0 equals zero -> skip final stage",
                "0x00093a88: mask bit 12 clear -> skip final stage",
            ],
            "profile_equation": "t = (clamp(float(u8 + 150),150,450) - profile.reference) * profile.multiplier; scale_i = lower_i + (upper_i-lower_i)*t",
            "low_loop": "for i=0..24 with mask bit i: low[i] = perpendicular_axis_scale(SKEL[i], scale_i) * low[i]",
            "high_loop": "for j=0..61 with mask bit schedule[j]: transform+normalize SKEL[schedule[j]], build T(-p)*S*T(p) from high[j].translation p, then high[j] = high[j] * pivot_scale",
            "final_condition": "if global 0x00e601f0 != 0 and mask bit 12: multiply low[12] 3x3 by f32 1.899999976158142",
            "profiles": profiles,
            "schedule_va": hex32(SCHEDULE_VA),
            "schedule_raw_hex": schedule_raw.hex(),
            "direct_callers": direct_call_rows,
            "portable_status": "bounded semantic C subset implemented; Xbox rsqrt seed and x87 bit identity remain PORTME",
        },
        "helper_contracts": helper_contracts(),
        "constants": constant_contract,
        "counts": {
            "low_transforms": len(lo),
            "high_transforms": len(hi),
            "skel_vectors": len(vectors),
            "persistent_write_rows": len(writes),
            "constant_rows": len(constants),
            "ordered_call_rows": len(calls),
            "direct_current_callers": len(direct_call_rows),
        },
        "worked": [
            "joined all 25 low and 62 high matrix indices to exact shipped SCNE transform names",
            "proved the dynamic low-to-high name map and both unmatched wrist slots",
            "proved every high local matrix receives a writer and expanded all 87 mask-controlled current-matrix writes",
            "recovered all four 0xd0 scalar profiles and the full 62-byte high-to-low scale schedule",
            "parsed every focused call in address order and pinned every target/helper/caller body",
            "inventoried every static f32/u8 constant range consumed by the targets and direct arithmetic helpers",
        ],
        "failed": [
            "0x00092140 is not yet emitted as structured portable C",
            "player-context +0x18 bits 3..4 and +0x2a lack independent semantic field names",
            "bit-identical Xbox rsqrt seed behavior and x87 extended intermediates are not reproduced",
            "no player animation was exported from this evidence pass",
        ],
        "portme": PORTMES,
    }
    return report, transforms, writes, calls, constants


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xbe", type=Path, default=Path("extracted/ESPN NFL 2K5 (USA)/default.xbe"))
    parser.add_argument("--xbe-header", type=Path, default=Path("reports/headers/nfl2k5_xbe_header.json"))
    parser.add_argument("--ledger", type=Path, default=Path("research/functions/nfl2k5/functions.tsv"))
    parser.add_argument("--index", type=Path, default=Path("extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"))
    parser.add_argument("--resource-scan", type=Path, default=Path("reports/assets/nfl2k5_resource_chunks_v2.json"))
    parser.add_argument("--ghidra-trace", type=Path, default=Path("reports/assets/nfl_player_postprocess_ghidra/nfl_player_postprocess_trace.txt"))
    parser.add_argument("--ghidra-pseudo", type=Path, default=Path("reports/assets/nfl_player_postprocess_ghidra/nfl_player_postprocess_focused_pseudo_c.c"))
    parser.add_argument("--json", type=Path, default=Path("reports/assets/nfl_player_postprocess.json"))
    parser.add_argument("--transforms-tsv", type=Path, default=Path("reports/assets/nfl_player_postprocess_transforms.tsv"))
    parser.add_argument("--writes-tsv", type=Path, default=Path("reports/assets/nfl_player_postprocess_writes.tsv"))
    parser.add_argument("--calls-tsv", type=Path, default=Path("reports/assets/nfl_player_postprocess_calls.tsv"))
    parser.add_argument("--constants-tsv", type=Path, default=Path("reports/assets/nfl_player_postprocess_constants.tsv"))
    return parser.parse_args()


def main() -> int:
    args = arguments()
    report, transforms, writes, calls, constants = build(args)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_tsv(args.transforms_tsv, transforms)
    write_tsv(args.writes_tsv, writes)
    write_tsv(args.calls_tsv, calls)
    write_tsv(args.constants_tsv, constants)
    print(
        "NFL_PLAYER_POSTPROCESS_REPORT_COMPLETE "
        f"low={len(transforms) - 37} high={len(transforms)} "
        f"writes={len(writes)} calls={len(calls)} constants={len(constants)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

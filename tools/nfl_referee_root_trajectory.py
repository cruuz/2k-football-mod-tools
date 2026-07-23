#!/usr/bin/env python3
"""Pin the selected NFL 2K5 referee clip's gameplay root-motion path.

This report joins the exact fixed-slot SMCD trajectory payload to the
gameplay referee controller and its actor-transform callback.  It deliberately
does not manufacture a glTF translation track: the title applies live actor
scale, controller heading, and mutable transform state after sampling.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
from typing import Any, Callable, Iterable

import nfl_outer


SCHEMA = "nfl2k5_referee_root_trajectory/v1"
EXPECTED_XBE_MD5 = "444064a9ec984dd29d2c05a43f5c96e8"
EXPECTED_XBE_SHA256 = (
    "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
)
EXPECTED_INVENTORY_SCHEMA = "nfl2k5_motion_inventory/v1"
EXPECTED_OWNERSHIP_SCHEMA = "nfl2k5_ref_clip_ownership/v1"
EXPECTED_AXIS_SCHEMA = "nfl2k5_axis_root_motion/v1"
TARGET_NAME = "ANM_REF_PENALTY_DELAY_OF_GAME_R"
TARGET_OUTER_INDEX = 3107
TARGET_OUTER_ID = "0xda37aa9d"
TARGET_CHUNK_INDEX = 27
TARGET_CHUNK_OFFSET = 0x4A400
TARGET_BODY_SIZE = 4400
TARGET_BODY_SHA256 = (
    "75b67ce8f338943a8cc6bdc46718f61c7c2d9c4945d186983796a090aa31363f"
)
TARGET_TRAJECTORY_OFFSET = 164
TARGET_TRAJECTORY_SIZE = 368
TARGET_TRAJECTORY_SHA256 = (
    "829de7b7999ea1a47401d81b4ccc7bfa042d872614e0ee50c792babdded111fa"
)
TARGET_FRAME_COUNT = 46
TARGET_SAMPLE_RATE = 15
TARGET_FLAGS = 2
TARGET_DURATION_RAW = 0x403DDDDF
WRAPPER_SIZE = 0x20
POSITION_SCALE = 0.125
CANONICAL_SAMPLES_PATH = Path(
    "reports/assets/nfl_referee_root_trajectory_samples.tsv"
)

# Exclusive ranges are the complete contiguous Ghidra function bodies.  The
# report hashes the raw executable bytes, independently of decompiler output.
FUNCTION_RANGES = (
    ("trajectory_sampler", 0x000DEE30, 0x000DF030),
    ("trajectory_interval", 0x000DF3D0, 0x000DF445),
    ("referee_scene_loader", 0x00096600, 0x00096A15),
    ("referee_hierarchy_apply", 0x00096B20, 0x00096B4E),
    ("referee_actor_constructor", 0x00217D00, 0x00217E01),
    ("referee_pool_initializer", 0x00217EB0, 0x00217F1F),
    ("referee_actor_update", 0x00218010, 0x00218087),
    ("referee_pool_update", 0x002180D0, 0x00218144),
    ("gameplay_referee_play_setup", 0x002406E0, 0x00240744),
    ("controller_fixed_turn_sincos", 0x002D6950, 0x002D69B1),
    ("controller_install_motion", 0x002D6B70, 0x002D6CC1),
    ("callback_fixed_turn_sincos", 0x002CC470, 0x002CC4D1),
    ("referee_trajectory_callback", 0x002CC570, 0x002CC622),
    ("live_transform_state_step", 0x00318310, 0x00318422),
    ("single_track_controller_step", 0x0031B2E0, 0x0031B4DF),
    ("dual_track_controller_step", 0x0031B4E0, 0x0031B908),
    ("controller_update_dispatch", 0x0031BEB0, 0x0031C0C2),
)

REQUIRED_TRACE_LINES = (
    "0x00218115 MOV ESI,dword ptr [0x00e60274]",
    "0x00218120 CALL 0x00218010",
    "0x00218019 MOV EDI,dword ptr [ESI + 0x14]",
    "0x0021801C PUSH 0x2d6aa0",
    "0x00218021 PUSH 0x2cc570",
    "0x0021802B CALL 0x0031beb0",
    "0x0024073A MOV ECX,EDI",
    "0x0024073C CALL 0x002d6b70",
    "0x0031B391 CALL 0x000df3d0",
    "0x0031B39A FMUL float ptr [ESI + 0x30]",
    "0x0031B3A1 FMUL float ptr [ESI + 0x2c]",
    "0x0031B49E CALL dword ptr [ESP + 0x80]",
    "0x002CC57A FLD float ptr [EDI + 0x8]",
    "0x002CC57D MOV ESI,dword ptr [EDI + 0x18]",
    "0x002CC582 LEA ECX,[ESI + 0x84]",
    "0x002CC5AF CALL 0x00318310",
    "0x002CC5CA MOV dword ptr [ESI + 0x34],ECX",
    "0x002CC5D1 MOV dword ptr [ESI + 0x38],ECX",
    "0x002CC5DC MOV dword ptr [ESI + 0x30],EDX",
    "0x002CC5E1 MOV dword ptr [ESI + 0x3c],0x3f800000",
    "0x002CC5FA MOV dword ptr [ESI + 0x50],ECX",
    "0x002CC60F MOV dword ptr [EDI + 0x28],ECX",
    "0x002CC617 CALL 0x002cc470",
)

PORTMES = [
    "// PORTME at 0x00318310: preserve the live transform-state inputs at actor transform +0x84; raw clip X/Z/Y are not final actor-space values.",
    "// PORTME: identify the concrete one-of-seven referee pool record selected for penalty row 4 and capture its initial scale, heading, and transform state.",
    "// PORTME: join actor +0x18 to the final referee render external-root consumer before exporting a gameplay-equivalent glTF root track.",
    "// PORTME: recover loop-boundary accumulation for looping referee clips; the selected delay-of-game witness is non-looping.",
]


class TrajectoryError(ValueError):
    """Raised when a pinned source or recovered contract differs."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_pin(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": sha256_file(path)}


def labeled_pin(label: Path, actual: Path) -> dict[str, str]:
    return {"path": str(label), "sha256": sha256_file(actual)}


def load_json(path: Path, schema: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != schema:
        raise TrajectoryError(f"{path}: expected schema {schema!r}")
    return value


def float_text(value: float) -> str:
    return format(value, ".9g")


def f32_from_bits(value: int) -> float:
    return struct.unpack("<f", struct.pack("<I", value))[0]


def xbe_reader(xbe: bytes, header: dict[str, Any]) -> Callable[[int, int], bytes]:
    def read(va: int, size: int) -> bytes:
        for section in header["sections"]:
            start = int(section["virtual_address"])
            raw_size = int(section["raw_size"])
            if start <= va and va + size <= start + raw_size:
                offset = int(section["raw_address"]) + va - start
                result = xbe[offset:offset + size]
                if len(result) != size:
                    break
                return result
        raise TrajectoryError(
            f"XBE VA 0x{va:08x}+0x{size:x} is not completely raw-backed"
        )
    return read


def executable_evidence(xbe_path: Path, header_path: Path) -> dict[str, Any]:
    xbe = xbe_path.read_bytes()
    header = json.loads(header_path.read_text(encoding="utf-8"))
    md5 = hashlib.md5(xbe).hexdigest()
    digest = sha256(xbe)
    if md5 != EXPECTED_XBE_MD5 or digest != EXPECTED_XBE_SHA256:
        raise TrajectoryError(f"unexpected NFL 2K5 XBE {md5}/{digest}")
    if header.get("md5") != md5 or header.get("sha256") != digest:
        raise TrajectoryError("XBE header report does not pin the executable")
    read = xbe_reader(xbe, header)
    ranges = []
    for name, start, end in FUNCTION_RANGES:
        body = read(start, end - start)
        ranges.append({
            "name": name,
            "start": f"0x{start:08x}",
            "end_exclusive": f"0x{end:08x}",
            "size": len(body),
            "sha256": sha256(body),
        })
    return {
        "path": str(xbe_path),
        "md5": md5,
        "sha256": digest,
        "header": source_pin(header_path),
        "function_ranges": ranges,
    }


def selected_resource(inventory: dict[str, Any]) -> dict[str, Any]:
    matches = [
        row for row in inventory.get("resources", [])
        if row.get("name") == TARGET_NAME
    ]
    if len(matches) != 1:
        raise TrajectoryError(
            f"expected one {TARGET_NAME!r}, found {len(matches)}"
        )
    row = matches[0]
    exact = {
        "kind": "SMCD",
        "outer_index": TARGET_OUTER_INDEX,
        "outer_id": TARGET_OUTER_ID,
        "chunk_index": TARGET_CHUNK_INDEX,
        "chunk_offset": TARGET_CHUNK_OFFSET,
        "decoded_length": TARGET_BODY_SIZE,
        "decoded_sha256": TARGET_BODY_SHA256,
        "root_count": 1,
    }
    for key, expected in exact.items():
        if row.get(key) != expected:
            raise TrajectoryError(
                f"selected resource {key} differs: {row.get(key)!r}"
            )
    return row


def validate_upstream(ownership: dict[str, Any], axis: dict[str, Any]) -> None:
    selected = ownership.get("selected_clip", {})
    expected = {
        "name": TARGET_NAME,
        "outer_index": TARGET_OUTER_INDEX,
        "outer_id": TARGET_OUTER_ID,
        "chunk_index": TARGET_CHUNK_INDEX,
        "slot_offset": TARGET_CHUNK_OFFSET,
        "decoded_length": TARGET_BODY_SIZE,
        "decoded_sha256": TARGET_BODY_SHA256,
        "frame_count": TARGET_FRAME_COUNT,
        "sample_rate_hz": TARGET_SAMPLE_RATE,
        "flags": TARGET_FLAGS,
        "trajectory_bytes": TARGET_TRAJECTORY_SIZE,
        "trajectory_stride": 8,
    }
    for key, value in expected.items():
        if selected.get(key) != value:
            raise TrajectoryError(f"ownership selected_clip.{key} differs")
    runtime = ownership.get("runtime_ownership", {})
    if runtime.get("gameplay_actor_pool_head_va") != "0x00e60274":
        raise TrajectoryError("ownership report lost the referee pool head")
    if runtime.get("gameplay_actor_pool_max_count") != 7:
        raise TrajectoryError("ownership report lost the seven-entry bound")
    if runtime.get("specific_pool_record_instance_link_proved") is not False:
        raise TrajectoryError("ownership report overclaims a pool instance")
    contract = axis.get("proved_contract", {})
    if contract.get("position_units") != (
        "centimeters; 1 engine position unit = 0.01 meter"
    ):
        raise TrajectoryError("axis report position units differ")
    if contract.get("interval_0x000df3d0") != (
        "D(t0,t1) = [X1-X0, Y1, Z1-Z0, t1-t0, turn1-turn0]; "
        "mirror negates X and turn only"
    ):
        raise TrajectoryError("axis report interval contract differs")


def extract_trajectory(index_path: Path, resource: dict[str, Any]) -> tuple[bytes, bytes]:
    archive = nfl_outer.parse_archive(index_path)
    entry = archive.entries[TARGET_OUTER_INDEX]
    if f"0x{entry.name_id:08x}" != TARGET_OUTER_ID:
        raise TrajectoryError("outer archive identifier differs")
    body = nfl_outer.read_entry_range(
        archive, entry, TARGET_CHUNK_OFFSET + WRAPPER_SIZE,
        int(resource["stored_size"]),
    )
    if len(body) != TARGET_BODY_SIZE or sha256(body) != TARGET_BODY_SHA256:
        raise TrajectoryError("selected SMCD body differs")
    trajectory = next(
        (
            region for region in resource["packed_regions"]
            if int(region["owner_root_index"]) == 0
            and int(region["owner_pointer_field_relative"]) == 0x28
        ),
        None,
    )
    if trajectory is None:
        raise TrajectoryError("selected SMCD has no trajectory region")
    if (
        int(trajectory["offset"]) != TARGET_TRAJECTORY_OFFSET
        or int(trajectory["length"]) != TARGET_TRAJECTORY_SIZE
        or trajectory["sha256"] != TARGET_TRAJECTORY_SHA256
    ):
        raise TrajectoryError("selected trajectory-region metadata differs")
    payload = body[
        TARGET_TRAJECTORY_OFFSET:
        TARGET_TRAJECTORY_OFFSET + TARGET_TRAJECTORY_SIZE
    ]
    if sha256(payload) != TARGET_TRAJECTORY_SHA256:
        raise TrajectoryError("selected trajectory bytes differ")
    return body, payload


def decode_records(payload: bytes) -> list[dict[str, Any]]:
    if len(payload) != TARGET_FRAME_COUNT * 8:
        raise TrajectoryError("trajectory payload does not tile into 46 records")
    result = []
    for index, packed in enumerate(struct.iter_unpack("<hhhh", payload)):
        x, y, z, turn = packed
        result.append({
            "frame_index": index,
            "nominal_time_seconds": float_text(index / TARGET_SAMPLE_RATE),
            "packed_x": x,
            "packed_y": y,
            "packed_z": z,
            "packed_turn": turn,
            "x_cm": float_text(x * POSITION_SCALE),
            "y_cm": float_text(y * POSITION_SCALE),
            "z_cm": float_text(z * POSITION_SCALE),
            "turn_units": turn * 8,
            "turn_degrees": float_text(turn * 8 * 360.0 / 65536.0),
        })
    if len(result) != TARGET_FRAME_COUNT:
        raise TrajectoryError("decoded trajectory record count differs")
    return result


def sample_duration_endpoint(records: list[dict[str, Any]]) -> dict[str, Any]:
    duration = f32_from_bits(TARGET_DURATION_RAW)
    frame_position = duration * TARGET_SAMPLE_RATE
    left = math.floor(frame_position)
    if left >= TARGET_FRAME_COUNT - 1:
        left = TARGET_FRAME_COUNT - 1
        right = left
        factor = 0.0
    else:
        right = left + 1
        factor = frame_position - left
    packed_lanes = []
    spatial = []
    for key in ("packed_x", "packed_y", "packed_z", "packed_turn"):
        a = int(records[left][key])
        b = int(records[right][key])
        packed_lanes.append(a + (b - a) * factor)
    for value in packed_lanes[:3]:
        spatial.append(float_text(value * POSITION_SCALE))
    return {
        "duration_raw": f"0x{TARGET_DURATION_RAW:08x}",
        "duration_seconds": float_text(duration),
        "sample_frame_position": float_text(frame_position),
        "left_frame": left,
        "right_frame": right,
        "interpolation_factor": float_text(factor),
        "pre_scale_interpolated_packed_lanes": [
            float_text(value) for value in packed_lanes
        ],
        "spatial_cm_before_controller": spatial,
        "turn_quantization": (
            "0x000DEE30 passes interpolated packed_turn through 0x000DEBD0 "
            "then shifts the returned integer left by 3"
        ),
        "last_serialized_frame_reached_at_title_duration": right == left,
    }


def lane_summary(records: list[dict[str, Any]], key: str) -> dict[str, Any]:
    values = [int(row[key]) for row in records]
    return {
        "minimum": min(values),
        "maximum": max(values),
        "unique_count": len(set(values)),
    }


def write_tsv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(records[0]), dialect="excel-tab",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(records)


def validate_ghidra(trace_path: Path, pseudo_path: Path) -> None:
    trace = trace_path.read_text(encoding="utf-8")
    pseudo = pseudo_path.read_text(encoding="utf-8")
    if trace.count("\nFUNCTION 0x") != len(FUNCTION_RANGES):
        raise TrajectoryError("focused Ghidra function count differs")
    if pseudo.count("/* 0x") != len(FUNCTION_RANGES):
        raise TrajectoryError("focused pseudo-C function count differs")
    if "// PORTME: could not decompile function at" in pseudo:
        raise TrajectoryError("focused Ghidra decompilation has a hard failure")
    for line in REQUIRED_TRACE_LINES:
        if line not in trace:
            raise TrajectoryError(f"Ghidra trace lost instruction {line}")
    for portme in PORTMES[:3]:
        # The generated pseudo-C uses equivalent, shorter wording.  Requiring
        # the address/ownership tokens keeps this check robust to prose edits.
        token = "0x00318310" if "0x00318310" in portme else None
        if token is not None and token not in pseudo:
            raise TrajectoryError("focused pseudo-C lost 0x00318310")
    for token in (
        "selected dynamic one-of-seven actor record",
        "actor scale and heading/facing inputs",
        "final referee render external-root consumer",
    ):
        if token not in pseudo:
            raise TrajectoryError(f"focused pseudo-C lost boundary {token!r}")


def instruction_chain() -> list[dict[str, Any]]:
    return [
        {
            "step": 1,
            "function_va": "0x002180d0",
            "instruction_vas": ["0x00218115", "0x00218120", "0x00218125"],
            "contract": (
                "walk the gameplay referee list at 0x00E60274 through actor "
                "+0x30 and update every live record"
            ),
            "confidence": "instruction_exact",
        },
        {
            "step": 2,
            "function_va": "0x00218010",
            "instruction_vas": [
                "0x00218019", "0x0021801c", "0x00218021", "0x0021802b"
            ],
            "contract": (
                "controller = actor+0x14; call 0x0031BEB0 with actor EDX, "
                "trajectory callback 0x002CC570, event callback 0x002D6AA0, "
                "and global frame delta 0x00B71D0C"
            ),
            "confidence": "instruction_exact",
        },
        {
            "step": 3,
            "function_va": "0x002406e0",
            "instruction_vas": [
                "0x002406fd", "0x0024070a", "0x0024070c", "0x00240717",
                "0x00240722", "0x00240727", "0x00240738", "0x0024073c"
            ],
            "contract": (
                "install the acquired referee motion root with push sequence "
                "[1,0,1,1,1.0f,0,0], actor in ECX, and root in EDX"
            ),
            "confidence": "instruction_exact",
        },
        {
            "step": 4,
            "function_va": "0x0031b2e0",
            "instruction_vas": [
                "0x0031b379", "0x0031b391", "0x0031b396", "0x0031b3c2",
                "0x0031b498", "0x0031b49e"
            ],
            "contract": (
                "sample D(t0,t1) from controller+0x74, rotate X/Z by "
                "controller sine/cosine at +0x2C/+0x30, then invoke the "
                "supplied callback with actor ECX and D EDX"
            ),
            "xz_rotation": {
                "x_prime": "x*cos + z*sin",
                "z_prime": "z*cos - x*sin",
                "sine_field": "controller+0x2c",
                "cosine_field": "controller+0x30",
            },
            "confidence": "instruction_exact",
        },
        {
            "step": 5,
            "function_va": "0x002cc570",
            "instruction_vas": [
                "0x002cc57a", "0x002cc57d", "0x002cc582", "0x002cc5af",
                "0x002cc5c7", "0x002cc5ca", "0x002cc5d1", "0x002cc5dc",
                "0x002cc5e1", "0x002cc5fa"
            ],
            "contract": (
                "multiply D.X/Y/Z by actor+0x08, mutate the scaled delta via "
                "state at (actor+0x18)+0x84, accumulate X/Z, assign absolute "
                "Y, set homogeneous W=1, and update the 16-bit heading"
            ),
            "writes": {
                "actor_transform_pointer": "actor+0x18",
                "x": "+0x30 += transformed_x",
                "y": "+0x34 = transformed_y",
                "z": "+0x38 += transformed_z",
                "homogeneous_w": "+0x3c = 1.0f",
                "heading": (
                    "+0x50 = low16(old + state_yaw_delta + trajectory_turn)"
                ),
            },
            "confidence": "instruction_exact",
        },
        {
            "step": 6,
            "function_va": "0x00318310",
            "instruction_vas": [
                "0x00318310", "0x0031831e", "0x0031832e", "0x0031833a",
                "0x003183bd", "0x00318405", "0x0031841b"
            ],
            "contract": (
                "consume and mutate live transform state: mix X/Z with delta "
                "time, advance a shaped vertical state, replace Y, and return "
                "a quantized yaw correction"
            ),
            "confidence": "instruction_exact_layout_semantics_partial_names",
        },
        {
            "step": 7,
            "function_va": "0x002cc570",
            "instruction_vas": [
                "0x002cc5fd", "0x002cc602", "0x002cc60f", "0x002cc617"
            ],
            "contract": (
                "when the state yaw correction is nonzero, add it to "
                "controller+0x28 and recompute +0x2C/+0x30 sine/cosine"
            ),
            "confidence": "instruction_exact",
        },
    ]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--index", type=Path,
        default=Path("extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"),
    )
    result.add_argument(
        "--inventory", type=Path,
        default=Path("reports/assets/nfl2k5_motion_inventory.json"),
    )
    result.add_argument(
        "--ownership", type=Path,
        default=Path("reports/assets/nfl_ref_clip_ownership.json"),
    )
    result.add_argument(
        "--axis-report", type=Path,
        default=Path("reports/assets/nfl_axis_root_motion.json"),
    )
    result.add_argument(
        "--xbe", type=Path,
        default=Path("extracted/ESPN NFL 2K5 (USA)/default.xbe"),
    )
    result.add_argument(
        "--xbe-header", type=Path,
        default=Path("reports/headers/nfl2k5_xbe_header.json"),
    )
    result.add_argument(
        "--ghidra-trace", type=Path,
        default=Path(
            "reports/assets/nfl_referee_root_trajectory_ghidra/"
            "nfl_referee_root_trajectory_trace.txt"
        ),
    )
    result.add_argument(
        "--ghidra-pseudo", type=Path,
        default=Path(
            "reports/assets/nfl_referee_root_trajectory_ghidra/"
            "nfl_referee_root_trajectory_focused_pseudo_c.c"
        ),
    )
    result.add_argument(
        "--ghidra-script", type=Path,
        default=Path("tools/ghidra_scripts/NflRefereeRootTrajectoryTrace.java"),
    )
    result.add_argument("--json", type=Path, required=True)
    result.add_argument("--samples-tsv", type=Path, required=True)
    return result


def main(argv: Iterable[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        inventory = load_json(args.inventory, EXPECTED_INVENTORY_SCHEMA)
        ownership = load_json(args.ownership, EXPECTED_OWNERSHIP_SCHEMA)
        axis = load_json(args.axis_report, EXPECTED_AXIS_SCHEMA)
        validate_upstream(ownership, axis)
        resource = selected_resource(inventory)
        body, payload = extract_trajectory(args.index, resource)
        records = decode_records(payload)
        validate_ghidra(args.ghidra_trace, args.ghidra_pseudo)
        write_tsv(args.samples_tsv, records)

        packed_keys = ("packed_x", "packed_y", "packed_z", "packed_turn")
        report = {
            "schema": SCHEMA,
            "sources": {
                "generator": labeled_pin(
                    Path("tools/nfl_referee_root_trajectory.py"), Path(__file__)
                ),
                "archive_index": source_pin(args.index),
                "motion_inventory": source_pin(args.inventory),
                "ownership_report": source_pin(args.ownership),
                "axis_report": source_pin(args.axis_report),
                "ghidra_trace": source_pin(args.ghidra_trace),
                "ghidra_pseudo_c": source_pin(args.ghidra_pseudo),
                "ghidra_script": source_pin(args.ghidra_script),
            },
            "executable": executable_evidence(args.xbe, args.xbe_header),
            "selected_clip": {
                "name": TARGET_NAME,
                "outer_index": TARGET_OUTER_INDEX,
                "outer_id": TARGET_OUTER_ID,
                "chunk_index": TARGET_CHUNK_INDEX,
                "chunk_offset": TARGET_CHUNK_OFFSET,
                "body_size": len(body),
                "body_sha256": sha256(body),
                "frame_count": TARGET_FRAME_COUNT,
                "sample_rate_hz": TARGET_SAMPLE_RATE,
                "flags": TARGET_FLAGS,
                "looping": bool(TARGET_FLAGS & 1),
                "mirrored": bool(TARGET_FLAGS & 4),
            },
            "serialized_trajectory": {
                "body_offset": TARGET_TRAJECTORY_OFFSET,
                "size": len(payload),
                "sha256": sha256(payload),
                "record_stride": 8,
                "record_count": len(records),
                "layout": "little-endian signed short X,Y,Z,turn",
                "position_scale_cm_per_short": POSITION_SCALE,
                "turn_units_per_short": 8,
                "turn_units_per_revolution": 65536,
                "samples_tsv": labeled_pin(
                    CANONICAL_SAMPLES_PATH, args.samples_tsv
                ),
                "first_record": records[0],
                "last_serialized_record": records[-1],
                "packed_lane_summary": {
                    key.removeprefix("packed_"): lane_summary(records, key)
                    for key in packed_keys
                },
                "title_duration_endpoint": sample_duration_endpoint(records),
            },
            "gameplay_instruction_chain": instruction_chain(),
            "proved_contract": {
                "interval": (
                    "D(t0,t1)=[X1-X0,Y1,Z1-Z0,t1-t0,turn1-turn0]; "
                    "mirror negates X and turn"
                ),
                "controller_rotation": (
                    "X'=X*cos+Z*sin; Z'=Z*cos-X*sin; Y/dt/turn unchanged"
                ),
                "actor_scale": "multiply rotated X, absolute Y, and Z by actor+0x08",
                "live_state": (
                    "0x00318310 at (actor+0x18)+0x84 mutates X/Y/Z and "
                    "returns an additional yaw correction"
                ),
                "actor_write": (
                    "X/Z accumulate, Y is assigned absolute, W becomes 1, "
                    "and heading is reduced modulo 16 bits"
                ),
                "coordinate_basis": (
                    "right-handed Y-up centimeters; X lateral, Y vertical, "
                    "Z longitudinal; glTF translation scale would be 0.01"
                ),
            },
            "confidence_boundary": {
                "proved": [
                    "the exact selected clip's 46 serialized trajectory records",
                    "the gameplay referee pool update reaches controller 0x0031BEB0",
                    "controller+0x74 is sampled over an interval and heading-rotated",
                    "callback 0x002CC570 scales and applies the result to actor+0x18",
                    "live transform state at +0x84 changes the result before actor writes",
                ],
                "unproved": [
                    "which concrete one of seven referee actors receives selector row 4",
                    "that actor's live scale, heading, and +0x84 state for a concrete play",
                    "the final actor+0x18 to renderer external-root ownership edge",
                    "loop-boundary root accumulation for other looping referee clips",
                ],
                "gltf_root_translation_emitted": False,
                "decision": (
                    "do not export raw serialized X/Y/Z as glTF root translation; "
                    "doing so would omit proved controller and live-actor transforms"
                ),
            },
            "worked": [
                "decoded and tabulated all 46 selected trajectory records",
                "hashed 17 complete executable function bodies",
                "joined the referee pool update, controller interval, callback, and actor writes",
                "proved why raw trajectory bytes are insufficient for gameplay-equivalent export",
            ],
            "failed": [
                "no static edge selects a concrete actor record from the seven-entry pool",
                "no current trace joins actor+0x18 to the final rendered referee root",
                "live transform-state values are runtime data, not recoverable from this clip alone",
            ],
            "portme": PORTMES,
        }
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (
        OSError, KeyError, IndexError, TypeError, ValueError,
        json.JSONDecodeError, struct.error, nfl_outer.FormatError,
    ) as exc:
        print(f"nfl_referee_root_trajectory: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL_REFEREE_ROOT_TRAJECTORY_COMPLETE "
        f"records={len(records)} functions={len(FUNCTION_RANGES)} "
        "gltf_root_translation_emitted=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

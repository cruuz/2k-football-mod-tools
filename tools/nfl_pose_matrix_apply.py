#!/usr/bin/env python3
"""Consolidate NFL 2K5 sampled-pose-to-current-matrix evidence.

This is an evidence generator, not an animation exporter.  It pins the XBE,
the focused function ledger rows, the two signed channel maps, the established
SCNE bone join, and the rest/current-matrix contract.  A deterministic
non-commuting matrix witness checks the recovered row-vector multiplication
order. This pass retains numbered lanes; the independent axis/root report now
supplies their right-handed centimeter XYZ semantics.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import struct
from pathlib import Path
from typing import Iterable, Sequence

from nfl_rest_orientation import (
    f32,
    identity_matrix,
    matrix_max_error,
    matrix_multiply_f32,
    quaternion_from_axis_angle,
    quaternion_to_row_matrix,
    translated_matrix,
    xbe_reader,
)


SCHEMA = "nfl2k5_pose_matrix_apply/v2"
EXPECTED_XBE_MD5 = "444064a9ec984dd29d2c05a43f5c96e8"

# End addresses are exclusive.  These are contiguous byte pins; Ghidra's
# recovered 0x0012f670 body omits its switch arms, so the raw-range pin is
# intentionally separate below.
FUNCTION_RANGES = (
    ("render_object_dispatch", 0x00021860, 0x000218C3),
    ("skin_palette_builder", 0x00022C00, 0x00022ECA),
    ("hierarchy_expander", 0x000233C0, 0x00023495),
    ("render_shape", 0x000243D0, 0x00024978),
    ("secondary_player_shape_lookup", 0x0002EB70, 0x0002EB7E),
    ("matrix_multiply", 0x00031110, 0x0003121C),
    ("scale_matrix_basis", 0x0008E350, 0x0008E3AB),
    ("player_twist_callback", 0x000901E0, 0x00090247),
    ("player_twist_dispatch", 0x00091890, 0x000918AA),
    ("player_root_basis_scale", 0x000918D0, 0x000918FC),
    ("player_pose_postprocess", 0x00092140, 0x000937F6),
    ("player_hierarchy_builder", 0x00093800, 0x00093849),
    ("player_current_matrix_postprocess", 0x00093850, 0x00093B39),
    ("coach_twist_callback", 0x00095B40, 0x00095BA9),
    ("coach_twist_dispatch", 0x00095FB0, 0x00096007),
    ("coach_hierarchy_builder", 0x00096050, 0x0009608B),
    ("referee_twist_callback", 0x00096590, 0x000965F9),
    ("referee_twist_dispatch", 0x00096A80, 0x00096ACC),
    ("referee_hierarchy_builder", 0x00096B20, 0x00096B4E),
    ("trajectory_sample", 0x000DEE30, 0x000DF030),
    ("trajectory_lane1_sample", 0x000DF2F0, 0x000DF3CB),
    ("trajectory_difference", 0x000DF3D0, 0x000DF444),
    ("packed_pose_sampler", 0x000DF700, 0x000DF8A5),
    ("cutscene_pose_builder", 0x0012F670, 0x0012F9F2),
    ("cutscene_descriptor_constructor", 0x00130150, 0x00130E9A),
    ("selected_ancestry_rotation_query", 0x002176D0, 0x00217793),
    ("selected_ancestry_position_query", 0x002177A0, 0x002178D3),
    ("selected_ancestry_matrix_query", 0x002178E0, 0x00217A4F),
    ("generic_full_pose_builder", 0x0028B140, 0x0028B24E),
    ("direct_player_vertical_builder", 0x00343220, 0x003432FE),
    ("direct_player_trajectory_builder", 0x0035B520, 0x0035B651),
    ("quaternion_multiply", 0x003CA150, 0x003CA1DC),
    ("quaternion_interpolate", 0x003CA270, 0x003CA3CF),
    ("quaternion_array_to_matrix", 0x003CA3D0, 0x003CA4D2),
)

RAW_RANGES = (
    ("cutscene_builder_including_switch_tables", 0x0012F670, 0x0012FA1C),
    ("cutscene_descriptor_constructor_all_bytes", 0x00130150, 0x00130E9A),
    ("generic_full_pose_builder_all_bytes", 0x0028B140, 0x0028B24E),
    ("direct_player_vertical_builder_all_bytes", 0x00343220, 0x003432FE),
    ("direct_player_trajectory_builder_all_bytes", 0x0035B520, 0x0035B651),
)

EXPECTED_JUMP_TABLES = {
    "sample_dispatch": (
        0x0012F9F4,
        [0x0012F877, 0x0012F7C5, 0x0012F7EF, 0x0012F81D, 0x0012F84B],
    ),
    "apply_dispatch": (
        0x0012FA08,
        [0x0012F9BF, 0x0012F937, 0x0012F970, 0x0012F99D, 0x0012F9AF],
    ),
}

EXPECTED_SCHEMAS = {
    "channel_maps": "nfl2k5_motion_channel_maps/v1",
    "bone_binding": "nfl2k5_bone_binding/v1",
    "rest_orientation": "nfl2k5_rest_orientation/v1",
    "motion_sampler": "nfl2k5_motion_sampler_inventory/v1",
}

PORTMES = [
    "// PORTME: recover 0x0012F670 switch arms as structured C; the raw trace preserves every instruction.",
    "// PORTME: semantically recover and port every player-proportion adjustment in 0x00092140 and 0x00093850.",
    "// PORTME: model the inactive-coach guard without introducing portable-C uninitialized reads.",
    "// PORTME: prove which runtime object families exercise the direct full-pose builders during football gameplay.",
    "// PORTME: apply the proved XYZ/centimeter contract while preserving each builder's external-root and loop ownership.",
    "// PORTME: do not export player animation until 0x00092140/0x00093850 are value-equivalently ported; coach/referee local rotation export remains separately eligible.",
]


class PoseMatrixError(ValueError):
    """A pinned input or recovered invariant failed."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PoseMatrixError(f"{path}: expected JSON object")
    return value


def executable_evidence(
    xbe_path: Path, header_path: Path, ledger_path: Path,
) -> tuple[dict[str, object], callable]:
    xbe = xbe_path.read_bytes()
    md5 = hashlib.md5(xbe).hexdigest()
    if md5 != EXPECTED_XBE_MD5:
        raise PoseMatrixError(f"unexpected NFL 2K5 XBE MD5 {md5}")
    header = load_json(header_path)
    read = xbe_reader(xbe, header)

    with ledger_path.open(encoding="utf-8", newline="") as stream:
        ledger = {
            row["address"].lower(): row
            for row in csv.DictReader(stream, dialect="excel-tab")
        }

    functions = []
    for name, start, end in FUNCTION_RANGES:
        key = f"0x{start:08x}"
        if key not in ledger:
            raise PoseMatrixError(f"function ledger is missing {key}")
        row = ledger[key]
        if row["decompile_status"] != "success":
            raise PoseMatrixError(f"{key}: ledger decompile is not successful")
        body = read(start, end - start)
        functions.append(
            {
                "name": name,
                "start": key,
                "end_exclusive": f"0x{end:08x}",
                "size": len(body),
                "sha256": sha256(body),
                "ledger_end_inclusive": row["end"].lower(),
                "ledger_body_ranges": row["body_ranges"].lower(),
                "ledger_callers": row["callers"],
                "ledger_callees": row["callees"],
            }
        )

    raw_ranges = []
    for name, start, end in RAW_RANGES:
        body = read(start, end - start)
        raw_ranges.append(
            {
                "name": name,
                "start": f"0x{start:08x}",
                "end_exclusive": f"0x{end:08x}",
                "size": len(body),
                "sha256": sha256(body),
            }
        )

    jump_tables = {}
    for name, (va, expected) in EXPECTED_JUMP_TABLES.items():
        raw = read(va, len(expected) * 4)
        values = list(struct.unpack("<" + "I" * len(expected), raw))
        if values != expected:
            raise PoseMatrixError(
                f"{name}: jump table {values!r} does not match {expected!r}"
            )
        jump_tables[name] = {
            "va": f"0x{va:08x}",
            "raw_hex": raw.hex(),
            "targets": [f"0x{value:08x}" for value in values],
        }

    constants = {}
    for name, va in {
        "player_basis_scale_per_byte": 0x004EFDFC,
        "special_player_lane1_origin": 0x004E5CAC,
    }.items():
        raw = read(va, 4)
        constants[name] = {
            "va": f"0x{va:08x}",
            "bits": f"0x{struct.unpack('<I', raw)[0]:08x}",
            "value": struct.unpack("<f", raw)[0],
        }
    if constants["special_player_lane1_origin"]["value"] != 100.0:
        raise PoseMatrixError("unexpected direct-player lane-1 origin")

    return (
        {
            "path": str(xbe_path),
            "size": len(xbe),
            "md5": md5,
            "sha256": sha256(xbe),
            "header_sha256": sha256_file(header_path),
            "ledger_sha256": sha256_file(ledger_path),
            "function_ranges": functions,
            "raw_ranges": raw_ranges,
            "jump_tables": jump_tables,
            "constants": constants,
        },
        read,
    )


def verify_sources(
    channel_maps_path: Path,
    bone_binding_path: Path,
    rest_orientation_path: Path,
    motion_sampler_path: Path,
) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    paths = {
        "channel_maps": channel_maps_path,
        "bone_binding": bone_binding_path,
        "rest_orientation": rest_orientation_path,
        "motion_sampler": motion_sampler_path,
    }
    values = {name: load_json(path) for name, path in paths.items()}
    for name, expected in EXPECTED_SCHEMAS.items():
        if values[name].get("schema") != expected:
            raise PoseMatrixError(
                f"{paths[name]}: schema {values[name].get('schema')!r}, expected {expected!r}"
            )
    for name in ("channel_maps", "bone_binding"):
        if values[name].get("executable_md5") != EXPECTED_XBE_MD5:
            raise PoseMatrixError(f"{paths[name]}: executable MD5 mismatch")
    if values["rest_orientation"]["executable"]["md5"] != EXPECTED_XBE_MD5:
        raise PoseMatrixError("rest-orientation executable MD5 mismatch")

    maps = values["channel_maps"]["maps"]
    if [(item["va"], item["enabled_channel_count"], item["disabled_logical_channels"])
            for item in maps] != [
        ("0x0051cd70", 23, [16, 21]),
        ("0x0051d010", 21, [15, 17, 21, 23]),
    ]:
        raise PoseMatrixError("installed channel-map contract changed")
    families = values["bone_binding"]["skeleton_families"]
    if len(families) != 2 or any(len(item["bindings"]) != 25 for item in families):
        raise PoseMatrixError("bone-binding family contract changed")
    if values["rest_orientation"]["quaternions"]["component_order"] != (
        "scalar-first [w,x,y,z]"
    ):
        raise PoseMatrixError("quaternion layout changed")
    if values["rest_orientation"]["proved_contract"]["row_vector_skin_equation"] != (
        "skin = T(-absolute_bind_translation) * current"
    ):
        raise PoseMatrixError("skin/current matrix contract changed")

    source_evidence = {
        name: {
            "path": str(path),
            "schema": values[name]["schema"],
            "sha256": sha256_file(path),
        }
        for name, path in paths.items()
    }
    return (
        values["channel_maps"],
        values["bone_binding"],
        values["rest_orientation"],
        values["motion_sampler"],
        source_evidence,
    )


def channel_source(
    target_family: str, channel: int, enabled: bool,
) -> tuple[str, str]:
    if target_family == "player":
        special = {
            16: (
                "callback_synthesized",
                "0x000901e0 writes the full signed twist extracted from sampled lhand channel 17",
            ),
            17: (
                "sampled_then_callback_adjusted",
                "0x000901e0 replaces lhand with conjugate(channel 16) * sampled lhand",
            ),
            21: (
                "callback_synthesized",
                "0x000901e0 writes the full signed twist extracted from sampled rhand channel 22",
            ),
            22: (
                "sampled_then_callback_adjusted",
                "0x000901e0 replaces rhand with conjugate(channel 21) * sampled rhand",
            ),
        }
    else:
        callback = "0x00095b40" if target_family == "coach" else "0x00096590"
        dispatch = "0x00095fb0" if target_family == "coach" else "0x00096a80"
        guard = (
            "when coach-active global 0x00b65fa0 is nonzero; "
            if target_family == "coach" else ""
        )
        special = {
            14: (
                "sampled_then_callback_adjusted",
                f"{guard}{callback} replaces lhumerus with sampled lhumerus * conjugate(channel 15)",
            ),
            15: (
                "callback_synthesized",
                f"{guard}{callback} writes a half-twist extracted from sampled lhumerus channel 14",
            ),
            17: (
                "callback_identity",
                f"{guard}{dispatch} writes scalar-first identity [1,0,0,0] to lwrist",
            ),
            20: (
                "sampled_then_callback_adjusted",
                f"{guard}{callback} replaces rhumerus with sampled rhumerus * conjugate(channel 21)",
            ),
            21: (
                "callback_synthesized",
                f"{guard}{callback} writes a half-twist extracted from sampled rhumerus channel 20",
            ),
            23: (
                "callback_identity",
                f"{guard}{dispatch} writes scalar-first identity [1,0,0,0] to rwrist",
            ),
        }
    if channel in special:
        return special[channel]
    if not enabled:
        raise PoseMatrixError(
            f"{target_family} channel {channel}: disabled channel has no synthesis rule"
        )
    return "sampled", "0x000df700 writes the mapped packed/interpolated quaternion"


def channel_rows(bone_binding: dict[str, object]) -> list[dict[str, object]]:
    by_map = {
        family["bindings"][0]["map_va"]: family["bindings"]
        for family in bone_binding["skeleton_families"]
    }
    if set(by_map) != {"0x0051cd70", "0x0051d010"}:
        raise PoseMatrixError("unexpected bone-binding maps")

    rows: list[dict[str, object]] = []
    for descriptor_type, target_family, map_va in (
        (2, "player", "0x0051cd70"),
        (3, "coach", "0x0051d010"),
        (4, "referee", "0x0051d010"),
    ):
        for binding in by_map[map_va]:
            channel = int(binding["logical_channel"])
            source, detail = channel_source(
                target_family, channel, bool(binding["enabled"])
            )
            rows.append(
                {
                    "descriptor_type": descriptor_type,
                    "target_family": target_family,
                    "logical_channel": channel,
                    "matrix_index_before_player_postprocess": int(
                        binding["transform_index"]
                    ),
                    "bone_name": binding["bone_name"],
                    "parent_channel": int(binding["parent_channel"]),
                    "parent_bone_name": binding["parent_bone_name"] or "",
                    "map_va": map_va,
                    "enabled_in_signed_map": bool(binding["enabled"]),
                    "normal_packed_index": int(binding["normal_packed_index"]),
                    "mirrored_packed_index": int(binding["mirrored_packed_index"]),
                    "final_quaternion_source": source,
                    "source_detail": detail,
                }
            )
    if len(rows) != 75:
        raise PoseMatrixError(f"expected 75 named channel rows, got {len(rows)}")
    return rows


def matrix_values(matrix: Sequence[float]) -> dict[str, object]:
    return {
        f"m{row}{column}": format(float(matrix[row * 4 + column]), ".9g")
        for row in range(4)
        for column in range(4)
    }


def add_local_translation(matrix: Sequence[float], value: Sequence[float]) -> list[float]:
    result = list(matrix)
    result[12] = f32(result[12] + value[0])
    result[13] = f32(result[13] + value[1])
    result[14] = f32(result[14] + value[2])
    return result


def matrix_witness() -> tuple[dict[str, object], list[dict[str, object]]]:
    trajectory = translated_matrix(7.0, -3.0, 5.0)
    descriptor_root = quaternion_to_row_matrix(
        quaternion_from_axis_angle((2.0, -1.0, 3.0), math.radians(31.0))
    )
    descriptor_root[12:15] = [11.0, 13.0, -17.0]
    controller_root = quaternion_to_row_matrix(
        quaternion_from_axis_angle((-3.0, 4.0, 1.0), math.radians(-43.0))
    )
    controller_root[12:15] = [-19.0, 23.0, 29.0]
    external_root = matrix_multiply_f32(
        matrix_multiply_f32(trajectory, descriptor_root), controller_root
    )

    root_local = add_local_translation(
        quaternion_to_row_matrix(
            quaternion_from_axis_angle((1.0, 5.0, -2.0), math.radians(37.0))
        ),
        (3.0, -2.0, 1.0),
    )
    child_local = add_local_translation(
        quaternion_to_row_matrix(
            quaternion_from_axis_angle((-2.0, 1.0, 4.0), math.radians(-29.0))
        ),
        (0.5, 4.0, -1.0),
    )
    root_current = matrix_multiply_f32(root_local, external_root)
    child_current = matrix_multiply_f32(child_local, root_current)

    wrong_external = matrix_multiply_f32(
        matrix_multiply_f32(controller_root, descriptor_root), trajectory
    )
    wrong_root = matrix_multiply_f32(external_root, root_local)
    wrong_child = matrix_multiply_f32(root_current, child_local)
    errors = {
        "external_reversed_order_error": matrix_max_error(external_root, wrong_external),
        "root_parent_left_error": matrix_max_error(root_current, wrong_root),
        "child_parent_left_error": matrix_max_error(child_current, wrong_child),
    }
    if min(errors.values()) <= 1.0e-3:
        raise PoseMatrixError(f"non-commuting matrix witness was degenerate: {errors}")

    stages = (
        ("trajectory_translation", trajectory),
        ("descriptor_root", descriptor_root),
        ("controller_root", controller_root),
        ("external_root", external_root),
        ("root_local_after_bind_translation", root_local),
        ("root_current", root_current),
        ("child_local_after_bind_translation", child_local),
        ("child_current", child_current),
    )
    rows = []
    for stage, matrix in stages:
        row = {"stage": stage}
        row.update(matrix_values(matrix))
        rows.append(row)
    return (
        {
            "equations": [
                "external_root = T(trajectory_lanes_0_1_2) * descriptor_root * controller_root",
                "local[i] = M(sampled_or_callback_quaternion[i]); local[i].m12_m13_m14 += transform[+0x50].xyz",
                "current[i] = local[i] * (current[parent] or external_root)",
                "skin[i] = T(-transform[+0x40].xyz) * current[i]",
            ],
            "errors_against_reversed_orders": errors,
            "note": (
                "synthetic numbered lanes prove order only; they do not assign axis names, "
                "handedness, scale, or a glTF root policy"
            ),
        },
        rows,
    )


def write_tsv(path: Path, rows: Iterable[dict[str, object]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)


def build_report(args: argparse.Namespace) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    executable, read = executable_evidence(args.xbe, args.xbe_header, args.ledger)
    channel_maps, bone_binding, rest, motion, sources = verify_sources(
        args.channel_maps, args.bone_binding, args.rest_orientation,
        args.motion_sampler,
    )

    # Pin the actual map bytes again rather than trusting only the prior JSON.
    installed_maps = {}
    for item in channel_maps["maps"]:
        va = int(item["va"], 16)
        raw = read(va, 50)
        if raw.hex() != item["raw_hex"]:
            raise PoseMatrixError(f"{item['va']}: map bytes differ from source report")
        installed_maps[item["va"]] = {
            "raw_hex": raw.hex(),
            "sha256": sha256(raw),
            "enabled_channel_count": item["enabled_channel_count"],
            "disabled_logical_channels": item["disabled_logical_channels"],
        }

    channels = channel_rows(bone_binding)
    witness, witness_rows = matrix_witness()
    packed_domain = motion["domains"]["packed_quaternion_dwords_per_frame"]
    if max(int(value) for value in packed_domain) != 31:
        raise PoseMatrixError("generic packed-channel maximum changed")

    report = {
        "schema": SCHEMA,
        "executable": executable,
        "source_evidence": sources,
        "cutscene_descriptor": {
            "controller_function": "0x0012f670",
            "constructor": "0x00130150 loads SCNE name 'cutscene' and emits 0x28-byte records",
            "controller_fields": {
                "+0x10": "inline controller row-vector root matrix",
                "+0xdc": "cutscene SCNE pointer",
                "+0xe0": "current sample time",
                "+0xec": "descriptor count",
                "+0xf0": "descriptor-array pointer",
            },
            "record_stride": 40,
            "record_fields": {
                "+0x00_u32": "dispatch type 1 generic, 2 player, 3 coach, 4 referee; zero is defensive no-op",
                "+0x04_pointer_or_index": "generic render object; player context; coach/referee slot index",
                "+0x08": "not consumed by 0x0012f670",
                "+0x0c_pointer": "SMCD motion root",
                "+0x10_pointer": "descriptor root matrix",
                "+0x14_pointer": "local/current matrix array; generic constructor stores target +0x14, named-family constructors store allocation +0x40",
                "+0x18_pointer": "owning allocation for named-family descriptors; not consumed by update",
                "+0x1c": "sidecar subtype used outside matrix update",
                "+0x20": "sidecar pointer used outside matrix update",
                "+0x24": "sidecar flag used outside matrix update",
            },
            "types": [
                {"type": 0, "name": "no_op", "channel_count": 0, "apply": "none"},
                {"type": 1, "name": "generic", "channel_count": "motion +0x00 byte, observed maximum 31", "map": "null/default identity", "apply": "in-place 0x000233c0 through render object +0x14"},
                {"type": 2, "name": "player", "channel_count": 25, "map": "0x0051cd70", "apply": "0x00093800 then 0x00093850"},
                {"type": 3, "name": "coach", "channel_count": 25, "map": "0x0051d010", "apply": "0x00096050"},
                {"type": 4, "name": "referee", "channel_count": 25, "map": "0x0051d010", "apply": "0x00096b20"},
            ],
        },
        "installed_channel_maps": installed_maps,
        "channel_matrix_contract": {
            "named_row_count": len(channels),
            "per_family_channel_count": 25,
            "logical_slot_equals_pre_postprocess_matrix_index": True,
            "sampler_output_stride": 16,
            "matrix_output_stride": 64,
            "quaternion_layout": "scalar-first [w,x,y,z]",
            "conversion": "0x003ca3d0 writes one row-major affine 4x4 per final logical quaternion",
            "disabled_channel_rule": (
                "0x000df700 skips negative map entries but advances its 0x10-byte output slot; "
                "the immediately following family callback deterministically fills every skipped slot before 0x003ca3d0 for active targets"
            ),
            "inactive_coach_boundary": (
                "if global 0x00b65fa0 is zero, 0x00095fb0 skips the four coach fills and "
                "0x00096050 later skips hierarchy application; the original still reaches "
                "0x003ca3d0, so a portable port must avoid turning discarded stack slots into C undefined behavior"
            ),
            "player_postprocess_boundary": (
                "0x00092140 can alter/copy local player matrices before hierarchy, and "
                "0x00093850 alters selected current player matrices afterward; indices remain the proved named order but value-equivalent reimplementation is PORTME"
            ),
        },
        "translation_contract": {
            "joint_translation": (
                "there is no sampled per-joint translation curve in this path; 0x000233c0 adds serialized transform +0x50.xyz to m12,m13,m14 of every quaternion-derived local matrix"
            ),
            "trajectory_difference_0x000df3d0": {
                "lane_0": "sample(current).lane0 - sample(start).lane0; mirror flag negates it",
                "lane_1": "sample(current).lane1, intentionally not differenced",
                "lane_2": "sample(current).lane2 - sample(start).lane2",
                "lane_3": "current_time - start_time",
                "lane_4": "yaw-like integer difference; mirror flag negates it",
            },
            "cutscene_use": (
                "0x0012f670 calls 0x000df3d0 with start=0, consumes only lanes 0..2 as T(lanes), and ignores lane4 in this matrix path"
            ),
            "direct_player_full_use": (
                "0x0035b520 calls 0x000df3d0 with start=0, subtracts 100 from lane1, and adds either all lanes 0..2 or only lane1 to the root channel local matrix before hierarchy"
            ),
            "direct_player_vertical_use": (
                "0x00343220 samples only trajectory lane1 through 0x000df2f0, subtracts 100, and places it in the external-root translation"
            ),
            "generic_use": (
                "0x0028b140 adds 0x000df3d0 lanes 0..2 to the first local matrix, uses a separately stored external root, and ignores lane4 in this path"
            ),
        },
        "multiplication_contract": {
            "quaternion_matrix": "0x003ca3d0 scalar-first row-vector matrix",
            "cutscene_external_root": "T(trajectory lanes 0..2) * descriptor[+0x10] * controller[+0x10]",
            "hierarchy": "current[i] = local[i] * (current[parent] or external_root)",
            "skin_palette": "T(-transform[+0x40].xyz) * current[i]",
            "matrix_witness": witness,
        },
        "player_specific_stages": {
            "0x000918d0": "scales only root local matrix 3x3 by player[+0x2b] * 0.012927484698593616 on direct player paths",
            "0x00092140": (
                "called before both player hierarchy expansions; copies/remaps 25 local matrices into a secondary array and performs extensive player morphology/equipment adjustments"
            ),
            "0x00093800": (
                "runs 0x00092140, expands the secondary array at local+0x640, then expands the primary array in place with the same external root"
            ),
            "0x00093850": (
                "post-hierarchy per-channel body-proportion scaling and pivot adjustments; full 0x01ffffff mask at the traced builders"
            ),
        },
        "query_helper_boundary": {
            "0x002176d0": "selected-channel ancestry quaternion query; samples all 25 but returns one composed quaternion and never writes a matrix array",
            "0x002177a0": "selected-channel ancestry position query; not the full skeleton writer",
            "0x002178e0": "selected-channel affine query; calls 0x003ca3d0 for one result and never calls 0x000233c0",
            "conclusion": "the full pose writers call 0x000df700 and 0x003ca3d0 directly; 0x002176d0 is corroborating channel/parent evidence, not the animation application loop",
        },
        "renderer_boundary": {
            "current_matrix_storage": "render object +0x14 for generic targets; family builders use setup-linked player/coach/referee current arrays",
            "render_dispatch": "0x00021860 -> 0x000243d0 -> 0x00022c00",
            "palette_equation": rest["proved_contract"]["row_vector_skin_equation"],
            "current_space": rest["proved_contract"]["current_matrix_space"],
        },
        "worked": [
            "recovered both 0x0012f670 five-way switch tables, including Ghidra-omitted arms",
            "proved descriptor types, field aliases, quaternion/matrix strides, and named channel indices",
            "proved deterministic initialization of all negative-map slots on active player/coach/referee targets",
            "proved cutscene, generic, and two direct-player root/trajectory placements without merging their orders",
            "connected quaternion matrices through local translation, hierarchy, and skin palette construction",
        ],
        "failed": [
            "0x00092140 and 0x00093850 are completely emitted but not yet semantically reimplemented helper-by-helper",
            "the inactive-coach path converts discarded skipped slots; portable-C initialization policy remains explicit PORTME",
            "the direct full-pose caller object classes are not named from runtime instrumentation",
            "this pass retains numbered lanes; the independent axis/root trace proves right-handed centimeter XYZ and the glTF 0.01-meter conversion",
            "no animation was exported from this evidence-only pass",
        ],
        "portme": PORTMES,
    }
    return report, channels, witness_rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xbe", type=Path, default=Path("extracted/ESPN NFL 2K5 (USA)/default.xbe"))
    parser.add_argument("--xbe-header", type=Path, default=Path("reports/headers/nfl2k5_xbe_header.json"))
    parser.add_argument("--ledger", type=Path, default=Path("research/functions/nfl2k5/functions.tsv"))
    parser.add_argument("--channel-maps", type=Path, default=Path("reports/assets/nfl_motion_channel_maps.json"))
    parser.add_argument("--bone-binding", type=Path, default=Path("reports/assets/nfl_bone_binding.json"))
    parser.add_argument("--rest-orientation", type=Path, default=Path("reports/assets/nfl_rest_orientation.json"))
    parser.add_argument("--motion-sampler", type=Path, default=Path("reports/assets/nfl_motion_sampler_inventory.json"))
    parser.add_argument("--json", type=Path, default=Path("reports/assets/nfl_pose_matrix_apply.json"))
    parser.add_argument("--channels-tsv", type=Path, default=Path("reports/assets/nfl_pose_matrix_apply_channels.tsv"))
    parser.add_argument("--witness-tsv", type=Path, default=Path("reports/assets/nfl_pose_matrix_apply_matrix_witness.tsv"))
    args = parser.parse_args()

    report, channels, witness_rows = build_report(args)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_tsv(args.channels_tsv, channels, tuple(channels[0]))
    write_tsv(args.witness_tsv, witness_rows, tuple(witness_rows[0]))
    print(
        "NFL_POSE_MATRIX_APPLY_REPORT_COMPLETE "
        f"functions={len(FUNCTION_RANGES)} channels={len(channels)} "
        f"witness_matrices={len(witness_rows)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

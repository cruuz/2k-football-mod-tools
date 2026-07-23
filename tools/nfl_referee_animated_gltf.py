#!/usr/bin/env python3
"""Bake a proved NFL referee local-pose path into a standard animated glTF witness."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
from pathlib import Path
import struct
from typing import Any

import nfl_outer
from nfl_rest_orientation import quaternion_to_row_matrix


SCHEMA = "nfl2k5_referee_animated_gltf/v1"
DEFAULT_CLIP = "ANM_REF_PENALTY_DELAY_OF_GAME_R"
EXPECTED_INVENTORY_SCHEMA = "nfl2k5_motion_inventory/v1"
EXPECTED_METER_SCHEMA = "nfl2k5_meter_skin_gltf_manifest/v1"
EXPECTED_OWNERSHIP_SCHEMA = "nfl2k5_ref_clip_ownership/v1"
EXPECTED_ROOT_TRAJECTORY_SCHEMA = "nfl2k5_referee_root_trajectory/v1"
EXPECTED_RENDER_ROOT_SCHEMA = "nfl2k5_referee_render_root/v1"
CHANNELS = 25
BAKE_RATE = 120
MAXIMUM_OBSERVED_GRID_ERROR_DEGREES = 0.1
BONES = (
    "root", "lfemur", "ltibia", "lfoot", "ltoes", "rfemur",
    "rtibia", "rfoot", "rtoes", "waist", "thorax", "neck", "head",
    "lcollar", "lhumerus", "ltwist", "lelbow", "lwrist", "lhand",
    "rcollar", "rhumerus", "rtwist", "relbow", "rwrist", "rhand",
)
EXPECTED_SELECTED_CLIP = {
    "chunk_index": 27,
    "decoded_length": 4400,
    "decoded_sha256":
        "75b67ce8f338943a8cc6bdc46718f61c7c2d9c4945d186983796a090aa31363f",
    "duration_raw": "0x403ddddf",
    "duration_seconds": 2.96666694,
    "event_count": 3,
    "exact_inventory_match_count": 1,
    "flags": 2,
    "frame_count": 46,
    "name": DEFAULT_CLIP,
    "outer_id": "0xda37aa9d",
    "outer_index": 3107,
    "packed_quaternion_dwords_per_frame": 21,
    "quaternion_bytes": 3864,
    "sample_rate_hz": 15,
    "selector_index": 4,
    "selector_name_pointer_va": "0x00513f5c",
    "selector_name_string_va": "0x00e87fb8",
    "selector_row_va": "0x00513f58",
    "selector_side": "right",
    "slot_index": 27,
    "slot_offset": 304128,
    "slot_size": 11264,
    "trajectory_bytes": 368,
    "trajectory_stride": 8,
    "wrapper_size": 32,
}
EXPECTED_RUNTIME_OWNERSHIP = {
    "acquire_function_va": "0x001685e0",
    "action_descriptor_va": "0x00514060",
    "action_descriptor_words": [
        "0x20000000", "0x00000000", "0x00240670", "0x002405f0",
        "0x002fc250",
    ],
    "channel_map_sha256":
        "39a441532daab4cdbe4ff777641021bc179da9a5a69d43a94cdcb45fcc21e435",
    "channel_map_va": "0x0051d010",
    "confidence": "instruction_exact_referee_namespace_and_skeletal_family",
    "controller_apply_function_va": "0x002d6b70",
    "controller_transition_function_va": "0x0031c180",
    "dual_selector_function_va": "0x002408a0",
    "enabled_channel_count": 21,
    "gameplay_actor_initializer_va": "0x00217eb0",
    "gameplay_actor_pool_head_va": "0x00e60274",
    "gameplay_actor_pool_max_count": 7,
    "gameplay_actor_state_callback_va": "0x001fb250",
    "gameplay_deferred_action_va": "0x001fb0b0",
    "gameplay_play_setup_va": "0x002406e0",
    "gameplay_selector_setup_va": "0x001fb1a0",
    "hierarchy_apply_va": "0x00096b20",
    "namespace_name": "Referee",
    "namespace_string_va": "0x00e887b0",
    "prefetch_function_va": "0x001685b0",
    "referee_scene_loader_va": "0x00096600",
    "referee_scene_name": "referee",
    "referee_scene_name_va": "0x00e65dd0",
    "referee_shape_name_vas": ["0x00e65cbc", "0x00e65ccc"],
    "referee_shape_names": ["ref_low", "ref_high"],
    "selector_function_va": "0x002407d0",
    "selector_table_base_va": "0x00513f28",
    "smcd_fourcc_immediate": "0x44434d53",
    "specific_pool_record_instance_link_proved": False,
    "twist_callback_va": "0x00096a80",
    "twist_extract_function_va": "0x00096590",
}
EXPECTED_CUTSCENE_TYPE4_RELATION = {
    "channel_map_va": "0x0051d010",
    "confidence": "instruction_exact_abi_relation_instance_unproved",
    "descriptor_constructor_va": "0x00130150",
    "descriptor_type": 4,
    "descriptor_update_va": "0x0012f670",
    "hierarchy_apply_va": "0x00096b20",
    "instance_level_link_proved": False,
    "portme": (
        "// PORTME: no exact runtime edge proves this gameplay penalty clip "
        "enters a cutscene 0x28-byte type-4 descriptor instance; do not label "
        "the clip itself as a type-4 descriptor resource"
    ),
    "relation":
        "same_referee_skeletal_family_not_proved_same_descriptor_instance",
    "twist_callback_va": "0x00096a80",
}
DEFAULT_NATIVE_DEPENDENCIES = (
    Path("include/recovered/nfl2k5/motion_pose_sample.h"),
    Path("src/recovered/nfl2k5/motion_pose_sample.c"),
    Path("include/recovered/nfl2k5/packed_pose.h"),
    Path("src/recovered/nfl2k5/packed_pose.c"),
    Path("include/recovered/nfl2k5/quaternion_interpolation.h"),
    Path("src/recovered/nfl2k5/quaternion_interpolation.c"),
    Path("src/recovered/nfl2k5/quaternion_interpolation_table.inc"),
)
DEFAULT_GENERATOR_DEPENDENCIES = (
    Path("tools/nfl_referee_animated_gltf.py"),
    Path("tools/nfl_outer.py"),
    Path("tools/nfl_rest_orientation.py"),
)
PORTME = [
    "PORTME: gameplay ownership is instruction-exact for the Referee namespace and skeletal family, but the specific record in the seven-entry runtime pool is not proved.",
    "PORTME: no exact runtime edge proves this gameplay penalty clip occupies a cutscene type-4 descriptor instance; the shared skeletal ABI is not an instance link.",
    "PORTME: glTF requires unit rotation quaternions, while the original matrix helper consumes slightly non-unit interpolated output; retain the measured normalization delta.",
    "PORTME: standard glTF LINEAR rotation uses ideal slerp, not the title's fixed-table/x87 interpolation; this witness bakes exact native samples at 120 Hz and records the between-key representation error.",
    "PORTME: trajectory sampling/controller/callback and the final renderer-root edge are instruction-exact, but root translation remains omitted until the concrete one-of-seven actor initialization and live state are captured.",
    "PORTME: player postprocessors 0x00092140 and 0x00093850 are value-equivalently ported; player animation remains withheld until an exact shipped clip/controller/hierarchy-root path is joined.",
]


class AnimationError(ValueError):
    pass


class ClipView(ctypes.Structure):
    _fields_ = [
        ("packed_frames", ctypes.POINTER(ctypes.c_uint8)),
        ("packed_frame_bytes", ctypes.c_size_t),
        ("frame_count", ctypes.c_uint16),
        ("packed_poses_per_frame", ctypes.c_uint8),
        ("sample_rate", ctypes.c_uint8),
        ("time_scale", ctypes.c_float),
        ("flags", ctypes.c_uint8),
        ("duration_seconds", ctypes.c_float),
    ]


Float4 = ctypes.c_float * 4


class LocalPose(ctypes.Structure):
    _fields_ = [("scalar_first", Float4 * CHANNELS)]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def f32_bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def exact_mapping(label: str, actual: object,
                  expected: dict[str, Any]) -> None:
    if not isinstance(actual, dict):
        raise AnimationError(f"{label} is not an object")
    if actual == expected:
        return
    for key in sorted(set(actual) | set(expected)):
        if actual.get(key) != expected.get(key):
            raise AnimationError(
                f"{label}.{key} differs: {actual.get(key)!r} != "
                f"{expected.get(key)!r}"
            )
    raise AnimationError(f"{label} differs")


def file_pins(paths: list[Path] | tuple[Path, ...]) -> list[dict[str, str]]:
    return [
        {"path": str(path), "sha256": sha256_file(path)}
        for path in paths
    ]


def validate_ownership_report(
    report: object,
    clip_meta: dict[str, Any],
    index_path: Path,
    inventory_path: Path,
) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise AnimationError("ownership report is not an object")
    if report.get("schema") != EXPECTED_OWNERSHIP_SCHEMA:
        raise AnimationError("ownership report schema differs")
    exact_mapping(
        "ownership selected_clip", report.get("selected_clip"),
        EXPECTED_SELECTED_CLIP,
    )
    exact_mapping(
        "ownership runtime_ownership", report.get("runtime_ownership"),
        EXPECTED_RUNTIME_OWNERSHIP,
    )
    exact_mapping(
        "ownership cutscene_type4_relation",
        report.get("cutscene_type4_relation"),
        EXPECTED_CUTSCENE_TYPE4_RELATION,
    )
    selected = report["selected_clip"]
    comparisons = {
        "name": clip_meta["name"],
        "outer_index": clip_meta["outer_index"],
        "outer_id": clip_meta["outer_id"],
        "chunk_index": clip_meta["chunk_index"],
        "slot_offset": clip_meta["chunk_offset"],
        "decoded_length": clip_meta["decoded_length"],
        "decoded_sha256": clip_meta["body_sha256"],
        "packed_quaternion_dwords_per_frame":
            clip_meta["packed_channels"],
        "quaternion_bytes": clip_meta["packed_payload_bytes"],
        "frame_count": clip_meta["frame_count"],
        "sample_rate_hz": clip_meta["sample_rate"],
        "flags": clip_meta["flags"],
        "trajectory_bytes": clip_meta["trajectory_bytes"],
    }
    for key, expected in comparisons.items():
        if selected.get(key) != expected:
            raise AnimationError(
                f"ownership selected_clip.{key} does not match extracted clip"
            )
    if f32_bits(float(selected["duration_seconds"])) != int(
        selected["duration_raw"], 16
    ) or f32(float(selected["duration_seconds"])) != f32(
        float(clip_meta["duration_seconds"])
    ):
        raise AnimationError("ownership selected clip duration bits differ")
    if report.get("source_index") != str(index_path):
        raise AnimationError("ownership source index path differs")
    inventory_pin = report.get("source_pins", {}).get("motion_inventory", {})
    if inventory_pin != {
        "path": str(inventory_path),
        "sha256": sha256_file(inventory_path),
    }:
        raise AnimationError("ownership motion-inventory provenance differs")
    required_failures = {
        "no exact instruction edge proves this clip occupies a cutscene "
        "type-4 descriptor instance",
        "no exact static edge chooses one particular record of the "
        "seven-entry referee pool for this clip",
    }
    if not required_failures.issubset(set(report.get("failed", []))):
        raise AnimationError("ownership report lost an instance-level failure")
    return {
        "schema": EXPECTED_OWNERSHIP_SCHEMA,
        "gameplay_confidence":
            EXPECTED_RUNTIME_OWNERSHIP["confidence"],
        "specific_pool_record_instance_link_proved": False,
        "cutscene_type4_confidence":
            EXPECTED_CUTSCENE_TYPE4_RELATION["confidence"],
        "cutscene_type4_relation":
            EXPECTED_CUTSCENE_TYPE4_RELATION["relation"],
        "cutscene_type4_instance_level_link_proved": False,
    }


def validate_root_trajectory_report(
    report: object, clip_meta: dict[str, Any], ownership_path: Path,
) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise AnimationError("root-trajectory report is not an object")
    if report.get("schema") != EXPECTED_ROOT_TRAJECTORY_SCHEMA:
        raise AnimationError("root-trajectory report schema differs")
    selected = report.get("selected_clip", {})
    expected_selected = {
        "name": clip_meta["name"],
        "outer_index": clip_meta["outer_index"],
        "outer_id": clip_meta["outer_id"],
        "chunk_index": clip_meta["chunk_index"],
        "chunk_offset": clip_meta["chunk_offset"],
        "body_size": clip_meta["decoded_length"],
        "body_sha256": clip_meta["body_sha256"],
        "frame_count": clip_meta["frame_count"],
        "sample_rate_hz": clip_meta["sample_rate"],
        "flags": clip_meta["flags"],
        "looping": bool(clip_meta["flags"] & 1),
        "mirrored": bool(clip_meta["flags"] & 4),
    }
    exact_mapping("root-trajectory selected_clip", selected, expected_selected)
    serialized = report.get("serialized_trajectory", {})
    if (
        serialized.get("size") != 368
        or serialized.get("record_count") != 46
        or serialized.get("record_stride") != 8
        or serialized.get("sha256") != clip_meta["trajectory_region_sha256"]
    ):
        raise AnimationError("root-trajectory serialized payload differs")
    boundary = report.get("confidence_boundary", {})
    if (
        boundary.get("gltf_root_translation_emitted") is not False
        or len(boundary.get("proved", [])) != 5
        or len(boundary.get("unproved", [])) != 4
        or "do not export raw" not in str(boundary.get("decision", ""))
    ):
        raise AnimationError("root-trajectory confidence boundary differs")
    ownership_pin = report.get("sources", {}).get("ownership_report", {})
    if ownership_pin != {
        "path": str(ownership_path),
        "sha256": sha256_file(ownership_path),
    }:
        raise AnimationError("root-trajectory ownership provenance differs")
    return {
        "schema": EXPECTED_ROOT_TRAJECTORY_SCHEMA,
        "serialized_record_count": 46,
        "controller_callback_actor_writes_proved": True,
        "concrete_actor_initial_state_proved": False,
        "final_renderer_root_ownership_proved": False,
        "gltf_root_translation_emitted": False,
    }


def validate_render_root_report(
    report: object, root_trajectory_path: Path,
) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise AnimationError("render-root report is not an object")
    if report.get("schema") != EXPECTED_RENDER_ROOT_SCHEMA:
        raise AnimationError("render-root report schema differs")
    result = report.get("result", {})
    if result != {
        "actor_transform_to_renderer_external_root_edge_proved": True,
        "closed_upstream_gap":
            "the final actor+0x18 to renderer external-root ownership edge",
        "confidence": "instruction_exact_static_ownership",
        "gameplay_equivalent_gltf_root_track_ready": False,
        "reason_root_track_remains_withheld": (
            "the render edge is closed, but the selected clip still lacks a "
            "concrete one-of-seven actor instance and captured live actor, "
            "controller, and transform-state values"
        ),
        "selected_clip_to_concrete_actor_instance_proved": False,
    }:
        raise AnimationError("render-root result boundary differs")
    root_pin = report.get("sources", {}).get("root_trajectory_report", {})
    if root_pin != {
        "path": str(root_trajectory_path),
        "sha256": sha256_file(root_trajectory_path),
    }:
        raise AnimationError("render-root trajectory provenance differs")
    builders = report.get("external_root_builders", [])
    if (
        not isinstance(builders, list)
        or [row.get("function_va") for row in builders] != [
            "0x001d2d90", "0x0028ea10"
        ]
        or len(report.get("ownership_chain", [])) != 6
    ):
        raise AnimationError("render-root builders/ownership chain differ")
    return {
        "schema": EXPECTED_RENDER_ROOT_SCHEMA,
        "actor_transform_to_renderer_external_root_edge_proved": True,
        "external_root_builder_count": 2,
        "selected_clip_to_concrete_actor_instance_proved": False,
        "gameplay_equivalent_gltf_root_track_ready": False,
    }


def align4(binary: bytearray) -> None:
    binary.extend(bytes((-len(binary)) & 3))


def append_view(gltf: dict[str, Any], binary: bytearray, payload: bytes) -> int:
    align4(binary)
    offset = len(binary)
    binary.extend(payload)
    views = gltf.setdefault("bufferViews", [])
    views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(payload)})
    return len(views) - 1


def append_accessor(gltf: dict[str, Any], view: int, count: int,
                    kind: str, minimum: list[float] | None = None,
                    maximum: list[float] | None = None) -> int:
    accessor: dict[str, Any] = {
        "bufferView": view,
        "componentType": 5126,
        "count": count,
        "type": kind,
    }
    if minimum is not None:
        accessor["min"] = minimum
    if maximum is not None:
        accessor["max"] = maximum
    accessors = gltf.setdefault("accessors", [])
    accessors.append(accessor)
    return len(accessors) - 1


def load_clip(index_path: Path, inventory_path: Path,
              clip_name: str) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    if inventory.get("schema") != EXPECTED_INVENTORY_SCHEMA:
        raise AnimationError("motion inventory schema differs")
    matches = [resource for resource in inventory.get("resources", [])
               if resource.get("name") == clip_name]
    if len(matches) != 1:
        raise AnimationError(f"expected one {clip_name!r} resource, found {len(matches)}")
    resource = matches[0]
    if resource.get("kind") != "SMCD" or int(resource.get("root_count", -1)) != 1:
        raise AnimationError("selected witness is not one-root SMCD")
    archive = nfl_outer.parse_archive(index_path)
    entry = archive.entries[int(resource["outer_index"])]
    body = nfl_outer.read_entry_range(
        archive, entry, int(resource["chunk_offset"]) + 0x20,
        int(resource["stored_size"]),
    )
    if len(body) != int(resource["decoded_length"]) or sha256(body) != resource["decoded_sha256"]:
        raise AnimationError("selected SMCD body differs from inventory")
    root = resource["roots"][0]
    words = [int(value, 16) for value in root["header_words"]]
    packed_count = words[0] & 0xFF
    frame_count = words[0] >> 16
    sample_rate = words[3] & 0xFF
    time_scale = struct.unpack("<f", struct.pack("<I", words[4]))[0]
    duration = struct.unpack("<f", struct.pack("<I", words[5]))[0]
    flags = words[1] & 0xFF
    if packed_count != 21 or frame_count < 2 or sample_rate == 0 or not (
        math.isfinite(time_scale) and time_scale > 0.0 and
        math.isfinite(duration) and duration > 0.0
    ):
        raise AnimationError("selected referee clip header contract differs")
    region = next(
        (item for item in resource["packed_regions"]
         if int(item["owner_root_index"]) == 0 and
         int(item["owner_pointer_field_relative"]) == 0x24),
        None,
    )
    if region is None:
        raise AnimationError("selected clip has no packed-pose region")
    region_bytes = body[int(region["offset"]):int(region["end"])]
    if sha256(region_bytes) != region["sha256"]:
        raise AnimationError("selected packed region differs")
    payload_size = packed_count * frame_count * 4
    if len(region_bytes) < payload_size:
        raise AnimationError("selected packed payload is truncated")
    payload = region_bytes[:payload_size]
    trajectory = next(
        (item for item in resource["packed_regions"]
         if int(item["owner_root_index"]) == 0 and
         int(item["owner_pointer_field_relative"]) == 0x28),
        None,
    )
    if trajectory is None:
        raise AnimationError("selected clip has no trajectory region")
    trajectory_bytes = body[int(trajectory["offset"]):int(trajectory["end"])]
    if sha256(trajectory_bytes) != trajectory["sha256"]:
        raise AnimationError("selected trajectory region differs")
    metadata = {
        "name": clip_name,
        "outer_index": int(resource["outer_index"]),
        "outer_id": resource["outer_id"],
        "chunk_index": int(resource["chunk_index"]),
        "chunk_offset": int(resource["chunk_offset"]),
        "decoded_length": int(resource["decoded_length"]),
        "body_sha256": resource["decoded_sha256"],
        "packed_region_sha256": region["sha256"],
        "packed_payload_sha256": sha256(payload),
        "packed_payload_bytes": len(payload),
        "packed_region_slack_bytes": len(region_bytes) - payload_size,
        "packed_channels": packed_count,
        "frame_count": frame_count,
        "sample_rate": sample_rate,
        "time_scale": time_scale,
        "duration_seconds": duration,
        "flags": flags,
        "trajectory_bytes": len(trajectory_bytes),
        "trajectory_region_sha256": trajectory["sha256"],
    }
    return metadata, payload, resource


def sample_native(library_path: Path, clip_meta: dict[str, Any],
                  payload: bytes, times: list[float]) -> tuple[list[list[tuple[float, ...]]], dict[str, Any]]:
    library = ctypes.CDLL(str(library_path.resolve()))
    sample = library.vc_nfl_coach_ref_pose_sample_title_policy
    sample.argtypes = [
        ctypes.POINTER(ClipView), ctypes.c_float,
        ctypes.POINTER(LocalPose), ctypes.c_void_p,
    ]
    sample.restype = ctypes.c_int
    twist_is_bit_exact = (
        library.vc_nfl_coach_ref_pose_twist_is_xbox_bit_exact
    )
    twist_is_bit_exact.argtypes = []
    twist_is_bit_exact.restype = ctypes.c_bool
    source = (ctypes.c_uint8 * len(payload)).from_buffer_copy(payload)
    clip = ClipView(
        ctypes.cast(source, ctypes.POINTER(ctypes.c_uint8)), len(payload),
        clip_meta["frame_count"], clip_meta["packed_channels"],
        clip_meta["sample_rate"], clip_meta["time_scale"],
        clip_meta["flags"], clip_meta["duration_seconds"],
    )
    tracks: list[list[tuple[float, ...]]] = [[] for _ in range(CHANNELS)]
    maximum_norm_deviation = 0.0
    maximum_normalization_lane_delta = 0.0
    maximum_matrix_element_delta = 0.0
    sign_flips = 0
    for time in times:
        pose = LocalPose()
        status = sample(ctypes.byref(clip), ctypes.c_float(time),
                        ctypes.byref(pose), None)
        if status != 0:
            raise AnimationError(f"native referee pose failed at {time}: {status}")
        for channel in range(CHANNELS):
            raw = tuple(float(pose.scalar_first[channel][lane])
                        for lane in range(4))
            norm = math.sqrt(sum(value * value for value in raw))
            if not math.isfinite(norm) or norm == 0.0:
                raise AnimationError("native pose produced invalid quaternion")
            normalized = tuple(f32(value / norm) for value in raw)
            normalized_norm = math.sqrt(sum(value * value for value in normalized))
            normalized = tuple(f32(value / normalized_norm) for value in normalized)
            if tracks[channel]:
                previous_xyzw = tracks[channel][-1]
                previous_wxyz = (previous_xyzw[3], previous_xyzw[0],
                                 previous_xyzw[1], previous_xyzw[2])
                if sum(left * right for left, right in zip(previous_wxyz, normalized)) < 0.0:
                    normalized = tuple(f32(-value) for value in normalized)
                    sign_flips += 1
            xyzw = (normalized[1], normalized[2], normalized[3], normalized[0])
            tracks[channel].append(xyzw)
            maximum_norm_deviation = max(maximum_norm_deviation, abs(norm - 1.0))
            maximum_normalization_lane_delta = max(
                maximum_normalization_lane_delta,
                *(abs(raw[lane] - normalized[lane]) for lane in range(4)),
            )
            original_matrix = quaternion_to_row_matrix(raw)
            normalized_matrix = quaternion_to_row_matrix(normalized)
            maximum_matrix_element_delta = max(
                maximum_matrix_element_delta,
                *(abs(left - right) for left, right in
                  zip(original_matrix, normalized_matrix)),
            )
    return tracks, {
        "maximum_source_norm_deviation": maximum_norm_deviation,
        "maximum_normalization_lane_delta": maximum_normalization_lane_delta,
        "maximum_original_matrix_element_delta_after_normalization": maximum_matrix_element_delta,
        "sign_continuity_flip_count": sign_flips,
        "twist_is_xbox_bit_exact": bool(twist_is_bit_exact()),
    }


def slerp(left: tuple[float, ...], right: tuple[float, ...], factor: float) -> tuple[float, ...]:
    dot = sum(a * b for a, b in zip(left, right))
    if dot < 0.0:
        right = tuple(-value for value in right)
        dot = -dot
    dot = min(1.0, max(-1.0, dot))
    if dot > 0.9995:
        result = tuple((1.0 - factor) * a + factor * b
                       for a, b in zip(left, right))
    else:
        theta = math.acos(dot)
        denominator = math.sin(theta)
        result = tuple(
            math.sin((1.0 - factor) * theta) / denominator * a +
            math.sin(factor * theta) / denominator * b
            for a, b in zip(left, right)
        )
    norm = math.sqrt(sum(value * value for value in result))
    return tuple(value / norm for value in result)


def gltf_interpolation_grid_error(library_path: Path,
                                  clip_meta: dict[str, Any], payload: bytes,
                                  times: list[float], tracks: list[list[tuple[float, ...]]]) -> dict[str, Any]:
    probes: list[float] = []
    owners: list[tuple[int, float]] = []
    for interval in range(len(times) - 1):
        for fraction in (0.25, 0.5, 0.75):
            probes.append(f32(times[interval] +
                              (times[interval + 1] - times[interval]) * fraction))
            owners.append((interval, fraction))
    exact_tracks, _ = sample_native(library_path, clip_meta, payload, probes)
    maximum_radians = 0.0
    maximum_case: dict[str, Any] | None = None
    for probe_index, (interval, fraction) in enumerate(owners):
        for channel in range(CHANNELS):
            represented = slerp(tracks[channel][interval],
                                 tracks[channel][interval + 1], fraction)
            exact = exact_tracks[channel][probe_index]
            dot = abs(sum(a * b for a, b in zip(represented, exact)))
            radians = 2.0 * math.acos(min(1.0, max(-1.0, dot)))
            if radians > maximum_radians:
                maximum_radians = radians
                maximum_case = {
                    "channel": channel,
                    "interval": interval,
                    "fraction": fraction,
                    "time_seconds": probes[probe_index],
                }
    return {
        "probe_count": len(probes) * CHANNELS,
        "fractions_per_interval": [0.25, 0.5, 0.75],
        "maximum_angular_error_radians": maximum_radians,
        "maximum_angular_error_degrees": math.degrees(maximum_radians),
        "maximum_case": maximum_case,
        "interpretation": "observed grid error, not a continuous mathematical bound",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path,
                        default=Path("extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"))
    parser.add_argument("--motion-inventory", type=Path,
                        default=Path("reports/assets/nfl2k5_motion_inventory.json"))
    parser.add_argument("--meter-manifest", type=Path,
                        default=Path("reports/assets/nfl_meter_skin_gltf_manifest.json"))
    parser.add_argument("--source-gltf", type=Path,
                        default=Path("assets/intermediate/nfl2k5/meter_skin_samples/0346_0109_referee_meter_skin.gltf"))
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--native-source", type=Path,
                        default=Path("src/recovered/nfl2k5/coach_ref_pose.c"))
    parser.add_argument("--native-header", type=Path,
                        default=Path("include/recovered/nfl2k5/coach_ref_pose.h"))
    parser.add_argument("--native-dependency", type=Path, action="append",
                        default=[])
    parser.add_argument("--ownership-report", type=Path, required=True)
    parser.add_argument("--root-trajectory-report", type=Path, required=True)
    parser.add_argument("--render-root-report", type=Path, required=True)
    parser.add_argument("--clip", default=DEFAULT_CLIP)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    native_files = [args.native_header, args.native_source]
    native_files.extend(DEFAULT_NATIVE_DEPENDENCIES)
    native_files.extend(args.native_dependency)
    if len({str(path) for path in native_files}) != len(native_files):
        raise AnimationError("native implementation file list has duplicates")
    native_pins = file_pins(native_files)
    generator_pins = file_pins(DEFAULT_GENERATOR_DEPENDENCIES)

    meter_manifest = json.loads(args.meter_manifest.read_text(encoding="utf-8"))
    if meter_manifest.get("schema") != EXPECTED_METER_SCHEMA:
        raise AnimationError("meter-skin manifest schema differs")
    source_row = next(
        (row for row in meter_manifest.get("outputs", [])
         if row["output_gltf"] == args.source_gltf.name), None,
    )
    if source_row is None or sha256_file(args.source_gltf) != source_row["output_gltf_sha256"]:
        raise AnimationError("source referee meter glTF is not canonical")

    clip_meta, payload, _ = load_clip(args.index, args.motion_inventory,
                                      args.clip)
    ownership_report = json.loads(
        args.ownership_report.read_text(encoding="utf-8")
    )
    ownership_boundary = validate_ownership_report(
        ownership_report, clip_meta, args.index, args.motion_inventory,
    )
    ownership = {
        "path": str(args.ownership_report),
        "sha256": sha256_file(args.ownership_report),
        "report": ownership_report,
        "boundary": ownership_boundary,
    }
    root_trajectory_report = json.loads(
        args.root_trajectory_report.read_text(encoding="utf-8")
    )
    root_trajectory_upstream_boundary = validate_root_trajectory_report(
        root_trajectory_report, clip_meta, args.ownership_report,
    )
    root_trajectory = {
        "path": str(args.root_trajectory_report),
        "sha256": sha256_file(args.root_trajectory_report),
        "schema": root_trajectory_report.get("schema"),
        "boundary": root_trajectory_upstream_boundary,
    }
    render_root_report = json.loads(
        args.render_root_report.read_text(encoding="utf-8")
    )
    render_root_boundary = validate_render_root_report(
        render_root_report, args.root_trajectory_report,
    )
    render_root = {
        "path": str(args.render_root_report),
        "sha256": sha256_file(args.render_root_report),
        "schema": render_root_report.get("schema"),
        "boundary": render_root_boundary,
    }
    root_motion_pipeline_boundary = {
        "serialized_record_count": 46,
        "controller_callback_actor_writes_proved": True,
        "actor_transform_to_renderer_external_root_edge_proved": True,
        "concrete_actor_initial_state_proved": False,
        "gameplay_equivalent_gltf_root_track_ready": False,
        "gltf_root_translation_emitted": False,
    }

    duration = f32(float(clip_meta["duration_seconds"]))
    regular_last = max(0, math.floor(duration * BAKE_RATE) - 1)
    times = [f32(index / BAKE_RATE) for index in range(regular_last + 1)]
    if not times or not duration > times[-1]:
        raise AnimationError("could not construct strictly increasing bake times")
    times.append(duration)
    tracks, normalization = sample_native(args.library, clip_meta, payload,
                                           times)
    interpolation = gltf_interpolation_grid_error(
        args.library, clip_meta, payload, times, tracks,
    )
    if not 0.0 <= float(
        interpolation["maximum_angular_error_degrees"]
    ) < MAXIMUM_OBSERVED_GRID_ERROR_DEGREES:
        raise AnimationError(
            "120 Hz standard-glTF sampled-grid error exceeds 0.1 degrees"
        )

    gltf = json.loads(args.source_gltf.read_text(encoding="utf-8"))
    buffers = gltf.get("buffers")
    if not isinstance(buffers, list) or len(buffers) != 1:
        raise AnimationError("source glTF does not have one external buffer")
    source_bin = args.source_gltf.parent / buffers[0]["uri"]
    if (source_bin.name != source_row["output_bin"] or
            sha256_file(source_bin) != source_row["output_bin_sha256"]):
        raise AnimationError("source referee meter binary is not canonical")
    binary = bytearray(source_bin.read_bytes())
    source_binary_bytes = len(binary)
    time_payload = b"".join(struct.pack("<f", value) for value in times)
    time_view = append_view(gltf, binary, time_payload)
    time_accessor = append_accessor(
        gltf, time_view, len(times), "SCALAR", [times[0]], [times[-1]],
    )
    rotation_accessors = []
    for track in tracks:
        payload_bytes = b"".join(struct.pack("<4f", *value)
                                 for value in track)
        view = append_view(gltf, binary, payload_bytes)
        rotation_accessors.append(
            append_accessor(gltf, view, len(track), "VEC4")
        )

    nodes = gltf["nodes"]
    node_by_name = {str(node.get("name")): index
                    for index, node in enumerate(nodes)}
    samplers = [
        {"input": time_accessor, "output": accessor,
         "interpolation": "LINEAR"}
        for accessor in rotation_accessors
    ]
    channels = []
    for logical in range(CHANNELS):
        for family in ("referee_high", "referee_low"):
            name = f"{family}:{BONES[logical]}"
            if name not in node_by_name:
                raise AnimationError(f"source meter skin lacks node {name}")
            channels.append({
                "sampler": logical,
                "target": {"node": node_by_name[name], "path": "rotation"},
            })
    gltf["animations"] = [{
        "name": args.clip,
        "samplers": samplers,
        "channels": channels,
        "extras": {
            "bake_rate_hz": BAKE_RATE,
            "key_count": len(times),
            "source_clip": clip_meta,
            "local_rotation_tracks_only": True,
            "root_translation_emitted": False,
            "trajectory_bytes_present_but_omitted":
                clip_meta["trajectory_bytes"],
            "title_policy": {
                "flags": clip_meta["flags"],
                "looping_flag_bit_0": bool(clip_meta["flags"] & 1),
                "mirrored_flag_bit_2": bool(clip_meta["flags"] & 4),
                "time_policy": "non_looping_final_frame_clamp",
            },
            "ownership_boundary": ownership_boundary,
            "root_motion_pipeline_boundary": root_motion_pipeline_boundary,
            "normalization": normalization,
            "between_key_representation": interpolation,
            "portme": PORTME,
        },
    }]
    gltf["asset"]["generator"] = (
        "nfl_referee_animated_gltf.py (meter skin + recovered native pose)"
    )
    gltf.setdefault("extras", {})["title_animation_witness"] = {
        "clip": args.clip,
        "native_key_samples": len(times) * CHANNELS,
        "bake_rate_hz": BAKE_RATE,
        "local_rotation_tracks_only": True,
        "root_translation_emitted": False,
        "trajectory_bytes_present_but_omitted":
            clip_meta["trajectory_bytes"],
        "ownership_report": {
            "path": ownership["path"], "sha256": ownership["sha256"]
        },
        "ownership_boundary": ownership_boundary,
        "root_trajectory_report": root_trajectory,
        "render_root_report": render_root,
        "root_motion_pipeline_boundary": root_motion_pipeline_boundary,
        "portme": PORTME,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output_bin = args.output.with_suffix(".bin")
    buffers[0]["uri"] = output_bin.name
    buffers[0]["byteLength"] = len(binary)
    output_bin.write_bytes(binary)
    args.output.write_text(json.dumps(gltf, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")

    report = {
        "schema": SCHEMA,
        "source": {
            "index": str(args.index),
            "index_sha256": sha256_file(args.index),
            "motion_inventory": str(args.motion_inventory),
            "motion_inventory_sha256": sha256_file(args.motion_inventory),
            "meter_manifest": str(args.meter_manifest),
            "meter_manifest_sha256": sha256_file(args.meter_manifest),
            "meter_gltf": str(args.source_gltf),
            "meter_gltf_sha256": sha256_file(args.source_gltf),
            "meter_bin": str(source_bin),
            "meter_bin_sha256": sha256_file(source_bin),
            "native_pose_implementation": {
                "files": native_pins,
                "runtime_library_path_intentionally_unpinned": True,
            },
            "generator_implementation": {
                "files": generator_pins,
            },
            "ownership_report": {
                "path": ownership["path"], "sha256": ownership["sha256"],
                "schema": ownership["report"].get("schema"),
                "boundary": ownership_boundary,
            },
            "root_trajectory_report": root_trajectory,
            "render_root_report": render_root,
        },
        "clip": clip_meta,
        "animation": {
            "target_family": "referee_high_and_low",
            "logical_channel_count": CHANNELS,
            "target_node_count": len(channels),
            "bake_rate_hz": BAKE_RATE,
            "key_count": len(times),
            "first_time_seconds": times[0],
            "last_time_seconds": times[-1],
            "native_key_sample_count": len(times) * CHANNELS,
            "local_rotation_tracks_only": True,
            "root_translation_emitted": False,
            "trajectory_bytes_present_but_omitted":
                clip_meta["trajectory_bytes"],
            "title_policy": {
                "flags": clip_meta["flags"],
                "looping_flag_bit_0": bool(clip_meta["flags"] & 1),
                "mirrored_flag_bit_2": bool(clip_meta["flags"] & 4),
                "time_policy": "non_looping_final_frame_clamp",
            },
            "ownership_boundary": ownership_boundary,
            "root_motion_pipeline_boundary": root_motion_pipeline_boundary,
            "normalization": normalization,
            "between_key_representation": interpolation,
        },
        "output": {
            "gltf": args.output.name,
            "bin": output_bin.name,
            "gltf_sha256": sha256_file(args.output),
            "bin_sha256": sha256_file(output_bin),
            "source_binary_prefix_bytes": source_binary_bytes,
            "total_binary_bytes": len(binary),
        },
        "portme": PORTME,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
    print(
        "NFL_REFEREE_ANIMATED_GLTF_COMPLETE "
        f"clip={args.clip} keys={len(times)} channels={CHANNELS} "
        f"targets={len(channels)} max_grid_degrees="
        f"{interpolation['maximum_angular_error_degrees']:.9g}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

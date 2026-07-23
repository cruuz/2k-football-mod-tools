#!/usr/bin/env python3
"""Structurally and numerically validate the baked NFL referee glTF witness."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
from typing import Any


SCHEMA = "nfl2k5_referee_animated_gltf/v1"
OWNERSHIP_SCHEMA = "nfl2k5_ref_clip_ownership/v1"
ROOT_TRAJECTORY_SCHEMA = "nfl2k5_referee_root_trajectory/v1"
RENDER_ROOT_SCHEMA = "nfl2k5_referee_render_root/v1"
EXPECTED_CLIP = "ANM_REF_PENALTY_DELAY_OF_GAME_R"
EXPECTED_METER_SCHEMA = "nfl2k5_meter_skin_gltf_manifest/v1"
BAKE_RATE = 120
MAXIMUM_OBSERVED_GRID_ERROR_DEGREES = 0.1
EXPECTED_BONES = (
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
    "name": EXPECTED_CLIP,
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
EXPECTED_OWNERSHIP_BOUNDARY = {
    "schema": OWNERSHIP_SCHEMA,
    "gameplay_confidence":
        "instruction_exact_referee_namespace_and_skeletal_family",
    "specific_pool_record_instance_link_proved": False,
    "cutscene_type4_confidence":
        "instruction_exact_abi_relation_instance_unproved",
    "cutscene_type4_relation":
        "same_referee_skeletal_family_not_proved_same_descriptor_instance",
    "cutscene_type4_instance_level_link_proved": False,
}
EXPECTED_ROOT_TRAJECTORY_BOUNDARY = {
    "schema": ROOT_TRAJECTORY_SCHEMA,
    "serialized_record_count": 46,
    "controller_callback_actor_writes_proved": True,
    "concrete_actor_initial_state_proved": False,
    "final_renderer_root_ownership_proved": False,
    "gltf_root_translation_emitted": False,
}
EXPECTED_RENDER_ROOT_BOUNDARY = {
    "schema": RENDER_ROOT_SCHEMA,
    "actor_transform_to_renderer_external_root_edge_proved": True,
    "external_root_builder_count": 2,
    "selected_clip_to_concrete_actor_instance_proved": False,
    "gameplay_equivalent_gltf_root_track_ready": False,
}
EXPECTED_ROOT_MOTION_PIPELINE_BOUNDARY = {
    "serialized_record_count": 46,
    "controller_callback_actor_writes_proved": True,
    "actor_transform_to_renderer_external_root_edge_proved": True,
    "concrete_actor_initial_state_proved": False,
    "gameplay_equivalent_gltf_root_track_ready": False,
    "gltf_root_translation_emitted": False,
}
EXPECTED_NATIVE_FILES = (
    "include/recovered/nfl2k5/coach_ref_pose.h",
    "src/recovered/nfl2k5/coach_ref_pose.c",
    "include/recovered/nfl2k5/motion_pose_sample.h",
    "src/recovered/nfl2k5/motion_pose_sample.c",
    "include/recovered/nfl2k5/packed_pose.h",
    "src/recovered/nfl2k5/packed_pose.c",
    "include/recovered/nfl2k5/quaternion_interpolation.h",
    "src/recovered/nfl2k5/quaternion_interpolation.c",
    "src/recovered/nfl2k5/quaternion_interpolation_table.inc",
)
EXPECTED_GENERATOR_FILES = (
    "tools/nfl_referee_animated_gltf.py",
    "tools/nfl_outer.py",
    "tools/nfl_rest_orientation.py",
)
EXPECTED_PORTME = [
    "PORTME: gameplay ownership is instruction-exact for the Referee namespace and skeletal family, but the specific record in the seven-entry runtime pool is not proved.",
    "PORTME: no exact runtime edge proves this gameplay penalty clip occupies a cutscene type-4 descriptor instance; the shared skeletal ABI is not an instance link.",
    "PORTME: glTF requires unit rotation quaternions, while the original matrix helper consumes slightly non-unit interpolated output; retain the measured normalization delta.",
    "PORTME: standard glTF LINEAR rotation uses ideal slerp, not the title's fixed-table/x87 interpolation; this witness bakes exact native samples at 120 Hz and records the between-key representation error.",
    "PORTME: trajectory sampling/controller/callback and the final renderer-root edge are instruction-exact, but root translation remains omitted until the concrete one-of-seven actor initialization and live state are captured.",
    "PORTME: player postprocessors 0x00092140 and 0x00093850 are value-equivalently ported; player animation remains withheld until an exact shipped clip/controller/hierarchy-root path is joined.",
]


class ValidationError(ValueError):
    pass


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
        raise ValidationError(f"{label} is not an object")
    if actual == expected:
        return
    for key in sorted(set(actual) | set(expected)):
        if actual.get(key) != expected.get(key):
            raise ValidationError(
                f"{label}.{key} differs: {actual.get(key)!r} != "
                f"{expected.get(key)!r}"
            )
    raise ValidationError(f"{label} differs")


def validate_file_pins(label: str, value: object,
                       expected_paths: tuple[str, ...]) -> None:
    if not isinstance(value, list):
        raise ValidationError(f"{label} file pins are not a list")
    paths = [pin.get("path") for pin in value if isinstance(pin, dict)]
    if paths != list(expected_paths) or len(paths) != len(value):
        raise ValidationError(f"{label} file paths differ")
    for pin in value:
        if set(pin) != {"path", "sha256"}:
            raise ValidationError(f"{label} pin shape differs")
        path = Path(pin["path"])
        if sha256_file(path) != pin["sha256"]:
            raise ValidationError(f"{label} hash differs for {path}")


def expected_times() -> list[float]:
    duration = struct.unpack(
        "<f", struct.pack("<I", int(EXPECTED_SELECTED_CLIP["duration_raw"], 16))
    )[0]
    regular_last = max(0, math.floor(duration * BAKE_RATE) - 1)
    values = [f32(index / BAKE_RATE)
              for index in range(regular_last + 1)]
    values.append(duration)
    return values


def accessor_values(gltf: dict[str, Any], binary: bytes,
                    accessor_index: int, components: int) -> list[tuple[float, ...]]:
    accessor = gltf["accessors"][accessor_index]
    if int(accessor["componentType"]) != 5126 or "sparse" in accessor:
        raise ValidationError("animation accessor is not dense float32")
    view = gltf["bufferViews"][int(accessor["bufferView"])]
    if int(view.get("buffer", 0)) != 0:
        raise ValidationError("animation accessor is not in buffer zero")
    stride = int(view.get("byteStride", components * 4))
    if stride < components * 4:
        raise ValidationError("animation accessor stride is too small")
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    count = int(accessor["count"])
    if count < 1 or start + (count - 1) * stride + components * 4 > len(binary):
        raise ValidationError("animation accessor is out of bounds")
    return [
        struct.unpack_from(f"<{components}f", binary, start + item * stride)
        for item in range(count)
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--asset-dir", type=Path, required=True)
    parser.add_argument("--ownership-report", type=Path, required=True)
    parser.add_argument("--root-trajectory-report", type=Path, required=True)
    parser.add_argument("--render-root-report", type=Path, required=True)
    args = parser.parse_args()

    report = json.loads(args.manifest.read_text(encoding="utf-8"))
    if report.get("schema") != SCHEMA:
        raise ValidationError("animated manifest schema differs")
    ownership = json.loads(args.ownership_report.read_text(encoding="utf-8"))
    if ownership.get("schema") != OWNERSHIP_SCHEMA:
        raise ValidationError("ownership schema differs")
    exact_mapping(
        "ownership selected_clip", ownership.get("selected_clip"),
        EXPECTED_SELECTED_CLIP,
    )
    exact_mapping(
        "ownership runtime_ownership", ownership.get("runtime_ownership"),
        EXPECTED_RUNTIME_OWNERSHIP,
    )
    exact_mapping(
        "ownership cutscene_type4_relation",
        ownership.get("cutscene_type4_relation"),
        EXPECTED_CUTSCENE_TYPE4_RELATION,
    )
    required_failures = {
        "no exact instruction edge proves this clip occupies a cutscene "
        "type-4 descriptor instance",
        "no exact static edge chooses one particular record of the "
        "seven-entry referee pool for this clip",
    }
    if not required_failures.issubset(set(ownership.get("failed", []))):
        raise ValidationError("ownership report lost an instance-level failure")
    root_trajectory = json.loads(
        args.root_trajectory_report.read_text(encoding="utf-8")
    )
    if root_trajectory.get("schema") != ROOT_TRAJECTORY_SCHEMA:
        raise ValidationError("root-trajectory schema differs")
    root_selected = root_trajectory.get("selected_clip", {})
    for key, expected in {
        "name": EXPECTED_CLIP,
        "outer_index": 3107,
        "outer_id": "0xda37aa9d",
        "chunk_index": 27,
        "chunk_offset": 304128,
        "body_size": 4400,
        "body_sha256": EXPECTED_SELECTED_CLIP["decoded_sha256"],
        "frame_count": 46,
        "sample_rate_hz": 15,
        "flags": 2,
        "looping": False,
        "mirrored": False,
    }.items():
        if root_selected.get(key) != expected:
            raise ValidationError(f"root-trajectory selected_clip.{key} differs")
    serialized = root_trajectory.get("serialized_trajectory", {})
    if (
        serialized.get("size") != 368
        or serialized.get("record_count") != 46
        or serialized.get("record_stride") != 8
        or serialized.get("sha256") !=
            "829de7b7999ea1a47401d81b4ccc7bfa042d872614e0ee50c792babdded111fa"
    ):
        raise ValidationError("root-trajectory serialized payload differs")
    root_boundary = root_trajectory.get("confidence_boundary", {})
    if (
        root_boundary.get("gltf_root_translation_emitted") is not False
        or len(root_boundary.get("proved", [])) != 5
        or len(root_boundary.get("unproved", [])) != 4
        or "do not export raw" not in str(root_boundary.get("decision", ""))
    ):
        raise ValidationError("root-trajectory confidence boundary differs")
    if root_trajectory.get("sources", {}).get("ownership_report") != {
        "path": str(args.ownership_report),
        "sha256": sha256_file(args.ownership_report),
    }:
        raise ValidationError("root-trajectory ownership provenance differs")
    render_root = json.loads(args.render_root_report.read_text(encoding="utf-8"))
    if render_root.get("schema") != RENDER_ROOT_SCHEMA:
        raise ValidationError("render-root schema differs")
    render_result = render_root.get("result", {})
    if render_result != {
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
        raise ValidationError("render-root result boundary differs")
    if render_root.get("sources", {}).get("root_trajectory_report") != {
        "path": str(args.root_trajectory_report),
        "sha256": sha256_file(args.root_trajectory_report),
    }:
        raise ValidationError("render-root trajectory provenance differs")
    if (
        [row.get("function_va") for row in
         render_root.get("external_root_builders", [])]
        != ["0x001d2d90", "0x0028ea10"]
        or len(render_root.get("ownership_chain", [])) != 6
    ):
        raise ValidationError("render-root builders/ownership chain differ")

    source = report.get("source", {})
    expected_ownership_source = {
        "path": str(args.ownership_report),
        "sha256": sha256_file(args.ownership_report),
        "schema": OWNERSHIP_SCHEMA,
        "boundary": EXPECTED_OWNERSHIP_BOUNDARY,
    }
    if source.get("ownership_report") != expected_ownership_source:
        raise ValidationError("ownership provenance differs")
    expected_root_source = {
        "path": str(args.root_trajectory_report),
        "sha256": sha256_file(args.root_trajectory_report),
        "schema": ROOT_TRAJECTORY_SCHEMA,
        "boundary": EXPECTED_ROOT_TRAJECTORY_BOUNDARY,
    }
    if source.get("root_trajectory_report") != expected_root_source:
        raise ValidationError("root-trajectory provenance differs")
    expected_render_source = {
        "path": str(args.render_root_report),
        "sha256": sha256_file(args.render_root_report),
        "schema": RENDER_ROOT_SCHEMA,
        "boundary": EXPECTED_RENDER_ROOT_BOUNDARY,
    }
    if source.get("render_root_report") != expected_render_source:
        raise ValidationError("render-root provenance differs")
    provenance_paths = {
        "index": "index_sha256",
        "motion_inventory": "motion_inventory_sha256",
        "meter_manifest": "meter_manifest_sha256",
        "meter_gltf": "meter_gltf_sha256",
        "meter_bin": "meter_bin_sha256",
    }
    for path_key, hash_key in provenance_paths.items():
        path = Path(source[path_key])
        if sha256_file(path) != source[hash_key]:
            raise ValidationError(f"source {path_key} hash differs")
    native = source.get("native_pose_implementation", {})
    if native.get("runtime_library_path_intentionally_unpinned") is not True:
        raise ValidationError("runtime native-library boundary differs")
    if set(native) != {
        "files", "runtime_library_path_intentionally_unpinned"
    }:
        raise ValidationError("native implementation provenance shape differs")
    validate_file_pins(
        "native implementation", native.get("files"),
        EXPECTED_NATIVE_FILES,
    )
    generator = source.get("generator_implementation", {})
    if set(generator) != {"files"}:
        raise ValidationError("generator provenance shape differs")
    validate_file_pins(
        "generator implementation", generator.get("files"),
        EXPECTED_GENERATOR_FILES,
    )

    meter_manifest = json.loads(
        Path(source["meter_manifest"]).read_text(encoding="utf-8")
    )
    if meter_manifest.get("schema") != EXPECTED_METER_SCHEMA:
        raise ValidationError("meter manifest schema differs")
    meter_row = next(
        (row for row in meter_manifest.get("outputs", [])
         if row.get("output_gltf") == Path(source["meter_gltf"]).name),
        None,
    )
    if meter_row is None or meter_row.get("output_gltf_sha256") != source[
        "meter_gltf_sha256"
    ] or meter_row.get("output_bin") != Path(source["meter_bin"]).name or (
        meter_row.get("output_bin_sha256") != source["meter_bin_sha256"]
    ):
        raise ValidationError("meter manifest referee row differs")

    output = report["output"]
    gltf_path = args.asset_dir / output["gltf"]
    bin_path = args.asset_dir / output["bin"]
    if (gltf_path.suffix != ".gltf" or bin_path.suffix != ".bin" or
            gltf_path.with_suffix(".bin").name != bin_path.name):
        raise ValidationError("animated output names differ")
    if (sha256_file(gltf_path) != output["gltf_sha256"] or
            sha256_file(bin_path) != output["bin_sha256"]):
        raise ValidationError("animated output hash differs")
    gltf = json.loads(gltf_path.read_text(encoding="utf-8"))
    binary = bin_path.read_bytes()
    if (not isinstance(gltf.get("buffers"), list) or
            len(gltf["buffers"]) != 1 or
            gltf["buffers"][0].get("uri") != bin_path.name or
            int(gltf["buffers"][0]["byteLength"]) != len(binary) or
            int(output["total_binary_bytes"]) != len(binary)):
        raise ValidationError("animated buffer length differs")

    source_gltf_path = Path(source["meter_gltf"])
    source_bin_path = Path(source["meter_bin"])
    source_gltf = json.loads(source_gltf_path.read_text(encoding="utf-8"))
    source_binary = source_bin_path.read_bytes()
    prefix = int(output["source_binary_prefix_bytes"])
    if prefix != len(source_binary) or binary[:prefix] != source_binary:
        raise ValidationError("meter binary prefix changed")
    for key in ("scene", "scenes", "nodes", "meshes", "skins", "materials"):
        if source_gltf.get(key) != gltf.get(key):
            raise ValidationError(f"base glTF {key} changed")
    source_accessors = source_gltf["accessors"]
    source_views = source_gltf["bufferViews"]
    if (gltf["accessors"][:len(source_accessors)] != source_accessors or
            gltf["bufferViews"][:len(source_views)] != source_views):
        raise ValidationError("base accessor/view definitions changed")
    if (len(gltf["accessors"]) != len(source_accessors) + 26 or
            len(gltf["bufferViews"]) != len(source_views) + 26):
        raise ValidationError("expected one time and 25 rotation accessors")
    source_buffer = dict(source_gltf["buffers"][0])
    output_buffer = dict(gltf["buffers"][0])
    source_buffer.pop("uri", None)
    source_buffer.pop("byteLength", None)
    output_buffer.pop("uri", None)
    output_buffer.pop("byteLength", None)
    if source_buffer != output_buffer:
        raise ValidationError("base glTF buffer metadata changed")

    if report.get("portme") != EXPECTED_PORTME:
        raise ValidationError("PORTME list differs")
    clip = report.get("clip", {})
    expected_clip_fields = {
        "name": EXPECTED_CLIP,
        "outer_index": 3107,
        "outer_id": "0xda37aa9d",
        "chunk_index": 27,
        "chunk_offset": 304128,
        "decoded_length": 4400,
        "body_sha256": EXPECTED_SELECTED_CLIP["decoded_sha256"],
        "packed_region_sha256":
            "842a8f14557f864efc238f5060de07a5c40343c32fdc78ee29461dc2817b8843",
        "packed_payload_sha256":
            "cf11e59e3bf6a14031c0261834d0bbba24688998e8ce8594463dc6798c9cd093",
        "packed_payload_bytes": 3864,
        "packed_region_slack_bytes": 4,
        "packed_channels": 21,
        "frame_count": 46,
        "sample_rate": 15,
        "time_scale": 1.0,
        "flags": 2,
        "trajectory_bytes": 368,
        "trajectory_region_sha256":
            "829de7b7999ea1a47401d81b4ccc7bfa042d872614e0ee50c792babdded111fa",
    }
    for key, expected in expected_clip_fields.items():
        if clip.get(key) != expected:
            raise ValidationError(f"animated clip.{key} differs")
    expected_duration_bits = int(
        EXPECTED_SELECTED_CLIP["duration_raw"], 16
    )
    if f32_bits(float(clip.get("duration_seconds", math.nan))) != (
        expected_duration_bits
    ) or f32_bits(float(EXPECTED_SELECTED_CLIP["duration_seconds"])) != (
        expected_duration_bits
    ):
        raise ValidationError("animated clip duration bits differ")
    if ownership.get("source_index") != source["index"]:
        raise ValidationError("ownership/index path differs")
    inventory_pin = ownership.get("source_pins", {}).get(
        "motion_inventory", {}
    )
    if inventory_pin != {
        "path": source["motion_inventory"],
        "sha256": source["motion_inventory_sha256"],
    }:
        raise ValidationError("ownership/motion-inventory pin differs")

    animations = gltf.get("animations")
    if not isinstance(animations, list) or len(animations) != 1:
        raise ValidationError("expected exactly one animation")
    animation = animations[0]
    if animation.get("name") != EXPECTED_CLIP:
        raise ValidationError("animation name differs")
    samplers = animation.get("samplers")
    channels = animation.get("channels")
    if (not isinstance(samplers, list) or len(samplers) != 25 or
            not isinstance(channels, list) or len(channels) != 50):
        raise ValidationError("animation dimensions differ")

    time_accessor = len(source_accessors)
    expected_samplers = [
        {
            "input": time_accessor,
            "output": time_accessor + 1 + logical,
            "interpolation": "LINEAR",
        }
        for logical in range(25)
    ]
    if samplers != expected_samplers:
        raise ValidationError("animation sampler/accessor binding differs")
    timeline = expected_times()
    times = [
        row[0] for row in accessor_values(
            gltf, binary, time_accessor, 1
        )
    ]
    if ([f32_bits(value) for value in times] !=
            [f32_bits(value) for value in timeline]):
        raise ValidationError("animation 120 Hz timeline differs")
    time_definition = gltf["accessors"][time_accessor]
    if time_definition != {
        "bufferView": len(source_views),
        "componentType": 5126,
        "count": len(timeline),
        "max": [timeline[-1]],
        "min": [timeline[0]],
        "type": "SCALAR",
    }:
        raise ValidationError("timeline accessor definition differs")
    for logical in range(25):
        accessor_index = time_accessor + 1 + logical
        definition = gltf["accessors"][accessor_index]
        if definition != {
            "bufferView": len(source_views) + 1 + logical,
            "componentType": 5126,
            "count": len(timeline),
            "type": "VEC4",
        }:
            raise ValidationError(
                f"rotation accessor {logical} definition differs"
            )

    node_names = [str(node.get("name")) for node in gltf["nodes"]]
    node_by_name: dict[str, int] = {}
    for index, name in enumerate(node_names):
        if name in node_by_name:
            raise ValidationError(f"duplicate glTF node name {name!r}")
        node_by_name[name] = index
    expected_channels = []
    for logical, bone in enumerate(EXPECTED_BONES):
        for family in ("referee_high", "referee_low"):
            name = f"{family}:{bone}"
            if name not in node_by_name:
                raise ValidationError(f"missing referee node {name}")
            node = gltf["nodes"][node_by_name[name]]
            if "matrix" in node:
                raise ValidationError(f"animated referee node {name} has matrix")
            expected_channels.append({
                "sampler": logical,
                "target": {
                    "node": node_by_name[name],
                    "path": "rotation",
                },
            })
    if channels != expected_channels:
        raise ValidationError("high/low referee target binding differs")

    varying_tracks = 0
    maximum_unit_error = 0.0
    minimum_adjacent_dot = 1.0
    for logical, sampler in enumerate(samplers):
        rotations = accessor_values(
            gltf, binary, int(sampler["output"]), 4
        )
        if len(rotations) != len(times):
            raise ValidationError("rotation/time key counts differ")
        if any(
            max(values[lane] for values in rotations) -
            min(values[lane] for values in rotations) > 1.0e-5
            for lane in range(4)
        ):
            varying_tracks += 1
        for index, value in enumerate(rotations):
            norm = math.sqrt(sum(component * component for component in value))
            maximum_unit_error = max(maximum_unit_error, abs(norm - 1.0))
            if not math.isfinite(norm) or abs(norm - 1.0) > 2.0e-6:
                raise ValidationError(
                    f"glTF rotation {logical}/{index} is not unit length"
                )
            if index:
                dot = sum(
                    a * b for a, b in zip(rotations[index - 1], value)
                )
                minimum_adjacent_dot = min(minimum_adjacent_dot, dot)
                if dot < -1.0e-6:
                    raise ValidationError("rotation sign continuity differs")
    if varying_tracks < 15:
        raise ValidationError("too few referee tracks vary")

    details = report.get("animation", {})
    expected_scope = {
        "target_family": "referee_high_and_low",
        "logical_channel_count": 25,
        "target_node_count": 50,
        "bake_rate_hz": BAKE_RATE,
        "key_count": len(timeline),
        "first_time_seconds": timeline[0],
        "last_time_seconds": timeline[-1],
        "native_key_sample_count": len(timeline) * 25,
        "local_rotation_tracks_only": True,
        "root_translation_emitted": False,
        "trajectory_bytes_present_but_omitted": 368,
        "title_policy": {
            "flags": 2,
            "looping_flag_bit_0": False,
            "mirrored_flag_bit_2": False,
            "time_policy": "non_looping_final_frame_clamp",
        },
        "ownership_boundary": EXPECTED_OWNERSHIP_BOUNDARY,
        "root_motion_pipeline_boundary":
            EXPECTED_ROOT_MOTION_PIPELINE_BOUNDARY,
    }
    for key, expected in expected_scope.items():
        if details.get(key) != expected:
            raise ValidationError(f"animation scope {key} differs")

    normalization = details.get("normalization", {})
    if set(normalization) != {
        "maximum_source_norm_deviation",
        "maximum_normalization_lane_delta",
        "maximum_original_matrix_element_delta_after_normalization",
        "sign_continuity_flip_count",
        "twist_is_xbox_bit_exact",
    } or normalization.get("twist_is_xbox_bit_exact") is not False or (
        int(normalization.get("sign_continuity_flip_count", -1)) != 0
    ) or not (
        0.0 < float(normalization["maximum_source_norm_deviation"]) < 0.001
        and 0.0 < float(normalization[
            "maximum_normalization_lane_delta"
        ]) < 0.001
        and 0.0 < float(normalization[
            "maximum_original_matrix_element_delta_after_normalization"
        ]) < 0.001
    ):
        raise ValidationError("normalization boundary differs")
    representation = details.get("between_key_representation", {})
    degrees = float(representation.get(
        "maximum_angular_error_degrees", math.nan
    ))
    radians = float(representation.get(
        "maximum_angular_error_radians", math.nan
    ))
    maximum_case = representation.get("maximum_case")
    if not (
        int(representation.get("probe_count", -1)) ==
            (len(times) - 1) * 3 * 25
        and representation.get("fractions_per_interval") == [0.25, 0.5, 0.75]
        and representation.get("interpretation") ==
            "observed grid error, not a continuous mathematical bound"
        and 0.0 < degrees < MAXIMUM_OBSERVED_GRID_ERROR_DEGREES
        and math.isclose(math.degrees(radians), degrees,
                         rel_tol=1.0e-12, abs_tol=1.0e-12)
        and maximum_case == {
            "channel": 14,
            "interval": 159,
            "fraction": 0.5,
            "time_seconds": f32(1.3291666507720947),
        }
    ):
        raise ValidationError("between-key representation boundary differs")

    expected_animation_extras = {
        "bake_rate_hz": BAKE_RATE,
        "key_count": len(timeline),
        "source_clip": clip,
        "local_rotation_tracks_only": True,
        "root_translation_emitted": False,
        "trajectory_bytes_present_but_omitted": 368,
        "title_policy": expected_scope["title_policy"],
        "ownership_boundary": EXPECTED_OWNERSHIP_BOUNDARY,
        "root_motion_pipeline_boundary":
            EXPECTED_ROOT_MOTION_PIPELINE_BOUNDARY,
        "normalization": normalization,
        "between_key_representation": representation,
        "portme": EXPECTED_PORTME,
    }
    if animation.get("extras") != expected_animation_extras:
        raise ValidationError("animation extras differ from manifest evidence")
    expected_title_witness = {
        "clip": EXPECTED_CLIP,
        "native_key_samples": len(timeline) * 25,
        "bake_rate_hz": BAKE_RATE,
        "local_rotation_tracks_only": True,
        "root_translation_emitted": False,
        "trajectory_bytes_present_but_omitted": 368,
        "ownership_report": {
            "path": str(args.ownership_report),
            "sha256": sha256_file(args.ownership_report),
        },
        "ownership_boundary": EXPECTED_OWNERSHIP_BOUNDARY,
        "root_trajectory_report": expected_root_source,
        "render_root_report": expected_render_source,
        "root_motion_pipeline_boundary":
            EXPECTED_ROOT_MOTION_PIPELINE_BOUNDARY,
        "portme": EXPECTED_PORTME,
    }
    expected_root_extras = dict(source_gltf.get("extras", {}))
    expected_root_extras["title_animation_witness"] = expected_title_witness
    if gltf.get("extras") != expected_root_extras:
        raise ValidationError("glTF title witness provenance differs")
    expected_asset = dict(source_gltf["asset"])
    expected_asset["generator"] = (
        "nfl_referee_animated_gltf.py "
        "(meter skin + recovered native pose)"
    )
    if gltf.get("asset") != expected_asset:
        raise ValidationError("glTF asset provenance differs")

    print(
        "NFL_REFEREE_ANIMATED_GLTF_STRUCTURAL_PASS "
        f"clip={EXPECTED_CLIP} keys={len(times)} channels=25 targets=50 "
        f"varying={varying_tracks} max_unit_error={maximum_unit_error:.9g} "
        f"min_adjacent_dot={minimum_adjacent_dot:.9g}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

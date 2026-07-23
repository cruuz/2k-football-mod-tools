#!/usr/bin/env python3
"""Structural and provenance validator for the APF player_shadow glTF pair."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path
from typing import Any

import apf_player_shadow_gltf as export


class ValidationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path} is not an object")
    return value


COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
FORMATS = {5121: "B", 5123: "H", 5125: "I", 5126: "f"}
SIZES = {5121: 1, 5123: 2, 5125: 4, 5126: 4}


def accessor(document: dict[str, Any], binary: bytes, index: int
             ) -> list[tuple[int | float, ...]]:
    item = document["accessors"][index]
    view = document["bufferViews"][item["bufferView"]]
    component = item["componentType"]
    count = item["count"]
    width = COMPONENTS[item["type"]]
    stride = view.get("byteStride", SIZES[component] * width)
    offset = view.get("byteOffset", 0) + item.get("byteOffset", 0)
    result: list[tuple[int | float, ...]] = []
    for row in range(count):
        result.append(struct.unpack_from("<" + FORMATS[component] * width,
                                         binary, offset + row * stride))
    return result


def vec_close(a: tuple[int | float, ...], b: tuple[float, ...],
              tolerance: float = 1e-7) -> bool:
    return all(abs(float(left) - right) <= tolerance
               for left, right in zip(a, b, strict=True))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-gltf", type=Path, default=Path(
        "assets/intermediate/apf2k8/models/1310_0415_player_shadow.gltf"))
    parser.add_argument("--source-bin", type=Path, default=Path(
        "assets/intermediate/apf2k8/models/1310_0415_player_shadow.bin"))
    parser.add_argument("--static-gltf", type=Path, default=Path(export.STATIC_CANONICAL))
    parser.add_argument("--animated-gltf", type=Path,
                        default=Path(export.ANIMATED_CANONICAL))
    parser.add_argument("--report", type=Path, default=Path(export.REPORT_CANONICAL))
    parser.add_argument("--joints-tsv", type=Path, default=Path(
        "reports/assets/apf_player_shadow_skin_joints.tsv"))
    parser.add_argument("--vertices-tsv", type=Path, default=Path(
        "reports/assets/apf_player_shadow_skin_vertices.tsv"))
    parser.add_argument("--bindings-tsv", type=Path, default=Path(
        "reports/assets/apf_animation_export_candidate_bindings.tsv"))
    parser.add_argument("--mocap", type=Path, default=Path(
        "reports/assets/apf_mocap_inventory.json"))
    parser.add_argument("--corpus", type=Path, default=Path(
        "reports/assets/apf_mocap_corpus.bin"))
    args = parser.parse_args()

    static_bin_path = args.static_gltf.with_suffix(".bin")
    animated_bin_path = args.animated_gltf.with_suffix(".bin")
    for path in (args.source_gltf, args.source_bin, args.static_gltf,
                 static_bin_path, args.animated_gltf, animated_bin_path,
                 args.report, args.joints_tsv, args.vertices_tsv,
                 args.bindings_tsv, args.mocap, args.corpus):
        require(path.is_file(), f"missing {path}")

    source_doc = load(args.source_gltf)
    static_doc = load(args.static_gltf)
    animated_doc = load(args.animated_gltf)
    report = load(args.report)
    source_bin = args.source_bin.read_bytes()
    static_bin = static_bin_path.read_bytes()
    animated_bin = animated_bin_path.read_bytes()
    joints = export.read_rows(args.joints_tsv)
    vertices = export.read_rows(args.vertices_tsv)
    bindings = export.read_rows(args.bindings_tsv)

    require(report["schema"] == export.SCHEMA, "report schema changed")
    require(report["joined_proof_gate"]["passed"] is True, "proof join failed")
    require(all(report["joined_proof_gate"]["checks"].values()),
            "a joined proof check failed")
    for source_name in ("host_runtime_test", "host_screenshot_test"):
        source = report["inputs"][source_name]
        source_path = Path(source["path"])
        require(source_path.is_file(), f"missing reported {source_name}")
        require(source["sha256"] == digest(source_path),
                f"reported {source_name} hash mismatch")
    static_output = report["static_canonical_contract"]["output"]
    animated_output = report["animated_derivative_contract"]["output"]
    require(static_output["gltf"]["sha256"] == digest(args.static_gltf),
            "static glTF report hash mismatch")
    require(static_output["bin"]["sha256"] == digest(static_bin_path),
            "static BIN report hash mismatch")
    require(animated_output["gltf"]["sha256"] == digest(args.animated_gltf),
            "animated glTF report hash mismatch")
    require(animated_output["bin"]["sha256"] == digest(animated_bin_path),
            "animated BIN report hash mismatch")

    require(static_doc["asset"]["version"] == "2.0", "not glTF 2.0")
    require(static_doc["buffers"] == [{
        "byteLength": len(static_bin), "uri": static_bin_path.name,
    }], "static buffer declaration mismatch")
    require(len(static_bin) == 16248, "static binary size changed")
    require(len(static_doc["accessors"]) == 5, "static accessor count changed")
    require(len(static_doc["bufferViews"]) == 5, "static view count changed")
    require(len(static_doc["nodes"]) == 23, "static node count changed")
    require(len(static_doc["skins"]) == 1, "static skin count changed")
    require("animations" not in static_doc, "static canonical has animation")

    # The source geometry layout remains the first 7,884 output bytes.  Index
    # bytes are identical; position bytes are exactly source float32 * 0.01.
    expected_positions = b"".join(
        struct.pack("<f", export.f32(value * 0.01))
        for value in struct.unpack_from("<1053f", source_bin, 0)
    )
    require(static_bin[:4212] == expected_positions,
            "meter-scaled position prefix changed")
    require(static_bin[4212:7884] == source_bin[4212:7884],
            "triangle index prefix changed")
    require(static_doc["accessors"][1] == source_doc["accessors"][1],
            "topology accessor changed")

    positions = accessor(static_doc, static_bin, 0)
    indices = accessor(static_doc, static_bin, 1)
    joint_values = accessor(static_doc, static_bin, 2)
    weights = accessor(static_doc, static_bin, 3)
    matrices = accessor(static_doc, static_bin, 4)
    require(len(positions) == 351 and len(indices) == 918, "geometry counts changed")
    require(max(max(abs(float(lane)) for lane in row) for row in positions) < 1.1,
            "positions are not meter scale")
    require(len(joint_values) == len(weights) == len(vertices) == 351,
            "influence counts changed")
    for index, row in enumerate(vertices):
        expected_joint = int(row["joint"])
        require(joint_values[index] == (expected_joint, 0, 0, 0),
                f"JOINTS_0 mismatch at vertex {index}")
        require(weights[index] == (1.0, 0.0, 0.0, 0.0),
                f"WEIGHTS_0 mismatch at vertex {index}")

    skin = static_doc["skins"][0]
    require(skin["joints"] == list(range(1, 22)), "skin joint order changed")
    require(skin["skeleton"] == 1 and skin["inverseBindMatrices"] == 4,
            "skin root/IBM binding changed")
    require(static_doc["nodes"][0]["children"] == [1, 22],
            "external-root children changed")
    global_translation: list[tuple[float, float, float]] = []
    for index, row in enumerate(joints):
        node = static_doc["nodes"][1 + index]
        require(node["name"] == row["name"], f"joint name mismatch {index}")
        require(node["rotation"] == [0.0, 0.0, 0.0, 1.0],
                f"bind rotation mismatch {index}")
        local = tuple(float(value) for value in node["translation"])
        parent = int(row["parent"])
        if parent < 0:
            current = local
        else:
            current = tuple(global_translation[parent][lane] + local[lane]
                            for lane in range(3))
        global_translation.append(current)
        matrix = matrices[index]
        require(all(float(matrix[axis]) == (1.0 if axis in (0, 5, 10, 15) else
                                             float(matrix[axis]))
                    for axis in (0, 5, 10, 15)), "IBM diagonal changed")
        for lane, element in enumerate((12, 13, 14)):
            require(abs(current[lane] + float(matrix[element])) < 2e-7,
                    f"IBM does not cancel bind global at joint {index}")

    require(animated_bin[:len(static_bin)] == static_bin,
            "animated binary does not retain exact static prefix")
    require(animated_doc["meshes"] == static_doc["meshes"],
            "animated derivative changed mesh")
    require(animated_doc["nodes"] == static_doc["nodes"],
            "animated derivative changed nodes")
    require(animated_doc["skins"] == static_doc["skins"],
            "animated derivative changed skin")
    require(animated_doc["accessors"][:5] == static_doc["accessors"],
            "animated derivative changed static accessors")
    require(animated_doc["bufferViews"][:5] == static_doc["bufferViews"],
            "animated derivative changed static views")
    require(len(animated_doc["animations"]) == 1, "animation count changed")
    animation = animated_doc["animations"][0]
    require(len(animation["channels"]) == len(animation["samplers"]) == 24,
            "glTF animation channel count changed")
    require(all(item["interpolation"] == "LINEAR"
                for item in animation["samplers"]), "non-LINEAR sampler")
    time_accessors = {item["input"] for item in animation["samplers"]}
    require(len(time_accessors) == 1, "animation does not share one time accessor")
    time_accessor = next(iter(time_accessors))
    times = [float(row[0]) for row in accessor(animated_doc, animated_bin,
                                                time_accessor)]
    require(len(times) == export.BAKE_COUNT, "time key count changed")
    require(times == [export.f32(index / export.BAKE_RATE)
                      for index in range(export.BAKE_COUNT)], "time grid changed")
    require(times[-1] == export.f32(7.7166666984558105), "duration changed")

    channel_map: dict[tuple[int, str], int] = {}
    for channel in animation["channels"]:
        target = channel["target"]
        key = (target["node"], target["path"])
        require(key not in channel_map, f"duplicate animation target {key}")
        channel_map[key] = animation["samplers"][channel["sampler"]]["output"]
    require((0, "translation") in channel_map, "external trajectory absent")

    mocap = load(args.mocap)
    selected = [entry for entry in mocap["resources"]
                if entry["name"] == export.SELECTED_CLIP]
    require(len(selected) == 1, "selected clip is not unique")
    clip = selected[0]
    corpus = args.corpus.read_bytes()
    motion_region = export.region(clip, "packed_motion")
    root_region = export.region(clip, "root_vector_samples")
    base = clip["corpus_offset"]
    motion = corpus[base + motion_region["offset"]:
                    base + motion_region["offset"] + motion_region["length"]]
    root_bytes = corpus[base + root_region["offset"]:
                        base + root_region["offset"] + root_region["length"]]
    local_bind = [(float(row["local_bind_x_cm"]),
                   float(row["local_bind_y_cm"]),
                   float(row["local_bind_z_cm"])) for row in joints]
    sampler = export.ClipSampler(motion, root_bytes, local_bind)

    rotation_rows = [row for row in bindings if row["rotation_logical_index"]]
    translation_rows = [row for row in bindings if row["translation_logical_index"]]
    require(len(rotation_rows) == 17 and len(translation_rows) == 6,
            "binding counts changed")
    for row in rotation_rows:
        joint = int(row["matrix_row"])
        logical = int(row["rotation_logical_index"])
        key = (1 + joint, "rotation")
        require(key in channel_map, f"rotation channel absent for joint {joint}")
        track = accessor(animated_doc, animated_bin, channel_map[key])
        require(len(track) == export.BAKE_COUNT, "rotation key count changed")
        for value in track:
            require(abs(math.sqrt(sum(float(lane) ** 2 for lane in value)) - 1.0) < 2e-6,
                    "stored quaternion is not normalized")
        for frame in range(116):
            actual = tuple(float(value) for value in track[frame * 8])
            expected = sampler.rotation(logical, float(frame))
            require(export.angular_error_degrees(actual, expected) < 1e-5,
                    f"stored source rotation key mismatch joint={joint} frame={frame}")
    for row in translation_rows:
        joint = int(row["matrix_row"])
        logical = int(row["translation_logical_index"])
        key = (1 + joint, "translation")
        require(key in channel_map, f"translation channel absent for joint {joint}")
        track = accessor(animated_doc, animated_bin, channel_map[key])
        require(len(track) == export.BAKE_COUNT, "translation key count changed")
        for frame in range(116):
            expected = sampler.bone_translation_m(joint, logical, float(frame))
            require(vec_close(track[frame * 8], expected, 2e-7),
                    f"stored source translation mismatch joint={joint} frame={frame}")
    root_track = accessor(animated_doc, animated_bin,
                          channel_map[(0, "translation")])
    require(len(root_track) == export.BAKE_COUNT, "external-root key count changed")
    require(vec_close(root_track[-1], (-0.0003125, 1.0325, 0.0), 2e-7),
            "external-root runtime endpoint changed")

    contract = report["animated_derivative_contract"]
    require(contract["bake_key_count"] == 927 and contract["bake_rate_hz"] == 120,
            "report bake grid changed")
    require(contract["source_keys_retained_inside_duration"] == 116,
            "source-key preservation count changed")
    errors = contract["measured_representation_error"]
    require(errors["probe_grid_hz"] == 960, "probe grid changed")
    require(errors["angular"]["degrees"] < 0.05,
            "observed angular representation error exceeded 0.05 degrees")
    require(errors["bone_translation"]["meters"] < 1e-6 and
            errors["external_root_translation"]["meters"] < 1e-6,
            "observed translation representation error exceeded one micrometer")
    require("neither a continuous bound nor a Xenon-bit-exact bound" in
            errors["scope"], "measurement boundary is absent")

    host = report["native_host_opengl_smoke"]
    require(host["cmake_tests"] == [
        "recovered_apf_player_shadow_host_semantics",
        "host_gl_smoke_recovered_apf_player_shadow_static",
        "host_gl_smoke_recovered_apf_player_shadow_animation",
        "host_gl_recovered_apf_player_shadow_screenshot_semantics",
    ], "host smoke CTest registration changed")
    require(host["host_import_boundary"] == {
        "assimp_join_identical_vertices": True,
        "canonical_vertices": 351,
        "explanation": (
            "Assimp merges duplicate canonical vertices with identical "
            "attributes/influences; the imported indexed topology and skin remain valid"
        ),
        "host_bones": 21,
        "host_triangle_indices": 918,
        "host_vertices": 175,
        "host_weight_records": 181,
    }, "host import boundary changed")
    require(host["runtime_probe"] == {
        "animation_channels_imported": 18,
        "maximum_vertex_delta_m": 0.0449219383,
        "moved_host_vertices": 175,
        "probe_seconds": 2.0,
    }, "host runtime probe changed")
    witness = host["verification_witness_2026_07_10"]
    require(witness["framebuffer"] == [1280, 720] and
            witness["differing_preview_pixels"] == 3546,
            "host framebuffer witness changed")
    require(witness["static_screenshot"]["sha256"] ==
            "464a2e15b83b8441bda6df7ecd992211d6d9cccd7fd0d83c23f63f2141238a26",
            "static screenshot witness changed")
    require(witness["animated_screenshot"]["sha256"] ==
            "e3435b051c40f52c75af357629c59df1d37e058f540b5430c985ff37229b4cf7",
            "animated screenshot witness changed")
    require(report["decision"]["native_host_opengl_smoke_covered"] is True,
            "host OpenGL smoke decision changed")

    print(
        "APF_PLAYER_SHADOW_GLTF_STRUCTURAL_VALIDATION_PASS "
        "vertices=351 triangles=306 joints=21 one_hot=351 keys=927 channels=24 "
        f"max_angle_deg={errors['angular']['degrees']:.9g}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

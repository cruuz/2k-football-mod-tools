#!/usr/bin/env python3
"""Prove APF's exact frontend animation transform/glTF boundary.

This is a read-only join over canonical XEX traces and extracted resources.  It
does not emit a skinned model: palette and inverse-bind ownership remain a
separate gate.  The output closes only quaternion lane order, coordinate/unit
semantics, and the selected clip's external-root placement.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import struct
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "apf_animation_transform_semantics/v1"
EXPECTED_XEX_MD5 = "217eea6084c3d03f0f1143802b1f5636"
EXPECTED_XEX_SHA256 = "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
SELECTED_CLIP = "mnu_stn_01_070130_01_lg"
GLTF_SPEC = "https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html"
XENIA_VMX_SOURCE = (
    "https://github.com/xenia-project/xenia/blob/"
    "95a5c3ee250f80c3b9d139658649d9ffb6db3eec/"
    "src/xenia/cpu/ppc/ppc_emit_altivec.cc#L1216-L1227"
)


TRACE_WORDS = {
    # Packed mode-0 output and matrix builder.
    0x846384C0: 0x19610710,
    0x84639500: 0x180407F0,
    0x84639504: 0x18CB0350,
    0x84639508: 0x193E03D0,
    0x8463954C: 0x100A20C3,
    0x84639554: 0x11A0000A,
    0x84639558: 0x196D0250,
    0x84639578: 0x140D0090,
    0x8463957C: 0x18F66A50,
    0x84639580: 0x156D5890,
    0x8463958C: 0x154A3890,
    0x84639594: 0x19940350,
    0x84639598: 0x18F80390,
    0x8463959C: 0x10094B2F,
    0x846395A0: 0x118B500A,
    0x846395A4: 0x116B504A,
    0x846395A8: 0x100901EF,
    0x846395C0: 0x180867D0,
    0x846395C4: 0x19446710,
    0x846395C8: 0x18426710,
    0x846395CC: 0x18045F50,
    0x846395D0: 0x19425F50,
    0x846395E0: 0x19885F50,
    0x846395EC: 0x7DA019CE,
    0x846395F4: 0x100C20AA,
    0x846395F8: 0x11AA1FEA,
    0x846395FC: 0x118132EA,
    0x84639604: 0x7C0049CE,
    0x84639608: 0x7DA041CE,
    0x8463960C: 0x7D8039CE,
    # Root sampler and asymmetric interval.
    0x84638730: 0x81230024,
    0x846387AC: 0xC00B0C30,
    0x846387B0: 0xEDAD0032,
    0x846392DC: 0x4BFFF445,
    0x846392E8: 0x4BFFF439,
    0x846392F8: 0xEC006828,
    0x84639308: 0xEC006828,
    0x84639314: 0x7D6A5850,
    0x84639330: 0xC0060000,
    0x84639338: 0xD0060000,
    # Exact frontend root construction and hierarchy handoff.
    0x84A11B8C: 0x7F5F582E,
    0x84A11B98: 0x480925A1,
    0x84A11C10: 0x4BC28711,
    0x84A11C30: 0x4BC278A1,
    0x84A11CC4: 0xC02B09A0,
    0x84A11CC8: 0x4BC27601,
    0x84A11CD0: 0x814100B0,
    0x84A11CD8: 0x7D7F582E,
    0x84A11CDC: 0x7C8B5214,
    0x84A11CE0: 0x481330B1,
    0x84A11D00: 0x101F58C3,
    0x84A11D08: 0xEC005FFA,
    0x84A11D14: 0xEDAD5FFA,
    0x84A11D24: 0xED8C5FFA,
    0x84A11D30: 0xD0010090,
    0x84A11D3C: 0xD0010094,
    0x84A11D48: 0xD0010098,
    0x84A11D4C: 0x480924A5,
    0x84A11D60: 0x48092529,
    # Live scale and Y-axis turn helpers.
    0x84AA4138: 0x896300D9,
    0x84AA4150: 0xC00BE120,
    0x84AA41F8: 0x896300D9,
    0x84AA4234: 0xC00BE120,
    0x84B44D90: 0x548A043E,
    0x84B44E18: 0xD1430000,
    0x84B44E20: 0xD1430008,
    0x84B44E40: 0xD1430010,
    0x84B44E4C: 0xD1430018,
    0x84B44E68: 0xD1430020,
    0x84B44E70: 0xD1430028,
    0x84B44E80: 0xD1830030,
    0x84B44E88: 0xD0030038,
    0x84B44E8C: 0x4E800020,
    # Local translation plus hierarchy record, then local * parent.
    0x84B0FB24: 0x10C050C3,
    0x84B0FB2C: 0x18C1EF10,
    0x84B0FB4C: 0x10E7300A,
    0x84B0FBD8: 0x7C0021CE,
    0x84B0FBF0: 0x4E800020,
}


VMX_EXPECTED = {
    0x84639504: ("vpermwi128", "v6,v0,171"),
    0x84639558: ("vpermwi128", "v11,v0,45"),
    0x8463959C: ("vnmsubfp", "v0,v9,v12,v9"),
    0x846395A8: ("vnmsubfp", "v0,v9,v7,v0"),
    0x846395C0: ("vrlimi128", "v0,v12,8,3"),
    0x846395CC: ("vrlimi128", "v0,v11,4,1"),
    0x846395FC: ("vsel", "v12,v1,v6,v11"),
    0x84A11D00: ("lvx128", "v0,r31,r11"),
    0x84B0FB4C: ("vaddfp", "v7,v7,v6"),
}


class SemanticsError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SemanticsError(message)


def digest(path: Path, algorithm: str = "sha256") -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path} is not a JSON object")
    return value


def trace_words(path: Path) -> dict[int, int]:
    result: dict[int, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[0] == "RAW32":
            result[int(fields[1], 16)] = int(fields[2], 16)
    return result


def trace_ranges(path: Path, words: dict[int, int]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) < 5 or fields[0] != "RAW_RANGE":
            continue
        first, after = int(fields[1], 16), int(fields[2], 16)
        declared_bytes = int(fields[3].split("=", 1)[1])
        declared_sha = fields[4].split("=", 1)[1]
        require(after - first == declared_bytes, "trace range byte count mismatch")
        payload = b"".join(words[address].to_bytes(4, "big")
                           for address in range(first, after, 4))
        require(len(payload) == declared_bytes, "trace range has missing RAW32 words")
        actual_sha = hashlib.sha256(payload).hexdigest()
        require(actual_sha == declared_sha, f"trace range hash mismatch at 0x{first:08X}")
        result.append({
            "first": f"0x{first:08X}",
            "after_last": f"0x{after:08X}",
            "bytes": declared_bytes,
            "sha256": actual_sha,
        })
    require(len(result) == 8, "unexpected transform trace range count")
    return result


def vmx_rows(path: Path) -> dict[int, tuple[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    return {
        int(row["address"], 16): (row["mnemonic"], row["operands"])
        for row in rows
    }


def f32(value: float) -> float:
    return struct.unpack(">f", struct.pack(">f", value))[0]


def signed20(value: int) -> int:
    value &= 0xFFFFF
    return value - (0x100000 if value & 0x80000 else 0)


def decode_mode0(encoded: bytes) -> tuple[float, float, float, float]:
    require(len(encoded) == 8, "mode-0 record is not eight bytes")
    bits = int.from_bytes(encoded, "big")
    stored = [
        signed20(bits) * (23.0 / 16777216.0),
        signed20(bits >> 20) * (23.0 / 16777216.0),
        signed20(bits >> 40) * (23.0 / 16777216.0),
    ]
    radicand = 1.0 - sum(component * component for component in stored)
    require(radicand >= 0.0, "shipped mode-0 record has negative ideal radicand")
    stored.append(math.sqrt(radicand))
    rotate = (bits >> 60) & 3
    return tuple(stored[(lane + rotate) & 3] for lane in range(4))  # type: ignore[return-value]


def vpermwi(vector: Iterable[float], immediate: int) -> list[float]:
    source = list(vector)
    return [
        source[(immediate >> 6) & 3], source[(immediate >> 4) & 3],
        source[(immediate >> 2) & 3], source[immediate & 3],
    ]


def vrlimi(destination: Iterable[float], source: Iterable[float],
            mask: int, rotate: int) -> list[float]:
    result = list(destination)
    original = list(source)
    rotated = original[rotate:] + original[:rotate]
    for lane in range(4):
        if mask & (1 << (3 - lane)):
            result[lane] = rotated[lane]
    return result


def apf_matrix_builder_rotation(lanes: Iterable[float]) -> list[float]:
    """Symbolically execute 0x84639554..0x846395F8 for a present rotation."""
    q = list(lanes)
    twice = [2.0 * value for value in q]
    product11 = [left * right for left, right in zip(twice, vpermwi(q, 0x2D))]
    product10 = [q[0] * right for right in vpermwi(twice, 0x36)]
    squares2 = [left * right for left, right in zip(twice, q)]
    perm12 = vpermwi(squares2, 0xB4)
    perm7 = vpermwi(squares2, 0xD8)
    base = [1.0 - perm12[i] - perm7[i] for i in range(3)] + [0.0]
    plus = [product11[i] + product10[i] for i in range(4)]
    minus = [product11[i] - product10[i] for i in range(4)]
    row2 = vrlimi(base, plus, 8, 3)
    row0 = vrlimi(base, plus, 4, 0)
    middle = vrlimi(base, plus, 2, 0)
    row2 = vrlimi(row2, minus, 4, 1)
    row0 = vrlimi(row0, minus, 2, 1)
    row1 = vrlimi(middle, minus, 8, 1)
    return row0 + row1 + row2


def gltf_rotation_from_xyzw(x: float, y: float, z: float, w: float) -> list[float]:
    # Column-major glTF matrix, excluding the affine fourth lane of each column.
    return [
        1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y + w * z),
        2.0 * (x * z - w * y), 0.0,
        2.0 * (x * y - w * z), 1.0 - 2.0 * (x * x + z * z),
        2.0 * (y * z + w * x), 0.0,
        2.0 * (x * z + w * y), 2.0 * (y * z - w * x),
        1.0 - 2.0 * (x * x + y * y), 0.0,
    ]


def determinant3(column_major: list[float]) -> float:
    a, d, g = column_major[0], column_major[1], column_major[2]
    b, e, h = column_major[4], column_major[5], column_major[6]
    c, f, i = column_major[8], column_major[9], column_major[10]
    return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)


def reflected_x_matrix(matrix: list[float]) -> list[float]:
    signs = (-1.0, 1.0, 1.0)
    result = matrix.copy()
    for column in range(3):
        for row in range(3):
            result[column * 4 + row] *= signs[column] * signs[row]
    return result


def region(resource: dict[str, Any], role: str) -> dict[str, Any]:
    matches = [entry for entry in resource["regions"] if entry["role"] == role]
    require(len(matches) == 1, f"{resource['name']} has ambiguous {role} region")
    return matches[0]


def sample_root(records: list[tuple[int, int, int]], seconds: float,
                rate: int, time_scale: float) -> tuple[float, float, float]:
    coordinate = f32(f32(f32(float(rate)) * f32(seconds)) * f32(time_scale))
    if coordinate >= float(len(records) - 1):
        left = right = records[-1]
        fraction = 0.0
    else:
        index = math.trunc(coordinate)
        left, right = records[index], records[index + 1]
        fraction = f32(coordinate - float(index))
    return tuple(
        f32(f32(f32(float(right[lane] - left[lane])) * fraction +
                f32(float(left[lane]))) * f32(0.125))
        for lane in range(3)
    )  # type: ignore[return-value]


def fmt(value: float) -> str:
    if value == 0.0:
        return "0"
    return format(value, ".10g")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xex", type=Path,
                        default=Path("extracted/All-Pro Football 2K8 (USA)/default.xex"))
    parser.add_argument("--trace", type=Path, default=Path(
        "reports/assets/apf_animation_transform_semantics_ghidra/animation_transform_semantics_trace.txt"))
    parser.add_argument("--pseudo", type=Path, default=Path(
        "reports/assets/apf_animation_transform_semantics_ghidra/animation_transform_semantics_focused_pseudo_c.c"))
    parser.add_argument("--vmx", type=Path, default=Path(
        "reports/assets/apf_animation_transform_semantics_ghidra/animation_transform_semantics_vmx128.tsv"))
    parser.add_argument("--readiness", type=Path,
                        default=Path("reports/assets/apf_animation_export_readiness.json"))
    parser.add_argument("--packed", type=Path,
                        default=Path("reports/assets/apf_packed_pose_decoder_inventory.json"))
    parser.add_argument("--mocap", type=Path,
                        default=Path("reports/assets/apf_mocap_inventory.json"))
    parser.add_argument("--corpus", type=Path,
                        default=Path("reports/assets/apf_mocap_corpus.bin"))
    parser.add_argument("--scenes", type=Path,
                        default=Path("reports/assets/apf_scene_inventory.json"))
    parser.add_argument("--lineage", type=Path,
                        default=Path("reports/assets/motion_lineage_inventory.json"))
    parser.add_argument("--nfl-axis", type=Path,
                        default=Path("reports/assets/nfl_axis_root_motion.json"))
    parser.add_argument("--nfl-shadow", type=Path, default=Path(
        "assets/intermediate/nfl2k5/models/0346_0060_shadow_low.gltf"))
    parser.add_argument("--xenon-recomp", type=Path, default=Path(
        "tools/vendor/XenonRecomp/XenonRecomp/recompiler.cpp"))
    parser.add_argument("--json", type=Path,
                        default=Path("reports/assets/apf_animation_transform_semantics.json"))
    parser.add_argument("--root-tsv", type=Path,
                        default=Path("reports/assets/apf_animation_transform_root_samples.tsv"))
    args = parser.parse_args()

    inputs = [
        args.xex, args.trace, args.pseudo, args.vmx, args.readiness, args.packed,
        args.mocap, args.corpus, args.scenes, args.lineage, args.nfl_axis,
        args.nfl_shadow, args.xenon_recomp,
    ]
    for path in inputs:
        require(path.is_file(), f"missing input {path}")
    require(digest(args.xex, "md5") == EXPECTED_XEX_MD5, "unexpected APF XEX MD5")
    require(digest(args.xex) == EXPECTED_XEX_SHA256, "unexpected APF XEX SHA-256")

    trace_text = args.trace.read_text(encoding="utf-8")
    require(f"Program MD5: {EXPECTED_XEX_MD5}" in trace_text, "trace program mismatch")
    words = trace_words(args.trace)
    for address, expected in TRACE_WORDS.items():
        require(words.get(address) == expected, f"trace word mismatch at 0x{address:08X}")
    ranges = trace_ranges(args.trace, words)
    vmx = vmx_rows(args.vmx)
    for address, expected in VMX_EXPECTED.items():
        require(vmx.get(address) == expected, f"VMX decode mismatch at 0x{address:08X}")

    xenon_text = args.xenon_recomp.read_text(encoding="utf-8")
    require("case PPC_INST_VPERMWI128:" in xenon_text, "missing vpermwi128 corroboration")
    require("case PPC_INST_VRLIMI128:" in xenon_text, "missing vrlimi128 corroboration")

    readiness = load_json(args.readiness)
    packed = load_json(args.packed)
    mocap = load_json(args.mocap)
    scenes = load_json(args.scenes)
    lineage = load_json(args.lineage)
    nfl_axis = load_json(args.nfl_axis)
    nfl_shadow = load_json(args.nfl_shadow)
    require(readiness["schema"] == "apf_animation_export_readiness/v1", "readiness schema")
    require(packed["schema"] == "apf_packed_pose_decoder/v1", "packed schema")
    require(mocap["schema"] == "apf_mocap_inventory/v1", "mocap schema")
    require(scenes["schema"].startswith("apf_scene_inventory/"), "scene schema")
    require(lineage["schema"] == "cross_title_motion_lineage/v1", "lineage schema")
    require(nfl_axis["schema"] == "nfl2k5_axis_root_motion/v1", "NFL axis schema")
    require(readiness["selected_clip_candidate"]["name"] == SELECTED_CLIP,
            "readiness selected clip changed")

    selected_matches = [resource for resource in mocap["resources"]
                        if resource["name"] == SELECTED_CLIP]
    require(len(selected_matches) == 1, "selected clip is not unique")
    selected = selected_matches[0]
    require(selected["sample_count"] == 117 and selected["sample_rate_hz"] == 15,
            "selected sampling grid changed")
    require(selected["mirror_flag"] is False and selected["root_sample_stride"] == 6,
            "selected root layout changed")
    corpus = args.corpus.read_bytes()

    # Exhaustively execute the recovered matrix algebra over every standard
    # shipped mode-0 record, then compare it to glTF's XYZW matrix equation.
    max_matrix_error = 0.0
    max_norm_error = 0.0
    max_det_error = 0.0
    max_mirror_error = 0.0
    mode0_record_count = 0
    selected_mode0_record_count = 0
    for clip in mocap["resources"]:
        if clip["kind"] != "full_clip" or clip["name"] == "hand_pose":
            continue
        motion = region(clip, "packed_motion")
        require(motion["length"] == clip["sample_count"] * 23 * 8,
                f"{clip['name']} packed layout changed")
        start = clip["corpus_offset"] + motion["offset"]
        for frame in range(clip["sample_count"]):
            for unit in range(17):
                offset = start + (frame * 23 + unit) * 8
                q = decode_mode0(corpus[offset:offset + 8])
                actual = apf_matrix_builder_rotation(q)
                expected = gltf_rotation_from_xyzw(q[1], q[2], q[3], q[0])
                max_matrix_error = max(max_matrix_error,
                                       max(abs(a - b) for a, b in zip(actual, expected)))
                norm = sum(value * value for value in q)
                max_norm_error = max(max_norm_error, abs(norm - 1.0))
                max_det_error = max(max_det_error, abs(determinant3(actual) - 1.0))
                mirrored_q = (q[0], q[1], -q[2], -q[3])
                mirrored = apf_matrix_builder_rotation(mirrored_q)
                reflected = reflected_x_matrix(actual)
                max_mirror_error = max(max_mirror_error,
                                       max(abs(a - b) for a, b in zip(mirrored, reflected)))
                mode0_record_count += 1
                if clip["name"] == SELECTED_CLIP:
                    selected_mode0_record_count += 1
    require(mode0_record_count > 100000, "mode-0 corpus coverage is unexpectedly small")
    require(selected_mode0_record_count == 117 * 17, "selected mode-0 coverage mismatch")
    require(max_matrix_error < 1e-12 and max_mirror_error < 1e-12,
            "APF/glTF quaternion algebra diverged")

    # Root records and exact asymmetric interval rows.
    root_region = region(selected, "root_vector_samples")
    root_start = selected["corpus_offset"] + root_region["offset"]
    root_bytes = corpus[root_start:root_start + root_region["length"]]
    require(len(root_bytes) == 117 * 6, "selected root byte count changed")
    root_records = [struct.unpack_from(">hhh", root_bytes, offset)
                    for offset in range(0, len(root_bytes), 6)]
    root_rows: list[dict[str, Any]] = []
    first = root_records[0]
    for frame, raw in enumerate(root_records):
        sample = tuple(component * 0.125 for component in raw)
        interval = ((raw[0] - first[0]) * 0.125, sample[1],
                    (raw[2] - first[2]) * 0.125)
        root_rows.append({
            "frame": frame,
            "seconds": frame / selected["sample_rate_hz"],
            "raw_x": raw[0], "raw_y": raw[1], "raw_z": raw[2],
            "sample_x_cm": sample[0], "sample_y_cm": sample[1],
            "sample_z_cm": sample[2],
            "interval_x_cm": interval[0], "interval_y_cm": interval[1],
            "interval_z_cm": interval[2], "interval_turn_units": 0,
        })
    duration_sample = sample_root(root_records, selected["duration"],
                                  selected["sample_rate_hz"], selected["time_scale"])
    duration_interval = (
        duration_sample[0] - first[0] * 0.125,
        duration_sample[1],
        duration_sample[2] - first[2] * 0.125,
    )

    # Exact player_shadow coordinate witnesses.
    scene_matches = [scene for scene in scenes["scenes"]
                     if scene["outer_table_index"] == 1310 and
                     scene["inner_file_index"] == 415 and
                     scene["root_name"] == "player_shadow"]
    require(len(scene_matches) == 1, "player_shadow scene is not unique")
    shadow = scene_matches[0]
    require(len(shadow["nodes"]) == 1, "player_shadow node count changed")
    node = shadow["nodes"][0]
    hierarchy = node["hierarchy"]
    named = {record["name"]: record for record in hierarchy["records"]}
    require(named["l_hip_hinge_base"]["vector_a"][0] > 0.0 and
            named["r_hip_hinge_base"]["vector_a"][0] < 0.0,
            "named left/right APF X witness changed")
    require(named["head"]["vector_a"][1] > named["r_knee_hinge"]["vector_a"][1],
            "named APF vertical witness changed")
    bounds = node["meshes"][0]["position"]
    nfl_position = nfl_shadow["accessors"][0]
    require(nfl_shadow["nodes"][0]["name"] == "player_shadow", "NFL shadow identity changed")

    pair_summary = lineage["pair_summary"]
    require(pair_summary["pair_count"] == 7 and pair_summary["paired_frame_count"] == 2591,
            "cross-title lineage coverage changed")
    require(pair_summary["combined_trajectory_best_transform"]["permutation"] == [0, 1, 2] and
            pair_summary["combined_trajectory_best_transform"]["signs"] == [1, 1, 1],
            "cross-title trajectory axis order changed")
    require(lineage["shared_runtime_contracts"]["trajectory"].endswith("exactly 0.125"),
            "cross-title trajectory scale changed")
    require(nfl_axis["proved_contract"]["position_units"].startswith("centimeters"),
            "NFL centimeter proof is absent")
    require(nfl_axis["proved_contract"]["gltf_basis"].startswith(
        "game and glTF are both right-handed and Y-up"), "NFL basis proof changed")

    mode1 = readiness["mode1_translation_recovery"]
    require(mode1["record_count"] == 40434, "mode-1 corpus coverage changed")
    require(mode1["mirror"] == "XOR float sign bit in numbered lane 0 after interpolation",
            "mode-1 mirror lane changed")

    source_paths = {
        "xex": args.xex, "ghidra_trace": args.trace, "ghidra_pseudo": args.pseudo,
        "vmx_disassembly": args.vmx, "prior_readiness": args.readiness,
        "packed_pose_report": args.packed, "mocap_inventory": args.mocap,
        "mocap_corpus": args.corpus, "scene_inventory": args.scenes,
        "cross_title_lineage": args.lineage, "nfl_axis_report": args.nfl_axis,
        "nfl_shadow_gltf": args.nfl_shadow, "xenon_recomp_semantics": args.xenon_recomp,
    }

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "program": {"md5": EXPECTED_XEX_MD5, "sha256": EXPECTED_XEX_SHA256},
        "sources": {
            key: {"path": str(path), "sha256": digest(path)}
            for key, path in source_paths.items()
        },
        "corroborating_primary_sources": {
            "gltf_2_0_specification": GLTF_SPEC,
            "xenia_vpermwi128_commit_source": XENIA_VMX_SOURCE,
            "xenon_recomp_commit": "ddd128bcca99fe8bfbb99bea583c972351fa6ace",
        },
        "trace": {
            "critical_word_count": len(TRACE_WORDS),
            "raw_ranges": ranges,
            "vmx_disassembled_row_count": len(vmx),
        },
        "quaternion_to_gltf": {
            "apf_numbered_lane_roles": {
                "lane0": "quaternion scalar W",
                "lane1": "quaternion vector X",
                "lane2": "quaternion vector Y",
                "lane3": "quaternion vector Z",
            },
            "gltf_xyzw_equation": "rotation = [apf_lane1, apf_lane2, apf_lane3, apf_lane0]",
            "raw_matrix_convention": (
                "APF stores its rotation basis as the first three rows of a row-vector matrix; "
                "that 3x3 numeric sequence is the transposed glTF column-vector basis. Export "
                "TRS rather than copying the complete 16-float runtime matrix because this proof "
                "does not assign the sampled translation vector's fourth lane"
            ),
            "matrix_columns_or_apf_rows": [
                "[1-2*(Y^2+Z^2), 2*(X*Y+W*Z), 2*(X*Z-W*Y), 0]",
                "[2*(X*Y-W*Z), 1-2*(X^2+Z^2), 2*(Y*Z+W*X), 0]",
                "[2*(X*Z+W*Y), 2*(Y*Z-W*X), 1-2*(X^2+Y^2), 0]",
                "[translation_X, translation_Y, translation_Z, runtime_lane3]",
            ],
            "translation_export": (
                "0x846395FC selects sampled translation XYZ unchanged; export those three lanes "
                "as glTF node.translation and let glTF TRS construct the affine fourth component"
            ),
            "mode0_mirror": (
                "APF flips lanes 2/3, which becomes glTF [X,-Y,-Z,W] and exactly "
                "implements F*R*F for lateral reflection F=diag(-1,1,1)"
            ),
            "corpus_validation": {
                "standard_clip_count": 66,
                "mode0_record_count": mode0_record_count,
                "selected_clip_mode0_record_count": selected_mode0_record_count,
                "maximum_matrix_equation_absolute_error": max_matrix_error,
                "maximum_ideal_quaternion_norm_error": max_norm_error,
                "maximum_rotation_determinant_error": max_det_error,
                "maximum_mirror_matrix_absolute_error": max_mirror_error,
            },
            "bit_exact_scope": (
                "lane order and algebra are exact; portable sqrt/interpolation and a host glTF "
                "implementation are not claimed bit-identical to Xenon estimate/FMA rounding"
            ),
        },
        "coordinate_and_unit_contract": {
            "axes": {
                "X": "character lateral; positive X is character-left",
                "Y": "vertical/up",
                "Z": "character/field longitudinal; positive Z is the retained asset-forward side",
            },
            "handedness": "right-handed",
            "raw_position_unit": "centimeter",
            "gltf_conversion": {
                "translation": "retain XYZ and multiply by 0.01",
                "position": "retain XYZ and multiply by 0.01",
                "rotation": "[lane1,lane2,lane3,lane0], with no axis reflection",
            },
            "instruction_evidence": [
                "0x846395FC copies mode-1 XYZ directly into the local matrix translation row/column",
                "0x84B0FB4C adds hierarchy record +0x10 XYZ in that same coordinate space",
                "0x846392C8 mirrors only root X/turn; mode-1 mirrors only numbered lane 0",
                "0x84B44D90 mixes only X/Z matrix pairs and therefore rotates about +Y",
                "0x846394D0 implements the standard right-handed quaternion matrix",
            ],
            "corpus_and_cross_title_evidence": {
                "apf_player_shadow_bounds": {
                    "minimum": bounds["minimum"], "maximum": bounds["maximum"],
                    "height_span": bounds["maximum"][1] - bounds["minimum"][1],
                },
                "nfl_same_named_player_shadow_bounds": {
                    "minimum": nfl_position["min"], "maximum": nfl_position["max"],
                    "height_span": nfl_position["max"][1] - nfl_position["min"][1],
                },
                "apf_named_left_hip_x": named["l_hip_hinge_base"]["vector_a"][0],
                "apf_named_right_hip_x": named["r_hip_hinge_base"]["vector_a"][0],
                "apf_named_head_y": named["head"]["vector_a"][1],
                "apf_named_right_knee_y": named["r_knee_hinge"]["vector_a"][1],
                "same_name_trajectory_pairs": pair_summary["pair_count"],
                "paired_trajectory_frames": pair_summary["paired_frame_count"],
                "combined_best_axis_transform": pair_summary[
                    "combined_trajectory_best_transform"],
                "shared_trajectory_scale": "0.125",
                "nfl_proved_unit": nfl_axis["proved_contract"]["position_units"],
            },
            "proof_scope_note": (
                "positive-Z anatomical/front naming uses the same-named shadow geometry and stance "
                "as corroboration; retain-XYZ/right-handed/Y-up and the 0.01 conversion do not depend "
                "on assigning a gameplay north/south sign"
            ),
        },
        "selected_root_trajectory": {
            "clip": SELECTED_CLIP,
            "clip_sha256": selected["sha256"],
            "root_region_sha256": root_region["sha256"],
            "sample_count": len(root_records),
            "sample_rate_hz": selected["sample_rate_hz"],
            "duration_seconds_f32": selected["duration"],
            "mirror": selected["mirror_flag"],
            "record_stride": selected["root_sample_stride"],
            "position_quantum_cm": 0.125,
            "raw_minimum": [min(row[lane] for row in root_records) for lane in range(3)],
            "raw_maximum": [max(row[lane] for row in root_records) for lane in range(3)],
            "first_raw": list(root_records[0]),
            "last_raw": list(root_records[-1]),
            "runtime_duration_sample_cm": list(duration_sample),
            "runtime_duration_interval_cm": list(duration_interval),
            "interval_equation": "D(t)=[X(t)-X(0), Y(t), Z(t)-Z(0), t, turn(t)-turn(0)]",
            "external_root_formula": {
                "live_scale": "S = uint8(player_object+0xD9) * f32(0x3C635B75)",
                "live_scale_constant": f32(struct.unpack(">f", bytes.fromhex("3c635b75"))[0]),
                "heading": "H = uint32(slot+0x50) + D.turn",
                "rotation": "external_root.rotation = right_handed_Ry_fixed_turn(H)",
                "translation": "external_root.T = float3(slot+0x40) + S * D.xyz",
                "local_scale": (
                    "0x84AA41F0 applies S to the named root local matrix 3x3 before hierarchy expansion"
                ),
                "hierarchy": (
                    "0x84B0FA88 uses the constructed matrix as the parent of player_shadow row 0; "
                    "the trajectory is not a mode-1 translation on the named root row"
                ),
            },
            "gltf_placement": (
                "place D on a dedicated player_shadow_external_root parent node; keep logical mode-0 "
                "channel 0 on the named root bone. For a normalized clip use slot base=(0,0,0), "
                "base heading=0, S=1; those are explicit export normalization values, not claimed "
                "live menu-instance state"
            ),
            "root_samples_tsv": "reports/assets/apf_animation_transform_root_samples.tsv",
        },
        "decision": {
            "quaternion_lanes_to_gltf_xyzw_proved": True,
            "apf_axes_handedness_units_proved": True,
            "selected_root_motion_placement_proved": True,
            "transform_export_contract_ready": True,
            "complete_skinned_gltf_export_ready": False,
            "remaining_primary_blocker": (
                "player_shadow BLENDINDICES0/BLENDWEIGHT0 palette and inverse-bind semantics"
            ),
        },
        "portme": [
            "// PORTME at 0x846384A8 and 0x84638610: emulate Xenon estimate/VMX rounding only if bit-exact replay is required.",
            "// PORTME at 0x84AA4138: bind the concrete live player_object+0xD9 value before claiming an exact menu-instance scale.",
            "// PORTME at 0x84A11CD8 and 0x84A11D00: bind slot+0x50 heading and slot+0x40 base position for a concrete live menu instance.",
            "// PORTME after 0x84B0FA88: prove player_shadow palette order and inverse-bind equations before emitting a complete skinned glTF.",
        ],
    }

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.root_tsv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(root_rows[0])
    with args.root_tsv.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter="\t",
                                lineterminator="\n")
        writer.writeheader()
        for row in root_rows:
            writer.writerow({key: fmt(value) if isinstance(value, float) else value
                             for key, value in row.items()})

    print(
        "APF_ANIMATION_TRANSFORM_SEMANTICS_COMPLETE "
        f"mode0={mode0_record_count} selected={selected_mode0_record_count} "
        f"root_samples={len(root_records)} quaternion=lane1,2,3,0 "
        "basis=right-handed-Y-up units=cm root=external-parent skin_ready=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

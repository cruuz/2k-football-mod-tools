#!/usr/bin/env python3
"""Audit the first APF shipped-clip -> named-hierarchy glTF export boundary.

This intentionally emits no animation.  It joins the exact frontend clip
selector and slot sampler to the player_shadow runtime assignment, the 21-row
human hierarchy, the static sampler/matrix tables, and the packed-pose
decoders.  Any missing standard-transform semantic remains a failed gate.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


EXPECTED_XEX_MD5 = "217eea6084c3d03f0f1143802b1f5636"
EXPECTED_XEX_SHA256 = "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
SELECTED_CLIP = "mnu_stn_01_070130_01_lg"
PLAYER_SHADOW = (1310, 415, "player_shadow")

EXPECTED_HUMAN_NAMES = [
    "root",
    "r_hip_hinge_base",
    "r_femur",
    "r_knee_hinge",
    "r_ankle",
    "l_hip_hinge_base",
    "l_femur",
    "l_knee_hinge",
    "l_ankle",
    "thorax",
    "l_clavicle",
    "l_shoulder_hinge_base",
    "l_humerus",
    "l_elbow",
    "l_hand",
    "head",
    "r_clavicle",
    "r_shoulder_hinge_base",
    "r_humerus",
    "r_elbow",
    "r_hand",
]
EXPECTED_HUMAN_PARENTS = [
    -1, 0, 1, 2, 3, 0, 5, 6, 7, 0, 9, 10, 11, 12, 13, 9, 9, 16, 17, 18, 19
]

TRACE_WORDS = {
    0x8463A52C: 0x556B1838,
    0x8463A56C: 0x19B86FF0,
    0x8463A574: 0x11AD0184,
    0x8463A57C: 0x10166B4A,
    0x8463A584: 0x18016710,
    0x8463A58C: 0x11AD004A,
    0x8463A590: 0x140DF0D3,
    0x8463A594: 0x1400DB13,
    0x84AA4458: 0x3BCBD550,
    0x84AA4728: 0x3CE0E26C,
    0x84AA4730: 0x3CC0EA76,
    0x84AA4734: 0x60E79B5D,
    0x84AA4738: 0x60C614F3,
    0x84AA4754: 0x48071C45,
    0x84AA4760: 0x48074D41,
    0x84AA4768: 0x937E0C20,
    0x84AA429C: 0x806B0C20,
    0x84B0FA8C: 0x81630060,
    0x84B0FAB0: 0x81630064,
    0x84B0FACC: 0xA14B0028,
    0x84B0FADC: 0x7D495050,
    0x84B0FAE0: 0x554A3032,
    0x84B0FB24: 0x10C050C3,
    0x84B0FBF0: 0x4E800020,
    0x820DBD00: 0x60900D71,
    0x84A6238C: 0x38800002,
    0x84A62390: 0x38600001,
    0x84A62394: 0x4BFAFE3D,
    0x84A121FC: 0x816B0010,
    0x84A12200: 0x556B17BE,
    0x84A1229C: 0x3D8084A1,
    0x84A122BC: 0x84A12338,
    0x84A1233C: 0x3CC05C6B,
    0x84A1234C: 0x60C61BF8,
    0x84A12368: 0x48104031,
    0x84A123C0: 0x4BFFFD99,
    0x84A12F94: 0x4809149D,
    0x84A11B8C: 0x7F5F582E,
    0x84A11BF8: 0x48092599,
    0x84A11C10: 0x4BC28711,
    0x84A11C1C: 0x48092585,
    0x84A11C24: 0x38A00015,
    0x84A11C30: 0x4BC278A1,
    0x84A11D60: 0x48092529,
}


class ReadinessError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReadinessError(message)


def digest(path: Path, algorithm: str = "sha256") -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path} is not a JSON object")
    return value


def signed20(value: int) -> int:
    value &= 0xFFFFF
    return value - (0x100000 if value & 0x80000 else 0)


def trace_words(path: Path) -> dict[int, int]:
    words: dict[int, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[0] == "RAW32":
            words[int(fields[1], 16)] = int(fields[2], 16)
    return words


def vmx_rows(path: Path) -> dict[int, tuple[int, str, str]]:
    result: dict[int, tuple[int, str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source, delimiter="\t"):
            result[int(row["address"], 16)] = (
                int(row["raw"], 16), row["mnemonic"], row["operands"]
            )
    return result


def region(resource: dict[str, Any], role: str) -> dict[str, Any]:
    matches = [entry for entry in resource["regions"] if entry["role"] == role]
    require(len(matches) == 1, f"{resource['name']} has {len(matches)} {role} regions")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xex", type=Path,
                        default=Path("extracted/All-Pro Football 2K8 (USA)/default.xex"))
    parser.add_argument("--mocap-inventory", type=Path,
                        default=Path("reports/assets/apf_mocap_inventory.json"))
    parser.add_argument("--mocap-corpus", type=Path,
                        default=Path("reports/assets/apf_mocap_corpus.bin"))
    parser.add_argument("--mocap-tsv", type=Path,
                        default=Path("reports/assets/apf_mocap.tsv"))
    parser.add_argument("--packed-pose-report", type=Path,
                        default=Path("reports/assets/apf_packed_pose_decoder_inventory.json"))
    parser.add_argument("--pose-config-report", type=Path,
                        default=Path("reports/assets/apf_pose_config_builder_inventory.json"))
    parser.add_argument("--pose-binding-report", type=Path,
                        default=Path("reports/assets/apf_pose_bone_binding_inventory.json"))
    parser.add_argument("--scene-inventory", type=Path,
                        default=Path("reports/assets/apf_scene_inventory.json"))
    parser.add_argument("--trace", type=Path,
                        default=Path("reports/assets/apf_animation_binding_gap_ghidra/animation_binding_gap_trace.txt"))
    parser.add_argument("--pseudo", type=Path,
                        default=Path("reports/assets/apf_animation_binding_gap_ghidra/animation_binding_gap_focused_pseudo_c.c"))
    parser.add_argument("--vmx", type=Path,
                        default=Path("reports/assets/apf_animation_binding_gap_ghidra/animation_binding_gap_vmx128.tsv"))
    parser.add_argument("--json", type=Path,
                        default=Path("reports/assets/apf_animation_export_readiness.json"))
    parser.add_argument("--bindings-tsv", type=Path,
                        default=Path("reports/assets/apf_animation_export_candidate_bindings.tsv"))
    args = parser.parse_args()

    for path in (
        args.xex, args.mocap_inventory, args.mocap_corpus, args.mocap_tsv,
        args.packed_pose_report, args.pose_config_report,
        args.pose_binding_report, args.scene_inventory, args.trace,
        args.pseudo, args.vmx,
    ):
        require(path.is_file(), f"missing input {path}")

    require(digest(args.xex, "md5") == EXPECTED_XEX_MD5, "unexpected APF XEX MD5")
    require(digest(args.xex) == EXPECTED_XEX_SHA256, "unexpected APF XEX SHA-256")

    mocap = load_json(args.mocap_inventory)
    packed = load_json(args.packed_pose_report)
    config = load_json(args.pose_config_report)
    binding = load_json(args.pose_binding_report)
    scenes = load_json(args.scene_inventory)
    require(mocap["schema"] == "apf_mocap_inventory/v1", "unexpected mocap schema")
    require(packed["schema"] == "apf_packed_pose_decoder/v1", "unexpected packed schema")
    require(config["schema"] == "apf_pose_config_builder/v1", "unexpected config schema")
    require(binding["schema"] == "apf_pose_bone_binding/v1", "unexpected binding schema")
    require(scenes["schema"].startswith("apf_scene_inventory/"), "unexpected scene schema")

    trace_text = args.trace.read_text(encoding="utf-8")
    require(f"Program MD5: {EXPECTED_XEX_MD5}" in trace_text, "trace XEX MD5 mismatch")
    words = trace_words(args.trace)
    for address, expected in TRACE_WORDS.items():
        require(words.get(address) == expected,
                f"trace word mismatch at 0x{address:08X}")
    require("MAIN_SECONDARY_MAP3_FIRST23_EQUAL true" in trace_text,
            "main/secondary map3 prefix is not equal")
    require("MAIN_SECONDARY_MAP2_FIRST21_EQUAL true" in trace_text,
            "main/secondary map2 prefix is not equal")
    require("CLIP_HASH_COUNT 68" in trace_text, "incomplete XEX clip-hash scan")
    require(
        "CLIP_HASH_MATERIALIZATION mnu_stn_01_070130_01_lg 0x5C6B1BF8 "
        "0x84A1233C->0x84A1234C(lis/ori,none)" in trace_text,
        "selected clip hash materialization is absent",
    )

    vmx = vmx_rows(args.vmx)
    expected_vmx = {
        0x8463A56C: ("vupkd3d128", "v13,v13,24"),
        0x8463A574: ("vslw", "v13,v13,v0"),
        0x8463A57C: ("vcfsx", "v0,v13,22"),
        0x8463A584: ("vrlimi128", "v0,v12,1,0"),
        0x8463A58C: ("vsubfp", "v13,v13,v0"),
        0x8463A590: ("vmaddfp128", "v0,v13,v126,v0"),
        0x8463A594: ("vxor128", "v0,v0,v123"),
    }
    for address, (mnemonic, operands) in expected_vmx.items():
        require(address in vmx, f"VMX trace missing 0x{address:08X}")
        require(vmx[address][1:] == (mnemonic, operands),
                f"VMX semantic mismatch at 0x{address:08X}")

    selected_matches = [entry for entry in mocap["resources"]
                        if entry["name"] == SELECTED_CLIP]
    require(len(selected_matches) == 1, "selected clip is not unique")
    selected = selected_matches[0]
    require(selected["kind"] == "full_clip", "selected clip is not a full clip")
    require(selected["variable_pointer_count"] == 0,
            "selected clip unexpectedly has mode-2 optional streams")
    require(selected["sample_count"] == 117 and selected["sample_rate_hz"] == 15,
            "selected clip sampling grid changed")
    selected_motion = region(selected, "packed_motion")
    require(selected_motion["length"] == selected["sample_count"] * 23 * 8,
            "selected packed region does not tile sample_count*23*8")

    with args.mocap_tsv.open("r", encoding="utf-8", newline="") as source:
        mocap_tsv_rows = list(csv.DictReader(source, delimiter="\t"))
    require(len(mocap_tsv_rows) == 68, "unexpected mocap TSV row count")
    selected_tsv = [row for row in mocap_tsv_rows if row["name"] == SELECTED_CLIP]
    require(len(selected_tsv) == 1, "selected clip is not unique in mocap TSV")
    require(selected_tsv[0]["name_crc32"].lower() == selected["name_crc32"].lower(),
            "selected clip TSV/inventory hash mismatch")

    corpus = args.mocap_corpus.read_bytes()
    mode1_bytes = bytearray()
    selector_counts: Counter[int] = Counter()
    component_min = [2**31 - 1] * 3
    component_max = [-(2**31)] * 3
    standard_clip_count = 0
    record_count = 0
    for clip in mocap["resources"]:
        if clip["kind"] != "full_clip" or clip["name"] == "hand_pose":
            continue
        standard_clip_count += 1
        motion = region(clip, "packed_motion")
        require(motion["length"] == clip["sample_count"] * 23 * 8,
                f"{clip['name']} standard packed tiling mismatch")
        start = clip["corpus_offset"] + motion["offset"]
        for frame in range(clip["sample_count"]):
            for unit in range(17, 23):
                offset = start + (frame * 23 + unit) * 8
                encoded = corpus[offset:offset + 8]
                require(len(encoded) == 8, f"truncated mode1 unit in {clip['name']}")
                mode1_bytes.extend(encoded)
                word = int.from_bytes(encoded, "big")
                selector_counts[word >> 60] += 1
                values = [signed20(word), signed20(word >> 20), signed20(word >> 40)]
                for lane, value in enumerate(values):
                    component_min[lane] = min(component_min[lane], value)
                    component_max[lane] = max(component_max[lane], value)
                record_count += 1
    require(standard_clip_count == 66, "unexpected standard clip count")
    require(record_count == 40434, "unexpected mode1 record count")
    require(selector_counts == Counter({0: record_count}),
            "a shipped mode1 record has a nonzero high nibble")

    scene_matches = [scene for scene in scenes["scenes"]
                     if (scene["outer_table_index"], scene["inner_file_index"],
                         scene["inner_name"]) == PLAYER_SHADOW]
    require(len(scene_matches) == 1, "player_shadow SCNE is not unique")
    scene = scene_matches[0]
    require(len(scene["nodes"]) == 1, "player_shadow node count changed")
    node = scene["nodes"][0]
    hierarchy = node["hierarchy"]
    names = [entry["name"] for entry in hierarchy["records"]]
    parents = [entry["parent"] for entry in hierarchy["records"]]
    require(hierarchy["count"] == 21, "player_shadow hierarchy is not 21 rows")
    require(names == EXPECTED_HUMAN_NAMES, "player_shadow hierarchy names changed")
    require(parents == EXPECTED_HUMAN_PARENTS, "player_shadow parents changed")

    human_schema_occurrences = []
    for candidate_scene in scenes["scenes"]:
        for candidate_node in candidate_scene["nodes"]:
            candidate_hierarchy = candidate_node.get("hierarchy")
            if candidate_hierarchy is None or candidate_hierarchy["count"] != 21:
                continue
            if ([entry["name"] for entry in candidate_hierarchy["records"]] == names and
                    [entry["parent"] for entry in candidate_hierarchy["records"]] == parents):
                human_schema_occurrences.append({
                    "outer_table_index": candidate_scene["outer_table_index"],
                    "inner_file_index": candidate_scene["inner_file_index"],
                    "inner_name": candidate_scene["inner_name"],
                    "node_index": candidate_node["index"],
                    "node_name": candidate_node["name"],
                })
    require(len(human_schema_occurrences) >= 40,
            "unexpectedly few exact 21-row human hierarchy copies")

    main_map2_rows = config["main_static_tables"]["map2"]["rows"][:21]
    main_map3_rows = config["main_static_tables"]["map3"]["rows"]
    require(len(main_map2_rows) == 21 and len(main_map3_rows) == 25,
            "static map row counts changed")
    require([row["mode"] for row in main_map3_rows[:17]] == [0] * 17,
            "rotation channel modes changed")
    require([row["mode"] for row in main_map3_rows[17:23]] == [1] * 6,
            "translation channel modes changed")
    require([row["mode"] for row in main_map3_rows[23:25]] == [2, 2],
            "optional channel modes changed")

    bindings = []
    for index, (bone, parent, map_row, hierarchy_row) in enumerate(
            zip(names, parents, main_map2_rows, hierarchy["records"], strict=True)):
        require(map_row["matrix_row"] == index and hierarchy_row["index"] == index,
                "candidate row indexing changed")
        bindings.append({
            "matrix_row": index,
            "bone_name": bone,
            "parent_row": parent,
            "rotation_logical_index": map_row["rotation_logical_index"],
            "translation_logical_index": map_row["translation_logical_index"],
            "main_static_map_address": "0x820FC55C",
            "secondary_direct_map_address": "0x82100738",
            "candidate_name_status": "exact_player_shadow_row",
            "active_main_binding_status": "exact_frontend_direct_getter_path",
        })

    input_paths = {
        "mocap_inventory": args.mocap_inventory,
        "mocap_corpus": args.mocap_corpus,
        "mocap_tsv": args.mocap_tsv,
        "packed_pose_report": args.packed_pose_report,
        "pose_config_report": args.pose_config_report,
        "pose_binding_report": args.pose_binding_report,
        "scene_inventory": args.scene_inventory,
        "ghidra_trace": args.trace,
        "focused_pseudo_c": args.pseudo,
        "vmx128_disassembly": args.vmx,
        "native_header": Path("include/recovered/apf2k8/translation_pose.h"),
        "native_source": Path("src/recovered/apf2k8/translation_pose.c"),
        "native_test": Path("tests/apf_translation_pose_test.c"),
    }
    for path in input_paths.values():
        require(path.is_file(), f"missing pinned input {path}")

    checks = [
        ("exact_shipped_clip_bytes", True,
         "mnu_stn_01_070130_01_lg is uniquely byte-anchored in frontend_sync.iff"),
        ("mode0_rotation_units", True,
         "logical rotation channels 0..16 use the existing instruction-proved mode-0 decoder"),
        ("mode1_translation_units", True,
         "0x8463A52C..0x8463A598 proves signed20 / 1024, linear interpolation, lane-0 mirror"),
        ("runtime_player_shadow_hierarchy_assignment", True,
         "0x84AA4728..0x84AA4768 looks up SCNE/player_shadow and stores its runtime object at 0x8522E170"),
        ("player_shadow_named_hierarchy", True,
         "outer 1310 inner 415 contains the exact 21-row named hierarchy consumed by the VMX hierarchy ABI"),
        ("main_static_table_matches_direct_table_prefix", True,
         "0x820FC510/55C and 0x821006F0/0738 match for the 23 logical and 21 matrix rows used here"),
        ("selected_clip_to_consumer_selector", True,
         "0x84A62394 calls selector index 2; the large-class branch at 0x84A12338 loads hash 0x5C6B1BF8, stores it in slot 1, and 0x84A11B8C reloads that exact slot clip"),
        ("active_frontend_static_config_getters", True,
         "0x84A11BF8 and 0x84A11C1C call exact getters 0x84AA4190/41A0 before sampling and expanding exactly 21 rows"),
        ("quaternion_lanes_to_gltf_xyzw", False,
         "0x846394D0 matrix expansion is raw-traced but numbered quaternion lanes are not yet mapped to standard glTF XYZW"),
        ("apf_axes_handedness_units", False,
         "APF local/root coordinate axes, handedness, and unit conversion are not instruction-proved"),
        ("root_motion_application_policy", False,
         "the selected consumer's trajectory-to-root matrix policy is not recovered"),
        ("skinning_palette_and_inverse_bind", False,
         "player_shadow BLENDINDICES/BLENDWEIGHT exist, but palette order and inverse-bind equation are not proved"),
    ]

    report = {
        "schema": "apf_animation_export_readiness/v1",
        "program": {
            "path": str(args.xex),
            "md5": EXPECTED_XEX_MD5,
            "sha256": EXPECTED_XEX_SHA256,
            "language": "PowerPC:BE:64:A2ALT-32addr",
        },
        "inputs": {
            name: {"path": str(path), "sha256": digest(path)}
            for name, path in sorted(input_paths.items())
        },
        "selected_clip_candidate": {
            "name": selected["name"],
            "name_crc32": selected["name_crc32"],
            "outer_table_index": selected["outer_table_index"],
            "outer_name": selected["outer_name"],
            "inner_index": selected["inner_index"],
            "part_block_index": selected["part_block_index"],
            "part_offset": selected["part_offset"],
            "corpus_offset": selected["corpus_offset"],
            "body_length": selected["length"],
            "body_sha256": selected["sha256"],
            "packed_motion_offset": selected_motion["offset"],
            "packed_motion_length": selected_motion["length"],
            "packed_motion_sha256": selected_motion["sha256"],
            "sample_count": selected["sample_count"],
            "sample_rate_hz": selected["sample_rate_hz"],
            "duration_seconds": selected["duration"],
            "mirror": selected["mirror_flag"],
            "variable_pointer_count": selected["variable_pointer_count"],
            "selection_reason": "exact large-class branch witness for the selector-index-2 call at 0x84A62394; the branch predicate and complete clip-to-player_shadow dataflow are instruction-bounded",
        },
        "runtime_frontend_binding_evidence": {
            "controller_call": "0x84A62384..0x84A62394 passes slot=1, selector=2, arg5=0, arg6=0 to 0x84A121D0",
            "selector_pdata_entry": "0x84A121D0",
            "selector_structured_status": "displaced_pdata_focused_raw_only",
            "object_class_field_equation": "(slot_object_u32_at_0x10 >> 30) & 3",
            "selected_branch_predicate": "object_class_field is 2 or 3",
            "selected_jump_table_entry": "0x84A122BC -> 0x84A12338 for selector index 2",
            "single_mocap_type_crc_address": "0x820DBD00",
            "single_mocap_type_crc32": "0x60900D71",
            "single_mocap_type_name": "SingleMoCap",
            "selected_name_crc_materialization": "0x84A1233C..0x84A1234C -> 0x5C6B1BF8",
            "selected_lookup_call": "0x84A12368 -> 0x84B16398",
            "slot_assignment_call": "0x84A123C0 -> 0x84A12158",
            "slot_clip_field": "0x851FFD80 + slot*0xAF0 + 0x54",
            "slot_one_clip_address": "0x852008C4",
            "per_frame_setup_call": "0x84A12F94 -> displaced 0x84AA4430 initializer containing the player_shadow assignment",
            "clip_reload": "0x84A11B8C loads the selected slot clip into r26",
            "packed_pose_sample": "0x84A11BF8 gets map3 0x820FC510; 0x84A11C10 calls 0x8463A320 with clip r26",
            "local_matrix_expand": "0x84A11C1C gets map2 0x820FC55C; 0x84A11C24 passes row_count=21; 0x84A11C30 calls 0x846394D0",
            "player_shadow_hierarchy_apply": "0x84A11D60 calls 0x84AA4288, which loads player_shadow runtime object 0x8522E170",
            "alternate_exact_branch": {
                "predicate": "object_class_field is neither 2 nor 3",
                "clip_name": "mnu_stn_01_070130_01",
                "clip_crc32": "0x5738AAEF",
                "lookup_call": "0x84A12288 -> 0x84B16398",
            },
            "binding_status": "exact_conditional_runtime_path",
        },
        "mode1_translation_recovery": {
            "instruction_range": "0x8463A52C..0x8463A598",
            "record_size": 8,
            "big_endian_bit_grammar": {
                "63..60": "non-translation nibble; zero in every shipped mode-1 record",
                "59..40": "signed20 component lane 2",
                "39..20": "signed20 component lane 1",
                "19..0": "signed20 component lane 0",
            },
            "value_equation": "lanes=[signed20_low/1024,signed20_mid/1024,signed20_high/1024,+0.0]",
            "interpolation": "a + (b-a)*frame_fraction",
            "mirror": "XOR float sign bit in numbered lane 0 after interpolation",
            "portable_sample_point_decode_bit_exact": True,
            "portable_interpolation_xenon_bit_exact": False,
            "standard_clip_count": standard_clip_count,
            "record_count": record_count,
            "record_bytes": len(mode1_bytes),
            "record_stream_sha256": hashlib.sha256(mode1_bytes).hexdigest(),
            "high_nibble_counts": {str(key): value for key, value in sorted(selector_counts.items())},
            "packed_component_minimum": component_min,
            "packed_component_maximum": component_max,
            "scaled_lane_minimum": [value / 1024.0 for value in component_min],
            "scaled_lane_maximum": [value / 1024.0 for value in component_max],
        },
        "runtime_hierarchy_evidence": {
            "initializer_pdata_start": "0x84AA4430",
            "initializer_structured_status": "displaced_pdata_focused_raw_only",
            "type_crc32": "0xE26C9B5D",
            "type_name": "SCNE",
            "resource_crc32": "0xEA7614F3",
            "resource_name": "player_shadow",
            "lookup_call": "0x84AA4754 -> 0x84B16398",
            "runtime_object_call": "0x84AA4760 -> 0x84B194A0",
            "global_store": "0x84AA4768 stores runtime object at 0x8522D550+0x0C20 = 0x8522E170",
            "consumer_global_load": "0x84AA429C loads 0x8522E170",
            "hierarchy_apply": {
                "function": "0x84B0FA88..0x84B0FBF0",
                "object_count_offset": "+0x60",
                "object_records_offset": "+0x64",
                "record_stride": 48,
                "local_translation_offset": "+0x10",
                "signed_parent_index_offset": "+0x28",
                "matrix_stride": 64,
                "equation": "current[row] = local[row] * (current[parent] or external_root)",
                "in_place_safe_parent_rule": "parent index is read before the already-written parent matrix; all player_shadow parents precede children",
            },
        },
        "player_shadow_candidate_hierarchy": {
            "outer_table_index": scene["outer_table_index"],
            "inner_file_index": scene["inner_file_index"],
            "inner_name": scene["inner_name"],
            "system_length": scene["system_length"],
            "system_sha256": scene["system_sha256"],
            "node_index": node["index"],
            "node_name": node["name"],
            "hierarchy_offset": hierarchy["offset"],
            "hierarchy_record_offset": hierarchy["record_offset"],
            "hierarchy_count": hierarchy["count"],
            "hierarchy_byte_length": hierarchy["byte_length"],
            "topology_status": hierarchy["topology_status"],
            "vertex_semantics": [entry["indexed_semantic"] for entry in node["vertex_declarations"]],
            "mesh_vertex_count": sum(mesh["vertex_count"] for mesh in node["meshes"]),
            "exact_same_named_parent_schema_occurrence_count": len(human_schema_occurrences),
            "exact_same_named_parent_schema_occurrences": human_schema_occurrences,
        },
        "conditional_row_join": {
            "status": "exact_active_frontend_main_table_to_player_shadow_rows",
            "main_map3_address": "0x820FC510",
            "main_map2_address": "0x820FC55C",
            "secondary_direct_map3_address": "0x821006F0",
            "secondary_direct_map2_address": "0x82100738",
            "main_secondary_first_23_logical_rows_equal": True,
            "main_secondary_first_21_matrix_rows_equal": True,
            "candidate_named_row_count": 21,
            "active_main_exact_named_binding_count": 21,
            "rows": bindings,
        },
        "readiness_checks": [
            {"check": name, "passed": passed, "evidence": evidence}
            for name, passed, evidence in checks
        ],
        "decision": {
            "standard_gltf_animation_export_ready": False,
            "export_emitted": False,
            "exact_clip_to_named_hierarchy_binding_proved": True,
            "reason": "the selected conditional branch is now instruction-bound from an exact SingleMoCap lookup through the active static maps to player_shadow's 21 named rows, but standard glTF rotation/coordinate/root and skinned inverse-bind semantics remain unproved",
            "narrowest_next_executable_gap": "decode 0x846394D0..0x84639614 into an exact numbered-quaternion-lane, matrix convention, and glTF XYZW mapping; then resolve 0x846392C8 root coordinates and the post-0x84B0FA88 skin palette/inverse-bind path",
        },
        "worked": [
            "proved the mode-1 signed20 /1024 translation decoder and lane-0 mirror over all 40434 shipped records",
            "proved the selector-index-2 large-class branch resolves mnu_stn_01_070130_01_lg as SingleMoCap hash 0x5C6B1BF8",
            "traced that exact slot clip through 0x84A11B58 into packed sampling, the main static map getters, 21 local matrices, and the player_shadow hierarchy wrapper",
            "proved that the hierarchy wrapper's runtime object is initialized from SCNE player_shadow and joined all 21 exact names and parents",
            "upgraded all 21 row bindings from candidates to exact active frontend bindings",
        ],
        "failed": [
            "numbered APF quaternion lanes are not yet converted to standard glTF XYZW",
            "APF axes, handedness, units, and root placement remain unresolved",
            "player_shadow skin palette order and inverse-bind semantics remain unresolved",
            "therefore no glTF animation is emitted",
        ],
        "portme": [
            "// PORTME at 0x84AA4430: recreate the displaced .pdata function; focused RAW32 proves player_shadow assignment but not the whole initializer.",
            "// PORTME at 0x84A121D0..0x84A123CC: recreate the displaced selector switch; RAW32 proves the selected conditional branch and slot assignment.",
            "// PORTME at 0x84A11B58..0x84A11D84: recreate the displaced frontend sample/apply function; RAW32 proves the exact clip/map/matrix/hierarchy dataflow.",
            "// PORTME at 0x846394D0..0x84639614: map numbered quaternion lanes and row-matrix convention to standard glTF XYZW without inference.",
            "// PORTME at 0x846392C8 and call 0x84A11CC8: recover the selected frontend consumer's trajectory/root placement and APF axis/unit contract.",
            "// PORTME after 0x84B0FA88: trace player_shadow BLENDINDICES/BLENDWEIGHT palette and inverse-bind application before emitting a skinned glTF.",
        ],
    }

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    args.bindings_tsv.parent.mkdir(parents=True, exist_ok=True)
    with args.bindings_tsv.open("w", encoding="utf-8", newline="") as output:
        columns = [
            "matrix_row", "bone_name", "parent_row", "rotation_logical_index",
            "translation_logical_index", "main_static_map_address",
            "secondary_direct_map_address", "candidate_name_status",
            "active_main_binding_status",
        ]
        writer = csv.DictWriter(output, fieldnames=columns, delimiter="\t",
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(bindings)

    print(
        "APF_ANIMATION_EXPORT_READINESS_COMPLETE "
        f"clip={selected['name']} hierarchy={node['name']} rows={len(bindings)} "
        f"mode1_records={record_count} export_ready=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReadinessError as error:
        raise SystemExit(f"APF animation export readiness: {error}") from error

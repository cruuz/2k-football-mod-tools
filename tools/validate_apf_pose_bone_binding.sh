#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

report=reports/assets/apf_pose_bone_binding_inventory.json
logical=reports/assets/apf_pose_bone_binding_logical.tsv
matrix=reports/assets/apf_pose_bone_binding_matrix.tsv
fingers=reports/assets/apf_pose_bone_finger_pairs.tsv
scene_join=reports/assets/apf_pose_bone_scene_join.tsv
trace=reports/assets/apf_pose_bone_binding_ghidra/pose_bone_binding_trace.txt
pseudo=reports/assets/apf_pose_bone_binding_ghidra/pose_bone_binding_focused_pseudo_c.c
packed_pose=reports/assets/apf_packed_pose_decoder_inventory.json
bone_scale=reports/assets/apf_bone_scale_map.tsv
scene=reports/assets/apf_scene_inventory.json
doc=docs/research/apf_pose_bone_binding.md

for required in \
  tools/apf_pose_bone_binding.py \
  tools/ghidra_scripts/apf/ApfPoseBoneBindingTrace.java \
  "$report" "$logical" "$matrix" "$fingers" "$scene_join" \
  "$trace" "$pseudo" "$packed_pose" "$bone_scale" "$scene" "$doc"; do
  test -f "$required"
done

temporary=$(mktemp -d /tmp/apf-pose-bone-binding.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  tools/apf_pose_bone_binding.py

python3 tools/apf_pose_bone_binding.py \
  --trace "$trace" \
  --pseudo "$pseudo" \
  --packed-pose "$packed_pose" \
  --bone-scale-map "$bone_scale" \
  --scene-inventory "$scene" \
  --json "$temporary/inventory.json" \
  --logical-tsv "$temporary/logical.tsv" \
  --matrix-tsv "$temporary/matrix.tsv" \
  --finger-tsv "$temporary/fingers.tsv" \
  --scene-join-tsv "$temporary/scene.tsv"

cmp "$temporary/inventory.json" "$report"
cmp "$temporary/logical.tsv" "$logical"
cmp "$temporary/matrix.tsv" "$matrix"
cmp "$temporary/fingers.tsv" "$fingers"
cmp "$temporary/scene.tsv" "$scene_join"

test "$(wc -l < "$logical")" -eq 26
test "$(wc -l < "$matrix")" -eq 23
test "$(wc -l < "$fingers")" -eq 16
test "$(wc -l < "$scene_join")" -eq 145

test "$(sha256sum "$report" | cut -d' ' -f1)" = \
  0ccab8212bf99a1a1b0ba20fb146b2aa9575716be1ade3f493e6d7a5bda30b64
test "$(sha256sum "$logical" | cut -d' ' -f1)" = \
  226a8d4247d5b437b0eef3aaa7a4ed2754e457f19892bef9a0b3f66b395b6fbe
test "$(sha256sum "$matrix" | cut -d' ' -f1)" = \
  ba7f9201c00f6025fd8b89f72435bc2eea230132c8c3bfe6ba51bf86928ac113
test "$(sha256sum "$fingers" | cut -d' ' -f1)" = \
  434b417c749c9227fc3cb631de6c7bbb3b8626e31b4e32edab373c38dd82f1e1
test "$(sha256sum "$scene_join" | cut -d' ' -f1)" = \
  95d5488ffa38cbe39bebbac13a15e3d5e2c4db4d3b596d18411f886da3f4b03f
test "$(sha256sum "$trace" | cut -d' ' -f1)" = \
  2f7157a6f3f6dc652b203d24baf05a2ee22e67c50228a6afb282a5c2c9eef29c
test "$(sha256sum "$pseudo" | cut -d' ' -f1)" = \
  70715dc266b81345fdd938aa7382079576c3d76877bfb763221804ef9b3bfaf0

python3 - "$report" "$logical" "$matrix" "$fingers" "$scene_join" <<'PY'
import csv
from collections import Counter
import json
from pathlib import Path
import sys

report_path, logical_path, matrix_path, finger_path, scene_path = map(
    Path, sys.argv[1:]
)
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "apf_pose_bone_binding/v1"
assert report["summary"] == {
    "aligned_direct_binding_pointer_word_count": 0,
    "bone_scale_scene_join_count": 144,
    "exact_named_finger_bone_count": 30,
    "exact_named_finger_pair_count": 15,
    "hires_exact_name_hash_join_count": 92,
    "hires_same_position_count": 66,
    "initialized_static_config_candidate_count": 0,
    "logical_map_record_count": 25,
    "logical_named_body_binding_count": 0,
    "lores_exact_order_join_count": 52,
    "matrix_ambiguous_trailing_pair_count": 1,
    "matrix_byte_pair_count": 22,
    "matrix_named_body_binding_count": 0,
    "matrix_semantic_pair_count": 21,
    "static_finger_table_copy_count": 3,
}

contract = report["sampler_to_matrix_contract"]
assert contract["concrete_callers"] == ["0x847C1438", "0x847C9428"]
assert contract["matrix_map_record"] == (
    "[signed rotation logical index, signed translation logical index]"
)
assert contract["default_matrix_map"]["records"] == [
    [index, -1] for index in range(32)
]
assert contract["logical_pose_record_size"] == 16
assert contract["matrix_map_record_size"] == 2
assert contract["matrix_output_stride"] == 64
assert contract["stack_pose_buffer_bytes"] == 520

logical_rows = report["logical_channels"]
assert [row["logical_channel"] for row in logical_rows] == list(range(25))
assert [row["normal_packed_index"] for row in logical_rows] == list(range(25))
assert Counter(row["mode"] for row in logical_rows) == {0: 17, 1: 6, 2: 2}
expected_mirror = [
    0, 4, 5, 6, 1, 2, 3, 7, 13, 14, 15, 16, 12,
    8, 9, 10, 11, 18, 17, 19, 22, 21, 20, 24, 23,
]
assert [row["mirrored_packed_index"] for row in logical_rows] == expected_mirror
assert all(row["bone_name"] is None for row in logical_rows)

matrix_rows = report["matrix_rows"]
expected_pairs = [
    (0, None), (None, None), (1, 17), (2, None), (3, None),
    (None, None), (4, 18), (5, None), (6, None), (7, 19),
    (8, None), (None, None), (9, 20), (10, None), (11, None),
    (12, 21), (13, None), (None, None), (14, 22), (15, None),
    (16, None), (0, 0),
]
assert [
    (row["rotation_logical_index"], row["translation_logical_index"])
    for row in matrix_rows
] == expected_pairs
assert all(row["extent_status"] == "semantic_pair" for row in matrix_rows[:21])
assert matrix_rows[21]["extent_status"] == "record_or_two_byte_alignment_unproved"
assert all(row["bone_name"] is None for row in matrix_rows)

finger_rows = report["finger_pairs"]
assert len(finger_rows) == 15
assert finger_rows[0] == {
    "binding_status": "exact_hash_to_scene_name; pose-channel consumer_unproved",
    "left_hash": 0xBF9AEFB2,
    "left_hires_index": 66,
    "left_lores_index": 14,
    "left_name": "def_Lthumb1",
    "pair_index": 0,
    "right_hash": 0x887B0821,
    "right_hires_index": 39,
    "right_lores_index": 34,
    "right_name": "def_Rthumb1",
}
assert finger_rows[-1]["left_name"] == "def_Lfinger4_3"
assert finger_rows[-1]["right_name"] == "def_Rfinger4_3"

families = report["skeleton_families"]
assert [(row["map_name"], row["bone_count"], row["same_position_count"],
         row["order_identical"]) for row in families] == [
    ("lores", 52, 52, True),
    ("hires", 92, 66, False),
]
joins = report["bone_scale_scene_joins"]
assert len(joins) == 144
assert all(row["same_position"] for row in joins[:52])
assert sum(row["same_position"] for row in joins[52:]) == 66
assert all(line.startswith("// PORTME") for line in report["portme"])

spans = report["executable_evidence"]["raw_spans"]
assert {row["name"]: row["sha256"] for row in spans} == {
    "matrix_expansion": "f99217385a0a8549367cf2f9a9a57f557ae3de85433d5d066c0cc42a9faec6b4",
    "sampler_matrix_caller_a": "f0917dc5416eb09e4f9a347a8e9a2af1dff1b0d4626ae777e273b278bbe3160e",
    "sampler_matrix_caller_b": "ebf0ac0e0c8ae3ceb22f5c7eaa720dcd0ead2ba89dcea9254ebef734647934ee",
    "static_matrix_row_lookup": "1300db22b941959a048454e85e5f2477aa8ade24fb5dfa6dc9ba2df76457f81d",
    "static_map_matrix_consumer": "85fc2592daf19af09b699255e4af40783fe4e12d580b03684742a8ad25720ac9",
    "static_table_getter_region": "41f941c8d88f81858e827dde08eae1eecba4b9256b5f9cde9aeef5ec5713e88e",
}

def rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream, dialect="excel-tab"))

assert len(rows(logical_path)) == 25
assert len(rows(matrix_path)) == 22
assert len(rows(finger_path)) == 15
assert len(rows(scene_path)) == 144
print("APF_POSE_BONE_BINDING_JSON_TSV_ASSERTIONS_PASS")
PY

for marker in \
  'STATIC_GETTER 0x84AA4190 target=0x820FC510 refs=' \
  'STATIC_GETTER 0x84AA41A0 target=0x820FC55C refs=0x8487770C' \
  'STATIC_GETTER 0x84AA41B0 target=0x820FC588 refs=' \
  'STATIC_MAP2_EXTENT 0x820FC55C 0x820FC588 bytes=44 record21_status=record_or_alignment_unproved' \
  'STATIC_CONFIG_COUNT 0' \
  'BINDING_POINTER_COUNT 0' \
  'RAW32 0x84639574 0x38C60002' \
  'RAW32 0x84877744 0x7D4A18AE' \
  'RAW32 0x84926074 0x4BD1345D'; do
  rg -Fq "$marker" "$trace"
done

for marker in \
  'return 0xffffffff820fc510;' \
  'return 0xffffffff820fc55c;' \
  'return 0xffffffff820fc588;' \
  'PORTME at 0x846394D0' \
  'PORTME at 0x8463A4F0/0x8463A52C' \
  'PORTME: Ghidra collapsed this shared-save/VMX function'; do
  rg -Fq "$marker" "$pseudo"
done

set +u
ghidra_mode=$APF_POSE_BONE_BINDING_GHIDRA
set -u
if test "$ghidra_mode" = 1; then
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" apf2k8 \
      -process default.xex -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts/apf" \
      -postScript ApfPoseBoneBindingTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/pose_bone_binding_trace.txt" "$trace"
  cmp "$temporary/ghidra/pose_bone_binding_focused_pseudo_c.c" "$pseudo"
  echo APF_POSE_BONE_BINDING_GHIDRA_REGEN_PASS
fi

echo 'APF_POSE_BONE_BINDING_VALIDATION_PASS logical=25 matrix_semantic=21 fingers=30 scene_joins=144'

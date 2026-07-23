#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

report=reports/assets/apf_pose_config_builder_inventory.json
bindings=reports/assets/apf_pose_config_builder_bindings.tsv
trace=reports/assets/apf_pose_config_builder_ghidra/pose_config_builder_trace.txt
pseudo=reports/assets/apf_pose_config_builder_ghidra/pose_config_builder_focused_pseudo_c.c
pose_binding=reports/assets/apf_pose_bone_binding_inventory.json
logical=reports/assets/apf_pose_bone_binding_logical.tsv
matrix=reports/assets/apf_pose_bone_binding_matrix.tsv
scene=reports/assets/apf_scene_inventory.json
manifest=research/functions/apf2k8/manifest.json
doc=docs/research/apf_pose_config_builder.md

for required in \
  tools/apf_pose_config_builder.py \
  tools/ghidra_scripts/apf/ApfPoseConfigBuilderTrace.java \
  "$report" "$bindings" "$trace" "$pseudo" \
  "$pose_binding" "$logical" "$matrix" "$scene" "$manifest" "$doc"; do
  test -f "$required"
done

temporary=$(mktemp -d /tmp/apf-pose-config-builder.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  tools/apf_pose_config_builder.py

python3 tools/apf_pose_config_builder.py \
  --trace "$trace" \
  --pseudo "$pseudo" \
  --pose-binding "$pose_binding" \
  --logical-tsv "$logical" \
  --matrix-tsv "$matrix" \
  --scene-inventory "$scene" \
  --function-manifest "$manifest" \
  --json "$temporary/inventory.json" \
  --bindings-tsv "$temporary/bindings.tsv"

cmp "$temporary/inventory.json" "$report"
cmp "$temporary/bindings.tsv" "$bindings"

test "$(wc -l < "$bindings")" -eq 48
test "$(sha256sum "$report" | cut -d' ' -f1)" = \
  e4e0c0ef633d5915ce151ee51bd423b79178951a4285038767813678a698d726
test "$(sha256sum "$bindings" | cut -d' ' -f1)" = \
  35290be6b28bfc69b08d8edaabd632e49721202fe166c3e48c751ac319cf5035
test "$(sha256sum "$trace" | cut -d' ' -f1)" = \
  7d7e5e6637b765f1f5a593b8797a9e4893769541321e423e4db518ef0bccbbf1
test "$(sha256sum "$pseudo" | cut -d' ' -f1)" = \
  1c12e8033a326a0eee43565fb78c6a7311cdb0973a792e096e8d03ad63a9f04d

python3 - "$report" "$bindings" <<'PY'
import csv
import json
from pathlib import Path
import sys

report_path, bindings_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))

assert report["schema"] == "apf_pose_config_builder/v1"
assert report["program"] == {
    "language": "PowerPC:BE:64:A2ALT-32addr",
    "md5": "217eea6084c3d03f0f1143802b1f5636",
    "name": "default.xex",
}
assert report["summary"] == {
    "direct_main_map3_installer_count": 0,
    "dynamic_descriptor_proved_field_count": 9,
    "dynamic_descriptor_record_size": 64,
    "main_exact_named_logical_binding_count": 0,
    "main_exact_named_matrix_binding_count": 0,
    "main_logical_row_count": 25,
    "main_matrix_ambiguous_trailing_pair_count": 1,
    "main_matrix_byte_pair_count": 22,
    "main_matrix_semantic_row_count": 21,
    "matrix_pool_half_bytes": 1344,
    "matrix_pool_matrix_capacity_at_64_byte_stride": 21,
    "secondary_direct_map3_row_count": 24,
    "static_accessor_count": 8,
}

contract = report["main_config_consumer_contract"]
assert contract["concrete_consumers"] == ["0x847C1438", "0x847C9428"]
assert [
    (field["offset_hex"], field["role"], field["status"])
    for field in contract["config_fields"]
] == [
    ("+0x1C", "matrix_count", "proved"),
    ("+0x24", "sampler_map3_pointer", "proved"),
    ("+0x28", "matrix_map2_pointer", "proved"),
    ("+0x40", "pose_storage_pointer", "proved"),
    ("+0x44", "optional_post_sample_callback", "proved"),
]
assert contract["pose_storage_pointer_evidence"] == {
    "inline_storage_rejected": True,
    "pointee_offsets_read": [0x170, 0x180],
    "reason": "+0x40 is loaded as a pointer before adding +0x170/+0x180; +0x44 is a distinct callback field",
}

main = report["main_static_tables"]
assert main["map3"]["address"] == "0x820FC510"
assert main["map3"]["getter"] == "0x84AA4190"
assert len(main["map3"]["rows"]) == 25
assert all(row["bone_name"] is None for row in main["map3"]["rows"])
assert main["map2"]["address"] == "0x820FC55C"
assert main["map2"]["end_exclusive"] == "0x820FC588"
assert len(main["map2"]["rows"]) == 22
assert all(row["extent_status"] == "semantic_pair" for row in main["map2"]["rows"][:21])
assert main["map2"]["rows"][21]["extent_status"] == "record_or_two_byte_alignment_unproved"
assert all(row["bone_name"] is None for row in main["map2"]["rows"])

search = report["direct_installer_search"]
assert search["status"] == "unresolved_indirect_installation_not_excluded"
assert search["derived_direct_main_map3_installer_count"] == 0
assert search["conclusion"] == "no_direct_retail_xex_builder_or_installer_recovered"
assert search["main_map3_only_materialization"] == "0x84AA4190->0x84AA4194(lis/addi)"
assert search["main_map3_getter_direct_reference_count"] == 0
assert search["main_map2_getter_direct_callers"] == ["0x8487770C", "0x84925BDC"]
targets = {row["target"]: row for row in search["targets"]}
assert targets["0x820FC510"]["reference_count"] == 0
assert targets["0x820FC510"]["raw_aligned_pointer_hit_count"] == 0
assert targets["0x820FC510"]["materializations"] == [
    "0x84AA4190->0x84AA4194(lis/addi)"
]
assert targets["0x84AA4190"]["reference_count"] == 0
assert targets["0x84AA4190"]["materialization_count"] == 0

accessors = report["static_accessor_family"]
assert [(row["address"], row["return"], row["role"]) for row in accessors] == [
    ("0x84AA4190", "0x820FC510", "main_map3"),
    ("0x84AA41A0", "0x820FC55C", "main_map2"),
    ("0x84AA41B0", "0x820FC588", "float_table"),
    ("0x84AA41C0", "0x01F9FF80", "mask_value_a"),
    ("0x84AA41D0", "0x0006007F", "mask_value_b"),
    ("0x84AA41E0", "0x00000000", "zero_value"),
    ("0x84AA41E8", "unchanged", "noop"),
    ("0x84AA41F0", "void", "scale_nine_pose_floats"),
]

dynamic = report["dynamic_descriptor_path"]
assert dynamic["consumer_function"] == "0x8497B7B0"
assert (dynamic["owner_count_offset"], dynamic["owner_record_pointer_offset"], dynamic["record_size"]) == (0xD8, 0xDC, 0x40)
assert [(row["offset_hex"], row["role"]) for row in dynamic["fields"]] == [
    ("+0x00", "type_tag_used_by_destroy_path"),
    ("+0x0C", "clip_or_single_mocap_pointer_passed_to_sampler"),
    ("+0x18", "matrix_output_pointer"),
    ("+0x1C", "owned_auxiliary_pointer_destroyed_with_record"),
    ("+0x2C", "matrix_count"),
    ("+0x30", "sampler_active_mask"),
    ("+0x34", "sampler_map3_pointer"),
    ("+0x38", "matrix_map2_pointer"),
    ("+0x3C", "optional_post_sample_callback"),
]
assert dynamic["lifetime"]["owner_fields_zeroed"] == ["+0xD8", "+0xDC"]
assert dynamic["relationship_to_main_static_tables"].endswith("population_and_main_table_ownership_unproved")

secondary = report["secondary_direct_config"]
assert secondary["consumer_function"] == "0x84AC1668"
assert secondary["map3_address"] == "0x821006F0"
assert secondary["map2_address"] == "0x82100738"
assert len(secondary["map3_rows"]) == 24
assert secondary["map3_rows"][-1] == {
    "bone_name": None,
    "mirrored_packed_index": 0,
    "mode": 0,
    "normal_packed_index": 0,
    "row": 23,
}
assert all(row["bone_name"] is None for row in secondary["map3_rows"])

pool = report["player_matrix_pool_clue"]
assert (pool["slot_size"], pool["second_region_offset"], pool["cleared_tail_offset"], pool["cleared_tail_size"]) == (0xAD0, 0x540, 0xA80, 0x50)
assert pool["matrix_capacity_per_0x540_region"] == 21
assert pool["proof_limit"] == "no_installer_or_ownership_edge_ties_this_pool_to_main_map2"

named = report["named_binding_result"]
assert named == {
    "assignment_policy": "no_anatomy_inference; no_assignment_without_installer_or_runtime_capture",
    "candidate_scne_name_join_row_count": 144,
    "logical_to_scne_exact_count": 0,
    "matrix_to_scne_exact_count": 0,
}
assert all(line.startswith("// PORTME at ") for line in report["portme"])
assert len(report["portme"]) == 9

expected_span_hashes = {
    "consumer_config_a": "f0917dc5416eb09e4f9a347a8e9a2af1dff1b0d4626ae777e273b278bbe3160e",
    "consumer_config_b": "ebf0ac0e0c8ae3ceb22f5c7eaa720dcd0ead2ba89dcea9254ebef734647934ee",
    "pose_storage_pointer": "3f921e453321ea074fa06f9b4adcc0da766e7091ee699335aa7d0a701e4e609e",
    "static_map2_index_lookup": "2128025a29b9343426247fe888f4228d9fc1d43ebab366b26d370f5498733acf",
    "static_map2_pair9_lookup": "5e75d6ef7e745c6d3eebd7a7a6da89cb7342c50fa559b0503c92093bb1b4ee39",
    "config_matrix_call": "86bc1f5f481589b2969d22e128f85188f014b2b88a13b464c73b445037650b61",
    "dynamic_record_sample": "a818f3629dd485fb388db94683ff103de5db61fd8936f2fb44cdc4dbb234e010",
    "dynamic_record_stride": "457062ecbdd43b438c12ea98daa41b776a035066d4d185c5e9e9ff9d44039fc4",
    "dynamic_record_destroy": "87335f36af62608d6eee5cbeda29f8bfc2715658edbb164130b085613f2b949c",
    "matrix_pool_allocator": "c318d92adf1a8cf558c5273d34660f96b691ee545aff1bdd171aacb3155301e1",
    "static_accessor_family": "5a49fc810b5d4ff9ccdf0cdf2e6d7a4a5232d6af0bb77af12e6873f1f867cedb",
    "secondary_hardcoded_config": "dac0d84a1ba0cd7f8fccbe9a2528853bd7279d07c909decf2a9a953f315b6bc1",
}
assert {row["name"]: row["sha256"] for row in report["executable_evidence"]["raw_spans"]} == expected_span_hashes
assert sum(row["ghidra_undecoded_word_count"] for row in report["executable_evidence"]["raw_spans"]) == 10

with bindings_path.open(newline="", encoding="utf-8") as stream:
    rows = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(rows) == 47
assert sum(row["domain"] == "logical_channel" for row in rows) == 25
assert sum(row["domain"] == "matrix_row" for row in rows) == 22
assert all(row["bone_name"] == "" for row in rows)
assert all(row["exact_named_binding_status"] == "unresolved_no_installer_or_runtime_capture" for row in rows)
assert rows[-1]["extent_status"] == "record_or_two_byte_alignment_unproved"

print("APF_POSE_CONFIG_BUILDER_JSON_TSV_ASSERTIONS_PASS")
PY

for marker in \
  'MAIN_MAP3 24 2 24 23' \
  'MAIN_MAP2 21 0 0 record_or_alignment_unproved' \
  'SECONDARY_MAP3 23 0 0 0' \
  'ACCESSOR 0x84AA41F0 return=void role=scale_nine_pose_floats' \
  'TARGET 0x820FC510 refs=0 raw_aligned_pointer_hits=0 materializations=1' \
  'TARGET 0x84AA4190 refs=0 raw_aligned_pointer_hits=0 materializations=0' \
  'DIRECT_MAIN_MAP3_INSTALLER_COUNT 0' \
  'DIRECT_MAIN_MAP3_INSTALLER_LIMIT indirect_runtime_dispatch_or_external_installation_not_excluded' \
  'RAW32 0x847C0C28 0x816B0040' \
  'RAW32 0x8497B8DC 0x80CB0034' \
  'RAW32 0x8497BA68 0x3BDE0040' \
  'RAW32 0x8497D600 0x939F00DC' \
  'RAW32 0x84AA40D4 0x394A0540' \
  'RAW32 0x84AC1694 0x38DCFFB8'; do
  rg -Fq "$marker" "$trace"
done

for marker in \
  'const unsigned char *apf_player_map3(void) { return (const unsigned char *)0x820FC510; }' \
  'const signed char *apf_player_map2(void) { return (const signed char *)0x820FC55C; }' \
  'PORTME at 0x8497B7B0' \
  'PORTME at 0x84AC1668' \
  'PORTME at 0x847C1470/0x847C14A4' \
  'PORTME at 0x820FC55C'; do
  rg -Fq "$marker" "$pseudo"
done

for marker in \
  'exact logical-channel-to-SCNE and matrix-row-to-SCNE name' \
  'no direct retail-XEX installer' \
  'Indirect dispatch and runtime/external installation remain open' \
  'No hard function is silently converted to clean C' \
  '// PORTME at 0x847C1470/0x847C14A4' \
  '// PORTME at 0x84AA41F0'; do
  rg -Fq "$marker" "$doc"
done

if test "${APF_POSE_CONFIG_BUILDER_GHIDRA:-0}" = 1; then
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" apf2k8 \
      -process default.xex -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts/apf" \
      -postScript ApfPoseConfigBuilderTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/pose_config_builder_trace.txt" "$trace"
  cmp "$temporary/ghidra/pose_config_builder_focused_pseudo_c.c" "$pseudo"
  echo APF_POSE_CONFIG_BUILDER_GHIDRA_REGEN_PASS
fi

echo 'APF_POSE_CONFIG_BUILDER_VALIDATION_PASS logical=25 matrix_semantic=21 matrix_ambiguous=1 named=0 dynamic_fields=9'

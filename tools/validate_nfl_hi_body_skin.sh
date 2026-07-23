#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
inventory='reports/assets/nfl2k5_resource_chunks_v2.json'
semantics='reports/assets/nfl_transform_semantics.json'
rest='reports/assets/nfl_rest_orientation.json'
axis='reports/assets/nfl_axis_root_motion.json'
post='reports/assets/nfl_player_postprocess.json'
player_transforms='reports/assets/nfl_player_postprocess_transforms.tsv'
source_gltf='assets/intermediate/nfl2k5/models/0003_0114_hi_body.gltf'
asset_dir='assets/intermediate/nfl2k5/hi_body_skin'
report='reports/assets/nfl_hi_body_skin.json'
transforms='reports/assets/nfl_hi_body_skin_transforms.tsv'
blends='reports/assets/nfl_hi_body_skin_blends.tsv'
palettes='reports/assets/nfl_hi_body_skin_palettes.tsv'
influences='reports/assets/nfl_hi_body_skin_influences.tsv'
doc='docs/research/nfl_hi_body_skin.md'

for required in \
  "$index" "$inventory" "$semantics" "$rest" "$axis" "$post" \
  "$player_transforms" "$source_gltf" \
  assets/intermediate/nfl2k5/models/0003_0114_hi_body.bin \
  "$report" "$transforms" "$blends" "$palettes" "$influences" "$doc" \
  "$asset_dir/0003_0114_hi_body_raw_skin.gltf" \
  "$asset_dir/0003_0114_hi_body_raw_skin.bin" \
  "$asset_dir/0003_0114_hi_body_meter_skin.gltf" \
  "$asset_dir/0003_0114_hi_body_meter_skin.bin" \
  tools/nfl_hi_body_skin.py tools/nfl_hi_body_skin_validate.py \
  tools/nfl_hi_body_assimp_validate.c; do
  test -f "$required"
done

test "$(sha256sum tools/nfl_hi_body_skin.py | cut -d' ' -f1)" = \
  3a29afc7ca2291a8ae06b08d69112006ecd226a167fa81ff8afab60065756c3e
test "$(sha256sum tools/nfl_hi_body_skin_validate.py | cut -d' ' -f1)" = \
  e42e6bb1503d2a8fe0d9cc7c1c5c5659f5c6c53443e29a351b17a0b9343b1ece
test "$(sha256sum tools/nfl_hi_body_assimp_validate.c | cut -d' ' -f1)" = \
  ec69c0ed5cc52b8f26287adb96bf6f15316773d5de0416f4586d8fb600c74f33
test "$(sha256sum "$report" | cut -d' ' -f1)" = \
  e14177c5b7b5e9b23fc17f90f14a47b521014a39f0e4fbd58218bc3fe5020e7e
test "$(sha256sum "$transforms" | cut -d' ' -f1)" = \
  ea8e74af7a64082f3dd18b37226e2a9503d415e02b517ffa6ecba410e87e7006
test "$(sha256sum "$blends" | cut -d' ' -f1)" = \
  49c7fcf5e0bf169816b2443f6ff608dfe1643112d01369396987418208ca9399
test "$(sha256sum "$palettes" | cut -d' ' -f1)" = \
  512363c881ec46823596a6d27deb9add7a81be55f4af832e01cdbc8c742be89e
test "$(sha256sum "$influences" | cut -d' ' -f1)" = \
  9afe30b6eba472a90827016b4cefd17f5dffb88b0874a4176f094f5264724ea7
test "$(sha256sum "$asset_dir/0003_0114_hi_body_raw_skin.gltf" | cut -d' ' -f1)" = \
  60fa7177e42f858b39bf9cad6692bd8d0c39ff14f33595a4ac164f1f2b824637
test "$(sha256sum "$asset_dir/0003_0114_hi_body_raw_skin.bin" | cut -d' ' -f1)" = \
  0f51ecf8125753b155423b2e9ec8206935222bea995f25a3d62b99288d2cd783
test "$(sha256sum "$asset_dir/0003_0114_hi_body_meter_skin.gltf" | cut -d' ' -f1)" = \
  15065af1aa5b8c39a168c0905815413cb17420697b480181922b85f668f6434a
test "$(sha256sum "$asset_dir/0003_0114_hi_body_meter_skin.bin" | cut -d' ' -f1)" = \
  3e53c4e335553f2ed4800c0664b563bec468abdca8ae162731f370c15686b75d
test "$(sha256sum "$doc" | cut -d' ' -f1)" = \
  180f9178f972589b99fd1a89f84a024f9dd89cf3c1ef85ee9285db00d4e95919

test "$(wc -l < "$transforms")" -eq 63
test "$(wc -l < "$blends")" -eq 140
test "$(wc -l < "$palettes")" -eq 4817
test "$(wc -l < "$influences")" -eq 7397

temporary=$(mktemp -d /tmp/nfl-hi-body-skin.XXXXXX)
trap 'rm -rf "$temporary"' EXIT
mkdir -p "$temporary/assets"
PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  tools/nfl_hi_body_skin.py tools/nfl_hi_body_skin_validate.py

PYTHONPATH=tools python3 tools/nfl_hi_body_skin.py "$index" \
  --resource-inventory "$inventory" \
  --transform-semantics "$semantics" \
  --rest-orientation "$rest" \
  --axis-report "$axis" \
  --player-postprocess "$post" \
  --player-transforms "$player_transforms" \
  --source-gltf "$source_gltf" \
  --output-dir "$temporary/assets" \
  --report "$temporary/nfl_hi_body_skin.json" \
  --transforms-tsv "$temporary/nfl_hi_body_skin_transforms.tsv" \
  --blends-tsv "$temporary/nfl_hi_body_skin_blends.tsv" \
  --palettes-tsv "$temporary/nfl_hi_body_skin_palettes.tsv" \
  --influences-tsv "$temporary/nfl_hi_body_skin_influences.tsv"

cmp "$temporary/nfl_hi_body_skin.json" "$report"
cmp "$temporary/nfl_hi_body_skin_transforms.tsv" "$transforms"
cmp "$temporary/nfl_hi_body_skin_blends.tsv" "$blends"
cmp "$temporary/nfl_hi_body_skin_palettes.tsv" "$palettes"
cmp "$temporary/nfl_hi_body_skin_influences.tsv" "$influences"
for name in \
  0003_0114_hi_body_raw_skin.gltf \
  0003_0114_hi_body_raw_skin.bin \
  0003_0114_hi_body_meter_skin.gltf \
  0003_0114_hi_body_meter_skin.bin; do
  cmp "$temporary/assets/$name" "$asset_dir/$name"
done
echo 'NFL_HI_BODY_SKIN_REGEN_PASS files=9'

python3 - "$report" "$doc" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

report_path, doc_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_hi_body_skin/v1"
source = report["source"]
assert source["outer_index"] == 3 and source["outer_id"] == "0x8ee9eeed"
assert source["chunk_index"] == 114 and source["resource_chunk_offset"] == 989936
assert source["decoded_size"] == 312064
assert source["decoded_sha256"] == "43c95e150c72805b419e05db3cff6cacc69c56791c349caa2f0456782775893b"

skin = report["serialized_skin"]
assert skin["scene_name"] == "hi_body" and skin["shape_name"] == "HI_res"
assert skin["vertex_count"] == skin["resolved_vertex_count"] == 7396
assert skin["unresolved_vertex_count"] == 0
assert skin["base_transform_count"] == 62
assert skin["cpu_blend_record_count"] == 139
assert skin["global_palette_count"] == 201
assert skin["submesh_count"] == 86
assert skin["palette_upload_mode"] == "per_submesh_remap"
assert skin["palette_slot_limit"] == 56
assert skin["selector_descriptor"] == "0x00040115"
assert skin["selector_min"] == 0 and skin["selector_max"] == 162
assert skin["selector_unique_count"] == 55
assert skin["cross_submesh_conflict_count"] == 0
assert skin["vertices_referenced_by_two_submeshes"] == 14
assert skin["used_global_palette_entry_count"] == 181
assert skin["influence_arity_counts"] == {"1": 5356, "2": 1921, "3": 119}
assert skin["blend_type_counts"] == {"2": 113, "3": 26}
assert skin["maximum_blend_weight_sum_error"] == 5.960464477539063e-08
assert skin["maximum_local_parent_delta_error"] == 3.814697265625e-06

xbox = report["xbox_semantics"]
assert xbox["executable_md5"] == "444064a9ec984dd29d2c05a43f5c96e8"
assert len(xbox["function_ranges"]) == 6
assert xbox["shader_object_count"] == xbox["shader_arl_a0x_v1x_count"] == 13
assert xbox["vertex_selector_equation"] == "local_matrix_slot = v1.x / 3"

gltf = report["gltf_contract"]
assert gltf["source_binary_prefix_bytes"] == 126252
assert gltf["joint_weight_accessor_count"] == 7396
assert gltf["inverse_bind_count"] == 62
assert gltf["animation_count"] == 0
assert gltf["live_profile_or_external_root_defaulted"] is False
assert gltf["raw_coordinate_basis"] == "right_handed_y_up_centimeters"
assert gltf["meter_coordinate_basis"] == "right_handed_y_up_meters"
assert gltf["axis_mapping"] == "XYZ_to_XYZ" and gltf["meter_scale"] == 0.01

assert report["outputs"]["raw"]["gltf_sha256"] == "60fa7177e42f858b39bf9cad6692bd8d0c39ff14f33595a4ac164f1f2b824637"
assert report["outputs"]["raw"]["bin_sha256"] == "0f51ecf8125753b155423b2e9ec8206935222bea995f25a3d62b99288d2cd783"
assert report["outputs"]["meter"]["gltf_sha256"] == "15065af1aa5b8c39a168c0905815413cb17420697b480181922b85f668f6434a"
assert report["outputs"]["meter"]["bin_sha256"] == "3e53c4e335553f2ed4800c0664b563bec468abdca8ae162731f370c15686b75d"
for value in report["source_pins"].values():
    path = Path(value["path"])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == value["sha256"], path
for key, value in report["proof_tsvs"].items():
    path = Path("reports/assets") / value["path"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == value["sha256"], key

assert report["ownership_result"] == {
    "all_139_cpu_blend_records_bounded": True,
    "all_62_serialized_joints_attached": True,
    "all_7396_vertices_resolved": True,
    "all_86_submesh_remap_tables_applied": True,
    "animation_or_live_root_claimed": False,
    "hi_body_HI_res_static_skin_attachment_proved": True,
    "static_skin_blockers": [],
}
assert report["failed"] == []
assert report["blockers"]["static_hi_body_skin"] == []
assert len(report["portme"]) == 3 and all(line.startswith("// PORTME:") for line in report["portme"])

doc = doc_path.read_text(encoding="utf-8")
for phrase in (
    "7,396 / 7,396",
    "One-joint vertices | 5,356",
    "Two-joint vertices | 1,921",
    "Three-joint vertices | 119",
    "there is no remaining",
    "Neither derivative contains an animation",
    "Assimp 5.3 retains",
):
    assert phrase in doc, phrase
PY

PYTHONPATH=tools python3 tools/nfl_hi_body_skin_validate.py \
  --report "$report" \
  --asset-dir "$asset_dir" \
  --transforms-tsv "$transforms" \
  --blends-tsv "$blends" \
  --palettes-tsv "$palettes" \
  --influences-tsv "$influences" \
  --index "$index" \
  --resource-inventory "$inventory"

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror \
  tools/nfl_hi_body_assimp_validate.c \
  $(pkg-config --cflags --libs assimp) -lm \
  -o "$temporary/nfl_hi_body_assimp_validate"

expected_assimp='NFL_HI_BODY_ASSIMP_PASS meshes=86 joint_nodes=62 vertices=5853 faces=18549 bones=5332 weights=12726 active_weights=7792 zero_weights=4934 max_weight_error=1.1920929e-07'
test "$("$temporary/nfl_hi_body_assimp_validate" "$asset_dir/0003_0114_hi_body_raw_skin.gltf")" = "$expected_assimp"
test "$("$temporary/nfl_hi_body_assimp_validate" "$asset_dir/0003_0114_hi_body_meter_skin.gltf")" = "$expected_assimp"
echo "$expected_assimp raw_and_meter=2"

mode=normal
if [[ "${NFL_HI_BODY_SKIN_FULL:-0}" == 1 ]]; then
  mkdir -p "$temporary/upstream"
  # Replay the two whole-SCNE-corpus generators directly. Their older wrapper
  # gates still assert obsolete pre-glTF prose, while these byte comparisons
  # retain the actual executable/corpus validation needed here.
  PYTHONPATH=tools python3 tools/nfl_transform_semantics.py "$index" \
    --resource-scan "$inventory" \
    --xbe 'extracted/ESPN NFL 2K5 (USA)/default.xbe' \
    --xbe-header reports/headers/nfl2k5_xbe_header.json \
    --cxbx-vsh tools/vendor/Cxbx-Reloaded/src/devices/video/nv2a_vsh.cpp \
    --json "$temporary/upstream/transform.json" \
    --samples-tsv "$temporary/upstream/transform_samples.tsv" \
    --influences-tsv "$temporary/upstream/transform_influences.tsv" \
    --progress-every 0
  cmp "$temporary/upstream/transform.json" reports/assets/nfl_transform_semantics.json
  cmp "$temporary/upstream/transform_samples.tsv" reports/assets/nfl_transform_semantics_samples.tsv
  cmp "$temporary/upstream/transform_influences.tsv" reports/assets/nfl_transform_semantics_influences.tsv
  echo 'NFL_HI_BODY_SKIN_FULL_TRANSFORM_CORPUS_PASS scenes=4616 shapes=54966 vertices=13731388'

  PYTHONPATH=tools python3 tools/nfl_rest_orientation.py "$index" \
    --resource-scan "$inventory" \
    --xbe 'extracted/ESPN NFL 2K5 (USA)/default.xbe' \
    --xbe-header reports/headers/nfl2k5_xbe_header.json \
    --json "$temporary/upstream/rest.json" \
    --hierarchy-tsv "$temporary/upstream/rest_hierarchy.tsv" \
    --vectors-tsv "$temporary/upstream/rest_vectors.tsv" \
    --progress-every 0
  cmp "$temporary/upstream/rest.json" reports/assets/nfl_rest_orientation.json
  cmp "$temporary/upstream/rest_hierarchy.tsv" reports/assets/nfl_rest_orientation_hierarchy.tsv
  cmp "$temporary/upstream/rest_vectors.tsv" reports/assets/nfl_rest_orientation_vectors.tsv
  echo 'NFL_HI_BODY_SKIN_FULL_REST_CORPUS_PASS transforms=110318 vectors=49'

  tools/validate_nfl_axis_root_motion.sh
  tools/validate_nfl_player_postprocess.sh
  mode=full
fi

echo "NFL_HI_BODY_SKIN_VALIDATION_COMPLETE mode=$mode joints=62 vertices=7396 blends=139 submeshes=86 animations=0"

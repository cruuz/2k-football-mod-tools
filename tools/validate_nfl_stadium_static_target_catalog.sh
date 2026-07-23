#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index=${NFL2K5_INDEX:-'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'}
scan='reports/assets/nfl2k5_resource_chunks_v2.json'
catalog='reports/specs/nfl2k5_stadium_static_target_catalog.v1.json'
report='docs/research/nfl_stadium_static_target_catalog.md'
temporary=$(mktemp -d "$root/.nfl-stadium-target-catalog.XXXXXX")
trap 'rm -rf "$temporary"' EXIT

for required in \
  "$index" "$scan" "$catalog" "$report" \
  tools/nfl_stadium_static_target_catalog.py \
  tests/test_nfl_stadium_static_target_catalog.py; do
  test -f "$required"
done

PYTHONPYCACHEPREFIX="$temporary/pycache" PYTHONPATH=tools python3 -m py_compile \
  tools/nfl_stadium_static_target_catalog.py \
  tests/test_nfl_stadium_static_target_catalog.py

PYTHONPATH=tools python3 -m unittest \
  tests.test_nfl_stadium_static_target_catalog >/dev/null

line=$(PYTHONPATH=tools python3 tools/nfl_stadium_static_target_catalog.py \
  "$index" --resource-scan "$scan" \
  --json "$temporary/catalog.json" --report "$temporary/report.md")
test "$line" = \
  'NFL_STADIUM_STATIC_TARGET_CATALOG_PASS targets=75 second=upper_deck second_consumed=908799 second_scratch=96 runtime=false sha256=f44472856044a5d8a50d18476a4c7af18ef98bcc3f7cf1d567db2b33d5336bfa'
cmp "$catalog" "$temporary/catalog.json"
cmp "$report" "$temporary/report.md"

PYTHONPATH=tools python3 tools/nfl_stadium_static_target_catalog.py \
  "$index" --resource-scan "$scan" --json "$catalog" --report "$report" \
  --check >/dev/null

jq -e '
  .schema == "nfl2k5_stadium_static_target_catalog/v1" and
  .data_policy.contains_retail_geometry_values == false and
  .data_policy.contains_retail_position_values == false and
  .data_policy.contains_retail_index_values == false and
  .scope == {
    "additional_catalog_target_count":75,
    "catalogued_resource_count":1,
    "catalogued_scene":"3280/5/2648:stadium",
    "exhaustive_for_all_477_stadium_scenes":false,
    "exhaustive_for_selected_resource":true,
    "implemented_reference_shape_count":1,
    "mechanically_eligible_shape_count_in_resource":76,
    "reason_for_bounded_v1":"close multi-shape dispatch in the already byte-proved resource before expanding archive coverage"
  } and
  (.targets | length) == 75 and
  ([.targets[].shape.index] == ([range(0;76)] - [4])) and
  ([.targets[] | select(
    .eligibility.mechanically_rigid_same_count_float3 == true and
    .position.declaration.format_name == "FLOAT3" and
    .position.stream_stride == 12 and
    .transform.base_count == 1 and
    .transform.blended_palette_entry_count == 0 and
    .transform.one_zero_root_parent_minus_one == true and
    .morph.count == 0 and
    .selectors.all_select_sole_transform == true and
    .topology_and_materials.all_vertex_references_in_bounds == true and
    .fixed_allocation.changed_stream_cap_bytes == 908864 and
    .fixed_allocation.fixed_final_tail_bytes == 16 and
    .eligibility.same_count_position_writer_implemented_for_this_target == false and
    .eligibility.runtime_visibility_proved == false
  )] | length) == 75 and
  .selected_second_target.target_id == "nfl2k5/stadium/o3280/c5/s1" and
  .selected_second_target.authored_probe.contains_retail_position_values == false and
  .selected_second_target.authored_probe.decoded_changed_byte_count == 144 and
  .selected_second_target.compression.rebuilt_consumed_bytes == 908799 and
  .selected_second_target.compression.zero_gap_bytes == 65 and
  .selected_second_target.compression.minimum_alias_scratch_bytes == 66 and
  .selected_second_target.compression.aligned_scratch_bytes == 96 and
  .selected_second_target.compression.scratch_0x60_has_retail_scne_precedent_count == 165 and
  .selected_second_target.claim_boundary.offline_fixed_allocation_fit_proved == true and
  .selected_second_target.claim_boundary.pack_write_implemented == false and
  .selected_second_target.claim_boundary.runtime_visibility_proved == false and
  .claim_flags.general_position_writer_implemented == false and
  .claim_flags.changed_topology_writer_implemented == false and
  .claim_flags.runtime_visibility_proved == false
' "$catalog" >/dev/null

python3 - "$catalog" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
text = path.read_text(encoding="utf-8")
for forbidden in ('"positions"', '"position_values"', '"indices"', '"vertices"'):
    assert forbidden not in text
upper = next(row for row in data["targets"] if row["shape"]["index"] == 1)
assert upper["shape"]["name"] == "upper_deck"
assert upper["shape"]["vertex_count"] == 12
assert upper["position"]["contiguous_decoded_span"] == {
    "offset": 0x11120,
    "end_offset": 0x111B0,
    "size": 144,
    "sha256": "95164ce59e125ac1775003846a1eb780c63f001c65f2b3da8d2aebd20fbe67f7",
}
assert upper["transform"]["table"]["sha256"] == \
    "9f93b547f55db606521ae4c19373fd857aba2b6009daecc1ceb6c724d3ca4658"
assert upper["selectors"]["lane_sha256"] == \
    "9d908ecfb6b256def8b49a7c504e6c889c4b0e41fe6ce3e01863dd7b61a20aa0"
assert upper["topology_and_materials"]["materials"] == [{
    "auxiliary_index_preserved": 1,
    "material_index": 1,
    "material_name": "sign01",
    "submesh_index": 0,
}]
assert upper["topology_and_materials"]["push_streams"][0]["commands"]["sha256"] == \
    "6811dd478e03b4be22628c3f07c27d2dcb7791b98e0f409086e3c4267bfce1b0"
assert data["selected_second_target"]["authored_probe"]["position_after_sha256"] == \
    hashlib.sha256(bytes(144)).hexdigest()
assert hashlib.sha256(path.read_bytes()).hexdigest() == \
    "f44472856044a5d8a50d18476a4c7af18ef98bcc3f7cf1d567db2b33d5336bfa"
PY

bash tools/validate_nfl_scne_static_format_spec.sh >/dev/null

catalog_size=$(stat -c %s "$catalog")
catalog_sha=$(sha256sum "$catalog" | cut -d' ' -f1)
report_size=$(stat -c %s "$report")
report_sha=$(sha256sum "$report" | cut -d' ' -f1)

echo "NFL_STADIUM_STATIC_TARGET_CATALOG_VALIDATION_PASS targets=75 vertices=16738 submeshes=423 second=upper_deck second_vertices=12 second_consumed=908799/908864 second_gap=65 second_scratch=96 scratch_0x60_retail_precedent=165 fixed_tail=16 retail_geometry=false writer=false runtime=false catalog_size=$catalog_size catalog_sha256=$catalog_sha report_size=$report_size report_sha256=$report_sha"

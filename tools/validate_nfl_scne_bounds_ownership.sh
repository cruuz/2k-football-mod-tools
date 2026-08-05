#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

tool='tools/nfl_scne_bounds_ownership.py'
test_file='tests/test_nfl_scne_bounds_ownership.py'
report='reports/assets/nfl_scne_bounds_ownership.json'
doc='docs/research/nfl_scne_bounds_ownership.md'
ghidra_script='tools/ghidra_scripts/NflScneBoundsTrace.java'
trace='reports/assets/nfl_scne_bounds_ownership_ghidra/nfl_scne_bounds_trace.txt'
pseudo='reports/assets/nfl_scne_bounds_ownership_ghidra/nfl_scne_bounds_focused_pseudo_c.c'

for required in \
  "$tool" "$test_file" "$report" "$doc" "$ghidra_script" "$trace" "$pseudo" \
  'extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' \
  reports/headers/nfl2k5_xbe_header.json \
  reports/assets/nfl2k5_resource_chunks_v2.json; do
  test -f "$required"
done

check_file() {
  local path=$1 expected_size=$2 expected_sha256=$3
  test "$(stat -c %s "$path")" = "$expected_size"
  test "$(sha256sum "$path" | cut -d' ' -f1)" = "$expected_sha256"
}

check_file "$tool" 29551 8bc7138df13e1cabbae29ec77f793ea2331fb3a3272d2f477ec002047b19b9e2
check_file "$test_file" 6811 55387579ff12e72272602375bede5682d8f98bd27295a7427db0f58f3a3c0e32
check_file "$doc" 7184 28acea11a48745a7a81e3f67a1646457c4d06c18ac82bacd43075c0859ec3422
check_file "$report" 8254 74c35c9c097e9d84a9ef8a3c9bfb163b6606f655d0fd576610fa3c9b4ec3864b
check_file "$ghidra_script" 5198 0b7b67116fa4533cf352f1b4af48e620762a9ff3ef09beab093fa9e92818d633
check_file "$trace" 73919 cf2c4f5f69ecacd32ea0937be052565696674739da2bc8f94ac174a13ef373e9
check_file "$pseudo" 30242 0ef867ee61fdda6c47bda70ac65844f2b7fb618048fc5b04f846ed9bd9ab8e72

python3 -m py_compile "$tool"
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_nfl_scne_bounds_ownership >/dev/null

temporary=$(mktemp -d /tmp/nfl-scne-bounds.XXXXXX)
trap 'rm -rf "$temporary"' EXIT
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 "$tool" \
  --json "$temporary/report.json" --progress-every 0 >/dev/null
cmp "$temporary/report.json" "$report"

jq -e '
  .schema == "nfl2k5_scne_bounds_ownership/v1" and
  .authorities.admitted_changed_counts == [4,8] and
  .authorities.external_vertex_values_admitted == false and
  .executable.md5 == "444064a9ec984dd29d2c05a43f5c96e8" and
  (.executable.function_ranges | length == 8)
' "$report" >/dev/null

jq -e '
  .corpus.counts == {
    "culling_bypass_node_count":0,
    "node_count":70555,
    "radius_scaled_node_count":0,
    "render_suppressed_node_count":0,
    "scene_count":4616,
    "shape_count":54966,
    "special_matrix_node_count":0,
    "vertex_count":13731388
  } and
  .corpus.register_zero_format_counts == {"FLOAT3":46192,"NORMSHORT3":8774} and
  .corpus.node_flag_word_counts == {"0x00000000":70555} and
  .corpus.sphere_containment.exact_containment_shape_count == 27435 and
  .corpus.sphere_containment.negative_slack_shape_count == 27531 and
  .corpus.sphere_containment.within_one_upward_radius_ulp_by_format == {
    "FLOAT3":46192,"NORMSHORT3":3002
  } and
  .corpus.sphere_containment.more_than_one_upward_radius_ulp_outside_count == 5772 and
  .corpus.upper_deck.target_id == "nfl2k5/stadium/o3280/c5/s1" and
  .corpus.upper_deck.source_vertex_count == 12 and
  .corpus.upper_deck.maximum_distance_le_radius == true and
  .corpus.upper_deck.all_admissible_4_or_8_source_subsets_contained == true
' "$report" >/dev/null

jq -e '
  .claim_flags.serialized_sphere_owner_proved == true and
  .claim_flags.frustum_culling_consumer_proved == true and
  .claim_flags.complete_static_shape_corpus_audited == true and
  .claim_flags.upper_deck_source_subset_needs_bounds_rewrite == false and
  .claim_flags.bounds_serializer_implemented == false and
  .claim_flags.arbitrary_external_positions_proved == false and
  .claim_flags.collision_or_lod_ownership_proved == false and
  .claim_flags.runtime_visibility_proved == false and
  .claim_flags.original_xbox_hardware_proved == false
' "$report" >/dev/null

for required in \
  '0x000215A0:FUN_000215a0' \
  '0x00021860:FUN_00021860' \
  '0x00023750:FUN_00023750' \
  '0x00023760:FUN_00023760' \
  '0x0002ADC0:FUN_0002adc0'; do
  rg -F "$required" "$trace" "$pseudo" >/dev/null
done
rg -F 'return (float10)*(float *)(param_1 + 0x48);' "$pseudo" >/dev/null
rg -F 'all 12 source positions inside preserved sphere' "$doc" >/dev/null
rg -F 'arbitrary glTF import' "$doc" >/dev/null

bash tools/validate_nfl_upper_deck_source_triangle_conformance.sh >/dev/null

if [[ ${NFL_SCNE_BOUNDS_GHIDRA:-0} == 1 ]]; then
  mkdir -p "$temporary/ghidra"
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" nfl2k5 \
      -process default.xbe -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts" \
      -postScript NflScneBoundsTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/nfl_scne_bounds_trace.txt" "$trace"
  cmp "$temporary/ghidra/nfl_scne_bounds_focused_pseudo_c.c" "$pseudo"
  echo NFL_SCNE_BOUNDS_GHIDRA_REGEN_PASS
fi

echo 'NFL_SCNE_BOUNDS_OWNERSHIP_VALIDATION_PASS scenes=4616 shapes=54966 vertices=13731388 float3=46192 float3_within_1ulp=46192 upper_deck_source=12 admitted=4,8 preserved_sphere=true owner=true culling=true serializer=false external=false collision_lod=false runtime=false tests=6'

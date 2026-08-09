#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

metadata_only=false
if [[ ${1-} == '--metadata-only' ]]; then
  metadata_only=true
  shift
fi
if (( $# != 0 )); then
  echo 'usage: validate_nfl_stadium_upper_deck_wide_overlay8.sh [--metadata-only]' >&2
  exit 2
fi

build='build/nfl2k5-stadium-upper-deck-wide-overlay8-20260716'
index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
boundary='reports/specs/nfl2k5_upper_deck_changed_count_boundary.v1.json'
catalog='reports/specs/nfl2k5_stadium_static_target_catalog.v1.json'
recipe_schema='reports/specs/nfl2k5_upper_deck_source_subset_recipe.schema.json'
recipe='reports/asset_samples/nfl_scne/stadium_upper_deck_wide_overlay8_source_subset_recipe.v1.json'
report='reports/specs/nfl2k5_upper_deck_board_map_wide_overlay8.v1.json'
runtime_queue='reports/specs/nfl2k5_upper_deck_wide_overlay8_runtime_queue.v1.json'
doc='docs/research/nfl_upper_deck_board_map_wide_overlay8.md'
test_file='tests/test_nfl_stadium_upper_deck_wide_overlay8.py'
retail_source='ESPN NFL 2K5 (USA).xiso.iso'
s42_source='build/nfl2k5-stadium-group36-geometry-xiso-20260713/ESPN-NFL-2K5-s42-visible-night-control.xiso.iso'
runtime_authority='reports/assets/nfl2k5_group36_s42_xemu_runtime_positive.v2.json'
retail_output="$build/ESPN-NFL-2K5-upper-deck-wide-overlay8-retail.xiso.iso"
s42_output="$build/ESPN-NFL-2K5-upper-deck-wide-overlay8-s42-visible-night.xiso.iso"

for path in \
  "$boundary" "$catalog" "$recipe_schema" "$recipe" "$report" \
  "$runtime_queue" "$doc" "$test_file" \
  tools/nfl_stadium_upper_deck_subset_verify.py \
  tools/nfl_stadium_upper_deck_subset_xiso_verify.py \
  tools/nfl_stadium_upper_deck_s42_xiso_verify.py; do
  test -f "$path"
done

test "$(stat -c %s "$recipe")" = 310
test "$(sha256sum "$recipe" | cut -d' ' -f1)" = \
  df3a552a9387cb351d3918fddf6cea106418ae1f908fce5d9b6c8f3f7c762056
test "$(stat -c %s "$report")" = 13260
test "$(sha256sum "$report" | cut -d' ' -f1)" = \
  bd6d6680efbb0e668718584f7ca9f01d3a80dbd9d00023ce886a20ff4e7cc2d1
test "$(stat -c %s "$runtime_queue")" = 8543
test "$(sha256sum "$runtime_queue" | cut -d' ' -f1)" = \
  79a14a2ed1ee006dddde33b3baab78df4a57f5169967209a6aa0d54f888a77f9
test "$(stat -c %s "$doc")" = 7964
test "$(sha256sum "$doc" | cut -d' ' -f1)" = \
  442fffa7343bf3fb20c17848430463e4afc89f734c7937278fa1e5ee7a4f30a5
test "$(stat -c %s "$test_file")" = 14276
test "$(sha256sum "$test_file" | cut -d' ' -f1)" = \
  6b3ae38b97cf89d284ee91843624db3a1d08555c269042516e1b3fd4f5376436

test "$(stat -c %s tools/nfl_stadium_upper_deck_subset_verify.py)" = 64069
test "$(sha256sum tools/nfl_stadium_upper_deck_subset_verify.py | cut -d' ' -f1)" = \
  bd8a7561e809fcd29296fcaa8123176b1bc7a3bbe3ac3ad1d30457d03404799c
test "$(stat -c %s tools/nfl_stadium_upper_deck_subset_xiso_verify.py)" = 15734
test "$(sha256sum tools/nfl_stadium_upper_deck_subset_xiso_verify.py | cut -d' ' -f1)" = \
  e22cc5476a65ee83457082a061e29a49dd15bd646dbc69ad0686c9e350c5d038
test "$(stat -c %s tools/nfl_stadium_upper_deck_s42_xiso_verify.py)" = 18113
test "$(sha256sum tools/nfl_stadium_upper_deck_s42_xiso_verify.py | cut -d' ' -f1)" = \
  a1c2513b48c5f06badbf5b33f0f3a751b7ba1673342f57d4ae5893a2db5144c8

python3 - <<'PY'
from pathlib import Path
import json

path = Path("reports/specs/nfl2k5_upper_deck_board_map_wide_overlay8.v1.json")
payload = path.read_bytes()
value = json.loads(payload)
canonical = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
assert payload == canonical
assert value["schema"] == "nfl2k5_upper_deck_board_map_wide_overlay8/v1"
assert value["status"] == "offline_positive_visibility_candidate_complete_runtime_pair_pending"
assert value["s42_control_from_retail"]["changed_byte_count"] == 45
assert value["s42_control_from_retail"]["pack9_is_retail_exact"] is True
assert value["candidate"]["decoded_changed_byte_count"] == 32
assert value["candidate"]["logical_output_quads"][1]["source_vertex_ids"] == [8, 9, 6, 7]
assert value["claims"]["installable_layout_identical_retail_xiso_built"] is True
assert value["claims"]["direct_upper_deck_runtime_visibility_proved"] is False
assert value["claims"]["manual_runtime_capture_pending"] is True
assert value["claims"]["runtime_launch_prepared"] is True
assert value["runtime_next_step"]["emulator_capture_completed"] is False
assert value["runtime_next_step"]["status"] == "manual_runtime_capture_pending"
PY

python3 - <<'PY'
from pathlib import Path
import json

path = Path("reports/specs/nfl2k5_upper_deck_wide_overlay8_runtime_queue.v1.json")
payload = path.read_bytes()
value = json.loads(payload)
canonical = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
assert payload == canonical
assert value["schema"] == "nfl2k5_upper_deck_wide_overlay8_runtime_queue/v1"
assert value["status"] == "offline_runtime_lane_prepared_manual_capture_pending"
assert value["claims"]["runtime_launch_prepared"] is True
assert value["claims"]["manual_runtime_capture_pending"] is True
assert value["claims"]["emulator_capture_completed"] is False
assert value["claims"]["direct_upper_deck_visibility_proved"] is False
assert value["runtime_capture_status"]["state"] == "manual_capture_pending"
assert len(value["manual_capture_plan"]["capture_sequence"]) == 3
assert set(value) == {
    "claims", "date", "emulator", "expected_evidence", "manual_capture_plan",
    "prepared_runs", "runtime_capture_status", "schema", "status", "target",
    "version",
}
assert set(value["manual_capture_plan"]) == {
    "camera_protocol", "capture_sequence", "comparison_questions", "scope",
    "uncertainty_policy",
}
assert set(value["runtime_capture_status"]) == {
    "desktop_environment", "emulator_capture_completed", "state",
}
assert len(value["prepared_runs"]) == 3
PY

PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile \
  tools/nfl_stadium_upper_deck_subset_verify.py \
  tools/nfl_stadium_upper_deck_subset_xiso_verify.py \
  tools/nfl_stadium_upper_deck_s42_xiso_verify.py \
  "$test_file"

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_nfl_stadium_upper_deck_wide_overlay8 >/dev/null

if "$metadata_only"; then
  echo 'NFL_UPPER_DECK_WIDE_OVERLAY8_METADATA_VALIDATION_PASS manual_capture_pending=true emulator_capture_completed=false tests=7'
  exit 0
fi

for path in \
  "$index" "$retail_source" "$s42_source" "$runtime_authority" \
  "$build/native/9" "$build/native/manifest.json" "$build/native-verification.json" \
  "$retail_output" "$build/retail-xiso-workflow.json" \
  "$build/retail-xiso-verification.json" "$s42_output" \
  "$build/s42-xiso-workflow.json" "$build/s42-xiso-verification.json"; do
  test -f "$path"
done

test "$(stat -c %s "$build/native/9")" = 634941440
test "$(stat -c %s "$retail_output")" = 6300499968
test "$(stat -c %s "$s42_output")" = 6300499968
test "$(sha256sum "$build/native/manifest.json" | cut -d' ' -f1)" = \
  3ea96253b1e858dc7e5c88e782e3aea92e84f87f1ef0d1f3795816562b2a4f97
test "$(sha256sum "$build/native-verification.json" | cut -d' ' -f1)" = \
  7c75c38a1aaab7fe38d8898d1447fa47d35792a10c9f0c833f316a8ce2b12e3c
test "$(sha256sum "$build/retail-xiso-workflow.json" | cut -d' ' -f1)" = \
  d414ff52fc5332f7c0bc2bc3b1a44aa7a93e28b2ba3565f832fd2af472901253
test "$(sha256sum "$build/retail-xiso-verification.json" | cut -d' ' -f1)" = \
  47e7dfdb086a73866ff15228a2cebdabf75dae90cf545c167da8dec1d941bb70
test "$(sha256sum "$build/s42-xiso-workflow.json" | cut -d' ' -f1)" = \
  40f5637011407be8e3f4cf59058cb9bef15cf44a90c92e905f45433927cb46c2
test "$(sha256sum "$build/s42-xiso-verification.json" | cut -d' ' -f1)" = \
  afb366b97baa80dc48ba25100c8b3e24d47b3ae2feec05fbfdd7875bbe3eb254

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

PYTHONDONTWRITEBYTECODE=1 python3 tools/nfl_stadium_upper_deck_subset_verify.py \
  --source-index "$index" \
  --boundary "$boundary" \
  --catalog "$catalog" \
  --recipe-schema "$recipe_schema" \
  --recipe "$recipe" \
  --output-dir "$build/native" \
  --report "$tmpdir/native-verification.json" >/dev/null
cmp "$tmpdir/native-verification.json" "$build/native-verification.json"

PYTHONDONTWRITEBYTECODE=1 python3 tools/nfl_stadium_upper_deck_subset_xiso_verify.py \
  --source-xiso "$retail_source" \
  --index "$index" \
  --boundary "$boundary" \
  --catalog "$catalog" \
  --recipe-schema "$recipe_schema" \
  --recipe "$recipe" \
  --subset-output-dir "$build/native" \
  --output-xiso "$retail_output" \
  --manifest "$build/retail-xiso-workflow.json" \
  >"$tmpdir/retail-xiso-verification.json"
cmp "$tmpdir/retail-xiso-verification.json" "$build/retail-xiso-verification.json"

PYTHONDONTWRITEBYTECODE=1 python3 tools/nfl_stadium_upper_deck_s42_xiso_verify.py \
  --source-xiso "$s42_source" \
  --runtime-authority "$runtime_authority" \
  --index "$index" \
  --boundary "$boundary" \
  --catalog "$catalog" \
  --recipe-schema "$recipe_schema" \
  --recipe "$recipe" \
  --subset-output-dir "$build/native" \
  --output-xiso "$s42_output" \
  --manifest "$build/s42-xiso-workflow.json" \
  >"$tmpdir/s42-xiso-verification.json"
cmp "$tmpdir/s42-xiso-verification.json" "$build/s42-xiso-verification.json"

echo 'NFL_UPPER_DECK_WIDE_OVERLAY8_VALIDATION_PASS target=3280/5/2648/1:upper_deck retail_map=base+right_inset+left_inset output_ids=0,1,2,3,8,9,6,7 vertices=8 quads=2 triangles=4 decoded_changes=32 consumed=908851/908864 scratch=32 s42_route_diff=45 candidate_disc_changes=856572 candidate_disc_runs=38041 outside_span_exact=true xdvdfs_exact=true retail_xbe_exact=true runtime_lane_prepared=true manual_capture_pending=true emulator_capture_completed=false runtime_visibility=false tests=7 independent_native_and_two_full_disc_verifiers=true'

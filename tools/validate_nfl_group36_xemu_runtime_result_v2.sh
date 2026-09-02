#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

SCHEMA='reports/specs/nfl2k5_group36_xemu_runtime_result.v2.schema.json'
REPORT='reports/assets/nfl2k5_group36_s42_xemu_runtime_positive.v2.json'
DOC='docs/research/nfl_group36_xemu_runtime_result_v2.md'
TOOL='tools/nfl_group36_xemu_runtime_result_v2.py'
VIRTUAL_TOOL='tools/nfl_group36_runtime_receipt_verify.py'
TEST='tests/test_nfl_group36_xemu_runtime_result_v2.py'
VIRTUAL_TEST='tests/test_nfl_group36_runtime_receipt_verify.py'

INDEX='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
RECIPE='.codex-tmp/nfl2k5-group36-geometry-xemu-20260713/expanded_local_wall_recipe.json'
GEOMETRY_DIR='.geometry-proof/expanded-wall-output'
STATIC_VERIFIER='tools/nfl_stadium_group36_geometry_verify.py'
CONTROL_HDD='.codex-tmp/nfl2k5-group36-geometry-xemu-20260713/xbox_hdd-s42-visible-night-control-matched.qcow2'
EXPANDED_HDD='.codex-tmp/nfl2k5-group36-geometry-xemu-20260713/xbox_hdd-s42-visible-night-expanded.qcow2'
CHAIN_SPEC='reports/specs/nfl2k5_historical_xemu_hdd_chain.v1.json'
CHAIN_SPEC_SHA='9f017bda0ffb99dd5d9859b2a92fb7e82b30d901a684635449b37bcfe91cfe90'
TEMPORARY=$(mktemp -d)
trap 'rm -rf "$TEMPORARY"' EXIT

check_pin() {
  local path="$1" size="$2" digest="$3"
  test -f "$path"
  test ! -L "$path"
  test "$(stat -c %s "$path")" = "$size"
  test "$(sha256sum "$path" | cut -d' ' -f1)" = "$digest"
}

# Preserve the complete v1 selector-negative evidence chain as immutable and
# separate from this positive v2 result.
check_pin reports/specs/nfl2k5_group36_xemu_runtime_result.v1.schema.json \
  6934 ca553ac95199813fec740a6eca305f4860daf21f062303ce2d98c689af3854b1
check_pin reports/assets/nfl2k5_group36_s42_xemu_runtime_partial.v1.json \
  4353 a606e8ef4a1030d1e2dca5202204e401eace7cc0a5b9ce0ff3443198e634bc6d
check_pin tools/nfl_group36_xemu_runtime_result.py \
  22386 3d1d6bff68f000f86f72f52db83613cef06053d0daf9d3b1e7df449843129f1f
check_pin tests/test_nfl_group36_xemu_runtime_result.py \
  9842 e449e3da9d525e59e6601df1f4f1ac53f9ed6e1b6f24169eebe23066466ab444
check_pin docs/research/nfl_group36_xemu_runtime_result.md \
  5577 df3f85b774959fc2a134fe8617b5d4cc106d6204f309bc05d739b10492e11368
check_pin tools/validate_nfl_group36_xemu_runtime_result.sh \
  5007 94f5b0213959ae7a8b725ee8490af50bdc11520a7082c7e607971b3e4f815227

check_pin "$SCHEMA" \
  15865 bd580e1abd911f5dbe16f733ececc843f94f2e862f233db10b766f38cec1c370
check_pin "$REPORT" \
  12051 33d76b3bbc9d11b52af6cf2861cf2890574a6d5b6820df8972d8419a63459d60
check_pin "$TOOL" \
  36637 80af3e1edc0bd00acc240d26bee0e299fc2b19b18144ad5b06d86556d92836e7
check_pin "$TEST" \
  9911 369ffb5767b8d606df8800f7db6d6a094db59a8aae5a32c55608d4057f3eb1cc
check_pin "$DOC" \
  10452 8029d75627b01f1a5870b4b8e33eaeb3957865ae123ea6e50b90019dcc6a28cc

PYTHONPYCACHEPREFIX="$TEMPORARY/pycache" python3 -m py_compile \
  "$TOOL" "$VIRTUAL_TOOL" "$TEST" "$VIRTUAL_TEST" \
  tools/nfl_qcow2_historical_chain_verify.py
PYTHONPATH=tools python3 -m unittest \
  tests.test_nfl_group36_xemu_runtime_result_v2 \
  tests.test_nfl_group36_runtime_receipt_verify >/dev/null

# The frozen result validator derives every claim from the immutable report.
# Retained files and the two cleaned XISOs are independently checked below.
result=$(python3 "$TOOL" --result "$REPORT")
test "$result" = \
  'NFL_GROUP36_XEMU_RUNTIME_RESULT_V2_PASS status=pinned_xemu_diagnostic_geometry_visible target_loaded=true geometry_visible=true same_sequence=true pixel_aligned=false gpu_trace=false hardware=false rsa_chain=false distribution=false production=false public_editor=false'

python3 tools/nfl_qcow2_historical_chain_verify.py \
  --root "$ROOT" \
  --spec "$CHAIN_SPEC" \
  --spec-sha256 "$CHAIN_SPEC_SHA" \
  --leaf group36_control_matched \
  >"$TEMPORARY/control-chain.json"
python3 tools/nfl_qcow2_historical_chain_verify.py \
  --root "$ROOT" \
  --spec "$CHAIN_SPEC" \
  --spec-sha256 "$CHAIN_SPEC_SHA" \
  --leaf group36_expanded \
  >"$TEMPORARY/expanded-chain.json"

virtual_result=$(PYTHONPATH=tools python3 "$VIRTUAL_TOOL" \
  --control-chain "$TEMPORARY/control-chain.json" \
  --expanded-chain "$TEMPORARY/expanded-chain.json")
test "$virtual_result" = \
  'NFL_GROUP36_RUNTIME_RECEIPT_VERIFY_PASS virtual_xisos=2 exact_hashes=true retained_artifacts=true screenshots=4 configs=2 hdd_leaves=2 geometry_visible=pinned_receipt pixel_aligned=false chain_complete=false guest_content_replayable=false historical_runtime_reexecuted=false emulator_started=false output_xiso_written=false'

python3 - "$TEMPORARY/control-chain.json" "$TEMPORARY/expanded-chain.json" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys


expected = {
    "group36_control_matched": [
        "group36_control_matched", "group36_selection_seed", "group36_root",
        "scorebug_runtime", "away_cacheclear", "jersey_tset_controller_base",
    ],
    "group36_expanded": [
        "group36_expanded", "group36_selection_seed", "group36_root",
        "scorebug_runtime", "away_cacheclear", "jersey_tset_controller_base",
    ],
}
for path in map(Path, sys.argv[1:]):
    chain = json.loads(path.read_text(encoding="utf-8"))
    assert chain["schema"] == "nfl2k5_historical_xemu_hdd_chain_verify/v1"
    assert chain["leaf"] in expected
    assert chain["base_status"] == "missing"
    assert chain["chain_complete"] is False
    assert chain["guest_content_replayable"] is False
    assert chain["historical_runtime_reexecuted"] is False
    assert chain["missing_base_reconstructed"] is False
    assert chain["substitution_allowed"] is False
    assert [row["id"] for row in chain["layers"]] == expected[chain["leaf"]]
    assert chain["layers"][-1]["pin"] is None
PY

static_verification=$(PYTHONPATH=tools python3 "$STATIC_VERIFIER" \
  --index "$INDEX" \
  --recipe "$RECIPE" \
  --output-dir "$GEOMETRY_DIR")

STATIC_VERIFICATION="$static_verification" python3 - <<'PY'
from __future__ import annotations

import json
import os


value = json.loads(os.environ["STATIC_VERIFICATION"])
assert value == {
    "consumed_bytes": 908862,
    "decoded_changed_byte_count": 48,
    "degenerate_triangle_count": 0,
    "fixed_tail_exact": True,
    "indices_after_sha256": "05e22f751efe1dca745f1e365b4e992bfcb79a57e22cd526a16150894c8cfd05",
    "indices_are_permutation": True,
    "manifest_sha256": "8d5454101129b8fc626cb42ac238ca49c6b39a4c0bdd52649fb1eba0a62d6417",
    "mode": "patched",
    "nondegenerate_triangle_count": 2,
    "output_volume_sha256": "c4ad271186e47389d00bd4131866548c8eec2320770bfeb5ce9f9ae44f3d5bad",
    "outside_authorized_geometry_bit_exact": True,
    "outside_chunk_bit_exact": True,
    "position_after_sha256": "4668d0a7693e3d92cf5261a3ef4082c27d61d34a83b4db5bb9e8f55e4f7e2709",
    "production_ready": False,
    "recipe_sha256": "3ee45f7b36fae28e51814e7695dc9bbd20d3ea4ac3a722ca53e9bf1264639625",
    "runtime_proved": False,
    "schema": "nfl2k5_group36_same_footprint_geometry_verify/v1",
    "scratch_bytes": 32,
    "source_unchanged": True,
    "unique_index_count": 4,
    "zero_gap_bytes": 2,
}
PY

python3 - "$SCHEMA" "$REPORT" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys


def canonical(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    value = json.loads(raw)
    expected = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    assert raw == expected, path
    assert isinstance(value, dict)
    return value


schema = canonical(Path(sys.argv[1]))
report = canonical(Path(sys.argv[2]))
assert schema["$id"] == "urn:nfl2k5-group36-xemu-runtime-result:v2"
assert report["schema"] == "nfl2k5_group36_xemu_runtime_result/v2"
assert report["status"] == "pinned_xemu_diagnostic_geometry_visible"
claims = report["claims"]
assert claims["target_outer_loaded_proved"] is True
assert claims["geometry_visibility_proved"] is True
assert claims["geometry_visibility_scope_pinned_xemu_diagnostic_only"] is True
assert claims["same_camera_sequence_proved"] is True
assert claims["pixel_aligned_matched_pair_proved"] is False
assert claims["strict_v1_exact_frame_branch_satisfied"] is False
assert claims["runtime_gpu_trace_proved"] is False
for key in (
    "distribution_ready",
    "original_xbox_hardware_proved",
    "production_ready",
    "public_editor_exposed",
    "retail_signed_executable_chain_preserved",
):
    assert claims[key] is False
camera = report["pair"]["camera_protocol"]
assert camera["same_sequence"] is True
assert camera["end_zone_facing"] is True
assert camera["pixel_aligned"] is False
assert camera["same_play_state"] is False
assert camera["same_team_state"] is False
assert [step["input"] for step in camera["steps"]] == [
    "left_stick_down", "dpad_up", "button_b_zoom_out"
]
for name in ("control", "expanded_wall"):
    runtime = report["runs"][name]["runtime"]
    assert runtime["clean_shutdown_observed"] is True
    assert runtime["exit_code"] == 0
    assert runtime["shutdown_method"] == "WM_DELETE_WINDOW"
PY

echo 'NFL_GROUP36_XEMU_RUNTIME_RESULT_V2_VALIDATION_PASS v1_negative_immutable=true pair=exact virtual_xisos=2 virtual_xiso_hashes=true output_xiso_written=false configs=2 hdd_branches=2 retained_hdd_layers_each=5 chain_complete=false guest_content_replayable=false historical_runtime_reexecuted=false screenshots=4 target=s42nd.iff target_loaded=true camera_sequence=exact pixel_aligned=false authored_wall_visible=true independent_static_verify=true decoded_changed=48 triangles=2 clean_exit_observed=2 gpu_trace=false hardware=false rsa_chain=false distribution=false production=false public_editor=false emulator_launched=false'

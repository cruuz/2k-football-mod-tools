#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONDONTWRITEBYTECODE=1

SOURCE="extracted/All-Pro Football 2K8 (USA)/0A"
if [[ ! -f "$SOURCE" ]]; then
  echo "error: required retail APF 0A is missing: $SOURCE" >&2
  exit 1
fi
mkdir -p "$ROOT/build"
TEMP_DIR="$(mktemp -d "$ROOT/build/apf-jersey-selector-validation.XXXXXX")"
trap 'rm -rf "$TEMP_DIR"' EXIT

python3 -m py_compile \
  tools/apf_jersey_selector_patch.py \
  tools/apf_jersey_selector_verify.py

TEST_COUNTS="$TEMP_DIR/test-counts.txt"
python3 - "$TEST_COUNTS" <<'PY'
from pathlib import Path
import sys
import unittest


def run_module(name: str) -> int:
    suite = unittest.defaultTestLoader.loadTestsFromName(name)
    discovered = suite.countTestCases()
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.skipped:
        details = "; ".join(f"{test}: {reason}" for test, reason in result.skipped)
        raise SystemExit(f"error: {name} skipped tests: {details}")
    if result.testsRun != discovered:
        raise SystemExit(
            f"error: {name} ran {result.testsRun} of {discovered} discovered tests"
        )
    if not result.wasSuccessful():
        raise SystemExit(f"error: {name} unit tests failed")
    return result.testsRun


writer = run_module("tests.test_apf_jersey_selector_patch")
verifier = run_module("tests.test_apf_jersey_selector_verify")
Path(sys.argv[1]).write_text(f"{writer} {verifier}\n", encoding="ascii")
PY
read -r WRITER_TESTS VERIFIER_TESTS < "$TEST_COUNTS"

validate_case() {
  local label="$1"
  local recipe="$2"
  local expected_mode="$3"
  local expected_changes="$4"
  local expected_payload="$5"
  local output="$TEMP_DIR/${label}-0A"
  local manifest="$TEMP_DIR/${label}-manifest.json"
  local report="$TEMP_DIR/${label}-verify.json"

  python3 tools/apf_jersey_selector_patch.py \
    --index "$SOURCE" \
    --recipe "$recipe" \
    --output-volume "$output" \
    --manifest "$manifest"

  python3 tools/apf_jersey_selector_verify.py \
    --source-index "$SOURCE" \
    --recipe "$recipe" \
    --output-volume "$output" \
    --manifest "$manifest" \
    --report "$report"

  python3 - "$manifest" "$report" "$expected_mode" "$expected_changes" "$expected_payload" <<'PY'
import json
from pathlib import Path
import sys

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
report = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
mode = sys.argv[3]
changes = int(sys.argv[4])
payload = int(sys.argv[5])
assert manifest["mode"] == report["mode"] == mode
assert manifest["preservation"]["decoded_changed_byte_count"] == changes
assert report["decoded_changed_byte_count"] == changes
assert manifest["compression"]["payload_size_after"] == payload
assert report["payload_size_after"] == payload
assert report["claims"]["all_bytes_outside_outer_entry_bit_exact"] is True
assert report["claims"]["complete_manifest_reconstructed"] is True
assert report["claims"]["emulator_runtime_visibility_proved"] is False
assert report["claims"]["original_xbox_360_hardware_proved"] is False
PY

  rm -f "$output" "$manifest" "$report"
}

validate_case \
  identity \
  reports/asset_samples/apf_roster/jersey_wasps_identity.v1.json \
  no_op 0 435225

validate_case \
  wasps-targeted \
  reports/asset_samples/apf_roster/jersey_wasps_4_to_21_targeted.v1.json \
  changed 2 435231

validate_case \
  full-unique \
  reports/asset_samples/apf_roster/jersey_all_24_built_in_unique.v1.json \
  changed 30 435262

echo "APF_JERSEY_SELECTOR_VALIDATION_PASS writer_tests=$WRITER_TESTS verifier_tests=$VERIFIER_TESTS identity_changes=0 targeted_changes=2 full_changes=30 full_payload=435262 full_headroom=762 independent_verifier=true runtime=false hardware=false"

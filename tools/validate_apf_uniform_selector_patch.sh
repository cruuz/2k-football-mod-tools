#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

source_volume=${APF_INDEX:-extracted/All-Pro Football 2K8 (USA)/0A}
recipe=reports/asset_samples/apf_roster/uniform_all_families_built_in_capacity.v1.json
schema=reports/specs/apf2k8_uniform_selector_assignment_recipe.schema.json
manifest_schema=reports/specs/apf2k8_uniform_selector_patch_manifest.schema.json
allocation=reports/assets/apf_uniform_selector_allocation.json
capacity=reports/assets/apf_uniform_selector_capacity_probe.json
closure=reports/assets/apf_uniform_selector_writeback_roundtrip.v1.json

for required in \
  "$source_volume" "$recipe" "$schema" "$manifest_schema" "$allocation" "$capacity" "$closure" \
  tools/apf_uniform_selector_recipe.py \
  tools/apf_uniform_selector_patch.py \
  tools/apf_uniform_selector_verify.py \
  tests/test_apf_uniform_selector_patch.py \
  docs/research/apf_uniform_selector_writeback.md; do
  test -f "$required"
done

test "$(wc -c < "$source_volume")" -eq 1140850688
test "$(sha256sum "$source_volume" | cut -d' ' -f1)" = \
  dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e
test "$(wc -c < "$recipe")" -eq 38317
test "$(sha256sum "$recipe" | cut -d' ' -f1)" = \
  440226a974aa9719b706a039eafafb7ffef9c2389b2e461c8ba25bcf22e24727
test "$(wc -c < "$schema")" -eq 6196
test "$(sha256sum "$schema" | cut -d' ' -f1)" = \
  728c3ccefc166d2dc64b9aee4df5b4bd243b7a341641652745a3e84c21d7bced
test "$(wc -c < "$manifest_schema")" -eq 10646
test "$(sha256sum "$manifest_schema" | cut -d' ' -f1)" = \
  f6a596531454e0cd32a40f1550640f5779ea9f6ae4e2a69247c90b121284af3b
test "$(wc -c < "$allocation")" -eq 264669
test "$(sha256sum "$allocation" | cut -d' ' -f1)" = \
  389efe3a90839bcc2210df6292817920b7bbfa1f2c0389ee632b2915adcdbef6
test "$(wc -c < "$capacity")" -eq 18842
test "$(sha256sum "$capacity" | cut -d' ' -f1)" = \
  4180997cc63129ef2df0f31a392abe270431ed490551db382ca4d91686e96213
test "$(wc -c < "$closure")" -eq 6378
test "$(sha256sum "$closure" | cut -d' ' -f1)" = \
  81ab97d1c3b292af661da36732658281ce0ee3bd2f4a847809a2fc21f2fed79f

temporary=$(mktemp -d "${APF_SELECTOR_TMPDIR:-/media/noah/Storage/.codex-tmp}/apf-uniform-selector-validation.XXXXXX")
trap 'rm -rf "$temporary"' EXIT
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX="$temporary/pycache"
export PYTHONPATH=tools

python3 -m py_compile \
  tools/apf_uniform_selector_recipe.py \
  tools/apf_uniform_selector_patch.py \
  tools/apf_uniform_selector_verify.py \
  tests/test_apf_uniform_selector_patch.py

python3 tools/apf_uniform_selector_recipe.py \
  --json "$temporary/recipe.json" > "$temporary/recipe.stdout"
cmp "$temporary/recipe.json" "$temporary/recipe.stdout"
cmp "$recipe" "$temporary/recipe.json"

python3 -m unittest -v tests/test_apf_uniform_selector_patch.py

python3 - "$closure" <<'PY'
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
raw = path.read_bytes()
closure = json.loads(raw)
assert raw == (json.dumps(closure, indent=2, sort_keys=True) + "\n").encode()
assert closure["schema"] == "apf2k8_uniform_selector_writeback_roundtrip/v1"
for row in closure["implementation"].values():
    target = Path(row["path"])
    payload = target.read_bytes()
    assert len(payload) == row["size_bytes"]
    assert hashlib.sha256(payload).hexdigest() == row["sha256"]
assert closure["proof"]["decoded_changed_byte_count"] == 190
assert closure["proof"]["output_volume_sha256"] == \
    "d2823acba35284dc35f08d3a9706476d08aba95120ccbbd168b987904f643d5a"
assert closure["claim_boundary"]["all_online_and_user_slots_bit_exact"] is True
assert closure["claim_boundary"]["emulator_runtime_visibility_proved"] is False
PY

source_before=$(sha256sum "$source_volume" | cut -d' ' -f1)
python3 tools/apf_uniform_selector_patch.py \
  --index "$source_volume" \
  --recipe "$recipe" \
  --output-volume "$temporary/all-family-0A" \
  --manifest "$temporary/all-family-manifest.json"

test "$(wc -c < "$temporary/all-family-0A")" -eq 1140850688
test "$(sha256sum "$temporary/all-family-0A" | cut -d' ' -f1)" = \
  d2823acba35284dc35f08d3a9706476d08aba95120ccbbd168b987904f643d5a
test "$(sha256sum "$temporary/all-family-manifest.json" | cut -d' ' -f1)" = \
  812b699a7c64e8e4310262381f5b81c654b4b11c6eb763d6484c42d5dc88e5a5

python3 tools/apf_uniform_selector_verify.py \
  --source-index "$source_volume" \
  --recipe "$recipe" \
  --output-volume "$temporary/all-family-0A" \
  --manifest "$temporary/all-family-manifest.json" \
  --json "$temporary/all-family-verify.json"

test "$(sha256sum "$temporary/all-family-verify.json" | cut -d' ' -f1)" = \
  a099b1fa0fe8d349a0fb4bbfaaf5115b106291b1f4c949300acaf783d6c2268c

python3 - \
  "$temporary/all-family-manifest.json" \
  "$temporary/all-family-verify.json" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

manifest_path, verify_path = map(Path, sys.argv[1:])
manifest_raw = manifest_path.read_bytes()
verify_raw = verify_path.read_bytes()
manifest = json.loads(manifest_raw)
verified = json.loads(verify_raw)
canonical = lambda value: (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
assert manifest_raw == canonical(manifest)
assert verify_raw == canonical(verified)
assert manifest["schema"] == "apf2k8_uniform_selector_patch/v1"
assert manifest["recipe"] == {
    "assignment_count": 264,
    "changed_team_family_assignment_count": 95,
    "family_count": 11,
    "schema": "apf2k8_uniform_selector_assignment_recipe/v1",
    "sha256": "440226a974aa9719b706a039eafafb7ffef9c2389b2e461c8ba25bcf22e24727",
    "size_bytes": 38317,
}
assert manifest["preservation"]["authorized_decoded_byte_count"] == 528
assert manifest["preservation"]["decoded_changed_byte_count"] == 190
assert manifest["preservation"]["online_and_user_team_selector_records_bit_exact"] is True
assert manifest["compression"]["payload_size_after"] == 435528
assert manifest["compression"]["headroom_bytes_after"] == 496
assert manifest["source"]["manifest_schema_sha256"] == \
    "f6a596531454e0cd32a40f1550640f5779ea9f6ae4e2a69247c90b121284af3b"
assert manifest["source"]["manifest_schema_size_bytes"] == 10646
assert manifest["result"]["outer_entry_sha256"] == \
    "5ecd30925837e8e847a00d1b81474955455bae5d94de0778998af26c1c59ec1d"
assert manifest["result"]["copied_volume"]["sha256"] == \
    "d2823acba35284dc35f08d3a9706476d08aba95120ccbbd168b987904f643d5a"
assert verified["claims"]["all_bytes_outside_outer_entry_bit_exact"] is True
assert verified["claims"]["all_online_and_user_slots_bit_exact"] is True
assert verified["decoded_changed_byte_count"] == 190
assert verified["decoded_output_sha256"] == \
    "90bc181b311f0f637fe2ab994845ae10a5b3202652d633c990e6b9450a79387f"
assert verified["payload_size_after"] == 435528
assert verified["output_volume_sha256"] == \
    "d2823acba35284dc35f08d3a9706476d08aba95120ccbbd168b987904f643d5a"
PY

source_after=$(sha256sum "$source_volume" | cut -d' ' -f1)
test "$source_after" = "$source_before"

echo "APF_UNIFORM_SELECTOR_VALIDATION_PASS families=11 assignments=264 changed_assignments=95 changed_bytes=190 payload=435528 headroom=496 copied_volume=d2823acba35284dc35f08d3a9706476d08aba95120ccbbd168b987904f643d5a online_user_unchanged=true runtime=false hardware=false"

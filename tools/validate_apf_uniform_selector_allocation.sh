#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index=${APF_INDEX:-extracted/All-Pro Football 2K8 (USA)/0A}
inventory=reports/assets/apf_uniform_inventory.json
allocation_report=reports/assets/apf_uniform_selector_allocation.json
capacity_report=reports/assets/apf_uniform_selector_capacity_probe.json
spec=reports/specs/apf2k8_uniform_selector_allocation.v1.json

for required in \
  "$index" "$inventory" "$allocation_report" "$capacity_report" "$spec" \
  tools/apf_uniform_selector_allocation.py \
  tools/apf_uniform_selector_capacity_probe.py \
  tools/apf_jersey_selector_patch.py \
  tests/test_apf_uniform_selector_allocation.py \
  reports/asset_samples/apf_roster/jersey_all_24_built_in_unique.v1.json \
  docs/research/apf_uniform_selector_allocation.md; do
  test -f "$required"
done

test "$(wc -c < "$inventory")" -eq 4350600
test "$(sha256sum "$inventory" | cut -d' ' -f1)" = \
  b3ad0e44af0163b30857e20c7c4e90ceb89cbc3dbc8cc41508fce3aaf1c136c7
test "$(wc -c < "$spec")" -eq 8554
test "$(sha256sum "$spec" | cut -d' ' -f1)" = \
  0eff80d01c04fbfbfc294d4125d203389c8a6cff4bcbab0ac20a227c58d6b05c
test "$(wc -c < "$allocation_report")" -eq 264669
test "$(sha256sum "$allocation_report" | cut -d' ' -f1)" = \
  389efe3a90839bcc2210df6292817920b7bbfa1f2c0389ee632b2915adcdbef6
test "$(wc -c < "$capacity_report")" -eq 18842
test "$(sha256sum "$capacity_report" | cut -d' ' -f1)" = \
  4180997cc63129ef2df0f31a392abe270431ed490551db382ca4d91686e96213

temporary=$(mktemp -d /tmp/apf-uniform-selector-allocation.XXXXXX)
trap 'rm -rf "$temporary"' EXIT
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX="$temporary/pycache"

python3 -m py_compile \
  tools/apf_uniform_selector_allocation.py \
  tools/apf_uniform_selector_capacity_probe.py \
  tests/test_apf_uniform_selector_allocation.py

source_sha_before=$(sha256sum "$index" | cut -d' ' -f1)
test "$source_sha_before" = \
  dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e

python3 tools/apf_uniform_selector_allocation.py \
  --json "$temporary/allocation.json" > "$temporary/allocation.stdout"
cmp "$temporary/allocation.json" "$temporary/allocation.stdout"
cmp "$allocation_report" "$temporary/allocation.json"

PYTHONPATH=tools python3 tools/apf_uniform_selector_capacity_probe.py \
  --index "$index" --json "$temporary/capacity.json" > "$temporary/capacity.stdout"
cmp "$temporary/capacity.json" "$temporary/capacity.stdout"
cmp "$capacity_report" "$temporary/capacity.json"

python3 - "$allocation_report" "$capacity_report" "$spec" <<'PY'
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

allocation_path, capacity_path, spec_path = map(Path, sys.argv[1:])
allocation_raw = allocation_path.read_bytes()
capacity_raw = capacity_path.read_bytes()
spec_raw = spec_path.read_bytes()
allocation = json.loads(allocation_raw)
capacity = json.loads(capacity_raw)
spec = json.loads(spec_raw)

compact = lambda value: (json.dumps(value, ensure_ascii=False,
                                     separators=(",", ":"), sort_keys=True) + "\n").encode()
pretty = lambda value: (json.dumps(value, ensure_ascii=False,
                                    indent=2, sort_keys=True) + "\n").encode()
assert allocation_raw == compact(allocation)
assert capacity_raw == compact(capacity)
assert spec_raw == pretty(spec)
assert allocation["schema"] == "apf2k8_uniform_selector_allocation/v1"
assert capacity["schema"] == "apf2k8_uniform_selector_capacity_probe/v1"
assert spec["schema"] == "apf2k8_uniform_selector_allocation_spec/v1"
assert hashlib.sha256(allocation_raw).hexdigest() == \
    capacity["source"]["allocation_report_sha256"]
assert allocation["summary"] == {
    "all_40_scope_internally_isolatable_families": ["logo", "textlogo"],
    "built_in_24_scope_internally_isolatable_families": [
        "helmet", "jersey", "logo", "textlogo", "number", "pants",
        "shoulder", "sock",
    ],
    "canonical_selector_family_count": 11,
    "filename_owned_selector_slot_count": 11,
    "physical_catalog_family_count": 12,
    "two_bank_selector_record_count_covered": 880,
}
assert allocation["combined_plans"]["built_in_24"][
    "changed_selector_byte_count_both_banks"
] == 190
assert allocation["combined_plans"]["all_40"][
    "changed_selector_byte_count_both_banks"
] == 250
assert capacity["combined"]["built_in_24"]["h7a_payload_size_bytes"] == 435528
assert capacity["combined"]["built_in_24"]["h7a_payload_headroom_bytes"] == 496
assert capacity["combined"]["all_40"]["h7a_payload_size_bytes"] == 435727
assert capacity["combined"]["all_40"]["h7a_payload_headroom_bytes"] == 297
assert all(
    scope["fits_fixed_h7a_payload_limit"]
    for family in capacity["families"]
    for scope in family["scopes"].values()
)
assert capacity["claim_boundary"]["binary_fit_is_recipe_or_write_authority"] is False
assert spec["writer_admission"]["admitted_fail_closed_selector_writer_families"] == [
    "jersey"
]
assert spec["writer_admission"]["generic_or_additional_family_writer_available"] is False
assert len(spec["writer_admission"]["required_before_admission"]) == 6

jersey = next(row for row in allocation["families"] if row["family"] == "jersey")
assert jersey["built_in_plan"]["outside_scope_boundary"] == {
    "asset_indices_shared_with_unchanged_outside_scope": [12, 13],
    "outside_scope_team_count": 16,
    "scope_team_indices_sharing_with_unchanged_outside_scope": [6, 14],
}
PY

python3 -m unittest -v tests/test_apf_uniform_selector_allocation.py

cp "$inventory" "$temporary/tampered-inventory.json"
python3 - "$temporary/tampered-inventory.json" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
payload = bytearray(path.read_bytes())
payload[-2] = ord(" ")
path.write_bytes(payload)
PY
if python3 tools/apf_uniform_selector_allocation.py \
  --inventory "$temporary/tampered-inventory.json" \
  > "$temporary/tampered.stdout" 2> "$temporary/tampered.stderr"; then
  echo "tampered inventory was accepted" >&2
  exit 1
fi
grep -q 'inventory identity drift' "$temporary/tampered.stderr"

printf sentinel > "$temporary/existing.json"
if python3 tools/apf_uniform_selector_allocation.py \
  --json "$temporary/existing.json" > /dev/null 2> "$temporary/existing.stderr"; then
  echo "existing report output was overwritten" >&2
  exit 1
fi
test "$(cat "$temporary/existing.json")" = sentinel

source_sha_after=$(sha256sum "$index" | cut -d' ' -f1)
test "$source_sha_after" = "$source_sha_before"

echo "APF_UNIFORM_SELECTOR_ALLOCATION_VALIDATION_PASS families=11 physical=12 built_in_isolatable=8 all40_isolatable=2 built_in_changes=95 built_in_bytes=190 built_in_payload=435528 built_in_headroom=496 all40_bytes=250 all40_payload=435727 all40_headroom=297 writer_at_frozen_checkpoint=jersey_only current_deterministic_writer=all_families runtime=false"

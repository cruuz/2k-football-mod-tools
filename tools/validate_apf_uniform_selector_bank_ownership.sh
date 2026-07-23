#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

tool='tools/apf_uniform_selector_bank_ownership.py'
test_file='tests/test_apf_uniform_selector_bank_ownership.py'
report='reports/specs/apf2k8_uniform_selector_bank_ownership.v1.json'
doc='docs/research/apf_uniform_selector_bank_ownership.md'

for path in "$tool" "$test_file" "$report" "$doc" \
  research/functions/apf2k8/manifest.json \
  research/functions/apf2k8/pseudo_c/apf2k8_pseudoc_12544_12799.c \
  research/functions/apf2k8/ledger/apf2k8_functions_12288_12799.jsonl \
  reports/assets/apf_uniform_ghidra/uniform_trace.txt; do
  test -f "$path"
done

test "$(stat -c %s "$tool")" = 17234
test "$(sha256sum "$tool" | cut -d' ' -f1)" = \
  799f226fa94109ce6edb84c6d3e03b9edad37da8e4f8edc943f45a319528cfb0
test "$(stat -c %s "$test_file")" = 5984
test "$(sha256sum "$test_file" | cut -d' ' -f1)" = \
  2e1eb3fa4394d238acb514422f027be1d69cc3d5b4b6b37bb8eac90cc1a431a0
test "$(stat -c %s "$report")" = 8108
test "$(sha256sum "$report" | cut -d' ' -f1)" = \
  5950496bb23fdceb97b9b5b2865ff6e45b13e4c2efccccabeb31aed216d17083
test "$(stat -c %s "$doc")" = 3747
test "$(sha256sum "$doc" | cut -d' ' -f1)" = \
  3534860b66f2e44e66542dfa788fdfde811d5f51ac34f627069681091f64702b

python3 - <<'PY'
from pathlib import Path
import json

path = Path("reports/specs/apf2k8_uniform_selector_bank_ownership.v1.json")
payload = path.read_bytes()
value = json.loads(payload)
canonical = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
assert payload == canonical
assert value["schema"] == "apf2k8_uniform_selector_bank_ownership/v1"
assert value["status"] == "static_home_away_bank_orientation_closed"
assert value["family_pair_count"] == 12
assert value["wrapper_count"] == 24
assert value["claims"]["bank_0_is_home"] is True
assert value["claims"]["bank_1_is_away"] is True
assert value["claims"]["gameplay_runtime_consumption_proved"] is False
assert value["claims"]["arbitrary_selector_writer_authorized"] is False
PY

PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile "$tool" "$test_file"
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_apf_uniform_selector_bank_ownership >/dev/null

temporary="$(mktemp)"
trap 'rm -f "$temporary"' EXIT
PYTHONDONTWRITEBYTECODE=1 python3 "$tool" --output "$temporary"
cmp "$temporary" "$report"

echo 'APF_UNIFORM_SELECTOR_BANK_OWNERSHIP_VALIDATION_PASS executable_md5=217eea6084c3d03f0f1143802b1f5636 selector=0x849D6BD0 bank0=HOME bank1=AWAY families=12 wrappers=24 literal_anchors=2 shared_non_font_resource_class_pairs=11 opaque_bytes_1_7=false runtime_consumption=false arbitrary_writer=false tests=6'

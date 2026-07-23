#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

tool='tools/apf_jersey_family_patch.py'
test_tool='tests/apf_jersey_family_patch_test.py'
report='reports/assets/apf_jersey_family_patch_roundtrip.json'
doc='docs/research/apf_jersey_family_patch.md'
for required in "$tool" "$test_tool" "$report" "$doc" \
    reports/assets/apf_jersey_family_layout.json \
    reports/assets/apf_jersey_family_layout.tsv \
    tools/apf_uniform_mip_patch.py \
    'extracted/All-Pro Football 2K8 (USA)/0A'; do
  test -f "$required"
done

temporary=$(mktemp -d /tmp/apf-jersey-family-patch-validate.XXXXXX)
trap 'rm -rf "$temporary"' EXIT
PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  "$tool" "$test_tool"

python3 "$test_tool" --full-copy --report "$temporary/report.json"
cmp "$temporary/report.json" "$report"

if python3 "$tool" \
    --index 'extracted/All-Pro Football 2K8 (USA)/0A' \
    --asset-index 24 \
    --png reports/assets/apf_uniform_samples/team00_bank0_jersey_06_jersey_color.png \
    --manifest "$temporary/invalid.json" >"$temporary/invalid.out" 2>"$temporary/invalid.err"; then
  echo 'out-of-range jersey target unexpectedly succeeded' >&2
  exit 1
fi
grep -F -- '--asset-index must be in 0..23' "$temporary/invalid.err"
test ! -e "$temporary/invalid.json"

python3 - "$report" "$doc" <<'PY'
import json
from pathlib import Path
import sys

report_path, doc_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "apf_jersey_family_patch_roundtrip/v1"
assert report["catalog"] == {
    "schema": "apf_jersey_family_layout/v1",
    "sha256": "f359a2ecd92e2305e29f2a34f1d0084ee8b2bb277a2f0bd43a1c76e12abb55dc",
    "target_count": 24,
    "all_targets_have_independent_retail_hash_pins": True,
}
assert report["source"]["sha256_before"] == report["source"]["sha256_after"]
assert report["source"]["modified"] is False
selection = report["target_selection"]
assert selection["accepted"] == list(range(24))
assert selection["rejected"] == [-1, 24]
assert selection["unique_outer_entry_count"] == 24
assert report["no_op"]["asset_index"] == 6
assert report["no_op"]["entry_bit_exact"] is True
controlled = report["controlled_edit"]
assert controlled["replacement_pixels_embedded"] is False
assert controlled["representative_asset_indices"] == [6, 14, 23]
assert [row["outer_table_index"] for row in controlled["results"]] == [875, 196, 128]
assert [row["allocation_size"] for row in controlled["results"]] == [32768, 34816, 14336]
assert [row["allocation_slack_after"] for row in controlled["results"]] == [20207, 22255, 1775]
for row in controlled["results"]:
    assert row["all_nine_levels_zero_error_decode_back"] is True
    assert row["inactive_padding_bit_exact"] is True
    assert row["footer_bit_exact"] is True
    assert row["unrelated_dram_part_preserved"] is True
copied = report["copied_volume"]
assert copied["asset_index"] == 23
assert copied["source_volume_sha256_before"] == copied["source_volume_sha256_after"]
assert copied["outside_replacement"]["source_and_output_match"] is True
assert copied["copied_archive_reparsed"] is True
safety = report["safety"]
assert safety == {
    "source_path_as_output_refused": True,
    "existing_output_refused": True,
    "fixed_allocation_gate_retained": True,
    "arbitrary_png_fit_guaranteed": False,
    "retail_source_modified": False,
    "replacement_bytes_embedded_in_report": False,
}
assert report["conclusion"] == {
    "copy_only_all_24_target_cli_exposed": True,
    "per_entry_retail_hash_gate": True,
    "representative_changed_entries_reparsed": True,
    "copied_volume_roundtrip_proved": True,
    "xenia_runtime_visibility_proved": False,
    "hardware_runtime_visibility_proved": False,
    "production_bc3_ready": False,
}

serialized = report_path.read_text(encoding="utf-8")
for forbidden in ("replacement_base64", "replacement_hex", "png_base64"):
    assert forbidden not in serialized

doc = doc_path.read_text(encoding="utf-8")
for phrase in (
    "## Worked", "## Failed or unproved", "## Blocking",
    "all 24 retail", "--asset-index", "smallest 14,336-byte allocation",
    "arbitrary PNGs", "not yet a production art pipeline",
    "APF_JERSEY_FAMILY_PATCH_VALIDATION_PASS",
):
    assert phrase in doc, phrase
PY

echo 'APF_JERSEY_FAMILY_PATCH_VALIDATION_PASS targets=24 controlled=3 copied_volume=true runtime_visibility=false'

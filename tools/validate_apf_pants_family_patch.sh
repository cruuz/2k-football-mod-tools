#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

source_volume='extracted/All-Pro Football 2K8 (USA)/0A'
layout_json='reports/assets/apf_pants_family_layout.json'
layout_tsv='reports/assets/apf_pants_family_layout.tsv'
roundtrip='reports/assets/apf_pants_family_patch_roundtrip.json'
doc='docs/research/apf_pants_family_patch.md'
temporary=$(mktemp -d /tmp/apf-pants-family-validate.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

for required in \
  "$source_volume" \
  tools/apf_xenos_bc1_mip_layout.py \
  tools/apf_pants_color_transport.py \
  tools/apf_pants_family_layout.py \
  tools/apf_pants_family_patch.py \
  tools/apf_pants_family_verify.py \
  tests/apf_pants_family_patch_test.py \
  "$layout_json" "$layout_tsv" "$roundtrip" "$doc"; do
  test -f "$required"
done

PYTHONPYCACHEPREFIX="$temporary/pycache" PYTHONPATH=tools python3 -m py_compile \
  tools/apf_xenos_bc1_mip_layout.py \
  tools/apf_pants_color_transport.py \
  tools/apf_pants_family_layout.py \
  tools/apf_pants_family_patch.py \
  tools/apf_pants_family_verify.py \
  tests/apf_pants_family_patch_test.py

PYTHONPATH=tools python3 tools/apf_pants_family_layout.py \
  --index "$source_volume" \
  --report "$temporary/layout.json" \
  --tsv "$temporary/layout.tsv"
cmp "$layout_json" "$temporary/layout.json"
cmp "$layout_tsv" "$temporary/layout.tsv"

PYTHONPATH=tools python3 tests/apf_pants_family_patch_test.py \
  --full-copy --report "$temporary/roundtrip.json"
cmp "$roundtrip" "$temporary/roundtrip.json"

python3 - "$temporary/solid.png" "$temporary/transparent.png" <<'PY'
from PIL import Image
import sys
Image.new("RGBA", (512, 512), (255, 0, 255, 255)).save(sys.argv[1])
Image.new("RGBA", (512, 512), (255, 0, 255, 254)).save(sys.argv[2])
PY

python3 - "$temporary/recipe.json" "$temporary/solid.png" <<'PY'
import json
from pathlib import Path
import sys

recipe, png = map(Path, sys.argv[1:])
recipe.write_text(json.dumps({
    "schema": "apf2k8_pants_color_recipe/v1",
    "asset_index": 23,
    "png": str(png.resolve()),
}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

PYTHONPATH=tools python3 tools/apf_pants_family_verify.py validate-recipe \
  --recipe "$temporary/recipe.json" >"$temporary/recipe-report.json"

mkdir -p "$temporary/game"
PYTHONPATH=tools python3 tools/apf_pants_family_patch.py \
  --index "$source_volume" \
  --asset-index 23 \
  --png "$temporary/solid.png" \
  --output-volume "$temporary/game/0A" \
  --manifest "$temporary/manifest.json"
ln -s "$root/extracted/All-Pro Football 2K8 (USA)/0B" "$temporary/game/0B"
ln -s "$root/extracted/All-Pro Football 2K8 (USA)/1A" "$temporary/game/1A"
ln -s "$root/extracted/All-Pro Football 2K8 (USA)/1B" "$temporary/game/1B"

PYTHONPATH=tools python3 tools/apf_pants_family_verify.py \
  --source-volume "$source_volume" \
  --output-volume "$temporary/game/0A" \
  --manifest "$temporary/manifest.json" \
  --png "$temporary/solid.png" \
  --asset-index 23 \
  --report "$temporary/verify.json"

PYTHONPATH=tools python3 tools/apf_pants_family_verify.py verify \
  --recipe "$temporary/recipe.json" \
  --source-0a "$source_volume" \
  --output-0a "$temporary/game/0A" \
  --manifest "$temporary/manifest.json" \
  --artifact-dir "$temporary/typed-artifacts"

if PYTHONPATH=tools python3 tools/apf_pants_family_patch.py \
    --index "$source_volume" --asset-index 24 \
    --png "$temporary/solid.png" --manifest "$temporary/invalid.json" \
    >"$temporary/invalid.out" 2>"$temporary/invalid.err"; then
  echo 'out-of-range APF pants target unexpectedly succeeded' >&2
  exit 1
fi
grep -F -- '--asset-index must be in 0..23' "$temporary/invalid.err"
test ! -e "$temporary/invalid.json"

if PYTHONPATH=tools python3 tools/apf_pants_family_patch.py \
    --index "$source_volume" --asset-index 6 \
    --png "$temporary/transparent.png" --manifest "$temporary/alpha.json" \
    >"$temporary/alpha.out" 2>"$temporary/alpha.err"; then
  echo 'transparent APF pants PNG unexpectedly succeeded' >&2
  exit 1
fi
grep -F 'must be fully opaque' "$temporary/alpha.err"
test ! -e "$temporary/alpha.json"

if PYTHONPATH=tools python3 tools/apf_pants_family_patch.py \
    --index "$source_volume" --asset-index 23 \
    --png "$temporary/solid.png" \
    --output-volume "$temporary/game/0A" \
    --manifest "$temporary/manifest.json" \
    >"$temporary/existing.out" 2>"$temporary/existing.err"; then
  echo 'existing APF pants outputs unexpectedly overwritten' >&2
  exit 1
fi
grep -F 'refusing to overwrite existing' "$temporary/existing.err"

python3 - "$layout_json" "$layout_tsv" "$roundtrip" "$temporary/verify.json" "$doc" \
  "$temporary/recipe-report.json" "$temporary/typed-artifacts/verification.json" <<'PY'
import csv
import hashlib
import json
from pathlib import Path
import sys

layout_path, tsv_path, roundtrip_path, verify_path, doc_path, recipe_path, typed_path = map(Path, sys.argv[1:])
layout = json.loads(layout_path.read_text(encoding="utf-8"))
rows = list(csv.DictReader(tsv_path.open(encoding="utf-8"), delimiter="\t"))
roundtrip = json.loads(roundtrip_path.read_text(encoding="utf-8"))
verify = json.loads(verify_path.read_text(encoding="utf-8"))
recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
typed = json.loads(typed_path.read_text(encoding="utf-8"))

assert recipe["schema"] == "apf2k8_pants_color_recipe/v1"
assert recipe["recipe_valid"] is True and recipe["asset_index"] == 23
assert recipe["png_dimensions"] == [512, 512]
assert recipe["png_mode"] == "RGBA" and recipe["png_fully_opaque"] is True
assert typed["schema"] == "apf_pants_family_verify/v1"
assert typed["recipe"] == {
    "asset_index": 23,
    "schema": "apf2k8_pants_color_recipe/v1",
    "sha256": hashlib.sha256((recipe_path.parent / "recipe.json").read_bytes()).hexdigest(),
}
assert typed["contains_game_or_replacement_bytes"] is False

assert hashlib.sha256(layout_path.read_bytes()).hexdigest() == "82241aefe6728a7426552663ee69ecffbdabca01f4359e8322edf75775adf293"
assert hashlib.sha256(tsv_path.read_bytes()).hexdigest() == "91406d5f018576d86765f9fb1e0e8c223f599f138c0f870564a489f726046576"
assert layout["schema"] == "apf_pants_family_layout/v1"
assert layout["source"]["sha256_before"] == layout["source"]["sha256_after"] == "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
assert layout["source"]["opened_for_write"] is False
eq = layout["family_equivalence"]
assert eq["package_count"] == 24
for key in (
    "all_24_names_resolved_by_outer_crc",
    "all_complete_txtr_descriptors_identical",
    "all_iff_structures_two_blocks_four_files",
    "all_h7a_shift_profiles_pinned",
    "all_eight_level_layouts_identical",
    "all_retail_transports_bit_exact",
    "all_controlled_solid_rebuilds_fit_fixed_allocations",
    "all_three_normal_maps_preserved",
):
    assert eq[key] is True, key
assert eq["h7a_shift_profile_counts"] == {"8,11": 19, "8,12": 5}
assert eq["minimum_controlled_allocation_slack"] == 723
descriptor = eq["canonical_txtr_descriptor"]
assert (descriptor["width"], descriptor["height"], descriptor["format"]) == (512, 512, 18)
assert descriptor["vc_base_data_length"] == 0x20000
assert descriptor["vc_mip_data_length"] == 0x10000
assert descriptor["mip_max_level"] == 7
layout_levels = eq["canonical_eight_level_layout"]
assert len(layout_levels) == 8
assert [item["data_offset"] for item in layout_levels] == [
    0, 0x20000, 0x28000, 0x2A000, 0x2C000, 0x2E000, 0x2E000, 0x2E000
]
assert [(item["level"], item["origin_block_x"], item["origin_block_y"])
        for item in layout_levels[5:]] == [(5, 4, 0), (6, 2, 0), (7, 1, 0)]
sharing = layout["selector_sharing"]
assert sharing["team_count"] == 40 and sharing["team_bank_use_count"] == 80
assert sharing["used_asset_indices"] == [0, 2, 4, 6, 10, 11, 13, 17, 18, 19, 22]
assert sharing["unused_asset_indices"] == [1, 3, 5, 7, 8, 9, 12, 14, 15, 16, 20, 21, 23]
assert sharing["asset_use_counts"] == {
    "0": 8, "1": 0, "2": 14, "3": 0, "4": 6, "5": 0,
    "6": 4, "7": 0, "8": 0, "9": 0, "10": 2, "11": 4,
    "12": 0, "13": 34, "14": 0, "15": 0, "16": 0, "17": 2,
    "18": 2, "19": 2, "20": 0, "21": 0, "22": 2, "23": 0,
}
assert len(layout["pants"]) == len(rows) == 24
for index, (item, row) in enumerate(zip(layout["pants"], rows)):
    assert item["asset_index"] == index
    assert item["outer_name"] == f"uniform_pants_{index:02d}.iff"
    assert item["iff"]["block_count"] == 2 and item["iff"]["file_count"] == 4
    assert item["inner_file"]["index"] == 2 and item["inner_file"]["name"] == "pants_color"
    assert len(item["eight_level_layout"]) == 8
    controlled = item["controlled_solid_rebuild_in_memory"]
    assert controlled["fixed_outer_allocation"] is True
    assert controlled["iff"]["three_normal_maps_preserved"] is True
    assert controlled["iff"]["allocation_slack_after"] >= 0
    assert controlled["entry_or_volume_written"] is False
    assert row["asset_index"] == str(index)
    assert row["team_bank_use_count"] == str(item["team_bank_use_count"])

boundary = layout["claim_boundary"]
assert boundary["structural_layout_generalizes_across_all_24_pants"] is True
assert boundary["in_memory_transport_and_fixed_allocation_rebuild_proved_for_all_24"] is True
assert boundary["runtime_visibility_proved"] is False
assert boundary["retail_or_copied_game_volume_written"] is False

assert roundtrip["schema"] == "apf_pants_family_patch_roundtrip/v1"
assert roundtrip["target_selection"]["accepted"] == list(range(24))
assert roundtrip["target_selection"]["rejected"] == [-1, 24]
assert roundtrip["controlled_edit"]["representative_asset_indices"] == [6, 13, 23]
assert [row["allocation_slack_after"] for row in roundtrip["controlled_edit"]["results"]] == [2986, 4773, 723]
assert roundtrip["copied_volume"]["outside_replacement"]["source_and_output_match"] is True
assert roundtrip["conclusion"]["copy_only_all_24_target_cli_exposed"] is True
assert roundtrip["conclusion"]["all_three_normal_maps_preserved"] is True
assert roundtrip["conclusion"]["xenia_runtime_visibility_proved"] is False
assert roundtrip["conclusion"]["production_dxt1_ready"] is False

assert verify["schema"] == "apf_pants_family_verify/v1"
assert verify["asset_index"] == 23 and len(verify["levels"]) == 8
for key in (
    "catalog_target_exact", "copied_archive_reparsed",
    "all_eight_levels_independently_decoded", "inactive_mip_bytes_preserved",
    "dram_block_preserved", "three_normal_maps_preserved", "footer_preserved",
    "fixed_allocation_preserved", "source_opened_read_only",
):
    assert verify["validation"][key] is True, key
assert verify["validation"]["runtime_visibility_proved"] is False
assert verify["output"]["outside_target_bit_exact"] is True
assert verify["contains_game_or_replacement_bytes"] is False

serialized = layout_path.read_text(encoding="utf-8") + roundtrip_path.read_text(encoding="utf-8")
for forbidden in ("replacement_base64", "replacement_hex", "png_base64"):
    assert forbidden not in serialized

doc = doc_path.read_text(encoding="utf-8")
for phrase in (
    "## Worked", "## Failed or unproved", "## Blocking",
    "All 24 retail", "Team selector sharing", "--asset-index",
    "723 bytes", "all three normal maps", "not yet a production art pipeline",
    "runtime visibility is not proved", "APF_PANTS_FAMILY_PATCH_VALIDATION_PASS",
):
    assert phrase in doc, phrase
PY

test "$(sha256sum "$source_volume" | cut -d' ' -f1)" = \
  dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e

echo 'APF_PANTS_FAMILY_PATCH_VALIDATION_PASS targets=24 levels=8 h7a_profiles=2 controlled=24 representative=3 copied_volume=true independent_verify=true typed_recipe=true typed_artifacts=hashes-only team_bank_uses=80 used_assets=11 normals_preserved=3 min_slack=723 opaque_only=true production_dxt1=false runtime_visibility=false retail_unchanged=true'

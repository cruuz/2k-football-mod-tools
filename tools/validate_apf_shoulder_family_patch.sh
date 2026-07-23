#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

source_volume='extracted/All-Pro Football 2K8 (USA)/0A'
layout_json='reports/assets/apf_shoulder_family_layout.json'
layout_tsv='reports/assets/apf_shoulder_family_layout.tsv'
roundtrip='reports/assets/apf_shoulder_family_patch_roundtrip.json'
doc='docs/research/apf_shoulder_family_patch.md'
temporary=$(mktemp -d /tmp/apf-shoulder-family-validate.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

for required in \
  "$source_volume" \
  tools/apf_shoulder_color_transport.py \
  tools/apf_shoulder_family_layout.py \
  tools/apf_shoulder_family_patch.py \
  tools/apf_shoulder_family_verify.py \
  tests/apf_shoulder_family_patch_test.py \
  "$layout_json" "$layout_tsv" "$roundtrip" "$doc"; do
  test -f "$required"
done

PYTHONPYCACHEPREFIX="$temporary/pycache" PYTHONPATH=tools python3 -m py_compile \
  tools/apf_shoulder_color_transport.py \
  tools/apf_shoulder_family_layout.py \
  tools/apf_shoulder_family_patch.py \
  tools/apf_shoulder_family_verify.py \
  tests/apf_shoulder_family_patch_test.py

PYTHONPATH=tools python3 tools/apf_shoulder_family_layout.py \
  --index "$source_volume" \
  --report "$temporary/layout.json" \
  --tsv "$temporary/layout.tsv"
cmp "$layout_json" "$temporary/layout.json"
cmp "$layout_tsv" "$temporary/layout.tsv"

PYTHONPATH=tools python3 tests/apf_shoulder_family_patch_test.py \
  --full-copy --report "$temporary/roundtrip.json"
cmp "$roundtrip" "$temporary/roundtrip.json"

python3 - "$temporary/solid.png" "$temporary/wrong-size.png" <<'PY'
from PIL import Image
import sys
Image.new("RGBA", (1024, 1024), (255, 0, 255, 255)).save(sys.argv[1])
Image.new("RGBA", (1023, 1024), (255, 0, 255, 255)).save(sys.argv[2])
PY

python3 -m mod_editor --create-apf-shoulder-recipe \
  "$temporary/shoulder-recipe.json" \
  --asset-index 23 \
  --shoulder-png "$temporary/solid.png"
PYTHONPATH=tools python3 tools/apf_shoulder_family_verify.py validate-recipe \
  --recipe "$temporary/shoulder-recipe.json" \
  >"$temporary/recipe-report.json"

mkdir -p "$temporary/game"
PYTHONPATH=tools python3 tools/apf_shoulder_family_patch.py \
  --index "$source_volume" \
  --asset-index 23 \
  --png "$temporary/solid.png" \
  --output-volume "$temporary/game/0A" \
  --manifest "$temporary/manifest.json"
ln -s "$root/extracted/All-Pro Football 2K8 (USA)/0B" "$temporary/game/0B"
ln -s "$root/extracted/All-Pro Football 2K8 (USA)/1A" "$temporary/game/1A"
ln -s "$root/extracted/All-Pro Football 2K8 (USA)/1B" "$temporary/game/1B"

PYTHONPATH=tools python3 tools/apf_shoulder_family_verify.py \
  --source-volume "$source_volume" \
  --output-volume "$temporary/game/0A" \
  --manifest "$temporary/manifest.json" \
  --png "$temporary/solid.png" \
  --asset-index 23 \
  --report "$temporary/verify.json"

PYTHONPATH=tools python3 tools/apf_shoulder_family_verify.py verify \
  --recipe "$temporary/shoulder-recipe.json" \
  --source-0a "$source_volume" \
  --output-0a "$temporary/game/0A" \
  --manifest "$temporary/manifest.json" \
  --artifact-dir "$temporary/typed-artifacts"
test -f "$temporary/typed-artifacts/verification.json"

if PYTHONPATH=tools python3 tools/apf_shoulder_family_patch.py \
    --index "$source_volume" --asset-index 24 \
    --png "$temporary/solid.png" --manifest "$temporary/invalid.json" \
    >"$temporary/invalid.out" 2>"$temporary/invalid.err"; then
  echo 'out-of-range APF shoulder target unexpectedly succeeded' >&2
  exit 1
fi
grep -F -- '--asset-index must be in 0..23' "$temporary/invalid.err"
test ! -e "$temporary/invalid.json"

if PYTHONPATH=tools python3 tools/apf_shoulder_family_patch.py \
    --index "$source_volume" --asset-index 5 \
    --png "$temporary/wrong-size.png" --manifest "$temporary/size.json" \
    >"$temporary/size.out" 2>"$temporary/size.err"; then
  echo 'wrong-size APF shoulder PNG unexpectedly succeeded' >&2
  exit 1
fi
grep -F 'must be exact 1024x1024 RGBA PNG' "$temporary/size.err"
test ! -e "$temporary/size.json"

if PYTHONPATH=tools python3 tools/apf_shoulder_family_patch.py \
    --index "$source_volume" --asset-index 23 \
    --png "$temporary/solid.png" \
    --output-volume "$temporary/game/0A" \
    --manifest "$temporary/manifest.json" \
    >"$temporary/existing.out" 2>"$temporary/existing.err"; then
  echo 'existing APF shoulder outputs unexpectedly overwritten' >&2
  exit 1
fi
grep -F 'refusing to overwrite existing' "$temporary/existing.err"

python3 - "$layout_json" "$layout_tsv" "$roundtrip" "$temporary/verify.json" "$doc" \
  "$temporary/shoulder-recipe.json" "$temporary/recipe-report.json" \
  "$temporary/typed-artifacts/verification.json" <<'PY'
import csv
import hashlib
import json
from pathlib import Path
import sys

(
    layout_path,
    tsv_path,
    roundtrip_path,
    verify_path,
    doc_path,
    recipe_path,
    recipe_report_path,
    typed_path,
) = map(Path, sys.argv[1:])
layout = json.loads(layout_path.read_text(encoding="utf-8"))
rows = list(csv.DictReader(tsv_path.open(encoding="utf-8"), delimiter="\t"))
roundtrip = json.loads(roundtrip_path.read_text(encoding="utf-8"))
verify = json.loads(verify_path.read_text(encoding="utf-8"))
recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
recipe_report = json.loads(recipe_report_path.read_text(encoding="utf-8"))
typed = json.loads(typed_path.read_text(encoding="utf-8"))

assert recipe == {
    "asset_index": 23,
    "png": "solid.png",
    "schema": "apf2k8_shoulder_color_recipe/v1",
}
assert recipe_report["schema"] == "apf2k8_shoulder_color_recipe/v1"
assert recipe_report["recipe_valid"] is True
assert recipe_report["asset_index"] == 23
assert recipe_report["png_dimensions"] == [1024, 1024]
assert recipe_report["png_mode"] == "RGBA"
assert typed["schema"] == "apf_shoulder_family_verify/v1"
assert typed["recipe"] == {
    "asset_index": 23,
    "schema": "apf2k8_shoulder_color_recipe/v1",
    "sha256": hashlib.sha256(recipe_path.read_bytes()).hexdigest(),
}
assert typed["contains_game_or_replacement_bytes"] is False

assert hashlib.sha256(layout_path.read_bytes()).hexdigest() == "a2ea45adb931677ef4d9d9a37530f2acc53013050793a47f41f69c65e8319875"
assert hashlib.sha256(tsv_path.read_bytes()).hexdigest() == "b18408c379ebde4006f7d7cf20688d931820c25062a5b1a1d4ed1d9010ddbc2b"
assert hashlib.sha256(roundtrip_path.read_bytes()).hexdigest() == "5a66993ffb350cb8ad79b677dd22e7b6298b1b83ff175778a0377713e13835f0"
assert layout["schema"] == "apf_shoulder_family_layout/v1"
assert layout["source"]["sha256_before"] == layout["source"]["sha256_after"] == "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
assert layout["source"]["opened_for_write"] is False
eq = layout["family_equivalence"]
assert eq["package_count"] == eq["paired_normal_package_count"] == 24
for key in (
    "all_24_color_and_normal_names_resolved_by_outer_crc",
    "all_complete_color_txtr_descriptors_identical",
    "all_iff_structures_two_blocks_four_files",
    "all_h7a_shift_profiles_9_9",
    "all_nine_level_layouts_identical",
    "all_retail_transports_bit_exact",
    "all_controlled_solid_rebuilds_fit_fixed_allocations",
    "all_three_sibling_textures_preserved",
):
    assert eq[key] is True, key
assert eq["minimum_controlled_allocation_slack"] == 4723
descriptor = eq["canonical_txtr_descriptor"]
assert (descriptor["width"], descriptor["height"], descriptor["format"]) == (1024, 1024, 20)
assert descriptor["vc_file_id"] == "0xb2f2b5ff"
assert descriptor["vc_base_data_length"] == 0x100000
assert descriptor["vc_mip_data_length"] == 0x60000
assert descriptor["mip_max_level"] == 8
levels = eq["canonical_nine_level_layout"]
assert len(levels) == 9
assert [(item["level"], item["origin_block_x"], item["origin_block_y"])
        for item in levels[6:]] == [(6, 4, 0), (7, 2, 0), (8, 1, 0)]

sharing = layout["selector_sharing"]
assert sharing["selector_slot"] == 11
assert sharing["selected_families"] == ["shoulder", "shoulder_normal"]
assert sharing["team_count"] == 40 and sharing["team_bank_use_count"] == 80
assert sharing["used_asset_indices"] == [0, 1, 3, 4, 5, 6, 7, 8, 9, 12, 15, 17, 18, 20]
assert sharing["unused_asset_indices"] == [2, 10, 11, 13, 14, 16, 19, 21, 22, 23]
assert sharing["asset_use_counts"] == {
    "0": 2, "1": 2, "2": 0, "3": 6, "4": 2, "5": 6,
    "6": 6, "7": 2, "8": 36, "9": 2, "10": 0, "11": 0,
    "12": 2, "13": 0, "14": 0, "15": 4, "16": 0, "17": 2,
    "18": 6, "19": 0, "20": 2, "21": 0, "22": 0, "23": 0,
}
assert len(layout["shoulders"]) == len(rows) == 24
for index, (item, row) in enumerate(zip(layout["shoulders"], rows)):
    assert item["asset_index"] == index
    assert item["outer_name"] == f"uniform_shoulder_{index:02d}.iff"
    assert item["paired_normal_package"]["outer_name"] == f"uniform_shoulder_normal_{index:02d}.iff"
    assert item["iff"]["block_count"] == 2 and item["iff"]["file_count"] == 4
    assert item["inner_file"]["index"] == 3 and item["inner_file"]["name"] == "shoulder_color"
    assert len(item["nine_level_layout"]) == 9
    controlled = item["controlled_solid_rebuild_in_memory"]
    assert controlled["fixed_outer_allocation"] is True
    assert controlled["iff"]["three_sibling_textures_preserved"] is True
    assert controlled["iff"]["allocation_slack_after"] >= 0
    assert controlled["entry_or_volume_written"] is False
    assert row["asset_index"] == str(index)
    assert row["team_bank_use_count"] == str(item["team_bank_use_count"])

boundary = layout["claim_boundary"]
assert boundary["structural_layout_generalizes_across_all_24_shoulders"] is True
assert boundary["in_memory_transport_and_fixed_allocation_rebuild_proved_for_all_24"] is True
assert boundary["paired_normal_packages_physically_separate_and_preserved"] is True
assert boundary["runtime_visibility_proved"] is False
assert boundary["retail_or_copied_game_volume_written"] is False

assert roundtrip["schema"] == "apf_shoulder_family_patch_roundtrip/v1"
assert roundtrip["target_selection"]["accepted"] == list(range(24))
assert roundtrip["target_selection"]["rejected"] == [-1, 24]
assert roundtrip["controlled_edit"]["representative_asset_indices"] == [5, 8, 23]
assert [row["allocation_slack_after"] for row in roundtrip["controlled_edit"]["results"]] == [33727, 10865, 4723]
assert roundtrip["copied_volume"]["outside_replacement"]["source_and_output_match"] is True
assert roundtrip["conclusion"]["copy_only_all_24_target_cli_exposed"] is True
assert roundtrip["conclusion"]["all_three_sibling_textures_preserved"] is True
assert roundtrip["conclusion"]["paired_normal_package_preserved"] is True
assert roundtrip["conclusion"]["xenia_runtime_visibility_proved"] is False
assert roundtrip["conclusion"]["production_bc3_ready"] is False

assert verify["schema"] == "apf_shoulder_family_verify/v1"
assert verify["asset_index"] == 23 and len(verify["levels"]) == 9
for key in (
    "catalog_target_exact", "copied_archive_reparsed",
    "all_nine_levels_independently_decoded", "inactive_mip_bytes_preserved",
    "dram_block_preserved", "jersey_regionmap_preserved",
    "two_sideline_textures_preserved", "paired_normal_package_preserved",
    "footer_preserved", "fixed_allocation_preserved", "source_opened_read_only",
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
    "All 24 shoulder-color", "Exact selector sharing", "--asset-index",
    "4,723", "jersey_regionmap", "paired shoulder-normal",
    "not yet a production art pipeline", "Runtime visibility is not proved",
    "APF_SHOULDER_FAMILY_PATCH_VALIDATION_PASS",
):
    assert phrase in doc, phrase
PY

test "$(sha256sum "$source_volume" | cut -d' ' -f1)" = \
  dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e

echo 'APF_SHOULDER_FAMILY_PATCH_VALIDATION_PASS targets=24 paired_normals=24 levels=9 controlled=24 representative=3 copied_volume=true independent_verify=true typed_recipe=true typed_artifacts=hashes-metrics-only team_bank_uses=80 used_assets=14 siblings_preserved=3 min_slack=4723 production_bc3=false runtime_visibility=false retail_unchanged=true'

#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

source_volume='extracted/All-Pro Football 2K8 (USA)/0A'
layout_json='reports/assets/apf_helmet_family_layout.json'
layout_tsv='reports/assets/apf_helmet_family_layout.tsv'
roundtrip='reports/assets/apf_helmet_family_patch_roundtrip.json'
doc='docs/research/apf_helmet_family_patch.md'
temporary=$(mktemp -d /tmp/apf-helmet-family-validate.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

for required in \
  "$source_volume" \
  tools/apf_xenos_dxn_mip_layout.py \
  tools/apf_helmet_color_transport.py \
  tools/apf_helmet_family_layout.py \
  tools/apf_helmet_family_patch.py \
  tools/apf_helmet_family_verify.py \
  tests/apf_helmet_family_patch_test.py \
  "$layout_json" "$layout_tsv" "$roundtrip" "$doc"; do
  test -f "$required"
done

PYTHONPYCACHEPREFIX="$temporary/pycache" PYTHONPATH=tools python3 -m py_compile \
  tools/apf_xenos_dxn_mip_layout.py \
  tools/apf_helmet_color_transport.py \
  tools/apf_helmet_family_layout.py \
  tools/apf_helmet_family_patch.py \
  tools/apf_helmet_family_verify.py \
  tests/apf_helmet_family_patch_test.py

PYTHONPATH=tools python3 tools/apf_helmet_family_layout.py \
  --index "$source_volume" \
  --report "$temporary/layout.json" \
  --tsv "$temporary/layout.tsv"
cmp "$layout_json" "$temporary/layout.json"
cmp "$layout_tsv" "$temporary/layout.tsv"

PYTHONPATH=tools python3 tests/apf_helmet_family_patch_test.py \
  --full-copy --report "$temporary/roundtrip.json"
cmp "$roundtrip" "$temporary/roundtrip.json"

python3 - "$temporary/solid.png" "$temporary/bad-b.png" "$temporary/bad-a.png" <<'PY'
from PIL import Image
import sys
Image.new("RGBA", (256, 1024), (255, 0, 0, 255)).save(sys.argv[1])
Image.new("RGBA", (256, 1024), (255, 0, 1, 255)).save(sys.argv[2])
Image.new("RGBA", (256, 1024), (255, 0, 0, 254)).save(sys.argv[3])
PY

mkdir -p "$temporary/game"
PYTHONPATH=tools python3 tools/apf_helmet_family_patch.py \
  --index "$source_volume" \
  --asset-index 23 \
  --png "$temporary/solid.png" \
  --output-volume "$temporary/game/0A" \
  --manifest "$temporary/manifest.json"
ln -s "$root/extracted/All-Pro Football 2K8 (USA)/0B" "$temporary/game/0B"
ln -s "$root/extracted/All-Pro Football 2K8 (USA)/1A" "$temporary/game/1A"
ln -s "$root/extracted/All-Pro Football 2K8 (USA)/1B" "$temporary/game/1B"

PYTHONPATH=tools python3 tools/apf_helmet_family_verify.py \
  --source-volume "$source_volume" \
  --output-volume "$temporary/game/0A" \
  --manifest "$temporary/manifest.json" \
  --png "$temporary/solid.png" \
  --asset-index 23 \
  --report "$temporary/verify.json"

python3 -m mod_editor --create-apf-helmet-recipe \
  "$temporary/helmet-recipe.json" \
  --asset-index 23 \
  --helmet-png "$temporary/solid.png"
PYTHONPATH=tools python3 tools/apf_helmet_family_verify.py validate-recipe \
  --recipe "$temporary/helmet-recipe.json"
PYTHONPATH=tools python3 tools/apf_helmet_family_verify.py verify \
  --recipe "$temporary/helmet-recipe.json" \
  --source-0a "$source_volume" \
  --output-0a "$temporary/game/0A" \
  --manifest "$temporary/manifest.json" \
  --artifact-dir "$temporary/typed-artifacts"
test -f "$temporary/typed-artifacts/verification.json"

if PYTHONPATH=tools python3 tools/apf_helmet_family_patch.py \
    --index "$source_volume" --asset-index 24 \
    --png "$temporary/solid.png" --manifest "$temporary/invalid.json" \
    >"$temporary/invalid.out" 2>"$temporary/invalid.err"; then
  echo 'out-of-range APF helmet target unexpectedly succeeded' >&2
  exit 1
fi
grep -F -- '--asset-index must be in 0..23' "$temporary/invalid.err"
test ! -e "$temporary/invalid.json"

if PYTHONPATH=tools python3 tools/apf_helmet_family_patch.py \
    --index "$source_volume" --asset-index 23 \
    --png "$temporary/bad-b.png" --manifest "$temporary/bad-b.json" \
    >"$temporary/bad-b.out" 2>"$temporary/bad-b.err"; then
  echo 'nonzero-B APF helmet PNG unexpectedly succeeded' >&2
  exit 1
fi
grep -F 'B channel must be zero' "$temporary/bad-b.err"
test ! -e "$temporary/bad-b.json"

if PYTHONPATH=tools python3 tools/apf_helmet_family_patch.py \
    --index "$source_volume" --asset-index 23 \
    --png "$temporary/bad-a.png" --manifest "$temporary/bad-a.json" \
    >"$temporary/bad-a.out" 2>"$temporary/bad-a.err"; then
  echo 'nonopaque APF helmet PNG unexpectedly succeeded' >&2
  exit 1
fi
grep -F 'A channel must be 255' "$temporary/bad-a.err"
test ! -e "$temporary/bad-a.json"

if PYTHONPATH=tools python3 tools/apf_helmet_family_patch.py \
    --index "$source_volume" --asset-index 23 \
    --png "$temporary/solid.png" \
    --output-volume "$temporary/game/0A" \
    --manifest "$temporary/manifest.json" \
    >"$temporary/existing.out" 2>"$temporary/existing.err"; then
  echo 'existing APF helmet outputs unexpectedly overwritten' >&2
  exit 1
fi
grep -F 'refusing to overwrite existing' "$temporary/existing.err"

python3 - "$layout_json" "$layout_tsv" "$roundtrip" "$temporary/verify.json" "$doc" <<'PY'
import csv
import hashlib
import json
from pathlib import Path
import sys

layout_path, tsv_path, roundtrip_path, verify_path, doc_path = map(Path, sys.argv[1:])
layout = json.loads(layout_path.read_text(encoding="utf-8"))
rows = list(csv.DictReader(tsv_path.open(encoding="utf-8"), delimiter="\t"))
roundtrip = json.loads(roundtrip_path.read_text(encoding="utf-8"))
verify = json.loads(verify_path.read_text(encoding="utf-8"))

assert hashlib.sha256(layout_path.read_bytes()).hexdigest() == \
    "29c3f097f63105f0ae2067d8f99f0ce8666e447d8bf13de4b1cb071e9638ed4c"
assert hashlib.sha256(tsv_path.read_bytes()).hexdigest() == \
    "1189ab49301c84b3b2d3edb7d1965ee0182d37f6a2d34da020311dc5b8cd2c1f"
assert hashlib.sha256(roundtrip_path.read_bytes()).hexdigest() == \
    "f85e37695b3b118f2a555e260dbfb6f207165677b68741a5b4c099fad811eb5c"
assert layout["schema"] == "apf_helmet_family_layout/v1"
assert layout["source"]["sha256_before"] == layout["source"]["sha256_after"] == \
    "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
assert layout["source"]["opened_for_write"] is False
eq = layout["family_equivalence"]
assert eq["package_count"] == 24
for key in (
    "all_24_names_resolved_by_outer_crc",
    "all_complete_txtr_descriptors_identical",
    "all_iff_structures_two_blocks_two_files",
    "all_h7a_shift_profiles_pinned",
    "all_seven_level_layouts_identical",
    "all_retail_transports_bit_exact",
    "all_controlled_two_channel_rebuilds_fit_fixed_allocations",
    "all_helmet_normal_files_preserved",
):
    assert eq[key] is True, key
assert eq["h7a_shift_profile_counts"] == {"8,10": 24}
assert eq["minimum_controlled_allocation_slack"] == 980
descriptor = eq["canonical_txtr_descriptor"]
assert (descriptor["width"], descriptor["height"], descriptor["format"]) == (256, 1024, 49)
assert descriptor["vc_base_data_length"] == 0x40000
assert descriptor["vc_mip_data_length"] == 0x20000
assert descriptor["mip_max_level"] == 6
levels = eq["canonical_seven_level_layout"]
assert len(levels) == 7
assert [item["data_offset"] for item in levels] == [
    0, 0x40000, 0x50000, 0x58000, 0x5C000, 0x5C000, 0x5C000
]
assert [(item["level"], item["origin_block_x"], item["origin_block_y"])
        for item in levels[4:]] == [(4, 4, 0), (5, 2, 0), (6, 1, 0)]
sharing = layout["selector_sharing"]
assert sharing["team_count"] == 40 and sharing["team_bank_use_count"] == 80
assert sharing["used_asset_indices"] == [0, 1, 8, 9, 12, 16]
assert sharing["asset_use_counts"] == {
    "0": 8, "1": 32, "2": 0, "3": 0, "4": 0, "5": 0,
    "6": 0, "7": 0, "8": 2, "9": 2, "10": 0, "11": 0,
    "12": 2, "13": 0, "14": 0, "15": 0, "16": 34,
    "17": 0, "18": 0, "19": 0, "20": 0, "21": 0,
    "22": 0, "23": 0,
}
assert len(layout["helmets"]) == len(rows) == 24
for index, (item, row) in enumerate(zip(layout["helmets"], rows)):
    assert item["asset_index"] == index
    assert item["outer_name"] == f"uniform_helmet_{index:02d}.iff"
    assert item["iff"]["block_count"] == 2 and item["iff"]["file_count"] == 2
    assert item["inner_file"]["index"] == 0 and item["inner_file"]["name"] == "helmet_color"
    assert item["preserved_normal_file"]["name"] == "helmet_normal"
    assert len(item["seven_level_layout"]) == 7
    controlled = item["controlled_two_channel_rebuild_in_memory"]
    assert controlled["fixed_outer_allocation"] is True
    assert controlled["iff"]["helmet_normal_preserved"] is True
    assert controlled["iff"]["allocation_slack_after"] >= 0
    assert controlled["entry_or_volume_written"] is False
    assert row["asset_index"] == str(index)

boundary = layout["claim_boundary"]
assert boundary["structural_layout_generalizes_across_all_24_helmets"] is True
assert boundary["in_memory_transport_and_fixed_allocation_rebuild_proved_for_all_24"] is True
assert boundary["helmet_normal_preservation_proved_for_all_24"] is True
assert boundary["helmet_color_channel_meanings_named"] is False
assert boundary["runtime_visibility_proved"] is False
assert boundary["retail_or_copied_game_volume_written"] is False

assert roundtrip["schema"] == "apf_helmet_family_patch_roundtrip/v1"
assert roundtrip["target_selection"]["accepted"] == list(range(24))
assert roundtrip["target_selection"]["rejected"] == [-1, 24]
assert roundtrip["controlled_edit"]["representative_asset_indices"] == [0, 16, 23]
assert [row["allocation_slack_after"] for row in roundtrip["controlled_edit"]["results"]] == \
    [6280, 24475, 980]
assert roundtrip["copied_volume"]["outside_replacement"]["source_and_output_match"] is True
assert roundtrip["conclusion"]["copy_only_all_24_target_cli_exposed"] is True
assert roundtrip["conclusion"]["all_24_controlled_rebuilds_proved_by_catalog"] is True
assert roundtrip["conclusion"]["helmet_normal_preserved"] is True
assert roundtrip["conclusion"]["helmet_color_channel_meanings_named"] is False
assert roundtrip["conclusion"]["production_dxn_ready"] is False

assert verify["schema"] == "apf_helmet_family_verify/v1"
assert verify["asset_index"] == 23 and len(verify["levels"]) == 7
for key in (
    "catalog_target_exact", "copied_archive_reparsed",
    "all_seven_levels_independently_decoded", "inactive_mip_bytes_preserved",
    "both_dram_descriptors_preserved", "helmet_normal_preserved",
    "footer_preserved", "fixed_allocation_preserved", "source_opened_read_only",
):
    assert verify["validation"][key] is True, key
assert verify["validation"]["helmet_color_channel_meanings_named"] is False
assert verify["validation"]["runtime_visibility_proved"] is False
assert verify["output"]["outside_target_bit_exact"] is True
assert verify["contains_game_or_replacement_bytes"] is False

serialized = layout_path.read_text(encoding="utf-8") + \
    roundtrip_path.read_text(encoding="utf-8")
for forbidden in ("replacement_base64", "replacement_hex", "png_base64"):
    assert forbidden not in serialized

doc = doc_path.read_text(encoding="utf-8")
for phrase in (
    "## Worked", "## Failed or unproved", "## Blocking broader release",
    "All 24 retail", "Team selector sharing", "--asset-index",
    "980 bytes", "helmet_normal", "not yet a production art",
    "Runtime visibility is not proved", "APF_HELMET_FAMILY_PATCH_VALIDATION_PASS",
):
    assert phrase in doc, phrase
PY

test "$(sha256sum "$source_volume" | cut -d' ' -f1)" = \
  dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e

echo 'APF_HELMET_FAMILY_PATCH_VALIDATION_PASS targets=24 levels=7 h7a_profile=8,10 controlled=24 representative=3 copied_volume=true independent_verify=true team_bank_uses=80 used_assets=6 normal_preserved=true min_slack=980 two_channel_png=true production_dxn=false runtime_visibility=false retail_unchanged=true'

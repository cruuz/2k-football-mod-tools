#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

source_volume='extracted/All-Pro Football 2K8 (USA)/0A'
layout='reports/assets/apf_digital_font_layout.json'
roundtrip='reports/assets/apf_digital_font_patch_roundtrip.json'
format_spec='reports/specs/apf_digital_font_asset_format.v1.json'
doc='docs/research/apf_digital_font_patch.md'
temporary=$(mktemp -d /tmp/apf-digital-font-validate.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

for required in \
  "$source_volume" \
  tools/apf_xenos_dxt5a.py \
  tools/apf_digital_font_layout.py \
  tools/apf_digital_font_transport.py \
  tools/apf_digital_font_patch.py \
  tools/apf_digital_font_verify.py \
  tests/apf_digital_font_patch_test.py \
  "$layout" "$roundtrip" "$format_spec" "$doc"; do
  test -f "$required"
done

PYTHONPYCACHEPREFIX="$temporary/pycache" PYTHONPATH=tools python3 -m py_compile \
  tools/apf_xenos_dxt5a.py \
  tools/apf_digital_font_layout.py \
  tools/apf_digital_font_transport.py \
  tools/apf_digital_font_patch.py \
  tools/apf_digital_font_verify.py \
  tests/apf_digital_font_patch_test.py

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/apf_digital_font_layout.py \
  --index "$source_volume" --report "$temporary/layout.json"
cmp "$layout" "$temporary/layout.json"

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tests/apf_digital_font_patch_test.py \
  --full-copy --report "$temporary/roundtrip.json"
cmp "$roundtrip" "$temporary/roundtrip.json"

python3 - "$temporary/colored.png" "$temporary/diagnostic.png" <<'PY'
from PIL import Image
import sys
Image.new("RGBA", (128, 128), (254, 255, 255, 128)).save(sys.argv[1])
image = Image.new("RGBA", (128, 128), (255, 255, 255, 0))
pixels = image.load()
for y in range(128):
    for x in range(128):
        alpha = 0
        if x < 4 or x >= 124 or y < 4 or y >= 124:
            alpha = 255
        if 24 <= x < 32 and 20 <= y < 108:
            alpha = 255
        if 32 <= x < 84 and (20 <= y < 28 or 60 <= y < 68 or 100 <= y < 108):
            alpha = 255
        if 84 <= x < 92 and 20 <= y < 108:
            alpha = 255
        if 100 <= x < 116:
            alpha = (y * 255) // 127
        pixels[x, y] = (255, 255, 255, alpha)
image.save(sys.argv[2])
PY

if PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/apf_digital_font_patch.py \
    --index "$source_volume" --png "$temporary/colored.png" \
    --manifest "$temporary/invalid.json" \
    >"$temporary/invalid.out" 2>"$temporary/invalid.err"; then
  echo 'colored-RGB DXT5A input unexpectedly succeeded' >&2
  exit 1
fi
grep -F 'RGB must be solid white' "$temporary/invalid.err"
test ! -e "$temporary/invalid.json"

python3 -m mod_editor --create-apf-digital-font-recipe \
  "$temporary/digital-font.recipe.json" \
  --apf-digital-font-png "$temporary/diagnostic.png"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools \
  python3 tools/apf_digital_font_verify.py validate-recipe \
  --recipe "$temporary/digital-font.recipe.json" \
  >"$temporary/recipe-report.json"

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/apf_digital_font_patch.py \
  --index "$source_volume" \
  --png "$temporary/diagnostic.png" \
  --output-volume "$temporary/game/0A" \
  --manifest "$temporary/typed-manifest.json"
ln -s "$root/extracted/All-Pro Football 2K8 (USA)/0B" "$temporary/game/0B"
ln -s "$root/extracted/All-Pro Football 2K8 (USA)/1A" "$temporary/game/1A"
ln -s "$root/extracted/All-Pro Football 2K8 (USA)/1B" "$temporary/game/1B"

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools \
  python3 tools/apf_digital_font_verify.py verify \
  --recipe "$temporary/digital-font.recipe.json" \
  --source-0a "$source_volume" \
  --output-0a "$temporary/game/0A" \
  --manifest "$temporary/typed-manifest.json" \
  --artifact-dir "$temporary/typed-artifacts"
test -f "$temporary/typed-artifacts/verification.json"

if rg -n '^import apf_digital_font_(patch|transport|layout)|^import apf_xenos_dxt5a' \
    tools/apf_digital_font_verify.py; then
  echo 'independent verifier imports a writer-side font module' >&2
  exit 1
fi

python3 - "$layout" "$roundtrip" "$format_spec" "$doc" \
  "$temporary/digital-font.recipe.json" "$temporary/recipe-report.json" \
  "$temporary/typed-artifacts/verification.json" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

(
    layout_path, roundtrip_path, spec_path, doc_path, recipe_path,
    recipe_report_path, typed_path,
) = map(Path, sys.argv[1:])
layout = json.loads(layout_path.read_text(encoding="utf-8"))
roundtrip = json.loads(roundtrip_path.read_text(encoding="utf-8"))
spec = json.loads(spec_path.read_text(encoding="utf-8"))
doc = doc_path.read_text(encoding="utf-8")
recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
recipe_report = json.loads(recipe_report_path.read_text(encoding="utf-8"))
typed = json.loads(typed_path.read_text(encoding="utf-8"))

assert recipe["schema"] == "apf2k8_digital_font_recipe/v1"
assert recipe["target"] == "digital_font"
assert recipe["scope"] == "shared-global-ui"
assert recipe["stored_channel"] == "alpha"
assert recipe["png"] == "diagnostic.png"
assert recipe_report["recipe_valid"] is True
assert recipe_report["png_dimensions"] == [128, 128]
assert recipe_report["png_mode"] == "RGBA"
assert recipe_report["png_rgb_solid_white"] is True
assert recipe_report["field_scorebug_only_proved"] is False
assert recipe_report["runtime_visibility_proved"] is False
assert recipe_report["production_dxt5a_encoder_ready"] is False
assert typed["schema"] == "apf_digital_font_verify/v1"
assert typed["recipe"]["sha256"] == hashlib.sha256(recipe_path.read_bytes()).hexdigest()
assert typed["recipe"]["alpha_sha256"] == recipe["alpha_sha256"]
assert typed["scope_boundary"] == {
    "field_scorebug_only_proved": False,
    "global_ui_consumers_mapped": False,
    "production_dxt5a_encoder_ready": False,
    "runtime_visibility_proved": False,
    "shared_global_ui_texture": True,
}
assert typed["verification"]["contains_game_or_replacement_bytes"] is False

assert hashlib.sha256(layout_path.read_bytes()).hexdigest() == \
    "1d5e83d476dee76b4013c957cb450b316ab2251d0337907e269855ac8c800a02"
assert hashlib.sha256(roundtrip_path.read_bytes()).hexdigest() == \
    "c1ccb433832fe4c3465c2f9632e3a31887133cc5f8cf811cdff71ec9b36cd06e"
assert spec["schema"] == "apf_digital_font_asset_format/v1"
assert spec["source_gate"]["outer_table_index"] == 1310
assert spec["source_gate"]["inner_file_index"] == 246
assert spec["iff"]["file_part_count"] == 751
assert spec["h7a"]["header"]["fields"][0]["required_value"] == "0x0e4837c3"
assert spec["h7a"]["token_stream"]["descriptor_bit_order"] == "least-significant bit first"
assert spec["txtr"]["xenos_fetch_constant"]["format_name"] == "DXT5A"
assert spec["txtr"]["xenos_fetch_constant"]["swizzle_components"] == [5, 5, 5, 0]
assert spec["dxt5a"]["bytes_per_block"] == 8
assert spec["dxt5a"]["logical_block_count"] == 1024
assert spec["xenos_transport"]["transport_roundtrip_must_be_bit_exact"] is True
assert spec["png_contract"]["decoded_mode"] == "RGBA"
assert spec["png_contract"]["rgb_required_value"] == [255, 255, 255]
assert spec["writer_invariants"]["unrelated_logical_part_count"] == 750
assert spec["writer_invariants"]["decoded_vram_outside_target_must_be_bit_exact"] is True
assert spec["claim_boundary"]["runtime_visibility_proved"] is False
assert layout["schema"] == "apf_digital_font_layout/v1"
assert layout["source"]["sha256_before"] == layout["source"]["sha256_after"] == \
    "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
assert layout["source"]["opened_for_write"] is False
assert layout["outer"]["index"] == 1310 and layout["outer"]["fixed_allocation"] == 25028608
assert layout["outer"]["zero_tail_slack"] == 1772
assert layout["ownership"] == {
    "file_count": 442,
    "file_part_count": 751,
    "exact_alias_group_count": 0,
    "target_overlap_owner_count": 1,
    "target_overlap_owners": [{
        "file_index": 246, "name": "digital_font", "part_index": 1,
        "offset": 0x643000, "length": 0x2000,
    }],
    "target_vram_span_exclusive": True,
}
descriptor = layout["target"]["descriptor"]
assert (descriptor["width"], descriptor["height"], descriptor["format"]) == (128, 128, 59)
assert descriptor["format_name"] == "DXT5A" and descriptor["endianness"] == 1
assert descriptor["swizzle_components"] == [5, 5, 5, 0]
assert descriptor["vc_base_data_length"] == 8192 and descriptor["vc_mip_data_length"] == 0
assert layout["transport"]["xenos_tile_endian_roundtrip_bit_exact"] is True
assert layout["claim_boundary"]["h7a_writer_proved"] is False

assert roundtrip["schema"] == "apf_digital_font_patch_roundtrip/v1"
assert roundtrip["read_only_gate"]["target_vram_span_exclusive"] is True
assert roundtrip["bounded_h7a_equivalence"]["general_and_memory_bounded_outputs_bit_exact"] is True
assert [row["shift"] for row in roundtrip["bounded_h7a_equivalence"]["profiles"]] == [8, 10, 12]
assert roundtrip["no_op"] == {
    "entry_bit_exact": True, "cli_exclusive_output_exercised": True,
}
changed = roundtrip["controlled_edit"]
assert changed["changed_dxt5a_block_count"] == 702
assert changed["decode_back_metrics"]["different_pixels"] == 0
assert changed["allocation_slack_after"] == 78773
assert changed["all_750_unrelated_inner_parts_preserved"] is True
assert changed["decoded_vram_outside_target_bit_exact"] is True
assert changed["dram_and_sram_stored_blocks_preserved"] is True
assert changed["footer_bit_exact"] is True
copied = roundtrip["copied_volume"]
assert copied["outside_replacement"]["source_and_output_match"] is True
assert copied["copied_archive_reparsed"] is True
independent = roundtrip["independent_verifier"]
assert independent["schema"] == "apf_digital_font_verify/v1"
assert independent["writer_modules_imported"] is False
assert independent["png_reencoded_independently"] is True
assert independent["xenos_tile_endian_implemented_independently"] is True
assert independent["all_750_unrelated_inner_parts_preserved"] is True
assert independent["decoded_vram_outside_target_bit_exact"] is True
safety = roundtrip["safety"]
for key in (
    "source_path_as_output_refused", "existing_output_refused",
    "wrong_dimensions_refused", "wrong_mode_refused", "nonwhite_rgb_refused",
    "fixed_allocation_overflow_refused",
):
    assert safety[key] is True, key
assert safety["arbitrary_png_fit_guaranteed"] is False
conclusion = roundtrip["conclusion"]
for key in (
    "copy_only_global_digital_font_cli_exposed", "dxt5a_encode_decode_proved",
    "xenos_tile_endian_roundtrip_proved", "full_shared_vram_h7a_rebuild_proved",
    "copied_volume_roundtrip_proved", "all_750_unrelated_inner_parts_preserved",
    "decoded_vram_outside_target_bit_exact",
):
    assert conclusion[key] is True, key
assert conclusion["xenia_runtime_visibility_proved"] is False
assert conclusion["hardware_runtime_visibility_proved"] is False
assert conclusion["production_dxt5a_encoder_ready"] is False

for phrase in (
    "offline copied-volume writer proved",
    "all other 750 parts are preserved",
    "RGB triplet exactly `(255, 255, 255)`",
    "runtime visibility is not",
    "Arbitrary PNG fit is not guaranteed",
):
    assert phrase in doc, phrase
PY

test "$(sha256sum "$source_volume" | cut -d' ' -f1)" = \
  'dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e'

echo 'APF_DIGITAL_FONT_PATCH_VALIDATION_PASS outer=1310 inner=246 format=DXT5A changed_blocks=702 parts=751 unrelated=750 slack=78773 copied_volume=true typed_recipe=true typed_artifacts=hashes-metrics-only shared_global=true field_only=false runtime=false hardware=false originals_unchanged=yes'

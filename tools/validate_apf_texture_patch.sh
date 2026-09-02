#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
report="$root/reports/assets/apf_texture_roundtrip.json"
tmp=$(mktemp -d "${TMPDIR:-/tmp}/apf-texture-patch-validate.XXXXXX")
trap 'rm -rf -- "$tmp"' EXIT

PYTHONPYCACHEPREFIX="$tmp/pycache" python3 -m py_compile \
  "$root/tools/apf_texture_patch.py" \
  "$root/tests/apf_texture_patch_test.py"

python3 "$root/tests/apf_texture_patch_test.py" \
  --full-copy \
  --report "$tmp/apf_texture_roundtrip.json"

cmp -- "$report" "$tmp/apf_texture_roundtrip.json"

python3 - "$report" <<'PY'
import json
from pathlib import Path
import sys

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert report["schema"] == "apf_texture_roundtrip_validation/v1"
assert report["scope"]["outer_entry_index"] == 810
assert report["scope"]["inner_file_index"] == 117
assert report["scope"]["inner_name"] == "draft_logo"
descriptor = report["scope"]["descriptor"]
assert (descriptor["width"], descriptor["height"]) == (128, 128)
assert descriptor["format_name"] == "DXT4_5"
assert descriptor["endianness_name"] == "8in16"
assert descriptor["tiled"] is True
assert descriptor["vc_mip_data_length"] == 0
assert len(report["unit_validation"]["h7a_vectors"]) == 7
assert all(item["roundtrip_exact"] for item in report["unit_validation"]["h7a_vectors"])
assert report["unit_validation"]["original_block1_recompression"]["decode_encode_decode_exact"] is True
assert report["unit_validation"]["xenos_tile"]["inverse_exact"] is True
assert report["unit_validation"]["bc3"]["decoded_exact"] is True
assert report["no_op"]["entry_bit_exact"] is True
assert report["no_op"]["entry_sha256_before"] == report["no_op"]["entry_sha256_after"]
assert all(report["safety_validation"].values())
patched = report["patched"]
assert patched["target"]["changed_bc3_block_indices"] == [66]
assert patched["target"]["decode_back_metrics"]["different_components"] == 0
assert patched["validation"]["unrelated_inner_part_count"] == 158
assert patched["validation"]["unrelated_inner_parts_preserved"] is True
assert patched["validation"]["h7a_decode_encode_decode_exact"] is True
assert patched["iff"]["footer_sha256_before"] == patched["iff"]["footer_sha256_after"]
assert patched["binary_patch_manifest"]["contains_replacement_bytes"] is False
live = report["live_uniform_assessment"]
assert live["team"] == "Americans"
assert live["team_banks_selecting_asset"] == [0, 1]
assert live["outer_entry_index"] == 875
assert live["inner_name"] == "jersey_color"
assert live["descriptor"]["packed_mips"] is True
assert live["descriptor"]["mip_max_level"] == 8
assert live["base_length"] == 1048576
assert live["mip_length"] == 393216
assert live["controlled_base_decode_back_exact"] is True
assert live["h7a_no_edit_roundtrip_exact"] is True
assert live["h7a_edited_roundtrip_exact"] is True
assert live["mip_sha256_before"] == live["mip_sha256_after_assessment"]
assert live["fixed_allocation_slack_if_base_only"] == 408
assert live["safe_writer_exposed"] is False
assert live["primary_mip_reference"]["commit"] == "95a5c3ee250f80c3b9d139658649d9ffb6db3eec"
copied = report["copied_volume"]
assert copied["source_volume_sha256_before"] == copied["source_volume_sha256_after"]
assert copied["outside_replacement"]["source_and_output_match"] is True
assert copied["copied_archive_reparsed_with_original_read_only_siblings"] is True
assert copied["copied_entry_sha256"] == patched["binary_patch_manifest"]["replacement_sha256"]
assert report["changed_png_fixture"]["contains_pixels"] is False
assert report["conclusion"]["retail_source_modified"] is False
assert report["conclusion"]["replacement_bytes_embedded_in_report"] is False
assert report["conclusion"]["xenia_runtime_validation"] is False
PY

echo "APF_TEXTURE_PATCH_VALIDATION_PASS mode=full-copy entry=810 file=117 h7a_vectors=7 unrelated_parts=158"

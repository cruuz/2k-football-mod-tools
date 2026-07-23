#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
report="$root/reports/assets/apf_uniform_mip_roundtrip.json"
tmp=$(mktemp -d "${TMPDIR:-/tmp}/apf-uniform-mip-validate.XXXXXX")
trap 'rm -rf -- "$tmp"' EXIT

PYTHONPYCACHEPREFIX="$tmp/pycache" python3 -m py_compile \
  "$root/tools/apf_xenos_mip_layout.py" \
  "$root/tools/apf_uniform_mip_patch.py" \
  "$root/tests/apf_uniform_mip_patch_test.py"

python3 "$root/tests/apf_uniform_mip_patch_test.py" \
  --full-copy \
  --report "$tmp/apf_uniform_mip_roundtrip.json"

cmp -- "$report" "$tmp/apf_uniform_mip_roundtrip.json"

python3 - "$report" <<'PY'
import json
from pathlib import Path
import sys

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert report["schema"] == "apf_uniform_mip_roundtrip_validation/v1"
scope = report["scope"]
assert scope["team"] == "Americans"
assert scope["outer_entry_index"] == 875
assert scope["inner_file_index"] == 0
assert scope["inner_name"] == "jersey_color"
descriptor = scope["descriptor"]
assert (descriptor["width"], descriptor["height"]) == (1024, 1024)
assert descriptor["format_name"] == "DXT4_5"
assert descriptor["endianness_name"] == "8in16"
assert descriptor["packed_mips"] is True
assert descriptor["mip_max_level"] == 8
assert report["xenia_reference"]["commit"] == "95a5c3ee250f80c3b9d139658649d9ffb6db3eec"
assert len(report["xenia_reference"]["files"]) == 5
layout = report["layout_validation"]
assert layout["declared_base_length"] == 0x100000
assert layout["declared_mip_length"] == 0x60000
assert layout["derived_final_end"] == 0x160000
assert layout["all_active_blocks_non_aliasing"] is True
assert layout["all_levels_extract_reinsert_bit_exact"] is True
assert len(layout["levels"]) == 9
assert [(x["level"], x["data_offset"], x["origin_block_x"], x["origin_block_y"]) for x in layout["levels"][6:]] == [
    (6, 0x15C000, 4, 0),
    (7, 0x15C000, 2, 0),
    (8, 0x15C000, 1, 0),
]
assert report["no_op"]["entry_bit_exact"] is True
patched = report["patched"]
assert len(patched["levels"]) == 9
assert [x["changed_bc3_blocks"]["count"] for x in patched["levels"]] == [
    65536, 16384, 4096, 1024, 256, 64, 16, 4, 1
]
assert all(x["decode_back_metrics"]["different_components"] == 0 for x in patched["levels"])
assert patched["texture"]["inactive_padding_bit_exact"] is True
assert patched["iff"]["allocation_slack_after"] >= 0
assert patched["iff"]["footer_bit_exact"] is True
assert patched["iff"]["unrelated_dram_part_preserved"] is True
assert patched["binary_patch_manifest"]["contains_replacement_bytes"] is False
copied = report["copied_volume"]
assert copied["source_volume_sha256_before"] == copied["source_volume_sha256_after"]
assert copied["outside_replacement"]["source_and_output_match"] is True
assert copied["copied_archive_reparsed_with_read_only_sibling_packs"] is True
assert copied["copied_entry_sha256"] == patched["binary_patch_manifest"]["replacement_sha256"]
assert report["controlled_edit_fixture"]["contains_pixels"] is False
safety = report["safety_validation"]
assert safety["retail_source_modified"] is False
assert safety["source_path_as_output_refused"] is True
assert safety["existing_output_refused"] is True
assert safety["fixed_outer_allocation"] is True
assert safety["unrelated_dram_part_preserved"] is True
assert safety["inactive_mip_padding_preserved"] is True
assert safety["footer_preserved"] is True
assert safety["replacement_bytes_embedded_in_report"] is False
conclusion = report["conclusion"]
assert conclusion["exact_nine_level_packed_layout_proved"] is True
assert conclusion["copy_only_writer_exposed"] is True
assert conclusion["controlled_edit_decoded_back_at_every_level"] is True
assert conclusion["copied_volume_roundtrip_proved"] is True
assert conclusion["xenia_runtime_validation"] is False
assert conclusion["hardware_runtime_validation"] is False
assert conclusion["production_bc3_ready"] is False
PY

echo "APF_UNIFORM_MIP_PATCH_VALIDATION_PASS levels=9 entry=875 file=0 copied_volume=true"

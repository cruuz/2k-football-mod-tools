#!/usr/bin/env bash
# Independent, fail-closed validator for the APF 2K8 team-logo base writer
# (tools/apf_logo_patch.py, schema apf_logo_patch/v1).  It compiles the writer
# and its proof test, regenerates the offline roundtrip + copied-volume proof to
# a private temp report, and asserts the honest invariants: the Xenos 4_4_4_4
# transport is bit-exact, decode->PNG->encode is a byte-identical no-op, a
# controlled edit changes only the logo_l0 base (mip tail + sibling logo_l1 and
# every other archive part byte-preserved), the whole-volume copy proves the
# retail source is untouched, and no runtime/scorebug effect is claimed.
#
# Regenerating to a temp path (rather than byte-diffing a committed report) keeps
# this robust across Pillow versions while still proving the writer end to end.
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
tmp=$(mktemp -d "${TMPDIR:-/tmp}/apf-logo-patch-validate.XXXXXX")
trap 'rm -rf -- "$tmp"' EXIT

PYTHONPYCACHEPREFIX="$tmp/pycache" python3 -m py_compile \
  "$root/tools/apf_logo_patch.py" \
  "$root/tests/apf_logo_patch_test.py"

python3 "$root/tests/apf_logo_patch_test.py" \
  --full-copy \
  --report "$tmp/apf_logo_roundtrip.json"

python3 - "$tmp/apf_logo_roundtrip.json" <<'PY'
import json
from pathlib import Path
import sys

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert report["schema"] == "apf_logo_roundtrip_validation/v1"

scope = report["scope"]
assert scope["outer_entry_index"] == 36
assert scope["inner_file_index"] == 1
assert scope["inner_name"] == "logo_l0"
assert scope["sibling_layer"] == "logo_l1"
descriptor = scope["descriptor"]
assert (descriptor["width"], descriptor["height"]) == (512, 512)
assert descriptor["tiled"] is True
assert descriptor["packed_mips"] is True

assert report["transport"]["decode_encode_bit_exact"] is True
assert report["no_op"]["entry_bit_exact"] is True
assert report["no_op"]["entry_sha256_before"] == report["no_op"]["entry_sha256_after"]

patched = report["patched"]
assert patched["mode"] == "patched"
assert patched["mip_tail"]["bit_exact"] is True
assert patched["iff"]["footer_bit_exact"] is True
assert patched["iff"]["allocation_slack_after"] >= 0
assert patched["validation"]["other_level_l1_preserved"] is True
assert patched["validation"]["changed_inner_parts"] == [
    {"file_index": 1, "part_index": 1, "block_index": 1}
]
assert patched["base_data"]["decode_back_metrics"]["maximum_absolute_error"] == 0
assert patched["binary_patch_manifest"]["contains_replacement_bytes"] is False

safety = report["safety_validation"]
assert safety["retail_source_modified"] is False
assert safety["source_path_as_output_refused"] is True
assert safety["existing_output_refused"] is True
assert safety["wrong_dimensions_refused"] is True
assert safety["fixed_outer_allocation"] is True
assert safety["mip_tail_preserved"] is True
assert safety["sibling_logo_l1_preserved"] is True
assert safety["footer_preserved"] is True
assert safety["replacement_bytes_embedded_in_report"] is False

copied = report["copied_volume"]
assert copied is not None, "run with --full-copy to prove the whole-volume copy"
assert copied["mode"] == "replaced_entry"
assert copied["source_volume_sha256_before"] == copied["source_volume_sha256_after"]
assert copied["outside_replacement"]["source_and_output_match"] is True

conclusion = report["conclusion"]
assert conclusion["offline_base_level_write_proved"] is True
assert conclusion["copy_only_writer_exposed"] is True
assert conclusion["controlled_edit_decoded_back_exactly"] is True
assert conclusion["copied_volume_roundtrip_proved"] is True
# Honest negatives: no runtime capture exists yet.
assert conclusion["xenia_runtime_validation"] is False
assert conclusion["hardware_runtime_validation"] is False
assert conclusion["scorebug_runtime_binding_proved"] is False
assert conclusion["mip_regeneration_implemented"] is False
PY

echo "APF_LOGO_PATCH_VALIDATION_PASS mode=full-copy entry=36 file=1 base=512x512 format=4_4_4_4"

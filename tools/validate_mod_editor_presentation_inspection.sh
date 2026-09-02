#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

temporary="$(mktemp -d /tmp/mod-editor-presentation.XXXXXX)"
trap 'rm -rf "$temporary"' EXIT
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX="$temporary/pycache"

python3 -m py_compile \
  mod_editor/core/presentation_inspection.py \
  tests/mod_editor/test_presentation_inspection.py

test "$(wc -c < reports/assets/scorebug_presentation_audit.json)" = 46512
test "$(sha256sum reports/assets/scorebug_presentation_audit.json | cut -d' ' -f1)" = \
  57bcbb1c0ff8e6c2376565365aba523e4c2fe8cdb66d3a7058daa84993c2ccd1
test "$(wc -c < reports/assets/apf_digital_font_layout.json)" = 4920
test "$(sha256sum reports/assets/apf_digital_font_layout.json | cut -d' ' -f1)" = \
  1d5e83d476dee76b4013c957cb450b316ab2251d0337907e269855ac8c800a02
test "$(wc -c < reports/assets/apf_digital_font_patch_roundtrip.json)" = 4738
test "$(sha256sum reports/assets/apf_digital_font_patch_roundtrip.json | cut -d' ' -f1)" = \
  96ee9a01eec320011154531272c570cbf2227c3d7ef9d1fe9ff5638baeac3b70

python3 -m unittest -v tests/mod_editor/test_presentation_inspection.py
python3 -m mod_editor --inspect-apf-scorebug > "$temporary/inspection.json"

python3 - "$temporary/inspection.json" <<'PY'
import json
from pathlib import Path
import re
import sys

value = json.loads(Path(sys.argv[1]).read_text())
assert value["schema"] == "mod_editor_apf_scorebug_presentation_inspection/v1"
assert value["field_scorebug"]["component_count"] == 7
assert value["safe_writer_count"] == 1
font = value["digital_font"]
assert font["dimensions"] == [128, 128] and font["format"] == "DXT5A"
assert font["copy_only_writer_proved"] is True
assert font["all_unrelated_global_parts_preserved"] is True
assert font["runtime_visibility_proved"] is False
text = json.dumps(value)
assert re.search(r"0x[0-9a-f]+", text, re.I) is None
assert "offset" not in text.lower()
PY

help="$(python3 -m mod_editor --help)"
rg -q -- '--inspect-apf-scorebug' <<<"$help"
rg -q 'offline copied-volume writer proved' docs/research/apf_digital_font_patch.md

echo 'MOD_EDITOR_PRESENTATION_INSPECTION_VALIDATION_PASS game=apf2k8 components=7 font=DXT5A writer=1 runtime=false raw_offsets=false report_pins=3 tests=3'

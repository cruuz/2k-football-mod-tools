#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$root"

python3 -m py_compile \
  tools/apf_audo_exact_slot.py \
  mod_editor/apf_studio/project.py \
  mod_editor/apf_studio/session.py \
  mod_editor/apf_studio/build.py
python3 -m unittest \
  tests.mod_editor.test_apf_audo_exact_slot \
  tests.mod_editor.test_apf_audo_project \
  tests.mod_editor.test_apf_build_raw_span_overlays

echo "APF_AUDO_EXACT_SLOT_VALIDATION_PASS retail_bytes_embedded=false source_modified=false"

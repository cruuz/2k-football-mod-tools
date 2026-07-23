#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"

PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile \
  tools/apf_uniform_selector_xenia_gamepad.py \
  tools/apf_uniform_selector_mod_release_verify.py \
  tools/apf_uniform_selector_xenia_match.py \
  tools/apf_uniform_selector_xenia_runtime_verify.py
bash -n tools/build_apf_uniform_selector_mod.sh
PYTHONDONTWRITEBYTECODE=1 python3 mod_editor/capabilities/validate_registry.py

bash tools/build_apf_uniform_selector_mod.sh \
  --source-game 'extracted/All-Pro Football 2K8 (USA)' \
  --output-game '/media/noah/Storage/.codex-tmp/apf-selector-release-validation-unused' \
  --preflight-only

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_apf_uniform_selector_xenia_gamepad \
  tests.test_apf_uniform_selector_mod_release \
  tests.test_apf_uniform_selector_xenia_match \
  tests.test_apf_uniform_selector_xenia_runtime_verify -q

PYTHONDONTWRITEBYTECODE=1 python3 tools/apf_uniform_selector_mod_release_verify.py \
  --report reports/assets/apf_uniform_selector_mod_release.v1.json

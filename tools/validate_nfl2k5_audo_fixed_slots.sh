#!/usr/bin/env bash
set -euo pipefail

workspace="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$workspace"
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.mod_editor.test_nfl2k5_audo_fixed_slots \
  tests.mod_editor.test_nfl2k5_audio_catalog \
  tests.mod_editor.test_unified_audio_composition \
  tests.mod_editor.test_audio_panel_qt

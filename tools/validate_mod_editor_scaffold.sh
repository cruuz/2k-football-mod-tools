#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

export PYTHONDONTWRITEBYTECODE=1
python3 -m mod_editor --check-registry --require-registry
help="$(python3 -m mod_editor --help)"
rg -q -- '--export-apf-jersey NEW_OUTPUT_DIR' <<<"$help"
rg -q -- '--create-apf-pants-recipe OUTPUT.json' <<<"$help"
rg -q -- '--pants-png PANTS_PNG' <<<"$help"
rg -q -- '--create-apf-helmet-recipe OUTPUT.json' <<<"$help"
rg -q -- '--helmet-png HELMET_PNG' <<<"$help"
rg -q -- '--create-apf-shoulder-recipe OUTPUT.json' <<<"$help"
rg -q -- '--shoulder-png SHOULDER_PNG' <<<"$help"
rg -q -- '--create-apf-digital-font-recipe OUTPUT.json' <<<"$help"
rg -q -- '--apf-digital-font-png APF_DIGITAL_FONT_PNG' <<<"$help"
rg -q -- '--create-nfl-menu-back-audio-recipe OUTPUT.json' <<<"$help"
rg -q -- '--audio-wav AUDIO_WAV' <<<"$help"
rg -q -- '--source-0a SOURCE_0A' <<<"$help"
rg -q -- '--inspect-nfl-uniform-sharing SELECTOR' <<<"$help"
rg -q -- '--inspect-apf-jersey-sharing ASSET_INDEX' <<<"$help"
rg -q -- '--inspect-apf-pants-sharing ASSET_INDEX' <<<"$help"
rg -q -- '--inspect-apf-helmet-sharing ASSET_INDEX' <<<"$help"
rg -q -- '--inspect-apf-shoulder-sharing ASSET_INDEX' <<<"$help"
rg -q -- '--inspect-gameplay-sliders GAME' <<<"$help"
rg -q -- '--inspect-draft-priority GAME' <<<"$help"
rg -q -- '--inspect-nfl-franchise-limit TARGET' <<<"$help"
rg -q -- '--inspect-nfl-save-inventory' <<<"$help"
rg -q -- '--inspect-main-menu GAME' <<<"$help"
rg -q 'Inspect Mapped Data…' mod_editor/gui/tkinter_app.py
if rg -q -- '--entry|--offset' <<<"$help"; then
  echo 'mod editor help exposed a raw APF archive selector' >&2
  exit 1
fi
python3 -m unittest discover -s tests/mod_editor -p 'test_*.py' -v
python3 -m unittest -v tests/apf_jersey_family_verify_test.py
python3 tests/nfl2k5_scorebug_mod_project_test.py

echo "MOD_EDITOR_SCAFFOLD_VALIDATION_PASS registry=canonical tests=discovery providers=nfl2k5_unified,nfl2k5_scorebug,nfl2k5_menu_back_audio,apf2k8_jersey,apf2k8_pants,apf2k8_helmet,apf2k8_shoulder,apf2k8_digital_font apf_read_only_export=true mapped_gui_inspectors=true uniform_sharing_lookup=true apf_pants_sharing=true apf_helmet_sharing=true apf_shoulder_sharing=true gameplay_sliders=true nfl_save_inventory=true draft_priority=true franchise_limits=true pcsx2_fixture_gate=SLUS-20919 main_menu=true raw_archive_selectors=false recipes=apf_jersey,apf_pants,apf_helmet,apf_shoulder,apf2k8_digital_font,nfl2k5_scorebug,nfl2k5_menu_back_audio emulator=false retail_sized_test_copy=false"

# Batched pytest guidance (monorepo hang residual)

Full `pytest tests/mod_editor` can hang mid-run on this machine (Qt order-state,
ProcessPool leftovers, high RAM). Use **separate-process batches** as release
evidence instead of a single monorepo run.

## Recommended product batches

```bash
export QT_QPA_PLATFORM=offscreen
cd "/media/noah/Storage/for codex 1.0"

# Critical UI / never-gray / playbooks / textures / audio / roster
python3 -m pytest \
  tests/mod_editor/test_gui_drop_parity.py \
  tests/mod_editor/test_model_import_disable_reason.py \
  tests/mod_editor/test_broken_play_annotations.py \
  tests/mod_editor/test_playbook_package_rule_spike.py \
  tests/mod_editor/test_apf_team_logo_gui.py \
  tests/mod_editor/test_apf_field_art_gui.py \
  tests/mod_editor/test_image_fit.py \
  tests/mod_editor/test_apf_xenos_4444_png.py \
  tests/mod_editor/test_apf_logo_patch.py \
  tests/mod_editor/test_audio_panel_qt.py \
  tests/mod_editor/test_apf_audio_batch_gui.py \
  tests/mod_editor/test_text_rosters_panel.py \
  tests/mod_editor/test_apf_roster_identity_gui.py \
  tests/mod_editor/test_apf_textlogo_gui.py \
  tests/mod_editor/test_never_silent_gray_boot.py \
  -q

# Or file-letter batches in separate processes:
for f in tests/mod_editor/test_[n-z]*.py; do
  timeout 120 python3 -m pytest "$f" -q --tb=no || echo FAIL "$f"
done
```

`tests/conftest.py` sets `QT_QPA_PLATFORM=offscreen` by default.

Do **not** claim full monorepo green while the hang residual is open.

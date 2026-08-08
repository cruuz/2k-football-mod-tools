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

# APF Complete audio GUI — run in process batches (32 tests hang if monorepo-ordered
# with other Qt workers; 8-at-a-time is green in ~3s wall):
python3 - <<'PY'
import subprocess, sys, os
out = subprocess.check_output(
    [sys.executable, "-m", "pytest",
     "tests/mod_editor/test_apf_studio_audio_gui.py", "--collect-only", "-q"],
    text=True,
)
tests = [line for line in out.splitlines() if line.startswith("tests/")]
for i in range(0, len(tests), 8):
    batch = tests[i : i + 8]
    r = subprocess.run(
        [sys.executable, "-m", "pytest", *batch, "-q", "--tb=line"],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        check=True,
    )
print(f"APF audio GUI {len(tests)} tests OK in { (len(tests)+7)//8 } batches")
PY

# Or file-letter batches in separate processes:
for f in tests/mod_editor/test_[n-z]*.py; do
  timeout 120 python3 -m pytest "$f" -q --tb=no || echo FAIL "$f"
done
```

`tests/conftest.py` sets `QT_QPA_PLATFORM=offscreen` by default.

Do **not** claim full monorepo green while the hang residual is open.

## Hang-prone composition (a–c)

Do **not** batch these together in one process without a hard timeout:

- `test_apf_logo_patch.py` (run alone; ~2m)
- `test_apf_field_art_patch.py` + helmet crest/placement suites (pass alone; may hang when combined)

Prefer 4-file batches for `test_[a-c]*.py` and isolate logo_patch.

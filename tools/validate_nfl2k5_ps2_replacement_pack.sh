#!/usr/bin/env bash
# Deterministic validator for the PS2 replacement-pack export.
#
# Runs the pack verifier's self-test, which builds a synthetic pack, its
# mapping manifest and its project from scratch and proves: a correct pack
# verifies; the audit tool independently reports xbox_mapping_ready on the
# same folder; and a single changed output byte, an extra file, a receipt
# entry naming an unedited target, a filename the manifest does not map, a
# missing file, a forged provenance block, a stray directory and an
# uncanonical filename are each rejected. It also proves that a run without
# the project is downgraded rather than passed, because the check that no
# exported file names an unedited target cannot run without it, and that a
# receipt with no emulator target, an unknown one, or another target's
# instructions is rejected. No game data is required.
#
# Then it checks the export window's "Where will you use this pack?" question:
# three answers, nothing preselected, and every fact in the dialog module's
# TARGET_EXPLANATION_REQUIRED_FACTS still present in the hover text that
# explains why the question is asked -- including the measured numbers. That
# check builds the real window offscreen, so it needs PyQt5; where PyQt5 is
# absent it says so and is skipped, because a build with no GUI has no
# tooltips to check.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

python3 -m py_compile mod_editor/core/ps2_export_service.py \
    tools/nfl2k5_ps2_replacement_pack_verify.py \
    tools/nfl2k5_ps2_replacement_pack_audit.py
python3 tools/nfl2k5_ps2_replacement_pack_verify.py --selftest

if python3 -c "import PyQt5" >/dev/null 2>&1; then
    QT_QPA_PLATFORM=offscreen python3 -m mod_editor.gui.ps2_export_dialog_qt
else
    echo "NFL2K5_PS2_EXPORT_TARGET_EXPLANATION_SKIPPED pyqt5=absent"
fi

echo "NFL2K5_PS2_REPLACEMENT_PACK_VALIDATION_PASS targets=penguinscreen2_classic,pcsx2_modern,pcsx2_legacy"

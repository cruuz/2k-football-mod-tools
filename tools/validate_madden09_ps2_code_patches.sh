#!/usr/bin/env bash
# Deterministic validator for the Madden 09 (PS2) executable-patch lane.
#
# Runs the lane's self-test and its unit tests, which prove on a synthetic ELF
# that: every proposed patch refuses translation by name; hand-authored words
# plan against the user's own ELF and refuse when the original does not match;
# the pnach names the ELF's own PCSX2 CRC; verify passes the file the receipt
# recorded and fails a tampered one; and a build never overwrites. No game data
# is required.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

python3 -m py_compile mod_editor/games/madden09_ps2/code_patches.py
python3 -m mod_editor.games.madden09_ps2.code_patches --selftest
python3 -m unittest tests.mod_editor.test_madden09_ps2_code_patches

echo "MADDEN09_PS2_CODE_PATCHES_VALIDATION_PASS"

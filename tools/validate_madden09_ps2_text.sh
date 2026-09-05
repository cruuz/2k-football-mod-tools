#!/usr/bin/env bash
# Deterministic validator for the Madden 09 (PS2) text lane.
#
# Runs the text lane's unit tests, which prove on a synthetic disc that: a TEXT
# member splits to the strings it holds; the catalogue carries counts, lengths and
# digests and no string at all; a preview reads the strings from the source it is
# given and elides an over-long one; and the lane refuses to plan, build or
# verify. No game data is required.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

python3 -m py_compile mod_editor/games/madden09_ps2/text_lane.py
python3 -m unittest tests.mod_editor.test_madden09_ps2_text

echo "MADDEN09_PS2_TEXT_VALIDATION_PASS"

#!/usr/bin/env bash
# Deterministic validator for the Madden 09 (PS2) team-database lane.
#
# Runs the EA TDB reader's unit tests and the lane's own, which between them
# prove: a synthetic TDB round-trips every field type through the bit-packer,
# including fields that straddle byte boundaries and negative signed values; the
# 4-byte franchise preamble is detected; a truncated or implausible database is
# refused with a sentence; the lane catalogues tables, record counts and field
# names and never a record's contents; and it refuses to plan, build or verify.
# No game data is required.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

python3 -m py_compile mod_editor/games/_formats/ea_tdb.py mod_editor/games/madden09_ps2/team_data.py
python3 -m unittest tests.mod_editor.test_ea_tdb tests.mod_editor.test_madden09_ps2_team_data

echo "MADDEN09_PS2_TEAM_DATA_VALIDATION_PASS"

#!/usr/bin/env bash
# Validator for Madden NFL 09 (PS2), the team-database lane.
#
# Runs in a shipped tree as well as a checkout: it compiles the lane module and
# runs the game-module conformance harness for madden09_ps2, which proves every
# lane of the module on a synthetic disc (no game data) and renders the studio's
# pages offscreen. Prints MADDEN09_PS2_TEAM_DATA_VALIDATION_PASS on success.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
python3 -m py_compile mod_editor/games/madden09_ps2/team_data.py
PYTHONPATH="$root" python3 -m mod_editor.games conformance --game madden09_ps2
echo "MADDEN09_PS2_TEAM_DATA_VALIDATION_PASS"

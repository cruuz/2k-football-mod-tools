#!/usr/bin/env bash
# Validator for NFL Blitz 2002 (PS2), the three text-member writer lanes.
#
# The behaviour is in tools/validate_game_lane.py and the steps this lane needs are
# declared in mod_editor/games/nflblitz2002_ps2/validators.json; the pass token is
# derived from the game id and the lane name, so it cannot drift from this file's name.
# Runs in a shipped tree as well as a checkout, and imports no test framework.
# Prints NFLBLITZ2002_PS2_TEXT_VALIDATION_PASS on success.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$root/tools/validate_game_lane.py" --game nflblitz2002_ps2 --lane text

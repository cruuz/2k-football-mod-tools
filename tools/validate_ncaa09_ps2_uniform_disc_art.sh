#!/usr/bin/env bash
# Validator for NCAA Football 09 (PS2), the kit, equipment and gear disc-art writer.
#
# The behaviour is in tools/validate_game_lane.py and the steps this lane needs are
# declared in mod_editor/games/ncaa09_ps2/validators.json; the pass token is derived
# from the game id and the lane name, so it cannot drift from this file's name.
# Runs in a shipped tree as well as a checkout, and imports no test framework.
# Prints NCAA09_PS2_UNIFORM_DISC_ART_VALIDATION_PASS on success.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$root/tools/validate_game_lane.py" --game ncaa09_ps2 --lane uniform_disc_art

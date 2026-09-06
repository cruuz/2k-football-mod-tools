#!/usr/bin/env bash
# Validator for NCAA Football 09 (PS2), the TEXT string-bank lane.
#
# Runs in a shipped tree as well as a checkout: it compiles the lane module,
# runs the game-module conformance harness for ncaa09_ps2 -- which proves every
# lane of the module on a synthetic disc (no game data) and renders the studio's
# pages offscreen -- and then runs the lane's own self-test on that same
# synthetic disc. Prints NCAA09_PS2_TEXT_VALIDATION_PASS on success.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
python3 -m py_compile mod_editor/games/ncaa09_ps2/text_lane.py
PYTHONPATH="$root" python3 -m mod_editor.games conformance --game ncaa09_ps2
PYTHONPATH="$root" python3 -m mod_editor.games.ncaa09_ps2.text_lane --selftest
echo "NCAA09_PS2_TEXT_VALIDATION_PASS"

#!/usr/bin/env bash
# Validator for Madden NFL 09 (PS2), the SCHl stream and BNKl bank audio lanes.
#
# Runs in a shipped tree as well as a checkout: it compiles the shared EA SCHl
# reader and the lane module, then runs the game-module conformance harness for
# madden09_ps2, which proves every lane of the module on a synthetic disc (no
# game data) -- for the audio lanes that means cataloguing computed SCHl streams
# and BNKl banks, decoding one, encoding a computed tone back into the bytes it
# has to fit, rebuilding the image with the preload cache kept in step, and
# failing the independent verifier on a byte outside the declared ranges.
# Prints MADDEN09_PS2_AUDIO_VALIDATION_PASS on success.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
python3 -m py_compile mod_editor/games/_formats/ea_schl.py
python3 -m py_compile mod_editor/games/madden09_ps2/audio_lane.py
PYTHONPATH="$root" python3 -m mod_editor.games conformance --game madden09_ps2
echo "MADDEN09_PS2_AUDIO_VALIDATION_PASS"

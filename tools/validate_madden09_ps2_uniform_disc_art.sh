#!/usr/bin/env bash
# Validator for Madden NFL 09 (PS2), the MMAP uniform-art DISC WRITER lane.
#
# Runs in a shipped tree as well as a checkout: it compiles the lane module and
# runs both ISO9660 self-tests and the game-module conformance harness for
# madden09_ps2, which proves every lane of the module on a synthetic disc
# (no game data) and renders the studio's pages offscreen. Prints MADDEN09_PS2_UNIFORM_DISC_ART_VALIDATION_PASS on success.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
python3 -m py_compile mod_editor/games/madden09_ps2/uniform_art.py tools/ps2_iso9660_writer.py tools/ps2_iso9660_verify.py
python3 tools/ps2_iso9660_writer.py --selftest
python3 tools/ps2_iso9660_verify.py --selftest
PYTHONPATH="$root" python3 -m mod_editor.games conformance --game madden09_ps2
echo "MADDEN09_PS2_UNIFORM_DISC_ART_VALIDATION_PASS"

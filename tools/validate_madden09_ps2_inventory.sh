#!/usr/bin/env bash
# Deterministic validator for the Madden 09 (PS2) container inventory lane.
#
# Runs the shared TERF reader's self-test and the lane's own unit tests, which
# between them prove: a synthetic TERF container round-trips through the reader
# and the writer at every alignment; a synthetic SLUS-21770 ISO carrying a DATA
# container and a COMP-with-stored container walks to the expected member counts,
# codecs and formats; the lane refuses to plan, build or verify; and no catalogue
# row carries a payload byte. No game data is required.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

python3 -m py_compile mod_editor/games/madden09_ps2/inventory_lane.py mod_editor/games/madden09_ps2/containers.py
python3 tools/ea_terf_inspect.py --selftest
python3 -m unittest tests.mod_editor.test_madden09_ps2_inventory

echo "MADDEN09_PS2_INVENTORY_VALIDATION_PASS"

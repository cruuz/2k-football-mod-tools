#!/usr/bin/env bash
# Deterministic validator for the Madden 09 (PS2) uniform-art lane.
#
# Runs the uniform-art lane's unit tests, which prove on synthetic MMAP members
# that: the header parses to the dimensions it declares; a decode round-trips to
# a PNG of exactly those dimensions; an import of the wrong size is refused with
# the size the lane wanted; the export writes the files its receipt declares and
# an independent verify re-derives every digest and fails on a tampered file; and
# the PCSX2 replacement identity is refused by name. No game data is required.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

python3 -m py_compile mod_editor/games/madden09_ps2/uniform_art.py mod_editor/games/madden09_ps2/mmap_art.py
python3 -m unittest tests.mod_editor.test_madden09_ps2_uniform_art

echo "MADDEN09_PS2_UNIFORM_ART_VALIDATION_PASS"

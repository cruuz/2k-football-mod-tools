#!/usr/bin/env bash
# Deterministic validator for the PS2 playbook patcher and its verifier.
#
# Compiles the three tools, then runs the synthetic suite, which proves without
# any game data: a PLAY body built field by field parses with the shipped codec
# and every play passes the ported retail validator; a formation and a play can
# be added and the independent verifier passes; a byte flipped outside the
# declared playbook span fails verification; a book already at the 270-play
# capacity is refused; and a compile returning the wrong body length is refused
# before the output image is created. No disc, no network.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

python3 -m py_compile \
    tools/nfl2k5_ps2_playbook_patch.py \
    tools/nfl2k5_ps2_playbook_verify.py \
    tools/nfl2k5_ps2_playbook_target_catalog.py

python3 -m unittest tests.mod_editor.test_nfl2k5_ps2_playbook -v

echo "NFL2K5_PS2_PLAYBOOK_VALIDATION_PASS"

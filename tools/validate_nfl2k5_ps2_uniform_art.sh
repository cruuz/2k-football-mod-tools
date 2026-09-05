#!/usr/bin/env bash
# Deterministic validator for the PS2 uniform-art lane.
#
# Runs the texture map's self-test (the forward maths and, since this lane, the
# inverse permutations a decoder reads pixels with), the lane's own self-test
# (a synthetic PS2 image carrying one PSMT8 and one PSMT4 uniform texture:
# catalogued, decoded to RGBA PNG, a replacement accepted at the texture's own
# size and at 2x, a 3:2 stretch and a non-PNG refused with the size the texture
# wanted, a pack written and verified, a flipped byte in the pack failing
# verification, and an existing destination refused), and the independent
# replacement-pack verifier's self-test, which now covers the disc-native art
# provenance as well as the Xbox-project one. No game data is required.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

python3 -m py_compile \
    tools/nfl2k5_ps2_texture_map.py \
    tools/nfl2k5_ps2_uniform_art.py \
    tools/nfl2k5_ps2_replacement_pack_verify.py \
    mod_editor/games/nfl2k5_ps2/uniform_art.py
python3 tools/nfl2k5_ps2_texture_map.py --selftest
python3 tools/nfl2k5_ps2_uniform_art.py --selftest
python3 tools/nfl2k5_ps2_replacement_pack_verify.py --selftest

echo "NFL2K5_PS2_UNIFORM_ART_VALIDATION_PASS"

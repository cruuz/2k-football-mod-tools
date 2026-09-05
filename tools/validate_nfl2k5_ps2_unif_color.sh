#!/usr/bin/env bash
# Deterministic validator for the PS2 uniform-colour on-disc writer.
#
# Runs the target catalogue's, the writer's and the independent verifier's
# self-tests, which between them prove: a synthetic PS2 ISO's Unif records are
# catalogued through their own descriptor pointers; a same-size eight-byte
# colour poke lands in a new image that keeps the source's exact byte length;
# an out-of-range selector, an over-length colour literal, a compressed body
# that cannot be refit into its stored span, a mismatched catalogue and a no-op
# edit are each refused without creating a destination; and a byte changed
# outside the declared spans fails verification. No game data is required.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

python3 -m py_compile \
    tools/nfl2k5_ps2_unif_color_target_catalog.py \
    tools/nfl2k5_ps2_unif_color_patch.py \
    tools/nfl2k5_ps2_unif_color_verify.py
python3 tools/nfl2k5_ps2_unif_color_target_catalog.py --selftest
python3 tools/nfl2k5_ps2_unif_color_patch.py --selftest
python3 tools/nfl2k5_ps2_unif_color_verify.py --selftest

echo "NFL2K5_PS2_UNIF_COLOR_VALIDATION_PASS"

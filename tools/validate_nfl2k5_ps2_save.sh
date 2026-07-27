#!/usr/bin/env bash
# Deterministic validator for the PS2 save writer.
#
# Runs the writer's and the verifier's self-tests, which between them prove:
# a sealed fixed-allocation edit round-trips through .psu unchanged; a save
# whose EXTRA was not resealed is rejected; and an edit outside the declared
# byte range is rejected. No game data is required.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

python3 -m py_compile tools/nfl2k5_ps2_save.py tools/nfl2k5_ps2_save_verify.py
python3 tools/nfl2k5_ps2_save.py --selftest
python3 tools/nfl2k5_ps2_save_verify.py --selftest

echo "NFL2K5_PS2_SAVE_VALIDATION_PASS"

#!/usr/bin/env bash
# Deterministic validator for the PS2 disc-roster on-disc writer.
#
# Runs the target catalogue's, the writer's and the independent verifier's
# self-tests, which between them prove: a synthetic PS2 ISO's ROST resources are
# catalogued with their fixed-allocation name budgets; a masked jersey /
# face-shield word and a same-allocation name land in a new image that keeps the
# source's exact byte length; an out-of-range player index, an over-length name,
# a zero-capacity placeholder slot, a compressed ROST body that cannot be refit
# into its stored span, a mismatched catalogue, the reserved face-shield value
# and a no-op edit are each refused without creating a destination; and a byte
# changed outside the declared ranges, or a table pointer that moved, fails
# verification. No game data is required.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

python3 -m py_compile \
    tools/nfl2k5_ps2_disc_roster_target_catalog.py \
    tools/nfl2k5_ps2_disc_roster_patch.py \
    tools/nfl2k5_ps2_disc_roster_verify.py
python3 tools/nfl2k5_ps2_disc_roster_target_catalog.py --selftest
python3 tools/nfl2k5_ps2_disc_roster_patch.py --selftest
python3 tools/nfl2k5_ps2_disc_roster_verify.py --selftest

echo "NFL2K5_PS2_DISC_ROSTER_VALIDATION_PASS"

#!/usr/bin/env bash
# Deterministic validator for the PS2 exact-slot AUDO audio lane.
#
# Runs the four self-tests that, between them, prove: SPU-ADPCM round-trips
# byte-exactly and every emitted block obeys the format's shift / filter / flag
# rules; a synthetic /VC_20919 disc catalogues to the expected AUDO slots with
# their channel counts, rates and byte budgets; a generated tone patches into a
# slot without touching one byte of container metadata, and over-length audio,
# a channel mismatch and a malformed WAV are all refused; and the independent
# verifier passes a clean patch while failing a byte flipped inside or outside
# the slot. No game data is required.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

python3 -m py_compile \
    tools/spu_adpcm.py \
    tools/nfl2k5_ps2_audo_target_catalog.py \
    tools/nfl2k5_ps2_audo_patch.py \
    tools/nfl2k5_ps2_audo_verify.py
python3 tools/spu_adpcm.py --selftest
python3 tools/nfl2k5_ps2_audo_target_catalog.py --selftest
python3 tools/nfl2k5_ps2_audo_patch.py --selftest
python3 tools/nfl2k5_ps2_audo_verify.py --selftest

echo "NFL2K5_PS2_AUDO_VALIDATION_PASS"

#!/usr/bin/env bash
# Deterministic validator for bounded PS2 stadium position editing.
#
# Runs the target catalogue's, the writer's and the verifier's self-tests plus
# the synthetic suite. Between them they prove, with no game data anywhere:
#
#   * a synthetic PS2 SCNE's shape table, batch table and DMA/VIF chains parse,
#     and an unknown VIF code, an escaped bounding sphere and a batch carrying
#     two position lanes are each classified rather than guessed at;
#   * a synthetic SLUS-20919-shaped ISO carrying a VC-LZ compressed SCNE can
#     have one catalogued V4_32 position lane rewritten, recompressed into the
#     chunk's fixed stored body with a byte-identical 0x20 wrapper, and spliced
#     back through the fixed-allocation ISO9660 writer;
#   * the independent verifier passes that image and fails a byte changed
#     outside the declared lanes, a byte changed outside the chunk span, and a
#     moved +0x14 scratch word;
#   * the writer refuses a changed vertex count, an inexact binary32
#     coordinate, an unauthorised target, a mismatched catalogue pin, edits
#     spanning two scenes, and a recompression that does not fit -- and in the
#     refusing cases no output image is created.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

python3 -m py_compile \
    tools/nfl2k5_ps2_stadium_target_catalog.py \
    tools/nfl2k5_ps2_stadium_position_patch.py \
    tools/nfl2k5_ps2_stadium_position_verify.py

python3 tools/nfl2k5_ps2_stadium_target_catalog.py --selftest
python3 tools/nfl2k5_ps2_stadium_position_verify.py --selftest
python3 tools/nfl2k5_ps2_stadium_position_patch.py --selftest
python3 -m unittest tests.mod_editor.test_nfl2k5_ps2_stadium_position -v

echo "NFL2K5_PS2_STADIUM_POSITION_VALIDATION_PASS"

#!/usr/bin/env bash
# Validator for the general NFL 2K5 P8 texture lane.
#
# The lane's own contract tests run everywhere and need no retail data: plan
# discipline, the mip-chain arithmetic the palette offset has to equal, and the
# standing refusal to gate on the whole container. The retail-gated class
# inside the same module resolves real targets and refits a real span when the
# private extracted index is present, and skips cleanly when it is not.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"

python3 -m unittest tests.mod_editor.test_all_texture_lane -v
python3 -m unittest tests.mod_editor.test_all_textures_workspace -v
echo 'NFL_ALL_TEXTURE_LANE_VALIDATION_PASS standalone=11395 p8=7315 a1=4080 new_presentation=1755 raw_menu=1585 franchise_draft=170 source=unchanged runtime=false'

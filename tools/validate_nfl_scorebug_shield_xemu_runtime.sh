#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
bash "$ROOT/tools/validate_nfl_scorebug_runtime_receipts.sh"

echo 'NFL2K5_SCOREBUG_SHIELD_XEMU_RUNTIME_VALIDATION_PASS target=shield_espn changed=5320 cyan=4557 fixture=8192 control=0 xemu=0.8.135 hardware=false retained_hdd_layers=2 chain_complete=false guest_content_replayable=false historical_runtime_reexecuted=false virtual_output_hash=true emulator_started=false originals_unchanged=yes'

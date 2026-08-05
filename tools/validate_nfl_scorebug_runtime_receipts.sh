#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
export PYTHONDONTWRITEBYTECODE=1
chain_spec='reports/specs/nfl2k5_historical_xemu_hdd_chain.v1.json'
chain_spec_sha=9f017bda0ffb99dd5d9859b2a92fb7e82b30d901a684635449b37bcfe91cfe90

PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  tools/nfl_scorebug_runtime_receipt_verify.py \
  tools/nfl_qcow2_historical_chain_verify.py
python3 tools/nfl_qcow2_historical_chain_verify.py \
  --root "$ROOT" \
  --spec "$chain_spec" \
  --spec-sha256 "$chain_spec_sha" \
  --leaf scorebug_runtime \
  >"$temporary/scorebug-chain.json"
python3 tools/nfl_qcow2_historical_chain_verify.py \
  --root "$ROOT" \
  --spec "$chain_spec" \
  --spec-sha256 "$chain_spec_sha" \
  --leaf scorebug_shield_runtime \
  >"$temporary/shield-chain.json"
python3 tools/nfl_scorebug_runtime_receipt_verify.py \
  --scorebug-chain "$temporary/scorebug-chain.json" \
  --shield-chain "$temporary/shield-chain.json"

echo 'NFL2K5_SCOREBUG_RUNTIME_RECEIPTS_VALIDATION_PASS targets=score_buga,shield_espn virtual_output_hashes=true retained_visuals=true chain_complete=false guest_content_replayable=false historical_runtime_reexecuted=false emulator_started=false output_xiso_written=false'

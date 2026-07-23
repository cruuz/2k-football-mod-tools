#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$ROOT/tools${PYTHONPATH:+:$PYTHONPATH}"

python3 tools/apf_stadium_static_target_catalog.py
python3 -m unittest tests.test_apf_stadium_static_target_catalog

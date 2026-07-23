#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

cd "$root"
python3 tools/apf_uniform_selector_xenia_runtime_verify.py \
  --report reports/assets/apf_uniform_selector_xenia_runtime.json

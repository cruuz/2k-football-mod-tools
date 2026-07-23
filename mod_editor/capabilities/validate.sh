#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
export PYTHONDONTWRITEBYTECODE=1

python3 mod_editor/capabilities/validate_registry.py
PYTHONPATH=mod_editor/capabilities python3 -m unittest -v mod_editor/capabilities/test_registry.py

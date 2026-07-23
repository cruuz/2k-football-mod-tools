#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Publication-only gate: local reads and hashes.  It does not render the HTML,
# launch an emulator, inspect undisclosed retail paths, or write game data.
export PYTHONDONTWRITEBYTECODE=1
export LC_ALL=C
exec python3 "$ROOT/tools/validate_nfl2k6_video_dossier.py"

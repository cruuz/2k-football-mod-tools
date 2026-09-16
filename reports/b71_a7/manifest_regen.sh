#!/bin/bash
set -eu
cd "$(dirname "$0")/../.."
work=/media/noah/Storage/.b71-a7-manifest
mkdir "$work"
trap 'rmdir "$work" 2>/dev/null || true' EXIT
PYTHONPATH=. python3 tools/nfl2k5_cave_oracle.py manifest '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' --xiso '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso' --work-dir "$work" --json data/nfl2k5_cave_reservations.json

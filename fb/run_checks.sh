#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")/.."
export TMPDIR=/media/noah/Storage/.b76-research/fb/tmp
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
# A running candidate build may continue: this process has a hard <2 GiB cap.
ulimit -v 1843200
python3 fb/catalog_art.py
python3 -m unittest discover -s tests/mod_editor -p 'test_nfl2k5_model_fan_art.py' -v
python3 -m unittest discover -s tests/mod_editor -p 'test_nfl2k5_stadium_shared_art.py' -v
python3 -m unittest discover -s tests/mod_editor -p 'test_nfl2k5_modern_venues_2026.py' -v
python3 fb/test_owner_contracts.py

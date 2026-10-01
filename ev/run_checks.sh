#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")/.."
export TMPDIR=/media/noah/Storage/.b76-research/ev/tmp
export PYTHONPATH="$PWD/tests:$PWD/tests/mod_editor:$PWD/tools:$PWD"
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
# Candidate builds may coexist: one process, no pools, hard ceiling below 2 GiB.
ulimit -v 1843200
python3 ev/prove_routing.py
python3 -m unittest tests.mod_editor.test_nfl2k5_event_fields tests.mod_editor.test_nfl2k5_stadium_shared_art -v
python3 tests/nfl2k5_season_length_test.py -v
python3 -m unittest tests.mod_editor.test_nfl2k5_calendar_engine tests.mod_editor.test_nfl2k5_calendar_engine_delivery -v
python3 -m unittest tests.mod_editor.test_nfl2k5_modern_venues_2026 tests.mod_editor.test_nfl2k5_model_fan_art tests.mod_editor.test_nfl2k5_sofi_model -v
python3 mod_editor/capabilities/validate_registry.py --skip-file-checks

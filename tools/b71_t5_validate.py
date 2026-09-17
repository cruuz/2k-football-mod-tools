"""Run requested standalone suites offscreen, with individual command receipts."""
from concurrent.futures import ThreadPoolExecutor
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SUITES = '''test_b71_t5_project_open test_b71_t4_equipment_project
test_b69_j1_fit test_b69_j1_build test_b69_j1_wiring test_b70_t1_build_speed
test_b70_t1_diagnostics test_b70_t2_equipment test_b70_t2_reporting test_b70_t2_wiring
test_b68_t1_build test_mod_build test_mod_build_performance test_build_panel_qt
test_nfl2k5_build_service test_2k5_build_is_explainable test_facade_external_build
test_project_document_workflow test_studio_session test_studio_facade
test_studio_shell_layout_qt test_studio_qt_models test_studio_visual_asset_routing
test_uniform_bundle_cross_project test_nfl2k5_model_project test_models_project_wiring
test_provider_integrity test_providers test_product_catalog test_phase1_packaging
test_nfl2k5_equipment_import test_nfl2k5_equipment_consumers test_nfl2k5_equipment_import_wiring
test_nfl2k5_equipment_scope_wiring test_nfl2k5_equipment_texture_chain
test_nfl2k5_equipment_texture_native test_nfl2k5_equipment_retail_roundtrip
test_nfl2k5_uniform_catalog test_nfl2k5_uniform_choice test_nfl2k5_uniform_choice_screens
test_2k5_uniform_equipment_export test_audio_annotation_project_archive
test_nfl2k5_stadium_editor_roundtrip test_nfl2k5_simulated_windows_build'''.split()

def run(suite, output):
    path = ROOT / 'tests/mod_editor' / (suite + '.py')
    command = [sys.executable, str(path)]
    start = time.monotonic()
    row = dict(command=command, started=datetime.datetime.now(datetime.timezone.utc).isoformat())
    with (output/(suite+'.log')).open('w') as log:
        try:
            result = subprocess.run(command, cwd=ROOT, env=dict(os.environ, PYTHONPATH=str(ROOT),
                QT_QPA_PLATFORM='offscreen'), stdout=log, stderr=subprocess.STDOUT, timeout=900)
            row['exit_code'] = result.returncode
        except subprocess.TimeoutExpired:
            row['exit_code'] = 124
    row['seconds'] = time.monotonic() - start
    (output/(suite+'.json')).write_text(json.dumps(row,indent=2)+'\n')
    print(suite, row['exit_code'], round(row['seconds'],3),flush=True)
    return row

if __name__ == '__main__':
    output = ROOT / 'reports/b71_t5' / sys.argv[1]
    output.mkdir(parents=True,exist_ok=True)
    suites = sys.argv[2:] or SUITES
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(lambda suite:run(suite,output),suites))
    (output/'validation.json').write_text(json.dumps(rows,indent=2)+'\n')
    sys.exit(any(row['exit_code'] for row in rows))

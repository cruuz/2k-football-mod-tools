"""Run the T4 standalone regression suites and retain commands, exits and times."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
NAMES = (
    'test_b71_t4_equipment_project', 'test_b69_j1_fit', 'test_b69_j1_build', 'test_b69_j1_wiring',
    'test_b70_t1_build_speed', 'test_b70_t2_equipment', 'test_b70_t2_reporting', 'test_b70_t2_wiring',
    'test_nfl2k5_equipment_import', 'test_nfl2k5_equipment_consumers',
    'test_nfl2k5_equipment_import_wiring', 'test_nfl2k5_equipment_scope_wiring',
    'test_nfl2k5_equipment_texture_chain', 'test_nfl2k5_equipment_texture_native',
    'test_nfl2k5_equipment_retail_roundtrip', 'test_2k5_uniform_equipment_export',
    'test_project_document_workflow', 'test_studio_session', 'test_studio_facade',
    'test_studio_shell_layout_qt', 'test_studio_qt_models', 'test_studio_visual_asset_routing',
    'test_facade_external_build', 'test_uniform_bundle_cross_project',
    'test_nfl2k5_model_project', 'test_models_project_wiring',
    'test_provider_integrity', 'test_providers', 'test_product_catalog', 'test_phase1_packaging',
)


def main():
    paths = sys.argv[1:] or [f'tests/mod_editor/{name}.py' for name in NAMES] + [
        'tools/test_nfl2k5_visual_mod_project.py']
    output = ROOT / 'reports/b71_t4/tests'
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONPATH=str(ROOT))
    def run(path):
        started = datetime.now(timezone.utc).isoformat()
        clock = time.monotonic()
        log = output / (Path(path).stem + '.log')
        with log.open('w') as stream:
            process = subprocess.run([sys.executable, path], cwd=ROOT, env=env,
                stdout=stream, stderr=subprocess.STDOUT)
        result = dict(command=f'QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 {path}',
                      started=started, exit_code=process.returncode,
                      seconds=round(time.monotonic() - clock, 3), log=str(log.relative_to(ROOT)))
        print(json.dumps(result), flush=True)
        return result
    results = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for result in pool.map(run, paths):
            results.append(result)
            (output / 'validation.json').write_text(json.dumps(results, indent=2) + '\n')
    return int(any(row['exit_code'] for row in results))


if __name__ == '__main__':
    raise SystemExit(main())

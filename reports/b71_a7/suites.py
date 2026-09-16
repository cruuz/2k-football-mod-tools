"""Run each requested suite standalone with durable command receipts."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import json
import sys
from run import ROOT, OUT, run

kind = sys.argv[1]
prefix = sys.argv[2] if len(sys.argv) > 2 else 'final-'
batch = kind if prefix == 'final-' else prefix + kind
tests = ROOT / 'tests/mod_editor'
if kind == 'fast':
    files = sorted(tests.glob('test_*manifest.py'))
    workers = 3
elif kind == 'presentation':
    files = sorted(set(tests.glob('test_*scorebug*.py')) | set(tests.glob('test_*scorebar*.py')) | set(tests.glob('test_*colour*.py')) | set(tests.glob('test_*color*.py')))
    files = [p for p in files if not p.name.startswith('test_apf')]
    files += [ROOT / 'tests/nfl2k5_scorebug_layout_test.py', ROOT / 'tests/nfl2k5_scorebug_mod_project_test.py']
    files += sorted(set((ROOT / 'tests').glob('*colour*.py')) | set((ROOT / 'tests').glob('*color*.py')))
    files += [tests / n for n in ('test_nfl2k5_modern_arrowhead.py', 'test_b71_a6_composition.py', 'test_build_panel_qt.py', 'test_mod_build.py', 'test_discord_bugs_1.py', 'test_nfl2k5_depth_chart_rows.py')]
    workers = 4
elif kind == 'apf':
    files = sorted(tests.glob('test_apf*.py')) + [tests / 'test_b69_a1_playcalling.py']
    workers = 4
elif kind == 'closure_units':
    files = [tests / n for n in ('test_provider_integrity.py', 'test_providers.py', 'test_product_catalog.py', 'test_phase1_packaging.py', 'test_b68_a1_audit.py', 'test_capability_registry_module_commands.py')]
    workers = 3
else:
    raise ValueError(kind)
(OUT / (batch + '-suite-paths.json')).write_text(json.dumps([str(p.relative_to(ROOT)) for p in files], indent=2) + '\n')
results = []
with ThreadPoolExecutor(max_workers=workers) as pool:
    futures = {pool.submit(run, prefix + p.stem, (['env', '-u', 'PYTHONPATH', 'python3'] if p.name == 'test_apf_studio_installer.py' else ['python3']) + [str(p.relative_to(ROOT))] + ([] if p.name == 'nfl_uniform_color_patch_test.py' else ['-v'])): p for p in files}
    for future in as_completed(futures):
        p = futures[future]
        results.append(dict(path=str(p.relative_to(ROOT)), exit_code=future.result()))
(OUT / (batch + '-results.json')).write_text(json.dumps(results, indent=2) + '\n')
raise SystemExit(any(r['exit_code'] for r in results))

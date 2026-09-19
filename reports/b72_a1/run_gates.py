"""Strict catalog/integrity checks and the two clean-stage APF gates."""
from pathlib import Path
import json
import os
import subprocess
import shutil
import sys
import time

root = Path(__file__).resolve().parents[2]
folder = Path(__file__).resolve().parent
stage = root / '.scratch' / 'apf-release'
assert not stage.is_symlink() and stage.resolve().parent == (root / '.scratch').resolve()
if stage.exists():
    shutil.rmtree(stage)
commands = [
    ('repin', [sys.executable, 'packaging/repin.py', '--apply'], root),
    ('registry', [sys.executable, '-m', 'mod_editor.capabilities.validate_registry'], root),
    ('provider-integrity', [sys.executable, 'tests/mod_editor/test_provider_integrity.py'], root),
    ('product-catalog', [sys.executable, 'tests/mod_editor/test_product_catalog.py'], root),
    ('phase1-packaging', [sys.executable, 'tests/mod_editor/test_phase1_packaging.py'], root),
    ('apf-installer', [sys.executable, 'tests/mod_editor/test_apf_studio_installer.py'], root),
    ('apf-action-parity', [sys.executable, 'tests/mod_editor/test_apf_capability_action_parity.py'], root),
    ('apf-visual-gate', [sys.executable, 'tests/mod_editor/test_apf_full_shell_visual_gate.py'], root),
    ('stage', [sys.executable, 'packaging/stage_release.py', 'packaging/apf2k8-release-allowlist.txt', str(stage)], root),
    ('release', [sys.executable, str(stage / 'packaging/check_apf2k8_mod_studio_release.py'), str(stage)], stage),
    ('runtime', [sys.executable, str(stage / 'packaging/check_apf2k8_mod_studio_runtime.py')], stage),
]
results = []
for name, command, cwd in commands:
    env = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(cwd), 'PATH': str(Path(sys.executable).parent) + os.pathsep + os.environ.get('PATH', '')}
    start = time.time()
    with (folder / (name + '.log')).open('w', encoding='utf-8', newline='\n') as log:
        result = subprocess.run(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
    row = dict(name=name, command=command, cwd=str(cwd), exit_code=result.returncode, seconds=round(time.time()-start, 3))
    results.append(row)
    (folder / 'gates.json').write_bytes((json.dumps(results, indent=2)+'\n').encode())
    print(json.dumps(row), flush=True)
    if result.returncode:
        raise SystemExit(result.returncode)

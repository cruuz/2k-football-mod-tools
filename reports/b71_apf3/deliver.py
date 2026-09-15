"""Commit explicit report paths and create the verified private APF-3 bundle."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

root = Path(__file__).resolve().parents[2]
receipt_path = root / '.scratch/astra-b71-apf3-delivery.json'
bundle = root / '.scratch/astra-b71-apf3.bundle'
base = '7d95493750156f77e0533a16378330f4d80e7caa'
git = ['git', '--git-dir=.scratch/git', '--work-tree=.']
receipt = {'base': base, 'branch': 'astra/b71-apf3-situation-exclusions', 'commands': [],
           'gameplay': 'UNWITNESSED', 'independent_situation_exclusion': 'unimplemented', 'push': False}

def save():
    receipt_path.write_bytes((json.dumps(receipt, indent=2) + '\n').encode())

def run(command):
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    begin = time.monotonic()
    result = subprocess.run(command, cwd=root, env=dict(os.environ, PYTHONPATH=str(root), QT_QPA_PLATFORM='offscreen'),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    receipt['commands'].append({'command': command, 'started_utc': started,
                                'elapsed_seconds': round(time.monotonic() - begin, 3),
                                'exit_code': result.returncode, 'output': result.stdout})
    save()
    if result.returncode:
        print(result.stdout)
        raise SystemExit(result.returncode)
    return result.stdout.strip()

paths = json.loads(Path(__file__).with_name('delivery_paths.json').read_text())
assert paths and all(not p.startswith('/') and '..' not in Path(p).parts and (root / p).is_file() for p in paths)
assert all(p in ('ASTRA_REPORT.md', 'ASTRA_LAST_MESSAGE.md') or p.startswith('reports/b71_apf3/') for p in paths)
run([*git, 'add', '-f', '--', *paths])
run(['python3', 'reports/b71_apf3/audit_delivery.py'])
run([*git, 'diff', '--cached', '--check', '--', '.', ':(exclude)reports/b71_apf3/*.log'])
run(['python3', 'packaging/repin.py', '--apply'])
run([*git, 'commit', '-m', 'APF: record native lineup receipts, exclusion limits and all 183 regression gates', '--', *paths])
receipt['head'] = run([*git, 'rev-parse', 'HEAD'])
receipt['commits'] = run([*git, 'log', '--oneline', base + '..HEAD'])
run([*git, 'bundle', 'create', str(bundle.relative_to(root)), base + '..astra/b71-apf3-situation-exclusions'])
run([*git, 'bundle', 'verify', str(bundle.relative_to(root))])
run([*git, 'bundle', 'list-heads', str(bundle.relative_to(root))])
run([*git, 'diff', '--exit-code'])
run([*git, 'diff', '--cached', '--exit-code'])
receipt['bundle'] = {'path': str(bundle.relative_to(root)), 'bytes': bundle.stat().st_size,
                     'sha256': hashlib.sha256(bundle.read_bytes()).hexdigest()}
for name in ('apf-release', 'test-python'):
    path = root / '.scratch' / name
    assert path.resolve().parent == (root / '.scratch').resolve()
    if path.exists():
        shutil.rmtree(path)
    receipt[name + '_removed'] = not path.exists()
locks = root / '.scratch/check-locks'
if locks.exists():
    assert not list(locks.iterdir()), 'A standalone check is still running'
    locks.rmdir()
save()
print(json.dumps({k: v for k, v in receipt.items() if k != 'commands'}, indent=2))

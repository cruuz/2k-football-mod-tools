"""Run each selected unittest file as an isolated process and retain exact output."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

root = Path.cwd()
group, workers = sys.argv[1], int(sys.argv[2])
inventory = json.loads((root / 'reports/b69_a1b/inventory.json').read_text())
paths = sys.argv[3:] or [p for p in inventory['standalone_tests']
    if 'manifest' not in p and not p.endswith(('test_xbe_patch_memory_writes.py',
        'test_xbe_patch_cave_references.py', 'test_nfl2k5_cave_oracle.py',
        'test_nfl2k5_owner_pairwise_composition.py'))]
logs = root / 'reports/b69_a1b' / group
logs.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, PYTHONPATH='.', QT_QPA_PLATFORM='offscreen',
           MOD_STUDIO_NO_UPDATE_CHECK='1', PYTHONHASHSEED='0')
projection = root / '.scratch/a2b/gate-manifest.json'
if projection.exists():
    env['NFL2K5_CAVE_MANIFEST'] = str(projection)
ledger = []

def fingerprints():
    return {p: hashlib.sha256((root / p).read_bytes()).hexdigest()
            for p in inventory['changed_modules']}

def run(path):
    start, sources = time.monotonic(), fingerprints()
    log = logs / (Path(path).stem + '.log')
    with log.open('w') as out:
        try:
            result = subprocess.run(['python3', path], env=env, stdout=out,
                stderr=subprocess.STDOUT, timeout=2400)
            code = result.returncode
        except subprocess.TimeoutExpired:
            code = 124
            out.write('\nAUDIT TIMEOUT: 2400 seconds\n')
    lines = log.read_text(errors='replace').strip().splitlines()
    return dict(path=path, command='python3 ' + path, exit=code,
        seconds=round(time.monotonic() - start, 3),
        ran=next((s for s in reversed(lines) if s.startswith('Ran ')), ''),
        status=next((s for s in reversed(lines) if re.match(r'^(OK|FAILED|ERROR|FAIL)\b', s)),
                    lines[-1] if lines else '(no output)'),
        log=str(log.relative_to(root)), log_sha256=hashlib.sha256(log.read_bytes()).hexdigest(),
        source_sha256=sources, sources_stable=sources == fingerprints(),
        projection=str(projection.relative_to(root)) if 'NFL2K5_CAVE_MANIFEST' in env else None)

with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
    for future in concurrent.futures.as_completed([pool.submit(run, p) for p in paths]):
        row = future.result()
        ledger.append(row)
        (logs / 'tests.json').write_text(json.dumps(sorted(ledger, key=lambda r: r['path']), indent=2) + '\n')
        print(row['path'], row['exit'], row['ran'], row['status'], flush=True)
print('COMPLETED', len(ledger), 'FAILED', sum(r['exit'] != 0 for r in ledger), flush=True)

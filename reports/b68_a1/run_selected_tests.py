"""Replay the grep-selected standalone audit, or a supplied subset, from the repo root."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--label', default='replay')
parser.add_argument('files', nargs='*')
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
os.chdir(root)
evidence = root / 'reports/b68_a1'
files = args.files or json.loads((evidence / 'test-selection.json').read_text())['files']
results = []
for file in files:
    log = evidence / 'tests' / (file.replace('/', '__') + '.' + args.label + '.log')
    started = time.monotonic()
    with log.open('w') as stream:
        try:
            code = subprocess.run(['python3', file], env=dict(
                os.environ, PYTHONPATH='.', QT_QPA_PLATFORM='offscreen',
                MOD_STUDIO_NO_UPDATE_CHECK='1'), stdout=stream,
                stderr=subprocess.STDOUT, timeout=600).returncode
        except subprocess.TimeoutExpired:
            code = 124
            stream.write('\nAUDIT_TIMEOUT: 600 seconds\n')
    row = dict(file=file, exit_code=code, seconds=round(time.monotonic()-started, 3),
               log=str(log.relative_to(root)))
    results.append(row)
    (evidence / ('test-' + args.label + '.json')).write_text(json.dumps(results, indent=2)+'\n')
    print(code, row['seconds'], file, flush=True)
raise SystemExit(any(row['exit_code'] for row in results))

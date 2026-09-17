"""Detached, timed command ledger for the T5 offline validation job."""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import time

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', required=True)
    parser.add_argument('--timeout', type=int, default=1800)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / 'reports/b71_t5'
    output.mkdir(exist_ok=True)
    command = args.command
    if command[0] == '--':
        command = command[1:]
    start = time.monotonic()
    row = dict(command=command, started=datetime.datetime.now(datetime.timezone.utc).isoformat())
    env = dict(os.environ, PYTHONPATH=str(root), QT_QPA_PLATFORM='offscreen')
    with (output / (args.name + '.log')).open('w') as log:
        try:
            result = subprocess.run(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=args.timeout)
            row['exit_code'] = result.returncode
        except subprocess.TimeoutExpired:
            row['exit_code'] = 124
    row['seconds'] = time.monotonic() - start
    (output / (args.name + '.json')).write_text(json.dumps(row, indent=2) + '\n')
    raise SystemExit(row['exit_code'])

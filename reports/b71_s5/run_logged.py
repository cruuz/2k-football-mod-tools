"""Run one bounded command and keep its exact argv, timing and exit status."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent

def run(name, argv):
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    tick = time.monotonic()
    env = dict(os.environ, PYTHONPATH=str(ROOT), QT_QPA_PLATFORM='offscreen')
    with (OUT / (name + '.log')).open('w') as log:
        result = subprocess.run(argv, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    row = dict(name=name, argv=argv, start_utc=started,
               end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
               seconds=round(time.monotonic()-tick, 3), exit_code=result.returncode)
    (OUT / (name + '.result.json')).write_text(json.dumps(row, indent=2)+'\n')
    print(json.dumps(row), flush=True)
    return result.returncode

if __name__ == '__main__':
    raise SystemExit(run(sys.argv[1], sys.argv[2:]))

"""Run a bounded offline check and record exact command, UTC times and exit code."""
from pathlib import Path
import datetime as dt
import json
import os
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
name, *command = sys.argv[1:]
folder = ROOT / 'reports' / 'b71_c5'
env = dict(os.environ, PYTHONPATH=str(ROOT), QT_QPA_PLATFORM='offscreen')
started = dt.datetime.now(dt.timezone.utc).isoformat()
t0 = time.monotonic()
with (folder / (name + '.log')).open('w') as log:
    result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
record = dict(command=command, start_utc=started, end_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
              seconds=round(time.monotonic()-t0, 3), exit_code=result.returncode)
(folder / (name + '.json')).write_text(json.dumps(record, indent=2)+'\n')
print(json.dumps(dict(name=name, **record)), flush=True)
raise SystemExit(result.returncode)

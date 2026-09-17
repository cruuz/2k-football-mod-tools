import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[1]
name, *command = sys.argv[1:]
logs = root / 'reports/b711_p1'
start = datetime.datetime.now(datetime.timezone.utc).isoformat()
tic = time.monotonic()
env = dict(os.environ, QT_QPA_PLATFORM='offscreen', MOD_STUDIO_NO_UPDATE_CHECK='1',
           PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(root), PYTHONUNBUFFERED='1')
env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + env['PATH']
with (logs / (name + '.log')).open('w') as out:
    result = subprocess.run(command, cwd=root, env=env, stdout=out, stderr=subprocess.STDOUT)
record = dict(command=command, start=start, seconds=round(time.monotonic()-tic, 3), exit_code=result.returncode)
(logs / (name + '.json')).write_text(json.dumps(record, indent=2)+'\n')
print(json.dumps(record), flush=True)
sys.exit(result.returncode)

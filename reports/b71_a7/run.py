"""Record an exact command, its complete output, exit code and wall time."""
from pathlib import Path
from datetime import datetime, timezone
import json
import os
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def run(name, argv):
    env = dict(os.environ, PYTHONPATH=str(ROOT), QT_QPA_PLATFORM='offscreen',
               PYTHONUNBUFFERED='1', PATH=str(ROOT / '.scratch/test-python/bin') + os.pathsep + os.environ['PATH'], GIT_DIR=str(ROOT / '.scratch/git-a7'),
               GIT_WORK_TREE=str(ROOT))
    start = datetime.now(timezone.utc).isoformat()
    before = time.monotonic()
    with (OUT / (name + '.log')).open('w') as log:
        result = subprocess.run(argv, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT)
    row = dict(name=name, argv=argv, started=start,
               ended=datetime.now(timezone.utc).isoformat(),
               seconds=round(time.monotonic() - before, 3), exit_code=result.returncode)
    (OUT / (name + '.result.json')).write_text(json.dumps(row, indent=2) + '\n')
    print(json.dumps({key: value for key, value in row.items() if key != 'argv'}), flush=True)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(run(sys.argv[1], sys.argv[2:]))

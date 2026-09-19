"""Run each requested file standalone; retain commands and complete outputs."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[2]
folder = Path(__file__).resolve().parent
results = []
for suite in sys.argv[1:]:
    command = [sys.executable, suite]
    env = {**os.environ, 'PYTHONPATH': str(root), 'QT_QPA_PLATFORM': 'offscreen', 'PYTHONUNBUFFERED': '1'}
    start = time.time()
    with (folder / (Path(suite).stem + '.log')).open('w', encoding='utf-8', newline='\n') as output:
        result = subprocess.run(command, cwd=root, env=env, stdout=output, stderr=subprocess.STDOUT)
    row = dict(command=command, exit_code=result.returncode, seconds=round(time.time()-start, 3))
    results.append(row)
    (folder / (Path(suite).stem + '.result.json')).write_bytes((json.dumps(row, indent=2)+'\n').encode())
    print(json.dumps(row), flush=True)
sys.exit(any(row['exit_code'] for row in results))

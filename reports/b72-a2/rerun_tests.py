"""Refresh selected receipts after a fix, preserving the complete test manifest."""
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import sys
import time
root = Path(__file__).resolve().parents[2]
report = root/'reports/b72-a2'
rows = {row['file']: row for row in json.loads((report/'test-results.json').read_text())}
initial = report/'tests-initial'
initial.mkdir(exist_ok=True)
if not (report/'test-results-initial.json').exists():
    shutil.copyfile(report/'test-results.json', report/'test-results-initial.json')
env = dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONPATH=str(root))
for name in sys.argv[1:]:
    log = report/'tests'/f'{Path(name).stem}.log'
    if log.exists() and not (initial/log.name).exists():
        shutil.copyfile(log,initial/log.name)
    start = time.monotonic()
    with log.open('w') as output:
        result = subprocess.run([sys.executable, str(root/name)], cwd=root, env=env,
                                stdout=output, stderr=subprocess.STDOUT, timeout=360)
    text = log.read_text(errors='replace')
    rows[name] = {'file':name, 'exit_code':result.returncode, 'seconds':round(time.monotonic()-start,2),
                  'tests':sum(map(int,re.findall(r'Ran (\d+) tests?',text))),
                  'result':'\n'.join(text.strip().splitlines()[-3:]), 'interpreter':sys.executable}
    (report/'test-results.json').write_text(json.dumps(sorted(rows.values(),key=lambda row:row['file']),indent=2)+'\n')
    print(json.dumps(rows[name]),flush=True)
sys.exit(any(row['exit_code'] for row in rows.values()))

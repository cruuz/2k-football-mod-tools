"""Summarize final per-file receipts, keeping earlier progress separate."""
from pathlib import Path
import hashlib
import json
import re

folder = Path(__file__).resolve().parent
rows = []
for path in sorted(folder.glob('test_*.result.json')):
    row = json.loads(path.read_text(encoding='utf-8'))
    log = path.with_name(path.name.replace('.result.json', '.log'))
    data = log.read_bytes()
    text = data.decode('utf-8')
    counts = re.findall(r'Ran (\d+) tests? in', text)
    row.update(tests=int(counts[-1]) if counts else 0, log=log.name,
               log_sha256=hashlib.sha256(data).hexdigest())
    rows.append(row)
summary = {'expected_files': 21, 'files': len(rows), 'tests': sum(r['tests'] for r in rows),
           'all_passed': len(rows) == 21 and all(r['exit_code'] == 0 for r in rows), 'results': rows}
(folder / 'final-tests.json').write_bytes((json.dumps(summary, indent=2)+'\n').encode())
print(json.dumps({k:v for k,v in summary.items() if k != 'results'}))

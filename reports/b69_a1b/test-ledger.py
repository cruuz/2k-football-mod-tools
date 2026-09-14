"""Combine isolated runs without hiding earlier failures or unrun files."""
import hashlib
import json
from pathlib import Path
import re

root = Path.cwd()
out = root / 'reports/b69_a1b'
inventory = json.loads((out / 'inventory.json').read_text())
required = set(inventory['standalone_tests'])
observations = {}
for ledger in sorted(out.glob('*/tests.json')):
    for original in json.loads(ledger.read_text()):
        row = dict(original, group=ledger.parent.name)
        path = root / row['log']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row['log_sha256'], path
        row['log_mtime_ns'] = path.stat().st_mtime_ns
        observations.setdefault(row['path'], []).append(row)

rows = []
for path in sorted(required | set(observations)):
    history = sorted(observations.get(path, []), key=lambda r: r['log_mtime_ns'])
    # Final gates are authoritative. Never substitute the pre-edit gate run.
    eligible = [r for r in history if r['group'] not in ('gates', 'final-gates')]
    chosen = eligible[-1] if eligible else None
    text = (root / chosen['log']).read_text() if chosen else ''
    if chosen is None:
        outcome = 'pending'
    elif chosen['exit'] == 0:
        outcome = 'pass'
    elif chosen['exit'] == 124:
        outcome = 'timeout'
    elif 'sources changed during observed XBE composition' in text:
        outcome = 'source-edit overlap; rerun required'
    elif ('FileNotFoundError:' in text or 'ModuleNotFoundError:' in text or
          'missing local file docs/research/' in text):
        outcome = 'environment failure; see exact traceback'
    else:
        outcome = 'failure; inspect traceback'
    rows.append(dict(path=path, required=path in required, outcome=outcome,
                     selected=chosen, history=history))

summary = {key: sum(r['required'] and r['outcome'] == key for r in rows)
           for key in sorted({r['outcome'] for r in rows})}
document = dict(required=len(required), summary=summary, rows=rows)
(out / 'test-ledger.json').write_text(json.dumps(document, indent=2) + '\n')
lines = ['# Standalone test ledger', '',
    'Environment for every isolated run: `PYTHONPATH=. QT_QPA_PLATFORM=offscreen '
    'MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONHASHSEED=0`.',
    'Each link retains exact stdout/stderr. JSON retains every attempt, source hashes, '
    'log hashes, projection selection and source-stability checks. Earlier failures are '
    'not discarded. The newest completed attempt is shown below.', '',
    '| Test file | Outcome | Exact unittest result | Log |',
    '| --- | --- | --- | --- |']
for row in rows:
    selected = row['selected']
    result = (selected['ran'] + '; ' + selected['status']) if selected else 'Not completed'
    log = ('[' + selected['group'] + '](' + str(Path(selected['log']).relative_to('reports/b69_a1b')) + ')') if selected else ''
    lines.append(f"| `{Path(row['path']).name}` | {row['outcome']} | {result.replace('|', '/')} | {log} |")
(out / 'test-ledger.md').write_text('\n'.join(lines) + '\n')
print(json.dumps(dict(required=len(required), summary=summary), indent=2))

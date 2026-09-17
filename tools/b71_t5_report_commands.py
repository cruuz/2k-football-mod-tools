"""Collect retained command receipts and the latest standalone suite results."""
import json
from pathlib import Path
import shlex

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports/b71_t5'
rows = []
for path in sorted(OUT.rglob('*.json')):
    if path.name in {'commands.json', 'validation.json', 'latest-suites.json'}:
        continue
    value = json.loads(path.read_text())
    values = value if path.name == 'inspection-commands.json' else [value]
    for row in values:
        if isinstance(row, dict) and 'command' in row and 'exit_code' in row:
            rows.append({k:row[k] for k in ('command','started','exit_code','seconds') if k in row} |
                        {'record':str(path.relative_to(ROOT))})
rows.sort(key=lambda row:row.get('started',''))
(OUT/'commands.json').write_text(json.dumps(rows,indent=2)+'\n')
lines = ['# T5 command ledger', '', 'All elapsed times are wall seconds. Nonzero development runs are retained; corrected runs follow them.', '',
         '| Command | Exit | Seconds | Record |', '| --- | ---: | ---: | --- |']
latest = {}
for row in rows:
    argv = row['command']
    command = shlex.join(argv) if isinstance(argv,list) else argv
    command = command.replace('|','\\|').replace('\n',' <br> ')
    lines.append(f"| `{command}` | {row['exit_code']} | {row.get('seconds',0):.3f} | [{Path(row['record']).name}]({Path(row['record']).relative_to('reports/b71_t5')}) |")
    if isinstance(argv,list) and len(argv)==2 and Path(argv[1]).name.startswith('test_'):
        latest[Path(argv[1]).name] = row
(OUT/'COMMANDS.md').write_text('\n'.join(lines)+'\n')
(OUT/'latest-suites.json').write_text(json.dumps(latest,indent=2)+'\n')
print(json.dumps(dict(command_receipts=len(rows),standalone_suites=len(latest),
                     failures={k:v for k,v in latest.items() if v['exit_code']}),indent=2))

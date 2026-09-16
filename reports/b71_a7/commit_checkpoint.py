"""Commit only enumerated integration paths, including a real two-parent merge."""
from pathlib import Path
import json
import subprocess
import sys
from run import ROOT, OUT, run

label = sys.argv[1]
message = sys.argv[2]
paths = set(subprocess.check_output(['git', 'diff', '--name-only', 'HEAD'], text=True).splitlines())
paths.update(subprocess.check_output(['git', 'diff', '--cached', '--name-only'], text=True).splitlines())
paths.update(str(p.relative_to(ROOT)) for p in OUT.rglob('*')
             if p.is_file() and '__pycache__' not in p.parts)
paths.update(('ASTRA_REPORT.md', 'ASTRA_LAST_MESSAGE.md', 'WIRING.md',
              'ASTRA_B71_S4_REPORT.md', 'WIRING_B71_S4.md'))
paths = sorted(paths)
assert not any(p.startswith(('.scratch/', 'reports/assets/')) for p in paths)
(OUT / (label + '-paths.json')).write_text(json.dumps(paths, indent=2) + '\n')
assert run(label + '-stage', ['git', 'add', '-f', '--', *paths]) == 0
staged = set(subprocess.check_output(['git', 'diff', '--cached', '--name-only'], text=True).splitlines())
assert staged <= set(paths), sorted(staged - set(paths))
# --include supports an explicit path list while concluding a conflicted merge.
raise SystemExit(run(label, ['git', 'commit', '--include', '-m', message, '--', *paths]))

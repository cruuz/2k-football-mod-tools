"""Run the affected APF files independently, as CI does, with offscreen Qt."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[2]
report = root/'reports/b72-a2'
pattern = re.compile(r'apf_studio\.(?:session|gui|build|project)|apf_studio import (?:session|gui|build|project)|playcalling_editor_qt|playbook_(?:membership|package_map|route)_qt|playcalling')
files = sorted(path for path in (root/'tests/mod_editor').glob('test_apf*.py') if pattern.search(path.read_text()))
files += [root/'tests/mod_editor/test_b69_a1_playcalling.py', root/'tests/mod_editor/test_b72_a2_editor_blockers.py']
if len(sys.argv) > 1:
    files = [root/value for value in sys.argv[1:]]
files = list(dict.fromkeys(files))
(report/'test-files.txt').write_text(''.join(str(path.relative_to(root))+'\n' for path in files))
(report/'tests').mkdir(exist_ok=True)
env = dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONPATH=str(root))

def run(path):
    start = time.monotonic()
    logfile = report/'tests'/f'{path.stem}.log'
    with logfile.open('w') as output:
        try:
            result = subprocess.run([sys.executable, str(path)], cwd=root, env=env,
                                    stdout=output, stderr=subprocess.STDOUT, timeout=360)
            code = result.returncode
        except subprocess.TimeoutExpired:
            code = 124
    text = logfile.read_text(errors='replace')
    rows = re.findall(r'Ran (\d+) tests?', text)
    summary = {'file': str(path.relative_to(root)), 'exit_code': code,
               'seconds': round(time.monotonic()-start, 2), 'tests': sum(map(int, rows)),
               'result': '\n'.join(text.strip().splitlines()[-3:])}
    print(json.dumps(summary), flush=True)
    return summary

# Only two independent suites run at once. The timing acceptance runs alone.
regular = [path for path in files if path.stem != 'test_b72_a2_editor_blockers']
results = []
with ThreadPoolExecutor(max_workers=2) as pool:
    futures = [pool.submit(run, path) for path in regular]
    for future in as_completed(futures):
        results.append(future.result())
for path in files:
    if path.stem == 'test_b72_a2_editor_blockers':
        results.append(run(path))
(report/'test-results.json').write_text(json.dumps(sorted(results, key=lambda row: row['file']), indent=2)+'\n')
sys.exit(bool(any(row['exit_code'] for row in results)))

"""Rerun failed isolated files, retaining the initial evidence."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import time
ROOT = Path(__file__).resolve().parents[3]

def main():
    report = ROOT / 'reports/b72_t1'
    initial = [json.loads(line) for line in (report / 'sweep_progress.jsonl').read_text().splitlines()
               if line.startswith('{')]
    failed = sorted({row['file'] for row in initial if row['status'] != 'OK'})
    environment = dict(os.environ, PYTHONPATH=str(ROOT), QT_QPA_PLATFORM='offscreen', MOD_STUDIO_NO_UPDATE_CHECK='1')
    def run(name):
        path = report / 'sweep' / (Path(name).stem + '.log')
        original = path.with_suffix('.initial.log')
        if path.exists() and not original.exists():
            original.write_bytes(path.read_bytes())
        started = time.monotonic()
        try:
            result = subprocess.run([sys.executable, '-m', 'pytest', str(ROOT / 'tests/mod_editor' / name), '-q', '--tb=short'],
                cwd=ROOT, env=environment, capture_output=True, text=True, timeout=1500)
            if result.returncode == 5 and name in {
                    'test_nfl2k5_bump_strength.py', 'test_nfl2k5_bump_texture_writer.py',
                    'test_nfl2k5_music_conform_integration.py', 'test_nfl2k5_save_writer.py',
                    'test_nfl2k5_throw_tuning.py'}:
                result = subprocess.run([sys.executable, str(ROOT / 'tests/mod_editor' / name)],
                    cwd=ROOT, env=environment, capture_output=True, text=True, timeout=1500)
            path.write_text(result.stdout + result.stderr)
            status = 'OK' if result.returncode == 0 else 'FAIL'
        except subprocess.TimeoutExpired as exc:
            path.write_bytes((exc.stdout or b'') + (exc.stderr or b''))
            status = 'TIMEOUT'
        row = dict(file=name, status=status, seconds=time.monotonic()-started)
        print(json.dumps(row), flush=True)
        return row
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(run, failed))
    (report / 'sweep_retry_results.json').write_text(json.dumps(rows, indent=2))
    return int(any(row['status'] != 'OK' for row in rows))

if __name__ == '__main__':
    raise SystemExit(main())

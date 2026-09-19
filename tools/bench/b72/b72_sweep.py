"""Isolated pytest sweep, with the exact sweep711 hour-long exclusions."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import time
ROOT = Path(__file__).resolve().parents[3]
SKIP = {'test_xbe_patch_memory_writes', 'test_xbe_patch_cave_references', 'test_nfl2k5_owner_pairwise_composition',
        'test_nfl2k5_cave_oracle', 'test_nfl2k5_playbook_pair_manifest', 'test_nfl2k5_guardian_manifest',
        'test_nfl2k5_calendar_engine_unicorn', 'test_nfl2k5_guardian_unicorn', 'test_nfl2k5_qb_spy_runtime',
        'test_nfl2k5_my_career_draft', 'test_apf_studio_installer', 'test_nfl2k5_supersim_live', 'test_apf_xex_image_retail'}

def main():
    output = ROOT / 'reports/b72_t1/sweep'
    output.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in (ROOT / 'tests/mod_editor').glob('test_*.py') if p.stem not in SKIP)
    environment = dict(os.environ, PYTHONPATH=str(ROOT), QT_QPA_PLATFORM='offscreen', MOD_STUDIO_NO_UPDATE_CHECK='1')
    def run(path):
        started = time.monotonic()
        try:
            result = subprocess.run([sys.executable, '-m', 'pytest', str(path), '-q', '--tb=short'], cwd=ROOT,
                                    env=environment, capture_output=True, text=True, timeout=1500)
            if result.returncode == 5 and path.name in {
                    'test_nfl2k5_bump_strength.py', 'test_nfl2k5_bump_texture_writer.py',
                    'test_nfl2k5_music_conform_integration.py', 'test_nfl2k5_save_writer.py',
                    'test_nfl2k5_throw_tuning.py'}:
                # These CI wrappers expose unittest.main, not pytest items.
                result = subprocess.run([sys.executable, str(path)], cwd=ROOT,
                                        env=environment, capture_output=True, text=True, timeout=1500)
            (output / (path.stem + '.log')).write_text(result.stdout + result.stderr)
            status = 'OK' if result.returncode == 0 else 'FAIL'
        except subprocess.TimeoutExpired as exc:
            (output / (path.stem + '.log')).write_bytes((exc.stdout or b'') + (exc.stderr or b''))
            status = 'TIMEOUT'
        row = dict(file=path.name, status=status, seconds=time.monotonic()-started)
        print(json.dumps(row), flush=True)
        return row
    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(run, files))
    (output / 'results.json').write_text(json.dumps(dict(excluded=sorted(SKIP), results=rows), indent=2))
    return int(any(row['status'] != 'OK' for row in rows))

if __name__ == '__main__':
    raise SystemExit(main())

"""Run standalone suites with bounded logs and per-process memory receipts.

Development only. Writes logs/JSON under this worktree's .scratch directory.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def run(files, output, manifest):
    output = Path(output).resolve()
    if ROOT / '.scratch' not in output.parents:
        raise ValueError('validation output must remain in this worktree .scratch')
    output.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'PYTHONHASHSEED': '0'}
    env['NFL2K5_CAVE_MANIFEST'] = str(Path(manifest).resolve())
    rows = []
    source_paths = [ROOT/'tools/mycareer_mode/runtime.c', ROOT/'tools/mycareer_mode/runtime.S']
    source_paths += sorted((ROOT/'mod_editor/core').glob('nfl2k5_my_career*.py'))
    source_paths += [ROOT/'mod_editor/core/nfl2k5_xbe_space.py', ROOT/'mod_editor/core/nfl2k5_senior_bowl.py']
    pins = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    for name in files:
        path = (ROOT/name).resolve()
        if path.parent != ROOT/'tests/mod_editor' or not path.name.startswith('test_') or path.suffix != '.py':
            raise ValueError('only standalone mod_editor unittest files are accepted')
        log = output.parent/(path.stem+'.log')
        launch_pins = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in source_paths}
        command = [sys.executable, str(path.relative_to(ROOT))]
        # GNU time's -f is not supported by the /usr/bin/time shipped on macOS.
        timed = (['/usr/bin/time', '-f', 'MAX_RSS_KIB=%M', *command]
                 if sys.platform.startswith('linux') and Path('/usr/bin/time').is_file() else command)
        print('RUN', path.name, flush=True)
        start = time.monotonic()
        with log.open('wb') as stream:
            try:
                result = subprocess.run(timed, cwd=ROOT, env=env, stdout=stream,
                                        stderr=subprocess.STDOUT, timeout=7200, check=False)
                code = result.returncode
            except subprocess.TimeoutExpired:
                code = 124
        if log.stat().st_size > 4*1024**2:
            raise ValueError('bounded test log exceeded 4 MiB')
        text = log.read_text(errors='replace')
        match = re.search(r'Ran (\d+) tests? in ([\d.]+)s', text)
        memory = re.search(r'MAX_RSS_KIB=(\d+)', text)
        skipped = re.search(r'skipped=(\d+)', text)
        row = dict(command='python3 '+path.relative_to(ROOT).as_posix(), exit_code=code,
            tests=int(match[1]) if match else None, seconds=float(match[2]) if match else None,
            wall_seconds=round(time.monotonic()-start,3),
            max_rss_kib=int(memory[1]) if memory else None,
            skipped=int(skipped[1]) if skipped else 0,
            result='passed' if code==0 and match else 'failed',
            source_sha256=launch_pins,
            log=log.relative_to(ROOT).as_posix(), log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
        if any(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=pin for p,pin in launch_pins.items()):
            row['result']='failed: production source changed during this suite'
        if row['max_rss_kib'] and row['max_rss_kib'] >= 2*1024**2:
            row['result']='failed: process exceeded 2 GiB RSS'
        rows.append(row)
        receipt=dict(schema='nfl2k5.mycareer.m3-validation-group.v1', experimental=True,
            runtime_witnessed=False, source_sha256=pins,
            manifest_sha256=hashlib.sha256(Path(manifest).read_bytes()).hexdigest(), tests=rows)
        output.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
        print(row['result'],path.name,row['tests'],row['seconds'],flush=True)
    return all(r['result']=='passed' for r in rows)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--manifest',required=True,type=Path)
    parser.add_argument('files',nargs='+')
    args=parser.parse_args()
    raise SystemExit(0 if run(args.files,args.output,args.manifest) else 1)

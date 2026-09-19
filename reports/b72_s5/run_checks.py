"""Standalone validation receipts, two bounded interpreters at most."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json
import os
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent/'checks'


def run(path):
    env=dict(os.environ,PYTHONPATH=str(ROOT),QT_QPA_PLATFORM='offscreen')
    start=time.monotonic()
    with (OUT/(path.stem+'.log')).open('w',encoding='utf-8') as log:
        try:
            p=subprocess.run([sys.executable,str(path)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=420)
            code=p.returncode
        except subprocess.TimeoutExpired:code=124
    row=dict(file=path.relative_to(ROOT).as_posix(),exit_code=code,seconds=round(time.monotonic()-start,2))
    print(json.dumps(row),flush=True)
    return row


def main():
    OUT.mkdir(exist_ok=True)
    names=['test_provider_integrity.py',
           'test_shipped_tools_posix_only.py','test_shipped_tools_are_self_sufficient.py','test_scorebug_replication.py']
    paths=sorted(set((ROOT/'tests/mod_editor'/n) for n in names)|set((ROOT/'tests/mod_editor').glob('test_*scorebug*.py')))
    # One worker leaves room for the independent release-closure run.
    rows=[]
    for path in paths:
        rows.append(run(path));(OUT/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
    return int(any(r['exit_code'] for r in rows))

if __name__=='__main__':raise SystemExit(main())

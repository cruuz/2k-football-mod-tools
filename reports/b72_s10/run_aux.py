"""Bounded standalone owner/oracle gates, separate from default sprite checks."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
names=['test_xbe_patch_memory_writes.py','test_xbe_patch_cave_references.py',
       'test_nfl2k5_cave_oracle.py','test_phase1_packaging.py']
rows=[]
for name in names:
    command=[sys.executable,str(ROOT/'tests/mod_editor'/name)]
    start=time.monotonic()
    with (OUT/(name+'.log')).open('w',encoding='utf-8') as log:
        try:
            result=subprocess.run(command,cwd=ROOT,env=dict(os.environ,PYTHONPATH=str(ROOT),QT_QPA_PLATFORM='offscreen'),
                stdout=log,stderr=subprocess.STDOUT,timeout=420)
            code=result.returncode
        except subprocess.TimeoutExpired:code=124
    row=dict(file='tests/mod_editor/'+name,exit_code=code,seconds=round(time.monotonic()-start,2))
    rows.append(row);print(json.dumps(row),flush=True)
    (OUT/'aux_checks.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8',newline='\n')
raise SystemExit(int(any(r['exit_code'] for r in rows)))

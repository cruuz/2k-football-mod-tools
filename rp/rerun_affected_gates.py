from pathlib import Path
import json
import os
import resource
import subprocess
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'rp/evidence'
os.sched_setaffinity(0,set(range(24,32)))
resource.setrlimit(resource.RLIMIT_AS,(3_800_000_000,3_800_000_000))
ENV=dict(os.environ,PYTHONPATH=str(ROOT),QT_QPA_PLATFORM='offscreen',PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
rows=json.loads((OUT/'gates.json').read_text())
def run(name,args,cwd=ROOT,env=ENV):
 start=time.monotonic()
 with (OUT/(name+'.log')).open('w') as log:
  p=subprocess.run(['/usr/bin/time','-v',*args],cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600)
 row=dict(name=name,exit_code=p.returncode,seconds=round(time.monotonic()-start,2))
 rows[:]=[r for r in rows if r['name']!=name]+[row]
 (OUT/'gates.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
 return p.returncode
with tempfile.TemporaryDirectory(prefix='b76-rp-final-') as folder:
 stage=Path(folder)/'stage'
 if not run('stage-2k5',[sys.executable,'packaging/stage_release.py','packaging/release-allowlist.txt',str(stage)]):
  env=dict(ENV,PYTHONPATH=str(stage))
  for kind in ['release','runtime']:
   args=[sys.executable,str(stage/'packaging'/f'check_2k5_mod_studio_{kind}.py')]
   if kind=='release':args.append(str(stage))
   run(kind+'-2k5',args,stage,env)
for suite in ['test_b76_ed2_build_recursion','test_phase1_packaging']:
 run(suite,[sys.executable,str(ROOT/'tests/mod_editor'/(suite+'.py'))])
print('FAILED',[r['name'] for r in rows if r['exit_code']],flush=True)

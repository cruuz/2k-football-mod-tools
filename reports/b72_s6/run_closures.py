"""Audit temporary release closures, without publishing or retaining a stage."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--app',choices=['all','2k5','apf2k8'],default='all')
args=parser.parse_args()
rows=[] if args.app=='all' else [r for r in json.loads((OUT/'closures.json').read_text()) if r['app']!=args.app]
for app,allowlist in [('2k5','release-allowlist.txt'),('apf2k8','apf2k8-release-allowlist.txt')]:
    if args.app!='all' and args.app!=app:continue
    with tempfile.TemporaryDirectory(prefix='b72-s6-closure-') as folder:
        stage=Path(folder)/'stage'
        commands=[([sys.executable,str(ROOT/'packaging/stage_release.py'),str(ROOT/'packaging'/allowlist),str(stage),str(ROOT)],ROOT),
            ([sys.executable,str(stage/'packaging'/('check_'+app+'_mod_studio_release.py')),str(stage)],stage),
            ([sys.executable,str(stage/'packaging'/('check_'+app+'_mod_studio_runtime.py'))],stage)]
        for index,(command,cwd) in enumerate(commands):
            start=time.monotonic()
            with (OUT/(app+'_closure_'+str(index)+'.log')).open('w',encoding='utf-8') as log:
                try:
                    result=subprocess.run(command,cwd=cwd,env=dict(os.environ,PYTHONPATH=str(stage),QT_QPA_PLATFORM='offscreen'),stdout=log,stderr=subprocess.STDOUT,timeout=420)
                    code=result.returncode
                except subprocess.TimeoutExpired:code=124
            row=dict(app=app,step=index,exit_code=code,seconds=round(time.monotonic()-start,2))
            rows.append(row);print(json.dumps(row),flush=True)
            (OUT/'closures.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
            if code:break
raise SystemExit(int(any(r['exit_code'] for r in rows)))

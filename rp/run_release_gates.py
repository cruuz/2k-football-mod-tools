"""Serial release closures and focused tests, constrained to the release-prep budget."""
from pathlib import Path
import json
import os
import resource
import subprocess
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'rp/evidence'
os.sched_setaffinity(0,set(range(24,32)))
resource.setrlimit(resource.RLIMIT_AS,(3_800_000_000,3_800_000_000))
ENV=dict(os.environ,PYTHONPATH=str(ROOT),QT_QPA_PLATFORM='offscreen',PYTHONDONTWRITEBYTECODE='1',
         OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
rows=[]
def run(name,argv,cwd=ROOT,env=ENV):
    start=time.monotonic()
    with (OUT/(name+'.log')).open('w') as log:
        try:
            p=subprocess.run(['/usr/bin/time','-v',*argv],cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600)
            rc=p.returncode
        except subprocess.TimeoutExpired:rc=124
    row=dict(name=name,exit_code=rc,seconds=round(time.monotonic()-start,2))
    rows.append(row)
    (OUT/'gates.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(json.dumps(row),flush=True)
    return rc
for app,allow in [('2k5','release-allowlist.txt'),('apf2k8','apf2k8-release-allowlist.txt')]:
    with tempfile.TemporaryDirectory(prefix='b76-rp-'+app+'-') as folder:
        stage=Path(folder)/'stage'
        if run('stage-'+app,[sys.executable,str(ROOT/'packaging/stage_release.py'),str(ROOT/'packaging'/allow),str(stage),str(ROOT)]):continue
        env=dict(ENV,PYTHONPATH=str(stage))
        run('release-'+app,[sys.executable,str(stage/'packaging'/f'check_{app}_mod_studio_release.py'),str(stage)],stage,env)
        run('runtime-'+app,[sys.executable,str(stage/'packaging'/f'check_{app}_mod_studio_runtime.py')],stage,env)
for suite in [
    'test_build_panel_qt','test_ux_build_plan_coverage_qt','test_b76_ed2_build_recursion',
    'test_b76_release_build_controls','test_b76_release_texts',
    'test_stage_release','test_phase1_packaging','test_runtime_dependencies',
    'test_update_check','test_self_update','test_beta45_honesty_freeze',
    'test_apf_public_docs_registry_current','test_build_data_allowlist',
]:
    run(suite,[sys.executable,str(ROOT/'tests/mod_editor'/(suite+'.py'))])
run('board-kit-data',[sys.executable,'-m','unittest','test_nfl2k5_board_kit.Data'],env=dict(ENV,PYTHONPATH=str(ROOT)+os.pathsep+str(ROOT/'tests/mod_editor')))
run('build-data-allowlist',[sys.executable,str(ROOT/'packaging/check_build_data_allowlist.py'),'--json',str(OUT/'data-final.json')])
run('registry-structure',[sys.executable,str(ROOT/'mod_editor/capabilities/validate_registry.py'),'--skip-file-checks'])
print('FAILED', [r['name'] for r in rows if r['exit_code']],flush=True)
raise SystemExit(any(r['exit_code'] for r in rows))

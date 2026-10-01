"""DESIGN: wait for space, run the entire unchanged C recipe with dc roster.

All writable cache/staging locations are local to astra-build. This launcher
copies the supplied project and recipe verbatim and uses the same build entry.
The dc finisher verifies the result before deleting only its own disc.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dc.import_depth import OUT,sha
HUB=Path('/home/noah/Desktop/2K5-8 Editors/ultimate')
RECIPE=HUB/'ULTIMATE_BUILD_RECIPE_2026-09-27_candidate_C.json'
PROJECT=Path('/media/noah/Storage/.b76-research/main/freeze/candC/league_project_k2_v54_49ers_frozen.json')
GB=1024**3
SESSION_LOCK=Path('/home/noah/2k-worktrees/.b76-session/xemu.lock')

def child():
    sys.path[:0]=[str(ROOT),str(OUT/'runner'),str(ROOT/'tools')]
    from mod_editor.core import nfl2k5_source_cache as cache
    cache.default_cache_root=lambda: OUT/'source-cache'
    import build_ultimate_teams2026 as build
    sys.argv=[str(OUT/'runner/build_ultimate_teams2026.py'),str(ROOT),str(OUT/'candidate_C_dc.xiso.iso'),
              '--recipe',str(OUT/'candidate_C_recipe.json'),'--project',str(OUT/'league_project.json'),
              '--roster-edits',str(OUT/'league_roster_edits_candC_dc.json')]
    # C's recipe coordinates the disc write with main's lab using this existing
    # advisory lock. Open read-only: never create or rewrite shared state.
    import fcntl
    with SESSION_LOCK.open('rb') as gate:
        print('DESIGN: waiting for the existing shared build/lab lock and space floors',flush=True)
        while True:
            if shutil.disk_usage(OUT).free>=30*GB and shutil.disk_usage(ROOT).free>100*GB:
                try:
                    fcntl.flock(gate.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:
                    pass
                else:
                    if shutil.disk_usage(OUT).free>=30*GB and shutil.disk_usage(ROOT).free>100*GB:
                        break
                    fcntl.flock(gate.fileno(),fcntl.LOCK_UN)
            time.sleep(15)
        print('PROVED OFFLINE: shared build/lab lock acquired read-only; space floors rechecked',flush=True)
        return build.main()

def main():
    if '--child' in sys.argv:return child()
    OUT.mkdir(parents=True,exist_ok=True)
    for p in ('tmp','cache','runner'): (OUT/p).mkdir(exist_ok=True)
    for source,target in [(RECIPE,OUT/'candidate_C_recipe.json'),(PROJECT,OUT/'league_project.json'),
                          (HUB/'build_ultimate.py',OUT/'runner/build_ultimate.py'),
                          (HUB/'build_ultimate_teams2026.py',OUT/'runner/build_ultimate_teams2026.py')]:
        shutil.copyfile(source,target)
        assert source.read_bytes()==target.read_bytes()
    receipt={'evidence':'PROVED OFFLINE','status':'waiting_for_space_and_ready',
             'inputs':{str(p):sha(p.read_bytes()) for p in (RECIPE,PROJECT,OUT/'league_roster_edits_candC_dc.json')},
             'storage_threshold_bytes':30*GB,'nvme_floor_bytes':100*GB,
             'recipe_overrides_changed':[], 'project_bytes_unchanged':True,
             'cache_override':'DESIGN: private source-cache root redirected under dc/astra-build; normal verification retained'}
    path=OUT/'build_execution.json'
    def save():path.write_text(json.dumps(receipt,indent=2)+'\n')
    started=time.time()
    while True:
        storage=shutil.disk_usage(OUT).free;nvme=shutil.disk_usage(ROOT).free
        receipt.update(storage_free=storage,nvme_free=nvme,wait_seconds=round(time.time()-started))
        save()
        if storage>=30*GB and nvme>100*GB and (OUT/'READY_FOR_BUILD').is_file():break
        time.sleep(15)
    env={**os.environ,'ULTIMATE_NO_REEXEC':'1','TMPDIR':str(OUT/'tmp'),'XDG_CACHE_HOME':str(OUT/'cache'),
         'PYTHONDONTWRITEBYTECODE':'1','QT_QPA_PLATFORM':'offscreen'}
    command=['nice','-n','10','taskset','-c','0-23',sys.executable,str(Path(__file__).resolve()),'--child']
    receipt.update(command=command,status='running',started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                   storage_free_start=storage,nvme_free_start=nvme,storage_free_min=storage,nvme_free_min=nvme)
    with (OUT/'build.log').open('w') as log:
        proc=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True)
        receipt['pid']=proc.pid;save()
        while proc.poll() is None:
            storage=shutil.disk_usage(OUT).free;nvme=shutil.disk_usage(ROOT).free
            receipt['storage_free_min']=min(receipt['storage_free_min'],storage)
            receipt['nvme_free_min']=min(receipt['nvme_free_min'],nvme)
            if nvme<=100*GB or storage<2*GB:
                import signal
                os.killpg(proc.pid,signal.SIGTERM)
                receipt['stop_reason']='space floor reached'
            save();time.sleep(15)
        receipt.update(status='passed' if proc.returncode==0 else 'failed',exit_code=proc.returncode,
                       finished_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
        save()
    if proc.returncode==0:
        result=subprocess.run(['nice','-n','10','taskset','-c','0-23',sys.executable,str(ROOT/'dc/finish_build.py')],env=env)
        receipt['finisher_exit_code']=result.returncode;save()
        return result.returncode
    return proc.returncode
if __name__=='__main__':raise SystemExit(main())

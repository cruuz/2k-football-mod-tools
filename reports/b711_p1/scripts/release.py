from pathlib import Path
import shutil
import subprocess
import sys

root=Path.cwd()
base=Path('/tmp/astra-b711-p1-stages')
base.mkdir(exist_ok=True)
codes=[]
prefix = sys.argv[1] + '-' if len(sys.argv) > 1 else ''
def run(label,*command):
    result=subprocess.run([sys.executable,'.scratch/run.py',prefix+label,*map(str,command)])
    codes.append(result.returncode)
    return result.returncode
for product,allow in (('2k5','release-allowlist.txt'),('apf2k8','apf2k8-release-allowlist.txt')):
    stage=base/product
    if stage.exists():shutil.rmtree(stage)
    if run('stage-'+product,sys.executable,'packaging/stage_release.py','packaging/'+allow,stage):continue
    run('release-'+product,sys.executable,'packaging/check_'+product+'_mod_studio_release.py',stage)
    run('runtime-'+product,'env','PYTHONPATH='+str(stage),sys.executable,stage/('packaging/check_'+product+'_mod_studio_runtime.py'))
    run('release-after-'+product,sys.executable,'packaging/check_'+product+'_mod_studio_release.py',stage)
print('RELEASE_FAILURES',sum(bool(c) for c in codes),flush=True)
sys.exit(bool(any(codes)))

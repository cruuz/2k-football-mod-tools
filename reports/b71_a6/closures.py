from pathlib import Path
import shutil,sys
from run import ROOT,run
failures=[]
for product,allow,stem in [('2k5','release-allowlist.txt','2k5'),('apf','apf2k8-release-allowlist.txt','apf2k8')]:
 stage=ROOT/'.scratch'/('release-'+product)
 if stage.exists():shutil.rmtree(stage)
 rc=run('stage-'+product+'-final',['python3','packaging/stage_release.py','packaging/'+allow,str(stage)])
 if rc:failures.append(product+' stage');continue
 rc=run('release-'+product+'-final',['env','PYTHONDONTWRITEBYTECODE=1','python3',f'packaging/check_{stem}_mod_studio_release.py',str(stage)])
 if rc:failures.append(product+' release')
 rc=run('runtime-'+product+'-final',['env','PYTHONDONTWRITEBYTECODE=1','PYTHONNOUSERSITE=1','PYTHONPATH='+str(stage),str(ROOT/'.scratch/test-python/bin/python3'),str(stage/f'packaging/check_{stem}_mod_studio_runtime.py')])
 if rc:failures.append(product+' runtime')
print('CLOSURES',failures,flush=True)
sys.exit(bool(failures))

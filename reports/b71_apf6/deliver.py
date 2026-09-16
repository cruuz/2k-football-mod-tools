"""Create an explicit-path report commit and verify the private A7-based bundle."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
root=Path(__file__).resolve().parents[2]
folder=Path(__file__).parent
base=(folder/'base.txt').read_text().strip()
git=['git','--git-dir=.scratch/git','--work-tree=.']
receipt_path=root/'.scratch/astra-b71-apf6-delivery.json'
bundle=root/'.scratch/astra-b71-apf6.bundle'
receipt={'base':base,'branch':'astra/b71-apf6-editor-workflow','commands':[],'push':False,'emulator_opened':False}
if receipt_path.is_file(): receipt['commands']=json.loads(receipt_path.read_text())['commands']
def save():receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
def run(command):
 begin=time.monotonic(); started=datetime.datetime.now(datetime.timezone.utc).isoformat()
 result=subprocess.run(command,cwd=root,env=dict(os.environ,PYTHONPATH=str(root),QT_QPA_PLATFORM='offscreen'),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
 receipt['commands'].append({'command':command,'started_utc':started,'elapsed_seconds':round(time.monotonic()-begin,3),'exit_code':result.returncode,'output':result.stdout})
 save()
 if result.returncode: print(result.stdout);raise SystemExit(result.returncode)
 return result.stdout.strip()
run(['python3','reports/b71_apf6/make_report.py','--require-pass'])
run(['python3','reports/b71_apf6/audit_delivery.py'])
implementation=json.loads((folder/'implementation_paths.json').read_text())
paths=['ASTRA_REPORT.md','ASTRA_LAST_MESSAGE.md',*implementation]
paths += [p.relative_to(root).as_posix() for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
paths=sorted(set(paths+['reports/b71_apf6/delivery_paths.json']))
(folder/'delivery_paths.json').write_text(json.dumps(paths,indent=2)+'\n')
assert all(not p.startswith('/') and '..' not in Path(p).parts and (root/p).is_file() for p in paths)
assert (root/'ASTRA_LAST_MESSAGE.md').read_text().endswith('ASTRA_DONE\n')
run([*git,'add','-f','--',*paths])
run([*git,'diff','--cached','--check','--','.',':(exclude)reports/b71_apf6/*.log'])
run(['python3','packaging/repin.py','--apply'])
run([*git,'commit','-m','APF: finish retirement atomicity and record editor workflow gates','--',*paths])
receipt['head']=run([*git,'rev-parse','HEAD'])
receipt['commits']=run([*git,'log','--oneline',base+'..HEAD'])
run([*git,'bundle','create',str(bundle.relative_to(root)),base+'..'+receipt['branch']])
run([*git,'bundle','verify',str(bundle.relative_to(root))])
run([*git,'bundle','list-heads',str(bundle.relative_to(root))])
run([*git,'diff','--exit-code'])
run([*git,'diff','--cached','--exit-code'])
receipt['bundle']={'path':str(bundle.relative_to(root)),'bytes':bundle.stat().st_size,'sha256':hashlib.sha256(bundle.read_bytes()).hexdigest()}
# No remaining check may depend on these temporary local resources at delivery.
begin=time.monotonic();started=datetime.datetime.now(datetime.timezone.utc).isoformat()
for name in ('apf-release','test-python'):
 path=root/'.scratch'/name
 assert not path.is_symlink() and path.resolve().parent==(root/'.scratch').resolve()
 if path.exists():shutil.rmtree(path)
receipt['commands'].append({'command':['python cleanup of exact local .scratch/apf-release and .scratch/test-python'],
                           'started_utc':started,'elapsed_seconds':round(time.monotonic()-begin,3),'exit_code':0,'output':'Deleted only the disposable release stage and prepared test interpreter.'})
receipt['scratch_bytes']=sum(p.stat().st_size for p in (root/'.scratch').rglob('*') if p.is_file() and not p.is_symlink())
assert receipt['scratch_bytes']<200*1024*1024
save()
print(json.dumps({k:v for k,v in receipt.items() if k!='commands'},indent=2))

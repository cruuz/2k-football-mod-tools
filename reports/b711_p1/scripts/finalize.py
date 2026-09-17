from pathlib import Path
import datetime
import hashlib
import json
import shutil
import subprocess
import time

root=Path.cwd()
private=root/'.scratch/private.git'
g=['git','--git-dir='+str(private),'--work-tree='+str(root)]
record=[]
def run(args):
    start=datetime.datetime.now(datetime.timezone.utc).isoformat();tick=time.monotonic()
    result=subprocess.run(args,cwd=root,text=True,capture_output=True)
    row=dict(command=args,start=start,seconds=round(time.monotonic()-tick,3),exit_code=result.returncode,
             output=result.stdout+result.stderr)
    record.append(row)
    (root/'.scratch/delivery.json').write_text(json.dumps(record,indent=2)+'\n')
    print(row['output'],flush=True)
    if result.returncode:raise RuntimeError(str(args))
    return result.stdout.strip()
paths=['ASTRA_REPORT.md','ASTRA_LAST_MESSAGE.md','tests/mod_editor/test_numpy_optional.py']+[p.relative_to(root).as_posix() for p in sorted((root/'reports/b711_p1').rglob('*')) if p.is_file()]
run(g+['add','-f','--']+paths)
run(g+['commit','-m','Record NumPy runtime diagnosis, regression checks and artifact evidence','--']+paths)
base=(root/'.scratch/base').read_text().strip()
bundle=root/'.scratch/astra-b71-p1.bundle'
run(g+['bundle','create',str(bundle),base+'..astra/b71-p1-numpy'])
run(g+['bundle','verify',str(bundle)])
run(g+['bundle','list-heads',str(bundle)])
head=run(g+['rev-parse','HEAD'])
digest=hashlib.sha256(bundle.read_bytes()).hexdigest()
(bundle.with_suffix(bundle.suffix+'.sha256')).write_text(digest+'  '+bundle.name+'\n')
for name in ('runtime','python','stages','removed','wine'):
    path=Path('/tmp')/('astra-b711-p1-'+name)
    tick=time.monotonic();start=datetime.datetime.now(datetime.timezone.utc).isoformat()
    if path.exists():shutil.rmtree(path)
    record.append(dict(command=['shutil.rmtree',str(path)],start=start,seconds=round(time.monotonic()-tick,3),exit_code=0))
run(g+['status','--short'])
(root/'.scratch/delivery.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(dict(head=head,bundle=str(bundle),bytes=bundle.stat().st_size,sha256=digest)),flush=True)

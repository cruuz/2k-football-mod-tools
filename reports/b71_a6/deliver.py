"""Publish the private branch as an incremental local bundle and verify read-back."""
from pathlib import Path
import datetime,hashlib,json,shlex,subprocess,tempfile,time
ROOT=Path(__file__).resolve().parents[2];G=['git','--git-dir='+str(ROOT/'.scratch/git-a6'),'--work-tree='+str(ROOT)]
commands=json.loads((ROOT/'.scratch/astra-b71-a6-final-commit.json').read_text())
def run(argv):
 start=time.monotonic();p=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True)
 commands.append(dict(command=shlex.join(argv),exit_code=p.returncode,seconds=round(time.monotonic()-start,3),stdout=p.stdout,stderr=p.stderr))
 if p.returncode:raise RuntimeError(p.stderr or p.stdout)
 return p.stdout.strip()
bundle=ROOT/'.scratch/astra-b71-a6.bundle'
head=run(G+['rev-parse','HEAD']);tree=run(G+['rev-parse','HEAD^{tree}'])
run(G+['bundle','create',str(bundle),'astra/b71-a6-integrate','^a142739b'])
run(G+['bundle','verify',str(bundle)])
with tempfile.TemporaryDirectory(prefix='b71-a6-bundle-check-') as folder:
 p=Path(folder)/'verify.git';run(['git','init','--bare',str(p)])
 (p/'objects/info/alternates').write_text('/home/noah/2k-football-mod-tools/.git/objects\n')
 vg=['git','--git-dir='+str(p)]
 run(vg+['fetch',str(bundle),'astra/b71-a6-integrate:refs/heads/verified'])
 assert run(vg+['rev-parse','verified'])==head
 assert run(vg+['rev-parse','verified^{tree}'])==tree
 run(vg+['fsck','--connectivity-only','--no-dangling','verified'])
size=sum(p.stat().st_size for p in (ROOT/'.scratch').rglob('*') if p.is_file())
assert size<200*1024*1024
receipt=dict(head=head,tree=tree,branch='astra/b71-a6-integrate',prerequisite='a142739b',bundle=str(bundle.relative_to(ROOT)),bytes=bundle.stat().st_size,sha256=hashlib.sha256(bundle.read_bytes()).hexdigest(),verified_fresh_fetch_and_tree=True,scratch_bytes=size,commands=commands)
(ROOT/'.scratch/astra-b71-a6-delivery.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({k:v for k,v in receipt.items() if k!='commands'},indent=2))

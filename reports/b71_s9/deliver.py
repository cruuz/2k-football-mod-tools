"""Commit completed evidence by explicit paths and create/verify the private bundle."""
from pathlib import Path
import datetime,hashlib,json,subprocess,time
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
BASE='02bbadd184e85498a441d3be71e70f8de94b9b0a'
BRANCH='refs/heads/astra/b71-s9-down-label'
GIT=['git','--git-dir=.scratch/astra-b71-s9.git','--work-tree=.']
rows=json.loads((ROOT/'.scratch/delivery_commands.json').read_text()) if (ROOT/'.scratch/delivery_commands.json').exists() else []
def run(argv):
 started=datetime.datetime.now(datetime.timezone.utc).isoformat();tick=time.monotonic()
 p=subprocess.run(argv,cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 row=dict(argv=argv,start_utc=started,seconds=round(time.monotonic()-tick,3),exit_code=p.returncode,output=p.stdout)
 rows.append(row);(ROOT/'.scratch/delivery_commands.json').write_text(json.dumps(rows,indent=2)+'\n')
 print(p.stdout,end='',flush=True)
 if p.returncode:raise SystemExit(p.returncode)
 return p.stdout.strip()
def main():
 for name in ('final-suites','prove-states-final','draw-order-anchor-final','repin-before-evidence-commit'):
  assert json.loads((OUT/(name+'.result.json')).read_text())['exit_code']==0,name
 assert (ROOT/'ASTRA_LAST_MESSAGE.md').read_text().endswith('ASTRA_DONE\n')
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==BASE
 paths=['ASTRA_REPORT.md','ASTRA_LAST_MESSAGE.md']
 paths += [p.relative_to(ROOT).as_posix() for p in sorted(OUT.iterdir()) if p.is_file() and p.suffix in ('.py','.json','.log','.png') and p.name!='inspect-launch.log']
 run(GIT+['add','--',*paths])
 run(GIT+['commit','-m','Record S9 native draw-order proof and hotfix candidate validation','--',*paths])
 run(GIT+['diff','--check',BASE+'..HEAD'])
 bundle='.scratch/astra-b71-s9.bundle'
 run(GIT+['bundle','create',bundle,BASE+'..'+BRANCH])
 run(GIT+['bundle','verify',bundle])
 head=run(GIT+['rev-parse','HEAD'])
 heads=run(GIT+['bundle','list-heads',bundle])
 assert heads==head+' '+BRANCH
 run(GIT+['diff','--exit-code','HEAD','--',*paths])
 report=dict(branch=BRANCH,base=BASE,head=head,bundle=bundle,bundle_bytes=(ROOT/bundle).stat().st_size,bundle_sha256=hashlib.sha256((ROOT/bundle).read_bytes()).hexdigest(),bundle_verified=True,normal_worktree_head_unchanged=True)
 (ROOT/'.scratch/delivery.json').write_text(json.dumps(report,indent=2)+'\n');print('ASTRA_DELIVERY_OK',json.dumps(report))
if __name__=='__main__':main()

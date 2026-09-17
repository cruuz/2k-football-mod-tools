"""Commit explicit evidence paths and verify the private prerequisite bundle."""
from pathlib import Path
import datetime,hashlib,json,subprocess,time
ROOT=Path(__file__).resolve().parents[2];GIT=ROOT/'.scratch/astra-b71-s10.git'
BASE='a3f18036230e386c63b26ee7ec95606753d7eea8';BRANCH='astra/b71-s10-down-label-cause'
ledger=[]
def run(argv):
 start=datetime.datetime.now(datetime.timezone.utc).isoformat();t=time.monotonic()
 result=subprocess.run(argv,cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
 row=dict(argv=argv,start_utc=start,end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),seconds=round(time.monotonic()-t,3),exit_code=result.returncode,output=result.stdout)
 ledger.append(row);(ROOT/'.scratch/delivery_commands.json').write_text(json.dumps(ledger,indent=2)+'\n')
 print(json.dumps(row),flush=True);result.check_returncode();return result.stdout.strip()
git=['git','--git-dir='+str(GIT),'--work-tree='+str(ROOT)]
run(['python3','reports/b71_s10/check_delivery_inputs.py'])
run(git+['diff','--check'])
files=['ASTRA_REPORT.md','ASTRA_LAST_MESSAGE.md']+[str(p.relative_to(ROOT)) for p in sorted((ROOT/'reports/b71_s10').rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc',) and p.name!='writers-launch.log']
run(git+['add','--',*files])
run(['python3','packaging/repin.py','--apply'])
# Repin must not introduce an uncommitted code mutation at delivery.
assert not run(git+['diff','--name-only','--','mod_editor','tools','data','docs'])
run(git+['commit','-m','Record S10 writer census, visibility correction and unresolved played cause','--',*files])
head=run(git+['rev-parse','HEAD']);run(git+['merge-base','--is-ancestor',BASE,'HEAD'])
bundle=ROOT/'.scratch/astra-b71-s10.bundle'
run(git+['bundle','create',str(bundle),BASE+'..'+BRANCH]);run(git+['bundle','verify',str(bundle)])
header=bundle.read_bytes().split(b'\n\n',1)[0].decode();assert '\n-'+BASE+' ' in header,header
verify=ROOT/'.scratch/astra-b71-s10-verify.git'
run(['git','init','--bare',str(verify)])
(verify/'objects/info/alternates').write_text((GIT/'objects/info/alternates').read_text())
vg=['git','--git-dir='+str(verify)]
run(vg+['fetch',str(bundle),BRANCH+':refs/heads/'+BRANCH]);assert run(vg+['rev-parse',BRANCH])==head
result=dict(base=BASE,head=head,branch=BRANCH,bundle=str(bundle.relative_to(ROOT)),bytes=bundle.stat().st_size,sha256=hashlib.sha256(bundle.read_bytes()).hexdigest(),independent_fetch_verified=True,root_cause_proved=False,runtime_witnessed=False)
(ROOT/'.scratch/delivery.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2),flush=True)

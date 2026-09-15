"""Explicit-path private commit and verified incremental bundle; never push."""
from pathlib import Path
import datetime,hashlib,json,subprocess,time
root=Path(__file__).resolve().parents[2]
folder=Path(__file__).parent
git=['git','--git-dir=.scratch/git','--work-tree=.']
records=[]
def run(args):
 start=datetime.datetime.now(datetime.timezone.utc).isoformat();begin=time.monotonic()
 result=subprocess.run(args,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
 records.append({'command':args,'started_utc':start,'elapsed_seconds':round(time.monotonic()-begin,3),
                 'exit_code':result.returncode,'output':result.stdout})
 if result.returncode:
  print(result.stdout);write();raise SystemExit(result.returncode)
 return result.stdout

def write():
 target=root/'.scratch/astra-b71-apf4-delivery.json'
 target.write_bytes((json.dumps({'commands':records},indent=2)+'\n').encode())

summary=json.loads((folder/'suite_results.json').read_text())
assert not summary['failures']
assert (root/'ASTRA_LAST_MESSAGE.md').read_text().rstrip().endswith('ASTRA_DONE')
paths=json.loads((folder/'delivery_paths.json').read_text())
run(['python3','packaging/repin.py','--apply'])
run([*git,'add','-f','--',*paths])
run([*git,'diff','--cached','--check'])
run([*git,'commit','-m','APF: pin native situation-mask proofs, preserve empty categories and close release gates','--',*paths])
head=run([*git,'rev-parse','HEAD']).strip()
run([*git,'bundle','create','.scratch/astra-b71-apf4.bundle','astra/b71-apf4-situation-mask','^dc87cd0f'])
run([*git,'bundle','verify','.scratch/astra-b71-apf4.bundle'])
run([*git,'diff','--exit-code','HEAD','--',*paths])
run([*git,'log','--oneline','dc87cd0f..HEAD'])
run([*git,'status','--short'])
write()
target=root/'.scratch/astra-b71-apf4.bundle'
receipt=json.loads((root/'.scratch/astra-b71-apf4-delivery.json').read_text())
receipt.update(head=head,base='dc87cd0f',branch='astra/b71-apf4-situation-mask',
               bundle=str(target.relative_to(root)),bundle_bytes=target.stat().st_size,
               bundle_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
               suite_files=summary['passed'],tests=summary['tests'],optional_skips=summary['optional_skips'],
               no_push=True,no_emulator=True)
(root/'.scratch/astra-b71-apf4-delivery.json').write_bytes((json.dumps(receipt,indent=2)+'\n').encode())
print(json.dumps({k:v for k,v in receipt.items() if k!='commands'},indent=2))

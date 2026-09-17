"""Seal only explicit reviewed paths in the private git directory, then bundle."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

root=Path(__file__).resolve().parents[2]
base='02bbadd184e85498a441d3be71e70f8de94b9b0a'
branch='refs/heads/astra/b71-apf7-overlay-books'
git=['git','--git-dir=.scratch/git']
receipt=root/'.scratch/astra-b71-apf7-delivery.json'
records=[]
invocation_started=datetime.datetime.now(datetime.timezone.utc).isoformat()
invocation_begin=time.monotonic()

def run(args):
    started=datetime.datetime.now(datetime.timezone.utc).isoformat()
    begin=time.monotonic()
    result=subprocess.run(args,cwd=root,capture_output=True,text=True)
    records.append({'command':args,'started_utc':started,
        'elapsed_seconds':round(time.monotonic()-begin,3),'exit_code':result.returncode,
        'stdout':result.stdout,'stderr':result.stderr})
    receipt.write_text(json.dumps({'base':base,'branch':branch,'commands':records},indent=2)+'\n')
    print(result.stdout,result.stderr,flush=True)
    if result.returncode: raise SystemExit(result.returncode)
    return result.stdout.strip()

assert json.loads((root/'reports/b71_apf7/suite_results.json').read_text())['passed_files']==199
paths=['ASTRA_REPORT.md','ASTRA_LAST_MESSAGE.md']
paths += [p.relative_to(root).as_posix() for p in sorted((root/'reports/b71_apf7').iterdir())
          if p.is_file()]
manifest=root/'reports/b71_apf7/delivery_paths.json'
if manifest.relative_to(root).as_posix() not in paths:
    paths.append(manifest.relative_to(root).as_posix())
manifest.write_text(json.dumps(paths,indent=2)+'\n')
run(git+['diff','--check'])
run(git+['add','-f','--',*paths])
run(['python3','packaging/repin.py','--apply'])
run(git+['commit','-m','Record APF-7 hotfix proofs, screenshots and validation','--',*paths])
head=run(git+['rev-parse','HEAD'])
bundle='.scratch/astra-b71-apf7.bundle'
run(git+['bundle','create',bundle,branch,'^'+base])
run(git+['bundle','verify',bundle])
run(git+['bundle','list-heads',bundle])
changes=run(git+['diff','--name-status',base,head])
data={'base':base,'branch':branch,'head':head,'bundle':bundle,
      'bundle_sha256':hashlib.sha256((root/bundle).read_bytes()).hexdigest(),
      'bundle_bytes':(root/bundle).stat().st_size,'commands':records,'changes':changes,
      'invocation':{'command':[sys.executable,str(Path(__file__).relative_to(root))],
          'started_utc':invocation_started,'elapsed_seconds':round(time.monotonic()-invocation_begin,3),'exit_code':0}}
receipt.write_text(json.dumps(data,indent=2)+'\n')
print(json.dumps({k:v for k,v in data.items() if k not in ('commands','changes')},indent=2))

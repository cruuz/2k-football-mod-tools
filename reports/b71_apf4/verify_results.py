"""Aggregate the latest complete standalone run of every acceptance suite."""
from pathlib import Path
import json,re,sys
root=Path(__file__).resolve().parents[2]
folder=Path(__file__).parent
records=[json.loads(line) for line in (folder/'commands.jsonl').read_text().splitlines()]
files=sorted((root/'tests/mod_editor').glob('test_apf*.py'))
files += [root/'tests/mod_editor'/name for name in ('test_b69_a1_playcalling.py','test_provider_integrity.py','test_product_catalog.py','test_phase1_packaging.py','test_capability_registry_module_commands.py')]
results=[]
for path in files:
 relative=path.relative_to(root).as_posix()
 matching=[r for r in records if r['command'] and r['command'][-1]==relative]
 if not matching:
  results.append({'suite':relative,'missing':True});continue
 record=matching[-1]
 output=(root/record['log']).read_text()
 counts=re.findall(r'Ran (\d+) tests?',output)
 skips=re.findall(r'OK \(skipped=(\d+)\)',output)
 results.append({'suite':relative,**record,'tests':int(counts[-1]) if counts else 0,'skips':int(skips[-1]) if skips else 0})
summary={'suite_files':len(results),'passed':sum(r.get('exit_code')==0 for r in results),
         'tests':sum(r.get('tests',0) for r in results),'optional_skips':sum(r.get('skips',0) for r in results),
         'failures':[r['suite'] for r in results if r.get('exit_code')!=0],'results':results}
(folder/'suite_results.json').write_bytes((json.dumps(summary,indent=2)+'\n').encode())
print(json.dumps({k:v for k,v in summary.items() if k!='results'},indent=2))
sys.exit(bool(summary['failures']))

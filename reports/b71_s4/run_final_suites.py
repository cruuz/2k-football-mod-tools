"""Run every standalone scorebug suite on frozen source, two independent processes at a time."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
paths=sorted((ROOT/'tests/mod_editor').glob('test_*scorebug*.py'))
paths += [ROOT/'tests/nfl2k5_scorebug_layout_test.py',ROOT/'tests/nfl2k5_scorebug_mod_project_test.py']
paths += [ROOT/'tests/mod_editor'/('test_'+n+'.py') for n in ('provider_integrity','product_catalog','phase1_packaging')]
def snapshot():
 return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths+list((ROOT/'mod_editor/core').glob('*scorebug*.py'))+list((ROOT/'tools').glob('*scorebug*.py'))}
def run(path):
 r=subprocess.run([sys.executable,'reports/b71_s4/run_logged.py',path.stem+'-release',sys.executable,str(path)],cwd=ROOT)
 return (str(path.relative_to(ROOT)),r.returncode)
before=snapshot()
with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,paths))
r=subprocess.run([sys.executable,'reports/b71_s4/run_logged.py','registry-strict-release',sys.executable,'-m','mod_editor.capabilities.validate_registry'],cwd=ROOT)
failed=[name for name,code in results if code]
if r.returncode:failed.append('registry-strict')
after=snapshot()
if before!=after:failed.append('source drift during final suites')
(ROOT/'reports/b71_s4/final-suite-summary.json').write_text(json.dumps(dict(results=results,failed=failed,source_sha256=after,sources_frozen=before==after),indent=2)+'\n')
print('FAILED:',failed,flush=True)
raise SystemExit(bool(failed))

"""Run each integration suite standalone and retain its complete timed output."""
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import json,sys
from run import ROOT,REPORT,run
kind=sys.argv[1]
tests=ROOT/'tests/mod_editor'
if kind=='apf':
 files=sorted(tests.glob('test_apf*.py'))
 files += [tests/'test_b69_a1_playcalling.py']
 workers=4
elif kind=='presentation':
 files=sorted(set(tests.glob('test_*scorebug*.py'))|set(tests.glob('test_*colour*.py'))|set(tests.glob('test_*color*.py')))
 files += [tests/n for n in ('test_nfl2k5_modern_arrowhead.py','test_b71_a6_composition.py','test_build_panel_qt.py','test_mod_build.py','test_discord_bugs_1.py')]
 workers=3
elif kind=='gates':
 files=[tests/n for n in ('test_nfl2k5_cave_oracle.py','test_nfl2k5_allocator_scaleout.py','test_xbe_patch_memory_writes.py','test_xbe_patch_cave_references.py','test_nfl2k5_owner_pairwise_composition.py')]
 workers=3
else:
 files=sorted(tests.glob('test_*manifest.py'))+[tests/n for n in ('test_provider_integrity.py','test_providers.py','test_product_catalog.py','test_phase1_packaging.py','test_b68_a1_audit.py','test_capability_registry_module_commands.py')]
 workers=2
REPORT.joinpath(kind+'-suite-paths.json').write_text(json.dumps([str(f.relative_to(ROOT)) for f in files],indent=2)+'\n')
results=[]
with ThreadPoolExecutor(max_workers=workers) as pool:
 futures={pool.submit(run,'final-'+p.stem,[str(ROOT/'.scratch/test-python/bin/python3') if p.name=='test_apf_studio_installer.py' else 'python3',str(p.relative_to(ROOT))]):p for p in files}
 for future in as_completed(futures):
  p=futures[future];code=future.result();results.append(dict(path=str(p.relative_to(ROOT)),exit_code=code))
  print(('PASS' if code==0 else 'FAIL')+' '+p.name,flush=True)
REPORT.joinpath(kind+'-results.json').write_text(json.dumps(results,indent=2)+'\n')
sys.exit(any(r['exit_code'] for r in results))

"""Final frozen-atlas tests and the affected owner's composition matrix."""
from pathlib import Path
import json,os,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent/'logs'
jobs=[
 ['tests/mod_editor/test_nfl2k5_scorebug_sprite.py'],
 ['tests/mod_editor/test_nfl2k5_scorebug_sd.py'],
 ['tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py','-k','scorebug_runtime'],
 ['reports/b72_s1/observe_gate_manifest.py'],
 ['reports/b72_s1/normalize_gate_manifest.py'],
 ['tests/mod_editor/test_nfl2k5_cave_oracle.py'],
 ['tools/scorebug_sprite/build_runtime.py','--check'],
 ['tests/mod_editor/test_mod_build.py'],
]
env=dict(os.environ,PYTHONPATH=str(ROOT),QT_QPA_PLATFORM='offscreen');rows=[]
previous=json.loads((OUT/'final_checks.json').read_text()) if '--resume' in sys.argv else []
for args in jobs:
 prior=next((r for r in previous if r['command']==['python3',*args]),None)
 if prior and prior['exit_code']==0:
  rows.append(prior);continue
 start=time.monotonic();log_path=OUT/('final_'+Path(args[0]).stem+'.log')
 if prior and log_path.exists():
  archive=log_path.with_name('previous_'+log_path.name);suffix=2
  while archive.exists():
   archive=log_path.with_name('previous'+str(suffix)+'_'+log_path.name);suffix+=1
  archive.write_bytes(log_path.read_bytes())
 with log_path.open('w') as log:
  run_env=dict(env)
  if args[0].endswith('test_nfl2k5_cave_oracle.py'):
   run_env['NFL2K5_CAVE_MANIFEST']=str(ROOT/'.scratch/b72-s1-gate-manifest.json')
  result=subprocess.run([sys.executable,*args],cwd=ROOT,env=run_env,stdout=log,stderr=subprocess.STDOUT)
 row=dict(command=['python3',*args],exit_code=result.returncode,seconds=round(time.monotonic()-start,2),log=log_path.name)
 rows.append(row);print(row,flush=True)
 (OUT/'final_checks.json').write_text(json.dumps(rows,indent=2)+'\n',newline='\n')
raise SystemExit(int(any(row['exit_code'] for row in rows)))

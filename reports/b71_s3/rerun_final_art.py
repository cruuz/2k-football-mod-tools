"""Repeat suites whose first run preceded the final capsule art and pins."""
from pathlib import Path
import subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
failed=[]
for name in ('assets','author','exact','fonts','freeze','freeze_v2'):
 program='test_nfl2k5_scorebug_'+name
 r=subprocess.run([sys.executable,'reports/b71_s3/run_logged.py',program+'-final',sys.executable,'tests/mod_editor/'+program+'.py'],cwd=ROOT)
 if r.returncode:failed.append(program)
print('FAILED:',failed,flush=True)
raise SystemExit(bool(failed))

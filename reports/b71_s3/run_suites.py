"""Standalone scorebug suites plus provider/catalog/packaging/registry checks."""
from pathlib import Path
import subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
paths=sorted((ROOT/'tests/mod_editor').glob('test_*scorebug*.py'))
paths += [ROOT/'tests/nfl2k5_scorebug_layout_test.py',ROOT/'tests/nfl2k5_scorebug_mod_project_test.py']
paths += [ROOT/'tests/mod_editor'/('test_'+name+'.py') for name in ('provider_integrity','product_catalog','phase1_packaging')]
failed=[]
for path in paths:
 result=subprocess.run([sys.executable,str(ROOT/'reports/b71_s3/run_logged.py'),path.stem,sys.executable,str(path)],cwd=ROOT)
 if result.returncode:failed.append(path.name)
result=subprocess.run([sys.executable,str(ROOT/'reports/b71_s3/run_logged.py'),'registry-strict',sys.executable,'-m','mod_editor.capabilities.validate_registry'],cwd=ROOT)
if result.returncode:failed.append('registry-strict')
print('FAILED:',failed,flush=True)
raise SystemExit(bool(failed))

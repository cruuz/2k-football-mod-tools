from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys

root=Path.cwd()
patterns=('test_studio*.py','test_apf_studio*.py','test_beta69_studios_offscreen.py',
          'test_phase1_packaging.py','test_stage_release.py','test_local_windows_ci.py',
          'test_self_update.py','test_self_update_manual_layout.py',
          'test_provider_integrity.py','test_providers.py','test_product_catalog.py',
          'test_nfl2k5_scorebug_assets.py','test_nfl2k5_scorebug_exact.py',
          'test_nfl2k5_scorebug_ingame*.py','test_nfl2k5_scorebug_sprite*.py',
          'test_nfl2k5_scorebug_mnf*.py','test_nfl2k5_scorebug_fonts.py',
          'test_scorebug_studio_panel_qt.py','test_mod_build*.py','test_numpy_optional.py',
          'test_nfl2k5_scorebug_template_release.py')
tests=sorted({p for pattern in patterns for p in (root/'tests/mod_editor').glob(pattern)})
def run(path):
    cmd=[sys.executable,'.scratch/run.py','suite-'+path.stem,sys.executable,str(path)]
    result=subprocess.run(cmd,timeout=1500)
    print(path.name,result.returncode,flush=True)
    return result.returncode
with ThreadPoolExecutor(max_workers=3) as pool:
    results=list(pool.map(run,tests))
result=subprocess.run([sys.executable,'.scratch/run.py','strict-registry',sys.executable,'mod_editor/capabilities/validate_registry.py'])
results.append(result.returncode)
print('SUITE_FILES',len(tests),'FAILURES',sum(bool(code) for code in results),flush=True)
sys.exit(bool(any(results)))

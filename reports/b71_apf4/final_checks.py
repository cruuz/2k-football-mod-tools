"""Refresh changed subjects and explicit integration gates after the full sweep."""
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import subprocess,sys
root=Path(__file__).resolve().parents[2]
files=['test_apf_playcalling_editor_qt.py','test_apf_playcalling_editor_facade.py',
       'test_apf_b71_situation_mask.py','test_apf_b71_situation_mask_abi.py','test_apf_b71_situation_mask_qt.py',
       'test_apf_b71_situation_mask_install.py','test_apf_b67_xenia_patch.py','test_apf_b69_launch_patches.py',
       'test_apf_playcalling_editor_patches.py','test_apf_playcall_patch.py',
       'test_provider_integrity.py','test_product_catalog.py','test_phase1_packaging.py','test_capability_registry_module_commands.py']
def run(name):
 return name,subprocess.run([sys.executable,str(root/'reports/b71_apf4/run.py'),'final-'+Path(name).stem,
                            sys.executable,'tests/mod_editor/'+name],cwd=root,capture_output=True,text=True)
failed=[]
with ThreadPoolExecutor(max_workers=3) as pool:
 for future in as_completed([pool.submit(run,name) for name in files]):
  name,result=future.result();print(name,result.returncode,flush=True)
  if result.returncode:failed.append(name);print(result.stdout,flush=True)
print('Failures:',failed,flush=True)
sys.exit(bool(failed))

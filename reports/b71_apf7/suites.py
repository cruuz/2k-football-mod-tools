"""Every requested suite runs standalone, offscreen, in a detached coordinator."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import subprocess
import sys
root = Path(__file__).resolve().parents[2]
files = sorted((root / 'tests/mod_editor').glob('test_apf*.py'))
files += [root / 'tests/mod_editor' / name for name in (
 'test_b69_a1_playcalling.py', 'test_provider_integrity.py', 'test_product_catalog.py',
 'test_phase1_packaging.py', 'test_capability_registry_module_commands.py',
 'test_studio_qt_models.py', 'test_studio_shell_layout_qt.py')]
Path(__file__).with_name('suite_paths.txt').write_text('\n'.join(str(p.relative_to(root)) for p in files)+'\n')
def run(path):
 command=[sys.executable, str(path.relative_to(root))]
 if path.name=='test_apf_studio_installer.py': command=['env','-u','PYTHONPATH',*command]
 result=subprocess.run([sys.executable,str(Path(__file__).with_name('run.py')),path.stem,*command],
                       cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
 return path.name,result.returncode,result.stdout
failed=[]
with ThreadPoolExecutor(max_workers=4) as pool:
 for task in as_completed([pool.submit(run,path) for path in files]):
  name,code,output=task.result()
  print(f'{"PASS" if code==0 else "FAIL"} {name} exit={code}',flush=True)
  if code: failed.append(name); print(output[-4000:],flush=True)
print(f'Completed {len(files)} standalone suites; failures: {failed}',flush=True)
sys.exit(bool(failed))

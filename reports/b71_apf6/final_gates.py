"""Rebuild a clean public stage after the final UI and action-binding changes."""
from pathlib import Path
import shutil
import subprocess
root=Path(__file__).resolve().parents[2]
stage=root/'.scratch/apf-release'
assert stage.resolve().parent==(root/'.scratch').resolve() and not stage.is_symlink()
if stage.exists(): shutil.rmtree(stage)
commands=[
 ('repin-final',['python3','packaging/repin.py','--apply']),
 ('strict-registry-final',['python3','-m','mod_editor.capabilities.validate_registry']),
 ('delivery-audit',['python3','reports/b71_apf6/audit_delivery.py']),
 ('release-stage-final',['python3','packaging/stage_release.py','packaging/apf2k8-release-allowlist.txt','.scratch/apf-release']),
 ('release-check-final',['env','PYTHONDONTWRITEBYTECODE=1','python3','packaging/check_apf2k8_mod_studio_release.py','.scratch/apf-release']),
 ('release-runtime-final',['env','PYTHONDONTWRITEBYTECODE=1','PYTHONNOUSERSITE=1','PYTHONPATH='+str(stage),'.scratch/test-python/bin/python3','.scratch/apf-release/packaging/check_apf2k8_mod_studio_runtime.py'])]
for label,command in commands:
 result=subprocess.run(['python3','reports/b71_apf6/run.py',label,*command],cwd=root)
 if result.returncode: raise SystemExit(result.returncode)

from pathlib import Path
import os
import importlib.util
import subprocess
import sys
import venv

base=Path('/tmp/astra-b711-p1-removed')
venv.EnvBuilder(with_pip=False,system_site_packages=False,clear=True).create(base)
site=next((base/'lib').glob('python*/site-packages'))
for name in ('PyQt5','PIL','capstone','unicorn'):
    source=Path(importlib.util.find_spec(name).origin).parent
    (site/name).symlink_to(source,target_is_directory=True)
python=base/'bin/python3'
assert subprocess.check_output([str(python),'-I','-c','import importlib.util; print(importlib.util.find_spec("numpy"))'],text=True).strip()=='None'
for product in ('2k5','apf2k8'):
    stage=Path('/tmp/astra-b711-p1-stages')/product
    command=[str(python),'-I','-B',str(stage/('packaging/check_'+product+'_mod_studio_runtime.py'))]
    result=subprocess.run(command,env=dict(os.environ,QT_QPA_PLATFORM='offscreen'),capture_output=True,text=True)
    print('COMMAND',command,'EXIT',result.returncode,flush=True)
    print(result.stdout+result.stderr,flush=True)
    assert result.returncode==1 and 'Staged runtime is missing third-party dependencies: ' in result.stderr and 'numpy' in result.stderr
print('BOTH_RELEASE_RUNTIME_GATES_REJECT_MISSING_NUMPY')

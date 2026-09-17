from pathlib import Path
import importlib.util
import json
import os
import shutil
import subprocess
import sys

root=Path.cwd()
base=Path('/tmp/astra-b711-p1-runtime')
exe=Path('/tmp/claude-1000/-home-noah-Desktop-2K5-8-Editors/7d06c350-f66f-4c4d-acf4-cdbdbedff1da/scratchpad/b71/ship/assets71/2K5-Mod-Studio-1.0.0rc96-Setup.exe')
payload=base/'published'
subprocess.run(['7z','x','-y',str(exe),'runtime/*','-o'+str(payload)],check=True,stdout=subprocess.DEVNULL)
runtime=payload/'runtime'
site=runtime/'Lib/site-packages'
def inventory(label):
    from importlib.metadata import distributions
    print(label, sorted((d.metadata['Name'],d.version) for d in distributions(path=[str(site)])),flush=True)
inventory('PUBLISHED PACKAGES')
# Rebuild the runtime's dependencies using the production installer function.
# Interpreter bytes come from the sidecar-verified published installer; the
# original python.org ZIP is no longer cached, so that fetch is UNWITNESSED.
spec=importlib.util.spec_from_file_location('winbuild',root/'packaging/windows/build_windows_installer.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
shutil.rmtree(site);site.mkdir(parents=True)
os.environ.update(PIP_NO_INDEX='1',PIP_FIND_LINKS=str(base/'dl'),PIP_DISABLE_PIP_VERSION_CHECK='1')
builder.install_wheels(site,base/'dl')
inventory('REASSEMBLED PACKAGES')
sys.path.insert(0,str(root/'packaging'))
from runtime_dependencies import check_runtime_dependencies
for product in ('2k5','apf2k8'):
    stage=Path('/tmp/astra-b711-p1-stages')/product
    result=check_runtime_dependencies(stage,runtime)
    print('WINDOWS CLOSURE',product,sorted(result['imports']),flush=True)
    (root/'reports/b711_p1'/('windows-'+product+'-closure.json')).write_text(json.dumps(result,indent=2)+'\n')
missing=site/'numpy'
hidden=site/'numpy.removed'
missing.rename(hidden)
try:
    for product in ('2k5','apf2k8'):
        try:check_runtime_dependencies(Path('/tmp/astra-b711-p1-stages')/product,runtime)
        except RuntimeError as exc:
            assert 'numpy' in str(exc)
            print('REMOVED NUMPY REJECTED',product,str(exc),flush=True)
        else:raise AssertionError('missing numpy passed')
finally:hidden.rename(missing)

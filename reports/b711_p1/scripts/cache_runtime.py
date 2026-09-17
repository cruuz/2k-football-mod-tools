from pathlib import Path
import hashlib
import importlib.util
import os
import shutil
import tempfile
import zipfile

spec=importlib.util.spec_from_file_location('installer',Path('packaging/windows/build_windows_installer.py'))
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
dest=Path('/tmp/astra-b711-p1-runtime/dl');dest.mkdir(parents=True,exist_ok=True)
wanted={value:name for name,value in mod.WHEEL_SHA256.items()}
wanted[mod.PYTHON_EMBED_SHA256]='python-embed.zip'
for base in (Path('/home/noah/.cache/pip'),Path('/tmp')):
    for folder, dirs, files in os.walk(base):
        dirs[:]=[d for d in dirs if d not in ('node_modules','.git','proc','astra-b711-p1-runtime')]
        for name in files:
            path=Path(folder)/name
            if not (name.endswith(('.body','.zip','.whl'))): continue
            try:
                if path.is_symlink() or not path.is_file():continue
                with path.open('rb') as f:
                    if f.read(4)!=b'PK\x03\x04':continue
                    f.seek(0);digest=hashlib.file_digest(f,'sha256').hexdigest()
                if digest in wanted:
                    target=dest/wanted[digest]
                    shutil.copyfile(path,target)
                    print('verified cached input',target.name,str(path),flush=True)
            except (OSError,ValueError):continue
print('missing', sorted(set(wanted.values())-{p.name for p in dest.iterdir()}),flush=True)
# Invoke the production build function with networking disabled. Fail honestly
# if the exact interpreter input has been deleted after the release build.
os.environ.update(PIP_NO_INDEX='1',PIP_FIND_LINKS=str(dest),PIP_DISABLE_PIP_VERSION_CHECK='1')
original_fetch=mod.fetch
def cached_fetch(url,path,expected=None):
    if not path.is_file(): raise RuntimeError('Offline runtime build lacks the pinned input: '+path.name)
    return original_fetch(url,path,expected)
mod.fetch=cached_fetch
runtime=mod.build_runtime(dest.parent,dest)
print('BUILT',runtime)
for path in sorted((runtime/'Lib/site-packages').glob('*.dist-info/METADATA')):
    print('\n'.join(line for line in path.read_text().splitlines() if line.startswith(('Name:','Version:'))))

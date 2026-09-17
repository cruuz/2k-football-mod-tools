from pathlib import Path
import importlib.abc
import sys
import time

root=Path.cwd()
sys.path[:0]=[str(root),str(root/'tools')]
class NoNumpy(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0]=='numpy':
            raise ModuleNotFoundError("No module named 'numpy'",name='numpy')
sys.meta_path.insert(0,NoNumpy())
from mod_editor.core import mod_build
source=Path('/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso')
before=source.stat()
result=mod_build.inspect(source)
after=source.stat()
assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
assert 'numpy' not in sys.modules
print('OPTIONS_READ',len(result),'container',result['container'],'scorebug',result['scorebug_runtime_resources'])

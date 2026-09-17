from pathlib import Path
import importlib.abc
import sys
import traceback

root = Path.cwd()
sys.path[:0] = [str(root), str(root/'tools'), str(root/'tests')]
class NoNumpy(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] == 'numpy':
            raise ModuleNotFoundError("No module named 'numpy'", name='numpy')
sys.meta_path.insert(0, NoNumpy())
from mod_editor.core import mod_build
source = Path('/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso')
try:
    mod_build.inspect(source)
except ModuleNotFoundError:
    traceback.print_exc()
else:
    raise AssertionError('Expected baseline reproduction')

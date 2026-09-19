"""Run the 24-item refit fixture with all changed owners restored from rc97."""
import importlib.abc
import importlib.util
import os
from pathlib import Path
import runpy
import subprocess
import sys
ROOT = Path(os.environ.get('B72_ROOT', Path.cwd())).resolve()
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(ROOT / 'tests/mod_editor')]
OWNERS = {
    'mod_editor.core.equipment_staging': 'mod_editor/core/equipment_staging.py',
    'mod_editor.core.nfl2k5_project_fit': 'mod_editor/core/nfl2k5_project_fit.py',
    'mod_editor.core.nfl2k5_uniform_equipment_writer': 'mod_editor/core/nfl2k5_uniform_equipment_writer.py',
    'mod_editor.core.equipment_palette': 'mod_editor/core/equipment_palette.py',
    'mod_editor.core.nfl2k5_equipment_lz': 'mod_editor/core/nfl2k5_equipment_lz.py',
    'nfl_txtr': 'tools/nfl_txtr.py',
    'tools.nfl_txtr': 'tools/nfl_txtr.py',
    'nfl_vc_lz_fill': 'tools/nfl_vc_lz_fill.py',
}
class Historical(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in OWNERS:
            return importlib.util.spec_from_loader(fullname, self)
    def create_module(self, spec):
        return None
    def exec_module(self, module):
        relative = OWNERS[module.__name__]
        module.__file__ = str(ROOT / relative)
        source = subprocess.run(['git', 'show', '088e3f41:' + relative], cwd=ROOT,
                                capture_output=True, check=True).stdout
        exec(compile(source, '088e3f41:' + relative, 'exec'), module.__dict__)
sys.meta_path.insert(0, Historical())
if __name__ == '__main__':
    runpy.run_path(str(ROOT / 'tools/bench/b72/b72_refit_bench.py'), run_name='__main__')

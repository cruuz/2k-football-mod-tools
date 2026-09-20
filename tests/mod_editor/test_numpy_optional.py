"""Both studios and options work in a real Python environment without NumPy."""
from pathlib import Path
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import venv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


class MissingNumpyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='studio-without-numpy-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.runtime = Path(cls.temp.name)/'runtime'
        venv.EnvBuilder(with_pip=False).create(cls.runtime)
        cls.python = cls.runtime/('Scripts/python.exe' if os.name == 'nt' else 'bin/python3')
        cls.site = Path(subprocess.check_output([str(cls.python), '-c', 'import sysconfig; print(sysconfig.get_path("purelib"))'], text=True).strip())
        # Copy only the two GUI dependencies. No NumPy, user site or PYTHONPATH
        # inheritance can satisfy imports in the isolated child or its workers.
        for name in ('PyQt5', 'PIL'):
            spec = importlib.util.find_spec(name)
            if spec is None:
                raise unittest.SkipTest(f'{name} is needed for the offscreen studio regression')
            shutil.copytree(Path(spec.origin).parent, cls.site/name,
                            ignore=shutil.ignore_patterns('__pycache__'))
            # Binary Pillow wheels can keep their JPEG/PNG libraries beside
            # PIL. Preserve those without introducing NumPy into the fixture.
            if name == 'PIL':
                libraries = Path(spec.origin).parent.parent/'pillow.libs'
                if libraries.is_dir():
                    shutil.copytree(libraries, cls.site/libraries.name)

    def child(self, code, timeout=120):
        bootstrap = f'import sys; sys.path[:0] = {[str(ROOT), str(ROOT/"tools"), str(ROOT/"tests"), str(ROOT/"tests/mod_editor")]!r}; '
        result = subprocess.run([str(self.python), '-I', '-B', '-c', bootstrap + code],
                                env=dict(os.environ, QT_QPA_PLATFORM='offscreen', MOD_STUDIO_NO_UPDATE_CHECK='1'),
                                capture_output=True, text=True, timeout=timeout)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_both_studios_open_all_pages_without_numpy(self):
        self.child('import importlib.util; assert importlib.util.find_spec("numpy") is None; '
                   'from test_beta69_studios_offscreen import replay; replay(); '
                   'assert "numpy" not in sys.modules')

    def test_read_options_in_real_child_without_numpy(self):
        self.child('''
import importlib.util, tempfile
from pathlib import Path
from nfl2k5_throw_tuning_test import _build_synthetic_xbe
from mod_editor.core.studio_inspection import inspect_source
from mod_editor.core.nfl2k5_scorebug_sprite import probe_sizes
assert importlib.util.find_spec('numpy') is None
assert probe_sizes() == (34, 325216, 325632)
with tempfile.TemporaryDirectory() as folder:
    source = Path(folder)/'fixture.xbe'
    source.write_bytes(_build_synthetic_xbe())
    result = inspect_source(source)
    assert result['container'] == 'xbe', result
assert 'numpy' not in sys.modules
''')

    def test_sprite_build_names_package_and_install_command(self):
        self.child('''
from mod_editor.core.nfl2k5_scorebug_sprite import compile_folder
from mod_editor.core.runtime_dependencies import MissingDependency
try:
    compile_folder()
except MissingDependency as exc:
    assert 'needs the numpy package' in str(exc), str(exc)
    assert '-m pip install numpy==1.26.4' in str(exc), str(exc)
    assert sys.executable in str(exc), str(exc)
else:
    raise AssertionError('Sprite build should need numpy')
''')

    def test_colour_blend_does_not_need_numpy(self):
        self.child('from mod_editor.core.nfl2k5_modern_color import blend_bytes; '
                   'assert blend_bytes(bytes([0,100]), bytes([100,200]), .5) == bytes([50,150]); '
                   'assert "numpy" not in sys.modules')

    def test_selected_build_option_reports_numpy_before_output_is_created(self):
        self.child('''
from pathlib import Path
import tempfile
from mod_editor.core.mod_build import BuildPlan, preflight_plan
from mod_editor.core.runtime_dependencies import MissingDependency
with tempfile.TemporaryDirectory() as folder:
    target = Path(folder)/'output.iso'
    try:
        preflight_plan(BuildPlan(source='unused-source.iso', target=str(target), scorebug_runtime=True))
    except MissingDependency as exc:
        assert 'Scorebug build needs the numpy package' in str(exc), str(exc)
        assert '-m pip install numpy==1.26.4' in str(exc), str(exc)
    else:
        raise AssertionError('Missing build dependency should be reported')
    assert not target.exists()
''')

    def test_broken_numpy_install_is_not_misreported_as_absent(self):
        from unittest.mock import patch
        from mod_editor.core.runtime_dependencies import require_numpy
        with patch('importlib.import_module', side_effect=ModuleNotFoundError('missing native dependency', name='numpy.core')):
            with self.assertRaises(ModuleNotFoundError):
                require_numpy('Sprite')

    def test_modified_scorebug_verification_does_not_abort_option_inspection(self):
        self.child('''
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
from mod_editor.core import nfl2k5_scorebug_ingame as scene
from mod_editor.core import nfl2k5_scorebug_resources as art
from mod_editor.core import nfl2k5_scorebug_runtime as runtime
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import platform_compat as io
from mod_editor.core.runtime_dependencies import MissingDependency, numpy_install_message
with tempfile.TemporaryDirectory() as folder:
    source = Path(folder)/'fixture.iso'
    source.write_bytes(b'bounded status fixture')
    entries = {'vc_53450030/0': SimpleNamespace(size=scene.PACK_SIZE, byte_offset=0),
               'default.xbe': SimpleNamespace(size=space.special.RETAIL_FILE_SIZE, byte_offset=0)}
    with patch.object(scene.layout.xc, 'parse_xdvdfs', return_value=(entries, None)), patch.object(io, 'pread', return_value=b''), patch.object(runtime, 'status', return_value='applied'), patch.object(art, 'runtime_pack_status', side_effect=MissingDependency(numpy_install_message('Scorebug texture conversion'))):
        result = scene.runtime_image_status(source)
    assert 'needs the numpy package' in result, result
    assert '-m pip install numpy==1.26.4' in result, result
''')


if __name__ == '__main__':
    unittest.main()

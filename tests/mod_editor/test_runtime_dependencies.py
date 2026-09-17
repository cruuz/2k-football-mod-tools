"""Release dependency closure covers lazy callbacks and the target runtime."""
from pathlib import Path
import importlib.util
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('dependency_audit', ROOT/'packaging/runtime_dependencies.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class ClosureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'mod_editor').mkdir()
        (self.root/'mod_editor/feature.py').write_text(
            'from pathlib import Path\n'
            'def callback():\n    import missing_demo.submodule\n'
            'LAZY_RUNTIME_IMPORTS = ("dynamic_demo",)\n')
        self.runtime = self.root/'runtime'
        self.site = self.runtime/'Lib/site-packages'
        self.site.mkdir(parents=True)
        (self.runtime/'python.exe').write_bytes(b'fixture')
        (self.runtime/'python312._pth').write_text('Lib\\site-packages\n')

    def test_static_scan_finds_nested_and_marked_lazy_imports(self):
        self.assertEqual(set(audit.third_party_imports(self.root)), {'missing_demo.submodule', 'dynamic_demo'})

    def test_target_runtime_removal_fails_even_when_build_host_has_package(self):
        (self.root/'mod_editor/feature.py').write_text('def callback():\n    import PIL\n')
        package = self.site/'PIL'
        package.mkdir()
        (package/'__init__.py').write_text('# fixture\n')
        self.assertIn('PIL', audit.check_runtime_dependencies(self.root, self.runtime)['origins'])
        (package/'__init__.py').unlink()
        # Pillow is installed on the host; it must never fill a target hole.
        import PIL
        self.assertIsNotNone(PIL)
        with self.assertRaisesRegex(RuntimeError, 'PIL.*mod_editor/feature.py:2'):
            audit.check_runtime_dependencies(self.root, self.runtime)

    def test_current_interpreter_closure_rejects_lazy_missing_dependency(self):
        with self.assertRaisesRegex(RuntimeError, 'dynamic_demo'):
            audit.check_runtime_dependencies(self.root)

    def test_literal_dynamic_import_is_scanned(self):
        (self.root/'mod_editor/feature.py').write_text(
            'import importlib\ndef run():\n    return importlib.import_module("another_missing_package")\n')
        self.assertEqual(set(audit.third_party_imports(self.root)), {'another_missing_package'})

    def test_windows_numpy_shim_without_native_libraries_is_rejected(self):
        (self.root/'mod_editor/feature.py').write_text('import numpy\n')
        (self.site/'numpy').mkdir()
        (self.site/'numpy/__init__.py').write_text('# shim without binary\n')
        with self.assertRaisesRegex(RuntimeError, 'numpy'):
            audit.check_runtime_dependencies(self.root, self.runtime)

    def test_windows_and_portable_numpy_pins_match_ci(self):
        spec = importlib.util.spec_from_file_location('win_builder', ROOT/'packaging/windows/build_windows_installer.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        self.assertIn('numpy==1.26.4', builder.WHEELS)
        self.assertEqual(builder.WHEEL_SHA256['numpy-1.26.4-cp312-cp312-win_amd64.whl'],
                         '08beddf13648eb95f8d867350f6a018a4be2e5ad54c8d8caed89ebca558b2818')
        self.assertIn('numpy==1.26.4', (ROOT/'packaging/requirements-studio.txt').read_text().splitlines())
        self.assertIn('numpy==1.26.4', (ROOT/'.github/workflows/ci.yml').read_text())


if __name__ == '__main__':
    unittest.main()

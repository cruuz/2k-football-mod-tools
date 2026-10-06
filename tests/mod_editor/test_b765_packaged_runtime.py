"""Finished artifact imports and source recognition regressions for beta 76.5."""
from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('artifact_gate', ROOT / 'packaging/check_packaged_runtime.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class ArtifactRuntimeTests(unittest.TestCase):
    def test_new_requirements_cannot_silently_escape_the_import_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'packaging').mkdir()
            requirements = root / 'packaging/requirements-studio.txt'
            requirements.write_text('numpy==1.26.4\n')
            self.assertIn('numpy', gate.declared_imports(root))
            requirements.write_text('new_dependency_fixture==1.0\n')
            with self.assertRaisesRegex(RuntimeError, 'executable import probe'):
                gate.declared_imports(root)

    def test_archive_builder_api_runs_the_finished_artifact_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = root / 'stage'
            (stage / 'mod_editor').mkdir(parents=True)
            (stage / 'mod_editor/__init__.py').write_text('# archive fixture\n')
            (stage / 'packaging').mkdir()
            (stage / 'packaging/requirements-studio.txt').write_text('numpy==1.26.4\n')
            # No packaging directory in sys.path: match API callers which
            # load build_archive through spec_from_file_location.
            artifact = root / 'studio.tar.gz'
            code = '''import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location('archive_builder', sys.argv[1])
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
try:
    builder.build(Path(sys.argv[2]), 'studio', Path(sys.argv[3]), 1)
except RuntimeError as exc:
    # Lean developer Python may lack runtime packages. That refusal also
    # proves the real gate imported successfully through the API path.
    assert 'Packaged runtime import failed' in str(exc), str(exc)
print('finished artifact gate reached')
'''
            result = subprocess.run([sys.executable, '-I', '-B', '-c', code,
                                     str(ROOT / 'packaging/build_archive.py'), str(stage), str(artifact)],
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('finished artifact gate reached', result.stdout)
            self.assertTrue(artifact.is_file())

    def test_probe_imports_every_dependency_and_reports_a_broken_binary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bad = root / 'broken_native_fixture.py'
            bad.write_text("raise ImportError('native DLL could not be loaded')\n")
            # Use the selected interpreter, including its actual import logic.
            # A package directory existing on disk would pass the old scan.
            probe = "import sys; sys.path.insert(0, " + repr(str(root)) + ");\n" + gate.PROBE
            request = dict(imports=['json', 'broken_native_fixture', 'dependency_missing_fixture'],
                           app=str(root), runtime='', disc='', probe_disc='')
            result = subprocess.run([sys.executable, '-I', '-B', '-c', probe, json.dumps(request)],
                                    capture_output=True, text=True, check=False)
            receipt = json.loads(result.stdout.split('PACKAGED_RUNTIME_JSON=')[1])
            self.assertEqual(result.returncode, 1)
            self.assertIn('json', receipt['imports'])
            self.assertIn('native DLL', receipt['errors']['broken_native_fixture'])
            self.assertIn('ModuleNotFoundError', receipt['errors']['dependency_missing_fixture'])

    def test_packaged_runtime_cannot_borrow_a_dependency_from_the_host(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = dict(imports=['json'], app=str(root), runtime=str(root), disc='', probe_disc='')
            result = subprocess.run([sys.executable, '-I', '-B', '-c', gate.PROBE, json.dumps(request)],
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn('outside the packaged runtime', result.stdout)

    def test_finished_archive_traversal_and_links_are_refused(self):
        for name, link in (('../escape.py', False), ('app/link', True)):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                artifact = root / 'studio.tar.gz'
                with tarfile.open(artifact, 'w:gz') as archive:
                    member = tarfile.TarInfo(name)
                    if link:
                        member.type = tarfile.SYMTYPE
                        member.linkname = '/tmp'
                        archive.addfile(member)
                    else:
                        member.size = 1
                        archive.addfile(member, io.BytesIO(b'x'))
                with self.assertRaisesRegex(RuntimeError, 'Unsafe release archive'):
                    gate.unpack(artifact, root / 'unpacked')

    def test_launchers_check_numpy_and_recommend_the_complete_requirements(self):
        for relative in ('2K5-Mod-Studio.bat', 'APF-2K8-Mod-Studio.bat',
                         '2K5-Mod-Studio.command', 'APF-2K8-Mod-Studio.command',
                         'tools/launch_2k5_mod_studio.sh', 'tools/launch_apf2k8_mod_studio.sh'):
            text = (ROOT / relative).read_text()
            with self.subTest(launcher=relative):
                for name in ('numpy', 'capstone', 'unicorn'):
                    self.assertIn('import ' + name, text)
                self.assertIn('requirements-studio.txt', text)

    def test_installer_preserves_verified_capstone_version_diagnostic(self):
        spec = importlib.util.spec_from_file_location(
            'artifact_installer', ROOT / 'packaging/apf2k8_mod_studio_installer.py')
        installer = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = installer
        self.addCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(installer)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for package, child in (('PyQt5', 'QtWidgets'), ('PIL', 'Image')):
                (root / package).mkdir()
                (root / package / '__init__.py').write_text('# importable fixture\n')
                (root / package / (child + '.py')).write_text('# importable fixture\n')
            (root / 'unicorn.py').write_text('# importable fixture\n')
            for version, numpy_missing, expected_count in (
                    ('5.0.7', False, 0), ('5.0.6', False, 1),
                    ('5.0.6', True, 2), (None, False, 1)):
                with self.subTest(version=version, numpy_missing=numpy_missing):
                    # Real child interpreters import these fixtures, exercising
                    # both importability and the exact version assertion.
                    (root / 'capstone.py').write_text(
                        'raise ImportError("missing Capstone fixture")\n' if version is None
                        else '__version__ = ' + repr(version) + '\n')
                    (root / 'numpy.py').write_text(
                        'raise ImportError("missing NumPy fixture")\n' if numpy_missing
                        else '# importable fixture\n')
                    with mock.patch.dict(os.environ, {'PYTHONPATH': str(root)}):
                        warnings = installer._dependency_warnings()
                    self.assertEqual(len(warnings), expected_count, warnings)
                    if version == '5.0.6':
                        self.assertIn('Pass-fetch patch export needs Capstone 5.0.7', warnings[-1])
                        self.assertIn('capstone==5.0.7', warnings[-1])
                    if version is None or numpy_missing:
                        self.assertIn('requirements-studio.txt', warnings[0])
                    if version is None:
                        self.assertIn('Capstone', warnings[0])


class SurfaceRecognitionTests(unittest.TestCase):
    def test_retail_source_recognition_never_compiles_numpy_art(self):
        from mod_editor.core import nfl2k5_modern_surfaces as surfaces
        surfaces._detail_by_hash.cache_clear()
        self.addCleanup(surfaces._detail_by_hash.cache_clear)
        with mock.patch.object(surfaces, 'detail_video', side_effect=ModuleNotFoundError("No module named 'numpy'")):
            recognized = surfaces._detail_by_hash()
        for kind in {look['detail'] for look in surfaces.LOOKS.values()}:
            for variant in ('full', 'tiled'):
                digest = surfaces.pins()['details'][kind][variant]
                self.assertEqual(recognized[digest], (kind, variant))
        for digest, row in surfaces.LEGACY_DETAIL_SHA256.items():
            self.assertEqual(recognized[digest], tuple(row))

    def test_pinned_normal_signatures_match_actual_generated_bytes(self):
        from mod_editor.core import nfl2k5_modern_surfaces as surfaces
        import hashlib
        for kind in {look['detail'] for look in surfaces.LOOKS.values()}:
            for variant in ('full', 'tiled'):
                data = surfaces.detail_video(kind, tiled=variant == 'tiled')
                self.assertEqual(hashlib.sha256(data).hexdigest(), surfaces.pins()['details'][kind][variant])


if __name__ == '__main__':
    unittest.main()

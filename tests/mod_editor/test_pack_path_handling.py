"""Windows path comparisons simulated on every CI host, without Win32 handles."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import platform_compat as pc
from mod_editor.core import image_use
from tests.mod_editor.pack_path_test_support import directory_symlink, hardlink


class PackPathTests(unittest.TestCase):
    def test_windows_prefix_case_dot_and_unc_comparisons(self):
        pairs = ((r"\\?\C:\Données\Sources\..\Été.iso", r"c:\données\été.iso"),
                 (r"\\?\UNC\Server\Share\User sources é\art.png", r"\\server\share\user sources É\art.png"))
        with mock.patch.object(pc, "IS_WINDOWS", True), \
             mock.patch.object(os.path, "samefile", side_effect=OSError("stat unavailable")), \
             mock.patch.object(Path, "resolve", side_effect=OSError(234, "More data available")):
            for left, right in pairs:
                with self.subTest(left=left):
                    self.assertTrue(pc.paths_alias(left, right))
            self.assertTrue(pc.path_is_within(r"\\?\C:\Données\assets\art.png", r"c:\données"))
            self.assertTrue(pc.path_is_within(r"\\?\UNC\Server\Share\assets\art.png", r"\\server\share"))
            self.assertFalse(pc.path_is_within(r"C:\sources-other\art.png", r"C:\sources"))
            self.assertFalse(pc.path_is_within(r"D:\sources\art.png", r"C:\sources"))
            self.assertFalse(pc.path_is_within(r"C:\sources\..\art.png", r"C:\sources"))
            self.assertFalse(pc.path_is_within(r"C:\sources", r"C:\sources"))

    def test_io_extends_long_drive_and_unc_but_keeps_short_names(self):
        with mock.patch.object(pc, "IS_WINDOWS", True):
            short = r"C:\User sources é\art.png"
            self.assertEqual(os.fspath(pc.io_path(short)), short)
            self.assertEqual(os.fspath(pc.io_path("\\\\?\\" + short)), short)
            for root in ("C:\\", "\\\\server\\share\\"):
                long = root + ("données\\" * 40) + "art.png"
                result = os.fspath(pc.io_path(long))
                self.assertTrue(result.startswith("\\\\?\\"))
                self.assertEqual(pc.path_key(result), pc.path_key(long))
                self.assertEqual(pc.io_path(result), pc.io_path(long))

    def test_windows_output_names_are_checked_before_io(self):
        with mock.patch.object(pc, "IS_WINDOWS", True), \
             mock.patch.object(pc, "absolute_path", side_effect=AssertionError("normalized before validation")):
            for name in (r"C:\CON.iso", r"C:\folder.\disc.iso", r"C:\folder \disc.iso", r"C:\disc.iso ",
                         r"C:\NUL.txt", r"C:\COM¹.txt", r"C:\foo:stream", r"\\.\NUL",
                         r"folder.\disc.iso", "disc.iso ", r"C:folder.\disc.iso", "CON.iso",
                         r"\folder.\disc.iso", "C:/folder./disc.iso",
                         r"C:\folder.\..\disc.iso", r"\\?\C:\folder.\disc.iso",
                         r"\\server\share\disc.iso ", r"\\?\UNC\server\share\disc.iso "):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    pc.validate_output_path(name)
            for name in (r"C:\user sources é\disc.iso", r"\\?\UNC\server\share\disc.iso",
                         r".\folder\..\disc.iso", r"C:disc.iso", "disc.iso"):
                with self.subTest(name=name):
                    pc.validate_output_path(name)

    def test_existing_hardlink_aliases(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.iso"
            source.write_bytes(b"unchanged")
            alias = root / "alias.iso"
            hardlink(self, alias, source)
            with mock.patch.object(Path, "resolve", side_effect=OSError(234, "More data available")):
                self.assertTrue(pc.paths_alias(source, alias))
                self.assertFalse(pc.paths_alias(source, root / "new.iso"))

    def test_existing_symlink_parent_aliases(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.iso"
            source.write_bytes(b"unchanged")
            directory_symlink(self, root / "link", root)
            with mock.patch.object(Path, "resolve", side_effect=OSError(234, "More data available")):
                self.assertTrue(pc.paths_alias(source, root / "link" / "source.iso"))

    def test_invalid_outputs_are_refused_before_normalization_at_entry_points(self):
        from mod_editor.core import modpack as m, modpack_files as f, modpack_sources as s, mod_build
        for name in (r"C:\folder.\disc.iso", r"C:\disc.iso "):
            operations = (
                lambda: image_use.check_image_destination(name),
                lambda: image_use.copy_image("unused.iso", name),
                lambda: f.export("unused.iso", "unused-built.iso", name),
                lambda: f.apply(None, "unused.iso", name),
                lambda: f.extract_assets(None, name),
                lambda: s.write_bundle(name, {}, {}),
                lambda: s.materialize({"schema": "softdrink_sources/v1"}, name),
                lambda: mod_build.build(mod_build.BuildPlan("unused.iso", name)),
            )
            with mock.patch.object(pc, "IS_WINDOWS", True), \
                 mock.patch.object(pc, "absolute_path", side_effect=AssertionError("normalized before validation")):
                for index, operation in enumerate(operations):
                    with self.subTest(name=name, operation=index), self.assertRaises((ValueError, m.ModpackError)):
                        operation()

    def test_image_copy_and_source_refusal_without_resolve(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source, target = root / "été.iso", root / "new.iso"
            source.write_bytes(b"synthetic image")
            with mock.patch.object(Path, "resolve", side_effect=OSError(234, "More data available")):
                image_use.copy_image(source, target)
                with self.assertRaisesRegex(image_use.ValidationError, "separate from the source"):
                    image_use.copy_image(source, source, overwrite=True)
            self.assertEqual(target.read_bytes(), source.read_bytes())


if __name__ == "__main__":
    unittest.main()

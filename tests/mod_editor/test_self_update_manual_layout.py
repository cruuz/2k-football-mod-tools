"""Manual/source installs must be refused before download or handoff."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import self_update as update


class ManualLayoutTests(unittest.TestCase):
    def test_unknown_source_zip_and_broken_setup_never_download(self):
        for kind in ("manual", "source-zip", "missing-runtime"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                root = Path(folder) / ("app" if kind == "missing-runtime" else "studio")
                (root / "mod_editor").mkdir(parents=True)
                (root / "mod_editor/__main__.py").write_bytes(b"")
                if kind != "manual":
                    (root / "2K5-Mod-Studio.bat").write_bytes(b"@echo off\n")
                if kind == "source-zip":
                    (root / ".github").mkdir()
                install = update.detect_install(root, platform="win32")
                self.assertEqual(install.kind, "unknown")
                opener, spawn = Mock(), Mock()
                with self.assertRaises(update.SelfUpdateError) as caught:
                    update.run_update({}, install=install, opener=opener, spawn_windows=spawn)
                self.assertEqual(str(caught.exception), update.UNSUPPORTED_LAYOUT_MESSAGE)
                opener.assert_not_called()
                spawn.assert_not_called()
                self.assertTrue((root / "mod_editor/__main__.py").exists())


if __name__ == "__main__":
    unittest.main()

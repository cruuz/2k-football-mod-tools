"""Cross-build preparation must disclose deferred Windows execution checks."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packaging"))
spec = importlib.util.spec_from_file_location(
    "windows_builder", ROOT / "packaging/windows/build_windows_installer.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class WindowsBuilderTests(unittest.TestCase):
    def test_default_requires_execution_and_explicit_deferral_records_pending(self):
        for deferred in (False, True):
            with self.subTest(deferred=deferred), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                stage = root / "stage"
                stage.mkdir()
                (stage / "application.txt").write_text("fixture\n")
                work = root / "work"
                argv = ["builder", "--stage", str(stage), "--product", "2k5",
                        "--version", "1.0.0rc111", "--out", str(root / "out"),
                        "--work", str(work)]
                if deferred:
                    argv.append("--defer-runtime-check")
                with (mock.patch.object(sys, "argv", argv),
                      mock.patch.object(builder, "build_runtime"),
                      mock.patch("runtime_dependencies.check_runtime_dependencies") as static_check,
                      mock.patch("check_packaged_runtime.check_layout",
                                 side_effect=RuntimeError("execution refused")) as execution):
                    if deferred:
                        self.assertEqual(builder.main(), 0)
                        execution.assert_not_called()
                        self.assertTrue((work / "installer.nsi").is_file())
                        receipt = json.loads((work / "runtime-check.json").read_text())
                        self.assertEqual(receipt["status"], "pending")
                        self.assertEqual(receipt["version"], "1.0.0rc111")
                    else:
                        with self.assertRaisesRegex(RuntimeError, "execution refused"):
                            builder.main()
                        execution.assert_called_once()
                        self.assertFalse((work / "installer.nsi").exists())
                    static_check.assert_called_once()


if __name__ == "__main__":
    unittest.main()

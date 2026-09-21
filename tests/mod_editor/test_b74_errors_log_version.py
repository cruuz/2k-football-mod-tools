"""Beta 74: every report in errors.log says which Studio build wrote it.

Nothing on a user's disk recorded the Studio version, so an errors.log entry
could not be tied to a build and a reinstall left no trace. Build and import
failures are caught and shown in a dialog, so the crash hook never saw them
and errors.log stayed empty for exactly the errors people report. Both are
fixed: caught failures are recorded through ``record_operation`` and every
entry, caught or uncaught, carries the version on its first line.

Temporary directories only; the real errors.log is never touched.
"""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).resolve().parent)]

import mod_editor
from mod_editor.gui import crash_report


class ErrorsLogVersionTests(unittest.TestCase):
    def test_app_version_is_the_shipped_version(self):
        self.assertEqual(crash_report.app_version("2K5 Mod Studio"), mod_editor.__version__)
        from mod_editor.apf_studio import __version__ as apf_version
        self.assertEqual(crash_report.app_version("APF 2K8 Mod Studio"), apf_version)

    def test_caught_operation_is_recorded_with_the_version(self):
        with tempfile.TemporaryDirectory() as folder:
            saved = crash_report.record_operation(
                "finish that", "The texture receipt is missing or exceeds its size bound: x",
                "2K5 Mod Studio", directory=Path(folder), when="2026-09-20 13:05:00")
            self.assertEqual(saved, Path(folder) / "errors.log")
            text = saved.read_text(encoding="utf-8")
            first = text.splitlines()[0]
            self.assertEqual(first, f"2K5 Mod Studio {mod_editor.__version__}")
            self.assertIn("time: 2026-09-20 13:05:00", text)
            self.assertIn("operation: finish that", text)
            self.assertIn("texture receipt is missing", text)
            self.assertIn("-" * 60, text)

    def test_two_records_append_in_order(self):
        with tempfile.TemporaryDirectory() as folder:
            crash_report.record_operation("open", "first", "2K5 Mod Studio", directory=Path(folder))
            crash_report.record_operation("build", "second", "2K5 Mod Studio", directory=Path(folder))
            text = (Path(folder) / "errors.log").read_text(encoding="utf-8")
            self.assertLess(text.index("first"), text.index("second"))
            self.assertEqual(text.count(f"2K5 Mod Studio {mod_editor.__version__}"), 2)

    def test_uncaught_crash_report_carries_the_version(self):
        try:
            raise RuntimeError("boom")
        except RuntimeError as exc:
            report = crash_report.format_report(type(exc), exc, exc.__traceback__, "2K5 Mod Studio",
                                                when="2026-09-20 00:00:00")
        self.assertTrue(report.startswith(f"2K5 Mod Studio {mod_editor.__version__}\n"), report[:80])
        self.assertIn("RuntimeError: boom", report)

    def test_a_failed_background_task_is_recorded_with_its_label(self):
        # The main window reports a failed build through its own
        # "Couldn't finish that" dialog, not show_operation_error, so the
        # recording hangs off the task runner's error path with the task label.
        from unittest.mock import patch
        from mod_editor.gui import studio_qt
        with patch.object(crash_report, "record_operation") as recorded:
            studio_qt._record_failed_operation("Making the disc", "The texture receipt is missing")
        recorded.assert_called_once_with("Making the disc", "The texture receipt is missing",
                                         "2K5 Mod Studio")
        with patch.object(crash_report, "record_operation", side_effect=RuntimeError("disk")):
            studio_qt._record_failed_operation("Making the disc", "boom")  # never raises

    def test_recording_never_raises_on_an_unwritable_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            blocked = Path(folder) / "file-not-a-dir"
            blocked.write_text("x", encoding="utf-8")
            # A directory that is actually a file cannot be created into; the
            # caller still shows its dialog, so this must return None, not raise.
            self.assertIsNone(crash_report.record_operation(
                "build", "msg", "2K5 Mod Studio", directory=blocked))


if __name__ == "__main__":
    unittest.main()

"""b791-h3: the Build tab says where a build stopped, why, and where its log and diagnostic report are (offscreen).

"Couldn't make the disc. It stopped during <step> (<resource>): <message>." with the build log, the diagnostic .zip
and "send that .zip to the SOFTDRINK Discord"; Copy Build summary carries the step, the resource, the colour values
and the paths; the worker writes the errors.log entry, the build log and the zip (calling the project doctor) before
the dialog. Temporary folders only (MOD_STUDIO_LOG_DIR); the real errors.log is never touched.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools", ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.core import build_steps, mod_build  # noqa: E402
from mod_editor.gui import build_panel_qt, crash_report, ux_text  # noqa: E402

RECORD = {
    "result": "failed", "step": "modern_surfaces", "label": "Modern playing surfaces", "resource": "s13ad.iff",
    "message": "During Modern playing surfaces (s13ad.iff): cannot keep the retail scratch word:",
    "reason": "cannot keep the retail scratch word (the step gave no reason)",
    "last_progress": "Modern surfaces: 117 of 288 bundles", "undo": "", "build_log": "C:\\2K5\\out.xiso.iso.build-log.txt",
    "log_copy": "C:\\Users\\Coach\\AppData\\Local\\2k5-mod-studio\\builds\\x.build-log.txt",
    "errors_log": "C:\\Users\\Coach\\AppData\\Local\\2k5-mod-studio\\errors.log",
    "zip": "C:\\2K5\\out.xiso.iso.diagnostic-20261102-143005.zip", "doctor": "ok",
    "left_out": ["Modern Arrowhead was left out: s13 field does not fit. Your disc keeps Arrowhead Stadium as it was."],
    "colour": "turf.value_lift=3.1 (default 1.0)",
}


class DialogTextTests(unittest.TestCase):
    def test_the_dialog_names_step_resource_reason_files_and_discord(self):
        text, details = ux_text.build_failure_texts(RECORD)
        self.assertTrue(text.startswith("Couldn't make the disc. It stopped during Modern playing surfaces (s13ad.iff): "
                                        "cannot keep the retail scratch word (the step gave no reason)."), text)
        self.assertIn("The build log is here:\nC:\\2K5\\out.xiso.iso.build-log.txt", text)
        self.assertIn("The diagnostic report is here:\nC:\\2K5\\out.xiso.iso.diagnostic-20261102-143005.zip", text)
        self.assertIn("send that .zip to the SOFTDRINK Discord", text)
        self.assertIn("Your original game disc was not changed.", text)
        self.assertNotIn("—", text + details)
        self.assertIn("Last progress line in that step: Modern surfaces: 117 of 288 bundles", details)
        self.assertIn("Left out earlier in this build:\n- Modern Arrowhead was left out", details)
        self.assertIn("Modern colour values: turf.value_lift=3.1", details)
        self.assertIn("errors.log: C:\\Users\\Coach", details)

    def test_a_known_refusal_keeps_its_fix_and_no_zip_falls_back_to_the_log(self):
        record = dict(RECORD, message="During the copy of your game disc: [Errno 28] No space left on device",
                      reason="[Errno 28] No space left on device", zip="", resource=None, label="the copy of your game disc")
        text, _details = ux_text.build_failure_texts(record)
        self.assertIn("It stopped during the copy of your game disc: [Errno 28] No space left on device.", text)
        self.assertIn("Fix: a drive is full.", text)
        self.assertIn("send that build log to the SOFTDRINK Discord", text)

    def test_the_summary_lines_carry_step_resource_colour_and_paths(self):
        lines = ux_text.build_summary_lines(RECORD)
        self.assertEqual(lines[0], "First error: " + RECORD["message"])
        for needle in ("Step: Modern playing surfaces (modern_surfaces)", "Resource: s13ad.iff",
                       "Modern colour values: turf.value_lift=3.1 (default 1.0)",
                       "Build log: C:\\2K5\\out.xiso.iso.build-log.txt",
                       "Diagnostic report: C:\\2K5\\out.xiso.iso.diagnostic-20261102-143005.zip"):
            self.assertIn(needle, lines)


class BuildPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.folder, ignore_errors=True))
        self.enterContext(mock.patch.dict(os.environ, {crash_report.LOG_DIRECTORY_ENV: str(self.folder / "logs")}))
        self.panel = build_panel_qt.BuildPanel()
        self.addCleanup(self.panel.deleteLater)
        self.source = self.folder / "ESPN NFL 2K5 (USA).xiso.iso"
        self.source.write_bytes(b"RETAIL-CANARY" * 4096)
        (self.folder / "out").mkdir()
        self.target = self.folder / "out" / "Coach (modded).xiso.iso"
        self.plan = mod_build.BuildPlan(str(self.source), str(self.target), modern_surfaces=True)
        self.panel._requested_build_labels = ["Modern playing surfaces"]
        self.panel._requested_build_summary = "2K5 Mod Studio test\nSelected: Modern playing surfaces"

    def _progress(self):
        lines = []

        def progress(message, done=0, total=0):
            lines.append(message)
        progress.cancelled = threading.Event()
        return progress, lines

    def test_failed_shows_the_build_failure_dialog_and_fills_the_summary(self):
        failure = ValueError("x")
        failure.studio_build_record = dict(RECORD)
        self.panel._task = SimpleNamespace(failure=failure)
        with mock.patch.object(build_panel_qt, "show_build_failure") as shown, \
             mock.patch.object(build_panel_qt, "show_operation_error") as plain:
            self.panel._failed("During Modern playing surfaces (s13ad.iff): cannot keep the retail scratch word:")
        shown.assert_called_once()
        plain.assert_not_called()
        self.assertEqual(self.panel.status_label.text(),
                         "Couldn't make the disc. It stopped during Modern playing surfaces (s13ad.iff): cannot keep "
                         "the retail scratch word (the step gave no reason).")
        summary = self.panel._last_build_summary
        self.assertTrue(summary.startswith("2K5 Mod Studio test\nSelected: Modern playing surfaces"))
        for needle in ("Step: Modern playing surfaces (modern_surfaces)", "Resource: s13ad.iff",
                       "Modern colour values: turf.value_lift=3.1", "Build log: C:\\2K5\\out.xiso.iso.build-log.txt",
                       "Diagnostic report: "):
            self.assertIn(needle, summary)
        self.panel._copy_build_summary()
        self.assertIn("Resource: s13ad.iff", QApplication.clipboard().text())

    def test_failed_without_a_record_keeps_the_old_dialog(self):
        self.panel._task = SimpleNamespace(failure=None)
        with mock.patch.object(build_panel_qt, "show_operation_error") as plain:
            self.panel._failed("Build cancelled; no output was published.")
        plain.assert_called_once()
        self.assertIn("First error: Build cancelled", self.panel._last_build_summary)

    def test_the_worker_writes_errors_log_build_log_and_zip_and_runs_the_doctor(self):
        doctor_calls = []

        class Report:
            def text(self):
                return "Project doctor: Modern surfaces would keep s13ad.iff's divot layer.\n"

            def as_dict(self):
                return {"findings": [{"severity": "note", "area": "Modern surfaces"}]}

        def doctor(project, source, settings, *, progress=None, workers=None):
            doctor_calls.append((project, source, settings, workers))
            progress("dry run 1 of 2", 1, 2)
            return Report()

        def failing_build(plan, progress, require_change=False):
            progress("Copying the image", 0, 0)
            build_steps.begin("modern_surfaces")
            progress("Modern surfaces: 117 of 288 bundles", 117, 288)
            with build_steps.resource("s13ad.iff"):
                raise ValueError("cannot keep the retail scratch word:")

        progress, lines = self._progress()
        with mock.patch.object(mod_build, "build", side_effect=failing_build), \
             mock.patch("mod_editor.core.nfl2k5_project_check.doctor", create=True, side_effect=doctor):
            with self.assertRaises(ValueError) as caught:
                self.panel._build_operation(self.plan, progress)
        exc = caught.exception
        self.assertIsInstance(exc, build_steps.StepFailure)
        record = exc.studio_build_record
        self.assertEqual((record["step"], record["resource"]), ("modern_surfaces", "s13ad.iff"))
        self.assertEqual(doctor_calls[0][0], None)                       # no project in this build
        self.assertEqual(Path(doctor_calls[0][1]), self.source)
        self.assertIs(doctor_calls[0][2], self.plan)
        self.assertIn("Diagnostic report, project doctor: dry run 1 of 2", lines)
        errors = (self.folder / "logs" / "2k5-mod-studio" / "errors.log").read_bytes().decode("utf-8")
        self.assertNotIn("\r\n", errors)
        self.assertIn("step: Modern playing surfaces (modern_surfaces)", errors)
        self.assertIn("Traceback (most recent call last):", errors)
        self.assertEqual(errors.count("operation: make the disc"), 1)
        self.assertEqual(Path(record["build_log"]).parent, self.target.parent)
        self.assertTrue(Path(record["log_copy"]).is_file())
        with zipfile.ZipFile(record["zip"]) as bundle:
            self.assertIn("project-doctor.txt", bundle.namelist())
            for name in bundle.namelist():
                self.assertNotIn(b"RETAIL-CANARY", bundle.read(name))
        # the dialog text built from that record
        text, _details = ux_text.build_failure_texts(record)
        self.assertIn(record["zip"], text)

    def test_a_finished_build_writes_its_log_beside_the_disc(self):
        def finished_build(plan, progress, require_change=False):
            progress("Copying the image", 0, 0)
            build_steps.begin("modern_surfaces")
            progress("Modern surfaces: 288 of 288 bundles", 288, 288)
            self.target.write_bytes(b"built")
            return {"target": str(self.target), "steps": [], "result": {}, "user_notes": []}

        progress, _lines = self._progress()
        with mock.patch.object(mod_build, "build", side_effect=finished_build):
            receipt = self.panel._build_operation(self.plan, progress)
        log = Path(receipt["build_log"])
        self.assertEqual(log.parent, self.target.parent)
        self.assertIn("Result: OK (the disc was made)", log.read_text(encoding="utf-8"))
        self.assertTrue(progress.published)

    def test_the_task_keeps_the_exception_for_the_dialog(self):
        task = build_panel_qt._Task(lambda progress: (_ for _ in ()).throw(ValueError("ValueError: boom")))
        seen = []
        task.signals.failed.connect(seen.append)
        task.run()
        self.assertIsInstance(task.failure, ValueError)
        self.assertEqual(seen, ["boom"])


class CrashReportTests(unittest.TestCase):
    def test_the_log_folder_override_and_lf_entries_with_details(self):
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.dict(os.environ, {crash_report.LOG_DIRECTORY_ENV: folder}):
            self.assertEqual(crash_report.log_directory("2K5 Mod Studio"), Path(folder) / "2k5-mod-studio")
            saved = crash_report.record_operation("open the project", "boom", "2K5 Mod Studio",
                                                  details="Traceback (most recent call last):\n  File x\nValueError: boom")
            data = saved.read_bytes().decode("utf-8")
        self.assertNotIn("\r\n", data)
        self.assertIn("boom\n\nTraceback (most recent call last):", data)

    def test_reports_go_to_the_log_folder_only_in_the_running_studio_or_when_asked(self):
        env = {key: value for key, value in os.environ.items() if key != crash_report.LOG_DIRECTORY_ENV}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(crash_report, "_INSTALLED", set()):
            self.assertFalse(crash_report.reports_enabled("2K5 Mod Studio"))
            self.assertIsNone(build_panel_qt._studio_log_directory())    # a test's panel never writes there
            crash_report._INSTALLED.add("2K5 Mod Studio")                 # what crash_report.install() records
            self.assertTrue(crash_report.reports_enabled("2K5 Mod Studio"))
            self.assertEqual(build_panel_qt._studio_log_directory(), crash_report.log_directory("2K5 Mod Studio"))

    def test_the_main_window_records_a_task_traceback(self):
        from mod_editor.gui import studio_qt
        with mock.patch.object(crash_report, "record_operation") as recorded:
            studio_qt._record_failed_operation("Opening and validating the project", "boom", "Traceback ...")
        recorded.assert_called_once_with("Opening and validating the project", "boom", "2K5 Mod Studio",
                                         details="Traceback ...")


if __name__ == "__main__":
    unittest.main()

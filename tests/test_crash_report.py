"""An unexpected error has to reach the user, not end the process silently.

PyQt5 aborts when an exception escapes a slot and no ``sys.excepthook`` is
installed, and these editors run from a desktop icon with no console, so the
window just disappeared. The tests below cover the two things that has to
become: a report that survives on disk, and a hook that does not itself fail.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mod_editor.gui import crash_report  # noqa: E402


def _raise(message: str = "boom"):
    """Produce a real traceback rather than a synthesised one."""
    try:
        raise ValueError(message)
    except ValueError:
        return sys.exc_info()


class ReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp(prefix="crash-report-"))

    def test_the_report_names_the_error_and_the_app(self) -> None:
        report = crash_report.format_report(*_raise("disc is truncated"), "2K5 Mod Studio")
        self.assertIn("2K5 Mod Studio", report)
        self.assertIn("ValueError: disc is truncated", report)
        self.assertIn("Traceback", report)

    def test_the_report_is_written_where_the_dialog_says_it_is(self) -> None:
        report = crash_report.format_report(*_raise(), "2K5 Mod Studio")
        written = crash_report.write_report(report, "2K5 Mod Studio", directory=self.directory)
        self.assertIsNotNone(written)
        self.assertTrue(written.is_file())
        self.assertIn("ValueError: boom", written.read_text(encoding="utf-8"))
        _title, _headline, detail = crash_report.summary_lines("2K5 Mod Studio", written)
        self.assertIn(str(written), detail)

    def test_reports_accumulate_rather_than_overwriting(self) -> None:
        """The second crash must not erase the evidence from the first."""

        for message in ("first failure", "second failure"):
            crash_report.write_report(
                crash_report.format_report(*_raise(message), "2K5 Mod Studio"),
                "2K5 Mod Studio",
                directory=self.directory,
            )
        text = (self.directory / "errors.log").read_text(encoding="utf-8")
        self.assertIn("first failure", text)
        self.assertIn("second failure", text)

    def test_an_unwritable_log_still_produces_a_usable_message(self) -> None:
        """A read-only home is not a reason to lose the error."""

        unwritable = self.directory / "file-in-the-way"
        unwritable.write_text("not a directory", encoding="utf-8")
        written = crash_report.write_report("x", "2K5 Mod Studio", directory=unwritable)
        self.assertIsNone(written)
        _title, headline, detail = crash_report.summary_lines("2K5 Mod Studio", None)
        self.assertTrue(headline)
        self.assertIn("could not be saved", detail)

    def test_the_user_is_told_their_source_is_untouched(self) -> None:
        """The first thing somebody wants to know is whether they lost anything.

        The editors never write to a user's original, so this is a fact the
        message is entitled to state plainly.
        """

        _title, headline, _detail = crash_report.summary_lines("2K5 Mod Studio", None)
        self.assertIn("original game files were not changed", headline)


class HookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp(prefix="crash-hook-"))
        self.previous = sys.excepthook
        self.addCleanup(setattr, sys, "excepthook", self.previous)

    def test_install_routes_exceptions_and_returns_the_old_hook(self) -> None:
        returned = crash_report.install("2K5 Mod Studio", directory=self.directory)
        self.assertIs(returned, self.previous)
        self.assertIsNot(sys.excepthook, self.previous)
        sys.excepthook(*_raise("routed through the hook"))
        text = (self.directory / "errors.log").read_text(encoding="utf-8")
        self.assertIn("routed through the hook", text)

    def test_keyboard_interrupt_is_not_reported_as_a_crash(self) -> None:
        """Ctrl+C is a request to quit. Reporting it would be wrong, and in a
        terminal it would also be impossible to escape."""

        try:
            raise KeyboardInterrupt
        except KeyboardInterrupt:
            info = sys.exc_info()
        crash_report.handle(*info, app_name="2K5 Mod Studio", directory=self.directory)
        self.assertFalse((self.directory / "errors.log").exists())

    def test_the_handler_does_not_raise_when_nothing_works(self) -> None:
        """A crash handler that crashes replaces the message with a worse one."""

        blocked = self.directory / "blocked"
        blocked.write_text("not a directory", encoding="utf-8")
        crash_report.handle(*_raise(), app_name="2K5 Mod Studio", directory=blocked,
                            show_dialog=False)


class RepeatedFaultTests(unittest.TestCase):
    """A fault thrown every frame must not become a wall of modal dialogs.

    Anything raised from a paint or timer handler fires again immediately. Each
    dialog waits for a click, so the second queues behind the first and the
    editor is unusable. Every occurrence is still logged; only the interruption
    is suppressed.
    """

    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp(prefix="crash-repeat-"))
        self.saved = set(crash_report._ALREADY_SHOWN)
        self.addCleanup(self._restore)
        self.shown: list[str] = []
        self.original = crash_report._show_dialog
        crash_report._show_dialog = lambda app, saved_to, report: (
            self.shown.append(app) or True
        )
        self.addCleanup(setattr, crash_report, "_show_dialog", self.original)

    def _restore(self) -> None:
        crash_report._ALREADY_SHOWN.clear()
        crash_report._ALREADY_SHOWN.update(self.saved)

    def test_the_same_fault_is_shown_once_but_logged_every_time(self) -> None:
        crash_report._ALREADY_SHOWN.clear()
        for _ in range(5):
            crash_report.handle(*_raise("repeating fault"),
                                app_name="2K5 Mod Studio", directory=self.directory)
        self.assertEqual(len(self.shown), 1)
        text = (self.directory / "errors.log").read_text(encoding="utf-8")
        self.assertEqual(text.count("repeating fault"), 5)

    def test_a_different_fault_still_gets_its_own_dialog(self) -> None:
        """Suppressing repeats must not suppress a genuinely new problem."""

        crash_report._ALREADY_SHOWN.clear()

        def other():
            try:
                raise KeyError("a different place entirely")
            except KeyError:
                return sys.exc_info()

        crash_report.handle(*_raise(), app_name="2K5 Mod Studio",
                            directory=self.directory)
        crash_report.handle(*other(), app_name="2K5 Mod Studio",
                            directory=self.directory)
        self.assertEqual(len(self.shown), 2)

    def test_the_signature_is_the_raising_line_not_the_message(self) -> None:
        """Two failures at one site are the same fault even with different text."""

        first, second = _raise("disc A"), _raise("disc B")
        self.assertEqual(crash_report.signature(first[0], first[2]),
                         crash_report.signature(second[0], second[2]))


class DialogSuppressionTests(unittest.TestCase):
    """A modal dialog nobody can dismiss is a hang, not a report.

    ``QMessageBox.exec_`` waits for a click. Under the offscreen platform, or in
    a test run, that click never comes, so the process stops there forever. This
    was not hypothetical: it stalled a full suite run at 85 percent.
    """

    def test_a_real_display_gets_the_dialog(self) -> None:
        self.assertTrue(crash_report.dialog_is_possible("xcb", environment={}))
        self.assertTrue(crash_report.dialog_is_possible("windows", environment={}))
        self.assertTrue(crash_report.dialog_is_possible("cocoa", environment={}))

    def test_headless_platforms_do_not(self) -> None:
        for platform in ("offscreen", "minimal", "vnc", "OffScreen"):
            with self.subTest(platform=platform):
                self.assertFalse(
                    crash_report.dialog_is_possible(platform, environment={}))

    def test_a_test_run_never_opens_a_dialog(self) -> None:
        self.assertFalse(crash_report.dialog_is_possible(
            "xcb", environment={"PYTEST_CURRENT_TEST": "something::test"}))

    def test_an_operator_can_turn_the_dialog_off(self) -> None:
        self.assertFalse(crash_report.dialog_is_possible(
            "xcb", environment={"MOD_STUDIO_NO_ERROR_DIALOG": "1"}))

    def test_an_unknown_platform_is_assumed_interactive(self) -> None:
        """Failing closed here would silence the report on a real desktop."""

        self.assertTrue(crash_report.dialog_is_possible("wayland-egl", environment={}))
        self.assertTrue(crash_report.dialog_is_possible(None, environment={}))


class LogLocationTests(unittest.TestCase):
    def test_the_directory_is_named_after_the_app(self) -> None:
        self.assertIn("2k5-mod-studio", str(crash_report.log_directory("2K5 Mod Studio")))

    def test_each_editor_gets_its_own_log(self) -> None:
        self.assertNotEqual(
            crash_report.log_directory("2K5 Mod Studio"),
            crash_report.log_directory("APF 2K8 Mod Studio"),
        )


if __name__ == "__main__":
    unittest.main()

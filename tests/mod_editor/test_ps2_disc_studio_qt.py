"""View-model, wording and dialog tests for the PS2 Disc Studio window.

Everything is synthetic: the combined disc the service tests build, driven
through the real service so the tabs see real catalogues.  The Qt-free view
model is tested without a display; the dialog itself runs against an
offscreen QApplication and is skipped where PyQt5 is absent, following the
disc-inventory and export windows' tests.  The entry points are checked
statically, as the wording tests check copy: constructing the whole Xbox
studio window is not this module's business.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
for _extra in (ROOT, ROOT / "tools", ROOT / "tests" / "mod_editor"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.core import ps2_disc_studio_lanes as lanes  # noqa: E402
from mod_editor.core import ps2_disc_studio_service as svc  # noqa: E402
from mod_editor.gui import ps2_disc_studio_qt as gui  # noqa: E402

import test_ps2_disc_studio_service as fixtures  # noqa: E402

try:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication, QDialog
except ImportError:  # PyQt5 is not installed here
    QApplication = None  # type: ignore[assignment]


class ViewModelTests(unittest.TestCase):
    def test_nothing_but_open_before_a_disc(self) -> None:
        state = gui.ps2_disc_studio_action_state(
            disc_open=False, supported=False, busy=False, catalogue_built=False,
            staged_count=0, plans_ready=False, built=False)
        self.assertTrue(state.can_open)
        self.assertFalse(state.can_build_catalogue or state.can_edit or state.can_check or state.can_build)

    def test_build_needs_a_clean_plan_for_every_staged_lane(self) -> None:
        common = dict(disc_open=True, supported=True, busy=False, catalogue_built=True, built=False)
        self.assertFalse(gui.ps2_disc_studio_action_state(staged_count=2, plans_ready=False, **common).can_build)
        self.assertTrue(gui.ps2_disc_studio_action_state(staged_count=2, plans_ready=True, **common).can_build)
        self.assertFalse(gui.ps2_disc_studio_action_state(staged_count=0, plans_ready=True, **common).can_build)

    def test_an_unsupported_disc_can_be_browsed_but_never_built(self) -> None:
        state = gui.ps2_disc_studio_action_state(
            disc_open=True, supported=False, busy=False, catalogue_built=True,
            staged_count=1, plans_ready=True, built=False)
        self.assertTrue(state.can_edit)
        self.assertFalse(state.can_check or state.can_build)

    def test_a_busy_window_offers_only_cancel(self) -> None:
        state = gui.ps2_disc_studio_action_state(
            disc_open=True, supported=True, busy=True, catalogue_built=True,
            staged_count=1, plans_ready=True, built=True)
        self.assertTrue(state.can_cancel)
        self.assertFalse(state.can_open or state.can_edit or state.can_build or state.can_open_folder)

    def test_the_suggested_destination_is_never_the_source_name(self) -> None:
        self.assertEqual(gui.suggested_destination("ESPN NFL 2K5 (USA).iso"), "ESPN NFL 2K5 (USA)-modded.iso")
        self.assertEqual(gui.suggested_destination(""), "nfl2k5-ps2-modded.iso")

    def test_the_queue_summary_says_what_to_do_next(self) -> None:
        self.assertIn("Nothing is staged", gui.queue_summary_text({}, {}, []))
        self.assertIn("not checked yet", gui.queue_summary_text({"text": 2}, {}, []))
        self.assertIn("not checked yet", gui.queue_summary_text({"text": 2}, {"text": object()}, ["text"]))
        self.assertIn("ready to build", gui.queue_summary_text({"text": 2}, {"text": object()}, []))

    def test_the_receipt_text_carries_every_verdict_and_the_digest(self) -> None:
        class Step:
            index, lane_id, plan_summary, verdict_summary = 1, "text", "1 string", "text verifier: pass"
            seconds = {"write": 12.0, "verify": 3.0}

        class Receipt:
            steps = (Step(),)
            message = "Wrote out.iso"
            receipt_path = Path("/tmp/out.iso.receipt.json")
            destination_sha256 = "abc"

        text = gui.receipt_text(Receipt())
        self.assertIn("text verifier: pass", text)
        self.assertIn("write 12 s, verify 3 s", text)
        self.assertIn("SHA-256: abc", text)


class WordingTests(unittest.TestCase):
    """Refusals name a fix; nothing claims a screen or a speaker."""

    FIX_WORDS = ("shorten", "choose", "remove", "supply", "change", "enter", "add", "type", "pick",
                 "leave", "replace", "fix", "free some space", "use ", "must be", "rebuild", "keep",
                 "give ")

    def test_boundary_and_caveats_never_claim_runtime(self) -> None:
        for sentence in (gui.BOUNDARY_NOTE, gui.UNSUPPORTED_DISC_NOTE):
            self.assertNotIn("proved in game", sentence.lower())
        self.assertIn("never changed", gui.BOUNDARY_NOTE)
        self.assertIn("seen or heard", gui.BOUNDARY_NOTE)

    def test_inline_refusals_name_the_fix(self) -> None:
        source = (ROOT / "mod_editor" / "core" / "ps2_disc_studio_lanes.py").read_text(encoding="utf-8")
        # Every `return (...)` / `return "..."` inside a check_edit body is an inline refusal.
        bodies = re.findall(r"def check_edit\(.*?\n(.*?)\n    def ", source, flags=re.S)
        self.assertGreaterEqual(len(bodies), 6)
        refusals = []
        for body in bodies:
            for match in re.finditer(r"return \(?\s*(f?\"(?:[^\"\\]|\\.)*\"(?:\s*f?\"(?:[^\"\\]|\\.)*\")*)", body):
                text = " ".join(re.findall(r"\"((?:[^\"\\]|\\.)*)\"", match.group(1)))
                # A bare "{exc}" passes the tool's own sentence through; the tool names the fix.
                if text.strip() and text.strip() not in ("{exc}",) and not text.rstrip().endswith(": {exc}"):
                    refusals.append(text.lower())
        self.assertGreaterEqual(len(refusals), 25)
        dead_ends = [text for text in refusals if not any(word in text for word in self.FIX_WORDS)]
        self.assertEqual(dead_ends, [], "every inline refusal must say what to do")


class EntryPointTests(unittest.TestCase):
    def test_the_file_menu_action_mirrors_the_other_ps2_windows(self) -> None:
        source = (ROOT / "mod_editor" / "gui" / "studio_qt.py").read_text(encoding="utf-8")
        self.assertIn('file_menu.addAction("PS2 Disc Studio…")', source)
        handler = source[source.index("def _open_ps2_disc_studio"):]
        handler = handler[:handler.index("\n    def ", 10)]
        self.assertIn('_refuse_while_audio_busy("open the PS2 Disc Studio")', handler)
        self.assertIn("from .ps2_disc_studio_qt import Ps2DiscStudioDialog", handler)
        self.assertIn("your Xbox project was not changed", handler)
        self.assertIn("self._ps2_disc_studio_action.setEnabled(not global_busy)", source)

    def test_the_command_line_flag_takes_an_optional_iso(self) -> None:
        source = (ROOT / "mod_editor" / "__main__.py").read_text(encoding="utf-8")
        self.assertIn('"--ps2-disc-studio"', source)
        self.assertIn("if args.ps2_disc_studio is not None:", source)
        self.assertIn("initial_iso=Path(args.ps2_disc_studio) if args.ps2_disc_studio else None", source)


def _qt_application():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if QApplication is None:
        return None
    return QApplication.instance() or QApplication([])


@unittest.skipIf(QApplication is None, "PyQt5 is not installed")
class DialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qt_application()
        if cls.app is None:  # pragma: no cover - environment guard
            raise unittest.SkipTest("no QApplication is available")
        cls._temp = tempfile.TemporaryDirectory(prefix="ps2-disc-studio-dialog-")
        cls.root = Path(cls._temp.name)
        cls.iso = cls.root / "source.iso"
        cls.iso.write_bytes(fixtures.combined_disc())
        # Catalogues are built once here; each dialog re-opens the disc and finds them in the cache.
        warm = svc.Ps2DiscStudioService(cache_root=cls.root / "cache", poll_seconds=0.05)
        warm.open(cls.iso)
        for lane_id in ("text", "colors", "roster", "audio"):
            warm.build_catalogue(lane_id)
        warm.close()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temp.cleanup()

    def _service(self):
        return svc.Ps2DiscStudioService(cache_root=self.root / "cache", poll_seconds=0.05)

    def _settle(self, dialog, timeout: float = 60.0) -> None:
        deadline = time.monotonic() + timeout
        while dialog._busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.app.processEvents()
        self.assertFalse(dialog._busy, "the background operation never finished")

    def _opened(self, dialog) -> None:
        dialog._open_path(self.iso)
        self.assertTrue(dialog._busy)
        self._settle(dialog)

    def test_the_dialog_is_a_qt_dialog_with_a_tab_per_lane_and_a_build_page(self) -> None:
        self.assertTrue(gui.PYQT5_AVAILABLE)
        self.assertTrue(issubclass(gui.Ps2DiscStudioDialog, QDialog))
        dialog = gui.Ps2DiscStudioDialog(host=self._service())
        try:
            self.assertEqual(list(dialog.tabs), list(lanes.LANE_ORDER))
            self.assertEqual(dialog.tab_widget.count(), 7)
            self.assertEqual(dialog.tab_widget.tabText(6), "Build")
            self.assertFalse(dialog.build_page.build_button.isEnabled())
            self.assertFalse(dialog.build_page.check_button.isEnabled())
            self.assertTrue(dialog.open_button.isEnabled())
        finally:
            dialog.done(0)

    def test_every_named_control_has_an_accessible_name(self) -> None:
        from PyQt5.QtWidgets import QComboBox, QLineEdit, QPlainTextEdit, QPushButton, QTableView, QTableWidget

        dialog = gui.Ps2DiscStudioDialog(host=self._service())
        try:
            named = [dialog.open_button, dialog.cancel_button, dialog.tab_widget, dialog.info_label,
                     dialog.status_label, dialog.progress_bar, dialog.build_page.queue,
                     dialog.build_page.destination, dialog.build_page.choose_button,
                     dialog.build_page.check_button, dialog.build_page.build_button,
                     dialog.build_page.open_folder_button, dialog.build_page.receipt_label]
            for tab in dialog.tabs.values():
                named.extend([tab.search, tab.table, tab.catalogue_button, tab.add_button, tab.staged_list,
                              tab.remove_button, tab.clear_button, tab.check_button, tab.preview, tab.rules_button])
                named.extend(widget for widget in tab.editor_box.findChildren(
                    (QLineEdit, QComboBox, QPlainTextEdit, QPushButton, QTableView, QTableWidget))
                    if widget.parent() is not None and not isinstance(widget.parent(), (QComboBox,))
                    and widget.objectName() != "qt_spinbox_lineedit")
            missing = [widget.__class__.__name__ for widget in named if not widget.accessibleName()]
            self.assertEqual(missing, [])
        finally:
            dialog.done(0)

    def test_opening_populates_the_tabs_from_the_cached_catalogues(self) -> None:
        dialog = gui.Ps2DiscStudioDialog(host=self._service())
        try:
            self._opened(dialog)
            self.assertIn("SLUS-20919", dialog.info_label.text())
            self.assertIn("Text: 1 banks", dialog.info_label.text())
            text_tab = dialog.tabs["text"]
            self.assertEqual(text_tab.model.rowCount(), 6)
            self.assertEqual(text_tab.model.data(text_tab.model.index(0, 2), Qt.DisplayRole), "MENU")
            self.assertIn("6 of 6 targets shown", text_tab.count_label.text())
            colours = dialog.tabs["colors"]
            self.assertEqual(colours.model.data(colours.model.index(colours.model.row_of("18H0"), 2),
                                                Qt.DisplayRole), "FFA29895")
            roster = dialog.tabs["roster"]
            self.assertEqual(roster.roster_combo.count(), 1)
            self.assertEqual(roster.model.rowCount(), 3)
            playbooks = dialog.tabs["playbooks"]
            self.assertIn("not built", playbooks.catalogue_label.text())
            self.assertEqual(playbooks.model.rowCount(), 0)
            text_tab.search.setText("options")
            self.assertEqual(text_tab.model.rowCount(), 1)
            text_tab.search.setText("")
            self.assertEqual(dialog.build_page.destination.text(),
                             str(self.iso.parent / "source-modded.iso"))
        finally:
            dialog.done(0)

    def test_an_over_budget_edit_is_refused_inline_and_build_waits_for_a_plan(self) -> None:
        dialog = gui.Ps2DiscStudioDialog(host=self._service())
        try:
            self._opened(dialog)
            text_tab = dialog.tabs["text"]
            text_tab.table.selectRow(0)
            self.app.processEvents()
            self.assertIn("Up to 4 characters", text_tab.budget_label.text())
            text_tab.text_edit.setPlainText("MENUS")
            text_tab._validate()
            self.assertIn("1 over the budget of 4", text_tab.refusal_label.text())
            self.assertIn("shorten", text_tab.refusal_label.text())
            self.assertFalse(text_tab.add_button.isEnabled())
            self.assertIn("1 over the budget", text_tab.remaining_label.text())
            text_tab.text_edit.setPlainText("PLAY")
            text_tab._validate()
            self.assertEqual(text_tab.refusal_label.text(), "")
            self.assertTrue(text_tab.add_button.isEnabled())
            text_tab._add()
            self.assertEqual(text_tab.staged_list.count(), 1)
            self.assertIn('"new_text": "PLAY"', text_tab.preview.toPlainText())
            self.assertNotIn("MENU", text_tab.preview.toPlainText(), "the recipe carries the user's value only")
            self.assertTrue(dialog.build_page.check_button.isEnabled())
            self.assertFalse(dialog.build_page.build_button.isEnabled(), "Build waits for a clean check")
            self.assertIn("not checked yet", dialog.build_page.queue_label.text())
            dialog._check_everything()
            self._settle(dialog)
            self.assertTrue(dialog.build_page.build_button.isEnabled())
            self.assertIn("checked clean", dialog.status_label.text())
            self.assertEqual(dialog.build_page.queue.item(0, 2).text(), "yes")
            # Editing again stales the plan: Build is withdrawn until the next check.
            text_tab._clear()
            self.assertFalse(dialog.build_page.build_button.isEnabled())
        finally:
            dialog.done(0)

    def test_a_refused_plan_is_shown_on_the_tab_and_the_queue_not_raised(self) -> None:
        dialog = gui.Ps2DiscStudioDialog(host=self._service())
        real_warning = gui.QMessageBox.warning
        warnings: list = []
        gui.QMessageBox.warning = staticmethod(lambda *args, **kwargs: warnings.append(str(args[2])))
        try:
            self._opened(dialog)
            text_tab = dialog.tabs["text"]
            target = text_tab.model.target_at(0)
            # Bypass the inline check to reach the patcher's own refusal.
            text_tab._staged.append(lanes.StagedEdit("text", target.key, {"new_text": "MENUS"}, "forced"))
            text_tab._refresh_recipe()
            dialog.recipe_changed("text")
            dialog._check_everything()
            self._settle(dialog)
            self.assertIn("Refused", text_tab.plan_label.text())
            self.assertIn("4 UTF-16 code units", text_tab.plan_label.text())
            self.assertEqual(dialog.build_page.queue.item(0, 2).text(), "refused")
            self.assertFalse(dialog.build_page.build_button.isEnabled())
            self.assertEqual(warnings, [], "a refused check is a status line and a queue row, not a modal")
        finally:
            gui.QMessageBox.warning = real_warning
            dialog.done(0)

    def test_a_build_writes_a_new_image_and_shows_the_receipt(self) -> None:
        dialog = gui.Ps2DiscStudioDialog(host=self._service())
        try:
            self._opened(dialog)
            text_tab = dialog.tabs["text"]
            text_tab.table.selectRow(0)
            self.app.processEvents()
            text_tab.text_edit.setPlainText("PLAY")
            text_tab._validate()
            text_tab._add()
            colours = dialog.tabs["colors"]
            colours.table.selectRow(colours.model.row_of("18H0"))
            self.app.processEvents()
            colours.colour_edits["facemask"].setText("#00FF00")
            colours._validate()
            self.assertTrue(colours.add_button.isEnabled())
            colours._add()
            dialog._check_everything()
            self._settle(dialog)
            destination = self.root / "built-from-the-window.iso"
            dialog.build_page.destination.setText(str(destination))
            self.assertIn("1.25 GiB", dialog.build_page.estimate_label.text())
            dialog._build()
            self._settle(dialog, timeout=120.0)
            self.assertTrue(destination.is_file())
            self.assertEqual(destination.stat().st_size, self.iso.stat().st_size)
            self.assertIn("every verifier passed", dialog.status_label.text())
            self.assertIn("text verifier: pass", dialog.build_page.receipt_label.text())
            self.assertIn("colour verifier: PASS", dialog.build_page.receipt_label.text())
            self.assertTrue(dialog.build_page.open_folder_button.isEnabled())
            self.assertEqual(dialog.tab_widget.currentWidget(), dialog.build_page)
            self.assertEqual(self.iso.read_bytes(), fixtures.combined_disc())
        finally:
            dialog.done(0)

    def test_closing_is_refused_while_an_operation_runs(self) -> None:
        dialog = gui.Ps2DiscStudioDialog(host=self._service())
        try:
            dialog._busy = True
            dialog._busy_verb = "Building the new disc image"
            dialog.reject()
            self.assertIn("still running", dialog.status_label.text())
            self.assertEqual(dialog.result(), 0)
        finally:
            dialog._busy = False
            dialog.done(0)

    def test_a_refused_disc_is_reported_not_raised(self) -> None:
        import ps2_iso9660 as iso_lib

        other = self.root / "not_2k5.iso"
        other.write_bytes(iso_lib.build_synthetic_iso())
        service = self._service()
        dialog = gui.Ps2DiscStudioDialog(host=service)
        real_warning = gui.QMessageBox.warning
        warnings: list = []
        gui.QMessageBox.warning = staticmethod(lambda *args, **kwargs: warnings.append(str(args[2])))
        try:
            dialog._open_path(other)
            self._settle(dialog)
            self.assertEqual(len(warnings), 1)
            self.assertIn("VC_20919", dialog.status_label.text())
            self.assertIn("was not changed", warnings[0])
            self.assertFalse(service.is_open)
            self.assertTrue(dialog.open_button.isEnabled())
        finally:
            gui.QMessageBox.warning = real_warning
            dialog.done(0)


if __name__ == "__main__":
    unittest.main()

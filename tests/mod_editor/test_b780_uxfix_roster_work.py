"""b780-uxfix: unsaved ★ Rosters work is always noticed (the Studio reviewer's two findings in the close prompt).

* The undo stack keeps at most 500 entries, so len(_done) stopped at 500 and an export snapshot taken there kept
  matching while the user went on editing: the title lost its "*" and closing went ahead without a prompt. The stack
  now has a revision that only goes up.
* Save disc copy… / Save Xbox save copy… hold the edits too: after one the work counts as saved.
* Undo and Redo move the title's "*" with them.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.gui.roster_editor_panel_qt import RosterEditorPanel, UndoEntry, UndoStack  # noqa: E402
from mod_editor.gui.studio_qt import StudioMainWindow  # noqa: E402
from test_nfl2k5_roster_records import synthetic_body  # noqa: E402

_APP: list[QApplication] = []


def _host(panel):
    """The Studio's own guard methods over a real ★ Rosters panel."""
    host = SimpleNamespace(_roster_editor_panel=panel, _prompt_roster_work_lost=mock.Mock(return_value=False))
    host._roster_work_unsaved = lambda: StudioMainWindow._roster_work_unsaved(host)
    host._roster_work_summary = lambda: StudioMainWindow._roster_work_summary(host)
    return host


class UndoStackTests(unittest.TestCase):
    def test_the_revision_keeps_counting_past_the_500_entry_limit(self):
        stack = UndoStack(limit=500)
        for _ in range(500):
            stack.push(UndoEntry("edit", lambda: None, lambda: None))
        at_limit = (len(stack._done), stack.revision)
        stack.push(UndoEntry("edit", lambda: None, lambda: None))
        self.assertEqual(len(stack._done), 500)                 # the old snapshot key could not see this edit
        self.assertNotEqual(stack.revision, at_limit[1])

    def test_undo_and_redo_report_a_change(self):
        changes = []
        stack = UndoStack(on_change=lambda: changes.append(1))
        stack.push(UndoEntry("edit", lambda: None, lambda: None))
        stack.undo()
        stack.redo()
        self.assertEqual(len(changes), 3)
        before = stack.revision
        stack.clear()                                            # a reset moves the revision on, quietly
        self.assertGreater(stack.revision, before)
        self.assertEqual(len(changes), 3)


class RosterWorkTests(unittest.TestCase):
    def setUp(self):
        if not _APP:
            _APP.append(QApplication.instance() or QApplication([]))
        self.panel = RosterEditorPanel()
        self.addCleanup(self.panel.deleteLater)
        self.panel.load_document(rr.load_body(synthetic_body()), label="synthetic")
        self.player = self.panel.document.players[0]
        self.folder = Path(tempfile.mkdtemp(prefix="uxfix-roster-"))

    def _edit(self, count):
        for n in range(count):
            self.panel.set_field(self.player, "jersey", 10 + n % 80)

    def test_an_edit_after_an_export_at_the_500_entry_limit_reads_unsaved_and_asks(self):
        self._edit(500)
        self.panel.save_edits_to(self.folder / "edits.json")
        host = _host(self.panel)
        self.assertFalse(host._roster_work_unsaved())          # exported: saved
        stale = []
        self.panel.roster_edits_stale.connect(lambda: stale.append(True))
        self._edit(1)                                            # the same player again: _dirty does not change
        self.assertTrue(host._roster_work_unsaved())
        self.assertEqual(stale, [True])                          # "the roster changed after edits.json was exported"
        with mock.patch("mod_editor.gui.crash_report.dialog_is_possible", return_value=True), \
             mock.patch("mod_editor.gui.studio_qt.QApplication.platformName", return_value="xcb"):
            self.assertFalse(StudioMainWindow._confirm_roster_work_lost(host, "Closing Mod Studio"))
        host._prompt_roster_work_lost.assert_called_once_with("Closing Mod Studio")

    def test_a_written_disc_or_save_copy_counts_as_saved(self):
        self._edit(3)
        host = _host(self.panel)
        self.assertTrue(host._roster_work_unsaved())
        refreshed = []
        previous = self.panel.undo_stack.on_change
        self.panel.undo_stack.on_change = lambda: (refreshed.append(True), previous())
        with mock.patch.object(RosterEditorPanel, "_write_copy_target", return_value={"written": True}):
            self.assertEqual(self.panel.write_copy_to(self.folder / "copy.iso"), {"written": True})
        self.assertFalse(host._roster_work_unsaved())
        self.assertTrue(refreshed)                               # the Studio title refreshes (its hook on on_change)
        self._edit(1)
        self.assertTrue(host._roster_work_unsaved())
        with mock.patch.object(RosterEditorPanel, "_write_copy_target", side_effect=rr.RosterRecordError("no room")):
            with self.assertRaises(rr.RosterRecordError):
                self.panel.write_copy_to(self.folder / "copy2.iso")
        self.assertTrue(host._roster_work_unsaved())            # a failed copy saves nothing

    def test_undo_back_to_the_export_still_asks_and_redo_moves_the_title(self):
        self._edit(2)
        self.panel.save_edits_to(self.folder / "edits.json")
        changes = []
        previous = self.panel.undo_stack.on_change
        self.panel.undo_stack.on_change = lambda: (changes.append(True), previous())
        self.panel.undo()
        self.assertTrue(changes)                                 # Undo reaches the Studio's title hook
        self.assertTrue(_host(self.panel)._roster_work_unsaved())


if __name__ == "__main__":
    unittest.main()

"""b780 c4-staffui: Fire / Hire / Swap on the Franchise page's Coaches tab, driven offscreen.

Every move goes through the page's widgets or its public methods, lands in the shared undo journal, writes through the
roster page's own "write a copy" path and is read back from the signed copy.  The modal dialogs are replaced by a
callback that fills them in and accepts them (a real ``exec_`` would block an offscreen run).
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import QDialog  # noqa: E402

from mod_editor.core import nfl2k5_franchise_save as fs  # noqa: E402
from mod_editor.gui.franchise_panel_qt import ClubPickerDialog, FireHireDialog, FranchiseEdit  # noqa: E402
from b780_staff_fixture import synthetic_staff_franchise  # noqa: E402
from test_franchise_panel_qt import _PanelCase, written_savegame  # noqa: E402
from test_nfl2k5_franchise_save import FIXTURES, FRANCHISE1  # noqa: E402


def answer(dialog_class, callback):
    """Replace ``dialog_class.exec_`` by: fill the dialog in with ``callback`` and accept it."""

    def fake(self):
        callback(self)
        return QDialog.Accepted

    return mock.patch.object(dialog_class, "exec_", fake)


def select_coach_row(page, name: str) -> None:
    for row in range(page.coach_list.count()):
        if page.coach_list.item(row).text().startswith(name + " "):
            page.coach_list.setCurrentRow(row)
            return
    raise AssertionError(f"{name} is not in the coach list: {[page.coach_list.item(i).text() for i in range(page.coach_list.count())]}")


class StaffMoveTests(_PanelCase):
    def setUp(self) -> None:
        super().setUp()
        self.payload = synthetic_staff_franchise(year_field=7, user_team=0)
        self.load(self.payload)
        self.page.tabs.setCurrentIndex(2)

    def test_the_coach_list_names_every_record_and_the_buttons_follow_the_selection(self) -> None:
        page = self.page
        texts = [page.coach_list.item(i).text() for i in range(page.coach_list.count())]
        self.assertEqual(texts[:4], ["Bill Belichick — IND", "Andy Reid — ATL", "Kyle Shanahan — SF", "Mike Holmgren — no team"])
        self.assertEqual(len(texts), 6)
        select_coach_row(page, "Bill Belichick")
        self.assertEqual([b.isEnabled() for b in (page.coach_swap_button, page.coach_fire_button, page.coach_hire_button)],
                         [True, True, False])
        select_coach_row(page, "Mike Holmgren")
        self.assertEqual([b.isEnabled() for b in (page.coach_swap_button, page.coach_fire_button, page.coach_hire_button)],
                         [False, False, True])
        self.assertIn("has no club", page.coach_move_label.text())
        select_coach_row(page, "xxxxxxxxxx")
        self.assertEqual([b.isEnabled() for b in (page.coach_swap_button, page.coach_fire_button, page.coach_hire_button)],
                         [False, False, False])
        self.assertIn("empty coach records", page.coach_move_label.text())

    def test_a_swap_through_the_widgets_is_journaled_undone_written_and_reloaded(self) -> None:
        page = self.page
        select_coach_row(page, "Bill Belichick")
        seen = {}

        def pick(dialog: ClubPickerDialog) -> None:
            seen["rows"] = [dialog.list.item(i).text() for i in range(dialog.list.count())]
            seen["ok_before"] = dialog.ok_button.isEnabled()
            dialog.list.setCurrentRow(1)                                   # SF
            seen["summary"] = dialog.summary.text()

        with answer(ClubPickerDialog, pick):
            page.coach_swap_button.click()
        self.assertEqual(seen["rows"], ["ATL · City1 Team1 · Andy Reid", "SF · City2 Team2 · Kyle Shanahan"])
        self.assertFalse(seen["ok_before"])
        self.assertEqual(seen["summary"], "Bill Belichick goes to SF and Kyle Shanahan goes to IND. Nobody loses a job.")
        assert page.save is not None
        self.assertEqual(page.save.head_coaches(), {0: 2, 1: 1, 2: 0})
        label = "IND and SF swap head coaches: Bill Belichick goes to SF, Kyle Shanahan goes to IND"
        self.assertEqual(page.edit_labels(), [label])
        self.assertEqual(page.status_label.text(), label)
        self.assertEqual(page.dirty_label.text(), "● 1 franchise edit (not yet written)")
        # the list follows the move and keeps the selected coach selected
        texts = [page.coach_list.item(i).text() for i in range(page.coach_list.count())]
        self.assertEqual(texts[:3], ["Kyle Shanahan — IND", "Andy Reid — ATL", "Bill Belichick — SF"])
        self.assertEqual(page.coach_name_label.text(), "Bill Belichick")
        self.assertIn("SF", page.coach_teams_label.text())
        # one undo puts the bytes back, redo repeats it
        self.assertEqual(self.panel.undo(), label)
        assert page.save is not None
        self.assertEqual(page.save.to_bytes(), self.payload)
        self.assertEqual(page.coach_list.item(0).text(), "Bill Belichick — IND")
        self.assertEqual(self.panel.redo(), label)
        assert page.save is not None
        self.assertEqual(page.save.head_coaches(), {0: 2, 1: 1, 2: 0})
        # written through the roster page: signed, byte-exact with the core move, and it reloads
        receipt, written = self.write()
        expected = fs.FranchiseSave(self.payload)
        expected.swap_head_coaches(0, 2)
        self.assertEqual(written, expected.to_bytes())
        self.assertEqual(receipt["franchise_edits"], [label])
        self.assertTrue(self.panel.load_save(self.root / "copy"))
        back = self.page.save
        assert back is not None
        self.assertEqual(back.coach_for_team(0).name, "Kyle Shanahan")
        self.assertEqual(back.coach_for_team(2).name, "Bill Belichick")
        self.assertEqual(self.page.coach_list.item(0).text(), "Kyle Shanahan — IND")

    def test_swap_options_reach_the_save(self) -> None:
        page = self.page
        self.assertTrue(page.swap_head_coaches(0, 1, restart=False, announcer=False))
        assert page.save is not None
        reid = page.save.coach_for_team(0)
        self.assertEqual((reid.fields["seasons_with_team"], reid.flags), (13, 0))
        self.assertTrue(page.swap_head_coaches(1, 2))
        kyle = page.save.coach_for_team(1)
        self.assertEqual((kyle.fields["seasons_with_team"], bool(kyle.flags & fs.COACH_FLAG_NO_NAME)), (0, True))

    def test_a_refused_move_says_why_and_changes_nothing(self) -> None:
        page = self.page
        self.assertFalse(page.swap_head_coaches(0, 0))
        self.assertIn("Refused: pick two different clubs", page.status_label.text())
        self.assertFalse(page.swap_head_coaches(0, 9))
        self.assertIn("Refused", page.status_label.text())
        self.assertFalse(page.fire_and_hire(0, 4))
        self.assertIn("empty placeholder", page.status_label.text())
        self.assertFalse(page.fire_and_hire(0, 99))
        self.assertIn("Refused: no coach 99", page.status_label.text())
        self.assertFalse(page.fire_and_replace(0, "", "Quinn"))
        self.assertIn("first name", page.status_label.text())
        assert page.save is not None
        self.assertEqual(page.save.to_bytes(), self.payload)
        self.assertEqual(page.edit_labels(), [])
        self.assertEqual(page.dirty_label.text(), "")

    def test_fire_and_hire_a_coach_who_has_no_club(self) -> None:
        page = self.page
        select_coach_row(page, "Mike Holmgren")
        seen = {}

        def pick(dialog: ClubPickerDialog) -> None:
            dialog.list.setCurrentRow(1)                                   # ATL
            seen["summary"] = dialog.summary.text()
            dialog.restart_check.setChecked(False)

        with answer(ClubPickerDialog, pick):
            page.coach_hire_button.click()
        self.assertEqual(seen["summary"], "Andy Reid is fired and stays on file. Mike Holmgren becomes head coach of ATL.")
        label = "ATL: Andy Reid fired, Mike Holmgren hired"
        self.assertEqual(page.edit_labels(), [label])
        assert page.save is not None
        self.assertEqual(page.save.coach_for_team(1).name, "Mike Holmgren")
        self.assertEqual(page.save.coach_for_team(1).fields["seasons_with_team"], 8)              # restart was unticked
        self.assertEqual([c.name for c in page.save.unemployed_coaches()], ["Andy Reid"])
        self.assertEqual(page.coach_name_label.text(), "Mike Holmgren")
        # the fired coach is on file and can be hired by the dialog on the other side
        select_coach_row(page, "Kyle Shanahan")
        seen.clear()

        def choose_file(dialog: FireHireDialog) -> None:
            seen["file"] = [dialog.file_combo.itemText(i) for i in range(dialog.file_combo.count())]
            seen["radio"] = (dialog.file_radio.isChecked(), dialog.new_radio.isChecked())

        with answer(FireHireDialog, choose_file):
            page.coach_fire_button.click()
        self.assertEqual(seen["file"], ["Andy Reid (on file, no club)"])
        self.assertEqual(seen["radio"], (True, False))
        self.assertEqual(page.edit_labels(), [label, "SF: Kyle Shanahan fired, Andy Reid hired"])
        self.assertEqual([c.name for c in page.save.unemployed_coaches()], ["Kyle Shanahan"])

    def test_fire_and_hire_a_new_coach_through_the_dialog(self) -> None:
        page = self.page
        select_coach_row(page, "Andy Reid")
        seen = {}

        def new_coach(dialog: FireHireDialog) -> None:
            seen["file_enabled"] = dialog.file_radio.isEnabled()
            seen["checked"] = (dialog.file_radio.isChecked(), dialog.new_radio.isChecked())
            seen["ok_empty"] = dialog.ok_button.isEnabled()
            dialog.new_radio.setChecked(True)
            dialog.first_field.setText("Dan")
            dialog.last_field.setText("Quinn")
            dialog.bio_fields[0].setText("A defensive mind.")
            seen["ok_filled"] = dialog.ok_button.isEnabled()

        # Mike Holmgren is on file, so the file choice exists; the user picks "a new coach"
        with answer(FireHireDialog, new_coach):
            page.coach_fire_button.click()
        self.assertTrue(seen["file_enabled"])
        self.assertTrue(seen["ok_filled"])
        label = "ATL: Andy Reid fired, Dan Quinn hired (new coach)"
        self.assertEqual(page.edit_labels(), [label])
        assert page.save is not None
        coach = page.save.coach_for_team(1)
        self.assertEqual((coach.name, coach.info[0], coach.fields["wins"], coach.fields["photo"]),
                         ("Dan Quinn", "A defensive mind.", 0, fs.COACH_NO_PHOTO))
        self.assertEqual([c.name for c in page.save.coaches()][:4], ["Bill Belichick", "Dan Quinn", "Kyle Shanahan", "Mike Holmgren"])
        receipt, written = self.write()
        expected = fs.FranchiseSave(self.payload)
        expected.replace_head_coach(1, "Dan", "Quinn", ["A defensive mind."])
        self.assertEqual(written, expected.to_bytes())
        self.assertTrue(self.panel.load_save(self.root / "copy"))
        self.assertEqual(self.page.save.coach_for_team(1).name, "Dan Quinn")

    def test_the_dialog_explains_why_a_new_name_cannot_be_written(self) -> None:
        self.load(synthetic_staff_franchise(contiguous=False), name="pieces")
        page = self.page
        page.tabs.setCurrentIndex(2)
        select_coach_row(page, "Bill Belichick")
        seen = {}

        def look(dialog: FireHireDialog) -> None:
            seen["new_enabled"] = dialog.new_radio.isEnabled()
            seen["note"] = dialog.new_note.text()
            seen["ok"] = dialog.ok_button.isEnabled()
            seen["choice"] = dialog.choice()

        with answer(FireHireDialog, look):
            page.coach_fire_button.click()
        self.assertFalse(seen["new_enabled"])
        self.assertIn("more than one place", seen["note"])
        self.assertTrue(seen["ok"])                                                   # Mike Holmgren is still on file
        self.assertEqual(seen["choice"]["kind"], "file")
        self.assertEqual(page.edit_labels(), ["IND: Bill Belichick fired, Mike Holmgren hired"])

    def test_the_dialog_with_nothing_to_choose_cannot_be_accepted(self) -> None:
        dialog = FireHireDialog("IND", "Bill Belichick", [], "this save keeps its coach names in more than one place")
        self.assertFalse(dialog.file_radio.isEnabled())
        self.assertFalse(dialog.new_radio.isEnabled())
        self.assertFalse(dialog.ok_button.isEnabled())
        self.assertIsNone(dialog.choice())
        self.assertIn("No unemployed coaches", dialog.file_note.text())
        dialog = FireHireDialog("IND", "Bill Belichick", [], "")
        self.assertTrue(dialog.new_radio.isChecked())
        self.assertFalse(dialog.ok_button.isEnabled())
        dialog.first_field.setText("Dan")
        self.assertFalse(dialog.ok_button.isEnabled())
        dialog.last_field.setText("Quinn")
        self.assertTrue(dialog.ok_button.isEnabled())
        self.assertEqual(dialog.choice(), {"kind": "new", "first": "Dan", "last": "Quinn", "bio": ["", "", ""]})

    def test_moves_share_the_roster_page_undo_stack_and_the_checks_page(self) -> None:
        page = self.page
        self.assertTrue(page.swap_head_coaches(0, 1))
        self.assertTrue(page.fire_and_replace(2, "Dan", "Quinn"))
        self.assertEqual(self.panel.undo_stack.depth, (2, 0))
        self.assertTrue(self.panel.is_dirty())
        page.tabs.setCurrentIndex(4)
        text = page.checks_text.toPlainText()
        self.assertIn("Franchise edits since load (2):", text)
        self.assertIn("1. IND and ATL swap head coaches: Bill Belichick goes to ATL, Andy Reid goes to IND", text)
        self.assertIn("2. SF: Kyle Shanahan fired, Dan Quinn hired (new coach)", text)
        self.assertIn("Head coach moves: swap, fire and hire: HYPOTHESIS", text)
        self.panel.undo()
        self.panel.undo()
        assert page.save is not None
        self.assertEqual(page.save.to_bytes(), self.payload)
        self.assertEqual(self.panel.redo(), "IND and ATL swap head coaches: Bill Belichick goes to ATL, Andy Reid goes to IND")

    def test_an_unknown_kind_and_the_three_kinds_apply_through_the_journal_record(self) -> None:
        save = fs.FranchiseSave(self.payload)
        FranchiseEdit("coach_swap", "x", {"a": 0, "b": 1}).apply(save)
        FranchiseEdit("coach_hire", "x", {"team": 2, "coach": 3, "restart": False}).apply(save)
        FranchiseEdit("coach_replace", "x", {"team": 0, "first": "Dan", "last": "Quinn", "bio": ["Hi"]}).apply(save)
        self.assertEqual([save.coach_for_team(t).name for t in range(3)], ["Dan Quinn", "Bill Belichick", "Mike Holmgren"])


@unittest.skipUnless(FRANCHISE1.is_file(), f"private Franchise1 fixture missing under {FIXTURES}")
class RealFranchisePanelTests(_PanelCase):
    def test_swap_and_a_new_coach_on_the_year_seven_lions_save_write_signed_and_reload(self) -> None:
        self.assertTrue(self.panel.load_save(FRANCHISE1.parents[3]))
        page = self.page
        assert page.save is not None
        original = FRANCHISE1.read_bytes()
        page.tabs.setCurrentIndex(2)
        names = {t: page.save.coach_for_team(t).name for t in range(32)}
        self.assertTrue(page.swap_head_coaches(18, 0))                            # the Lions and the 49ers
        self.assertTrue(page.fire_and_replace(2, "Dan", "Quinn", ["A defensive mind."]))
        self.assertEqual(page.save.coach_for_team(18).name, names[0])
        self.assertEqual(page.save.coach_for_team(0).name, names[18])
        self.assertEqual(page.coach_list.count(), 35)
        receipt, written = self.write()
        expected = fs.FranchiseSave(original)
        expected.swap_head_coaches(18, 0)
        expected.replace_head_coach(2, "Dan", "Quinn", ["A defensive mind."])
        self.assertEqual(written, expected.to_bytes())
        self.assertEqual(FRANCHISE1.read_bytes(), original)
        self.assertTrue(self.panel.load_save(self.root / "copy"))
        back = self.page.save
        assert back is not None
        self.assertEqual((back.coach_for_team(18).name, back.coach_for_team(2).name), (names[0], "Dan Quinn"))
        self.assertEqual([c.name for c in back.coaches()].count("Dan Quinn"), 1)
        self.assertEqual(self.page.edit_labels(), [])


if __name__ == "__main__":
    unittest.main()

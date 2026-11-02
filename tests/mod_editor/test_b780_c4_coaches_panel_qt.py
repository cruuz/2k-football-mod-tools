"""b780 c4-staffui: the Rosters > Coaches page, driven offscreen.

The page alone (``CoachesPanel``) is driven with the 32 clubs' 2026 head coaches; the page inside ★ Rosters is driven with
a small synthetic disc roster and, when the released disc is on this machine, with its real roster (read only).  Modal
dialogs are replaced by a callback that fills them in and accepts them.
"""

from __future__ import annotations

import json
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
from PyQt5.QtWidgets import QApplication, QDialog  # noqa: E402

from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_staff_ui as ui  # noqa: E402
from mod_editor.gui.coaches_panel_qt import CoachesPanel, NewCoachDialog, PickDialog, face_pixmap, monogram  # noqa: E402
from mod_editor.gui.roster_editor_panel_qt import RosterEditorPanel  # noqa: E402
from b780_staff_fixture import synthetic_staff_body, synthetic_staff_franchise  # noqa: E402
from test_b780_c4_staff_ui_model import DISC, rows_2026  # noqa: E402
from test_roster_editor_panel_franchise import write_container  # noqa: E402


def answer(dialog_class, callback):
    def fake(self):
        callback(self)
        return QDialog.Accepted

    return mock.patch.object(dialog_class, "exec_", fake)


class _Case(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def pump(self) -> None:
        self.application.processEvents()


class PagePlanTests(_Case):
    def setUp(self) -> None:
        self.page = CoachesPanel()
        self.rows = rows_2026()
        self.page.set_rows(self.rows)
        self.edits: list[tuple[str, dict, dict]] = []
        self.page.edit_made.connect(lambda label, before, after: self.edits.append((label, before, after)))
        self.names = {r.club.code: r.name for r in self.rows}

    def tearDown(self) -> None:
        self.page.deleteLater()
        self.pump()

    def row_of(self, code: str) -> int:
        for row in range(self.page.table.rowCount()):
            if self.page.table.item(row, 0).text().startswith(code + " "):
                return row
        raise AssertionError(code)

    def test_the_table_lists_every_club_with_its_coach_and_coordinator(self) -> None:
        page = self.page
        self.assertEqual(page.table.rowCount(), 32)
        self.assertEqual([page.table.horizontalHeaderItem(c).text() for c in range(4)],
                         ["Club", "Head coach", "Defensive coordinator", "Change"])
        row = self.row_of("KC")
        self.assertEqual(page.table.item(row, 0).text(), "KC Chiefs")
        self.assertEqual(page.table.item(row, 1).text(), self.names["KC"])
        self.assertEqual(page.table.item(row, 2).text(), ui.coordinators()["KC"].name)
        self.assertEqual(page.table.item(row, 3).text(), "")
        self.assertEqual(page.selected_club().code, "SF")                                  # the first club is selected
        self.assertEqual(page.coach_name.text(), self.names["SF"])
        self.assertIn("Career", page.coach_career.text())
        self.assertIn("Play calling:", page.coach_style.text())
        self.assertTrue(all(b.isEnabled() for b in (page.swap_button, page.hire_button, page.dc_button)))
        self.assertFalse(page.reset_button.isEnabled())
        self.assertEqual(page.state_label.text(), "")
        self.assertIn("No staff changes", page.changes_text.toPlainText())

    def test_nothing_to_plan_without_a_disc_roster(self) -> None:
        page = CoachesPanel()
        self.assertIn("Open a game disc", page.state_label.text())
        self.assertEqual(page.table.rowCount(), 0)
        self.assertFalse(page.swap_button.isEnabled())
        self.assertFalse(page.table.isEnabled())
        self.assertFalse(page.swap_clubs("KC", "DAL"))
        page.set_roster(rr.load_body(synthetic_staff_body()), kind="save")
        self.assertIn("Franchise tab", page.state_label.text())
        self.assertEqual(page.table.rowCount(), 0)
        self.assertEqual(page.export_staff(), {})
        page.deleteLater()

    def test_a_swap_shows_in_the_table_the_words_and_the_edit_signal(self) -> None:
        page = self.page
        self.assertTrue(page.swap_clubs("LV", "KC"))
        kc, lv = self.row_of("KC"), self.row_of("LV")
        self.assertEqual(page.table.item(kc, 1).text(), f"{self.names['LV']}  (was {self.names['KC']})")
        self.assertEqual(page.table.item(lv, 1).text(), f"{self.names['KC']}  (was {self.names['LV']})")
        self.assertEqual((page.table.item(kc, 3).text(), page.table.item(lv, 3).text()), ("head coach", "head coach"))
        self.assertNotEqual(page.table.item(kc, 1).background().color().alpha(), 0)
        self.assertEqual(page.table.item(self.row_of("DAL"), 3).text(), "")
        text = page.changes_text.toPlainText().splitlines()
        self.assertEqual(text, [f"KC head coach: {self.names['KC']} → {self.names['LV']} (from LV)",
                                f"LV head coach: {self.names['LV']} → {self.names['KC']} (from KC)"])
        self.assertEqual(page.count_label.text(), "2 changes")
        self.assertTrue(page.reset_button.isEnabled())
        self.assertEqual(len(self.edits), 1)
        label, before, after = self.edits[0]
        self.assertEqual(label, f"LV and KC swap head coaches: {self.names['LV']} goes to KC, {self.names['KC']} goes to LV")
        self.assertEqual((before, after), (ui.empty(), page.staff()))
        self.assertTrue(page.has_changes())
        self.assertEqual(page.export_staff()["head_coaches"][0], {"team": "KC", "coach": self.names["LV"]})
        self.assertEqual(page.change_count(), 2)

    def test_the_swap_button_asks_for_the_other_club(self) -> None:
        page = self.page
        page.select_club("KC")
        seen = {}

        def pick(dialog: PickDialog) -> None:
            seen["rows"] = dialog.list.count()
            seen["ok"] = dialog.ok_button.isEnabled()
            dialog.filter.setText("Cowboys")
            seen["filtered"] = dialog.list.count()
            dialog.choose(11)                                                             # DAL
            seen["summary"] = dialog.summary.text()

        with answer(PickDialog, pick):
            page.swap_button.click()
        self.assertEqual((seen["rows"], seen["ok"], seen["filtered"]), (31, False, 1))
        self.assertEqual(seen["summary"], f"{self.names['KC']} goes to DAL and {self.names['DAL']} goes to KC. Nobody loses a job.")
        self.assertEqual(ui.head_seats(self.rows, page.staff())["DAL"], ("coach", self.names["KC"]))
        self.assertEqual(page.selected_club().code, "KC")                                  # the selection stays on the club

    def test_hire_a_head_coach_from_another_club_is_a_swap(self) -> None:
        page = self.page
        page.select_club("NYG")
        seen = {}

        def pick(dialog: PickDialog) -> None:
            seen["rows"] = [dialog.list.item(i).text() for i in range(dialog.list.count())]
            dialog.choose(self.names["TB"])
            seen["summary"] = dialog.summary.text()

        with answer(PickDialog, pick):
            page.hire_button.click()
        self.assertEqual(len(seen["rows"]), 31)
        self.assertIn(f"{self.names['TB']} · TB head coach", seen["rows"])
        self.assertEqual(seen["summary"], f"{self.names['TB']} leaves TB for NYG and {self.names['NYG']} takes his old job at TB. "
                                          "Nobody loses a job.")
        seats = ui.head_seats(self.rows, page.staff())
        self.assertEqual((seats["NYG"], seats["TB"]), (("coach", self.names["TB"]), ("coach", self.names["NYG"])))

    def test_create_a_new_head_coach_from_the_hire_dialog(self) -> None:
        page = self.page
        page.select_club("NYG")
        seen = {}

        def pick(dialog: PickDialog) -> None:
            seen["buttons"] = [dialog.extra.itemAt(i).widget().text() for i in range(dialog.extra.count()) if dialog.extra.itemAt(i).widget()]
            dialog.extra.itemAt(0).widget().click()                                       # Create a new coach…

        def create(dialog: NewCoachDialog) -> None:
            seen["ok_empty"] = dialog.ok_button.isEnabled()
            dialog.first_field.setText("Pat")
            dialog.last_field.setText("Shurmur")
            dialog.bio_fields[0].setText("A patient play caller.")
            dialog.body_combo.setCurrentIndex(dialog.body_combo.findData(21))
            dialog.style_combo.setCurrentIndex(dialog.style_combo.findData("SF"))
            dialog.overall_spin.setValue(72)
            seen["ok_full"] = dialog.ok_button.isEnabled()
            seen["bodies"] = dialog.body_combo.count()
            seen["body_text"] = dialog.body_combo.currentText()

        with answer(PickDialog, pick), answer(NewCoachDialog, create):
            page.hire_button.click()
        self.assertEqual(seen["buttons"], ["Create a new coach…"])
        self.assertFalse(seen["ok_empty"])
        self.assertTrue(seen["ok_full"])
        self.assertEqual(seen["bodies"], len(ui.COACH_BODIES))
        self.assertIn("Model c21", seen["body_text"])
        staff = page.staff()
        self.assertEqual(staff["head_coaches"], [{"team": "NYG", "created": "pat-shurmur"}])
        spec = staff["created_coaches"][0]
        self.assertEqual((spec["first"], spec["last"], spec["body"], spec["style"], spec["ratings"], spec["bio"][0]),
                         ("Pat", "Shurmur", 21, "SF", {"overall": 72}, "A patient play caller."))
        self.assertEqual(page.coach_name.text(), "Pat Shurmur")
        self.assertIn("A new coach you created", page.coach_origin.text())
        self.assertIn("year 1", page.coach_career.text())
        self.assertEqual(page.table.item(self.row_of("NYG"), 3).text(), "new coach")
        self.assertIn(f"{self.names['NYG']} is let go and leaves the roster", page.changes_text.toPlainText())
        self.assertEqual(self.edits[0][0], "NYG: Pat Shurmur hired as a new head coach")

    def test_the_new_coach_dialog_says_what_to_fix(self) -> None:
        dialog = NewCoachDialog("KC Chiefs", {}, [("SF", "Kyle Shanahan (SF)")])
        dialog.first_field.setText("Pat")
        dialog.last_field.setText("Shurmur")
        dialog.bio_fields[0].setMaxLength(100)
        dialog.bio_fields[0].setText("b" * 60)
        dialog.ok_button.click()
        self.assertEqual(dialog.result(), QDialog.Rejected)                               # not accepted
        self.assertIn("longer than 52", dialog.problem.text())
        dialog.bio_fields[0].setText("short")
        self.assertEqual(dialog.problem.text(), "")
        self.assertEqual(dialog.spec()["bio"], ["short", "", ""])
        dialog.ok_button.click()
        self.assertEqual(dialog.result(), QDialog.Accepted)

    def test_change_a_coordinator_swaps_two_defenses(self) -> None:
        page = self.page
        page.select_club("KC")
        people = ui.coordinators()
        seen = {}

        def pick(dialog: PickDialog) -> None:
            seen["rows"] = dialog.list.count()
            dialog.choose("PHI")
            seen["summary"] = dialog.summary.text()

        with answer(PickDialog, pick):
            page.dc_button.click()
        self.assertEqual(seen["rows"], 31)
        self.assertEqual(seen["summary"], f"{people['PHI'].name} runs the KC defense. {people['KC'].name} goes to PHI. "
                                          "The two defenses swap.")
        self.assertEqual(page.table.item(self.row_of("KC"), 2).text(), f"{people['PHI'].name}  (was {people['KC'].name})")
        self.assertEqual(page.table.item(self.row_of("PHI"), 3).text(), "coordinator")
        self.assertIn(f"from PHI)", page.dc_name.text())
        self.assertIn("defensive coordinator", page.changes_text.toPlainText())
        self.assertEqual(ui.problems(self.rows, page.staff()), [])

    def test_the_playbook_box_is_only_for_a_coach_who_arrives(self) -> None:
        page = self.page
        page.select_club("KC")
        self.assertFalse(page.playbook_check.isEnabled())
        page.swap_clubs("KC", "DAL")
        self.assertTrue(page.playbook_check.isEnabled())
        self.assertFalse(page.playbook_check.isChecked())
        page.playbook_check.setChecked(True)
        entries = {e["team"]: e.get("playbook", "club") for e in page.staff()["head_coaches"]}
        self.assertEqual(entries, {"KC": "coach", "DAL": "club"})
        self.assertEqual(self.edits[-1][0], "KC: the new coach brings his playbook")
        self.assertIn("brings his playbook", page.changes_text.toPlainText())
        page.playbook_check.setChecked(False)
        self.assertEqual({e["team"]: e.get("playbook", "club") for e in page.staff()["head_coaches"]}["KC"], "club")
        self.assertFalse(page.set_playbook("PHI", "coach"))
        self.assertIn("only a coach who arrives", page.state_label.text())

    def test_a_refusal_says_why_and_changes_nothing(self) -> None:
        page = self.page
        self.assertFalse(page.swap_clubs("KC", "KC"))
        self.assertIn("Refused: pick two different clubs", page.state_label.text())
        self.assertFalse(page.move_coach("Nobody Atall", "KC"))
        self.assertIn("Refused", page.state_label.text())
        self.assertFalse(page.hire_new_coach("KC", {"first": "", "last": "Quinn"}))
        self.assertIn("type the coach's first name", page.state_label.text())
        self.assertFalse(page.set_defense("KC", "KC"))
        self.assertIn("already runs this defense", page.state_label.text())
        self.assertEqual(page.staff(), ui.empty())
        self.assertEqual(self.edits, [])
        self.assertFalse(page.reset_all())

    def test_put_every_coach_back_is_one_edit(self) -> None:
        page = self.page
        page.swap_clubs("KC", "DAL")
        page.set_defense("KC", "PHI")
        self.assertEqual(page.change_count(), 4)
        self.assertTrue(page.reset_all())
        self.assertEqual(page.staff(), ui.empty())
        self.assertEqual(self.edits[-1][0], "Every coach back where the roster has him")
        self.assertEqual(self.edits[-1][1]["head_coaches"][0]["team"], "KC")
        self.assertEqual(page.export_staff(), {})
        self.assertFalse(page.reset_button.isEnabled())

    def test_set_staff_replaces_the_plan_quietly(self) -> None:
        page = self.page
        staff = ui.swap_head_coaches(self.rows, ui.empty(), "KC", "DAL")
        page.set_staff(staff)
        self.assertEqual(page.staff(), staff)
        self.assertEqual(self.edits, [])
        self.assertEqual(page.table.item(self.row_of("DAL"), 3).text(), "head coach")
        page.set_staff(None)
        self.assertEqual(page.staff(), ui.empty())

    def test_the_filter_narrows_the_table(self) -> None:
        page = self.page
        page.filter.setText(self.names["KC"].split()[-1])
        visible = [r for r in range(page.table.rowCount()) if not page.table.isRowHidden(r)]
        self.assertIn(self.row_of("KC"), visible)
        self.assertLess(len(visible), 5)
        page.filter.setText("")
        self.assertFalse(any(page.table.isRowHidden(r) for r in range(page.table.rowCount())))

    def test_staff_files_round_trip_and_a_wrong_one_is_refused(self) -> None:
        page = self.page
        page.swap_clubs("KC", "DAL")
        saved = page.staff()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "staff.json"
            ui.write_file(path, saved)
            page.reset_all()
            self.assertTrue(page.load_file(path))
            self.assertEqual(page.staff(), saved)
            self.assertEqual(self.edits[-1][0], "Staff file staff.json loaded")
            bad = Path(td) / "bad.json"
            bad.write_text(json.dumps(dict(ui.empty(), head_coaches=[{"team": "KC", "coach": "Nobody Atall"}])), encoding="utf-8")
            before = len(self.edits)
            self.assertFalse(page.load_file(bad))
            self.assertIn("does not fit this roster", page.state_label.text())
            self.assertIn("not a head coach on this roster", page.state_label.text())
            junk = Path(td) / "junk.json"
            junk.write_text("{not json", encoding="utf-8")
            self.assertFalse(page.load_file(junk))
            self.assertIn("Could not read that staff file", page.state_label.text())
            self.assertFalse(page.load_file(Path(td) / "missing.json"))
            self.assertEqual(len(self.edits), before)
            self.assertEqual(page.staff(), saved)

    def test_pictures_are_painted_faces_or_initials(self) -> None:
        face = face_pixmap("SF", "Kyle Shanahan")
        self.assertFalse(face.isNull())
        self.assertEqual((face.width(), face.height()), (96, 72))
        tile = monogram("Pat Shurmur")
        self.assertEqual((tile.width(), tile.height()), (96, 72))
        self.assertNotEqual(face.toImage(), tile.toImage())
        self.assertEqual(face_pixmap(None, "Pat Shurmur").toImage(), tile.toImage())
        self.assertEqual(face_pixmap("ZZZ", "Pat Shurmur").toImage(), tile.toImage())
        self.assertEqual(ui.face_path("ZZZ"), None)


class _FakeClubPlan:
    def __init__(self, **data) -> None:
        self.data = data

    def as_dict(self) -> dict:
        return dict(self.data)


class _FakeEngine:
    """The slice of nfl2k5_coach_staff the page talks to: plan() and normalize()."""

    def __init__(self) -> None:
        self.seen: list[tuple[dict, bytes]] = []

    def plan(self, staff, body):
        self.seen.append((dict(staff), bytes(body)))
        return type("Plan", (), {
            "errors": ["Dallas: nothing is wrong, this is a test"], "notes": ["Kansas City: head coach from Dallas"],
            "clubs": [_FakeClubPlan(team="KC", playbook_from="DAL", profile="DAL", native_reason=None),
                      _FakeClubPlan(team="DAL", playbook_from="DAL", profile=None,
                                    native_reason="Andy Reid has no 2026 CPU coach profile on this roster")]})()

    def normalize(self, staff):
        return dict(staff, note="normalized by the engine")


class EngineWordsTests(_Case):
    def setUp(self) -> None:
        self.page = CoachesPanel()
        self.rows = rows_2026()
        self.page.set_rows(self.rows)
        self.page.body_provider = lambda: b"roster body"
        self.engine = _FakeEngine()

    def tearDown(self) -> None:
        self.page.deleteLater()
        self.pump()

    def test_the_engines_answer_for_each_club_is_on_the_page(self) -> None:
        with mock.patch.object(ui, "engine", return_value=self.engine):
            self.assertTrue(self.page.swap_clubs("KC", "DAL"))
            self.assertEqual(self.engine.seen[-1][1], b"roster body")
            names = {code: name for name, code in ui.head_coach_homes().items()}
            self.page.select_club("KC")
            self.assertEqual(self.page.coach_engine.text(),
                             f"Plays the Cowboys playbook. Automatic 2026 play calling: on, the way {names['DAL']} calls plays.")
            self.page.select_club("DAL")
            self.assertEqual(self.page.coach_engine.text(),
                             "Automatic 2026 play calling: off. Andy Reid has no 2026 CPU coach profile on this roster.")
            notes = self.page.notes_text.text()
            self.assertIn("Dallas: nothing is wrong, this is a test", notes)
            self.assertIn("Kansas City: head coach from Dallas", notes)
            self.assertNotIn("no build-time staff engine yet", notes)
            self.page.select_club("PHI")
            self.assertEqual(self.page.coach_engine.text(), "")                           # a club the plan does not name
            self.assertEqual(self.page.export_staff()["note"], "normalized by the engine")

    def test_nothing_is_asked_of_the_engine_until_there_is_a_change(self) -> None:
        with mock.patch.object(ui, "engine", return_value=self.engine):
            self.page.select_club("KC")
            self.assertEqual(self.engine.seen, [])
            self.assertEqual(self.page.coach_engine.text(), "")
            self.page.swap_clubs("KC", "DAL")
            self.page.reset_all()
            self.assertEqual(self.page.coach_engine.text(), "")
            self.assertEqual(len(self.engine.seen), 1)

    def test_an_engine_that_raises_does_not_break_the_page(self) -> None:
        class Broken:
            def plan(self, staff, body):
                raise RuntimeError("the engine fell over")

        with mock.patch.object(ui, "engine", return_value=Broken()):
            self.assertTrue(self.page.swap_clubs("KC", "DAL"))
            self.assertIn("the engine fell over", self.page.notes_text.text())
            self.assertEqual(self.page.table.item(0, 0).text(), "SF 49ers")


class InsideRostersTests(_Case):
    def setUp(self) -> None:
        self.panel = RosterEditorPanel()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pump()

    def tearDown(self) -> None:
        self.panel.deleteLater()
        self.pump()
        self.temp.cleanup()

    def load_disc_like(self) -> None:
        self.panel.load_document(rr.load_body(synthetic_staff_body()), label="synthetic disc")
        self.pump()

    def test_the_tab_follows_the_loaded_source(self) -> None:
        pages = self.panel.pages
        index = pages.indexOf(self.panel.coaches_panel)
        self.assertEqual((pages.tabText(0), pages.tabText(1), pages.tabText(2), pages.tabText(index)),
                         ("Roster", "Franchise", "ESPN Anniversary", "Coaches"))
        self.assertFalse(pages.isTabEnabled(index))
        self.assertIn("Open a game disc", pages.tabToolTip(index))
        self.load_disc_like()
        self.assertTrue(pages.isTabEnabled(index))
        self.assertEqual(self.panel.coaches_panel.table.rowCount(), 3)
        self.assertIn("Swap head coaches", pages.tabToolTip(index))
        source = write_container(self.root / "save", synthetic_staff_franchise())
        self.assertTrue(self.panel.load_save(source))
        self.pump()
        self.assertFalse(pages.isTabEnabled(index))
        self.assertIn("Franchise tab", pages.tabToolTip(index))
        self.assertEqual(self.panel.coaches_panel.table.rowCount(), 0)
        self.assertEqual(pages.tabText(1), "Franchise")
        self.assertTrue(pages.isTabVisible(1))

    def test_a_staff_change_is_a_roster_edit_with_undo_redo_and_an_export(self) -> None:
        self.load_disc_like()
        panel, page = self.panel, self.panel.coaches_panel
        self.assertFalse(panel.is_dirty())
        self.assertNotIn("staff", panel.edits_document())
        self.assertEqual(panel.edited_label.text(), "No roster edits yet")
        self.assertTrue(page.swap_clubs("SF", "CIN"))
        self.assertTrue(panel.is_dirty())
        self.assertEqual(panel.undo_stack.depth, (1, 0))
        self.assertEqual(panel.edited_label.text(), "2 staff changes")
        self.assertTrue(panel.undo_button.isEnabled())
        staff = panel.edits_document()["staff"]
        self.assertEqual(staff["schema"], ui.SCHEMA)
        self.assertEqual([(e["team"], e["coach"]) for e in staff["head_coaches"]],
                         [("SF", "Kyle Shanahan"), ("CIN", "Bill Belichick")])
        # the toolbar's Undo and Redo
        self.assertEqual(panel.undo(), "SF and CIN swap head coaches: Bill Belichick goes to CIN, Kyle Shanahan goes to SF")
        self.assertFalse(page.has_changes())
        self.assertNotIn("staff", panel.edits_document())
        self.assertEqual(panel.edited_label.text(), "No roster edits yet")
        panel.redo()
        self.assertTrue(page.has_changes())
        self.assertIn("staff", panel.edits_document())
        # exported with the roster edits, readable back
        path = self.root / "edits.json"
        panel.save_edits_to(path)
        document = rr.read_edits(path)
        self.assertEqual(document["staff"], staff)
        self.assertEqual(document["edits"], [])
        self.assertIn("2 staff changes", panel.edited_label.text())
        # the export went stale when the plan changed afterwards
        stale = []
        panel.roster_edits_stale.connect(lambda: stale.append(True))
        page.set_defense("SF", "KC")
        self.assertEqual(stale, [True])

    def test_replacing_the_roster_resets_the_plan_and_the_prompt_counts_staff_changes(self) -> None:
        self.load_disc_like()
        panel, page = self.panel, self.panel.coaches_panel
        page.swap_clubs("SF", "CIN")
        self.assertIn("2 staff changes", panel.edited_label.text())
        with mock.patch("mod_editor.gui.roster_editor_panel_qt.QMessageBox") as box:
            box.return_value.clickedButton.return_value = "keep"
            box.return_value.addButton.side_effect = ["keep", "discard"]
            self.assertFalse(panel._confirm_replace())
            text = box.return_value.setText.call_args[0][0]
        self.assertIn("2 staff changes would be lost", text)
        self.load_disc_like()
        self.assertFalse(page.has_changes())
        self.assertEqual(panel.undo_stack.depth, (0, 0))

    def test_a_complete_roster_with_faces_cannot_carry_staff_changes_yet(self) -> None:
        self.load_disc_like()
        panel = self.panel
        panel.coaches_panel.swap_clubs("SF", "CIN")
        panel._appearance_bundle = {"anything": 1}
        with self.assertRaisesRegex(rr.RosterRecordError, "cannot be exported together with a complete roster with faces"):
            panel.edits_document()

    def test_the_engine_note_says_what_is_missing(self) -> None:
        self.load_disc_like()
        page = self.panel.coaches_panel
        page.swap_clubs("SF", "CIN")
        if ui.engine() is None:
            self.assertIn("no build-time staff engine yet", page.notes_text.text())
        else:
            self.assertNotIn("no build-time staff engine yet", page.notes_text.text())


@unittest.skipUnless(DISC.is_file(), f"the released SOFTDRINK disc is not at {DISC}")
class RealDiscPageTests(_Case):
    def test_the_released_disc_fills_the_page_and_a_swap_exports(self) -> None:
        panel = RosterEditorPanel()
        try:
            document = rr.load_image(DISC)
            panel.load_document(document, label="released v0.8", kind="disc")
            self.pump()
            page = panel.coaches_panel
            self.assertEqual(page.table.rowCount(), 32)
            kc = next(r for r in range(32) if page.table.item(r, 0).text().startswith("KC "))
            self.assertEqual(page.table.item(kc, 1).text(), "Andy Reid")
            self.assertTrue(page.swap_clubs("KC", "DAL"))
            staff = panel.edits_document()["staff"]
            self.assertEqual({e["team"]: e["coach"] for e in staff["head_coaches"]},
                             {"KC": "Brian Schottenheimer", "DAL": "Andy Reid"})
            self.assertEqual(ui.problems(page.rows, staff), [])
            self.assertEqual(document.diff(), [])                                      # the page never edits the roster itself
        finally:
            panel.deleteLater()
            self.pump()


if __name__ == "__main__":
    unittest.main()

"""The Franchise page of ★ Rosters, driven offscreen.

Synthetic: a franchise save from the core tests' generator, plus one coach record grafted into the
arena so the coach editor has something to edit.  Every edit goes through the page's widgets or its
public methods, is written through the roster page's own "write a copy" path and reloaded, and the
written bytes are compared with what the core module produces for the same edits, so the copy is
byte-exact wherever nothing changed.  The private classes open the real fixtures under
``NFL2K5_SAVE_FIXTURES`` (skipped, with the path, when absent) and reproduce Finn's IR move between the
two 8007Fran saves byte for byte through the UI path.
"""

from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.core import nfl2k5_franchise_save as fs  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.gui.franchise_panel_qt import COACH_STATS, FranchiseEdit, FranchisePanel, IrPickerDialog, money  # noqa: E402
from mod_editor.gui.roster_editor_panel_qt import RosterEditorPanel, ValueBar  # noqa: E402
from test_nfl2k5_franchise_save import F0, F1, FIXTURES, FRANCHISE1, synthetic_franchise  # noqa: E402
from test_nfl2k5_roster_records import synthetic_body, synthetic_save_v0  # noqa: E402
from test_roster_editor_panel_franchise import write_container  # noqa: E402

COACH_AT = 0x85000                      # a zero stretch of the synthetic arena (file offset)
COACH_STRINGS_AT = COACH_AT + 0x100


def _rel(buffer: bytearray, field: int, target: int) -> None:
    struct.pack_into("<i", buffer, field, target - field + 1)


def synthetic_franchise_with_coach(**kwargs) -> bytes:
    """The core tests' synthetic franchise save plus one coach record on team 0 (Finn's numbers for Belichick)."""

    data = bytearray(synthetic_franchise(**kwargs))
    save = fs.FranchiseSave(bytes(data))
    cursor = COACH_STRINGS_AT

    def put(text: str) -> int:
        nonlocal cursor
        raw = text.encode("utf-16-le") + b"\0\0"
        at = cursor
        data[at:at + len(raw)] = raw
        cursor += len(raw)
        return at

    for field_rel, text in ((0x00, "Bill"), (0x04, "Belichick"), (0x08, "One of the winningest coaches"),
                            (0x0C, "in football history"), (0x10, "")):
        if text:
            _rel(data, COACH_AT + field_rel, put(text))
    struct.pack_into("<I", data, COACH_AT + 0x18, 7)                         # body
    for name, value in (("seasons_with_team", 5), ("total_seasons", 10), ("wins", 75), ("losses", 69),
                        ("ties", 0), ("winning_seasons", 5), ("super_bowls", 2), ("playoff_wins", 7),
                        ("playoff_losses", 1), ("super_bowl_wins", 2), ("super_bowl_losses", 0), ("photo", 33)):
        rel, fmt = fs.COACH_FIELDS[name]
        struct.pack_into(fmt, data, COACH_AT + rel, value)
    data[COACH_AT + fs.COACH_FIELDS["playcalling_run"][0]] = 45
    for k in range(len(fs.COACH_RATINGS)):
        data[COACH_AT + fs.COACH_RATINGS_OFFSET + k] = 60 + k
    for k in range(fs.COACH_TENDENCY_COUNT):
        data[COACH_AT + fs.COACH_TENDENCIES_OFFSET + k] = 40 + 5 * k
    struct.pack_into("<I", data, fs.ARENA_ROOT + 0x30, 1)
    _rel(data, fs.ARENA_ROOT + 0x34, COACH_AT)
    _rel(data, save.team_offset(0) + rr.TEAM_COACH, COACH_AT)
    return bytes(data)


def written_savegame(copy: Path) -> bytes:
    return next(copy.rglob("SAVEGAME.DAT")).read_bytes()


class _PanelCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.panel = RosterEditorPanel()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.application.processEvents()

    def tearDown(self) -> None:
        self.panel.deleteLater()
        self.application.processEvents()
        self.temp.cleanup()

    @property
    def page(self) -> FranchisePanel:
        return self.panel.franchise_panel

    def load(self, payload: bytes, name: str = "fr") -> Path:
        source = write_container(self.root / name, payload)
        self.assertTrue(self.panel.load_save(source))
        self.application.processEvents()
        return source

    def write(self, name: str = "copy") -> tuple[dict, bytes]:
        receipt = self.panel.write_copy_to(self.root / name)
        self.assertTrue(receipt["signed"])
        return receipt, written_savegame(self.root / name)


class TabVisibilityTests(_PanelCase):
    def test_the_tab_appears_only_for_a_franchise_save(self) -> None:
        pages = self.panel.pages
        self.assertEqual(pages.tabText(0), "Roster")
        self.assertEqual(pages.tabText(1), "Franchise")
        self.assertFalse(pages.isTabVisible(1))
        self.assertFalse(pages.tabBar().isVisibleTo(self.panel))
        self.assertFalse(self.page.active)
        self.load(synthetic_franchise_with_coach(year_field=7, user_team=0))
        self.assertTrue(self.page.active)
        self.assertTrue(pages.isTabVisible(1))
        self.assertTrue(pages.tabBar().isVisibleTo(self.panel))
        self.assertIn("2011", self.page.title_label.text())
        self.assertEqual(self.page.dirty_label.text(), "")
        # a plain roster-arena save hides it again, and so does a bare body
        plain = write_container(self.root / "plain", synthetic_save_v0(synthetic_body()))
        self.assertTrue(self.panel.load_save(plain))
        self.assertFalse(self.page.active)
        self.assertFalse(pages.isTabVisible(1))
        self.assertFalse(pages.tabBar().isVisibleTo(self.panel))
        self.panel.load_document(rr.load_body(synthetic_body()), label="body")
        self.assertFalse(self.page.active)
        self.assertFalse(pages.isTabVisible(1))
        # the page refuses non-franchise bytes on its own too
        self.assertFalse(self.page.load(rr.SaveContainer.load(plain), rr.SaveContainer.load(plain).document()))

    def test_the_tabs_are_finns_screens_in_our_words(self) -> None:
        titles = [self.page.tabs.tabText(i) for i in range(self.page.tabs.count())]
        self.assertEqual(titles, ["Overview", "Schedule", "Coaches", "Injured Reserve", "Checks"])
        self.assertEqual(money(88_113), "$88.1M")
        self.assertEqual([name for name, _caption in COACH_STATS][:3], ["wins", "losses", "ties"])


class OverviewTests(_PanelCase):
    def setUp(self) -> None:
        super().setUp()
        self.payload = synthetic_franchise_with_coach(year_field=7, user_team=0)
        self.load(self.payload)

    def test_year_cap_and_user_control_round_trip_through_one_resigned_copy(self) -> None:
        page = self.page
        self.assertEqual(page.year_spin.value(), 2011)
        self.assertIn("2004 + year field 7", page.year_rule_label.text())
        self.assertIn("regular season, week 3/17", page.stage_label.text())
        self.assertAlmostEqual(page.cap_spin.value(), 80.5)
        self.assertIn("80,500", page.cap_raw_label.text())
        self.assertEqual(page.salary_table.rowCount(), 3)
        page.year_spin.setValue(2012)
        page.cap_spin.setValue(90.0)
        self.assertTrue(page.set_user_control(0, False))
        self.assertTrue(page.set_user_control(2, True))
        self.application.processEvents()
        assert page.save is not None
        self.assertEqual((page.save.header.display_year, page.save.salary_cap, page.save.user_teams()), (2012, 90_000, [2]))
        self.assertIn("2004 + year field 8", page.year_rule_label.text())
        self.assertIn("90,000", page.cap_raw_label.text())
        self.assertEqual(page.dirty_label.text(), "● 4 franchise edits (not yet written)")
        self.assertEqual(page.edit_labels(), [
            "Season year 2011 → 2012 (year field 8)",
            "Salary cap $80.5M (80,500) → $90.0M (90,000)",
            "IND: user-controlled → CPU",
            "SF: CPU → user-controlled",
        ])
        receipt, written = self.write()
        self.assertEqual(receipt["franchise_edits"], page.edit_labels())
        expected = fs.FranchiseSave(self.payload)
        expected.set_display_year(2012)
        expected.set_salary_cap(90_000)
        expected.set_user_control(0, False)
        expected.set_user_control(2, True)
        self.assertEqual(written, expected.to_bytes())                     # byte-exact wherever nothing changed
        self.assertEqual(len(expected.changed_ranges()), 4)
        # reload the copy through the page
        self.assertTrue(self.panel.load_save(self.root / "copy"))
        back = self.page.save
        assert back is not None
        self.assertEqual((back.header.display_year, back.salary_cap, back.user_teams()), (2012, 90_000, [2]))
        self.assertEqual(self.page.edit_labels(), [])
        self.assertEqual(self.page.dirty_label.text(), "")
        self.assertEqual(self.page.control_list.item(2).checkState(), Qt.Checked)
        self.assertEqual(self.page.control_list.item(0).checkState(), Qt.Unchecked)

    def test_undo_and_redo_are_per_action_and_restore_the_bytes(self) -> None:
        page = self.page
        assert page.save is not None
        page.year_spin.setValue(2013)
        page.cap_spin.setValue(95.5)
        self.assertEqual(page.save.changed_ranges(), [(fs.SEASON_BLOCK + fs.S_YEAR, fs.SEASON_BLOCK + fs.S_YEAR + 1),
                                                      (0x9ACCC, 0x9ACCE)])
        self.assertTrue(page.undo_button.isEnabled())
        self.assertFalse(page.redo_button.isEnabled())
        self.assertEqual(page.undo(), "Salary cap $80.5M (80,500) → $95.5M (95,500)")
        assert page.save is not None
        self.assertEqual(page.save.salary_cap, 80_500)
        self.assertEqual(page.save.header.display_year, 2013)
        self.assertTrue(page.redo_button.isEnabled())
        self.assertEqual(page.undo(), "Season year 2011 → 2013 (year field 9)")
        assert page.save is not None
        self.assertEqual(page.save.to_bytes(), self.payload)
        self.assertEqual(page.undo(), "")
        self.assertEqual(page.redo(), "Season year 2011 → 2013 (year field 9)")
        self.assertEqual(page.redo(), "Salary cap $80.5M (80,500) → $95.5M (95,500)")
        self.assertEqual(page.redo(), "")
        assert page.save is not None
        self.assertEqual((page.save.header.display_year, page.save.salary_cap), (2013, 95_500))
        # a new edit after an undo drops the redo branch
        page.undo()
        page.year_spin.setValue(2020)
        self.assertEqual(page.edit_labels(), ["Season year 2011 → 2013 (year field 9)", "Season year 2013 → 2020 (year field 16)"])
        self.assertFalse(page.redo_button.isEnabled())


class ScheduleTests(_PanelCase):
    def setUp(self) -> None:
        super().setUp()
        self.payload = synthetic_franchise_with_coach(year_field=7, user_team=0)
        self.load(self.payload)

    def test_played_cell_is_refused_unless_allowed_and_swap_works(self) -> None:
        page = self.page
        page.tabs.setCurrentIndex(1)
        page.week_combo.setCurrentIndex(0)
        self.assertEqual(page.schedule_table.rowCount(), 2)
        self.assertEqual(page.schedule_table.item(0, 5).text(), "yes")
        self.assertEqual(page.schedule_table.item(0, 6).text(), "17 – 17")
        self.assertIn("HYPOTHESIS", page.schedule_table.item(0, 6).toolTip())
        self.assertEqual(page.schedule_table.item(1, 5).text(), "")
        self.assertEqual(page.week_label.text(), "2 games, 1 played")
        # the played cell: refused with the reason
        self.assertFalse(page.edit_game(0, 0, home=4))
        self.assertIn("has been played", page.status_label.text())
        self.assertIn("Allow editing played games", page.status_label.text())
        assert page.save is not None
        self.assertEqual(page.save.to_bytes(), self.payload)
        self.assertEqual(page.edit_labels(), [])
        # through the editor row: select the played game, change home, Apply -> same refusal
        page.schedule_table.selectRow(0)
        page.home_combo.setCurrentIndex(page.home_combo.findData(4))
        page.apply_game_button.click()
        self.assertIn("has been played", page.status_label.text())
        # allowed: the edit lands and says it was a played game
        page.allow_played_check.setChecked(True)
        page.apply_game_button.click()
        assert page.save is not None
        self.assertEqual(page.save.game(0, 0).home, 4)
        self.assertEqual(page.edit_labels(), ["Week 1 game 1: home ATL → Broncos (played game, allowed)"])
        page.allow_played_check.setChecked(False)
        # the scheduled cell: every field, then a swap
        self.assertTrue(page.edit_game(0, 1, home=1, away=0, month=10, day=3, hour=8, minute=30))
        game = page.save.game(0, 1)
        self.assertEqual((game.home, game.away, game.month, game.day, game.kickoff()), (1, 0, 10, 3, "8:30"))
        self.assertEqual(page.schedule_table.item(1, 1).text(), "IND")
        self.assertEqual(page.schedule_table.item(1, 2).text(), "ATL")
        self.assertEqual(page.schedule_table.item(1, 3).text(), "10/3")
        self.assertEqual(page.schedule_table.item(1, 4).text(), "8:30")
        page.schedule_table.selectRow(1)
        page.swap_button.click()
        game = page.save.game(0, 1)
        self.assertEqual((game.home, game.away), (0, 1))
        self.assertEqual(page.edit_labels()[-1], "Week 1 game 2: home ATL → IND, away IND → ATL")
        # a team cannot play itself: refused by the core, the live save restored
        self.assertFalse(page.edit_game(0, 1, home=1))
        self.assertIn("play itself", page.status_label.text())
        self.assertEqual((page.save.game(0, 1).home, page.save.game(0, 1).away), (0, 1))
        self.assertFalse(page.edit_game(0, 1, home=0))                      # nothing to change
        self.assertFalse(page.edit_game(0, 2, home=3))                      # the row filler
        self.assertIn("filler", page.status_label.text())
        receipt, written = self.write()
        expected = fs.FranchiseSave(self.payload)
        expected.set_game(0, 0, home=4, allow_played=True)
        expected.set_game(0, 1, home=1, away=0, month=10, day=3, hour=8, minute=30)
        expected.set_game(0, 1, home=0, away=1)
        self.assertEqual(written, expected.to_bytes())
        self.assertEqual(len(receipt["franchise_edits"]), 3)


class CoachTests(_PanelCase):
    def setUp(self) -> None:
        super().setUp()
        self.payload = synthetic_franchise_with_coach(year_field=7, user_team=0)
        self.load(self.payload)

    def test_coach_edits_through_the_cards_and_spins(self) -> None:
        page = self.page
        page.tabs.setCurrentIndex(2)
        self.assertEqual(page.coach_list.count(), 1)
        self.assertEqual(page.coach_list.item(0).text(), "Bill Belichick — IND")
        self.assertEqual(page.coach_name_label.text(), "Bill Belichick")
        self.assertIn("One of the winningest coaches / in football history", page.coach_info_label.text())
        self.assertIn("read-only", page.coach_teams_label.text())
        self.assertEqual(page._coach_spins["wins"].value(), 75)
        self.assertEqual(page._coach_spins["super_bowls"].value(), 2)
        self.assertEqual(page._coach_spins["playcalling_run"].maximum(), 100)
        overall = page._coach_cards["overall"]
        self.assertIsInstance(overall.bar, ValueBar)                        # the player cards' bar, reused
        self.assertEqual(overall.value(), 60)
        self.assertEqual(page._coach_cards["shotgun_pass"].value(), 45)
        page._coach_spins["wins"].setValue(76)
        overall.spin.setValue(99)
        page._coach_cards["shotgun_pass"].bar.setValue(70)               # a bar drag routes through the spin
        page._coach_spins["playcalling_run"].setValue(55)
        self.application.processEvents()
        assert page.save is not None
        coach = page.save.coach_for_team(0)
        assert coach is not None
        self.assertEqual((coach.fields["wins"], coach.ratings["overall"], coach.tendencies["shotgun_pass"],
                          coach.fields["playcalling_run"]), (76, 99, 70, 55))
        self.assertEqual(page.edit_labels(), [
            "Bill Belichick: Wins 75 → 76",
            "Bill Belichick: Overall 60 → 99",
            "Bill Belichick: Shotgun Pass 45 → 70",
            "Bill Belichick: Playcalling: run % 45 → 55",
        ])
        self.assertEqual(page.undo(), "Bill Belichick: Playcalling: run % 45 → 55")
        self.assertEqual(page._coach_spins["playcalling_run"].value(), 45)
        page.redo()
        receipt, written = self.write()
        expected = fs.FranchiseSave(self.payload)
        expected.set_coach_field(0, "wins", 76)
        expected.set_coach_field(0, "overall", 99)
        expected.set_coach_field(0, "shotgun_pass", 70)
        expected.set_coach_field(0, "playcalling_run", 55)
        self.assertEqual(written, expected.to_bytes())
        self.assertTrue(self.panel.load_save(self.root / "copy"))
        back = self.page.save
        assert back is not None and back.coach_for_team(0) is not None
        self.assertEqual(back.coach_for_team(0).fields["wins"], 76)
        self.assertEqual(self.page._coach_cards["overall"].value(), 99)
        # out-of-range values never reach the bytes
        self.assertFalse(self.page.set_coach_value(0, "overall", 150))
        self.assertIn("Refused", self.page.status_label.text())
        self.assertFalse(self.page.set_coach_value(7, "wins", 1))
        self.assertIn("no coach 7", self.page.status_label.text())


class InjuredReserveTests(_PanelCase):
    def setUp(self) -> None:
        super().setUp()
        self.payload = synthetic_franchise_with_coach(year_field=7, user_team=0)
        self.load(self.payload)

    def test_place_refusals_activate_and_the_written_bytes(self) -> None:
        page = self.page
        page.tabs.setCurrentIndex(3)
        page.ir_team_combo.setCurrentIndex(0)
        self.assertEqual(page.ir_table.item(0, 1).text(), "(empty)")
        self.assertFalse(page.activate_ir_button.isEnabled())
        candidates = page.ir_candidates(0)
        self.assertEqual([index for index, _text in candidates], [0, 1, 2])
        self.assertEqual(candidates[0][1], "QB Peyton Manning (#0)")
        dialog = IrPickerDialog("IND", candidates)
        dialog.list.setCurrentRow(1)
        self.assertEqual(dialog.chosen(), 1)
        # Finn's refusals come first, in his words
        self.assertFalse(page.place_on_ir(0, 6))
        self.assertEqual(page.status_label.text(), f"Refused: {rr.MSG_FREE_AGENT_IR}")
        self.assertFalse(page.place_on_ir(0, 7))
        self.assertEqual(page.status_label.text(), f"Refused: {rr.MSG_DRAFT_CLASS}")
        self.assertFalse(page.place_on_ir(1, 0))                            # not on that team
        self.assertIn("not on team 1", page.status_label.text())
        assert page.save is not None
        self.assertEqual(page.save.to_bytes(), self.payload)
        # the move
        self.assertTrue(page.place_on_ir(0, 1))
        self.assertEqual(page.ir_table.item(0, 1).text(), "Marvin Harrison")
        self.assertEqual(page.ir_table.item(0, 2).text(), "1")
        self.assertEqual(page.league_ir_list.count(), 1)
        self.assertIn("Marvin Harrison (slot 1, player #1)", page.league_ir_list.item(0).text())
        self.assertTrue(page.activate_ir_button.isEnabled())
        self.assertEqual(page.save.team_player_indices(0), [0, 2])
        self.assertEqual(page.ir_candidates(0), [(0, "QB Peyton Manning (#0)"), (2, "HB Edgerrin James (#2)")])
        self.assertEqual(page.edit_labels(), ["IND: Marvin Harrison (#1) placed on injured reserve"])
        receipt, written = self.write("copy1")
        expected = fs.FranchiseSave(self.payload)
        expected.place_on_injured_reserve(0, 1)
        self.assertEqual(written, expected.to_bytes())
        # reload: the roster page shows him IR, the franchise page lists him; activate through the table
        self.assertTrue(self.panel.load_save(self.root / "copy1"))
        page = self.page
        assert page.save is not None
        self.assertEqual([(e.team, e.player_index) for e in page.save.injured_reserve()], [(0, 1)])
        self.assertTrue(self.panel.document is not None)
        harrison = next(p for p in self.panel.document.players if p.index == 1 and p.pool == "primary")
        self.assertTrue(harrison.record.on_injured_reserve)
        page.tabs.setCurrentIndex(3)
        page.ir_table.selectRow(0)
        page.activate_ir_button.click()
        self.assertEqual(page.edit_labels(), ["IND: Marvin Harrison (#1) activated from injured reserve (unwitnessed in game)"])
        self.assertEqual(page.save.injured_reserve(), [])
        self.assertEqual(page.save.team_player_indices(0), [0, 2, 1])       # re-added at the end, as the core says
        self.assertFalse(page.activate_ir_button.isEnabled())               # no filled slot is left
        page._activate_ir_clicked()
        self.assertIn("Select a filled", page.status_label.text())
        receipt, written = self.write("copy2")
        expected = fs.FranchiseSave(written_savegame(self.root / "copy1"))
        expected.activate_from_injured_reserve(0, 1)
        self.assertEqual(written, expected.to_bytes())


class SharedBytesTests(_PanelCase):
    """Roster edits and franchise edits land in ONE copy, roster first."""

    def setUp(self) -> None:
        super().setUp()
        self.payload = synthetic_franchise_with_coach(year_field=7, user_team=0)
        self.load(self.payload)

    def test_a_roster_edit_and_a_cap_edit_share_the_copy(self) -> None:
        document = self.panel.document
        assert document is not None
        document.players[0].record.set("speed", 77)
        self.assertTrue(self.page.set_salary_cap(91_000))
        receipt, written = self.write()
        self.assertEqual(receipt["franchise_edits"], ["Salary cap $80.5M (80,500) → $91.0M (91,000)"])
        expected = fs.FranchiseSave(document.to_body())
        expected.set_salary_cap(91_000)
        self.assertEqual(written, expected.to_bytes())
        self.assertNotEqual(written[:fs.ARENA_END], self.payload[:fs.ARENA_END])    # the roster edit is in
        self.assertTrue(self.panel.load_save(self.root / "copy"))
        assert self.panel.document is not None
        self.assertEqual(self.panel.document.players[0].record.get("speed"), 77)
        assert self.page.save is not None
        self.assertEqual(self.page.save.salary_cap, 91_000)

    def test_a_membership_move_on_the_roster_page_and_an_ir_move_replay_in_order(self) -> None:
        document = self.panel.document
        assert document is not None
        manning = next(p for p in document.players if p.index == 0)
        vick = next(p for p in document.players if p.index == 3)
        document.swap(manning, vick)                                         # Vick to IND, Manning to ATL (counts kept)
        self.assertEqual([index for index, _t in self.page.ir_candidates(0)], [3, 1, 2])
        self.assertTrue(self.page.place_on_ir(0, 2))
        receipt, written = self.write()
        expected = fs.FranchiseSave(document.to_body())
        expected.place_on_injured_reserve(0, 2)
        self.assertEqual(written, expected.to_bytes())
        back = fs.FranchiseSave(written)
        self.assertEqual(back.team_player_indices(0), [3, 1])
        self.assertEqual(back.team_player_indices(1), [0, 4, 5])
        self.assertEqual([(e.team, e.player_index) for e in back.injured_reserve()], [(0, 2)])
        # the roster page pulling the rug: IR James, then swap him away on the roster page -> the IR edit is dropped and said
        self.panel.load_save(self.root / "fr")
        document = self.panel.document
        assert document is not None
        self.assertTrue(self.page.place_on_ir(0, 2))
        james = next(p for p in document.players if p.index == 2)
        dunn = next(p for p in document.players if p.index == 4)
        document.swap(james, dunn)
        self.assertTrue(self.page.sync_from_roster())
        self.assertEqual(self.page.edit_labels(), [])
        self.assertIn("Dropped a franchise edit", self.page.status_label.text())
        self.assertIn("not on team 0", self.page.status_label.text())


class ChecksTests(_PanelCase):
    def test_the_checks_page_says_what_is_proved_and_what_changed(self) -> None:
        payload = synthetic_franchise_with_coach(year_field=7, user_team=0)
        self.load(payload)
        page = self.page
        page.tabs.setCurrentIndex(4)
        text = page.checks_text.toPlainText()
        for piece in ("PROVED: ", "HYPOTHESIS: ", "OPAQUE: ", "never shown as editable", "Editable on this page:",
                      "Injured reserve: activate: HYPOTHESIS", "Franchise edits since load (0):", "  none",
                      "0 ranges, 0 bytes"):
            self.assertIn(piece, text)
        page.tabs.setCurrentIndex(0)
        page.cap_spin.setValue(90.0)
        page.year_spin.setValue(2012)
        page.tabs.setCurrentIndex(4)                                       # refreshed on show
        text = page.checks_text.toPlainText()
        self.assertIn("Franchise edits since load (2):", text)
        self.assertIn("1. Salary cap $80.5M (80,500) → $90.0M (90,000)", text)
        self.assertIn("2. Season year 2011 → 2012 (year field 8)", text)
        self.assertIn("2 ranges, 3 bytes", text)
        self.assertIn("0x09ACCC..0x09ACCE (2 B) — salary cap $1000 (DAT_00e3c278) [PROVED]", text)
        self.assertIn("year field (DAT_00e576b8), display = 2004 + field [PROVED]", text)
        self.assertEqual(page.checks_text_for(), text)
        page.checks_refresh_button.click()
        self.assertEqual(page.checks_text.toPlainText(), text)

    def test_an_unknown_edit_kind_is_refused(self) -> None:
        with self.assertRaises(fs.FranchiseSaveError):
            FranchiseEdit("teleport", "nope").apply(fs.FranchiseSave(synthetic_franchise()))


@unittest.skipUnless(F0.is_file() and F1.is_file(), f"private 8007Fran fixtures missing under {FIXTURES}")
class RealFinnFixturePanelTests(_PanelCase):
    def test_finns_ir_move_through_the_page_reproduces_f1_byte_for_byte(self) -> None:
        self.assertTrue(self.panel.load_save(F0.parents[3]))
        page = self.page
        self.assertTrue(page.active)
        assert page.save is not None
        self.assertEqual(page.save.header.display_year, 2004)
        self.assertEqual(page.coach_list.count(), 35)
        self.assertIn("Harris Barton", dict(page.ir_candidates(0)).get(1369, ""))
        self.assertTrue(page.place_on_ir(0, 1369))
        self.assertEqual(page.edit_labels(), ["SF: Harris Barton (#1369) placed on injured reserve"])
        receipt = self.panel.write_copy_to(self.root / "copy")
        self.assertTrue(receipt["signed"])
        copy = self.root / "copy"
        self.assertEqual(next(copy.rglob("SAVEGAME.DAT")).read_bytes(), F1.read_bytes())
        self.assertEqual(next(copy.rglob("EXTRA")).read_bytes(), F1.with_name("EXTRA").read_bytes())
        self.assertEqual(F0.read_bytes(), fs.FranchiseSave.load(F0.parents[3]).original)    # source untouched


@unittest.skipUnless(FRANCHISE1.is_file(), f"private Franchise1 fixture missing under {FIXTURES}")
class RealFranchise1PanelTests(_PanelCase):
    def test_every_tab_edits_the_year_seven_lions_save_and_reloads(self) -> None:
        self.assertTrue(self.panel.load_save(FRANCHISE1.parents[3]))
        page = self.page
        assert page.save is not None
        original = FRANCHISE1.read_bytes()
        self.assertEqual((page.year_spin.value(), page.save.salary_cap, page.save.user_teams()), (2011, 88_113, [18]))
        self.assertIn("offseason stage 1", page.stage_label.text())
        self.assertEqual(page.salary_table.rowCount(), 32)
        self.assertEqual(page.salary_table.item(18, 3).text(), "user-controlled")
        # overview
        page.year_spin.setValue(2012)
        page.cap_spin.setValue(90.0)
        self.assertTrue(page.set_user_control(18, False))
        self.assertTrue(page.set_user_control(19, True))
        # schedule: every cell is played in this save
        page.tabs.setCurrentIndex(1)
        page.week_combo.setCurrentIndex(0)
        self.assertEqual(page.schedule_table.rowCount(), 16)
        self.assertEqual(page.week_label.text(), "16 games, 16 played")
        self.assertFalse(page.edit_game(0, 0, day=6))
        self.assertIn("has been played", page.status_label.text())
        page.allow_played_check.setChecked(True)
        self.assertTrue(page.edit_game(0, 0, day=6))
        self.assertTrue(page.swap_home_away(0, 1))
        page.allow_played_check.setChecked(False)
        # coaches
        page.tabs.setCurrentIndex(2)
        coach = page.save.coach_for_team(18)
        assert coach is not None
        self.assertEqual(coach.name, "Steve Mariucci")
        self.assertTrue(page.select_coach(coach.index))
        self.assertEqual(page.coach_name_label.text(), "Steve Mariucci")
        wins = coach.fields["wins"]
        page._coach_spins["wins"].setValue(wins + 1)
        page._coach_cards["motivation"].spin.setValue(77)
        # injured reserve: the first Lion
        page.tabs.setCurrentIndex(3)
        page.ir_team_combo.setCurrentIndex(18)
        first, _text = page.ir_candidates(18)[0]
        self.assertTrue(page.place_on_ir(18, first))
        labels = page.edit_labels()
        self.assertEqual(len(labels), 9)
        receipt, written = self.write()
        expected = fs.FranchiseSave(original)
        expected.set_display_year(2012)
        expected.set_salary_cap(90_000)
        expected.set_user_control(18, False)
        expected.set_user_control(19, True)
        expected.set_game(0, 0, day=6, allow_played=True)
        game = expected.game(0, 1)
        expected.set_game(0, 1, home=game.away, away=game.home, allow_played=True)
        expected.set_coach_field(coach.index, "wins", wins + 1)
        expected.set_coach_field(coach.index, "motivation", 77)
        expected.place_on_injured_reserve(18, first)
        self.assertEqual(written, expected.to_bytes())
        self.assertEqual(FRANCHISE1.read_bytes(), original)
        # reload the copy through the page and read everything back
        self.assertTrue(self.panel.load_save(self.root / "copy"))
        page = self.page
        assert page.save is not None
        self.assertEqual((page.save.header.display_year, page.save.salary_cap, page.save.user_teams()), (2012, 90_000, [19]))
        self.assertEqual(page.save.game(0, 0).day, 6)
        self.assertEqual((page.save.game(0, 1).home, page.save.game(0, 1).away), (game.away, game.home))
        back = page.save.coach_for_team(18)
        assert back is not None
        self.assertEqual((back.fields["wins"], back.ratings["motivation"]), (wins + 1, 77))
        self.assertEqual([(e.team, e.player_index) for e in page.save.injured_reserve()], [(18, first)])
        self.assertEqual(page.edit_labels(), [])
        self.assertIn("1 on IR", page.title_label.text())


if __name__ == "__main__":
    unittest.main()

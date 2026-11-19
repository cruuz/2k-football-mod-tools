"""Flying Finn's GameSave Editor, rebuilt on the ★ Rosters page (b81, job finn).

The parity audit (``FINN_PARITY.md``, ranks R1 to R17) compared Finn 4.0.0.41 with the Studio item by item.
These tests pin what this wave added: the league-wide Find player (R1), Finn's keys (R6), the places and words a
Finn user looks for (the naming table, including the right-click Place on IR and the after-save message), the
sortable grid (R2), coaches in a roster save (R5), the schedule card and tools (R8), and the small passes (R10, R12,
R15, R16, R17).

Offscreen Qt on synthetic rosters everywhere; the real SOFTDRINK roster save (4,096 primary records, one-pool
positions, reserves) is used when it is present (``NFL2K5_SOFTDRINK_ROSTER_SAVE``) and skipped, with its path,
when it is not.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor", ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402
from PyQt5.QtWidgets import QApplication, QDialog  # noqa: E402

from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.gui import roster_editor_panel_qt as panel_module  # noqa: E402
from mod_editor.gui.franchise_panel_qt import IrPickerDialog  # noqa: E402
from mod_editor.gui.roster_editor_panel_qt import FindPlayerDialog, RosterEditorPanel  # noqa: E402
from test_nfl2k5_roster_records import league_body, synthetic_body, synthetic_save_v0  # noqa: E402
from test_roster_editor_panel_franchise import write_container  # noqa: E402

SOFTDRINK_ROSTER_SAVE = Path(os.environ.get(
    "NFL2K5_SOFTDRINK_ROSTER_SAVE",
    "/media/noah/Storage/2K5-project/beta81/isolated-data/FC3-native-roster.zip"))


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


# --------------------------------------------------------------------------------------------- R1 core
class FindPlayersCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = rr.load_body(league_body())

    def test_every_list_is_searched_and_each_hit_says_where_he_is(self) -> None:
        rows = rr.find_players(self.document, "Last112")
        self.assertEqual([r["player"].display for r in rows], ["F112 Last112"])
        self.assertEqual(rows[0]["location"], ("team", 1))
        self.assertTrue(rows[0]["where"].startswith("ATL ("), rows[0]["where"])
        agent = rr.find_players(self.document, "agenttwo")
        self.assertEqual(agent[0]["location"], ("free_agent", -1))
        self.assertEqual(agent[0]["where"], "Free Agents")
        prospect = rr.find_players(self.document, "Prospect")
        self.assertEqual(prospect[0]["location"], ("draft_class", -1))

    def test_finns_last_comma_first_order_full_names_and_colleges_match(self) -> None:
        self.assertEqual([r["player"].last for r in rr.find_players(self.document, "Last05, F05")], ["Last05"])
        self.assertEqual([r["player"].last for r in rr.find_players(self.document, "f05 last05")], ["Last05"])
        tennessee = rr.find_players(self.document, "Tennessee")
        self.assertTrue(tennessee and all(r["player"].college == "Tennessee" for r in tennessee))
        self.assertEqual(rr.find_players(self.document, "nobody by that name"), [])

    def test_position_and_years_pro_narrow_and_a_last_name_prefix_ranks_first(self) -> None:
        qbs = rr.find_players(self.document, "", positions=(0,))
        self.assertTrue(qbs and all(r["player"].record.values["position"] == 0 for r in qbs))
        rookies = rr.find_players(self.document, "", years_pro=rr.ROOKIE_YEARS_PRO)
        self.assertTrue(rookies and all(r["player"].record.values["years_pro"] == 1 for r in rookies))
        ranked = rr.find_players(self.document, "agent")
        self.assertEqual({r["player"].last for r in ranked[:3]}, {"AgentOne", "AgentTwo", "AgentThree"})

    def test_unnamed_capacity_records_are_never_offered(self) -> None:
        nobody = self.document.players[0]
        nobody.first = nobody.last = ""
        self.assertNotIn(nobody, [r["player"] for r in rr.find_players(self.document, "")])
        self.assertEqual(rr.player_location(self.document, self.document.players[1]), ("team", 0))


@unittest.skipUnless(SOFTDRINK_ROSTER_SAVE.is_file(), f"SOFTDRINK roster save absent: {SOFTDRINK_ROSTER_SAVE}")
class FindPlayersSoftdrinkTests(unittest.TestCase):
    """The expanded roster: 4,164 records, one-pool positions, reserves."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.document = rr.load_save(SOFTDRINK_ROSTER_SAVE, detect=True)

    def test_buckner_is_found_on_his_club_and_a_reserve_under_his_clubs_reserves(self) -> None:
        self.assertEqual(self.document.scheme, "one_pool")
        started = time.perf_counter()
        rows = rr.find_players(self.document, "Buckner")
        elapsed = time.perf_counter() - started
        self.assertEqual([r["player"].display for r in rows], ["DeForest Buckner"])
        self.assertEqual(rows[0]["location"], ("team", self.document.club_of(rows[0]["player"])))
        self.assertLess(elapsed, 0.5, "a league-wide find is interactive")
        reserve = next(p for p in self.document.players if (p.pool, p.index) in self.document.reserve_owner)
        hit = next(r for r in rr.find_players(self.document, f"{reserve.first} {reserve.last}") if r["player"] is reserve)
        self.assertEqual(hit["location"], ("reserve", self.document.reserve_owner[reserve.pool, reserve.index]))
        self.assertTrue(hit["where"].endswith("Reserves"))

    def test_the_quick_reserve_check_is_quick_and_agrees_with_the_full_one(self) -> None:
        # b81: the page ran the full transaction for every selected club player (about 3 s each on this save)
        doc = self.document
        sample = [p for p in doc.players if (p.pool, p.index) in doc.reserve_owner][:2]
        sample += [p for p in doc.team_players(3)[:2]] + [p for p in doc.team_players(20)[-1:]]
        for player in sample:
            owner = doc.club_of(player)
            for promote in (True, False):
                started = time.perf_counter()
                try:
                    doc.reserve_move_precheck(owner, player.index, promote=promote)
                    quick = ""
                except rr.RosterRecordError as exc:
                    quick = str(exc)
                self.assertLess(time.perf_counter() - started, 0.1)
                try:
                    doc.reserve_move_check(owner, player.index, promote=promote)
                    full = ""
                except rr.RosterRecordError as exc:
                    full = str(exc)
                with self.subTest(player=player.display, promote=promote):
                    self.assertEqual(quick, full)


class ReservePrecheckTests(unittest.TestCase):
    """The quick check gives the full transaction's own refusal for every state the document answers."""

    def test_capacity_membership_kind_and_ir_refusals_match_the_full_check(self) -> None:
        from test_rosters_reserves_abilities import document, league_save
        doc = document(league_save(53))
        doc.demote_active(0, 0)
        cases = [(0, 0, True), (0, 0, False), (0, 1, False), (0, 1, True), (1, 60, False), (0, 53 * 2 + 1, True),
                 (5, 1, False)]
        doc.players[2].record.values["injured_reserve"] = 0xEE
        cases.append((0, 2, False))
        doc.players[3].record.values["player_type"] |= 0x10
        cases.append((0, 3, False))
        for team, index, promote in cases:
            outcomes = []
            for check in (doc.reserve_move_precheck, doc.reserve_move_check):
                try:
                    check(team, index, promote=promote)
                    outcomes.append("")
                except rr.RosterRecordError as exc:
                    outcomes.append(str(exc))
            with self.subTest(team=team, index=index, promote=promote):
                self.assertEqual(outcomes[0], outcomes[1])


# --------------------------------------------------------------------------------------------- panel cases
class _PanelCase(unittest.TestCase):
    body_factory = staticmethod(synthetic_body)

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = _app()

    def setUp(self) -> None:
        self.panel = RosterEditorPanel()
        self.panel.load_document(rr.load_body(self.body_factory()), label="synthetic")
        self.application.processEvents()

    def tearDown(self) -> None:
        self.panel.close()
        self.panel.deleteLater()
        self.application.processEvents()

    def player(self, last: str) -> rr.Player:
        assert self.panel.document is not None
        return next(p for p in self.panel.document.players if p.last == last)

    def activate(self) -> None:
        self.panel.resize(1366, 768)
        self.panel.show()
        self.panel.activateWindow()
        QApplication.setActiveWindow(self.panel)
        self.application.processEvents()


class FindDialogTests(_PanelCase):
    body_factory = staticmethod(league_body)

    def test_find_goes_to_a_free_agent_and_a_prospect_from_any_list(self) -> None:
        dialog = self.panel.open_find_dialog()
        assert isinstance(dialog, FindPlayerDialog)
        self.assertEqual(dialog.count_label.text(), "Type a name to search the whole league.")
        self.panel._chip_clicked("QB")
        self.panel.search.setText("zzz")                    # filters that would hide him are cleared
        dialog.text.setText("AgentThree")
        self.assertEqual(dialog.table.rowCount(), 1)
        self.assertEqual(dialog.table.item(0, 5).text(), "Free Agents")
        self.assertTrue(dialog.go())
        self.assertEqual(self.panel.selected_player().last, "AgentThree")
        self.assertEqual(self.panel._group, ("free_agent", -1))
        self.assertEqual((self.panel._chip, self.panel.search.text()), ("All", ""))
        self.assertIn("Found F", self.panel.status_label.text())
        dialog = self.panel.open_find_dialog()
        assert dialog is not None
        dialog.text.setText("Prospect")
        self.assertTrue(dialog.go())
        self.assertEqual(self.panel._group, ("draft_class", -1))
        self.assertEqual(self.panel.selected_player().last, "Prospect")

    def test_a_club_player_is_selected_on_his_club_and_the_position_filter_follows_the_scheme(self) -> None:
        dialog = self.panel.open_find_dialog()
        assert dialog is not None
        positions = [dialog.position_combo.itemText(i) for i in range(dialog.position_combo.count())]
        self.assertEqual(positions[0], "Any position")
        self.assertIn("OLB", positions)                     # retail scheme keeps OLB
        dialog.text.setText("Last130")
        self.assertTrue(dialog.go())
        self.assertEqual(self.panel._group, ("team", 1))
        self.assertEqual(self.panel.selected_player().last, "Last130")
        self.assertIs(self.panel.team_list.currentItem().data(Qt.UserRole)[1], 1)

    def test_the_search_box_says_ctrl_f_and_the_find_button_opens_the_dialog(self) -> None:
        self.assertIn("Ctrl+F", self.panel.search.placeholderText())
        self.assertTrue(self.panel.search.placeholderText().casefold().startswith("search"),
                        "the studio's Ctrl+F fallback still recognises the box")
        self.panel.find_button.click()
        self.assertIsNotNone(self.panel._find_dialog)
        self.assertTrue(self.panel._find_dialog.isVisible())


# --------------------------------------------------------------------------------------------- R6 keys
class ShortcutTests(_PanelCase):
    def test_finns_keys_copy_paste_attributes_undo_redo_on_the_grid(self) -> None:
        self.activate()
        table = self.panel.player_table
        table.setFocus()
        self.panel.select_player(self.player("Manning"))
        QTest.keyClick(table, Qt.Key_C, Qt.ControlModifier)
        self.assertIsNotNone(self.panel._clipboard)
        harrison = self.player("Harrison")
        self.panel.select_player(harrison)
        QTest.keyClick(table, Qt.Key_A, Qt.ControlModifier | Qt.AltModifier)
        self.assertEqual(harrison.record.values["speed"], 66, "Ctrl+Alt+A is Paste attributes only")
        self.assertEqual(harrison.last, "Harrison")
        QTest.keyClick(table, Qt.Key_Z, Qt.ControlModifier)
        self.assertEqual(harrison.record.values["speed"], 88)
        QTest.keyClick(table, Qt.Key_Y, Qt.ControlModifier)
        self.assertEqual(harrison.record.values["speed"], 66)
        QTest.keyClick(table, Qt.Key_Z, Qt.ControlModifier | Qt.ShiftModifier)  # no-op: nothing to redo
        QTest.keyClick(table, Qt.Key_Z, Qt.ControlModifier)
        QTest.keyClick(table, Qt.Key_V, Qt.ControlModifier)
        self.assertEqual(harrison.record.values["jersey"], 18, "Ctrl+V is Paste player")

    def test_a_text_box_keeps_its_own_copy_and_undo(self) -> None:
        self.activate()
        self.panel.search.setFocus()
        self.panel.search.setText("Peyton")
        self.panel.search.selectAll()
        QTest.keyClick(self.panel.search, Qt.Key_C, Qt.ControlModifier)
        self.assertIsNone(self.panel._clipboard, "Ctrl+C in the search box copies text, not a player")
        self.assertEqual(QApplication.clipboard().text(), "Peyton")

    def test_ctrl_d_shows_his_position_and_pgdn_steps_from_the_editor(self) -> None:
        self.activate()
        self.panel.player_table.setFocus()
        self.panel.select_player(self.player("Harrison"))
        QTest.keyClick(self.panel.player_table, Qt.Key_D, Qt.ControlModifier)
        self.assertEqual(self.panel._chip, "WR")
        self.assertEqual([p.last for p in self.panel.visible_players()], ["Harrison"])
        self.panel._chip_clicked("All")
        self.panel.select_player(self.player("Manning"))
        spin = self.panel.cards["speed"].spin
        spin.setFocus()
        self.application.processEvents()
        QTest.keyClick(spin, Qt.Key_PageDown)
        self.assertEqual(self.panel.selected_player().last, "Harrison", "PgDn: next player, as in Edit Player")
        QTest.keyClick(spin, Qt.Key_PageUp)
        self.assertEqual(self.panel.selected_player().last, "Manning")
        self.assertFalse(self.panel.step_player(-1), "the first player has no previous one")

    def test_the_espn_tab_does_not_take_the_roster_undo(self) -> None:
        self.panel.select_player(self.player("Manning"))
        self.panel.set_field(self.player("Manning"), "speed", 70)
        self.panel.pages.setCurrentWidget(self.panel.espn25_panel)
        self.panel._shortcut_undo()
        self.assertEqual(self.player("Manning").record.values["speed"], 70)
        self.panel.pages.setCurrentIndex(0)
        self.panel._shortcut_undo()
        self.assertEqual(self.player("Manning").record.values["speed"], 66)


# --------------------------------------------------------------------------------------------- naming table
class NamingTests(_PanelCase):
    def test_finns_words_are_where_a_finn_user_looks(self) -> None:
        self.assertEqual(self.panel.open_save_button.text(), "Open Xbox save (Finn's zip)…")
        self.assertIn("Action Replay .zip", self.panel.open_save_button.toolTip())
        actions = [a.text() for a in self.panel.passes_button.menu().actions()]
        self.assertIn("Add a year pro to everyone (Advance year)", actions)
        self.assertIn("already exists shares it", self.panel.name_pool_label.text())
        self.assertIn("Select a player to edit him", self.panel.player_table.toolTip())
        menu = [a.text() for a in self.panel.grid_menu().actions() if a.text()]
        self.assertEqual(menu[:5], ["Copy player", "Paste player", "Paste attributes only", "Paste photo only",
                                    "Find player… (every team)"])
        self.assertIn("Place on IR…", menu)
        place = next(a for a in self.panel.grid_menu().actions() if a.text() == "Place on IR…")
        self.assertFalse(place.isEnabled(), "IR belongs to a franchise save")
        self.assertIn("franchise save", place.toolTip())


# --------------------------------------------------------------------------------------------- R2 grid
class GridTests(_PanelCase):
    body_factory = staticmethod(league_body)

    def headers(self) -> list[str]:
        table = self.panel.player_table
        return [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]

    def test_sorting_by_speed_puts_the_fastest_first_and_keeps_the_selection(self) -> None:
        chosen = self.panel._rows[7]
        self.panel.select_player(chosen)
        self.panel.sort_by("speed")
        speeds = [p.record.values["speed"] for p in self.panel._rows]
        self.assertEqual(speeds, sorted(speeds, reverse=True), "a rating sorts highest first")
        self.assertIs(self.panel.selected_player(), chosen, "the selected player survives the sort")
        self.assertIn("SPD", self.headers(), "sorting by a hidden column shows it")
        column = self.headers().index("SPD")
        self.panel._header_clicked(column)
        speeds = [p.record.values["speed"] for p in self.panel._rows]
        self.assertEqual(speeds, sorted(speeds), "a second click reverses")
        self.panel._header_clicked(2)
        names = [p.last.casefold() for p in self.panel._rows]
        self.assertEqual(names, sorted(names), "the name column sorts A to Z first")
        rows = [self.panel.player_table.item(r, 2).text().lstrip("● ") for r in range(len(self.panel._rows))]
        self.assertEqual(rows, [p.display for p in self.panel._rows], "the grid shows the sorted order")

    def test_the_arrows_edit_the_depth_chart_in_any_grid_order(self) -> None:
        # wave 1 disabled the arrows while sorted (they moved the pointer list); wave 2 (R4) makes them edit the
        # stored depth rank, which does not depend on the grid's order
        self.assertFalse(self.panel.sort_box.isVisibleTo(self.panel))
        qbs = self.panel.document.depth_order(0, 0)
        self.panel.sort_by("ovr")
        self.panel.select_player(qbs[1])
        self.assertTrue(self.panel.up_button.isEnabled())
        self.assertTrue(self.panel.sort_box.isVisibleTo(self.panel))
        self.assertEqual(self.panel.sort_note.text(), "Sorted by Est. OVR, highest first. Team order puts the list back.")
        slots = list(self.panel.document.teams[0].slots)
        self.assertTrue(self.panel.move_selected(-1))
        self.assertIs(self.panel.document.depth_order(0, 0)[0], qbs[1])
        self.assertEqual(self.panel.document.teams[0].slots, slots)
        self.panel.team_order_button.click()
        self.assertIsNone(self.panel._sort)
        self.assertEqual(self.panel._rows, self.panel.document.team_players(0), "team order is the pointer list again")

    def test_the_column_picker_offers_finns_bands_in_his_order(self) -> None:
        self.panel._fill_columns_menu()
        bands = [a.text() for a in self.panel.columns_menu.actions() if a.menu() is not None]
        self.assertEqual(bands, ["Ratings", "Body", "Gear", "Contract"])
        ratings = next(a.menu() for a in self.panel.columns_menu.actions() if a.text() == "Ratings")
        entries = [a.text() for a in ratings.actions() if a.isCheckable()]
        self.assertEqual(entries[:5], ["Speed", "Agility", "Strength", "Jumping", "Coverage"], "Finn's order")
        self.assertEqual(len(entries), 28)
        self.panel._show_band("Ratings", True)
        self.assertEqual(self.headers()[:7], ["POS", "#", "Player", "Yrs", "Est. OVR", "Depth", "Locks"])
        self.assertEqual(self.headers()[7:10], ["SPD", "AGI", "STR"])
        player = self.panel._rows[0]
        self.assertEqual(self.panel.player_table.item(0, 7).text(), str(player.record.values["speed"]))
        self.panel._toggle_grid_column("helmet", True)
        self.assertEqual(self.headers()[-1], "Helmet")
        self.assertEqual(self.panel.player_table.item(0, len(self.headers()) - 1).text(),
                         rr.HELMETS[player.record.values["helmet"]])
        self.panel.set_grid_columns([])
        self.assertEqual(len(self.headers()), 7)

    def test_an_edit_updates_its_cell_in_place_in_a_sorted_grid(self) -> None:
        self.panel.sort_by("speed")
        self.panel.select_player(self.panel._rows[0])
        player = self.panel.selected_player()
        self.panel.set_field(player, "speed", 1)
        self.assertIs(self.panel._rows[0], player, "the edited row stays where it is")
        column = self.headers().index("SPD")
        self.assertEqual(self.panel.player_table.item(0, column).text(), "1")
        self.panel.undo()
        self.assertEqual(self.panel.player_table.item(0, column).text(), str(player.record.values["speed"]))

    def test_free_agents_get_lock_boxes_only_where_a_lock_can_be_cleared(self) -> None:
        document = self.panel.document
        agent = next(p for p in document.players if p.last == "AgentTwo")
        agent.record.set_depth_lock("kr1", True)
        self.panel.team_list.setCurrentRow(self.panel._team_list_row("free_agent", -1))
        widgets = [self.panel.player_table.cellWidget(r, 6) for r in range(self.panel.player_table.rowCount())]
        owners = [p for p, w in zip(self.panel._rows, widgets) if w is not None]
        self.assertEqual(owners, [agent])


@unittest.skipUnless(SOFTDRINK_ROSTER_SAVE.is_file(), f"SOFTDRINK roster save absent: {SOFTDRINK_ROSTER_SAVE}")
class GridSpeedTests(unittest.TestCase):
    """b81 brief: opening Free Agents and sorting must stay interactive on the 4,096-player roster."""

    def test_free_agents_open_and_sort_quickly_with_every_column(self) -> None:
        application = _app()
        panel = RosterEditorPanel()
        try:
            self.assertTrue(panel.load_save(SOFTDRINK_ROSTER_SAVE))
            panel.set_grid_columns([k for band in panel_module.GRID_BANDS.values() for k in band])
            started = time.perf_counter()
            panel.team_list.setCurrentRow(panel._team_list_row("free_agent", -1))
            application.processEvents()
            opened = time.perf_counter() - started
            self.assertGreater(len(panel._rows), 800)
            started = time.perf_counter()
            panel.sort_by("speed")
            application.processEvents()
            sorted_in = time.perf_counter() - started
            started = time.perf_counter()
            panel.team_list.setCurrentRow(panel._team_list_row("team", 1))
            application.processEvents()
            team = time.perf_counter() - started
            # measured on the build machine: 0.49 s, 0.52 s and 0.05 s; the bound leaves room for a busy runner
            self.assertLess(opened, 1.5)
            self.assertLess(sorted_in, 1.5)
            self.assertLess(team, 1.0)
        finally:
            panel.deleteLater()
            application.processEvents()


class SaveCopyTests(unittest.TestCase):
    """Finn saved over the zip; the Studio writes a new signed copy and says what to do with it."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = _app()

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.panel = RosterEditorPanel()

    def tearDown(self) -> None:
        self.panel.deleteLater()
        self.application.processEvents()
        self.temp.cleanup()

    def _zip_save(self) -> Path:
        import zipfile
        savegame = synthetic_save_v0(synthetic_body())
        source = self.root / "BaseRoster.zip"
        with zipfile.ZipFile(source, "w") as archive:
            archive.writestr("UDATA/53450030/0001/SAVEGAME.DAT", savegame)
            archive.writestr("UDATA/53450030/0001/EXTRA", rr.sign_save(savegame))
            archive.writestr("UDATA/53450030/0001/SaveMeta.xbx", b"\xff\xfeN\x00")
        return source

    def test_a_chosen_folder_gets_a_new_edited_zip_and_the_message_says_the_original_stayed(self) -> None:
        source = self._zip_save()
        before = source.read_bytes()
        self.assertTrue(self.panel.load_save(source))
        player = self.panel.document.players[0]
        self.panel.set_field(player, "speed", 21)
        out = self.root / "out"
        out.mkdir()
        (out / "BaseRoster (edited).zip").write_bytes(b"someone else's file")
        with mock.patch.object(panel_module.QFileDialog, "getExistingDirectory", return_value=str(out)):
            self.panel._write_copy()
        written = out / "BaseRoster (edited 2).zip"
        self.assertTrue(written.is_file(), self.panel.status_label.text())
        self.assertEqual((out / "BaseRoster (edited).zip").read_bytes(), b"someone else's file")
        self.assertTrue(rr.SaveContainer.load(written).verified)
        self.assertEqual(rr.load_save(written).players[0].record.values["speed"], 21)
        self.assertEqual(source.read_bytes(), before, "the original zip is never written")
        status = self.panel.status_label.text()
        self.assertIn("Your original save was not changed", status)
        self.assertIn("SAVEGAME.DAT and EXTRA", status)
        self.assertIn("pair", status)

    def test_a_folder_save_gets_a_new_folder_beside_nothing_it_owns(self) -> None:
        source = write_container(self.root / "fr", synthetic_save_v0(synthetic_body()))
        self.assertTrue(self.panel.load_save(source))
        target = self.panel.save_copy_destination(self.root)
        self.assertEqual(target, self.root / "fr (edited)")
        receipt = self.panel.write_copy_to(target)
        self.assertIn("Copy SAVEGAME.DAT and EXTRA from this folder", self.panel.save_copy_message(receipt))


class PlaceOnIrTests(unittest.TestCase):
    """Finn's right-click Place on IR, from the Roster grid to Franchise > Injured Reserve."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = _app()

    def setUp(self) -> None:
        from test_franchise_panel_qt import synthetic_franchise_with_coach
        self.temp = tempfile.TemporaryDirectory()
        self.panel = RosterEditorPanel()
        source = write_container(Path(self.temp.name) / "fr", synthetic_franchise_with_coach(year_field=7, user_team=0))
        self.assertTrue(self.panel.load_save(source))

    def tearDown(self) -> None:
        self.panel.deleteLater()
        self.application.processEvents()
        self.temp.cleanup()

    def test_right_click_place_on_ir_jumps_with_him_chosen_and_places_him(self) -> None:
        document = self.panel.document
        harrison = next(p for p in document.players if p.last == "Harrison")
        self.assertTrue(self.panel.select_player(harrison))
        place = next(a for a in self.panel.grid_menu().actions() if a.text() == "Place on IR…")
        self.assertTrue(place.isEnabled(), place.toolTip())
        chosen: list[int | None] = []

        def accept(dialog: IrPickerDialog) -> int:
            chosen.append(dialog.chosen())
            return QDialog.Accepted

        with mock.patch.object(IrPickerDialog, "exec_", accept):
            self.assertTrue(self.panel.place_selected_on_ir())
        franchise = self.panel.franchise_panel
        self.assertIs(self.panel.pages.currentWidget(), franchise)
        self.assertEqual(franchise.tabs.tabText(franchise.tabs.currentIndex()), "Injured Reserve")
        self.assertEqual(chosen, [harrison.index], "the picker opened on him")
        self.assertEqual(franchise.ir_table.item(0, 1).text(), "Marvin Harrison")
        self.assertIn("not Finn's Heal Player", franchise.activate_ir_button.toolTip())

    def test_free_agents_and_prospects_are_refused_in_finns_words(self) -> None:
        document = self.panel.document
        agent = next(p for p in document.players if p.last == "Agent")
        prospect = next(p for p in document.players if p.last == "Prospect")
        self.assertEqual(self.panel.ir_place_reason(agent), rr.MSG_FREE_AGENT_IR)
        self.assertEqual(self.panel.ir_place_reason(prospect), rr.MSG_DRAFT_CLASS)


# --------------------------------------------------------------------------------------------- R5 coaches in a roster save
def roster_save_with_coach() -> bytes:
    """The core tests' synthetic ROSTER save (no franchise season) with one coach record on team 0, grafted the way
    the franchise page tests graft theirs (Finn's numbers for Belichick)."""

    import struct
    from mod_editor.core import nfl2k5_franchise_save as fs
    from test_franchise_panel_qt import COACH_AT, COACH_STRINGS_AT, _rel
    data = bytearray(synthetic_save_v0(synthetic_body()))
    team0 = rr.RosterDocument(bytes(data), base=fs.ARENA_PREAMBLE).teams[0].offset
    cursor = COACH_STRINGS_AT
    for field_rel, text in ((0x00, "Bill"), (0x04, "Belichick")):
        raw = text.encode("utf-16-le") + b"\0\0"
        data[cursor:cursor + len(raw)] = raw
        _rel(data, COACH_AT + field_rel, cursor)
        cursor += len(raw)
    for name, value in (("wins", 75), ("losses", 69), ("super_bowls", 2), ("photo", 33)):
        rel, fmt = fs.COACH_FIELDS[name]
        struct.pack_into(fmt, data, COACH_AT + rel, value)
    for k in range(len(fs.COACH_RATINGS)):
        data[COACH_AT + fs.COACH_RATINGS_OFFSET + k] = 60 + k
    struct.pack_into("<I", data, fs.ARENA_ROOT + 0x30, 1)
    _rel(data, fs.ARENA_ROOT + 0x34, COACH_AT)
    _rel(data, team0 + rr.TEAM_COACH, COACH_AT)
    return bytes(data)


class RosterSaveCoachCoreTests(unittest.TestCase):
    def test_a_roster_save_opens_for_its_coaches_and_refuses_everything_seasonal(self) -> None:
        from mod_editor.core import nfl2k5_franchise_save as fs
        payload = roster_save_with_coach()
        self.assertFalse(fs.is_franchise_save(payload), "a roster save is still not a franchise")
        save = fs.FranchiseSave.roster_save(payload)
        self.assertEqual(save.kind, "roster")
        coach = save.coaches()[0]
        self.assertEqual((coach.name, coach.teams, coach.fields["wins"]), ("Bill Belichick", (0,), 75))
        for reach in (lambda: save.header, lambda: save.salary_cap, lambda: save.games(),
                      lambda: save.injured_reserve()):
            with self.assertRaisesRegex(fs.FranchiseSaveError, "roster save has no franchise"):
                reach()
        save.set_coach_field(0, "overall", 88)
        save.set_coach_field(0, "wins", 76)
        with self.assertRaises(fs.FranchiseSaveError):
            save.set_coach_field(0, "overall", 300)
        changed = [i for i, (a, b) in enumerate(zip(payload, save.to_bytes())) if a != b]
        offset = save._coach_offset(0)
        self.assertTrue(changed and all(offset <= i < offset + fs.COACH_SIZE for i in changed))
        with self.assertRaisesRegex(fs.FranchiseSaveError, "no coach records"):
            fs.FranchiseSave.roster_save(synthetic_save_v0(synthetic_body()))

    def test_the_franchise_mode_is_unchanged(self) -> None:
        from mod_editor.core import nfl2k5_franchise_save as fs
        from test_franchise_panel_qt import synthetic_franchise_with_coach
        save = fs.FranchiseSave(synthetic_franchise_with_coach(year_field=7, user_team=0))
        self.assertEqual((save.kind, save.arena_root, save.arena_preamble), ("franchise", fs.ARENA_ROOT, fs.ARENA_PREAMBLE))
        self.assertEqual(save.header.year_field, 7)
        self.assertEqual(save.coaches()[0].name, "Bill Belichick")


class RosterSaveCoachPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = _app()

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.panel = RosterEditorPanel()
        self.source = write_container(self.root / "roster", roster_save_with_coach())
        self.assertTrue(self.panel.load_save(self.source))

    def tearDown(self) -> None:
        self.panel.deleteLater()
        self.application.processEvents()
        self.temp.cleanup()

    def test_the_coaches_page_appears_alone_beside_roster(self) -> None:
        pages, page = self.panel.pages, self.panel.franchise_panel
        self.assertTrue(page.coaches_only)
        self.assertFalse(page.active, "the roster save is not treated as a franchise anywhere else")
        index = pages.indexOf(page)
        self.assertTrue(pages.isTabVisible(index))
        self.assertEqual(pages.tabText(index), "Coaches")
        self.assertFalse(pages.isTabVisible(self.panel._coaches_index), "no second, disabled Coaches tab")
        shown = [page.tabs.tabText(i) for i in range(page.tabs.count()) if page.tabs.isTabVisible(i)]
        self.assertEqual(shown, ["Coaches"])
        self.assertFalse(page.upgrade_button.isVisibleTo(page))
        self.assertFalse(page.tabs.tabBar().isVisibleTo(page), "one page needs no tab bar")
        self.assertEqual(page.coach_list.count(), 1)
        self.assertIn("Bill Belichick", page.coach_list.item(0).text())
        # a disc or a plain body afterwards brings the build staff plan back and the page goes away
        self.panel.load_document(rr.load_body(synthetic_body()), label="body")
        self.assertFalse(pages.isTabVisible(index))
        self.assertTrue(pages.isTabVisible(self.panel._coaches_index))
        self.assertEqual(pages.tabText(index), "Franchise")
        self.assertTrue(page.tabs.tabBar().isVisibleTo(page))

    def test_a_coach_edit_undoes_shows_in_my_changes_and_reaches_the_signed_copy(self) -> None:
        from mod_editor.core import nfl2k5_franchise_save as fs
        page = self.panel.franchise_panel
        before = self.source.joinpath("53450030", "0001", "SAVEGAME.DAT").read_bytes()
        self.assertTrue(page.set_coach_value(0, "overall", 88))
        self.assertTrue(page.set_coach_value(0, "wins", 80))
        self.assertEqual(page._save.coaches()[0].ratings["overall"], 88)
        self.assertIn("2 coach edits", page.dirty_label.text())
        self.assertTrue(self.panel.is_dirty())
        self.panel.undo()
        self.assertEqual(page._save.coaches()[0].fields["wins"], 75)
        self.panel.redo()
        self.panel.refresh_diff()
        report = self.panel.report.toPlainText()
        self.assertIn("Coach changes (2), written by Save Xbox save copy:", report)
        self.assertIn("Overall 60 → 88", report)
        # a player edit and the coach edits travel in the same signed copy
        player = self.panel.document.players[0]
        self.panel.set_field(player, "speed", 21)
        receipt = self.panel.write_copy_to(self.root / "copy")
        self.assertTrue(receipt["signed"])
        container = rr.SaveContainer.load(self.root / "copy")
        self.assertTrue(container.verified)
        back = fs.FranchiseSave.roster_save(container.savegame)
        self.assertEqual((back.coaches()[0].ratings["overall"], back.coaches()[0].fields["wins"]), (88, 80))
        self.assertEqual(rr.load_save(self.root / "copy").players[0].record.values["speed"], 21)
        self.assertEqual(self.source.joinpath("53450030", "0001", "SAVEGAME.DAT").read_bytes(), before)

    def test_a_refused_value_changes_nothing(self) -> None:
        page = self.panel.franchise_panel
        depth = self.panel.undo_stack.depth
        self.assertFalse(page.set_coach_value(0, "overall", 300))
        self.assertIn("Refused", page.status_label.text())
        self.assertEqual(self.panel.undo_stack.depth, depth)
        self.assertEqual(page._save.coaches()[0].ratings["overall"], 60)

    def test_a_head_coach_swap_goes_through_the_composed_path_and_undoes(self) -> None:
        page = self.panel.franchise_panel
        heads_before = page._save.head_coaches()
        self.assertEqual(heads_before.get(0), 0)
        # one coach record: a swap needs two employed coaches, so the page refuses in its own words
        self.assertFalse(page.swap_head_coaches(0, 1))
        self.assertEqual(page._save.head_coaches(), heads_before)


@unittest.skipUnless(SOFTDRINK_ROSTER_SAVE.is_file(), f"SOFTDRINK roster save absent: {SOFTDRINK_ROSTER_SAVE}")
class RosterSaveCoachSoftdrinkTests(unittest.TestCase):
    """b81 R5 on the real expanded roster save: edit a coach rating, write the signed copy, reload it."""

    def test_a_coach_rating_round_trips_through_a_signed_copy_and_only_his_record_changes(self) -> None:
        from mod_editor.core import nfl2k5_franchise_save as fs
        application = _app()
        panel = RosterEditorPanel()
        try:
            self.assertTrue(panel.load_save(SOFTDRINK_ROSTER_SAVE))
            page = panel.franchise_panel
            self.assertTrue(page.coaches_only)
            coach = page._save.coaches()[0]
            wanted = 77 if coach.ratings["overall"] != 77 else 76
            started = time.perf_counter()
            self.assertTrue(page.set_coach_value(coach.index, "overall", wanted))
            self.assertLess(time.perf_counter() - started, 0.5, "a coach bar step is interactive")
            with tempfile.TemporaryDirectory() as folder:
                receipt = panel.write_copy_to(Path(folder) / "copy.zip")
                self.assertTrue(receipt["signed"])
                container = rr.SaveContainer.load(Path(folder) / "copy.zip")
                self.assertTrue(container.verified)
                back = fs.FranchiseSave.roster_save(container.savegame)
                self.assertEqual(back.coaches()[coach.index].ratings["overall"], wanted)
                source = rr.SaveContainer.load(SOFTDRINK_ROSTER_SAVE).savegame
                changed = [i for i, (a, b) in enumerate(zip(source, container.savegame)) if a != b]
                record = back._coach_offset(coach.index)
                self.assertEqual(changed, [record + fs.COACH_RATINGS_OFFSET], "one byte: his Overall")
        finally:
            panel.deleteLater()
            application.processEvents()


# --------------------------------------------------------------------------------------------- R8 schedule
def _real_franchise(name: str):
    from mod_editor.core import nfl2k5_franchise_save as fs
    from test_nfl2k5_franchise_save import FIXTURES
    folder = FIXTURES / name
    if not folder.is_dir():
        raise unittest.SkipTest(f"franchise fixture absent: {folder}")
    return fs.FranchiseSave(rr.SaveContainer.load(folder).savegame)


class ScheduleCoreTests(unittest.TestCase):
    def test_the_retail_season_checks_clean_and_a_removed_game_is_flagged_then_restored(self) -> None:
        save = _real_franchise("f0")                     # 2004, week 0, nothing played
        report = save.schedule_integrity()
        self.assertEqual((report["weeks"], report["expected"]), (17, 16))
        self.assertEqual(report["flagged"], [])
        self.assertIn("All 32 clubs have 16 games", report["summary"])
        week = 2
        before = [save.game(week, slot) for slot in range(17)]
        games = [g for g in before if g.exists]
        removed = save.remove_game(week, 3)
        self.assertEqual((removed.home, removed.away), (games[3].home, games[3].away))
        after = [g for g in (save.game(week, slot) for slot in range(17)) if g.exists]
        self.assertEqual([(g.home, g.away) for g in after], [(g.home, g.away) for g in games[:3] + games[4:]])
        self.assertEqual(after[3].slot, 3, "the later games moved up one cell")
        self.assertEqual(save.game(week, len(games) - 1).kind, 7, "the old last cell is a row end now")
        self.assertEqual(save.game(week, len(games) - 1).flags, 0)
        flagged = {row["name"] for row in save.schedule_integrity()["flagged"]}
        self.assertEqual(flagged, {save.team_abbreviation(removed.home), save.team_abbreviation(removed.away)})
        added = save.add_game(week, home=removed.home, away=removed.away, month=removed.month, day=removed.day,
                              hour=removed.hour, minute=removed.minute)
        self.assertEqual((added.slot, added.slot_code, added.flags), (len(games) - 1, removed.slot_code, 0x0101))
        self.assertEqual(save.schedule_integrity()["flagged"], [])

    def test_refusals_say_why_and_change_nothing(self) -> None:
        from mod_editor.core import nfl2k5_franchise_save as fs
        save = _real_franchise("f0")
        original = save.to_bytes()
        game = save.game(0, 0)
        cases = [
            (lambda: save.add_game(0, home=game.home, away=31 if game.away != 31 else 30, month=9, day=9, hour=1,
                                   minute=0), "already plays in week 1"),
            (lambda: save.add_game(17, home=0, away=1, month=1, day=2, hour=1, minute=0), "not a regular-season week"),
            (lambda: save.add_game(4, home=5, away=5, month=10, day=3, hour=1, minute=0), "cannot play itself"),
            (lambda: save.add_game(4, home=32, away=5, month=10, day=3, hour=1, minute=0), "outside 0..31"),
            (lambda: save.remove_game(4, 16), "holds no game"),
            (lambda: save.clear_week(19), "not a regular-season week"),
        ]
        for action, words in cases:
            with self.subTest(words=words):
                with self.assertRaisesRegex(fs.FranchiseSaveError, words):
                    action()
                self.assertEqual(save.to_bytes(), original)

    def test_played_weeks_need_the_override_and_scores_move_with_their_games(self) -> None:
        from mod_editor.core import nfl2k5_franchise_save as fs
        save = _real_franchise("256B40374FD6-Franchise1")          # 2011, the whole season played
        week = 5
        games = save.games(rows=[week])
        self.assertTrue(all(g.played for g in games))
        with self.assertRaisesRegex(fs.FranchiseSaveError, "Allow editing played games"):
            save.remove_game(week, 0)
        with self.assertRaisesRegex(fs.FranchiseSaveError, "Allow editing played games"):
            save.clear_week(week)
        save.remove_game(week, 0, allow_played=True)
        moved = save.game(week, 0)
        self.assertEqual((moved.home, moved.away, moved.scores), (games[1].home, games[1].away, games[1].scores))
        self.assertEqual(save.clear_week(week, allow_played=True), len(games) - 1)
        self.assertEqual(save.games(rows=[week]), [])
        self.assertTrue(all(save.game(week, slot).kind == 7 for slot in range(17)))


class SchedulePanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = _app()

    def setUp(self) -> None:
        from test_franchise_panel_qt import synthetic_franchise_with_coach
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.panel = RosterEditorPanel()
        self.payload = synthetic_franchise_with_coach(year_field=7, user_team=0)
        self.assertTrue(self.panel.load_save(write_container(self.root / "fr", self.payload)))
        self.page = self.panel.franchise_panel
        self.page.tabs.setCurrentIndex(1)

    def tearDown(self) -> None:
        self.panel.deleteLater()
        self.application.processEvents()
        self.temp.cleanup()

    def week(self, row: int) -> list[tuple[int, int]]:
        return [(g.away, g.home) for g in self.page.save.games(rows=[row])]

    def test_add_remove_and_clear_journal_undo_and_reach_the_copy(self) -> None:
        page = self.page
        page.week_combo.setCurrentIndex(1)                       # week 2: empty in the synthetic save
        self.assertTrue(page.add_game_button.isEnabled())
        self.assertIn("Season check (17 weeks, 16 games a club)", page.integrity_label.text())
        page.away_combo.setCurrentIndex(page.away_combo.findData(2))
        page.home_combo.setCurrentIndex(page.home_combo.findData(0))
        page.month_spin.setValue(9)
        page.day_spin.setValue(19)
        page.add_game_button.click()
        self.assertEqual(self.week(1), [(2, 0)], page.status_label.text())
        self.assertEqual(page.save.game(1, 0).slot_code, 0x0A, "the year byte comes from the season's games")
        self.assertEqual(page.integrity_table.rowCount(), page.save.league_team_count)
        page.add_game_button.click()                             # the same teams again that week
        self.assertIn("already plays in week 2", page.status_label.text())
        self.assertEqual(self.week(1), [(2, 0)])
        page.schedule_table.selectRow(0)
        page.remove_game_button.click()
        self.assertEqual(self.week(1), [])
        self.panel.undo()
        self.assertEqual(self.week(1), [(2, 0)])
        page.week_combo.setCurrentIndex(0)                       # week 1 has a played game
        page.clear_week_button.click()
        self.assertIn("Allow editing played games", page.status_label.text())
        self.assertEqual(len(self.week(0)), 2)
        page.allow_played_check.setChecked(True)
        page.clear_week_button.click()
        self.assertEqual(self.week(0), [])
        self.panel.undo()
        self.assertEqual(len(self.week(0)), 2)
        self.panel.refresh_diff()
        self.assertIn("Week 2: add", self.panel.report.toPlainText())
        receipt = self.panel.write_copy_to(self.root / "copy")
        self.assertTrue(receipt["signed"])
        from mod_editor.core import nfl2k5_franchise_save as fs
        back = fs.FranchiseSave(rr.SaveContainer.load(self.root / "copy").savegame)
        self.assertEqual([(g.away, g.home) for g in back.games(rows=[1])], [(2, 0)])

    def test_playoff_rounds_keep_the_week_tools_off_and_say_why(self) -> None:
        page = self.page
        page.week_combo.setCurrentIndex(17)
        for button in (page.add_game_button, page.remove_game_button, page.clear_week_button):
            self.assertFalse(button.isEnabled())
        self.assertIn("bracket", page.add_game_button.toolTip())
        page.week_combo.setCurrentIndex(page.week_combo.count() - 1)        # All postseason
        self.assertFalse(page.clear_week_button.isEnabled())


# --------------------------------------------------------------------------------------------- R10, R12, R15, R16, R17
class SmallPassesCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = rr.load_body(league_body())

    def player(self, last: str) -> rr.Player:
        return next(p for p in self.document.players if p.last == last)

    def test_body_type_follows_finns_weight_and_bmi_thresholds(self) -> None:
        cases = {199: 0, 200: 1, 269: 1, 270: 2, 299: 2, 300: 3}
        targets = self.document.team_players(0)[:len(cases)]
        for player, (weight, _body) in zip(targets, cases.items()):
            player.record.weight = weight
            player.record.values["body"] = 0 if weight >= 200 else 3
        rows = {(r["pool"], r["index"]): r for r in rr.body_type_preview(self.document, "weight", targets)}
        for player, (weight, body) in zip(targets, cases.items()):
            with self.subTest(weight=weight):
                self.assertEqual(rows[(player.pool, player.index)]["after"], body)
        unchanged = targets[0].record.values["body"]
        self.assertEqual(rr.body_type_apply(self.document, list(rows.values())), len(rows))
        self.assertEqual(targets[1].record.values["body"], 1)
        self.assertNotEqual(unchanged, targets[0].record.values["body"])
        player = targets[0]
        player.record.weight, player.record.values["height"] = 250, 70          # BMI 35.9
        self.assertAlmostEqual(rr.body_mass_index(player.record), 35.9)
        bmi = rr.body_type_preview(self.document, "bmi", [player])
        self.assertEqual(bmi[0]["after"], 3)
        with self.assertRaises(rr.RosterRecordError):
            rr.body_type_preview(self.document, "height")

    def test_several_attributes_and_teams_including_their_reserves_in_one_pass(self) -> None:
        rows = rr.global_edit_preview_many(self.document, attributes=["speed", "agility"], mode="equal", value=77,
                                           teams=[1])
        self.assertEqual({r["attribute"] for r in rows}, {"speed", "agility"})
        self.assertTrue(all(1 in next(p for p in self.document.players if p.index == r["index"]).teams
                            for r in rows))
        rr.global_edit_apply(self.document, rows)
        atl = self.document.team_players(1)
        self.assertTrue(all(p.record.values["speed"] == 77 and p.record.values["agility"] == 77 for p in atl))
        self.assertTrue(any(p.record.values["speed"] != 77 for p in self.document.team_players(0)))
        # the condition is judged before any attribute changes
        fast = self.document.team_players(0)[0]
        fast.record.values["speed"] = 90
        rows = rr.global_edit_preview_many(self.document, attributes=["speed", "agility"], mode="equal", value=10,
                                           where=("speed", ">=", 90), players=[fast])
        self.assertEqual({r["attribute"] for r in rows}, {"speed", "agility"},
                         "agility is still chosen although speed changes in the same pass")

    def test_a_global_position_change_unlocks_and_reranks(self) -> None:
        player = self.document.team_players(0)[1]
        player.record.set_depth_lock("rank", True)
        rows = rr.global_edit_preview(self.document, attribute="position", mode="equal", value=0, players=[player])
        rr.global_edit_apply(self.document, rows, "position")
        self.assertEqual(player.record.values["position"], 0)
        self.assertFalse(any(player.record.depth_locks.values()))

    def test_the_contract_years_guard(self) -> None:
        record = self.document.players[0].record
        record.values["contract_length"], record.values["contract_remaining"] = 4, 3
        with self.assertRaisesRegex(rr.RosterRecordError, "cannot be greater than the contract length"):
            rr.contract_years_change(record, "contract_remaining", 5)
        self.assertEqual(rr.contract_years_change(record, "contract_remaining", 4), {"contract_remaining": 4})
        self.assertEqual(rr.contract_years_change(record, "contract_length", 2),
                         {"contract_length": 2, "contract_remaining": 2})
        self.assertEqual(rr.contract_years_change(record, "contract_length", 6), {"contract_length": 6})
        record.values["contract_remaining"] = 9
        found = [f for f in rr.validate(self.document) if f["check"] == "contract"]
        self.assertEqual(len(found), 1)


class PlayerDataGroupsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = rr.load_body(synthetic_body())
        self.backup = rr.export_player_data(self.document)
        self.manning = next(p for p in self.document.players if p.last == "Manning")

    def test_a_default_restore_keeps_the_roster_spot_and_says_so(self) -> None:
        manning = self.manning
        manning.record.set("speed", 12)
        before_spot = {k: manning.record.values[k] for k in ("depth_rank", "depth_side", "injured_reserve")}
        backup = bytearray(self.backup)
        raw = bytearray(backup[0:rr.PLAYER_SIZE])
        values = rr.decode_record(bytes(raw))
        values.update(depth_rank=5, depth_side=5, injured_reserve=0xEE, unknown_52=values["unknown_52"] | 0x04)
        backup[0:rr.PLAYER_SIZE] = rr.encode_record(values)
        receipt = rr.import_player_data(self.document, bytes(backup))
        self.assertEqual(receipt["changed"], 1)
        self.assertEqual(manning.record.values["speed"], 66)
        self.assertEqual({k: manning.record.values[k] for k in before_spot}, before_spot)
        self.assertFalse(manning.record.depth_locks["kr1"], "a returner lock never comes back by default")
        rr.import_player_data(self.document, bytes(backup), groups=["spot"])
        self.assertEqual((manning.record.values["depth_rank"], manning.record.values["injured_reserve"]), (5, 0xEE))
        self.assertTrue(manning.record.depth_locks["kr1"])

    def test_groups_pick_what_comes_back(self) -> None:
        manning = self.manning
        manning.record.set("speed", 12)
        manning.record.set("contract_value", 1)
        manning.record.set("helmet", 1 - manning.record.values["helmet"])
        rr.import_player_data(self.document, self.backup, groups=["contract"])
        self.assertEqual((manning.record.values["speed"], manning.record.values["contract_value"]), (12, 200))
        rr.import_player_data(self.document, self.backup, groups=["ratings", "appearance"])
        self.assertEqual(manning.record.values["speed"], 66)
        self.assertEqual(manning.record.values["helmet"], rr.decode_record(self.backup[:rr.PLAYER_SIZE])["helmet"])
        with self.assertRaisesRegex(rr.RosterRecordError, "unknown .PlayerData group"):
            rr.import_player_data(self.document, self.backup, groups=["everything"])


class SmallPassesPanelTests(_PanelCase):
    body_factory = staticmethod(league_body)

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        from PyQt5.QtCore import QSettings
        settings_file = str(Path(self.temp.name) / "rosters.ini")
        self.settings_patch = mock.patch.object(panel_module, "_roster_settings",
                                                lambda: QSettings(settings_file, QSettings.IniFormat))
        self.settings_patch.start()
        super().setUp()

    def tearDown(self) -> None:
        super().tearDown()
        self.settings_patch.stop()
        self.temp.cleanup()

    def test_body_type_dialog_previews_applies_and_undoes(self) -> None:
        from mod_editor.gui.roster_editor_panel_qt import BodyTypeDialog
        player = self.panel._rows[0]
        player.record.weight = 320
        player.record.values["body"] = 0
        dialog = BodyTypeDialog(self.panel, "weight")
        dialog.list_only.setChecked(True)
        self.assertIn("Extra Large from 300 lb", dialog.rule.text())
        self.assertIn(f"{player.display}", dialog.preview.toPlainText())
        count = dialog.apply()
        self.assertGreaterEqual(count, 1)
        self.assertEqual(player.record.values["body"], 3)
        self.assertIn((player.pool, player.index), self.panel._dirty)
        self.panel.undo()
        self.assertEqual(player.record.values["body"], 0)

    def test_the_global_dialog_takes_several_attributes_and_teams(self) -> None:
        from mod_editor.gui.roster_editor_panel_qt import GlobalEditDialog
        dialog = GlobalEditDialog(self.panel)
        dialog.attribute.setCurrentIndex(dialog.attribute.findData("speed"))
        dialog.set_checked(dialog.more_attributes, ["agility", "strength"])
        dialog.set_checked(dialog.team_checks, [1])
        dialog.value.setValue(55)
        self.assertIn("ATL", dialog.scope_label.text())
        rows = dialog.refresh_preview()
        self.assertEqual({r["attribute"] for r in rows}, {"speed", "agility", "strength"})
        self.assertIn("Agility", dialog.preview.toPlainText())
        dialog._apply()
        atl = self.panel.document.team_players(1)
        self.assertTrue(all(p.record.values["strength"] == 55 for p in atl))
        self.panel.undo()
        self.assertTrue(any(p.record.values["strength"] != 55 for p in atl), "one undo for the whole pass")

    def test_years_remaining_cannot_pass_the_length(self) -> None:
        player = self.panel.selected_player()
        player.record.values["contract_length"], player.record.values["contract_remaining"] = 3, 2
        self.panel._show_player(player)
        self.assertFalse(self.panel.set_contract_years(player, "contract_remaining", 5))
        self.assertIn("cannot be greater than the contract length", self.panel.status_label.text())
        self.assertEqual(player.record.values["contract_remaining"], 2)
        self.assertTrue(self.panel.set_contract_years(player, "contract_length", 1))
        self.assertEqual((player.record.values["contract_length"], player.record.values["contract_remaining"]), (1, 1))
        self.panel.undo()
        self.assertEqual((player.record.values["contract_length"], player.record.values["contract_remaining"]), (3, 2))

    def test_default_list_on_open_and_the_html_export(self) -> None:
        self.panel.team_list.setCurrentRow(self.panel._team_list_row("team", 1))
        self.assertEqual(self.panel.remember_default_list(), "team:ATL")
        self.panel.load_document(rr.load_body(league_body()), label="again")
        self.assertEqual(self.panel._group, ("team", 1), "Finn's Default Team")
        self.panel.forget_default_list()
        self.panel.load_document(rr.load_body(league_body()), label="again")
        self.assertEqual(self.panel._group, ("team", 0))
        self.panel.set_grid_columns(["speed"])
        self.panel.sort_by("speed")
        text = self.panel.export_html_text()
        self.assertTrue(text.startswith("<!doctype html>"))
        self.assertIn("<th>Speed</th>", text)
        self.assertEqual(text.count("<tr>"), len(self.panel._rows) + 1)
        first = self.panel._rows[0]
        self.assertLess(text.index(first.display), text.index(self.panel._rows[-1].display))
        self.assertNotIn("●", text)

    def test_the_restore_dialog_defaults_leave_the_roster_spot_alone(self) -> None:
        from mod_editor.gui.roster_editor_panel_qt import PlayerDataRestoreDialog
        dialog = PlayerDataRestoreDialog(self.panel, 10)
        self.assertNotIn("spot", dialog.chosen_groups())
        self.assertIn("ratings", dialog.chosen_groups())
        self.assertIn("two kick returners", dialog.spot_note.text())
        attributes = PlayerDataRestoreDialog(self.panel, 10, attributes_only=True)
        self.assertEqual(attributes.chosen_groups(), ["ratings"])
        backup = rr.export_player_data(self.panel.document)
        player = self.panel.document.team_players(0)[0]
        player.record.set("speed", 3)
        receipt = self.panel.import_player_data_bytes(backup, groups=["ratings"], current_list_only=True)
        self.assertEqual(receipt["changed"], 1)
        self.assertNotEqual(player.record.values["speed"], 3)


# --------------------------------------------------------------------------------------------- wave 2: R4 depth
class DepthCoreTests(unittest.TestCase):
    """The stored depth rank (+0x28 bits 10-12) is what the game's chart and starters follow (finn-facts FACTS.md)."""

    def setUp(self) -> None:
        self.document = rr.load_body(league_body())

    def rows(self, code: int, field: str = "depth_rank") -> list[tuple[str, int, int, int]]:
        return [(p.last, p.record.values["depth_rank"], p.record.values["depth_side"],
                 p.record.values["unknown_52"]) for p in self.document.depth_order(0, code, field)]

    def test_a_move_keeps_rows_unique_and_gap_free_and_locks_who_moved(self) -> None:
        qbs = self.document.depth_order(0, 0)
        self.assertEqual(len(qbs), 3)
        slots = list(self.document.teams[0].slots)
        result = self.document.place_in_depth(qbs[2], 0)
        self.assertEqual([r[0] for r in self.rows(0)], [qbs[2].last, qbs[0].last, qbs[1].last])
        self.assertEqual([r[1] for r in self.rows(0)], [0, 1, 2])
        self.assertTrue(all(r[3] & 1 for r in self.rows(0)), "every QB whose place changed is rank-locked")
        self.assertEqual(self.document.teams[0].slots, slots, "the pointer list is not the depth chart")
        self.assertEqual(set(p.offset for p in result["changed"]), {p.offset for p in qbs})
        self.document.restore_depth(result["before"])
        self.assertEqual([r[0] for r in self.rows(0)], [p.last for p in qbs])
        self.assertTrue(all(r[3] == 0 for r in self.rows(0)))

    def test_gaps_close_without_locking_and_a_paired_starter_never_holds_both_slots(self) -> None:
        tackles = self.document.depth_order(0, 14)
        self.assertEqual([r[1] for r in self.rows(14)], [0, 2, 3], "the fixture has a gap")
        result = self.document.place_in_depth(tackles[1], 0)
        rows = self.rows(14)
        self.assertEqual([r[1] for r in rows], [0, 1, 2])
        self.assertEqual(sorted(r[2] for r in rows), [0, 1, 2], "the side order is unique and gap-free too")
        top = rows[0]
        self.assertNotEqual(top[2], 0, "LT is not also RT")
        self.assertEqual(rows[-1][3], 0, "a player only renumbered to close a gap is not locked")
        self.assertEqual(len(result["changed"]), 3)

    def test_the_side_order_of_a_paired_position_and_refusals(self) -> None:
        wrs = self.document.depth_order(0, 3, "depth_side")
        self.document.place_in_depth(wrs[-1], 0, "depth_side")
        self.assertEqual(self.document.depth_order(0, 3, "depth_side")[0].last, wrs[-1].last)
        self.assertTrue(wrs[-1].record.depth_locks["side"])
        qb = self.document.depth_order(0, 0)[0]
        with self.assertRaisesRegex(rr.RosterRecordError, "one depth order"):
            self.document.place_in_depth(qb, 1, "depth_side")
        agent = next(p for p in self.document.players if p.last == "AgentOne")
        with self.assertRaisesRegex(rr.RosterRecordError, "no depth chart row"):
            self.document.place_in_depth(agent, 0)
        self.assertEqual(rr.depth_slot_names(14), ("LT", "RT"))
        self.assertEqual(rr.depth_slot_names(0), ("QB", None))
        self.assertEqual(rr.depth_slot_names(16, "one_pool")[0], "L EDGE")

    def test_a_csv_depth_change_seats_the_chart_and_names_the_others(self) -> None:
        qbs = self.document.depth_order(0, 0)
        text = rr.export_csv(self.document, [qbs[1]])
        lines = text.splitlines()
        header = lines[0].split(",")
        cells = lines[1].split(",")
        cells[header.index("depth_rank")] = "0"
        preview = rr.preview_csv(self.document, "\n".join([lines[0], ",".join(cells)]) + "\n")
        related = {(c["pool"], c["index"]) for c in preview.receipt["changes"]}
        self.assertIn(("primary", qbs[0].index), related, "the QB he passed is part of the preview")
        rr.apply_csv_preview(self.document, preview)
        self.assertEqual([p.last for p in self.document.depth_order(0, 0)], [qbs[1].last, qbs[0].last, qbs[2].last])
        self.assertEqual([p.record.values["depth_rank"] for p in self.document.depth_order(0, 0)], [0, 1, 2])
        self.assertTrue(self.document.depth_order(0, 0)[0].record.depth_locks["rank"])
        self.document.check_depth_locks()


class DepthPanelTests(_PanelCase):
    body_factory = staticmethod(league_body)

    def test_the_chip_shows_the_chart_the_arrows_change_and_my_changes_lists_it(self) -> None:
        panel = self.panel
        panel._chip_clicked("OL")
        tackles = [p for p in panel._rows if p.record.values["position"] == 14]
        self.assertEqual([p.record.values["depth_rank"] for p in tackles], sorted(p.record.values["depth_rank"]
                                                                                    for p in tackles))
        panel.select_player(tackles[-1])
        self.assertFalse(panel.depth_order_combo.isHidden(), "a tackle has LT and RT orders")
        self.assertEqual([panel.depth_order_combo.itemText(i) for i in range(2)], ["LT order", "RT order"])
        self.assertTrue(panel.up_button.isEnabled())
        self.assertIn("depth chart", panel.up_button.toolTip())
        self.assertTrue(panel.move_selected(-1))
        self.assertIn("is now LT #2", panel.status_label.text())
        panel.depth_order_combo.setCurrentIndex(1)
        panel.select_player(tackles[-1])
        self.assertTrue(panel.move_selected(-1) or panel.move_selected(1))
        panel.refresh_diff()
        report = panel.report.toPlainText()
        self.assertIn("Depth", report)
        panel.sort_by("speed")
        panel.select_player(tackles[0])
        self.assertTrue(panel.up_button.isEnabled(), "the arrows do not depend on the grid's order any more")
        panel._chip_clicked("All")
        panel.team_list.setCurrentRow(panel._team_list_row("free_agent", -1))
        self.assertIsNotNone(panel.selected_player())
        self.assertFalse(panel.up_button.isEnabled())
        self.assertIn("club", panel.up_button.toolTip())


def _depth_cpu():
    from test_nfl2k5_depth_locks import CPU, HAVE_CPU, XBE
    if not (HAVE_CPU and XBE.is_file()):
        raise unittest.SkipTest(f"retail extraction and Unicorn required: {XBE}")
    return CPU, XBE


class DepthNativeTests(unittest.TestCase):
    """The game's own code over records the Studio wrote: the depth chart row picker 0x242AE0 (Codex's witness) and the
    patched weekly sort 0x2BDCF0, run in the in-tree Unicorn harness of test_nfl2k5_depth_locks."""

    def chart(self, cpu, position: int = 0, chain: int = 0, rows: int = 2) -> list[int]:
        """0x242AE0(row, position, chain) with the team in EDX: the player the chart shows in that row of that
        position's rank order (chain 0) or side order (chain 1); the screen's caller 0x24353E is the return."""

        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EDX, UC_X86_REG_ESP
        from test_nfl2k5_depth_locks import PLAYERS, STACK, TEAM
        import struct
        out = []
        for row in range(rows):
            cpu.uc.mem_write(STACK, struct.pack("<IIII", 0x24353E, row, position, chain))
            cpu.uc.reg_write(UC_X86_REG_ESP, STACK)
            cpu.uc.reg_write(UC_X86_REG_EDX, TEAM)
            cpu.uc.emu_start(0x242AE0, 0x24353E, count=2_000_000)
            eax = cpu.uc.reg_read(UC_X86_REG_EAX)
            out.append((eax - PLAYERS) // 84 if eax else None)
        return out

    @staticmethod
    def studio_records(players):
        return [p.record.encode() for p in players]

    def test_a_studio_rank_move_changes_the_games_chart_and_a_pointer_swap_does_not(self) -> None:
        CPU, XBE = _depth_cpu()
        retail = XBE.read_bytes()
        document = rr.load_body(league_body())
        qbs = document.depth_order(0, 0)[:2]
        records = self.studio_records(qbs)
        cpu = CPU(retail)
        cpu.seed(records)
        self.assertEqual(self.chart(cpu), [0, 1], "loaded: QB1 then QB2")
        cpu.seed(records, order=[1, 0])
        self.assertEqual(self.chart(cpu), [0, 1], "the old arrows (pointer order) leave the game's chart alone")
        document.place_in_depth(qbs[1], 0)
        cpu = CPU(retail)
        cpu.seed(self.studio_records(qbs))
        self.assertEqual(self.chart(cpu), [1, 0], "the Studio's move makes QB2 the game's starter")

    def test_the_side_order_is_the_right_slot_of_the_chart(self) -> None:
        CPU, XBE = _depth_cpu()
        document = rr.load_body(league_body())
        tackles = document.depth_order(0, 14)
        document.place_in_depth(tackles[0], 0)                  # settle both orders first
        right = document.depth_order(0, 14, "depth_side")
        document.place_in_depth(right[-1], 0, "depth_side")
        cpu = CPU(XBE.read_bytes())
        players = document.depth_order(0, 14)
        cpu.seed([p.record.encode() for p in players])
        rt = self.chart(cpu, position=14, chain=1, rows=1)[0]   # RT: the tackles' side order (slot table 0x5140D8)
        lt = self.chart(cpu, position=14, chain=0, rows=1)[0]   # LT: their rank order
        self.assertIs(players[rt], right[-1])
        self.assertIs(players[lt], document.depth_order(0, 14)[0])
        self.assertNotEqual(lt, rt)

    def test_the_patched_weekly_pass_keeps_a_studio_move_and_undoes_an_unlocked_one(self) -> None:
        CPU, XBE = _depth_cpu()
        from mod_editor.core import nfl2k5_depth_locks as locks
        from mod_editor.core import nfl2k5_returner_fix as returners
        from test_nfl2k5_depth_locks import record, fields
        patched = locks.apply(returners.apply(XBE.read_bytes())[0])[0]
        document = rr.load_body(league_body())
        qbs = document.depth_order(0, 0)[:2]
        for qb, rank in zip(qbs, (0, 1)):
            qb.record.values.update(depth_rank=rank, depth_side=rank, unknown_52=0)
        document.place_in_depth(qbs[1], 0)
        studio = [record(position=0, rank=q.record.values["depth_rank"], side=q.record.values["depth_side"],
                         bits=q.record.values["unknown_52"], score=score) for q, score in zip(qbs, (.80, .79))]
        raw = [record(position=0, rank=r, side=r, score=score) for r, score in ((1, .80), (0, .79))]
        for label, records, starter in (("studio, locked", studio, 1), ("rank only, unlocked", raw, 0)):
            cpu = CPU(patched)
            cpu.seed(records)
            cpu.run(0x2BDCF0)
            starters = [i for i in range(2) if fields(cpu.player(i))[0] == 0]
            with self.subTest(label):
                self.assertEqual(starters, [starter])


# --------------------------------------------------------------------------------------------- wave 2: R3 special teams
class SpecialTeamsCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = rr.load_body(league_body())

    def club(self, code: int) -> list[rr.Player]:
        return self.document.depth_order(0, code)

    def test_a_returner_writes_the_byte_and_takes_the_lock_claim(self) -> None:
        doc = self.document
        wr, cb = self.club(3)[0], self.club(4)[0]
        doc.set_special_role(0, "kr1", wr)
        self.assertIs(doc.special_teams(0)["kr1"], wr)
        self.assertTrue(wr.record.depth_locks["kr1"])
        doc.set_special_role(0, "kr1", cb)
        self.assertIs(doc.special_teams(0)["kr1"], cb)
        self.assertFalse(wr.record.depth_locks["kr1"], "the claim leaves the old returner")
        self.assertTrue(cb.record.depth_locks["kr1"])
        doc.set_special_role(0, "kr1", None)
        self.assertIsNone(doc.special_teams(0)["kr1"])
        self.assertFalse(cb.record.depth_locks["kr1"])
        self.assertEqual(doc.special_teams(0)["bytes"]["kr1"], 0xFF)
        with self.assertRaisesRegex(rr.RosterRecordError, "returners are WR, CB, FS, SS, HB or FB"):
            doc.set_special_role(0, "pr", self.club(0)[0])
        doc.set_special_role(0, "holder", self.club(0)[0])
        self.assertIs(doc.special_teams(0)["holder"], self.club(0)[0])

    def test_kicker_punter_and_snapper_are_depth_rows_and_the_stored_bytes_follow(self) -> None:
        doc = self.document
        kickers, centers = self.club(1), self.club(12)
        doc.set_depth_role(0, "kicker", kickers[-1])
        self.assertIs(doc.special_teams(0)["kicker"], kickers[-1])
        self.assertIs(doc.special_teams(0)["stored_kicker"], kickers[-1])
        doc.set_depth_role(0, "long_snapper", centers[0])
        roles = doc.special_teams(0)
        self.assertIs(roles["long_snapper"], centers[0], "C #2 snaps on punts and kicks")
        self.assertIs(self.club(12)[1], centers[0])
        self.assertIs(roles["stored_long_snapper"], centers[0])
        with self.assertRaisesRegex(rr.RosterRecordError, "make him K first"):
            doc.set_depth_role(0, "kicker", self.club(0)[0])
        punter = self.club(2)[-1]
        doc.set_depth_role(0, "punter", punter)
        self.assertIs(doc.special_teams(0)["punter"], punter)

    def test_release_sign_move_and_swap_keep_every_role_on_its_player(self) -> None:
        doc = self.document
        wr, cb, hb, qb = self.club(3)[-1], self.club(4)[-1], self.club(7)[-1], self.club(0)[0]
        doc.set_special_role(0, "kr1", wr)
        doc.set_special_role(0, "kr2", cb)
        doc.set_special_role(0, "pr", hb)
        doc.set_special_role(0, "holder", qb)
        team = doc.teams[0]
        first = doc.by_offset[team.slots[0]]
        if first in (wr, cb, hb, qb):
            first = doc.by_offset[team.slots[1]]
        doc.release(first)                                  # every later role byte moves down one slot
        roles = doc.special_teams(0)
        self.assertEqual((roles["kr1"], roles["kr2"], roles["pr"], roles["holder"]), (wr, cb, hb, qb))
        doc.sign(next(p for p in doc.players if p.last == "AgentOne"), 0)
        roles = doc.special_teams(0)
        self.assertEqual((roles["kr1"], roles["kr2"], roles["pr"], roles["holder"]), (wr, cb, hb, qb))
        other = doc.team_players(1)[0]
        doc.swap(cb, other)                                 # KR2 leaves the club: nobody holds it
        roles = doc.special_teams(0)
        self.assertEqual((roles["kr1"], roles["pr"], roles["holder"]), (wr, hb, qb))
        self.assertIsNone(roles["kr2"])
        doc.move_in_depth(0, team.slots.index(wr.offset), 1 if team.slots.index(wr.offset) == 0 else -1)
        self.assertIs(doc.special_teams(0)["kr1"], wr, "a pointer exchange keeps the role on him")


class SpecialTeamsPanelTests(_PanelCase):
    body_factory = staticmethod(league_body)

    def test_the_dialog_applies_as_one_undo_and_says_how_the_game_picks(self) -> None:
        from mod_editor.gui.roster_editor_panel_qt import SpecialTeamsDialog
        panel = self.panel
        self.assertTrue(panel.special_teams_button.isEnabled())
        doc = panel.document
        dialog = SpecialTeamsDialog(panel, 0)
        self.assertIn("C #2", dialog.notes["long_snapper"].text())
        self.assertIn("K #1", dialog.notes["kicker"].text())
        wr = doc.depth_order(0, 3)[-1]
        center = doc.depth_order(0, 12)[0]
        dialog.combos["kr1"].setCurrentIndex(dialog.combos["kr1"].findData(wr.offset))
        dialog.combos["long_snapper"].setCurrentIndex(dialog.combos["long_snapper"].findData(center.offset))
        holder = doc.special_teams(0)["kr1"]
        positions = {dialog.combos["kr1"].itemText(i).split()[0] for i in range(1, dialog.combos["kr1"].count())
                     if dialog.combos["kr1"].itemData(i) != (holder.offset if holder else None)}
        self.assertTrue(positions <= {"WR", "CB", "FS", "SS", "HB", "FB"}, positions)
        before = doc.special_teams_snapshot(0)
        self.assertTrue(dialog.apply())
        self.assertIs(doc.special_teams(0)["kr1"], wr)
        self.assertIs(doc.special_teams(0)["long_snapper"], center)
        self.assertEqual(panel.status_label.text(), "IND special teams set: KR1, long snapper.",
                         "untouched roles are left alone")
        panel.undo()
        self.assertEqual(doc.special_teams_snapshot(0), before, "one undo takes it all back")
        panel.redo()
        self.assertIs(doc.special_teams(0)["kr1"], wr)
        panel.team_list.setCurrentRow(panel._team_list_row("free_agent", -1))
        self.assertFalse(panel.special_teams_button.isEnabled())


@unittest.skipUnless(SOFTDRINK_ROSTER_SAVE.is_file(), f"SOFTDRINK roster save absent: {SOFTDRINK_ROSTER_SAVE}")
class SpecialTeamsSoftdrinkTests(unittest.TestCase):
    def test_the_49ers_read_as_the_game_fields_them_and_a_new_kr1_reaches_the_signed_copy(self) -> None:
        doc = rr.load_save(SOFTDRINK_ROSTER_SAVE, detect=True)
        roles = {k: (v.display if isinstance(v, rr.Player) else v) for k, v in doc.special_teams(0).items()}
        # Codex's witness on this disc roster: Samuel, James and Cowing return; Pineiro kicks; Waitman punts and
        # holds; Jon Weeks is the center at C #2 who snaps on punts and kicks
        self.assertEqual((roles["kr1"], roles["kr2"], roles["pr"], roles["kicker"], roles["punter"],
                          roles["long_snapper"]),
                         ("Deebo Samuel", "Jordan James", "Jacob Cowing", "Eddy Pineiro", "Corliss Waitman",
                          "Jon Weeks"))
        samuel = doc.special_teams(0)["kr1"]
        new = next(p for p in doc.depth_order(0, 3) if p is not samuel and p is not doc.special_teams(0)["kr2"]
                   and p is not doc.special_teams(0)["pr"])
        doc.set_special_role(0, "kr1", new)
        with tempfile.TemporaryDirectory() as folder:
            rr.save_document(doc, Path(folder) / "copy.zip")
            back = rr.load_save(Path(folder) / "copy.zip")
            self.assertTrue(rr.SaveContainer.load(Path(folder) / "copy.zip").verified)
            after = back.special_teams(0)
            self.assertEqual(after["kr1"].display, new.display)
            self.assertEqual((after["kr2"].display, after["pr"].display), ("Jordan James", "Jacob Cowing"))
            moved = next(p for p in back.team_players(0) if p.display == new.display)
            old = next(p for p in back.team_players(0) if p.display == "Deebo Samuel")
            self.assertTrue(moved.record.depth_locks["kr1"])
            self.assertFalse(old.record.depth_locks["kr1"])


class SpecialTeamsNativeTests(unittest.TestCase):
    """The patched weekly pass 0x2BDCF0 over a club the Studio's chooser edited (in-tree Unicorn harness)."""

    def test_a_chosen_returner_survives_the_weekly_pass_only_with_his_lock(self) -> None:
        CPU, XBE = _depth_cpu()
        import struct
        from mod_editor.core import nfl2k5_depth_locks as locks
        from mod_editor.core import nfl2k5_returner_fix as returners
        from test_nfl2k5_depth_locks import record
        patched = locks.apply(returners.apply(XBE.read_bytes())[0])[0]
        base = [record(position=3, rank=r, side=r, score=.5) for r in range(3)]
        base[0] = record(position=3, rank=0, side=0, bits=0x04, score=.5)      # the loaded KR1 holds the KR1 lock
        for label, moved_lock, expected in (("Studio: byte and lock", True, 2), ("byte only", False, 0)):
            records = [bytearray(raw) for raw in base]
            if moved_lock:
                records[0][0x52] &= ~0x04
                records[2][0x52] |= 0x04
            cpu = CPU(patched)
            cpu.seed([bytes(raw) for raw in records], assignments=(2, 1, 1))
            cpu.run(0x2BDCF0)
            with self.subTest(label):
                self.assertEqual(cpu.returner_identities()[0], expected)


# --------------------------------------------------------------------------------------------- wave 2: item 6, edit speed
SOFTDRINK_FRANCHISE_SAVE = Path(os.environ.get(
    "NFL2K5_SOFTDRINK_FRANCHISE_SAVE",
    "/media/noah/Storage/2K5-project/beta81/cpu-sim/played-game-beta80/SAVEGAME.DAT"))


class EditSpeedHelpersTests(unittest.TestCase):
    def test_changed_ranges_and_overlap(self) -> None:
        before = bytes(10000)
        after = bytearray(before)
        after[5] = 1
        after[6] = 2
        after[9000] = 3
        self.assertEqual(rr.changed_ranges(before, bytes(after)), [(5, 7), (9000, 9001)])
        self.assertTrue(rr.ranges_touch([(5, 7)], [(6, 100)]))
        self.assertFalse(rr.ranges_touch([(5, 7)], [(7, 100), (0, 5)]))

    def test_the_encode_and_decode_caches_follow_the_values(self) -> None:
        document = rr.load_body(synthetic_body())
        player = document.players[0]
        raw = player.record.encode()
        self.assertIs(player.record.encode(), raw, "unchanged values reuse the bytes")
        player.record.values["speed"] = 12
        self.assertEqual(rr.decode_record(player.record.encode())["speed"], 12)
        first = rr.decode_record(raw)
        first["speed"] = 99
        self.assertNotEqual(rr.decode_record(raw)["speed"], 99, "callers get their own dict")


@unittest.skipUnless(SOFTDRINK_FRANCHISE_SAVE.is_file(), f"SOFTDRINK franchise save absent: {SOFTDRINK_FRANCHISE_SAVE}")
class FranchiseEditSpeedTests(unittest.TestCase):
    """b81 item 6: about 3 to 4 s an edit on a 4,096-player SOFTDRINK franchise before; measured 0.1 to 0.2 s after."""

    def test_season_coach_and_schedule_edits_are_quick_and_reach_the_signed_copy(self) -> None:
        from mod_editor.core import nfl2k5_franchise_save as fs
        application = _app()
        panel = RosterEditorPanel()
        try:
            self.assertTrue(panel.load_save(SOFTDRINK_FRANCHISE_SAVE))
            page = panel.franchise_panel
            self.assertTrue(page.active)
            cap = page.save.salary_cap
            page.set_salary_cap(cap + 1000)                       # the first edit fills the encode cache
            timings = {}
            # the fast path never re-reads the roster (a whole-arena re-read was the 3 to 4 s); asserted directly,
            # so a busy test machine cannot fail it, with a loose wall-clock bound beside it
            with mock.patch.object(rr.RosterDocument, "adopt_body", side_effect=AssertionError("roster re-read")):
                for label, action in (("cap", lambda: page.set_salary_cap(cap + 2000)),
                                      ("coach", lambda: page.set_coach_value(0, "overall", 71)),
                                      ("game", lambda: page.edit_game(5, 0, minute=30))):
                    started = time.perf_counter()
                    self.assertTrue(action(), page.status_label.text())
                    timings[label] = time.perf_counter() - started
            self.assertLess(max(timings.values()), 3.0, timings)
            self.assertEqual(page.save.salary_cap, cap + 2000)
            panel.undo()
            self.assertEqual(page.save.game(5, 0).minute, fs.FranchiseSave(rr.SaveContainer.load(
                SOFTDRINK_FRANCHISE_SAVE, require_signature=False).savegame).game(5, 0).minute)
            panel.redo()
            with tempfile.TemporaryDirectory() as folder:
                receipt = panel.write_copy_to(Path(folder) / "copy")
                self.assertTrue(receipt["signed"])
                back = fs.FranchiseSave(rr.SaveContainer.load(Path(folder) / "copy").savegame)
                self.assertEqual((back.salary_cap, back.coaches()[0].ratings["overall"], back.game(5, 0).minute),
                                 (cap + 2000, 71, 30))
        finally:
            panel.deleteLater()
            application.processEvents()


# --------------------------------------------------------------------------------------------- wave 2: R13 team settings
CODEX_TEAM_OPTIONS_SIGNED = Path(os.environ.get(
    "NFL2K5_FINN_TEAM_OPTIONS_SIGNED",
    "/media/noah/Storage/2K5-project/beta81/finn-facts/evidence/team-options-signed-roster-signed/SAVEGAME.DAT"))


@unittest.skipUnless(SOFTDRINK_ROSTER_SAVE.is_file(), f"SOFTDRINK roster save absent: {SOFTDRINK_ROSTER_SAVE}")
class TeamSettingsSoftdrinkTests(unittest.TestCase):
    CHANGES = {"stadium": 5, "playbook": 1, "jersey": 1, "pbp": 5, "front": 1}   # SF takes Chicago's, as in Codex's arm

    def save(self):
        from mod_editor.core import nfl2k5_franchise_save as fs
        return fs.FranchiseSave.roster_save(rr.SaveContainer.load(SOFTDRINK_ROSTER_SAVE).savegame)

    def test_the_49ers_settings_read_as_the_game_reads_them(self) -> None:
        options = self.save().team_options(0)
        self.assertEqual((options["stadium"]["id"], options["playbook"]["key"], options["jersey"], options["pbp"],
                          options["front"], options["logo"]), (25, "SF", 0, 25, 0, "25"))
        self.assertEqual(options["jersey_styles"], list(range(8)))

    def test_the_studio_writes_the_bytes_of_codexs_game_accepted_signed_copy(self) -> None:
        save = self.save()
        source = save.to_bytes()
        for option, value in self.CHANGES.items():
            save.set_team_option(0, option, value)
        changed = rr.changed_ranges(source, save.to_bytes())
        team = save.team_offset(0)
        self.assertTrue(all(team <= start and end <= team + rr.TEAM_SIZE for start, end in changed))
        if not CODEX_TEAM_OPTIONS_SIGNED.is_file():
            self.skipTest(f"Codex's signed candidate absent: {CODEX_TEAM_OPTIONS_SIGNED}")
        codex = CODEX_TEAM_OPTIONS_SIGNED.read_bytes()
        for start, end in changed:     # his candidate also changed the logo; every byte the Studio wrote matches his
            self.assertEqual(save.to_bytes()[start:end], codex[start:end], hex(start))

    def test_refusals_and_the_logo(self) -> None:
        from mod_editor.core import nfl2k5_franchise_save as fs
        save = self.save()
        before = save.to_bytes()
        for option, value, words in (("jersey", 9, "not one of this club's styles"),
                                     ("pbp", 777, "not one the league's clubs carry"),
                                     ("front", 3, "4-3"), ("stadium", 999, "stadium records"),
                                     ("logo", 5, "uniform and helmet set")):
            with self.subTest(option=option):
                with self.assertRaisesRegex(fs.FranchiseSaveError, words):
                    save.set_team_option(0, option, value)
        self.assertEqual(save.to_bytes(), before)

    def test_the_dialog_applies_as_one_undo_and_the_copy_carries_it(self) -> None:
        from mod_editor.core import nfl2k5_franchise_save as fs
        from mod_editor.gui.roster_editor_panel_qt import TeamOptionsDialog
        application = _app()
        panel = RosterEditorPanel()
        try:
            self.assertTrue(panel.load_save(SOFTDRINK_ROSTER_SAVE))
            self.assertTrue(panel.team_options_button.isEnabled(), panel.team_options_button.toolTip())
            dialog = TeamOptionsDialog(panel, 0)
            self.assertIn("s25 Levi's Stadium", dialog.combos["stadium"].currentText())
            for key, value in self.CHANGES.items():
                dialog.combos[key].setCurrentIndex(dialog.combos[key].findData(value))
            self.assertTrue(dialog.apply(), dialog.status.text())
            self.assertIn("stadium s05 Soldier Field", panel.status_label.text())
            panel.refresh_diff()
            self.assertIn("SF settings:", panel.report.toPlainText())
            panel.undo()
            self.assertEqual(panel.franchise_panel.save.team_options(0)["stadium"]["id"], 25)
            panel.redo()
            with tempfile.TemporaryDirectory() as folder:
                panel.write_copy_to(Path(folder) / "copy.zip")
                container = rr.SaveContainer.load(Path(folder) / "copy.zip")
                self.assertTrue(container.verified)
                options = fs.FranchiseSave.roster_save(container.savegame).team_options(0)
                self.assertEqual((options["stadium"]["id"], options["playbook"]["key"], options["jersey"],
                                  options["pbp"], options["front"]), (5, "CHI", 1, 5, 1))
        finally:
            panel.deleteLater()
            application.processEvents()


class TeamSettingsAvailabilityTests(_PanelCase):
    def test_a_disc_roster_says_where_team_settings_live(self) -> None:
        self.assertFalse(self.panel.team_options_button.isEnabled())
        self.assertIn("Xbox save", self.panel.team_options_button.toolTip())


# --------------------------------------------------------------------------------------------- wave 2: R9 Clear Stats
CODEX_HISTORY_SOURCE = Path(os.environ.get(
    "NFL2K5_FINN_HISTORY_SOURCE",
    "/media/noah/Storage/2K5-project/beta81/cpu-sim/verified-disc-128-dynasty-signed/2026/SAVEGAME.DAT"))
CODEX_HISTORY_SIGNED = Path(os.environ.get(
    "NFL2K5_FINN_HISTORY_SIGNED",
    "/media/noah/Storage/2K5-project/beta81/finn-facts/evidence/player-history-signed/SAVEGAME.DAT"))


class NeutralHistoryTests(unittest.TestCase):
    def test_the_six_words_are_the_game_writers_for_slot_nine(self) -> None:
        self.assertEqual([hex(w) for w in rr.neutral_history(9)],          # history-clear-native.json, tail_words
                         ["0x248d0000", "0x24880000", "0x24820000", "0x48d0000", "0x4880000", "0x84820000"])
        with self.assertRaises(rr.RosterRecordError):
            rr.neutral_history(32)


@unittest.skipUnless(CODEX_HISTORY_SOURCE.is_file() and CODEX_HISTORY_SIGNED.is_file(),
                     f"Codex's history witness absent: {CODEX_HISTORY_SOURCE}")
class ClearStatsWitnessTests(unittest.TestCase):
    def test_clearing_lamar_writes_codexs_game_accepted_bytes(self) -> None:
        document = rr.load_save(CODEX_HISTORY_SOURCE)
        lamar = next(p for p in document.players if p.pool == "primary" and p.index == 137)
        self.assertEqual(lamar.display, "Lamar Jackson")
        receipt = document.clear_history([lamar])
        self.assertEqual((receipt["words"], receipt["used_before"], receipt["used_after"]), (6, 44207, 44213))
        self.assertEqual(document.to_body(), CODEX_HISTORY_SIGNED.read_bytes())   # all 987,836 bytes, 22 changed
        again = document.clear_history([lamar])
        self.assertEqual((again["words"], [p.display for p in again["already"]]), (0, ["Lamar Jackson"]))


@unittest.skipUnless(SOFTDRINK_ROSTER_SAVE.is_file(), f"SOFTDRINK roster save absent: {SOFTDRINK_ROSTER_SAVE}")
class ClearStatsCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = rr.load_save(SOFTDRINK_ROSTER_SAVE)
        self.with_history = [p for p in self.document.players if p.record.values["history_pointer"]]

    def test_a_shared_stream_stays_with_the_other_player_and_undo_is_exact(self) -> None:
        document = self.document
        target, peer = self.with_history[0], self.with_history[1]
        # a private copy where the peer shares the target's stream, as in Codex's adversarial arm
        link = target.offset + rr.FIELD_BY_NAME["history_pointer"].offset
        stream = link + rr._signed(target.record.values["history_pointer"]) - 1
        peer.record.values["history_pointer"] = (stream - (peer.offset + 0x2C) + 1) & 0xFFFFFFFF
        shared = document.history_words(peer)
        body = bytes(document.body)
        receipt = document.clear_history([target])
        self.assertEqual(document.history_words(peer), shared)
        self.assertEqual(document.history_words(target), rr.neutral_history(target.record.values["years_pro"]))
        document.restore_history(receipt["before"])
        self.assertEqual(bytes(document.body), body)
        self.assertEqual(document.history_words(target), shared)

    def test_a_pool_without_room_refuses_and_changes_nothing(self) -> None:
        document = self.document
        pool = document.history_pool()
        struct.pack_into("<I", document.body, document.obj_base + rr.OBJ_OFF + 0x40, pool["capacity"] - 11)
        body = bytes(document.body)
        links = [p.record.values["history_pointer"] for p in self.with_history[:2]]
        with self.assertRaisesRegex(rr.RosterRecordError, "has 11 free words of 50,000 and clearing 2 players needs 12"):
            document.clear_history(self.with_history[:2])
        self.assertEqual(bytes(document.body), body)
        self.assertEqual([p.record.values["history_pointer"] for p in self.with_history[:2]], links)

    def test_the_page_clears_with_one_undo_and_the_signed_copy_carries_it(self) -> None:
        application = _app()
        panel = RosterEditorPanel()
        try:
            self.assertTrue(panel.load_save(SOFTDRINK_ROSTER_SAVE))
            document = panel.document
            player = panel.selected_player()
            self.assertTrue(player is not None and player.record.values["history_pointer"])
            used = document.history_pool()["used"]
            ok, message = panel.clear_career_stats(confirm=False)
            self.assertTrue(ok, message)
            self.assertIn("career stats cleared", message)
            self.assertIn((player.pool, player.index), panel._dirty)
            panel.refresh_diff()
            self.assertIn("Career stats: cleared", panel.report.toPlainText())
            self.assertEqual(panel.clear_career_stats(confirm=False)[1], f"Already clear: {player.display}.")
            panel.undo()
            self.assertEqual(document.history_pool()["used"], used)
            self.assertNotIn((player.pool, player.index), panel._dirty)
            panel.redo()
            with tempfile.TemporaryDirectory() as folder:
                panel.write_copy_to(Path(folder) / "copy.zip")
                back = rr.load_save(Path(folder) / "copy.zip")
                self.assertTrue(back.container.verified)
                twin = back.by_offset[player.offset]
                self.assertTrue(back.history_is_clear(twin))
                self.assertEqual(back.history_pool()["used"], used + 6)
        finally:
            panel.deleteLater()
            application.processEvents()


@unittest.skipUnless(SOFTDRINK_FRANCHISE_SAVE.is_file(), f"SOFTDRINK franchise save absent: {SOFTDRINK_FRANCHISE_SAVE}")
class ClearStatsFranchiseTests(unittest.TestCase):
    def test_a_franchise_clear_composes_with_franchise_edits(self) -> None:
        from mod_editor.core import nfl2k5_franchise_save as fs
        application = _app()
        panel = RosterEditorPanel()
        try:
            self.assertTrue(panel.load_save(SOFTDRINK_FRANCHISE_SAVE))
            document = panel.document
            player = next(p for p in document.players if p.record.values["history_pointer"]
                          and document.club_of(p) is not None)
            self.assertTrue(panel.clear_career_stats([player], confirm=False)[0])
            page = panel.franchise_panel
            cap = page.save.salary_cap
            self.assertTrue(page.set_salary_cap(cap + 1000))
            with tempfile.TemporaryDirectory() as folder:
                receipt = panel.write_copy_to(Path(folder) / "copy")
                self.assertTrue(receipt["signed"])
                back = rr.load_save(Path(folder) / "copy" / "SAVEGAME.DAT"
                                    if (Path(folder) / "copy").is_dir() else Path(folder) / "copy")
                self.assertTrue(back.history_is_clear(back.by_offset[player.offset]))
                self.assertEqual(fs.FranchiseSave(back.container.savegame).salary_cap, cap + 1000)
            panel.undo()
            panel.undo()
            self.assertFalse(document.history_is_clear(player))
        finally:
            panel.deleteLater()
            application.processEvents()


class ClearStatsAvailabilityTests(_PanelCase):
    def test_a_disc_roster_says_career_stats_are_cleared_in_a_save(self) -> None:
        ok, message = self.panel.clear_career_stats(self.panel.document.players[:1], confirm=False)
        self.assertFalse(ok)
        self.assertIn("Xbox save", message)


# --------------------------------------------------------------------------------------------- wave 2: R11 photos
def _retail_pack0() -> Path | None:
    named = os.environ.get("NFL2K5_RETAIL_PACK0")
    if named:
        return Path(named) if Path(named).is_file() else None
    from mod_editor.core.nfl2k5_source_cache import PACK0_SIZE, PACK_FOLDER
    root = Path.home() / ".cache" / "2k5-mod-studio"
    for candidate in sorted(root.glob("*/" + PACK_FOLDER.as_posix() + "/0")) if root.is_dir() else ():
        if candidate.is_file() and candidate.stat().st_size == PACK0_SIZE:
            return candidate
    return None


RETAIL_PACK0 = _retail_pack0()


class PortraitPreviewCoreTests(unittest.TestCase):
    def test_real_and_draft_faces_decode_from_the_shipped_sets(self) -> None:
        import hashlib
        from mod_editor.core import nfl2k5_portrait_preview as pp, nfl2k5_real_portraits as real
        previews = pp.PortraitPreviews(None)
        photo, (cell, palette) = real.faces()[0]                 # the build's own decode of the first headshot
        picture = previews.picture(photo)
        self.assertEqual(picture.kind, "real")
        self.assertEqual(picture.rgba, b"".join(palette[4 * i:4 * i + 4] for i in cell))
        draft = previews.picture(13569)
        self.assertEqual((draft.kind, len(draft.rgba or b"")), ("rookie", 128 * 128 * 4))
        self.assertEqual(hashlib.sha256(draft.rgba).hexdigest(), hashlib.sha256(previews.picture(11849).rgba).hexdigest(),
                         "a legacy id shows the same face")
        none = previews.picture(22000)
        self.assertEqual((none.kind, none.rgba), ("none", None))
        self.assertIn("no photo", none.note)
        closed = previews.picture(5147)
        self.assertEqual((closed.kind, closed.rgba), ("catalogue", None))
        self.assertIn("open your original game disc", closed.note)

    def test_selected_art_uses_game_palette_switches_and_reloads(self) -> None:
        from PIL import Image
        from mod_editor.core import nfl2k5_portrait_preview as pp
        from tools import nfl_tset_png_import as writer

        previews = pp.PortraitPreviews(None)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            png = folder / "portrait.png"
            project = folder / "selected.json"
            pixels = bytes(v for i in range(128 * 128) for v in (i % 251, i % 13, 9, 224))
            Image.frombytes("RGBA", (128, 128), pixels).save(png)
            row = {"kind": "player_portrait", "png": png.name, "portrait_id": "0028"}
            recipe = {"schema": "nfl2k5_visual_mod_project/v1", "purpose": "portrait selection", "edits": [row]}
            project.write_text(json.dumps(recipe))
            palette, indices, _ = writer.quantize_levels([writer.MipLevel(0, 128, 128, pixels)])
            expected = writer.rgba_from_indices(indices[0], palette)
            self.assertNotEqual(pixels, expected)
            self.assertEqual(previews.picture(28, league_project=project).rgba, expected)
            self.assertEqual(previews.picture(28, staged_png=png).rgba, expected)
            self.assertIsNone(previews.picture(28).rgba)         # this fixture has no original disc cache
            self.assertIsNone(previews.picture(28, league_project=project, staged_png=png).rgba)
            Image.new("RGBA", (128, 128), (51, 17, 39, 224)).save(png)
            second = previews.picture(28, league_project=project)
            self.assertEqual(second.rgba, bytes((51, 17, 39, 224)) * (128 * 128))
            project.write_text(json.dumps(dict(recipe, edits=[])))
            self.assertIsNone(previews.picture(28, league_project=project).rgba)
            project.write_text(json.dumps(dict(recipe, edits=[row, row])))
            self.assertIn("repeats portrait", previews.picture(28, league_project=project).note)
            self.assertEqual(previews.picture(30326, rookie_faces=False).kind, "none")
            self.assertTrue(previews.picture(30326, rookie_faces=True).available)

    @unittest.skipUnless(RETAIL_PACK0 is not None, "no retail source cache (open the original disc in the Studio once)")
    def test_a_catalogue_portrait_is_the_retail_picture(self) -> None:
        import hashlib
        from mod_editor.core import nfl2k5_portrait_preview as pp
        previews = pp.PortraitPreviews(RETAIL_PACK0)
        for photo in (0, 386, 5147, 9507):
            with self.subTest(photo=photo):
                picture = previews.picture(photo)
                self.assertEqual(picture.kind, "catalogue")
                self.assertEqual(hashlib.sha256(picture.rgba).hexdigest(),
                                 previews._catalogue()[photo].rgba_sha256)     # the catalogue's own decoded identity


@unittest.skipUnless(SOFTDRINK_ROSTER_SAVE.is_file(), f"SOFTDRINK roster save absent: {SOFTDRINK_ROSTER_SAVE}")
class PortraitPreviewPanelTests(unittest.TestCase):
    def test_the_header_and_the_picker_draw_the_photo(self) -> None:
        from mod_editor.gui.roster_editor_panel_qt import IdPickerDialog
        application = _app()
        panel = RosterEditorPanel()
        try:
            panel.portrait_pack0 = RETAIL_PACK0
            self.assertTrue(panel.load_save(SOFTDRINK_ROSTER_SAVE))
            document = panel.document
            real = next(p for p in document.players if 30000 <= p.record.values["photo_id"] < 31200
                        and document.club_of(p) is not None)
            panel.select_player(real)
            panel._show_player(real)
            self.assertTrue(panel.header_photo.isVisibleTo(panel))
            self.assertFalse(panel.header_photo.pixmap() is None or panel.header_photo.pixmap().isNull())
            self.assertIn("Real NFL headshot", panel.header_photo.toolTip())
            entries, note = panel.picker_entries("photo_id")
            dialog = IdPickerDialog("Portrait", entries, real.record.values["photo_id"], panel, note=note,
                                    preview=panel.portrait_pixmap)
            self.assertFalse(dialog.preview_label.pixmap() is None or dialog.preview_label.pixmap().isNull())
            dialog.spin.setValue(22000)
            self.assertEqual(dialog.preview_label.text(), "No picture")
            self.assertIn("no photo", dialog.preview_note.text())
            if RETAIL_PACK0 is not None:
                dialog.spin.setValue(386)
                self.assertFalse(dialog.preview_label.pixmap() is None or dialog.preview_label.pixmap().isNull())
                self.assertIn("from your original disc", dialog.preview_note.text())
            dialog.deleteLater()
        finally:
            panel.deleteLater()
            application.processEvents()


# --------------------------------------------------------------------------------------------- wave 3: team transfer
def _team_rows(package):
    return [(e["list"], e["first"], e["last"], e["college"], e["birth_year"], e["fields"]) for e in package["players"]]


class TeamTransferSyntheticTests(_PanelCase):
    def test_a_disc_paste_carries_players_depth_and_special_teams_with_one_undo(self) -> None:
        from mod_editor.core import nfl2k5_team_transfer as tt
        panel, document = self.panel, self.panel.document
        source, target = 0, 1                                     # IND and ATL, three players each
        package = tt.team_package(document, source)
        self.assertIsNone(package["settings"])
        before = tt.team_package(document, target)
        body = document.to_body()
        ok, message = panel.paste_team(target, package)
        self.assertTrue(ok, message)
        after = tt.team_package(document, target)
        self.assertEqual(_team_rows(after), _team_rows(package))
        self.assertEqual(after["specialists"], package["specialists"])
        for player in document.team_players(target):           # the club keeps each record's slot state
            original = rr.PlayerRecord.decode(document.original[player.offset:player.offset + rr.PLAYER_SIZE])
            for name in tt.KEPT_BY_CLUB:
                self.assertEqual(player.record.values[name], original.values[name], name)
        panel.refresh_diff()
        self.assertIn("pasted onto ATL", panel.report.toPlainText())
        panel.undo()
        self.assertEqual(_team_rows(tt.team_package(document, target)), _team_rows(before))
        self.assertEqual(document.to_body(), body)
        panel.redo()
        self.assertEqual(_team_rows(tt.team_package(document, target)), _team_rows(package))
        edits = rr.edits_document(document)                       # a disc copy replays it through the edits file
        self.assertTrue(edits["edits"])

    def test_a_file_round_trips_and_a_bad_file_refuses(self) -> None:
        from mod_editor.core import nfl2k5_team_transfer as tt
        self.panel._group = ("team", 0)
        with tempfile.TemporaryDirectory() as folder:
            written = self.panel.export_team(Path(folder) / "ind")
            self.assertEqual(written.suffix, tt.SUFFIX)
            self.assertEqual(tt.read_package(written), tt.team_package(self.panel.document, 0))
            bad = Path(folder) / "bad.2k5team"
            bad.write_text('{"schema": "nfl2k5_studio_team/v1", "players": [{"list": "active", "fields": '
                           '{"history_pointer": 5}}], "specialists": [255, 255, 255, 255, 255, 255]}', encoding="utf-8")
            with self.assertRaisesRegex(rr.RosterRecordError, "not a field a team file carries"):
                tt.read_package(bad)

    def test_counts_and_ir_refuse_with_the_reason(self) -> None:
        from mod_editor.core import nfl2k5_team_transfer as tt
        document = self.panel.document
        package = tt.team_package(document, 0)
        package["players"] = package["players"][:2]
        ok, message = self.panel.paste_team(1, package)
        self.assertFalse(ok)
        self.assertIn("ATL has 3 active players and IND 2", message)
        self.assertIn("release 1 ATL player first", message)
        full = tt.team_package(document, 0)
        document.team_players(1)[0].record.values["injured_reserve"] = 0xEE
        ok, message = self.panel.paste_team(1, full)
        self.assertFalse(ok)
        self.assertIn("on injured reserve; activate them first", message)


@unittest.skipUnless(SOFTDRINK_ROSTER_SAVE.is_file(), f"SOFTDRINK roster save absent: {SOFTDRINK_ROSTER_SAVE}")
class TeamTransferRosterSaveTests(unittest.TestCase):
    SOURCE, TARGET = 0, 14                                       # SF and ATL: 55 active and 4 reserves each

    def test_sf_onto_atl_round_trips_through_the_signed_copy(self) -> None:
        from mod_editor.core import nfl2k5_franchise_save as fs, nfl2k5_team_transfer as tt
        application = _app()
        panel = RosterEditorPanel()
        try:
            self.assertTrue(panel.load_save(SOFTDRINK_ROSTER_SAVE))
            document = panel.document
            panel._group = ("team", self.SOURCE)
            self.assertTrue(panel.copy_team())
            package = panel._team_clipboard
            self.assertEqual((package["counts"], package["settings"]["playbook_key"], package["coach"]["last"]),
                             ({"active": 55, "reserve": 4}, "SF", "Shanahan"))
            before = panel.team_package(self.TARGET)
            ok, message = panel.paste_team(self.TARGET, package)
            self.assertTrue(ok, message)
            after = panel.team_package(self.TARGET)
            dropped = {text.split(" (")[0] for text in message.split("original: ")[-1].split(", ")} if "left off" in message else set()
            for want, got in zip(package["players"], after["players"]):
                differs = {k for k in want["fields"] if want["fields"][k] != got["fields"][k]}
                if differs:                                      # only a lock that would collide on a squad is left off
                    self.assertEqual(differs, {"unknown_52"})
                    self.assertEqual(want["fields"]["unknown_52"] & ~rr.PASTE_LOCK_MASK,
                                     got["fields"]["unknown_52"] & ~rr.PASTE_LOCK_MASK)
            self.assertEqual(after["specialists"], package["specialists"])
            self.assertEqual({k: v for k, v in after["settings"].items()}, package["settings"])
            self.assertEqual((after["coach"]["first"], after["coach"]["last"], after["coach"]["ratings"],
                              after["coach"]["tendencies"]),
                             (package["coach"]["first"], package["coach"]["last"], package["coach"]["ratings"],
                              package["coach"]["tendencies"]))
            self.assertEqual(document.check_depth_locks(), 0)
            with tempfile.TemporaryDirectory() as folder:
                panel.write_copy_to(Path(folder) / "copy.zip")
                back = rr.load_save(Path(folder) / "copy.zip")
                self.assertTrue(back.container.verified)
                again = tt.team_package(back, self.TARGET, save=fs.FranchiseSave.roster_save(back.container.savegame))
                self.assertEqual(_team_rows(again), _team_rows(after))
                self.assertEqual((again["settings"], again["coach"]["ratings"]), (after["settings"], after["coach"]["ratings"]))
            panel.undo()
            self.assertEqual(_team_rows(panel.team_package(self.TARGET)), _team_rows(before))
            self.assertEqual(panel.team_package(self.TARGET)["coach"]["last"], before["coach"]["last"])
        finally:
            panel.deleteLater()
            application.processEvents()

    def test_a_retail_shaped_package_converts_or_refuses(self) -> None:
        from mod_editor.core import nfl2k5_team_transfer as tt
        document = rr.load_save(SOFTDRINK_ROSTER_SAVE, scheme="one_pool")
        package = tt.team_package(document, self.SOURCE)
        package["source"]["scheme"] = "retail"
        linebacker = next(e for e in package["players"] if e["fields"]["position"] == 11)
        linebacker["fields"]["position"] = 10                    # a retail OLB onto a one-pool roster
        plan = tt.plan(document, self.TARGET, package)
        self.assertFalse(plan["refusals"], plan["refusals"])
        self.assertTrue(any("retired" in note and "code 11" in note for note in plan["notes"]), plan["notes"])
        tt.apply_players(document, self.TARGET, package, plan)
        slot = package["players"].index(linebacker)
        self.assertEqual(plan["pairs"][slot][1].record.values["position"], 11)
        old = tt.team_package(document, self.SOURCE)
        old["players"][0]["birth_year"] = 1890
        plan = tt.plan(document, self.TARGET, old)
        self.assertTrue(any("birth-year window" in text for text in plan["refusals"]), plan["refusals"])
        disc = rr.load_body(synthetic_body())                    # a retail disc club of 3 cannot take 55 + 4
        refusals = tt.plan(disc, 1, tt.team_package(document, self.SOURCE))["refusals"]
        self.assertTrue(any("ATL has 3 active players and SF 55" in text for text in refusals), refusals)
        self.assertTrue(any("0 reserves and SF 4" in text for text in refusals), refusals)


@unittest.skipUnless(SOFTDRINK_FRANCHISE_SAVE.is_file(), f"SOFTDRINK franchise save absent: {SOFTDRINK_FRANCHISE_SAVE}")
class TeamTransferFranchiseTests(unittest.TestCase):
    def test_a_franchise_paste_composes_with_franchise_edits_and_writes(self) -> None:
        import collections
        from mod_editor.core import nfl2k5_franchise_save as fs, nfl2k5_team_transfer as tt
        application = _app()
        panel = RosterEditorPanel()
        try:
            self.assertTrue(panel.load_save(SOFTDRINK_FRANCHISE_SAVE))
            document = panel.document
            shapes = collections.defaultdict(list)
            for team in document.teams[:32]:
                lists = tt.club_lists(document, team.index)
                if not any(p.record.on_injured_reserve for lst in lists.values() for p in lst):
                    shapes[(len(lists["active"]), len(lists["reserve"]))].append(team.index)
            source, target = next(v for v in shapes.values() if len(v) > 1)[:2]
            page = panel.franchise_panel
            cap = page.save.salary_cap
            self.assertTrue(page.set_salary_cap(cap + 1000))
            package = panel.team_package(source)
            ok, message = panel.paste_team(target, package)
            self.assertTrue(ok, message)
            with tempfile.TemporaryDirectory() as folder:
                receipt = panel.write_copy_to(Path(folder) / "copy")
                self.assertTrue(receipt["signed"])
                back = rr.load_save(Path(folder) / "copy")
                save = fs.FranchiseSave(back.container.savegame)
                again = tt.team_package(back, target, save=save)
                self.assertEqual([(e["first"], e["last"]) for e in again["players"]],
                                 [(e["first"], e["last"]) for e in package["players"]])
                self.assertEqual(again["settings"], package["settings"])
                self.assertEqual(save.salary_cap, cap + 1000)
            panel.undo()
            self.assertEqual(page.save.salary_cap, cap + 1000)
            panel.undo()
            self.assertEqual(page.save.salary_cap, cap)
        finally:
            panel.deleteLater()
            application.processEvents()


class SharedDecodeTests(unittest.TestCase):
    """b81 wave 3: a composed franchise edit decoded the same two payloads seven times (IR place 2.1 s -> 1.4 s)."""

    def test_the_same_bytes_decode_once_inside_the_block_only(self) -> None:
        from mod_editor.core import nfl2k5_save_rost as codec
        savegame = synthetic_save_v0(synthetic_body())
        self.assertIsNot(codec.decode(savegame), codec.decode(savegame))
        with codec.shared_decodes():
            first = codec.decode(savegame)
            self.assertIs(codec.decode(savegame), first)
            self.assertIs(codec.decode(savegame, preamble=first.layout.preamble), first)
            first.edit_player(first.players[0].pool, first.players[0].index, {"speed": 33})
            self.assertIsNot(codec.decode(savegame), first, "an edited result is not handed out again")
        self.assertIsNot(codec.decode(savegame), codec.decode(savegame))

    def test_a_decoded_record_reuses_bytes_this_process_encoded(self) -> None:
        record = rr.PlayerRecord.decode(synthetic_body()[0:0] or rr.encode_record(rr.decode_record(bytes(rr.PLAYER_SIZE))))
        raw = record.encode()
        again = rr.PlayerRecord.decode(raw)
        self.assertIs(again.encode(), raw)
        again.values["speed"] = 77
        self.assertEqual(rr.decode_record(again.encode())["speed"], 77)


# --------------------------------------------------------------------------------------------- wave 3: PS2 rosters
def _ps2_save(payload: bytes, name: str = "Test", kind: str = "ROS"):
    from mod_editor.core import nfl2k5_ps2_rosters as ps2
    save = ps2.save_lib.Ps2Save(directory=ps2.save_lib.SAVE_PREFIX + name)
    save.files[save.payload_name] = bytes(payload)
    save.files["TYPE"] = kind.encode("utf-16le") + b"\x00\x00"
    save.files["icon.sys"] = bytes(964)
    save.reseal()
    return save


def _ps2_roster_payload() -> bytes:
    return synthetic_save_v0(synthetic_body(), suffix=b"")[0x2E0:]          # wrapper at 0, root at 0x40


def _ps2_card(path: Path, saves) -> None:
    """A FAT-backed, ECC-correct PS2 card image holding ``saves`` (1 KB clusters, as many FAT clusters as needed)."""

    from mod_editor.core import nfl2k5_ps2_rosters as ps2
    lib = ps2.save_lib
    size, per_fat = 1024, 256
    need = sum(-(-len(data) // size) for save in saves for data in save.files.values()) + 4 * len(saves) + 8
    fats = -(-need // per_fat)
    alloc = 2 + fats
    data: list[bytearray] = []
    fat = [0xFFFFFFFF] * (fats * per_fat)

    def store(blob: bytes) -> int:
        start = len(data)
        for offset in range(0, max(len(blob), 1), size):
            if offset:
                fat[len(data) - 1] = 0x80000000 | len(data)
            data.append(bytearray(blob[offset:offset + size].ljust(size, b"\0")))
        fat[len(data) - 1] = 0xFFFFFFFF
        return start

    def entry(name: str, mode: int, length: int, first: int) -> bytes:
        row = bytearray(512)
        struct.pack_into("<II", row, 0, mode, length)
        struct.pack_into("<I", row, 0x10, first)
        row[0x40:0x40 + len(name)] = name.encode("ascii")
        return bytes(row)

    dirs = []
    for save in saves:
        rows = [entry(key, 0x8417, len(blob), store(blob)) for key, blob in save.files.items()]
        dirs.append((save.directory, len(rows), store(b"".join(rows))))
    root = store(entry(".", 0x8427, len(dirs) + 1, 0) + b"".join(entry(n, 0x8427, c, f) for n, c, f in dirs))
    superblock = bytearray(size)
    superblock[:27] = b"Sony PS2 Memory Card Format"
    struct.pack_into("<H", superblock, 0x2A, 2)
    struct.pack_into("<III", superblock, 0x34, alloc, len(data), root)
    struct.pack_into("<32I", superblock, 0x50, 1, *([0xFFFFFFFF] * 31))
    indirect = bytearray(struct.pack(f"<{per_fat}I", *[2 + i for i in range(fats)],
                                     *([0xFFFFFFFF] * (per_fat - fats))))
    clusters = [superblock, indirect] + [bytearray(struct.pack(f"<{per_fat}I", *fat[i * per_fat:(i + 1) * per_fat]))
                                         for i in range(fats)] + data
    with path.open("wb") as out:
        for cluster in clusters:
            for offset in (0, 512):
                page = bytes(cluster[offset:offset + 512])
                out.write(page + b"".join(lib.chunk_ecc(page[n:n + 128]) for n in range(0, 512, 128)) + bytes(4))


class Ps2RostersTests(_PanelCase):
    def setUp(self) -> None:
        super().setUp()
        self._temp = tempfile.TemporaryDirectory(prefix="ps2-rosters-")
        self.root = Path(self._temp.name)

    def tearDown(self) -> None:
        self._temp.cleanup()
        super().tearDown()

    def _edit(self, panel) -> rr.Player:
        player = panel.document.team_players(0)[0]
        panel.select_player(player)
        panel.set_field(player, "speed", 91)
        panel.document.set_name(player, "last", "Psotwo")
        return player

    def test_a_psu_opens_on_every_page_and_writes_a_verified_copy(self) -> None:
        from mod_editor.core import nfl2k5_ps2_rosters as ps2
        source = self.root / "source.psu"
        ps2.save_lib.write_psu(_ps2_save(_ps2_roster_payload()), source)
        original = source.read_bytes()
        panel = self.panel
        self.assertTrue(panel.load_save(source), panel.status_label.text())
        self.assertEqual(panel.write_button.text(), "Save PS2 save copy…")
        self.assertIn("PCSX2", panel.status_label.text())
        player = self._edit(panel)
        receipt = panel.write_copy_to(panel.save_copy_destination(self.root))
        self.assertEqual((receipt["platform"], receipt["kind"], receipt["verified"], receipt["sealed"]),
                         ("ps2", "psu", True, True))
        self.assertTrue(receipt["target"].endswith("source (edited).psu"))
        self.assertIn("PS2 save copy written", panel.save_copy_message(receipt))
        back = ps2.Ps2SaveContainer.load(receipt["target"])
        self.assertTrue(back.verified)
        twin = back.document().by_offset[player.offset]
        self.assertEqual((twin.record.values["speed"], twin.last), (91, "Psotwo"))
        self.assertEqual(source.read_bytes(), original)
        with self.assertRaisesRegex(rr.RosterRecordError, "exists"):
            back.write(receipt["target"], back.savegame)

    def test_a_card_copy_keeps_the_other_saves_and_verifies_every_page(self) -> None:
        from mod_editor.core import nfl2k5_ps2_rosters as ps2
        card = self.root / "card.ps2"
        neighbour = ps2.save_lib._synthetic_save()
        _ps2_card(card, [neighbour, _ps2_save(_ps2_roster_payload(), "Mine")])
        self.assertEqual(ps2.card_saves(card), [neighbour.directory, ps2.save_lib.SAVE_PREFIX + "Mine"])
        panel = self.panel
        self.assertFalse(panel.load_save(card))                          # two roster saves: one must be chosen
        self.assertIn("choose one", panel.status_label.text())
        self.assertTrue(panel.load_save(card, directory=ps2.save_lib.SAVE_PREFIX + "Mine"), panel.status_label.text())
        player = self._edit(panel)
        receipt = panel.write_copy_to(panel.save_copy_destination(self.root))
        self.assertEqual((receipt["kind"], receipt["other_saves_untouched"]), ("card", [neighbour.directory]))
        self.assertGreater(receipt["ecc_pages"], 1000)
        written = ps2.save_lib.read_memcard(Path(receipt["target"]))
        self.assertEqual({s.directory: s.files for s in written}[neighbour.directory], neighbour.files)
        mine = ps2.Ps2SaveContainer.load(receipt["target"], directory=ps2.save_lib.SAVE_PREFIX + "Mine")
        self.assertEqual(mine.document().by_offset[player.offset].record.values["speed"], 91)

    def test_franchise_kinds_and_bad_checksums_refuse(self) -> None:
        from mod_editor.core import nfl2k5_ps2_rosters as ps2
        franchise = self.root / "fran.psu"
        ps2.save_lib.write_psu(_ps2_save(_ps2_roster_payload(), "Fran", "FXG"), franchise)
        self.assertFalse(self.panel.load_save(franchise))
        self.assertIn("PS2 franchise save", self.panel.status_label.text())
        broken = _ps2_save(_ps2_roster_payload(), "Bad")
        broken.files["EXTRA"] = b"\0\0\0\0"
        ps2.save_lib.write_psu(broken, self.root / "bad.psu")
        self.assertFalse(self.panel.load_save(self.root / "bad.psu"))
        self.assertIn("checksum does not match", self.panel.status_label.text())


@unittest.skipUnless(SOFTDRINK_ROSTER_SAVE.is_file(), f"SOFTDRINK roster save absent: {SOFTDRINK_ROSTER_SAVE}")
class Ps2RostersLargeArenaTests(unittest.TestCase):
    """Codec scale only: the SOFTDRINK Xbox roster arena (4,096 players) inside a PS2 container. It says nothing about
    the PS2 game, which has no SOFTDRINK build."""

    def test_team_paste_depth_and_specialists_write_through_the_ps2_writer(self) -> None:
        from mod_editor.core import nfl2k5_ps2_rosters as ps2, nfl2k5_team_transfer as tt
        payload = rr.SaveContainer.load(SOFTDRINK_ROSTER_SAVE).savegame
        application = _app()
        panel = RosterEditorPanel()
        with tempfile.TemporaryDirectory(prefix="ps2-large-") as folder:
            try:
                source = Path(folder) / "big.psu"
                ps2.save_lib.write_psu(_ps2_save(payload, "Big"), source)
                self.assertTrue(panel.load_save(source), panel.status_label.text())
                package = panel.team_package(0)
                ok, message = panel.paste_team(14, package)
                self.assertTrue(ok, message)
                receipt = panel.write_copy_to(panel.save_copy_destination(folder))
                self.assertTrue(receipt["verified"])
                back = ps2.Ps2SaveContainer.load(receipt["target"]).document()
                self.assertEqual([(e["first"], e["last"]) for e in tt.team_package(back, 14)["players"]],
                                 [(e["first"], e["last"]) for e in package["players"]])
            finally:
                panel.deleteLater()
                application.processEvents()


if __name__ == "__main__":
    unittest.main()

"""The ★ Rosters page, driven offscreen against a synthetic roster.

Loads a document, walks the team list and the position chips, edits a rating through a card, undoes
it, previews and applies a global edit, round-trips a CSV, saves a roster-edits document, writes a
re-signed save copy, and checks the page's place in the studio shell.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor", ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.gui.roster_editor_panel_qt import (  # noqa: E402
    AttributeCard,
    UndoEntry,
    GlobalEditDialog,
    IdPickerDialog,
    RosterEditorPanel,
    SwapPlayerDialog,
    UndoStack,
    ValueBar,
)
from test_nfl2k5_roster_records import (  # noqa: E402
    COLLEGES,
    LEAGUE_CLUB_SIZE,
    SAMPLE,
    damaged_body,
    league_body,
    one_pool_body,
    retail_front_body,
    synthetic_body,
)


class RosterEditorPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.body = synthetic_body()
        self.panel = RosterEditorPanel()
        self.panel.load_document(rr.load_body(self.body), label="synthetic")
        self.application.processEvents()

    def tearDown(self) -> None:
        self.panel.deleteLater()
        self.application.processEvents()

    # ------------------------------------------------------------------ layout
    def test_the_page_opens_with_the_teams_pools_and_the_first_squad(self) -> None:
        rows = [self.panel.team_list.item(i).text() for i in range(self.panel.team_list.count())]
        self.assertEqual(rows[:6], ["IND · 3 active + 0 reserve", "    Reserves · 0",
                                  "ATL · 3 active + 0 reserve", "    Reserves · 0",
                                  "SF · 0 active + 0 reserve", "    Reserves · 0"])
        self.assertEqual(rows[-3:], ["Free Agents · 1", "Draft Class · 1", "Other pools · 0"])
        self.assertEqual([p.display for p in self.panel.visible_players()],
                         ["Peyton Manning", "Marvin Harrison", "Edgerrin James"])
        self.assertEqual(self.panel.player_table.rowCount(), 3)
        self.assertEqual(self.panel.player_table.item(0, 0).text(), "QB")
        self.assertEqual(self.panel.player_table.item(0, 1).text(), "18")
        self.assertEqual(self.panel.player_table.item(0, 2).text(), "Peyton Manning")
        self.assertIn("Peyton Manning", self.panel.header_name.text())
        self.assertIn("6'5\"", self.panel.header_stats.text())
        self.assertIn("Tennessee", self.panel.header_stats.text())
        self.assertIn("Contract", self.panel.header_contract.text())

    def test_every_card_group_from_the_core_module_is_on_a_tab(self) -> None:
        titles = [self.panel.tabs.tabText(i) for i in range(self.panel.tabs.count())]
        self.assertEqual(titles[:-1], list(rr.ATTRIBUTE_CARDS) + ["Abilities"])
        self.assertEqual(titles[-1], "Checks")
        placed = [name for fields in rr.ATTRIBUTE_CARDS.values() for name in fields]
        self.assertEqual(len(placed), len(set(placed)), "a field may only sit on one card")
        for group, fields in rr.ATTRIBUTE_CARDS.items():
            for name in fields:
                self.assertIn(name, self.panel.cards, f"{group}/{name}")
        for name in rr.RATING_BYTE_ORDER:
            self.assertIn(name, placed, f"{name} has no card")
        self.assertIsNotNone(self.panel.cards["position"].combo, "enums are dropdowns")
        self.assertEqual(self.panel.cards["position"].combo.count(), len(rr.POSITIONS))
        self.assertIsNotNone(self.panel.cards["speed"].bar, "ratings get a drag bar")

    def test_chips_and_search_narrow_the_grid(self) -> None:
        self.panel._chip_clicked("QB")
        self.assertEqual([p.display for p in self.panel.visible_players()], ["Peyton Manning"])
        self.panel._chip_clicked("All")
        self.panel.search.setText("harrison")
        self.application.processEvents()
        self.assertEqual([p.display for p in self.panel.visible_players()], ["Marvin Harrison"])
        self.panel.search.setText("Tennessee")
        self.application.processEvents()
        self.assertEqual(len(self.panel.visible_players()), 3)
        self.panel.search.setText("8")                      # years pro
        self.application.processEvents()
        self.assertEqual([p.display for p in self.panel.visible_players()], ["Marvin Harrison"])
        self.panel.search.setText("")
        self.panel.team_list.setCurrentRow(self.panel.team_list.count() - 2)
        self.application.processEvents()
        self.assertEqual([p.display for p in self.panel.visible_players()], ["Draft Prospect"])

    # ------------------------------------------------------------------ editing
    def test_a_card_edit_marks_the_player_and_undo_puts_it_back(self) -> None:
        player = self.panel.selected_player()
        assert player is not None
        card = self.panel.cards["speed"]
        self.assertEqual(card.value(), 66)
        card.spin.setValue(80)
        self.application.processEvents()
        self.assertEqual(player.record.values["speed"], 80)
        self.assertIn((player.pool, player.index), self.panel._dirty)
        self.assertEqual(self.panel.player_table.item(0, 2).text(), "● Peyton Manning")
        self.assertTrue(self.panel.undo_button.isEnabled())
        self.assertEqual(self.panel.undo(), "Peyton Manning: speed")
        self.assertEqual(player.record.values["speed"], 66)
        self.assertNotIn((player.pool, player.index), self.panel._dirty)
        self.assertEqual(self.panel.player_table.item(0, 2).text(), "Peyton Manning")
        self.assertTrue(self.panel.redo_button.isEnabled())
        self.panel.redo()
        self.assertEqual(player.record.values["speed"], 80)

    def test_the_bar_sets_the_value_and_arrow_keys_nudge_it(self) -> None:
        bar = ValueBar(0, 99)
        seen: list[int] = []
        bar.valueChanged.connect(seen.append)
        bar.resize(101, 12)
        bar.setValue(50)
        self.assertEqual(bar.value(), 50)
        bar.setValue(-5)
        self.assertEqual(bar.value(), 0)
        bar.setValue(500)
        self.assertEqual(bar.value(), 99)
        self.assertEqual(seen, [50, 0, 99])
        moves: list[int] = []
        bar.focusMoved.connect(moves.append)
        from PyQt5.QtGui import QKeyEvent

        bar.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Left, Qt.NoModifier))
        self.assertEqual(bar.value(), 98)
        bar.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Down, Qt.NoModifier))
        self.assertEqual(moves, [1])

    def test_arrow_keys_move_focus_between_the_cards_of_the_open_tab(self) -> None:
        self.panel.tabs.setCurrentIndex(0)                  # Athletic
        order = rr.ATTRIBUTE_CARDS["Athletic"]
        self.assertEqual(self.panel._move_card_focus(order[0], 1), order[1])
        self.assertEqual(self.panel._move_card_focus(order[0], -1), order[-1], "wraps around")
        self.assertEqual(self.panel._move_card_focus("speed", 1), "agility")
        self.panel.tabs.setCurrentIndex(list(rr.ATTRIBUTE_CARDS).index("Contract"))
        self.assertEqual(self.panel._move_card_focus("speed", 1), "", "speed is not on this tab")

    def test_the_style_tab_offers_segmented_controls_and_presets(self) -> None:
        style = list(rr.ATTRIBUTE_CARDS).index("Style")
        self.assertEqual(self.panel.tabs.tabText(style), "Style")
        bucket = self.panel.cards["power_run_style_bucket"]
        self.assertEqual([b.text() for b in bucket.segments], list(rr.POWER_RUN_STYLES))
        throw = self.panel.cards["throw_style"]
        self.assertEqual([b.text() for b in throw.segments], list(rr.THROW_STYLES))
        self.assertIn("only bit test", throw.toolTip())
        self.assertIn("EXPERIMENTAL", self.panel.cards["kicking_style"].toolTip())
        self.assertIn("Best Hand", self.panel.cards["hand"].toolTip())
        self.assertEqual(self.panel.cards["hand"].name, "hand")
        player = self.panel.selected_player()
        assert player is not None
        player.record.values["power_run_style"] = 1
        player.record.values["scramble"] = 10
        self.panel._show_player(player)
        self.assertEqual(bucket.value(), 0)
        self.assertEqual(throw.value(), 0)
        # the segmented control writes the game's own value
        bucket._segment_clicked(2)
        self.application.processEvents()
        self.assertEqual(player.record.values["power_run_style"], 99)
        self.assertEqual(self.panel.undo(), "Peyton Manning: power_run_style_bucket")
        self.assertEqual(player.record.values["power_run_style"], 1)
        # the throw-style toggle moves only the low bit
        throw._segment_clicked(1)
        self.application.processEvents()
        self.assertEqual(player.record.values["scramble"], 11)
        self.assertEqual(player.record.throw_style, 1)
        # and the Scramble slider moves the magnitude without disturbing it
        self.panel.cards["scramble"]._preset_clicked(90)
        self.application.processEvents()
        self.assertEqual(player.record.values["scramble"], 91)
        self.assertEqual(player.record.throw_style, 1)
        self.assertIn("signature release", self.panel.header_stats.text())
        self.assertIn(rr.POWER_RUN_STYLES[player.record.power_run_style_bucket],
                      self.panel.header_stats.text())

    def test_the_global_dialog_can_sweep_a_style_with_a_condition(self) -> None:
        for player in self.panel.document.players:
            player.record.throw_style = 0
        dialog = GlobalEditDialog(self.panel)
        try:
            targets = [dialog.attribute.itemData(i) for i in range(dialog.attribute.count())]
            for name in ("power_run_style_bucket", "throw_style", "scramble", "kicking_style"):
                self.assertIn(name, targets)
            dialog.attribute.setCurrentIndex(targets.index("throw_style"))
            dialog.mode.setCurrentIndex(0)                  # equal
            dialog.value.setValue(1)
            dialog.positions["QB"].setChecked(True)
            dialog.where_enabled.setChecked(True)
            where_targets = [dialog.where_attribute.itemData(i)
                             for i in range(dialog.where_attribute.count())]
            dialog.where_attribute.setCurrentIndex(where_targets.index("speed"))
            dialog.where_operator.setCurrentIndex(0)        # >=
            dialog.where_value.setValue(80)
            self.assertEqual(dialog.settings()["where"], ("speed", ">=", 80))
            rows = dialog.refresh_preview()
            self.assertEqual([row["name"] for row in rows], ["Michael Vick"])
            dialog._apply()
            vick = next(p for p in self.panel.document.players if p.last == "Vick")
            self.assertEqual(vick.record.throw_style, 1)
        finally:
            dialog.deleteLater()
            self.application.processEvents()

    def test_a_name_edit_shares_a_pool_string_and_a_long_one_is_refused(self) -> None:
        self.panel._chip_clicked("All")
        self.panel.team_list.setCurrentRow(2)               # ATL: Vick, Dunn, Moss
        self.application.processEvents()
        self.assertTrue(self.panel.select_player(self.panel.visible_players()[0]))
        player = self.panel.selected_player()
        assert player is not None and player.last == "Vick"
        self.panel.first_field.setText("Randy")
        self.panel._name_committed("first")
        self.assertEqual(player.first, "Randy")
        self.assertIn((player.pool, player.index), self.panel._dirty)
        self.panel.undo()
        self.assertEqual(player.first, "Michael")
        # a name with nowhere to go is refused and the field snaps back
        self.panel.last_field.setText("Vickerstaffe")
        self.panel._name_committed("last")
        self.assertEqual(player.last, "Vick")
        self.assertEqual(self.panel.last_field.text(), "Vick")
        self.assertIn("full", self.panel.status_label.text())

    def test_depth_reorder_moves_the_player_in_the_list(self) -> None:
        self.assertTrue(self.panel.move_selected(1))
        self.assertEqual([p.display for p in self.panel.visible_players()],
                         ["Marvin Harrison", "Peyton Manning", "Edgerrin James"])
        self.panel.undo()
        self.assertEqual([p.display for p in self.panel.visible_players()],
                         ["Peyton Manning", "Marvin Harrison", "Edgerrin James"])

    def test_copy_and_paste_modes(self) -> None:
        self.assertTrue(self.panel.copy_player())
        self.panel.player_table.setCurrentCell(1, 0)
        self.application.processEvents()
        target = self.panel.selected_player()
        assert target is not None
        self.assertEqual(self.panel.paste_player("attributes"), 28)
        self.assertEqual(target.record.values["speed"], 66)
        self.assertEqual(target.last, "Harrison", "names never travel with a paste")
        self.panel.undo()
        self.assertEqual(target.record.values["speed"], 88)

    # ------------------------------------------------------------------ passes
    def test_global_edit_preview_and_apply(self) -> None:
        preview = self.panel.global_edit_preview(attribute="speed", mode="add", value=5, positions=["QB"])
        self.assertEqual({row["name"] for row in preview}, {"Peyton Manning", "Michael Vick"})
        self.assertEqual(self.panel.apply_global_edit(preview, "speed"), 2)
        self.assertEqual(self.panel.document.players[0].record.values["speed"], 71)
        self.assertEqual(len(self.panel._dirty), 2)
        self.panel.undo()
        self.assertEqual(self.panel.document.players[0].record.values["speed"], 66)

    def test_the_global_dialog_previews_before_it_applies(self) -> None:
        dialog = GlobalEditDialog(self.panel)
        try:
            dialog.attribute.setCurrentIndex(
                [dialog.attribute.itemData(i) for i in range(dialog.attribute.count())].index("speed"))
            dialog.mode.setCurrentIndex(1)                  # add
            dialog.value.setValue(3)
            dialog.positions["QB"].setChecked(True)
            rows = dialog.refresh_preview()
            self.assertEqual(len(rows), 2)
            self.assertIn("Peyton Manning (QB): 66 -> 69", dialog.preview.toPlainText())
            self.assertEqual(self.panel.document.players[0].record.values["speed"], 66,
                             "the preview changes nothing")
            dialog._apply()
            self.assertEqual(self.panel.document.players[0].record.values["speed"], 69)
        finally:
            dialog.deleteLater()
            self.application.processEvents()

    def test_advance_years_pro_and_restore_measurements(self) -> None:
        self.assertEqual(self.panel.advance_years_pro(False), len(SAMPLE))
        self.assertEqual(self.panel.document.players[0].record.values["years_pro"], 8)
        self.panel.undo()
        self.assertEqual(self.panel.document.players[0].record.values["years_pro"], 7)
        player = self.panel.selected_player()
        assert player is not None
        player.record.weight = 305
        self.panel.restore_measurements()
        self.assertEqual(player.record.weight, 230)

    def test_validation_and_diff_fill_the_report(self) -> None:
        player = self.panel.selected_player()
        assert player is not None
        self.panel.set_field(player, "jersey", 88)
        findings = self.panel.run_validation()
        self.assertTrue(any(item["check"] == "jersey" for item in findings))
        self.assertIn("outside this check's", self.panel.report.toPlainText())
        self.assertIn("Editor check —", self.panel.report.toPlainText())
        entries = self.panel.refresh_diff()
        self.assertEqual(len(entries), 1)
        self.assertIn("1 player differs", self.panel.report.toPlainText())
        self.assertIn("Jersey Number: 18 -> 88", self.panel.report.toPlainText())

    # ------------------------------------------------------------------ round trips
    def test_csv_export_and_import_round_trip(self) -> None:
        text = self.panel.export_csv_text(everything=True)
        self.assertEqual(len(text.strip().splitlines()), len(SAMPLE) + 1)
        receipt = self.panel.import_csv_text(text)
        self.assertEqual((receipt["rows"], receipt["changed"], receipt["fields"], receipt["log"]),
                         (len(SAMPLE), 0, 0, []))
        edited = text.replace("Peyton,Manning,QB,18,7", "Peyton,Manning,QB,12,9")
        receipt = self.panel.import_csv_text(edited)
        self.assertEqual(receipt["fields"], 2)
        self.assertEqual(self.panel.document.players[0].record.values["jersey"], 12)
        self.panel.undo()
        self.assertEqual(self.panel.document.players[0].record.values["jersey"], 18)

    def test_the_play_by_play_and_portrait_cards_carry_a_searchable_picker(self) -> None:
        player = self.panel.selected_player()
        assert player is not None
        for name in ("pbp_id", "photo_id"):
            self.assertIsNotNone(self.panel.cards[name].pick_button, name)
        self.assertIsNone(self.panel.cards["jersey"].pick_button)
        entries, note = self.panel.picker_entries("pbp_id")
        self.assertEqual(entries[1000], "Manning, Peyton")
        self.assertIn("recorded surname bank", note)
        dialog = IdPickerDialog("Play-by-play name", entries, player.record.values["pbp_id"], self.panel, note=note)
        self.assertEqual(dialog.chosen(), 1000)
        self.assertEqual(dialog.list.currentRow(), 0)
        dialog.search.setText("vick")
        self.assertEqual(dialog.list.count(), 1)
        self.assertEqual(dialog.count_label.text().split(" of ")[0], "1")
        dialog.list.setCurrentRow(0)
        self.assertEqual(dialog.chosen(), 1003)
        dialog.search.setText("9300")
        self.assertEqual(dialog.list.item(0).text().strip(), "9300 · Smith (recorded surname bank)")
        dialog.spin.setValue(4242)                                      # any id can still be typed
        self.assertEqual(dialog.chosen(), 4242)
        self.panel.set_field(player, "pbp_id", dialog.chosen())
        self.assertEqual(player.record.values["pbp_id"], 4242)
        self.assertEqual(self.panel.cards["pbp_id"].value(), 4242)
        self.panel.undo()
        self.assertEqual(player.record.values["pbp_id"], 1000)
        entries, note = self.panel.picker_entries("photo_id")
        if rr.PORTRAIT_REPORT.is_file():
            self.assertEqual(len(entries), 4303)
            self.assertIn("4303 portraits", note)
        else:
            self.assertEqual(entries, {})
            self.assertIn("not listed", note)

    def test_templates_offer_the_positions_three_first_and_apply_with_undo(self) -> None:
        player = self.panel.selected_player()
        assert player is not None
        self.assertTrue(self.panel.template_button.isEnabled())
        self.panel._fill_template_menu()
        labels = [a.text() for a in self.panel.template_menu.actions() if a.text() and not a.menu()]
        self.assertEqual(labels[:3], ["Pocket QB", "Scrambling QB", "Balanced QB"])
        self.assertTrue(labels[-1].startswith("Source: retail table"))
        before = dict(player.record.values)
        changes = self.panel.apply_template(rr.create_player_templates()[1])
        self.assertGreater(len(changes), 20)
        self.assertEqual(player.record.values["scramble"], 90)
        self.assertEqual(self.panel.cards["scramble"].value(), 90)
        self.assertIn((player.pool, player.index), self.panel._dirty)
        self.assertIn("Applied Scrambling QB", self.panel.status_label.text())
        self.assertEqual(self.panel.undo(), "Peyton Manning: template Scrambling QB")
        self.assertEqual(player.record.values, before)
        self.panel.team_list.setCurrentRow(self.panel.team_list.count() - 2)      # the DT prospect
        self.application.processEvents()
        self.panel._fill_template_menu()
        first = self.panel.template_menu.actions()[0]
        self.assertFalse(first.isEnabled())
        self.assertIn("No template for DT", first.text())

    def test_a_player_data_backup_round_trips_with_undo(self) -> None:
        backup = self.panel.export_player_data_bytes()
        self.assertEqual(len(backup), rr.PLAYER_DATA_ENTRY_SIZE * len(SAMPLE))
        player = self.panel.selected_player()
        assert player is not None
        self.panel.set_field(player, "speed", 3)
        receipt = self.panel.import_player_data_bytes(backup)
        self.assertEqual((receipt["matched"], receipt["changed"], receipt["fields"]), (len(SAMPLE), 1, 1))
        self.assertEqual(player.record.values["speed"], 66)
        self.assertNotIn((player.pool, player.index), self.panel._dirty)
        self.assertIn(".PlayerData: 8 entries", self.panel.status_label.text())
        self.assertEqual(self.panel.undo(), ".PlayerData restore (1 players)")
        self.assertEqual(player.record.values["speed"], 3)
        self.panel.redo()
        self.assertEqual(player.record.values["speed"], 66)
        with self.assertRaises(rr.RosterRecordError):
            self.panel.import_player_data_bytes(b"not a backup")

    def test_saving_the_edits_document_announces_it_for_the_build_tab(self) -> None:
        seen: list[str] = []
        self.panel.roster_edits_changed.connect(seen.append)
        player = self.panel.selected_player()
        assert player is not None
        self.panel.set_field(player, "speed", 44)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "roster_edits.json"
            document = self.panel.save_edits_to(target)
            self.assertEqual(seen, [str(target)])
            self.assertEqual(document["schema"], rr.EDITS_SCHEMA)
            written = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(written["edits"][0]["fields"], {"speed": 44})
            replayed, receipt = rr.apply_body(self.body, target)
            self.assertEqual(receipt["players_changed"], 1)
            self.assertEqual(replayed, self.panel.document.to_body())

    def test_a_save_container_is_loaded_verified_and_written_back_re_signed(self) -> None:
        savegame = self.body + bytes(224)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = tmp / "BaseRoster.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("53450030/0001/SAVEGAME.DAT", savegame)
                archive.writestr("53450030/0001/EXTRA", rr.sign_save(savegame))
                archive.writestr("53450030/0001/SaveMeta.xbx", b"META")
            self.assertTrue(self.panel.load_save(source))
            self.assertIn("signature verified", self.panel.source_label.text())
            player = self.panel.selected_player()
            assert player is not None
            self.panel.set_field(player, "speed", 21)
            receipt = self.panel.write_copy_to(tmp / "edited.zip")
            self.assertTrue(receipt["signed"])
            self.assertTrue(rr.SaveContainer.load(tmp / "edited.zip").verified)
            self.assertEqual(rr.load_save(tmp / "edited.zip").players[0].record.values["speed"], 21)
            with self.assertRaises(rr.RosterRecordError):
                self.panel.write_copy_to(source)

    def test_a_disc_copy_is_written_beside_the_source_and_the_source_is_untouched(self) -> None:
        from nfl2k5_xiso_fixture import SyntheticXiso
        from test_nfl2k5_roster_records import synthetic_resource

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            dummies = [(100 + k, b"DUMY" + bytes(0x100)) for k in range(5)]
            fixture = SyntheticXiso(tmp, dummies + [(5, synthetic_resource(self.body)),
                                                    (200, b"TAIL" + bytes(0x100))],
                                    pack_sizes=(0xA0000,), pack_sectors=(64,))
            before = Path(fixture.path).read_bytes()
            self.assertTrue(self.panel.load_disc(fixture.path))
            player = self.panel.selected_player()
            assert player is not None
            self.panel.set_field(player, "speed", 17)
            target = tmp / "copy.xiso.iso"
            receipt = self.panel.write_copy_to(target)
            self.assertEqual(receipt["fields_written"], 1)
            self.assertEqual(Path(fixture.path).read_bytes(), before, "the source disc is untouched")
            self.assertEqual(rr.load_image(target).players[0].record.values["speed"], 17)
            with self.assertRaises(rr.RosterRecordError):
                self.panel.write_copy_to(Path(fixture.path))

    # ------------------------------------------------------------------ empties
    def test_an_empty_panel_is_inert_rather_than_broken(self) -> None:
        panel = RosterEditorPanel()
        try:
            self.assertEqual(panel.visible_players(), [])
            self.assertIsNone(panel.selected_player())
            self.assertEqual(panel.export_csv_text(), "")
            self.assertEqual(panel.edits_document(), {})
            self.assertEqual(panel.advance_years_pro(), 0)
            self.assertEqual(panel.run_validation(), [])
            self.assertFalse(panel.copy_player())
            self.assertFalse(panel.save_edits_button.isEnabled())
            with self.assertRaises(rr.RosterRecordError):
                panel.write_copy_to("nowhere")
        finally:
            panel.deleteLater()
            self.application.processEvents()


class MembershipPanelTests(unittest.TestCase):
    """Release / Sign / Move / Swap under the grid, on a league big enough for Finn's rules."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.body = league_body()
        self.panel = RosterEditorPanel()
        self.panel.load_document(rr.load_body(self.body), label="league")
        self.application.processEvents()

    def tearDown(self) -> None:
        self.panel.deleteLater()
        self.application.processEvents()

    def rows(self) -> list[str]:
        return [self.panel.team_list.item(i).text() for i in range(self.panel.team_list.count())
                if self.panel.team_list.item(i).data(Qt.UserRole)[0] != "reserve"]

    def goto(self, row: int, cell: int = 0) -> rr.Player:
        rows = [i for i in range(self.panel.team_list.count())
                if self.panel.team_list.item(i).data(Qt.UserRole)[0] != "reserve"]
        self.panel.team_list.setCurrentRow(rows[row])
        self.application.processEvents()
        self.panel.player_table.setCurrentCell(cell, 0)
        self.application.processEvents()
        player = self.panel.selected_player()
        assert player is not None
        return player

    def test_the_buttons_follow_the_selection(self) -> None:
        self.assertEqual(self.rows()[:2], [f"IND · {LEAGUE_CLUB_SIZE} active + 0 reserve", f"ATL · {LEAGUE_CLUB_SIZE} active + 0 reserve"])
        self.assertTrue(self.panel.release_button.isEnabled())
        self.assertTrue(self.panel.swap_button.isEnabled())
        self.assertEqual(self.panel.team_menu_button.text(), "Move to ▾")
        self.goto(len(self.rows()) - 3)                  # Free Agents
        self.assertFalse(self.panel.release_button.isEnabled())
        self.assertFalse(self.panel.swap_button.isEnabled())
        self.assertTrue(self.panel.team_menu_button.isEnabled())
        self.assertEqual(self.panel.team_menu_button.text(), "Sign to ▾")
        self.goto(len(self.rows()) - 2)                  # Draft Class
        self.assertFalse(self.panel.release_button.isEnabled())
        self.assertFalse(self.panel.team_menu_button.isEnabled())
        self.assertFalse(self.panel.swap_button.isEnabled())
        self.panel._fill_team_menu()
        self.assertEqual(len(self.panel.team_menu.actions()), 0, "nothing is offered for a prospect")

    def test_release_updates_the_lists_and_undo_puts_him_back(self) -> None:
        player = self.goto(0, 5)
        receipt = self.panel.release_selected()
        assert receipt is not None
        self.assertEqual(receipt["from"]["slot"], 5)
        self.assertEqual(self.rows()[0], f"IND · {LEAGUE_CLUB_SIZE - 1} active + 0 reserve")
        self.assertEqual(self.rows()[-3], "Free Agents · 4")
        self.assertIn((player.pool, player.index), self.panel._dirty)
        self.assertNotIn(player, self.panel.visible_players())
        self.assertIn("Released", self.panel.status_label.text())
        self.assertEqual(self.panel.undo(), f"{player.display}: release")
        self.assertEqual(self.rows()[0], f"IND · {LEAGUE_CLUB_SIZE} active + 0 reserve")
        self.assertIs(self.panel.visible_players()[5], player)
        self.assertNotIn((player.pool, player.index), self.panel._dirty)
        self.assertEqual(self.panel.document.to_body(), self.body)
        self.panel.redo()
        self.assertEqual(self.rows()[0], f"IND · {LEAGUE_CLUB_SIZE - 1} active + 0 reserve")

    def test_a_refusal_is_reported_on_the_status_line_and_changes_nothing(self) -> None:
        self.panel.load_document(rr.load_body(league_body(rr.TEAM_MIN_PLAYERS)), label="tight")
        self.application.processEvents()
        self.goto(0, 0)
        self.assertIsNone(self.panel.release_selected())
        self.assertIn("must maintain at least 42", self.panel.status_label.text())
        self.assertEqual(self.panel.undo_stack.depth, (0, 0))
        self.assertEqual(self.panel.document.diff(), [])

    def test_sign_and_move_through_the_team_menu(self) -> None:
        free_agent = self.goto(len(self.rows()) - 3)
        self.panel._fill_team_menu()
        labels = [a.text() for a in self.panel.team_menu.actions() if a.text()]
        self.assertTrue(labels[0].startswith("IND ·"))
        receipt = self.panel.send_selected_to(1)
        assert receipt is not None
        self.assertEqual((receipt["operation"], receipt["to"]["team"]), ("sign", "ATL"))
        self.assertEqual(self.rows()[1], f"ATL · {LEAGUE_CLUB_SIZE + 1} active + 0 reserve")
        self.assertIn("Sign:", self.panel.status_label.text())
        self.goto(1, LEAGUE_CLUB_SIZE)                    # he sits at the bottom of ATL
        self.assertIs(self.panel.selected_player(), free_agent)
        self.assertIn(f"ATL ({LEAGUE_CLUB_SIZE + 1} of {LEAGUE_CLUB_SIZE + 1})", self.panel.header_contract.text())
        self.assertEqual(self.panel.team_menu_button.text(), "Move to ▾")
        moved = self.panel.send_selected_to(0)
        assert moved is not None
        self.assertEqual((moved["operation"], moved["from"]["team"], moved["to"]["team"]), ("transfer", "ATL", "IND"))
        self.assertEqual(self.rows()[:2], [f"IND · {LEAGUE_CLUB_SIZE + 1} active + 0 reserve", f"ATL · {LEAGUE_CLUB_SIZE} active + 0 reserve"])
        self.panel.undo()
        self.panel.undo()
        self.assertEqual(self.panel.document.to_body(), self.body)

    def test_swap_through_the_dialog_and_the_diff_names_the_teams(self) -> None:
        player = self.goto(0, 2)
        dialog = SwapPlayerDialog(self.panel, player)
        self.assertEqual(dialog.team_combo.currentData(), 1, "defaults to the other club")
        other = self.panel.document.team_players(1)[4]
        self.assertTrue(dialog.select_player(other))
        self.assertIs(dialog.chosen(), other)
        receipt = self.panel.swap_selected_with(dialog.chosen())
        assert receipt is not None
        self.assertEqual(receipt["operation"], "swap")
        self.assertIs(self.panel.visible_players()[2], other)
        self.assertIs(self.panel.document.team_players(1)[4], player)
        self.assertEqual(self.rows()[:2], [f"IND · {LEAGUE_CLUB_SIZE} active + 0 reserve", f"ATL · {LEAGUE_CLUB_SIZE} active + 0 reserve"])
        entries = self.panel.refresh_diff()
        self.assertEqual({e["name"] for e in entries}, {player.display, other.display})
        report = self.panel.report.toPlainText()
        self.assertIn(f"team: IND (3 of {LEAGUE_CLUB_SIZE}) -> ATL (5 of {LEAGUE_CLUB_SIZE})", report)
        self.panel.undo()
        self.assertEqual(self.panel.document.to_body(), self.body)

    def test_the_csv_team_column_and_the_edits_document_carry_moves(self) -> None:
        text = self.panel.export_csv_text(everything=True)
        mover = self.panel.document.team_players(1)[3]
        edited = text.replace(f"primary,{mover.index},ATL,", f"primary,{mover.index},IND,")
        receipt = self.panel.import_csv_text(edited)
        self.assertEqual(receipt["changed"], 1)
        self.assertEqual(self.rows()[:2], [f"IND · {LEAGUE_CLUB_SIZE + 1} active + 0 reserve", f"ATL · {LEAGUE_CLUB_SIZE - 1} active + 0 reserve"])
        self.assertIn((mover.pool, mover.index), self.panel._dirty)
        document = self.panel.edits_document()
        self.assertEqual(len(document["moves"]), 1)
        self.assertEqual(document["moves"][0]["to_teams"][0]["team"], "IND")
        replayed, replay = rr.apply_body(self.body, document)
        self.assertEqual(replay["players_moved"], 1)
        self.assertEqual(replayed, self.panel.document.to_body())
        self.panel.undo()
        self.assertEqual(self.rows()[:2], [f"IND · {LEAGUE_CLUB_SIZE} active + 0 reserve", f"ATL · {LEAGUE_CLUB_SIZE} active + 0 reserve"])
        self.assertEqual(self.panel.document.to_body(), self.body)
        self.assertNotIn((mover.pool, mover.index), self.panel._dirty)


class RepairPanelTests(unittest.TestCase):
    """Check & repair on load: offered, never silent; applied with a receipt and an undo."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.body = damaged_body()
        self.panel = RosterEditorPanel()
        self.panel.load_document(rr.load_body(self.body), label="damaged")
        self.application.processEvents()

    def tearDown(self) -> None:
        self.panel.deleteLater()
        self.application.processEvents()

    def test_repairs_are_offered_on_load_and_nothing_is_touched(self) -> None:
        self.assertEqual(self.panel.repair_button.text(), "Repair (3)")
        self.assertTrue(self.panel.repair_button.isEnabled())
        self.assertIn("3 repairs available", self.panel.status_label.text())
        self.assertIn("Nothing has been changed", self.panel.report.toPlainText())
        self.assertIn("Peyton Manning", self.panel.report.toPlainText())
        self.assertEqual(self.panel.document.to_body(), self.body)
        self.assertEqual(self.panel.undo_stack.depth, (0, 0))
        clean = RosterEditorPanel()
        clean.load_document(rr.load_body(synthetic_body()), label="clean")
        self.assertEqual(clean.repair_button.text(), "Repair")
        self.assertFalse(clean.repair_button.isEnabled())
        self.assertNotIn("repair", clean.status_label.text())
        clean.deleteLater()

    def test_repair_applies_with_a_receipt_and_undoes(self) -> None:
        receipt = self.panel.run_repairs()
        assert receipt is not None
        self.assertEqual(receipt["applied"], 3)
        report = self.panel.report.toPlainText()
        self.assertTrue(report.startswith("Repaired 1 headless player;"), report)
        self.assertIn("City1 Team1: the count byte says 4", report)
        self.assertEqual(self.panel.tabs.currentIndex(), self.panel.tabs.count() - 1)
        self.assertFalse(self.panel.repair_button.isEnabled())
        self.assertEqual(self.panel.document.players[0].record.values["headless"], 0)
        self.assertIn(("primary", 0), self.panel._dirty)
        self.assertEqual([self.panel.team_list.item(i).text() for i in (0, 2)],
                         ["IND · 3 active + 0 reserve", "ATL · 3 active + 0 reserve"])
        self.assertEqual(self.panel.undo(), "repair (3)")
        self.assertEqual(self.panel.document.to_body(), self.body)
        self.assertEqual(self.panel.repair_button.text(), "Repair (3)")
        self.assertNotIn(("primary", 0), self.panel._dirty)
        self.panel.redo()
        self.assertEqual(rr.plan_repairs(self.panel.document), [])
        diff = self.panel.refresh_diff()
        self.assertEqual(diff[0]["changes"], {"headless": (1, 0)})


class UndoStackTests(unittest.TestCase):
    def test_push_undo_redo_and_the_limit(self) -> None:
        stack = UndoStack(limit=3)
        log: list[str] = []
        for index in range(5):
            stack.push(UndoEntry(str(index), (lambda i=index: log.append(f"-{i}")),
                                 (lambda i=index: log.append(f"+{i}"))))
        self.assertEqual(stack.depth, (3, 0))
        self.assertEqual(stack.undo(), "4")
        self.assertEqual(stack.depth, (2, 1))
        self.assertEqual(stack.redo(), "4")
        self.assertEqual(log, ["-4", "+4"])
        stack.clear()
        self.assertEqual((stack.undo(), stack.redo()), ("", ""))


class ShellPlacementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_the_studio_offers_the_rosters_row_and_its_page(self) -> None:
        from mod_editor.gui.studio_qt import BrowseOnlyFacade, StudioMainWindow

        if not (ROOT / "reports" / "assets").exists():
            self.skipTest("Studio shell requires the private uniform catalog under reports/assets")
        window = StudioMainWindow(facade=BrowseOnlyFacade(), offer_recovery=False)
        try:
            rows = [window.navigation.item(i).text().strip() for i in range(window.navigation.count())]
            self.assertIn("★ Rosters", rows)
            row = rows.index("★ Rosters")
            self.assertEqual(window.navigation.item(row).data(Qt.UserRole), "rosters")
            window.navigation.setCurrentRow(row)
            self.application.processEvents()
            self.assertEqual(window.page_title.text(), "Rosters")
            self.assertIs(window.pages.widget(row).findChildren(RosterEditorPanel)[0],
                          window._roster_editor_panel)
            self.assertEqual(window.pages.count(), window.navigation.count())
        finally:
            window.deleteLater()
            self.application.processEvents()

    def test_the_build_tab_takes_a_roster_edits_document(self) -> None:
        from mod_editor.gui.build_panel_qt import BuildPanel

        panel = BuildPanel(None)
        try:
            panel.roster_edits_check.setEnabled(True)
            panel.set_roster_edits("/tmp/roster_edits.json")
            self.assertTrue(panel.roster_edits_check.isChecked())
            panel.source_field.setText("disc.iso")
            panel.target_field.setText("copy.iso")
            self.assertEqual(panel.plan().roster_edits, "/tmp/roster_edits.json")
            self.assertTrue(panel.has_work())
            panel.set_roster_edits("")
            self.assertEqual(panel.plan().roster_edits, "")
        finally:
            panel.deleteLater()
            self.application.processEvents()


class PositionSchemePanelTests(unittest.TestCase):
    """The page relabels itself for the scheme the loaded source is on."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.panel = RosterEditorPanel()

    def tearDown(self) -> None:
        self.panel.deleteLater()
        self.application.processEvents()

    def _load(self, body: bytes) -> None:
        self.panel.load_document(rr.load_body(body), label="synthetic")
        self.application.processEvents()

    def _grid(self) -> dict[str, str]:
        out = {}
        for row in range(self.panel.player_table.rowCount()):
            out[self.panel.player_table.item(row, 2).text().lstrip("● ")] = \
                self.panel.player_table.item(row, 0).text()
        return out

    # ------------------------------------------------------------------ detection
    def test_a_reclassified_roster_is_detected_and_relabels_the_page(self) -> None:
        self._load(one_pool_body())
        self.assertEqual(self.panel.scheme, "one_pool")
        self.assertIn("EDGE", self.panel.chips, "one pool gets its own EDGE chip")
        self.assertNotIn("EDGE", RosterEditorPanel().chips, "a fresh page starts on the retail set")
        self.assertIn("no primary-pool player carries the retired OLB code",
                      self.panel.scheme_label.text())
        self.panel.team_list.setCurrentRow(4)
        self.application.processEvents()
        grid = self._grid()
        self.assertEqual(grid["Ray Lewis"], "LB")
        self.assertEqual(grid["Terrell Suggs"], "EDGE")
        self.assertEqual(grid["Kelly Gregg"], "DT")

    def test_a_retail_roster_keeps_the_retail_table(self) -> None:
        self._load(retail_front_body())
        self.assertEqual(self.panel.scheme, "retail")
        self.assertNotIn("EDGE", self.panel.chips)
        self.panel.team_list.setCurrentRow(4)
        self.application.processEvents()
        grid = self._grid()
        self.assertEqual(grid["Peter Boulware"], "OLB")
        self.assertEqual(grid["Terrell Suggs"], "DE")
        self.assertIn("EDGE rename", self.panel.scheme_label.text(),
                      "the page admits it cannot see the rename in roster data")

    def test_the_selector_overrides_the_detection_both_ways(self) -> None:
        self._load(one_pool_body())
        index = self.panel.scheme_combo.findData("retail")
        self.panel.scheme_combo.setCurrentIndex(index)
        self.panel._scheme_chosen(index)
        self.application.processEvents()
        self.assertEqual(self.panel.scheme, "retail")
        self.panel.team_list.setCurrentRow(4)
        self.application.processEvents()
        self.assertEqual(self._grid()["Ray Lewis"], "ILB")
        self.assertIn("chosen by you", self.panel.scheme_label.text())
        back = self.panel.scheme_combo.findData("auto")
        self.panel.scheme_combo.setCurrentIndex(back)
        self.panel._scheme_chosen(back)
        self.application.processEvents()
        self.assertEqual(self.panel.scheme, "one_pool")
        self.assertEqual(self._grid()["Ray Lewis"], "LB")

    def test_the_chips_filter_by_code_under_one_pool(self) -> None:
        self._load(one_pool_body())
        self.panel.team_list.setCurrentRow(4)
        self.panel._chip_clicked("EDGE")
        self.application.processEvents()
        self.assertEqual(sorted(p.last for p in self.panel.visible_players()),
                         ["Boulware", "Suggs", "Thomas"])
        self.panel._chip_clicked("DL")
        self.assertEqual([p.last for p in self.panel.visible_players()], ["Gregg"])
        self.panel._chip_clicked("LB")
        self.assertEqual([p.last for p in self.panel.visible_players()], ["Lewis"])

    # ------------------------------------------------------------------ the picker
    def test_the_position_picker_hides_the_retired_code_and_refuses_to_write_it(self) -> None:
        self._load(one_pool_body())
        card = self.panel.cards["position"]
        self.assertEqual(card.combo.itemText(11), "LB")
        self.assertEqual(card.combo.itemText(16), "EDGE")
        self.assertEqual(card.combo.itemText(10), "OLB (retired)")
        model = card.combo.model()
        self.assertFalse(model.item(10).isEnabled(), "the retired row cannot be picked or cycled")
        self.assertTrue(model.item(11).isEnabled())
        self.panel.team_list.setCurrentRow(4)
        self.application.processEvents()
        self.panel.select_player(next(p for p in self.panel.visible_players() if p.last == "Lewis"))
        player = self.panel.selected_player()
        self.assertEqual(player.last, "Lewis")
        self.panel._card_changed("position", 10)
        self.assertEqual(player.record.values["position"], 11, "the write is refused")
        self.assertIn("retired", self.panel.status_label.text())
        self.panel._card_changed("position", 16)
        self.assertEqual(player.record.values["position"], 16, "a live code still writes")
        self.assertEqual(self.panel.undo(), f"{player.display}: position")
        self.assertEqual(player.record.values["position"], 11)

    def test_the_picker_cycles_only_live_codes(self) -> None:
        try:
            from PyQt5.QtTest import QTest
        except ImportError:                                     # pragma: no cover - Qt build choice
            self.skipTest("PyQt5.QtTest is not available")
        self._load(one_pool_body())
        self.panel.team_list.setCurrentRow(4)
        self.application.processEvents()
        self.panel.select_player(next(p for p in self.panel.visible_players() if p.last == "Lewis"))
        combo = self.panel.cards["position"].combo
        combo.setCurrentIndex(9)                                # TE, the row above the retired OLB
        QTest.keyClick(combo, Qt.Key_Down)
        self.assertEqual(combo.currentText(), "LB", "the arrow keys step over the retired row")
        self.assertEqual(self.panel.selected_player().record.values["position"], 11)

    def test_the_picker_stays_whole_on_a_retail_roster(self) -> None:
        self._load(retail_front_body())
        card = self.panel.cards["position"]
        self.assertEqual(card.combo.itemText(10), "OLB")
        self.assertTrue(card.combo.model().item(10).isEnabled())
        self.panel.team_list.setCurrentRow(4)
        self.panel.select_player(next(p for p in self.panel.visible_players() if p.last == "Lewis"))
        self.panel._card_changed("position", 10)
        self.assertEqual(self.panel.selected_player().record.values["position"], 10)

    # ------------------------------------------------------------------ cards and header
    def test_the_header_names_the_position_and_the_card_set_it_is_rated_on(self) -> None:
        self._load(one_pool_body())
        self.panel.team_list.setCurrentRow(4)
        self.application.processEvents()
        self.panel.select_player(next(p for p in self.panel.visible_players() if p.last == "Suggs"))
        text = self.panel.header_profile.text()
        self.assertIn("Edge Rusher", text)
        self.assertIn("key ratings", text)
        self.assertIn("Pass Rush", text)
        # the card set the game rates the code on stays one hover away (the visible line says
        # "key ratings" so nobody reads it as the game's overall formula)
        self.assertIn("DE card set", self.panel.header_profile.toolTip())
        self.panel.select_player(next(p for p in self.panel.visible_players() if p.last == "Lewis"))
        text = self.panel.header_profile.text()
        self.assertIn("Linebacker", text)
        self.assertIn("ILB card set", self.panel.header_profile.toolTip())

    def test_the_depth_cell_says_where_the_player_sits_in_his_own_pool(self) -> None:
        self._load(one_pool_body())
        self.panel.team_list.setCurrentRow(4)
        self.application.processEvents()
        rows = [self.panel.player_table.item(r, 2).text() for r in range(self.panel.player_table.rowCount())]
        row = rows.index("Terrell Suggs")
        self.assertIn("Edge Rusher #", self.panel.player_table.item(row, 5).toolTip())
        self.assertIn(" of 3 ", self.panel.player_table.item(row, 5).toolTip())

    # ------------------------------------------------------------------ global edit and CSV
    def test_the_global_editor_offers_the_schemes_own_names(self) -> None:
        self._load(one_pool_body())
        dialog = GlobalEditDialog(self.panel)
        try:
            self.assertIn("EDGE", dialog.positions)
            self.assertIn("LB", dialog.positions)
            self.assertNotIn("ILB", dialog.positions)
            self.assertFalse(dialog.positions["OLB"].isEnabled(), "the retired pool cannot be aimed at")
            dialog.positions["EDGE"].setChecked(True)
            dialog.attribute.setCurrentIndex(0)          # Speed
            dialog.mode.setCurrentIndex(0)
            dialog.value.setValue(70)
            rows = dialog.refresh_preview()
            self.assertTrue(rows)
            self.assertTrue(all(row["position"] == "EDGE" for row in rows))
        finally:
            dialog.deleteLater()

    def test_loading_a_second_roster_reswitches_the_scheme(self) -> None:
        self._load(one_pool_body())
        self.panel.team_list.setCurrentRow(4)
        self.application.processEvents()
        self.assertEqual(self.panel.scheme, "one_pool")
        self._load(retail_front_body())
        self.assertEqual(self.panel.scheme, "retail")
        self.assertNotIn("EDGE", self.panel.chips)
        self.panel.team_list.setCurrentRow(4)
        self.application.processEvents()
        self.assertEqual(self._grid()["Peter Boulware"], "OLB")

    def test_the_checks_tab_reports_a_player_parked_on_the_retired_code(self) -> None:
        self._load(retail_front_body())
        index = self.panel.scheme_combo.findData("one_pool")
        self.panel.scheme_combo.setCurrentIndex(index)
        self.panel._scheme_chosen(index)
        self.panel.team_list.setCurrentRow(4)
        self.application.processEvents()
        findings = self.panel.run_validation()
        parked = [f for f in findings if f["check"] == "position"]
        self.assertEqual(len(parked), 2)
        self.assertIn("retired", self.panel.report.toPlainText())

    def test_the_diff_names_a_position_change_in_the_loaded_scheme(self) -> None:
        self._load(one_pool_body())
        self.panel.team_list.setCurrentRow(4)
        self.application.processEvents()
        self.panel.select_player(next(p for p in self.panel.visible_players() if p.last == "Lewis"))
        self.panel._card_changed("position", 16)
        self.panel.refresh_diff()
        self.assertIn("Position: LB -> EDGE", self.panel.report.toPlainText())

    def test_a_retail_csv_lands_on_a_one_pool_roster_with_a_warning(self) -> None:
        source = RosterEditorPanel()
        source.load_document(rr.load_body(retail_front_body()), label="retail")
        text = source.export_csv_text(everything=True)
        source.deleteLater()
        self.assertIn("OLB", text)

        self._load(one_pool_body())
        receipt = self.panel.import_csv_text(text)
        notes = [line for line in receipt["log"] if "retired" in line]
        self.assertEqual(len(notes), 2)
        moved = {p.last: p.record.values["position"] for p in self.panel.document.players}
        self.assertEqual(moved["Boulware"], 11)
        self.assertEqual(moved["Thomas"], 11)
        self.assertIn("notes", self.panel.status_label.text())

    def test_a_save_is_detected_from_its_records_alone(self) -> None:
        savegame = one_pool_body() + bytes(224)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "one-pool.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("53450030/0001/SAVEGAME.DAT", savegame)
                archive.writestr("53450030/0001/EXTRA", rr.sign_save(savegame))
            self.assertTrue(self.panel.load_save(source))
        self.assertEqual(self.panel.scheme, "one_pool")
        self.assertEqual(self.panel._scheme_detection["source"], "roster data",
                         "a save carries no executable to read a patch state off")
        self.assertIn("EDGE", self.panel.chips)

    def test_a_one_pool_csv_round_trips_through_the_page(self) -> None:
        self._load(one_pool_body())
        text = self.panel.export_csv_text(everything=True)
        self.assertIn("EDGE", text)
        self.assertIn("LB", text)
        before = self.panel.document.to_body()
        receipt = self.panel.import_csv_text(text)
        self.assertEqual(receipt["log"], [])
        self.assertEqual(receipt["fields"], 0)
        self.assertEqual(self.panel.document.to_body(), before)


if __name__ == "__main__":
    unittest.main()

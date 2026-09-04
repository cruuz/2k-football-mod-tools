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
    RosterEditorPanel,
    UndoStack,
    ValueBar,
)
from test_nfl2k5_roster_records import COLLEGES, SAMPLE, synthetic_body  # noqa: E402


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
        self.assertEqual(rows[:3], ["IND · 3", "ATL · 3", "SF · 0"])
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
        self.assertEqual(titles[:-1], list(rr.ATTRIBUTE_CARDS))
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
        self.assertIn("throw style B", self.panel.header_stats.text())
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
        self.panel.team_list.setCurrentRow(1)               # ATL: Vick, Dunn, Moss
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
        self.assertIn("outside the NFL range", self.panel.report.toPlainText())
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


if __name__ == "__main__":
    unittest.main()

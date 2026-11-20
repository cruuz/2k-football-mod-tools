"""b81 row R42: three Finn features on the Rosters page player card.

1. "PBP last name only" (Finn's checkbox beside the jersey number): checked exactly when the little-endian word at
   player +0x08 equals 5; the setter only acts on a word of 4 or 5 (checked writes 5, unchecked 4, every other byte
   kept); any other word disables the box with a tooltip that names the value.
2. Clear Photo (Finn's Edit > Clear Photo): 65535 into the u16 at +0x06 and nothing else.
3. Print (Finn's File > Print): the HTML export's table through QPrinter, here to a PDF without a dialog.

Offscreen Qt on synthetic rosters, plus the real SOFTDRINK roster save when it is present.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor", ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtPrintSupport import QPrinter  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.gui.roster_editor_panel_qt import RosterEditorPanel  # noqa: E402
from test_nfl2k5_roster_records import synthetic_body  # noqa: E402

SOFTDRINK_ROSTER_SAVE = Path(os.environ.get(
    "NFL2K5_SOFTDRINK_ROSTER_SAVE",
    "/media/noah/Storage/2K5-project/beta81/isolated-data/FC3-native-roster.zip"))


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def record_bytes(document: rr.RosterDocument, player: rr.Player) -> bytes:
    return bytes(document.to_body()[player.offset: player.offset + rr.PLAYER_SIZE])


def set_word(player: rr.Player, word: int) -> None:
    player.record.set("player_type", word & 0xFF)
    player.record.set("unknown_09", word >> 8)


class _Case(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = _app()

    def setUp(self) -> None:
        self.panel = RosterEditorPanel()
        self.panel.load_document(rr.load_body(synthetic_body()), label="synthetic")
        self.application.processEvents()
        self.player = next(p for p in self.panel.document.players if p.last == "Manning")
        self.panel.select_player(self.player)

    def tearDown(self) -> None:
        self.panel.close()
        self.panel.deleteLater()
        self.application.processEvents()

    def with_word(self, word: int) -> None:
        set_word(self.player, word)
        self.panel._show_player(self.player)

    def differing_offsets(self, before: bytes) -> list[int]:
        after = record_bytes(self.panel.document, self.player)
        return [i for i in range(rr.PLAYER_SIZE) if before[i] != after[i]]


class PbpLastNameOnlyTests(_Case):
    def test_the_box_follows_the_whole_word_at_plus_8(self) -> None:
        check = self.panel.pbp_last_check
        expectations = {4: (True, False), 5: (True, True), 0: (False, False), 12: (False, False),
                        0x0104: (False, False)}
        for word, (enabled, checked) in expectations.items():
            with self.subTest(word=word):
                self.with_word(word)
                self.assertEqual((check.isEnabled(), check.isChecked()), (enabled, checked))
                self.assertEqual(self.player.record.pbp_last_name_only, checked)

    def test_a_disabled_box_names_the_value_and_an_enabled_one_does_not_promise_a_recording(self) -> None:
        check = self.panel.pbp_last_check
        self.with_word(0x0104)
        self.assertIn("260", check.toolTip())
        self.assertIn("0x0104", check.toolTip())
        self.with_word(12)
        self.assertIn("12", check.toolTip())
        self.with_word(4)
        tip = check.toolTip()
        self.assertIn("has not been heard", tip)
        self.assertIn("does not promise", tip)
        self.assertNotIn("announce last name only", tip)

    def test_the_box_sits_on_the_jersey_card(self) -> None:
        self.assertIs(self.panel.pbp_last_check.parentWidget(), self.panel.cards["jersey"])

    def test_toggling_writes_5_then_4_and_only_byte_8_changes(self) -> None:
        original = record_bytes(self.panel.document, self.player)
        self.assertEqual(original[0x08:0x0A], bytes([4, 0]))
        self.panel.pbp_last_check.click()
        checked = record_bytes(self.panel.document, self.player)
        self.assertEqual(checked[0x08:0x0A], bytes([5, 0]))
        self.assertEqual(self.differing_offsets(original), [0x08])
        self.assertTrue(self.panel.pbp_last_check.isChecked())
        self.panel.pbp_last_check.click()
        self.assertEqual(record_bytes(self.panel.document, self.player), original)
        self.assertFalse(self.panel.pbp_last_check.isChecked())

    def test_every_other_byte_is_kept_when_the_setter_acts(self) -> None:
        self.player.record.set("jersey", 17)
        self.player.record.set("photo_id", 1234)
        before = record_bytes(self.panel.document, self.player)
        self.assertTrue(self.panel.set_pbp_last_only(self.player, True))
        self.assertEqual(self.differing_offsets(before), [0x08])

    def test_a_word_the_setter_does_not_own_is_refused_and_left_alone(self) -> None:
        for word in (0, 12, 0x0104):
            with self.subTest(word=word):
                self.with_word(word)
                before = record_bytes(self.panel.document, self.player)
                self.assertFalse(self.panel.set_pbp_last_only(self.player, True))
                self.assertFalse(self.panel.set_pbp_last_only(self.player, False))
                self.assertEqual(record_bytes(self.panel.document, self.player), before)

    def test_each_toggle_is_one_undo_and_redo(self) -> None:
        original = record_bytes(self.panel.document, self.player)
        self.panel.pbp_last_check.click()
        self.panel.pbp_last_check.click()
        self.panel.pbp_last_check.click()
        self.assertEqual(self.player.record.values["player_type"], 5)
        self.panel.undo()
        self.assertEqual(self.player.record.values["player_type"], 4)
        self.assertFalse(self.panel.pbp_last_check.isChecked())
        self.panel.undo()
        self.assertEqual(self.player.record.values["player_type"], 5)
        self.assertTrue(self.panel.pbp_last_check.isChecked())
        self.panel.undo()
        self.assertEqual(record_bytes(self.panel.document, self.player), original)
        self.assertNotIn((self.player.pool, self.player.index), self.panel._dirty)
        self.panel.redo()
        self.assertEqual(self.player.record.values["player_type"], 5)
        self.assertTrue(self.panel.pbp_last_check.isChecked())

    def test_show_my_changes_lists_it(self) -> None:
        self.panel.pbp_last_check.click()
        self.panel.refresh_diff()
        report = self.panel.report.toPlainText()
        self.assertIn("Player Type: 4 -> 5", report)
        self.assertIn("play-by-play last name only: on", report)

    def test_editing_the_player_type_card_moves_the_box(self) -> None:
        self.panel.cards["player_type"].set_value(5)
        self.panel._card_changed("player_type", 5)
        self.assertTrue(self.panel.pbp_last_check.isChecked())
        self.panel._card_changed("player_type", 0)
        self.assertFalse(self.panel.pbp_last_check.isEnabled())

    def test_the_field_note_no_longer_calls_bit_2_a_name_setting(self) -> None:
        note = rr.FIELD_BY_NAME["player_type"].note
        self.assertNotIn("announce last name only", note)
        self.assertIn("eligib", note)
        self.assertIn("equal to 5", note)


class ClearPhotoTests(_Case):
    def menu_action(self):
        return next(a for a in self.panel.grid_menu().actions() if a.text() == "Clear photo")

    def test_clear_photo_writes_ffff_at_6_and_nothing_else(self) -> None:
        before = record_bytes(self.panel.document, self.player)
        self.assertNotEqual(before[0x06:0x08], b"\xff\xff")
        self.assertTrue(self.panel.clear_photo())
        after = record_bytes(self.panel.document, self.player)
        self.assertEqual(after[0x06:0x08], b"\xff\xff")
        self.assertEqual(self.differing_offsets(before), [i for i in (0x06, 0x07) if before[i] != 0xFF])
        self.assertEqual(self.player.record.values["photo_id"], 65535)

    def test_undo_restores_redo_clears_and_it_is_one_entry(self) -> None:
        before = record_bytes(self.panel.document, self.player)
        self.panel.clear_photo()
        self.panel.undo()
        self.assertEqual(record_bytes(self.panel.document, self.player), before)
        self.assertFalse(self.panel.undo_stack.can_undo())
        self.panel.redo()
        self.assertEqual(self.player.record.values["photo_id"], 65535)

    def test_the_menu_entry_and_the_button_are_off_when_it_is_already_65535(self) -> None:
        self.assertTrue(self.menu_action().isEnabled())
        self.assertTrue(self.panel.clear_photo_button.isEnabled())
        self.panel.clear_photo()
        self.assertFalse(self.menu_action().isEnabled())
        self.assertFalse(self.panel.clear_photo_button.isEnabled())
        self.assertFalse(self.panel.clear_photo())            # nothing to do, no second undo entry
        self.panel.undo()
        self.assertFalse(self.panel.undo_stack.can_undo())

    def test_the_menu_entry_sits_with_the_paste_entries(self) -> None:
        texts = [a.text() for a in self.panel.grid_menu().actions()]
        # b81 finn-r2: "Paste exact copy" now sits right after "Paste photo only", so Clear photo follows that
        self.assertEqual(texts[texts.index("Paste photo only") + 2], "Clear photo")
        self.menu_action().trigger()
        self.assertEqual(self.player.record.values["photo_id"], 65535)

    def test_the_header_then_shows_the_no_photo_picture(self) -> None:
        self.panel.clear_photo()
        self.assertFalse(self.panel.header_photo.isHidden())
        self.assertIn("Photo 65535", self.panel.header_photo.toolTip())
        self.assertIn("No photo", self.panel.header_photo.toolTip())
        expected = self.panel._no_photo_pixmap().toImage()
        self.assertEqual(self.panel.header_photo.pixmap().toImage(), expected)

    def test_show_my_changes_and_the_status_line_say_it(self) -> None:
        self.panel.clear_photo()
        self.assertIn("65535", self.panel.status_label.text())
        self.assertNotIn("Choose an existing Photo ID", self.panel.status_label.text())
        self.panel.refresh_diff()
        self.assertIn("-> 65535", self.panel.report.toPlainText())

    def test_the_bulk_clear_user_photos_is_not_offered(self) -> None:
        texts = [a.text() for a in self.panel.grid_menu().actions()]
        self.assertFalse([t for t in texts if "user photos" in t.lower()])


class PrintTests(_Case):
    def test_the_list_prints_to_a_pdf_without_a_dialog(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "list.pdf"
            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(str(target))
            self.assertTrue(self.panel.print_list(printer))
            data = target.read_bytes()
            self.assertTrue(data.startswith(b"%PDF"))
            self.assertGreater(len(data), 1000)

    def test_it_is_in_the_csv_menu(self) -> None:
        texts = [a.text() for a in self.panel.csv_button.menu().actions()]
        self.assertIn("Print this list…", texts)

    def test_nothing_loaded_prints_nothing(self) -> None:
        empty = RosterEditorPanel()
        try:
            with tempfile.TemporaryDirectory() as folder:
                printer = QPrinter()
                printer.setOutputFormat(QPrinter.PdfFormat)
                printer.setOutputFileName(str(Path(folder) / "none.pdf"))
                self.assertFalse(empty.print_list(printer))
        finally:
            empty.deleteLater()


@unittest.skipUnless(SOFTDRINK_ROSTER_SAVE.is_file(), f"SOFTDRINK roster save absent: {SOFTDRINK_ROSTER_SAVE}")
class SoftdrinkSaveTests(unittest.TestCase):
    def test_both_edits_on_one_named_player_survive_a_signed_copy_and_nothing_else_moves(self) -> None:
        application = _app()
        panel = RosterEditorPanel()
        try:
            self.assertTrue(panel.load_save(SOFTDRINK_ROSTER_SAVE))
            document = panel.document
            source = rr.load_save(SOFTDRINK_ROSTER_SAVE)
            target = next(p for p in panel.visible_players()
                          if p.last and p.first and p.record.player_type_word == 4
                          and p.record.values["photo_id"] != 65535)
            self.assertTrue(panel.select_player(target))
            panel.pbp_last_check.click()
            self.assertTrue(panel.clear_photo())
            panel.refresh_diff()
            report = panel.report.toPlainText()
            self.assertIn("play-by-play last name only: on", report)
            self.assertIn("-> 65535", report)
            with tempfile.TemporaryDirectory() as folder:
                panel.write_copy_to(Path(folder) / "copy.zip")
                back = rr.load_save(Path(folder) / "copy.zip")
                self.assertTrue(back.container.verified, "the written copy is signed")
                twin = back.by_offset[target.offset]
                self.assertEqual((twin.last, twin.first), (target.last, target.first))
                self.assertEqual(twin.record.player_type_word, 5)
                self.assertEqual(twin.record.values["photo_id"], 65535)
                self.assertEqual(len(back.players), len(source.players))
                for was in source.players:
                    if was.offset == target.offset:
                        continue
                    self.assertEqual(
                        bytes(source.body[was.offset: was.offset + rr.PLAYER_SIZE]),
                        bytes(back.body[was.offset: was.offset + rr.PLAYER_SIZE]), f"{was.display} changed")
                mine = bytes(back.body[target.offset: target.offset + rr.PLAYER_SIZE])
                theirs = bytes(source.body[target.offset: target.offset + rr.PLAYER_SIZE])
                self.assertEqual([i for i in range(rr.PLAYER_SIZE) if mine[i] != theirs[i]],
                                 [i for i in (0x06, 0x07, 0x08) if mine[i] != theirs[i]])
                self.assertEqual(mine[0x06:0x09], b"\xff\xff\x05")
        finally:
            panel.deleteLater()
            application.processEvents()


if __name__ == "__main__":
    unittest.main()

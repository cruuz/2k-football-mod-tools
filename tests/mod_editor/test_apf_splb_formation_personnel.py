"""Formation changes follow retail personnel; overrides remain deliberate."""

from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt5.QtWidgets import QApplication, QComboBox, QDialog, QLabel, QListWidget

from mod_editor.apf_studio.playbook_membership_qt import ApfPlaybookMembershipPanel
from mod_editor.core import apf2k8_splb_writer as splb


RETAIL_INDEX = Path(
    "/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A"
)
OUTER = 130


def forged_book(outer: int, pairs: tuple[tuple[int, int], ...]) -> splb.SplbBook:
    """Synthetic SPLB: one tagged play per populated record, then empty slots."""

    body = bytearray(splb.RESOURCE_SIZE)
    body[0x0C:0x10] = b"BLPS"
    name = "Synthetic personnel".encode("utf-16-be")
    body[0x30:0x30 + len(name)] = name
    mask = 0
    for index in range(splb.RECORD_COUNT):
        base = splb.RECORD_BASE + index * splb.RECORD_STRIDE
        for slot in range(splb.ENTRY_CAPACITY):
            struct.pack_into(">H", body, base + 2 * slot, splb.FILLER)
        # An unused trailer must never contribute a retail pairing.
        formation, category = pairs[index] if index < len(pairs) else (162, 27)
        word_a = (formation << 24) | (category << 17) | 0x9200
        struct.pack_into(">2I", body, base + splb.TRAILER_OFFSET, word_a, 1 << category)
        if index < len(pairs):
            struct.pack_into(">H", body, base, (2 << 13) | index)
            mask |= 1 << category
    struct.pack_into(">I", body, splb.BOOK_CATEGORY_MASK_OFFSET, mask)
    return splb.parse_book(bytes(body), outer)


def assert_quads_receipt(test: unittest.TestCase, book, changes, record_index=0):
    test.assertEqual(changes, (splb.TrailerReplace(book.outer_index, record_index, 69, 8),))
    compiled = splb.compile_book(book, changes)
    splb.verify_book(book.body, compiled.replacement, changes)
    record = splb.parse_book(compiled.replacement, book.outer_index).records[record_index]
    test.assertEqual((record.formation_index, record.category_index), (69, 8))
    offset = splb.RECORD_BASE + record_index * splb.RECORD_STRIDE + splb.TRAILER_OFFSET
    before_a, before_b = struct.unpack_from(">2I", book.body, offset)
    after_a, after_b = struct.unpack_from(">2I", compiled.replacement, offset)
    test.assertEqual((after_a >> 17) & 0x7F, 8)
    test.assertEqual(after_a & 0x1FFFF, before_a & 0x1FFFF)
    test.assertEqual(after_b, before_b | (1 << 8))
    test.assertTrue(after_b & 1, "The old Jacks membership must remain")
    before_mask = struct.unpack_from(">I", book.body, 0x7E04)[0]
    after_mask = struct.unpack_from(">I", compiled.replacement, 0x7E04)[0]
    test.assertEqual(after_mask, before_mask | (1 << 8))
    test.assertTrue(after_mask & 1, "The old book-mask bit must remain")
    allowed = set(range(offset, offset + 8)) | set(range(0x7E04, 0x7E08))
    changed = {i for i, (a, b) in enumerate(zip(book.body, compiled.replacement)) if a != b}
    test.assertTrue(changed)
    test.assertLessEqual(changed, allowed)
    receipt = compiled.report["records_trailer_replaced"][0]
    test.assertEqual((receipt["formation_after"], receipt["category_after"]), (69, 8))
    test.assertFalse(compiled.report["claims"]["runtime_lineup_after_replace_proved"])


class RetailTableFixtureTests(unittest.TestCase):
    def test_two_books_count_records_order_ties_and_ignore_empty_slots(self):
        books = {
            130: forged_book(130, ((9, 0), (69, 8), (72, 5), (120, 6))),
            134: forged_book(134, ((9, 0), (69, 8), (72, 2), (72, 2), (120, 3))),
        }
        with tempfile.TemporaryDirectory() as directory:
            index = Path(directory) / "0A"
            with patch.object(splb, "STOCK_BOOKS", {130: "First", 134: "Second"}), patch.object(
                splb, "read_book", side_effect=lambda _index, outer: books[outer]
            ) as reader:
                table = splb.retail_formation_packages(index)
                self.assertEqual(table, {
                    9: ((0, 2),), 69: ((8, 2),),
                    72: ((2, 2), (5, 1)), 120: ((3, 1), (6, 1)),
                })
                self.assertEqual(splb.natural_package(72, table), 2)
                self.assertEqual(splb.natural_package(120, table), 3)
                self.assertIsNone(splb.natural_package(162, table))
                self.assertIsNone(splb.natural_package(9, {}))
                # The selector honors counts/ties even with an unordered input.
                self.assertEqual(splb.natural_package(120, {120: ((6, 1), (3, 1))}), 3)
                table.pop(9)
                again = splb.retail_formation_packages(str(index))
                self.assertIn(9, again, "Callers must not poison cached defaults")
                self.assertEqual(reader.call_args_list, [call(index, 130), call(index, 134)])
                splb.retail_formation_packages(Path(directory) / "another" / "0A")
                self.assertEqual(reader.call_count, 4, "Cache must be per source index")


class RetailGroundTruthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not RETAIL_INDEX.is_file():
            raise unittest.SkipTest(f"Retail APF 0A absent: {RETAIL_INDEX}")
        cls.table = splb.retail_formation_packages(RETAIL_INDEX)

    def test_all_fifteen_books_rederive_127_formations_and_209_records(self):
        self.assertEqual(len(splb.STOCK_BOOKS), 15)
        self.assertEqual(len(self.table), 127)
        self.assertEqual(sum(n for pairs in self.table.values() for _, n in pairs), 209)
        self.assertEqual(sum(len(pairs) == 1 for pairs in self.table.values()), 124)
        self.assertEqual({f: p for f, p in self.table.items() if len(p) > 1}, {
            72: ((2, 2), (5, 1)), 78: ((2, 2), (5, 1)), 120: ((3, 2), (6, 2)),
        })
        self.assertEqual(self.table[9], ((0, 4),))
        self.assertEqual(self.table[69], ((8, 3),))
        self.assertEqual(splb.natural_package(9, self.table), 0)
        self.assertEqual(splb.natural_package(69, self.table), 8)
        self.assertEqual(splb.natural_package(67, self.table), 2)
        self.assertEqual(splb.natural_package(126, self.table), 8)
        self.assertEqual(splb.natural_package(133, self.table), 7)

    def test_master_roles_confirm_jacks_and_flush_personnel(self):
        from mod_editor.apf_studio.session import ApfSession
        from mod_editor.core.apf2k8_playbook_route_writer import read_master_play_body

        body = read_master_play_body(RETAIL_INDEX)
        categories = ApfSession.master_categories(SimpleNamespace(_master_play_body=lambda: body))
        self.assertEqual(len(categories), 28)
        for index, name, expected in ((0, "Jacks", (2, 3, 0)), (8, "Flush", (1, 0, 4))):
            category = categories[index]
            self.assertEqual(category["name"], name)
            roles = category["roles"]
            self.assertEqual((roles.count(10) + roles.count(11), roles.count(8), roles.count(9)), expected)

    def test_retail_jacks_to_quads_compiles_and_reparses_with_flush(self):
        book = splb.read_book(RETAIL_INDEX, OUTER)
        record = next(r for r in book.records if r.populated and r.formation_index == 9)
        changes = (splb.TrailerReplace(OUTER, record.record_index, 69,
                                     splb.natural_package(69, self.table)),)
        assert_quads_receipt(self, book, changes, record.record_index)


class DialogPersonnelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.stored = ()
        self.book = forged_book(OUTER, ((9, 0), (10, 0)))
        self.formations = {
            9: "I Jacks", 10: "I Jacks Flip", 69: "Quads", 72: "Tight Triple",
            120: "Gun: Split Spread", 133: "Gun: Straight", 162: "Unused formation",
        }
        # Synthetic roles and pairings. In particular 133 -> 8 proves Add does
        # not simply retain its hard-coded package 7 when the table differs.
        self.table = {9: ((0, 4),), 69: ((8, 3),), 72: ((2, 2), (5, 1)),
                      120: ((3, 2), (6, 2)), 133: ((8, 1),)}
        self.categories = tuple(
            {"index": i, "name": name, "roles": (1, 2, 3, 4, 5, 6) + roles}
            for i, name, roles in (
                (0, "Jacks", (10, 11, 8, 8, 8)), (2, "Ace", (10, 8, 8, 9, 9)),
                (3, "Pro Set", (10, 11, 8, 9, 9)), (5, "Kings", (10, 8, 9, 9, 9)),
                (6, "Queens", (10, 11, 9, 9, 9)), (7, "Straight", (8, 9, 9, 9, 9)),
                (8, "Flush", (10, 9, 9, 9, 9)),
            )
        )

        def stage(changes, **_kwargs):
            self.stored = tuple(changes)

        self.facade = SimpleNamespace(
            source_ready=True, source=SimpleNamespace(index_0a=Path("0A")),
            stage_splb_membership=stage, staged_splb_changes=lambda: self.stored,
            retail_formation_packages=Mock(return_value=self.table),
            master_categories=Mock(return_value=self.categories),
        )
        master = {"plays": [{"name": "Play 0"}, {"name": "Play 1"}], "formations": [
            {"index": i, "name": name} for i, name in self.formations.items()
        ]}
        with patch.object(splb, "read_book", return_value=self.book), patch(
            "playbook_inventory.parse_apf", return_value=[master]
        ):
            self.panel = ApfPlaybookMembershipPanel(
                self.facade,
                lambda _title, operation, done, _cancel: done(operation(lambda *_args: None)),
            )
        self.facade.master_categories.assert_called_once_with()
        self.facade.retail_formation_packages.assert_called_once_with()
        self.facade.master_categories.side_effect = AssertionError("Dialog reread MASTER")
        self.facade.retail_formation_packages.side_effect = AssertionError("Dialog reread SPLBs")

    def tearDown(self):
        self.panel.close()
        self.panel.deleteLater()
        self.application.processEvents()

    def accept_dialog(self, action):
        def execute(dialog):
            combos = {c.accessibleName(): c for c in dialog.findChildren(QComboBox)}
            hint = dialog.findChild(QLabel, "retailPairingHint")
            warning = dialog.findChild(QLabel, "retailPairingWarning")
            dialog.show()
            self.application.processEvents()
            try:
                action(combos["MASTER formation"], combos["Personnel package"], hint, warning, dialog)
                return QDialog.Accepted
            finally:
                dialog.hide()
                dialog.deleteLater()
        return patch.object(QDialog, "exec", execute)

    def test_formation_only_change_stages_flush_and_compiles_honest_receipt(self):
        def choose(formation, package, hint, warning, _dialog):
            self.assertEqual((formation.currentData(), package.currentData()), (9, 0))
            formation.setCurrentIndex(formation.findData(69))
            self.assertEqual(package.currentData(), 8)
            self.assertEqual(hint.text(), "Retail pairs Quads with Flush (1 RB, 0 TE, 4 WR)")
            self.assertFalse(warning.isVisible())

        with self.accept_dialog(choose), patch.object(
            self.panel, "stage_trailer_replace", wraps=self.panel.stage_trailer_replace
        ) as stage:
            self.panel._change_trailer()
        stage.assert_called_once_with(0, 69, 8)
        assert_quads_receipt(self, self.book, self.stored)

    def test_manual_unpaired_override_survives_accept_and_reopen(self):
        def choose(formation, package, _hint, warning, _dialog):
            formation.setCurrentIndex(formation.findData(69))
            package.setCurrentIndex(package.findData(0))
            self.assertTrue(warning.isVisible())
            self.assertEqual(warning.text(),
                "Retail never lines Quads up with Jacks personnel; the CPU will field 2 RB, 3 TE, 0 WR")

        with self.accept_dialog(choose):
            self.panel._change_trailer()
        self.assertEqual(self.stored, (splb.TrailerReplace(OUTER, 0, 69, 0),))

        def reopen(formation, package, _hint, warning, _dialog):
            self.assertEqual((formation.currentData(), package.currentData()), (69, 0))
            self.assertTrue(warning.isVisible())

        with self.accept_dialog(reopen):
            self.panel._change_trailer()
        self.assertEqual(self.stored, (splb.TrailerReplace(OUTER, 0, 69, 0),))

    def test_alternatives_show_counts_accept_override_and_break_ties(self):
        def choose(formation, package, hint, warning, _dialog):
            formation.setCurrentIndex(formation.findData(72))
            self.assertEqual(package.currentData(), 2)
            self.assertIn("Ace (1 RB, 2 TE, 2 WR; 2 retail records)", hint.text())
            self.assertIn("Kings (1 RB, 1 TE, 3 WR; 1 retail record)", hint.text())
            package.setCurrentIndex(package.findData(5))
            self.assertEqual(package.currentData(), 5)
            self.assertFalse(warning.isVisible())
            formation.setCurrentIndex(formation.findData(120))
            self.assertEqual(package.currentData(), 3)
            self.assertIn("Pro Set", hint.text())
            self.assertIn("Queens", hint.text())

        with self.accept_dialog(choose):
            self.assertEqual(self.panel._trailer_dialog("Test", (9, 0), False), (120, 3, ()))

    def test_unknown_formation_keeps_hand_picked_package_and_clears_warning(self):
        def choose(formation, package, hint, warning, _dialog):
            formation.setCurrentIndex(formation.findData(69))
            package.setCurrentIndex(package.findData(0))
            self.assertTrue(warning.isVisible())
            formation.setCurrentIndex(formation.findData(162))
            self.assertEqual(package.currentData(), 0)
            self.assertIn("No retail pairing is known for Unused formation", hint.text())
            self.assertFalse(warning.isVisible())
            formation.setCurrentIndex(formation.findData(69))
            self.assertEqual(package.currentData(), 8)

        with self.accept_dialog(choose):
            self.panel._change_trailer()

    def test_add_resolves_initial_133_and_stages_its_natural_package(self):
        def choose(formation, package, hint, warning, dialog):
            self.assertEqual((formation.currentData(), package.currentData()), (133, 8))
            self.assertIn("Retail pairs Gun: Straight with Flush", hint.text())
            self.assertFalse(warning.isVisible())
            dialog.findChild(QListWidget).item(0).setSelected(True)

        with self.accept_dialog(choose):
            self.panel._add_record()
        self.assertIn(splb.TrailerReplace(OUTER, 2, 133, 8), self.stored)
        self.assertIn(splb.MembershipChange(OUTER, 2, 0, True), self.stored)

    def test_cancel_does_not_stage_the_automatic_change(self):
        def execute(dialog):
            formation = next(c for c in dialog.findChildren(QComboBox)
                             if c.accessibleName() == "MASTER formation")
            formation.setCurrentIndex(formation.findData(69))
            dialog.deleteLater()
            return QDialog.Rejected

        with patch.object(QDialog, "exec", execute):
            self.panel._change_trailer()
        self.assertEqual(self.stored, ())

    def test_facade_without_optional_readers_keeps_safe_defaults(self):
        del self.facade.master_categories
        del self.facade.retail_formation_packages
        with patch.object(splb, "read_book", return_value=self.book), patch(
            "playbook_inventory.parse_apf", return_value=[{
                "plays": [], "formations": [{"index": 133, "name": "Gun: Straight"}]
            }]
        ):
            self.panel._load_book()
        self.assertEqual(self.panel._formation_packages, {})
        self.assertEqual(self.panel._categories, ())
        with self.accept_dialog(lambda _f, p, h, w, _d: (
            self.assertEqual(p.currentData(), 7),
            self.assertIn("No retail pairing", h.text()), self.assertFalse(w.isVisible())
        )):
            self.assertEqual(self.panel._trailer_dialog("Add", (133, 7), True), (133, 7, ()))


if __name__ == "__main__":
    unittest.main()

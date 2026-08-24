"""Adding more than one formation to a stock CPU book in a single session.

Urianus (2026-08-22): "Same for the fixed 'Add Formation' in beta 50, but why
doesn't it let me add more than 1?"  The panel used to offer exactly one empty
slot -- ``max(populated) + 1`` -- and refused everything once that slot was
staged.  The writer itself never had that limit: several trailer repoints and
play additions compile and verify in one build.  These tests pin both halves:
the panel now walks the free slots one per add, and the writer ships any
number of added records in one patched volume, with the receipt naming the
records a shared play can still resolve to (per-entry resolution, 0x84A89EA8)
and the personnel rows the book promises (mask at +0x7E04, row search
0x84A8B438) -- which row the CPU requests when remains runtime-unproved.
"""

from __future__ import annotations

import os
from pathlib import Path
import struct
import unittest
from unittest import mock


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mod_editor.core import apf2k8_splb_writer as splb  # noqa: E402
from mod_editor.core.errors import ValidationError  # noqa: E402


OUTER = 369          # O-SinglebackAce in the retail naming; forged bytes here
FIRST_EMPTY = 4      # records 0..3 are populated in the forged book


def _book_bytes(populate_last: bool = False) -> bytes:
    """A proved-shape book with four populated records (0..3).

    Every populated record obeys the retail tag rule (min(4, plays) slots in
    the 1, 0, 2, 3 spend order) so any panel preview can re-derive it.
    ``populate_last`` also fills record 175 to prove the slot walk has an end.
    """

    body = bytearray(splb.RESOURCE_SIZE)
    body[0x0C:0x10] = b"BLPS"
    encoded = "O-SinglebackAce".encode("utf-16-be")
    body[0x30 : 0x30 + len(encoded)] = encoded
    for index in range(splb.RECORD_COUNT):
        base = splb.RECORD_BASE + index * splb.RECORD_STRIDE
        for slot in range(splb.ENTRY_CAPACITY):
            struct.pack_into(">H", body, base + slot * 2, splb.FILLER)

    def populate(record_index: int, formation: int, category: int, plays: list[int]):
        base = splb.RECORD_BASE + record_index * splb.RECORD_STRIDE
        tags = {0: 1, 1: 0, 2: 2, 3: 3}
        for slot, play in enumerate(plays):
            y = tags.get(slot, splb.UNTAGGED_Y)
            struct.pack_into(">H", body, base + slot * 2, (2 << 13) | (y << 10) | play)
        word_a = (formation << 24) | (category << 17)
        struct.pack_into(">I", body, base + splb.TRAILER_OFFSET, word_a)
        struct.pack_into(">I", body, base + splb.TRAILER_OFFSET + 4, 1 << category)
        mask_at = splb.BOOK_CATEGORY_MASK_OFFSET
        mask = struct.unpack_from(">I", body, mask_at)[0]
        struct.pack_into(">I", body, mask_at, mask | (1 << category))

    populate(0, 62, 2, [40, 41, 42, 43, 44, 45])
    populate(1, 63, 2, [50, 51, 52, 53, 54])
    populate(2, 64, 3, [60, 61, 62, 63, 64])
    populate(3, 65, 3, [70, 71, 72, 73, 74])
    if populate_last:
        populate(splb.RECORD_COUNT - 1, 66, 2, [80, 81, 82, 83, 84])
    return bytes(body)


def _addition(record_index: int, formation: int, category: int, plays: tuple[int, ...]):
    """The change set the panel stages for one added formation."""

    return [
        splb.MembershipChange(OUTER, record_index, play, True) for play in plays
    ] + [splb.TrailerReplace(OUTER, record_index, formation, category)]


class MultipleAdditionWriterTests(unittest.TestCase):
    """The writer ships any number of added records in one patched book."""

    def setUp(self) -> None:
        self.body = _book_bytes()
        self.book = splb.parse_book(self.body, OUTER)

    def test_two_additions_compile_and_verify_in_one_build(self) -> None:
        changes = _addition(4, 133, 7, (300, 301, 302)) + _addition(5, 134, 5, (310, 311))
        compiled = splb.compile_book(self.book, changes)
        splb.verify_book(self.body, compiled.replacement, changes)
        reparsed = splb.parse_book(compiled.replacement, OUTER)
        self.assertEqual(
            [entry.play_index for entry in reparsed.records[4].entries],
            [300, 301, 302],
        )
        self.assertEqual(
            [entry.play_index for entry in reparsed.records[5].entries],
            [310, 311],
        )
        self.assertEqual(reparsed.records[4].formation_index, 133)
        self.assertEqual(reparsed.records[4].category_index, 7)
        self.assertEqual(reparsed.records[5].formation_index, 134)
        self.assertEqual(reparsed.records[5].category_index, 5)
        # Untouched records and trailers stay byte-exact.
        for index in (0, 1, 2, 3):
            self.assertEqual(
                reparsed.records[index].entries, self.book.records[index].entries
            )
            self.assertEqual(
                reparsed.records[index].trailer, self.book.records[index].trailer
            )

    def test_two_additions_or_both_mask_bits_into_the_book_supply(self) -> None:
        changes = _addition(4, 133, 7, (300,)) + _addition(5, 134, 9, (310,))
        compiled = splb.compile_book(self.book, changes)
        splb.verify_book(self.body, compiled.replacement, changes)
        rows_before = splb.book_category_rows(self.body)
        rows_after = splb.book_category_rows(compiled.replacement)
        self.assertEqual(rows_before, (2, 3))
        self.assertEqual(rows_after, (2, 3, 7, 9))
        self.assertEqual(compiled.report["book_category_rows_before"], [2, 3])
        self.assertEqual(compiled.report["book_category_rows_after"], [2, 3, 7, 9])

    def test_two_additions_under_one_package_gain_one_mask_bit(self) -> None:
        changes = _addition(4, 133, 7, (300,)) + _addition(5, 134, 7, (310,))
        compiled = splb.compile_book(self.book, changes)
        splb.verify_book(self.body, compiled.replacement, changes)
        mask = struct.unpack_from(
            ">I", compiled.replacement, splb.BOOK_CATEGORY_MASK_OFFSET
        )[0]
        self.assertEqual(
            mask,
            struct.unpack_from(">I", self.body, splb.BOOK_CATEGORY_MASK_OFFSET)[0]
            | (1 << 7),
        )

    def test_the_receipt_flags_records_whose_plays_resolve_elsewhere(self) -> None:
        # Plays 40 and 41 already live in record 0; 302 is unique to the add.
        changes = _addition(4, 133, 7, (40, 41, 302))
        compiled = splb.compile_book(self.book, changes)
        sharing = compiled.report["trailer_record_play_sharing"]
        self.assertEqual(len(sharing), 1)
        self.assertEqual(sharing[0]["record_index"], 4)
        self.assertEqual(sharing[0]["shared_with_records"], [0])
        self.assertEqual(sharing[0]["shared_play_count"], 2)
        claims = compiled.report["claims"]
        self.assertIs(claims["personnel_row_lookup_static_proved"], True)
        self.assertIs(claims["personnel_row_request_policy_proved"], False)
        self.assertIs(
            claims["record_resolution_per_stored_entry_static_proved"], True
        )

    def test_an_addition_with_unique_plays_reports_no_sharing(self) -> None:
        changes = _addition(4, 133, 7, (300, 301))
        compiled = splb.compile_book(self.book, changes)
        sharing = compiled.report["trailer_record_play_sharing"]
        self.assertEqual(sharing[0]["shared_with_records"], [])
        self.assertEqual(sharing[0]["shared_play_count"], 0)

    def test_sharing_ignores_the_record_being_added(self) -> None:
        sharing = splb.record_play_sharing(self.book, 0)
        self.assertNotIn(0, sharing)
        # Record 0 and 1 share no plays; records 2 and 3 share none either.
        self.assertEqual(sharing, {})


class PanelAddFlowTests(unittest.TestCase):
    """The panel walks the free slots, one per add, instead of stopping at one."""

    @classmethod
    def setUpClass(cls) -> None:
        from PyQt5.QtWidgets import QApplication

        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        from types import SimpleNamespace

        from mod_editor.apf_studio.playbook_membership_qt import (
            ApfPlaybookMembershipPanel,
        )

        self.stored: tuple = ()

        def stage(changes, **_kwargs) -> int:
            self.stored = tuple(changes)
            return len(self.stored)

        self.facade = SimpleNamespace(
            source_ready=True,
            source=SimpleNamespace(index_0a=Path("0A")),
            stage_splb_membership=stage,
            staged_splb_changes=lambda: self.stored,
            staged_splb_book=lambda: next(
                iter({c.outer_index for c in self.stored}), None
            ),
        )
        self.panel = ApfPlaybookMembershipPanel(self.facade, lambda *_a: None)
        self.panel._book = splb.parse_book(_book_bytes(), OUTER)
        self.panel._plays = [f"Play {index}" for index in range(586)]
        self.panel._formations = {
            62: "Ace",
            63: "Ace Flip",
            64: "Slot",
            65: "Goal",
            133: "Gun: Straight",
            134: "Gun: Base Open",
        }
        self.panel._refresh_formations()

    def tearDown(self) -> None:
        self.panel.deleteLater()

    def test_the_first_free_slot_appends_after_the_populated_run(self) -> None:
        self.assertEqual(self.panel._first_empty_record(), FIRST_EMPTY)

    def test_staging_an_add_moves_the_next_add_to_the_next_slot(self) -> None:
        self.panel.stage_record_addition(FIRST_EMPTY, 133, 7, (300,))
        self.assertEqual(self.panel._first_empty_record(), FIRST_EMPTY + 1)
        self.panel.stage_record_addition(FIRST_EMPTY + 1, 134, 5, (310,))
        self.assertEqual(self.panel._first_empty_record(), FIRST_EMPTY + 2)
        trailers = [
            change
            for change in self.panel.staged_changes()
            if isinstance(change, splb.TrailerReplace)
        ]
        self.assertEqual(
            sorted(change.record_index for change in trailers),
            [FIRST_EMPTY, FIRST_EMPTY + 1],
        )

    def test_the_add_button_flow_accepts_a_second_formation(self) -> None:
        """Urianus's exact complaint: the second add used to be refused."""

        infos: list[str] = []
        with mock.patch(
            "mod_editor.apf_studio.playbook_membership_qt.QMessageBox.information",
            side_effect=lambda _parent, title, text: infos.append(title),
        ):
            with mock.patch.object(
                self.panel, "_trailer_dialog", return_value=(133, 7, (300,))
            ):
                self.panel._add_record()
                self.panel._add_record()
        self.assertEqual(infos, [])
        self.assertEqual(
            self.panel._staged_trailers,
            {FIRST_EMPTY: (133, 7), FIRST_EMPTY + 1: (133, 7)},
        )
        self.assertIn(FIRST_EMPTY, self.panel._staged)
        self.assertIn(FIRST_EMPTY + 1, self.panel._staged)

    def test_the_third_add_uses_the_third_slot(self) -> None:
        with mock.patch.object(
            self.panel, "_trailer_dialog", return_value=(133, 7, (300,))
        ):
            for _ in range(3):
                self.panel._add_record()
        self.assertEqual(
            sorted(self.panel._staged_trailers),
            [FIRST_EMPTY, FIRST_EMPTY + 1, FIRST_EMPTY + 2],
        )

    def test_an_already_staged_slot_is_refused_not_overwritten(self) -> None:
        self.panel.stage_record_addition(FIRST_EMPTY, 133, 7, (300,))
        with self.assertRaisesRegex(ValidationError, "already staged"):
            self.panel.stage_record_addition(FIRST_EMPTY, 134, 5, (310,))
        self.assertEqual(self.panel._staged_trailers[FIRST_EMPTY], (133, 7))
        self.assertEqual(self.panel._staged[FIRST_EMPTY], {300: True})

    def test_several_staged_additions_round_trip_through_the_project(self) -> None:
        self.panel.stage_record_addition(FIRST_EMPTY, 133, 7, (300, 301))
        self.panel.stage_record_addition(FIRST_EMPTY + 1, 134, 5, (310,))
        saved = self.panel.staged_changes()
        self.panel._clear_staged()
        self.assertEqual(self.panel.staged_changes(), ())
        self.panel._restore_from_project()
        self.assertEqual(self.panel.staged_changes(), saved)
        self.assertEqual(self.panel._first_empty_record(), FIRST_EMPTY + 2)

    def test_the_walk_ends_at_the_last_record_slot(self) -> None:
        # Record 175 populated: the append run starts past the array's end.
        self.panel._book = splb.parse_book(_book_bytes(populate_last=True), OUTER)
        self.assertIsNone(self.panel._first_empty_record())

    def test_the_walk_ends_when_every_free_slot_is_staged(self) -> None:
        for slot in range(FIRST_EMPTY, splb.RECORD_COUNT):
            self.panel._staged_trailers[slot] = (133, 7)
        self.assertIsNone(self.panel._first_empty_record())
        self.panel._refresh_actions()
        reason = str(self.panel.add_record_button.property("disableReason"))
        self.assertIn("already staged", reason)


if __name__ == "__main__":
    unittest.main()

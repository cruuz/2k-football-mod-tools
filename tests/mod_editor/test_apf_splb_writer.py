"""Editing APF 2K8's stock CPU playbooks.

These are the stock playbook resources the game ships. A roster save's 36
offensive and 33 defensive playbook records are only labels -- they hold a
name, a type and a side and no content pointer -- and they resolve to seven
offensive and four defensive real books, which is why reassigning one so often
changed nothing. The stored membership is fifteen on-disc ``SPLB`` resources,
and this is the writer for them. Runtime CPU consumption remains unproved.

The layout is proved; two trailer fields and both tail regions are not. This
writer is offerable anyway because it never touches them, and the tests below
are mostly about proving that it never does.
"""

from __future__ import annotations

import os
import struct
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mod_editor.core import apf2k8_splb_writer as splb  # noqa: E402
from mod_editor.core.errors import ValidationError  # noqa: E402


def _synthetic_book(outer_index: int = 943, name: str = "O-ZoneBlock") -> bytes:
    """A minimal resource with the proved shape and two populated records."""

    body = bytearray(splb.RESOURCE_SIZE)
    body[0x0C:0x10] = b"BLPS"
    encoded = name.encode("utf-16-be")
    body[0x30 : 0x30 + len(encoded)] = encoded
    for index in range(splb.RECORD_COUNT):
        base = splb.RECORD_BASE + index * splb.RECORD_STRIDE
        for slot in range(splb.ENTRY_CAPACITY):
            struct.pack_into(">H", body, base + slot * 2, splb.FILLER)
        # The neutral trailer the game itself writes into unused records.
        struct.pack_into(">Q", body, base + splb.TRAILER_OFFSET, 0x0000920000000000)

    def populate(record_index: int, formation: int, entries: list[tuple[int, int, int]]):
        base = splb.RECORD_BASE + record_index * splb.RECORD_STRIDE
        for slot, (x, y, play) in enumerate(entries):
            struct.pack_into(">H", body, base + slot * 2, (x << 13) | (y << 10) | play)
        word_a = (formation << 24) | (3 << 17) | (2 << 14) | (2 << 11) | (2 << 8)
        struct.pack_into(">I", body, base + splb.TRAILER_OFFSET, word_a)
        struct.pack_into(">I", body, base + splb.TRAILER_OFFSET + 4, 1 << 3)

    # One tagged slot 1 plus tags 0/2/3, then untagged plays -- the shape every
    # populated retail record has.
    populate(0, 62, [(2, 1, 10), (2, 0, 11), (2, 2, 12), (2, 3, 13),
                     (2, 4, 20), (2, 4, 21), (3, 4, 22)])
    populate(1, 63, [(2, 1, 30), (2, 4, 31)])
    return bytes(body)


class ParseTests(unittest.TestCase):
    def test_a_book_decodes_to_records_entries_and_formations(self) -> None:
        book = splb.parse_book(_synthetic_book(), 943)
        self.assertEqual(book.name, "O-ZoneBlock")
        self.assertEqual(len(book.records), splb.RECORD_COUNT)
        populated = [r for r in book.records if r.populated]
        self.assertEqual(len(populated), 2)
        first = populated[0]
        self.assertEqual(first.formation_index, 62)
        self.assertEqual([e.play_index for e in first.entries],
                         [10, 11, 12, 13, 20, 21, 22])
        self.assertEqual([e.y for e in first.entries], [1, 0, 2, 3, 4, 4, 4])

    def test_a_wrong_size_or_missing_magic_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            splb.parse_book(bytes(splb.RESOURCE_SIZE - 1), 943)
        broken = bytearray(_synthetic_book())
        broken[0x0C:0x10] = b"XXXX"
        with self.assertRaises(ValidationError):
            splb.parse_book(bytes(broken), 943)

    def test_an_entry_after_the_terminator_is_refused(self) -> None:
        """Entries are a contiguous prefix in every retail record; enforce it."""

        broken = bytearray(_synthetic_book())
        base = splb.RECORD_BASE
        struct.pack_into(">H", broken, base + 20 * 2, (2 << 13) | (4 << 10) | 99)
        with self.assertRaises(ValidationError):
            splb.parse_book(bytes(broken), 943)


class CompileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.body = _synthetic_book()
        self.book = splb.parse_book(self.body, 943)

    def test_adding_a_play_appends_an_untagged_entry(self) -> None:
        change = splb.MembershipChange(943, 0, 400, True)
        compiled = splb.compile_book(self.book, [change])
        after = splb.parse_book(compiled.replacement, 943).records[0]
        self.assertIn(400, [e.play_index for e in after.entries])
        added = next(e for e in after.entries if e.play_index == 400)
        self.assertEqual(added.y, splb.UNTAGGED_Y)
        # X is constant per (book, play); with no precedent it takes the
        # neutral value the game writes into unused records.
        self.assertEqual(added.x, splb.NEUTRAL_X)

    def test_an_added_play_reuses_its_x_from_elsewhere_in_the_book(self) -> None:
        change = splb.MembershipChange(943, 1, 22, True)   # x=3 in record 0
        compiled = splb.compile_book(self.book, [change])
        after = splb.parse_book(compiled.replacement, 943).records[1]
        added = next(e for e in after.entries if e.play_index == 22)
        self.assertEqual(added.x, 3)

    def test_removing_an_untagged_play_compacts_the_prefix(self) -> None:
        change = splb.MembershipChange(943, 0, 21, False)
        compiled = splb.compile_book(self.book, [change])
        after = splb.parse_book(compiled.replacement, 943).records[0]
        self.assertNotIn(21, [e.play_index for e in after.entries])
        self.assertEqual(len(after.entries), 6)
        # Still a contiguous prefix: reparsing would have raised otherwise.

    def test_removing_a_tagged_slot_is_refused(self) -> None:
        for play_index in (10, 11, 12, 13):
            with self.subTest(play=play_index):
                with self.assertRaisesRegex(ValidationError, "tagged slot"):
                    splb.compile_book(
                        self.book, [splb.MembershipChange(943, 0, play_index, False)]
                    )

    def test_a_redundant_change_is_a_no_op(self) -> None:
        compiled = splb.compile_book(
            self.book, [splb.MembershipChange(943, 0, 20, True)]
        )
        self.assertEqual(compiled.replacement, self.body)

    def test_contradicting_changes_are_refused(self) -> None:
        with self.assertRaises(ValidationError):
            splb.compile_book(
                self.book,
                [
                    splb.MembershipChange(943, 0, 400, True),
                    splb.MembershipChange(943, 0, 400, False),
                ],
            )

    def test_two_books_in_one_request_are_refused(self) -> None:
        with self.assertRaises(ValidationError):
            splb.compile_book(
                self.book,
                [
                    splb.MembershipChange(943, 0, 400, True),
                    splb.MembershipChange(618, 0, 400, True),
                ],
            )

    def test_a_play_outside_master_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            splb.compile_book(self.book, [splb.MembershipChange(943, 0, 586, True)])

    def test_overflowing_the_84_slot_capacity_is_refused(self) -> None:
        changes = [
            splb.MembershipChange(943, 1, play, True) for play in range(100, 200)
        ]
        with self.assertRaisesRegex(ValidationError, "maximum"):
            splb.compile_book(self.book, changes)


class VerifierTests(unittest.TestCase):
    """The verifier is the safety net, so it is tested against forged output."""

    def setUp(self) -> None:
        self.body = _synthetic_book()
        self.book = splb.parse_book(self.body, 943)
        self.change = splb.MembershipChange(943, 0, 400, True)

    def test_the_honest_edit_verifies(self) -> None:
        compiled = splb.compile_book(self.book, [self.change])
        report = splb.verify_book(self.body, compiled.replacement, [self.change])
        self.assertEqual(report["changed_records"], [0])
        self.assertGreater(report["changed_byte_count"], 0)

    def test_a_touched_trailer_is_refused(self) -> None:
        compiled = splb.compile_book(self.book, [self.change])
        forged = bytearray(compiled.replacement)
        forged[splb.RECORD_BASE + splb.TRAILER_OFFSET] ^= 0x01
        with self.assertRaises(ValidationError):
            splb.verify_book(self.body, bytes(forged), [self.change])

    def test_a_touched_untouched_record_is_refused(self) -> None:
        compiled = splb.compile_book(self.book, [self.change])
        forged = bytearray(compiled.replacement)
        other = splb.RECORD_BASE + splb.RECORD_STRIDE
        struct.pack_into(">H", forged, other + 4, (2 << 13) | (4 << 10) | 77)
        with self.assertRaises(ValidationError):
            splb.verify_book(self.body, bytes(forged), [self.change])

    def test_a_touched_tail_region_is_refused(self) -> None:
        """0x7998 and 0x7D98 are unmapped; nothing may write them."""

        compiled = splb.compile_book(self.book, [self.change])
        for offset in (0x7998, 0x7D98):
            with self.subTest(offset=hex(offset)):
                forged = bytearray(compiled.replacement)
                forged[offset] ^= 0xFF
                with self.assertRaises(ValidationError):
                    splb.verify_book(self.body, bytes(forged), [self.change])

    def test_a_result_that_does_not_say_what_was_asked_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            splb.verify_book(self.body, self.body, [self.change])


class LayoutPinTests(unittest.TestCase):
    def test_the_proved_layout_constants_are_pinned(self) -> None:
        self.assertEqual(splb.RECORD_BASE, 0x0070)
        self.assertEqual(splb.RECORD_STRIDE, 176)
        self.assertEqual(splb.RECORD_COUNT, 176)
        self.assertEqual(splb.ARRAY_END, 0x7970)
        self.assertEqual(splb.ENTRY_CAPACITY, 84)
        self.assertEqual(splb.TRAILER_OFFSET, 0xA8)
        self.assertEqual(splb.FILLER, 0x13FF)
        self.assertEqual(splb.RESOURCE_SIZE, 32_288)
        self.assertEqual(len(splb.STOCK_BOOKS), 15)
        named = [name for name in splb.STOCK_BOOKS.values() if name]
        self.assertEqual(len(named), 11)
        self.assertEqual(sum(1 for n in named if n.startswith("O-")), 7)
        self.assertEqual(sum(1 for n in named if n.startswith("X-")), 4)

    def test_the_filler_is_just_an_out_of_range_play_index(self) -> None:
        self.assertEqual(splb.FILLER & splb.PLAY_MASK, 1023)
        self.assertGreater(splb.FILLER & splb.PLAY_MASK, 585)

    def test_flip_partner_name_is_an_exact_suffix_pair(self) -> None:
        self.assertEqual(splb.flip_partner_name("Ace"), "Ace Flip")
        self.assertEqual(splb.flip_partner_name("Ace Flip"), "Ace")
        self.assertEqual(
            splb.flip_partner_name("Weak I Jokers"), "Weak I Jokers Flip"
        )
        self.assertNotEqual(
            splb.flip_partner_name("Weak I Jokers"),
            "Weak I Jokers Flip Pair",
        )
        self.assertIsNone(splb.flip_partner_name(""))
        self.assertIsNone(splb.flip_partner_name("   "))

    def test_flip_partner_record_uses_the_exact_suffix(self) -> None:
        book = splb.parse_book(_synthetic_book(), 943)
        populated = [record for record in book.records if record.populated]
        names = {
            populated[0].formation_index: "Ace",
            populated[1].formation_index: "Ace Flip",
        }
        partner = splb.find_flip_partner_record(book, populated[0], names)
        self.assertIsNotNone(partner)
        assert partner is not None
        self.assertEqual(partner.record_index, populated[1].record_index)
        names[populated[1].formation_index] = "Weak I Jokers Flip Pair"
        self.assertIsNone(
            splb.find_flip_partner_record(book, populated[0], names)
        )


class PanelContractTests(unittest.TestCase):
    def test_the_panel_states_the_unproved_boundary(self) -> None:
        from mod_editor.apf_studio.playbook_membership_qt import BOUNDARY

        self.assertIn("does not guarantee", BOUNDARY)
        self.assertIn("will not empty a whole book", BOUNDARY)
        self.assertIn("Research pins", BOUNDARY)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

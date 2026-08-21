"""Moving a formation's tagged slots instead of refusing to touch them.

Every populated record in the fifteen retail books carries ``min(4, plays)``
tagged slots -- 209 records, zero exceptions -- and the slots are authored per
formation rather than falling out of entry order.  Three of them are the
formation's audibles -- the game writes a slot number into bits 12..10 at
``0x84864c78`` and runs that counter 0, 1, 2 per record -- and the fourth is
collected with them at ``0x84a850f0``, not proved as 3rd-and-long.  Either way the studio's rule is the same: never drop a slot,
never duplicate one, never invent a value the retail books do not use, but let
the user hand one to another play in the same formation.  These tests hold that
line from both ends -- the writer's, and a forged output the verifier has to
reject.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mod_editor.core import apf2k8_splb_writer as splb  # noqa: E402
from mod_editor.core.errors import ValidationError  # noqa: E402


WORKSPACE = Path(__file__).resolve().parents[2]
INDEX_PATH = WORKSPACE / "extracted/All-Pro Football 2K8 (USA)/0A"
DISC_AVAILABLE = INDEX_PATH.exists()

OUTER = 369          # O-SinglebackAce, the book that proves the tags are authored
FULL = 0             # a record shaped like the 201 four-tag retail records
FOUR = 1             # exactly four plays: every entry is tagged
THREE = 2            # three plays, three tags, like the four retail 3-play records
ONE = 3              # one play, one slot, like the two retail 1-play records


def _book_bytes() -> bytes:
    """A resource with the proved shape and four retail-shaped records.

    One of each size the retail books actually contain: a long formation with
    four slots, and the three short shapes that carry fewer.
    """

    body = bytearray(splb.RESOURCE_SIZE)
    body[0x0C:0x10] = b"BLPS"
    encoded = "O-SinglebackAce".encode("utf-16-be")
    body[0x30 : 0x30 + len(encoded)] = encoded
    for index in range(splb.RECORD_COUNT):
        base = splb.RECORD_BASE + index * splb.RECORD_STRIDE
        for slot in range(splb.ENTRY_CAPACITY):
            struct.pack_into(">H", body, base + slot * 2, splb.FILLER)
        struct.pack_into(">Q", body, base + splb.TRAILER_OFFSET, 0x0000920000000000)

    def populate(record_index: int, formation: int, entries: list[tuple[int, int, int]]):
        base = splb.RECORD_BASE + record_index * splb.RECORD_STRIDE
        for slot, (x, y, play) in enumerate(entries):
            struct.pack_into(">H", body, base + slot * 2, (x << 13) | (y << 10) | play)
        word_a = (formation << 24) | (3 << 17) | (2 << 14) | (2 << 11) | (2 << 8)
        struct.pack_into(">I", body, base + splb.TRAILER_OFFSET, word_a)
        struct.pack_into(">I", body, base + splb.TRAILER_OFFSET + 4, 1 << 3)

    populate(FULL, 62, [(2, 4, 40), (2, 4, 41), (2, 4, 42),
                        (2, 0, 10), (2, 1, 11), (2, 2, 12), (2, 3, 13)])
    populate(FOUR, 63, [(2, 0, 50), (2, 1, 51), (2, 2, 52), (2, 3, 53)])
    populate(THREE, 64, [(2, 0, 60), (2, 1, 61), (2, 2, 62)])
    populate(ONE, 65, [(2, 1, 70)])
    return bytes(body)


def _tags(record: splb.SplbRecord) -> dict[int, int]:
    return {entry.play_index: entry.y for entry in record.entries if entry.tagged}


class TagMoveTests(unittest.TestCase):
    """A move is a swap, so the count of tagged slots cannot change."""

    def setUp(self) -> None:
        self.body = _book_bytes()
        self.book = splb.parse_book(self.body, OUTER)

    def _record_after(self, changes, record_index: int = FULL) -> splb.SplbRecord:
        compiled = splb.compile_book(self.book, changes)
        splb.verify_book(self.body, compiled.replacement, changes)
        return splb.parse_book(compiled.replacement, OUTER).records[record_index]

    def test_a_slot_moves_onto_an_untagged_play(self) -> None:
        move = splb.TagMove(OUTER, FULL, 11, 40)
        after = self._record_after([move])
        self.assertEqual(_tags(after), {10: 0, 40: 1, 12: 2, 13: 3})
        self.assertEqual(len(after.entries), 7)
        self.assertTrue(splb.follows_tag_rule(after.entries))

    def test_a_move_between_two_tagged_plays_swaps_them(self) -> None:
        move = splb.TagMove(OUTER, FULL, 10, 13)
        after = self._record_after([move])
        self.assertEqual(_tags(after)[13], 0)
        self.assertEqual(_tags(after)[10], 3)

    def test_a_move_leaves_the_play_list_itself_alone(self) -> None:
        move = splb.TagMove(OUTER, FULL, 11, 42)
        after = self._record_after([move])
        self.assertEqual(
            [e.play_index for e in after.entries],
            [e.play_index for e in self.book.records[FULL].entries],
        )
        self.assertEqual(
            [e.x for e in after.entries],
            [e.x for e in self.book.records[FULL].entries],
        )

    def test_a_move_from_an_untagged_play_is_refused(self) -> None:
        with self.assertRaisesRegex(ValidationError, "holds no tagged slot"):
            splb.compile_book(self.book, [splb.TagMove(OUTER, FULL, 40, 41)])

    def test_a_move_to_a_play_outside_the_record_is_refused(self) -> None:
        with self.assertRaisesRegex(ValidationError, "not in record"):
            splb.compile_book(self.book, [splb.TagMove(OUTER, FULL, 11, 500)])

    def test_a_move_onto_the_same_play_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            splb.compile_book(self.book, [splb.TagMove(OUTER, FULL, 11, 11)])

    def test_one_slot_cannot_be_sent_to_two_plays_at_once(self) -> None:
        with self.assertRaises(ValidationError):
            splb.compile_book(
                self.book,
                [
                    splb.TagMove(OUTER, FULL, 11, 40),
                    splb.TagMove(OUTER, FULL, 11, 41),
                ],
            )

    def test_a_move_then_remove_of_the_source_composes(self) -> None:
        """Urianus's Save-Project loss: staged move + staged removal of the
        same play compose in the fixed order adds -> moves -> removals."""

        compiled = splb.compile_book(
            self.book,
            [
                splb.TagMove(OUTER, FULL, 11, 40),
                splb.MembershipChange(OUTER, FULL, 11, False),
            ],
        )
        splb.verify_book(
            self.body,
            compiled.replacement,
            [
                splb.TagMove(OUTER, FULL, 11, 40),
                splb.MembershipChange(OUTER, FULL, 11, False),
            ],
        )
        after = splb.parse_book(compiled.replacement, OUTER).records[FULL]
        self.assertEqual(_tags(after), {10: 0, 40: 1, 12: 2, 13: 3})
        self.assertNotIn(11, [e.play_index for e in after.entries])

    def test_a_move_then_remove_of_the_destination_with_heir_composes(self) -> None:
        after = self._record_after(
            [
                splb.TagMove(OUTER, FULL, 11, 40),
                splb.MembershipChange(OUTER, FULL, 40, False, tag_heir=41),
            ]
        )
        self.assertEqual(_tags(after), {10: 0, 41: 1, 12: 2, 13: 3})
        self.assertNotIn(40, [e.play_index for e in after.entries])

    def test_a_move_then_remove_of_the_destination_sheds_a_slot_when_legal(self) -> None:
        after = self._record_after(
            [
                splb.TagMove(OUTER, FOUR, 52, 53),
                splb.MembershipChange(OUTER, FOUR, 52, False),
            ],
            record_index=FOUR,
        )
        self.assertEqual([e.play_index for e in after.entries], [50, 51, 53])
        self.assertEqual(_tags(after), {50: 0, 51: 1, 53: 2})

    def test_a_move_then_remove_that_would_drop_a_slot_is_still_refused(self) -> None:
        with self.assertRaisesRegex(ValidationError, "carry the slot"):
            splb.compile_book(
                self.book,
                [
                    splb.TagMove(OUTER, FULL, 11, 40),
                    splb.MembershipChange(OUTER, FULL, 40, False),
                ],
            )

    def test_a_slot_can_move_onto_a_play_added_in_the_same_request(self) -> None:
        """The verifier used to demand a Y-swap against the original book.

        Play 560 in X-43Blitz Bear is the community case: add it, then hand it
        tagged slot 1. The destination has no original Y, so treating the move
        as a swap against the source book refused a legal compile.
        """

        changes = [
            splb.MembershipChange(OUTER, FULL, 300, True),
            splb.TagMove(OUTER, FULL, 11, 300),
        ]
        after = self._record_after(changes)
        self.assertEqual(_tags(after)[300], 1)
        self.assertNotIn(11, _tags(after))
        self.assertIn(300, [e.play_index for e in after.entries])
        self.assertTrue(splb.follows_tag_rule(after.entries))


class RemovalCarriesTheSlotTests(unittest.TestCase):
    """Removing a tagged play offers a successor instead of a flat refusal."""

    def setUp(self) -> None:
        self.body = _book_bytes()
        self.book = splb.parse_book(self.body, OUTER)

    def test_an_heir_carries_the_slot_and_the_play_goes(self) -> None:
        change = splb.MembershipChange(OUTER, FULL, 11, False, tag_heir=41)
        compiled = splb.compile_book(self.book, [change])
        splb.verify_book(self.body, compiled.replacement, [change])
        after = splb.parse_book(compiled.replacement, OUTER).records[FULL]
        self.assertNotIn(11, [e.play_index for e in after.entries])
        self.assertEqual(_tags(after), {10: 0, 41: 1, 12: 2, 13: 3})
        self.assertTrue(splb.follows_tag_rule(after.entries))

    def test_a_play_added_in_the_same_request_can_be_the_heir(self) -> None:
        changes = [
            splb.MembershipChange(OUTER, FULL, 300, True),
            splb.MembershipChange(OUTER, FULL, 11, False, tag_heir=300),
        ]
        compiled = splb.compile_book(self.book, changes)
        splb.verify_book(self.body, compiled.replacement, changes)
        after = splb.parse_book(compiled.replacement, OUTER).records[FULL]
        self.assertEqual(_tags(after)[300], 1)

    def test_removing_a_tagged_play_with_no_heir_names_the_way_through(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            splb.compile_book(self.book, [splb.MembershipChange(OUTER, FULL, 11, False)])
        message = str(caught.exception)
        self.assertIn("tagged slot", message)
        # The refusal has to point at what the app itself will do, not at a
        # chore the user is expected to perform elsewhere.
        self.assertIn("carry", message)
        self.assertIn("studio offers", message)

    def test_an_heir_outside_the_record_is_refused(self) -> None:
        with self.assertRaisesRegex(ValidationError, "cannot carry"):
            splb.compile_book(
                self.book, [splb.MembershipChange(OUTER, FULL, 11, False, tag_heir=500)]
            )

    def test_a_short_formation_sheds_a_slot_with_its_play(self) -> None:
        """Four plays carry four slots; three plays carry three, so no heir."""

        change = splb.MembershipChange(OUTER, FOUR, 53, False)
        compiled = splb.compile_book(self.book, [change])
        splb.verify_book(self.body, compiled.replacement, [change])
        after = splb.parse_book(compiled.replacement, OUTER).records[FOUR]
        self.assertEqual(_tags(after), {50: 0, 51: 1, 52: 2})
        self.assertTrue(splb.follows_tag_rule(after.entries))

    def test_the_slot_one_play_still_needs_an_heir_in_a_short_formation(self) -> None:
        with self.assertRaisesRegex(ValidationError, "slot-1"):
            splb.compile_book(self.book, [splb.MembershipChange(OUTER, FOUR, 51, False)])
        change = splb.MembershipChange(OUTER, FOUR, 51, False, tag_heir=50)
        compiled = splb.compile_book(self.book, [change])
        splb.verify_book(self.body, compiled.replacement, [change])
        after = splb.parse_book(compiled.replacement, OUTER).records[FOUR]
        self.assertEqual(_tags(after)[50], 1)

    def test_growing_a_short_formation_hands_the_new_play_the_next_slot(self) -> None:
        """min(4, plays) has no exceptions, so a fourth play needs a fourth slot."""

        change = splb.MembershipChange(OUTER, THREE, 200, True)
        compiled = splb.compile_book(self.book, [change])
        splb.verify_book(self.body, compiled.replacement, [change])
        after = splb.parse_book(compiled.replacement, OUTER).records[THREE]
        self.assertEqual(_tags(after), {60: 0, 61: 1, 62: 2, 200: 3})
        self.assertTrue(splb.retail_tag_shape(after.entries))

    def test_the_next_slot_after_slot_one_is_slot_zero(self) -> None:
        """Retail's two-play formations carry 0 and 1, so slot 0 comes second."""

        change = splb.MembershipChange(OUTER, ONE, 200, True)
        compiled = splb.compile_book(self.book, [change])
        splb.verify_book(self.body, compiled.replacement, [change])
        after = splb.parse_book(compiled.replacement, OUTER).records[ONE]
        self.assertEqual(_tags(after), {70: 1, 200: 0})
        self.assertTrue(splb.retail_tag_shape(after.entries))

    def test_emptying_a_formation_sheds_every_tagged_slot(self) -> None:
        changes = [
            splb.MembershipChange(OUTER, FULL, play, False)
            for play in (40, 41, 42, 10, 11, 12, 13)
        ]
        compiled = splb.compile_book(self.book, changes)
        splb.verify_book(self.body, compiled.replacement, changes)
        after = splb.parse_book(compiled.replacement, OUTER).records[FULL]
        self.assertEqual(after.entries, ())
        self.assertTrue(splb.follows_tag_rule(after.entries))
        self.assertEqual(after.trailer, self.book.records[FULL].trailer)


class InvariantTests(unittest.TestCase):
    """The rule the writer enforces is exactly the one the retail books keep."""

    def setUp(self) -> None:
        self.body = _book_bytes()
        self.book = splb.parse_book(self.body, OUTER)

    def test_the_rule_is_min_four_and_the_retail_books_obey_it(self) -> None:
        self.assertEqual(splb.required_tag_count(0), 0)
        self.assertEqual(splb.required_tag_count(1), 1)
        self.assertEqual(splb.required_tag_count(3), 3)
        self.assertEqual(splb.required_tag_count(77), 4)
        self.assertEqual(splb.TAG_PRIORITY, (1, 0, 2, 3))
        for record in (FULL, FOUR, THREE):
            self.assertTrue(splb.follows_tag_rule(self.book.records[record].entries))
            self.assertTrue(splb.retail_tag_shape(self.book.records[record].entries))

    def test_dropping_below_min_four_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            splb.compile_book(self.book, [splb.MembershipChange(OUTER, FULL, 12, False)])

    def _forged_slot(self, y: int) -> tuple[bytes, splb.TagMove]:
        """An honest move, then play 41's slot forged behind the writer's back."""

        move = splb.TagMove(OUTER, FULL, 11, 40)
        forged = bytearray(splb.compile_book(self.book, [move]).replacement)
        base = splb.RECORD_BASE + FULL * splb.RECORD_STRIDE
        entries = splb.parse_book(bytes(forged), OUTER).records[FULL].entries
        slot = next(i for i, e in enumerate(entries) if e.play_index == 41)
        struct.pack_into(">H", forged, base + slot * 2, (2 << 13) | (y << 10) | 41)
        return bytes(forged), move

    def test_a_duplicated_slot_is_refused(self) -> None:
        forged, move = self._forged_slot(0)   # play 10 already holds slot 0
        with self.assertRaisesRegex(ValidationError, "tagged slot twice"):
            splb.verify_book(self.body, forged, [move])

    def test_a_slot_value_the_retail_books_never_use_is_refused(self) -> None:
        for y in (5, 6, 7):
            with self.subTest(y=y):
                forged, move = self._forged_slot(y)
                with self.assertRaisesRegex(ValidationError, "only 0-3"):
                    splb.verify_book(self.body, forged, [move])

    def test_the_writer_flags_a_legal_tag_set_retail_never_uses(self) -> None:
        """{1, 2, 3} keeps the counted rule but is off the retail distribution."""

        change = splb.MembershipChange(OUTER, FOUR, 51, False, tag_heir=50)
        compiled = splb.compile_book(self.book, [change])
        self.assertEqual(compiled.report["records_outside_retail_tag_sets"], [FOUR])
        move = splb.TagMove(OUTER, FULL, 11, 40)
        self.assertEqual(
            splb.compile_book(self.book, [move]).report[
                "records_outside_retail_tag_sets"
            ],
            [],
        )

    def test_the_report_never_claims_the_slots_are_understood(self) -> None:
        move = splb.TagMove(OUTER, FULL, 11, 40)
        claims = splb.compile_book(self.book, [move]).report["claims"]
        self.assertTrue(claims["tag_count_rule_held"])
        self.assertFalse(claims["tag_meaning_proved"])
        self.assertTrue(claims["cpu_membership_static_proved"])
        self.assertFalse(claims["cpu_behaviour_runtime_proved"])
        self.assertTrue(claims["empty_record_returns_no_plays"])
        self.assertFalse(claims["wr3_te_package_sub_proved"])


class ForgedOutputTests(unittest.TestCase):
    """The verifier is the safety net for a reassignment too."""

    def setUp(self) -> None:
        self.body = _book_bytes()
        self.book = splb.parse_book(self.body, OUTER)
        self.move = splb.TagMove(OUTER, FULL, 11, 40)
        self.compiled = splb.compile_book(self.book, [self.move])

    def test_the_honest_move_verifies(self) -> None:
        report = splb.verify_book(self.body, self.compiled.replacement, [self.move])
        self.assertEqual(report["changed_records"], [FULL])
        self.assertTrue(report["tag_rule_reverified"])
        self.assertTrue(report["independent_reparse"])

    def test_a_diff_outside_the_named_record_is_refused(self) -> None:
        for offset in (
            splb.RECORD_BASE + splb.RECORD_STRIDE,          # another record's entries
            splb.RECORD_BASE + splb.TRAILER_OFFSET,         # this record's trailer
            0x7998,                                         # unmapped tail region
            0x7D98,                                         # unmapped tail region
            0x30,                                           # the book name
        ):
            with self.subTest(offset=hex(offset)):
                forged = bytearray(self.compiled.replacement)
                forged[offset] ^= 0xFF
                with self.assertRaises(ValidationError):
                    splb.verify_book(self.body, bytes(forged), [self.move])

    def test_a_move_the_output_does_not_show_is_refused(self) -> None:
        with self.assertRaisesRegex(ValidationError, "moved from play"):
            splb.verify_book(self.body, self.body, [self.move])

    def test_an_heir_the_output_does_not_show_is_refused(self) -> None:
        change = splb.MembershipChange(OUTER, FULL, 11, False, tag_heir=41)
        forged = bytearray(splb.compile_book(self.book, [change]).replacement)
        base = splb.RECORD_BASE + FULL * splb.RECORD_STRIDE
        entries = splb.parse_book(bytes(forged), OUTER).records[FULL].entries
        slot = next(i for i, e in enumerate(entries) if e.play_index == 41)
        struct.pack_into(">H", forged, base + slot * 2, (2 << 13) | (3 << 10) | 41)
        with self.assertRaises(ValidationError):
            splb.verify_book(self.body, bytes(forged), [change])


def _prose(copy: str) -> str:
    """Strip reStructuredText emphasis so assertions can match spoken phrases."""

    return copy.replace("*", "").replace("`", "").lower()


class CopyTests(unittest.TestCase):
    """What the product says about the slots has to match what was proved."""

    def setUp(self) -> None:
        from mod_editor.apf_studio import playbook_membership_qt as panel

        # The panel shows BOUNDARY / TAG_BOUNDARY inline and puts the address
        # wall behind "Research pins". Both halves are still product copy a
        # user can reach, so both are held to the same standard here.
        self.panel_copy = "\n".join(
            (
                panel.BOUNDARY,
                panel.TAG_BOUNDARY,
                panel.RESEARCH_PINS,
                panel.TAG_RESEARCH_PINS,
                panel.EMPTY_FORMATION_WARNING,
                str(panel.__doc__),
            )
        )
        self.writer_copy = str(splb.__doc__)
        # These read as prose to a user but as reStructuredText in a docstring,
        # so "**not** established" and "``Y``" carry markup mid-phrase. Assert
        # against the words rather than the markup.
        self.panel_prose = _prose(self.panel_copy)
        self.writer_prose = _prose(self.writer_copy)

    def test_the_copy_states_what_was_proved_about_the_slots(self) -> None:
        for copy in (self.panel_copy, self.writer_copy):
            self.assertIn("min(4, plays)", copy)
            self.assertIn("209", copy)
            # authored per formation, not a positional artefact
            self.assertIn("Ace Flip", copy)
            self.assertIn("77", copy)

    def test_the_copy_states_the_audible_proof_and_credits_the_reporter(self) -> None:
        """The reading was unconfirmed until the executable settled it.

        It is settled now: ``0x84864c78`` inserts a slot number into bits 12-10
        of an SPLB entry and stores it back, and its loop runs that counter
        0, 1, 2 while stepping one 176-byte record per formation. So the copy
        must assert the audible reading rather than hedge it -- and must still
        credit the reporter who got there from the data alone.
        """

        self.assertIn("Urianus", self.panel_copy)
        for copy in (self.panel_copy, self.writer_copy):
            self.assertIn("audible", copy.lower())
            self.assertIn("0x84864c78", copy)      # the write that proves it
            self.assertIn("0x84a8ab28", copy)      # the swap the panel mirrors
            self.assertIn("0x84a8ac30", copy)      # count-plays consumer
            self.assertIn("0x84a8bd20", copy)      # get-nth consumer

    def test_the_copy_states_the_fourth_slot_is_collected_not_3rd_and_long(self) -> None:
        """Y==3 is a first-class tagged slot in 0x84a850f0; 3rd-and-long is not pinned.

        The assign loop still runs 0..2 and never writes slot 3. The collector
        at 0x84a850f0 walks 0..3. Down is pinned at +0x254 / 0x848d96e4, but
        that is not the play picker. Copy must name the collector and the down
        field and still refuse to call either the CPU's 3rd-and-long choice.
        """

        for copy in (self.panel_copy, self.writer_copy):
            self.assertIn("0x84a850f0", copy)
            self.assertIn("0x84a851ec", copy)
            self.assertIn("0x848d96e4", copy)
            self.assertIn("0x848605b4", copy)
            self.assertIn("0x820E57C8", copy)
            self.assertIn("0x8485bd38", copy)
            self.assertIn("0x84a472d0", copy)
            self.assertIn("0x8486ce88", copy)
            self.assertIn("0x8485e810", copy)
            self.assertIn("0x84862580", copy)
            self.assertIn("0x844dbe00", copy)
            self.assertIn("0x820FC380", copy)
            self.assertIn("0x84b694a8", copy)
            self.assertIn("0x84a89ea8", copy)
            self.assertIn("0x84DCB2A8", copy)
            self.assertIn("0x848699d8", copy)
            self.assertIn("0x8485e7f8", copy)
            self.assertIn("0x851A2780", copy)
            self.assertIn("0x8466b998", copy)
            self.assertIn("0x8493d968", copy)
            self.assertIn("0x8493e180", copy)
            self.assertIn("0x8466af70", copy)
            self.assertIn("0x8466a818", copy)
            self.assertIn("0x8466aae0", copy)
            self.assertIn("0x8466abc0", copy)
            self.assertIn("0x8466af28", copy)
            self.assertIn("0x8470c2c4", copy)
            self.assertIn("0x84712498", copy)
            self.assertIn("0x847163d4", copy)
            self.assertIn("0x84867938", copy)
            self.assertIn("0x84a139d0", copy)
            self.assertIn("0x84a28318", copy)
            self.assertIn("0x84887e18", copy)
            self.assertIn("0x850F1218", copy)
            self.assertIn("0x84ad0048", copy)
            self.assertIn("0x847c6da8", copy)
            self.assertIn("0x849fd6a8", copy)
            self.assertIn("0x8486cd80", copy)
            self.assertIn("0x849fd6c8", copy)
            self.assertIn("0x851D9660", copy)
            self.assertIn("0x849fcf60", copy)
            self.assertIn("0x849d81d0", copy)
            self.assertIn("0x84E28670", copy)
            self.assertIn("0x84EB0DE4", copy)
            self.assertIn("0x849c9c90", copy)
            self.assertIn("0x8466a994", copy)
            self.assertIn("0x000dca40", copy)
            self.assertIn("0x84ab2010", copy)
            self.assertIn("0x8466ba30", copy)
            self.assertIn("0x8466bd38", copy)
            self.assertIn("0x8466af48", copy)
            self.assertIn("0x84b162a8", copy)
            self.assertIn("0x8466b8fc", copy)
            self.assertIn("0x84c381e8", copy)
            self.assertIn("0x84a87b38", copy)
            self.assertIn("0x84bdfb00", copy)
            self.assertIn("0x848bb1a8", copy)
            self.assertIn("0x8466b660", copy)
            self.assertIn("0x8466c7f0", copy)
            self.assertIn("0x84671838", copy)
            self.assertIn("0x84842f48", copy)
            self.assertIn("0x8476ca80", copy)
            self.assertIn("0x8492bb24", copy)
            self.assertIn("0x84b0a4c0", copy)
            self.assertIn("0x84EE65A8", copy)
            self.assertIn("0x849e7790", copy)
            self.assertIn("0x847e2818", copy)
            self.assertIn("0x84abb590", copy)
            self.assertIn("0x84a9d7a0", copy)
            self.assertIn("0x84be2b48", copy)
            self.assertIn("0x848777cc", copy)
            self.assertIn("0x84b93b10", copy)
            self.assertIn("0x84b94258", copy)
            self.assertIn("0x849277a8", copy)
            self.assertIn("0x84c4c480", copy)
            self.assertIn("0x84ba2520", copy)
            self.assertIn("0x846c2068", copy)
            self.assertIn("0x8466c890", copy)
            self.assertIn("0x8466c91c", copy)
            self.assertIn("0x844dd260", copy)
            self.assertIn("0x8477f950", copy)
            self.assertIn("0x84a37850", copy)
            self.assertIn("0x848864b0", copy)
            self.assertIn("0x84a5eb08", copy)
            self.assertIn("0x8475b7b0", copy)
            self.assertIn("0x1138e0", copy)
            self.assertIn("0x84a23bd0", copy)
            self.assertIn("0x844e8568", copy)
            self.assertIn("0x849d36d8", copy)
            self.assertIn("0x848631d0", copy)
            self.assertIn("0x168ad0", copy)
            self.assertIn("0x84a2ccd8", copy)
            self.assertIn("0x84961548", copy)
            self.assertIn("0x849e3a24", copy)
            self.assertIn("0x84814dcc", copy)
            self.assertIn("0x84816118", copy)
            self.assertIn("0x8485a04c", copy)
            self.assertIn("0x84869e60", copy)
            self.assertIn("0x84a9adcc", copy)
            self.assertIn("0x84a21298", copy)
            self.assertIn("0x84E446C8", copy)
            self.assertIn("0x845FD8B4", copy)
            self.assertIn("0x85212B88", copy)
            self.assertIn("0x84911750", copy)
            self.assertIn("0x849ecd48", copy)
            self.assertIn("0x847d7590", copy)
            self.assertIn("0x8480189c", copy)
            self.assertIn("0x84F1779C", copy)
            self.assertIn("0x8466c8dc", copy)
            self.assertIn("0x8499e420", copy)
            self.assertIn("0x849a3b58", copy)
            self.assertIn("0x84b68cd8", copy)
            self.assertIn("0x84ad92e0", copy)
            self.assertIn("0x84879bc0", copy)
            self.assertIn("0x84b68cc8", copy)
            self.assertIn("0x84ad0348", copy)
            self.assertIn("0x844f72b0", copy)
            self.assertIn("0x84b39458", copy)
            self.assertIn("0x84EB02D0", copy)
            self.assertIn("0x84ad9f40", copy)
            self.assertIn("0x848ee750", copy)
            self.assertIn("0x84b64c88", copy)
        self.assertIn("does not prove", self.panel_copy)
        for copy in (self.panel_prose, self.writer_prose):
            self.assertIn("3rd-and-long", copy)
            self.assertNotIn("generic bit-field clamp", copy)

    def test_the_copy_does_not_cite_the_disproved_glyph_mapper(self) -> None:
        """A disassembly showed 0x84a17298 never touches the glyph strings."""

        for copy in (self.panel_copy, self.writer_copy):
            self.assertNotIn("84a17298", copy.lower())

    def test_the_copy_no_longer_calls_the_slot_meaning_the_reason_to_refuse(self) -> None:
        self.assertNotIn("removing one is refused rather than guessed", self.panel_copy)
        self.assertIn("moved", self.panel_copy)
        self.assertIn("Emptying a formation", self.panel_copy)
        self.assertIn("min(4, 0)", self.panel_copy)

    def test_the_copy_does_not_claim_runtime_cpu_play_calling(self) -> None:
        for copy in (self.panel_prose, self.writer_prose):
            self.assertIn("runtime", copy)
            self.assertIn("unproved", copy)
            self.assertNotIn("cpu may call", copy)
            self.assertNotIn("cpu actually calls", copy)

    def test_the_copy_states_role_8_is_te_and_role_9_is_wr(self) -> None:
        for copy in (self.panel_copy, self.writer_copy):
            self.assertIn("0x820FC320", copy)
            self.assertIn("0x84a9ae68", copy)
            self.assertIn("8 → TE", copy)
            self.assertIn("9 → WR", copy)

    def test_the_copy_states_empty_records_return_no_plays(self) -> None:
        for copy in (self.panel_copy, self.writer_copy):
            self.assertIn("0x84a8ac30", copy)
            self.assertIn("0x84a8bd20", copy)


class StaticConsumerPinTests(unittest.TestCase):
    """When the decompressed PE is present, the cited instructions must match."""

    def test_static_consumer_words_match_the_decompressed_pe(self) -> None:
        candidates = (
            Path("/tmp/apf.pe"),
            WORKSPACE / ".codex-tmp/apf-sixth/apf-decoded.pe",
        )
        pe_path = next((path for path in candidates if path.is_file()), None)
        if pe_path is None:
            self.skipTest("decompressed APF PE is not on this machine")
        payload = pe_path.read_bytes()
        self.assertEqual(hashlib.sha256(payload).hexdigest(), splb.APF_PE_SHA256)
        for address, expected in splb.STATIC_CONSUMER_WORDS.items():
            offset = address - splb.APF_PE_IMAGE_BASE
            actual = struct.unpack_from(">I", payload, offset)[0]
            self.assertEqual(
                actual,
                expected,
                f"VA 0x{address:08x}: expected 0x{expected:08x}, got 0x{actual:08x}",
            )
        from mod_editor.core.playbook_package_rule_spike import (
            APF_ROLE_TO_ROSTER_FIRST_11,
            APF_ROLE_TO_ROSTER_TABLE_VA,
        )

        table_off = APF_ROLE_TO_ROSTER_TABLE_VA - splb.APF_PE_IMAGE_BASE
        self.assertEqual(
            tuple(payload[table_off : table_off + 11]),
            APF_ROLE_TO_ROSTER_FIRST_11,
        )
        from mod_editor.core.playbook_package_rule_spike import (
            APF_DOWN_NAME_TABLE_VA,
            APF_DOWN_NAMES,
        )

        name_off = APF_DOWN_NAME_TABLE_VA - splb.APF_PE_IMAGE_BASE
        for index, expected in enumerate(APF_DOWN_NAMES):
            ptr = struct.unpack_from(">I", payload, name_off + index * 4)[0]
            text_off = ptr - splb.APF_PE_IMAGE_BASE
            got = payload[text_off : text_off + len(expected) * 2].decode("utf-16-be")
            self.assertEqual(got, expected, f"down name {index}")
        from mod_editor.core.playbook_package_rule_spike import (
            APF_CATEGORY_PERSONNEL_ACE_ROW_INDEX,
            APF_CATEGORY_PERSONNEL_FIVE_WIDE_ROW_INDEX,
            APF_CATEGORY_PERSONNEL_ROW_ACE,
            APF_CATEGORY_PERSONNEL_ROW_FIVE_WIDE,
            APF_CATEGORY_PERSONNEL_TABLE_VA,
        )

        table_off = APF_CATEGORY_PERSONNEL_TABLE_VA - splb.APF_PE_IMAGE_BASE
        for row_index, expected in (
            (APF_CATEGORY_PERSONNEL_ACE_ROW_INDEX, APF_CATEGORY_PERSONNEL_ROW_ACE),
            (
                APF_CATEGORY_PERSONNEL_FIVE_WIDE_ROW_INDEX,
                APF_CATEGORY_PERSONNEL_ROW_FIVE_WIDE,
            ),
        ):
            got = []
            for col in range(11):
                word_off = table_off + (row_index * 11 + col) * 4
                got.append(payload[word_off])
            self.assertEqual(tuple(got), expected, f"personnel row {row_index}")
        from mod_editor.core.playbook_package_rule_spike import (
            APF_PACKAGE_MAP_ROLE_TE,
            APF_PACKAGE_MAP_ROLE_WR3,
            APF_ROLE_ELIGIBILITY_MASK_TE,
            APF_ROLE_ELIGIBILITY_MASK_WR,
            APF_ROLE_ELIGIBILITY_WORD_TABLE_VA,
        )

        elig_off = APF_ROLE_ELIGIBILITY_WORD_TABLE_VA - splb.APF_PE_IMAGE_BASE
        self.assertEqual(
            struct.unpack_from(">I", payload, elig_off + APF_PACKAGE_MAP_ROLE_TE * 4)[0],
            APF_ROLE_ELIGIBILITY_MASK_TE,
        )
        self.assertEqual(
            struct.unpack_from(">I", payload, elig_off + APF_PACKAGE_MAP_ROLE_WR3 * 4)[0],
            APF_ROLE_ELIGIBILITY_MASK_WR,
        )


class PanelTests(unittest.TestCase):
    """The panel offers the carry rather than telling the user to go do it."""

    @classmethod
    def setUpClass(cls) -> None:
        from PyQt5.QtWidgets import QApplication

        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        from types import SimpleNamespace

        from mod_editor.apf_studio.playbook_membership_qt import (
            ApfPlaybookMembershipPanel,
        )

        facade = SimpleNamespace(source_ready=False, source=None)
        self.panel = ApfPlaybookMembershipPanel(facade, lambda *_a: None)
        self.body = _book_bytes()
        self.panel._book = splb.parse_book(self.body, OUTER)
        self.panel._plays = [f"Play {index}" for index in range(586)]
        self.panel._formations = {62: "Ace", 63: "Ace Flip", 64: "Slot"}
        self.panel._refresh_formations()

    def tearDown(self) -> None:
        self.panel.deleteLater()

    def test_the_panel_knows_when_a_removal_needs_an_heir(self) -> None:
        self.assertTrue(self.panel.removal_needs_heir(FULL, 11))
        self.assertFalse(self.panel.removal_needs_heir(FULL, 40))
        # Four plays, four slots: the slot leaves with its play.
        self.assertFalse(self.panel.removal_needs_heir(FOUR, 53))

    def test_live_play_controls_use_the_stored_membership_boundary(self) -> None:
        self.panel._refresh_plays()

        self.assertIn("Stored plays for", self.panel.play_header.text())
        self.assertNotIn("CPU may call", self.panel.play_header.text())
        self.assertIn("stored", self.panel.play_list.toolTip())
        self.assertIn("Audibles", self.panel.play_list.toolTip())

    def test_the_panel_only_offers_heirs_that_actually_work(self) -> None:
        candidates = self.panel._carry_candidates(FULL, 11)
        self.assertEqual(candidates, [40, 41, 42])
        for heir in candidates:
            change = splb.MembershipChange(OUTER, FULL, 11, False, heir)
            self.assertIsNotNone(splb.compile_book(self.panel._book, [change]))

    def test_staging_a_carry_compiles_and_verifies(self) -> None:
        self.panel.stage_membership(FULL, 11, False, heir=41)
        changes = self.panel.staged_changes()
        self.assertEqual(changes[0].tag_heir, 41)
        compiled = splb.compile_book(self.panel._book, changes)
        splb.verify_book(self.body, compiled.replacement, changes)
        after = splb.parse_book(compiled.replacement, OUTER).records[FULL]
        self.assertEqual(_tags(after)[41], 1)

    def test_staging_a_move_compiles_and_verifies(self) -> None:
        self.panel.stage_tag_move(FULL, 11, 40)
        changes = self.panel.staged_changes()
        self.assertEqual(len(changes), 1)
        compiled = splb.compile_book(self.panel._book, changes)
        splb.verify_book(self.body, compiled.replacement, changes)
        self.assertEqual(self.panel._effective_tags(FULL)[40], 1)

    def test_an_illegal_move_is_not_staged(self) -> None:
        with self.assertRaises(ValidationError):
            self.panel.stage_tag_move(FULL, 40, 41)
        self.assertEqual(self.panel.staged_changes(), ())

    def test_a_rejected_removal_leaves_nothing_staged(self) -> None:
        with self.assertRaises(ValidationError):
            self.panel.stage_membership(FULL, 11, False)
        self.assertEqual(self.panel.staged_changes(), ())

    def _item_for(self, play_index: int):
        from PyQt5.QtCore import Qt

        for row in range(self.panel.play_list.count()):
            item = self.panel.play_list.item(row)
            if int(item.data(Qt.UserRole)) == play_index:
                return item
        raise AssertionError(f"play {play_index} is not listed")

    def test_unticking_a_tagged_play_offers_the_carry_instead_of_a_wall(self) -> None:
        from unittest.mock import patch

        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QMessageBox

        from mod_editor.apf_studio import playbook_membership_qt as module

        item = self._item_for(11)
        with patch.object(
            module.QMessageBox, "question", return_value=QMessageBox.Yes
        ) as asked, patch.object(
            module.QInputDialog, "getItem", side_effect=lambda *a, **k: (a[3][0], True)
        ) as picked:
            item.setCheckState(Qt.Unchecked)
        self.assertTrue(asked.called)
        self.assertTrue(picked.called)
        self.assertIn("audible", asked.call_args[0][2])
        changes = self.panel.staged_changes()
        self.assertEqual(len(changes), 1)
        self.assertFalse(changes[0].member)
        self.assertEqual(changes[0].tag_heir, 40)

    def test_declining_the_carry_stages_nothing_and_restores_the_tick(self) -> None:
        from unittest.mock import patch

        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QMessageBox

        from mod_editor.apf_studio import playbook_membership_qt as module

        item = self._item_for(11)
        with patch.object(
            module.QMessageBox, "question", return_value=QMessageBox.Cancel
        ):
            item.setCheckState(Qt.Unchecked)
        self.assertEqual(self.panel.staged_changes(), ())
        self.assertEqual(self._item_for(11).checkState(), Qt.Checked)

    def test_emptying_a_formation_stages_a_verified_clear(self) -> None:
        self.panel.stage_empty_formation(FULL)
        changes = self.panel.staged_changes()
        self.assertTrue(changes)
        self.assertTrue(all(isinstance(c, splb.MembershipChange) for c in changes))
        self.assertTrue(all(not c.member for c in changes))
        compiled = splb.compile_book(self.panel._book, changes)
        splb.verify_book(self.body, compiled.replacement, changes)
        after = splb.parse_book(compiled.replacement, OUTER).records[FULL]
        self.assertEqual(after.entries, ())

    def test_the_panel_counts_what_would_still_be_populated(self) -> None:
        self.assertEqual(self.panel.populated_records_after_staging(), 4)
        self.assertEqual(
            self.panel.populated_records_after_staging(pending_empty=FULL), 3
        )
        self.panel.stage_empty_formation(FULL)
        self.assertEqual(self.panel.populated_records_after_staging(), 3)

    def test_the_last_populated_formation_cannot_be_emptied(self) -> None:
        for record_index in (FULL, FOUR, THREE):
            self.panel.stage_empty_formation(record_index)
        self.assertEqual(self.panel.populated_records_after_staging(), 1)
        with self.assertRaises(ValidationError) as caught:
            self.panel.stage_empty_formation(ONE)
        self.assertIn("last formation", str(caught.exception))
        # The refusal leaves the three staged clears exactly as they were.
        self.assertEqual(self.panel.populated_records_after_staging(), 1)


class PanelReadabilityTests(unittest.TestCase):
    """Honesty copy has to be reachable, not in the way.

    The inline boundary label had grown to 11,360 characters and the tagged-slot
    dialog to 11,252 -- mostly executable addresses and withdrawn candidates,
    word-wrapped between a user and the controls they came for. The record still
    ships in full; it moved behind "Research pins".
    """

    #: Long enough to state the boundary, short enough that someone reads it.
    INLINE_LIMIT = 3_000

    def setUp(self) -> None:
        from mod_editor.apf_studio import playbook_membership_qt as panel

        self.panel = panel

    def test_the_inline_copy_is_short_enough_to_read(self) -> None:
        for name in ("BOUNDARY", "TAG_BOUNDARY", "EMPTY_FORMATION_WARNING"):
            with self.subTest(copy=name):
                self.assertLessEqual(len(getattr(self.panel, name)), self.INLINE_LIMIT)

    def test_the_full_static_record_still_ships(self) -> None:
        pins = f"{self.panel.RESEARCH_PINS}\n{self.panel.TAG_RESEARCH_PINS}"
        # Every address the boundary leans on has to remain checkable.
        for address in (
            "0x84a8ac30",
            "0x84a8bd20",
            "0x84864c78",
            "0x84a8ab28",
            "0x84a850f0",
            "0x820FC320",
        ):
            with self.subTest(address=address):
                self.assertIn(
                    address,
                    pins
                    + self.panel.BOUNDARY
                    + self.panel.TAG_BOUNDARY
                    + self.panel.EMPTY_FORMATION_WARNING,
                )

    def test_the_inline_copy_points_at_the_pins(self) -> None:
        self.assertIn("Research pins", self.panel.BOUNDARY)
        self.assertIn("Research pins", self.panel.TAG_BOUNDARY)

    def test_switching_books_does_not_ask_to_discard(self) -> None:
        source = inspect.getsource(self.panel.ApfPlaybookMembershipPanel._load_book)
        self.assertNotIn("Discard the staged playbook", source)
        self.assertIn("no longer discards", source)

    def test_the_copy_does_not_treat_play_names_as_personnel(self) -> None:
        """Adding a TE-named play or moving a Y tag is not a personnel edit."""

        getting_started = (
            WORKSPACE / "docs/mod_editor/apf2k8_mod_studio_getting_started.md"
        ).read_text(encoding="utf-8")
        for name, copy in (
            ("EMPTY_FORMATION_WARNING", self.panel.EMPTY_FORMATION_WARNING),
            ("getting-started", getting_started),
        ):
            with self.subTest(copy=name):
                self.assertNotIn("put TEs on", copy)
                self.assertNotIn("TE-using plays", copy)
                self.assertIn("Personnel comes from the formation package map", copy)
                self.assertIn("Play names are not personnel", copy)
        self.assertNotIn("put TEs on", self.panel.BOUNDARY)
        self.assertNotIn("TE-using plays", self.panel.BOUNDARY)
        self.assertIn("does not change the personnel", self.panel.BOUNDARY)
        self.assertIn("does not add a tight end", self.panel.BOUNDARY)


class PanelProjectHandoffTests(unittest.TestCase):
    """Every staged tick has to reach the session, or Save Project loses it."""

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
        self.body = _book_bytes()
        self.panel = ApfPlaybookMembershipPanel(self.facade, lambda *_a: None)
        self.panel._book = splb.parse_book(self.body, OUTER)
        self.panel._plays = [f"Play {index}" for index in range(586)]
        self.panel._formations = {62: "Ace", 63: "Ace Flip", 64: "Slot", 65: "Goal"}
        self.panel._refresh_formations()

    def tearDown(self) -> None:
        self.panel.deleteLater()

    def test_staging_hands_every_change_to_the_project(self) -> None:
        self.panel.stage_membership(ONE, 200, True)
        self.assertEqual(self.stored, self.panel.staged_changes())
        self.assertEqual(len(self.stored), 1)
        self.panel.stage_tag_move(FULL, 11, 40)
        self.assertEqual(self.stored, self.panel.staged_changes())
        self.assertEqual(len(self.stored), 2)

    def test_reverting_clears_the_project_too(self) -> None:
        self.panel.stage_membership(ONE, 200, True)
        self.assertTrue(self.stored)
        self.panel._revert()
        self.assertEqual(self.stored, ())

    def test_staging_a_trailer_replace_reaches_and_restores(self) -> None:
        from mod_editor.apf_studio.playbook_membership_qt import (
            ApfPlaybookMembershipPanel,
        )

        self.panel.stage_trailer_replace(FULL, 133, 7)
        self.assertEqual(len(self.stored), 1)
        change = self.stored[0]
        self.assertIsInstance(change, splb.TrailerReplace)
        self.assertEqual((change.formation_index, change.category_index), (133, 7))
        reopened = ApfPlaybookMembershipPanel(self.facade, lambda *_a: None)
        try:
            reopened._book = splb.parse_book(self.body, OUTER)
            reopened._plays = [f"Play {index}" for index in range(586)]
            reopened._formations = {62: "Ace", 133: "Gun: Straight"}
            reopened._restore_from_project()
            self.assertEqual(reopened._staged_trailers, {FULL: (133, 7)})
        finally:
            reopened.deleteLater()

    def test_staging_a_record_addition_bundles_trailer_and_plays(self) -> None:
        self.panel.stage_record_addition(4, 133, 7, (300, 301))
        kinds = sorted(type(change).__name__ for change in self.stored)
        self.assertEqual(
            kinds, ["MembershipChange", "MembershipChange", "TrailerReplace"]
        )

    def test_record_addition_refuses_a_populated_slot(self) -> None:
        with self.assertRaisesRegex(ValidationError, "already holds plays"):
            self.panel.stage_record_addition(FULL, 133, 7, (300,))

    def test_a_reopened_project_restores_the_staged_ticks(self) -> None:
        self.panel.stage_membership(FULL, 11, False, heir=41)
        self.panel.stage_membership(ONE, 200, True)
        self.panel.stage_tag_move(FOUR, 50, 51)
        saved = self.stored

        self.panel._clear_staged()
        self.assertEqual(self.panel.staged_changes(), ())

        self.panel._restore_from_project()
        self.assertEqual(self.panel.staged_changes(), saved)
        self.assertEqual(self.panel._staged_heirs[FULL][11], 41)
        self.assertEqual(self.panel._staged_moves[FOUR][50], 51)
        self.assertNotIn(11, self.panel._wanted_plays(FULL))
        self.assertIn(200, self.panel._wanted_plays(ONE))

    def test_edits_for_another_book_are_not_restored_here(self) -> None:
        self.stored = (splb.MembershipChange(130, FULL, 11, False, 41),)
        self.panel._restore_from_project()
        self.assertEqual(self.panel.staged_changes(), ())

    def test_refreshing_the_same_game_and_book_does_not_reread_the_catalog(
        self,
    ) -> None:
        """A refresh must not spend seconds re-reading MASTER for nothing."""

        self.panel._loaded_index = self.panel._index_0a()
        self.panel.book_picker.setCurrentIndex(
            self.panel.book_picker.findData(OUTER)
        )
        self.panel._loaded_index = self.panel._index_0a()
        self.stored = (splb.MembershipChange(OUTER, ONE, 200, True),)

        calls: list[str] = []
        self.panel.run_task = lambda *args: calls.append(str(args[0]))
        self.panel.set_context()

        self.assertEqual(calls, [])
        # It still picks up what the project gained while the panel was idle.
        self.assertEqual(self.panel.staged_changes(), self.stored)

    def test_a_playbooks_page_refresh_reaches_this_panel(self) -> None:
        """The panel used to load a book only when the dropdown changed."""

        from mod_editor.apf_studio.gui import InspectorCategoryPage

        source = inspect.getsource(InspectorCategoryPage.refresh)
        self.assertIn("playbook_membership", source)
        self.assertIn("set_context", source)


class EmptyBookRefusalTests(unittest.TestCase):
    """A book with nothing stored anywhere is refused, not shipped.

    Static count/get-nth returning 0/null for an empty record was never a proof
    that the director handles one gracefully, and Urianus's alpha.70 report says
    it does not: emptied formations produced out-of-book plays and personnel
    packages.  Emptying every populated record has no honest reading at all.
    """

    def setUp(self) -> None:
        self.body = _book_bytes()
        self.book = splb.parse_book(self.body, OUTER)

    def _clear(self, record_index: int) -> list[splb.MembershipChange]:
        return [
            splb.MembershipChange(OUTER, record_index, entry.play_index, False)
            for entry in self.book.records[record_index].entries
        ]

    def test_emptying_every_populated_record_is_refused(self) -> None:
        changes: list[splb.MembershipChange] = []
        for record_index in (FULL, FOUR, THREE, ONE):
            changes.extend(self._clear(record_index))
        with self.assertRaises(ValidationError) as caught:
            splb.compile_book(self.book, changes)
        message = str(caught.exception)
        self.assertIn("every populated formation", message)
        self.assertIn("out-of-book", message)

    def test_leaving_one_formation_populated_still_compiles(self) -> None:
        changes: list[splb.MembershipChange] = []
        for record_index in (FULL, FOUR, THREE):
            changes.extend(self._clear(record_index))
        compiled = splb.compile_book(self.book, changes)
        splb.verify_book(self.body, compiled.replacement, changes)
        self.assertEqual(compiled.report["records_emptied"], [FULL, FOUR, THREE])
        self.assertEqual(compiled.report["populated_records_remaining"], 1)

    def test_the_report_never_claims_an_emptied_record_is_runtime_safe(self) -> None:
        compiled = splb.compile_book(self.book, self._clear(FULL))
        claims = compiled.report["claims"]
        self.assertIs(claims["empty_record_returns_no_plays"], True)
        self.assertIs(claims["empty_record_runtime_safe"], False)
        self.assertIs(claims["empty_record_reported_out_of_book_calls"], True)
        untouched = splb.compile_book(
            self.book, [splb.MembershipChange(OUTER, ONE, 200, True)]
        )
        self.assertEqual(untouched.report["records_emptied"], [])
        self.assertIs(
            untouched.report["claims"]["empty_record_reported_out_of_book_calls"],
            False,
        )


class ProjectPayloadTests(unittest.TestCase):
    """Save Project has to carry Fine-tune Plays, and carry only selectors.

    Reported by Urianus against alpha.69 and again against alpha.70: the panel
    held the staged edits and nothing else did, so a saved project reopened with
    the playbook apparently untouched.
    """

    def test_a_membership_change_round_trips_through_its_payload(self) -> None:
        for change in (
            splb.MembershipChange(OUTER, FULL, 11, False, 41),
            splb.MembershipChange(OUTER, ONE, 200, True),
            splb.TagMove(OUTER, FULL, 11, 40),
        ):
            with self.subTest(change=change):
                payload = splb.encode_membership_payload(change)
                self.assertEqual(
                    splb.decode_membership_payload(payload, change.selector), change
                )
                self.assertEqual(
                    splb.change_from_mapping(splb.change_metadata(change)), change
                )

    def test_a_payload_carries_no_resource_bytes(self) -> None:
        payload = splb.encode_membership_payload(
            splb.MembershipChange(OUTER, FULL, 11, False, 41)
        )
        document = json.loads(payload.decode("utf-8"))
        self.assertEqual(document["schema"], splb.PAYLOAD_SCHEMA)
        self.assertEqual(
            set(document["change"]),
            {
                "change_kind",
                "outer_index",
                "record_index",
                "play_index",
                "member",
                "tag_heir",
            },
        )

    def test_a_payload_that_names_another_target_is_refused(self) -> None:
        change = splb.MembershipChange(OUTER, FULL, 11, False, 41)
        payload = splb.encode_membership_payload(change)
        other = splb.MembershipChange(OUTER, FULL, 12, False, 41)
        with self.assertRaises(ValidationError):
            splb.decode_membership_payload(payload, other.selector)

    def test_a_non_canonical_or_malformed_payload_is_refused(self) -> None:
        change = splb.MembershipChange(OUTER, FULL, 11, False, 41)
        selector = change.selector
        for payload in (
            b'{"schema":"' + splb.PAYLOAD_SCHEMA.encode() + b'","change":{}}\n',
            splb.encode_membership_payload(change).replace(b",", b", ", 1),
            b"not json",
            b'{"schema":"other/v1","change":{}}\n',
        ):
            with self.subTest(payload=payload[:32]):
                with self.assertRaises(ValidationError):
                    splb.decode_membership_payload(payload, selector)

    def test_the_project_archive_round_trips_one_staged_change(self) -> None:
        from mod_editor.apf_studio import project
        from mod_editor.apf_studio.models import Modification

        change = splb.MembershipChange(OUTER, FULL, 11, False, 41)
        payload = splb.encode_membership_payload(change)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            replacement = root / "membership.json"
            replacement.write_bytes(payload)
            modification = Modification(
                change.selector,
                splb.PROVIDER_KIND,
                replacement,
                hashlib.sha256(payload).hexdigest(),
                splb.change_metadata(change),
            )
            archive = project.save_project(
                root / "playbook.apf2k8mod",
                source_sha256="b" * 64,
                modifications=(modification,),
            )
            _document, loaded, _annotations = project.load_project(
                archive,
                expected_source_sha256="b" * 64,
                destination_dir=root / "loaded",
            )
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].asset_id, change.selector)
            self.assertEqual(loaded[0].kind, splb.PROVIDER_KIND)
            self.assertEqual(loaded[0].metadata, splb.change_metadata(change))
            self.assertEqual(
                splb.decode_membership_payload(
                    loaded[0].replacement_path.read_bytes(), change.selector
                ),
                change,
            )


@unittest.skipUnless(DISC_AVAILABLE, "extracted APF 0A not present")
class RealBookTests(unittest.TestCase):
    """Against the user's own game, not a fixture."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.book = splb.read_book(INDEX_PATH, OUTER)

    def test_every_populated_retail_record_obeys_the_counted_rule(self) -> None:
        populated = [r for r in self.book.records if r.populated]
        self.assertTrue(populated)
        for record in populated:
            self.assertTrue(splb.follows_tag_rule(record.entries))
            self.assertTrue(splb.retail_tag_shape(record.entries))

    def test_the_two_ace_records_prove_the_slots_are_authored(self) -> None:
        ace, flip = self.book.records[0], self.book.records[1]
        self.assertEqual(
            [(e.x, e.play_index) for e in ace.entries],
            [(e.x, e.play_index) for e in flip.entries],
        )
        self.assertEqual(
            sorted(i for i, e in enumerate(ace.entries) if e.tagged), [70, 71, 72, 73]
        )
        self.assertEqual(
            sorted(i for i, e in enumerate(flip.entries) if e.tagged), [0, 1, 2, 3]
        )

    def test_a_real_reassignment_changes_only_that_records_entry_region(self) -> None:
        source = self.book.records[0]
        holder = next(e.play_index for e in source.entries if e.y == 1)
        target = source.entries[0].play_index
        move = splb.TagMove(OUTER, 0, holder, target)
        compiled = splb.compile_book(self.book, [move])
        report = splb.verify_book(self.book.body, compiled.replacement, [move])

        before, after = self.book.body, compiled.replacement
        differing = [i for i in range(len(before)) if before[i] != after[i]]
        region = range(splb.RECORD_BASE, splb.RECORD_BASE + splb.ENTRY_BYTES)
        self.assertTrue(differing)
        self.assertTrue(all(offset in region for offset in differing))
        self.assertEqual(report["changed_records"], [0])
        self.assertEqual(len(after), len(before))

        rebuilt = splb.parse_book(after, OUTER).records[0]
        self.assertEqual(rebuilt.trailer, source.trailer)
        self.assertEqual(
            [(e.x, e.play_index) for e in rebuilt.entries],
            [(e.x, e.play_index) for e in source.entries],
        )
        self.assertEqual(_tags(rebuilt)[target], 1)
        self.assertNotIn(holder, _tags(rebuilt))
        self.assertTrue(splb.follows_tag_rule(rebuilt.entries))


class TrailerReplaceTests(unittest.TestCase):
    """Repoint a record's trailer so a book gains a pass-friendly 1TE/4WR set.

    The director resolves a requested personnel row through the book category
    mask at +0x7E04 and each record's word B; O-Ace lacks the Straight (01)
    package, so a pass-down request ladders down to 0-TE Flush personnel -- the
    observed WR-for-TE sub.  Giving the book a category-7 record is the data-side
    lever; these tests hold the writer to the whitelisted bytes only.
    """

    def setUp(self) -> None:
        self.body = _book_bytes()
        self.book = splb.parse_book(self.body, OUTER)

    def _compiled(self, changes) -> bytes:
        compiled = splb.compile_book(self.book, changes)
        splb.verify_book(self.body, compiled.replacement, changes)
        return compiled.replacement

    def test_retarget_rewrites_formation_category_and_word_b_only(self) -> None:
        change = splb.TrailerReplace(OUTER, FULL, 133, 7)
        after = self._compiled([change])
        trailer_at = splb.RECORD_BASE + FULL * splb.RECORD_STRIDE + splb.TRAILER_OFFSET
        before_a, before_b = struct.unpack_from(">2I", self.body, trailer_at)
        after_a, after_b = struct.unpack_from(">2I", after, trailer_at)
        self.assertEqual(after_a >> 24, 133)
        self.assertEqual((after_a >> 17) & 0x7F, 7)
        self.assertEqual(after_a & 0x0001FFFF, before_a & 0x0001FFFF)
        self.assertEqual(after_b, before_b | (1 << 7))
        mask_at = splb.BOOK_CATEGORY_MASK_OFFSET
        (before_mask,) = struct.unpack_from(">I", self.body, mask_at)
        (after_mask,) = struct.unpack_from(">I", after, mask_at)
        self.assertEqual(after_mask, before_mask | (1 << 7))
        differing = {
            i for i in range(len(self.body)) if self.body[i] != after[i]
        }
        whitelisted = set(range(trailer_at, trailer_at + 8)) | set(
            range(mask_at, mask_at + 4)
        )
        self.assertTrue(differing <= whitelisted, sorted(differing))
        self.assertIn(trailer_at, differing)
        self.assertIn(trailer_at + 7, differing)
        self.assertIn(mask_at + 3, differing)

    def test_a_no_op_retarget_is_refused(self) -> None:
        with self.assertRaisesRegex(ValidationError, "already lines up"):
            splb.compile_book(self.book, [splb.TrailerReplace(OUTER, FULL, 62, 3)])

    def test_bounds_are_enforced(self) -> None:
        with self.assertRaisesRegex(ValidationError, "MASTER formation"):
            splb.compile_book(
                self.book, [splb.TrailerReplace(OUTER, FULL, 163, 7)]
            )
        with self.assertRaisesRegex(ValidationError, "Personnel package"):
            splb.compile_book(
                self.book, [splb.TrailerReplace(OUTER, FULL, 133, 28)]
            )

    def test_a_forged_cde_drift_is_refused(self) -> None:
        change = splb.TrailerReplace(OUTER, FULL, 133, 7)
        compiled = splb.compile_book(self.book, [change])
        forged = bytearray(compiled.replacement)
        trailer_at = splb.RECORD_BASE + FULL * splb.RECORD_STRIDE + splb.TRAILER_OFFSET
        (after_a,) = struct.unpack_from(">I", forged, trailer_at)
        struct.pack_into(">I", forged, trailer_at, after_a | (1 << 14))
        with self.assertRaisesRegex(ValidationError, "trailer does not match"):
            splb.verify_book(self.body, bytes(forged), [change])

    def test_a_forged_word_b_bit_clear_is_refused(self) -> None:
        change = splb.TrailerReplace(OUTER, FULL, 133, 7)
        compiled = splb.compile_book(self.book, [change])
        forged = bytearray(compiled.replacement)
        trailer_at = (
            splb.RECORD_BASE + FULL * splb.RECORD_STRIDE + splb.TRAILER_OFFSET + 4
        )
        (after_b,) = struct.unpack_from(">I", forged, trailer_at)
        struct.pack_into(">I", forged, trailer_at, after_b & ~(1 << 3))
        with self.assertRaisesRegex(ValidationError, "trailer does not match"):
            splb.verify_book(self.body, bytes(forged), [change])

    def test_record_addition_fills_the_first_empty_slot(self) -> None:
        used = max(
            (r.record_index for r in self.book.records if r.populated), default=-1
        )
        slot = used + 1
        plays = [100, 101, 102, 103]
        changes = [
            splb.TrailerReplace(OUTER, slot, 133, 7),
            *(splb.MembershipChange(OUTER, slot, play, True) for play in plays),
        ]
        after = self._compiled(changes)
        record = splb.parse_book(after, OUTER).records[slot]
        self.assertEqual([e.play_index for e in record.entries], plays)
        self.assertEqual(record.formation_index, 133)
        self.assertEqual(record.category_index, 7)
        self.assertTrue(splb.follows_tag_rule(record.entries))

    def test_payload_round_trip(self) -> None:
        change = splb.TrailerReplace(OUTER, FULL, 133, 7)
        payload = splb.encode_membership_payload(change)
        decoded = splb.decode_membership_payload(payload, change.selector)
        self.assertEqual(decoded, change)

    @unittest.skipUnless(DISC_AVAILABLE, "extracted APF 0A not present")
    def test_retarget_retail_oace_into_the_01_package(self) -> None:
        """The Urianus fix against pristine retail: O-Ace's Ace record gains
        the Straight (01) package and only the whitelisted bytes change."""

        book = splb.read_book(INDEX_PATH, OUTER)
        ace = next(
            record
            for record in book.records
            if record.formation_index == 62 and record.populated
        )
        change = splb.TrailerReplace(OUTER, ace.record_index, 133, 7)
        compiled = splb.build_book_patch(INDEX_PATH, [change])
        claims = compiled.report["claims"]
        self.assertFalse(claims["trailers_untouched"])
        self.assertTrue(claims["trailer_cde_fields_preserved"])
        self.assertTrue(claims["book_category_mask_only_gained_bits"])
        self.assertFalse(claims["director_formation_choice_proved"])
        self.assertFalse(claims["runtime_lineup_after_replace_proved"])
        before, after = book.body, compiled.replacement
        trailer_at = (
            splb.RECORD_BASE + ace.record_index * splb.RECORD_STRIDE + splb.TRAILER_OFFSET
        )
        whitelisted = set(range(trailer_at, trailer_at + 8)) | set(
            range(splb.BOOK_CATEGORY_MASK_OFFSET, splb.BOOK_CATEGORY_MASK_OFFSET + 4)
        )
        differing = {i for i in range(len(before)) if before[i] != after[i]}
        self.assertTrue(differing <= whitelisted, sorted(differing))
        replaced = compiled.report["records_trailer_replaced"][0]
        self.assertEqual(replaced["formation_after"], 133)
        self.assertEqual(replaced["category_after"], 7)

    def test_honesty_claims_name_the_runtime_gap(self) -> None:
        compiled = splb.compile_book(
            self.book, [splb.TrailerReplace(OUTER, FULL, 133, 7)]
        )
        claims = compiled.report["claims"]
        self.assertTrue(claims["trailers_untouched"] is False)
        self.assertTrue(claims["trailer_cde_fields_preserved"])
        self.assertTrue(claims["director_formation_choice_proved"] is False)
        self.assertTrue(claims["runtime_lineup_after_replace_proved"] is False)
        self.assertTrue(claims["cpu_trailer_consumption_static_proved"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

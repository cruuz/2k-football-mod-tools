"""Moving a formation's tagged slots instead of refusing to touch them.

Every populated record in the fifteen retail books carries ``min(4, plays)``
tagged slots -- 209 records, zero exceptions -- and the slots are authored per
formation rather than falling out of entry order.  Three of them are the
formation's audibles -- the game writes a slot number into bits 12..10 at
``0x84864c78`` and runs that counter 0, 1, 2 per record -- and the fourth is
unexplained.  Either way the studio's rule is the same: never drop a slot,
never duplicate one, never invent a value the retail books do not use, but let
the user hand one to another play in the same formation.  These tests hold that
line from both ends -- the writer's, and a forged output the verifier has to
reject.
"""

from __future__ import annotations

import os
from pathlib import Path
import struct
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

    def test_a_move_naming_a_play_the_same_request_removes_is_refused(self) -> None:
        with self.assertRaisesRegex(ValidationError, "both removed"):
            splb.compile_book(
                self.book,
                [
                    splb.TagMove(OUTER, FULL, 11, 40),
                    splb.MembershipChange(OUTER, FULL, 40, False),
                ],
            )


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
        self.assertFalse(claims["cpu_behaviour_runtime_proved"])


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

        self.panel_copy = f"{panel.BOUNDARY}\n{panel.TAG_BOUNDARY}\n{panel.__doc__}"
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

    def test_the_copy_still_refuses_to_explain_the_fourth_slot(self) -> None:
        """Three slots are proved audibles; the fourth is not explained.

        The assign loop runs 0..2 and never writes slot 3, and the only place
        the executable tests for it is a generic bit-field clamp. Claiming a
        purpose for it would be exactly the overreach this product forbids.
        """

        for copy in (self.panel_prose, self.writer_prose):
            self.assertIn("not established", copy)
        self.assertIn("NOT proved", self.panel_copy)   # in-game CPU behaviour

    def test_the_copy_does_not_cite_the_disproved_glyph_mapper(self) -> None:
        """A disassembly showed 0x84a17298 never touches the glyph strings."""

        for copy in (self.panel_copy, self.writer_copy):
            self.assertNotIn("84a17298", copy.lower())

    def test_the_copy_no_longer_calls_the_slot_meaning_the_reason_to_refuse(self) -> None:
        self.assertNotIn("removing one is refused rather than guessed", self.panel_copy)
        self.assertIn("moved", self.panel_copy)


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
        # The offer quotes the same boundary text the panel shows everywhere else.
        self.assertIn("Urianus", asked.call_args[0][2])
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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

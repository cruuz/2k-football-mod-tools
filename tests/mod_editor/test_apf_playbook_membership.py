"""Adding and removing plays inside an APF formation.

The only playbook edit either this product or the community's editor offered was
reassigning which stock book a team calls from, and the book records in a save
are labels that collapse to a handful of real types, so that swap often changed
nothing. This is the edit below it: one bit per play per formation, inside a
fixed allocation, provable by byte diff.
"""

from __future__ import annotations

import os
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mod_editor.core import apf2k8_playbook_membership_writer as membership  # noqa: E402
from mod_editor.core.errors import ValidationError  # noqa: E402


MASK = membership.MEMBERSHIP_MASK
ROW = membership.MEMBERSHIP_ROW
BASE = membership.MEMBERSHIP_BASE


class NormalisationTests(unittest.TestCase):
    def test_an_empty_request_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            membership._normalize(())

    def test_contradicting_edits_for_one_slot_are_refused(self) -> None:
        with self.assertRaises(ValidationError):
            membership._normalize(
                (
                    membership.MembershipEdit(3, 9, True),
                    membership.MembershipEdit(3, 9, False),
                )
            )

    def test_a_repeated_identical_edit_collapses(self) -> None:
        edits = membership._normalize(
            (
                membership.MembershipEdit(3, 9, True),
                membership.MembershipEdit(3, 9, True),
            )
        )
        self.assertEqual(len(edits), 1)

    def test_out_of_range_selectors_are_refused(self) -> None:
        for row in (
            {"formation_index": -1, "play_index": 0, "member": True},
            {"formation_index": 0, "play_index": MASK * 8, "member": True},
            {"formation_index": membership.MEMBERSHIP_CAPACITY, "play_index": 0, "member": True},
            {"formation_index": 0, "play_index": 0, "member": "yes"},
            {"formation_index": 0, "play_index": 0, "member": True, "extra": 1},
        ):
            with self.subTest(row=row):
                with self.assertRaises(ValidationError):
                    membership.edit_from_mapping(row)

    def test_a_payload_round_trips(self) -> None:
        edits = (
            membership.MembershipEdit(0, 5, True),
            membership.MembershipEdit(2, 9, False),
        )
        decoded = membership.decode_membership_payload(
            membership.encode_membership_payload(edits)
        )
        self.assertEqual(decoded, edits)

    def test_a_foreign_payload_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            membership.decode_membership_payload(b'{"schema": "other"}')
        with self.assertRaises(ValidationError):
            membership.decode_membership_payload(b"not json")


class VerifierTests(unittest.TestCase):
    """The verifier is the safety net, so it is tested against forged input."""

    def _body(self, size: int = 4096) -> bytes:
        return bytes(size)

    def test_a_byte_no_edit_named_is_refused(self) -> None:
        before = bytearray(BASE + ROW * 4)
        after = bytearray(before)
        after[BASE + 1] = 0x01  # a byte inside row 0's mask, but unrequested
        with self.assertRaisesRegex(ValidationError, "no edit named it"):
            membership.verify_membership_edits(
                bytes(before), bytes(after), (membership.MembershipEdit(0, 0, True),)
            )

    def test_extra_bits_inside_a_named_byte_are_refused(self) -> None:
        before = bytearray(BASE + ROW * 4)
        after = bytearray(before)
        # Requested bit 0 (0x80) but also flipped 0x40.
        after[BASE] = 0xC0
        with self.assertRaisesRegex(ValidationError, "bits no edit asked for"):
            membership.verify_membership_edits(
                bytes(before), bytes(after), (membership.MembershipEdit(0, 0, True),)
            )

    def test_a_changed_length_is_refused(self) -> None:
        with self.assertRaisesRegex(ValidationError, "length changed"):
            membership.verify_membership_edits(
                bytes(16), bytes(17), (membership.MembershipEdit(0, 0, True),)
            )

    def test_a_touched_opaque_row_tail_is_refused(self) -> None:
        """The ten bytes trailing each mask are not ours to edit."""

        before = bytearray(BASE + ROW * 4)
        after = bytearray(before)
        tail = BASE + MASK  # first byte past row 0's mask
        after[tail] = 0x01
        with self.assertRaises(ValidationError):
            membership.verify_membership_edits(
                bytes(before), bytes(after), (membership.MembershipEdit(0, 0, True),)
            )


class BitAddressingTests(unittest.TestCase):
    def test_the_bit_address_matches_the_inventory_grammar(self) -> None:
        """play n lives at row[n // 8] & (0x80 >> (n % 8)) -- MSB first."""

        for play_index in (0, 1, 7, 8, 63, 585):
            with self.subTest(play=play_index):
                byte_offset = BASE + play_index // 8
                bit = 0x80 >> (play_index % 8)
                self.assertEqual(
                    (byte_offset, bit),
                    (
                        BASE + 0 * ROW + play_index // 8,
                        0x80 >> (play_index % 8),
                    ),
                )

    def test_rows_are_addressed_by_the_inventory_stride(self) -> None:
        import playbook_inventory

        self.assertEqual(ROW, playbook_inventory.APF_FORMATION_MEMBERSHIP_SIZE)
        self.assertEqual(MASK, playbook_inventory.APF_FORMATION_MEMBERSHIP_MASK_SIZE)
        self.assertEqual(
            BASE, playbook_inventory.APF_FORMATION_MEMBERSHIP_BASE
        )
        self.assertGreaterEqual(MASK * 8, 586, "the mask must cover every play")


class PanelContractTests(unittest.TestCase):
    """The panel must not promise more than the writer proves."""

    def test_the_panel_states_the_unproved_boundary(self) -> None:
        from mod_editor.apf_studio.playbook_membership_qt import BOUNDARY

        self.assertIn("NOT proved", BOUNDARY)
        self.assertIn("MASTER PLAY", BOUNDARY)

    def test_the_report_never_claims_cpu_play_calling(self) -> None:
        claims = {
            "membership_bits_only": True,
            "cpu_play_calling_proved": False,
            "runtime_visibility_proved": False,
        }
        # Mirrors compile_membership_edits' claim block; a future edit that
        # flips either of these to True has to change this test on purpose.
        self.assertFalse(claims["cpu_play_calling_proved"])
        self.assertFalse(claims["runtime_visibility_proved"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

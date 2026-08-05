"""Retail-free contract tests for APF save player and membership authoring."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

from mod_editor.apf_studio import save_roster_players as subject
from tests.test_apf_save_custom_team_appearance import synthetic_save, synthetic_stfs


def _relative(field: int, target: int) -> int:
    return (target + 1 - field) & 0xFFFFFFFF


def roster_save() -> bytes:
    data = bytearray(synthetic_save())
    player_start = 0x150
    player_pointer = 4 + 4
    struct.pack_into(">I", data, player_pointer, _relative(player_pointer, player_start))

    # The base fixture has one counted 42-player user team.  Give all counted
    # slots unique, aligned player pointers so membership validation is real.
    team_start = 0x0B8078
    team = team_start + 32 * subject.TEAM_STRIDE
    for slot in range(subject.TEAM_MEMBER_CAPACITY):
        field = team + slot * 4
        target = player_start + slot * subject.PLAYER_STRIDE
        struct.pack_into(">I", data, field, _relative(field, target))

    # Save ROST adds a four-byte prefix to the trailing root pointer fields.
    # Player 0 gets one private five-character allocation; all remaining
    # identity pointers share a legal zero-capacity empty allocation.
    private_text = len(data) - 32
    empty_text = len(data) - 2
    data[private_text : private_text + 12] = "Alpha".encode("utf-16-be") + b"\0\0"
    data[empty_text : empty_text + 2] = b"\0\0"
    for body_relative, target in (
        (0x140, private_text),
        (0x144, private_text),
        (0x148, private_text),
    ):
        field = 4 + body_relative
        struct.pack_into(">I", data, field, _relative(field, target))
    for player in range(subject.PLAYER_COUNT):
        record = player_start + player * subject.PLAYER_STRIDE
        for field_id, relative in subject.PLAYER_TEXT_FIELDS_BY_ID.items():
            field = record + relative
            target = private_text if (player, field_id) == (0, "first_name") else empty_text
            struct.pack_into(">I", data, field, _relative(field, target))

    # Exercise preservation of packed neighbors and the required position mirror.
    first = player_start
    data[first + 23] = 0x0B
    data[first + 35] = 0x01
    data[first + 52] = data[first + 53] = 4
    data[first + 0xBA] = 50
    return bytes(data)


class InventoryAndPatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = roster_save()
        self.document = subject.inspect_bytes(self.source)

    def test_complete_typed_inventory_and_text_ownership(self) -> None:
        self.assertEqual(len(subject.FIELDS), 149)
        self.assertEqual(sum(row.category == "base_rating" for row in subject.FIELDS), 31)
        self.assertEqual(sum(row.category == "ability" for row in subject.FIELDS), 77)
        self.assertEqual(sum(row.category == "ability_style" for row in subject.FIELDS), 5)
        self.assertNotIn("overall", subject.FIELDS_BY_ID)
        self.assertTrue(subject.FIELDS_BY_ID["position"].mirrored_parts)
        self.assertEqual(len(self.document.text_owner_map), 2_254 * 15)
        self.assertEqual(self.document.player_text_values(0)["first_name"], "Alpha")

    def test_packed_edits_preserve_shared_bits_and_both_position_mirrors(self) -> None:
        original = self.document.player_record(0)
        output, manifest = subject.make_patch(
            self.document,
            field_edits=(
                subject.PlayerFieldEdit(0, "jersey_number", 42),
                subject.PlayerFieldEdit(0, "position", 5),
                subject.PlayerFieldEdit(0, "weight_pounds", 210),
                subject.PlayerFieldEdit(0, "ability_qb_evade", 0),
                subject.PlayerFieldEdit(0, "rating_speed", 75),
            ),
        )
        parsed = subject.inspect_bytes(output)
        values = parsed.player_values(0)
        self.assertEqual(values["jersey_number"], 42)
        self.assertEqual(values["position"], 5)
        self.assertEqual(values["weight_pounds"], 210)
        self.assertEqual(values["ability_qb_evade"], 0)
        self.assertEqual(values["rating_speed"], 75)
        changed = parsed.player_record(0)
        self.assertEqual(changed[35] & 1, original[35] & 1)
        self.assertEqual(changed[23] & 0x0E, original[23] & 0x0E)
        self.assertEqual((changed[52], changed[53]), (5, 5))
        self.assertTrue(subject.verify_patch(self.document, output, manifest)["verified"])

    def test_fixed_allocation_player_text_edit_and_overflow(self) -> None:
        output, manifest = subject.make_patch(
            self.document,
            text_edits=(subject.PlayerTextEdit(0, "first_name", "Beta"),),
        )
        parsed = subject.inspect_bytes(output)
        self.assertEqual(parsed.player_text_values(0)["first_name"], "Beta")
        self.assertEqual(self.document.player_text_values(0)["first_name"], "Alpha")
        self.assertNotIn("Beta", json.dumps(manifest))
        with self.assertRaisesRegex(subject.SaveRosterPlayerError, "at most 5"):
            subject.make_patch(
                self.document,
                text_edits=(subject.PlayerTextEdit(0, "first_name", "Longer"),),
            )

    def test_membership_swap_preserves_counts_uniqueness_and_multiset(self) -> None:
        output, manifest = subject.make_patch(
            self.document,
            membership_swaps=(subject.MembershipSwap(32, 0, 32, 41),),
        )
        parsed = subject.inspect_bytes(output)
        before = {(row.team_index, row.roster_slot): row.player_index for row in self.document.memberships}
        after = {(row.team_index, row.roster_slot): row.player_index for row in parsed.memberships}
        self.assertEqual(after[(32, 0)], before[(32, 41)])
        self.assertEqual(after[(32, 41)], before[(32, 0)])
        self.assertEqual(sorted(after.values()), sorted(before.values()))
        self.assertTrue(subject.verify_patch(self.document, output, manifest)["verified"])

    def test_unknown_noop_overlap_and_unowned_tamper_fail_closed(self) -> None:
        with self.assertRaisesRegex(subject.SaveRosterPlayerError, "unknown"):
            subject.make_patch(
                self.document,
                field_edits=(subject.PlayerFieldEdit(0, "overall", 99),),
            )
        with self.assertRaisesRegex(subject.SaveRosterPlayerError, "already equals"):
            subject.make_patch(
                self.document,
                field_edits=(subject.PlayerFieldEdit(0, "jersey_number", 0),),
            )
        output, manifest = subject.make_patch(
            self.document,
            field_edits=(subject.PlayerFieldEdit(0, "jersey_number", 12),),
        )
        tampered = bytearray(output)
        tampered[-100] ^= 1
        forged = json.loads(json.dumps(manifest))
        forged["output"]["sha256"] = hashlib.sha256(tampered).hexdigest()
        forged["output"]["changed_byte_count"] += 1
        with self.assertRaisesRegex(subject.SaveRosterPlayerError, "outside authorized"):
            subject.verify_patch(self.document, bytes(tampered), forged)


class FileAndContainerTests(unittest.TestCase):
    def test_signed_stfs_extracts_and_writes_verified_raw_handoff(self) -> None:
        raw = roster_save()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "signed.CON"
            output = root / "Roster-edited.ROS"
            source.write_bytes(synthetic_stfs(raw))
            document = subject.inspect_save(source)
            self.assertTrue(document.signed_container)
            receipt = subject.write_new_save(
                document,
                output,
                field_edits=(subject.PlayerFieldEdit(0, "jersey_number", 12),),
            )
            self.assertTrue(receipt.verification_passed)
            self.assertTrue(receipt.external_reinjection_required)
            self.assertTrue(receipt.output_is_raw_payload)
            self.assertEqual(output.read_bytes()[:4], raw[:4])
            self.assertEqual(subject.inspect_save(output).player_values(0)["jersey_number"], 12)

    def test_source_change_and_existing_destination_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "Roster.ROS"
            output = root / "new.ROS"
            source.write_bytes(roster_save())
            document = subject.inspect_save(source)
            changed = bytearray(source.read_bytes())
            changed[-100] ^= 1
            source.write_bytes(changed)
            with self.assertRaisesRegex(subject.SaveRosterPlayerError, "changed after"):
                subject.write_new_save(
                    document,
                    output,
                    field_edits=(subject.PlayerFieldEdit(0, "jersey_number", 12),),
                )
            self.assertFalse(output.exists())

            source.write_bytes(roster_save())
            document = subject.inspect_save(source)
            output.write_bytes(b"keep")
            with self.assertRaisesRegex(subject.SaveRosterPlayerError, "refusing to overwrite"):
                subject.write_new_save(
                    document,
                    output,
                    field_edits=(subject.PlayerFieldEdit(0, "jersey_number", 12),),
                )
            self.assertEqual(output.read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main()

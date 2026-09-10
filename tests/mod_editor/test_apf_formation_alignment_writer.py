"""APF MASTER formation alignment writer: bytes only, no runtime claim."""

from __future__ import annotations

import json
from pathlib import Path
import struct
import unittest

from mod_editor.core.apf2k8_formation_alignment_writer import (
    APF_CATEGORY_BASE,
    APF_CATEGORY_ROLE_OFFSET,
    APF_CATEGORY_SIZE,
    APF_FORMATION_DEFAULT_CATEGORY_OFFSET,
    APF_FORMATION_ELIGIBLE_ORDER_OFFSET,
    APF_FORMATION_ELIGIBLE_ORDER_SIZE,
    APF_FORMATION_NO_SLOT,
    APF_FORMATION_SLOT_COUNT,
    APF_FORMATION_SLOT_ENTRY_SIZE,
    APF_FORMATION_SLOT_ORDER_OFFSET,
    APF_FORMATION_SLOT_ORDER_SIZE,
    APF_FORMATION_SLOT_TABLE_OFFSET,
    HONESTY,
    FormationAlignmentChange,
    SlotAlignment,
    alignment_ranking_permutation,
    alignment_selector,
    build_formation_alignment_patch,
    category_depth_order,
    category_slot_role_depth,
    compile_formation_alignments,
    decode_alignment_payload,
    encode_alignment_payload,
    formation_record_offset,
    formation_slot_entry_offset,
    permute_formation_slots,
    read_formation_alignment,
    read_formation_default_category,
    read_formation_eligible_order,
    read_formation_slot_order,
    swap_formation_slots,
    verify_formation_alignment_patch,
)
from mod_editor.core.apf2k8_package_map_writer import (
    APF_FORMATION_BASE,
    APF_FORMATION_COUNT_OFFSET,
    APF_FORMATION_SIZE,
    APF_MASTER_BODY_SIZE,
)
from mod_editor.core.errors import ValidationError


I_LOAD_INDEX = 10
I_LOAD_HEAVY_INDEX = 11
GUN_SPLIT_SPREAD_INDEX = 120
GUN_EMPTY_OPEN_INDEX = 137

# Retail bytes, dumped from the disc during the 2026-08-28 investigation.
RETAIL_I_LOAD_SLOT_ORDER = (0, 9, 10, 8, 1, 4, 3, 5, 2, 6, 7)
RETAIL_I_LOAD_ELIGIBLE_ORDER = (10, 7, 8, 6, 9)
RETAIL_HEAVY_SLOT_ORDER = (0, 6, 10, 8, 1, 4, 3, 5, 2, 7, 9)
RETAIL_HEAVY_ELIGIBLE_ORDER = (10, 9, 8, 7, 6)
# permutation[new_slot] = old_slot for I Load -> I Load Heavy.
I_LOAD_TO_HEAVY_PERMUTATION = (0, 1, 2, 3, 4, 5, 9, 6, 8, 7, 10)


def _synthetic_master(
    *,
    formation_count: int = 3,
    category_count: int = 2,
) -> bytes:
    body = bytearray(APF_MASTER_BODY_SIZE)
    struct.pack_into(">I", body, APF_FORMATION_COUNT_OFFSET, formation_count)
    struct.pack_into(">I", body, 0x3C, category_count)
    pool = 0x22384
    for index in range(formation_count):
        record = APF_FORMATION_BASE + index * APF_FORMATION_SIZE
        encoded = f"Formation {index}".encode("utf-16be") + b"\0\0"
        body[pool : pool + len(encoded)] = encoded
        struct.pack_into(">i", body, record, (pool - record) + 1)
        pool += len(encoded)
        # +0x05 is four times a category index in retail.
        body[record + APF_FORMATION_DEFAULT_CATEGORY_OFFSET] = 4 * (
            index % category_count
        )
        start = record + APF_FORMATION_ELIGIBLE_ORDER_OFFSET
        body[start : start + APF_FORMATION_ELIGIBLE_ORDER_SIZE] = bytes(
            (10, 7, 8, 6, 9)
        )
        start = record + APF_FORMATION_SLOT_ORDER_OFFSET
        body[start : start + APF_FORMATION_SLOT_ORDER_SIZE] = bytes(
            (0, 9, 10, 8, 1, 4, 3, 5, 2, 6, 7)
        )
        for slot in range(APF_FORMATION_SLOT_COUNT):
            entry = SlotAlignment(
                0x0003 + slot * 0x10,
                (100 * slot + index, 200 * slot, -100 * slot),
                (-10 * slot, -20 * slot, -30 * slot),
            )
            start = (
                record
                + APF_FORMATION_SLOT_TABLE_OFFSET
                + slot * APF_FORMATION_SLOT_ENTRY_SIZE
            )
            body[start : start + APF_FORMATION_SLOT_ENTRY_SIZE] = entry.to_bytes()
    # Category 0 mimics retail "5 Wide": five role-9 slots with ordinals 3,1,0,2,4.
    five_wide = (0, 5, 37, 6, 7, 39, 105, 41, 9, 73, 137)
    start = APF_CATEGORY_BASE + APF_CATEGORY_ROLE_OFFSET
    body[start : start + APF_FORMATION_SLOT_COUNT] = bytes(five_wide)
    if category_count > 1:
        queens = (0, 5, 37, 6, 7, 39, 73, 41, 9, 11, 10)
        start = APF_CATEGORY_BASE + APF_CATEGORY_SIZE + APF_CATEGORY_ROLE_OFFSET
        body[start : start + APF_FORMATION_SLOT_COUNT] = bytes(queens)
    return bytes(body)


class OffsetTests(unittest.TestCase):
    def test_slot_entry_offsets_match_the_proved_instruction_offsets(self) -> None:
        # 0x84A9B914 reads x[0] at +0x20 + slot*14 and y[0] at +0x26 + slot*14.
        for index in (0, 10, 137):
            base = formation_record_offset(index)
            for slot in range(APF_FORMATION_SLOT_COUNT):
                entry = formation_slot_entry_offset(index, slot)
                self.assertEqual(entry, base + 0x1E + slot * 14)
                self.assertEqual(entry + 2, base + 0x20 + slot * 14)
                self.assertEqual(entry + 8, base + 0x26 + slot * 14)

    def test_record_offsets_use_the_declared_table(self) -> None:
        self.assertEqual(formation_record_offset(0), APF_FORMATION_BASE)
        self.assertEqual(
            formation_record_offset(1), APF_FORMATION_BASE + APF_FORMATION_SIZE
        )

    def test_slot_table_fills_the_record_tail_exactly(self) -> None:
        self.assertEqual(
            APF_FORMATION_SLOT_TABLE_OFFSET
            + APF_FORMATION_SLOT_COUNT * APF_FORMATION_SLOT_ENTRY_SIZE,
            APF_FORMATION_SIZE,
        )

    def test_bad_indices_are_refused(self) -> None:
        with self.assertRaises(ValidationError):
            formation_record_offset(-1)
        with self.assertRaises(ValidationError):
            formation_record_offset(176)
        with self.assertRaises(ValidationError):
            formation_slot_entry_offset(0, 11)


class SlotAlignmentTests(unittest.TestCase):
    def test_round_trip_is_byte_exact(self) -> None:
        entry = SlotAlignment(0x00B3, (-613, 615, -615), (-219, -219, -213))
        self.assertEqual(len(entry.to_bytes()), APF_FORMATION_SLOT_ENTRY_SIZE)
        self.assertEqual(SlotAlignment.from_bytes(entry.to_bytes()), entry)

    def test_position_id_is_the_tag_high_nibble(self) -> None:
        self.assertEqual(SlotAlignment(0x00B3, (0, 0, 0), (0, 0, 0)).position_id, 11)
        self.assertEqual(SlotAlignment(0x0063, (0, 0, 0), (0, 0, 0)).position_id, 6)

    def test_strict_types(self) -> None:
        with self.assertRaises(ValidationError):
            SlotAlignment(0x10000, (0, 0, 0), (0, 0, 0))
        with self.assertRaises(ValidationError):
            SlotAlignment(0, (0, 0), (0, 0, 0))
        with self.assertRaises(ValidationError):
            SlotAlignment(0, (0, 0, 40000), (0, 0, 0))
        with self.assertRaises(ValidationError):
            SlotAlignment(0, (0, 0, "1"), (0, 0, 0))  # type: ignore[arg-type]
        with self.assertRaises(ValidationError):
            SlotAlignment(0, (0, 0, True), (0, 0, 0))  # type: ignore[arg-type]


class ReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.body = _synthetic_master()

    def test_reads_eleven_entries(self) -> None:
        rows = read_formation_alignment(self.body, 1)
        self.assertEqual(len(rows), APF_FORMATION_SLOT_COUNT)
        self.assertEqual(rows[3].x[0], 300 + 1)

    def test_reads_both_order_lists(self) -> None:
        self.assertEqual(
            read_formation_slot_order(self.body, 0), RETAIL_I_LOAD_SLOT_ORDER
        )
        self.assertEqual(
            read_formation_eligible_order(self.body, 0), RETAIL_I_LOAD_ELIGIBLE_ORDER
        )

    def test_default_category_is_the_stored_byte_over_four(self) -> None:
        self.assertEqual(read_formation_default_category(self.body, 0), 0)
        self.assertEqual(read_formation_default_category(self.body, 1), 1)

    def test_out_of_range_formation_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            read_formation_alignment(self.body, 3)

    def test_short_body_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            read_formation_alignment(self.body[:-1], 0)


class CategoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.body = _synthetic_master()

    def test_role_and_depth_split_at_bit_five(self) -> None:
        self.assertEqual(category_slot_role_depth(self.body, 0, 6), (9, 3))
        self.assertEqual(category_slot_role_depth(self.body, 0, 7), (9, 1))
        self.assertEqual(category_slot_role_depth(self.body, 0, 8), (9, 0))
        self.assertEqual(category_slot_role_depth(self.body, 0, 9), (9, 2))
        self.assertEqual(category_slot_role_depth(self.body, 0, 10), (9, 4))

    def test_depth_order_lists_slots_by_stored_ordinal(self) -> None:
        self.assertEqual(category_depth_order(self.body, 0, 9), (8, 7, 9, 6, 10))
        self.assertEqual(category_depth_order(self.body, 1, 9), (8, 7, 6))

    def test_bad_category_or_slot_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            category_slot_role_depth(self.body, 2, 0)
        with self.assertRaises(ValidationError):
            category_slot_role_depth(self.body, 0, 11)


class PermutationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.body = _synthetic_master()

    def test_permutation_moves_entries_and_remaps_both_lists(self) -> None:
        before = read_formation_alignment(self.body, 0)
        change = permute_formation_slots(self.body, 0, I_LOAD_TO_HEAVY_PERMUTATION)
        self.assertEqual(change.slots[6], before[9])
        self.assertEqual(change.slots[7], before[6])
        self.assertEqual(change.slots[9], before[7])
        # Retail's own I Load -> I Load Heavy list rewrite.
        self.assertEqual(change.slot_order, RETAIL_HEAVY_SLOT_ORDER)
        self.assertEqual(change.eligible_order, RETAIL_HEAVY_ELIGIBLE_ORDER)

    def test_identity_permutation_is_a_no_op_change(self) -> None:
        change = permute_formation_slots(self.body, 0, tuple(range(11)))
        self.assertEqual(change.slots, read_formation_alignment(self.body, 0))
        with self.assertRaises(ValidationError):
            compile_formation_alignments(self.body, [change])

    def test_non_permutations_are_refused(self) -> None:
        with self.assertRaises(ValidationError):
            permute_formation_slots(self.body, 0, (0, 0, 2, 3, 4, 5, 6, 7, 8, 9, 10))
        with self.assertRaises(ValidationError):
            permute_formation_slots(self.body, 0, tuple(range(10)))
        with self.assertRaises(ValidationError):
            permute_formation_slots(self.body, 0, (0,) * 11)

    def test_swap_helper_builds_the_same_change(self) -> None:
        swapped = swap_formation_slots(self.body, 0, [(6, 8), (7, 9)])
        expected = permute_formation_slots(
            self.body, 0, (0, 1, 2, 3, 4, 5, 8, 9, 6, 7, 10)
        )
        self.assertEqual(swapped, expected)

    def test_swap_refuses_reused_or_degenerate_pairs(self) -> None:
        with self.assertRaises(ValidationError):
            swap_formation_slots(self.body, 0, [(6, 6)])
        with self.assertRaises(ValidationError):
            swap_formation_slots(self.body, 0, [(6, 8), (8, 9)])
        with self.assertRaises(ValidationError):
            swap_formation_slots(self.body, 0, [])
        with self.assertRaises(ValidationError):
            swap_formation_slots(self.body, 0, [(6, 11)])

    def test_ranking_permutation_lines_ordinals_up_with_fill_order(self) -> None:
        # Category 0 is a 5 Wide clone: ordinals 3,1,0,2,4 on slots 6..10.
        permutation = alignment_ranking_permutation(self.body, 0, 9)
        self.assertEqual(permutation, (0, 1, 2, 3, 4, 5, 8, 7, 9, 6, 10))
        change = permute_formation_slots(self.body, 0, permutation)
        before = read_formation_alignment(self.body, 0)
        self.assertEqual(change.slots[6], before[8])
        self.assertEqual(change.slots[10], before[10])

    def test_ranking_permutation_needs_two_slots_of_the_role(self) -> None:
        with self.assertRaises(ValidationError):
            alignment_ranking_permutation(self.body, 0, 0)

    def test_no_slot_sentinel_passes_through_the_order_lists(self) -> None:
        body = bytearray(_synthetic_master())
        start = formation_record_offset(0) + APF_FORMATION_ELIGIBLE_ORDER_OFFSET
        body[start : start + APF_FORMATION_ELIGIBLE_ORDER_SIZE] = bytes(
            (APF_FORMATION_NO_SLOT,) * APF_FORMATION_ELIGIBLE_ORDER_SIZE
        )
        change = permute_formation_slots(
            bytes(body), 0, I_LOAD_TO_HEAVY_PERMUTATION
        )
        self.assertEqual(
            change.eligible_order,
            (APF_FORMATION_NO_SLOT,) * APF_FORMATION_ELIGIBLE_ORDER_SIZE,
        )


class PatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.body = _synthetic_master()
        self.change = permute_formation_slots(self.body, 1, I_LOAD_TO_HEAVY_PERMUTATION)

    def test_patch_touches_only_the_named_formation(self) -> None:
        patched = build_formation_alignment_patch(self.body, self.change)
        verify_formation_alignment_patch(self.body, patched, self.change)
        base = formation_record_offset(1)
        for index, (left, right) in enumerate(
            zip(self.body, patched, strict=True)
        ):
            if left != right:
                self.assertGreaterEqual(index, base + APF_FORMATION_ELIGIBLE_ORDER_OFFSET)
                self.assertLess(index, base + APF_FORMATION_SIZE)

    def test_patch_keeps_the_body_size(self) -> None:
        patched = build_formation_alignment_patch(self.body, self.change)
        self.assertEqual(len(patched), len(self.body))

    def test_verifier_catches_drift_outside_the_region(self) -> None:
        patched = bytearray(build_formation_alignment_patch(self.body, self.change))
        patched[0x100] ^= 0xFF
        with self.assertRaises(ValidationError):
            verify_formation_alignment_patch(self.body, bytes(patched), self.change)

    def test_verifier_catches_a_wrong_entry_inside_the_region(self) -> None:
        patched = bytearray(build_formation_alignment_patch(self.body, self.change))
        patched[formation_slot_entry_offset(1, 6) + 2] ^= 0xFF
        with self.assertRaises(ValidationError):
            verify_formation_alignment_patch(self.body, bytes(patched), self.change)

    def test_verifier_catches_a_wrong_order_byte(self) -> None:
        patched = bytearray(build_formation_alignment_patch(self.body, self.change))
        patched[formation_record_offset(1) + APF_FORMATION_SLOT_ORDER_OFFSET] = 3
        with self.assertRaises(ValidationError):
            verify_formation_alignment_patch(self.body, bytes(patched), self.change)


class CompileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.body = _synthetic_master()

    def test_compile_applies_every_change_and_reports_ranges(self) -> None:
        changes = [
            permute_formation_slots(self.body, 0, I_LOAD_TO_HEAVY_PERMUTATION),
            swap_formation_slots(self.body, 2, [(6, 8)]),
        ]
        body, ranges = compile_formation_alignments(self.body, changes)
        self.assertEqual(len(body), len(self.body))
        self.assertEqual(len(ranges), 6)
        for change in changes:
            self.assertEqual(
                read_formation_alignment(body, change.formation_index), change.slots
            )
            self.assertEqual(
                read_formation_slot_order(body, change.formation_index),
                change.slot_order,
            )
        changed = {
            index
            for index, (left, right) in enumerate(zip(self.body, body, strict=True))
            if left != right
        }
        allowed = set()
        for start, end in ranges:
            allowed.update(range(start, end))
        self.assertTrue(changed <= allowed)
        self.assertTrue(changed)

    def test_duplicate_formations_are_refused(self) -> None:
        change = swap_formation_slots(self.body, 0, [(6, 8)])
        with self.assertRaises(ValidationError):
            compile_formation_alignments(self.body, [change, change])

    def test_empty_batch_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            compile_formation_alignments(self.body, [])

    def test_untouched_formations_stay_byte_identical(self) -> None:
        change = swap_formation_slots(self.body, 1, [(6, 8)])
        body, _ranges = compile_formation_alignments(self.body, [change])
        for index in (0, 2):
            self.assertEqual(
                self.body[
                    formation_record_offset(index) : formation_record_offset(index)
                    + APF_FORMATION_SIZE
                ],
                body[
                    formation_record_offset(index) : formation_record_offset(index)
                    + APF_FORMATION_SIZE
                ],
            )


class PayloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.body = _synthetic_master()
        self.change = swap_formation_slots(self.body, 1, [(6, 8)])

    def test_round_trip(self) -> None:
        raw = encode_alignment_payload(self.change)
        decoded = decode_alignment_payload(raw, self.change.selector)
        self.assertEqual(decoded, self.change)

    def test_selector_shape(self) -> None:
        self.assertEqual(
            alignment_selector(11), "apf:alignment:apf:playbook:180:0:f11"
        )

    def test_bad_payloads_fail_closed(self) -> None:
        raw = encode_alignment_payload(self.change)
        with self.assertRaises(ValidationError):
            decode_alignment_payload(b"not json", self.change.selector)
        with self.assertRaises(ValidationError):
            decode_alignment_payload(raw, "apf:alignment:apf:playbook:180:0:f99")
        broken = json.loads(raw)
        broken["schema"] = "other/v1"
        with self.assertRaises(ValidationError):
            decode_alignment_payload(
                json.dumps(broken).encode("utf-8"), self.change.selector
            )
        broken = json.loads(raw)
        broken["slots"][0]["x"] = [0, 0]
        with self.assertRaises(ValidationError):
            decode_alignment_payload(
                json.dumps(broken).encode("utf-8"), self.change.selector
            )
        broken = json.loads(raw)
        broken["slot_order"][0] = 42
        with self.assertRaises(ValidationError):
            decode_alignment_payload(
                json.dumps(broken).encode("utf-8"), self.change.selector
            )
        with self.assertRaises(ValidationError):
            decode_alignment_payload(
                b'{"schema": 1, "schema": 2}', self.change.selector
            )

    def test_change_rejects_short_lists(self) -> None:
        with self.assertRaises(ValidationError):
            FormationAlignmentChange(
                0, self.change.slots[:10], self.change.slot_order, self.change.eligible_order
            )
        with self.assertRaises(ValidationError):
            FormationAlignmentChange(
                0, self.change.slots, self.change.slot_order[:10], self.change.eligible_order
            )


class HonestyTests(unittest.TestCase):
    def test_copy_makes_no_runtime_or_depth_chart_claim(self) -> None:
        lowered = HONESTY.casefold()
        self.assertIn("unproved", lowered)
        self.assertIn("route", lowered)
        self.assertNotIn("fixes", lowered)
        self.assertNotIn("3rd-and-long", lowered)


_APF_DISC_0A = Path(
    "/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A"
)


@unittest.skipUnless(
    _APF_DISC_0A.is_file() and not _APF_DISC_0A.is_symlink(),
    "APF retail 0A not present at the Storage disc path",
)
class RealApfFormationAlignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from mod_editor.core.apf2k8_playbook_route_writer import read_master_play_body

        cls.raw = read_master_play_body(_APF_DISC_0A)

    def test_retail_i_load_and_heavy_order_lists(self) -> None:
        self.assertEqual(
            read_formation_slot_order(self.raw, I_LOAD_INDEX),
            RETAIL_I_LOAD_SLOT_ORDER,
        )
        self.assertEqual(
            read_formation_eligible_order(self.raw, I_LOAD_INDEX),
            RETAIL_I_LOAD_ELIGIBLE_ORDER,
        )
        self.assertEqual(
            read_formation_slot_order(self.raw, I_LOAD_HEAVY_INDEX),
            RETAIL_HEAVY_SLOT_ORDER,
        )
        self.assertEqual(
            read_formation_eligible_order(self.raw, I_LOAD_HEAVY_INDEX),
            RETAIL_HEAVY_ELIGIBLE_ORDER,
        )

    def test_i_load_permutation_reproduces_retail_heavy_order_lists(self) -> None:
        change = permute_formation_slots(
            self.raw, I_LOAD_INDEX, I_LOAD_TO_HEAVY_PERMUTATION
        )
        self.assertEqual(
            change.slot_order, read_formation_slot_order(self.raw, I_LOAD_HEAVY_INDEX)
        )
        self.assertEqual(
            change.eligible_order,
            read_formation_eligible_order(self.raw, I_LOAD_HEAVY_INDEX),
        )

    def test_i_load_and_heavy_share_one_personnel_category(self) -> None:
        load = read_formation_default_category(self.raw, I_LOAD_INDEX)
        heavy = read_formation_default_category(self.raw, I_LOAD_HEAVY_INDEX)
        self.assertEqual(load, heavy)
        roles = [
            category_slot_role_depth(self.raw, load, slot)
            for slot in range(APF_FORMATION_SLOT_COUNT)
        ]
        # QB, two tackles, centre, two guards, a third tackle, two tight ends,
        # fullback, halfback.
        self.assertEqual(
            roles,
            [
                (0, 0),
                (5, 0),
                (5, 1),
                (6, 0),
                (7, 0),
                (7, 1),
                (5, 2),
                (8, 0),
                (8, 1),
                (11, 0),
                (10, 0),
            ],
        )

    def test_every_retail_slot_order_is_a_permutation_of_slots(self) -> None:
        from mod_editor.core.apf2k8_package_map_writer import apf_formation_count

        for index in range(apf_formation_count(self.raw)):
            order = read_formation_slot_order(self.raw, index)
            self.assertEqual(sorted(order), list(range(APF_FORMATION_SLOT_COUNT)))
            eligible = read_formation_eligible_order(self.raw, index)
            for value in eligible:
                self.assertTrue(
                    value == APF_FORMATION_NO_SLOT
                    or 0 <= value < APF_FORMATION_SLOT_COUNT
                )

    def test_gun_split_spread_ranking_permutation_swaps_wr1_and_wr3(self) -> None:
        category = read_formation_default_category(self.raw, GUN_SPLIT_SPREAD_INDEX)
        self.assertEqual(category_depth_order(self.raw, category, 9), (8, 7, 6))
        permutation = alignment_ranking_permutation(
            self.raw, GUN_SPLIT_SPREAD_INDEX, 9
        )
        self.assertEqual(permutation, (0, 1, 2, 3, 4, 5, 8, 7, 6, 9, 10))

    def test_gun_empty_open_ranking_permutation(self) -> None:
        category = read_formation_default_category(self.raw, GUN_EMPTY_OPEN_INDEX)
        self.assertEqual(category_depth_order(self.raw, category, 9), (8, 7, 9, 6, 10))
        permutation = alignment_ranking_permutation(self.raw, GUN_EMPTY_OPEN_INDEX, 9)
        self.assertEqual(permutation, (0, 1, 2, 3, 4, 5, 8, 7, 9, 6, 10))

    def test_compile_on_retail_touches_only_the_named_records(self) -> None:
        changes = [
            permute_formation_slots(
                self.raw, I_LOAD_INDEX, I_LOAD_TO_HEAVY_PERMUTATION
            ),
            swap_formation_slots(self.raw, GUN_EMPTY_OPEN_INDEX, [(6, 8), (7, 9)]),
        ]
        body, ranges = compile_formation_alignments(self.raw, changes)
        self.assertEqual(len(body), len(self.raw))
        changed = {
            index
            for index, (left, right) in enumerate(zip(self.raw, body, strict=True))
            if left != right
        }
        allowed = set()
        for start, end in ranges:
            allowed.update(range(start, end))
        self.assertTrue(changed <= allowed)
        for index in (I_LOAD_HEAVY_INDEX, 0, 62, 106):
            start = formation_record_offset(index)
            self.assertEqual(
                self.raw[start : start + APF_FORMATION_SIZE],
                body[start : start + APF_FORMATION_SIZE],
            )


if __name__ == "__main__":
    unittest.main()

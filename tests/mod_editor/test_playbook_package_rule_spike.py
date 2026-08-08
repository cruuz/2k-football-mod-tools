"""G1/G2 package-rule RE spike drives shipped layout + inspector types."""

from __future__ import annotations

from pathlib import Path
import unittest

from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_playbook_inspector import (
    ASSIGNMENT_COUNT,
    BODY_SIZE,
    FORMATION_BASE,
    FORMATION_SIZE,
    PLAY_BASE,
    PLAY_SIZE,
    RESOURCE_HEADER_SIZE,
    FormationPlayLink,
    Nfl2k5Playbook,
    PlaybookAssignment,
    PlaybookCategory,
    PlaybookChain,
    PlaybookFormation,
    PlaybookNode,
    PlaybookPlay,
)
from mod_editor.core.playbook_package_rule_spike import (
    O0308_ASSET_ID,
    O0308_PACK_OFFSET,
    PACKAGE_MAP_OFFSET_IN_FORMATION,
    PACKAGE_MAP_SIZE,
    assignment_body_offset,
    build_formation_link_table_copy_patch,
    build_formation_package_map_patch,
    census_g1_dime_vs_nickel,
    descriptor_body_offset,
    formation_package_map_body_offset,
    layout_pins,
    read_formation_package_map,
    spike_g1_dime_ilb,
    spike_g2_ace_te,
    verify_formation_link_table_copy_patch,
    verify_formation_package_map_patch,
)

_O0308_PACK = Path(
    "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
)
_O0308_RESOURCE_SIZE = RESOURCE_HEADER_SIZE + BODY_SIZE


def _book_with_named_packages() -> Nfl2k5Playbook:
    def nodes(first_op: int) -> tuple[PlaybookNode, ...]:
        return (
            PlaybookNode(0, first_op, 0x00, "010203040506", "0100010203040506"),
            PlaybookNode(1, 0x04, 0x02, "0708090a0b0c", "04020708090a0b0c"),
        )

    def play(
        index: int, name: str, family_id: int, first_ops: tuple[int, ...]
    ) -> PlaybookPlay:
        assignments = tuple(
            PlaybookAssignment(slot, 0x1000 + slot + index * 16, slot)
            for slot in range(ASSIGNMENT_COUNT)
        )
        # chain_start_index equals slot for synthetic map
        return PlaybookPlay(
            index,
            name,
            family_id << 6,
            family_id,
            ("Offense", "Defense")[family_id],
            assignments,
        )

    # Defense Dime play: slots 4–6 use 0x1b like the offline role census
    dime_ops = tuple(0x01 if s < 4 else 0x1B for s in range(11))
    ace_ops = tuple(0x01 for _ in range(11))
    dime_play = play(0, "Dime Cover 2", 1, dime_ops)
    ace_play = play(1, "Ace Twins Right", 0, ace_ops)
    # Rebuild with chain starts that book.chain can resolve
    chains = (
        PlaybookChain(0, 2, nodes(0x1B)),
        PlaybookChain(1, 3, nodes(0x01)),
    )
    dime_assignments = tuple(
        PlaybookAssignment(slot, 0xB000 + slot, 0 if slot >= 4 else 1)
        for slot in range(11)
    )
    ace_assignments = tuple(
        PlaybookAssignment(slot, 0xA000 + slot, 1) for slot in range(11)
    )
    dime_play = PlaybookPlay(
        0, "Dime Cover 2", 1 << 6, 1, "Defense", dime_assignments
    )
    ace_play = PlaybookPlay(
        1, "Ace Twins Right", 0, 0, "Offense", ace_assignments
    )
    formations = (
        PlaybookFormation(
            0,
            "Dime",
            (FormationPlayLink(0, 0, 1, (1 << 9) | 0),),
        ),
        PlaybookFormation(
            1,
            "Ace",
            (FormationPlayLink(0, 1, 0, (0 << 9) | 1),),
        ),
    )
    return Nfl2k5Playbook(
        asset_id=O0308_ASSET_ID,
        outer_index=308,
        book_name="Synthetic o0308-class",
        formations=formations,
        plays=(dime_play, ace_play),
        categories=(PlaybookCategory(0, "Test"),),
        chains=chains,
        node_count=4,
    )


class LayoutPinTests(unittest.TestCase):
    def test_assignment_offsets_match_shipped_play_layout(self) -> None:
        # play 3 slot 5 → PLAY_BASE + 3*0x60 + 8 + 5*8
        self.assertEqual(
            assignment_body_offset(3, 5),
            PLAY_BASE + 3 * PLAY_SIZE + 8 + 5 * 8,
        )
        self.assertEqual(descriptor_body_offset(3), PLAY_BASE + 3 * PLAY_SIZE + 4)

    def test_layout_pins_include_fixture_identity(self) -> None:
        pins = layout_pins()
        self.assertEqual(pins["o0308_asset_id"], O0308_ASSET_ID)
        self.assertEqual(pins["o0308_pack_offset"], O0308_PACK_OFFSET)
        self.assertEqual(pins["play_base"], PLAY_BASE)


class G1G2SpikeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.book = _book_with_named_packages()

    def test_g1_spike_reports_dime_slots_with_body_offsets(self) -> None:
        result = spike_g1_dime_ilb(self.book)
        self.assertEqual(result.bug_id, "G1")
        self.assertEqual(result.status, "re_spike")
        self.assertEqual(result.fixture_pack_offset, O0308_PACK_OFFSET)
        self.assertIn("Dime", result.matching_formations)
        self.assertTrue(result.slot_snapshots)
        for snap in result.slot_snapshots:
            self.assertIn(snap.slot, (4, 5, 6))
            self.assertEqual(
                snap.body_offset, assignment_body_offset(snap.play_index, snap.slot)
            )
        gate = result.next_offline_writer_gate.casefold()
        self.assertTrue(
            "package-map" in gate or "package map" in gate or "assignment" in gate
        )
        self.assertNotEqual(result.status, "offline_writer_proved")

    def test_g2_spike_reports_ace_skill_slots(self) -> None:
        result = spike_g2_ace_te(self.book)
        self.assertEqual(result.bug_id, "G2")
        self.assertEqual(result.status, "re_spike")
        self.assertIn("Ace", result.matching_formations)
        self.assertTrue(any(s.slot in (3, 6, 7, 8, 9) for s in result.slot_snapshots))
        self.assertIn(O0308_ASSET_ID, result.fixture_asset_id)


class PackageMapLayoutTests(unittest.TestCase):
    def test_package_map_offset_formula(self) -> None:
        self.assertEqual(
            formation_package_map_body_offset(24),
            FORMATION_BASE + 24 * FORMATION_SIZE + PACKAGE_MAP_OFFSET_IN_FORMATION,
        )
        pins = layout_pins()
        self.assertEqual(pins["package_map_size"], PACKAGE_MAP_SIZE)
        self.assertEqual(
            pins["package_map_offset_in_formation"], PACKAGE_MAP_OFFSET_IN_FORMATION
        )

    def test_reject_non_permutation_map(self) -> None:
        # Minimal fake resource: only length+magic checked before map validate
        # on build — use real path if available else skip build path.
        if not _O0308_PACK.is_file():
            self.skipTest("o0308 pack fixture not present")
        raw = _O0308_PACK.read_bytes()[
            O0308_PACK_OFFSET : O0308_PACK_OFFSET + _O0308_RESOURCE_SIZE
        ]
        with self.assertRaises(ValidationError):
            build_formation_package_map_patch(raw, 24, [0] * 11)
        with self.assertRaises(ValidationError):
            build_formation_package_map_patch(raw, 24, list(range(10)))  # short


@unittest.skipUnless(_O0308_PACK.is_file(), "o0308 pack fixture not present")
class RealO0308PackageMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pack = _O0308_PACK.read_bytes()
        cls.raw = pack[O0308_PACK_OFFSET : O0308_PACK_OFFSET + _O0308_RESOURCE_SIZE]
        assert len(cls.raw) == _O0308_RESOURCE_SIZE
        assert cls.raw[:4] == b"PLAY"

    def test_census_assignment_only_gate_failed_package_map_differs(self) -> None:
        census = census_g1_dime_vs_nickel(self.raw)
        self.assertEqual(census.assignment_only_gate, "failed")
        self.assertTrue(census.package_map_differs)
        self.assertEqual(
            list(census.nickel_package_map), [4, 5, 0, 2, 3, 1, 7, 8, 9, 6, 10]
        )
        self.assertEqual(
            list(census.dime_package_map), [5, 0, 2, 3, 1, 7, 8, 9, 4, 6, 10]
        )
        # Role 4: Nickel slot-index 0 → Dime slot-index 8
        role4 = next(d for d in census.role_slot_deltas if d[0] == 4)
        self.assertEqual(role4, (4, 0, 8))
        self.assertGreaterEqual(len(census.shared_play_indices), 1)
        self.assertTrue(census.shared_plays_assignment_identical)
        self.assertIn("package map", census.primary_offline_delta.casefold())

    def test_all_formation_maps_are_permutations(self) -> None:
        from mod_editor.core.playbook_package_rule_spike import (
            read_all_formation_package_maps,
        )
        from mod_editor.core.nfl2k5_playbook_inspector import parse_playbook_resource

        book = parse_playbook_resource(self.raw)
        maps = read_all_formation_package_maps(self.raw)
        self.assertEqual(len(maps), len(book.formations))
        for fi, pmap in maps.items():
            self.assertEqual(sorted(pmap), list(range(11)), msg=f"formation {fi}")

    def test_ace_shares_offense_package_map(self) -> None:
        from mod_editor.core.nfl2k5_playbook_inspector import parse_playbook_resource

        book = parse_playbook_resource(self.raw)
        ace_i = next(f.index for f in book.formations if f.name == "Ace")
        split_i = next(f.index for f in book.formations if f.name == "Split Pro")
        ace_map = read_formation_package_map(self.raw, ace_i)
        split_map = read_formation_package_map(self.raw, split_i)
        self.assertEqual(ace_map, split_map)
        self.assertEqual(list(ace_map), [0, 8, 6, 9, 7, 10, 1, 4, 3, 5, 2])

    def test_package_map_patch_dime_to_nickel_offline_proved(self) -> None:
        nickel = read_formation_package_map(self.raw, 23)
        dime_before = read_formation_package_map(self.raw, 24)
        self.assertNotEqual(nickel, dime_before)

        patch = build_formation_package_map_patch(self.raw, 24, nickel)
        self.assertEqual(patch.status, "offline_writer_proved")
        self.assertEqual(patch.old_map, dime_before)
        self.assertEqual(patch.new_map, nickel)
        self.assertGreater(patch.changed_byte_count, 0)
        self.assertLessEqual(patch.changed_byte_count, PACKAGE_MAP_SIZE)

        # Independent verifier
        verify_formation_package_map_patch(
            self.raw, patch.raw_resource, 24, nickel
        )
        self.assertEqual(
            read_formation_package_map(patch.raw_resource, 24), nickel
        )
        # Source unchanged identity
        self.assertEqual(
            read_formation_package_map(self.raw, 24), dime_before
        )
        # Other formations untouched
        self.assertEqual(
            read_formation_package_map(patch.raw_resource, 23), nickel
        )

    def test_g2_link_table_copy_ace_from_quads_offline_proved(self) -> None:
        from mod_editor.core.nfl2k5_playbook_inspector import parse_playbook_resource

        book = parse_playbook_resource(self.raw)
        ace_i = next(f.index for f in book.formations if f.name == "Ace")
        quads_i = next(f.index for f in book.formations if f.name == "Quads")
        before_links = len(book.formations[ace_i].play_links)
        donor_links = len(book.formations[quads_i].play_links)
        self.assertNotEqual(before_links, donor_links)

        patch = build_formation_link_table_copy_patch(self.raw, ace_i, quads_i)
        self.assertEqual(patch.status, "offline_writer_proved")
        self.assertEqual(patch.target_link_count_before, before_links)
        self.assertEqual(patch.target_link_count_after, donor_links)
        self.assertGreater(patch.changed_byte_count, 0)
        verify_formation_link_table_copy_patch(
            self.raw, patch.raw_resource, ace_i, quads_i
        )
        # Package map of Ace must be unchanged (menu-only writer)
        self.assertEqual(
            read_formation_package_map(patch.raw_resource, ace_i),
            read_formation_package_map(self.raw, ace_i),
        )


if __name__ == "__main__":
    unittest.main()

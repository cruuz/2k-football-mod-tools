"""G1/G2 package-rule RE spike drives shipped layout + inspector types."""

from __future__ import annotations

import unittest

from mod_editor.core.nfl2k5_playbook_inspector import (
    ASSIGNMENT_COUNT,
    PLAY_BASE,
    PLAY_SIZE,
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
    assignment_body_offset,
    descriptor_body_offset,
    layout_pins,
    spike_g1_dime_ilb,
    spike_g2_ace_te,
)


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
        self.assertIn("assignment", result.next_offline_writer_gate.casefold())
        self.assertNotEqual(result.status, "offline_writer_proved")

    def test_g2_spike_reports_ace_skill_slots(self) -> None:
        result = spike_g2_ace_te(self.book)
        self.assertEqual(result.bug_id, "G2")
        self.assertEqual(result.status, "re_spike")
        self.assertIn("Ace", result.matching_formations)
        self.assertTrue(any(s.slot in (3, 6, 7, 8, 9) for s in result.slot_snapshots))
        self.assertIn(O0308_ASSET_ID, result.fixture_asset_id)


if __name__ == "__main__":
    unittest.main()

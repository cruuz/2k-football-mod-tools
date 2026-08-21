"""G1/G2 package-rule RE spike drives shipped layout + inspector types."""

from __future__ import annotations

from pathlib import Path
import re
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
    build_g1_dime_from_nickel_package_map_pack,
    build_g2_ace_from_quads_link_table_pack,
    census_g1_dime_vs_nickel,
    descriptor_body_offset,
    formation_package_map_body_offset,
    layout_pins,
    read_formation_package_map,
    spike_g1_dime_ilb,
    spike_g2_ace_te,
    verify_formation_link_table_copy_patch,
    verify_formation_package_map_patch,
    verify_g1_dime_from_nickel_package_map_pack,
    verify_g2_ace_from_quads_link_table_pack,
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
    def test_apf_package_map_offset_is_not_the_2k5_offset(self) -> None:
        from mod_editor.core.playbook_package_rule_spike import (
            APF_ACE_PACKAGE_MAP,
            APF_FORMATION_SIZE,
            APF_PACKAGE_MAP_OFFSET_IN_FORMATION,
            APF_PACKAGE_MAP_ROLE_8_TE_9_WR_PROVED,
            APF_PACKAGE_MAP_ROLE_LEGEND_PROVED,
            APF_PACKAGE_MAP_ROLE_TE,
            APF_PACKAGE_MAP_ROLE_WR3,
            APF_ROLE_TO_ROSTER_FIRST_11,
            APF_ROLE_TO_ROSTER_TABLE_VA,
            APF_ROSTER_POSITION_TE,
            APF_ROSTER_POSITION_WR,
        )

        self.assertEqual(APF_PACKAGE_MAP_OFFSET_IN_FORMATION, 0x11)
        self.assertEqual(APF_FORMATION_SIZE, 0xB8)
        self.assertNotEqual(
            APF_PACKAGE_MAP_OFFSET_IN_FORMATION, PACKAGE_MAP_OFFSET_IN_FORMATION
        )
        self.assertFalse(APF_PACKAGE_MAP_ROLE_LEGEND_PROVED)
        self.assertTrue(APF_PACKAGE_MAP_ROLE_8_TE_9_WR_PROVED)
        self.assertEqual(APF_ROLE_TO_ROSTER_TABLE_VA, 0x820FC320)
        self.assertEqual(APF_ROLE_TO_ROSTER_FIRST_11[APF_PACKAGE_MAP_ROLE_TE], APF_ROSTER_POSITION_TE)
        self.assertEqual(APF_ROLE_TO_ROSTER_FIRST_11[APF_PACKAGE_MAP_ROLE_WR3], APF_ROSTER_POSITION_WR)
        self.assertEqual(APF_ACE_PACKAGE_MAP[2], APF_PACKAGE_MAP_ROLE_TE)
        self.assertEqual(APF_ACE_PACKAGE_MAP[3], APF_PACKAGE_MAP_ROLE_WR3)
        self.assertEqual(sorted(APF_ACE_PACKAGE_MAP), list(range(11)))
        from mod_editor.core.playbook_package_rule_spike import (
            APF_ACE_EMPTY_IS_WR3_TE_SWAP_OF_ACE,
            APF_ACE_EMPTY_PACKAGE_MAP,
            APF_ACE_VS_ACE_EMPTY_SLOT_DELTAS,
            APF_FORMATION_BASE,
            APF_G12_PACK_EXPERIMENTAL,
            APF_G12_PACK_USES_ACE_EMPTY_AS_SOURCE,
            APF_MASTER_BODY_SIZE,
            APF_USER_3RD_AND_LONG_DATA_WRITER_EXISTS,
            APF_WR3_TE_PACKAGE_SUB_PROVED,
            swap_apf_package_map_wr3_te,
        )

        self.assertEqual(APF_FORMATION_BASE, 0x0244)
        self.assertEqual(APF_MASTER_BODY_SIZE, 0x2C750)
        self.assertFalse(APF_ACE_EMPTY_IS_WR3_TE_SWAP_OF_ACE)
        self.assertFalse(APF_WR3_TE_PACKAGE_SUB_PROVED)
        self.assertTrue(APF_G12_PACK_EXPERIMENTAL)
        self.assertFalse(APF_G12_PACK_USES_ACE_EMPTY_AS_SOURCE)
        self.assertFalse(APF_USER_3RD_AND_LONG_DATA_WRITER_EXISTS)
        self.assertEqual(APF_ACE_EMPTY_PACKAGE_MAP[2], APF_PACKAGE_MAP_ROLE_TE)
        self.assertEqual(APF_ACE_EMPTY_PACKAGE_MAP[3], APF_PACKAGE_MAP_ROLE_WR3)
        self.assertEqual(
            APF_ACE_VS_ACE_EMPTY_SLOT_DELTAS, ((9, 6, 7), (10, 7, 6))
        )
        self.assertNotEqual(
            APF_ACE_EMPTY_PACKAGE_MAP,
            swap_apf_package_map_wr3_te(APF_ACE_PACKAGE_MAP),
        )
        from mod_editor.core.playbook_package_rule_spike import (
            APF_3RD_AND_LONG_PLAY_CHOICE_PROVED,
            APF_DOWN_NAME_TABLE_VA,
            APF_DOWN_NAMES,
            APF_DOWN_THIRD,
            APF_GAME_STATE_DOWN_OFFSET,
            APF_GAME_STATE_YTG_OFFSET,
            APF_PACKAGE_MAP_BUILDER_SLOT_LOOP_PROVED,
        )

        self.assertTrue(APF_PACKAGE_MAP_BUILDER_SLOT_LOOP_PROVED)
        self.assertFalse(APF_3RD_AND_LONG_PLAY_CHOICE_PROVED)
        self.assertEqual(APF_GAME_STATE_DOWN_OFFSET, 0x254)
        self.assertEqual(APF_GAME_STATE_YTG_OFFSET, 0x25C)
        self.assertEqual(APF_DOWN_THIRD, 3)
        self.assertEqual(APF_DOWN_NAMES[APF_DOWN_THIRD], "Third Down")
        self.assertEqual(APF_DOWN_NAME_TABLE_VA, 0x820E57C8)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_INGAME_PLAY_PICKER_VA,
            APF_PLAYCALL_BY_TYPE_UI_VA,
            APF_PLAY_TYPE_UI_TABLE_VA,
            APF_SITUATION_PLAYCALL_TAB_OFFSET,
            APF_SITUATION_WORD0_OFFSET,
        )

        self.assertEqual(APF_PLAYCALL_BY_TYPE_UI_VA, 0x84A472D0)
        self.assertEqual(APF_PLAY_TYPE_UI_TABLE_VA, 0x84E4D810)
        self.assertEqual(APF_INGAME_PLAY_PICKER_VA, 0x8486CE88)
        self.assertEqual(APF_SITUATION_WORD0_OFFSET, 0)
        self.assertEqual(APF_SITUATION_PLAYCALL_TAB_OFFSET, 0x2BC)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_FIVE_WIDE_SKILL_CELL_LOW,
            APF_ROLE_ELIGIBILITY_MASK_TE,
            APF_ROLE_ELIGIBILITY_MASK_WR,
            APF_ROLE_ELIGIBILITY_WORD_TABLE_VA,
            APF_SITUATION_GET_DOWN_VA,
            APF_SITUATION_VTABLE8_QUERY_VA,
        )

        self.assertEqual(APF_SITUATION_GET_DOWN_VA, 0x84AD92E0)
        self.assertEqual(APF_SITUATION_VTABLE8_QUERY_VA, 0x84B694A8)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_SCRIPT_FN_TAG_TABLE_COUNT,
            APF_SCRIPT_FN_TAG_TABLE_VA,
            APF_SCRIPT_SITUATION_LEAF_VA,
        )

        self.assertEqual(APF_SCRIPT_SITUATION_LEAF_VA, 0x8499E3E8)
        self.assertEqual(APF_SCRIPT_FN_TAG_TABLE_VA, 0x844DBE00)
        self.assertEqual(APF_SCRIPT_FN_TAG_TABLE_COUNT, 18472)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_ELIGIBILITY_AND_FN_VA,
            APF_ELIGIBILITY_AND_LIVE_INSN_VA,
            APF_ELIGIBILITY_AND_LOOP_VA,
            APF_PDATA_FUNCTION_COUNT,
            APF_PDATA_SECTION_VA,
            APF_SCRIPT_ONFIELD_ROLE_OPCODE_VA,
        )

        self.assertEqual(APF_PDATA_SECTION_VA, 0x844DBE00)
        self.assertEqual(APF_PDATA_FUNCTION_COUNT, 18472)
        self.assertEqual(APF_SCRIPT_FN_TAG_TABLE_VA, APF_PDATA_SECTION_VA)
        self.assertEqual(APF_ELIGIBILITY_AND_LOOP_VA, 0x848623E8)
        self.assertEqual(APF_ELIGIBILITY_AND_LIVE_INSN_VA, 0x84862580)
        self.assertEqual(APF_ELIGIBILITY_AND_FN_VA, 0x8485E7F8)
        self.assertEqual(APF_SCRIPT_ONFIELD_ROLE_OPCODE_VA, 0x846302D8)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_INGAME_PLAY_FETCH_VA,
            APF_PLAYTYPE_FILTER_TABLE_VA,
            APF_SITUATION_PLAYTYPE_FILTER_OFFSET,
            APF_SPLB_RECORD_FOR_PLAY_VA,
        )

        self.assertEqual(APF_SPLB_RECORD_FOR_PLAY_VA, 0x84A89EA8)
        self.assertEqual(APF_INGAME_PLAY_FETCH_VA, 0x848699D8)
        self.assertEqual(APF_SITUATION_PLAYTYPE_FILTER_OFFSET, 0x1F8)
        self.assertEqual(APF_PLAYTYPE_FILTER_TABLE_VA, 0x84DCB2A8)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_DRCT_IFF_LOAD_VA,
            APF_DRCT_REGISTRY_TABLE_VA,
            APF_DRCT_RESOURCE_LOAD_VA,
            APF_DRCT_TYPE_CTOR_VA,
            APF_DRCT_TYPE_HASH,
            APF_DRCT_TYPE_INSERT_VA,
            APF_DRCT_TYPE_OBJECT_VA,
            APF_DRCT_TYPE_ROW_VA,
            APF_DRCT_TYPE_VTABLE_VA,
            APF_PLAYCALL_BOOK_OFFSET,
            APF_PLAYCALL_BOOK_SETTER_VA,
            APF_PLAYCALL_OBJECT_GLOBAL_VA,
            APF_PLAYCALL_OBJECT_REGISTER_VA,
            APF_SPLB_ENTRY_TO_MASTER_PLAY_VA,
        )

        self.assertEqual(APF_SPLB_ENTRY_TO_MASTER_PLAY_VA, 0x84A8BA80)
        self.assertEqual(APF_DRCT_TYPE_HASH, 0xED586383)
        self.assertEqual(APF_DRCT_TYPE_ROW_VA, 0x84D1B834)
        self.assertEqual(APF_DRCT_TYPE_CTOR_VA, 0x8466B964)
        self.assertEqual(APF_DRCT_TYPE_OBJECT_VA, 0x84D1B830)
        self.assertEqual(APF_DRCT_TYPE_VTABLE_VA, 0x82003F90)
        self.assertEqual(APF_DRCT_TYPE_INSERT_VA, 0x8466B998)
        self.assertEqual(APF_DRCT_IFF_LOAD_VA, 0x8466AF70)
        self.assertEqual(APF_DRCT_RESOURCE_LOAD_VA, 0x8468DA70)
        self.assertEqual(APF_DRCT_REGISTRY_TABLE_VA, 0x84D1B7D0)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_DRCT_POST_RELOC_FIXED_WALK_VA,
            APF_DRCT_RELOCATOR_VA,
            APF_DRCT_RELOC_FIXED_SLOT_BYTES,
            APF_DRCT_RELOC_FIXED_SLOT_LOOP_VA,
            APF_DRCT_RELOC_INSN_DIR_ADDI_VA,
            APF_DRCT_RELOC_INSN_DIR_VA,
            APF_DRCT_VTABLE0_VA,
        )

        self.assertEqual(APF_DRCT_RELOCATOR_VA, 0x8466A818)
        self.assertEqual(APF_DRCT_RELOC_FIXED_SLOT_LOOP_VA, 0x8466A97C)
        self.assertEqual(APF_DRCT_RELOC_FIXED_SLOT_BYTES, 868)
        self.assertEqual(APF_DRCT_RELOC_INSN_DIR_VA, 0x8466A984)
        self.assertEqual(APF_DRCT_RELOC_INSN_DIR_ADDI_VA, 0x8466A994)
        self.assertEqual(APF_DRCT_VTABLE0_VA, 0x8466B8B0)
        self.assertEqual(APF_DRCT_POST_RELOC_FIXED_WALK_VA, 0x8466AAE0)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_DRCT_AUX_INDEX_VA,
            APF_DRCT_FIXED_CHILD_INDEX_VA,
            APF_DRCT_FIXED_RECORD_CONSUMER_VA,
            APF_DRCT_ROOT_TABLE_VA,
            APF_DRCT_STRING_INDEX_VA,
        )

        self.assertEqual(APF_DRCT_ROOT_TABLE_VA, 0x84F16EE0)
        self.assertEqual(APF_DRCT_FIXED_CHILD_INDEX_VA, 0x8466ABC0)
        self.assertEqual(APF_DRCT_STRING_INDEX_VA, 0x8466AF28)
        self.assertEqual(APF_DRCT_AUX_INDEX_VA, 0x8466AF60)
        self.assertEqual(APF_DRCT_FIXED_RECORD_CONSUMER_VA, 0x8466AC38)
        self.assertEqual(APF_PLAYCALL_OBJECT_GLOBAL_VA, 0x851A2780)
        self.assertEqual(APF_PLAYCALL_BOOK_OFFSET, 0x20)
        self.assertEqual(APF_PLAYCALL_OBJECT_REGISTER_VA, 0x8493D968)
        self.assertEqual(APF_PLAYCALL_BOOK_SETTER_VA, 0x8493E180)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_JUMP_TABLE_PICKER_CASE,
            APF_JUMP_TABLE_PICKER_FN_VA,
            APF_PICKER_PLAYCALL_LOAD_VA,
            APF_PLAYCALL_BOOK_READER_VA,
        )

        self.assertEqual(APF_PLAYCALL_BOOK_READER_VA, 0x84867938)
        self.assertEqual(APF_PICKER_PLAYCALL_LOAD_VA, 0x8470C2C4)
        self.assertEqual(APF_JUMP_TABLE_PICKER_FN_VA, 0x8470BF18)
        self.assertEqual(APF_JUMP_TABLE_PICKER_CASE, 2)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_JUMP_TABLE_MODE_2_FN_VA,
            APF_JUMP_TABLE_MODE_2_LI_VA,
            APF_JUMP_TABLE_MODE_2_OBJECT_VA,
            APF_JUMP_TABLE_MODE_WRAPPER_VA,
            APF_JUMP_TABLE_NESTED_VA,
            APF_PICKER_PLAYCALL_UI_LOAD_VA,
            APF_PICKER_UI_FN_VA,
            APF_PICKER_UI_PLAYCALL_LOAD_VA,
            APF_SPLB_FIND_BOOK_GLOBAL_VA,
        )

        self.assertEqual(APF_JUMP_TABLE_MODE_WRAPPER_VA, 0x84712498)
        self.assertEqual(APF_JUMP_TABLE_MODE_2_FN_VA, 0x84716310)
        self.assertEqual(APF_JUMP_TABLE_MODE_2_LI_VA, 0x847163D4)
        self.assertEqual(APF_JUMP_TABLE_MODE_2_OBJECT_VA, 0x8502C670)
        self.assertEqual(APF_JUMP_TABLE_NESTED_VA, 0x8470C248)
        self.assertEqual(APF_PICKER_UI_FN_VA, 0x84A25270)
        self.assertEqual(APF_PICKER_UI_PLAYCALL_LOAD_VA, 0x84A254E0)
        self.assertEqual(APF_PICKER_PLAYCALL_UI_LOAD_VA, 0x84892DF8)
        self.assertEqual(APF_SPLB_FIND_BOOK_GLOBAL_VA, 0x8520CDE0)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_PLAYCALL_SIBLING_OFFSET,
            APF_PLAYCALL_UI_FIELD_COPY_VA,
            APF_PLAYCALL_UI_OBJECT_VA,
            APF_SPLB_FIND_BOOK_GETTER_VA,
            APF_SPLB_FIND_BOOK_INIT_STW_VA,
            APF_SPLB_FIND_BOOK_INIT_TABLE_VA,
            APF_SPLB_FIND_BOOK_INIT_VA,
        )

        self.assertEqual(APF_SPLB_FIND_BOOK_INIT_VA, 0x84A139D0)
        self.assertEqual(APF_SPLB_FIND_BOOK_INIT_STW_VA, 0x84A139F4)
        self.assertEqual(APF_SPLB_FIND_BOOK_GETTER_VA, 0x846F09D0)
        self.assertEqual(APF_SPLB_FIND_BOOK_INIT_TABLE_VA, 0x820DC630)
        self.assertEqual(APF_PLAYCALL_SIBLING_OFFSET, 0x1C)
        self.assertEqual(APF_PLAYCALL_UI_OBJECT_VA, 0x85212D30)
        self.assertEqual(APF_PLAYCALL_UI_FIELD_COPY_VA, 0x84A283E0)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_PLAYCALL_SHADOW_BITMASK_VA,
            APF_PLAYCALL_SHADOW_FILL_VA,
            APF_PLAYCALL_SHADOW_VA,
        )

        self.assertEqual(APF_PLAYCALL_SHADOW_VA, 0x8516C908)
        self.assertEqual(APF_PLAYCALL_SHADOW_FILL_VA, 0x84887E18)
        self.assertEqual(APF_PLAYCALL_SHADOW_BITMASK_VA, 0x84884EA0)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_BOOK_FORMATION_GETTER_VA,
            APF_BOOK_RESOLVE_HELPER_VA,
            APF_LIVE_MASTER_GETTER_VA,
            APF_LIVE_MASTER_SETTER_VA,
            APF_LIVE_MASTER_SLOT_OFFSET,
            APF_LIVE_MASTER_SLOT_VA,
            APF_PLAYCALL_SLOT_INSTALL_VA,
            APF_PLAYCALL_TYPE_INIT_STW20_VA,
            APF_PLAYCALL_TYPE_INIT_VA,
            APF_PLAYCALL_TYPE_OBJECT_A_VA,
            APF_PLAYCALL_TYPE_OBJECT_B_VA,
        )

        self.assertEqual(APF_PLAYCALL_TYPE_OBJECT_A_VA, 0x850F1218)
        self.assertEqual(APF_PLAYCALL_TYPE_OBJECT_B_VA, 0x850F1260)
        self.assertEqual(APF_PLAYCALL_TYPE_INIT_VA, 0x847C6DA8)
        self.assertEqual(APF_PLAYCALL_TYPE_INIT_STW20_VA, 0x847C6DF8)
        self.assertEqual(APF_PLAYCALL_SLOT_INSTALL_VA, 0x84AD0048)
        self.assertEqual(APF_LIVE_MASTER_GETTER_VA, 0x849FD6A8)
        self.assertEqual(APF_LIVE_MASTER_SETTER_VA, 0x849FD6C8)
        self.assertEqual(APF_LIVE_MASTER_SLOT_VA, 0x84F3F7D8)
        self.assertEqual(APF_LIVE_MASTER_SLOT_OFFSET, 0x2C)
        self.assertEqual(APF_BOOK_RESOLVE_HELPER_VA, 0x8486CD80)
        self.assertEqual(APF_BOOK_FORMATION_GETTER_VA, 0x84A89E08)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_DRCT_PROPERTY_TABLE_VA,
            APF_LIVE_MASTER_BIND_VA,
            APF_LIVE_MASTER_SPLB_SELECT_VA,
            APF_SPLB_RAM_INDEX_VA,
            APF_SPLB_RAM_STRIDE,
            APF_SPLB_RAM_TABLE_VA,
            APF_SPLB_SELECT_WORD0_CMP_VA,
        )

        self.assertEqual(APF_LIVE_MASTER_BIND_VA, 0x849D4000)
        self.assertEqual(APF_LIVE_MASTER_SPLB_SELECT_VA, 0x849D6208)
        self.assertEqual(APF_SPLB_RAM_INDEX_VA, 0x849FCF60)
        self.assertEqual(APF_SPLB_RAM_TABLE_VA, 0x851D9660)
        self.assertEqual(APF_SPLB_RAM_STRIDE, 32288)
        self.assertEqual(APF_SPLB_SELECT_WORD0_CMP_VA, 0x849D81EC)
        self.assertEqual(APF_DRCT_PROPERTY_TABLE_VA, 0x84EE65C0)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_SPLB_SELECT_INIT_VA,
            APF_SPLB_SELECT_OBJECT_VA,
            APF_SPLB_SELECT_SLOT_OFFSET,
            APF_SPLB_SELECT_THUNK_VA,
            APF_SPLB_SELECT_WORD0_THUNK_VA,
            APF_SITUATION_GET_DOWN_TABLE_VA,
        )

        self.assertEqual(APF_SPLB_SELECT_WORD0_THUNK_VA, 0x849D81A8)
        self.assertEqual(APF_SPLB_SELECT_THUNK_VA, 0x849D81D0)
        self.assertEqual(APF_SPLB_SELECT_INIT_VA, 0x84D00A48)
        self.assertEqual(APF_SPLB_SELECT_OBJECT_VA, 0x84E28670)
        self.assertEqual(APF_SPLB_SELECT_SLOT_OFFSET, 0x2C94)
        self.assertEqual(APF_SITUATION_GET_DOWN_TABLE_VA, 0x84EB0DE4)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_DCA40_FALSE_STVX_VA,
            APF_DCA40_FALSE_VSUB_VA,
            APF_NFL_DCA40_VA,
            APF_SITUATION_GET_DOWN_ROW_VA,
            APF_SITUATION_GET_DOWN_SIBLING_VA,
        )

        self.assertEqual(APF_SITUATION_GET_DOWN_ROW_VA, 0x84EB0DD0)
        self.assertEqual(APF_NFL_DCA40_VA, 0x000DCA40)

        self.assertEqual(APF_SITUATION_GET_DOWN_SIBLING_VA, 0x847463C8)
        self.assertEqual(APF_DCA40_FALSE_STVX_VA, 0x8484D488)
        self.assertEqual(APF_DCA40_FALSE_VSUB_VA, 0x84878588)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_DCA40_FALSE_PLAYCALL_JT_VA,
            APF_PROPERTY_GET_BY_ID_VA,
            APF_PROPERTY_GET_SINGLETON_VA,
        )

        self.assertEqual(APF_DCA40_FALSE_PLAYCALL_JT_VA, 0x84880740)
        self.assertEqual(APF_PROPERTY_GET_BY_ID_VA, 0x849C9C90)
        self.assertEqual(APF_PROPERTY_GET_SINGLETON_VA, 0x851C96A0)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_DRCT_BYTE_STREAM_READER_VA,
            APF_DRCT_FALSE_ASCII_SWITCH_VA,
            APF_DRCT_INSN_COUNT_INGAME,
            APF_DRCT_INSN_OUTER_INGAME,
            APF_DRCT_INSN_RECORD_PREFIX,
            APF_DRCT_INSN_TOKEN_OFFSET,
            APF_DRCT_INSN_TOKEN_TOP,
            APF_DRCT_PACKED_INSN_COUNT_GETTER_VA,
            APF_DRCT_VT2_UNLINK_VA,
        )

        self.assertEqual(APF_DRCT_INSN_OUTER_INGAME, 153)
        self.assertEqual(APF_DRCT_INSN_COUNT_INGAME, 1015)
        self.assertEqual(APF_DRCT_INSN_RECORD_PREFIX, 0x0B000100)
        self.assertEqual(APF_DRCT_INSN_TOKEN_OFFSET, 4)
        self.assertEqual(APF_DRCT_INSN_TOKEN_TOP, (99, 83, 70, 82))
        self.assertEqual(APF_DRCT_PACKED_INSN_COUNT_GETTER_VA, 0x84AB2010)
        self.assertEqual(APF_DRCT_VT2_UNLINK_VA, 0x8466BA30)
        self.assertEqual(APF_DRCT_BYTE_STREAM_READER_VA, 0x8466BD38)
        self.assertEqual(APF_DRCT_FALSE_ASCII_SWITCH_VA, 0x84BCD760)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_DRCT_COMPACT_INDEX_CHECK_VA,
            APF_DRCT_FALSE_EMBEDDED20_VA,
            APF_DRCT_INSN_COUNT_WRAPUP,
            APF_DRCT_INSN_TAG_BYTE,
            APF_DRCT_INSN_WRAPUP_OUTER,
            APF_DRCT_VT0_FIXED_WALK_BL_VA,
        )

        self.assertEqual(APF_DRCT_INSN_TAG_BYTE, 0x0B)
        self.assertEqual(APF_DRCT_INSN_WRAPUP_OUTER, 265)
        self.assertEqual(APF_DRCT_INSN_COUNT_WRAPUP, 96)
        self.assertEqual(APF_DRCT_COMPACT_INDEX_CHECK_VA, 0x8466AF48)
        self.assertEqual(APF_DRCT_FALSE_EMBEDDED20_VA, 0x84B162A8)
        self.assertEqual(APF_DRCT_VT0_FIXED_WALK_BL_VA, 0x8466B8FC)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_DRCT_FALSE_ASCII_YI_VA,
            APF_DRCT_FALSE_FIELD100_VA,
            APF_DRCT_FALSE_PLAYTYPE_NIBBLE_VA,
            APF_DRCT_INSN_FIELD_ID_1,
            APF_DRCT_INSN_FIELD_ID_2,
            APF_DRCT_INSN_NEST_LEAD,
        )

        self.assertEqual(APF_DRCT_INSN_FIELD_ID_1, 0x0100)
        self.assertEqual(APF_DRCT_INSN_FIELD_ID_2, 0x0200)
        self.assertEqual(APF_DRCT_INSN_NEST_LEAD, (0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09))
        self.assertEqual(APF_DRCT_FALSE_FIELD100_VA, 0x84C381E8)
        self.assertEqual(APF_DRCT_FALSE_PLAYTYPE_NIBBLE_VA, 0x84A87B38)
        self.assertEqual(APF_DRCT_FALSE_ASCII_YI_VA, 0x84BDFB00)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_DRCT_FALSE_BE_FLOAT_VA,
            APF_DRCT_FALSE_CAP256_VA,
            APF_DRCT_FALSE_R4_VT2_VA,
            APF_DRCT_FALSE_RTTI_2_11_VA,
        )

        self.assertEqual(APF_DRCT_FALSE_RTTI_2_11_VA, 0x848BB1A8)
        self.assertEqual(APF_DRCT_FALSE_CAP256_VA, 0x8466B660)
        self.assertEqual(APF_DRCT_FALSE_BE_FLOAT_VA, 0x8466C7F0)
        self.assertEqual(APF_DRCT_FALSE_R4_VT2_VA, 0x84671838)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_DRCT_FALSE_PLUS5_OCCUPANCY_VA,
            APF_DRCT_FALSE_PLUS5_SUM_VA,
            APF_DRCT_FALSE_RTTI_TLV_VA,
            APF_DRCT_INSN_VARIANTS,
        )

        self.assertEqual(APF_DRCT_INSN_VARIANTS, (0, 1, 2, 3, 4, 5))
        self.assertEqual(APF_DRCT_FALSE_RTTI_TLV_VA, 0x84842F48)
        self.assertEqual(APF_DRCT_FALSE_PLUS5_OCCUPANCY_VA, 0x8476CA80)
        self.assertEqual(APF_DRCT_FALSE_PLUS5_SUM_VA, 0x8492BB24)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_DRCT_FALSE_STRUCT12_VA,
            APF_DRCT_PROP_JT_MAX_ID,
            APF_DRCT_PROP_JT_VA,
            APF_DRCT_PROP_TABLE_INDEX_VA,
            APF_DRCT_PROP_WALK_VA,
        )

        self.assertEqual(APF_DRCT_PROP_WALK_VA, 0x84B0A4C0)
        self.assertEqual(APF_DRCT_PROP_TABLE_INDEX_VA, 0x84EE65A8)
        self.assertEqual(APF_DRCT_PROP_JT_VA, 0x84B0A51C)
        self.assertEqual(APF_DRCT_PROP_JT_MAX_ID, 0x35)
        self.assertEqual(APF_DRCT_FALSE_STRUCT12_VA, 0x849E7790)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_DRCT_FALSE_CLASS_35764_VA,
            APF_DRCT_FALSE_COPY5_VA,
            APF_DRCT_FALSE_STRIDE32_F32_VA,
        )

        self.assertEqual(APF_DRCT_FALSE_CLASS_35764_VA, 0x847E2818)
        self.assertEqual(APF_DRCT_FALSE_COPY5_VA, 0x84ABB590)
        self.assertEqual(APF_DRCT_FALSE_STRIDE32_F32_VA, 0x84A9D7A0)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_DRCT_FALSE_ASCII_SCANF_VA,
            APF_DRCT_FALSE_CODEC5_VA,
            APF_DRCT_FALSE_DCA40_SINGLE_F32_VA,
            APF_NFL_DRCT_INSN_COUNT_INGAME,
            APF_NFL_DRCT_INSN_OUTER_INGAME,
            APF_NFL_DRCT_INSN_PREFIX_TOP,
        )

        self.assertEqual(APF_NFL_DRCT_INSN_OUTER_INGAME, 4)
        self.assertEqual(APF_NFL_DRCT_INSN_COUNT_INGAME, 1310)
        self.assertEqual(
            APF_NFL_DRCT_INSN_PREFIX_TOP, (0x0B000100, 0x0B000101, 0x0B000102)
        )
        self.assertEqual(APF_DRCT_FALSE_ASCII_SCANF_VA, 0x84BE2B48)
        self.assertEqual(APF_DRCT_FALSE_DCA40_SINGLE_F32_VA, 0x848777CC)
        self.assertEqual(APF_DRCT_FALSE_CODEC5_VA, 0x84B93B10)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_DRCT_FALSE_BYTE_JT_VA,
            APF_DRCT_FALSE_ENDIAN_COPY_VA,
            APF_DRCT_INSN_BEGIN_GROUP_SIZE,
            APF_DRCT_INSN_CLOSE_GROUP_SIZE,
            APF_DRCT_INSN_FLOAT_GROUP_SIZE,
            APF_DRCT_INSN_MARK_GROUP_SIZE,
            APF_DRCT_INSN_ONE_BYTE_TYPES,
            APF_DRCT_INSN_TYPE_BEGIN,
            APF_DRCT_INSN_TYPE_CLOSE,
            APF_DRCT_INSN_TYPE_FLOAT,
            APF_DRCT_INSN_TYPE_MARK,
            APF_DRCT_INSN_TYPE_TERM,
        )

        self.assertEqual(APF_DRCT_INSN_TYPE_TERM, 0x00)
        self.assertEqual(APF_DRCT_INSN_TYPE_BEGIN, 0x03)
        self.assertEqual(APF_DRCT_INSN_TYPE_FLOAT, 0x04)
        self.assertEqual(APF_DRCT_INSN_TYPE_MARK, 0x07)
        self.assertEqual(APF_DRCT_INSN_TYPE_CLOSE, 0x06)
        self.assertEqual(APF_DRCT_INSN_BEGIN_GROUP_SIZE, 2)
        self.assertEqual(APF_DRCT_INSN_FLOAT_GROUP_SIZE, 5)
        self.assertEqual(APF_DRCT_INSN_MARK_GROUP_SIZE, 1)
        self.assertEqual(APF_DRCT_INSN_CLOSE_GROUP_SIZE, 1)
        self.assertEqual(APF_DRCT_INSN_ONE_BYTE_TYPES, (0x05, 0x06, 0x07, 0x08, 0x09))
        self.assertEqual(APF_DRCT_FALSE_BYTE_JT_VA, 0x849277A8)
        self.assertEqual(APF_DRCT_FALSE_ENDIAN_COPY_VA, 0x84C4C480)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_DRCT_FALSE_PLUS5_STATE_VA,
            APF_DRCT_FALSE_STRIDE12_R4_VA,
        )

        self.assertEqual(APF_DRCT_FALSE_STRIDE12_R4_VA, 0x84BA2520)
        self.assertEqual(APF_DRCT_FALSE_PLUS5_STATE_VA, 0x846C2068)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_DRCT_FALSE_EXPR_CASE11_VA,
            APF_DRCT_FALSE_EXPR_DESC_VA,
            APF_DRCT_FALSE_EXPR_JT_VA,
            APF_DRCT_FALSE_EXPR_VM_VA,
        )

        self.assertEqual(APF_DRCT_FALSE_EXPR_VM_VA, 0x8466C890)
        self.assertEqual(APF_DRCT_FALSE_EXPR_JT_VA, 0x8466C91C)
        self.assertEqual(APF_DRCT_FALSE_EXPR_CASE11_VA, 0x8466CCDC)
        self.assertEqual(APF_DRCT_FALSE_EXPR_DESC_VA, 0x844DD260)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_DRCT_FALSE_UI_BYTE_JT_VA,
            APF_FALSE_YTG_WRAP_VA,
        )

        self.assertEqual(APF_DRCT_FALSE_UI_BYTE_JT_VA, 0x8477F950)
        self.assertEqual(APF_FALSE_YTG_WRAP_VA, 0x84A37850)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_DRCT_FALSE_TYPE24_VA,
            APF_FALSE_SIT_WORD0_EQ4_VA,
        )

        self.assertEqual(APF_FALSE_SIT_WORD0_EQ4_VA, 0x848864B0)
        self.assertEqual(APF_DRCT_FALSE_TYPE24_VA, 0x84A5EB08)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_FALSE_TWEEN_OBJ_VA,
            APF_NFL_FALSE_BYTE35_VA,
        )

        self.assertEqual(APF_FALSE_TWEEN_OBJ_VA, 0x8475B7B0)
        self.assertEqual(APF_NFL_FALSE_BYTE35_VA, 0x001138E0)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_DRCT_FALSE_UTF8_WALK_VA,
            APF_FALSE_FILTER_SETTER_VA,
            APF_FALSE_FILTER_UI_VA,
            APF_PICKER_DESC_SLOT_VA,
        )

        self.assertEqual(APF_FALSE_FILTER_UI_VA, 0x84A23BD0)
        self.assertEqual(APF_PICKER_DESC_SLOT_VA, 0x844E8568)
        self.assertEqual(APF_DRCT_FALSE_UTF8_WALK_VA, 0x84B64C88)
        self.assertEqual(APF_FALSE_FILTER_SETTER_VA, 0x849D36D8)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_FALSE_FILTER_GETTER_VA,
            APF_NFL_FALSE_SHAP_LIST_VA,
        )

        self.assertEqual(APF_FALSE_FILTER_GETTER_VA, 0x848631D0)
        self.assertEqual(APF_NFL_FALSE_SHAP_LIST_VA, 0x00168AD0)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_DRCT_FALSE_BITPACK_R26_VA,
            APF_DRCT_FALSE_CMP4_OCC_VA,
            APF_FALSE_FILTER_TAB_GATE_VA,
        )

        self.assertEqual(APF_FALSE_FILTER_TAB_GATE_VA, 0x84A2CCD8)
        self.assertEqual(APF_DRCT_FALSE_CMP4_OCC_VA, 0x84961548)
        self.assertEqual(APF_DRCT_FALSE_BITPACK_R26_VA, 0x849E3A24)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_DRCT_FALSE_FILL4_VA,
            APF_DRCT_FALSE_SLOT11_PLUS5_VA,
            APF_FALSE_SIT_WORD0_EQ4_PICKER_VA,
            APF_FALSE_SIT_WORD0_SWITCH_VA,
        )

        self.assertEqual(APF_FALSE_SIT_WORD0_EQ4_PICKER_VA, 0x84814DCC)
        self.assertEqual(APF_FALSE_SIT_WORD0_SWITCH_VA, 0x8485A04C)
        self.assertEqual(APF_DRCT_FALSE_FILL4_VA, 0x84869E60)
        self.assertEqual(APF_DRCT_FALSE_SLOT11_PLUS5_VA, 0x84A9ADCC)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_DND_NAME_TABLE_VA,
            APF_DND_THIRD_LONG_STR_VA,
            APF_DRCT_FALSE_BYTE34_JT_VA,
            APF_DRCT_FALSE_BYTE36_JT_VA,
            APF_FALSE_DND_LABEL_VA,
        )

        self.assertEqual(APF_FALSE_DND_LABEL_VA, 0x84A21298)
        self.assertEqual(APF_DND_NAME_TABLE_VA, 0x84E446C8)
        self.assertEqual(APF_DND_THIRD_LONG_STR_VA, 0x845FD8B4)
        self.assertEqual(APF_DRCT_FALSE_BYTE36_JT_VA, 0x84911750)
        self.assertEqual(APF_DRCT_FALSE_BYTE34_JT_VA, 0x849ECD48)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_DRCT_EXPR_CURSOR_INIT_VA,
            APF_DRCT_EXPR_CURSOR_VA,
            APF_FALSE_PLAYCALL_3C_VA,
            APF_FALSE_SCRIPT_DND_VA,
        )

        self.assertEqual(APF_FALSE_PLAYCALL_3C_VA, 0x847D7590)
        self.assertEqual(APF_DRCT_EXPR_CURSOR_VA, 0x84F1779C)
        self.assertEqual(APF_DRCT_EXPR_CURSOR_INIT_VA, 0x8466C8DC)
        self.assertEqual(APF_FALSE_SCRIPT_DND_VA, 0x849A3B58)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_FALSE_YTG_LSB_VA,
            APF_PACKED_GET_YTG_VA,
        )

        self.assertEqual(APF_PACKED_GET_YTG_VA, 0x84B68CD8)
        self.assertEqual(APF_FALSE_YTG_LSB_VA, 0x84879BC0)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_FALSE_SIT_COPYOUT_VA,
            APF_FALSE_SIT_PTR254_VA,
            APF_PACKED_GET_DOWN_OBJ_VA,
        )

        self.assertEqual(APF_PACKED_GET_DOWN_OBJ_VA, 0x84B68CC8)
        self.assertEqual(APF_FALSE_SIT_COPYOUT_VA, 0x84AD0348)
        self.assertEqual(APF_FALSE_SIT_PTR254_VA, 0x84B39458)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_FALSE_0B00_MASK_VA,
            APF_FALSE_BLOB_INDEXER_VA,
            APF_SITUATION_FALSE_BLOB_ROW_VA,
        )

        self.assertEqual(APF_SITUATION_FALSE_BLOB_ROW_VA, 0x84EB02D0)
        self.assertEqual(APF_FALSE_BLOB_INDEXER_VA, 0x84AD9F40)
        self.assertEqual(APF_FALSE_0B00_MASK_VA, 0x848EE750)
        self.assertEqual(APF_ROLE_ELIGIBILITY_WORD_TABLE_VA, 0x820FC380)
        self.assertEqual(APF_ROLE_ELIGIBILITY_MASK_TE, 0x0000CD00)
        self.assertEqual(APF_ROLE_ELIGIBILITY_MASK_WR, 0x0000DD20)
        self.assertEqual(APF_FIVE_WIDE_SKILL_CELL_LOW, 0x00000200)
        self.assertEqual(APF_ROLE_ELIGIBILITY_MASK_TE & APF_FIVE_WIDE_SKILL_CELL_LOW, 0)
        self.assertEqual(APF_ROLE_ELIGIBILITY_MASK_WR & APF_FIVE_WIDE_SKILL_CELL_LOW, 0)
        from mod_editor.core.playbook_package_rule_spike import (
            APF_CATEGORY_GETTER_VA,
            APF_CATEGORY_INDEX_EXTRACT_PROVED,
            APF_MASTER_CATEGORY_ACE,
            APF_MASTER_CATEGORY_COUNT,
            APF_MASTER_CATEGORY_FIVE_WIDE,
            APF_MASTER_CATEGORY_FLUSH,
            APF_MASTER_CATEGORY_NAMES,
        )

        self.assertTrue(APF_CATEGORY_INDEX_EXTRACT_PROVED)
        self.assertEqual(APF_CATEGORY_GETTER_VA, 0x8485BD38)
        self.assertEqual(APF_MASTER_CATEGORY_COUNT, 28)
        self.assertEqual(APF_MASTER_CATEGORY_NAMES[APF_MASTER_CATEGORY_ACE], "Ace")
        self.assertEqual(APF_MASTER_CATEGORY_NAMES[APF_MASTER_CATEGORY_FLUSH], "Flush")
        self.assertEqual(
            APF_MASTER_CATEGORY_NAMES[APF_MASTER_CATEGORY_FIVE_WIDE], "5 Wide"
        )
        from mod_editor.core.playbook_package_rule_spike import (
            APF_CATEGORY_PERSONNEL_ACE_ROW_INDEX,
            APF_CATEGORY_PERSONNEL_FIVE_WIDE_ROW_INDEX,
            APF_CATEGORY_PERSONNEL_ROW_ACE,
            APF_CATEGORY_PERSONNEL_ROW_FIVE_WIDE,
        )

        self.assertEqual(APF_CATEGORY_PERSONNEL_ACE_ROW_INDEX, 3)
        self.assertEqual(APF_CATEGORY_PERSONNEL_FIVE_WIDE_ROW_INDEX, 10)
        self.assertEqual(APF_CATEGORY_PERSONNEL_ROW_ACE[6:11], (8, 9, 9, 8, 10))
        self.assertEqual(APF_CATEGORY_PERSONNEL_ROW_FIVE_WIDE[6:11], (9, 9, 9, 9, 9))
        self.assertEqual(APF_CATEGORY_PERSONNEL_ROW_ACE[6], APF_PACKAGE_MAP_ROLE_TE)
        self.assertEqual(APF_CATEGORY_PERSONNEL_ROW_FIVE_WIDE[6], APF_PACKAGE_MAP_ROLE_WR3)

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

    def test_g1_multi_dime_from_nickel_pack_offline_proved(self) -> None:
        """Multi-formation G1 pack: every Dime gets Nickel package map."""

        from mod_editor.core.nfl2k5_playbook_inspector import parse_playbook_resource

        book = parse_playbook_resource(self.raw)
        dime_indices = [
            f.index for f in book.formations if re.search(r"\bdime\b", f.name or "", re.I)
        ]
        nickel_i = next(
            f.index for f in book.formations if re.search(r"\bnickel\b", f.name or "", re.I)
        )
        self.assertGreaterEqual(len(dime_indices), 1)
        nickel_map = read_formation_package_map(self.raw, nickel_i)

        pack = build_g1_dime_from_nickel_package_map_pack(self.raw)
        self.assertEqual(pack.status, "offline_writer_proved")
        self.assertFalse(pack.manifest["runtime_proved"])
        self.assertEqual(pack.nickel_formation_index, nickel_i)
        self.assertEqual(pack.nickel_package_map, nickel_map)
        self.assertGreaterEqual(len(pack.targets), len(dime_indices))
        self.assertGreater(pack.total_changed_byte_count, 0)
        self.assertIn("runtime", pack.honesty.casefold())
        self.assertIn("unproved", pack.honesty.casefold())

        verify_g1_dime_from_nickel_package_map_pack(
            self.raw,
            pack.raw_resource,
            nickel_index=nickel_i,
            dime_indices=tuple(t.formation_index for t in pack.targets),
            expected_map=nickel_map,
        )
        for fi in dime_indices:
            self.assertEqual(
                read_formation_package_map(pack.raw_resource, fi),
                nickel_map,
                msg=f"Dime formation {fi}",
            )
        # Nickel donor unchanged; source PLAY identity preserved.
        self.assertEqual(
            read_formation_package_map(pack.raw_resource, nickel_i), nickel_map
        )
        self.assertEqual(
            read_formation_package_map(self.raw, nickel_i), nickel_map
        )
        # Ace package map untouched (offense surface).
        ace_i = next(f.index for f in book.formations if f.name == "Ace")
        self.assertEqual(
            read_formation_package_map(pack.raw_resource, ace_i),
            read_formation_package_map(self.raw, ace_i),
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

    def test_g2_multi_ace_from_quads_pack_offline_proved(self) -> None:
        """Multi-formation G2 pack: every Ace gets Quads play-link menu table."""

        from mod_editor.core.nfl2k5_playbook_inspector import parse_playbook_resource

        book = parse_playbook_resource(self.raw)
        ace_indices = [
            f.index
            for f in book.formations
            if re.search(r"\bace\b", f.name or "", re.I)
        ]
        quads_i = next(
            f.index
            for f in book.formations
            if re.search(r"\bquads\b", f.name or "", re.I)
        )
        self.assertGreaterEqual(len(ace_indices), 1)
        quads_links = len(book.formations[quads_i].play_links)

        pack = build_g2_ace_from_quads_link_table_pack(self.raw)
        self.assertEqual(pack.status, "offline_writer_proved")
        self.assertFalse(pack.manifest["runtime_proved"])
        self.assertEqual(pack.quads_formation_index, quads_i)
        self.assertEqual(pack.quads_link_count, quads_links)
        self.assertGreaterEqual(len(pack.targets), len(ace_indices))
        self.assertGreater(pack.total_changed_byte_count, 0)
        self.assertIn("runtime", pack.honesty.casefold())
        self.assertIn("unproved", pack.honesty.casefold())
        self.assertIn("menu", pack.honesty.casefold())

        verify_g2_ace_from_quads_link_table_pack(
            self.raw,
            pack.raw_resource,
            quads_index=quads_i,
            ace_indices=tuple(t.formation_index for t in pack.targets),
        )
        patched = parse_playbook_resource(pack.raw_resource)
        for fi in ace_indices:
            self.assertEqual(
                len(patched.formations[fi].play_links),
                quads_links,
                msg=f"Ace formation {fi}",
            )
            # Package map identity for each Ace (menu-only pack).
            self.assertEqual(
                read_formation_package_map(pack.raw_resource, fi),
                read_formation_package_map(self.raw, fi),
                msg=f"Ace package map mutated at {fi}",
            )
        # Quads donor unchanged; source identity preserved.
        self.assertEqual(
            len(patched.formations[quads_i].play_links),
            quads_links,
        )
        self.assertEqual(
            len(book.formations[quads_i].play_links),
            quads_links,
        )
        # Dime package map untouched (defense surface).
        dime_i = next(
            f.index
            for f in book.formations
            if re.search(r"\bdime\b", f.name or "", re.I)
        )
        self.assertEqual(
            read_formation_package_map(pack.raw_resource, dime_i),
            read_formation_package_map(self.raw, dime_i),
        )


def _put_apf_name(body: bytearray, field: int, text: str, pool: int) -> int:
    encoded = text.encode("utf-16be") + b"\0\0"
    body[pool : pool + len(encoded)] = encoded
    import struct

    struct.pack_into(">i", body, field, pool - field + 1)
    return pool + len(encoded)


def _synthetic_apf_master() -> bytes:
    """Minimal MASTER body with Ace / Ace Empty / Nickel maps."""

    import struct

    from mod_editor.core.playbook_package_rule_spike import (
        APF_ACE_EMPTY_PACKAGE_MAP,
        APF_ACE_PACKAGE_MAP,
        APF_FORMATION_BASE,
        APF_FORMATION_COUNT_OFFSET,
        APF_FORMATION_SIZE,
        APF_MASTER_BODY_SIZE,
        APF_PACKAGE_MAP_OFFSET_IN_FORMATION,
    )

    body = bytearray(APF_MASTER_BODY_SIZE)
    struct.pack_into(">I", body, APF_FORMATION_COUNT_OFFSET, 3)
    names = ("Ace", "Ace Empty", "Nickel")
    maps = (
        APF_ACE_PACKAGE_MAP,
        APF_ACE_EMPTY_PACKAGE_MAP,
        (4, 5, 0, 2, 3, 1, 7, 8, 9, 6, 10),
    )
    pool = 0x22384
    for index, (name, pmap) in enumerate(zip(names, maps, strict=True)):
        field = APF_FORMATION_BASE + index * APF_FORMATION_SIZE
        pool = _put_apf_name(body, field, name, pool)
        offset = field + APF_PACKAGE_MAP_OFFSET_IN_FORMATION
        body[offset : offset + 11] = bytes(pmap)
    return bytes(body)


class ApfG12PackageMapWriterTests(unittest.TestCase):
    def test_swap_is_a_permutation_and_toggles_8_and_9(self) -> None:
        from mod_editor.core.playbook_package_rule_spike import (
            APF_ACE_PACKAGE_MAP,
            swap_apf_package_map_wr3_te,
        )

        swapped = swap_apf_package_map_wr3_te(APF_ACE_PACKAGE_MAP)
        self.assertEqual(sorted(swapped), list(range(11)))
        self.assertEqual(swapped[2], 9)
        self.assertEqual(swapped[3], 8)
        self.assertEqual(swap_apf_package_map_wr3_te(swapped), APF_ACE_PACKAGE_MAP)

    def test_swap_refuses_a_map_missing_one_role(self) -> None:
        from mod_editor.core.playbook_package_rule_spike import (
            swap_apf_package_map_wr3_te,
        )

        missing = (0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 10)
        with self.assertRaises(ValidationError):
            swap_apf_package_map_wr3_te(missing)

    def test_synthetic_census_and_g12_pack(self) -> None:
        from mod_editor.core.playbook_package_rule_spike import (
            APF_3RD_AND_LONG_PLAY_CHOICE_PROVED,
            APF_ACE_EMPTY_PACKAGE_MAP,
            APF_ACE_PACKAGE_MAP,
            APF_WR3_TE_PACKAGE_SUB_PROVED,
            build_g12_wr3_te_package_map_pack,
            census_apf_ace_vs_ace_empty,
            read_apf_formation_package_map,
            swap_apf_package_map_wr3_te,
            verify_g12_wr3_te_package_map_pack,
        )

        raw = _synthetic_apf_master()
        census = census_apf_ace_vs_ace_empty(raw)
        self.assertEqual(census.ace_formation_index, 0)
        self.assertEqual(census.empty_formation_index, 1)
        self.assertEqual(census.ace_package_map, APF_ACE_PACKAGE_MAP)
        self.assertEqual(census.empty_package_map, APF_ACE_EMPTY_PACKAGE_MAP)
        self.assertFalse(census.maps_identical)
        self.assertFalse(census.empty_is_wr3_te_swap_of_ace)
        self.assertEqual(census.slot_deltas, ((9, 6, 7), (10, 7, 6)))

        pack = build_g12_wr3_te_package_map_pack(raw)
        self.assertEqual(pack.status, "offline_writer_proved")
        self.assertFalse(pack.manifest["runtime_proved"])
        self.assertTrue(pack.manifest["experimental"])
        self.assertFalse(pack.manifest["wr3_te_package_sub_proved"])
        self.assertFalse(pack.manifest["APF_3RD_AND_LONG_PLAY_CHOICE_PROVED"])
        self.assertFalse(pack.manifest["ace_empty_is_wr3_te_swap_of_ace"])
        self.assertFalse(pack.manifest["ace_empty_used_as_source"])
        self.assertFalse(APF_WR3_TE_PACKAGE_SUB_PROVED)
        self.assertFalse(APF_3RD_AND_LONG_PLAY_CHOICE_PROVED)
        self.assertIn("experimental", pack.honesty.casefold())
        self.assertIn("ace-named", pack.honesty.casefold())
        self.assertIn("8", pack.honesty)
        self.assertIn("unproved", pack.honesty.casefold())
        self.assertIn("3rd-and-long", pack.honesty.casefold())
        self.assertIn("does not copy ace empty", pack.honesty.casefold())
        self.assertEqual(len(pack.targets), 2)
        names = {t.formation_name for t in pack.targets}
        self.assertEqual(names, {"Ace", "Ace Empty"})
        self.assertTrue(all("ace" in t.formation_name.casefold() for t in pack.targets))
        self.assertGreater(pack.total_changed_byte_count, 0)

        verify_g12_wr3_te_package_map_pack(
            raw,
            pack.raw_resource,
            formation_indices=tuple(t.formation_index for t in pack.targets),
        )
        ace_after = read_apf_formation_package_map(pack.raw_resource, 0)
        empty_after = read_apf_formation_package_map(pack.raw_resource, 1)
        self.assertEqual(ace_after, swap_apf_package_map_wr3_te(APF_ACE_PACKAGE_MAP))
        self.assertEqual(
            empty_after, swap_apf_package_map_wr3_te(APF_ACE_EMPTY_PACKAGE_MAP)
        )
        self.assertNotEqual(ace_after, APF_ACE_EMPTY_PACKAGE_MAP)
        self.assertNotEqual(ace_after, empty_after)
        self.assertEqual(
            read_apf_formation_package_map(pack.raw_resource, 2),
            read_apf_formation_package_map(raw, 2),
        )
        self.assertEqual(
            read_apf_formation_package_map(raw, 0), APF_ACE_PACKAGE_MAP
        )

    def test_pack_refuses_a_book_without_ace(self) -> None:
        import struct

        from mod_editor.core.playbook_package_rule_spike import (
            APF_FORMATION_BASE,
            APF_FORMATION_COUNT_OFFSET,
            APF_FORMATION_SIZE,
            APF_MASTER_BODY_SIZE,
            APF_PACKAGE_MAP_OFFSET_IN_FORMATION,
            build_g12_wr3_te_package_map_pack,
        )

        body = bytearray(APF_MASTER_BODY_SIZE)
        struct.pack_into(">I", body, APF_FORMATION_COUNT_OFFSET, 1)
        _put_apf_name(body, APF_FORMATION_BASE, "Nickel", 0x22384)
        offset = APF_FORMATION_BASE + APF_PACKAGE_MAP_OFFSET_IN_FORMATION
        body[offset : offset + 11] = bytes(range(11))
        with self.assertRaisesRegex(ValidationError, "Ace"):
            build_g12_wr3_te_package_map_pack(bytes(body))

    def test_g12_pack_is_experimental_ace_named_8_9(self) -> None:
        from mod_editor.core.playbook_package_rule_spike import (
            APF_G12_PACK_EXPERIMENTAL,
            APF_PACKAGE_MAP_ROLE_TE,
            APF_PACKAGE_MAP_ROLE_WR3,
            APF_WR3_TE_PACKAGE_SUB_PROVED,
            build_g12_wr3_te_package_map_pack,
            swap_apf_package_map_wr3_te,
        )

        self.assertTrue(APF_G12_PACK_EXPERIMENTAL)
        self.assertFalse(APF_WR3_TE_PACKAGE_SUB_PROVED)
        pack = build_g12_wr3_te_package_map_pack(_synthetic_apf_master())
        self.assertTrue(pack.manifest["experimental"])
        self.assertIn("experimental", pack.honesty.casefold())
        self.assertIn("ace-named", pack.honesty.casefold())
        for target in pack.targets:
            self.assertRegex(target.formation_name, r"(?i)\bace\b")
            self.assertEqual(
                target.new_map, swap_apf_package_map_wr3_te(target.old_map)
            )
            self.assertEqual(
                target.old_map.index(APF_PACKAGE_MAP_ROLE_TE),
                target.new_map.index(APF_PACKAGE_MAP_ROLE_WR3),
            )
            self.assertEqual(
                target.old_map.index(APF_PACKAGE_MAP_ROLE_WR3),
                target.new_map.index(APF_PACKAGE_MAP_ROLE_TE),
            )

    def test_g12_pack_does_not_use_ace_empty_as_source(self) -> None:
        from mod_editor.core.playbook_package_rule_spike import (
            APF_ACE_EMPTY_PACKAGE_MAP,
            APF_ACE_PACKAGE_MAP,
            APF_G12_PACK_USES_ACE_EMPTY_AS_SOURCE,
            build_g12_wr3_te_package_map_pack,
            read_apf_formation_package_map,
            swap_apf_package_map_wr3_te,
        )

        self.assertFalse(APF_G12_PACK_USES_ACE_EMPTY_AS_SOURCE)
        raw = _synthetic_apf_master()
        pack = build_g12_wr3_te_package_map_pack(raw)
        self.assertFalse(pack.manifest["ace_empty_used_as_source"])
        self.assertIn("not used as a source", pack.honesty.casefold())
        ace = next(t for t in pack.targets if t.formation_name == "Ace")
        self.assertEqual(ace.old_map, APF_ACE_PACKAGE_MAP)
        self.assertEqual(ace.new_map, swap_apf_package_map_wr3_te(APF_ACE_PACKAGE_MAP))
        self.assertNotEqual(ace.new_map, APF_ACE_EMPTY_PACKAGE_MAP)
        self.assertNotEqual(
            ace.new_map, read_apf_formation_package_map(raw, 1)
        )
        self.assertNotEqual(
            ace.new_map, swap_apf_package_map_wr3_te(APF_ACE_EMPTY_PACKAGE_MAP)
        )

    def test_3rd_and_long_writer_is_refused(self) -> None:
        from mod_editor.core.playbook_package_rule_spike import (
            APF_3RD_AND_LONG_PLAY_CHOICE_PROVED,
            APF_3RD_AND_LONG_USER_LOGIC_REFUSAL,
            APF_USER_3RD_AND_LONG_DATA_WRITER_EXISTS,
            ApfThirdAndLongUserLogicRefusal,
            refuse_apf_3rd_and_long_user_logic_writer,
        )

        self.assertFalse(APF_3RD_AND_LONG_PLAY_CHOICE_PROVED)
        self.assertFalse(APF_USER_3RD_AND_LONG_DATA_WRITER_EXISTS)
        with self.assertRaises(ValidationError) as caught:
            refuse_apf_3rd_and_long_user_logic_writer()
        self.assertIsInstance(caught.exception, ApfThirdAndLongUserLogicRefusal)
        self.assertEqual(str(caught.exception), APF_3RD_AND_LONG_USER_LOGIC_REFUSAL)
        self.assertIn("default.xex", str(caught.exception))
        self.assertIn("0x8486CE88", str(caught.exception))
        self.assertIn("does not patch", str(caught.exception).casefold())


_APF_DISC_0A = Path(
    "/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A"
)


@unittest.skipUnless(
    _APF_DISC_0A.is_file() and not _APF_DISC_0A.is_symlink(),
    "APF retail 0A not present at the Storage disc path",
)
class RealApfMasterG12Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from mod_editor.core.apf2k8_playbook_route_writer import (
            read_master_play_body,
        )

        cls.raw = read_master_play_body(_APF_DISC_0A)

    def test_retail_ace_empty_is_not_an_8_9_swap(self) -> None:
        from mod_editor.core.playbook_package_rule_spike import (
            APF_ACE_EMPTY_FORMATION_INDEX,
            APF_ACE_EMPTY_PACKAGE_MAP,
            APF_ACE_FORMATION_INDEX,
            APF_ACE_PACKAGE_MAP,
            APF_RETAIL_FORMATION_COUNT,
            apf_formation_count,
            census_apf_ace_vs_ace_empty,
        )

        self.assertEqual(apf_formation_count(self.raw), APF_RETAIL_FORMATION_COUNT)
        census = census_apf_ace_vs_ace_empty(self.raw)
        self.assertEqual(census.ace_formation_index, APF_ACE_FORMATION_INDEX)
        self.assertEqual(census.empty_formation_index, APF_ACE_EMPTY_FORMATION_INDEX)
        self.assertEqual(census.ace_package_map, APF_ACE_PACKAGE_MAP)
        self.assertEqual(census.empty_package_map, APF_ACE_EMPTY_PACKAGE_MAP)
        self.assertFalse(census.empty_is_wr3_te_swap_of_ace)

    def test_g12_pack_swaps_ace_named_maps_only(self) -> None:
        from mod_editor.core.playbook_package_rule_spike import (
            build_g12_wr3_te_package_map_pack,
            list_apf_ace_named_formations,
            read_apf_formation_package_map,
            swap_apf_package_map_wr3_te,
            verify_g12_wr3_te_package_map_pack,
        )

        named = list_apf_ace_named_formations(self.raw)
        self.assertGreaterEqual(len(named), 2)
        names = {name for _index, name in named}
        self.assertIn("Ace", names)
        self.assertIn("Ace Empty", names)
        pack = build_g12_wr3_te_package_map_pack(self.raw)
        verify_g12_wr3_te_package_map_pack(
            self.raw,
            pack.raw_resource,
            formation_indices=tuple(t.formation_index for t in pack.targets),
        )
        self.assertGreater(pack.total_changed_byte_count, 0)
        for index, name in named:
            self.assertEqual(
                read_apf_formation_package_map(pack.raw_resource, index),
                swap_apf_package_map_wr3_te(
                    read_apf_formation_package_map(self.raw, index)
                ),
                msg=name,
            )


if __name__ == "__main__":
    unittest.main()

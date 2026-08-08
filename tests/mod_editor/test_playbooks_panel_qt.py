"""Headless model tests for the structured Playbooks & Plays panel."""

from __future__ import annotations

import unittest

from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_playbook_inspector import (
    FormationPlayLink,
    Nfl2k5Playbook,
    PlaybookAssignment,
    PlaybookCategory,
    PlaybookChain,
    PlaybookFormation,
    PlaybookNode,
    PlaybookPlay,
)
from mod_editor.gui.playbooks_panel_qt import (
    PLAY_EDITOR_FINDINGS_PLAIN_TEXT,
    book_has_community_flags,
    broken_play_annotations,
    filter_playbooks,
    format_formation_package_map_line,
    format_play_name_with_warnings,
    formation_play_rows,
    playbook_action_state,
    playbook_search_text,
    suggested_playbook_filename,
)


def _book(
    *, asset_id: str, name: str, formation_name: str, play_name: str,
    family_id: int, outer_index: int,
) -> Nfl2k5Playbook:
    nodes = (
        PlaybookNode(0, 0x01, 0x00, "010203040506", "0100010203040506"),
        PlaybookNode(1, 0x04, 0x02, "0708090a0b0c", "04020708090a0b0c"),
    )
    chain = PlaybookChain(0, 2, nodes)
    play = PlaybookPlay(
        0,
        play_name,
        family_id << 6,
        family_id,
        ("Offense", "Defense")[family_id],
        tuple(PlaybookAssignment(slot, 0x1000 + slot, 0) for slot in range(11)),
    )
    formation = PlaybookFormation(
        0,
        formation_name,
        (FormationPlayLink(7, 0, 2, (2 << 9) | 0),),
    )
    return Nfl2k5Playbook(
        asset_id=asset_id,
        outer_index=outer_index,
        book_name=name,
        formations=(formation,),
        plays=(play,),
        categories=(PlaybookCategory(0, "Synthetic category"),),
        chains=(chain,),
        node_count=2,
    )


class PlaybooksPanelModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.offense = _book(
            asset_id="private.play.offense",
            name="Synthetic Offense",
            formation_name="I Pro",
            play_name="Quick Test",
            family_id=0,
            outer_index=10,
        )
        self.defense = _book(
            asset_id="private.play.defense",
            name="Synthetic Defense",
            formation_name="Nickel",
            play_name="Cover Test",
            family_id=1,
            outer_index=11,
        )
        self.books = (self.offense, self.defense)

    def test_search_and_family_filters_cover_all_structured_names(self) -> None:
        result = filter_playbooks(self.books, search="i pro quick")
        self.assertEqual(result.books, (self.offense,))
        self.assertEqual(result.catalog_total, 2)
        self.assertEqual(result.formation_total, 2)
        self.assertEqual(result.play_total, 2)
        self.assertEqual(result.chain_total, 2)
        self.assertEqual(result.node_total, 4)
        self.assertEqual(filter_playbooks(self.books, family_id=1).books,
                         (self.defense,))
        self.assertIn("synthetic category", playbook_search_text(self.offense))

    def test_invalid_family_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValidationError, "eight decoded"):
            filter_playbooks(self.books, family_id=8)
        with self.assertRaisesRegex(ValidationError, "eight decoded"):
            filter_playbooks(self.books, family_id=True)  # type: ignore[arg-type]

    def test_formation_rows_retain_exact_link_and_play_words(self) -> None:
        rows = formation_play_rows(self.offense, 0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].link_index, 7)
        self.assertEqual(rows[0].group, 2)
        self.assertEqual(rows[0].packed_value, 0x0400)
        self.assertEqual(rows[0].play.flags_or_id, 0)
        self.assertEqual(len(rows[0].play.assignments), 11)
        chain = self.offense.chain(rows[0].play.assignments[0].chain_start_index)
        self.assertEqual(chain.nodes[-1].raw_hex, "04020708090a0b0c")

    def test_export_gating_and_filename_are_viewer_only(self) -> None:
        self.assertTrue(
            playbook_action_state(
                self.offense, source_ready=True, busy=False
            ).can_export
        )
        self.assertFalse(
            playbook_action_state(
                self.offense, source_ready=True, busy=True
            ).can_export
        )
        self.assertFalse(
            playbook_action_state(None, source_ready=True, busy=False).can_export
        )
        self.assertEqual(
            suggested_playbook_filename(self.offense),
            "0010_Synthetic_Offense_PLAY.bin",
        )

    def test_findings_state_exact_authoring_and_retail_boundaries(self) -> None:
        note = PLAY_EDITOR_FINDINGS_PLAIN_TEXT
        self.assertIn("Freehand route drawing is not supported", note)
        self.assertIn("37 PLAY books", note)
        self.assertIn("32,502 complete chains", note)
        self.assertIn("all 91,833 eight-byte nodes", note)
        self.assertIn("shareable Mod Studio projects never contain PLAY data", note)
        self.assertIn("only along X", note)
        self.assertIn("only along Y", note)

    def test_community_flagged_filter_keeps_dime_ace_books(self) -> None:
        dime = _book(
            asset_id="private.play.dime",
            name="Defense Book",
            formation_name="Dime",
            play_name="Cover 2",
            family_id=1,
            outer_index=12,
        )
        quiet = self.offense
        result = filter_playbooks(
            (quiet, dime), community_flagged_only=True
        )
        self.assertEqual(result.books, (dime,))
        self.assertTrue(book_has_community_flags(dime))
        self.assertFalse(book_has_community_flags(quiet))

    def test_package_map_line_formats_dime_g1_honesty(self) -> None:
        dime_map = (5, 0, 2, 3, 1, 7, 8, 9, 4, 6, 10)
        line = format_formation_package_map_line("Dime", dime_map)
        self.assertIn("+0x0D", line)
        self.assertIn("5, 0, 2, 3, 1, 7, 8, 9, 4, 6, 10", line)
        self.assertIn("G1", line)
        self.assertIn("unproved", line.casefold())
        empty = format_formation_package_map_line("Dime", ())
        self.assertIn("not present", empty.casefold())
        ace = format_formation_package_map_line(
            "Ace", (0, 8, 6, 9, 7, 10, 1, 4, 3, 5, 2)
        )
        self.assertIn("G2", ace)
        self.assertIn("not this map", ace.casefold())


@unittest.skipUnless(
    __import__("pathlib").Path(
        "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
    ).is_file(),
    "2K5 pack0 fixture not present",
)
class RealO0308PackageMapInInspectorTests(unittest.TestCase):
    """Shipped parser populates package_map on real o0308."""

    def test_dime_nickel_maps_match_census(self) -> None:
        from pathlib import Path

        from mod_editor.core.nfl2k5_playbook_inspector import (
            BODY_SIZE,
            RESOURCE_HEADER_SIZE,
            parse_playbook_resource,
        )

        pack = Path("extracted/ESPN NFL 2K5 (USA)/vc_53450030/0")
        raw = pack.read_bytes()[
            106_803_200 : 106_803_200 + RESOURCE_HEADER_SIZE + BODY_SIZE
        ]
        book = parse_playbook_resource(raw)
        nickel = book.formations[23]
        dime = book.formations[24]
        self.assertEqual(nickel.name, "Nickel")
        self.assertEqual(dime.name, "Dime")
        self.assertEqual(
            list(nickel.package_map), [4, 5, 0, 2, 3, 1, 7, 8, 9, 6, 10]
        )
        self.assertEqual(
            list(dime.package_map), [5, 0, 2, 3, 1, 7, 8, 9, 4, 6, 10]
        )
        ui = format_formation_package_map_line(dime.name, dime.package_map)
        self.assertIn("5, 0, 2, 3, 1, 7, 8, 9, 4, 6, 10", ui)


if __name__ == "__main__":
    unittest.main()

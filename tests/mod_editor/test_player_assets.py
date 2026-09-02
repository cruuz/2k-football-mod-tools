"""One player, and everything the disc lets you edit about them.

"Which face is this player?" had no answer in the app. Faces are found by a
``face_id`` stored in the player's own roster record and filed under a number,
so the only method was scrolling 1,872 textures hoping a label matched.

Two links exist and they are not equally strong, which is the point of these
tests. The **face** link is real: the player record carries the id at offset
``0x06`` and the live-face catalog is keyed by exactly that number. The
**portrait** link is not in the bytes at all -- portraits are numbered
separately and nothing ties a number to a player -- so it is matched on the
name in the label and reported as ``by_name``. Presenting the two the same way
would be claiming a relationship the disc does not contain.

Equipment gets the same treatment for the opposite reason. Gloves, cleats,
wristbands and elbow pads exist as five shared textures, one copy for the whole
game, so there is nothing per-player to show and the panel says so instead of
implying ownership.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mod_editor.core.nfl2k5_player_assets import (  # noqa: E402
    EQUIPMENT_NOTE, SHARED_EQUIPMENT, build_player_assets, equipment_rows,
)


class _Asset:
    """The shape the extended visual catalog exposes."""

    def __init__(self, asset_id: str, label: str, kind: str,
                 face_id: str | None = None, width: int = 128,
                 height: int = 128) -> None:
        self.asset_id = asset_id
        self.label = label
        self.kind = kind
        self.face_id = face_id
        self.width = width
        self.height = height


def _catalog() -> list[_Asset]:
    return [
        _Asset("face.0002.f", "Face / Eye Texture 0002 — Aeneas Williams",
               "live_face", "0002"),
        _Asset("face.0002.h", "Alternate Face Texture 0002 — Aeneas Williams",
               "live_face", "0002"),
        _Asset("face.0007.f", "Face / Eye Texture 0007 — Someone Else",
               "live_face", "0007"),
        _Asset("portrait.0002", "Portrait 0002 — Aeneas Williams",
               "player_portrait"),
        _Asset("portrait.0100", "Portrait 0100 — Unassigned / Historical",
               "player_portrait"),
        _Asset("portrait.0101", "Portrait 0101 — **************** ****",
               "player_portrait"),
        _Asset("p8.386.endzone", "End Zone North — Left", "p8_texture"),
    ]


class FaceLinkTests(unittest.TestCase):
    def test_a_player_finds_every_face_carrying_their_face_id(self) -> None:
        rows = [{"player_index": 1, "outer_index": 9,
                 "name": "Aeneas Williams", "face_id": "0002"}]
        summary = build_player_assets(rows, _catalog())[0]
        self.assertEqual(len(summary.face_assets), 2)
        self.assertEqual(
            {a.asset_id for a in summary.face_assets},
            {"face.0002.f", "face.0002.h"},
        )

    def test_the_face_link_is_labelled_as_coming_from_the_record(self) -> None:
        """The strong link. It must be distinguishable from the weak one."""
        rows = [{"player_index": 1, "outer_index": 9,
                 "name": "Aeneas Williams", "face_id": "0002"}]
        summary = build_player_assets(rows, _catalog())[0]
        for asset in summary.face_assets:
            self.assertEqual(asset.link, "face_id")

    def test_another_players_face_is_not_returned(self) -> None:
        rows = [{"player_index": 1, "outer_index": 9,
                 "name": "Aeneas Williams", "face_id": "0002"}]
        summary = build_player_assets(rows, _catalog())[0]
        self.assertNotIn("face.0007.f",
                         {a.asset_id for a in summary.assets})

    def test_a_player_with_no_face_says_so_rather_than_guessing(self) -> None:
        rows = [{"player_index": 2, "outer_index": 9,
                 "name": "Nobody At All", "face_id": "9999"}]
        summary = build_player_assets(rows, _catalog())[0]
        self.assertEqual(summary.face_assets, ())
        self.assertTrue(any("9999" in note for note in summary.notes))


class PortraitLinkTests(unittest.TestCase):
    def test_a_portrait_matched_by_name_is_labelled_by_name(self) -> None:
        """The weak link, and it must never masquerade as the strong one."""
        rows = [{"player_index": 1, "outer_index": 9,
                 "name": "Aeneas Williams", "face_id": "0002"}]
        summary = build_player_assets(rows, _catalog())[0]
        self.assertEqual(len(summary.portrait_assets), 1)
        self.assertEqual(summary.portrait_assets[0].link, "by_name")

    def test_placeholder_portraits_are_never_matched(self) -> None:
        for name in ("Unassigned / Historical", "**************** ****"):
            with self.subTest(name=name):
                rows = [{"player_index": 3, "outer_index": 9,
                         "name": name, "face_id": "0002"}]
                summary = build_player_assets(rows, _catalog())[0]
                self.assertEqual(summary.portrait_assets, ())

    def test_name_matching_ignores_spacing_and_case(self) -> None:
        rows = [{"player_index": 1, "outer_index": 9,
                 "name": "  aeneas   WILLIAMS ", "face_id": "0002"}]
        summary = build_player_assets(rows, _catalog())[0]
        self.assertEqual(len(summary.portrait_assets), 1)

    def test_a_player_with_no_portrait_says_the_roster_does_not_point_at_one(
        self,
    ) -> None:
        rows = [{"player_index": 4, "outer_index": 9,
                 "name": "Someone Else", "face_id": "0007"}]
        summary = build_player_assets(rows, _catalog())[0]
        self.assertEqual(summary.portrait_assets, ())
        self.assertTrue(
            any("numbered separately" in note for note in summary.notes)
        )


class EquipmentTests(unittest.TestCase):
    def test_the_five_shared_textures_are_the_ones_that_exist(self) -> None:
        keys = {key for key, _label in SHARED_EQUIPMENT}
        self.assertEqual(keys, {
            "shoes_taped", "wristband_qb", "elbowpad_taped",
            "elbowpad_rubber", "elbowpad_elastic",
        })

    def test_the_note_refuses_to_imply_per_player_ownership(self) -> None:
        self.assertIn("not per-player", EQUIPMENT_NOTE)
        self.assertIn("changes it for everybody", EQUIPMENT_NOTE)

    def test_equipment_is_never_attached_to_a_player(self) -> None:
        rows = [{"player_index": 1, "outer_index": 9,
                 "name": "Aeneas Williams", "face_id": "0002"}]
        summary = build_player_assets(rows, _catalog())[0]
        for asset in summary.assets:
            self.assertIn(asset.kind, {"live_face", "player_portrait"})

    def test_the_rows_are_available_for_a_panel(self) -> None:
        self.assertEqual(equipment_rows(), SHARED_EQUIPMENT)


class WiringTests(unittest.TestCase):
    def test_the_roster_workspace_mounts_a_player_assets_tab(self) -> None:
        source = (
            _REPO_ROOT / "mod_editor" / "gui" / "studio_qt.py"
        ).read_text(encoding="utf-8")
        self.assertIn('roster_tabs.addTab(self._build_player_assets_page(), "Player Assets")',
                      source)
        self.assertIn("def _build_player_assets_page", source)

    def test_the_panel_reads_face_id_from_the_roster_player(self) -> None:
        """The join must come from the record, not from a name heuristic."""
        source = (
            _REPO_ROOT / "mod_editor" / "gui" / "studio_qt.py"
        ).read_text(encoding="utf-8")
        start = source.index("    def _player_asset_summaries(")
        block = source[start:start + 1800]
        self.assertIn("player.face_id", block)
        self.assertIn("player.display_name", block)

    def test_the_panel_reports_which_link_each_asset_used(self) -> None:
        source = (
            _REPO_ROOT / "mod_editor" / "gui" / "studio_qt.py"
        ).read_text(encoding="utf-8")
        start = source.index("    def _show_player_assets(")
        block = source[start:start + 1200]
        self.assertIn("linked by the roster record", block)
        self.assertIn("matched by name", block)


if __name__ == "__main__":
    unittest.main()

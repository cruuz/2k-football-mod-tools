"""Star decal under tagged players: the in-place predicate rewrite, the roster tag, and the UI column.

Roster and GUI wiring regressions. End-to-end draw execution is in
``test_nfl2k5_player_star_draw.py``; a predicate-only test cannot prove a decal.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import struct
import sys
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from mod_editor.core import nfl2k5_player_star as ps  # noqa: E402
from mod_editor.core import nfl2k5_player_tags as pt  # noqa: E402
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest  # noqa: E402

EXTRACTION = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted"))
GAME = EXTRACTION / "ESPN NFL 2K5 (USA)"
XBE = GAME / "default.xbe"
PACKS = GAME / "vc_53450030"
BASE = 0x10000
HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
HAVE_CAPSTONE = importlib.util.find_spec("capstone") is not None


def _rost_body() -> bytes:
    from nfl2k5_playbook_position_recode import OuterImage

    with OuterImage(GAME) as archive:
        entry = archive.entries[pt.ROST_OUTER_INDEX]
        resource = archive.read(entry.virtual_offset, entry.size)
    return resource[pt.RESOURCE_HEADER_SIZE:]


class ShapeTests(unittest.TestCase):
    def test_a_payload_without_sections_is_foreign(self) -> None:
        self.assertEqual(ps.status(b"XBEH" + b"\0" * 0x200), "foreign")
        with self.assertRaises(ps.PlayerStarError):
            ps.apply(b"XBEH" + b"\0" * 0x200)


    def test_build_plan_presets_and_availability(self) -> None:
        from mod_editor.core import mod_build

        self.assertTrue(mod_build.BuildPlan(source="s", target="t", player_star=True).wants_xbe_patch())
        self.assertFalse(mod_build.BuildPlan(source="s", target="t").player_star)
        self.assertEqual(mod_build.BuildPlan(source="s", target="t").player_tags, [])
        self.assertFalse(mod_build.PRESETS["softdrink_basic"]["player_star"])
        self.assertTrue(mod_build.PRESETS["softdrink_advanced"]["player_star"])
        self.assertTrue(mod_build.PRESETS["softdrink_experimental"]["player_star"])
        self.assertTrue(mod_build.availability()["player_star"])
        self.assertTrue(mod_build.availability()["player_tags"])
        plan = mod_build.apply_preset(mod_build.BuildPlan(source="s", target="t"), "softdrink_advanced")
        self.assertTrue(plan.player_star)
        self.assertIn("player_star", plan.to_recipe())
        self.assertIn("player_tags", plan.to_recipe())


    def test_a_bare_xbe_refuses_the_tags(self) -> None:
        from mod_editor.core import mod_build
        import tempfile

        if str(REPO / "tests") not in sys.path:      # CI runs each file standalone: tests/ is not on sys.path there
            sys.path.insert(0, str(REPO / "tests"))
        from nfl2k5_throw_tuning_test import _build_progression_xbe  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "default.xbe"
            source.write_bytes(_build_progression_xbe())
            plan = mod_build.BuildPlan(source=str(source), target=str(Path(tmp) / "out.xbe"),
                                       player_tags=["17"])
            with self.assertRaises(ValueError):
                mod_build.build(plan)


class TagShapeTests(unittest.TestCase):
    def test_the_tag_is_a_pad_byte_of_the_record(self) -> None:
        self.assertEqual(ps.TAG_RECORD_OFFSET, 0x53)
        self.assertEqual(ps.TAG_BIT, 1)
        self.assertEqual(ps.TAG_RECORD_OFFSET, pt.PLAYER_SIZE - 1)
        self.assertEqual(pt.PLAYER_SIZE, 0x54)
        self.assertEqual(pt.POOLS, ("primary", "secondary"))

    def test_normalise_tags_drops_blanks_and_keeps_order(self) -> None:
        self.assertEqual(pt.normalise_tags(["7", "", "  ", "Vick,Michael", 3, True, None]),
                         ["7", "Vick,Michael", 3])
        self.assertEqual(pt.normalise_tags(None), [])


@unittest.skipUnless(PACKS.is_dir(), "retail extraction not present")
class RetailRosterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.body = _rost_body()
        cls.roster = pt.parse_body(cls.body)

    def test_the_retail_roster_has_the_star_bit_clear_everywhere(self) -> None:
        self.assertEqual(len(self.roster.by_pool("primary")), pt.RETAIL_PRIMARY_COUNT)
        self.assertEqual(len(self.roster.by_pool("secondary")), pt.RETAIL_SECONDARY_COUNT)
        self.assertEqual(len(self.roster.players), pt.RETAIL_PRIMARY_COUNT + pt.RETAIL_SECONDARY_COUNT)
        # every record's whole pad byte is zero, not just its bit 0
        self.assertEqual({self.body[p.offset + ps.TAG_RECORD_OFFSET] for p in self.roster.players}, {0})
        self.assertEqual(self.roster.tagged, [])
        self.assertEqual(pt.body_status(self.body), "retail")

    def test_the_contract_block_and_the_other_candidates_are_live_data(self) -> None:
        """Why the tag is +0x53: every offset proposed before it carries retail data.

        +0x0A / +0x24 / +0x26 / +0x27 are the contract block (value, years remaining, type and
        bonus tier, length) and +0x08 is the Player Type flags, so bit 0 of +0x27, +0x26 and +0x08
        is somebody's field; +0x24 bit 7 is set in retail data too."""

        taken = {offset: sum(1 for p in self.roster.players if self.body[p.offset + offset] & 1)
                 for offset in (0x27, 0x26, 0x08)}
        self.assertEqual(taken, {0x27: 981, 0x26: 386, 0x08: 155})
        union = {}
        for offset in (0x23, 0x24, 0x30, 0x31, 0x32, 0x33, 0x52, 0x53):
            bits = 0
            for player in self.roster.players:
                bits |= self.body[player.offset + offset]
            union[offset] = bits
        self.assertEqual(union[0x24] & 0x80, 0x80, "+0x24 bit 7 is set in retail records")
        # the bytes that really are zero across the whole retail roster
        self.assertEqual({o: v for o, v in union.items() if v == 0},
                         {0x23: 0, 0x30: 0, 0x31: 0, 0x32: 0, 0x33: 0, 0x52: 0, 0x53: 0})

    def test_tagging_changes_only_the_pad_byte_of_the_named_records(self) -> None:
        out, receipt = pt.apply_body(self.body, [0, "Vick,Michael", "5"])
        self.assertEqual(receipt["tagged"], 3)
        self.assertEqual(receipt["log"], [])
        self.assertEqual([row["index"] for row in receipt["players"]], [0, 88, 5])
        self.assertEqual([row["pool"] for row in receipt["players"]], ["primary"] * 3)
        self.assertEqual(receipt["players"][1]["name"], "Michael Vick")
        changed = [i for i in range(len(self.body)) if self.body[i] != out[i]]
        primary = self.roster.by_pool("primary")
        self.assertEqual(changed, sorted(primary[i].offset + ps.TAG_RECORD_OFFSET for i in (0, 5, 88)))
        self.assertEqual({out[i] for i in changed}, {ps.TAG_BIT})
        self.assertEqual(pt.body_status(out), "applied")
        # a round trip through the parser, and clearing everything gets retail back
        back = pt.parse_body(out)
        self.assertEqual([p.index for p in back.tagged], [0, 5, 88])
        cleared, _ = pt.apply_body(out, [0])
        self.assertEqual(pt.parse_body(cleared).tagged[0].index, 0)
        self.assertEqual(len(pt.parse_body(cleared).tagged), 1)

    def test_the_other_roster_passes_still_accept_the_result(self) -> None:
        """The pad byte is outside every region the other ROST gates hash."""

        from mod_editor.core import nfl2k5_team_history as history

        out, _receipt = pt.apply_body(self.body, [0, 88, 1000])
        self.assertEqual(history.body_status(self.body), "retail")
        self.assertEqual(history.body_status(out), "retail")
        self.assertEqual(history.pool_digest(history.parse_body(out)),
                         history.pool_digest(history.parse_body(self.body)))
        self.assertEqual(history.summary(out), history.summary(self.body))
        # and the reverse: the team-history writer leaves the tags alone
        rows, _prov = history.load_rows("retail")
        with_history, _ = history.apply_body(out, rows)
        self.assertEqual([p.index for p in pt.parse_body(with_history).tagged], [0, 88, 1000])

    def test_bad_tags_are_logged_not_raised(self) -> None:
        out, receipt = pt.apply_body(self.body, ["99999", "Nosuchname,Ever", "Smith"])
        self.assertEqual(receipt["tagged"], 0)
        self.assertEqual(out, self.body)
        self.assertEqual(len(receipt["log"]), 3)
        self.assertIn("no primary roster record with index 99999", receipt["log"][0])
        self.assertIn("no roster record matches", receipt["log"][1])
        self.assertIn("ambiguous", receipt["log"][2])

    def test_more_than_nine_tags_needs_no_quota_warning(self) -> None:
        _out, receipt = pt.apply_body(self.body, [str(i) for i in range(12)])
        self.assertEqual(receipt["tagged"], 12)
        self.assertEqual(receipt["log"], [])

    def test_status_reads_the_extraction(self) -> None:
        self.assertEqual(pt.status(GAME), "retail")
        players = pt.read_players(GAME)
        self.assertEqual(len(players), pt.RETAIL_PRIMARY_COUNT + pt.RETAIL_SECONDARY_COUNT)
        self.assertTrue(all(not p.tagged for p in players))
        self.assertEqual(players[88].display, "Michael Vick")
        self.assertEqual(players[88].key, "Vick,Michael,1980-06-28")
        # a pad byte carrying anything but the tag bit is foreign
        body = bytearray(self.body)
        body[self.roster.players[3].offset + ps.TAG_RECORD_OFFSET] = 0x02
        self.assertEqual(pt.body_status(bytes(body)), "foreign")


class StarColumnTests(unittest.TestCase):
    """The ★ Star column in Text & Rosters and the list the Build tab reads."""

    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PyQt5.QtWidgets import QApplication
        except Exception as exc:  # noqa: BLE001
            raise unittest.SkipTest(f"PyQt5 not available: {exc}")
        cls.app = QApplication.instance() or QApplication([])

    def test_the_column_ticks_primary_players_and_feeds_the_build_plan(self) -> None:
        from PyQt5.QtCore import Qt

        from mod_editor.gui.text_rosters_panel import (CurrentPlayerTableModel, current_roster_players,
                                                       star_tag_for)
        sys.path.insert(0, str(REPO / "tests" / "mod_editor"))
        from test_text_rosters_panel import FakeHost, catalog_fixture  # noqa: PLC0415

        catalog = catalog_fixture()
        host = FakeHost(catalog)
        rows = current_roster_players(catalog)
        tags: set[str] = set()
        changes: list[int] = []
        model = CurrentPlayerTableModel(host, catalog, tags, lambda: changes.append(len(tags)))
        model.set_rows(rows)
        self.assertEqual(model.HEADERS[model.STAR_COLUMN], "★ Star")
        self.assertEqual(model.columnCount(), 8)
        primary = [r for r in rows if r.player.pool == "primary_players"]
        secondary = [r for r in rows if r.player.pool == "secondary_players"]
        self.assertTrue(primary and secondary)
        self.assertEqual(star_tag_for(primary[0].player), str(primary[0].player.player_index))
        self.assertIsNone(star_tag_for(secondary[0].player))
        for row, expected in ((rows.index(primary[0]), True), (rows.index(secondary[0]), False)):
            index = model.index(row, model.STAR_COLUMN)
            checkable = bool(model.flags(index) & Qt.ItemIsUserCheckable)
            self.assertEqual(checkable, expected)
            self.assertEqual(model.data(index, Qt.CheckStateRole) is not None, expected)
        index = model.index(rows.index(primary[0]), model.STAR_COLUMN)
        self.assertTrue(model.setData(index, Qt.Checked, Qt.CheckStateRole))
        self.assertEqual(tags, {star_tag_for(primary[0].player)})
        self.assertEqual(model.data(index, Qt.CheckStateRole), Qt.Checked)
        self.assertEqual(changes, [1])
        # a secondary row refuses the tick
        self.assertFalse(model.setData(model.index(rows.index(secondary[0]), model.STAR_COLUMN),
                                       Qt.Checked, Qt.CheckStateRole))
        self.assertEqual(tags, {star_tag_for(primary[0].player)})
        self.assertTrue(model.setData(index, Qt.Unchecked, Qt.CheckStateRole))
        self.assertEqual(tags, set())

    def test_the_build_tab_shows_and_plans_the_ticked_players(self) -> None:
        from mod_editor.gui.build_panel_qt import BuildPanel

        panel = BuildPanel(None)
        try:
            self.assertIn("none selected", panel.star_players_label.text())
            self.assertEqual(panel.plan().player_tags, [])
            panel.set_star_players(["88", "5"], ["Michael Vick", "Calvin Pace"])
            self.assertEqual(panel.star_players, ["88", "5"])
            self.assertIn("Michael Vick", panel.star_players_label.text())
            self.assertEqual(panel.plan().player_tags, ["88", "5"])
            self.assertFalse(panel.plan().player_star)
            panel.player_star_check.setChecked(True)
            self.assertTrue(panel.plan().player_star)
            panel.set_star_players([str(i) for i in range(12)])
            self.assertNotIn("at most", panel.star_players_label.text())
            panel.set_star_players([str(i) for i in range(30)])
            self.assertIn("at most 22", panel.star_players_label.text())
        finally:
            panel.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()

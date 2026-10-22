"""b778 of1: no CPU defender lines up past the line of scrimmage before the snap.

v0.6.1 shipped "Cover 1 Corner Fire" on Pittsburgh's Bear 46: a 4-3 crash-corner script whose Defense Start node
(0x1B, mode 0) walks the corner 3 yd up from HIS FORMATION SPOT.  On the 4-3 that spot is 4 yd deep; on Bear 46 it is
1.7 yd, so the corner stood 1.3 yd offside and the engine flagged CPU PIT #5 (Jalen Ramsey) before the snap three or
four times in one game.  The same borrowing put corners or the strong safety past the line on 17 Bear 46 plays in 13
books.

* the linter rule DEF_PRESNAP_ACROSS_LINE and the generator's onside rule, on synthetic chains (run anywhere);
* every shipped defense pack, from the repository alone: each authored spot-relative walk-up stays onside on the
  pack formation it is listed on (run anywhere);
* with the private retail XISO: all 32 retail team books are clean under the rule (it is retail's own geometry), and
  every defensive play of every composed SOFTDRINK book (offense pack, then defense pack, exactly what Build writes)
  keeps every defender on his side of the line before the snap.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(ROOT / 'pb/v2/defense')]
sys.dont_write_bytecode = True

from mod_editor.core import nfl2k5_defense_lint as dlint  # noqa: E402
from mod_editor.core import nfl2k5_play_codec as codec  # noqa: E402
from mod_editor.core import nfl2k5_playbook_pack as pk  # noqa: E402

TEAMS = pk.TEAM_BOOKS
FT = codec.FT_CM
YD = codec.YD_CM
IMAGE = Path(os.environ.get('NFL2K5_RETAIL_IMAGE', '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso'))


def start(mode, x, y, lane=0):
    return (0x1B, [mode, 0, x, y, lane, 0])


def crash_corner(y=-9 * FT):
    return [start(0, 0.0, y, 16), (0x0B, [1, 16, 0])]


def pack_path(team: str) -> Path:
    return ROOT / f'data/playbooks/softdrink_{team.lower()}_defense.2k5book'


def offense_path(team: str) -> Path:
    return ROOT / f"data/playbooks/softdrink_{'giants' if team == 'NYG' else team.lower()}_modern.2k5book"


class Rule(unittest.TestCase):
    def test_only_spot_relative_starts_move_a_defender(self):
        self.assertEqual(dlint.presnap_offset(crash_corner()), (0.0, -9 * FT))
        for mode in (1, 2, 3):        # line- or receiver-anchored: the engine places those itself
            self.assertIsNone(dlint.presnap_offset([start(mode, 0.0, -9 * FT), (0x0B, [1, 16, 0])]))
        self.assertIsNone(dlint.presnap_offset([(0x0B, [1, 16, 0])]))
        self.assertIsNone(dlint.presnap_offset([]))

    def test_v061_bear_corner_is_offside_and_the_4_3_one_is_not(self):
        self.assertAlmostEqual(dlint.presnap_depth(152, crash_corner()), 152 - 274.32)    # Bear 46 press spot
        self.assertAlmostEqual(dlint.presnap_depth(365, crash_corner()), 365 - 274.32)    # retail 4-3 spot
        self.assertLess(dlint.presnap_depth(152, crash_corner()), -dlint.ACROSS_LINE_TOLERANCE_CM)
        self.assertGreater(dlint.presnap_depth(365, crash_corner()), 0)
        self.assertIn('DEF_PRESNAP_ACROSS_LINE', dlint.ERROR_CODES)


class Generator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import build as B
        cls.B = B

    def onside(self, chains, targets, source=()):
        return self.B.onside_presnap(chains, targets, source)

    def test_crash_corner_stops_where_retail_put_him(self):
        chains = [None] * 9 + [crash_corner(), None]
        out, changed = self.onside(chains, {9: [152]}, [0] * 9 + [365, 365])
        self.assertEqual([c[0] for c in changed], [9])
        y = out[9][0][1][3]
        self.assertAlmostEqual(y, -2 * FT)                       # 3 ft short of the 4-3 walk-up
        self.assertAlmostEqual(152 + y, 152 - 2 * FT)            # 1.0 yd off the ball, as on the retail 4-3
        self.assertEqual(out[9][1], chains[9][1])                # the blitz itself is untouched
        self.assertEqual(out[9][0][1][:3], chains[9][0][1][:3])
        self.assertIsNone(out[0])

    def test_never_moves_a_defender_back_and_never_past_the_line(self):
        ss = [start(0, 182.88, -15 * FT), (0x0D, [0, 1645.92, 7, 9, 8, 0, 0])]
        out, changed = self.onside([None] * 8 + [ss, None, None], {8: [411]}, [0] * 8 + [1097, 0, 0])
        self.assertAlmostEqual(out[8][0][1][3], 0.0)              # retail wanted 7 yd; the box safety stays at 4.5
        self.assertAlmostEqual(out[8][0][1][2], 0.0)              # on his spot: no sideways step into the Mike
        self.assertEqual(changed[0][3], 411)
        out, _ = self.onside([crash_corner(-20 * FT)], {0: [152]})   # source unknown
        self.assertGreaterEqual(152 + out[0][0][1][3], self.B.MIN_WALKUP_CM)
        self.assertLessEqual(152 + out[0][0][1][3], 152)

    def test_onside_walkups_and_other_modes_are_untouched(self):
        chains = [crash_corner(), [start(2, 0.0, -9 * FT), (0x0B, [1, 16, 0])], [start(1, 0.0, 0.0), (0x0B, [1, 8, 0])]]
        out, changed = self.onside(chains, {0: [365], 1: [152], 2: [0]}, [365, 152, 0])
        self.assertEqual(changed, [])
        self.assertEqual(out, chains)

    def test_shared_record_uses_its_shallowest_formation(self):
        out, changed = self.onside([crash_corner()], {0: [365, 152]}, [365])
        self.assertEqual(len(changed), 1)
        self.assertGreaterEqual(152 + out[0][0][1][3], 0)


class ShippedPacks(unittest.TestCase):
    """Repository only: every authored spot-relative walk-up stays onside on the pack formation of its home."""

    def test_every_authored_walkup_stays_onside(self):
        bad = []
        for team in TEAMS:
            pack = pk.load_pack(pack_path(team))
            spots = {f.replace_name: f.slot_positions for f in pack.formations if f.replace_name}
            for play in pack.plays:
                where = spots.get(play.defense_formation or '')
                if where is None:
                    continue
                for slot, chain in enumerate(play.assignments):
                    depth = dlint.presnap_depth(where[slot][1], chain) if chain else None
                    if depth is not None and depth < -dlint.ACROSS_LINE_TOLERANCE_CM:
                        bad.append(f'{team} {play.id} "{play.custom_name}" slot {slot}: {depth / YD:+.2f} yd')
        self.assertEqual(bad, [])


@unittest.skipUnless(IMAGE.is_file(), f'private retail XISO absent: {IMAGE}')
class ComposedBooks(unittest.TestCase):
    """Every defensive play listed on every defensive formation of every composed team book (offense pack, then the
    defense pack: Build's order) keeps every defender on his side of the line before the snap."""

    @classmethod
    def setUpClass(cls):
        from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
        from mod_editor.core.nfl2k5_complete_offense import compile_offense
        from mod_editor.core.nfl2k5_formation_play_writer import compile_formation_play_creations
        from mod_editor.core import nfl2k5_playbook_inspector as ip
        cls.retail, cls.composed = {}, {}
        with OuterImage(IMAGE) as image:
            for team in TEAMS:
                raw = image.read_entry(BOOK_ENTRIES[team])
                cls.retail[team] = raw
                source = compile_offense(raw, pk.load_pack(offense_path(team)), asset_id='book:' + team).replacement
                # The defense compile Build runs (minus its native scoring pass, which reads plays, not alignments).
                rows = pk.pack_requests(pk.load_pack(pack_path(team)), 'pack-apply', ip.parse_playbook_resource(source))
                cls.composed[team] = compile_formation_play_creations(source, *rows).replacement

    def test_retail_team_books_are_clean(self):
        self.assertEqual({t: [f.message for f in dlint.play_findings(raw)] for t, raw in self.retail.items()
                          if dlint.play_findings(raw)}, {})

    def test_every_defender_stays_onside_before_the_snap(self):
        found = {t: [f'{f.formation}: {f.message}' for f in dlint.play_findings(raw)] for t, raw in self.composed.items()}
        self.assertEqual({t: v for t, v in found.items() if v}, {})


if __name__ == '__main__':
    unittest.main()

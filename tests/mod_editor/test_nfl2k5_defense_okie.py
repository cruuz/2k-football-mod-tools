"""b776 de2: EDGE players on the odd (3-4 Okie) fronts rush on base calls and drop only on designed zone blitzes.

Pure-data tests (the chain surgery, the verdicts, the edge accounting) run anywhere.  The integration test compiles four
odd-front teams from the committed packs on the private retail XISO (NFL2K5_RETAIL_IMAGE) and skips without it: it
applies the position recode and counts, over the CPU's call weights, how often each EDGE slot covers.
"""
from __future__ import annotations

from collections import defaultdict
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(ROOT / 'pb/v2/defense')]
sys.dont_write_bytecode = True

import library as L  # noqa: E402
import okie  # noqa: E402

YD = 91.44
IMAGE = Path(os.environ.get('NFL2K5_RETAIL_IMAGE', '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso'))
XBE = Path(os.environ.get('NFL2K5_SCORING_XBE', '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe'))
# 3-4 base: weak edge OLB (slot 0), three linemen, two inside backers, strong edge OLB (slot 6)
KINDS_34 = [15, 12, 12, 13, 14, 14, 15, 16, 17, 18, 18]
START = (0x1B, [0, 0, 0, 0, 0, 0])


def zone(x_yd, y_yd, mode=4):
    return [START, (0x0D, [x_yd * YD, y_yd * YD, 5, 5, mode, 0, 0])]


def rush(lane):
    return [START, (0x0B, [2, lane, 0])]


def man():
    return [START, (0x0E, [0, 2 * YD, 0, 0, 0, 0, 0, 0])]


def chains(**slots):
    out = [[] for _ in range(11)]
    for k, v in slots.items():
        out[int(k[1:])] = v
    return out


def cover3(edge0, edge6, ilb4=None, ilb5=None):
    """Three deep, underneath zones for the inside backers and the strong safety; the edges as given."""
    return chains(s0=edge0, s4=ilb4 or zone(7, 8), s5=ilb5 or zone(-2, 8), s6=edge6, s7=zone(0, 18, 8), s8=zone(-12, 7),
                  s9=zone(15, 18, 9), s10=zone(-15, 18, 10))


class Role:
    def __init__(self, kinds, name='3-4 Okie', key='base'):
        self.kinds, self.source_name, self.key = kinds, name, key


def front_slots(role):
    return {1, 2, 3}


class ChainSurgery(unittest.TestCase):
    def test_a_far_vacated_zone_moves_the_nearest_same_side_defender_halfway(self):
        c = cover3(rush(15), zone(-18, 4))
        taken = set()
        self.assertTrue(okie.rehome(c, 6, taken))
        self.assertEqual(taken, {8})                                  # the strong safety, the nearest on that side
        x, y = c[8][1][1][0] / YD, c[8][1][1][1] / YD
        self.assertAlmostEqual(x, -15.0, places=3)                    # halfway from (-12, 7) to (-18, 4)
        self.assertAlmostEqual(y, 5.5, places=3)

    def test_an_overlapping_neighbour_just_keeps_his_zone(self):
        c = cover3(rush(15), zone(-14, 7))
        before = c[8][1][1][:2]
        self.assertTrue(okie.rehome(c, 6, set()))
        self.assertEqual(c[8][1][1][:2], before)

    def test_deep_zones_and_nobody_to_take_it_are_refused(self):
        c = cover3(rush(15), zone(-15, 18, 10))
        self.assertFalse(okie.rehome(c, 6, set()))
        lone = chains(s0=rush(15), s6=zone(-16, 5))
        self.assertFalse(okie.rehome(lone, 6, set()))

    def test_to_rush_turns_a_dropper_into_a_rusher_and_refuses_man(self):
        c = cover3(rush(15), zone(-16, 5))
        out = okie.to_rush(c, [6])
        self.assertEqual(L.first_action(out[6])[0], 0x0B)
        self.assertEqual(L.first_action(out[6])[1][1], 1)             # strong flat: the outside lane
        self.assertEqual(L.first_action(c[6])[0], 0x0D)               # the input is not touched
        c_man = cover3(rush(15), man())
        self.assertIsNone(okie.to_rush(c_man, [6]))


class Verdicts(unittest.TestCase):
    role = Role(KINDS_34)

    def judge(self, c):
        return okie.classify_for_role(c, self.role, front_slots(self.role))

    def test_both_edges_rushing_is_a_base_call_and_not_a_blitz(self):
        verdict, st = self.judge(cover3(rush(15), rush(1)))
        self.assertEqual(verdict, 'base')
        self.assertEqual(st.edges, (0, 6))
        self.assertEqual(len(st.rushers), 5)
        self.assertEqual(st.n_rush, 4)                                # the edge pair counts once
        self.assertFalse(st.pressure)

    def test_the_retail_four_man_rush_with_a_covering_strong_edge_is_bad(self):
        verdict, st = self.judge(cover3(rush(15), zone(-16, 5)))
        self.assertEqual(verdict, 'bad')
        self.assertEqual(st.edge_drops, [6])

    def test_a_zone_blitz_is_designed_only_when_a_back_rushes_in_the_edges_place(self):
        verdict, st = self.judge(cover3(rush(15), zone(-16, 5), ilb5=rush(5)))
        self.assertEqual(verdict, 'designed')
        self.assertEqual(st.edge_drops, [6])
        self.assertEqual(st.extra, [5])
        self.assertTrue(st.pressure)                                  # three linemen, an edge and a back: five

    def test_both_edges_covering_is_bad_even_with_a_blitz(self):
        verdict, _ = self.judge(cover3(zone(14, 6), zone(-16, 5), ilb5=rush(5), ilb4=rush(9)))
        self.assertEqual(verdict, 'bad')

    def test_even_layouts_have_no_edge_accounting(self):
        st = L.structure(cover3(rush(15), rush(1)), KINDS_34, {0, 1, 2, 3}, 'even:4-3')
        self.assertEqual((st.edges, st.edge_credit), ((), 0))
        self.assertEqual(st.n_rush, len(st.rushers))

    def test_variants_contain_the_scripts_own_rushers_and_never_move_a_man_edge(self):
        sc = L.Script('X', 1, 't', 0x900444, '3-4', (), 4, cover3(rush(15), zone(-16, 5)),
                      L.structure(cover3(rush(15), zone(-16, 5)), KINDS_34, {1, 2, 3}, 'odd:3-4'), 'k1')
        patterns = {v.pattern for v in okie.variants(sc)}
        self.assertIn(frozenset({0}), patterns)
        self.assertIn(frozenset({0, 6}), patterns)
        self.assertTrue(all(0 in p for p in patterns))
        both = [v for v in okie.variants(sc) if v.pattern == frozenset({0, 6})][0]
        self.assertEqual(self.judge(both.chains)[0], 'base')


def weighted_edge_cover(raw):
    """{(formation, slot): cover share} over the CPU call weights (band cubed), per odd defensive formation."""
    from mod_editor.core import nfl2k5_play_library as lib, nfl2k5_playbook_inspector as insp
    curve = (2.0, 1.4, 1.0, 0.5, 0.1, 0.1, 0.1, 0.1)
    book = insp.parse_playbook_resource(raw)
    body = raw[32:]
    out = {}
    for f in book.formations:
        if lib.formation_record(body, f.index).type_code != 4:
            continue
        codes = lib.category_positions(body, lib.formation_category(body, f.index))
        entries = [(p, lib.decoded_chains(body, p.index)) for p in book.plays_for_formation(f.index) if p.family_id == 1]
        front = next(c for _, c in entries if lib.defense_component(c) == 'front')
        cover, total = defaultdict(float), 0.0
        for p, c in entries:
            if lib.defense_component(c) != 'coverage':
                continue
            w = curve[(p.flags_or_id >> 9) & 7] ** 3
            total += w
            eff = lib.effective_defense(front, c)
            for s, chain in enumerate(eff):
                if codes[s] & 31 == 12:                              # an EDGE slot after the recode
                    op = next((n[0] for n in chain if n[0] in (0x0B, 0x0D, 0x0E)), None)
                    if op in (0x0D, 0x0E):
                        cover[s] += w
        for s in {s for s, k in enumerate(codes) if k & 31 == 12 and s in (0, 4, 5, 6)}:
            out[(f.name, s)] = cover[s] / total
    return out


def line_violations(raw):
    """Noah's rule (10/18) over every defensive formation of one recoded PLAY resource: the two outermost slots of the line
    of scrimmage are EDGE, interior line slots are DT, linebacker slots are LB (not on the line), and an EDGE neither
    stands at linebacker depth nor inside the interior linemen.  A standing EDGE may be up to 2.1 yd off the ball.
    [(formation, [violation, ...])] for the formations that break it."""
    from mod_editor.core import nfl2k5_play_library as lib, nfl2k5_playbook_inspector as insp
    line_z, stand_z = YD + 1, 2.1 * YD
    book = insp.parse_playbook_resource(raw)
    body = raw[32:]
    out = []
    for f in book.formations:
        rec = lib.formation_record(body, f.index)
        if rec.type_code not in (4, 5, 7):
            continue
        kinds = [c & 31 for c in lib.category_positions(body, lib.formation_category(body, f.index))]
        pos = [(s.x[0], s.z[0]) for s in rec.slots]
        line = [s for s in range(11) if (kinds[s] in (13, 14, 15) and pos[s][1] <= line_z) or (kinds[s] == 12 and pos[s][1] <= stand_z)]
        bad = []
        if line:
            left, right = min(line, key=lambda s: (pos[s][0], s)), max(line, key=lambda s: (pos[s][0], s))
            bad += [f'outermost slot {s} is kind {kinds[s]}' for s in (left, right) if kinds[s] != 12]
            bad += [f'slot {s} (kind {kinds[s]}) on the line between the edge men' for s in line
                    if s not in (left, right) and kinds[s] != 13]
        for s in range(11):
            if kinds[s] == 12 and pos[s][1] > stand_z:
                bad.append(f'EDGE slot {s} off the line at {pos[s][1] / YD:.1f} yd')
        if bad:
            out.append((f.name, bad))
    return out


@unittest.skipUnless(IMAGE.is_file() and XBE.is_file(), 'needs the private retail XISO and default.xbe')
class CommittedPacks(unittest.TestCase):
    TEAMS = ('PIT', 'NE', 'SD', 'BUF', 'BAL', 'ARZ', 'DEN', 'TEN')

    @classmethod
    def setUpClass(cls):
        import build as B
        import nfl2k5_playbook_position_recode as rc
        xbe = XBE.read_bytes()
        cls.cover = {}
        cls.lines = {}
        for team in cls.TEAMS:
            offense = ROOT / 'data/playbooks' / f"softdrink_{'giants' if team == 'NYG' else team.lower()}_modern.2k5book"
            source, _ = B.compiled_source(team, offense.parent)
            from mod_editor.core import nfl2k5_playbook_pack as pk
            pack = pk.load_pack(ROOT / f'data/playbooks/softdrink_{team.lower()}_defense.2k5book')
            raw = pk.apply_pack_to_resource(source, pack, xbe=xbe).replacement
            with rc.OuterImage(IMAGE) as img:
                book = rc.parse_book(team, img.entries[rc.BOOK_ENTRIES[team]], raw)
            table = bytearray(book.table_bytes())
            for cat in book.categories:
                new, _ = rc.recode_codes(cat.codes, cat.formation_type)
                table[cat.index * rc.CATEGORY_SIZE + 5: cat.index * rc.CATEGORY_SIZE + 16] = bytes(new)
            out = bytearray(raw)
            at = 32 + rc.CATEGORY_BASE
            out[at:at + len(table)] = table
            cls.cover[team] = weighted_edge_cover(bytes(out))
            cls.lines[team] = line_violations(bytes(out))

    def test_no_edge_covers_on_more_than_fifteen_percent_of_the_calls_the_cpu_makes(self):
        for team, rows in self.cover.items():
            self.assertEqual(bool(rows), team not in ('ARZ', 'DEN'), team)     # the even teams have no odd formation
            for (formation, slot), share in rows.items():
                with self.subTest(team=team, formation=formation, slot=slot):
                    self.assertLessEqual(share, 0.15)

    def test_the_outermost_line_slots_are_edge_in_every_pack_formation(self):
        for team, found in self.lines.items():
            with self.subTest(team=team):
                self.assertEqual(found, [])

    def test_buf_pressure_nickel_edges_rush(self):
        rows = {k: v for k, v in self.cover['BUF'].items() if k[0] == 'Nickel 3-3 Pressure'}
        self.assertTrue(rows)
        self.assertLess(max(rows.values()), 0.05)                      # it used to be 100 percent on the strong edge


if __name__ == '__main__':
    unittest.main()

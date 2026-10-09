"""Beta 77 (GOAL P5/P6/P9): SOFTDRINK defense v2 packs, the defensive alignment linter and formation situation ratings.

Pure-data tests run anywhere; the compile tests need the private retail XISO (NFL2K5_RETAIL_IMAGE) and skip without it.
"""
from __future__ import annotations

import json
import os
import re
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
sys.dont_write_bytecode = True

from mod_editor.core import nfl2k5_defense_lint as dlint  # noqa: E402
from mod_editor.core import nfl2k5_playbook_pack as pk  # noqa: E402
from mod_editor.core import nfl2k5_formation_play_writer as writer  # noqa: E402
from mod_editor.core import nfl2k5_play_codec as codec  # noqa: E402

TEAMS = pk.TEAM_BOOKS
YD = codec.YD_CM
IMAGE = Path(os.environ.get('NFL2K5_RETAIL_IMAGE', '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso'))
DL, LB, DB = 0x0C, 0x0E, 0x12          # DE, MLB, CB kinds


def pack_path(team: str) -> Path:
    return ROOT / f'data/playbooks/softdrink_{team.lower()}_defense.2k5book'


def offense_path(team: str) -> Path:
    return ROOT / f"data/playbooks/softdrink_{'giants' if team == 'NYG' else team.lower()}_modern.2k5book"


def four_three(**moves):
    """Retail 4-3 geometry (cm) with optional slot moves."""
    pos = [(365, 0), (-365, 0), (150, 0), (-150, 0), (402, 365), (0, 457), (-402, 365),
           (640, 1188), (-640, 1097), (1371, 365), (-1371, 365)]
    for s, xy in moves.items():
        pos[int(s[1:])] = xy
    codes = [12, 12, 13, 13, 15, 14, 15, 16, 17, 18, 18]
    stances = [3, 3, 3, 3, 1, 1, 1, 1, 1, 1, 1]
    return pos, codes, stances


class Linter(unittest.TestCase):
    def codes_of(self, findings):
        return sorted({f.code for f in findings})

    def test_retail_shape_is_clean(self):
        pos, codes, st = four_three()
        self.assertEqual(dlint.formation_findings(dlint.DefenseFormation('4-3', pos, codes, st)), [])

    def test_spacing_and_middle_standing(self):
        pos, codes, st = four_three(s4=(76, 91), s6=(-76, 91))
        found = dlint.formation_findings(dlint.DefenseFormation('Nickel', pos, codes, st))
        self.assertEqual(self.codes_of(found), ['DEF_MIDDLE_STANDING', 'DEF_SPACING'])
        named = dlint.formation_findings(dlint.DefenseFormation('Nickel Mug', pos, codes, st))
        self.assertEqual(self.codes_of(named), ['DEF_SPACING'])      # a name never excuses 1.66 yd

    def test_pressure_look_cannot_be_the_whole_category(self):
        pos, codes, st = four_three(s2=(255, 0), s3=(-255, 0), s0=(460, 0), s1=(-460, 0), s4=(80, 100), s6=(-80, 100))
        f = dlint.DefenseFormation('Nickel Mug', pos, codes, st, 3, 7)
        self.assertEqual(dlint.formation_findings(f), [])
        self.assertEqual(self.codes_of(dlint.formation_findings(f, sole_in_category=True)), ['DEF_PRESSURE_AS_BASE'])
        self.assertEqual(self.codes_of(dlint.lint_formations([f])), ['DEF_PRESSURE_AS_BASE'])

    def test_lopsided_front_and_backfield(self):
        # v0.5 "Tite Look": nobody on the line outside the left tackle.
        pos, codes, st = four_three(s0=(365, 46), s1=(137, 46), s2=(-137, 46), s3=(0, 46))
        self.assertIn('DEF_NO_EDGE', self.codes_of(dlint.formation_findings(dlint.DefenseFormation('4-3', pos, codes, st))))
        pos, codes, st = four_three(s5=(0, -100))
        self.assertIn('DEF_ACROSS_LINE', self.codes_of(dlint.formation_findings(dlint.DefenseFormation('4-3', pos, codes, st))))

    def test_technique_labels(self):
        self.assertEqual([dlint.technique(x) for x in (0, 50, 205, 255, 365, 420, 515, 700)],
                         ['0', '1', '3', '4i', '5', '7', '9', 'wide'])

    def test_ascii_diagram_draws_the_line(self):
        pos, codes, st = four_three()
        art = dlint.front_diagram(dlint.DefenseFormation('4-3', pos, codes, st))
        self.assertIn('offensive line', art)
        self.assertEqual(art.splitlines()[-2].count('E') + art.splitlines()[-2].count('T'), 4)


class Situation(unittest.TestCase):
    def test_bits_and_validation(self):
        flags = 0x18514500
        out = writer.apply_situation(flags, (1, 3, 4))
        self.assertEqual([(out >> s) & 7 for s in (21, 24, 27)], [1, 3, 4])
        self.assertEqual(out & ~writer.SITUATION_MASK, flags & ~writer.SITUATION_MASK)
        self.assertEqual(writer.apply_situation(flags, None), flags)
        for bad in ((1, 2), (0, 8, 1), (1.0, 2, 3), 'abc'):
            with self.assertRaises(Exception):
                writer.situation_from(bad)
        req = writer.formation_request_from_mapping(dict(asset_id='book:KC', donor_formation_index=25,
                                                         situation=[2, 1, 2]))
        self.assertEqual(req.situation, (2, 1, 2))
        self.assertIn('situation', req.provider_edit())

    def test_pack_round_trip(self):
        pack = pk.load_pack(pack_path('KC'))
        text = json.dumps(pack.to_json())
        again = pk.loads_pack(text)
        self.assertEqual([f.situation for f in again.formations], [f.situation for f in pack.formations])
        self.assertTrue(all(f.situation is not None for f in pack.formations))


class Packs(unittest.TestCase):
    """The 32 shipped v2 defense packs, from the repository alone."""

    @classmethod
    def setUpClass(cls):
        cls.packs = {t: pk.load_pack(pack_path(t)) for t in TEAMS}
        cls.manifest = {r['team']: r for r in json.loads((ROOT / 'pb/v2/defense/out/manifest.json').read_text())['teams']}

    def test_offline_checks_pass(self):
        for team, pack in self.packs.items():
            with self.subTest(team=team):
                self.assertEqual(pack.schema, pk.DEFENSE_SCHEMA)
                self.assertEqual(pack.book.resolved_targets(), (team,))
                check = pk.check_pack(pack)
                self.assertTrue(check.ok, check.text())
                self.assertFalse(pack.menus)

    def test_every_formation_is_clean(self):
        for team, pack in self.packs.items():
            for f in pack.formations:
                with self.subTest(team=team, formation=f.custom_name):
                    stances = [3 if (c & 31) in (12, 13) else 1 for c in f.position_codes]
                    view = dlint.DefenseFormation(f.custom_name, f.slot_positions, f.position_codes, stances)
                    self.assertEqual([x.message for x in dlint.formation_findings(view)], [])
                    self.assertIsNotNone(f.situation)

    def test_mug_is_an_extra_named_pressure_formation(self):
        mugs = {t for t, p in self.packs.items() if any('Mug' in f.custom_name for f in p.formations)}
        self.assertTrue({'KC', 'MIN', 'WAS', 'TB', 'DEN'} <= mugs, mugs)
        for team in mugs:
            mug = next(f for f in self.packs[team].formations if 'Mug' in f.custom_name)
            with self.subTest(team=team):
                self.assertIsNone(mug.replace_index)                    # appended, the Nickel stays
                self.assertEqual(mug.situation[2], 1)                   # long yardage
                self.assertGreaterEqual(min(mug.situation[:2]), 4)      # never on short or medium yardage
                linked = [p for p in self.packs[team].plays if p.link_formation == 'mug']
                self.assertTrue(any(p.component == 'front' for p in linked))
                self.assertTrue(any(p.component == 'coverage' for p in linked))

    def test_bear_competes_inside_the_base_personnel_group(self):
        """0x2093F0 draws same-code defensive groups with equal weight, so the Bear only becomes situational when it
        joins the 4-3 group (donor = the 4-3 record) and the formation ratings choose it on short yardage."""
        merged = 0
        for team, pack in self.packs.items():
            bear = next((f for f in pack.formations if f.replace_name == 'Bear'), None)
            base = next((f for f in pack.formations if f.replace_name == '4-3'), None)
            if bear is None or base is None:
                continue
            with self.subTest(team=team):
                if bear.position_codes == base.position_codes:
                    merged += 1
                    self.assertEqual(bear.donor.index, base.replace_index)
                    self.assertEqual(bear.category_index, base.category_index)
                    self.assertLess(bear.situation[0], base.situation[0])      # better on short yardage
                    self.assertGreater(bear.situation[1], base.situation[1])   # worse on 1st and 10
        self.assertGreaterEqual(merged, 20)

    def test_names_are_modern_and_unique(self):
        for team, pack in self.packs.items():
            names = [p.custom_name for p in pack.plays]
            with self.subTest(team=team):
                self.assertEqual(len(names), len(set(names)))
                self.assertFalse([n for n in names if n.startswith('PB ') or 'Front ' in n])
                self.assertTrue(all(len(n) <= 40 for n in names))

    def test_spy_only_kc(self):
        for team, pack in self.packs.items():
            with self.subTest(team=team):
                self.assertEqual(sum(len(p.spy_slots) for p in pack.plays), int(team == 'KC'))

    def test_only_cpu_band_differs_from_donor(self):
        for team, pack in self.packs.items():
            for p in pack.plays:
                self.assertEqual((p.play_flags ^ p.donor.flags) & ~0xE00, 0, (team, p.custom_name))

    def test_every_team_has_core_and_variety(self):
        core = {'Cover 3', 'Cover 1', 'Cover 2', 'Cover 4', 'Cover 6', '2-Man', 'Cover 0', 'Fire Zone', 'Sim'}
        for team, pack in self.packs.items():
            names = [p.custom_name for p in pack.plays if p.component == 'coverage']
            fronts = [p.custom_name for p in pack.plays if p.component == 'front']
            with self.subTest(team=team):
                have = {c for c in core if any(n.startswith(c) or c in n for n in names)}
                self.assertGreaterEqual(len(have), 7, sorted(have))
                self.assertGreaterEqual(len(set(names)), 35)
                self.assertGreaterEqual(len(fronts), 6)

    def test_manifest_matches_packs(self):
        import hashlib
        for team in TEAMS:
            with self.subTest(team=team):
                row = self.manifest[team]
                self.assertEqual(row['pack_sha256'], hashlib.sha256(pack_path(team).read_bytes()).hexdigest())
                self.assertEqual(row['offense_pack_sha256'], hashlib.sha256(offense_path(team).read_bytes()).hexdigest())
                self.assertEqual(row['misses'], [])
                self.assertLess(row['nodes'], pk.NODE_CAPACITY)


@unittest.skipUnless(IMAGE.is_file(), f'private retail XISO absent: {IMAGE}')
class Compile(unittest.TestCase):
    """Each defense pin equals the current compile of its offense pack (a stale pin makes Build refuse it)."""

    @classmethod
    def setUpClass(cls):
        from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
        from mod_editor.core.nfl2k5_complete_offense import compile_offense
        cls.sources = {}
        with OuterImage(IMAGE) as image:
            for team in TEAMS:
                raw = image.read_entry(BOOK_ENTRIES[team])
                cls.sources[team] = compile_offense(raw, pk.load_pack(offense_path(team)), asset_id='book:' + team).replacement

    def test_pins_are_fresh(self):
        for team in TEAMS:
            with self.subTest(team=team):
                pack = pk.load_pack(pack_path(team))
                self.assertEqual(pack.base.book_fingerprint, pk.book_fingerprint(self.sources[team][32:]))

    def test_compile_lint_and_situation_bits(self):
        from mod_editor.core.nfl2k5_formation_play_writer import compile_formation_play_creations
        from mod_editor.core import nfl2k5_play_library as lib
        from mod_editor.core import nfl2k5_playbook_inspector as ip
        for team in ('KC', 'BAL', 'PHI', 'NE', 'BUF', 'TB'):
            with self.subTest(team=team):
                source = self.sources[team]
                pack = pk.load_pack(pack_path(team))
                book = ip.parse_playbook_resource(source)
                rows = pk.pack_requests(pack, 'pack-apply', book)
                out = compile_formation_play_creations(source, *rows)
                body = out.replacement[32:]
                self.assertEqual([f.message for f in dlint.lint_resource(out.replacement) if f.severity == 'error'], [])
                appended = [f for f in pack.formations if f.replace_index is None]
                for i, f in enumerate(pack.formations):
                    index = f.replace_index if f.replace_index is not None else len(book.formations) + appended.index(f)
                    flags = lib.formation_record(body, index).flags
                    self.assertEqual(tuple((flags >> s) & 7 for s in (21, 24, 27)), f.situation)
                self.assertEqual(ip.menu_link_problems(out.replacement), [])



@unittest.skipUnless(IMAGE.is_file(), f'private retail XISO absent: {IMAGE}')
class RetailLabels(unittest.TestCase):
    def test_retail_classifier_labels(self):
        sys.path.insert(0, str(ROOT / 'pb/v2/defense'))
        import library as L
        from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
        with OuterImage(IMAGE) as image:
            rows = L.scan_book('ATL', image.read_entry(BOOK_ENTRIES['ATL']))
        label = {(r.formation, r.name): r.struct.label for r in rows}
        self.assertEqual(label[('4-3', '2 Man')], '2-Man Under')
        self.assertEqual(label[('4-3', 'All Blitz 0')], 'Cover 0 Blitz')
        self.assertEqual(label[('4-3', 'Weak Crash 1')], 'Cover 1 Blitz')
        self.assertTrue(label[('4-3', '3 Weak')].startswith('Cover 3'))
        self.assertTrue(label[('4-3', '2 Hard')].startswith('Cover 2'))
        self.assertIn('Cover 4 Quarters', set(label.values()))       # retail "Cover 12" (four deep)


if __name__ == '__main__':
    unittest.main()

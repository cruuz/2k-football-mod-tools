"""vb3 (2026-09-23): historic teams wear their franchise's marks and colours on the sprite scorebug.

Noah's recording of 2026-09-23 [v2 7:12, the Ice Bowl]: in the 25th Anniversary moments the in-game scorebug was a
plain dark bar with no team marks or colours, while NFL games had both.

Root cause (PROVED OFFLINE). A historic team is category 4 at +0x128 and keeps its franchise's art code at +0x10C
("10" for Packers '66, "07" for Cowboys '71). The sprite engine (tools/scorebug_sprite/runtime.c) refused category 4 in
logo(), which then bound the neutral "sb--h0" panel, and accents() matched (code, category) against a table that has
no category 4 rows, which left the wing, rim and plate at the 0xFF303030 grey. The fix gives category 4 its
franchise's panel and the accents of the NFL row (category 0) with the same art code. Created teams (category 2) keep
the neutral panel. The same rule covers the historic teams h1 added to Quick Game (also category 4).

Offline evidence only: the owner's compiled code runs under Unicorn on the mapped retail executable (setup and the
per-frame update), and the ESPN 25th Anniversary moment harness (tests/nfl2k5_espn25_in_game.py) supplies the real
match contexts. Nothing here is a played game.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(ROOT / 'tests')]
from mod_editor.core import nfl2k5_scorebug_resources as art  # noqa: E402
from mod_editor.core import nfl2k5_scorebug_sprite as sprite  # noqa: E402
from mod_editor.core import nfl2k5_scorebug_teams as teams  # noqa: E402

PACK = ROOT / 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
HAVE_UC = importlib.util.find_spec('unicorn') is not None
HOME, AWAY = 0xB30864, 0xB30A58
GREY = 0xFF303030


def nfl_rows():
    """{art code: accent row} for the 32 NFL teams (category 0)."""
    return {t['asset_code']: t for t in teams.load().values() if t['kind'] == 0}


class SourceTests(unittest.TestCase):
    def test_engine_source_admits_category_four_and_maps_its_accents_to_the_nfl_row(self):
        source = (ROOT / 'tools/scorebug_sprite/runtime.c').read_text(encoding='utf-8')
        self.assertIn('if(p && kind!=2) {', source)
        self.assertNotIn('kind!=4', source)
        self.assertIn('if(kind==4)kind=0;', source)

    def test_every_historic_art_code_has_an_nfl_panel_and_accent_row(self):
        # The 75 historic files the retail roster names use the franchise codes 00..30 (h-%s-%d-%s-%d.iff).
        panels = {record['asset_code'] for record in art.TEAM_LOGOS.values()}
        rows = nfl_rows()
        for code in ['%02d' % n for n in range(31)]:
            self.assertIn(code, panels)
            self.assertIn(code, rows)


@unittest.skipUnless(PACK.is_file() and HAVE_UC, 'retail resources and Unicorn required')
class NativeEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_scorebug_runtime as owner
        cls.preview = sprite.NativePreview()
        payload = owner.apply(cls.preview.payload)[0]
        code, data = owner.sites(payload)
        cls.labels = owner.code_for(code['va'], data['va'])[1]

    def machine(self, wide=False):
        _, capture = self.preview.capture(dict(home='GB', away='DAL'), wide)
        spans = {int(k, 16): bytes(v) for k, v in capture['texture_spans'].items()}
        return capture, spans

    def bound(self, capture, spans):
        """{material name: texture name} for the two logo materials, and the tinted static colours."""
        from mod_editor.core import nfl2k5_scorebug_ingame as scene
        m = capture['machine']
        base = m.get(0xA95528)
        logos = {}
        for i in range(m.get(base + 0x1C)):
            at = m.get(base + 0x20) + i * 128
            name = m.read_string(m.get(at))
            if name in ('hscore_buga', 'zscore_buga'):
                chunk, decoded, _ = scene.decode(spans[m.get(at + 0x30)])
                logos[name] = scene.tx.parse_texture(decoded, chunk).name
        compiled = self.preview.modes[False]['compiled']
        colours = {q['name']: m.get(capture['body'] + 0x2D20 + q['vertex'] * 10)
                   for q in compiled.quads if q.get('tint', 'none') != 'none' and not q['dynamic']}
        return logos, colours

    def setup(self, m, home, away, kind):
        m.identity(home='GB', away='DAL', home_code=home, away_code=away, home_kind=kind, away_kind=kind)
        m.put(0xE60280, 0xE5FC20)
        m.run(self.labels['setup'], limit=100000)
        m.run(self.labels['update'], (0x3C888889,), limit=100000)

    def test_historic_teams_take_the_franchise_panel_and_accents(self):
        rows = nfl_rows()
        capture, spans = self.machine()
        try:
            m = capture['machine']
            for n in range(31):
                home, away = '%02d' % n, '%02d' % ((n + 7) % 31)
                with self.subTest(home=home, away=away):
                    self.setup(m, home, away, 4)
                    logos, colours = self.bound(capture, spans)
                    self.assertEqual(logos, {'hscore_buga': 'sb%sh0' % home, 'zscore_buga': 'sb%sh0' % away})
                    self.assertEqual(colours['home_wing'], 0xFF000000 | int(rows[home]['wing'][1:], 16))
                    self.assertEqual(colours['away_wing'], 0xFF000000 | int(rows[away]['wing'][1:], 16))
                    # Possession is home: the plate wears the home team's plate accent.
                    self.assertEqual(colours['plate'], 0xFF000000 | int(rows[home]['plate'][1:], 16))
                    self.assertNotIn(GREY, colours.values())
        finally:
            capture['machine'].close()

    def test_historic_team_matches_its_nfl_franchise_exactly(self):
        capture, spans = self.machine()
        try:
            m = capture['machine']
            self.setup(m, '10', '07', 0)
            nfl = self.bound(capture, spans)
            self.setup(m, '10', '07', 4)
            self.assertEqual(self.bound(capture, spans), nfl)
        finally:
            capture['machine'].close()

    def test_created_teams_keep_the_neutral_panel(self):
        capture, spans = self.machine()
        try:
            m = capture['machine']
            self.setup(m, '10', '07', 2)
            logos, colours = self.bound(capture, spans)
            self.assertEqual(logos, {'hscore_buga': 'sb--h0', 'zscore_buga': 'sb--h0'})
            self.assertEqual(colours['home_wing'], GREY)
            self.assertEqual(colours['away_wing'], GREY)
        finally:
            capture['machine'].close()


@unittest.skipUnless(HAVE_UC, 'Unicorn required')
class MomentContextTests(unittest.TestCase):
    """The real 25th Anniversary selection gives both match contexts category 4 and the franchise's art code."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_espn25_rosters as e
        from mod_editor.core import nfl2k5_throw_tuning as tt
        from tests.mod_editor.test_nfl2k5_espn25_rosters import RETAIL
        if not ((RETAIL / 'default.xbe').is_file() and (RETAIL / 'vc_53450030/0').is_file()):
            raise unittest.SkipTest('user-owned USA extraction absent')
        from nfl2k5_espn25_in_game import LiveCPU, evidence
        cls.resources, cls.context, cls.ids = evidence(RETAIL)
        payload = tt._apply_all(e.read_xbe(RETAIL), None, catch_slider=False, practice_squad=True)[0]
        cls.cpu = LiveCPU(payload, cls.resources, cls.context, cls.ids)

    def test_ice_bowl_and_wide_right_match_contexts(self):
        cpu = self.cpu
        panels = {record['asset_code'] for record in art.TEAM_LOGOS.values()}
        expected = {0: ("Packers '66", '10', "Cowboys '71", '07'), 14: ("Giants '90", '18', "Bills '90", '03')}
        for moment, (home, home_code, away, away_code) in expected.items():
            with self.subTest(moment=moment):
                cpu.select(moment)
                cpu.match()
                for context, name, code in ((HOME, home, home_code), (AWAY, away, away_code)):
                    self.assertEqual(cpu.text(cpu.r(context + 0x104)), name)
                    self.assertEqual(cpu.text(cpu.r(context + 0x10C)), code)
                    self.assertEqual(cpu.r(context + 0x128), 4)
                    self.assertIn(code, panels)


if __name__ == '__main__':
    unittest.main()

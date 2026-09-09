"""Standalone r64 regression: real visibility, cells, identity and witness calibration."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools'), str(Path(__file__).resolve().parent)]
from test_nfl2k5_scorebug_runtime import XBE, PACK, HAVE_UC
from mod_editor.core import nfl2k5_scorebug_ingame as scene
from mod_editor.core import nfl2k5_scorebug_runtime as runtime
import nfl2k5_scorebug_projection as projection
import nfl2k5_scorebug_witness as witness

HAVE_IMAGES = all(importlib.util.find_spec(n) for n in ('PIL', 'numpy'))


def box(draw):
    points = [v['screen'] for v in draw['vertices']]
    return [min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points)]


def overlap(a, b):
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


@unittest.skipUnless(XBE.is_file() and PACK.is_file() and HAVE_UC and HAVE_IMAGES,
                     'pinned USA XBE/pack, Unicorn, Pillow and numpy required')
class NativeFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from nfl2k5_scorebug_exact import Build
        cls.build = Build(PACK, XBE)
        cls.addClassCleanup(cls.build.close)
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.output = Path(cls.temp.name).resolve()
        cls.span = scene.apply(cls.build.spans['score_bug'], 'score_bug')[0]
        cls.decoded = scene.decode(cls.span)[1]
        cls.atlas = scene.apply(cls.build.spans['score_buga'], 'score_buga')[0]

    def capture(self, **kwargs):
        capture = {}
        geometry = projection.native_geometry(self.build.payload, self.decoded,
            fonts=self.build.fonts, texture_span=self.atlas, capture=capture, **kwargs)
        return geometry, capture

    def test_quarter_clocks_and_long_down_fit_separate_cells_both_modes_and_aspects(self):
        for wide in (False, True):
            for mode in (0, 1):
                geometry, capture = self.capture(widescreen=wide, mode=mode)
                m = capture['machine']
                try:
                    for quarter in (1, 2, 3, 4, 5, 13):
                        m.put(0xe602c4, quarter)
                        for seconds in (0, 300, 599, 600, 900):
                            m.float(m.game_clock+16, seconds)
                            for play_seconds in (0, 4, 22, 40):
                                m.float(m.clock+16, play_seconds)
                                rows = {d['callback']: d for d in projection.native_text_draw(capture)['draws']}
                                for callback, cell in (('0xfc090','quarter'), ('0xfc100','game_clock'),
                                                       ('0xfc150','game_clock'), ('0xfbe30','play_clock')):
                                    draw = rows[callback]
                                    if not draw['vertices']: continue
                                    left, right = scene.exact.STATIC_CELLS[cell]
                                    if wide: left, right = (320+(v-320)*27/32 for v in (left, right))
                                    bounds = box(draw)
                                    self.assertGreaterEqual(bounds[0], left+1, (quarter,seconds,play_seconds,cell))
                                    self.assertLessEqual(bounds[2], right-1, (quarter,seconds,play_seconds,cell))
                                    self.assertGreater(bounds[1], geometry['clock'][1])
                                    self.assertLess(bounds[3], geometry['clock'][3])
                                self.assertEqual(rows['0xfbe30']['color'], '0xffffffff')
                    m.put(m.play+4, 4); m.float(m.play+0x28, 1)
                    rows = {d['callback']: d for d in projection.native_text_draw(capture)['draws']}
                    self.assertEqual(rows['0xfc7d0']['text'], '4th & Inches')
                    down = box(rows['0xfc7d0'])
                    self.assertGreater(down[0], geometry['down'][0]+2)
                    self.assertLess(down[2], geometry['down'][2]-2)
                finally:
                    m.close()

    def test_all_teams_and_possession_remain_live_without_runtime_and_clear_three_digit_scores(self):
        for wide in (False, True):
            geometry, capture = self.capture(widescreen=wide, score_values=(999,999))
            m = capture['machine']
            try:
                self.assertFalse(geometry['scorebug_runtime_installed'])
                for team in scene.TEAM_LOGOS:
                    m.identity(home=team.lower(), away=team.lower())
                    for possession, yellow in ((0xe5fc20, '0xfc010'), (0xe5fc60, '0xfc030')):
                        m.put(0xe60280, possession)
                        rows = {d['callback']: d for d in projection.native_text_draw(capture)['draws']}
                        for callback, score in (('0xfc010','0xfc050'), ('0xfc030','0xfc070')):
                            self.assertEqual(rows[callback]['text'], team)
                            self.assertEqual(rows[callback]['color'], '0xffffff40' if callback == yellow else '0xffffffff')
                            self.assertFalse(overlap(box(rows[callback]), box(rows[score])), team)
                        self.assertEqual(projection.containment_failures({**geometry,'draws':list(rows.values())},geometry['frame'],.02), {})
            finally:
                m.close()

    def test_native_retail_visibility_requests_separate_down_and_ball_on_and_keep_event_text_clear(self):
        requests = {'pre_snap': [1,1,0,0,0,0], 'after_play': [1,1,0,0,1,0],
                    'live': [1,1,0,0,0,0], 'flag': [1,1,0,1,0,0],
                    'fumble': [1,1,0,0,0,1], 'kickoff': [1,1,1,0,0,0]}
        for wide in (False, True):
            for mode in (0, 1):
                for state, wanted in requests.items():
                    geometry, capture = self.capture(widescreen=wide, mode=mode, visibility_state=state,
                        visible_elements=(), identity=dict(home='NYG',away='WAS'), possession='away', ball_yards=35)
                    m = capture['machine']
                    try:
                        self.assertEqual(geometry['visibility_trace'][-1]['requests'], wanted, state)
                        off = scene.layout.sbpos.va_to_off(self.build.payload,0xfc9c0)
                        self.assertEqual(bytes(m.uc.mem_read(0xfc9c0,5)), self.build.payload[off:off+5])
                        drawn = projection.native_text_draw(capture)
                        rows = {d['callback']:d for d in drawn['draws']}
                        if state == 'after_play':
                            self.assertEqual(rows['0xfbeb0']['text'], 'Ball on WAS 35')
                            # V3 events replace down text, keeping clocks clear.
                            self.assertTrue(overlap(box(rows['0xfc7d0']),box(rows['0xfbeb0'])))
                            for clock in ('0xfc090', '0xfc100', '0xfc150', '0xfbe30'):
                                if rows[clock]['vertices']:
                                    self.assertFalse(overlap(box(rows[clock]),box(rows['0xfbeb0'])))
                            for score in ('0xfc050','0xfc070'):
                                self.assertFalse(overlap(box(rows[score]),box(rows['0xfbeb0'])))
                            # Its front material replaces down in the pill.
                            event_z = max(v['world'][2] for v in rows['0xfbeb0']['vertices'])
                            clock_z = min(v['world'][2] for v in rows['0xfc090']['vertices'])
                            self.assertLess(event_z,clock_z)
                            self.assertIn('bscore_buga1',geometry['objects'])
                        if state == 'pre_snap':
                            self.assertNotIn('0xfbeb0',rows)
                            self.assertNotIn('bscore_buga1',geometry['objects'])
                        self.assertEqual(projection.containment_failures({**geometry,**drawn},geometry['frame'],.02), {})
                    finally:
                        m.close()

    def test_native_event_transition_reverses_without_disabling_bound_nodes(self):
        geometry, capture = self.capture(visibility_state='pre_snap', visible_elements=())
        m = capture['machine']
        try:
            binding = m.get(0xa95be0)  # ball element +58
            self.assertEqual(binding,1)
            for state in ('after_play', 'pre_snap', 'after_play', 'live'):
                projection.configure_visibility(m,state)
                for _ in range(40):
                    m.run(0xfce70,(0x3c888889,),limit=500000)
                    rows={d['callback']:d for d in projection.native_text_draw(capture)['draws']}
                    if '0xfbeb0' in rows and '0xfc7d0' in rows:
                        for clock in ('0xfc090','0xfc150','0xfbe30'):
                            if rows[clock]['vertices']:
                                self.assertFalse(overlap(box(rows['0xfbeb0']),box(rows[clock])))
                    self.assertEqual(m.get(0xa95be0),binding)
                self.assertEqual('0xfbeb0' in rows,state=='after_play')
        finally:
            m.close()

    def test_scoped_capitalization_keeps_shared_strings_overtime_and_callee_saved_registers(self):
        payload = scene.apply_xbe(self.build.payload)[0]
        m = projection.StaticMachine(payload)
        try:
            dest = m.alloc(128)
            before = bytes(m.uc.mem_read(0xe6c3e4,32))
            for quarter, expected in ((1,'1ST'),(2,'2ND'),(3,'3RD'),(4,'4TH'),(5,'OT1'),(14,'OT10')):
                m.put(0xe602c4,quarter)
                m.uc.mem_write(dest,b'\xa5'*128)
                regs=dict(ebx=0x12345678,esi=0x23456789,edi=0x34567890,ebp=0x456789ab)
                m.run(0xfc090,ecx=dest,**regs)
                self.assertEqual(m.read_string(dest),expected)
                self.assertEqual(bytes(m.uc.mem_read(dest+2*(len(expected)+1),8)),b'\xa5'*8)
                for name,value in regs.items():
                    self.assertEqual(m.uc.reg_read(getattr(m.x,'UC_X86_REG_'+name.upper())),value)
            self.assertEqual(bytes(m.uc.mem_read(0xe6c3e4,32)),before)
        finally:
            m.close()

    def test_play_clock_color_isolated_and_static_composes_in_both_orders(self):
        code, labels = runtime.code_for(0x14ba2c0,0x14bb000)
        with mock.patch.object(runtime,'PLAY_CLOCK_NORMAL',runtime.DARK):
            dark, dark_labels = runtime.code_for(0x14ba2c0,0x14bb000)
        self.assertEqual(labels,dark_labels)
        at = dark.index(bytes.fromhex('c705485aa900181111ff'))+6
        self.assertEqual(code[:at],dark[:at]); self.assertEqual(code[at+4:],dark[at+4:])
        self.assertEqual(code[at:at+4],b'\xff'*4)
        # R65 scopes binding to GAMEDATA; the color variant still changes only
        # this word. Native before/after entry controls live in freeze_v2.
        self.assertEqual(scene.digest(dark),'e6aebda915ab509f9d4873393b28c12a88bf186cb5ed16d3c6950d5bd8113a28')
        first = runtime.apply(scene.apply_xbe(self.build.payload)[0])[0]
        second = scene.apply_xbe(runtime.apply(self.build.payload)[0])[0]
        self.assertEqual(first,second)
        self.assertEqual(runtime.apply(first)[0],first)
        self.assertEqual(scene.apply_xbe(first)[0],first)
        for va in (0xa95894,0xa958bc):
            off=scene.layout.sbpos.va_to_off(first,va)
            self.assertEqual(first[off:off+4],bytes(4))
            bad=bytearray(first);bad[off:off+4]=b'\xff'*4
            self.assertEqual(runtime.status(bytes(bad)),'foreign')
            with self.assertRaises(ValueError): runtime.apply(bytes(bad))

    def test_runtime_event_row_composes_with_private_fonts_in_all_placements(self):
        span=scene.stage_binding_scene(self.build.spans['score_bug'],runtime=True)[0]
        decoded=scene.decode(span)[1]
        for wide in (False,True):
            for mode in (0,1):
                capture={}
                geometry=projection.native_geometry(self.build.payload,decoded,fonts=self.build.fonts,
                    texture_span=self.atlas,runtime_textures=self.build.panels,runtime_fonts=self.build.font_spans,
                    identity=dict(home='HOU',away='LV',home_code='37',away_code='20'),
                    visible_elements=(),visibility_state='after_play',ball_yards=35,
                    widescreen=wide,mode=mode,capture=capture)
                try:
                    drawn=projection.native_text_draw(capture)
                    rows={d['callback']:d for d in drawn['draws']}
                    self.assertEqual(rows['0xfbeb0']['text'],'Ball on HOU 35')
                    event=box(rows['0xfbeb0'])
                    for callback in ('0xfc7d0','0xfc050','0xfc070'):
                        self.assertFalse(overlap(event,box(rows[callback])))
                    self.assertEqual(projection.containment_failures({**geometry,**drawn},geometry['frame'],.02),{})
                finally:
                    capture['machine'].close()

    def test_v1_is_a_pinned_negative_control_and_requires_rebuild(self):
        with witness.historical() as old:
            prior = scene.apply_xbe(self.build.payload)[0]
            geometry = witness.render(self.build,self.output/'before.png',compiler=old,state='after_play')
            rows={d['callback']:d for d in geometry['draws']}
            self.assertTrue(overlap(box(rows['0xfc7d0']),box(rows['0xfbeb0'])))
            self.assertEqual(rows['0xfc030']['color'],'0x0')
        self.assertEqual(scene.xbe_status(prior),'foreign')
        with self.assertRaises(ValueError): scene.apply_xbe(prior)

    def test_calibrated_projection_matches_independent_witness_ink_within_two_pixels(self):
        from PIL import Image
        for name, record in witness.WITNESSES.items():
            path=ROOT/'docs/scorebug_ingame/fix/witness'/record['file']
            if not path.is_file(): self.skipTest('Noah r64 gameplay PNGs absent')
            self.assertEqual(scene.digest(path.read_bytes()),record['sha256'])
            with witness.historical() as old:
                witness.render(self.build,self.output/'calibrated.png',compiler=old,state=name,
                               calibrated=witness.calibration(name))
            with Image.open(path) as actual, Image.open(self.output/'calibrated.png') as predicted:
                rows=witness.measure(actual,predicted,name)
            for label,row in rows.items():
                self.assertIsNotNone(row['maximum_edge_error_px'],(name,label))
                self.assertLessEqual(row['maximum_edge_error_px'],2,(name,label,row))


if __name__ == '__main__':
    unittest.main()

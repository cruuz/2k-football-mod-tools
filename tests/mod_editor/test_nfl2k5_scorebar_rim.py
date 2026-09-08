"""Rim ownership, retail primary/secondary selection, missing teams and old-v3 refusal."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools'), str(Path(__file__).resolve().parent)]
import test_nfl2k5_scorebar_v3 as v3_tests
HAVE_IMAGES = v3_tests.HAVE_IMAGES
from test_nfl2k5_scorebug_runtime import XBE, PACK, HAVE_UC
from mod_editor.core import nfl2k5_scorebar_v3 as rim, nfl2k5_scorebug_ingame as scene
import nfl2k5_scorebar_rim_witness as witness
import nfl2k5_scorebar_v3_witness as v3_witness
import nfl2k5_scorebug_projection as projection

# Independent, pinned retail observations. Deliberately include dark primaries
# that select secondary and bright primaries that differ from their panel fill.
EXPECTED = {
    'BAL': (0xff31145c, 0xff101010), 'JAX': (0xff0c586d, 0xff03031b),
    'MIN': (0xff422259, 0xffffffff), 'NYJ': (0xff253f36, 0xffffffff),
    'LV': (0xff101010, 0xffd1d2d3), 'HOU': (0xff061638, 0xffab253c),
    'ATL': (0xff101010, 0xffb51441), 'GB': (0xff006419, 0xffe0b02a),
}


class RimContractTests(unittest.TestCase):
    def test_selection_and_silver_fallback(self):
        self.assertEqual(rim.rim_color(0xff101010, 0xffd1d2d3), 0xffd1d2d3)
        self.assertEqual(rim.rim_color(0xff101010, 0xff101010), 0xffd1d2d3)
        self.assertEqual(rim.rim_color(0xff101010, None), 0xffd1d2d3)
        self.assertEqual(rim.rim_color(None, None, known=False), 0xffd1d2d3)
        self.assertEqual(rim.rim_color(None, 0xffffffff), 0xffffffff)
        self.assertEqual(rim.rim_color(0xff0065e6, 0xff00a0ff), 0xffd1d2d3)
        self.assertEqual(rim.rim_color(0xff9a494c, 0xff000000), 0xff9a494c)

    @unittest.skipUnless(all(shutil.which(n) for n in ('as', 'ld', 'objcopy')) and sys.platform == 'linux',
                         'GNU ELF32 binutils on Linux required for assembly reproduction')
    def test_assembly_exactly_fills_the_existing_span(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            source = ROOT/'docs/scorebug_ingame/rim/visibility_and_color.s'
            for cmd in (['as','--32',str(source),'-o',str(root/'a.o')],
                        ['ld','-m','elf_i386','-Ttext=0xfca87',str(root/'a.o'),'-o',str(root/'a.elf')],
                        ['objcopy','-O','binary','-j','.text',str(root/'a.elf'),str(root/'a.bin')]):
                subprocess.run(cmd, check=True, capture_output=True)
            self.assertEqual((root/'a.bin').read_bytes(), rim.VISIBILITY_CODE)
            self.assertEqual(len(rim.VISIBILITY_CODE), len(rim.RETAIL_VISIBILITY))
            self.assertEqual(len(rim.VISIBILITY_CODE), 581)


@unittest.skipUnless(XBE.is_file() and PACK.is_file() and HAVE_UC and HAVE_IMAGES,
                     'pinned USA XBE/pack, Unicorn, Pillow and numpy required')
class NativeRimTests(unittest.TestCase):
    setUpClass = classmethod(v3_tests.NativeV3Tests.setUpClass.__func__)
    capture = v3_tests.NativeV3Tests.capture

    def test_both_sides_keep_their_panel_and_choose_retail_rims_across_live_team_changes(self):
        _, cap = self.capture(visibility_state='pre_snap')
        m = cap['machine']; table = m.get(m.get(0xa95528)+0x20); dest = m.alloc(128)
        self.assertEqual([m.get(table+128*i+24) for i in (7,9)], [rim.SILVER]*2)
        for away, home in (('BAL','JAX'),('MIN','NYJ'),('LV','HOU'),('ATL','GB'),('HOU','LV')):
            m.identity(away=away, home=home)
            for side, team, callback in (('away',away,0xfc030), ('home',home,0xfc010)):
                before = [m.get(table+128*i+24) for i in range(11)]
                m.run(callback, ecx=dest)
                after = [m.get(table+128*i+24) for i in range(11)]
                primary, color = EXPECTED[team]
                self.assertEqual(after[rim.MATERIAL_INDICES[side]], rim.contrast_color(primary))
                self.assertEqual(after[rim.RIM_INDICES[side]], color)
                self.assertEqual(m.read_string(dest), team)
                for i in set(range(11)) - {rim.MATERIAL_INDICES[side],rim.RIM_INDICES[side]}:
                    self.assertEqual(before[i], after[i], (team,i))
                self.assertIn(0x68d70, m.visits)
                self.assertEqual(0x68dc0 in m.visits, primary == rim.contrast_color(primary))
                self.assertNotIn(0x449e0, m.visits)
            m.run(0xfce70, (0x3c888889,), limit=500000)
            for side, team in (('away',away), ('home',home)):
                self.assertEqual(m.get(table+128*rim.RIM_INDICES[side]+24), EXPECTED[team][1])
            self.assertEqual([m.get(table+128*i+24) for i in (2,4,8)], [0xffffffff]*3)

    def test_missing_codes_null_records_and_indistinguishable_secondary_fall_back_to_silver(self):
        _, cap = self.capture(visibility_state='pre_snap')
        m = cap['machine']; table = m.get(m.get(0xa95528)+0x20); dest = m.alloc(128)
        m.identity(home='JAX', away='BAL', home_code='missing', away_code='missing')
        for side, callback in (('home',0xfc010), ('away',0xfc030)):
            m.run(callback, ecx=dest)
            self.assertEqual(m.get(table+128*rim.RIM_INDICES[side]+24), rim.SILVER)
            # Null context: invoke the helper with its documented native ABI.
            m.run(rim.COLOR_VA, eax=0, esi=dest, edx=128*rim.MATERIAL_INDICES[side])
            self.assertEqual(m.get(table+128*rim.RIM_INDICES[side]+24), rim.SILVER)
            self.assertEqual(m.read_string(dest), '')
        m.identity(home='BAL')
        # Bounded synthetic palette input exercises the equality fallback.
        secondary = 0x4e8024; original = m.get(secondary)
        try:
            m.put(secondary, 0xff31145c); m.run(0xfc010, ecx=dest)
            self.assertEqual(m.get(table+128*9+24), rim.SILVER)
        finally:
            m.put(secondary, original)
        m.put(0xb30864+0x10c, 0); m.run(0xfc010, ecx=dest)
        self.assertEqual(m.get(table+128*9+24), rim.SILVER)

    def test_no_cached_material_table_and_guarded_missing_or_wrong_scene(self):
        _, cap = self.capture(visibility_state='pre_snap', identity=dict(away='ATL',home='GB'))
        m = cap['machine']; instance = m.get(0xa95528); table = m.get(instance+0x20); dest = m.alloc(128)
        m.run(0xfc010, ecx=dest)
        replacement = m.alloc(11*128)
        m.uc.mem_write(replacement, bytes(m.uc.mem_read(table,11*128)))
        m.put(instance+0x20, replacement); m.identity(home='HOU'); m.run(0xfc010,ecx=dest)
        self.assertEqual(m.get(replacement+9*128+24), 0xffab253c)
        self.assertEqual(m.get(table+9*128+24), 0xffe0b02a)
        for count, pointer, scene_pointer in ((10,replacement,instance),(11,0,instance),(11,replacement,0)):
            m.put(instance+0x1c,count);m.put(instance+0x20,pointer);m.put(0xa95528,scene_pointer)
            m.run(0xfc010,ecx=dest)
            self.assertEqual(m.read_string(dest),'HOU')
            self.assertTrue(all(m.STACK <= at and at+n <= m.STACK+0x10000 or
                                dest <= at and at+n <= dest+128 for at,n,_ in m.writes))

    def test_rim_material_reaches_native_shader_command(self):
        _, cap = self.capture(visibility_state='pre_snap',identity=dict(away='ATL',home='GB'))
        m = cap['machine']; table=m.get(m.get(0xa95528)+0x20);dest=m.alloc(128)
        for side,callback,wanted in (('away',0xfc030,0xffb51441),('home',0xfc010,0xffe0b02a)):
            m.run(callback,ecx=dest)
            row=v3_witness.material_submission(m,self.build.payload,table+128*rim.RIM_INDICES[side])
            self.assertEqual(int(row['argb'],16),wanted)
            self.assertEqual(row['command_bytes'],28)
            self.assertFalse(row['gpu_executed'])

    def test_compacted_visibility_writes_only_the_existing_state_and_restores_ebp(self):
        import unicorn
        _, cap = self.capture(visibility_state='pre_snap')
        m = cap['machine']
        allowed = {0xa95a00,0xa95a70,0xa95ae0,0xa95b50,0xa95bc0,0xa95c30,0xba2f10}
        observed = []
        def watch(u, _access, at, n, _value, _data):
            pc = u.reg_read(m.x.UC_X86_REG_EIP)
            if rim.VISIBILITY_VA <= pc < rim.COLOR_VA:
                observed.append((at,n))
        hook = m.uc.hook_add(unicorn.UC_HOOK_MEM_WRITE, watch)
        try:
            for state in ('pre_snap','after_play','live','kickoff','flag','fumble'):
                projection.configure_visibility(m,state)
                m.run(0xfce70,(0x3c888889,),ebp=0x12345678,limit=500000)
                self.assertEqual(m.uc.reg_read(m.x.UC_X86_REG_EBP),0x12345678)
            self.assertTrue(observed)
            for at,n in observed:
                self.assertTrue(at in allowed and n == 4 or
                                m.STACK <= at and at+n <= m.STACK+0x10000,(hex(at),n))
        finally:
            m.uc.hook_del(hook)

    def test_pinned_v3_is_a_real_negative_control_and_refuses_cross_version_install(self):
        with witness.previous_v3() as old:
            xbe = scene.apply_xbe(self.build.payload)[0]
            decoded = scene.serialize(old.mesh(self.build.retail_scene))
            prior_scene = scene.layout.refit(self.build.spans['score_bug'],decoded)[0]
            prior_atlas = scene.encode_atlas(self.build.spans['score_buga'],old.atlas())[0]
        self.assertEqual(scene.digest(xbe),'5ec31f2351d6e0257b978ca577585161cf44b2f76cd85fce183e75a8a13f46fd')
        self.assertEqual(scene.digest(prior_scene),'7b072c04b9d35f59a5645ce196cd209238ff5426d657e5bae43de6e26a5f7a35')
        self.assertEqual(scene.xbe_status(xbe),'foreign')
        with self.assertRaises(ValueError): scene.apply_xbe(xbe)
        for name,data in (('score_bug',prior_scene),('score_buga',prior_atlas)):
            self.assertEqual(scene.status(data,name),'foreign')
            with self.assertRaises(ValueError): scene.apply(data,name)


if __name__ == '__main__':
    unittest.main()

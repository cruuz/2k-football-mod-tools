"""Real native ratings, modern roster changes, guarded patching and Studio wiring."""
from pathlib import Path
import os,struct,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from mod_editor.core import nfl2k5_team_ratings as tr
from mod_editor.core import mod_build
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tools.b77.tr1_repair import repair
from tests.nfl2k5_supersim_draft_fixture import retail_bytes,retail_roster,HAVE_UC

class Wiring(unittest.TestCase):
    def test_presets_and_persisted_recipe_key(self):
        from mod_editor.core.nfl2k5_build_settings import FEATURE_KEYS
        self.assertIn('team_ratings',FEATURE_KEYS)
        self.assertFalse(mod_build.PRESETS['softdrink_basic']['team_ratings'])
        self.assertTrue(mod_build.PRESETS['softdrink_experimental']['team_ratings'])
        self.assertTrue(mod_build.BuildPlan('a','b',team_ratings=True).wants_xbe_patch())
    def test_repair_refuses_unknown_input_hash_without_outputs(self):
        from tools.b77.tr1_repair import main
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);source=p/'unknown.xbe';source.write_bytes(b'unknown input')
            with patch.object(sys,'argv',['repair','--xbe',str(source),'--output',str(p/'out.xbe'),'--receipt',str(p/'receipt.json')]):
                with self.assertRaisesRegex(ValueError,'Unknown XBE input hash'):main()
            self.assertFalse((p/'out.xbe').exists());self.assertFalse((p/'receipt.json').exists())

@unittest.skipUnless(HAVE_UC,'Unicorn is an optional test dependency')
class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_modern_positions as modern,nfl2k5_position_pools as pools
        from mod_editor.core import nfl2k5_xbe_space as space
        from tools.b77.tr1_probe import Ratings
        if os.environ.get('B77_TR1_XBE'):
            cls.before=Path(os.environ['B77_TR1_XBE']).read_bytes()
        else:
            cls.before=pools.apply(modern.apply(retail_bytes())[0])[0]
            cls.before=space.apply(cls.before,(),scaleout=True)[0]
        cls.body=Path(os.environ['B77_TR1_BODY']).read_bytes() if os.environ.get('B77_TR1_BODY') else retail_roster()
        cls.after,cls.receipt=repair(cls.before)
        cls.m=Ratings(cls.after,cls.body)
    def setUp(self):
        # Fresh relocated roster each time, preserving native program code.
        self.m.uc.mem_write(self.m.ARENA+0x300,self.body);self.m.fixup_roster(self.m.ARENA+0x340)
    def expected(self,i,table):
        team=self.m.team(i);weighted=total=0
        for pos,n,w in table:
            if pos==8 and not self.m.player(team,8):continue
            weighted+=self.m.pool(team,pos,n)*w;total+=w
        return weighted/total
    def test_all_32_real_getters_match_native_pools_and_equal_overall(self):
        for i in range(32):
            with self.subTest(team=i):
                team=self.m.team(i)
                off=self.m.rating(0xC4830,team);de=self.m.rating(0xC4860,team)
                self.assertAlmostEqual(off,self.expected(i,tr.OFFENSE),places=4)
                self.assertAlmostEqual(de,self.expected(i,tr.DEFENSE),places=4)
                self.assertAlmostEqual(self.m.rating(0xC48A0,team),(off+de)/2,places=4)
                self.assertEqual(self.m.reg('EBX'),0x11111111)
                self.assertEqual(self.m.reg('ESI'),0x22222222)
                self.assertEqual(self.m.reg('EDI'),0x33333333)
                self.assertEqual(self.m.reg('ESP'),self.m.STACK+4)
        self.assertEqual(self.m.leaves,[])
    def test_same_roster_is_independent_of_34_or_43_flag(self):
        for i in range(32):
            t=self.m.team(i);self.m.put(t+0x150,0)
            a=[self.m.rating(fn,t) for fn in (0xC4830,0xC4860,0xC48A0)]
            self.m.put(t+0x150,1)
            self.assertEqual(a,[self.m.rating(fn,t) for fn in (0xC4830,0xC4860,0xC48A0)])
    def test_optional_fb_is_removed_from_denominator(self):
        for i in range(32):
            team=self.m.team(i)
            n=0
            while p:=self.m.player(team,8,n):
                # Reclassify FB as TE, as an H-back authoring option can do.
                self.m.uc.mem_write(p+0x35,b'\x09');n=0
            self.assertAlmostEqual(self.m.rating(0xC4830,team),self.expected(i,tr.OFFENSE),places=4)
    def test_native_roster_release_updates_without_refresh(self):
        team=self.m.team(0);player=self.m.player(team,8)
        self.assertTrue(player)
        count=self.m.uc.mem_read(team+0x11C,1)[0]
        index=next(i for i in range(count) if self.m.get(team+4*i)==player)
        before=self.m.rating(0xC4830,team)
        self.assertEqual(self.m.call(0xC3A90,eax=team,ecx=index),1)
        self.assertEqual(self.m.call(0xC3CB0,ecx=team,edx=8),0)
        after=self.m.rating(0xC4830,team)
        self.assertNotEqual(before,after)
        self.assertAlmostEqual(after,self.expected(0,tr.OFFENSE),places=4)

    def test_roster_rating_change_is_immediate_without_refresh(self):
        team=self.m.team(0);qb=self.m.player(team,0)
        before=self.m.rating(0xC4830,team)
        # Copy another native QB's attributes, preserving identity and depth order.
        donor=self.m.player(self.m.team(1),0)
        self.m.uc.mem_write(qb+0x38,bytes(self.m.uc.mem_read(donor+0x38,0x18)))
        after=self.m.rating(0xC4830,team)
        self.assertNotEqual(before,after)
        self.assertAlmostEqual(after,self.expected(0,tr.OFFENSE),places=4)
    def test_wr3_and_cb3_are_starters_and_bench_still_counts(self):
        for pos in (3,4):
            team=self.m.team(0);players=[];n=0
            while p:=self.m.player(team,pos,n):players.append(p);n+=1
            self.assertGreaterEqual(len(players),3)
            ranks=[struct.unpack('<H',self.m.uc.mem_read(p+0x28,2))[0] for p in players]
            # Author an unambiguous native depth chart: WR1/CB1 rank0, WR2/CB2 side0,
            # WR3/CB3 rank1/side1, subsequent players rank/side >=2.
            for j,p in enumerate(players):
                rank,side=(0,7) if j==0 else (7,0) if j==1 else (j-1,j-1)
                self.m.uc.mem_write(p+0x28,struct.pack('<H',(ranks[j]&1023)|(min(rank,7)<<10)|(min(side,7)<<13)))
            a=self.m.pool(team,pos,2);b=self.m.pool(team,pos,1)
            self.assertNotEqual(a,b)
            fn=0xC4830 if pos==3 else 0xC4860
            before=self.m.rating(fn,team)
            # Move WR3/CB3 behind WR4/CB4 in both orderings.
            p=players[2];self.m.uc.mem_write(p+0x28,struct.pack('<H',(ranks[2]&1023)|(7<<10)|(7<<13)))
            self.assertNotEqual(before,self.m.rating(fn,team))
    def test_guards_replay_scope_and_existing_allocations(self):
        self.assertEqual(tr.apply(self.after)[0],self.after)
        self.assertEqual(self.receipt['changed_bytes_outside_allowed_spans'],0)
        self.assertTrue(self.receipt['existing_allocations_unchanged'])
        for va in (0xC4830,0xC4400,tr.allocation(self.after)['va']):
            bad=bytearray(self.after)
            from mod_editor.core.nfl2k5_rdata_sites import offset_of
            bad[offset_of(bad,va)]^=1
            with self.assertRaises(ValueError):tr.apply(bytes(bad))
    def test_actual_team_select_grade_formatter(self):
        from mod_editor.core import nfl2k5_letter_grades as grades
        if grades.status(self.after) != 'applied':
            self.skipTest('Requires installed letter grades for native formatter proof')
        seen=0
        for i in range(32):
            for fn in (0xC4830,0xC4860,0xC48A0):
                rating=self.m.rating(fn,self.m.team(i))/100
                scratch=self.m.ARENA+0x180000
                self.m.uc.mem_write(scratch,bytes(256));esi=scratch+64
                self.m.f32(esi-32,rating);self.m.f32(esi-28,0.5)
                self.m.call(0x31F6C2,esi=esi,stop=0x31F73A,budget=300000)
                text=bytes(self.m.uc.mem_read(self.m.reg('EDX'),16)).decode('utf-16-le').split('\0')[0]
                self.assertEqual(text,grades.grade_for(int(min(100,rating*100))))
                seen+=1
        self.assertEqual(seen,96)

    def test_studio_final_pass_equals_repair(self):
        # Exercise the actual final Studio helper; only filesystem transport is substituted.
        receipt={'steps':[]};captured=[]
        with patch.object(mod_build,'_core_module',return_value=tr),patch.object(mod_build,'_xbe_bytes',return_value=self.before),patch.object(mod_build,'_write_xbe_bytes',side_effect=lambda _,b:captured.append(b)):
            mod_build._apply_team_ratings(mod_build.BuildPlan('a','b',team_ratings=True,position_pools=True),'target',receipt,lambda *_:None)
        self.assertEqual(captured,[self.after]);self.assertEqual(receipt['steps'][0]['step'],'team_ratings')
if __name__=='__main__':unittest.main()

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
        cls.baseline=Ratings(cls.before,cls.body)
        cls.functions=tr.entrypoints(cls.after)
        cls.raw_functions=tr.entrypoints(cls.after,raw=True)
    def setUp(self):
        # Fresh relocated roster each time, preserving native program code.
        self.m.uc.mem_write(self.m.ARENA+0x300,self.body);self.m.fixup_roster(self.m.ARENA+0x340)
        self.baseline.uc.mem_write(self.baseline.ARENA+0x300,self.body);self.baseline.fixup_roster(self.baseline.ARENA+0x340)
    def expected(self,i,table):
        team=self.m.team(i);weighted=total=0
        for pos,n,w in table:
            if pos==8 and not self.m.player(team,8):continue
            weighted+=self.m.pool(team,pos,n)*w;total+=w
        return weighted/total
    def test_all_32_display_getters_match_raw_pools_and_mapped_overall(self):
        for i in range(32):
            with self.subTest(team=i):
                team=self.m.team(i)
                off=self.m.rating(self.functions[0],team);de=self.m.rating(self.functions[1],team)
                self.assertAlmostEqual(self.m.rating(self.raw_functions[0],team),self.expected(i,tr.OFFENSE),places=4)
                self.assertAlmostEqual(off,tr.map_score(self.expected(i,tr.OFFENSE)/100,0)*100,places=4)
                self.assertAlmostEqual(self.m.rating(self.raw_functions[1],team),self.expected(i,tr.DEFENSE),places=4)
                self.assertAlmostEqual(de,tr.map_score(self.expected(i,tr.DEFENSE)/100,1)*100,places=4)
                mean=(self.expected(i,tr.OFFENSE)+self.expected(i,tr.DEFENSE))/200
                self.assertAlmostEqual(self.m.rating(self.functions[2],team),tr.map_score(mean,2)*100,places=4)
                self.assertEqual(self.m.reg('EBX'),0x11111111)
                self.assertEqual(self.m.reg('ESI'),0x22222222)
                self.assertEqual(self.m.reg('EDI'),0x33333333)
                self.assertEqual(self.m.reg('ESP'),self.m.STACK+4)
        self.assertEqual(self.m.leaves,[])
    def test_same_roster_is_independent_of_34_or_43_flag(self):
        for i in range(32):
            t=self.m.team(i);self.m.put(t+0x150,0)
            a=[self.m.rating(fn,t) for fn in self.functions]
            self.m.put(t+0x150,1)
            self.assertEqual(a,[self.m.rating(fn,t) for fn in self.functions])
    def test_optional_fb_is_removed_from_denominator(self):
        for i in range(32):
            team=self.m.team(i)
            n=0
            while p:=self.m.player(team,8,n):
                # Reclassify FB as TE, as an H-back authoring option can do.
                self.m.uc.mem_write(p+0x35,b'\x09');n=0
            self.assertAlmostEqual(self.m.rating(self.functions[0],team),tr.map_score(self.expected(i,tr.OFFENSE)/100,0)*100,places=4)
    def test_native_roster_release_updates_without_refresh(self):
        team=self.m.team(0);player=self.m.player(team,8)
        self.assertTrue(player)
        count=self.m.uc.mem_read(team+0x11C,1)[0]
        index=next(i for i in range(count) if self.m.get(team+4*i)==player)
        before=self.m.rating(self.functions[0],team)
        fb_count=self.m.call(0xC3CB0,ecx=team,edx=8)
        self.assertEqual(self.m.call(0xC3A90,eax=team,ecx=index),1)
        self.assertEqual(self.m.call(0xC3CB0,ecx=team,edx=8),fb_count-1)
        after=self.m.rating(self.functions[0],team)
        self.assertNotEqual(before,after)
        self.assertAlmostEqual(after,tr.map_score(self.expected(0,tr.OFFENSE)/100,0)*100,places=4)

    def test_roster_rating_change_is_immediate_without_refresh(self):
        team=self.m.team(0);qb=self.m.player(team,0)
        before=self.m.rating(self.functions[0],team)
        # Copy another native QB's attributes, preserving identity and depth order.
        donor=self.m.player(self.m.team(1),0)
        self.m.uc.mem_write(qb+0x38,bytes(self.m.uc.mem_read(donor+0x38,0x18)))
        after=self.m.rating(self.functions[0],team)
        self.assertNotEqual(before,after)
        self.assertAlmostEqual(after,tr.map_score(self.expected(0,tr.OFFENSE)/100,0)*100,places=4)
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
            fn=self.functions[0] if pos==3 else self.functions[1]
            before=self.m.rating(fn,team)
            # Move WR3/CB3 behind WR4/CB4 in both orderings.
            p=players[2];self.m.uc.mem_write(p+0x28,struct.pack('<H',(ranks[2]&1023)|(7<<10)|(7<<13)))
            self.assertNotEqual(before,self.m.rating(fn,team))
    def test_guards_replay_scope_and_existing_allocations(self):
        self.assertEqual(tr.apply(self.after)[0],self.after)
        self.assertEqual(self.receipt['changed_bytes_outside_allowed_spans'],0)
        self.assertTrue(self.receipt['existing_feature_allocations_unchanged'])
        for va in (0xC4830,0xC4400,tr.allocation(self.after)['va']):
            bad=bytearray(self.after)
            from mod_editor.core.nfl2k5_rdata_sites import offset_of
            bad[offset_of(bad,va)]^=1
            with self.assertRaises(ValueError):tr.apply(bytes(bad))
    def test_all_18_actual_caller_edges_route_only_ui_to_display(self):
        # Execute each real CALL/JMP instruction and its real callee, stopping
        # before the caller's remaining body. No callee is substituted.
        seen={"UI":0,"native":0}
        for i in range(32):
            for site,target,kind in tr.CALLERS:
                m=self.m;before=self.baseline
                values=[]
                for machine in (before,m):
                    jump=bytes(machine.uc.mem_read(site,1))==b'\xe9'
                    machine.uc.ctl_flush_tb()
                    try:
                        machine.call(site,ecx=machine.team(i),stop=None if jump else site+5,budget=3000000)
                    except Exception as exc:
                        raise AssertionError(f'team={i} site={site:#x} pc={machine.reg("EIP"):#x} ecx={machine.reg("ECX"):#x} team={machine.team(i):#x}') from exc
                    pop=machine.STOP+0x400;out=machine.output
                    machine.uc.mem_write(pop,b'\xd9\x1d'+struct.pack('<I',out)+b'\xc3')
                    machine.call(pop);values.append(machine.f32(out)*100)
                if kind.startswith('UI:'):
                    unit=(0xC4830,0xC4860,0xC48A0).index(target)
                    self.assertAlmostEqual(values[1],m.rating(self.functions[unit],m.team(i)),places=5)
                    seen['UI']+=1
                else:
                    self.assertEqual(values[0],values[1],(i,hex(site)))
                    seen['native']+=1
        self.assertEqual(seen,{'UI':128,'native':448})

    def test_full_image_caller_census_has_no_unclassified_references(self):
        from tools.b77.tr1_probe import caller_census
        actual=caller_census(self.before)
        self.assertEqual(actual['absolute_references'],[])
        self.assertEqual({(r['site'],r['target']) for r in actual['calls']},
                         {(site,target) for site,target,_ in tr.CALLERS})
        installed=caller_census(self.after)
        self.assertEqual(installed['absolute_references'],[])
        self.assertEqual({(r['site'],r['target']) for r in installed['calls']},
                         {(site,target) for site,target,kind in tr.CALLERS if not kind.startswith('UI:')})

    def test_display_spread_preserves_all_32_continuous_rank_orders(self):
        for unit in range(3):
            raw=[self.m.rating(self.raw_functions[unit],self.m.team(i)) for i in range(32)]
            shown=[self.m.rating(self.functions[unit],self.m.team(i)) for i in range(32)]
            for a in range(32):
                for b in range(a):
                    self.assertEqual((raw[a]>raw[b])-(raw[a]<raw[b]),
                                     (shown[a]>shown[b])-(shown[a]<shown[b]))

    def test_native_getters_and_non_ui_instructions_are_byte_identical(self):
        before,after=XbeImage(self.before),XbeImage(self.after)
        for va,n,_digest in tr.GUARDS:
            self.assertEqual(before.read(va,n),after.read(va,n))
        for site,_target,kind in tr.CALLERS:
            if not kind.startswith('UI:'):
                self.assertEqual(before.read(site,5),after.read(site,5))
        for i in range(32):
            for fn in (0xC4830,0xC4860,0xC48A0):
                self.assertEqual(self.m.rating(fn,self.m.team(i)),self.baseline.rating(fn,self.baseline.team(i)))

    def test_display_getters_leave_no_persistent_shared_state_changes(self):
        writes=set();m=self.m
        initial=bytes(m.uc.mem_read(m.ARENA,0x200000))
        hook=m.uc.hook_add(m.u.UC_HOOK_MEM_WRITE,
                           lambda _uc,_access,address,size,_value,_data:
                           writes.update(range(address,address+size)))
        try:
            for i in range(32):
                for fn in self.functions:m.rating(fn,m.team(i))
        finally:m.uc.hook_del(hook)
        outside={a for a in writes if not 0x3000000<=a<0x3010000}
        # The native OL-overall helper temporarily substitutes player +2A and
        # restores it before returning. Permit only those transient bytes.
        temporary={m.ARENA+0x300+p.offset+0x2A for p in m.doc.players}
        self.assertFalse(outside-(temporary|set(range(m.output,m.output+4))))
        final=bytearray(m.uc.mem_read(m.ARENA,0x200000))
        offset=m.output-m.ARENA;final[offset:offset+12]=initial[offset:offset+12]
        self.assertEqual(bytes(final),initial)

    def test_native_spread_mapper_matches_reference_and_is_monotonic(self):
        m=self.m;rows=tr.allocations(self.after)
        at=m.STOP+0x300;arg=m.output+100
        m.uc.mem_write(at,b'\xd9\x05'+struct.pack('<I',arg)+b'\x8b\x15'+struct.pack('<I',arg+4)
                       +b'\xff\x15'+struct.pack('<I',arg+8)+b'\xd9\x1d'+struct.pack('<I',m.output)+b'\xc3')
        m.put(arg+8,rows['code']['va']+tr.MAP_OFFSET)
        for unit in range(3):
            m.put(arg+4,rows['read_only']['va']+tr.SPREAD_OFFSET+unit*tr.CURVE_SIZE)
            values=sorted(set([-1.,1.1]+[i/1000 for i in range(1001)]
                              +[x+d for x,_ in tr.KNOTS[unit] for d in (-1e-6,0,1e-6)]))
            previous=-1.
            for value in values:
                m.f32(arg,value);m.call(at)
                actual=m.f32(m.output)
                self.assertAlmostEqual(actual,tr.map_score(m.f32(arg),unit),places=6)
                self.assertGreaterEqual(actual,previous)
                previous=actual

    def test_actual_panel_calculation_block_writes_all_three_display_scores(self):
        m=self.m
        for i in range(32):
            # Execute the game's entire three-rating calculation block with
            # its real CALLs and UI stores, stopping before rendering starts.
            m.put(m.STACK+0x13C,0)
            m.call(0x31F21C,edi=m.team(i),stop=0x31F25D,budget=3000000)
            stored=[m.f32(at)*100 for at in (0xAE2B74,0xAE2BA0,0xAE2BCC)]
            expected=[m.rating(fn,m.team(i)) for fn in self.functions]
            self.assertEqual(stored,expected)

    def test_actual_overall_defense_column_returns_new_display_integer(self):
        for i in range(32):
            shown=self.m.rating(self.functions[1],self.m.team(i))
            self.assertEqual(self.m.call(0x34BB60,ecx=self.m.team(i),budget=3000000),int(shown))

    def test_actual_team_select_grade_formatter(self):
        from mod_editor.core import nfl2k5_letter_grades as grades
        if grades.status(self.after) != 'applied':
            self.skipTest('Requires installed letter grades for native formatter proof')
        seen=0
        for i in range(32):
            for fn in self.functions:
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
@unittest.skipUnless(os.environ.get('B77_RO1_XBE'), 'played-disc XBE required')
class IntegratedAllocation(unittest.TestCase):
    def test_legacy_exact_binary_remains_readable_and_replays(self):
        import hashlib
        base=Path(os.environ['B77_RO1_XBE']).read_bytes()
        legacy_requests=((tr.LEGACY_OWNER,'code',512,16),(tr.LEGACY_OWNER,'read_only',512,16))
        with patch.object(tr,'REQUESTS',legacy_requests):
            legacy=tr.apply(base)[0]
        self.assertEqual(hashlib.sha256(legacy).hexdigest(),
                         'd870ece82cee187c8f0d271a466e49dd61411f666a9caea855d3e51802156042')
        self.assertEqual(tr.apply(legacy)[0],legacy)

    def test_four_features_compose_and_preserve_existing_owners(self):
        import json
        from mod_editor.core import nfl2k5_draft_picks as dp,nfl2k5_hback as hb
        from mod_editor.core import nfl2k5_abilities_runtime as abilities,nfl2k5_xbe_space as space
        base=Path(os.environ['B77_RO1_XBE']).read_bytes()
        picks=json.loads(Path(os.environ['B77_RO1_PICKS']).read_text())
        roles=json.loads(Path(os.environ['B77_RO1_HBACK']).read_text())
        left=tr.apply(hb.apply(dp.apply(abilities.apply(base)[0],picks)[0],roles)[0])[0]
        right=abilities.apply(dp.apply(hb.apply(tr.apply(base)[0],roles)[0],picks)[0])[0]
        self.assertEqual(left,right)
        self.assertEqual(len(left),len(base))
        for row in space.layout(base)['allocations']:
            if row['owner'] != space.DIRECTORY_OWNER:
                self.assertIn(row,space.layout(left)['allocations'])
                at,n=row['raw'],row['size']
                # Tap burst deliberately changes its existing abilities code.
                if row['owner'] not in ('nfl2k5_abilities_runtime','nfl2k5_abilities'):
                    self.assertEqual(base[at:at+n],left[at:at+n],row['owner'])
        self.assertEqual(tr.apply(left)[0],left)
        for kind,row in tr.allocations(left).items():
            section=next(s for s in XbeImage(left).sections if s.start<=row['va']<s.start+s.size)
            self.assertFalse(section.flags & 1)  # write permission
            self.assertTrue(section.flags & 4)   # executable directory section
            bad=bytearray(left);bad[row['raw']] ^= 1
            self.assertEqual(tr.status(bytes(bad)),'foreign')

    def test_physical_writer_uses_windows_fallback_and_checks_short_writes(self):
        from tools.b77 import tr1_repair as repair
        from mod_editor.core import platform_compat as io
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'binary';p.write_bytes(bytes(32))
            with patch.object(io.os,'pread',None,create=True),patch.object(io.os,'pwrite',None,create=True):
                self.assertEqual(repair.write_spans(p,[(3,b'\x00\x0a\x1a\xff')]),4)
            self.assertEqual(p.read_bytes(),bytes(3)+b'\x00\x0a\x1a\xff'+bytes(25))
            with patch.object(io,'pwrite',return_value=1):
                with self.assertRaisesRegex(OSError,'Short'):
                    repair.write_spans(p,[(0,b'ab')])


if __name__=='__main__':unittest.main()

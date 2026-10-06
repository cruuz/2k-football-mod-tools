"""PROVED OFFLINE: integration, failed-source guard and native weighting regression."""
from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
import struct
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_playbook_pack as pk
from mod_editor.core import nfl2k5_playbook_inspector as ip
from mod_editor.core import nfl2k5_play_library as lib
from pb.defense.build import semantic
from pb.defense.selector import Selector,XBE,probabilities,native_weight_choice
from tests.mod_editor.test_nfl2k5_complete_offense import PipelineTests

class Books(unittest.TestCase):
    def test_team_ownership_no_options_and_distinct_content(self):
        rows=json.loads((ROOT/'pb/defense_manifest.json').read_text())['teams']
        self.assertEqual({r['team'] for r in rows},set(pk.TEAM_BOOKS));hashes=set();allocations=set()
        for row in rows:
            p=pk.load_pack(ROOT/row['pack'])
            with self.subTest(team=row['team']):
                self.assertEqual(p.book.resolved_targets(),(row['team'],))
                self.assertTrue(pk.check_pack(p).ok)
                self.assertFalse(p.menus)
                for play in p.plays:self.assertFalse(play.option_intent)
                self.assertEqual(sum(len(play.spy_slots) for play in p.plays), int(row["team"]=="KC"))
                hashes.add(semantic(p))
                allocations.add(tuple(sorted(Counter(play.concept for play in p.plays if play.component=='coverage').items())))
        self.assertEqual(len(hashes),32)
        self.assertEqual(len(allocations),32)
    def test_only_custom_cpu_score_bits_can_differ_from_donor(self):
        pack=pk.load_pack(ROOT/'data/playbooks/softdrink_dal_defense.2k5book')
        play=next(p for p in pack.plays if p.component=='coverage')
        for band in range(8):
            with self.subTest(band=band):
                tuned=replace(play,play_flags=(play.donor.flags&~0xe00)|(band<<9))
                pk.validate_defense_pack_play(tuned,None,None)
        for bit in (0,6,8,12,16,26,31):
            with self.subTest(bit=bit):
                with self.assertRaises(pk.PlaybookPackError):
                    pk.validate_defense_pack_play(replace(play,play_flags=play.play_flags^(1<<bit)),None,None)
        preset=pk.load_pack(ROOT/'data/playbooks/softdrink_modern_defense.2k5book').plays[0]
        with self.assertRaises(pk.PlaybookPackError):
            pk.validate_defense_pack_play(replace(preset,play_flags=preset.donor.flags^0x200),None,None)
    def test_build_orders_all_offense_before_defense_then_menu_gate(self):
        recipe=json.loads((ROOT/'pb/recipes/final_playbooks.json').read_text())['overrides']
        for flag in ('playbook_pair','read_option_runtime'):self.assertFalse(recipe[flag])
        self.assertNotIn('qb_spy',recipe)
        paths=[Path(p.replace('<stack>',str(ROOT))) for p in recipe['playbook_packs']]
        events=[];PipelineTests().run_build(list(reversed(paths)),events)
        self.assertEqual(events,['forward_pass_ruling',[pk.OFFENSE_SCHEMA]*32,[pk.DEFENSE_SCHEMA]*32,'menus','scoring'])
    def test_research_counts_sum_and_unavailable_not_zero(self):
        data=json.loads((ROOT/'pb/research/defense_tendencies_2025.json').read_text())['teams']
        for team,row in data.items():
            with self.subTest(team=team):
                c=row['counts'];self.assertEqual(c['man']+c['zone'],c['man_zone_known'])
                self.assertEqual(sum(row['coverage_counts'].values()),c['coverage_known'])
                self.assertIsNone(row['presnap_two_high']);self.assertIsNone(row['creeper'])
                self.assertAlmostEqual(row['rates']['blitz'],100*c['blitz']/c['rush_known'],places=3)
    def test_final_rate_receipts_fit_sourced_baselines_within_three_points(self):
        summary=ROOT/'pb/receipts/defense/selector-summary.json'
        if not summary.is_file():self.skipTest('Run composition and sweep first')
        sims=json.loads(summary.read_text())['teams']
        profiles=json.loads((ROOT/'pb/research/defense_profiles.json').read_text())
        real=json.loads((ROOT/'pb/research/defense_tendencies_2025.json').read_text())['teams']
        manifest=json.loads((ROOT/'pb/defense_manifest.json').read_text())['teams']
        composition=json.loads((ROOT/'pb/receipts/defense/composition.json').read_text())['teams']
        for row in manifest:
            t=row['team']
            with self.subTest(team=t):
                self.assertEqual(composition[t]['resource_sha256'],row['compile']['replacement_sha256'])
                self.assertEqual(composition[t]['defense_semantic_sha256'],semantic(pk.load_pack(ROOT/row['pack'])))
                self.assertEqual(sims[t]['state_count'],252)
                if profiles[t]['baseline_team']:
                    actual=real[profiles[t]['baseline_team']]['rates']
                    for field in ('man','split_family','blitz'):
                        self.assertLess(abs(sims[t]['rates'][field]-actual[field]),3.0)
    def test_main_lab_has_no_operator_protocol_and_python_compiles(self):
        import ast
        for name in ('pb_def_probe.py','pb_def_stats.py'):
            ast.parse((ROOT/'pb/lab'/name).read_text())
        source=(ROOT/'pb/lab/pb_def_probe.py').read_text()
        self.assertNotIn('cmds.txt',source);self.assertIn('neutral',source)

    @unittest.skipIf(sys.platform == 'win32', 'POSIX lab shell syntax requires native bash; Windows bash may be a WSL stub')
    def test_main_lab_shell_compiles(self):
        import shutil,subprocess
        bash = shutil.which('bash')
        if bash is None:
            self.skipTest('POSIX lab shell syntax requires bash')
        subprocess.run([bash,'-n',str(ROOT/'pb/lab/pb_lab_def.sh')],check=True)

@unittest.skipUnless(XBE.is_file(),'Pinned retail executable unavailable')
class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p=ROOT/'.scratch/pb3/compiled/NYG.bin'
        if not p.is_file():raise unittest.SkipTest('Run pb/defense/verify.py first')
        cls.raw=p.read_bytes();cls.machine=Selector(XBE.read_bytes(),cls.raw)
    def test_native_validator_rejects_invalid_defensive_permission(self):
        s=self.machine;play=next(p for p in s.book.plays if p.family_id==1)
        va=0x2000000+ip.PLAY_BASE+96*play.index
        original=bytes(s.uc.mem_read(va+8,4));desc=struct.unpack('<I',original)[0]
        try:
            s.put(va+8,desc&~0x20)
            self.assertNotEqual(s.call(0x1a9840,ecx=va),0)
        finally:s.uc.mem_write(va+8,original)
        self.assertEqual(s.call(0x1a9840,ecx=va),0)
        original_flags=bytes(s.uc.mem_read(va+4,4));flags=struct.unpack('<I',original_flags)[0]
        try:
            for band in range(8):
                s.put(va+4,(flags&~0xe00)|(band<<9))
                self.assertEqual(s.call(0x1a9840,ecx=va),0)
        finally:s.uc.mem_write(va+4,original_flags)
    def test_native_category_field_and_prevent_branches(self):
        s=self.machine
        self.assertEqual(s.requested_category(0,1,1),11)
        self.assertEqual(s.requested_category(0,50,1),13)
        self.assertEqual(s.requested_category(6,50,1,prevent=True),16)
        self.assertEqual(s.requested_category(6,50,1,prevent=False),14)
    def test_inherited_header_curve_and_pressure_multiplier(self):
        s=self.machine;cov=0x3100600;front=0x3100680;stub=0x3100200;out=0x3100800
        s.uc.mem_write(stub,b'\xd9\x1d'+struct.pack('<I',out))
        for code,curve in enumerate((2,1.4,1,.5,.1,.1,.1,.1)):
            for special,mult in ((0,1),(0x10000,1.525)):
                with self.subTest(code=code,special=special):
                    s.put(cov+4,0x45+(code<<9)+special);s.put(front+4,0x45)
                    s.call(0x203f20,esi=front,edi=cov,args=(0xe5fc20,0x3f000000))
                    s.uc.emu_start(stub,stub+6,count=1)
                    actual=struct.unpack('<f',s.uc.mem_read(out,4))[0]
                    self.assertAlmostEqual(actual,2*curve*mult,places=5)
    def test_cubed_lottery_matches_native_sampling(self):
        s=self.machine;rows=[dict(pointer=i,score=v) for i,v in enumerate((1.,2.,3.,3.05))]
        expected=probabilities(rows,3);n=12000
        counts=Counter(native_weight_choice(s,rows,3) for _ in range(n))
        for i,p in enumerate(expected):self.assertLess(abs(counts[i]/n-p),.015)
    def test_each_written_defense_refuses_uncompiled_retail_source(self):
        from pb.verify_league import OuterImage,BOOK_ENTRIES
        from pb.defense.verify import IMAGE
        with OuterImage(IMAGE) as image:
            for row in json.loads((ROOT/'pb/defense_manifest.json').read_text())['teams']:
                with self.subTest(team=row['team']):
                    raw=image.read_entry(BOOK_ENTRIES[row['team']]);pack=pk.load_pack(ROOT/row['pack'])
                    with self.assertRaisesRegex(pk.PlaybookPackError,'fingerprint'):
                        pk.apply_pack_to_resource(raw,pack)
                    play=next(p for p in pack.plays if p.component=='coverage')
                    forged=replace(play,donor=replace(play.donor,flags=play.donor.flags^0x4000000),
                                   play_flags=play.play_flags^0x4000000)
                    with self.assertRaisesRegex(pk.PlaybookPackError,'donor header'):
                        pk.validate_defense_pack_play(forged,ip.parse_playbook_resource(raw),raw[32:])


if __name__ == "__main__":
    unittest.main()

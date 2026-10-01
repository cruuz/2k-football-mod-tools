"""PROVED OFFLINE: league identity, role correctness, replay freshness and recipe wiring."""
import copy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_playbook_pack as p,nfl2k5_play_library as lib,nfl2k5_playbook_inspector as i
from pb import build_league as generator
from pb.lab.pb_runtime import FreezeClock,page_matches
from tests.mod_editor import test_nfl2k5_complete_offense as complete_tests
from nfl2k5_playbook_position_recode import OuterImage,BOOK_ENTRIES
IMAGE=Path(os.environ.get('NFL2K5_RETAIL_IMAGE','/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso'))

class LeagueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=json.loads((ROOT/'pb/league_manifest.json').read_text())['teams']
        cls.packs={r['team']:p.load_pack(ROOT/r['pack']) for r in cls.manifest}
    def test_exact_team_coverage_and_distinct_football_content(self):
        self.assertEqual(set(self.packs),set(p.TEAM_BOOKS))
        self.assertEqual(len({generator.semantic_digest(v) for v in self.packs.values()}),32)
        # PROVED OFFLINE: concept/menu/personnel allocations differ without using names or indices.
        signatures=[]
        for team,pack in self.packs.items():
            with self.subTest(team=team):
                self.assertEqual(pack.book.resolved_targets(),(team,))
                check=p.check_pack(pack);self.assertTrue(check.ok,check.text())
                rows=json.loads((ROOT/f'pb/catalogs/{team}.json').read_text())
                signatures.append(tuple((r['personnel'],r['concept']) for r in rows))
        self.assertEqual(len(set(signatures)),32)
    def test_every_menu_rejects_duplicate_play(self):
        for team,pack in self.packs.items():
            for fid,menu in pack.menus:
                with self.subTest(team=team,formation=fid):
                    doc=pack.to_json();doc['menus'][fid]=[*menu,menu[0]]
                    with self.assertRaisesRegex(p.PlaybookPackError,'duplicate play in menu'):p.pack_from_json(doc)
    def test_all_native_roles_handoffs_reads_and_screens(self):
        for team,pack in self.packs.items():
            rows={r['play_index']:r for r in json.loads((ROOT/f'pb/catalogs/{team}.json').read_text())}
            byplay={v.id:v for v in pack.plays}
            for fid,menu in pack.menus:
                form=pack.formations_by_id[fid]
                for pid in menu:
                    play=byplay[pid];row=rows[play.replace_index]
                    with self.subTest(team=team,play=pid):
                        self.assertFalse(play.option_intent)
                        self.assertNotIn(0x1A,[op for chain in play.assignments for op,_ in chain])
                        self.assertEqual(form.position_codes[row['te1_slot']],lib.TE)
                        for op,vals in play.assignments[0]:
                            if op in (0x13,0x14):
                                carrier=int(vals[0]);self.assertIn(form.position_codes[carrier]&31,(lib.HB,lib.WR))
                                self.assertTrue(any(n[0] in (0x16,0x17) for n in play.assignments[carrier]))
                            if op==6:
                                self.assertEqual(int(vals[1])+5,row['primary_slot'])
                                if play.concept=='RB Slip':
                                    self.assertEqual(tuple(vals),(5,5,0,0,0,.6))
                                else:
                                    self.assertEqual(len(set(int(v) for v in vals[1:5])),4)
                        if play.concept=='RB Slip':
                            self.assertEqual(form.position_codes[row['primary_slot']],lib.HB)
                            self.assertEqual(sum(any(op==0x18 for op,_ in ch) for ch in play.assignments[1:6]),3)
    def test_declared_bunch_trips_and_empty_are_distinct_geometry(self):
        pack=self.packs['CIN']
        gun=[f for f in pack.formations if ' 11 ' in f.custom_name and 'Gun' in f.custom_name]
        self.assertGreaterEqual(len({f.slot_positions for f in gun}),5)
    def test_league_recipe_resolves_all_books_and_preserves_specials(self):
        recipe=json.loads((ROOT/'pb/recipes/all_teams.json').read_text())['overrides']
        final=json.loads((ROOT/'pb/recipes/final_playbooks.json').read_text())['overrides']
        self.assertEqual(recipe['playbook_packs'],final['playbook_packs'])
        self.assertEqual(set(recipe['playbook_packs'][:32]),{'<stack>/'+r['pack'] for r in self.manifest})
        for flag in ('read_option_runtime','playbook_pair'):
            self.assertFalse(recipe[flag])
        self.assertTrue(recipe['qb_spy'])
        # PROVED OFFLINE: the production preset supplies these enabled owners.
        from mod_editor.core import mod_build
        plan=mod_build.apply_preset(mod_build.BuildPlan('',''),'softdrink_experimental')
        self.assertEqual(plan.screen_timing,'D')
        self.assertTrue(plan.xemu_display_list_fix)
        events=[]
        fixture=complete_tests.PipelineTests()
        fixture.run_build([ROOT/r['pack'] for r in self.manifest],events)
        self.assertEqual(events,[[p.OFFENSE_SCHEMA]*32,'menus','scoring'])
    def test_all_diagram_pages_have_the_correct_native_te_role(self):
        pages=json.loads((ROOT/'pb/diagrams/league_pages.json').read_text())
        self.assertEqual(set(pages),set(p.TEAM_BOOKS))
        for team,row in pages.items():
            text=(ROOT/'pb/diagrams'/row['page']).read_text()
            self.assertIn('DESIGN',text);self.assertIn(team+' MODERN',text)
            self.assertEqual(len(row['plays']),6)

@unittest.skipUnless(IMAGE.is_file(),'Retail image unavailable')
class RetailLeagueTests(unittest.TestCase):
    def test_generator_reproduces_all_31_packs_and_preserves_stock_categories(self):
        profiles=json.loads(generator.PROFILES.read_text())['teams']
        tendency={r['team']:r for r in json.loads((ROOT/'pb/research/tendencies_2025.json').read_text())['teams']}
        with OuterImage(IMAGE) as image:
            for team in p.TEAM_BOOKS:
                if team=='NYG':continue
                with self.subTest(team=team):
                    raw=image.read_entry(BOOK_ENTRIES[team])
                    pack,rows=generator.build(raw,team,profiles[team],tendency[generator.ALIASES.get(team,team)])
                    self.assertEqual(pack.dumps(),p.load_pack(ROOT/f'data/playbooks/softdrink_{team.lower()}_modern.2k5book').dumps())
                    for f in pack.formations:self.assertEqual(f.position_codes,tuple(lib.category_positions(raw[32:],f.category_index)))
    def test_replay_receipts_cover_every_formation_page_and_current_pack(self):
        receipt=json.loads((ROOT/'pb/receipts/league-offline.json').read_text())
        self.assertEqual(receipt['build_menu_gate'],{'books':37,'problems':0})
        self.assertFalse(receipt['runtime_witness'])
        self.assertEqual(set(receipt['teams']),set(p.TEAM_BOOKS))
        with OuterImage(IMAGE) as image:
            for team,row in receipt['teams'].items():
                with self.subTest(team=team):
                    raw=image.read_entry(BOOK_ENTRIES[team]);stock=i.parse_playbook_resource(raw)
                    self.assertEqual(row['compile']['source_sha256'],hashlib.sha256(raw).hexdigest())
                    self.assertEqual(row['pack_sha256'],hashlib.sha256((ROOT/row['pack']).read_bytes()).hexdigest())
                    self.assertEqual(len(row['walks']),len(stock.formations))
                    self.assertEqual(row['unique_plays'],len(stock.plays))
                    for f in row['walks']:
                        self.assertTrue(f['ended']);self.assertEqual(len(f['plays']),len(set(f['plays'])))
                        self.assertEqual([pi for page in f['pages'] for pi in page['plays']],f['plays'])
                        self.assertTrue(all(page['returned'] for page in f['pages']))

class LabTests(unittest.TestCase):
    def test_plan_has_ten_cases_six_formations_all_concepts(self):
        plan=json.loads((ROOT/'pb/lab/plan.template.json').read_text());cases=plan['cases']
        self.assertEqual(len(cases),10);self.assertGreaterEqual(len({r['formation'] for r in cases}),6)
        self.assertTrue({'Inside Zone','Outside Zone','Mesh','Y Cross','TE Seam','TE Drag','RB Slip','End Around'}<={r['concept'] for r in cases})
        for row in cases:
            self.assertTrue(page_matches(row['formation']+' '+' '.join(row['page_labels']),row))
            self.assertFalse(page_matches(' '.join(row['page_labels']),row))
        self.assertEqual(plan['attempts'],1)
    def test_freeze_guard_ignores_inputs_and_stops_after_sixty_seconds(self):
        guard=FreezeClock(0)
        self.assertIsNone(guard.observe('a',0));self.assertIsNone(guard.observe('a',60))
        self.assertIn('static frame',guard.observe('a',61))
        guard=FreezeClock(0);guard.advance('case 1',0)
        for n in range(61):guard.observe(str(n),n)
        self.assertIn('stage progress',guard.observe('changed',61))
        guard.advance('case 2',61);self.assertIsNone(guard.observe('changed',62))
    def test_lab_script_security_and_two_turn_lifecycle_are_explicit(self):
        text=(ROOT/'pb/lab/pb_lab.sh').read_text()
        for required in ('trap cleanup EXIT','rm -f -- "$DISC"','nice -n 10 taskset -c 0-23','nice -n 19 taskset -c 24-31','LP_NUM_THREADS=4 SDL_AUDIODRIVER=dummy','while pgrep -x xemu >/dev/null; do sleep 5; done','run-turn-2'):
            self.assertIn(required,text)
        self.assertEqual(text.count('pb_runtime.py'),1)
        self.assertNotIn('pkill',text)
        recipe=json.loads((ROOT/'pb/lab/v7.pb.json').read_text())['overrides']
        self.assertFalse(recipe['read_option_runtime']);self.assertFalse(recipe['playbook_pair'])
        self.assertFalse(any('softdrink_option' in v for v in recipe['playbook_packs']))


if __name__ == "__main__":
    unittest.main()

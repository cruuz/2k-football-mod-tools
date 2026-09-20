"""Replication gates must reject false confidence and invalid team colours."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from tools.scorebug_sprite.jev import accents,descriptors,judge,layout_search,session,replay


class ReplicationTests(unittest.TestCase):
    def test_source_closure_and_pins(self):
        spec=importlib.util.spec_from_file_location('replication_pins',ROOT/'packaging/scorebug_replication_pins.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        declared=set((ROOT/'packaging/release-allowlist.txt').read_text().splitlines())
        for name,wanted in module.PINS.items():
            self.assertIn(name,declared)
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),wanted,name)

    def test_all_roster_slots_and_contrast_gates(self):
        data=json.loads((ROOT/'data/nfl2k5_scorebug_sprite/team_accents.json').read_text())
        self.assertEqual({t['slot'] for t in data['teams'].values()},set(range(52)))
        for name,team in data['teams'].items():
            for role in ('wing','rim','plate','wash'):
                color=team[role]
                self.assertGreaterEqual(descriptors.contrast(accents.rgb(color)),4.5,(name,role))
                candidates=[c for c in team['candidates'].values() if c['hex']==color]
                self.assertTrue(candidates)
                self.assertTrue(all(c['parent'] in team['official'] for c in candidates))
        for role in ('wing','rim','plate'):
            r,g,b=accents.rgb(data['teams']['LV'][role]);self.assertLessEqual(max(r,g,b)-min(r,g,b),2)

    def test_every_native_team_roundtrips_through_matchup_arguments(self):
        from tools.scorebug_sprite.render import team,TEAM_LOGOS
        for name in TEAM_LOGOS:self.assertEqual(team(name),name)
        self.assertEqual(team('COMMANDERS'),'WAS')

    def test_current_nfl_palette_uses_supplied_shades_and_excludes_logo_details(self):
        source=json.loads((ROOT/'data/nfl2k5_scorebug_sprite/team_colors_official_2026.json').read_text())
        actual=json.loads((ROOT/'data/nfl2k5_scorebug_sprite/team_accents.json').read_text())['teams']
        by_slot={t['nfl2k5_retail_slot']['index']:t for t in source['teams']}
        for team in actual.values():
            if team['slot']>=32:continue
            allowed={c['hex'].upper() for c in by_slot[team['slot']]['colors'] if not c.get('logo_detail_only',False)}
            self.assertEqual(set(team['official']),allowed)

    def test_jev_cannot_inject_a_foreign_colour(self):
        team=dict(slot=22,asset_code='20',source='test',official=['#101010','#D1D2D3'],logo_fit=dict(fill_x=1,height=1))
        teams,_=accents.prepare(dict(teams={'LV':team}))
        bad={role:dict(choice='#FF00AA',confidence=1) for role in ('wing','rim','plate')}
        result=accents.choose(teams,[bad,bad]);self.assertTrue(result['review'])
        self.assertIn(result['teams']['LV']['plate'],{v['hex'] for v in teams['LV']['candidates'].values()})

    def test_equivalent_black_variants_are_not_a_colour_disagreement(self):
        team=dict(slot=22,asset_code='20',source='test',official=['#000000'],logo_fit={})
        teams,_=accents.prepare(dict(teams={'LV':team}))
        a={r:dict(choice='colour0_base',confidence=1) for r in ('wing','rim','plate')}
        b={r:dict(choice='colour0_dark',confidence=1) for r in ('wing','rim','plate')}
        self.assertEqual(accents.choose(teams,[a,b])['review'],[])

    def test_unverified_calibration_blocks_mutations_and_baseline(self):
        called=[]
        with self.assertRaisesRegex(ValueError,'calibration'):
            layout_search.run({},lambda _:called.append('render'),lambda _:called.append('Jev'))
        self.assertEqual(called,[])

    def test_measured_objective_vetoes_confident_worsening_and_matches_control_budget(self):
        spec=json.loads((ROOT/'data/nfl2k5_scorebug_sprite/layout.json').read_text())
        def evaluate(s):
            size=next(f['size'] for f in s['fields'] if f['name']=='down')
            return dict(residuals=[dict(feature='cap',error=abs(size-28),tolerance=.5)],readability=dict(label=True))
        def decide(_):return dict(next_input='label_larger',confidence=1,goal_reached_p=1)
        final,result=layout_search.run(spec,evaluate,decide,steps=3,calibration_verified=True)
        self.assertEqual(final,spec)
        self.assertFalse(any(r['kept'] for r in result['curves']['jev']))
        self.assertFalse(any(r['goal_reached'] for r in result['curves']['jev']))
        self.assertEqual(len(result['curves']['jev']),len(result['curves']['random']))

    def test_budget_reads_batch_and_individual_receipts(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(session,'usage_total',return_value=0):
                s=session.Session(directory)
                s.record(dict(tool='jev_ask'),dict(answers={},meta=dict(cost_usd=1.4)))
                s.record(dict(tool='jev_batch'),dict(results=[],totals=dict(cost_usd=1.6)))
                self.assertAlmostEqual(s.spent(),3)
                with self.assertRaisesRegex(RuntimeError,'cap'):s.guard(dict(state='no call'))

    def test_opaque_source_image_does_not_turn_every_glyph_into_a_rectangle(self):
        templates=descriptors.templates()
        for name in ('0','1','&'):
            self.assertTrue(templates[name].any())
            self.assertFalse(templates[name].all())

    def test_replay_cannot_reuse_a_judgment_for_changed_evidence(self):
        import tempfile
        request=dict(state='first frame')
        with tempfile.TemporaryDirectory() as directory:
            log=Path(directory)/'answers.jsonl'
            log.write_text(json.dumps(dict(request_sha256=replay.request_hash(request),answers={'state':'normal'}))+'\n',encoding='utf-8')
            self.assertEqual(replay.resume([request],log),[{'state':'normal'}])
            with self.assertRaisesRegex(ValueError,'does not match'):
                replay.resume([dict(state='another frame')],log)

    def test_missing_bright_ink_does_not_assert_an_occlusion_cause(self):
        row=dict(field='down',actual_luma=[19,27,67],preview_luma=[20,80,255],core_delta=255,
            placement_delta=None,residual='far',actual_ink=False,preview_ink=True,actual_hue='neutral',preview_hue='neutral')
        req=judge.request([row],'plate submits before label')
        self.assertNotIn('actual_luma',req['state']['fields'][0])
        self.assertIn('unproved',req['questions']['down']['instructions'])


if __name__=='__main__':unittest.main()

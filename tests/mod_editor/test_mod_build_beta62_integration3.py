"""Integration-3 behavior gates. Compact fixtures and bounded retail XBE reads."""
from contextlib import ExitStack
import dataclasses
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from mod_editor.core import mod_build as build, nfl2k5_throw_tuning as tt
from mod_editor.core import nfl2k5_build_settings as saved, nfl2k5_roster_records as rr
from tests.mod_editor.test_nfl2k5_xbe_space import RETAIL, image_with_xbe

FLAGS = ('momentum_collisions', 'read_option_runtime', 'franchise_2026_rules', 'senior_bowl',
         'guardian_overlay', 'my_career', 'crib_reclaim', 'screen_hooks', 'modern_naming', 'reserves_16')


class IntegrationPlans(unittest.TestCase):
    def test_presets_and_explicit_recipe_values(self):
        for key in build.PRESETS:
            p = build.apply_preset(build.BuildPlan('s', 't'), key)
            for flag in set(FLAGS) - {'modern_naming'}:
                self.assertIs(getattr(p, flag), False, (key, flag))
            self.assertIs(p.scorebug_runtime, False)
            self.assertEqual(p.created_teams_extra, 0)
        with patch.object(tt.modern_naming_patch, 'preset_enabled', return_value=False):
            self.assertFalse(build.apply_preset(build.BuildPlan('s', 't'), 'softdrink_experimental').modern_naming)
        p = build.BuildPlan('s', 't', momentum_collisions=True, momentum_collision_level=37,
                            guardian_overlay=True, guardian_everyone_practice=False,
                            created_teams_extra=2, hires_families=('helmets', 'jerseys'))
        restored = build.BuildPlan('s', 't', **json.loads(json.dumps(p.to_recipe())))
        self.assertEqual(restored.momentum_collision_level, 37)
        self.assertFalse(restored.guardian_everyone_practice)
        self.assertEqual(restored.created_teams_extra, 2)
        self.assertEqual(tuple(restored.hires_families), ('helmets', 'jerseys'))
        self.assertNotIn('scorebug_runtime_probe', {f.name for f in dataclasses.fields(p)})

    def test_new_invalid_settings_and_unavailable_events_refuse_before_copy(self):
        with tempfile.TemporaryDirectory() as folder, patch('shutil.copyfile', side_effect=AssertionError('copied')):
            source, target = Path(folder)/'source.iso', Path(folder)/'target.iso'
            source.write_bytes(b'not an image'); target.write_bytes(b'KEEP')
            cases = [{key: 1} for key in FLAGS] + [
                {'season_cap': 1}, {'guardian_everyone_practice': 1}, {'momentum_collision_level': True},
                {'momentum_collision_level': 1}, {'momentum_collisions':True, 'momentum_collision_level':101},
                {'created_teams_extra':True}, {'created_teams_extra':1}, {'senior_bowl_seed':True},
                {'franchise_2026_rules':True}, {'senior_bowl':True}, {'my_career':True},
                {'guardian_overlay':True, 'guardian_cap':True}, {'guardian_players':[]},
                {'hires_families':('helmets','helmets')}, {'hires_families':('names',)},
                {'hires_pack':True,'hires_families':()},
            ]
            for settings in cases:
                with self.subTest(settings=settings), self.assertRaises(ValueError):
                    build.build(build.BuildPlan(str(source), str(target), overwrite=True, **settings))
                self.assertEqual(target.read_bytes(), b'KEEP')
            for key in ('franchise_2026_rules', 'senior_bowl'):
                with patch.object(build, '_prepare_music_project', side_effect=AssertionError('prepared unavailable event')):
                    with self.assertRaises(ValueError):
                        build.build(build.BuildPlan(str(source), str(target), **{key:True}))
                with self.assertRaises(ValueError):
                    tt._apply_all(b'', None, False, **{key:True})
                with self.assertRaises(ValueError):
                    tt._selected_space_requests(**{key:True})

    def test_exact_owner_union_and_independent_career(self):
        self.assertEqual(tt._selected_space_requests(my_career=True), tt.my_career_patch.REQUESTS)
        self.assertEqual(tt._selected_space_requests(momentum_collisions=True), ())
        kwargs = dict(momentum_collisions=True, momentum_collision_level=50, read_option_runtime=True,
                      guardian_overlay=True, my_career=True, screen_hooks=True, reserves_16=True,
                      created_teams_extra=2)
        expected = tuple(row for module in (tt.momentum_patch, tt.read_option_patch,
            tt.guardian_overlay_patch, tt.my_career_patch, tt.screen_hooks_patch,
            tt.roster_arena_patch, tt.practice_squad_screen_patch) for row in module.REQUESTS)
        actual = tt._selected_space_requests(**kwargs)
        self.assertCountEqual(actual, expected)
        self.assertEqual(len(actual), len(set(actual)))

    def test_typed_project_settings_are_detached_and_music_compatible(self):
        choices = {'momentum_collisions':True, 'momentum_collision_level':37,
                   'senior_bowl_settings': saved.defaults()['senior_bowl_settings'], 'senior_bowl_seed':42,
                   'guardian_everyone_practice':False, 'hires_families':['helmets']}
        copy = saved.build_settings(choices)
        choices['senior_bowl_settings']['away']['bank'] = 51
        self.assertEqual(copy['senior_bowl_settings']['away']['bank'],50)
        self.assertEqual(saved.build_settings(json.loads(json.dumps(copy))), copy)
        self.assertEqual(saved.build_settings({}), {})
        for invalid in ({'unknown':True},{'senior_bowl_seed':True},{'guardian_players':[0]},
                        {'momentum_collisions':1},{'hires_families':['helmets','helmets']}):
            with self.assertRaises(ValueError):saved.build_settings(invalid)

    def test_later_play_edits_cannot_reuse_earlier_report(self):
        from mod_editor.core import nfl2k5_playbook_pack as packs
        recode=packs._outer_image(); team=next(iter(recode.BOOK_ENTRIES))
        archive=unittest.mock.MagicMock()
        archive.__enter__.return_value=archive
        archive.read_entry.return_value=b'changed'
        report={'asset_id':'book:'+team,'option_intent':{'records':[{}]}}
        with patch.object(recode,'OuterImage',return_value=archive):
            with self.assertRaisesRegex(ValueError,'changed after compilation'):
                build._verify_play_intents(Path('unused'),[(b'original',report)])
        self.assertEqual(build._preview_play_intents(Path('missing'),()), [])

    def test_guardian_csv_and_bulk_preserve_every_neighbor_bit(self):
        from tests.mod_editor.test_nfl2k5_roster_records import synthetic_body
        doc=rr.RosterDocument(synthetic_body()); player=doc.players[0]
        raw=player.record.encode(); record=rr.PlayerRecord.decode(raw)
        before=record.encode(); abilities=record.abilities.copy(); helmet=record.values['helmet']
        record.guardian_cap=True
        after=record.encode()
        self.assertEqual([i for i,(a,b) in enumerate(zip(before,after)) if a!=b], [0x53] if not before[0x53]&0x20 else [])
        self.assertEqual(after[0x53], before[0x53]|0x20)
        self.assertEqual(record.abilities,abilities);self.assertEqual(record.values['helmet'],helmet)
        player.record.guardian_cap=True
        csv=rr.export_csv(doc)
        self.assertIn('guardian_cap', csv.splitlines()[0])
        player.record.guardian_cap=False
        imported=rr.import_csv(doc,csv)
        self.assertEqual(imported['fields'],1)
        self.assertTrue(player.record.guardian_cap)
        self.assertEqual(rr.import_csv(doc,csv)['fields'],0)
        record.set('guardian_cap',0); self.assertFalse(record.guardian_cap)
        with self.assertRaises(ValueError): record.guardian_cap=1


@unittest.skipUnless(RETAIL.is_file(), 'pinned USA retail executable absent')
class ExecutableIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail=RETAIL.read_bytes()

    def test_collision_only_uses_scaleout_and_retains_zero_movement(self):
        settings=dict(momentum_collisions=True,momentum_collision_level=37)
        payload,receipt=tt._apply_all(self.retail,None,False,**settings)
        self.assertTrue(tt.xbe_space_patch.is_scaleout(payload))
        fields=tt._grown_status_fields(payload)
        self.assertEqual(fields['momentum'],'retail')
        self.assertEqual(fields['momentum_collisions'],'applied')
        self.assertEqual(tt.momentum_patch.read_settings(payload)['momentum_collision_level'],37)
        self.assertEqual(tt._apply_all(payload,None,False,**settings)[0],payload)
        self.assertEqual(tt._apply_all(self.retail,None,False,momentum_collisions=True)[0],self.retail)

    def test_new_dispatcher_components_compose_and_roundtrip_all_statuses(self):
        kwargs=dict(read_option_runtime=True,screen_hooks=True,my_career=True,guardian_overlay=True,
                    guardian_everyone_practice=False,created_teams_extra=2,reserves_16=True,
                    defensive_try=True,widescreen=True)
        payload,receipt=tt._apply_all(self.retail,None,False,**kwargs)
        fields=tt._grown_status_fields(payload)
        for key in ('read_option_runtime','screen_hooks','my_career','guardian_overlay',
                    'reserves_16','created_teams_extra','defensive_try'):
            self.assertEqual(fields[key],'applied',key)
        self.assertEqual(fields['franchise_2026_rules'],'unavailable')
        self.assertIs(fields['senior_bowl_native_available'],False)
        self.assertEqual(receipt['widescreen_patch']['version'],3)
        self.assertEqual(tt._apply_all(payload,None,False,**kwargs)[0],payload)
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'default.xbe'; p.write_bytes(payload)
            read=tt.read_xbe(p)
            for key in ('read_option_runtime','screen_hooks','my_career','reserves_16','created_teams_extra'):
                self.assertEqual(read[key],'applied')


@unittest.skipUnless(RETAIL.is_file(), 'paired resources require the pinned USA extraction')
class PairedBuildIntegration(unittest.TestCase):
    def test_guardian_resource_growth_then_final_screen_hooks(self):
        from tests.mod_editor.test_nfl2k5_guardian_resources import ResourceTests, g
        ResourceTests.setUpClass()
        fixture = ResourceTests(methodName='test_streamed_paired_image_growth_all_outer_mappings_and_replay')
        with tempfile.TemporaryDirectory() as directory, patch.object(g,'compile_collection',new=fixture.compiler):
            source=Path(directory)/'source.iso';target=Path(directory)/'target.iso'
            fixture.fixture(source)
            with patch.object(build,'inspect',return_value={'container':'xiso'}):
                receipt=build.build(build.BuildPlan(str(source),str(target),guardian_overlay=True,screen_hooks=True,
                                                    guardian_everyone_practice=False))
            self.assertEqual(g.image_status(target),'applied')
            payload=build._xbe_bytes(target)
            self.assertEqual(tt.screen_hooks_patch.status(payload),'applied')
            self.assertFalse(tt.guardian_overlay_patch.read_settings(payload)['guardian_everyone_practice'])
            self.assertEqual([row['step'] for row in receipt['steps']],['copy','guardian_overlay','xbe_space'])
            self.assertEqual(g.image_status(source),'retail')

    def test_modern_naming_build_writes_both_halves_and_off_refuses_named_source(self):
        from tests.mod_editor.test_nfl2k5_modern_naming import fixture_image, synthetic_strg, n
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);fixture=fixture_image(root,RETAIL.read_bytes(),synthetic_strg())
            target=root/'named.iso'
            with patch.object(build,'inspect',return_value={'container':'xiso'}):
                receipt=build.build(build.BuildPlan(str(fixture.path),str(target),modern_naming=True))
            self.assertEqual(n.image_status(target),'applied')
            self.assertEqual(n.image_status(fixture.path),'retail')
            self.assertIn('modern_naming_patch',receipt['steps'][0])
            other=root/'keep.iso';other.write_bytes(b'KEEP')
            with self.assertRaisesRegex(ValueError,'original source'):
                build.build(build.BuildPlan(str(target),str(other),overwrite=True))
            self.assertEqual(other.read_bytes(),b'KEEP')

    def test_roster_growth_is_paired_after_final_executable(self):
        from tests.mod_editor.test_nfl2k5_roster_arena_image import PairedArchiveTests, writer
        fixture=PairedArchiveTests(methodName='test_paired_growth_replay_neighbors_and_transaction_rollback')
        fixture.setUp();self.addCleanup(fixture.doCleanups)
        target=fixture.directory/'build.iso'
        with patch.object(build,'inspect',return_value={'container':'xiso'}):
            receipt=build.build(build.BuildPlan(str(fixture.source),str(target),reserves_16=True,created_teams_extra=2))
        self.assertEqual(writer.image_status(target),'applied')
        payload=build._xbe_bytes(target)
        self.assertEqual(tt.practice_squad_screen_patch.status(payload),'applied')
        settings=tt.roster_arena_patch.read_settings(payload)
        self.assertTrue(settings['reserves_16']);self.assertEqual(settings['created_teams_extra'],2)
        self.assertEqual(receipt['steps'][-1]['step'],'roster_arena_growth')
        self.assertEqual(writer.image_status(fixture.source),'retail')


if __name__=='__main__':unittest.main()

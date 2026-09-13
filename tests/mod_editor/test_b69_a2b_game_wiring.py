"""Integrated choices, source refusals and real compact-disc publication.

The XBE is the private pinned USA executable. The climate ROST is synthesized
and only its declared shape pin is substituted. All parsers, writers, read-back,
allocation and publication paths run unchanged; no retail resource is bundled.
"""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from mod_editor.core import mod_build as build, nfl2k5_throw_tuning as tt
from mod_editor.core import nfl2k5_weather as weather, nfl2k5_weather_haze as haze
from mod_editor.core import nfl2k5_build_settings as saved
from tests.mod_editor.test_nfl2k5_weather import synthetic
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe
from tests.mod_editor.test_shipped_tools_posix_only import simulated_non_posix

DEFAULTS = dict(weather_plan='', weather_haze=False, coin_defer=False,
                decided_clock=False, decided_clock_margin=17,
                decided_clock_seconds=60, cpu_scrambles='retail')


def compact_image(xbe, resource, *, pack_sector=48):
    from nfl2k5_xiso_fixture import dir_node, xiso
    # A complete index with invented empty resources lets unrelated inspectors
    # reject metadata normally, without substituting the integrated inspector.
    align = lambda n: (n + 2047) // 2048 * 2048
    count = 16384
    offset = align(156 + count * 12)
    pack = bytearray(offset + 5*2048 + align(len(resource)))
    struct.pack_into('<4I', pack, 0, count, 0, 1, len(pack)//2048)
    for i in range(count):
        blob = resource if i == 5 else bytes([i])*32 if i < 5 else b''
        struct.pack_into('<3I', pack, 156+12*i, i+1, len(blob), offset//2048)
        pack[offset:offset+len(blob)] = blob
        offset += align(len(blob))
    xbe_sector = pack_sector + len(pack)//2048 + 1
    neighbour = xbe_sector + align(len(xbe))//2048
    children = dir_node([(pack_sector, len(pack), 0x80, '0')])
    rows = [(40, len(children), 0x10, 'vc_53450030'),
            (xbe_sector, len(xbe), 0x80, 'default.xbe'),
            (neighbour, 8, 0x80, 'neighbour')]
    root = dir_node(rows)
    image = bytearray((neighbour+1)*2048)
    image[0x10000:0x10014] = image[0x107ec:0x10800] = xiso.XDVDFS_MAGIC
    struct.pack_into('<II', image, 0x10014, 33, len(root))
    image[33*2048:33*2048+len(root)] = root
    image[40*2048:40*2048+len(children)] = children
    image[pack_sector*2048:pack_sector*2048+len(pack)] = pack
    image[xbe_sector*2048:xbe_sector*2048+len(xbe)] = xbe
    image[neighbour*2048:neighbour*2048+8] = b'KEEPTHIS'
    return bytes(image)


class ChoiceTests(unittest.TestCase):
    def test_all_defaults_and_recipe_identity_roundtrip(self):
        for preset in build.PRESETS.values():
            self.assertEqual({key:preset[key] for key in DEFAULTS}, DEFAULTS)
        plan = build.BuildPlan('s','t', weather_plan='weather.json', weather_haze=True,
            coin_defer=True, decided_clock=True, decided_clock_margin=25,
            decided_clock_seconds=90, cpu_scrambles='modern')
        recipe = saved.from_plan(plan)
        self.assertEqual(json.loads(json.dumps(saved.to_plan(recipe, 's','t').to_recipe())), json.loads(json.dumps(plan.to_recipe())))
        for key, default in DEFAULTS.items():
            self.assertNotEqual(saved.from_plan(replace(plan, **{key:default})), recipe, key)
        self.assertFalse(build.BuildPlan('s','t',weather_plan='climate.json').wants_xbe_patch())
        self.assertTrue(build.BuildPlan('s','t',weather_haze=True).wants_xbe_patch())

    def test_union_and_enum_deferral(self):
        union = tt._selected_space_requests(coin_defer=True, decided_clock=True, cpu_scrambles='modern')
        self.assertCountEqual(union,tt.coin_defer_patch.REQUESTS+tt.decided_clock_patch.REQUESTS+tt.cpu_scrambles_patch.REQUESTS)
        self.assertEqual(tt._selected_space_requests(), ())
        defaults = build._r62_plan_options(build.BuildPlan('s','t'))
        deferred = tt._deferred_r62_options({k:defaults[k] for k in tt.R62_RUNTIME_KEYS}, True)
        self.assertEqual(deferred['cpu_scrambles'],'retail')
        tt._validate_r62_options(**deferred)


class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from mod_editor.gui.build_panel_qt import BuildPanel
        from mod_editor.gui.gameplay_patches_panel_qt import GameplayPatchesPanel
        from mod_editor.gui.gameplay_project_ui import GameplayBuildLink
        self.build,self.gameplay=BuildPanel(),GameplayPatchesPanel()
        self.addCleanup(self.build.close);self.addCleanup(self.gameplay.close)
        self.link=GameplayBuildLink(self.build,self.gameplay,lambda:None)
        self.state=dict(path='source.iso',container='xiso',weather_plan='available',
            weather_haze='retail',coin_defer='retail',decided_clock='retail',cpu_scrambles='retail')
        self.build.apply_state(self.state);self.gameplay.apply_state(self.state)
        self.build.source_field.setText('source.iso');self.build.target_field.setText('target.iso')

    def test_live_controls_roundtrip_project_and_both_views(self):
        choices=dict(weather_plan='climate.json',weather_haze=True,coin_defer=True,
            decided_clock=True,decided_clock_margin=25,decided_clock_seconds=90,cpu_scrambles='modern')
        with patch.object(self.build,'_weather_plan_problem',return_value=''):
            self.build.restore_project_build_settings(choices)
            self.link.refresh_from_build()
            self.assertEqual({k:self.build.plan().to_recipe()[k] for k in choices},choices)
            for key in ('coin_defer','decided_clock','decided_clock_margin','decided_clock_seconds','cpu_scrambles','weather_haze'):
                self.assertEqual(getattr(self.gameplay.plan(),key),choices[key])
            self.gameplay.cpu_scrambles_level.setCurrentIndex(0)
            self.assertEqual(self.build.plan().cpu_scrambles,'retail')
            self.gameplay.decided_clock_margin.setCurrentIndex(0)
            self.assertEqual(self.build.plan().decided_clock_margin,9)
            self.assertIn('CPU winners only', self.build.coin_defer_check.text())
            self.assertTrue(self.build.has_work())
            self.assertIn('Climate plan: climate.json',self.build.confirmation_text(self.build.plan()))
        # Source reinspection followed by normal project restore preserves path and selection.
        self.build.apply_state(self.state)
        with patch.object(self.build,'_weather_plan_problem',return_value=''):
            self.build.restore_project_build_settings(choices)
        self.assertEqual(self.build.plan().weather_plan,'climate.json')

    def test_installed_rules_preserved_across_presets_and_haze_off_is_visible(self):
        state={**self.state,'weather_haze':'applied','coin_defer':'applied',
            'decided_clock':'applied','cpu_scrambles':'applied',
            'decided_clock_settings':dict(status='applied',settings=dict(margin=33,seconds=120))}
        self.build.apply_state(state);self.gameplay.apply_state(state)
        for preset in build.PRESETS:
            self.build.apply_preset(preset)
            plan=self.build.plan()
            self.assertTrue(plan.coin_defer and plan.decided_clock)
            self.assertEqual((plan.decided_clock_margin,plan.decided_clock_seconds,plan.cpu_scrambles),(33,120,'modern'))
            self.assertFalse(self.build.decided_clock_margin.isEnabled())
            self.assertIn('Restore retail dry-weather haze response',self.build.selected_labels())
        self.gameplay.checks['weather_haze'].setChecked(False)
        self.assertTrue(self.gameplay._weather_haze_changed())


class CompactBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail=retail_xbe()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='a2b-compact-')
        self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.resource,digest=synthetic()
        self.pin=patch.object(weather,'SHAPE_SHA256',digest);self.pin.start();self.addCleanup(self.pin.stop)
        self.source=self.root/'source.iso';self.source.write_bytes(compact_image(self.retail,self.resource))
        draft=weather.WeatherDraft(self.resource);draft.set_value(5,12,'temperature_f',15)
        self.document=draft.plan();self.plan_file=self.root/'climate.json'
        weather.write_json(self.plan_file,self.document)

    def test_off_build_is_byte_identical_and_new_choices_each_build(self):
        for key,value in DEFAULTS.items():
            if key in ('decided_clock_margin','decided_clock_seconds'):continue
            selected={'weather_plan':str(self.plan_file),'weather_haze':True,'coin_defer':True,
                      'decided_clock':True,'cpu_scrambles':'modern'}[key]
            target=self.root/(key+'.iso')
            with self.subTest(key=key),simulated_non_posix():
                receipt=build.build(build.BuildPlan(str(self.source),str(target),**{key:selected}))
            if key=='weather_plan':
                self.assertEqual(weather.status(weather.load_resource(target),self.document),'applied')
                self.assertEqual(build._xbe_bytes(target),self.retail)
            else:self.assertEqual(receipt['result'][key],'applied')
        target=self.root/'off.iso'
        with simulated_non_posix():build.build(build.BuildPlan(str(self.source),str(target)))
        self.assertEqual(target.read_bytes(),self.source.read_bytes())

    def test_new_options_compose_with_career_and_relocated_climate_then_replay(self):
        target=self.root/'composed.iso'
        plan=build.BuildPlan(str(self.source),str(target),weather_plan=str(self.plan_file),
            weather_haze=True,coin_defer=True,decided_clock=True,decided_clock_margin=25,
            decided_clock_seconds=90,cpu_scrambles='modern',my_career=True,accelerated_clock=True)
        original=hashlib.sha256(self.source.read_bytes()).hexdigest()
        def project_copy(destination):destination.write_bytes(compact_image(self.retail,self.resource,pack_sector=56))
        with simulated_non_posix(): receipt=build.build(plan,_project_builder=project_copy)
        result=build._xbe_bytes(target)
        for owner in (tt.coin_defer_patch,tt.decided_clock_patch,tt.cpu_scrambles_patch,tt.my_career_mode_patch,haze):
            self.assertEqual(owner.status(result),'applied')
        tt.decided_clock_patch.verify(result,margin=25,seconds=90)
        self.assertTrue(receipt['plan']['depth_locks'])
        self.assertEqual(receipt['steps'][-1]['step'],'weather_plan')
        weather.verify(weather.load_resource(target),self.document,before=self.resource)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(),original)
        repeat=self.root/'repeated.iso'
        with simulated_non_posix():build.build(replace(plan,source=str(target),target=str(repeat)))
        self.assertEqual(build._xbe_bytes(repeat),result)
        self.assertEqual(weather.load_resource(repeat),weather.load_resource(target))
        # Removal/reconfiguration refuses before project materialization too.
        for change in ({'decided_clock_margin':17}, {'coin_defer':False},
                       {'decided_clock':False}, {'cpu_scrambles':'retail'},
                       {'accelerated_clock':False}):
            with self.subTest(change=change):
                project=unittest.mock.Mock(side_effect=AssertionError('materialized before refusal'))
                with self.assertRaises(ValueError):
                    build.build(replace(plan,source=str(target),target=str(self.root/'bad.iso'),**change),
                                _project_builder=project)
                project.assert_not_called()
                self.assertFalse((self.root/'bad.iso').exists())

    def test_climate_refuses_stale_partial_and_arena_plans_before_project_copy(self):
        invalid=json.loads(json.dumps(self.document));invalid['changes'][0]['before']=99
        weather.write_json(self.root/'stale.json',invalid)
        for settings in ({'weather_plan':str(self.root/'stale.json')},
                         {'weather_plan':str(self.plan_file),'reserves_16':True},
                         {'weather_plan':str(self.plan_file),'created_teams_extra':2},
                         {'weather_haze':1},{'coin_defer':1},{'cpu_scrambles':False},
                         {'decided_clock':True,'decided_clock_margin':True}):
            with self.subTest(settings=settings),patch.object(build,'_prepare_music_project',side_effect=AssertionError('prepared')):
                project=unittest.mock.Mock(side_effect=AssertionError('copied before refusal'))
                with self.assertRaises(ValueError):build.build(build.BuildPlan(str(self.source),str(self.root/'refused.iso'),**settings),_project_builder=project)
                project.assert_not_called()

    def test_haze_off_restores_and_climate_failure_preserves_destination(self):
        applied=haze.apply(self.retail)[0];self.source.write_bytes(compact_image(applied,self.resource))
        target=self.root/'restored.iso'
        receipt=build.build(build.BuildPlan(str(self.source),str(target)))
        self.assertEqual(build._xbe_bytes(target),self.retail)
        self.assertEqual(receipt['steps'][-1]['step'],'weather_haze')
        target.write_bytes(b'KEEP DESTINATION')
        with patch.object(weather,'apply_to_image',side_effect=OSError('simulated final write failure')):
            with self.assertRaises(OSError):build.build(build.BuildPlan(str(self.source),str(target),overwrite=True,weather_plan=str(self.plan_file)))
        self.assertEqual(target.read_bytes(),b'KEEP DESTINATION')


if __name__=='__main__':unittest.main()

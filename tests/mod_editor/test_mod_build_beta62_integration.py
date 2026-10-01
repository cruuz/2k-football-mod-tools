"""Beta-62 Build/Share handoff contracts; host byte proofs, never played evidence."""
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from mod_editor.core import mod_build as build, nfl2k5_throw_tuning as tt
from mod_editor.core import nfl2k5_team_names_2026 as names
# Exactly the owners selected by this integration-2 fixture. Integration 3
# additionally tests the independently selected new owners in its own suite.
REQUESTS = tuple(row for module in (
    tt.kickoff_relocated_patch, tt.scorebug_runtime_patch, tt.momentum_patch,
    tt.defensive_try_patch, tt.zone_drop_patch, tt.roster_storage_patch,
    tt.coverage_slider_patch, tt.scramble_tuning_patch, tt.music_playlist_patch,
    tt.practice_squad_screen_patch, tt.abilities_patch, tt.qb_spy_patch, tt.calendar_engine_patch,
) for row in module.REQUESTS)
from tests.mod_editor.test_nfl2k5_xbe_space import RETAIL, image_with_xbe

FLAGS = ('all_stadiums', 'team_names_2026', 'coverage_slider', 'scramble_tuning',
         'flatter_deep_ball', 'chop_block_toggle', 'hires_pack')
GROWN = dict(all_stadiums=True, coverage_slider=True, scramble_tuning=True, music_shuffle=True, practice_squad_screen=True, abilities=True, abilities_off_week=6, qb_spy=True,
             momentum=100, momentum_contact=True, defensive_try=True, zone_drop_cap=True)


class PlanTests(unittest.TestCase):
    def setUp(self):
        # These plan fixtures have no PLAY archive. Real native gate execution
        # and corruption rejection are covered by test_nfl2k5_play_scoring.
        gate = patch.object(build, '_check_playbook_scoring', return_value={'status':'applied','books':0,'faults':0})
        gate.start()
        self.addCleanup(gate.stop)

    def test_presets_clear_optins_and_recipe_retains_hires_inputs(self):
        initial = build.BuildPlan('s', 't', **dict.fromkeys(FLAGS, True),
                                  hires_folder='Hi-res', hires_scale=1, hires_target='xemu-64')
        for preset in build.PRESETS:
            plan = build.apply_preset(initial, preset)
            self.assertTrue(all(getattr(plan, key) is False for key in FLAGS))
            restored = build.BuildPlan('s', 't', **plan.to_recipe())
            self.assertEqual((restored.hires_folder, restored.hires_scale, restored.hires_target),
                             ('Hi-res', 1, 'xemu-64'))
        for key in FLAGS:
            self.assertTrue(build.availability()[key], key)
            plan = build.BuildPlan('s', 't', **{key: True})
            self.assertEqual(plan.wants_xbe_patch(), key not in ('team_names_2026', 'hires_pack'))

    def test_invalid_switches_and_hires_modes_preserve_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory)/'source.xbe', Path(directory)/'output.xbe'
            source.write_bytes(b'invalid input'); target.write_bytes(b'KEEP')
            for key in FLAGS:
                with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'boolean'):
                    build.build(build.BuildPlan(str(source), str(target), overwrite=True, **{key: 1}))
                self.assertEqual(target.read_bytes(), b'KEEP')
            for kwargs in (dict(hires_scale=True), dict(hires_scale=3),
                           dict(hires_pack=True, hires_target='xemu-128')):
                with self.assertRaises(ValueError):
                    build.build(build.BuildPlan(str(source), str(target), overwrite=True, **kwargs))
                self.assertEqual(target.read_bytes(), b'KEEP')
            for key in set(FLAGS) - {'team_names_2026', 'hires_pack'}:
                with self.assertRaisesRegex(ValueError, 'boolean'):
                    tt.write_xbe_copy(source, target, overwrite=True, **{key: 1})
                self.assertEqual(target.read_bytes(), b'KEEP')

    @patch("mod_editor.core.nfl2k5_disc_extents.validate_image", side_effect=lambda target: {"fixture": True})
    @patch("mod_editor.core.xdvdfs_compact.finish_private",
           side_effect=lambda target, **_: {"output_bytes": Path(target).stat().st_size})
    def test_hires_is_last_and_pre_remap_states_are_not_final_claims(self, _compact, _extents):
        # ig: sd2's final extent gate reads the image's XDVDFS tree; this marker-text fixture has none.
        # This ordering fixture writes marker text in place of a disc image.
        from mod_editor.core import nfl2k5_hires_pack as hires
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            source, target = Path(directory)/'source.iso', Path(directory)/'output.iso'
            source.write_bytes(b'source'); events = []
            stack.enter_context(patch.object(tt, 'is_disc_image', return_value=True))
            def inspect(path, **kw):
                events.append('inspect')
                self.assertEqual(Path(path).read_bytes(), b'source')
                return dict(path=str(path), container='xiso', scorebug='retail', hires_pack='retail')
            stack.enter_context(patch.object(build, 'inspect', new=inspect))
            stack.enter_context(patch.object(hires, 'preflight_budget', return_value={'whole_game_fit_proved':False}))
            stack.enter_context(patch.object(hires, 'inspect_image', return_value={'assets':[{'key':'helmet','family':'helmets'}]}))
            def compile(source, output, folder, **kw):
                events.append('hires')
                Path(output).write_bytes(b'final remapped archive')
                return {'verification': {'status':'verified', 'output_sha256':hashlib.sha256(b'final remapped archive').hexdigest()}}
            stack.enter_context(patch.object(hires, 'build_image', new=compile))
            def scoring(path, progress):
                events.append('scoring')
                self.assertEqual(Path(path).read_bytes(), b'final remapped archive')
                return {'status':'applied','books':37,'faults':0}
            stack.enter_context(patch.object(build, '_check_playbook_scoring', side_effect=scoring))
            receipt = build.build(build.BuildPlan(str(source), str(target), hires_pack=True, hires_folder='art'))
            self.assertEqual(events, ['inspect', 'hires', 'scoring'])
            self.assertEqual([s['step'] for s in receipt['steps']], ['copy', 'hires_pack'])
            self.assertEqual(receipt['pre_remap_inspection']['scorebug'], 'retail')
            self.assertNotIn('scorebug', receipt['result'])
            self.assertEqual(receipt['result']['hires_pack'], 'verified')
            self.assertEqual(receipt['result']['image_sha256'], hashlib.sha256(target.read_bytes()).hexdigest())
            self.assertEqual(receipt['result']['image_size'], target.stat().st_size)
            self.assertEqual(source.read_bytes(), b'source')
            target.write_bytes(b'previous output')
            with patch.object(hires, 'build_image', side_effect=ValueError('injected final failure')):
                with self.assertRaisesRegex(ValueError, 'injected final failure'):
                    build.build(build.BuildPlan(str(source), str(target), overwrite=True, hires_pack=True, hires_folder='art'))
            self.assertEqual(target.read_bytes(), b'previous output')

    def test_scorebug_hires_conflict_refuses_before_copy(self):
        from mod_editor.core import nfl2k5_hires_pack as hires
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            source, target = Path(directory)/'source.iso', Path(directory)/'output.iso'
            source.write_bytes(b'source')
            stack.enter_context(patch.object(tt, 'is_disc_image', return_value=True))
            stack.enter_context(patch.object(hires, 'preflight_budget', return_value={'whole_game_fit_proved':False}))
            stack.enter_context(patch.object(hires, 'inspect_image', return_value={'assets':[{'key':'renamed_art', 'family':'scorebug'}]}))
            stack.enter_context(patch.object(shutil, 'copyfile', side_effect=AssertionError('copied before preflight')))
            for flag in ('scorebug', 'scorebug_runtime'):
                with self.assertRaisesRegex(ValueError, 'conflicts'):
                    build.build(build.BuildPlan(str(source), str(target), hires_pack=True, hires_folder='art', **{flag:True}))
                self.assertFalse(target.exists())

    def test_grouped_names_follow_roster_edits_and_refuse_manual_conflict(self):
        from mod_editor.core import nfl2k5_roster_records as records
        from tests.mod_editor.test_nfl2k5_team_names_2026 import synthetic_resource
        from nfl2k5_xiso_fixture import SyntheticXiso
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            fixture = SyntheticXiso(root, [(100+i,b'DUMY'+bytes(256)) for i in range(5)]+
                                    [(5,synthetic_resource()), (200,b'TAIL'+bytes(256))],
                                    pack_sizes=(0xA0000,), pack_sectors=(96,))
            stack.enter_context(patch.object(build, 'inspect', return_value={'path':'unused', 'container':'xiso'}))
            # The synthetic image has no executable: the XBE key paths are proved on the retail XBE in
            # test_nfl2k5_team_names_2026; here a stand-in records that the step installs them once.
            xbe = {'state': 'retail'}
            stack.enter_context(patch.object(build, '_xbe_bytes', side_effect=lambda path: b'XBE-' + xbe['state'].encode()))
            stack.enter_context(patch.object(build, '_write_xbe_bytes', side_effect=lambda path, data: xbe.update(state=data[4:].decode())))
            stack.enter_context(patch.object(names, 'xbe_status', side_effect=lambda data: data[4:].decode()))
            stack.enter_context(patch.object(names, 'apply_xbe', side_effect=lambda data: (b'XBE-applied', {'status': 'applied'})))
            def roster_edits(path, *args, **kwargs):
                self.assertEqual(names.image_status(path), 'retail')
                return {'log':[]}
            stack.enter_context(patch.object(records, 'apply', new=roster_edits))
            target = root/'built.iso'
            edits_path = root/'edits.json'
            edits_path.write_text(json.dumps({'schema': records.EDITS_SCHEMA, 'edits': []}), encoding='utf-8')
            receipt = build.build(build.BuildPlan(str(fixture.path),str(target),team_names_2026=True,roster_edits=str(edits_path)))
            self.assertEqual([r['step'] for r in receipt['steps']], ['copy','roster_edits','team_names_2026'])
            self.assertEqual(names.image_status(target), 'applied')
            # u3: five teams' runs plus Washington's old label nickname; the XBE key paths installed once.
            self.assertEqual(len(receipt['steps'][-1]['runs']), 6)
            self.assertEqual([t['team'] for t in receipt['steps'][-1]['teams']], [7, 8, 22, 23, 25])
            self.assertEqual((receipt['steps'][-1]['xbe']['status'], xbe['state']), ('applied', 'applied'))
            self.assertEqual(names.image_status(fixture.path), 'retail')
            def conflicting(path, *args, **kwargs):
                with records._outer_image()(path) as archive:
                    entry = archive.entries[5]
                    block = names.manifest()['blocks'][0]
                    archive.write(entry.virtual_offset+32+block['start'], b'X\0')
                return {'log':[]}
            xbe['state'] = 'retail'
            target.write_bytes(b'preserve previous')
            with patch.object(records, 'apply', new=conflicting), self.assertRaises(ValueError):
                build.build(build.BuildPlan(str(fixture.path),str(target),overwrite=True,team_names_2026=True,roster_edits=str(edits_path)))
            self.assertEqual(target.read_bytes(), b'preserve previous')


@unittest.skipUnless(RETAIL.is_file(), 'pinned USA retail executable absent')
class ExecutableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()

    def test_complete_request_union_and_four_status_returns(self):
        union = tt._selected_space_requests(True, True, 100, True, True, True, True, True, True, True, True, True, True)
        self.assertEqual(set(union), set(REQUESTS))
        options = {**GROWN, 'calendar_engine':True, 'season_cap':True, 'flatter_deep_ball':True, 'chop_block_toggle':True, 'settings':tt.TuningSettings(80)}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for image in (False, True):
                source, target = root/('source.iso' if image else 'source.xbe'), root/('out.iso' if image else 'out.xbe')
                source.write_bytes(image_with_xbe(self.retail) if image else self.retail)
                original=hashlib.sha256(source.read_bytes()).hexdigest()
                result = (tt.write_image_copy if image else tt.write_xbe_copy)(source,target,**options)
                report = tt.read_any(target)
                for key in ('all_stadiums','coverage_slider','scramble_tuning','flatter_deep_ball','chop_block_toggle','music_shuffle','practice_squad_screen','abilities','qb_spy','calendar_engine'):
                    self.assertEqual((result[key],report[key]), ('applied','applied'),key)
                    self.assertIn(key+'_patch',result)
                self.assertIn('chop_block_evidence',report)
                self.assertEqual(report['settings'],tt.TuningSettings(80))
                payload = build._xbe_bytes(target)
                self.assertTrue(tt.xbe_space_patch.is_scaleout(payload))
                self.assertEqual(tt._apply_all(payload,None,False,**GROWN,calendar_engine=True,season_cap=True,flatter_deep_ball=True,chop_block_toggle=True)[0],payload)
                self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),original)

    def test_runtime_scorebug_reserves_all_owners_before_final_install(self):
        from mod_editor.core import nfl2k5_scorebug_runtime as runtime
        from mod_editor.core import nfl2k5_scorebug_ingame as ingame
        from mod_editor.core import nfl2k5_dynamic_kickoff_relocated as kickoff
        from mod_editor.core import nfl2k5_xbe_space as space
        events = []
        def resources(image, *, with_kickoff=False, extra_requests=(), scorebug_folder=None, widescreen=False, **_kwargs):
            events.append('runtime')
            before = build._xbe_bytes(Path(image))
            for key in ('all_stadiums','coverage_slider','scramble_tuning','music_shuffle','practice_squad_screen','abilities','qb_spy'):
                self.assertEqual(tt._grown_status_fields(before)[key], 'retail')
            requested = tuple(runtime.REQUESTS) + tuple(extra_requests) + (tuple(kickoff.REQUESTS) if with_kickoff else ())
            from mod_editor.core import nfl2k5_calendar_engine as calendar
            self.assertEqual(set(requested), set(REQUESTS) - set(calendar.REQUESTS))  # the calendar needs the 2026 templates, absent on a synthetic disc
            grown, rec = space.apply(before, requested)
            grown, _ = runtime.apply(grown)
            if with_kickoff:
                grown, _ = kickoff.apply(grown)
            build._write_xbe_bytes(Path(image), grown)
            return rec
        def validate_playlist(image, *, expected):
            # This fixture owns only an XBE. Validate its actual installed table;
            # descriptor/archive geometry is covered by the Music owner suite.
            state, selected = tt.music_playlist_patch._inspect(build._xbe_bytes(image))
            self.assertEqual(state, 'applied')
            self.assertEqual(selected, tt.music_playlist_patch.from_options(expected))
            tt.music_playlist_patch.validate_source(selected, tt.music_playlist_patch.BANK_COUNTS)
            return {'installed':True, 'revalidated_after_rebuild':True}
        with tempfile.TemporaryDirectory() as directory, patch.object(ingame,'runtime_apply_in_place',new=resources), patch.object(
                build._core_module('nfl2k5_music_banks'), 'read_descriptor_counts', return_value=tt.music_playlist_patch.BANK_COUNTS), patch.object(
                build._core_module('nfl2k5_music_banks'), 'revalidate_playlist', side_effect=validate_playlist):
            source=Path(directory)/'source.iso'
            source.write_bytes(image_with_xbe(self.retail))
            for writer in ('dispatcher','build'):
                target=Path(directory)/(writer+'.iso')
                if writer == 'dispatcher':
                    result=tt.write_image_copy(source,target,scorebug_runtime=True,kickoff_relocated=True,**GROWN)
                else:
                    with patch.object(build,'inspect',return_value={'container':'xiso'}), patch.object(
                            build._tools_module('nfl2k5_kickoff_alignment'), 'apply', return_value={'status':'applied','kicker_depth_yd':5,'changed_bytes':0,'books':[]}), patch.object(
                            build._tools_module('nfl2k5_kickoff_returns'), 'apply', return_value={'status':'applied','changed_bytes':0,'books':[]}), patch.object(
                            build, '_check_playbook_menus', return_value=None), patch.object(
                            build, '_check_playbook_scoring', return_value={'status':'applied','books':0,'faults':0}):  # Synthetic image has no PLAY archive; both real gates are covered with retail resources separately.
                        result=build.build(build.BuildPlan(str(source),str(target),scorebug_runtime=True,
                                                           kickoff_relocated=True,**GROWN))
                    self.assertEqual([row['step'] for row in result['steps']], ['xbe','kickoff_alignment','kickoff_returns','scorebug_runtime','xbe_space'])  # the plan wants XBE work, so the ordinary XBE pass (grown owners deferred) runs first
                final=build._xbe_bytes(target)
                for key in ('all_stadiums','coverage_slider','scramble_tuning','music_shuffle','practice_squad_screen','abilities','qb_spy'):
                    self.assertEqual(tt._grown_status_fields(final)[key], 'applied')
                self.assertEqual(runtime.status(final), 'applied')
                self.assertEqual(len(final), space.SCALE_FILE_SIZE)
            self.assertEqual(events,['runtime','runtime'])

    def test_flatter_flight_preserves_ceiling_and_refuses_other_flight_before_overwrite(self):
        flat = tt._apply_all(self.retail,tt.curves_for(tt.TuningSettings(80)),False,flatter_deep_ball=True)[0]
        changed = tt._apply_all(flat,tt.curves_for(tt.TuningSettings(90)),False,flatter_deep_ball=True)[0]
        self.assertEqual(tt.flatter_flight_patch.status(changed),'applied')
        self.assertEqual(tt._apply_all(changed,tt.curves_for(tt.TuningSettings(90)),False,flatter_deep_ball=True)[0],changed)
        with tempfile.TemporaryDirectory() as directory:
            source,target=Path(directory)/'source.xbe',Path(directory)/'output.xbe'
            for settings in (tt.TuningSettings(80,arc=.5),tt.TuningSettings(80,realistic_flight=True),tt.TuningSettings(80,arc_by_distance=True)):
                source.write_bytes(self.retail);target.write_bytes(b'KEEP')
                with self.assertRaisesRegex(ValueError,'one flight'):
                    tt.write_xbe_copy(source,target,overwrite=True,settings=settings,flatter_deep_ball=True)
                self.assertEqual(target.read_bytes(),b'KEEP')
            source.write_bytes(tt.apply_arc_table(self.retail)[0])
            with self.assertRaisesRegex(ValueError,'original source'):
                tt.write_xbe_copy(source,target,overwrite=True,flatter_deep_ball=True)
            self.assertEqual(target.read_bytes(),b'KEEP')


if __name__ == '__main__':
    unittest.main()

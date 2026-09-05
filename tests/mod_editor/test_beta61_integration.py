"""Integration boundaries: ordering, selected owner replay and atomic publication."""
from dataclasses import replace
from pathlib import Path
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import mod_build as build
from mod_editor.core import nfl2k5_throw_tuning as tt


class BuildIntegrationTests(unittest.TestCase):
    def test_presets_reset_policy_and_runtime_without_replacing_personal_inputs(self):
        plan = build.BuildPlan('source', 'target', music_policy='jukebox_menus', music_unlock=True,
                               music_userlist=True, music_library='mine.json', music_project='mine.2k5music')
        for name in build.PRESETS:
            selected = build.apply_preset(plan, name)
            self.assertEqual((selected.music_policy, selected.music_unlock, selected.music_userlist),
                             ('retail', False, False))
            self.assertEqual((selected.music_library, selected.music_project), ('mine.json', 'mine.2k5music'))
            self.assertEqual(selected.scorebug, name == 'softdrink_experimental')
            self.assertEqual(selected.scorebug_runtime, name == 'softdrink_experimental')
            self.assertEqual(build.BuildPlan('source', 'target', **selected.to_recipe()).to_recipe(), selected.to_recipe())

    def test_library_metadata_is_a_selected_content_transaction(self):
        with tempfile.TemporaryDirectory() as folder:
            recipe = Path(folder) / 'music.json'
            for bank in ('femusic', 'cribmusic'):
                recipe.write_text(json.dumps({'schema':'nfl2k5_music_library/v1','bank':bank,
                                               'tracks':[{'source_index':0}]}), newline='\n')
                plan = build.BuildPlan('source', 'target', music_library=str(recipe))
                self.assertEqual(plan.wants_xbe_patch(), bank == 'cribmusic')

    def test_runtime_then_library_replans_on_intermediate_and_publishes_once(self):
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as folder:
                root = Path(folder); source = root / 'source.iso'; target = root / 'target.iso'
                source.write_bytes(b'original'); target.write_bytes(b'previous output')
                planned = []
                def plan(path, recipe):
                    snapshot = Path(path).read_bytes(); planned.append(snapshot)
                    return {'source_bytes':snapshot, 'layout':{'image_size':32}, 'scratch_bytes':64}
                def runtime(path, *, with_kickoff):
                    self.assertFalse(with_kickoff)
                    Path(path).write_bytes(Path(path).read_bytes() + b' runtime')
                    return {'status':'applied', 'requires_resources':False}
                def rebuild(source, destination, recipe, *, expected_plan, progress):
                    self.assertEqual(Path(source).read_bytes(), expected_plan['source_bytes'])
                    Path(destination).write_bytes(Path(source).read_bytes() + b' music')
                    if fail:
                        raise ValueError('cancelled during music rebuild')
                    return {'status':'applied', 'source_sha256':'intermediate', 'runtime_witnessed':False}
                modules = {'nfl2k5_music_banks':SimpleNamespace(plan=plan,rebuild=rebuild),
                           'nfl2k5_scorebug_ingame':SimpleNamespace(runtime_apply_in_place=runtime)}
                selected = build.BuildPlan(str(source), str(target), overwrite=True,
                                            scorebug_runtime=True, music_library='recipe.json')
                with patch.object(build, '_core_module', side_effect=modules.get), patch.object(tt, 'is_disc_image', return_value=True), \
                        patch.object(build, 'inspect', side_effect=lambda p, **k:{'path':str(p)}), \
                        patch.object(build, '_identity_note', return_value=''):
                    if fail:
                        with self.assertRaisesRegex(ValueError, 'cancelled'):
                            build.build(selected)
                        self.assertEqual(target.read_bytes(), b'previous output')
                    else:
                        receipt = build.build(selected)
                        self.assertEqual(target.read_bytes(), b'original runtime music')
                        self.assertEqual([r['step'] for r in receipt['steps']], ['copy','scorebug_runtime','music_library'])
                        self.assertEqual(receipt['source'], str(source))
                        self.assertTrue(receipt['plan']['scorebug'] and receipt['plan']['xbe_space'])
                    self.assertEqual(planned, [b'original', b'original runtime'])
                    self.assertEqual(source.read_bytes(), b'original')
                    self.assertEqual(set(root.iterdir()), {source,target})

    def test_invalid_policy_refuses_before_copy(self):
        for values in ({'music_policy':True},{'music_unlock':1},{'music_userlist':True}):
            with self.subTest(values=values), tempfile.TemporaryDirectory() as folder:
                source=Path(folder)/'source.xbe';source.write_bytes(b'XBEH')
                target=Path(folder)/'target.xbe'
                with self.assertRaises(ValueError):
                    build.build(build.BuildPlan(str(source),str(target),**values))
                self.assertFalse(target.exists())


RETAIL = Path('/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe')

@unittest.skipUnless(RETAIL.is_file(), 'private retail XBE unavailable')
class ComposedMusicTests(unittest.TestCase):
    def test_metadata_and_policy_orders_and_exact_replay(self):
        from mod_editor.core import nfl2k5_music_metadata as metadata, nfl2k5_music_policy as policy
        original=RETAIL.read_bytes()
        records=[dict(title=f'Tone {i}',artist='Synthetic',frames=256) for i in range(200)]
        first,_=tt._apply_all(original,None,catch_slider=False,music_unlock=True)
        first,_=tt._apply_all(first,None,catch_slider=False,music_policy='jukebox_menus',music_userlist=True,
                              music_metadata=records)
        other,_=metadata.apply(original,records)
        other,_=tt._apply_all(other,None,catch_slider=False,music_policy='jukebox_menus',music_unlock=True,music_userlist=True)
        self.assertEqual(first,other)
        self.assertEqual(policy.read_any(first)['music_policy'],'applied')
        self.assertEqual(metadata.status(first),'applied')
        self.assertEqual(tt._apply_all(first,None,catch_slider=False,music_metadata=records)[0],first)
        with self.assertRaisesRegex(ValueError,'different jukebox recipe'):
            tt._apply_all(first,None,catch_slider=False,music_metadata=[{**r,'title':'Changed'} for r in records])


if __name__ == '__main__':
    unittest.main()

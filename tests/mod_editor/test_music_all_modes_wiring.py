"""Exercise the protected-file handoff in memory; never edit protected files.

Full Studio construction needs unrelated reports/assets. Real Playlist and Build
widgets are connected to the proposed Studio methods on a small host instead.
"""
import ast
import copy
import os
from pathlib import Path
import re
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import mod_build, nfl2k5_music_playlist as playlist
from tests.mod_editor.test_nfl2k5_music_playlist_library import options

try:
    from PyQt5.QtWidgets import QApplication
    from mod_editor.gui.music_panel_qt import MusicPanel
except ImportError:
    QApplication = None


def proposed_sources():
    # The reviewed handoff is installed. Exercise the live functions even when
    # later integration changes move their line numbers or surrounding context.
    paths = ("mod_editor/core/mod_build.py", "mod_editor/gui/build_panel_qt.py",
             "mod_editor/gui/studio_qt.py")
    result = {path: (ROOT / path).read_text(encoding="utf-8") for path in paths}
    for path, source in result.items():
        compile(source, path, "exec")
    return result


def functions(source, names):
    nodes = [node for node in ast.walk(ast.parse(source))
             if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {n.name for n in nodes} == set(names)
    return compile(ast.Module(body=nodes, type_ignores=[]), '<protected handoff>', 'exec')


class PublicationHandoffTests(unittest.TestCase):
    def test_final_private_image_checked_before_replace_and_failure_preserves_target(self):
        source = proposed_sources()['mod_editor/core/mod_build.py']
        namespace = dict(vars(mod_build))
        exec(functions(source, {'build'}), namespace)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            original, target = root/'source.iso', root/'result.iso'
            original.write_bytes(b'source'); target.write_bytes(b'previous')
            value = options({('cribmusic',199)})
            plan = mod_build.BuildPlan(source=str(original), target=str(target), overwrite=True,
                                       music_shuffle=True, music_shuffle_selection=value)
            checked = dict(installed=True, revalidated_after_rebuild=True,
                           descriptor_counts={'cribmusic':200}, records=1, enabled=1)
            def build_private(plan, *args, **kwargs):
                Path(plan.target).write_bytes(b'final after all edits')
                return dict(steps=[dict(music_shuffle_preflight={'revalidated_after_rebuild':False})], result={})
            def validate(private, *, expected):
                self.assertEqual(target.read_bytes(), b'previous')
                self.assertNotEqual(private, target)
                self.assertEqual(private.read_bytes(), b'final after all edits')
                self.assertEqual(expected, value)
                return checked
            library = types.SimpleNamespace(revalidate_playlist=Mock(side_effect=validate))
            namespace.update(_build=build_private, _core_module=lambda name:library,
                             _with_identity=lambda exc,*args:exc)
            receipt = namespace['build'](plan)
            self.assertEqual(target.read_bytes(), b'final after all edits')
            self.assertEqual(receipt['music_shuffle_validation'], checked)
            self.assertTrue(receipt['steps'][0]['music_shuffle_preflight']['revalidated_after_rebuild'])
            target.write_bytes(b'previous')
            library.revalidate_playlist.side_effect = ValueError('invalid final descriptors')
            with self.assertRaisesRegex(ValueError, 'invalid final'):
                namespace['build'](plan)
            self.assertEqual(target.read_bytes(), b'previous')
            self.assertEqual(original.read_bytes(), b'source')
            self.assertEqual(sorted(p.name for p in root.iterdir()), ['result.iso','source.iso'])


@unittest.skipUnless(QApplication is not None, 'PyQt5 absent; offscreen handoff tests unavailable')
class WidgetHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        sources = proposed_sources()
        module = types.ModuleType('mod_editor.gui._music_wiring_test')
        module.__package__ = 'mod_editor.gui'
        module.__file__ = str(ROOT/'mod_editor/gui/build_panel_qt.py')
        sys.modules[module.__name__] = module
        exec(compile(sources['mod_editor/gui/build_panel_qt.py'], module.__file__, 'exec'), vars(module))
        cls.BuildPanel = module.BuildPanel
        methods = {'_music_playlist_changed', '_capture_music_build_settings', '_restore_music_build_settings',
                   '_build_music_shuffle_changed', '_music_library_preview_ready', '_music_changed'}
        namespace = {}
        exec(functions(sources['mod_editor/gui/studio_qt.py'], methods), namespace)
        cls.Host = type('Host', (), {name:namespace[name] for name in methods})

    def panel(self):
        panel = self.BuildPanel()
        self.addCleanup(panel.deleteLater)
        state = {key:'retail' for key in panel._boxes()}
        state.update(path='retail.iso', container='xiso', throw=None)
        panel.apply_state(state)
        return panel

    def test_build_settings_detach_validate_and_reach_plan_as_json(self):
        panel = self.panel()
        value = options({('cribmusic',199)})
        panel.set_music_shuffle_selection(value)
        value['catalog'][0]['title'] = 'caller changed'
        state = panel.music_build_settings()
        self.assertNotEqual(state['music_shuffle_selection'], value)
        self.assertIsInstance(panel.plan().music_shuffle_selection, dict)
        self.assertEqual(playlist.from_options(panel.plan().music_shuffle_selection).records, (('cribmusic',199),))
        bad = copy.deepcopy(state); bad['music_shuffle_selection']['checked'] = [9999]
        with self.assertRaises(ValueError): panel.restore_music_build_settings(bad)
        self.assertEqual(panel.music_build_settings(), state)
        panel.restore_music_build_settings({})
        self.assertFalse(panel.music_shuffle_check.isChecked())
        self.assertIsNone(panel.plan().music_shuffle_selection)

    def test_only_current_preview_with_counts_updates_playlist(self):
        panel = self.panel()
        panel.music_library_field.setText('library.json')
        panel._music_preview_identity = ('retail.iso', 'library.json')
        result = dict(layout={'image_size':1200}, scratch_bytes=1600, source_size=1000)
        observed = []
        panel.music_library_preview_ready.connect(lambda counts,preview:observed.append((counts,preview)))
        panel._music_preview_done(result)
        self.assertEqual(observed, [])
        self.assertIn('2,600 bytes', panel.music_preview_label.text())
        result['source_descriptor_counts'] = dict(playlist.BANK_COUNTS)
        panel._music_preview_done(result)
        self.assertEqual(observed, [(playlist.BANK_COUNTS,result)])
        panel.music_library_field.setText('changed.json')
        panel._music_preview_done(result)
        self.assertEqual(len(observed),1)
        self.assertIn('Preview again',panel.music_preview_label.text())

    def test_lazy_pages_save_restore_and_toggle_do_not_overwrite_project(self):
        host = self.Host()
        host._music_panel = host._build_panel = None
        host._music_playlist_document = host._music_playlist_catalog = None
        host._restoring_music_playlist = False
        host._music_policy_values = {}  # beta 66: the studio keeps the policy choices beside the playlist
        host._sync_uniform_helmet_finish = lambda: None  # beta 66: the studio mirrors the helmet finish after quiet restores
        host._mark_workspace_changed = Mock()
        host.statusBar = lambda:types.SimpleNamespace(showMessage=Mock())
        state = {}
        def save(value):
            # The project file carries every Build choice since the Discord bug batch (B22),
            # so the fake facade validates the complete map like the real one does.
            from mod_editor.core import nfl2k5_build_settings as saved
            state.clear(); state.update(saved.build_settings(value))
        host.facade = types.SimpleNamespace(source_ready=True, modified_count=0,
            project_build_settings=lambda:copy.deepcopy(state), set_project_build_settings=save)
        value = options({('femusic',199),('cribmusic',198)})
        host._music_playlist_changed(value)  # Music changes survive lazy Build creation.
        self.assertEqual(state['music_shuffle_selection'], value)
        host._build_panel = self.panel()
        host._build_panel.music_shuffle_check.toggled.connect(host._build_music_shuffle_changed)
        host._music_panel = MusicPanel(None)
        self.addCleanup(host._music_panel.deleteLater)
        host._music_panel.playlist_changed.connect(host._music_playlist_changed)
        host._music_panel.changed.connect(host._music_changed)
        host._music_playlist_catalog = value['catalog']
        host._mark_workspace_changed.reset_mock()
        host._restore_music_build_settings()
        self.assertEqual(host._music_panel.playlist_options(), value)
        self.assertEqual(state['music_shuffle_selection'], value)
        host._mark_workspace_changed.assert_not_called()
        host._build_panel.music_shuffle_check.setChecked(False)
        self.assertFalse(state['music_shuffle'])
        self.assertFalse(host._music_panel.playlist_options()['music_shuffle'])
        self.assertEqual(state['music_shuffle_selection']['records'], value['records'])
        state.clear()  # Opening an old project cannot inherit the last project's choices.
        host._restore_music_build_settings()
        self.assertFalse(host._build_panel.music_shuffle_check.isChecked())
        self.assertIsNone(host._build_panel.music_build_settings()['music_shuffle_selection'])
        self.assertEqual(host._music_panel.playlist_page.selected().records, playlist.CORE)
        self.assertEqual(state, {})


if __name__ == '__main__': unittest.main()

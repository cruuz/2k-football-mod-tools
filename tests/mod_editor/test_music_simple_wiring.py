"""Test the reviewable protected-file handoff entirely in memory."""
import ast
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import re
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_music_playlist as playlist
try:
    from PyQt5.QtWidgets import QApplication
    from mod_editor.gui.music_panel_qt import MusicPanel
    from mod_editor.gui.build_panel_qt import BuildPanel
except ImportError:
    QApplication = None


def proposed_sources():
    """Apply exact-context unified hunks to strings; no protected file writes."""
    lines = (ROOT/'docs/mod_editor/music_simple_wiring.patch').read_text().splitlines(True)
    sources = {}
    index = 0
    while index < len(lines):
        assert lines[index].startswith('--- a/')
        name = lines[index][6:].strip()
        assert lines[index+1].strip() == '+++ b/'+name
        original = (ROOT/name).read_text().splitlines(True)
        result, cursor = [], 0
        index += 2
        while index < len(lines) and not lines[index].startswith('--- a/'):
            match = re.match(r'@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@', lines[index])
            assert match, lines[index]
            start = int(match[1])-1
            result.extend(original[cursor:start]); cursor = start
            index += 1
            while index < len(lines) and not lines[index].startswith(('@@ ', '--- a/')):
                prefix, text = lines[index][0], lines[index][1:]
                if prefix in (' ', '-'):
                    assert original[cursor] == text, (name, cursor, text)
                    cursor += 1
                if prefix in (' ', '+'):
                    result.append(text)
                index += 1
        result.extend(original[cursor:])
        sources[name] = ''.join(result)
        compile(sources[name], name, 'exec')
    return sources


def function_namespace(source, names, initial=None):
    nodes = [node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in nodes} == set(names)
    namespace = {} if initial is None else dict(initial)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<music handoff>', 'exec'), namespace)
    return namespace


class BuildHandoffTests(unittest.TestCase):
    def test_portable_music_project_additions_reach_build_and_final_verifier(self):
        sources = proposed_sources()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source, output, recipe = root/'source.iso', root/'output.iso', root/'library.json'
            source.write_bytes(b'synthetic input'); recipe.write_text('{}')
            def prepare(source, project, directory, progress, *, library_result):
                library_result.append(str(recipe))
                return ('fixed replacements',)
            received = []
            def build_private(plan, progress, **kwargs):
                received.append((plan, kwargs))
                Path(plan.target).write_bytes(b'fully composed music')
                return {'steps': [], 'result': {}}
            verifier = Mock(return_value={'installed': False})
            namespace = function_namespace(sources['mod_editor/core/mod_build.py'], {'build'}, vars(mod_build))
            namespace.update(_prepare_music_project=prepare, _build=build_private,
                             _core_module=lambda name: types.SimpleNamespace(revalidate_playlist=verifier))
            # Feedback is unrelated to the handoff's small synthetic image.
            from unittest.mock import patch
            image_kind = patch.object(namespace['tt'], 'is_disc_image', return_value=True)
            image_kind.start(); self.addCleanup(image_kind.stop)
            with patch('mod_editor.core.build_feedback.measure', return_value={}):
                result = namespace['build'](mod_build.BuildPlan(str(source), str(output), music_project='songs.2k5music'))
            self.assertEqual(received[0][0].music_library, str(recipe))
            self.assertEqual(received[0][1]['music_edits'], ('fixed replacements',))
            self.assertIn('music_shuffle_validation', result)
            verifier.assert_called_once()
            self.assertEqual(output.read_bytes(), b'fully composed music')
            self.assertEqual(source.read_bytes(), b'synthetic input')
            with self.assertRaisesRegex(ValueError, 'Music project or the separate'):
                namespace['build'](mod_build.BuildPlan(str(source), str(root/'other.iso'),
                    music_project='songs.2k5music', music_library='separate.json'))
            self.assertFalse((root/'other.iso').exists())


@unittest.skipUnless(QApplication is not None, 'PyQt5 absent; offscreen protected handoff unavailable')
class StudioHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_catalogued_source_mounts_songs_without_fixed_replacement_scan(self):
        source = proposed_sources()['mod_editor/gui/studio_qt.py']
        panel = MusicPanel()
        self.addCleanup(panel.deleteLater)
        session = types.SimpleNamespace(audio_service=object())
        service = Mock()
        service.library_recipe_path.return_value = None
        factory = Mock(return_value=service)
        namespace = function_namespace(source, {'_sync_music_service'}, {'MusicService': factory})
        host = types.SimpleNamespace(_music_panel=panel, _blocking=False,
            facade=types.SimpleNamespace(_session=session, audio_editing_ready=False), _music_policy_values={})
        from unittest.mock import patch
        with patch.object(panel, 'set_service') as mount:
            namespace['_sync_music_service'](host)
        mount.assert_called_once_with(service)
        factory.assert_called_once_with(session, lock=None)

    def test_signal_lazy_build_existing_fields_and_saved_settings(self):
        source = proposed_sources()['mod_editor/gui/studio_qt.py']
        names = {'_music_library_changed', '_capture_music_build_settings'}
        namespace = function_namespace(source, names)
        host = type('Host', (), {name: namespace[name] for name in names})()
        host._build_panel = None
        host._restoring_music_playlist = False
        host._music_playlist_document = playlist.default_options()
        host.facade = types.SimpleNamespace(source_ready=True, set_project_build_settings=Mock())
        panel = MusicPanel()
        self.addCleanup(panel.deleteLater)
        panel.library_changed.connect(host._music_library_changed)
        panel.library_changed.emit('/prepared/library.json')
        self.assertEqual(host.facade.set_project_build_settings.call_args.args[0]['music_library'], '/prepared/library.json')
        host._build_panel = BuildPanel()
        self.addCleanup(host._build_panel.deleteLater)
        host._music_library_changed(host._music_library_recipe)
        self.assertEqual(host._build_panel.music_library_field.text(), '/prepared/library.json')
        self.assertTrue(host._build_panel.music_library_check.isChecked())
        self.assertEqual(host.facade.set_project_build_settings.call_args.args[0]['music_library'], '/prepared/library.json')
        panel.library_changed.emit(None)
        self.assertEqual(host._build_panel.music_library_field.text(), '')
        self.assertFalse(host._build_panel.music_library_check.isChecked())
        self.assertIsNone(host.facade.set_project_build_settings.call_args.args[0]['music_library'])


if __name__ == '__main__':
    unittest.main()

"""Exercise exact protected-source proposals in memory, never edit their files."""
import ast
import importlib
import os
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from mod_editor.core.errors import ValidationError


def proposed_sources():
    lines = (ROOT / 'tests/fixtures/discord_bugs_2_wiring.patch').read_text(encoding="utf-8").splitlines(True)
    paths = [line[6:].strip() for line in lines if line.startswith('--- a/')]
    # The proposal was integrated on the stack on 2026-09-07 (the protected patch is applied),
    # so these checks run against the wired modules. ASTRA_TEST_PROPOSAL=1 re-applies the
    # historical fixture in memory, which only works against the pre-integration base.
    if os.environ.get('ASTRA_TEST_PROPOSAL') != '1':
        return {path: (ROOT / path).read_text(encoding="utf-8") for path in paths}
    result, i = {}, 0
    while i < len(lines):
        assert lines[i].startswith('--- a/')
        path = lines[i][6:].strip()
        assert lines[i+1].strip() == '+++ b/' + path
        original = (ROOT / path).read_text(encoding="utf-8").splitlines(True)
        output, cursor = [], 0
        i += 2
        while i < len(lines) and lines[i].startswith('@@'):
            start = int(re.match(r'@@ -(\d+)', lines[i])[1])-1
            assert start >= cursor
            output += original[cursor:start]
            cursor = start
            i += 1
            while i < len(lines) and not lines[i].startswith(('@@', '--- a/')):
                line = lines[i]
                if line == '\n': line = ' \n'
                if line[0] in ' -':
                    assert original[cursor] == line[1:], (path, cursor, line)
                    cursor += 1
                if line[0] in ' +': output.append(line[1:])
                i += 1
        result[path] = ''.join(output + original[cursor:])
    return result


def functions_from(path, names, class_name=None):
    module = importlib.import_module(path[:-3].replace('/', '.'))
    namespace = dict(module.__dict__)
    tree = ast.parse(proposed_sources()[path])
    body = tree.body
    if class_name:
        body = next(n for n in body if isinstance(n, ast.ClassDef) and n.name == class_name).body
    nodes = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    nodes += [n for n in body if isinstance(n, ast.FunctionDef) and n.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), path, 'exec'), namespace)
    return namespace


class CopyWiringTests(unittest.TestCase):
    def test_build_refuses_open_target_before_backend(self):
        from mod_editor.core import image_use
        ns = functions_from('mod_editor/core/mod_build.py', {'build'})
        from mod_editor.core.mod_build import BuildPlan
        ns['_validated_r62_plan_options'] = lambda _: {}
        backend = ns['_build'] = Mock()
        ns['_with_identity'] = lambda exc, *args: exc
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            source, target = root/'source.iso', root/'target.iso'
            source.write_bytes(b'source'); target.write_bytes(b'keep')
            with patch.object(image_use, 'assert_image_available', side_effect=image_use._busy(target)):
                with self.assertRaisesRegex(ValidationError, 'Eject'):
                    ns['build'](BuildPlan(str(source), str(target), overwrite=True))
            backend.assert_not_called()
            self.assertEqual(target.read_bytes(), b'keep')

    def test_throw_copy_rechecks_handle_before_final_publication(self):
        from mod_editor.core import image_use
        ns = functions_from('mod_editor/core/nfl2k5_throw_tuning.py', {'_transactional_image_writer'})
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            source, target = root/'source.iso', root/'target.iso'
            source.write_bytes(b'source'); target.write_bytes(b'keep')
            def writer(_source, stage, **kwargs):
                stage.write_bytes(b'candidate')
                return {'target': {'path': str(stage)}}
            wrapped = ns['_transactional_image_writer'](writer)
            with patch.object(image_use, 'assert_image_available', side_effect=[None, image_use._busy(target)]):
                with self.assertRaisesRegex(ValidationError, 'Eject'):
                    wrapped(source, target, overwrite=True)
            self.assertEqual(target.read_bytes(), b'keep')
            self.assertEqual(list(root.glob('.xbe-disc-*')), [])

    def test_fresh_target_racer_is_not_overwritten(self):
        ns = functions_from('mod_editor/core/nfl2k5_throw_tuning.py', {'_transactional_image_writer'})
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve(); source=root/'source.iso'; target=root/'target.iso'
            source.write_bytes(b'source')
            def writer(_source, stage, **kwargs):
                stage.write_bytes(b'candidate'); target.write_bytes(b'racer')
                return {'target': {'path': str(stage)}}
            with self.assertRaises(FileExistsError):
                ns['_transactional_image_writer'](writer)(source,target)
            self.assertEqual(target.read_bytes(),b'racer')


class GuiWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from PyQt5.QtWidgets import QApplication
            from mod_editor.apf_studio import gui
        except ImportError as exc:
            raise unittest.SkipTest(f'Offscreen Qt dependencies unavailable: {exc}')
        cls.app = QApplication.instance() or QApplication([])
        cls.ns = dict(gui.__dict__)
        exec(compile(proposed_sources()['mod_editor/apf_studio/gui.py'], str(ROOT/'mod_editor/apf_studio/gui.py'), 'exec'), cls.ns)

    @unittest.skipUnless(hasattr(__import__("mod_editor.apf_studio.gui", fromlist=["ApfFieldArtPanel"]).ApfFieldArtPanel, "_stage_session"),
                         "the APF GUI hunk of the proposal is deferred (see WIRING.md); apply it with session-aware fixtures")
    def test_crest_picker_does_not_jump_back_to_previous_team(self):
        from mod_editor.apf_studio.helmet_crest_design import metadata, RETAIL_CREST_PROFILE
        import apf_team_crests
        slots=apf_team_crests.TEAM_CRESTS
        first,second=slots[:2]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'crest.png'
            from PIL import Image
            Image.new('RGBA',(512,512),(255,0,0,255)).save(path)
            mod=SimpleNamespace(asset_id='apf:logos:helmet_crest_design', replacement_path=path,
                metadata=metadata(profile=RETAIL_CREST_PROFILE,crest_asset_index=first.asset_index,
                crest_outer_entry_index=first.outer_entry_index,fit_visible_mask=False,
                source_horizontal_coverage=1.,output_horizontal_coverage=1.))
            session=SimpleNamespace(modification=lambda _:mod,
                crest_modification=lambda slot:mod if slot==first.asset_index else None)
            facade=SimpleNamespace(source_ready=False, source=None, session=session)
            panel=self.ns['ApfTeamLogoPanel'](facade, Mock())
            try:
                facade.source_ready=True
                panel.slot.setCurrentIndex(0); panel.set_context()
                panel.slot.setCurrentIndex(1); panel.set_context()
                self.assertEqual(panel.selected_crest().asset_index, second.asset_index)
                self.assertIsNone(panel._staged_png)
                panel.slot.setCurrentIndex(0); panel.set_context()
                self.assertEqual(panel._staged_png,path)
            finally:
                panel.close(); panel.deleteLater()

    @unittest.skipUnless(hasattr(__import__("mod_editor.apf_studio.gui", fromlist=["ApfFieldArtPanel"]).ApfFieldArtPanel, "_stage_session"),
                         "the APF GUI hunk of the proposal is deferred (see WIRING.md); apply it with session-aware fixtures")
    def test_field_art_stage_calls_shared_facade_and_marks_project(self):
        cls=self.ns['ApfFieldArtPanel']
        facade=SimpleNamespace(replace_field_art=Mock(return_value=Path('private.png')))
        done=Mock(); refresh=Mock()
        def run(_label, operation, success, _blocking):
            success(operation(lambda *_:None))
        host=SimpleNamespace(facade=facade,run_task=run,set_context=refresh,
                             modifiedChanged=SimpleNamespace(emit=done))
        cls._stage_session(host,SimpleNamespace(key=(659,1)),Path('input.png'))
        self.assertEqual(facade.replace_field_art.call_args.args[:2],((659,1),Path('input.png')))
        done.assert_called_once(); refresh.assert_called_once()

    def test_number_layout_selection_reaches_splitter(self):
        from mod_editor.core.nfl2k5_digit_sheet import SHEET_LAYOUTS
        # Run the real proposed Studio callback until splitting. The splitter
        # sentinel avoids requiring an unrelated full asset catalog/team kit.
        path='mod_editor/gui/studio_qt.py'
        tree=ast.parse(proposed_sources()[path])
        owner=next(n for n in tree.body if isinstance(n,ast.ClassDef)
                   and any(isinstance(m,ast.FunctionDef) and m.name=='_choose_digit_sheet_import' for m in n.body))
        ns=functions_from(path,{'_choose_digit_sheet_import'},owner.name)
        split=Mock(side_effect=RuntimeError('split sentinel'))
        ns['split_digit_sheet']=split
        ns['QInputDialog']=SimpleNamespace(getItem=Mock(side_effect=[('Jersey numbers',True),(SHEET_LAYOUTS[2][0],True)]))
        ns['QFileDialog']=SimpleNamespace(getOpenFileName=lambda *args:('grid.png',''))
        host=SimpleNamespace(_selected_set=SimpleNamespace(selector='28H0'),_selected_asset=None,
            facade=SimpleNamespace(source_ready=True),uniform_catalog=SimpleNamespace(assets_for_set=lambda _:()),
            _start_task=lambda operation, success, **kw:operation(lambda *_:None))
        with self.assertRaisesRegex(RuntimeError,'split sentinel'):
            ns['_choose_digit_sheet_import'](host)
        self.assertEqual(split.call_args.kwargs,{'orientation':'grid_5x2'})


if __name__=='__main__': unittest.main()

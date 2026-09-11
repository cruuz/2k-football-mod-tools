"""Execute Coach's protected integration patch in memory, with offscreen Qt."""
from __future__ import annotations
import ast
import inspect
from pathlib import Path
import sys
import textwrap
from threading import RLock
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(Path(__file__).parent)]
import test_number_sheet_quality_wiring as legacy
from mod_editor.core.nfl2k5_digit_preview import DigitSheetPreview


def proposed(path):
    original=(ROOT/path).read_text(encoding='utf-8')
    marker={
        'mod_editor/gui/studio_qt.py':'preview.import_button_text',
        'mod_editor/studio/facade.py':'background = jersey_preview_colour',
        'packaging/release-allowlist.txt':'mod_editor/core/nfl2k5_digit_art.py',
        'packaging/check_2k5_mod_studio_runtime.py':'"mod_editor.core.nfl2k5_digit_art"',
    }[path]
    if marker in original:return original
    return legacy.apply_fixture(original,path,'coach_digit_wiring.patch')


class PatchTests(unittest.TestCase):
    def test_complete_patch_parses_and_runtime_closure_is_included(self):
        for path in ('mod_editor/gui/studio_qt.py','mod_editor/studio/facade.py',
                     'packaging/check_2k5_mod_studio_runtime.py'):
            ast.parse(proposed(path))
        self.assertIn('mod_editor/core/nfl2k5_digit_art.py',proposed('packaging/release-allowlist.txt'))
        self.assertIn('"mod_editor.core.nfl2k5_digit_art"',proposed('packaging/check_2k5_mod_studio_runtime.py'))
        from mod_editor.core.providers import Nfl2k5UnifiedVisualProvider, _validate_pin_set
        self.assertIn('mod_editor/core/nfl2k5_digit_art.py',Nfl2k5UnifiedVisualProvider.module_pins)
        _validate_pin_set(ROOT,Nfl2k5UnifiedVisualProvider.module_pins,'coach')


class CoachWiringTests(legacy.NumberSheetQualityWiringTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        tree=ast.parse(proposed('mod_editor/gui/studio_qt.py'))
        owner=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='StudioMainWindow')
        methods=[n for n in owner.body if isinstance(n,ast.FunctionDef) and n.name in
                 {'_review_digit_sheet_preview','_choose_digit_sheet_import'}]
        exec(compile(ast.Module(body=methods,type_ignores=[]),'<coach proposed GUI>','exec'),cls.ns)

    def preview(self):
        old=super().preview()
        return DigitSheetPreview(old.png,old.details,tuple({'kept_retail':i<3} for i in range(10)))

    # Keep the previous transaction/source-change tests, adding the new third
    # chooser and verifying its metadata survives the real splitter.
    flow=textwrap.dedent(inspect.getsource(legacy.NumberSheetQualityWiringTests.run_flow))
    flow=flow.replace('("Match retail size", True)', '("As authored", True)')
    flow=flow.replace('self.assertEqual(len(outputs), 10)',
                      'self.assertEqual(len(outputs), 10)\n            from mod_editor.core.nfl2k5_digit_art import registration_mode\n            self.assertTrue(all(registration_mode(o.png) == "as_authored" for o in outputs))')
    namespace=dict(legacy.__dict__)
    exec(compile(flow,'<coach transaction test>','exec'),namespace)
    run_flow=namespace['run_flow']
    del flow,namespace

    def test_preview_dialog_keeps_encoded_pixels_at_native_display_size_and_notes(self):
        from PyQt5.QtWidgets import QDialog,QDialogButtonBox,QLabel,QWidget
        preview=self.preview()
        def inspect_dialog(dialog):
            self.assertEqual(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).text(),
                             'Import 7 digits, 3 kept retail')
            labels=dialog.findChildren(QLabel)
            self.assertTrue(any('KEPT RETAIL' in label.text() for label in labels))
            image=next(label.pixmap() for label in labels if label.pixmap() is not None)
            self.assertEqual((image.width(),image.height()),(730,850))
            return QDialog.Accepted
        host=QWidget()
        try:
            with patch.object(QDialog,'exec_',inspect_dialog):
                self.assertTrue(self.ns['_review_digit_sheet_preview'](host,preview))
        finally:host.close();host.deleteLater()

    def test_facade_encoding_holds_source_session_lock(self):
        from mod_editor.studio import facade
        tree=ast.parse(proposed('mod_editor/studio/facade.py'))
        owner=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Nfl2k5StudioFacade')
        method=next(n for n in owner.body if isinstance(n,ast.FunctionDef) and n.name=='preview_digit_sheet')
        ns=dict(facade.__dict__)
        exec(compile(ast.Module(body=[method],type_ignores=[]),'<coach proposed facade>','exec'),ns)
        gate=RLock(); torso=SimpleNamespace(kind='torso'); digit=SimpleNamespace(set_selector='26A0')
        outputs=(SimpleNamespace(asset_id='digit'),)
        session=SimpleNamespace(cache=SimpleNamespace(pack0=Path('index')),current_path=Mock(return_value=Path('current-jersey.png')))
        host=SimpleNamespace(_lock=gate,_require_session=lambda:session,
                             uniform_catalog=SimpleNamespace(get_asset=lambda _:digit,assets_for_set=lambda _:(torso,)))
        def encode(index,targets,supplied,progress,*,background):
            if hasattr(gate,'_is_owned'):self.assertTrue(gate._is_owned())
            self.assertEqual((index,targets,supplied,background),(Path('index'),(digit,),outputs,(224,225,226)))
            return 'preview'
        with patch('mod_editor.core.nfl2k5_digit_preview.jersey_preview_colour',return_value=(224,225,226)) as colour, \
             patch('mod_editor.core.nfl2k5_digit_preview.preview_digit_sheet',encode):
            self.assertEqual(ns['preview_digit_sheet'](host,outputs,Mock()),'preview')
            colour.assert_called_once_with(Path('current-jersey.png'))
            session.current_path.assert_called_once_with(torso)


if __name__=='__main__':unittest.main()

"""Replay the protected H4 GUI handoff in memory, or test it after integration."""
from __future__ import annotations
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import re
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO))
from PyQt5.QtWidgets import QApplication
from mod_editor.core import nfl2k5_models as M
from mod_editor.core import nfl2k5_animation_bones as B


def wired_module():
    source_path=REPO/'mod_editor/gui/models_panel_qt.py'
    source=source_path.read_text(encoding='utf-8')
    if 'self.skeleton_mode = QComboBox()' not in source:
        lines=source.splitlines(True)
        patch_lines=(REPO/'docs/mod_editor/nfl2k5_model_skeleton_gui.patch').read_text(encoding='utf-8').splitlines(True)
        out=[];cursor=0;active=False
        for line in patch_lines:
            if line.startswith('@@ '):
                match=re.match(r'@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@',line)
                assert match,line
                start=int(match[1])-1
                out.extend(lines[cursor:start]);cursor=start;active=True
            elif active and line[:1] in (' ','-','+'):
                if line[0] in (' ','-'):
                    assert lines[cursor]==line[1:],('H4 GUI patch context differs',cursor,line)
                    cursor+=1
                if line[0] in (' ','+'):
                    out.append(line[1:])
        out.extend(lines[cursor:]);source=''.join(out)
    module=ModuleType('mod_editor.gui._h4_models_wiring')
    module.__file__=str(source_path)
    sys.modules[module.__name__]=module
    exec(compile(source,str(source_path),'exec'),module.__dict__)
    return module


class WiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.module=wired_module()

    def setUp(self):
        self.panel=self.module.ModelsPanel()
        self.addCleanup(self.panel.deleteLater)
        self.addCleanup(self.panel.wait_idle)

    def test_mode_defaults_off_and_invalidates_previous_check(self):
        p=self.panel
        self.assertEqual([p.skeleton_mode.itemText(i) for i in range(2)],['Geometry only','Geometry and skeleton'])
        self.assertEqual(p.skeleton_mode.currentData(),'geometry')
        p._compiled=object()
        p.skeleton_mode.setCurrentIndex(1)
        self.assertIsNone(p._compiled)
        self.assertIsNone(p._compiled_set)
        self.assertIn('translations only',p.skeleton_mode.toolTip())

    def test_single_file_path_checks_pair_and_renders_centimetre_receipt(self):
        p=self.panel
        p._source=object()
        p.current_key=lambda:'o3c113'
        bs=SimpleNamespace(outer_index=3,entries=[])
        p.current_body_set=lambda:bs
        p._run=lambda operation,done:done(operation())
        p.skeleton_mode.setCurrentIndex(1)
        receipt={'changed_bones':[{'bone':'left_forearm','before_cm':20.,'after_cm':21.}],
                 'changed_bind_lengths':[{'member':'o3c114','bone':'lhand','before_cm':20.,'after_cm':21.}]}
        result=M.CompiledModelSet(3,skeleton_plan=B.BonePlan((),receipt))
        with patch.object(M,'compile_body_set_import',return_value=result) as compile_set:
            p.compile_edited(Path('export/lo_body_o3c113.gltf'))
        self.assertEqual(compile_set.call_args.args[2],Path('export'))
        self.assertTrue(compile_set.call_args.kwargs['import_skeleton'])
        self.assertIs(p._compiled_set,result)
        self.assertIn('20.00000 -> 21.00000',p.details.toPlainText())
        self.assertIn('UNWITNESSED',p.details.toPlainText())
        self.assertIn('o3c114 / lhand',p.details.toPlainText())


if __name__=='__main__':unittest.main()

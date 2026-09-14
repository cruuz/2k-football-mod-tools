"""Execute the exact protected J2 handoff in memory, or use it after integration."""
from __future__ import annotations
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import re
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT),str(Path(__file__).parent)]
import test_nfl2k5_model_project as fixtures
from mod_editor.core import nfl2k5_model_project as P
from mod_editor.core import nfl2k5_build_service as BS
from PyQt5.QtWidgets import QApplication


def wired(relative, marker):
    path = ROOT/relative; original = path.read_text()
    name = str(relative).replace('/','.').removesuffix('.py') + '_j2'
    if marker not in original:
        lines = original.splitlines(True); output = []; cursor = 0; active = False; hunk = False
        for line in (ROOT/'docs/mod_editor/nfl2k5_model_project_wiring.patch').read_text().splitlines(True):
            if line.startswith('--- a/'):
                active = line[6:].strip() == str(relative); hunk = False
            elif active and line.startswith('@@ '):
                start = int(re.match(r'@@ -(\d+)',line)[1])-1
                output.extend(lines[cursor:start]); cursor = start; hunk = True
            elif active and hunk and line[:1] in (' ','-','+'):
                if line[0] in (' ','-'):
                    assert lines[cursor] == line[1:], (relative,cursor,line)
                    cursor += 1
                if line[0] in (' ','+'):
                    output.append(line[1:])
        output.extend(lines[cursor:]); original = ''.join(output)
    module = ModuleType(name); module.__file__ = str(path); module.__package__ = name.rsplit('.',1)[0]
    sys.modules[name] = module
    exec(compile(original,str(path),'exec'),module.__dict__)
    return module


class WiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.RetailProjectTests.setUpClass.__func__(cls)
        cls.app = QApplication.instance() or QApplication([])
        cls.studio = wired('mod_editor/gui/studio_qt.py','def _models_project_changed(')
        cls.builder = wired('mod_editor/core/mod_build.py','receipt["project_models"]')
        cls.build_panel_module = wired('mod_editor/gui/build_panel_qt.py','saved checked bytes; in-game UNWITNESSED')

    def setUp(self):
        fixtures.RetailProjectTests.setUp(self)

    build_context = fixtures.RetailProjectTests.build_context

    def test_real_bottom_bar_and_build_plan_add_undo_readd(self):
        window = self.studio.StudioMainWindow(self.facade,uniform_catalog=self.catalog,eager_pages=False)
        panel = window._models_panel
        try:
            panel.apply_catalog(self.source,self.source.catalog()); panel.select_key('o3c113')
            panel.wait_idle(); self.app.processEvents()
            panel.compile_edited(self.export.gltf_path); panel.wait_idle(); self.app.processEvents()
            panel.add_project_button.click(); panel.wait_idle(); self.app.processEvents()
            self.assertEqual(window.edit_count.text(),'1 project edit')
            self.assertTrue(window._workspace_dirty)
            self.facade.undo(lambda *a:None); window._refresh_edit_state()
            self.assertIn('No project edits',window.edit_count.text())
            panel.add_project_button.click(); panel.wait_idle(); self.app.processEvents()
            self.assertEqual(window.edit_count.text(),'1 project edit')
            build_panel = self.build_panel_module.BuildPanel(self.facade,available={})
            try:
                text = build_panel.confirmation_text(build_panel.plan())
                self.assertIn('Model: ',text)
                self.assertIn('saved checked bytes',text)
            finally:
                build_panel.deleteLater()
            self.facade.build_service = BS.Nfl2k5BuildService(runner=fixtures.InlineBackend())
            with self.build_context():
                result = self.facade.build_iso(self.root/'wired-project.iso',lambda *a:None)
            self.assertGreater(result.changed_byte_count,0)
        finally:
            panel.wait_idle(); window.deleteLater(); self.app.processEvents()

    def test_project_writer_precedes_gameplay_and_models_are_in_combined_receipt(self):
        self.session.stage_model(self.record)
        service = BS.Nfl2k5BuildService(runner=fixtures.InlineBackend())
        plan = self.builder.BuildPlan(source=str(self.fixture.path),target=str(self.root/'combined.iso'))
        def gameplay(plan, progress, *, _project_builder):
            # The actual project service runs first. This artificial XBE write
            # represents the next writer; no retail gameplay claim is made.
            result = _project_builder(Path(plan.target))
            payload = bytearray(result.output_xiso.read_bytes())
            payload[35*2048+4] = 123
            result.output_xiso.write_bytes(payload)
            return {'target':plan.target,'steps':[{'step':'synthetic_gameplay'}]}
        with self.build_context(), patch.object(self.builder,'build',side_effect=gameplay):
            receipt = self.builder.build_with_project(plan,service,self.cache,self.session)
        self.assertEqual(receipt['project_models'],P.plan_rows(self.session))
        with open(plan.target,'rb') as stream:
            spans = fixtures.M.image_spans(self.source,self.compiled,stream.fileno(),Path(plan.target).stat().st_size)
            for absolute,inner,size in spans:
                stream.seek(absolute)
                self.assertEqual(stream.read(size),self.compiled.rebuilt_span[inner:inner+size])
        self.assertEqual(Path(plan.target).read_bytes()[35*2048+4],123)
        plan = fixtures.SimpleNamespace(guardian_cap=True)
        with patch.object(service,'build') as build:
            with self.assertRaisesRegex(P.ValidationError,'Guardian cap/overlay'):
                self.builder.build_with_project(plan,service,self.cache,self.session)
            build.assert_not_called()


if __name__ == '__main__':
    unittest.main()

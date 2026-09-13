"""Execute the complete proposed Studio method with real offscreen dialogs."""
import os
import inspect
from pathlib import Path
import re
import sys
import textwrap
import tempfile
from types import SimpleNamespace, MethodType
import unittest
from unittest.mock import patch, Mock

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PyQt5.QtWidgets import QApplication, QWidget, QPlainTextEdit
from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_uniform_equipment_writer import EquipmentFitError
from mod_editor.gui import equipment_texture_import_dialog as dialogs


class WiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def test_try_that_restarts_after_blocking_task_and_keeps_scope_and_pixels(self):
        namespace={'Path':Path,'ValidationError':ValidationError,
                   '_result_message':lambda result,default:getattr(result,'message',default)}
        source=(ROOT/'reports/b69_j1/studio-equipment-method.py.txt').read_text()
        exec('from __future__ import annotations\n'+source,namespace)
        calls=[]
        asset=SimpleNamespace(asset_id='tset:3653:9:4:shoes10',label='Bears shoe',
            width=256,height=256,kind='uniform_equipment_texture',editable=True)
        class Facade:
            def replace_equipment_texture(self, selected,path,progress,**options):
                calls.append((selected.asset_id,path,options))
                if len(calls)==1:
                    raise EquipmentFitError(58432,60000,(),dict(asset_id=selected.asset_id,
                        scale=2,width=128,height=128,colours=64))
                return SimpleNamespace(changed_asset_ids=(selected.asset_id,),modified=True,message='Imported')
        class Owner(QWidget):
            def __init__(self):
                super().__init__();self._texture_master_drafts={};self.facade=Facade()
                self.busy=False;self.queue=[];self.changes=0
            def _fit_for_slot(self,path,*args):return path
            def _prepare_texture_master_draft(self,*args):return None
            def _show_error(self,message):raise AssertionError(message)
            def _set_status(self,message):pass
            def _filter_visual_assets(self,*args):pass
            def _load_visual_preview(self,*args):pass
            def _discard_texture_master_draft(self,*args):pass
            def _mark_workspace_changed(self):self.changes+=1
            def _defer_until_blocking_task_finished(self,callback):
                if self.busy:self.queue.append(callback)
                else:callback()
            def _start_task(self,operation,success,**kwargs):
                if self.busy:raise AssertionError('Retry was submitted before the first task finished')
                self.busy=True
                success(operation(lambda *args:None))
                self.busy=False
                while self.queue:self.queue.pop(0)()
        owner=Owner();method=MethodType(namespace['_replace_visual_asset'],owner)
        def choose(dialog):dialog.accept();return dialog.Accepted
        def retry(dialog):dialog.try_that.click();return dialog.result()
        state=SimpleNamespace(category='Textures',preview=object(),selected_asset_id=None)
        with patch.object(dialogs.EquipmentTextureImportDialog,'exec_',choose), \
             patch.object(dialogs.EquipmentFitRetryDialog,'exec_',retry):
            method(state,asset,Path('same-authored-pixels.png'))
        self.assertEqual([row[2]['scale'] for row in calls],[1,2])
        self.assertEqual([row[1] for row in calls],[Path('same-authored-pixels.png')]*2)
        self.assertTrue(all(row[2]['independent'] and row[2]['scope']=='selected-package' for row in calls))
        self.assertEqual(owner.changes,1)

    def test_build_list_method_renders_all_original_indices_and_newest_observed_edit(self):
        wiring=(ROOT/'WIRING_B69_J1.md').read_text()
        block=next(block for block in re.findall(r'```python\n(.*?)```',wiring,re.S)
                   if 'def _refresh_build_includes(' in block)
        namespace={}
        exec(textwrap.dedent(block),namespace)
        doc={'edits':[dict(kind='torso',asset_code='02',side='H',variant=0),
                      dict(kind='unif_color',selector='05H0',facemask='FF123456')]}
        session=SimpleNamespace(modified_count=2,canonical_document=lambda:doc)
        output=QPlainTextEdit()
        owner=SimpleNamespace(facade=SimpleNamespace(_session=session),
                              _build_panel=SimpleNamespace(project_includes_list=output))
        render=MethodType(namespace['_refresh_build_includes'],owner)
        render(baseline=True)
        self.assertEqual(output.toPlainText().count('Project edit index'),2)
        doc['edits'][0]['variant']=1
        render()
        self.assertTrue(output.toPlainText().startswith('Project edit index 0'))
        self.assertIn('Project edit index 1',output.toPlainText())
        self.assertIn('Uniforms / torso',output.toPlainText())

    def test_load_hook_refuses_real_unfit_group_and_cleans_before_session_mutation(self):
        from mod_editor.studio import session as session_module
        from test_b69_j1_fit import tight_fixture
        wiring=(ROOT/'WIRING_B69_J1.md').read_text()
        hook=next(block for block in re.findall(r'```python\n(.*?)```',wiring,re.S)
                  if 'preflight_project_equipment(self.cache.pack0' in block)
        source=textwrap.dedent(inspect.getsource(session_module.StudioSession.load_shareable_project))
        source=source.replace('    try:\n', '    try:\n'+textwrap.indent(textwrap.dedent(hook),'        '),1)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();fixture,rgba=tight_fixture(root)
            asset,png=fixture.png(rgba=rgba)
            cleanup=Mock()
            loaded=SimpleNamespace(edits=[SimpleNamespace(
                asset=SimpleNamespace(kind='uniform_equipment_texture',asset_id=asset),staged_path=png)],
                cleanup=cleanup)
            namespace=dict(vars(session_module),load_project_archive=lambda **kwargs:loaded)
            exec('from __future__ import annotations\n'+source,namespace)
            sentinel={};owner=SimpleNamespace(modified_count=0,_audio_annotations={},_build_settings={},
                _project_catalog_router=None,_project_io_router=None,root=root,
                cache=SimpleNamespace(pack0=root/'0'),_edits=sentinel)
            with fixture.context(), self.assertRaisesRegex(ValueError,'Cannot load equipment edits:.*shoes01.*202 bytes'):
                namespace['load_shareable_project'](owner,root/'old.2k5mod')
            cleanup.assert_called_once_with()
            self.assertIs(owner._edits,sentinel)


if __name__=='__main__':unittest.main()

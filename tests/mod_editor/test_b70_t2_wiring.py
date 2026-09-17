"""Execute the exact protected GUI/build snippets supplied in WIRING.md."""
import os
from pathlib import Path
import re
import sys
import tempfile
import textwrap
from types import SimpleNamespace, MethodType
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(Path(__file__).parent)]
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from mod_editor.core import equipment_staging as staging
from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
from test_nfl2k5_equipment_texture_chain import Fixture


def snippet(phrase):
    blocks=re.findall(r'```python\n(.*?)\n```',(ROOT/'WIRING_B70_T2.md').read_text(),re.S)
    return textwrap.dedent(next(b for b in blocks if phrase in b))


class WiringTests(unittest.TestCase):
    def test_project_rows_take_returned_preflight_measurements_without_recompiling(self):
        from PyQt5.QtWidgets import QApplication,QPlainTextEdit
        from unittest.mock import patch
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            f=Fixture(Path(directory))
            asset_id,png=f.png()
            with f.context():
                rows=writer.preflight_project_equipment(f.pack,[(None,asset_id,png)])
            import hashlib
            edit=SimpleNamespace(asset_id=asset_id,replacement_sha256=hashlib.sha256(png.read_bytes()).hexdigest())
            document=dict(edits=[dict(kind='uniform_equipment_texture',asset_id=asset_id,png=str(png))])
            session=SimpleNamespace(modified_count=1,iter_edits=lambda:(edit,),canonical_document=lambda:document)
            staging._remember_fit(session,rows,persist=False)  # presentation-only stub
            output=QPlainTextEdit()
            owner=SimpleNamespace(facade=SimpleNamespace(_session=session),_build_panel=SimpleNamespace(project_includes_list=output))
            namespace={}
            exec(snippet('def _refresh_build_includes('),namespace)
            render=MethodType(namespace['_refresh_build_includes'],owner)
            with patch.object(writer,'build_unified_uniform_equipment_imports',side_effect=AssertionError('GUI must not compile')):
                render(baseline=True)
                self.assertIn(rows[0]['fit_summary'],output.toPlainText())
                self.assertIn('Project edit index 0',output.toPlainText())
                edit.replacement_sha256='changed'
                render()
                # Beta 71.1 (T5): opening no longer fits, so the live build list marks a stale
                # receipt 'fit pending' where the beta 70 proposal said 'measurement unavailable'.
                self.assertRegex(output.toPlainText(),r'measurement unavailable|fit pending')
                self.assertNotIn(rows[0]['fit_summary'],output.toPlainText())
            output.close()
            app.processEvents()

    def test_build_property_includes_measured_rows_and_existing_refusals(self):
        namespace={}
        exec(snippet('def message(self)'),namespace)
        prop=namespace['message']
        owner=SimpleNamespace(output_xiso=Path('user-game.iso'),kept_retail=(),
                              texture_summary=('Equipment socks00 (05H0): fitted at 64 x 64, 16 colours.',))
        self.assertIn('fitted at 64 x 64, 16 colours',prop.fget(owner))
        owner.kept_retail=({'selector':'arm2','message':'Arm digit 2 kept retail'},)
        self.assertIn('Arm digit 2 kept retail',prop.fget(owner))
        owner.kept_retail=();owner.texture_summary=()
        self.assertEqual(prop.fget(owner),'')


if __name__=='__main__':unittest.main()

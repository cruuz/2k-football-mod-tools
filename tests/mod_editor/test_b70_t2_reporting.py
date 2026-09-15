"""Real compile receipt captions, tamper refusal and offscreen arm help."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT),str(ROOT/'tools'),str(Path(__file__).parent)]
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from mod_editor.core.equipment_reporting import verified_build_texture_lines, fit_caption
from mod_editor.core.errors import ValidationError
from test_nfl2k5_equipment_texture_chain import Fixture


class ReportingTests(unittest.TestCase):
    def test_build_without_texture_edits_needs_no_artifact_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest=Path(directory)/'manifest.json'
            manifest.write_text('{"edits": []}')
            self.assertEqual(verified_build_texture_lines(manifest),())

    def test_real_compiler_fit_roundtrip_and_modified_receipt_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            f=Fixture(root)
            _span,_previews,report,_selector,_target=f.build([f.png()])
            receipt=root/'equipment.json'
            payload=json.dumps(report).encode()
            receipt.write_bytes(payload)
            manifest=root/'manifest.json'
            value=dict(output=dict(artifact_directory=str(root)),edits=[dict(kind='uniform_equipment_texture',
                import_report=dict(file_name=receipt.name,sha256=hashlib.sha256(payload).hexdigest()))])
            manifest.write_text(json.dumps(value))
            lines=verified_build_texture_lines(manifest)
            self.assertEqual(lines,(f"Equipment shoes01 (SYNTHETIC): {fit_caption(report['edits'][0])}.",))
            receipt.write_bytes(payload+b' ')
            with self.assertRaisesRegex(ValidationError,'changed'):
                verified_build_texture_lines(manifest)
            value['edits'][0]['import_report']['file_name']='../outside.json'
            manifest.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValidationError,'filename'):
                verified_build_texture_lines(manifest)

    def test_stadium_summary_names_each_compiled_occurrence(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            target=dict(selector='nfl2k5.stadium.o3141.c0006.scene1998.texture0042',
                        scene_id='scene1998',stadium_package=dict(label='Chicago Field / Day / Dry (s05dd.iff)'),
                        mapped_material_names=['banner_corp'])
            payload=json.dumps(dict(compiled_textures=[dict(target=target)])).encode()
            (root/'stadium.json').write_bytes(payload)
            manifest=root/'manifest.json'
            manifest.write_text(json.dumps(dict(output=dict(artifact_directory=str(root)),edits=[dict(
                kind='stadium_texture',import_report=dict(file_name='stadium.json',sha256=hashlib.sha256(payload).hexdigest()))])))
            line,=verified_build_texture_lines(manifest)
            for phrase in ('Chicago Field','Day / Dry','texture0042','banner_corp','UNWITNESSED'):
                self.assertIn(phrase,line)

    def test_caption_rejects_missing_or_unmeasured_fields(self):
        for row in ({},dict(encoded_dimensions=[64,64],used_palette_entries=0),
                    dict(encoded_dimensions=[64,64],used_palette_entries=True)):
            with self.assertRaises(ValidationError):fit_caption(row)

    def test_arm_import_dialog_explains_model_placement(self):
        from PyQt5.QtWidgets import QApplication,QLabel
        from mod_editor.gui.equipment_texture_import_dialog import ArmDigitImportDialog
        app=QApplication.instance() or QApplication([])
        dialog=ArmDigitImportDialog(SimpleNamespace(label='Arm digit 2'))
        text=dialog.findChild(QLabel,'armDigitPlacementHelp').text()
        for phrase in ('UV','model','artwork','position','shoulder pad'):
            self.assertIn(phrase,text)
        dialog.close()
        app.processEvents()


if __name__=='__main__':unittest.main()

"""Measured overflow, real retry compilation, and original-index load errors."""
from dataclasses import replace
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools'), str(Path(__file__).parent)]
from test_nfl2k5_equipment_texture_chain import Fixture, digest
from test_b68_t1_build import backend
from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
from mod_editor.core.nfl2k5_equipment_lz import compress_equipment_optimal
from nfl_txtr import HEADER, parse_chunks


def tight_fixture(root):
    f = Fixture(root, margin=0)
    raw = bytearray(f.decoded)
    rows = []
    for row in f.rows:
        palette = bytes((30,50,70,255))*256
        start = f.chunk.system_bytes+row.palette_offset
        raw[start:start+1024] = palette
        rows.append(replace(row, palette_bgra_sha256=digest(palette)))
    f.rows, f.decoded = tuple(rows), bytes(raw)
    encoded = min((compress_equipment_optimal(f.decoded, stream_tag=1,
        offset_bits=bits, max_encoded_size=10000) for bits in (10,11,12)), key=len)
    stored = (len(encoded)+128+15)&~15
    f.span = HEADER.pack(b'TSET', stored, f.chunk.system_bytes, f.chunk.video_bytes,
        0xFEEDBEEF, stored, 0, 0)+encoded+bytes(stored-len(encoded))
    f.chunk = replace(parse_chunks(f.span)[0], index=8)
    f.pack.write_bytes(f.span)
    rng = random.Random(69)
    rgba = b''.join(bytes((rng.randrange(256),rng.randrange(256),rng.randrange(256),255)) for _ in range(1024))
    return f, rgba


class FitTests(unittest.TestCase):
    def test_shortfall_and_largest_retry_recompile_with_identical_budget_and_scratch(self):
        with tempfile.TemporaryDirectory() as directory:
            f, rgba = tight_fixture(Path(directory))
            before = f.pack.read_bytes()
            with self.assertRaises(writer.EquipmentFitError) as caught:
                f.build([f.png(rgba=rgba)])
            error = caught.exception
            self.assertEqual((error.budget,error.required), (464,666))
            self.assertIn('missed the 464-byte span by 202 bytes', str(error))
            self.assertEqual(error.suggestion['scale'],2)
            self.assertEqual(error.suggestion['colours'],2)
            span, _, receipt, _, _ = f.build([f.png(rgba=rgba,scale=error.suggestion['scale'])])
            self.assertEqual(len(span),len(f.span))
            self.assertEqual(span[20:24],f.span[20:24])
            self.assertEqual(receipt['edits'][0]['encoded_dimensions'],[16,16])
            self.assertEqual(f.pack.read_bytes(),before)

    def test_load_refuses_unhonourable_legacy_group_before_session_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            f,rgba = tight_fixture(root)
            asset,png = f.png(rgba=rgba)  # npTC/v1 is the exact beta-62/65 record shape.
            tool = backend()
            project = root/'legacy.json'
            project.write_bytes(tool.canonical_json(dict(schema=tool.SCHEMA,purpose='legacy own chain',
                edits=[dict(kind=tool.UNIFORM_EQUIPMENT_KIND,asset_id=asset,png=str(png))])))
            with f.context(), patch.object(tool,'uniform_equipment_adapter',writer), \
                 self.assertRaisesRegex(ValueError,'Cannot load equipment edits:.*shoes01.*202 bytes.*Reimport'):
                tool.read_project(project,equipment_index=f.pack)
            self.assertEqual(f.pack.read_bytes(),f.span)

    def test_legacy_glove_record_retains_full_mip_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);f = Fixture(root,family=6)
            asset,png = f.png()
            tool = backend();project=root/'legacy-glove.json'
            project.write_bytes(tool.canonical_json(dict(schema=tool.SCHEMA,purpose='legacy glove',
                edits=[dict(kind=tool.UNIFORM_EQUIPMENT_KIND,asset_id=asset,png=str(png))])))
            with f.context(),patch.object(tool,'uniform_equipment_adapter',writer):
                tool.read_project(project,equipment_index=f.pack)
            _span,_previews,receipt,_selector,_target=f.build([(asset,png)])
            self.assertEqual(receipt['edits'][0]['mip_levels'],2)
            self.assertEqual(receipt['edits'][0]['encoded_dimensions'],[32,16])

    def test_build_include_list_tracks_edits_not_alphabetical_asset_order(self):
        tool=backend();timeline=tool.ProjectEditTimeline()
        doc={'edits':[dict(kind='torso',asset_code='02',side='H',variant=0,clean_png='absent.png'),
                      dict(kind='unif_color',selector='05H0',facemask='FF000000',turtleneck=None)]}
        rows=timeline.observe(doc,baseline=True)
        self.assertFalse(any(row['original_order_known'] for row in rows))
        doc['edits'][0]['clean_png']='latest.png'
        rows=timeline.observe(doc)
        self.assertEqual([row['project_edit_index'] for row in rows],[0,1])
        self.assertEqual(timeline.observe(doc),rows)
        doc['edits'][1]['facemask']='FFFFFFFF'
        self.assertEqual([row['project_edit_index'] for row in timeline.observe(doc)],[1,0])
        for kind, page in (('universal_fixed_text', 'Text & Team Identity'),
                           ('crib_scene_geometry', 'The Crib'), ('stadium_geometry', 'Stadiums'),
                           ('player_portrait', 'Portraits & Faces')):
            self.assertIn(page, tool.project_edit_label({'kind': kind, 'selector': 'chosen'}, 8))


class RetryDialogTests(unittest.TestCase):
    def test_try_that_carries_checked_scale_without_accepting_another_edit(self):
        from PyQt5.QtWidgets import QApplication, QDialog
        from mod_editor.gui.equipment_texture_import_dialog import EquipmentFitRetryDialog
        self.app=QApplication.instance() or QApplication([])
        asset=SimpleNamespace(asset_id='tset:0:8:0:shoes01')
        suggestion=dict(asset_id=asset.asset_id,scale=2,width=128,height=128,colours=64)
        error=writer.EquipmentFitError(58432,60000,(),suggestion)
        dialog=EquipmentFitRetryDialog(asset,error)
        self.assertTrue(dialog.try_that.isEnabled())
        self.assertEqual(dialog.scale,2)
        dialog.try_that.click()
        self.assertEqual(dialog.result(),QDialog.Accepted)
        other=EquipmentFitRetryDialog(SimpleNamespace(asset_id='other'),error)
        self.assertFalse(other.try_that.isEnabled())


if __name__=='__main__':unittest.main()

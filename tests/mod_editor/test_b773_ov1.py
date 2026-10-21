"""ov1: imported-mark exclusions and pinned native duplicate-shield cleanup."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools')]
import nfl2k5_team_2026_art as art
from mod_editor.core import nfl2k5_kit_fixes_2026 as fixes
from tools.b77 import ov1_repair as repair


class DecorationExclusions(unittest.TestCase):
    def setUp(self):
        self.spec = SimpleNamespace(colour=lambda n: np.array([1.,0.,0.],np.float32))
        self.base = np.full((32,48,4), .3, np.float32)
        self.item = dict(rect=[1,1,10,7],colour='red',exclude_boxes=[[4,2,6,4]])

    def test_exclusion_preserves_the_underlying_layer_and_surrounding_art(self):
        out = art.decorate(self.base.copy(),self.spec,[self.item],None)
        np.testing.assert_array_equal(out[8:16,16:24],self.base[8:16,16:24])
        self.assertTrue((out[5,5,:3] == [1,0,0]).all())
        np.testing.assert_array_equal(out[:4],self.base[:4])

    def test_bad_box_is_refused_before_it_can_slice_the_texture(self):
        for box in [[-1,0,1,1],[0,0,100,1],[1,1,1,2],[1.5,0,2,1],[1,2,3]]:
            with self.subTest(box=box),self.assertRaises(ValueError):
                art.decorate(self.base.copy(),self.spec,[dict(self.item,exclude_boxes=[box])],None)

    def test_exclusion_is_local_to_its_own_decoration(self):
        second=dict(rect=[4,2,6,4],colour='red')
        out=art.decorate(self.base.copy(),self.spec,[self.item,second],None)
        self.assertTrue((out[10,18,:3] == [1,0,0]).all())


class Contract(unittest.TestCase):
    def test_only_the_two_tampa_torsos_are_owned(self):
        doc=fixes.overlaps()
        self.assertEqual({(r['selector'],r['chunk']) for r in doc['textures']},{('27H0',1),('27A0',1)})
        spec=json.loads((ROOT/'data/nfl2k5_teams_2026/TB.json').read_text())
        for side in ['home','away']:
            kit=spec['kits'][side]
            self.assertEqual(kit['torso']['decorations'][1]['exclude_boxes'],[repair.BOXES[kit['selector']]])
            box=repair.BOXES[kit['selector']]
            self.assertGreaterEqual(box[1],82)  # shared collar shield ends at 81
            self.assertLessEqual(box[3],89)     # wordmark letters begin at 89
        self.assertIn('data/nfl2k5_kit_fixes_2026_ov1.json',(ROOT/'packaging/release-allowlist.txt').read_text())

    def test_studio_build_orders_the_pass_after_uf3(self):
        text=(ROOT/'mod_editor/core/mod_build.py').read_text()
        self.assertLess(text.index('kit_fixes.apply_finish(target)'),text.index('kit_fixes.apply_overlaps(target)'))

    def test_unknown_disc_is_refused_without_creating_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);disc=p/'bad.iso';disc.write_bytes(b'unknown')
            with self.assertRaisesRegex(ValueError,'unexpected disc size'):
                repair.run(disc,p/'receipts',audit=True)
            self.assertEqual(disc.read_bytes(),b'unknown')
            self.assertFalse((p/'receipts').exists())


@unittest.skipUnless(os.environ.get('NFL2K5_OV1_DISC'),'set NFL2K5_OV1_DISC for read-only native checks')
class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc=fixes.overlaps()
        cls.raws,cls.ranges,cls.extents=repair.transport.read_resources(Path(os.environ['NFL2K5_OV1_DISC']),cls.doc,{})
        cls.compiled,cls.receipts=repair.compile_plans(cls.raws,cls.doc)

    def test_pixels_outside_duplicate_fragment_and_all_other_chunks_are_preserved(self):
        for row in self.doc['textures']:
            sel=row['selector'];raw=self.raws[sel];new=self.compiled[sel];at=row['offset'];end=at+row['length']
            self.assertEqual(raw[:at],new[:at]);self.assertEqual(raw[end:],new[end:])
            before=fixes.texture_rgba(raw[at:end]);after=fixes.texture_rgba(new[at:end]);x,y,X,Y=repair.BOXES[sel]
            mask=np.zeros(before.shape[:2],bool);mask[y:Y,x:X]=True
            np.testing.assert_array_equal(before[~mask],after[~mask])
            self.assertGreater(np.count_nonzero((before!=after).any(2)),0)
            cloth=[178,28,53] if sel=='27H0' else [255,255,255]
            self.assertTrue((after[y:Y,x:X,:3] == cloth).all())

    def test_zero_byte_replay_and_foreign_art_refusal(self):
        for sel,new in self.compiled.items():
            parts,receipt=fixes.compile_resource(sel,new,document=self.doc)
            self.assertEqual(parts,[]);self.assertEqual(receipt['changed_bytes'],0)
            bad=bytearray(self.raws[sel]);bad[120]^=1
            with self.assertRaisesRegex(ValueError,'unknown or partially repaired'):
                fixes.compile_resource(sel,bytes(bad),document=self.doc)

    def test_native_compact_writer_and_replay_equal_compiled_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);repair.compact_fixture(p,self.raws)
            written=fixes.apply_overlaps(p,strict=True)
            self.assertEqual(written['written_spans'],2)
            self.assertEqual(fixes.apply_overlaps(p,strict=True)['written_bytes'],0)
            with repair.bump._Image.open(p,writable=False) as im:
                ix=repair.bump._parsed_index(im)
                for e in ix.entries:
                    sel=repair.bump.logical_name_for(e.name_id)[:-4]
                    self.assertEqual(im.read_segments(ix.sub_extents(e,0,e.size)),self.compiled[sel])


if __name__ == '__main__':
    unittest.main()

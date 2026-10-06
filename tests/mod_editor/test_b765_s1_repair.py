"""Native texture transport and batch preflight, with synthetic non-retail pixels."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
import numpy as np
from PIL import Image
from tests.mod_editor.test_b765_s1_geometry import native_bundle
from tools.b765 import s1_geometry as g,s1_repair as repair
from mod_editor.core import nfl2k5_scne_builder as sb


def textured_bundle():
    original=native_bundle();c,r,d=g.stadium(original);sc=sb.parse(d,c.system_bytes)
    tr=bytearray(0x20);struct.pack_into('<I',tr,0x0c,0x29);struct.pack_into('<I',tr,0x14,0x80000000)
    sc.textures=[sb.p8_texture(sb.Texture(tr,b'',b''),np.full((8,8,4),[80,100,120,255],np.uint8))]
    sc.materials[1].texture=0
    sc.materials.append(sb.Material(bytearray(sc.materials[1].record),'seat_alias',0))
    decoded,system,video=sb.serialize(sc)
    chunk,_=sb.compressed_chunk('SCNE',decoded,system,video,stream_tag=3,offset_bits=12,optimal=False)
    head=list(struct.unpack_from('<4s7I',chunk));head[1]=sb.align(len(decoded)+128,16)
    padded=struct.pack('<4s7I',*head)+chunk[32:]+bytes(head[1]-len(chunk)+32)
    span,_=sb.fixed_span_chunk('SCNE',decoded,system,video,padded)
    return original[:c.offset]+span+original[c.end_offset:]


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.data=textured_bundle();self.export=self.root/'export'
        g.export_bundle(self.data,'s07dd.iff',self.export)
        self.png=self.root/'seat.png';Image.new('RGBA',(8,8),(10,20,30,255)).save(self.png)
        self.items=[dict(material='seat01',png=str(self.png))]

    def test_texture_scope_readback_and_idempotence(self):
        out,receipt=repair.texture_bundle(self.data,self.export/'manifest.json',self.items)
        self.assertNotEqual(out,self.data);self.assertTrue(receipt['outside_stored_span_identical']);self.assertTrue(receipt['readback_exact'])
        again,second=repair.texture_bundle(out,self.export/'manifest.json',self.items)
        self.assertEqual(out,again);self.assertTrue(second['already_applied']);self.assertEqual(second['decoded_scope']['changed_decoded_bytes'],0)

    def test_other_chunks_compose(self):
        altered=bytes([self.data[0]^1])+self.data[1:]
        # Chunk tag remains printable so the reader still admits the unrelated resource.
        out,_=repair.texture_bundle(altered,self.export/'manifest.json',self.items)
        self.assertEqual(out[:48],altered[:48]);self.assertEqual(out[-48:],altered[-48:])

    def test_unknown_texture_and_wrong_dimensions_refuse(self):
        with self.assertRaises(ValueError):repair.texture_bundle(self.data,self.export/'manifest.json',[dict(material='field',png=str(self.png))])
        Image.new('RGBA',(4,4),(1,2,3,255)).save(self.png)
        with self.assertRaises(ValueError):repair.texture_bundle(self.data,self.export/'manifest.json',self.items)

    def test_batch_preflight_refuses_before_output(self):
        inputs=self.root/'input';inputs.mkdir();(inputs/'s07dd.iff').write_bytes(self.data)
        plan=self.root/'plan.json';entry=dict(name='s07dd.iff',manifest='export/manifest.json',textures=[dict(material='seat01',png='seat.png')])
        plan.write_text(json.dumps(dict(schema='b765_s1_repair_plan/v1',entries=[entry,entry])))
        with self.assertRaises(ValueError):repair.main(['--input-dir',str(inputs),'--output-dir',str(self.root/'output'),'--plan',str(plan),'--receipt',str(self.root/'receipt.json')])
        self.assertFalse((self.root/'output').exists());self.assertFalse((self.root/'receipt.json').exists())

    def test_aliases_cannot_silently_replace_each_others_texture(self):
        with self.assertRaises(ValueError):repair.texture_bundle(self.data,self.export/'manifest.json',self.items+[dict(material='seat_alias',png=str(self.png))])

    def test_receipt_cannot_overwrite_game_input_output_or_plan(self):
        inputs=self.root/'input';inputs.mkdir();(inputs/'s07dd.iff').write_bytes(self.data)
        plan=self.root/'plan.json';entry=dict(name='s07dd.iff',manifest='export/manifest.json',textures=[dict(material='seat01',png='seat.png')])
        plan.write_text(json.dumps(dict(schema='b765_s1_repair_plan/v1',entries=[entry])))
        for receipt in (inputs/'s07dd.iff',self.root/'output/s07dd.iff',plan,self.export/'manifest.json'):
            with self.assertRaises(ValueError):repair.main(['--input-dir',str(inputs),'--output-dir',str(self.root/'output'),'--plan',str(plan),'--receipt',str(receipt)])
            self.assertEqual((inputs/'s07dd.iff').read_bytes(),self.data)
            self.assertFalse((self.root/'output').exists())


if __name__=='__main__':unittest.main()

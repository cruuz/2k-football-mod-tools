"""Scoped field authoring, native refusal/idempotence and private midfield vertices."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import numpy as np
from PIL import Image
from mod_editor.core import nfl2k5_modern_venues_2026 as mv
from mod_editor.core import nfl2k5_mercedes_benz_model as mb
from mod_editor.core import nfl2k5_scne_builder as sb
from mod_editor.core import nfl2k5_modern_metlife as ml
from tools.b765 import s2_author_field as author, s2_repair as repair


class ScopeAndPlacementTests(unittest.TestCase):
    def fixture(self):
        command=sb.encode_words(sb.TRIANGLE_STRIP,[0,1,2,3])
        data=bytearray(256);data[:len(command)]=command
        for i,(x,z) in enumerate([(-1,-1),(1,-1),(-1,1),(1,1)]):
            struct.pack_into("<3f",data,128+i*12,x*423.2652893066406,0,z*457.5841064453125)
        rec=dict(shapes=[dict(name="D_graphic_overlays",index=0,vertex_streams=[
            dict(stream_index=0,offset=128,stride=12)])],submeshes=[dict(shape_index=0,
            material_name="center_logo",command_offset=0,primary_command_word_count=len(command)//4)])
        return data,rec

    def test_midfield_scaling_keeps_y_draws_and_every_unowned_byte(self):
        data,rec=self.fixture();before=bytes(data)
        ranges=mb.scale_midfield(data,rec,1.6)
        self.assertEqual(sum(b-a for a,b in ranges),32)
        self.assertEqual(repair.outside_digest(data,ranges),repair.outside_digest(before,ranges))
        for i in range(4):
            x,y,z=struct.unpack_from("<3f",data,128+i*12)
            self.assertEqual(y,0)
            self.assertAlmostEqual(abs(x),677.22446,places=3)
            self.assertAlmostEqual(abs(z),732.13457,places=3)
        with self.assertRaises(ValueError):mb.scale_midfield(data,rec,1.6)

    def test_midfield_shared_draw_refuses_before_mutation(self):
        data,rec=self.fixture();before=bytes(data)
        other=dict(rec["submeshes"][0],material_name="numbers")
        rec["submeshes"].append(other)
        with self.assertRaises(ValueError):mb.scale_midfield(data,rec,1.6)
        self.assertEqual(bytes(data),before)

    def test_default_placement_is_byte_identical(self):
        data,rec=self.fixture();before=bytes(data)
        self.assertEqual(mb.scale_midfield(data,rec,1.0),[])
        self.assertEqual(bytes(data),before)

    def test_field_override_preserves_all_other_teams_and_stadium_art(self):
        with tempfile.TemporaryDirectory() as temp:
            src=Path(temp)/"input";dst=Path(temp)/"output"
            v=src/"ATL/venue";v.mkdir(parents=True)
            p=v/"native.png";Image.new("RGBA",(8,4),(10,20,30,255)).save(p)
            (v/"wall.txt").write_bytes(b"unselected stadium source")
            (src/"OTHER").mkdir();(src/"OTHER/preserved.dat").write_bytes(b"other team bytes")
            doc=dict(schema=mv.ART_SCHEMA,team="ATL",venue_prefix="s01",items=[dict(scene="field",
                material="endzone_N_M",size=[8,4],file="native.png",layer="overlay",sha256=author.sha(p.read_bytes()))])
            (v/"manifest.json").write_text(json.dumps(doc))
            image=Image.new("RGBA",(64,32),(120,20,30,255))
            receipt=author.install_overrides(src,dst,"s01",{"endzone_N_M":image})
            self.assertEqual((dst/"ATL/venue/wall.txt").read_bytes(),b"unselected stadium source")
            self.assertEqual((dst/"OTHER/preserved.dat").read_bytes(),b"other team bytes")
            self.assertEqual((src/"ATL/venue/manifest.json").read_text(),json.dumps(doc))
            self.assertEqual(receipt["selected"],["endzone_N_M"])
            self.assertEqual(mb.team_field_art(dst)["endzone_N_M"][0,0].tolist(),[120,20,30,255])
            with self.assertRaises(ValueError):author.install_overrides(src,dst,"s01",{"endzone_N_M":image})

    def test_stadium_override_refuses_without_copying(self):
        with tempfile.TemporaryDirectory() as temp:
            src=Path(temp)/"input";src.mkdir();dst=Path(temp)/"output"
            Image.new("RGBA",(8,4)).save(src/"native.png")
            doc=dict(schema=mv.ART_SCHEMA,team="ATL",venue_prefix="s01",items=[dict(scene="field",
                material="endzone_N_M",size=[8,4],file="native.png",layer="overlay",
                sha256=author.sha((src/"native.png").read_bytes()))])
            (src/"manifest.json").write_text(json.dumps(doc))
            with self.assertRaises(ValueError):
                author.install_overrides(src,dst,"s01",{"wall01":Image.new("RGBA",(64,32))})
            self.assertFalse(dst.exists())


class ActualNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=os.environ.get("S2_NATIVE_EVIDENCE")
        if not root:raise unittest.SkipTest("Set S2_NATIVE_EVIDENCE to the private s2 evidence directory")
        cls.root=Path(root)
        cls.doc=json.loads(repair.MANIFEST.read_text())
        cls.team=mb.team_field_art(cls.root/"art_refined")
        cls.after=(cls.root/"native_after_v3/s01dd.iff").read_bytes()
        cls.before=(cls.root/"native_before/s01dd.iff").read_bytes()
        chunk=ml.bundle_scenes(cls.after)["field"]
        rec,decoded=ml._scene(cls.after,chunk)
        cls.payloads={}
        for key in repair.MATERIALS:
            row=ml.texture_rows(rec)[key]
            start=chunk.system_bytes+int(row["pixel_offset"])
            end=chunk.system_bytes+int(row["palette_offset"])+1024
            rgba,_=ml.read_p8(decoded,chunk.system_bytes,row)
            cls.payloads[key]=dict(bytes=decoded[start:end],rgba=rgba,size=[row["width"],row["height"]],mip_levels=row["mip_levels"])

    def test_native_repair_reproduces_all_pinned_bytes(self):
        out,receipt=repair.repair_bundle(self.before,"s01dd.iff",self.team,self.doc,payloads=self.payloads)
        self.assertEqual(out,self.after)
        self.assertTrue(all(t["studio_native_exact"] for t in receipt["textures"]))

    def test_stadium_overlap_survives_repair(self):
        data=self.before[:-1]+bytes([self.before[-1]^1])
        out,_=repair.repair_bundle(data,"s01dd.iff",self.team,self.doc,payloads=self.payloads)
        self.assertEqual(out,self.after[:-1]+bytes([self.before[-1]^1]))

    def test_foreign_compiled_payload_refuses(self):
        payloads=copy.deepcopy(self.payloads)
        data=payloads["endzone_N_M"]["bytes"]
        payloads["endzone_N_M"]["bytes"]=bytes([data[0]^1])+data[1:]
        with self.assertRaises(ValueError):
            repair.repair_bundle(self.before,"s01dd.iff",self.team,self.doc,payloads=payloads)

    def test_exact_native_output_is_idempotent(self):
        out,receipt=repair.repair_bundle(self.after,"s01dd.iff",self.team,self.doc)
        self.assertEqual(out,self.after)
        self.assertEqual(receipt["state"],"already_applied")

    def test_stadium_overlap_survives_already_applied_field(self):
        data=self.after[:-1]+bytes([self.after[-1]^1])
        out,receipt=repair.repair_bundle(data,"s01dd.iff",self.team,self.doc)
        self.assertEqual(out,data)
        self.assertEqual(receipt["state"],"already_applied")

    def test_unexpected_field_and_art_refuse(self):
        foreign=bytearray(self.before);foreign[100]^=1
        with self.assertRaises(ValueError):repair.repair_bundle(bytes(foreign),"s01dd.iff",self.team,self.doc)
        team=copy.deepcopy(self.team);team["endzone_N_M"][0,0,0]^=1
        with self.assertRaises(ValueError):repair.repair_bundle(self.before,"s01dd.iff",team,self.doc)

    def test_all9_outputs_keep_native_decoder_inside_original_allocation(self):
        from tools.b765.s2_native_decoder import prove_chunk
        xbe=ROOT/"extracted/ESPN NFL 2K5 (USA)/default.xbe"
        if not xbe.is_file():
            self.skipTest("Actual native decoder check needs recognized retail XBE")
        for name,pin in self.doc["bundles"].items():
            with self.subTest(name=name):
                data=(self.root/"native_after_v3"/name).read_bytes()
                chunk=ml.bundle_scenes(data)["field"]
                self.assertEqual(repair.sha(ml.scene_span(data,chunk)),pin["after_field_sha256"])
                proof=prove_chunk(data,chunk,xbe)
                self.assertTrue(proof["exact_native_output"])
                self.assertTrue(proof["guard_unchanged"])
                self.assertLessEqual(proof["max_read"],proof["decoded_bytes"]+proof["scratch"])


if __name__=="__main__":unittest.main()

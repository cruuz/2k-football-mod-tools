"""Scope, original-quad guards and same-variant turf for existing field paint."""
from __future__ import annotations
import json
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from mod_editor.core import nfl2k5_modern_venues_2026 as mv
from mod_editor.core import nfl2k5_modern_metlife as ml
from tools.b765 import s2_existing_fields as repair


class SelectionTests(unittest.TestCase):
    def test_manifest_scope_types_and_default_digest(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);png=root/"panel.png"
            Image.new("RGBA",(256,128)).save(png)
            items=[dict(scene="field",material="endzone_"+end+"_"+part,size=[256,128],
                        file="panel.png",layer="overlay",sha256=mv.sha(png.read_bytes())) for end in "NS" for part in "LMR"]
            doc=dict(schema=mv.ART_SCHEMA,team="TB",venue_prefix="s27",items=items)
            path=root/"manifest.json"
            def load():
                path.write_text(json.dumps(doc));return mv.load_art(root)["venues"][doc["venue_prefix"]]
            baseline=load()["digest"]
            doc["endzone_turf_from_field"]=False;doc["midfield_scale_xz"]=None
            self.assertEqual(load()["digest"],baseline)
            doc["endzone_turf_from_field"]=True;doc["midfield_scale_xz"]=[1.49,1.88]
            self.assertNotEqual(load()["digest"],baseline)
            doc["venue_prefix"]="s29"
            with self.assertRaisesRegex(ValueError,"reviewed s27"):load()
            doc["venue_prefix"]="s27";doc["midfield_scale_xz"]=[True,1.88]
            with self.assertRaisesRegex(ValueError,"scale values"):load()
            doc["midfield_scale_xz"]=[1.49,1.88];doc["endzone_turf_from_field"]=1
            with self.assertRaisesRegex(ValueError,"boolean"):load()
            doc["endzone_turf_from_field"]=True;doc["items"]=items[:-1]
            with self.assertRaisesRegex(ValueError,"all six"):load()

    def test_unreviewed_geometry_refuses_before_parsing(self):
        for prefix,scale in (("s29",[1.49,1.88]),("s27",[1.49,3]),("s27",[True,1])):
            with self.subTest(prefix=prefix,scale=scale),self.assertRaisesRegex(ValueError,"reviewed s27"):
                mv.scale_existing_midfield(bytearray(),{},prefix,scale)

    def test_washington_shared_donor_is_explicit_and_strict(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);png=root/"panel.png"
            Image.new("RGBA",(256,128)).save(png)
            items=[dict(scene="field",material="endzone_N_"+part,size=[256,128],
                        file="panel.png",layer="overlay",sha256=mv.sha(png.read_bytes())) for part in "LMR"]
            doc=dict(schema=mv.ART_SCHEMA,team="WAS",venue_prefix="s29",items=items)
            path=root/"manifest.json"
            def load():
                path.write_text(json.dumps(doc));return mv.load_art(root)["venues"][doc["venue_prefix"]]
            baseline=load()["digest"]
            self.assertEqual(repair.source_turf_donors(root,{"s29":[]}),{})
            self.assertEqual(mv.field_normal_loan_prefixes(root),())
            doc["endzone_turf_from_field"]=False
            self.assertEqual(load()["digest"],baseline)
            doc["endzone_turf_from_field"]=True
            self.assertNotEqual(load()["digest"],baseline)
            self.assertEqual(repair.source_turf_donors(root,{"s29":[]}),{"s29":True})
            self.assertEqual(mv.field_normal_loan_prefixes(root),("s29",))
            doc["items"]=items[:-1]
            with self.assertRaisesRegex(ValueError,"all three shared North"):load()
            doc["items"]=items;doc["endzone_turf_from_field"]=1
            with self.assertRaisesRegex(ValueError,"boolean"):load()
            doc["endzone_turf_from_field"]=True;doc["venue_prefix"]="s28"
            with self.assertRaisesRegex(ValueError,"reviewed only for s27/s29"):load()

    def test_explicit_turf_background_keeps_the_donor_grain(self):
        import numpy as np
        current=np.full((8,8,4),(167,25,48,255),dtype=np.uint8)
        donor=np.full((8,8,4),(60,110,55,255),dtype=np.uint8)
        donor[::2,::2,:3]+=10
        transparent=np.zeros_like(current)
        item=dict(layer="overlay",key="endzone_N_L",scene="field")
        got=mv.compose(item,current,current,transparent,"d",endzone_base=donor)
        self.assertTrue(np.array_equal(got,donor))
        ordinary=mv.compose(item,current,current,transparent,"d")
        self.assertFalse(np.array_equal(ordinary,donor))


class OriginalQuadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail=Path(__file__).resolve().parents[2]/"extracted/ESPN NFL 2K5 (USA)"
        if not retail.is_dir():raise unittest.SkipTest("hydrated retail archive is required")
        cls.inputs={}
        with mv._outer_image()(retail) as archive:
            for pin in mv.venues()["s27"]["bundles"]:
                e=mv._entry(archive,pin);b=archive.read(e.virtual_offset,e.size)
                if mv.sha(b)!=pin["retail_sha256"]:raise ValueError("Unexpected retail source")
                c=ml.bundle_scenes(b)["field"];cls.inputs[pin["name"]]=ml._scene(b,c)

    def test_all_nine_only_eight_original_floats_move(self):
        for name,(rec,data) in self.inputs.items():
            with self.subTest(name=name):
                out=bytearray(data);ranges=mv.scale_existing_midfield(out,rec,"s27",[1.49,1.88])
                self.assertEqual(len(ranges),8);self.assertEqual(sum(b-a for a,b in ranges),32)
                self.assertEqual(repair.outside_sha(data,ranges),repair.outside_sha(out,ranges))
                self.assertNotEqual(bytes(out),data)

    def test_second_scale_refuses_without_writing(self):
        rec,data=next(iter(self.inputs.values()));out=bytearray(data)
        mv.scale_existing_midfield(out,rec,"s27",[1.49,1.88]);before=bytes(out)
        with self.assertRaisesRegex(ValueError,"original placement"):
            mv.scale_existing_midfield(out,rec,"s27",[1.49,1.88])
        self.assertEqual(bytes(out),before)

    def test_foreign_original_position_refuses_without_partial_write(self):
        import struct
        rec,data=next(iter(self.inputs.values()));probe=bytearray(data)
        ranges=mv.scale_existing_midfield(probe,rec,"s27",[1.49,1.88]);out=bytearray(data)
        struct.pack_into("<f",out,ranges[-1][0],999);before=bytes(out)
        with self.assertRaisesRegex(ValueError,"original placement"):
            mv.scale_existing_midfield(out,rec,"s27",[1.49,1.88])
        self.assertEqual(bytes(out),before)


class ActualNativeRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder=os.environ.get("S2_NATIVE_EVIDENCE")
        if not folder:raise unittest.SkipTest("S2_NATIVE_EVIDENCE supplies private native evidence")
        cls.root=Path(folder);cls.doc=json.loads(repair.PINS.read_text());cls.before={};cls.after={};cls.compiled={}
        for prefix,stem in (("s27","tb"),("s29","was")):
            payloads=cls.root/os.environ.get("S2_"+stem.upper()+"_PAYLOADS",stem+"_source_payloads")
            meta=json.loads((payloads/"payload_metadata.json").read_text())
            for name,values in meta.items():
                cls.before[name]=(cls.root/"native_before"/name).read_bytes()
                cls.after[name]=(cls.root/os.environ.get("S2_"+stem.upper()+"_OUTPUTS",stem+"_native_final")/name).read_bytes()
                cls.compiled[name]={key:dict(value,data=(payloads/(name+"_"+key+".p8")).read_bytes()) for key,value in values.items()}

    def test_all_eighteen_reproduce_frozen_fields_and_exact_outside_bytes(self):
        self.assertEqual(len(self.before),18)
        for name,data in self.before.items():
            with self.subTest(name=name):
                out,row=repair.repair_bundle(data,name,self.compiled[name],self.doc)
                self.assertEqual(out,self.after[name]);self.assertTrue(row["outside_scope_identical"])
                self.assertTrue(row["wrapper_scratch_and_decoded_sizes_identical"])
                self.assertEqual(row["wrapper_identical"],name.startswith("s27"))
                self.assertTrue(row["studio_native_payload_exact"])

    def test_all_eighteen_are_idempotent(self):
        for name,data in self.after.items():
            with self.subTest(name=name):
                out,row=repair.repair_bundle(data,name,self.compiled[name],self.doc)
                self.assertEqual(out,data);self.assertTrue(row["already_applied"])

    def test_independent_stadium_suffix_stacks_with_paint(self):
        for name in ("s27dd.iff","s29dd.iff"):
            data=self.before[name][:-1]+bytes([self.before[name][-1]^1])
            expected=self.after[name][:-1]+bytes([self.after[name][-1]^1])
            out,_=repair.repair_bundle(data,name,self.compiled[name],self.doc)
            self.assertEqual(out,expected)

    def test_unexpected_field_and_payload_bytes_refuse(self):
        name="s27dd.iff";doc=copy.deepcopy(self.doc);doc["bundles"][name]["before_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"owned field"):
            repair.repair_bundle(self.before[name],name,self.compiled[name],doc)
        payload=copy.deepcopy(self.compiled[name]);key=next(iter(payload));p=payload[key]
        p["data"]=bytes([p["data"][0]^1])+p["data"][1:]
        with self.assertRaisesRegex(ValueError,"payload bytes"):
            repair.repair_bundle(self.before[name],name,payload,self.doc)
        p["sha256"]=repair.sha(p["data"])
        with self.assertRaisesRegex(ValueError,"Studio field"):
            repair.repair_bundle(self.before[name],name,payload,self.doc)

    def test_washington_normal_is_hash_gated_and_decoded_exact(self):
        for name,before in self.before.items():
            if not name.startswith("s29"):continue
            with self.subTest(name=name):
                _field,layer,normal,decoded=repair.midfield.pit_sites(before)
                _newfield,newlayer,newnormal,newdecoded=repair.midfield.pit_sites(self.after[name])
                self.assertEqual(decoded,newdecoded)
                self.assertEqual(ml.scene_span(before,layer),ml.scene_span(self.after[name],newlayer))
                self.assertEqual(normal.end_offset,newnormal.end_offset)
                self.assertEqual(self.after[name][normal.end_offset:],before[normal.end_offset:])
                self.assertEqual(normal.stored_size-newnormal.stored_size,1680)
                foreign=bytearray(before);foreign[normal.body_offset+128]^=1
                with self.assertRaisesRegex(ValueError,"owned field"):
                    repair.repair_bundle(bytes(foreign),name,self.compiled[name],self.doc)

    def test_reviewed_final_source_pixels_match_all_pins(self):
        art=self.root/os.environ.get("S2_REVIEWED_ART","art_final_s2_reviewed")
        self.assertEqual(repair.source_pixels(art,self.doc["selected"]),self.doc["source_rgba_sha256"])
        self.assertEqual(repair.source_turf_donors(art,self.doc["selected"]),self.doc["endzone_turf_from_field"])


if __name__=="__main__":unittest.main()

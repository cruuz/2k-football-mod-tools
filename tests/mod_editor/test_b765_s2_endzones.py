"""Meaningful scene-preservation checks for independent end-zone allocations."""
from __future__ import annotations

import copy
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import nfl2k5_split_endzone_art as ez
from mod_editor.core import nfl2k5_scne_builder as sb
from tools.b765 import s2_endzones as repair


class SceneScopeTests(unittest.TestCase):
    def test_manifest_refuses_incomplete_or_unreviewed_split_sources(self):
        import json
        from PIL import Image
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);image=root/"panel.png"
            Image.new("RGBA",(256,128),(0,0,0,255)).save(image)
            items=[dict(scene="field",material=key,layer="full",size=[256,128],
                        file="panel.png",sha256=repair.sha(image.read_bytes())) for key in repair.KEYS]
            manifest=root/"manifest.json"
            doc=dict(schema=mv.ART_SCHEMA,team="HOU",venue_prefix="s37",items=items,split_shared_endzones=True)
            manifest.write_text(json.dumps(doc));self.assertTrue(mv.load_art(root)["venues"]["s37"]["split_shared_endzones"])
            doc["items"]=items[:-1];manifest.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError,"all six"):
                mv.load_art(root)
            doc["items"]=items;doc["venue_prefix"]="s00";manifest.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError,"not reviewed"):
                mv.load_art(root)
            doc["venue_prefix"]="s37";doc["split_shared_endzones"]="true";manifest.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError,"must be a boolean"):
                mv.load_art(root)

    def test_unreviewed_venue_refuses_before_parsing(self):
        with self.assertRaisesRegex(ValueError, "not been reviewed"):
            ez.split_span(b"invalid", "s00dd.iff")

    def test_manifest_unselected_route_is_exact_noop(self):
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        self.assertEqual(mv._split_shared_endzones(b"unparsed", "s37dd.iff", {}, {}),
                         (b"unparsed", None))

    def test_missing_material_pair_refuses(self):
        with self.assertRaisesRegex(ValueError, "missing or repeated"):
            ez.pairs(SimpleNamespace(materials=[]))

    def test_textureless_material_pair_refuses(self):
        scene = SimpleNamespace(materials=[
            SimpleNamespace(name="endzone_N_L", texture=1),
            SimpleNamespace(name="endzone_S_L", texture=None)])
        with self.assertRaisesRegex(ValueError, "lacks its P8"):
            ez.pairs(scene)

    def test_all_nine_native_fields_preserve_old_records_and_loader_wrapper(self):
        root = os.environ.get("S2_NATIVE_EVIDENCE")
        if not root:
            self.skipTest("S2_NATIVE_EVIDENCE supplies extracted native fields")
        from mod_editor.core import nfl2k5_modern_metlife as ml
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        tx = ml._tools()[0]
        rows = []
        for code in mv.CODES:
            name = "s37" + code + ".iff"
            with self.subTest(name=name):
                data = (Path(root) / "native_before" / name).read_bytes()
                chunk = ml.bundle_scenes(data)["field"]
                span = ml.scene_span(data, chunk)
                decoded, _ = tx.decode_chunk(data, chunk)
                before = sb.parse(decoded, chunk.system_bytes, secondary=True)
                after, receipt = ez.split_span(span, name)
                new_chunk = tx.parse_chunks(after, allow_trailing=True)[0]
                decoded, _ = tx.decode_chunk(after, new_chunk)
                parsed = sb.parse(decoded, new_chunk.system_bytes, secondary=True)
                self.assertEqual(len(after), len(span))
                self.assertEqual(after[:8] + after[16:32], span[:8] + span[16:32])
                self.assertTrue(receipt["existing_scene_preserved"])
                for old, new in zip(before.textures, parsed.textures):
                    self.assertEqual(old.pixels, new.pixels)
                    self.assertEqual(old.palette, new.palette)
                for north, south in ez.pairs(parsed):
                    self.assertNotEqual(north.texture, south.texture)
                    self.assertEqual(parsed.textures[north.texture].pixels,
                                     parsed.textures[south.texture].pixels)
                    self.assertEqual(parsed.textures[north.texture].palette,
                                     parsed.textures[south.texture].palette)
                ez.assert_original_scene(before, parsed)
                repeated, replay = ez.split_span(after, name)
                self.assertEqual(repeated, after)
                self.assertFalse(replay["added"])
                rows.append(dict(name=name, **receipt))
        import json
        (Path(root) / "HOU_split_module_proof.json").write_text(json.dumps(rows, indent=2) + "\n")


class ActualRepairTests(unittest.TestCase):
    PREFIX="s37"
    NATIVE_FOLDER="hou_native_final"
    STUDIO_FOLDER="hou_studio_candidate"
    @classmethod
    def setUpClass(cls):
        import json
        root=os.environ.get("S2_NATIVE_EVIDENCE")
        if not root:raise unittest.SkipTest("S2_NATIVE_EVIDENCE supplies private native evidence")
        cls.root=Path(root);cls.doc=json.loads(repair.PINSETS[cls.PREFIX].read_text())
        cls.names=sorted(cls.doc["bundles"])
        cls.before={n:(cls.root/"native_before"/n).read_bytes() for n in cls.names}
        cls.after={n:(cls.root/cls.NATIVE_FOLDER/n).read_bytes() for n in cls.names}
        cls.compiled={n:repair.payloads((cls.root/cls.STUDIO_FOLDER/n).read_bytes()) for n in cls.names}

    def test_all_nine_outputs_match_studio_and_frozen_native(self):
        for name in self.names:
            with self.subTest(name=name):
                out,row=repair.repair_bundle(self.before[name],name,self.compiled[name],self.doc)
                self.assertEqual(out,self.after[name])
                self.assertTrue(row["outside_scope_identical"])
                self.assertTrue(row["studio_native_payload_exact"])
                self.assertTrue(row["detail"]["existing_scene_preserved"])

    def test_all_nine_outputs_are_idempotent(self):
        for name in self.names:
            with self.subTest(name=name):
                out,row=repair.repair_bundle(self.after[name],name,self.compiled[name],self.doc)
                self.assertEqual(out,self.after[name]);self.assertTrue(row["already_applied"])

    def test_independent_stadium_suffix_survives_repair_and_idempotence(self):
        name=self.names[0];data=self.before[name][:-1]+bytes([self.before[name][-1]^1])
        expected=self.after[name][:-1]+bytes([self.after[name][-1]^1])
        out,_=repair.repair_bundle(data,name,self.compiled[name],self.doc)
        self.assertEqual(out,expected)
        out,row=repair.repair_bundle(out,name,self.compiled[name],self.doc)
        self.assertEqual(out,expected);self.assertTrue(row["already_applied"])

    def test_foreign_payload_bytes_and_hashes_refuse(self):
        name=self.names[0];payload=copy.deepcopy(self.compiled[name]);p=payload[repair.KEYS[0]]
        p["pixels"]=bytes([p["pixels"][0]^1])+p["pixels"][1:]
        with self.assertRaisesRegex(ValueError,"payload bytes"):
            repair.repair_bundle(self.before[name],name,payload,self.doc)
        p["sha256"]=repair.sha(p["pixels"]+p["palette"])
        with self.assertRaisesRegex(ValueError,"Unexpected Studio"):
            repair.repair_bundle(self.before[name],name,payload,self.doc)

    def test_foreign_owned_hash_and_resource_refuse(self):
        name=self.names[0];doc=copy.deepcopy(self.doc);doc["bundles"][name]["before_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"Unexpected owned field"):
            repair.repair_bundle(self.before[name],name,self.compiled[name],doc)
        with self.assertRaisesRegex(ValueError,"Unowned"):
            repair.repair_bundle(self.before[name],"s03dd.iff",self.compiled[name],self.doc)

    def test_reviewed_source_pixels_match_pins(self):
        self.assertEqual(repair.source_pixels(self.root/"art_final_s2_loan",self.PREFIX),self.doc["source_rgba_sha256"])

    def test_lossless_donor_and_original_scene_records(self):
        from mod_editor.core import nfl2k5_midfield_art as mf
        from mod_editor.core import nfl2k5_modern_metlife as ml
        tx=ml._tools()[0]
        for name in self.names:
            with self.subTest(name=name):
                before,after=self.before[name],self.after[name]
                bc,bs=repair.field_scene(before);ac,as_=repair.field_scene(after)
                painted=[as_.materials[as_.material_index(k)].texture for k in repair.KEYS]
                ez.assert_original_scene(bs,as_,painted)
                self.assertEqual(before[:bc.offset],after[:ac.offset])
                preserved_header = 4 if self.PREFIX in ez.LOAN_VENUES else 8
                self.assertEqual(ml.scene_span(before,bc)[:preserved_header]+ml.scene_span(before,bc)[16:32],
                                 ml.scene_span(after,ac)[:preserved_header]+ml.scene_span(after,ac)[16:32])
                if self.PREFIX in ez.LOAN_VENUES:
                    _bf,bl,bn,bd=mf.pit_sites(before);_af,al,an,ad=mf.pit_sites(after)
                    self.assertEqual(ml.scene_span(before,bl),ml.scene_span(after,al))
                    self.assertEqual(bd,ad)
                    self.assertEqual(bn.end_offset,an.end_offset)
                    self.assertEqual(before[bn.end_offset:],after[an.end_offset:])
                    self.assertTrue(an.compressed);self.assertEqual(an.overlap_scratch_bytes,0)
                    _compressed,loan=mf.compress_detail_normal(ml.scene_span(before,bn))
                    self.assertEqual(ac.stored_size,bc.stored_size+loan["loan"])
                else:
                    self.assertEqual(before[bc.end_offset:],after[ac.end_offset:])


class DetroitRepairTests(ActualRepairTests):
    PREFIX="s09"
    NATIVE_FOLDER="det_native_final"
    STUDIO_FOLDER="endzone_source_loan18_final_v3"


class ClevelandRepairTests(ActualRepairTests):
    PREFIX="s30"
    NATIVE_FOLDER="cle_native_final"
    STUDIO_FOLDER="endzone_source_loan18_final_v3"


if __name__ == "__main__":
    unittest.main()

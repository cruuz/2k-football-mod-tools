"""Standalone v7 resource, native-driver data and transaction checks. No emulator."""
from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from mod_editor.core import nfl2k5_scorebug_ingame as r
from mod_editor.core import nfl2k5_scorebug_source_art as source_art

EXTRACTION=Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION","/media/noah/Storage/for codex 1.0/extracted"))/"ESPN NFL 2K5 (USA)"
PACK=EXTRACTION/"vc_53450030"/"0"
XBE=EXTRACTION/"default.xbe"


class MetadataTests(unittest.TestCase):
    def test_team_asset_codes_are_not_roster_ids(self):
        self.assertEqual(len(r.TEAM_LOGOS),32)
        self.assertEqual(r.TEAM_LOGOS["LV"]["asset_code"],"20")
        self.assertEqual(r.TEAM_LOGOS["LV"]["roster_id"],22)
        self.assertEqual(r.TEAM_LOGOS["HOU"]["asset_code"],"37")
        self.assertEqual(r.TEAM_LOGOS["HOU"]["roster_id"],29)
        self.assertEqual(r.TEAM_LOGOS["PIT"]["asset_code"],"22")
        self.assertEqual({v["roster_id"] for v in r.TEAM_LOGOS.values()},set(range(32)))

    def test_availability_does_not_depend_on_old_missing_audit(self):
        with mock.patch.object(source_art,"AUDIT",Path("no-such-audit")):
            self.assertTrue(source_art.available())

    def test_unrecognized_resource_and_corrupt_spans_refuse(self):
        for name in ("score_bug","score_buga"):
            self.assertEqual(r.status(b"broken",name),"foreign")
            with self.assertRaises(r.ScorebugError):
                r.apply(b"broken",name)
        with self.assertRaises(r.ScorebugError):
            r.status(b"","digital_font")


@unittest.skipUnless(PACK.is_file() and XBE.is_file(),"retail pack 0 and default.xbe evidence absent")
class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with PACK.open("rb") as stream:
            cls.inputs={}
            for name,record in r.RESOURCES.items():
                stream.seek(record["pack_offset"])
                cls.inputs[name]=stream.read(record["span_size"])
        cls.xbe=XBE.read_bytes()
        cls.replacements={n:r.apply(cls.inputs[n],n,inputs=cls.inputs)[0] for n in ("score_bug","score_buga")}
        cls.patched_xbe,cls.xbe_receipt=r.apply_xbe(cls.xbe)

    def test_resources_keep_wrapper_allocation_and_loader_overlap_budget(self):
        for name,after in self.replacements.items():
            before=self.inputs[name]
            self.assertEqual(after[:32],before[:32])
            self.assertEqual(len(after),len(before))
            self.assertEqual(r.status(after,name),"applied")
            self.assertEqual(r.apply(after,name)[0],after)
            chunk,decoded,info=r.decode(after)
            scratch=r.tx.minimum_vc_lz_overlap_scratch(after[32:32+info.consumed_bytes],chunk.stored_size,len(decoded))
            self.assertLessEqual(scratch,chunk.overlap_scratch_bytes)
            self.assertEqual(r.digest(after),r.PATCHED_SHA256[name])
            for offset in (0,20,32,len(after)-1):
                foreign=bytearray(after);foreign[offset]^=1
                self.assertEqual(r.status(bytes(foreign),name),"foreign")

    def test_scene_changes_only_geometry_uvs_and_text_transforms(self):
        before=r.decode(self.inputs["score_bug"])[1]
        after=r.decode(self.replacements["score_bug"])[1]
        L=r.layout
        for i,(a,b) in enumerate(zip(before,after)):
            if a==b:continue
            allowed=(L.S0<=i<L.S0+L.VCOUNT*6 or L.SHAPE+0x10<=i<L.SHAPE+0x2c
                     or (L.S1<=i<L.S1+L.VCOUNT*10 and 4<=(i-L.S1)%10<8)
                     or any(L.TBASE+t*0x70+0x40<=i<L.TBASE+t*0x70+0x5c for t in range(L.TCOUNT)))
            self.assertTrue(allowed,hex(i))
        self.assertEqual(L.strips(before),L.strips(after))
        self.assertEqual(len(after),16512)

    def test_scene_proportions_both_mark_modes_and_field_anchors(self):
        m=r.mesh(r.decode(self.inputs["score_bug"])[1])
        self.assertEqual(r.FRAME[2]-r.FRAME[0],480)
        self.assertEqual(r.FRAME[3]-r.FRAME[1],48)
        self.assertLess(424-r.FRAME[1],440)
        for v in range(274,286):
            self.assertEqual(m.pos[v],m.pos[v-12])
            self.assertEqual(m.uv_edit[v],m.uv_edit[v-12])
        self.assertGreater(r.WATERMARK[1],360)
        for name,xyz in r.ANCHORS.items():
            self.assertEqual(m.world[r.layout.T[name]],list(xyz))
        self.assertGreater(r.PILL[1],r.STRIP[3])

    def test_xbe_idempotence_guards_shared_shield_and_native_animation(self):
        self.assertEqual(r.xbe_status(self.xbe),"retail")
        self.assertEqual(r.xbe_status(self.patched_xbe),"applied")
        self.assertEqual(r.apply_xbe(self.patched_xbe)[0],self.patched_xbe)
        for section in r.bs._sections(self.patched_xbe):
            off=section.header_offset+36
            self.assertEqual(self.patched_xbe[off:off+20],r.bs.section_digest(self.patched_xbe,section))
        def at(va,fmt):
            return struct.unpack_from(fmt,self.patched_xbe,r.layout.sbpos.va_to_off(self.patched_xbe,va))
        self.assertAlmostEqual(at(0xa959f0,"<f")[0],.2)
        self.assertEqual(at(0xa959f8,"<f")[0],30.)
        self.assertAlmostEqual(at(0xa959e0,"<f")[0]*30,6.,places=6)
        self.assertEqual(at(0xa95cac,"<I"),at(0xa95cb4,"<I"))
        self.assertEqual(at(0xa95cac,"<I")[0],0xe6c6e8)
        # The animation code is pinned unchanged, not simulated by a replacement.
        for va,size,sha,label in r.XBE_GUARDS:
            off=r.layout.sbpos.va_to_off(self.patched_xbe,va)
            self.assertEqual(r.digest(self.patched_xbe[off:off+size]),sha,label)

    def test_mixed_xbe_and_foreign_driver_refuse(self):
        for va,old,new,label in r.xbe_specs():
            mixed=bytearray(self.xbe)
            off=r.layout.sbpos.va_to_off(self.xbe,va)
            mixed[off:off+len(new)]=new
            with self.assertRaises(r.ScorebugError,msg=label):
                r.apply_xbe(bytes(mixed))
        changed=bytearray(self.xbe)
        changed[r.layout.sbpos.va_to_off(self.xbe,r.XBE_GUARDS[0][0])]^=1
        with self.assertRaises(r.ScorebugError):r.apply_xbe(bytes(changed))

    def test_all_real_team_sources_pin_and_stage_both_sides(self):
        import zlib
        with PACK.open("rb") as stream:
            for team,record in r.TEAM_LOGOS.items():
                self.assertEqual(zlib.crc32(("FR"+record["asset_code"]+".IFF").encode("utf-16le"))&0xffffffff,record["outer_id"])
                stream.seek(record["pack_offset"])
                span=stream.read(record["span_size"])
                for side in ("away","home"):
                    data,receipt=r.stage_team_panel(span,team,side=side)
                    self.assertEqual(len(data),128*32*4)
                    self.assertEqual(r.digest(data),receipt["sha256"])
                    self.assertFalse(receipt["runtime_bound"])
                foreign=bytearray(span);foreign[-1]^=1
                with self.assertRaises(r.ScorebugError):r.stage_team_panel(bytes(foreign),team)

    def test_staged_binding_scene_has_independent_materials_and_cannot_be_mistaken_for_installed(self):
        span,receipt=r.stage_binding_scene(self.inputs["score_bug"])
        self.assertEqual(span[:32],self.inputs["score_bug"][:32])
        self.assertEqual(len(span),4832)
        self.assertFalse(receipt["runtime_bound"])
        self.assertEqual(r.status(span,"score_bug"),"foreign")
        data=r.decode(span)[1]
        for v in range(80,96):
            self.assertEqual(struct.unpack_from("<h",data,r.layout.S1+v*10+8)[0],0)
        self.assertEqual(r.layout.strips(data),r.layout.strips(r.decode(self.inputs["score_bug"])[1]))

    def test_transaction_refuses_late_foreign_resource_before_any_write_and_reapplies(self):
        from mod_editor.core import nfl2k5_throw_tuning as tt
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"sparse.iso"
            base=4096;xoff=base+r.PACK_SIZE
            with path.open("wb") as stream:
                for n,record in r.RESOURCES.items():
                    stream.seek(base+record["pack_offset"]);stream.write(self.inputs[n])
                stream.seek(xoff);stream.write(self.xbe)
            with mock.patch.object(r.layout.xc,"pack_extent",return_value=(base,r.PACK_SIZE)),mock.patch.object(tt,"image_xbe_extent",return_value=(xoff,len(self.xbe))):
                bad_off=base+r.RESOURCES["score_buga"]["pack_offset"]
                with path.open("r+b") as stream:stream.seek(bad_off);stream.write(b"NOPE")
                with self.assertRaises(r.ScorebugError):r.apply_in_place(path)
                with path.open("rb") as stream:
                    stream.seek(xoff);self.assertEqual(stream.read(len(self.xbe)),self.xbe)
                    stream.seek(base+r.RESOURCES["score_bug"]["pack_offset"])
                    self.assertEqual(stream.read(4832),self.inputs["score_bug"])
                with path.open("r+b") as stream:stream.seek(bad_off);stream.write(self.inputs["score_buga"])
                self.assertEqual(r.image_status(path),"retail")
                receipt=r.apply_in_place(path)
                self.assertEqual(receipt["state_before"],"retail")
                self.assertEqual(r.image_status(path),"applied")
                self.assertEqual(r.apply_in_place(path)["state_before"],"applied")
                with path.open("rb") as stream:
                    record=r.RESOURCES["shield_espn"]
                    stream.seek(base+record["pack_offset"])
                    self.assertEqual(stream.read(record["span_size"]),self.inputs["shield_espn"])


if __name__=="__main__":
    unittest.main()

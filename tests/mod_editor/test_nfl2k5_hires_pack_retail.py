"""Standalone optional retail evidence tests, bounded resource reads only."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from PIL import Image
from mod_editor.core import nfl2k5_hires_pack as pack
from mod_editor.core import nfl2k5_hires_texture as texture
from mod_editor.core import nfl2k5_music_archive as archive
from mod_editor.core import nfl2k5_models as models
from tools import nfl_scne_gltf as topology

SOURCE = Path(os.environ.get("NFL2K5_HIRES_TEST_IMAGE",
    "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))


class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_file():
            raise unittest.SkipTest("Retail NFL 2K5 XISO absent; set NFL2K5_HIRES_TEST_IMAGE to a retail evidence copy")
        with archive.Disc(SOURCE,descriptors=()) as disc:
            cls.resources,_ = pack._read(disc,(a.key for a in texture.PILOT_ASSETS))
            entry = disc.entries["default.xbe"]
            if entry.size > 16*archive.BLOCK:
                raise AssertionError("oversized XBE")
            cls.xbe = disc.read(entry.size,entry.byte_offset)
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.folder = Path(cls.temp.name).resolve()
        for a in texture.PILOT_ASSETS:
            size = a.native*2
            rgba = bytes(c for y in range(size) for x in range(size)
                         for c in (255 if x%2 else 0,255 if y%2 else 0,0,255))
            Image.frombytes("RGBA",(size,size),rgba).save(cls.folder/(a.key+".png"))

    def test_exact_pilot_pins_and_selector_names(self):
        for a in texture.PILOT_ASSETS:
            with self.subTest(asset=a.key):
                self.assertEqual(texture.sha(self.resources[a.key]),a.retail_sha256)
                info,_ = texture.inspect_span(self.resources[a.key],a)
                self.assertEqual(info["scale"],1)
        self.assertEqual(zlib.crc32("CT33D.IFF".encode("utf-16le"))&0xffffffff,texture.BY_KEY["field_logo"].name_id)
        self.assertEqual(zlib.crc32("00H0.IFF".encode("utf-16le"))&0xffffffff,texture.BY_KEY["helmet"].name_id)

    def test_consumer_ranges_refuse_every_tampered_pin(self):
        result = pack.validate_consumer_xbe(self.xbe,tuple(texture.BY_KEY))
        self.assertEqual(result["xbe_sha256"],"73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9")
        self.assertFalse(result["exhaustive_runtime_consumers_proved"])
        for row in result["ranges"]:
            bad = bytearray(self.xbe)
            bad[row["offset"]] ^= 1
            with self.subTest(address=hex(row["address"])),self.assertRaisesRegex(ValueError,"Foreign .* consumer"):
                pack.validate_consumer_xbe(bytes(bad),tuple(texture.BY_KEY))

    def test_native_and_2x_mips_descriptor_isolation_and_replay(self):
        enlarged,receipt = pack.apply(self.resources,self.folder)
        self.assertEqual(receipt["memory"]["selected_video_bytes"],718336)
        self.assertEqual(receipt["memory"]["video_delta"],536448)
        for a in texture.PILOT_ASSETS:
            raw = enlarged[a.key]
            decoded,_ = texture.txtr.decode_chunk(raw,texture.txtr.parse_chunks(raw)[0])
            original,_ = texture.txtr.decode_chunk(self.resources[a.key],texture.txtr.parse_chunks(self.resources[a.key])[0])
            changed = {i for i,(l,r) in enumerate(zip(original[:128],decoded[:128])) if l!=r}
            self.assertLessEqual(changed,set(range(a.descriptor+8,a.descriptor+16)))
            self.assertEqual(len(raw)%16,0)
            info,_ = texture.inspect_span(raw,a)
            self.assertEqual(info["mips"][-1]["width"],128 if a.key=="scorebug" else 16)
        self.assertEqual(pack.apply(enlarged,self.folder)[0],enlarged)
        native,native_receipt = pack.apply(enlarged,self.folder,scale=1)
        self.assertEqual(native_receipt["memory"]["selected_video_bytes"],181888)
        self.assertEqual(pack.apply(native,self.folder)[0],enlarged)

    def test_scene_receipts_and_normalized_uv_lanes(self):
        evidence = json.loads((ROOT/"reports/hires_pack_consumers.v1.json").read_text())
        selected = {"o346c78","o3c113","o3c115","o3179c0"}
        receipts = {r["key"]:r for r in evidence["scenes"] if r["key"] in selected}
        self.assertEqual(set(receipts),selected)
        with archive.Disc(SOURCE,descriptors=()) as disc:
            for key,expected in receipts.items():
                outer,chunk = models.parse_model_key(key)
                entry = disc.archive_entries[outer]
                self.assertLess(entry.size,32*archive.BLOCK)
                container = disc.read_entry_range(entry,0,entry.size)
                _,_,raw = list(archive.chunks(container))[chunk]
                self.assertEqual(texture.sha(raw),expected["span_sha256"])
                source = models.ModelSpanSource({key:raw})
                _,decoded,scene = source.parse(key)
                for draw in expected["draws"]:
                    shape = next(s for s in scene["shapes"] if s["index"]==draw["shape"])
                    lanes = models._shape_lanes(scene,shape,decoded)
                    self.assertIsNotNone(lanes.texcoord)
                    self.assertEqual(list(lanes.uv_scale),draw["uv_scale"])
                    self.assertEqual(list(lanes.uv_offset),draw["uv_offset"])
                    raw_uv = models.read_lane_2h(decoded,shape,lanes.texcoord,lanes.vertex_count)
                    sub = next(s for s in scene["submeshes"] if s["shape_index"]==draw["shape"] and s["material_name"]==draw["material"])
                    ids = sorted({i for _,batch in topology.decode_batches(decoded,sub["command_offset"],sub["primary_command_word_count"]) for i in batch})
                    self.assertEqual(texture.sha(b"".join(struct.pack("<2h",*raw_uv[i]) for i in ids)),draw["uv_bytes_sha256"])


if __name__ == "__main__":
    unittest.main()

"""Missing-field overlay contract, fixed wrapper and scene isolation proofs."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_midfield_art as mf
from mod_editor.core import nfl2k5_modern_venues_2026 as mv
from mod_editor.core import nfl2k5_scne_builder as sb
from tools.b765 import s2_midfield as repair


def scene():
    texture = bytearray(32)
    struct.pack_into("<I", texture, 12, (3 << 24) | (3 << 20) | (1 << 16) | (0x0B << 8) | 0x29)
    shape = bytearray(256)
    struct.pack_into("<4f", shape, 0x30, 1, 1, 0, 0)
    struct.pack_into("<H", shape, 0x4C, 4)
    struct.pack_into("<H", shape, 0x54, 1)
    struct.pack_into("<2H", shape, 0xC4, 12, 10)
    sub = bytearray(128)
    words = sb.encode_words(sb.TRIANGLE_STRIP, [0, 1, 2, 3])
    struct.pack_into("<H", sub, 0x7C, len(words) // 4)
    material = bytearray(128)
    return sb.Scene("field", [sb.Texture(texture, bytes(64), bytes(1024))],
                    [sb.Material(material, "numbers", 0)], [],
                    [sb.Shape(shape, "D_graphic_overlays", [], [sb.Submesh(sub, words)],
                              [bytes(48), bytes(40), None, None, None, None, None, None])], [])


class Contract(unittest.TestCase):
    def test_manifest_requires_explicit_boolean_and_reviewed_venue(self):
        with tempfile.TemporaryDirectory() as folder:
            venue = Path(folder) / "TEAM" / "venue"
            venue.mkdir(parents=True)
            path = venue / "logo.png"
            Image.new("RGBA", (256, 256), (200, 20, 30, 255)).save(path)
            doc = dict(schema=mv.ART_SCHEMA, team="TST", venue_prefix="s08",
                       items=[dict(scene="field", material="center_logo", layer="full", size=[256, 256],
                                   file="logo.png", sha256=hashlib.sha256(path.read_bytes()).hexdigest())])
            manifest = venue / "manifest.json"
            manifest.write_text(json.dumps(doc))
            plain = mv.load_art(folder)["venues"]["s08"]
            self.assertFalse(plain["add_missing_midfield"])
            doc["add_missing_midfield"] = True
            manifest.write_text(json.dumps(doc))
            selected = mv.load_art(folder)["venues"]["s08"]
            self.assertTrue(selected["add_missing_midfield"])
            self.assertNotEqual(plain["digest"], selected["digest"])
            doc["add_missing_midfield"] = "true"
            manifest.write_text(json.dumps(doc))
            with self.assertRaisesRegex(mv.ModernVenuesError, "must be a boolean"):
                mv.load_art(folder)
            doc.update(add_missing_midfield=True, venue_prefix="s03")
            manifest.write_text(json.dumps(doc))
            with self.assertRaisesRegex(mv.ModernVenuesError, "not reviewed"):
                mv.load_art(folder)

    def test_unselected_source_hook_is_byte_identical(self):
        data = b"unselected field bytes"
        with patch.object(mf, "append_span", side_effect=AssertionError("unselected writer ran")):
            got, receipt = mv._append_missing_midfield(data, "s08dd.iff", {})
        self.assertIs(got, data)
        self.assertIsNone(receipt)

    def test_art_copy_changes_only_three_manifests_and_refuses_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source"
            for team in ("DEN", "MIA", "PIT", "ATL"):
                venue = source / team / "venue"
                venue.mkdir(parents=True)
                (venue / "manifest.json").write_text(json.dumps({"team": team}) + "\n")
                (venue / "logo.png").write_bytes(b"private source bytes " + team.encode())
            output = Path(folder) / "prepared"
            with patch.object(mv, "load_art"):
                repair.prepare_art(source, output)
            proof = json.loads((output / "midfield_source_scope.json").read_text())
            self.assertEqual({row["file"] for row in proof["files"] if not row["unchanged"]},
                             {str(Path(team) / "venue" / "manifest.json") for team in ("DEN", "MIA", "PIT")})
            self.assertEqual((source / "ATL/venue/manifest.json").read_bytes(),
                             (output / "ATL/venue/manifest.json").read_bytes())
            for team in ("DEN", "MIA", "PIT", "ATL"):
                self.assertEqual((source / team / "venue/logo.png").read_bytes(),
                                 (output / team / "venue/logo.png").read_bytes())
            with self.assertRaisesRegex(ValueError, "already exists"):
                repair.prepare_art(source, output)
            with self.assertRaisesRegex(ValueError, "outside the source"):
                repair.prepare_art(source, source / "nested")

    def test_scene_scope_guard_detects_existing_texture_damage(self):
        old = scene()
        new = copy.deepcopy(old)
        new.textures.append(copy.deepcopy(old.textures[0]))
        new.materials.append(sb.Material(bytearray(128), mf.MATERIAL, 1))
        shape = new.shapes[0]
        shape.submeshes.append(copy.deepcopy(shape.submeshes[0]))
        struct.pack_into("<H", shape.submeshes[-1].record, 0, 1)
        struct.pack_into("<H", shape.record, 0x4C, 8)
        struct.pack_into("<H", shape.record, 0x54, 2)
        shape.streams[0] += bytes(48)
        shape.streams[1] += bytes(40)
        mf.assert_existing_scene(old, new)
        new.textures[0].pixels = b"X" + new.textures[0].pixels[1:]
        with self.assertRaisesRegex(sb.ScneBuildError, "existing scene record"):
            mf.assert_existing_scene(old, new)
        new.textures[0].pixels = old.textures[0].pixels
        struct.pack_into("<f", new.shapes[0].record, 0x30, 0.5)
        with self.assertRaisesRegex(sb.ScneBuildError, "existing scene record"):
            mf.assert_existing_scene(old, new)

    def test_unreviewed_placement_refuses_before_parsing(self):
        with self.assertRaisesRegex(sb.ScneBuildError, "not been reviewed"):
            mf.append_span(b"invalid bytes", "s03dd.iff", np.zeros((256, 256, 4), np.uint8))

    def test_native_repair_refuses_unowned_resource_and_wrong_art(self):
        logo = np.zeros((256, 256, 4), np.uint8)
        pins = dict(bundles={"s08dd.iff": {}}, logo_rgba_sha256={"s08": "0" * 64})
        with self.assertRaisesRegex(ValueError, "Unowned"):
            repair.repair_bundle(b"never parsed", "s22dd.iff", logo, pins)
        with self.assertRaisesRegex(ValueError, "Unexpected midfield source"):
            repair.repair_bundle(b"never parsed", "s08dd.iff", logo, pins)

    def test_frozen_repair_scope_has_twenty_one_full_quality_fields(self):
        pins = json.loads(repair.PINS.read_text())
        self.assertEqual(pins["schema"], repair.SCHEMA)
        self.assertEqual(len(pins["bundles"]), 21)
        self.assertEqual({name[:3] for name in pins["bundles"]}, {"s08", "s14", "s22"})
        for name, pin in pins["bundles"].items():
            self.assertNotEqual(pin["before_sha256"], pin["after_sha256"], name)
            receipt = pin["receipt"]
            self.assertEqual(receipt["native_size"], [256, 256], name)
            self.assertEqual(receipt["palette_cap"], 256, name)
            self.assertFalse(receipt["half_detail"], name)
            self.assertTrue(receipt["existing_scene_preserved"], name)
            self.assertLessEqual(receipt["alias_scratch"], receipt["scratch"], name)
            if name.startswith("s22"):
                self.assertEqual(pin["scope_kind"], "field_detail_prefix")
                self.assertTrue(receipt["detail_normal_decoded_identical"])
                self.assertTrue(receipt["detail_layer_span_identical"])
                self.assertEqual(receipt["allocation_loan"]["scratch"], 0)
                self.assertEqual(receipt["allocation_loan"]["alias_scratch"], 0)

    def test_pit_source_append_is_deferred_until_after_surface_writer(self):
        data = b"deferred PIT bytes"
        with patch.object(mf, "append_span", side_effect=AssertionError("early PIT append")):
            got, receipt = mv._append_missing_midfield(data, "s22ds.iff", {"missing_midfield": {}})
        self.assertIs(got, data)
        self.assertIsNone(receipt)
        code = (ROOT / "mod_editor/core/mod_build.py").read_text()
        self.assertLess(code.index('surfaces.apply_to_image(target'), code.index('midfield.apply_late_to_image(target'))

    def test_normal_loan_preserves_descriptor_all_mips_palette_and_zero_scratch(self):
        from mod_editor.core import nfl2k5_modern_metlife as ml
        tx = ml._tools()[0]
        system = bytearray(128)
        system[12:16] = b"TXTR"
        struct.pack_into("<2I", system, 16, 32 - 15, 60 - 19)
        system[32:60] = "detail_normal\0".encode("utf-16le")
        packed = (8 << 24) | (9 << 20) | (6 << 16) | (0x0B << 8) | 0x29
        struct.pack_into("<5I", system, 64, 0, 174720, packed, 0, 0x80000000)
        pixels = (bytes(range(256)) * 683)[:174720]
        palette = bytes((i * 67 + 37) & 255 for i in range(1024))
        decoded = bytes(system) + pixels + palette
        span = tx.HEADER.pack(b"TXTR", len(decoded), 128, 175744, 0, 0, 0, 0) + decoded
        result, receipt = mf.compress_detail_normal(span)
        chunk = tx.parse_chunks(result)[0]
        back, info = tx.decode_chunk(result, chunk)
        self.assertEqual(back, decoded)
        texture = tx.parse_texture(back, chunk)
        self.assertEqual((texture.width, texture.height, texture.mip_levels), (512, 256, 6))
        self.assertEqual(back[128:128 + texture.palette_offset], pixels)
        self.assertEqual(back[128 + texture.palette_offset:], palette)
        self.assertEqual(chunk.overlap_scratch_bytes, 0)
        self.assertEqual(info.offset_bits, 15)
        self.assertEqual(receipt["alias_scratch"], 0)
        self.assertLess(len(result), len(span))


if __name__ == "__main__":
    unittest.main()

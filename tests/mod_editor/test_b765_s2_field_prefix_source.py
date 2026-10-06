"""Selected source allocation keeps complete normals and default field routes."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import nfl2k5_modern_venues_2026 as mv
from mod_editor.core import nfl2k5_modern_surfaces as surfaces
from mod_editor.core import nfl2k5_midfield_art as midfield
from mod_editor.core import nfl2k5_modern_metlife as ml
from mod_editor.core import nfl2k5_modern_color as colour
from mod_editor.core import nfl2k5_scne_builder as sb
from mod_editor.core import nfl2k5_split_endzone_art as endzones


class SelectionTests(unittest.TestCase):
    def test_unselected_prefix_is_exact_noop_before_parsing(self):
        data = b"unparsed source bundle"
        result, receipt = mv._prepare_field_prefix(data, "s09dd.iff", {}, {})
        self.assertIs(result, data)
        self.assertIsNone(receipt)

    def test_unreviewed_prefix_refuses_before_parsing(self):
        with self.assertRaisesRegex(ValueError, "not been reviewed"):
            mv._prepare_field_prefix(b"unparsed", "s37dd.iff",
                                     dict(field_prefix_loan=True, split_shared_endzones=True), {})

    def test_manifest_bool_scope_and_digest(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "panel.png"
            Image.new("RGBA", (256, 128), (0, 118, 182, 255)).save(image)
            items = [dict(scene="field", material="endzone_" + e + "_" + p, layer="full",
                          size=[256, 128], file="panel.png", sha256=mv.sha(image.read_bytes()))
                     for e in "NS" for p in "LMR"]
            manifest = root / "manifest.json"
            doc = dict(schema=mv.ART_SCHEMA, team="DET", venue_prefix="s09", items=items,
                       split_shared_endzones=True)
            manifest.write_text(json.dumps(doc))
            original = mv.load_art(root)["venues"]["s09"]["digest"]
            doc["field_prefix_loan"] = False
            manifest.write_text(json.dumps(doc))
            self.assertEqual(mv.load_art(root)["venues"]["s09"]["digest"], original)
            doc["field_prefix_loan"] = True
            manifest.write_text(json.dumps(doc))
            selected = mv.load_art(root)["venues"]["s09"]
            self.assertNotEqual(selected["digest"], original)
            self.assertEqual(mv.field_prefix_loan_prefixes(root), ("s09",))
            doc["field_prefix_loan"] = 1
            manifest.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError, "must be a boolean"):
                mv.load_art(root)
            doc["field_prefix_loan"] = True
            doc["venue_prefix"] = "s37"
            manifest.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError, "reviewed independent-end"):
                mv.load_art(root)

    def test_surface_worker_default_call_stays_unchanged(self):
        with mock.patch.object(surfaces, "surface_bundle", return_value=(b"after", {})) as writer:
            self.assertEqual(surfaces._job(("s09dd.iff", b"before", True, None, None)),
                             ("s09dd.iff", b"after", {}))
            writer.assert_called_once_with(b"before", "s09dd.iff", indoor=True,
                                           colour_settings=None, overrides=None)

    def test_surface_worker_selection_keeps_full_normal_and_pattern(self):
        with mock.patch.object(surfaces, "surface_bundle", return_value=(b"after", {})) as writer:
            surfaces._job(("s09dd.iff", b"before", True, None, None, True))
            writer.assert_called_once_with(b"before", "s09dd.iff", indoor=True,
                                           colour_settings=None, overrides=None,
                                           preserve_full_normal=True, full_detail=True)

    def test_washington_worker_selects_only_its_surface_stage_loan(self):
        with mock.patch.object(surfaces, "surface_bundle", return_value=(b"after", {})) as writer:
            surfaces._job(("s29ds.iff", b"before", False, None, None, False, True))
            writer.assert_called_once_with(b"before", "s29ds.iff", indoor=False,
                                           colour_settings=None, overrides=None, field_normal_loan=True)

    def test_washington_loan_refuses_foreign_scope_before_parsing(self):
        for name in ("s09dd.iff", "s27dd.iff"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError,"reviewed only for WAS"):
                surfaces.surface_bundle(b"unparsed", name, indoor=False, field_normal_loan=True)


class NormalQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail = Path(__file__).resolve().parents[2] / "extracted/ESPN NFL 2K5 (USA)"
        if not retail.is_dir():
            raise unittest.SkipTest("hydrated retail image folder is required")
        cls.retail = retail
        pin = next(p for p in mv.venues()["s09"]["bundles"] if p["name"] == "s09dd.iff")
        with mv._outer_image()(str(retail)) as image:
            entry = mv._entry(image, pin)
            bundle = image.read(entry.virtual_offset, entry.size)
        assert mv.sha(bundle) == pin["retail_sha256"]
        cls.det_retail = bundle
        cls.tx = ml._tools()[0]
        normal = cls.tx.parse_chunks(bundle, allow_trailing=True)[2]
        cls.kind = surfaces.LOOKS[surfaces.venue_look("s09")]["detail"]
        cls.raw, variant = surfaces.normal_span(ml.scene_span(bundle, normal), cls.kind)
        assert variant == "full"
        cls.compressed, cls.loan = midfield.compress_detail_normal(cls.raw)

    def test_selected_compressed_full_normal_is_byte_identical(self):
        after, variant = surfaces.normal_span(self.compressed, self.kind, preserve_full=True)
        self.assertEqual(variant, "full")
        self.assertEqual(after, self.compressed)
        decoded, _ = self.tx.decode_chunk(after, self.tx.parse_chunks(after)[0])
        original, _ = self.tx.decode_chunk(self.raw, self.tx.parse_chunks(self.raw)[0])
        self.assertEqual(decoded, original)
        self.assertEqual(self.loan["scratch"], 0)

    def test_default_compressed_route_remains_tiled(self):
        after, variant = surfaces.normal_span(self.compressed, self.kind)
        self.assertEqual(variant, "tiled")
        self.assertNotEqual(after, self.compressed)

    def test_selected_normal_refuses_wrong_full_art(self):
        other = next(k for k in surfaces.DETAIL_ALPHA if k != self.kind)
        with self.assertRaisesRegex(ValueError, "exact full-resolution normal"):
            surfaces.normal_span(self.compressed, other, preserve_full=True)

    def test_snow_presurface_keeps_outside_colour_mask_and_vertex_tints(self):
        pin = next(p for p in mv.venues()["s30"]["bundles"] if p["name"] == "s30ds.iff")
        with mv._outer_image()(str(self.retail)) as image:
            entry = mv._entry(image, pin)
            retail = image.read(entry.virtual_offset, entry.size)
        self.assertEqual(mv.sha(retail), pin["retail_sha256"])

        def scene(data):
            chunk = ml.bundle_scenes(data)["field"]
            decoded, _ = self.tx.decode_chunk(data, chunk)
            return chunk, sb.parse(decoded, chunk.system_bytes, secondary=True)

        def outside(scene):
            return scene.textures[scene.materials[scene.material_index("grass_outside_premipped")].texture]

        _, old = scene(retail)
        checked = []
        def capture_prepaint(data, name, *, painter):
            _, prepared = scene(data)
            self.assertEqual(outside(prepared).palette, outside(old).palette)
            self.assertNotEqual(outside(prepared).pixels, outside(old).pixels)
            checked.append(name)
            normal = self.tx.parse_chunks(data, allow_trailing=True)[2]
            return data, dict(scope_size=normal.end_offset)

        with mock.patch.object(endzones, "split_bundle", side_effect=capture_prepaint):
            prepared, _ = mv._prepare_field_prefix(retail, pin["name"],
                dict(field_prefix_loan=True, split_shared_endzones=True), {})
        self.assertEqual(checked, [pin["name"]])

        def grade(data):
            chunk, _ = scene(data)
            span, _ = colour.modern_field_scene(ml.scene_span(data, chunk))
            return data[:chunk.offset] + span + data[chunk.end_offset:]

        baseline = grade(retail)
        selected = grade(prepared)
        _, baseline_scene = scene(baseline)
        _, selected_scene = scene(selected)
        baseline_shape = next(s for s in baseline_scene.shapes if s.name == "Outside_grass")
        selected_shape = next(s for s in selected_scene.shapes if s.name == "Outside_grass")
        self.assertEqual(selected_shape.streams, baseline_shape.streams)

    def test_borrowed_turf_presurface_keeps_original_material_inputs(self):
        def scene(data):
            chunk = ml.bundle_scenes(data)["field"]
            decoded, _ = self.tx.decode_chunk(data, chunk)
            return chunk, sb.parse(decoded, chunk.system_bytes, secondary=True)

        _, original = scene(self.det_retail)
        def capture_prepaint(data, name, *, painter):
            _, prepared = scene(data)
            for key in ("color_premipped", "grass_outside_premipped"):
                before = original.materials[original.material_index(key)]
                after = prepared.materials[prepared.material_index(key)]
                self.assertEqual(after.texture, before.texture)
                self.assertEqual(after.record[0x14:0x1C], before.record[0x14:0x1C])
            normal = self.tx.parse_chunks(data, allow_trailing=True)[2]
            return data, dict(scope_size=normal.end_offset)

        with mock.patch.object(endzones, "split_bundle", side_effect=capture_prepaint):
            prepared, _ = mv._prepare_field_prefix(self.det_retail, "s09dd.iff",
                dict(field_prefix_loan=True, split_shared_endzones=True), {})

        def outside_after_grade(data):
            chunk, _ = scene(data)
            span, _ = colour.modern_field_scene(ml.scene_span(data, chunk))
            graded, _ = ml._scene(span, self.tx.parse_chunks(span, allow_trailing=True)[0])
            decoded, _ = self.tx.decode_chunk(span, self.tx.parse_chunks(span, allow_trailing=True)[0])
            parsed = sb.parse(decoded, graded["system_bytes"], secondary=True)
            return next(s for s in parsed.shapes if s.name == "Outside_grass").streams

        self.assertEqual(outside_after_grade(prepared), outside_after_grade(self.det_retail))


if __name__ == "__main__":
    unittest.main()

"""Authoring refusal/atomicity contracts; public fixtures are synthetic P8 data.

An optional private native integration run requires B765_U1_NYG_PRIVATE_FIXTURE
to name a JSON file pinning spec/export paths and their SHA256s. Retail bytes
are neither embedded here nor fetched by the test.
"""
from pathlib import Path
import copy
import importlib.util
import json
import os
import struct
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("u1_nyg_author", ROOT / "tools/b765/u1_nyg.py")
u = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(u)
from nfl_txtr import HEADER, COMPRESSED_SENTINEL, compress_vc_lz, swizzle_2d


def synthetic_resource():
    """Solid navy helmet02: valid native layout, no reconstructed filter oracle."""
    system = bytearray(128)
    system[12:16] = b"TXTR"
    struct.pack_into("<II", system, 16, 17, 33)
    system[32:50] = "helmet02\0".encode("utf-16le")
    struct.pack_into("<6I", system, 52, 0, 0, 87360, 0x08860B29, 0, 0x80000000)
    palette = bytearray(1024)
    palette[:4] = bytes((101, 34, 11, 255))
    chain = b"".join(swizzle_2d(bytes((256 >> level) ** 2), 256 >> level,
                                256 >> level, 1) for level in range(6))
    compressed, _ = compress_vc_lz(bytes(system) + chain + bytes(palette),
                                   stream_tag=141, offset_bits=11, max_encoded_size=16384)
    span = HEADER.pack(b"TXTR", 16384, 128, 88384, COMPRESSED_SENTINEL, 16384, 0, 0) + \
        compressed + bytes(16384 - len(compressed))
    filler = HEADER.pack(b"USTR", 4, 4, 0, 0, 0, 0, 0) + b"pad!"
    return filler * 12 + span, span


class GiantsAuthorRefusalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resource, cls.span = synthetic_resource()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.out = self.base / "delivery"
        self.spec_path = self.base / "spec.json"
        self.export_path = self.base / "export.json"
        self.spec = {"schema": "nfl2k5_team_2026/v1", "team": "NYG", "asset_code": "18",
                     "live_helmet_mip_refinement": {
                         "schema": "b765/u1/nyg-logo-mips/v1", "family": "helmet02",
                         "filter": "direct_premultiplied_area_native_palette",
                         "base_boxes": [[52, 60, 107, 102], [51, 157, 106, 204]],
                         "mip_levels": [1]}}
        self.export = {"schema": "b765/u1/actual-kit-export/v1", "sets": []}
        for selector in ("18H0", "18A0"):
            path = self.base / (selector + ".IFF")
            path.write_bytes(self.resource)
            self.export["sets"].append({"selector": selector, "resource_path": str(path),
                                        "resource_sha256": u.sha(self.resource)})
        self.write_inputs()

    def write_inputs(self):
        self.spec_path.write_text(json.dumps(self.spec))
        self.export_path.write_text(json.dumps(self.export))

    def assert_refused_before_authoring(self):
        self.write_inputs()
        with mock.patch.object(u, "scoped_levels") as author, \
             mock.patch.object(u.helmet, "build_import") as compiler, \
             mock.patch.object(u, "publish_batch") as publisher:
            with self.assertRaises(ValueError):
                u.build(self.spec_path, self.export_path, self.out)
            author.assert_not_called()
            compiler.assert_not_called()
            publisher.assert_not_called()
        self.assertFalse(self.out.exists())

    def test_only_reviewed_team_and_schema_are_owned(self):
        original = copy.deepcopy(self.spec)
        for mutation in ({"team": "DAL"}, {"asset_code": "17"}, {"schema": "wrong"},
                         {"asset_code": 18}):
            with self.subTest(mutation=mutation):
                self.spec = dict(original, **mutation)
                self.assert_refused_before_authoring()
        for invalid in (None, [], "NYG"):
            with self.subTest(spec=invalid):
                self.spec = invalid
                self.assert_refused_before_authoring()

    def test_missing_or_wrong_recipe_is_a_controlled_refusal(self):
        original = copy.deepcopy(self.spec)
        for recipe in (None, [], "recipe", {}, {"schema": "wrong"}):
            with self.subTest(recipe=recipe):
                self.spec = dict(original, live_helmet_mip_refinement=recipe)
                self.assert_refused_before_authoring()
        self.spec = copy.deepcopy(original)
        del self.spec["live_helmet_mip_refinement"]
        self.assert_refused_before_authoring()
        for mutation in ({"family": "helmet00"}, {"filter": "recursive"}):
            with self.subTest(mutation=mutation):
                self.spec = copy.deepcopy(original)
                self.spec["live_helmet_mip_refinement"].update(mutation)
                self.assert_refused_before_authoring()
        self.spec = copy.deepcopy(original)
        del self.spec["live_helmet_mip_refinement"]["base_boxes"]
        self.assert_refused_before_authoring()

    def test_only_exact_reviewed_mip_one_is_accepted(self):
        for levels in ([1, 2], [0], [2], [3], [], [True], [1.0], [1, 1], [1, 0], None, "1"):
            with self.subTest(levels=levels):
                self.spec["live_helmet_mip_refinement"]["mip_levels"] = levels
                self.assert_refused_before_authoring()

    def test_invalid_or_whole_atlas_boxes_are_refused(self):
        for boxes in ([], None, "boxes", [[1, 2, 3]], [[0, 0, 257, 2]],
                      [[True, 0, 3, 3]], [[1.0, 0, 3, 3]], [[0, 0, 256, 256]],
                      [[0, 0, 3, 3]] * 2, [[5, 5, 4, 6]], [[-1, 0, 2, 2]]):
            with self.subTest(boxes=boxes):
                self.spec["live_helmet_mip_refinement"]["base_boxes"] = boxes
                self.assert_refused_before_authoring()

    def test_baseline_schema_and_selectors_are_validated(self):
        original = copy.deepcopy(self.export)
        for baseline in (None, [], {"schema": "wrong", "sets": []},
                         {"schema": original["schema"], "sets": {}},
                         {"schema": original["schema"], "sets": [None]},
                         {"schema": original["schema"], "sets": [{"selector": 18}]}):
            with self.subTest(baseline=baseline):
                self.export = baseline
                self.assert_refused_before_authoring()

    def test_duplicate_or_missing_baseline_selectors_are_refused(self):
        original = copy.deepcopy(self.export)
        for rows in ([original["sets"][0]], original["sets"] + [original["sets"][0]]):
            with self.subTest(rows=rows):
                self.export = dict(original, sets=rows)
                self.assert_refused_before_authoring()

    def test_both_resource_hashes_are_checked_before_authoring(self):
        original = copy.deepcopy(self.export)
        for side in (0, 1):
            with self.subTest(side=side):
                self.export = copy.deepcopy(original)
                self.export["sets"][side]["resource_sha256"] = "0" * 64
                self.assert_refused_before_authoring()

    def test_missing_or_symlinked_second_resource_is_refused_before_authoring(self):
        path = Path(self.export["sets"][1]["resource_path"])
        path.unlink()
        self.assert_refused_before_authoring()
        path.symlink_to(Path(self.export["sets"][0]["resource_path"]))
        self.assert_refused_before_authoring()

    def test_malformed_resource_pin_fields_are_controlled_refusals(self):
        original = copy.deepcopy(self.export)
        for field, value in (("resource_path", None), ("resource_sha256", None),
                             ("resource_path", 7), ("resource_sha256", 7)):
            with self.subTest(field=field, value=value):
                self.export = copy.deepcopy(original)
                self.export["sets"][1][field] = value
                self.assert_refused_before_authoring()

    def test_later_compiler_failure_publishes_neither_side_and_cleans_stage(self):
        stages = []

        def compiler(_index, _report, _code, side, _variant, _family, png):
            stages.append(png)
            self.assertTrue(png.is_file())
            self.assertFalse(png.is_relative_to(self.out))
            if side == "A":
                raise ValueError("simulated away compiler refusal")
            return self.span, [], {"input_png": {"path": str(png)}}

        with mock.patch.object(u.helmet, "build_import", side_effect=compiler) as writer, \
             mock.patch.object(u, "publish_batch") as publisher:
            with self.assertRaisesRegex(ValueError, "away compiler refusal"):
                u.build(self.spec_path, self.export_path, self.out)
            self.assertEqual(writer.call_count, 2)
            publisher.assert_not_called()
        self.assertFalse(self.out.exists())
        self.assertEqual(len(stages), 2)
        self.assertTrue(all(not path.exists() for path in stages))

    def test_refusal_preserves_existing_output_bytes(self):
        self.out.mkdir()
        marker = self.out / "coordinator-owned.txt"
        marker.write_bytes(b"preserve this exact existing delivery")
        self.export["sets"][1]["resource_sha256"] = "0" * 64
        self.write_inputs()
        with mock.patch.object(u.helmet, "build_import") as writer:
            with self.assertRaisesRegex(ValueError, "pin changed"):
                u.build(self.spec_path, self.export_path, self.out)
            writer.assert_not_called()
        self.assertEqual(list(self.out.iterdir()), [marker])
        self.assertEqual(marker.read_bytes(), b"preserve this exact existing delivery")

    def test_success_checks_both_sides_before_one_publish(self):
        real_publish = u.publish_batch
        with mock.patch.object(u.helmet, "build_import",
                               side_effect=lambda *args: (self.span, [], {"input_png": {"path": str(args[-1])}})), \
             mock.patch.object(u, "publish_batch", wraps=real_publish) as publisher:
            receipt = u.build(self.spec_path, self.export_path, self.out)
            publisher.assert_called_once()
        self.assertEqual(set(receipt["resources"]), {"18H0", "18A0"})
        self.assertFalse(receipt["geometry_edited"])
        self.assertFalse(receipt["runtime_visibility_proved"])
        for selector, row in receipt["resources"].items():
            self.assertTrue(row["idempotent"])
            self.assertTrue(row["outside_scope_identical"])
            self.assertEqual(row["pixel_scope"]["protected_changed_texels"], 0)
            self.assertEqual((self.out / "resources" / (selector + ".IFF")).read_bytes(), self.resource)


class PrivateNativeGiantsIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("B765_U1_NYG_PRIVATE_FIXTURE"),
                         "private native fixture requires explicit pinned local fixture JSON")
    def test_real_writer_readback_scope_and_second_build_match(self):
        fixture = json.loads(Path(os.environ["B765_U1_NYG_PRIVATE_FIXTURE"]).read_text())
        spec = Path(fixture["spec"])
        baseline = Path(fixture["baseline_export"])
        self.assertEqual(u.sha(spec.read_bytes()), fixture["spec_sha256"])
        self.assertEqual(u.sha(baseline.read_bytes()), fixture["baseline_export_sha256"])
        with tempfile.TemporaryDirectory() as temp:
            first, second = Path(temp) / "first", Path(temp) / "second"
            receipts = [u.build(spec, baseline, out) for out in (first, second)]
            for selector in ("18H0", "18A0"):
                for suffix in ("resources/" + selector + ".IFF", "art/" + selector + "_helmet02.png"):
                    self.assertEqual((first / suffix).read_bytes(), (second / suffix).read_bytes())
                for receipt in receipts:
                    row = receipt["resources"][selector]
                    self.assertTrue(row["outside_scope_identical"])
                    self.assertTrue(row["idempotent"])
                    scope = row["pixel_scope"]
                    self.assertEqual(scope["protected_changed_texels"], 0)
                    self.assertTrue(scope["system_identical"])
                    self.assertTrue(scope["descriptor_identical"])
                    self.assertTrue(scope["allocation_identical"])
                    for level in scope["levels"]:
                        if level["level"] != 1:
                            self.assertEqual(level["changed_texels"], 0)
                expected = fixture.get("after_sha256", {}).get(selector)
                if expected:
                    self.assertEqual(u.sha((first / "resources" / (selector + ".IFF")).read_bytes()), expected)
            self.assertEqual((first / "payload/native_manifest.json").read_bytes(),
                             (second / "payload/native_manifest.json").read_bytes())
            first_payloads = {p.name: p.read_bytes() for p in (first / "payload").glob("*.span")}
            second_payloads = {p.name: p.read_bytes() for p in (second / "payload").glob("*.span")}
            self.assertEqual(first_payloads, second_payloads)


if __name__ == "__main__":
    unittest.main()

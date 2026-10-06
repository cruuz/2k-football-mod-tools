"""Decoded helmet scope gates use synthetic P8 spans, never retail fixtures."""
from pathlib import Path
import copy
import importlib.util
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("u1_nyg_repair", ROOT / "tools/b765/u1_repair.py")
u = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(u)
from nfl_txtr import (HEADER, COMPRESSED_SENTINEL, Chunk, compress_vc_lz,
                      decode_chunk, swizzle_2d)
from nfl_live_helmet_txtr_png_import import decode_levels


def synthetic_span(changes=(), *, permute=False, palette_change=False, system_change=False,
                   descriptor_change=False):
    system = bytearray(128)
    system[12:16] = b"TXTR"
    struct.pack_into("<II", system, 16, 17, 33)
    system[32:50] = "helmet00\0".encode("utf-16le")
    struct.pack_into("<6I", system, 52, 0, 0, 87360, 0x08860B29, 0, 0x80000000)
    if system_change:
        system[0] = 7
    if descriptor_change:
        struct.pack_into("<I", system, 72, 0x80000001)
    palette = bytearray(1024)
    for index, rgba in enumerate(((11, 34, 101, 255), (255, 255, 255, 255), (220, 10, 40, 255))):
        r, g, b, a = rgba
        palette[index * 4:index * 4 + 4] = bytes((b, g, r, a))
    if permute:
        palette[:4], palette[4:8] = palette[4:8], palette[:4]
    if palette_change:
        palette[:4] = bytes((40, 10, 220, 255))
    chain = []
    for level in range(6):
        width = 256 >> level
        indices = bytearray(width * width)
        indices[(80 >> level) * width + (80 >> level)] = 1
        for target_level, x, y, index in changes:
            if target_level == level:
                indices[y * width + x] = index
        if permute:
            indices = bytearray(1 if value == 0 else 0 if value == 1 else value for value in indices)
        chain.append(swizzle_2d(bytes(indices), width, width, 1))
    decoded = bytes(system) + b"".join(chain) + bytes(palette)
    compressed, _ = compress_vc_lz(decoded, stream_tag=141, offset_bits=11, max_encoded_size=16384)
    return HEADER.pack(b"TXTR", 16384, 128, 88384, COMPRESSED_SENTINEL, 16384, 0, 0) + \
        compressed + bytes(16384 - len(compressed))


def decode(span):
    fields = HEADER.unpack_from(span)
    chunk = Chunk(0, 0, "TXTR", *fields[1:])
    return decode_chunk(span, chunk)[0]


def declaration(span, *, levels=None, boxes=None):
    decoded = decode(span)
    scope = {"schema": u.HELMET_SCOPE_SCHEMA, "family": "helmet00",
             "base_boxes": boxes or [[64, 64, 128, 128]],
             "mip_levels": list(range(6)) if levels is None else levels,
             "system_sha256": u.sha(decoded[:128]), "descriptor_sha256": u.sha(decoded[52:76]),
             "protected_rgba_sha256": ["0" * 64] * 6}
    masks = u.helmet_scope_masks(scope)
    for level, mask in zip(decode_levels(decoded), masks):
        pixels = b"".join(level.rgba[i * 4:i * 4 + 4] for i, allowed in enumerate(mask) if not allowed)
        scope["protected_rgba_sha256"][level.level] = u.sha(pixels)
    return scope


class HelmetDecodedScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = synthetic_span()
        cls.inside = synthetic_span([(level, 80 >> level, 80 >> level, 2) for level in range(6)])
        cls.scope = declaration(cls.before)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def patch(self, replacement, *, before=None, scope=None, filename="fixed.bin"):
        (self.base / filename).write_bytes(replacement)
        return {"offset": 3, "length": len(replacement), "replacement": filename,
                "before_sha256": u.sha(self.before if before is None else before),
                "after_sha256": u.sha(replacement),
                "helmet_pixel_scope": copy.deepcopy(self.scope if scope is None else scope)}

    def apply(self, replacement, *, before=None, scope=None):
        before = self.before if before is None else before
        patch = self.patch(replacement, before=before, scope=scope)
        return u.apply_spans(b"PRE" + before + b"TAIL", [patch], self.base)

    def test_all_six_mips_allow_inside_changes_and_record_actual_complements(self):
        after, receipt = self.apply(self.inside)
        self.assertEqual(after, b"PRE" + self.inside + b"TAIL")
        self.assertTrue(receipt["outside_scope_identical"])
        pixel = receipt["spans"][0]["helmet_pixel_scope"]
        self.assertEqual(pixel["changed_texels"], 6)
        self.assertEqual(pixel["protected_changed_texels"], 0)
        self.assertTrue(pixel["system_identical"])
        self.assertTrue(pixel["descriptor_identical"])
        self.assertTrue(pixel["allocation_identical"])
        self.assertEqual([row["allowed_texels"] for row in pixel["levels"]], [4096, 1024, 256, 64, 16, 4])
        self.assertEqual([row["protected_texels"] for row in pixel["levels"]], [61440, 15360, 3840, 960, 240, 60])
        self.assertEqual([row["protected_after_sha256"] for row in pixel["levels"]],
                         self.scope["protected_rgba_sha256"])

    def test_already_applied_input_is_rechecked_and_reports_zero_new_changes(self):
        patch = self.patch(self.inside)
        after, _ = u.apply_spans(b"PRE" + self.before + b"TAIL", [patch], self.base)
        again, receipt = u.apply_spans(after, [patch], self.base)
        self.assertEqual(again, after)
        self.assertTrue(receipt["spans"][0]["already_applied"])
        self.assertEqual(receipt["spans"][0]["helmet_pixel_scope"]["changed_texels"], 0)
        patch["helmet_pixel_scope"]["protected_rgba_sha256"][5] = "1" * 64
        with self.assertRaisesRegex(ValueError, "input protected mip5"):
            u.apply_spans(after, [patch], self.base)

    def test_each_mip_rejects_outside_changes_even_when_span_hash_is_pinned(self):
        for level in range(6):
            with self.subTest(level=level):
                bad = synthetic_span([(level, 0, 0, 1)])
                with self.assertRaisesRegex(ValueError, f"replacement protected mip{level}"):
                    self.apply(bad)

    def test_original_input_protection_is_checked_independently_of_its_span_pin(self):
        bad_input = synthetic_span([(2, 0, 0, 1)])
        with self.assertRaisesRegex(ValueError, "input protected mip2"):
            self.apply(self.inside, before=bad_input)

    def test_undeclared_mip_is_fully_protected_including_its_logo_box(self):
        scope = declaration(self.before, levels=[1, 2])
        with self.assertRaisesRegex(ValueError, "replacement protected mip0"):
            self.apply(self.inside, scope=scope)
        accepted = synthetic_span([(1, 40, 40, 2), (2, 20, 20, 2)])
        _, receipt = self.apply(accepted, scope=scope)
        rows = receipt["spans"][0]["helmet_pixel_scope"]["levels"]
        self.assertEqual([row["allowed_texels"] for row in rows], [0, 1024, 256, 0, 0, 0])

    def test_palette_permutations_are_allowed_when_all_decoded_pixels_match(self):
        permuted = synthetic_span(permute=True)
        _, receipt = self.apply(permuted)
        pixel = receipt["spans"][0]["helmet_pixel_scope"]
        self.assertFalse(pixel["palette_identical"])
        self.assertEqual(pixel["changed_texels"], 0)

    def test_palette_changes_that_recolour_protected_pixels_are_refused(self):
        with self.assertRaisesRegex(ValueError, "replacement protected mip0"):
            self.apply(synthetic_span(palette_change=True))

    def test_system_and_descriptor_changes_are_refused(self):
        with self.assertRaisesRegex(ValueError, "system/descriptor hash"):
            self.apply(synthetic_span(system_change=True))
        with self.assertRaisesRegex(ValueError, "descriptor/layout"):
            self.apply(synthetic_span(descriptor_change=True))

    def test_allocation_is_bounded_before_decode(self):
        bad = bytearray(self.inside)
        struct.pack_into("<I", bad, 8, 0x7fffffff)
        with mock.patch("nfl_txtr.decode_chunk") as decoder:
            with self.assertRaisesRegex(ValueError, "pinned compressed allocation"):
                u.verify_helmet_pixel_scope(bytes(bad), self.inside, self.scope)
            decoder.assert_not_called()

    def test_family_and_loader_scratch_are_checked(self):
        scope = copy.deepcopy(self.scope)
        scope["family"] = "helmet02"
        with self.assertRaisesRegex(ValueError, "descriptor/layout"):
            self.apply(self.inside, scope=scope)
        bad = bytearray(self.inside)
        struct.pack_into("<I", bad, 20, 0)
        with self.assertRaisesRegex(ValueError, "loader scratch"):
            self.apply(bytes(bad))

    def test_scope_schema_bounds_and_hashes_are_strict(self):
        mutations = [
            {"schema": "wrong"}, {"extra": True}, {"family": "jersey00"},
            {"base_boxes": []}, {"base_boxes": [[0, 0, 257, 10]]},
            {"base_boxes": [[True, 1, 10, 10]]}, {"base_boxes": [[4, 4, 4, 8]]},
            {"base_boxes": [[0, 0, 256, 256]]},
            {"base_boxes": [[0, 0, 2, 2]] * 9},
            {"base_boxes": [[64, 64, 128, 128]] * 2},
            {"mip_levels": []}, {"mip_levels": [0, 0]}, {"mip_levels": [2, 1]},
            {"mip_levels": [True]}, {"mip_levels": [6]},
            {"protected_rgba_sha256": ["0" * 64] * 5},
            {"descriptor_sha256": "z" * 64}, {"system_sha256": "0" * 1000},
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                scope = dict(self.scope, **mutation)
                with self.assertRaises(ValueError):
                    u.helmet_scope_masks(scope)
        with self.assertRaises(ValueError):
            u.helmet_scope_masks(None)

    def test_non_aligned_boxes_use_intersecting_base_footprints(self):
        scope = declaration(self.before, levels=[1, 3], boxes=[[65, 66, 127, 130]])
        masks = u.helmet_scope_masks(scope)
        self.assertEqual([sum(mask) for mask in masks], [0, 1024, 0, 72, 0, 0])
        self.assertEqual(masks[1][33 * 128 + 32], 1)
        self.assertEqual(masks[1][32 * 128 + 32], 0)

    def test_generic_patch_without_metadata_retains_legacy_behaviour(self):
        (self.base / "generic.bin").write_bytes(b"XY")
        patch = {"offset": 2, "length": 2, "before_sha256": u.sha(b"cd"),
                 "after_sha256": u.sha(b"XY"), "replacement": "generic.bin"}
        after, receipt = u.apply_spans(b"abcdef", [patch], self.base)
        self.assertEqual(after, b"abXYef")
        self.assertNotIn("helmet_pixel_scope", receipt["spans"][0])

    def test_public_guard_refuses_a_different_stored_span_size_before_decoding(self):
        with mock.patch.object(u, "_decode_scoped_helmet") as decoder:
            with self.assertRaisesRegex(ValueError, "stored span size changed"):
                u.verify_helmet_pixel_scope(self.before, self.inside + b"padding", self.scope)
            decoder.assert_not_called()

    def test_pack_mapping_retains_the_optional_scope_metadata(self):
        patch = self.patch(self.inside)
        resource = b"PRE" + self.before + b"TAIL"
        physical = resource + bytes(32768 - len(resource)) + b"trailing native padding"
        source = self.base / "disc.iso"
        source.write_bytes(b"read-only source")
        index = u.bump._IndexPack(1, 2, (1, 16), (0, 2048),
                                 (u.bump._IndexEntry(0, 123, len(resource), 1),))
        image = SimpleNamespace(index_size=11, pack_size=lambda _i: len(physical),
                                read_pack=lambda _i, start, length: physical[start:start + length],
                                read_index_range=lambda start, length: b"index bytes"[start:start + length])
        context = mock.MagicMock()
        context.__enter__.return_value = image
        manifest = {"resources": {"18H0.IFF": [patch]}}
        with mock.patch.object(u.bump._Image, "open", return_value=context), \
             mock.patch.object(u.bump, "_parsed_index", return_value=index), \
             mock.patch.object(u.bump, "logical_name_for", return_value="18H0.IFF"):
            receipt = u.repair_packs(source, self.base / "packs", manifest, self.base)
        row = receipt["disc_files"][f"vc_53450030/{u.PACK_NAMES[1]}"]["spans"][0]
        self.assertEqual(row["helmet_pixel_scope"]["changed_texels"], 6)
        expected = physical[:3] + self.inside + physical[3 + len(self.inside):]
        self.assertEqual((self.base / "packs" / u.PACK_NAMES[1]).read_bytes(), expected)
        self.assertEqual(source.read_bytes(), b"read-only source")

    def test_resource_batch_checks_every_pixel_scope_before_publishing(self):
        source = self.base / "resources"
        source.mkdir()
        for name in ("18H0.IFF", "18A0.IFF"):
            (source / name).write_bytes(b"PRE" + self.before + b"TAIL")
        good = self.patch(self.inside)
        bad = self.patch(synthetic_span([(5, 0, 0, 1)]), filename="bad.bin")
        output = self.base / "output"
        with self.assertRaisesRegex(ValueError, "protected mip5"):
            u.repair_resources(source, output, {"resources": {"18H0.IFF": [good], "18A0.IFF": [bad]}}, self.base)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()

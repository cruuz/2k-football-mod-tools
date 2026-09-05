"""Standalone resource/compiler gates. No game, GUI or instruction emulator runs."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_guardian_cap as cap
from mod_editor.core import nfl2k5_models as models
from mod_editor.core.nfl2k5_p8_texture_writer import compile_live_helmet_span
import nfl_live_helmet_txtr_png_import as helmet
import nfl_txtr as txtr

EXTRACTION = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted"))
PACKS = EXTRACTION / "ESPN NFL 2K5 (USA)" / "vc_53450030"
XISO = Path(os.environ.get("NFL2K5_RETAIL_XISO", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))


def decode(span):
    kind, stored, system, video, magic, scratch, r0, r1 = struct.unpack_from("<4s7I", span)
    chunk = txtr.Chunk(0, 0, kind.decode("ascii"), stored, system, video, magic, scratch, r0, r1)
    return txtr.decode_chunk(span, chunk)[0]


class ContractTests(unittest.TestCase):
    def test_unknown_truncated_and_xbe_bytes_fail_closed(self):
        for payload in (b"", b"SCNE", b"XBEH" + bytes(512), bytes(135840), bytes(270368), bytes(36704)):
            self.assertEqual(cap.status(payload), "foreign")
            with self.assertRaises(cap.GuardianCapError):
                cap.apply(payload)
        with patch.object(cap, "_compile") as compile_mock:
            for resources in ({}, {"o3c113": b""}, {t.key: b"" for t in cap.TARGETS}):
                self.assertEqual(cap.resources_status(resources), "foreign")
                with self.assertRaises(cap.GuardianCapError):
                    cap.apply_resources(resources)
            compile_mock.assert_not_called()

    def test_span_adapter_refuses_bad_wrappers_and_keys(self):
        wrapper = struct.pack("<4s7I", b"SCNE", 1, 1, 0, 0xFEEDBEEF, 16, 0, 0) + b"x"
        for key, payload in (("bad", wrapper), ("o3c113", b""), ("o3c113", wrapper[:-1]),
                             ("o3c113", b"TXTR" + wrapper[4:])):
            with self.assertRaises(models.ModelsError):
                models.ModelSpanSource({key: payload})

    def test_texture_adapter_refuses_non_helmet_allocation(self):
        for payload in (b"", bytes(32), struct.pack("<4s7I", b"TXTR", 0, 128, 42, 0xFEEDBEEF, 16, 0, 0)):
            with self.assertRaises(ValueError):
                compile_live_helmet_span(payload, cap.matte_cap_rgba())

    def test_profile_is_translation_invariant_and_keeps_seams_together(self):
        points = [(10 * math.sin(a) * math.cos(b), 14 * math.sin(b), 13 * math.cos(a) * math.cos(b))
                  for a in (0, .4, 1.1, 1.9, 2.7, 3.5, 4.7, 5.9)
                  for b in (-1.1, -.4, .3, 1.1)]
        points += points[:3]
        moved = cap.sculpt_shell(points)
        shifted = cap.sculpt_shell([(x + 11, y - 35, z + 5) for x, y, z in points])
        self.assertEqual(moved[-3:], moved[:3])
        for p, q in zip(moved, shifted):
            for a, shift in enumerate((11, -35, 5)):
                self.assertAlmostEqual(p[a] + shift, q[a], places=10)
        for bad in ([], [(0, 0, 0)], [(float("nan"), 0, 0)]):
            with self.assertRaises(cap.GuardianCapError):
                cap.sculpt_shell(bad)

    def test_art_is_neutral_opaque_and_diffuse(self):
        rgba = cap.matte_cap_rgba()
        self.assertEqual(len(rgba), 256 * 256 * 4)
        self.assertEqual(rgba[0::4], rgba[1::4])
        self.assertEqual(rgba[1::4], rgba[2::4])
        self.assertEqual(set(rgba[3::4]), {255})
        self.assertGreater(max(rgba[0::4]) - min(rgba[0::4]), 15)
        self.assertLess(max(rgba[0::4]), 140)
        self.assertIn("Every player wearing helmet C shows a guardian cap.", cap.UI_TEXT)
        self.assertIn("Helmet C's normal look is replaced while this is on.", cap.UI_TEXT)
        self.assertEqual(cap.EVIDENCE, "EXPERIMENTAL / UNWITNESSED")

    def test_image_extent_resolution_uses_pack_location_and_bounds(self):
        packs = {"0": SimpleNamespace(byte_offset=8192, size=4 * 1024 * 1024),
                 "B": SimpleNamespace(byte_offset=10 * 1024 * 1024, size=300 * 1024 * 1024)}
        with patch.object(models, "_xdvdfs_pack_entries", return_value=packs):
            locations = cap._image_locations(123, 400 * 1024 * 1024)
            for t in cap.TARGETS:
                self.assertEqual(locations[t.key], packs[t.pack].byte_offset + t.pack_offset)
            with self.assertRaises(cap.GuardianCapError):
                cap._image_locations(123, 4096)
            packs["B"].size = 0
            with self.assertRaises(cap.GuardianCapError):
                cap._image_locations(123, 400 * 1024 * 1024)

    def test_raw_xbe_is_not_a_resource_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / "default.xbe"
            path.write_bytes(b"XBEH" + bytes(512))
            self.assertEqual(cap.image_status(path), "foreign")
            with self.assertRaises(ValueError):
                cap.apply_to_image(path)
            os.replace(path, path.with_suffix(".closed"))


class RetailResourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for name in ("0", "B"):
            if not (PACKS / name).is_file():
                raise unittest.SkipTest(f"Retail archive evidence missing: {PACKS / name}; set NFL2K5_RETAIL_EXTRACTION")
        cls.retail = cap.read_archive_resources(PACKS / "0")
        for target in cap.TARGETS:
            if hashlib.sha256(cls.retail[target.key]).hexdigest() != target.retail_sha256:
                raise AssertionError(f"Present retail evidence has a foreign span: {target.key}")
        # Real production export/import and texture compiler, once for both LODs.
        cls.compiled, cls.receipt = cap.apply_resources(cls.retail)
        cls.before = {key: decode(span) for key, span in cls.retail.items()}
        cls.after = {key: decode(span) for key, span in cls.compiled.items()}

    def test_exact_fixed_spans_wrappers_and_receipts(self):
        self.assertEqual(sum(map(len, self.retail.values())), 442912)
        self.assertEqual(sum(map(len, self.compiled.values())), 442912)
        self.assertEqual(self.receipt["archive_growth"], 0)
        self.assertEqual(self.receipt["before"], "retail")
        self.assertEqual(self.receipt["after"], "applied")
        json.dumps(self.receipt, allow_nan=False)
        for t, receipt in zip(cap.TARGETS, self.receipt["resources"]):
            with self.subTest(key=t.key):
                before, after = self.retail[t.key], self.compiled[t.key]
                self.assertEqual((len(before), len(after)), (t.size, t.size))
                self.assertEqual(before[:32], after[:32])
                self.assertEqual(hashlib.sha256(after).hexdigest(), t.applied_sha256)
                self.assertEqual(cap.status(before), "retail")
                self.assertEqual(cap.status(after), "applied")
                self.assertEqual(receipt["changed_bytes"], sum(a != b for a, b in zip(before, after)))
                self.assertEqual(receipt["before_sha256"], t.retail_sha256)
                self.assertEqual(receipt["after_sha256"], t.applied_sha256)
                if t.shell_material >= 0:
                    compression = receipt["compiler"]["compression"]
                    self.assertLessEqual(compression["exact_minimum_scratch_bytes"], 16)
                    self.assertLessEqual(compression["consumed_bytes"], t.size - 32)
                    self.assertIn("vertex index lane", receipt["compiler"]["shapes"][0]["matched_by"])
                    for lane in ("normals_changed", "uvs_changed", "colours_changed"):
                        self.assertEqual(receipt["compiler"]["shapes"][0][lane], 0)

    def test_independent_decoded_diff_only_c_positions_at_both_lods(self):
        # Addresses independently read from the retail declarations. The gate is
        # stricter than allowing shape range constants: they must stay identical.
        for key, base, first, count, total in (("o3c113", 0x11CC0, 4349, 112, 5065),
                                               ("o3c115", 0x26780, 11022, 435, 11727)):
            with self.subTest(key=key):
                before, after = self.before[key], self.after[key]
                self.assertEqual(len(before), len(after))
                allowed = {base + 10 * vertex + lane for vertex in range(first, first + count) for lane in range(6)}
                diff = {i for i, (a, b) in enumerate(zip(before, after)) if a != b}
                self.assertTrue(diff)
                self.assertLessEqual(diff, allowed)
                for vertex in range(total):
                    at = base + 10 * vertex
                    if first <= vertex < first + count:
                        self.assertNotEqual(before[at:at + 6], after[at:at + 6])
                    else:
                        self.assertEqual(before[at:at + 6], after[at:at + 6])
                    self.assertEqual(before[at + 6:at + 10], after[at + 6:at + 10])
                # All commands, material IDs, UVs, selectors, transforms, morphs,
                # facemask/accessory/A/B/head/body vertices are outside this set.

    def test_shell_padding_exceeds_probe_and_keeps_lower_opening(self):
        for t in cap.TARGETS[:2]:
            source = models.ModelSpanSource({t.key: self.retail[t.key]})
            _, _, scene = source.parse(t.key)
            shape = scene["shapes"][0]
            lanes = models._shape_lanes(scene, shape, self.before[t.key])
            before = models.read_positions(self.before[t.key], shape, lanes)
            after = models.read_positions(self.after[t.key], shape, lanes)
            ids = range(t.first_vertex, t.first_vertex + t.shell_vertices)
            centre = [sum(before[i][a] for i in ids) / t.shell_vertices for a in range(3)]
            old_probe = .08 * sum(math.dist(before[i], centre) for i in ids) / t.shell_vertices
            moves = [math.dist(before[i], after[i]) for i in ids]
            self.assertGreater(sum(moves) / len(moves), old_probe * 1.5)
            self.assertGreater(max(moves), 2.5)
            self.assertLess(max(moves), 3.0)
            self.assertGreater(max(after[i][1] for i in ids), max(before[i][1] for i in ids) + 2)
            self.assertGreaterEqual(min(after[i][1] for i in ids), min(before[i][1] for i in ids))
            self.assertLess(min(after[i][2] for i in ids), min(before[i][2] for i in ids) - 1.5)
            self.assertGreater(max(after[i][0] for i in ids), max(before[i][0] for i in ids) + 1.0)

    def test_one_live_helmet_texture_has_six_neutral_mips_and_same_system_bytes(self):
        before, after = self.before["o4002c12"], self.after["o4002c12"]
        self.assertEqual(len(after), 88512)
        self.assertEqual(before[:128], after[:128])
        self.assertIn("helmet02".encode("utf-16-le"), after[:128])
        levels = helmet.decode_levels(after)
        self.assertEqual([(m.width, m.height) for m in levels], [(256, 256), (128, 128), (64, 64), (32, 32), (16, 16), (8, 8)])
        for level in levels:
            self.assertEqual(level.rgba[0::4], level.rgba[1::4])
            self.assertEqual(level.rgba[1::4], level.rgba[2::4])
            self.assertEqual(set(level.rgba[3::4]), {255})
        self.assertEqual(levels[0].rgba, cap.matte_cap_rgba())
        self.assertEqual([t.key for t in cap.TARGETS if t.shell_material < 0], ["o4002c12"])

    def test_idempotence_requires_no_compiler_or_source_archive(self):
        with patch.object(cap, "_compile", side_effect=AssertionError("must not compile")):
            again, receipt = cap.apply_resources(self.compiled)
            self.assertEqual(again, self.compiled)
            self.assertEqual(receipt["before"], "applied")
            self.assertTrue(all(r["changed_bytes"] == 0 for r in receipt["resources"]))
            for t in cap.TARGETS:
                self.assertEqual(cap.apply(self.compiled[t.key])[0], self.compiled[t.key])

    def test_every_partial_install_and_foreign_span_refuses_before_compilation(self):
        with patch.object(cap, "_compile") as compiler:
            for mask in range(1, 7):
                mixed = {t.key: (self.compiled if mask & (1 << i) else self.retail)[t.key]
                         for i, t in enumerate(cap.TARGETS)}
                self.assertEqual(cap.resources_status(mixed), "foreign")
                with self.assertRaises(cap.GuardianCapError):
                    cap.apply_resources(mixed)
            for dataset in (self.retail, self.compiled):
                for t in cap.TARGETS:
                    for at in (0, 20, 31, 32, t.size // 2, t.size - 1):
                        corrupt = bytearray(dataset[t.key])
                        corrupt[at] ^= 1
                        self.assertEqual(cap.status(corrupt), "foreign")
                        with self.assertRaises(cap.GuardianCapError):
                            cap.apply_resources(dict(dataset, **{t.key: corrupt}))
                    self.assertEqual(cap.status(dataset[t.key], key="o999c1"), "foreign")
            compiler.assert_not_called()

    def _image(self, folder):
        original = bytearray(b"untouched prefix" * 31)
        locations = {}
        for target in cap.TARGETS:
            locations[target.key] = len(original)
            original.extend(self.retail[target.key])
            original.extend(b"untouched between resources" * 23)
        path = folder / "build-copy.iso"
        path.write_bytes(original)
        return path, bytes(original), locations

    def _precompiled(self, payload, target):
        self.assertEqual(payload, self.retail[target.key])
        return self.compiled[target.key], {}

    def test_resource_pass_zero_growth_and_only_three_owned_extents(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, original, locations = self._image(Path(tmp).resolve())
            with patch.object(cap, "_image_locations", return_value=locations), \
                    patch.object(cap, "_compile", side_effect=self._precompiled):
                self.assertEqual(cap.image_status(path), "retail")
                receipt = cap.apply_to_image(path)
                self.assertEqual(cap.image_status(path), "applied")
                expected = bytearray(original)
                for t in cap.TARGETS:
                    start = locations[t.key]
                    expected[start:start + t.size] = self.compiled[t.key]
                self.assertEqual(path.read_bytes(), bytes(expected))
                self.assertEqual(receipt["image_size_before"], receipt["image_size_after"])
                with patch.object(cap.platform_compat, "pwrite") as write:
                    cap.apply_to_image(path)
                    write.assert_not_called()
            os.replace(path, path.with_suffix(".closed"))

    def test_image_mutation_during_compile_refuses_before_any_write_and_closes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, original, locations = self._image(Path(tmp).resolve())
            def changed_read(_fd, _locations):
                changed = dict(self.retail)
                changed["o4002c12"] = b"foreign"
                return changed
            with patch.object(cap, "_image_locations", return_value=locations), \
                    patch.object(cap, "_compile", side_effect=self._precompiled), \
                    patch.object(cap, "_read_image", side_effect=[self.retail, changed_read(None, None)]), \
                    patch.object(cap.platform_compat, "pwrite") as write:
                with self.assertRaisesRegex(cap.GuardianCapError, "changed during compilation"):
                    cap.apply_to_image(path)
                write.assert_not_called()
            self.assertEqual(path.read_bytes(), original)
            os.replace(path, path.with_suffix(".closed"))

    def test_image_foreign_last_resource_never_writes_first_resources(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, original, locations = self._image(Path(tmp).resolve())
            changed = bytearray(original)
            changed[locations["o4002c12"] + 40] ^= 1
            path.write_bytes(changed)
            with patch.object(cap, "_image_locations", return_value=locations), \
                    patch.object(cap.platform_compat, "pwrite") as write:
                self.assertEqual(cap.image_status(path), "foreign")
                with self.assertRaises(cap.GuardianCapError):
                    cap.apply_to_image(path)
                write.assert_not_called()
            self.assertEqual(path.read_bytes(), bytes(changed))
            os.replace(path, path.with_suffix(".closed"))

    def test_real_xiso_spans_match_extracted_evidence(self):
        if not XISO.is_file():
            self.skipTest(f"Retail XISO evidence missing: {XISO}; set NFL2K5_RETAIL_XISO")
        with XISO.open("rb") as stream:
            locations = cap._image_locations(stream.fileno(), os.fstat(stream.fileno()).st_size)
            self.assertEqual(cap._read_image(stream.fileno(), locations), self.retail)
        self.assertEqual(cap.image_status(XISO), "retail")

    def test_short_image_write_is_reported_and_handle_closes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, original, locations = self._image(Path(tmp).resolve())
            with patch.object(cap, "_image_locations", return_value=locations), \
                    patch.object(cap, "_compile", side_effect=self._precompiled), \
                    patch.object(cap.platform_compat, "pwrite", return_value=0):
                with self.assertRaisesRegex(cap.GuardianCapError, "Short guardian-cap write"):
                    cap.apply_to_image(path)
            self.assertEqual(path.read_bytes(), original)
            os.replace(path, path.with_suffix(".closed"))


if __name__ == "__main__":
    unittest.main()

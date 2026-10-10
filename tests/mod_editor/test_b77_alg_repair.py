"""Beta 77 ALG: the Allegiant stretch and grass repair's manifest, its refusals and its idempotence, and the PNG catalog seal.

The bundle checks need the nine v0.5 s20 bundles (ALG_V05_BUNDLES) and the repair's output (ALG_REPAIRED_BUNDLES);
without them only the manifest and catalog checks run."""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import colorsys  # noqa: E402

from mod_editor.core import nfl2k5_allegiant_model as lv  # noqa: E402
from mod_editor.core import nfl2k5_modern_color as colour  # noqa: E402
from mod_editor.core import nfl2k5_modern_metlife as ml  # noqa: E402
from mod_editor.core import nfl2k5_modern_surfaces as ms  # noqa: E402
from tools.b77 import alg_grass_check as gc  # noqa: E402
from tools.b77 import alg_repair as ar  # noqa: E402

V05 = Path(os.environ.get("ALG_V05_BUNDLES", "/nonexistent"))
OUT = Path(os.environ.get("ALG_REPAIRED_BUNDLES", "/nonexistent"))


class Manifest(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads(ar.MANIFEST.read_text(encoding="utf-8"))

    def test_the_manifest_owns_the_nine_stretches_at_the_model_pins(self):
        self.assertEqual(self.doc["schema"], ar.SCHEMA)
        self.assertEqual(sorted(self.doc["bundles"]), sorted(lv.VARIANTS))
        pins = {p["name"]: p for p in lv.model_pins()["bundles"]}
        for name, want in self.doc["bundles"].items():
            pin = pins[name]
            self.assertEqual((want["size"], want["offset"], want["length"]), (pin["size"], pin["offset"], pin["length"]))
            self.assertNotEqual(want["before_stretch_sha256"], want["after_stretch_sha256"])
            self.assertNotEqual(want["after_stretch_sha256"], pin["retail_sha256"])

    def test_the_manifest_owns_the_field_and_divots_spans_and_the_colour_settings(self):
        settings = ar.grass_settings(self.doc)
        self.assertEqual(colour.settings_id(settings), self.doc["colour_settings_sha256"])
        for name, want in self.doc["bundles"].items():
            g = want["grass"]
            self.assertEqual(g["field_offset"], 0, name)
            self.assertLess(g["field_offset"] + g["field_length"], g["divots_offset"], name)
            self.assertLessEqual(g["divots_offset"] + g["divots_length"], want["offset"], name)   # clear of the stretch
            for kind in ("field", "divots"):
                self.assertNotEqual(g[kind + "_before_sha256"], g[kind + "_after_sha256"], (name, kind))

    def test_the_new_target_is_the_designs_and_the_old_one_the_measured_broadcast(self):
        self.assertEqual([round(v, 3) for v in ar.old_target()], [86.0, 114.0, 58.0])
        self.assertEqual([round(v, 3) for v in ar.new_target()], [75.0, 106.0, 49.0])
        luma = lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
        hue = lambda c: colorsys.rgb_to_hsv(*(v / 255 for v in c))[0] * 360
        self.assertLess(luma(ar.new_target()), luma(ar.old_target()) * 0.92)
        self.assertGreater(hue(ar.new_target()), hue(ar.old_target()))

    def test_every_s20_bundle_takes_the_dome_rig(self):
        for name in lv.VARIANTS:
            self.assertEqual(ms.light_class(name, True), "dome")
            self.assertEqual(ms.rig_name("dome", name[3]), "night_indoor")

    def test_an_unowned_bundle_is_refused(self):
        with self.assertRaises(ValueError):
            ar.repair_bundle(b"", "s01dd.iff", self.doc)

    def test_a_bundle_of_the_wrong_size_is_refused(self):
        with self.assertRaises(ValueError):
            ar.repair_bundle(b"\0" * 64, "s20dd.iff", self.doc)


class Catalog(unittest.TestCase):
    def test_the_allegiant_art_is_sealed_in_the_release_catalog(self):
        run = subprocess.run([sys.executable, str(ROOT / "tools" / "b77" / "alg_seal_catalog.py"), "--check"],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertTrue(json.loads(run.stdout)["sealed"])


@unittest.skipUnless((V05 / "s20dd.iff").is_file() and (OUT / "s20dd.iff").is_file(),
                     "needs the v0.5 s20 bundles and the repair's output")
class Bundles(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads(ar.MANIFEST.read_text(encoding="utf-8"))

    def test_an_unexpected_stretch_is_refused(self):
        data = bytearray(ar.read(V05 / "s20dd.iff"))
        want = self.doc["bundles"]["s20dd.iff"]
        data[want["offset"] + want["length"] - 1] ^= 0xFF
        with self.assertRaises(ValueError):
            ar.repair_bundle(bytes(data), "s20dd.iff", self.doc)

    def test_the_v05_input_needs_a_compiled_model(self):
        with self.assertRaises(ValueError):
            ar.repair_bundle(ar.read(V05 / "s20dd.iff"), "s20dd.iff", self.doc)

    def test_the_output_is_already_applied_and_only_the_three_spans_differ(self):
        for name in lv.VARIANTS:
            before, after = ar.read(V05 / name), ar.read(OUT / name)
            want = self.doc["bundles"][name]
            g = want["grass"]
            start, end = want["offset"], want["offset"] + want["length"]
            f_end, d_at = g["field_offset"] + g["field_length"], g["divots_offset"]
            d_end = d_at + g["divots_length"]
            self.assertEqual(len(before), len(after))
            self.assertEqual(before[f_end:d_at], after[f_end:d_at], name)       # detail normal, Fldd and the rest
            self.assertEqual(before[d_end:start], after[d_end:start], name)
            self.assertEqual(before[end:], after[end:], name)
            self.assertEqual(ar.sha(after[start:end]), want["after_stretch_sha256"], name)
            self.assertEqual(ar.sha(before[:f_end]), g["field_before_sha256"], name)
            self.assertEqual(ar.sha(after[:f_end]), g["field_after_sha256"], name)
            self.assertEqual(ar.sha(after[d_at:d_end]), g["divots_after_sha256"], name)
            self.assertNotEqual(before[:f_end], after[:f_end], name)
            again, receipt = ar.repair_bundle(after, name, self.doc)
            self.assertEqual(receipt["state"], "already_applied")
            self.assertEqual(again, after)

    def test_an_unexpected_field_or_divots_span_is_refused(self):
        for offset_key in ("field_offset", "divots_offset"):
            data = bytearray(ar.read(V05 / "s20nd.iff"))
            g = self.doc["bundles"]["s20nd.iff"]["grass"]
            data[g[offset_key] + 100] ^= 0x55
            with self.assertRaises(ValueError):
                ar.repair_grass(bytes(data), "s20nd.iff", self.doc)

    def test_the_recorded_settings_reproduce_the_v05_field_from_its_measured_target(self):
        settings = ar.grass_settings(self.doc)
        for name in ("s20dd.iff", "s20as.iff", "s20nr.iff"):
            data = ar.read(V05 / name)
            (at, size), _d, tint = ar._grass_sites(data, name)
            span = data[at:at + size]
            again, _ = ms.field_span(span, look=ar.LOOK, cls=ar.LIGHT, rig="night_indoor", colour_settings=settings, tint=tint,
                                     target=ar.old_target())
            self.assertEqual(again, span, name)

    def test_only_the_colour_map_and_the_outside_grass_change_in_the_field_scene(self):
        for name in ("s20dd.iff", "s20ad.iff", "s20ns.iff"):
            ranges = []
            decoded = []
            for folder in (V05, OUT):
                data = ar.read(folder / name)
                chunk = ml.bundle_scenes(data)["field"]
                rec, dec = ml._scene(data, chunk)
                rows = ml.texture_rows(rec)
                decoded.append(dec)
                if not ranges:
                    for key in (ms.COLOUR_MATERIAL, ms.OUTSIDE_MATERIAL):
                        ranges.append((chunk.system_bytes + int(rows[key]["pixel_offset"]),
                                       chunk.system_bytes + int(rows[key]["palette_offset"]) + 1024))
            self.assertEqual(len(decoded[0]), len(decoded[1]))
            diff = [i for i, (a, b) in enumerate(zip(decoded[0], decoded[1])) if a != b]
            self.assertTrue(diff, name)
            for i in diff:
                self.assertTrue(any(a <= i < b for a, b in ranges), (name, i))       # no end zone, logo, UV or paint byte moved

    def test_the_turf_draws_the_design_target_in_all_nine_bundles_and_keeps_its_stripes(self):
        settings = ar.grass_settings(self.doc)
        for name in lv.VARIANTS:
            row_old = gc.bundle_check(ar.read(V05 / name), name, settings)
            row_new = gc.bundle_check(ar.read(OUT / name), name, settings)
            for got, want in zip(row_new["field_on_screen"], ar.new_target()):
                self.assertAlmostEqual(got, want, delta=want * 0.012, msg=name)
            self.assertLess(row_new["field_on_screen_luma"], row_old["field_on_screen_luma"] * 0.96, name)   # afternoon was 4% under its target already
            # the mowing stripes stay as subtle as before: the same relative spread of the map
            rel_old = row_old["map_luma_std"] / (0.299 * row_old["map_mean"][0] + 0.587 * row_old["map_mean"][1] + 0.114 * row_old["map_mean"][2])
            rel_new = row_new["map_luma_std"] / (0.299 * row_new["map_mean"][0] + 0.587 * row_new["map_mean"][1] + 0.114 * row_new["map_mean"][2])
            self.assertAlmostEqual(rel_new, rel_old, delta=0.012, msg=name)
            self.assertEqual(row_new["fldd_tint"], row_old["fldd_tint"], name)

    def test_the_divots_keep_their_luminance_and_every_other_entry(self):
        for name in ("s20dd.iff", "s20ds.iff"):
            palettes = []
            for folder in (V05, OUT):
                data = ar.read(folder / name)
                at, size = ms.bundle_sites(data)["divots"]
                tx, _h = ms._tools()
                chunk = tx.parse_chunks(data[at:at + size], allow_trailing=True)[0]
                out, _ = tx.decode_chunk(data[at:at + size], chunk)
                info = tx.parse_texture(out, chunk)
                palettes.append(bytes(out[chunk.system_bytes + info.palette_offset:chunk.system_bytes + info.palette_offset + 1024]))
            moved = 0
            for i in range(256):
                old, new = palettes[0][i * 4:i * 4 + 4], palettes[1][i * 4:i * 4 + 4]
                self.assertEqual(old[3], new[3])
                if old != new:
                    moved += 1
                    luma = lambda e: 0.299 * e[2] + 0.587 * e[1] + 0.114 * e[0]
                    self.assertAlmostEqual(luma(old), luma(new), delta=4)
                    h = colorsys.rgb_to_hsv(old[2] / 255, old[1] / 255, old[0] / 255)
                    self.assertTrue(60 <= h[0] * 360 <= 160 and h[1] > 0.15)
            self.assertGreater(moved, 0)

    def test_the_v05_fan_banners_are_carried_across(self):
        for name in ("s20dd.iff", "s20ns.iff"):
            have, got = ar.fan_payloads(ar.read(V05 / name)), ar.fan_payloads(ar.read(OUT / name))
            for key in have:
                self.assertEqual(have[key]["bytes"], got[key]["bytes"], (name, key))


if __name__ == "__main__":
    unittest.main()

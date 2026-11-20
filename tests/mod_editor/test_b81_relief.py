"""b81-uniforms: the 2026 jersey relief at level B on every 2026 kit package (Noah 2026-11-19: "B. Keep new.").

data/nfl2k5_relief_2026_b81u.json and its art folder, mod_editor/core/nfl2k5_relief_2026.py and the optional build step
relief_2026_b81u. b81-retail-free-art (schema v2): the retail-derived base of every map (the 2004 folds softened, the
2004 construction lifted out) is derived at build time from the user's own disc; only the authored differences ship.

The document's shape and pins; that no shipped relief file is a retail-derived map (the guard the catalog generator
applies, and the measured old masters it refuses); the numpy base port against scipy (where scipy is installed); the
composer and its mip chain against the bump writer's; the build hook; and, with the retail disc and the released v0.9
disc on this machine (B81_RETAIL_DISC, B81_UNIFORM_DISC), every slot waiting at its pinned input and a sample of kits
derived from the retail disc and compiled to their output pins."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/b77")]
from mod_editor.core import build_steps, mod_build, nfl2k5_relief_2026 as rl  # noqa: E402
from mod_editor.core import nfl2k5_bump_texture_writer as bump  # noqa: E402
import modern_art_png_catalog as catalog  # noqa: E402

DISC = Path(os.environ.get("B81_UNIFORM_DISC", "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.9 (2026-11-05).xiso.iso"))
RETAIL = Path(os.environ.get("B81_RETAIL_DISC", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
SIZES = {"bump_jersey": (512, 256), "bump_sleeve": (128, 128), "bump_pants": (512, 256)}
#: three kits with different collar openings, shields and maker's marks (Cowboys throwback: the small shield, the pants
#: shield at its own place, swooshes on the torso caps with wrap-over slivers)
SAMPLE = ("18H0", "01A0", "07H9")
ART = "data/nfl2k5_relief_2026_b81u/"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tilt(rgba):
    n = rgba[..., :2].astype(float) / 127.5 - 1.0
    return np.hypot(n[..., 0], n[..., 1]) * 127


def normal_map(rng, h, w):
    """A plausible absolute tangent-space normal map (what the withdrawn v1 masters were)."""
    xy = rng.normal(0, 0.15, (h, w, 2))
    z = np.sqrt(np.clip(1 - (xy ** 2).sum(-1), 0, 1))
    n = np.dstack([xy, z])
    return np.dstack([np.clip(np.round(n * 127.5 + 127.5), 0, 255).astype(np.uint8), np.full((h, w), 255, np.uint8)])


def png(rgba):
    from io import BytesIO
    from PIL import Image
    out = BytesIO()
    Image.fromarray(rgba, "RGBA").save(out, "PNG")
    return out.getvalue()


class Document(unittest.TestCase):
    def setUp(self):
        self.doc = rl.relief_b81u()

    def test_every_kit_has_its_three_slots_pinned(self):
        slots = self.doc["slots"]
        kits = {r["selector"] for r in slots}
        self.assertEqual(len(kits), 178)
        self.assertEqual(len(slots), 3 * 178)
        for row in slots:
            for key in ("before_sha256", "after_sha256", "composed_sha256"):
                self.assertEqual(len(row[key]), 64, row)
            self.assertNotEqual(row["before_sha256"], row["after_sha256"], row)
            self.assertEqual(row["base"], "before" if row["slot"] == "bump_pants" else "retail")
            self.assertEqual(row["chunk"], {"bump_jersey": 45, "bump_sleeve": 46, "bump_pants": 47}[row["slot"]])
            self.assertEqual(row["offset"] + row["length"] <= row["resource_size"], True)
            if row["slot"] == "bump_pants":
                self.assertEqual([tuple(b) for b in row["worked"][:2]], list(rl.OLD_PANTS))

    def test_the_bases_are_pinned_retail_maps_and_the_kernels_are_stored(self):
        self.assertEqual(set(self.doc["bases"]), {"bump_jersey", "bump_sleeve"})
        for slot, entry in self.doc["bases"].items():
            self.assertEqual((entry["selector"], entry["chunk"]), ("18H0", {"bump_jersey": 45, "bump_sleeve": 46}[slot]))
            self.assertEqual(len(entry["span_sha256"]), 64)
        kernels = rl.Kernels(self.doc["gauss_kernels"])
        self.assertEqual(sorted(kernels.table), sorted(float(s) for s in rl.SIGMAS))
        self.assertEqual(rl.kernel_table(rl.SIGMAS), self.doc["gauss_kernels"])

    def test_the_art_is_two_difference_masters_the_island_mask_and_small_patches_each_stored_once(self):
        folder = rl.art_folder(self.doc)
        self.assertEqual(folder, ROOT / "data/nfl2k5_relief_2026_b81u")
        self.assertEqual(set(self.doc["masters"]), {"bump_jersey", "bump_sleeve"})     # pants: patches only
        for name, entry in self.doc["masters"].items():
            self.assertEqual((entry["width"], entry["height"]), SIZES[name])
        files = sorted(p.name for p in folder.glob("*.png"))
        named = sorted([m["png"] for m in self.doc["masters"].values()] + [p["png"] for p in self.doc["patches"].values()]
                       + [self.doc["bases"]["bump_jersey"][m]["png"] for m in ("islands", "openings")])
        self.assertEqual(files, named)
        self.assertEqual(len(set(p["sha256"] for p in self.doc["patches"].values())), len(self.doc["patches"]))
        self.assertLess(sum((folder / f).stat().st_size for f in files), 1024 * 1024)
        used = {r["patch"] for r in self.doc["slots"] if r["patch"]}
        self.assertEqual(used, set(self.doc["patches"]))
        for key, entry in self.doc["patches"].items():
            patch = rl.read_art(folder, entry)
            w, h = SIZES[entry["slot"]]
            self.assertLessEqual(entry["x"] + entry["width"], w)
            self.assertLessEqual(entry["y"] + entry["height"], h)
            self.assertTrue(set(np.unique(patch[..., 3])) <= {0, 255}, key)
            self.assertLess(int((patch[..., 3] == 255).sum()), 6000, key)              # a patch, not a map
        island = rl.islands(self.doc)
        self.assertEqual(island.shape, (512, 1024))
        collars = rl.openings(self.doc)
        self.assertEqual(len(collars), self.doc["bases"]["bump_jersey"]["openings"]["count"])
        self.assertEqual({r["opening"] for r in self.doc["slots"] if r["slot"] == "bump_jersey"}, set(range(len(collars))))
        for mask in collars:
            self.assertTrue(mask[:, :125].sum() == 0 and mask[158:].sum() == 0 and mask.any())     # inside the neck

    def test_a_pinned_png_that_changed_is_refused(self):
        entry = dict(next(iter(self.doc["masters"].values())))
        entry["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            rl.read_art(rl.art_folder(self.doc), entry)

    def test_the_art_folder_must_be_a_plain_relief_folder_name(self):
        for name in ("../nfl2k5_relief_2026_b81u", "nfl2k5_kit_fixes_2026", None):
            with self.assertRaises(ValueError):
                rl.art_folder(dict(self.doc, art=name))

    def test_a_v1_document_with_absolute_masters_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "v1.json"
            path.write_text(json.dumps(dict(self.doc, schema="nfl2k5_relief_2026/v1")), encoding="utf-8")
            with self.assertRaises(ValueError):
                rl.spec(path)
            rows = [dict(r, base="master") if r["slot"] == "bump_jersey" else r for r in self.doc["slots"]]
            path.write_text(json.dumps(dict(self.doc, slots=rows)), encoding="utf-8")
            with self.assertRaises(ValueError):
                rl.spec(path)


class RetailFree(unittest.TestCase):
    """b81-retail-free-art: a relief file that carries a retail-derived map must never reach the package again."""

    def test_no_shipped_relief_file_decodes_as_an_absolute_normal_map(self):
        allow = (ROOT / "packaging/release-allowlist.txt").read_text(encoding="utf-8").splitlines()
        shipped = sorted(line.strip() for line in allow if line.strip().startswith(ART) and line.strip().endswith(".png"))
        on_disk = sorted(ART + p.name for p in rl.art_folder(rl.relief_b81u()).glob("*.png"))
        self.assertEqual(shipped, on_disk)
        for relative in shipped:
            self.assertIsNone(catalog.relief_problem(relative, (ROOT / relative).read_bytes()), relative)

    def test_the_guard_refuses_an_absolute_map_a_patch_of_one_and_a_grey_island_mask(self):
        rng = np.random.default_rng(81)
        self.assertIsNotNone(catalog.relief_problem(ART + "master_jersey.png", png(normal_map(rng, 256, 512))))
        patch = np.zeros((40, 60, 4), np.uint8)
        patch[5:35, 5:55] = normal_map(rng, 30, 50)
        self.assertIsNotNone(catalog.relief_problem(ART + "pants_0123456789abcdef.png", png(patch)))
        grey = np.full((8, 8, 4), 255, np.uint8)
        grey[..., :3] = 128
        self.assertIsNotNone(catalog.relief_problem(ART + "islands_jersey.png", png(grey)))
        diff = np.zeros((256, 512, 4), np.uint8)
        diff[..., 3] = 255
        diff[100:110, 100:110, :3] = (3, 251, 254)
        self.assertIsNone(catalog.relief_problem(ART + "difference_jersey.png", png(diff)))

    def test_the_catalog_lists_every_relief_file_and_refuses_a_retail_shaped_one(self):
        document = json.loads((ROOT / catalog.CATALOG).read_text(encoding="utf-8"))
        listed = sorted(p for p in document["files"] if p.startswith(ART))
        self.assertEqual(listed, sorted(ART + p.name for p in rl.art_folder(rl.relief_b81u()).glob("*.png")))
        self.assertIn(ART, catalog.FOLDERS)
        self.assertIn("refuses any relief file", document["classification"])

    def test_the_difference_masters_are_mostly_zero(self):
        doc = rl.relief_b81u()
        for name, entry in doc["masters"].items():
            d = rl.read_art(rl.art_folder(doc), entry)[..., :3]
            self.assertGreater(float((d == 0).all(-1).mean()), 0.5, name)


try:
    from scipy import ndimage as ndi
except ImportError:      # the Studio runtime has no scipy; the port is checked where the authoring tools run
    ndi = None


@unittest.skipIf(ndi is None, "scipy is not installed (authoring machines only)")
class BasePortEqualsScipy(unittest.TestCase):
    """The build-time base is bump_true's scipy arithmetic to the bit."""

    def setUp(self):
        self.rng = np.random.default_rng(2026)
        self.gauss = rl.Kernels(rl.relief_b81u()["gauss_kernels"])

    def test_gaussian_filter(self):
        for sigma in rl.SIGMAS:
            a = self.rng.standard_normal((96, 160))
            self.assertTrue(np.array_equal(self.gauss(a, sigma), ndi.gaussian_filter(a, sigma)), sigma)

    def test_morphology_components_and_holes(self):
        m = self.rng.random((120, 200)) > 0.55
        for n in (1, 4, 6):
            self.assertTrue(np.array_equal(rl.dilate(m, n), ndi.binary_dilation(m, iterations=n)))
            self.assertTrue(np.array_equal(rl.erode(m, n), ndi.binary_erosion(m, iterations=n)))
            self.assertTrue(np.array_equal(rl.dilate(rl.erode(m, n), n), ndi.binary_opening(m, iterations=n)))
            self.assertTrue(np.array_equal(rl.erode(rl.dilate(m, n), n), ndi.binary_closing(m, iterations=n)))
        labels, sizes = rl.components(m)
        theirs, count = ndi.label(m)
        self.assertEqual(len(sizes) - 1, count)
        self.assertEqual(sorted(sizes[1:].tolist()), sorted(ndi.sum(m, theirs, np.arange(1, count + 1)).astype(int).tolist()))
        self.assertTrue(np.array_equal(rl.fill_holes(m), ndi.binary_fill_holes(m)))

    def test_distance_below_the_cap(self):
        feature = self.rng.random((90, 130)) > 0.995
        mine = rl.distance_within(feature, 28)
        theirs = ndi.distance_transform_edt(~feature)
        near = theirs < 28
        self.assertTrue(np.array_equal(mine[near], theirs[near]))
        self.assertTrue((mine[~near] >= 28).all())

    def test_bilinear_enlargement(self):
        from PIL import Image
        rgb = self.rng.integers(0, 256, (32, 48, 3), dtype=np.uint8)
        theirs = np.asarray(Image.fromarray(rgb).resize((96, 64), Image.BILINEAR)).astype(np.float64) / 127.5 - 1.0
        self.assertTrue(np.array_equal(rl.decode_map(np.dstack([rgb, rgb[..., :1]])), theirs))


class Composer(unittest.TestCase):
    def test_the_mip_chain_is_the_bump_writers_box_filter(self):
        rng = np.random.default_rng(81)
        for w, h, levels in ((512, 256, 6), (128, 128, 5)):
            rgba = rng.integers(0, 256, (h, w, 4), dtype=np.uint8)
            mine = rl.mip_levels(rgba, levels)
            theirs = bump.generate_mips(rgba.tobytes(), w, h, levels)
            self.assertEqual([m.tobytes() for m in mine], [t.rgba for t in theirs])

    def test_a_patch_replaces_only_its_opaque_texels_and_alpha_ends_opaque(self):
        base = np.zeros((8, 8, 4), np.uint8)
        base[..., 3] = 7
        patch = np.zeros((2, 3, 4), np.uint8)
        patch[0, 1] = (10, 20, 30, 255)
        out = rl.compose(base, patch, (4, 5))
        self.assertEqual(tuple(out[5, 5]), (10, 20, 30, 255))
        self.assertEqual(int((out[..., :3] != 0).any(-1).sum()), 1)
        self.assertTrue((out[..., 3] == 255).all())
        half = patch.copy()
        half[1, 1, 3] = 128
        with self.assertRaises(ValueError):
            rl.compose(base, half, (4, 5))
        with self.assertRaises(ValueError):
            rl.compose(base, patch, (6, 5))

    def test_a_difference_adds_back_to_the_authored_map_modulo_256(self):
        rng = np.random.default_rng(7)
        authored = rng.integers(0, 256, (16, 16, 4), dtype=np.uint8)
        base = rng.integers(0, 256, (16, 16, 4), dtype=np.uint8)
        difference = rl.difference_of(authored, base)
        back = rl.add_difference(base, difference)
        self.assertTrue(np.array_equal(back[..., :3], authored[..., :3]))
        self.assertTrue((back[..., 3] == 255).all())
        self.assertTrue((rl.difference_of(base, base)[..., :3] == 0).all())

    def test_the_body_is_the_system_buffer_then_the_swizzled_bgra_chain(self):
        rgba = np.zeros((4, 4, 4), np.uint8)
        rgba[..., 0] = 200
        rgba[..., 3] = 255
        out = rl.body(b"SYS", rgba, 3)
        self.assertTrue(out.startswith(b"SYS"))
        self.assertEqual(len(out), 3 + 4 * (16 + 4 + 1))
        self.assertEqual(out[3:7], bytes((0, 0, 200, 255)))                 # stored B, G, R, A


class BuildHook(unittest.TestCase):
    def test_an_optional_labelled_step_right_after_the_uniform_pass_numbers_reading_the_retail_disc(self):
        self.assertIn("relief_2026_b81u", mod_build.OPTIONAL_STEPS)
        self.assertEqual(build_steps.STEP_LABELS["relief_2026_b81u"], "the 2026 jersey relief")
        source = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        digits = source.index("apply_digits_b81(target)")
        relief = source.index("apply_relief_b81u(target")
        self.assertLess(digits, relief)
        self.assertLess(relief, source.index('if loaded_weather_plan is not None:'))
        self.assertIn('"2026 jersey relief"), progress=progress)', source[relief:relief + 400])

    def test_the_module_document_and_art_are_shipped_and_pinned(self):
        from mod_editor.core.providers import Nfl2k5UnifiedVisualProvider
        provider = Nfl2k5UnifiedVisualProvider()
        allow = (ROOT / "packaging/release-allowlist.txt").read_text(encoding="utf-8").splitlines()
        self.assertIn("mod_editor/core/nfl2k5_relief_2026.py", allow)
        self.assertIn("mod_editor/core/nfl2k5_relief_2026.py", provider.module_pins)
        paths = ["data/nfl2k5_relief_2026_b81u.json"] + [f"data/nfl2k5_relief_2026_b81u/{p.name}"
                                                          for p in sorted(rl.art_folder(rl.relief_b81u()).glob("*.png"))]
        for path in paths:
            self.assertIn(path, allow)
            self.assertEqual(provider.data_pins[path], sha((ROOT / path).read_bytes()), path)

    def test_an_image_it_cannot_read_is_left_alone_unless_strict(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "not_a_disc.iso"
            path.write_bytes(b"\0" * 4096)
            self.assertEqual(rl.apply_relief_b81u(path)["state"], "other_image")
            with self.assertRaises((ValueError, OSError)):
                rl.apply_relief_b81u(path, strict=True)

    def test_a_disc_without_the_pinned_retail_maps_gives_no_base(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "not_a_disc.iso"
            path.write_bytes(b"\0" * 4096)
            self.assertIsNone(rl.retail_maps(rl.relief_b81u(), path))


@unittest.skipUnless(DISC.is_file() and RETAIL.is_file(), "the released v0.9 disc or the retail disc is not on this machine")
class ReleasedDisc(unittest.TestCase):
    """The bump spans of a v0.10 build at this step are the released v0.9 ones (this job's two other passes change
    colour textures and digits only), so every slot waits at its pinned input on the released disc."""

    @classmethod
    def setUpClass(cls):
        cls.doc = rl.relief_b81u()
        cls.kits = {}
        with bump._Image.open(DISC, writable=False) as image:
            index = bump._parsed_index(image)
            for entry in index.entries:
                name = bump.logical_name_for(entry.name_id)
                if name and name[:-4] in {r["selector"] for r in cls.doc["slots"]}:
                    cls.kits[name[:-4]] = image.read_segments(index.sub_extents(entry, 0, entry.size))
        cls.retail = rl.retail_maps(cls.doc, RETAIL)

    def test_every_slot_waits_at_its_pinned_input(self):
        states = {}
        for row in self.doc["slots"]:
            state, _chunk, _span = rl.state_of(row, self.kits[row["selector"]])
            states.setdefault(state, []).append((row["selector"], row["slot"]))
        self.assertEqual(sorted(states), ["before"], {k: v[:5] for k, v in states.items()})

    def test_the_retail_disc_holds_the_pinned_base_maps(self):
        self.assertIsNotNone(self.retail)
        self.assertEqual(self.retail["bump_jersey"].shape, (256, 512, 4))
        self.assertEqual(self.retail["bump_sleeve"].shape, (128, 128, 4))

    def test_a_sample_compiles_from_the_retail_base_to_its_pins_and_decodes_to_the_composed_map(self):
        from nfl_txtr import decode_chunk, parse_chunks, parse_texture, texture_to_rgba
        rows = [r for r in self.doc["slots"] if r["selector"] in SAMPLE]
        spans = {}
        for row in rows:
            spans[(row["selector"], row["slot"])] = rl.state_of(row, self.kits[row["selector"]])[2]
        results = rl.compile_slots(rows, spans, self.doc, retail=self.retail, count=1)
        for row in rows:
            new, detail = results[(row["selector"], row["slot"])]
            self.assertEqual(sha(new), row["after_sha256"], row["selector"] + " " + row["slot"])
            self.assertLessEqual(detail["packed_bytes"], detail["stored_size"])
            chunk = parse_chunks(new)[0]
            decoded, _ = decode_chunk(new, chunk)
            texture = parse_texture(decoded, chunk)
            rgba = np.frombuffer(texture_to_rgba(decoded, chunk, texture), np.uint8).reshape(texture.height, texture.width, 4)
            self.assertEqual(sha(rgba.tobytes()), row["composed_sha256"])
            if row["slot"] == "bump_jersey":                        # the approved prototype, within 10 percent
                t = tilt(rgba)
                self.assertLess(abs(float(np.median(t[t > 0.5])) - 9.9), 0.99, row["selector"])
                self.assertLess(abs(float(np.percentile(t, 90)) - 25.6), 2.56, row["selector"])

    def test_the_shipped_differences_hold_no_retail_texel(self):
        """The difference master is not the retail map, nor the base derived from it: almost no texel of it equals
        either (the zero difference is no texel value of any map)."""
        gauss = rl.Kernels(self.doc["gauss_kernels"])
        folder = rl.art_folder(self.doc)
        for slot in ("bump_jersey", "bump_sleeve"):
            difference = rl.read_art(folder, self.doc["masters"][slot])[..., :3]
            if slot == "bump_sleeve":
                base = rl.sleeve_base(gauss, self.retail[slot])
            else:
                row = next(r for r in self.doc["slots"] if r["selector"] == "18H0" and r["slot"] == "bump_jersey")
                opening = rl.openings(self.doc)[row["opening"]]
                base = rl.jersey_base(gauss, self.retail[slot], opening, rl.islands(self.doc))
            for reference in (self.retail[slot][..., :3], base[..., :3]):
                same = (difference == reference).all(-1)
                self.assertLess(float(same.mean()), 0.001, slot)

    def test_a_slot_holding_other_art_is_left_alone_and_refused_when_strict(self):
        row = next(r for r in self.doc["slots"] if r["selector"] == "18H0" and r["slot"] == "bump_sleeve")
        raw = bytearray(self.kits["18H0"])
        raw[row["offset"] + 100] ^= 0xFF
        self.assertEqual(rl.state_of(row, bytes(raw))[0], "other")


if __name__ == "__main__":
    unittest.main()

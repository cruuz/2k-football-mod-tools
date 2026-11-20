"""b81-uniforms: the 2026 jersey relief at level B on every 2026 kit package (Noah 2026-11-19: "B. Keep new.").

data/nfl2k5_relief_2026_b81u.json and its art folder, mod_editor/core/nfl2k5_relief_2026.py and the optional build step
relief_2026_b81u. The document's shape and pins, the shipped art (two masters, small patches), the composer and its mip
chain against the bump writer's, the build hook, and (with the released v0.9 disc on this machine, B81_UNIFORM_DISC)
every slot waiting at its pinned input and a sample of kits compiled to their output pins."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import build_steps, mod_build, nfl2k5_relief_2026 as rl  # noqa: E402
from mod_editor.core import nfl2k5_bump_texture_writer as bump  # noqa: E402

DISC = Path(os.environ.get("B81_UNIFORM_DISC", "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.9 (2026-11-05).xiso.iso"))
SIZES = {"bump_jersey": (512, 256), "bump_sleeve": (128, 128), "bump_pants": (512, 256)}
#: three kits with different collar openings, shields and maker's marks (Cowboys throwback: the small shield, the pants
#: shield at its own place, swooshes on the torso caps with wrap-over slivers)
SAMPLE = ("18H0", "01A0", "07H9")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tilt(rgba):
    n = rgba[..., :2].astype(float) / 127.5 - 1.0
    return np.hypot(n[..., 0], n[..., 1]) * 127


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
            self.assertEqual(row["base"], "before" if row["slot"] == "bump_pants" else "master")
            self.assertEqual(row["chunk"], {"bump_jersey": 45, "bump_sleeve": 46, "bump_pants": 47}[row["slot"]])
            self.assertEqual(row["offset"] + row["length"] <= row["resource_size"], True)

    def test_the_art_is_two_masters_and_small_patches_each_stored_once(self):
        folder = rl.art_folder(self.doc)
        self.assertEqual(folder, ROOT / "data/nfl2k5_relief_2026_b81u")
        self.assertEqual(set(self.doc["masters"]), {"bump_jersey", "bump_sleeve"})     # pants: the kit's own map
        for name, entry in self.doc["masters"].items():
            self.assertEqual((entry["width"], entry["height"]), SIZES[name])
        files = sorted(p.name for p in folder.glob("*.png"))
        named = sorted([m["png"] for m in self.doc["masters"].values()] + [p["png"] for p in self.doc["patches"].values()])
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

    def test_a_pinned_png_that_changed_is_refused(self):
        entry = dict(next(iter(self.doc["masters"].values())))
        entry["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            rl.read_art(rl.art_folder(self.doc), entry)

    def test_the_art_folder_must_be_a_plain_relief_folder_name(self):
        for name in ("../nfl2k5_relief_2026_b81u", "nfl2k5_kit_fixes_2026", None):
            with self.assertRaises(ValueError):
                rl.art_folder(dict(self.doc, art=name))

    def test_every_jersey_holds_level_b(self):
        folder = rl.art_folder(self.doc)
        master = rl.read_art(folder, self.doc["masters"]["bump_jersey"])
        for key in sorted({r["patch"] for r in self.doc["slots"] if r["slot"] == "bump_jersey"}):
            entry = self.doc["patches"][key]
            t = tilt(rl.compose(master, rl.read_art(folder, entry), (entry["x"], entry["y"])))
            median, p90 = float(np.median(t[t > 0.5])), float(np.percentile(t, 90))
            self.assertLess(abs(median - 9.9), 0.99, key)          # the approved prototype, within 10 percent
            self.assertLess(abs(p90 - 25.6), 2.56, key)


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

    def test_the_body_is_the_system_buffer_then_the_swizzled_bgra_chain(self):
        rgba = np.zeros((4, 4, 4), np.uint8)
        rgba[..., 0] = 200
        rgba[..., 3] = 255
        out = rl.body(b"SYS", rgba, 3)
        self.assertTrue(out.startswith(b"SYS"))
        self.assertEqual(len(out), 3 + 4 * (16 + 4 + 1))
        self.assertEqual(out[3:7], bytes((0, 0, 200, 255)))                 # stored B, G, R, A


class BuildHook(unittest.TestCase):
    def test_an_optional_labelled_step_right_after_the_uniform_pass_numbers(self):
        self.assertIn("relief_2026_b81u", mod_build.OPTIONAL_STEPS)
        self.assertEqual(build_steps.STEP_LABELS["relief_2026_b81u"], "the 2026 jersey relief")
        source = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        digits = source.index("apply_digits_b81(target)")
        relief = source.index("apply_relief_b81u(target")
        self.assertLess(digits, relief)
        self.assertLess(relief, source.index('if loaded_weather_plan is not None:'))

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


@unittest.skipUnless(DISC.is_file(), "the released v0.9 disc is not on this machine")
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

    def test_every_slot_waits_at_its_pinned_input(self):
        states = {}
        for row in self.doc["slots"]:
            state, _chunk, _span = rl.state_of(row, self.kits[row["selector"]])
            states.setdefault(state, []).append((row["selector"], row["slot"]))
        self.assertEqual(sorted(states), ["before"], {k: v[:5] for k, v in states.items()})

    def test_a_sample_compiles_to_its_pins_and_decodes_to_the_composed_map(self):
        from nfl_txtr import decode_chunk, parse_chunks, parse_texture, texture_to_rgba
        rows = [r for r in self.doc["slots"] if r["selector"] in SAMPLE]
        spans = {}
        for row in rows:
            spans[(row["selector"], row["slot"])] = rl.state_of(row, self.kits[row["selector"]])[2]
        results = rl.compile_slots(rows, spans, self.doc, count=1)
        for row in rows:
            new, detail = results[(row["selector"], row["slot"])]
            self.assertEqual(sha(new), row["after_sha256"], row["selector"] + " " + row["slot"])
            self.assertLessEqual(detail["packed_bytes"], detail["stored_size"])
            chunk = parse_chunks(new)[0]
            decoded, _ = decode_chunk(new, chunk)
            texture = parse_texture(decoded, chunk)
            self.assertEqual(sha(texture_to_rgba(decoded, chunk, texture)), row["composed_sha256"])

    def test_a_slot_holding_other_art_is_left_alone_and_refused_when_strict(self):
        row = next(r for r in self.doc["slots"] if r["selector"] == "18H0" and r["slot"] == "bump_sleeve")
        raw = bytearray(self.kits["18H0"])
        raw[row["offset"] + 100] ^= 0xFF
        self.assertEqual(rl.state_of(row, bytes(raw))[0], "other")


if __name__ == "__main__":
    unittest.main()

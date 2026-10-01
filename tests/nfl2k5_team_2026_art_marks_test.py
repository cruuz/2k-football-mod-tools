"""The 2026 team art tool's official marks (tools/nfl2k5_team_2026_art.py, job uw): the NFL shield and the maker's
swoosh are pinned masters loaded from the user's files, never drawn; how they are placed and lit on the kit textures.

The real masters are trademark renders that never ship in the repository, so the placement tests use synthetic
stand-ins registered under the mark names (the pins are exercised on their own)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "tools", ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import nfl2k5_team_2026_art as art  # noqa: E402


def two_tone_mark(h: int = 40, w: int = 120) -> np.ndarray:
    """An opaque stand-in whose left half (the hook end) is red and right half (the tip end) is blue."""
    rgba = np.zeros((h, w, 4), np.float32)
    rgba[..., 3] = 1.0
    rgba[:, : w // 2, 0] = 1.0
    rgba[:, w // 2:, 2] = 1.0
    return rgba


class StandIn:
    """Registers synthetic masters under the official names for one test (the pins are bypassed on purpose)."""

    def __init__(self, **marks):
        self.marks = marks

    def __enter__(self):
        self.saved = dict(art._UNIFORM_MARKS)
        art._UNIFORM_MARKS.clear()
        for name, rgba in self.marks.items():
            art._UNIFORM_MARKS[name] = {"rgba": rgba, "sha256": "stand-in", "file": "stand-in"}
        return self

    def __exit__(self, *exc):
        art._UNIFORM_MARKS.clear()
        art._UNIFORM_MARKS.update(self.saved)
        return False


class NeverDrawnTest(unittest.TestCase):
    def test_the_drawn_marks_are_gone(self):
        self.assertFalse(hasattr(art, "swoosh_points"))
        self.assertFalse(hasattr(art, "shield_layers"))

    def test_a_mark_without_the_masters_is_refused(self):
        with StandIn():
            with self.assertRaises(SystemExit) as caught:
                art.uniform_mark("nike_swoosh")
        self.assertIn("--uniform-marks", str(caught.exception))

    def test_every_committed_spec_names_resolvable_mark_colours(self):
        for path in sorted((ROOT / "data" / "nfl2k5_teams_2026").glob("*.json")):
            spec = art.Spec(path)
            for side, kit in spec.data["kits"].items():
                sw = kit["torso"].get("sleeve_swooshes")
                if sw:
                    spec.colour(sw["colour"])
                spec.colour(kit["pants"]["swoosh_colour"])


class PinsTest(unittest.TestCase):
    def write(self, folder: Path, name: str, rgba: np.ndarray) -> str:
        Image.fromarray((rgba * 255).astype(np.uint8), "RGBA").save(folder / name)
        return hashlib.sha256((folder / name).read_bytes()).hexdigest()

    def test_an_unreviewed_master_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            digest = self.write(folder, "swoosh.png", two_tone_mark())
            shield = self.write(folder, "shield.png", two_tone_mark(60, 44))
            doc = {"schema": art.UNIFORM_MARKS_SCHEMA,
                   "marks": {"nike_swoosh": {"file": "swoosh.png", "sha256": digest},
                             "nfl_shield": {"file": "shield.png", "sha256": shield}}}
            (folder / "manifest.json").write_text(json.dumps(doc))
            with StandIn():
                with self.assertRaises(SystemExit) as caught:
                    art.use_uniform_marks(folder / "manifest.json")
            self.assertIn("not the reviewed", str(caught.exception))

    def test_a_manifest_must_name_both_masters(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            doc = {"schema": art.UNIFORM_MARKS_SCHEMA, "marks": {}}
            (folder / "manifest.json").write_text(json.dumps(doc))
            with StandIn():
                with self.assertRaises(SystemExit):
                    art.use_uniform_marks(folder / "manifest.json")


class PlaceMarkTest(unittest.TestCase):
    def canvas(self, h=64, w=96, grey=0.5) -> np.ndarray:
        out = np.zeros((h, w, 4), np.float32)
        out[..., :3] = grey
        out[..., 3] = 1.0
        return out

    def test_box_centre_and_antialiased_edges(self):
        with StandIn(nike_swoosh=two_tone_mark()):
            out = self.canvas()
            art.place_mark(out, "nike_swoosh", (48.0, 32.0), 29.0, 10.0, colour=np.array([1.0, 1.0, 1.0], np.float32))
        white = out[..., 0] > 0.75
        ys, xs = np.nonzero(white)
        self.assertAlmostEqual((xs.min() + xs.max() + 1) / 2.0, 48.0, delta=0.6)
        self.assertAlmostEqual((ys.min() + ys.max() + 1) / 2.0, 32.0, delta=0.6)
        self.assertAlmostEqual(xs.max() + 1 - xs.min(), 29.0, delta=1.0)
        # a box edge falling mid-texel (x 33.5) is a partial texel, not a hard step
        edge = out[32, 33, 0]
        self.assertTrue(0.55 < edge < 0.95, edge)

    def test_mirror_swaps_the_ends(self):
        with StandIn(nike_swoosh=two_tone_mark()):
            plain, flipped = self.canvas(), self.canvas()
            art.place_mark(plain, "nike_swoosh", (48.0, 32.0), 40.0, 12.0)
            art.place_mark(flipped, "nike_swoosh", (48.0, 32.0), 40.0, 12.0, mirror=True)
        self.assertGreater(plain[32, 36, 0], 0.9)       # hook end (red) on the left
        self.assertGreater(plain[32, 60, 2], 0.9)       # tip end (blue) on the right
        self.assertGreater(flipped[32, 36, 2], 0.9)
        self.assertGreater(flipped[32, 60, 0], 0.9)

    def test_the_texture_lighting_carries_into_the_mark(self):
        with StandIn(nike_swoosh=two_tone_mark()):
            out = self.canvas()
            out[..., :3] *= np.linspace(0.8, 1.2, out.shape[1], dtype=np.float32)[None, :, None]
            art.place_mark(out, "nike_swoosh", (48.0, 32.0), 60.0, 12.0, colour=np.array([0.5, 0.5, 0.5], np.float32))
        self.assertLess(out[32, 22, 0], out[32, 74, 0])  # darker where the cloth is darker


class SleeveSwooshTest(unittest.TestCase):
    def test_the_tip_points_the_same_way_on_both_arms(self):
        # s runs from the hook end at the front to the tip end at the back on both arms (the grid is measured in
        # 3D): the hook-end half lands at s < 0.5 and the tip-end half at s > 0.5, with no flip for either arm
        g = art.SLEEVE_SWOOSH
        with StandIn(nike_swoosh=two_tone_mark()):
            for arm in ("R", "L"):
                out = np.zeros((128 * art.MASTER, 128 * art.MASTER, 4), np.float32)
                out[..., 3] = 1.0
                art.sleeve_swoosh(out, None, arm)
                for s_val, channel in ((0.15, 0), (0.85, 2)):
                    i = int(np.argmin(np.abs(np.asarray(g["s"]) - s_val)))
                    j = int(np.argmin(np.abs(np.asarray(g["t"]) - 0.5)))
                    x = g[arm]["x"][j][i] * art.MASTER
                    y = g[arm]["y"][j][i] * art.MASTER
                    self.assertGreater(out[int(y), int(x), channel], 0.8, (arm, s_val))

    def test_the_arms_use_their_own_islands(self):
        g = art.SLEEVE_SWOOSH
        self.assertLess(max(max(r) for r in g["R"]["y"]), 64.0)     # the right arm: rows 0-64
        self.assertGreater(min(min(r) for r in g["L"]["y"]), 64.0)  # the left arm: rows 64-128


class ClearOldMarkTest(unittest.TestCase):
    def test_a_2004_hip_mark_is_filled_from_the_fabric(self):
        h, w = 64, 128
        out = np.zeros((h * art.MASTER, w * art.MASTER, 4), np.float32)
        fabric = np.array([0.1, 0.2, 0.6], np.float32)
        shade = np.linspace(0.9, 1.1, out.shape[1], dtype=np.float32)[None, :, None]
        out[..., :3] = fabric * shade
        out[..., 3] = 1.0
        box = (40, 20, 52, 31)
        x0, y0, x1, y1 = (v * art.MASTER for v in box)
        out[y0 - 4:y1 + 4, x0 - 4:x1 + 4, :3] = (0.9, 0.9, 0.9)     # a white-ringed old shield, bigger than its box
        out[y0:y1, x0:x1, :3] = (0.8, 0.1, 0.1)
        cleared = art._clear_old_mark(out, box)
        want = (fabric * shade)[0, x0 - 8:x1 + 8]
        got = cleared[y0 - 8:y1 + 8, x0 - 8:x1 + 8, :3]
        self.assertLess(float(np.abs(got - want[None, :, :]).max()), 0.06)


class SleeveArtShiftTest(unittest.TestCase):
    def sleeve(self, art_rows):
        out = np.zeros((128 * art.MASTER, 128 * art.MASTER, 4), np.float32)
        out[..., :3] = 1.0
        out[..., 3] = 1.0
        for top in (0, 64):
            y0, y1 = (top + art_rows[0]) * art.MASTER, (top + art_rows[1]) * art.MASTER
            out[y0:y1, 40 * art.MASTER:80 * art.MASTER, :3] = (0.1, 0.2, 0.6)
        return out

    def test_the_art_moves_down_each_island_and_the_top_takes_the_base(self):
        out = self.sleeve((10, 30))
        moved = art.shift_sleeve_islands(out, 6, np.array([1.0, 1.0, 1.0], np.float32))
        for top in (0, 64):
            self.assertLess(moved[(top + 17) * art.MASTER, 60 * art.MASTER, 0], 0.2)   # art now at rows 16-36
            self.assertGreater(moved[(top + 12) * art.MASTER, 60 * art.MASTER, 0], 0.9)  # vacated: base colour
            self.assertGreater(moved[(top + 2) * art.MASTER, 60 * art.MASTER, 0], 0.9)

    def test_a_shift_that_would_cut_the_art_is_refused(self):
        out = self.sleeve((40, 62))
        with self.assertRaises(SystemExit):
            art.shift_sleeve_islands(out, 6, np.array([1.0, 1.0, 1.0], np.float32), "test")

    def test_the_swoosh_offset_moves_it_on_both_arms(self):
        with StandIn(nike_swoosh=two_tone_mark()):
            base = np.zeros((128 * art.MASTER, 128 * art.MASTER, 4), np.float32)
            base[..., 3] = 1.0
            a, b = base.copy(), base.copy()
            art.sleeve_swoosh(a, None, "L")
            art.sleeve_swoosh(b, None, "L", offset=(0.0, 10.0))
        rows_a = np.nonzero((a[..., :3].sum(-1) > 0.5).any(axis=1))[0]
        rows_b = np.nonzero((b[..., :3].sum(-1) > 0.5).any(axis=1))[0]
        self.assertAlmostEqual((rows_b.mean() - rows_a.mean()) / art.MASTER, 10.0, delta=0.6)


class PantsMarksTest(unittest.TestCase):
    def test_the_shield_on_the_right_hip_the_swoosh_on_the_left_tops_level(self):
        sh, sw = art.PANTS_SHIELD, art.PANTS_SWOOSH
        self.assertGreater(sh["centre"][0], 256)      # the texture's right half: the player's right hip (x < 0)
        self.assertLess(sw["centre"][0], 256)         # the player's left hip
        top_sh = sh["centre"][1] - sh["height_px"] / 2.0
        top_sw = sw["centre"][1] - sw["height_px"] / 2.0
        self.assertAlmostEqual(top_sh, top_sw, delta=0.5)
        self.assertGreater(top_sw, 12)                # below the belt (rows 2-12)


if __name__ == "__main__":
    unittest.main()

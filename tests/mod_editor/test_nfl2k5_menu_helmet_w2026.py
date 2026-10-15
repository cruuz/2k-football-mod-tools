"""hu1 (b773): Washington's Team Select helmet cards and schedule miniatures re-rendered with the 2026 helmet W.

The pinned document, the vector W, the paint pass on a synthetic helmet (strokes, splits, strap and facemask kept),
determinism, refusals, the build order, and (with the v0.6.1 base disc) every slot reproducing its after pin."""
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_menu_helmet_w2026 as hw  # noqa: E402
from tools import nfl_txtr as tx  # noqa: E402

DISC = os.environ.get("NFL2K5_HU1_DISC")
SIZE = 64
TRANSFORM = [0.15, 0.0, 14.0, 0.0, 0.15, 20.0]       # the 233 x 127 model W to 35 x 19 texels at (14, 20)
STRAP_X = (40, 42)
FACEMASK_Y = 52


def synthetic_helmet():
    """A synthetic uncompressed 64 x 64 P8 slot: a lit burgundy shell, an outlined W, a grey strap across the W and
    a gold facemask bar below it (drawn here, not game data)."""
    model = hw.spec()["model"]
    footprint = hw.coverage(model, TRANSFORM, 0.0, (0, 0, SIZE, SIZE)) > 0
    inner = footprint.copy()
    inner[1:-1, 1:-1] &= footprint[:-2, 1:-1] & footprint[2:, 1:-1] & footprint[1:-1, :-2] & footprint[1:-1, 2:]
    ring = footprint & ~inner
    rgba = np.zeros((SIZE, SIZE, 4), np.int64)
    rgba[..., 3] = 255
    shade = np.arange(SIZE)[:, None]
    rgba[..., 0], rgba[..., 1], rgba[..., 2] = 150 - shade, 40 - shade // 4, 50 - shade // 4
    rgba[ring, :3] = (230, 170, 40)
    rgba[FACEMASK_Y:FACEMASK_Y + 2, 4:60, :3] = (235, 200, 30)
    rgba[12:48, STRAP_X[0]:STRAP_X[1], :3] = (170, 170, 170)
    colours = sorted({tuple(v) for v in rgba.reshape(-1, 4).tolist()})
    hs_index = {c: i for i, c in enumerate(colours)}
    indices = bytes(hs_index[tuple(v)] for v in rgba.reshape(-1, 4).tolist())
    palette = b"".join(bytes((b, g, r, a)) for r, g, b, a in colours).ljust(1024, b"\0")
    system = bytearray(128)
    system[0x0C:0x10] = b"TXTR"
    struct.pack_into("<II", system, 0x10, 0x11, 0x25)
    name = "mini_h29_0".encode("utf-16le")
    system[0x20:0x20 + len(name)] = name
    struct.pack_into("<6I", system, 0x38, 0, 0, SIZE * SIZE, 0x06610B29, 0, 0x80000000)
    video = tx.swizzle_2d(indices, SIZE, SIZE, 1) + palette
    span = tx.HEADER.pack(b"TXTR", 128 + len(video), 128, len(video), 0, 0, 0, 0) + bytes(system) + video
    target = dict(aggregate="mini", member="mini_h29_0", box=[0, 0, SIZE, SIZE], strap=True,
                  transform=TRANSFORM, gap=0.9)
    return span + bytes(96), model, target, rgba, footprint


def rgba_of(span):
    indices, palette, _ = hw.read_slot(span)
    return palette[indices]


class Document(unittest.TestCase):
    def test_eight_pinned_washington_slots(self):
        doc = hw.spec()
        keys = {(t["aggregate"], t["member"]) for t in doc["targets"]}
        self.assertEqual(keys, {("logos", "helm_h29_0"), ("logos", "helm_a29_0"), ("logos", "unif_h29_0"),
                                ("logos", "unif_a29_0"), ("logos128", "helm_h29_0"), ("logos128", "helm_a29_0"),
                                ("mini", "mini_h29_0"), ("mini", "mini_a29_0")})
        for target in doc["targets"]:
            self.assertIn(target["aggregate"], hw.AGGREGATES)
            self.assertEqual(target["strap"], target["aggregate"] != "mini")
            self.assertIn(len(target["transform"]), (6, 8))
            self.assertGreaterEqual(target["gap"], 0.9)
            self.assertNotEqual(target["before_sha256"], target["after_sha256"])
            self.assertEqual(len(target["after_sha256"]), 64)

    def test_the_w_is_four_solid_strokes_in_the_2026_gold(self):
        model = hw.spec()["model"]
        self.assertEqual(len(model["strokes"]), 4)
        self.assertEqual(model["gold"], "#FFB612")
        self.assertNotIn("logo_29_0", {t["member"] for t in hw.spec()["targets"]})      # the club logo stays

    def test_unknown_document_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.json"
            path.write_text('{"schema": "other"}', encoding="utf-8", newline="\n")
            with self.assertRaises(hw.hs.HistoricStylesError):
                hw.spec(path)


class Paint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.span, cls.model, cls.target, cls.before, cls.footprint = synthetic_helmet()
        cls.after, cls.receipt = hw.paint(cls.span, cls.model, cls.target)
        cls.image = rgba_of(cls.after)

    def test_same_length_and_deterministic(self):
        self.assertEqual(len(self.after), len(self.span))
        self.assertEqual(hw.paint(self.span, self.model, self.target)[0], self.after)
        self.assertEqual(self.after[-96:], bytes(96))

    def test_strokes_are_solid_gold(self):
        cover = hw.coverage(self.model, TRANSFORM, 0.9, (0, 0, SIZE, SIZE))
        solid = cover == hw.SAMPLES
        solid[:, STRAP_X[0] - 1:STRAP_X[1] + 1] = False
        rgb = self.image[solid][:, :3]
        self.assertGreater(len(rgb), 150)
        self.assertTrue(((rgb[:, 0] > 150) & (rgb[:, 1] > 90) & (rgb[:, 2] < 60)).all())

    def test_splits_leave_burgundy_between_strokes(self):
        split = (hw.coverage(self.model, TRANSFORM, 0.0, (0, 0, SIZE, SIZE)) == hw.SAMPLES)
        split &= hw.coverage(self.model, TRANSFORM, 0.9, (0, 0, SIZE, SIZE)) < hw.SAMPLES // 2
        self.assertGreater(int(split.sum()), 5)
        rgb = self.image[split][:, :3]
        self.assertTrue((rgb[:, 1] < 90).mean() > 0.8)

    def test_shell_around_the_w_is_kept(self):
        near = self.footprint.copy()
        for _ in range(4):
            near = hw._dilate(near)
        near &= ~hw._dilate(hw._dilate(self.footprint))
        near[:, STRAP_X[0] - 2:STRAP_X[1] + 2] = False
        self.assertGreater(int(near.sum()), 100)
        self.assertLessEqual(int(np.abs(self.image[near] - self.before[near]).max()), 8)

    def test_strap_and_facemask_stay_in_front(self):
        strap = np.zeros((SIZE, SIZE), bool)
        strap[12:48, STRAP_X[0]:STRAP_X[1]] = True
        rgb = self.image[strap][:, :3]
        self.assertTrue((rgb.max(axis=1) - rgb.min(axis=1) < 18).all())
        mask = self.image[FACEMASK_Y:FACEMASK_Y + 2, 4:60, :3].reshape(-1, 3)
        self.assertTrue((np.abs(mask - (235, 200, 30)).max(axis=1) <= 8).all())
        self.assertTrue((self.image[..., 3] == 255).all())

    def test_receipt_counts_the_repaint(self):
        self.assertEqual(self.receipt["member"], "mini_h29_0")
        self.assertGreater(self.receipt["repainted_texels"], self.receipt["covered_texels"] // 2)
        self.assertEqual(self.receipt["gold_unlit"], "#BF880D")


class Refusals(unittest.TestCase):
    def test_unrelated_image_is_skipped_by_studio_but_refused_strictly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "other.img"
            path.write_bytes(b"other game")
            self.assertEqual(hw.apply_to_image(path)["state"], "other_image")
            self.assertEqual(path.read_bytes(), b"other game")
            with self.assertRaises((ValueError, OSError)):
                hw.apply_to_image(path, strict=True)

    def test_a_slot_without_the_old_w_is_refused(self):
        span, model, target, _, _ = synthetic_helmet()
        blank = dict(target, transform=[0.15, 0.0, 14.0, 0.0, 0.15, 60.0])       # the W placed off the helmet
        with self.assertRaises(hw.hs.HistoricStylesError):
            hw.paint(span, model, blank)

    def test_compressed_or_mipped_slots_are_refused(self):
        span = bytearray(synthetic_helmet()[0])
        struct.pack_into("<I", span, 32 + 0x44, 0x06620B29)                  # two mip levels
        with self.assertRaises(hw.hs.HistoricStylesError):
            hw.read_slot(bytes(span))


class Build(unittest.TestCase):
    def test_build_runs_it_after_the_uf3_miniature(self):
        source = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        self.assertLess(source.index('_core_module("nfl2k5_menu_icon_uf3")'),
                        source.index('_core_module("nfl2k5_menu_helmet_w2026")'))
        self.assertIn('"step": "menu_helmet_w2026"', source)


@unittest.skipUnless(DISC, "set NFL2K5_HU1_DISC (the v0.6.1 base disc, read only) for native integration")
class BaseDisc(unittest.TestCase):
    def test_every_slot_reproduces_its_pin(self):
        from tools.nfl2k5_playbook_position_recode import OuterImage
        doc = hw.spec()
        with OuterImage(Path(DISC)) as archive:
            for target in doc["targets"]:
                _, span = hw.locate(archive, target["aggregate"], target["member"])
                self.assertEqual(hw.sha(span), target["before_sha256"], target["member"])
                after, _ = hw.paint(span, doc["model"], target)
                self.assertEqual(hw.sha(after), target["after_sha256"], target["member"])
            plan, receipt = hw.plan_archive(archive, doc)
        self.assertEqual((len(plan), receipt["state"]), (8, "applied"))


if __name__ == "__main__":
    unittest.main()

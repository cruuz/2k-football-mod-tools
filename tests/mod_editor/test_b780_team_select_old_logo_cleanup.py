"""b780 art1: the old 2004 logo pieces around the new 2026 logo on the SOFTDRINK Team Select helmet cards, cleaned at
the source PNGs (tools/b780_team_select_old_logo_cleanup.py, data/nfl2k5_team_select_old_logo_cleanup.json).

The document, the repaint on synthetic shaded helmets (only the region changes, the piece goes, the shading and a
highlight stay, alpha stays), the 128 card rule, refusals, and (with the SOFTDRINK v0.9 league project on this machine)
every card reproducing its pin."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
import b780_team_select_old_logo_cleanup as cl  # noqa: E402

PROJECT = Path(os.environ.get("B780_ART1_PROJECT",
                              "/home/noah/2k-worktrees/.b77-scratch/ship10/project/recipe_project_v09.json"))


def shell(size=64, base=(120, 30, 40), highlight=True):
    """A lit synthetic shell: a vertical gradient plus a soft diagonal highlight (drawn here, not game data)."""
    y, x = np.mgrid[0:size, 0:size].astype(np.float64)
    rgb = np.stack([base[0] + 60 * y / size, base[1] + 20 * y / size, base[2] + 20 * y / size], axis=-1)
    if highlight:
        rgb += 40.0 * np.exp(-((x - y) ** 2) / 30.0)[..., None]
    rgba = np.zeros((size, size, 4), np.uint8)
    rgba[..., :3] = np.clip(np.floor(rgb + 0.5), 0, 255)
    rgba[..., 3] = 255
    return rgba


class Document(unittest.TestCase):
    def test_every_card_is_named_pinned_and_regioned(self):
        doc = cl.spec()
        regions = cl.card_regions(doc)
        halves = cl.derived_cards(doc)
        self.assertTrue(regions)
        self.assertEqual(set(doc["cards"]), set(regions) | set(halves))
        for name, pin in doc["cards"].items():
            self.assertEqual(len(pin["source_rgba_sha256"]), 64, name)
            self.assertEqual(len(pin["clean_rgba_sha256"]), 64, name)
            self.assertNotEqual(pin["source_rgba_sha256"], pin["clean_rgba_sha256"], name)
            self.assertGreater(pin["changed_pixels"], 0, name)
        for small, big in halves.items():
            self.assertTrue(small.startswith("helm_") and small.endswith("_128") and big in regions)
        for group in doc["groups"]:
            self.assertIn(group["card"], ("helm_h_256", "helm_a_256", "unif_h_256", "unif_a_256"))
            for region in group["regions"]:
                self.assertIn(region.get("mode", "deviation"), ("all", "deviation"))
                self.assertGreaterEqual(len(region["poly"]), 3)
                self.assertTrue(region["note"])
                for x, y in region["poly"]:
                    self.assertTrue(0 <= x <= 256 and 0 <= y <= 256)

    def test_the_cleaned_teams(self):
        teams = {(g["team"], g["code"]) for g in cl.spec()["groups"]}
        self.assertEqual(teams, {("ARI", "00"), ("BAL", "02"), ("DET", "09"), ("NYJ", "19"), ("WAS", "29")})

    def test_in_game_texture_fixes_are_named_pinned_and_use_repository_marks(self):
        doc = cl.spec()
        entries = cl.texture_entries(doc)
        self.assertEqual({e["name"] for e in entries}, set(doc["texture_pins"]))
        self.assertEqual({e["name"] for e in entries},
                         {"lac_helmet00_24", "det_splayer_h", "det_splayer_a", "ten_splayer_h", "ten_splayer_a",
                          "car_splayer_a", "buf_splayer_h", "buf_splayer_a"})
        for entry in entries:
            self.assertIn(entry["kind"], ("live_helmet", "p8_texture"))
            self.assertTrue(entry["note"])
            pin = doc["texture_pins"][entry["name"]]
            self.assertNotEqual(pin["source_rgba_sha256"], pin["clean_rgba_sha256"])
            for mark in entry.get("marks", ()):
                self.assertTrue((ROOT / mark["png"]).is_file(), mark["png"])
                self.assertTrue(mark["png"].startswith("data/nfl2k5_scorebug_assets/logos/"))

    def test_marks_are_drawn_inside_their_box_and_lit(self):
        base = shell(64, base=(150, 150, 150), highlight=False)
        out = cl.apply_marks(base, [dict(png="data/nfl2k5_scorebug_assets/logos/ten.png", box=[10, 10, 30, 30])])
        changed = (out != base).any(axis=2)
        ys, xs = np.nonzero(changed)
        self.assertTrue(len(ys) > 100)
        self.assertTrue(xs.min() >= 10 and xs.max() < 30 and ys.min() >= 10 and ys.max() < 30)
        self.assertTrue((out[..., 3] == base[..., 3]).all())

    def test_neutral_mode_keeps_brightness_and_drops_the_tint(self):
        rgba = shell(32, base=(230, 230, 230), highlight=False)
        rgba[10:14, 10:14, :3] = (30, 80, 140)                   # navy left in a screw's rim
        out, _ = cl.clean_regions(rgba, [dict(poly=[[8, 8], [16, 8], [16, 16], [8, 16]], mode="neutral",
                                              sign="bluer", threshold=18, note="t")])
        rim = out[10:14, 10:14, :3].astype(int)
        self.assertTrue((rim.max(axis=-1) - rim.min(axis=-1) <= 1).all())
        self.assertTrue((np.abs(rim[..., 0] - 72) <= 2).all())        # 0.299*30 + 0.587*80 + 0.114*140
        self.assertTrue((out[:8] == rgba[:8]).all())

    def test_unknown_document_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.json"
            path.write_text('{"schema": "other"}', encoding="utf-8", newline="\n")
            with self.assertRaises(cl.CleanupError):
                cl.spec(path)


class Repaint(unittest.TestCase):
    def setUp(self):
        self.clean = shell()
        self.dirty = self.clean.copy()
        self.dirty[20:30, 22:34, :3] = (230, 180, 30)          # an old gold piece on the shell
        self.dirty[24:26, 26:30, :3] = (250, 250, 250)
        self.poly = [[18, 16], [38, 16], [38, 34], [18, 34]]

    def check_only_region_changed(self, after, poly):
        inside = cl.polygon_mask(after.shape[:2], poly)
        changed = (after != self.dirty).any(axis=2)
        self.assertFalse((changed & ~inside).any())
        self.assertTrue((after[..., 3] == self.dirty[..., 3]).all())

    def test_all_mode_restores_the_shell(self):
        after, rows = cl.clean_regions(self.dirty, [dict(poly=self.poly, mode="all", note="t")])
        self.check_only_region_changed(after, self.poly)
        piece = np.zeros(after.shape[:2], bool)
        piece[20:30, 22:34] = True
        error = np.abs(after[piece, :3].astype(int) - self.clean[piece, :3].astype(int)).max()
        self.assertLessEqual(error, 45)          # a narrow highlight crossing the region is smoothed, not copied
        gold = np.abs(after[piece, :3].astype(int) - (230, 180, 30)).max(axis=1)
        self.assertGreater(int(gold.min()), 60)                 # no trace of the old gold
        self.assertEqual(rows[0]["painted_pixels"], int(cl.polygon_mask(after.shape[:2], self.poly).sum()))

    def test_deviation_mode_paints_only_the_piece(self):
        self.clean = shell(highlight=False)
        self.dirty = self.clean.copy()
        self.dirty[20:30, 22:34, :3] = (230, 180, 30)
        self.dirty[24:26, 26:30, :3] = (250, 250, 250)
        after, rows = cl.clean_regions(self.dirty, [dict(poly=self.poly, mode="deviation", threshold=12, grow=1,
                                                         note="t")])
        self.check_only_region_changed(after, self.poly)
        far = cl.polygon_mask(after.shape[:2], self.poly) & ~cl.dilate(np.pad(np.ones((10, 12), bool),
                                                                              ((20, 34), (22, 30))), 2)
        self.assertTrue((after[far] == self.dirty[far]).all())
        self.assertLess(rows[0]["painted_pixels"], int(cl.polygon_mask(after.shape[:2], self.poly).sum()))
        self.assertLessEqual(np.abs(after[20:30, 22:34, :3].astype(int) - self.clean[20:30, 22:34, :3]).max(), 26)

    def test_local_estimate_keeps_the_highlight(self):
        dirty = self.clean.copy()
        dirty[10:50, 40, :3] = (20, 20, 20)                     # a thin dark old outline across the highlight
        poly = [[36, 6], [46, 6], [46, 54], [36, 54]]
        after, _ = cl.clean_regions(dirty, [dict(poly=poly, mode="deviation", estimate="local", threshold=10,
                                                 grow=1, note="t")])
        self.assertLessEqual(np.abs(after[10:50, 40, :3].astype(int) - self.clean[10:50, 40, :3]).max(), 20)
        untouched = cl.polygon_mask(after.shape[:2], poly).copy()
        untouched[:, 38:43] = False
        self.assertTrue((after[untouched] == dirty[untouched]).all())

    def test_redder_takes_only_red(self):
        grey = shell(base=(30, 30, 30))
        grey[..., :3] = grey[..., :3].mean(axis=2, keepdims=True).astype(np.uint8)
        dirty = grey.copy()
        dirty[20:24, 10:50, :3] = (80, 20, 20)                  # a dark red ring piece
        dirty[40:44, 10:50, :3] = (200, 200, 200)               # a white feature that must stay
        poly = [[6, 16], [54, 16], [54, 48], [6, 48]]
        after, _ = cl.clean_regions(dirty, [dict(poly=poly, mode="deviation", sign="redder", threshold=8, grow=1,
                                                 note="t")])
        self.assertTrue((after[41:43, 12:48] == dirty[41:43, 12:48]).all())
        red = after[20:24, 10:50, :3].astype(int)
        self.assertLessEqual(int((red[..., 0] - red[..., 1:].max(axis=-1)).max()), 6)

    def test_deterministic_and_transparent_pixels_untouched(self):
        dirty = self.dirty.copy()
        dirty[16:20, 18:38, 3] = 0
        one, _ = cl.clean_regions(dirty, [dict(poly=self.poly, mode="all", note="t")])
        two, _ = cl.clean_regions(dirty, [dict(poly=self.poly, mode="all", note="t")])
        self.assertTrue((one == two).all())
        self.assertTrue((one[16:20, 18:38] == dirty[16:20, 18:38]).all())

    def test_polygon_uses_pixel_centres(self):
        mask = cl.polygon_mask((8, 8), [[2, 2], [5, 2], [5, 4], [2, 4]])
        self.assertEqual(sorted(zip(*np.nonzero(mask))), [(2, 2), (2, 3), (2, 4), (3, 2), (3, 3), (3, 4)])

    def test_a_region_without_shell_is_refused(self):
        rgba = shell()
        rgba[..., 3] = 0
        with self.assertRaises(cl.CleanupError):
            cl.clean_regions(rgba, [dict(poly=self.poly, mode="all", note="t")])


class HalfCard(unittest.TestCase):
    def test_only_blocks_under_changed_pixels_follow(self):
        big = shell()
        small = np.floor(cl.box_reduce(big) + 0.5).astype(np.uint8)
        new = big.copy()
        new[10:14, 20:23, :3] = 0
        out = cl.derive_half(small, big, new)
        changed = (out != small).any(axis=2)
        blocks = np.zeros(changed.shape, bool)
        blocks[5:7, 10:12] = True
        self.assertFalse((changed & ~blocks).any())
        self.assertLessEqual(np.abs(out[blocks].astype(int) - np.floor(cl.box_reduce(new)[blocks] + 0.5)).max(), 1)
        self.assertTrue((out[..., 3] == small[..., 3]).all())


class Refusals(unittest.TestCase):
    def test_a_card_that_is_not_the_known_art_is_refused(self):
        doc = cl.spec()
        name = sorted(cl.card_regions(doc))[0]
        family, sc, style, res = name.split("_")
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "card.png"
            cl.save_rgba(shell(256), png)
            edits = []
            for wanted in sorted(set(cl.card_regions(doc)) | set(cl.derived_cards(doc))):
                f, s, st, r = wanted.split("_")
                edits.append(dict(kind="team_select", family=f, side="home" if s[0] == "h" else "away",
                                  asset_code=s[1:], style=int(st), resolution=int(r),
                                  png=str(png if r == "256" else Path(tmp) / "small.png")))
            cl.save_rgba(shell(128), Path(tmp) / "small.png")
            with self.assertRaises(cl.CleanupError):
                cl.clean_project_cards(dict(edits=edits), doc)


@unittest.skipUnless(PROJECT.is_file(), "the SOFTDRINK v0.9 league project (B780_ART1_PROJECT) is not on this machine")
class LeagueProject(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project = json.loads(PROJECT.read_text(encoding="utf-8"))
        cls.images, cls.receipts = cl.clean_project_cards(cls.project)

    def test_every_card_reproduces_its_pin(self):
        doc = cl.spec()
        self.assertEqual(set(self.images), set(doc["cards"]))
        for name, receipt in self.receipts.items():
            self.assertEqual(receipt["clean_rgba_sha256"], doc["cards"][name]["clean_rgba_sha256"], name)
            self.assertEqual(receipt["changed_pixels"], doc["cards"][name]["changed_pixels"], name)

    def test_every_in_game_texture_reproduces_its_pin(self):
        images, receipts = cl.clean_project_textures(self.project)
        doc = cl.spec()
        self.assertEqual(set(images), set(doc["texture_pins"]))
        for name, receipt in receipts.items():
            self.assertEqual(receipt["clean_rgba_sha256"], doc["texture_pins"][name]["clean_rgba_sha256"], name)

    @unittest.skipUnless(os.environ.get("NFL2K5_RETAIL_INDEX"), "set NFL2K5_RETAIL_INDEX (retail pack 0) for the importer")
    def test_the_pants_hem_pass_knows_the_fixed_sideline_atlases(self):
        """The pants hem still paints the 2026 hem on the fixed distance-player atlases: the importer's span of each
        fixed splayer is the hem row's ``also`` before pin and the hem compile gives its ``also`` after pin."""
        import hashlib
        import nfl2k5_visual_mod_project as writer
        from mod_editor.core import nfl2k5_pants_hem_2026 as hem
        images, _ = cl.clean_project_textures(self.project)
        rows = {r["selector"]: r for r in hem.spec()["textures"] if r["kind"] == "splayer" and r.get("also")}
        kits = {"det_splayer_h": "09H0", "det_splayer_a": "09A0", "ten_splayer_h": "28H0", "ten_splayer_a": "28A0",
                "car_splayer_a": "04A0", "buf_splayer_h": "03H0", "buf_splayer_a": "03A0"}
        entries = {e["name"]: e for e in cl.texture_entries(cl.spec())}
        with tempfile.TemporaryDirectory() as tmp:
            for name, selector in kits.items():
                png = Path(tmp) / f"{name}.png"
                cl.save_rgba(images[name], png)
                span = writer.p8_texture_adapter.build_unified_p8_texture_import(
                    Path(os.environ["NFL2K5_RETAIL_INDEX"]), entries[name]["match"]["asset_id"], png)[0]
                row = rows[selector]
                self.assertEqual(hashlib.sha256(span).hexdigest(), row["also"][0]["before_sha256"], name)
                new, _ = hem._compile_row(span, row, hem.spec())
                self.assertEqual(hashlib.sha256(new).hexdigest(), row["also"][0]["after_sha256"], name)

    @unittest.skipUnless(os.environ.get("NFL2K5_RETAIL_INDEX"), "set NFL2K5_RETAIL_INDEX (retail pack 0) for the importer")
    def test_the_washington_w_pass_knows_the_cleaned_cards(self):
        """The hu1 W pass still paints the 2026 W on Washington's cleaned 29_0 cards: the importer's slot for each
        cleaned card is the pass's ``also`` before pin, and its paint gives the ``also`` after pin."""
        import hashlib
        import nfl_team_select_card_png_import as importer
        from mod_editor.core import nfl2k5_menu_helmet_w2026 as hw
        doc = hw.spec()
        checked = 0
        with tempfile.TemporaryDirectory() as tmp:
            for target in doc["targets"]:
                if not target.get("also"):
                    continue
                family, sc, style = target["member"].split("_")
                res = 128 if target["aggregate"] == "logos128" else 256
                name = f"{family}_{sc}_{style}_{res}"
                png = Path(tmp) / f"{name}.png"
                cl.save_rgba(self.images[name], png)
                span, _, _ = importer.build_import(
                    Path(os.environ["NFL2K5_RETAIL_INDEX"]), ROOT / "reports/assets/nfl2k5_team_select_card_inventory.json",
                    family, sc[1:], "home" if sc[0] == "h" else "away", int(style), res, png)
                slot = span + bytes(96)
                self.assertEqual(hashlib.sha256(slot).hexdigest(), target["also"][0]["before_sha256"], name)
                after, _ = hw.paint(slot, doc["model"], target)
                self.assertEqual(hashlib.sha256(after).hexdigest(), target["also"][0]["after_sha256"], name)
                checked += 1
        self.assertEqual(checked, 4)


if __name__ == "__main__":
    unittest.main()

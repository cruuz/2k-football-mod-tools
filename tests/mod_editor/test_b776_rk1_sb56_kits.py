"""b776-rk1: the Super Bowl LVI kits (Noah 10/18: "those aren't even the Rams' correct jerseys").

Static tests check the data: the Rams 2020-2025 kit RK1-LAR takes the Rams' only index that is not the historic spare
(K11's 13), the Bengals kit RK1-CIN takes the free 06:13, both sides of moment row 48 point at them, and the menu
helmet cards come from each side's own letter. The disc tests compose both kits from the release-candidate test disc
(read only) and look at the texels: gradient numerals on the royal home, solid royal numerals and 2020 sol on the
Super Bowl white, white Bengals pants with orange tiger stripes outlined in black over orange socks.
"""
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_historic_styles as hs  # noqa: E402
from mod_editor.core import nfl2k5_moment_kits as mk  # noqa: E402

DISC = Path(os.environ.get("B775_EK1_DISC",
                           "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.6.1 i4 test (2026-10-17).xiso.iso"))


def kit(kit_id):
    return next(k for k in mk.document()["kits"] if k["id"] == kit_id)


class Data(unittest.TestCase):
    def test_row_48_points_at_the_new_kits(self):
        doc = mk.document()
        self.assertNotIn("K11", {k["id"] for k in doc["kits"]})
        sel = {(s["row"], s["side"]): s for s in doc["selections"]}
        self.assertEqual(sel[(48, "away")], {"row": 48, "side": "away", "file": "h-23-2021-rams-9.iff", "before": 2,
                                             "style": 13, "kit": "RK1-LAR"})
        self.assertEqual(sel[(48, "home")], {"row": 48, "side": "home", "file": "h-06-2021-bengals-9.iff",
                                             "before": 0, "style": 13, "kit": "RK1-CIN"})
        defaults = {c["file"]: c["style"] for c in doc["classic_defaults"]}
        self.assertEqual(defaults["h-23-2021-rams-9.iff"], 13)
        self.assertEqual(defaults["h-06-2021-bengals-9.iff"], 13)
        self.assertEqual((kit("RK1-LAR")["code"], kit("RK1-LAR")["style"]), ("23", 13))
        self.assertEqual((kit("RK1-CIN")["code"], kit("RK1-CIN")["style"]), ("06", 13))

    def test_the_rams_have_no_other_index(self):
        # 14 is the Rams' historic spare: a moment kit there would take it (and spare_style would have none left)
        from mod_editor.core import nfl2k5_espn25_rosters as er
        self.assertEqual(er.HISTORIC_SPARES["23"], 14)
        self.assertEqual(er.HISTORIC_SPARES["06"], 8)
        self.assertNotIn(("23", 14), mk.reserved_styles())
        self.assertNotIn(("06", 8), mk.reserved_styles())

    def test_menu_helmet_cards_come_from_each_sides_own_letter(self):
        # sm1 (b776): a helmet card taken from the other letter faces the wrong way in the moment menu
        for kit_id in ("RK1-LAR", "RK1-CIN"):
            k = kit(kit_id)
            for new, (_aggregate, old) in mk.card_sources(k).items():
                if new.startswith(("helm_", "mini_")):
                    self.assertEqual(new[5], old[5], (kit_id, new, old))          # helm_a.. / mini_h..
        cards = mk.card_sources(kit("RK1-LAR"))
        self.assertEqual(cards["helm_a23_13"], ("logos", "helm_a23_0"))   # the 2020 helmet, facing as an A card
        self.assertEqual(cards["helm_h23_13"], ("logos", "helm_h23_0"))

    def test_the_super_bowl_white_takes_the_2020_parts(self):
        a = kit("RK1-LAR")["sides"]["A"]
        self.assertEqual(a["base"], "23A2")
        chunks = mk._expand(a["chunks"])
        # helmet 11-12, socks 4, equipment 5-10, numerals 13-22, helmet numbers 23-32, arm numbers 33-42 (none on
        # the modern throwback), names 43-44, sock bump 48 from the 2020-era road kit; torso, pants, sleeves stay
        self.assertTrue(all(chunks[i] == "23A0" for i in [*range(4, 45), 48]))
        for i in (1, 2, 3, 45, 46, 47):
            self.assertNotIn(i, chunks)
        self.assertEqual(a["unif"], "23A0")                                 # royal facemask and turtleneck


@unittest.skipUnless(DISC.is_file(), "release-candidate test disc absent")
class Disc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import numpy as np
        from nfl_txtr import decode_chunk, parse_chunks, parse_texture, texture_to_rgba
        sys.path.insert(0, str(ROOT / "tools/b765"))
        import u1_audit as u
        cls.np = np
        doc = mk.document()
        with hs.Source(DISC) as src:
            inputs = mk.read_inputs(src, doc)
        cls.packages = mk.compose(doc, inputs["packages"])
        cls.donors = inputs["packages"]

        def tex(raw, index):
            ch = parse_chunks(raw)[index]
            decoded, _ = decode_chunk(raw, ch)
            t = u.tset_texture(decoded, 0) if ch.kind == "TSET" else parse_texture(decoded, ch)
            return np.frombuffer(texture_to_rgba(decoded, ch, t), np.uint8).reshape(t.height, t.width, 4)
        cls.tex = staticmethod(tex)

    def test_home_numerals_fade_from_sol_to_white(self):
        np = self.np
        for index in range(13, 23):
            a = self.tex(self.packages["23h13.iff"], index).astype(int)
            ys = np.flatnonzero((a[..., 3] >= 128).any(axis=1))
            top, bottom = a[ys[0]][a[ys[0], :, 3] >= 128], a[ys[-1]][a[ys[-1], :, 3] >= 128]
            self.assertTrue((top[:, 0] > 240).all() and (top[:, 2] < 40).all(), index)          # sol at the top
            self.assertTrue((bottom[:, :3] > 235).all(), index)                                  # white at the bottom
            blues = a[(a[..., 3] >= 128)][:, 2]
            self.assertGreater(len(set(blues.tolist())), 8, index)                              # a real gradient

    def test_super_bowl_numerals_are_solid_royal(self):
        np = self.np
        for index in range(13, 23):
            a = self.tex(self.packages["23a13.iff"], index).astype(int)
            opaque = a[a[..., 3] > 200][:, :3]
            self.assertTrue(len(opaque), index)
            self.assertTrue((np.abs(opaque - [0, 53, 148]).max(axis=1) <= 12).mean() > 0.97, index)
        for index in range(33, 43):                                                             # no sleeve numbers
            self.assertEqual(int(self.tex(self.packages["23a13.iff"], index)[..., 3].max()), 0)

    def test_super_bowl_gold_is_the_2020_sol(self):
        np = self.np
        for index in (1, 2, 3):
            rgb = self.tex(self.packages["23a13.iff"], index)[..., :3].reshape(-1, 3).astype(int)
            old = (np.abs(rgb - [252, 178, 0]).max(axis=1) <= 6).sum()
            sol = (np.abs(rgb - [255, 209, 0]).max(axis=1) <= 6).sum()
            self.assertEqual(old, 0, index)
            self.assertGreater(sol, 1000, index)

    def test_author_script_reproduces_the_data_from_the_donors(self):
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            for selector in ("23H0", "23A0", "23A2", "06H0", "06A0"):
                (Path(tmp) / f"{selector}.IFF").write_bytes(self.donors[selector])
            r = subprocess.run([sys.executable, str(ROOT / "tools/b77/rk1_kits_author.py"), "--donors", tmp, "--check"],
                               capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_bengals_pants_white_with_outlined_orange_stripes_and_orange_socks(self):
        np = self.np
        a = self.tex(self.packages["06h13.iff"], 2)[..., :3].astype(int)
        orange = (np.abs(a - [251, 79, 20]).max(axis=2) <= 12)
        black = (a.max(axis=2) <= 30)
        white = (a.min(axis=2) >= 240)
        self.assertGreater(white[:180].mean(), 0.8)                       # white pants
        self.assertGreater(orange[215:].mean(), 0.99)                    # orange sock band
        stripe = (slice(0, 196), slice(112, 172))
        self.assertGreater(orange[stripe].sum(), 300)
        self.assertGreater(black[stripe].sum(), 150)                     # the black outline
        # every orange stripe texel that touches white cloth would be an outline gap: none
        o = orange[stripe]
        w = white[stripe]
        touching = o[1:-1, 1:-1] & (w[:-2, 1:-1] | w[2:, 1:-1] | w[1:-1, :-2] | w[1:-1, 2:])
        self.assertLess(int(touching.sum()), 6)
        self.assertEqual(self.packages["06a13.iff"], self.donors["06A0"])   # the road kit is a byte copy


if __name__ == "__main__":
    unittest.main()

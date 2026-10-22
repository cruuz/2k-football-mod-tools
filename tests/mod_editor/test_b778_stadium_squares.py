"""b778 sd1: the stadium bugs from Noah's 2026-10-21 stream.

* The black squares in the crowd (EverBank, Gillette, AT&T, MetLife ...) were the stadium models' vomitory portals: a
  2.4 x 2.2 m flat dark quad standing in the seating every 24 to 26 m. No model draws them now; the only portal-material
  quad left is Highmark's players' tunnel mouth at field level.
* The Raymond James clock floating mid-facade was one of the four 2004 suite-fascia game clocks (retail shape
  group208, each on a small dark housing quad) that the 2016 stadium does not have; the board kit removes the clocks
  and their housings, and the game clock stays on the two end-zone boards.
"""
import importlib
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core import nfl2k5_board_kit as bk  # noqa: E402
from mod_editor.core import nfl2k5_scne_builder as sb  # noqa: E402

EXTRACTED = ROOT / "extracted" / "ESPN NFL 2K5 (USA)"
MODELS = ("allegiant", "att", "everbank", "gillette", "hard_rock", "highmark", "lambeau", "levis", "lucas_oil",
          "mercedes_benz", "metlife", "sofi", "state_farm", "usbank")
#: a portal-material quad below this height (metres) is a field-level tunnel mouth, not an opening in the seating
FIELD_LEVEL = 4.0


def portal_points(model):
    """Every vertex (metres) a ``*_portal`` material draws in a built model."""
    out = []
    for mesh in model.meshes.values():
        for material, strips in mesh.groups.items():
            if material.endswith("_portal"):
                out += [mesh.P[i] for strip in strips for i in strip]
    return np.array(out, dtype=float).reshape(-1, 3)


class NoPortalsInTheSeating(unittest.TestCase):
    def test_no_model_draws_a_portal_in_the_stands(self):
        for name in MODELS:
            with self.subTest(model=name):
                module = importlib.import_module(f"mod_editor.core.nfl2k5_{name}_model")
                pts = portal_points(module.build())
                high = pts[pts[:, 1] > FIELD_LEVEL] if len(pts) else pts
                self.assertEqual(len(high), 0, f"{name}: {len(high)} portal vertices up in the stands")

    def test_highmark_keeps_its_field_level_tunnel_mouth(self):
        from mod_editor.core import nfl2k5_highmark_model as hm
        pts = portal_points(hm.build())
        self.assertGreater(len(pts), 0)
        self.assertLessEqual(float(pts[:, 1].max()), 3.6 + 1e-6)

    def test_the_old_portal_comes_back_only_on_request(self):
        """The opening is still there for a later, better portal: ``draw`` True puts the quads back."""
        from mod_editor.core import nfl2k5_everbank_model as jx
        self.assertGreater(len(portal_points(jx.build(params={"portals": {"draw": True}}))), 0)


def _retail_stadium(name):
    from mod_editor.core import nfl2k5_modern_metlife as ml
    retail = bk.read_retail(EXTRACTED, name[:3])[name]
    chunk = ml.bundle_scenes(retail)["stadium"]
    _rec, dec = ml._scene(retail, chunk)
    return sb.parse(dec, chunk.system_bytes)


def _material_points(sc, wanted):
    """{shape name: [(material, vertex positions in metres)]} for the submeshes whose material passes ``wanted``."""
    out = {}
    for s in sc.shapes:
        if struct_kind(s) != 0x32:
            continue
        P = np.array(sb.shape_positions(s), dtype=float) / 100.0
        for sub in s.submeshes:
            name = sc.materials[sub.material].name
            if wanted(name):
                ix = sorted({i for _mode, idx in sb.decode_words(sub.words) for i in idx})
                out.setdefault(s.name, []).append((name, P[ix]))
    return out


def struct_kind(shape):
    import struct
    return struct.unpack_from("<I", shape.record, 0x84)[0]


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class RaymondJamesFasciaClocks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = _retail_stadium("s27nd.iff")
        cls.kit = _retail_stadium("s27nd.iff")
        cls.info = bk.renovate(cls.kit, "s27")

    def test_retail_has_the_four_fascia_clocks(self):
        got = _material_points(self.retail, lambda n: n.startswith("digit_"))
        self.assertIn("group208", got)
        xs = np.concatenate([p for _n, p in got["group208"]])[:, 0]
        self.assertTrue(np.allclose(np.abs(xs), 88.08, atol=0.05))

    def test_every_digit_is_on_an_end_zone_board(self):
        got = _material_points(self.kit, lambda n: n.startswith("digit_"))
        self.assertNotIn("group208", got)
        self.assertEqual(set(got), {"bk_group447", "bk_group448"})
        for shape, rows in got.items():
            for material, pts in rows:
                self.assertTrue(np.all(np.abs(pts[:, 2]) > 110.0), (shape, material))

    def test_the_clock_housings_are_gone_and_the_rest_of_the_texture_stays(self):
        def in_housing(p):
            return 87.5 <= abs(p[0]) <= 88.6 and 19.4 <= p[1] <= 21.5 and 30.0 <= abs(p[2]) <= 35.4
        before = _material_points(self.retail, lambda n: n == "stadium_lambert11ss")
        after = _material_points(self.kit, lambda n: n == "stadium_lambert11ss")
        count = lambda got: sum(int(np.sum([in_housing(p) for p in pts])) for rows in got.values() for _n, pts in rows)
        self.assertEqual(count(before), 16)    # four housing quads
        self.assertEqual(count(after), 0)
        self.assertEqual(self.info["cut"][1:], [4, 4])
        self.assertIn("group208", self.info["replaced"])


if __name__ == "__main__":
    unittest.main()

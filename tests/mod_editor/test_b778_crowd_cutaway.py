"""b778 sd2: the crowd in the model stadiums (Noah's 2026-10-21 stream at Lucas Oil Stadium: "the fans are inside the
stands, that's not right"; a player's report on 10/22: "AT&T Stadium still has glitchy fans").

* The crowd-reaction cutaway: the executable stands one of the retail close-up crowd cutscenes on the stadium scene's
  ``nosebleed`` marker (position and yaw). Every model had put that marker on an upper-deck row, so the cutscene's fans
  (on a flat floor 15 m deep) stood up to their chests in the seats and the crowd billboards, and four models kept a
  retail yaw from another side. Now every fan of every retail crowd cutscene stands clear of the model and the cutscene
  faces the field.
* The crowd billboards: the lower bowl's top rows stood through the next tier's ledge in every stacked model; at AT&T
  Stadium the Party Pass decks' glass rails shared the plane of the deck crowd (fans flickering through the glass); a
  few bands ran through boards, facades and seats. No billboard now cuts or shares a plane with other geometry.
* No model gained a vertex.

The cutaway envelope (``b778_crowd_cutaway_envelope.json``) is every fan marker and camera of the 180 retail crowd
cutscenes, positions only.
"""
import importlib
import json
import math
import struct
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core import nfl2k5_metlife_model as mm  # noqa: E402

EXTRACTED = ROOT / "extracted" / "ESPN NFL 2K5 (USA)"
ENVELOPE = json.loads((Path(__file__).with_name("b778_crowd_cutaway_envelope.json")).read_text(encoding="utf-8"))
#: (module, venue) of every model stadium
MODELS = (("allegiant", None), ("att", None), ("everbank", None), ("gillette", None), ("hard_rock", None),
          ("highmark", None), ("lambeau", None), ("levis", None), ("lucas_oil", None), ("mercedes_benz", None),
          ("state_farm", None), ("usbank", None), ("sofi", "s23"), ("sofi", "s24"), ("metlife", "s18"),
          ("metlife", "s19"))
#: MetLife keeps the retail Giants Stadium record (free air in front of its upper deck), yaw -90 degrees
RETAIL_NOSEBLEED = (50.75, 19.5, 25.0)
#: every model's vertex count before sd2 (776e4d9b4): the crowd fixes only move or take out billboards
VERTICES_BEFORE = {"allegiant": 20655, "att": 18942, "everbank": 15940, "gillette": 15733, "hard_rock": 16353,
                   "highmark": 20618, "lambeau": 14117, "levis": 17075, "lucas_oil": 22710, "mercedes_benz": 20882,
                   "state_farm": 18506, "usbank": 22883, "sofi:s23": 24738, "sofi:s24": 24738, "metlife:s18": 22155,
                   "metlife:s19": 21805}

_BUILT = {}


def built(name, venue):
    key = (name, venue)
    if key not in _BUILT:
        module = importlib.import_module(f"mod_editor.core.nfl2k5_{name}_model")
        _BUILT[key] = module.build(venue) if venue else module.build()
    return _BUILT[key]


def triangles(model):
    """{material: (n, 3, 3) triangles in metres} of a built model."""
    out = {}
    for mesh in model.meshes.values():
        P = np.asarray(mesh.P, float)
        for mat, strips in mesh.groups.items():
            t = [tr for st in strips for tr in mm._strip_triangles(st)]
            if t:
                T = P[np.array(t)]
                area = np.linalg.norm(np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]), axis=1)
                out.setdefault(mat, []).append(T[area > 1e-9])      # a folded billboard draws nothing
    return {k: np.concatenate(v) for k, v in out.items()}


def tri_box(T, c, h):
    """Per triangle of T (n, 3, 3): does it touch the axis-aligned box (centre c, half sizes h)? (separating axes)"""
    v = T - c
    e = [v[:, 1] - v[:, 0], v[:, 2] - v[:, 1], v[:, 0] - v[:, 2]]
    ok = np.ones(len(T), bool)
    for i in range(3):
        ok &= (v[:, :, i].min(1) <= h[i]) & (v[:, :, i].max(1) >= -h[i])
    n = np.cross(e[0], e[1])
    ok &= np.abs((n * v[:, 0]).sum(1)) <= np.abs(n) @ h
    for k in range(3):
        axis = np.eye(3)[k]
        for j in range(3):
            a = np.cross(np.broadcast_to(axis, e[j].shape), e[j])
            p = (v * a[:, None, :]).sum(2)
            r = np.abs(a) @ h
            ok &= (p.min(1) <= r) & (p.max(1) >= -r)
    return ok


def to_world(local, anchor, yaw_bam=mm.CUTAWAY_YAW):
    th = math.radians(yaw_bam * 360.0 / 65536.0)
    x, y, z = local
    return np.array([anchor[0] + x * math.cos(th) + z * math.sin(th), anchor[1] + y,
                     anchor[2] - x * math.sin(th) + z * math.cos(th)])


class CutawayStandsClear(unittest.TestCase):
    def test_every_cutscene_fan_stands_clear_of_the_model(self):
        r, ht = ENVELOPE["fan"]["radius"], ENVELOPE["fan"]["height"]
        half = np.array([r, ht / 2, r])
        for name, venue in MODELS:
            with self.subTest(model=name, venue=venue):
                model = built(name, venue)
                anchor = getattr(model, "nosebleed", RETAIL_NOSEBLEED)
                T = np.concatenate(list(triangles(model).values()))
                boxes = [to_world((x, y + ht / 2, z), anchor) for x, y, z in ENVELOPE["fans"]]
                lo, hi = np.min(boxes, 0) - 2, np.max(boxes, 0) + 2
                T = T[(T.max(1) >= lo).all(1) & (T.min(1) <= hi).all(1)]
                clipped = [tuple(np.round(c, 2)) for c in boxes if tri_box(T, c, half).any()]
                self.assertEqual(clipped, [], f"{name}: {len(clipped)} of {len(boxes)} cutaway fans stand in geometry "
                                              f"at the nosebleed {anchor}")

    def test_no_cutscene_camera_stands_in_a_wall(self):
        half = np.array([0.3, 0.3, 0.3])
        for name, venue in MODELS:
            with self.subTest(model=name, venue=venue):
                model = built(name, venue)
                anchor = getattr(model, "nosebleed", RETAIL_NOSEBLEED)
                T = np.concatenate(list(triangles(model).values()))
                bad = [c for c in ENVELOPE["cameras"] if tri_box(T, to_world(c, anchor), half).any()]
                self.assertEqual(bad, [], f"{name}: cutscene cameras inside geometry")

    def test_the_cutaway_faces_the_field_from_the_plus_x_stands(self):
        """The cutscene's cameras stand in front of its fans (+z of its frame): with the yaw the models write they are
        on the field side (toward x = 0) of every model's nosebleed point, which is in the +x stands."""
        for name, venue in MODELS:
            with self.subTest(model=name, venue=venue):
                anchor = getattr(built(name, venue), "nosebleed", RETAIL_NOSEBLEED)
                self.assertGreater(anchor[0], 30.0)
                self.assertLess(to_world((0.0, 0.0, 5.0), anchor)[0], anchor[0] - 4.9)

    def test_place_cutaway_writes_the_point_and_the_yaw(self):
        rec = bytearray(0x40)
        mm.place_cutaway(rec, (69.0, 34.5, -1.25))
        self.assertEqual(struct.unpack_from("<3f", rec, 0x10), (6900.0, 3450.0, -125.0))
        self.assertEqual(struct.unpack_from("<i", rec, 0x24)[0], -16383)
        self.assertEqual(bytes(rec[0x24:0x28]).hex(), "01c0ffff")      # retail's +x record word

    @unittest.skipUnless(EXTRACTED.is_dir(), "needs the retail archive at extracted/")
    def test_the_built_scenes_carry_the_point_and_the_yaw(self):
        from mod_editor.core import nfl2k5_modern_metlife as ml
        from mod_editor.core import nfl2k5_scne_builder as sb
        for name, filename in (("lucas_oil", "s11dd.iff"), ("att", "s07dd.iff"), ("allegiant", "s20dd.iff"),
                               ("gillette", "s16dd.iff")):
            with self.subTest(model=name):
                module = importlib.import_module(f"mod_editor.core.nfl2k5_{name}_model")
                retail = module.read_retail(EXTRACTED)[filename]
                out = module.model_bundle(retail, filename)[0]
                chunk = ml.bundle_scenes(out)["stadium"]
                _rec, dec = ml._scene(out, chunk)
                sc = sb.parse(dec, chunk.system_bytes)
                nb = [m for m in sc.markers if m.name.startswith("nosebleed")]
                self.assertEqual(len(nb), 1)
                pos = struct.unpack_from("<3f", nb[0].record, 0x10)
                want = built(name, None).nosebleed
                self.assertTrue(np.allclose(pos, [float(np.float32(v * 100)) for v in want]), (pos, want))
                self.assertEqual(struct.unpack_from("<i", nb[0].record, 0x24)[0], mm.CUTAWAY_YAW)


class CrowdBillboardsClear(unittest.TestCase):
    def test_no_billboard_cuts_through_other_geometry(self):
        for name, venue in MODELS:
            with self.subTest(model=name, venue=venue):
                tris = triangles(built(name, venue))
                C = tris.pop("crowd")
                S = np.concatenate(list(tris.values()))
                s_lo, s_hi = S.min(1), S.max(1)
                c_lo, c_hi = C.min(1), C.max(1)
                worst = 0.0
                for i in range(0, len(C), 256):
                    a_lo, a_hi = c_lo[i:i + 256], c_hi[i:i + 256]
                    ia, ib = np.nonzero((a_hi[:, None, :] >= s_lo[None]).all(2) & (a_lo[:, None, :] <= s_hi[None]).all(2))
                    if len(ia):
                        worst = max(worst, float(mm.triangle_cuts(C[i:i + 256][ia], S[ib]).max()))
                self.assertLessEqual(worst, mm.CROWD_CUT_MIN, f"{name}: a crowd billboard cuts {worst:.2f} m into "
                                                              f"other geometry")

    def test_att_deck_rails_do_not_share_the_fans_plane(self):
        """Before sd2 the Party Pass decks' glass rails and the deck crowd stood in one plane (1,267 square metres of
        coplanar overlap): the fans flickered through the glass."""
        from mod_editor.core import nfl2k5_att_model as att
        tris = triangles(built("att", None))
        C, R = tris["crowd"], tris["att_rail"]
        nC = np.cross(C[:, 1] - C[:, 0], C[:, 2] - C[:, 0]); nC /= np.linalg.norm(nC, axis=1, keepdims=True)
        lo, hi = R.min(1) - 0.03, R.max(1) + 0.03
        ia, ib = np.nonzero((C.max(1)[:, None, :] >= lo[None]).all(2) & (C.min(1)[:, None, :] <= hi[None]).all(2))
        off = np.abs(((R[ib] - C[ia][:, None, 0]) * nC[ia][:, None, :]).sum(2)).max(1)
        self.assertEqual(int((off < 0.03).sum()), 0)
        self.assertGreater(att.ATT.RAIL_AHEAD, 0.0)

    def test_the_top_rows_stay_under_the_club_ledge(self):
        """The ceiling a stacked model passes keeps the lower bowl's billboards under the next tier's ledge."""
        from mod_editor.core import nfl2k5_usbank_model as um
        model = um.USBank()
        secs = [model.section(lp) for lp in model.loop]
        ceil = model.soffit_ceiling(secs)
        self.assertTrue(any(c is not None for c in ceil))
        m = mm.Mesh("t")
        model._crowd(m, model.loop, [s["lower"] for s in secs], ceiling=ceil)
        P = np.asarray(m.P)
        for lp, c in zip(model.loop, ceil):
            if c is None:
                continue
            d = (P[:, 0] - lp.x) * lp.nx + (P[:, 2] - lp.z) * lp.nz
            near = (np.hypot(P[:, 0] - (lp.x + lp.nx * d), P[:, 2] - (lp.z + lp.nz * d)) < 0.05) & (d >= c[0] - 0.3)
            if near.any():
                self.assertLessEqual(float(P[near, 1].max()), c[1] - model.CEILING_GAP + 1e-6)


class NoModelGrows(unittest.TestCase):
    def test_vertex_counts_do_not_rise(self):
        for name, venue in MODELS:
            key = name + (f":{venue}" if venue else "")
            with self.subTest(model=key):
                n = sum(len(mesh.P) for mesh in built(name, venue).meshes.values())
                self.assertLessEqual(n, VERTICES_BEFORE[key])


if __name__ == "__main__":
    unittest.main()

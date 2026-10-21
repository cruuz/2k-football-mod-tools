"""sw1 (b777): the sleeve swoosh centred on the sleeve (warp operation, pinned layer, Studio order)."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_kit_fixes_2026 as fixes  # noqa: E402

UNIT = fixes.UNIT


def plain(h, w, colour):
    out = np.zeros((h, w, 4), np.uint8)
    out[..., :3] = colour
    out[..., 3] = 255
    return out


def identity_op(dx, dy, size, mask=None, colour="#FF0000"):
    """A warp whose source grid is the decal box [0, size] x [0, size] texels and whose destination nodes are the same
    box moved by (dx, dy)."""
    n = 5
    grid = {"s": [i * 250 for i in range(n)], "t": [i * 250 for i in range(n)],
            "x": [[int(i * size * UNIT / (n - 1)) for i in range(n)] for _ in range(n)],
            "y": [[int(j * size * UNIT / (n - 1))] * n for j in range(n)]}
    dst = []
    for j in range(n):
        for i in range(n):
            dst.append([int((dx + i * size / (n - 1)) * UNIT), int((dy + j * size / (n - 1)) * UNIT)])
    mask = mask or [[y, 0, 64] for y in range(64)]
    return {"op": "warp", "grid": grid, "nodes": {"a": [i * 250 for i in range(n)], "b": [j * 250 for j in range(n)],
                                                  "dst": dst, "use": "1" * (n * n)},
            "mask": mask, "alpha_line": {"field": "#FFFFFF", "mark": "#000000"}, "color": colour}


class Warp(unittest.TestCase):
    def setUp(self):
        self.src = plain(64, 64, (255, 255, 255))
        self.src[10:14, 8:20, :3] = 0          # a black bar on white, inside the 0..32 box
        self.dst = plain(64, 64, (0, 0, 255))

    def test_identity_mesh_moves_the_mark_exactly(self):
        out, hit = fixes.warp(self.dst, identity_op(20, 16, 32), self.src)
        self.assertTrue((out[26:30, 28:40, :3] == (255, 0, 0)).all())
        self.assertTrue((out[~hit][:, :3] == (0, 0, 255)).all())
        self.assertEqual(int(hit.sum()), 4 * 12)

    def test_mask_limits_the_change(self):
        mask = [[y, 0, 34] for y in range(64)]
        out, hit = fixes.warp(self.dst, identity_op(20, 16, 32, mask=mask), self.src)
        self.assertFalse(hit[:, 34:].any())
        self.assertTrue((out[26:30, 28:34, :3] == (255, 0, 0)).all())

    def test_unused_nodes_drop_their_triangles(self):
        op = identity_op(20, 16, 32)
        op["nodes"]["use"] = "".join("0" if i % 5 >= 2 else "1" for i in range(25))
        out, hit = fixes.warp(self.dst, op, self.src)
        self.assertFalse(hit[:, 20 + 16 + 1:].any())

    def test_deterministic_and_through_paint(self):
        op = identity_op(7, 3, 40)
        a, _ = fixes.paint(self.dst, [dict(op, donor=5)], donors={5: self.src})
        b, _ = fixes.paint(self.dst, [dict(op, donor=5)], donors={5: self.src})
        self.assertTrue(np.array_equal(a, b))
        with self.assertRaises(ValueError):
            fixes.paint(self.dst, [dict(op, donor=6)], donors={5: self.src})

    def test_bad_grid_and_mask_are_refused(self):
        op = identity_op(0, 0, 16)
        bad = json.loads(json.dumps(op))
        bad["grid"]["s"][2] += 1
        with self.assertRaises(ValueError):
            fixes.warp(self.dst, bad, self.src)
        bad = json.loads(json.dumps(op))
        bad["mask"] = [[70, 0, 4]]
        with self.assertRaises(ValueError):
            fixes.warp(self.dst, bad, self.src)


class Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = fixes.swooshes()

    def modern(self):
        sels = set()
        codes = {}
        for p in (ROOT / "data/nfl2k5_teams_2026").glob("*.json"):
            t = json.loads(p.read_text(encoding="utf-8"))
            codes[p.stem] = t.get("asset_code")
            for k in (t.get("kits") or {}).values():
                if isinstance(k, dict) and k.get("selector"):
                    sels.add(k["selector"])
        slots = json.loads((ROOT / "data/nfl2k5_uniform_slots_2026.json").read_text(encoding="utf-8"))
        for team, v in slots["teams"].items():
            for a in v["assignments"]:
                sels |= {f"{codes[team]}{side}{a['style']}" for side in "HA"}
        return sels

    def test_only_modern_torso_and_sleeve_textures_are_owned(self):
        modern = self.modern()
        for row in self.doc["textures"]:
            self.assertIn(row["selector"], modern)
            self.assertIn((row["chunk"], row["texture"]), {(1, "jersey00"), (3, "sleeve00")})
            for op in row["ops"]:
                if op["op"] == "poly":
                    # only the Jaguars black alternate: its 2004 maker marks on the shoulder tops painted out
                    self.assertIn(row["selector"], ("12A5", "12H5"))
                    self.assertEqual(row["chunk"], 1)
                    continue
                self.assertIn(op["op"], ("warp", "texels"))
                if op["op"] == "warp":
                    # one clean source swoosh (the Packers home sleeve), pinned on every row that names it
                    self.assertEqual(op["donor"], "10H0:3")
            if any(op["op"] == "warp" for op in row["ops"]):
                self.assertEqual(set(row["donors"]), {"10H0:3"})
        self.assertNotIn("10H0", {r["selector"] for r in self.doc["textures"]})

    def test_no_pants_helmet_or_number_textures(self):
        self.assertFalse({r["chunk"] for r in self.doc["textures"]} - {1, 3})

    def test_studio_build_order_and_packaging(self):
        text = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        self.assertLess(text.index("kit_fixes.apply_chiefs(target)"), text.index("kit_fixes.apply_swooshes(target)"))
        self.assertLess(text.index("kit_fixes.apply_swooshes(target)"), text.index("moment_kits.apply_to_image(target)"))
        self.assertIn("data/nfl2k5_kit_fixes_2026_sw1.json",
                      (ROOT / "packaging/release-allowlist.txt").read_text(encoding="utf-8"))

    def test_no_private_paths_in_the_data(self):
        text = fixes.DATA_SW1.read_text(encoding="utf-8")
        self.assertNotIn("/home/", text)
        self.assertNotIn("/media/", text)


@unittest.skipUnless(os.environ.get("NFL2K5_SW1_DISC"), "set NFL2K5_SW1_DISC (the b776 base disc) for native checks")
class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tools.b77 import uf3_repair as transport
        from tools.b77 import ov1_repair as ov1
        cls.doc = fixes.swooshes()
        from tools.b77 import sw1_repair
        cls.donors = {}
        cls.raws, cls.ranges, cls.extents = transport.read_resources(Path(os.environ["NFL2K5_SW1_DISC"]), cls.doc,
                                                                     cls.donors)
        cls.compiled, cls.receipts = sw1_repair.compile_plans(cls.raws, cls.doc, cls.donors)
        cls.ov1 = ov1

    def test_every_kit_compiles_to_its_pin_and_replays_to_nothing(self):
        for sel, new in self.compiled.items():
            parts, receipt = fixes.compile_resource(sel, new, document=self.doc, kits=self.donors)
            self.assertEqual((parts, receipt["changed_bytes"]), ([], 0), sel)

    def test_only_the_swoosh_regions_change(self):
        for row in self.doc["textures"]:
            sel = row["selector"]
            at, end = row["offset"], row["offset"] + row["length"]
            raw, new = self.raws[sel], self.compiled[sel]
            before, after = fixes.texture_rgba(raw[at:end]), fixes.texture_rgba(new[at:end])
            allowed = np.zeros(before.shape[:2], bool)
            for op in row["ops"]:
                if op["op"] == "warp":
                    for y, x0, x1 in op["mask"]:
                        allowed[y, x0:x1] = True
                elif op["op"] == "poly":
                    xs = [p[0] for p in op["points"]]
                    ys = [p[1] for p in op["points"]]
                    allowed[int(min(ys)):int(max(ys)) + 1, int(min(xs)):int(max(xs)) + 1] = True
                else:
                    for x, y in op["points"]:
                        allowed[y, x] = True
            delta = np.abs(before.astype(int) - after.astype(int)).max(axis=2)
            # outside the art: nothing, or (a full palette's twin entries folded together) one level at most
            self.assertLessEqual(int(delta[~allowed].max()), fixes.MERGE_LEVELS, sel)
            self.assertTrue((delta[allowed] > 0).any(), sel)

    def test_compact_fixture_writer_equals_the_compiler(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            self.ov1.compact_fixture(p, dict(self.raws, **self.donors))
            fixes.apply_swooshes(p, strict=True)
            self.assertEqual(fixes.apply_swooshes(p, strict=True)["written_bytes"], 0)
            with self.ov1.bump._Image.open(p, writable=False) as im:
                ix = self.ov1.bump._parsed_index(im)
                for e in ix.entries:
                    sel = self.ov1.bump.logical_name_for(e.name_id)[:-4]
                    self.assertEqual(im.read_segments(ix.sub_extents(e, 0, e.size)),
                                     self.compiled.get(sel, self.donors.get(sel)))


if __name__ == "__main__":
    unittest.main()

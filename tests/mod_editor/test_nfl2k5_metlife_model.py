"""Modern MetLife model (u5): geometry, cameras, pins and the same-size writes."""
import json
import math
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core import nfl2k5_metlife_model as mm  # noqa: E402
from mod_editor.core import nfl2k5_scne_builder as sb  # noqa: E402

EXTRACTED = ROOT / "extracted" / "ESPN NFL 2K5 (USA)"


class Geometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = mm.build(venue="s18")

    def test_budget_and_shapes(self):
        total = sum(m.count() for m in self.model.meshes.values())
        self.assertLess(total, 30000)
        for m in self.model.meshes.values():
            self.assertLess(m.count(), 0xFFFF, m.name)
        self.assertTrue(any(n.startswith("ml_bowl") for n in self.model.meshes))
        self.assertTrue(any(n.startswith("ml_ring") for n in self.model.meshes))
        self.assertTrue(any(n.startswith("ml_facade") for n in self.model.meshes))
        self.assertIn("ml_boards", self.model.meshes)
        self.assertIn("ml_signs", self.model.meshes)

    def test_crowd_uv_convention(self):
        """Crowd billboards: U inside one quarter strip of the runtime atlas, V along the row at 9.14 m a unit."""
        for m in self.model.meshes.values():
            for strip in m.groups.get("crowd", ()):
                us = [m.UV[i][0] for i in strip]
                self.assertGreaterEqual(min(us), 0.0)
                self.assertLessEqual(max(us), 1.0)
                self.assertLess(max(us) - min(us), 0.25)

    def test_field_wall_clears_the_sideline_props(self):
        """The wall line stays outside the retail benches (x 30.4..39.5) and the broadcast eye (x 56.5, y 16.5)
        stays above the lower bowl's rake."""
        loop = self.model.loop
        self.assertGreaterEqual(min(abs(lp.x) for lp in loop if abs(lp.z) < 40), 39.0)
        sec = self.model.section(loop[0])
        for d, y in sec["lower"]:
            if abs(39.0 + d - 56.5) < 1.0:
                self.assertLess(y, 16.5 - 3.0)

    def test_every_triangle_faces_its_viewer(self):
        """Seats, crowd and fascias face the field (the retail winding: (b-a)x(c-a) toward the viewer)."""
        for m in self.model.meshes.values():
            if not m.name.startswith("ml_bowl"):
                continue
            for mat in ("seat01", "seat02", "crowd"):
                for strip in m.groups.get(mat, ()):
                    for k in range(len(strip) - 2):
                        a, b, c = strip[k], strip[k + 1], strip[k + 2]
                        if len({a, b, c}) < 3:
                            continue
                        if k % 2:
                            a, b = b, a
                        pa, pb, pc = (m.P[i] for i in (a, b, c))
                        n = [(pb[1] - pa[1]) * (pc[2] - pa[2]) - (pb[2] - pa[2]) * (pc[1] - pa[1]),
                             (pb[2] - pa[2]) * (pc[0] - pa[0]) - (pb[0] - pa[0]) * (pc[2] - pa[2]),
                             (pb[0] - pa[0]) * (pc[1] - pa[1]) - (pb[1] - pa[1]) * (pc[0] - pa[0])]
                        if math.hypot(*n) < 1e-9:
                            continue
                        cen = [(pa[i] + pb[i] + pc[i]) / 3 for i in range(3)]
                        f = mm.toward_field(cen) + (0.0 if mat == "crowd" else 1.0) * mm.np.array([0, 1.0, 0])
                        self.assertGreater(sum(n[i] * f[i] for i in range(3)), 0.0, (m.name, mat))


class Cameras(unittest.TestCase):
    def test_rest_matrix_convention(self):
        """camera_matrix reproduces retail camera 1's rest matrix from its channel start (yaw 27045.5, pitch
        -2548.8 binary angles)."""
        rows = mm.camera_matrix(3942.889, 7826.549, -10010.43, 27045.5 / mm.BAM, -2548.8 / mm.BAM)
        expect = [(-0.853, 0.0, -0.521), (-0.126, 0.970, 0.206), (0.506, 0.242, -0.828)]
        for r, e in zip(rows, expect):
            for a, b in zip(r[:3], e):
                self.assertAlmostEqual(a, b, places=2)

    def test_look_angles_round_trip(self):
        for eye, target in (((0, 10, -50), (0, 0, 0)), ((130, 95, -235), (-5, 30, 10))):
            yaw, pitch = mm.look_angles(eye, target)
            rows = mm.camera_matrix(0, 0, 0, yaw, pitch)
            forward = [-v for v in rows[2][:3]]
            d = [t - e for t, e in zip(target, eye)]
            n = math.sqrt(sum(v * v for v in d))
            for a, b in zip(forward, d):
                self.assertAlmostEqual(a, b / n, places=5)

    def test_shots_are_outside_the_geometry_or_in_the_air(self):
        """The exterior shot starts outside the facade; every other eye is above the seats under it."""
        shots = mm.metlife_shots()
        ex, ey, ez = shots[0]["eye"]
        self.assertTrue(abs(ex) > 120 or abs(ez) > 145)
        self.assertEqual(len(shots), 5)


class BuildOption(unittest.TestCase):
    def test_off_in_every_preset(self):
        from mod_editor.core import mod_build
        for name, preset in mod_build.PRESETS.items():
            self.assertIs(preset.get("modern_metlife_model"), False, name)

    def test_needs_the_skin_but_no_k128_roster_heap(self):
        """Main 2026-09-24: the model's STADIUM block is 156 KB smaller than retail and the coin-toss free heap is
        unchanged (lab 2), so the option composes with the skin alone; the K128 roster heap is not required."""
        import dataclasses
        from mod_editor.core import mod_build
        plan = mod_build.BuildPlan("", "")
        changes = dict(modern_metlife=True, modern_metlife_model=True)
        if hasattr(plan, "k128_roster_heap"):
            changes["k128_roster_heap"] = False
        blockers = mod_build.validate_plan(dataclasses.replace(plan, **changes))
        self.assertEqual([b for b in blockers if "MetLife" in b or "K128" in b or "roster heap" in b], [])


class LetterBacks(unittest.TestCase):
    def test_every_letter_quad_has_a_dark_back(self):
        """The engine draws the alpha-tested sign material from both sides: each METLIFE STADIUM quad has a copy
        15 cm behind it on ml_letters_back (same silhouette, lit dark), so no lettering reads mirrored."""
        model = mm.build(venue="s19")
        fronts = backs = 0
        for m in model.meshes.values():
            fronts += len(m.groups.get("ml_letters", ()))
            backs += len(m.groups.get("ml_letters_back", ()))
        self.assertGreaterEqual(fronts, 3)
        self.assertEqual(fronts, backs)
        self.assertLess(max(mm.BASE["ml_letters_back"]), 64)


def _extent(points):
    """(width along the ground, height) of a vertical quad's four points."""
    ys = [p[1] for p in points]
    low = [p for p in points if abs(p[1] - min(ys)) < 1e-6]
    return math.dist((low[0][0], low[0][2]), (low[-1][0], low[-1][2])), max(ys) - min(ys)


class Fidelity(unittest.TestCase):
    """b76-u5b: the boards' feed crop, signs and plates at their cells' aspect, the field-wall panels."""

    @classmethod
    def setUpClass(cls):
        cls.models = {v: mm.build(venue=v) for v in ("s18", "s19")}

    def test_board_feed_fills_its_window_without_stretching(self):
        """The live feed is 640x448 inside the 1024x512 jumbo_tron target: each window maps a crop of that
        rectangle (u 0..0.625, v 0..0.875) with the window's own aspect, using its full width or full height."""
        for venue, model in self.models.items():
            m = model.meshes["ml_boards"]
            strips = m.groups["jumbo_tron"]
            self.assertEqual(len(strips), 4, venue)
            for st in strips:
                us = [m.UV[i][0] for i in st]
                vs = [m.UV[i][1] for i in st]
                self.assertGreaterEqual(min(us), -1e-9)
                self.assertLessEqual(max(us), 0.625 + 1e-9)
                self.assertGreaterEqual(min(vs), -1e-9)
                self.assertLessEqual(max(vs), 0.875 + 1e-9)
                du, dv = max(us) - min(us), max(vs) - min(vs)
                self.assertTrue(abs(du - 0.625) < 1e-6 or abs(dv - 0.875) < 1e-6)
                w, h = _extent([m.P[i] for i in st])
                self.assertAlmostEqual(w / h, du * 1024 / (dv * 512), delta=0.01 * w / h)

    def test_signs_and_plates_keep_their_cells_aspect(self):
        for venue, model in self.models.items():
            placements = model.sign_placements(model.loop, model.secs)
            runs = {}
            for key, run, s0, width, height, (u0, v0, u1, v1) in placements:
                cell = (u1 - u0) * 256 / ((v1 - v0) * 512)
                self.assertAlmostEqual(width / height, cell, delta=0.01 * cell, msg=(venue, key))
                runs.setdefault((key, tuple(run)), []).append((s0, width))
            for key, items in runs.items():
                items.sort()
                for (a0, aw), (b0, _bw) in zip(items, items[1:]):
                    self.assertGreaterEqual(b0, a0 + aw - 1e-6, (venue, key))
            plates = [p for p in placements if p[0] == "upper_fascia"]
            self.assertEqual(len(plates), model.roh_count, venue)

    def test_gate_signs_are_not_stretched(self):
        m = self.models["s18"].meshes["ml_gates"]
        for st in m.groups["ml_signs"]:
            w, h = _extent([m.P[i] for i in st])
            self.assertAlmostEqual(w / h, 8.0, delta=0.08, msg=(w, h))

    def test_wall_panels_run_round_the_field_at_their_cells_aspect(self):
        for venue, model in self.models.items():
            spec, v = model.wall_spec()
            H, cells = spec["height_m"], v["cells"]
            panels = model.wall_panels()
            for (a0, aw, _), (b0, _bw, _n) in zip(panels, panels[1:]):
                self.assertAlmostEqual(b0, a0 + aw, places=6)
            self.assertAlmostEqual(panels[-1][0] + panels[-1][1] - panels[0][0], model.loop[-1].s, delta=0.01)
            for s0, w, name in panels:
                if name.startswith("num_"):
                    self.assertAlmostEqual(w, v["number_panel_m"], places=6)
                    self.assertIn(name, v["number_decals"]["cells"])
                    continue
                x0, y0, x1, y1 = cells[name]
                cell_w = H * (x1 - x0) / (y1 - y0)
                if name.startswith("base"):
                    self.assertLessEqual(w, cell_w + 1e-6)
                else:
                    self.assertAlmostEqual(w, cell_w, places=6)
            numbers = [n for _s, _w, n in panels if n.startswith("num_")]
            self.assertEqual(sorted(numbers), sorted(f"num_{k}" for side in v["numbers"] for k in side))
            if numbers:                      # each box keeps its atlas cell's aspect
                bw, bh = v["number_decals"]["size_m"]
                for x0, y0, x1, y1 in v["number_decals"]["cells"].values():
                    self.assertAlmostEqual(bw / bh, (x1 - x0) / (y1 - y0), delta=0.02)

    def test_retail_field_banners_are_gone(self):
        self.assertNotIn("banners_corp01", mm.KEEP)
        self.assertNotIn("banners_fan01", mm.KEEP)


class ColourReceipt(unittest.TestCase):
    """b76-u5b (u6's finding): with Modern colour on the image, the model's writes re-pin the colour receipt's rows
    for the bundles it wrote, so the whole-image colour read-back and a rebuild from the output disc still pass."""

    def _receipt(self, bundles):
        return dict(state="applied", settings={}, bundle_pins={
            name: dict(outer=i, size=len(data), applied_sha256=mm.sha(data),
                       sites=[dict(kind="field", offset=0, size=4, retail="r", applied=mm.sha(data[:4])),
                              dict(kind="normal", offset=12, size=4, retail="r", applied=mm.sha(data[12:16]))])
            for i, (name, data) in enumerate(bundles.items())})

    def test_repin_updates_only_the_written_rows(self):
        bundles = {"s18dd.iff": b"FFFFSSSSSSSSNNNN", "s03dd.iff": b"ffffssssssssnnnn"}
        receipt = self._receipt(bundles)
        after = b"FFFFMMMMMMMMNNNN"
        out = mm.repin_colour_rows(receipt, {"s18dd.iff": after})
        row = out["bundle_pins"]["s18dd.iff"]
        self.assertEqual(row["applied_sha256"], mm.sha(after))
        self.assertEqual([s["applied"] for s in row["sites"]], [mm.sha(b"FFFF"), mm.sha(b"NNNN")])
        self.assertEqual(out["bundle_pins"]["s03dd.iff"], receipt["bundle_pins"]["s03dd.iff"])
        self.assertEqual(out["metlife_model"]["bundles"], ["s18dd.iff"])
        self.assertEqual(receipt["bundle_pins"]["s18dd.iff"]["applied_sha256"], mm.sha(bundles["s18dd.iff"]))

    def test_apply_to_image_repins_the_colour_rows_it_wrote(self):
        from contextlib import contextmanager
        from types import SimpleNamespace
        from unittest import mock
        from mod_editor.core import nfl2k5_modern_color as colour
        from mod_editor.core import nfl2k5_modern_metlife as ml
        names = ["s18dd.iff", "s19nd.iff"]
        skin = {n: bytes([65 + i]) * 4 + b"SKINSKIN" + b"NNNN" for i, n in enumerate(names)}
        model = {n: skin[n][:4] + b"MODELMOD" + skin[n][12:] for n in names}
        disc = bytearray(b"".join(skin[n] for n in names) + b"gradedonly")
        entries = [SimpleNamespace(virtual_offset=16 * i, size=16) for i in range(len(names))]

        class Archive:
            def __init__(self):
                self.entries = entries

            def read(self, at, n):
                return bytes(disc[at:at + n])

            def write(self, at, data):
                disc[at:at + len(data)] = data
                return len(data)

        @contextmanager
        def opener(path, writable=False):
            yield Archive()

        pins = dict(bundles=[dict(name=n, outer=i, offset=4, length=8, skin_sha256=mm.sha(b"SKINSKIN"),
                                  model_sha256=mm.sha(b"MODELMOD")) for i, n in enumerate(names)], crowd=[])
        receipt = self._receipt({n: skin[n] for n in names})
        saved = {}

        def colour_state(target, receipt):
            ok = all(mm.sha(bytes(disc[16 * r["outer"]:16 * r["outer"] + 16])) == r["applied_sha256"]
                     for r in receipt["bundle_pins"].values())
            return "applied" if ok else "foreign"

        with mock.patch.object(mm.official, "validate_feature"), \
                mock.patch.object(mm, "model_pins", return_value=pins), \
                mock.patch.object(mm, "image_status", return_value="skin"), \
                mock.patch.object(mm, "verify", return_value=dict(state="applied")), \
                mock.patch.object(mm, "build_all", return_value={n: (skin[n], model[n], {}) for n in names}), \
                mock.patch.object(mm, "_stretch", side_effect=lambda b: (4, bytes(b[4:12]))), \
                mock.patch.object(ml, "_outer_image", return_value=opener), \
                mock.patch.object(ml, "VARIANTS", names), \
                mock.patch.object(colour, "read_image_receipt", return_value=receipt), \
                mock.patch.object(colour, "image_status", side_effect=colour_state), \
                mock.patch.object(colour, "_save_image_receipt", side_effect=lambda t, r: saved.update(r)):
            out = mm.apply_to_image("disc.iso", retail_source="retail")
        self.assertEqual(out["colour_rows_repinned"], sorted(names))
        for i, n in enumerate(names):
            self.assertEqual(bytes(disc[16 * i:16 * i + 16]), model[n])
            row = saved["bundle_pins"][n]
            self.assertEqual(row["applied_sha256"], mm.sha(model[n]))
            self.assertEqual([s["applied"] for s in row["sites"]], [mm.sha(model[n][:4]), mm.sha(model[n][12:16])])
        self.assertEqual(colour_state("disc.iso", saved), "applied")


@unittest.skipUnless(EXTRACTED.is_dir() and mm.PINS_PATH.is_file(), "needs the hydrated retail archive and pins")
class Pins(unittest.TestCase):
    def test_two_bundles_match_their_pins(self):
        from mod_editor.core import nfl2k5_modern_metlife as ml
        pins = {p["name"]: p for p in mm.model_pins()["bundles"]}
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(EXTRACTED)
        with ml._outer_image()(str(EXTRACTED)) as archive:
            entries = ml.metlife_entries(archive)
            for name in ("s18dd.iff", "s19ns.iff"):
                e = entries[name]
                retail = archive.read(e.virtual_offset, e.size)
                dry = archive.read(entries[ml.dry_name(name)].virtual_offset, entries[ml.dry_name(name)].size)
                skin = mm.skin_bundle(retail, name, dry)
                model, info = mm.model_bundle(skin, name)
                self.assertEqual(len(model), len(retail))
                off, stretch = mm._stretch(model)
                self.assertEqual(off, pins[name]["offset"])
                self.assertEqual(mm.sha(stretch), pins[name]["model_sha256"])
                self.assertEqual(mm.sha(mm._stretch(skin)[1]), pins[name]["skin_sha256"])
                # outside the stretch the bundle is the skin's, byte for byte
                self.assertEqual(model[:off], skin[:off])
                self.assertEqual(model[off + len(stretch):], skin[off + len(stretch):])


if __name__ == "__main__":
    unittest.main()

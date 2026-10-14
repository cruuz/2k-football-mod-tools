"""2025-26 NFL officials (beta 77 rf1): the pins and the shipped art, the Build wiring, and, when a retail USA image is
present, the real compile of the referee scene, the caps and the number textures against their pins.

The always-on tests read only the repository. The retail checks read the user's own disc image and skip without it
(point NFL2K5_RETAIL_XISO at the retail USA .xiso.iso).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for _extra in (ROOT, ROOT / "tools", ROOT / "tests"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_build_settings as build_settings  # noqa: E402
from mod_editor.core import nfl2k5_modern_officials as mo  # noqa: E402

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_XISO", str(ROOT / "ESPN NFL 2K5 (USA).xiso.iso")))
HAVE_RETAIL = RETAIL.is_file()
PARTS = {"scene:referee", "tset:rhat"} | {f"txtr:{n}" for n in mo.NUMBERS}


def _rgba(name):
    import numpy as np
    from PIL import Image
    with Image.open(mo.art_path(name)) as image:
        return np.asarray(image.convert("RGBA")).astype(int)


class PinsAndArt(unittest.TestCase):
    def test_pins_name_every_part(self):
        pins = mo.pins()
        self.assertEqual(pins["archive"], "gamedata.iff")
        self.assertEqual({p["part"] for p in pins["parts"]}, PARTS)
        for p in pins["parts"]:
            self.assertNotEqual(p["retail_sha256"], p["applied_sha256"])
            self.assertIn(p["palette_max"], mo.PALETTE_LADDER)
            self.assertLessEqual(p["fit"]["scratch_needed"], p["fit"]["scratch_retail"])
            self.assertEqual(p["fit"]["stored_size"] + 0x20, p["span_size"])
            self.assertEqual(p["outer_id"], f"0x{mo.name_id('gamedata.iff'):08x}")
        scene = [p for p in pins["parts"] if p["kind"] == "SCNE"][0]
        self.assertEqual((scene["chunk_index"], scene["span_size"]), (109, 0x20 + 166416))
        lanes = scene["uv_lanes"]
        self.assertEqual(len(lanes), sum(len(v) for _s, _m, v, _t in mo.UV_EDITS))
        self.assertTrue(all(lane["retail"] != lane["applied"] for lane in lanes))

    def test_the_shipped_art_matches_its_pins_and_sizes(self):
        self.assertTrue(mo.available())
        from PIL import Image
        for name, digest in mo.pins()["art"].items():
            path = mo.art_path(name)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            with Image.open(path) as image:
                self.assertEqual(image.size, mo.ART_SIZES[name], name)

    def test_only_authored_textures_ship(self):
        shipped = {p.relative_to(mo.DATA_DIR).as_posix() for p in mo.DATA_DIR.rglob("*") if p.is_file()}
        self.assertEqual(shipped, {"pins.json", "README.md"} | {f"{name}.png" for name in mo.ART})

    def test_the_number_textures_are_black_ink_below_a_clear_band(self):
        for name in mo.NUMBERS:
            rgba = _rgba(f"numbers/{name}")
            self.assertEqual(int(rgba[:51, :, 3].max()), 0, name)           # the retired front patch samples here
            ink = rgba[..., 3] > 128
            self.assertGreater(int(ink[51:].sum()), 150, name)
            self.assertLess(int(rgba[ink][:, :3].max()), 40, name)            # black letters and numbers
            self.assertLess(int(rgba[rgba[..., 3] == 0][:, :3].max()), 40)    # clear texels carry no light fringe
        # the head linesman's slot draws two letters (DJ) like the other two-letter roles, the referee one (R)
        widths = {}
        for name in mo.NUMBERS:
            rows = _rgba(f"numbers/{name}")[61:78, :, 3] > 128
            cols = rows.any(0).nonzero()[0]
            widths[name] = int(cols.max() - cols.min())
        self.assertGreater(widths["ref_HL"], widths["ref_R"] * 1.4)
        self.assertGreater(widths["ref_LJ"], widths["ref_U"] * 1.4)

    def test_the_caps_share_one_structure(self):
        white, black = _rgba("hat_white"), _rgba("hat_black")
        self.assertEqual(white.shape, black.shape)
        # the piping weight read back from each cap agrees texel for texel (white 240 -> 224, black 22 -> 230)
        t_white = (240.0 - white[..., :3].mean(-1)) / 16.0
        t_black = (black[..., :3].mean(-1) - 22.0) / 208.0
        self.assertLess(float(abs(t_white - t_black).max()), 0.2)
        self.assertGreater(int(white[..., :3].min()), 180)                   # a white cap
        self.assertLess(int(black[..., :3].mean()), 80)                      # a black cap with light piping
        self.assertGreater(int(black[..., :3].max()), 200)

    def test_the_collar_texel_is_inside_a_black_area(self):
        shirt = _rgba("shirt")
        r, c = int(mo.COLLAR_UV[1] * 256), int(mo.COLLAR_UV[0] * 256)
        self.assertLess(int(shirt[r - 6:r + 7, c - 6:c + 7, :3].max()), 60)
        numbers = _rgba("numbers/ref_R")
        r, c = int(mo.FRONT_PATCH_UV[1] * 128), int(mo.FRONT_PATCH_UV[0] * 128)
        self.assertEqual(int(numbers[max(0, r - 12):r + 13, :, 3].max()), 0)

    def test_joint_quantize_keeps_identical_structure(self):
        import numpy as np
        a = np.zeros((8, 8, 4), np.uint8)
        a[...] = (240, 240, 238, 255)
        b = np.zeros((8, 8, 4), np.uint8)
        b[...] = (22, 22, 24, 255)
        a[2:4, :] = (224, 224, 222, 255)
        b[2:4, :] = (230, 230, 228, 255)
        idx, pa, pb = mo.joint_quantize([a.tobytes()], [b.tobytes()])
        index = np.frombuffer(idx[0], np.uint8).reshape(8, 8)
        self.assertEqual(len(pa), 2)
        self.assertTrue((pa[index] == a).all() and (pb[index] == b).all())

    def test_malformed_pins_are_refused(self):
        with self.assertRaises(mo.ModernOfficialsError):
            mo._check_pins({"schema": "other"})
        good = json.loads(mo.PINS_PATH.read_text(encoding="utf-8"))
        with self.assertRaises(mo.ModernOfficialsError):
            mo._check_pins(dict(good, parts=good["parts"][1:]))
        with self.assertRaises(mo.ModernOfficialsError):
            mo._check_pins(dict(good, archive="other.iff"))


class BuildWiring(unittest.TestCase):
    def test_plan_presets_availability_and_settings(self):
        plan = mod_build.BuildPlan("s", "t")
        self.assertIs(plan.modern_officials, False)
        self.assertIn("modern_officials", plan.to_recipe())
        for name, values in mod_build.PRESETS.items():
            with self.subTest(preset=name):
                self.assertIs(values["modern_officials"], name == "softdrink_experimental")
        self.assertTrue(mod_build.availability()["modern_officials"])
        self.assertIn("modern_officials", build_settings.FEATURE_KEYS)
        saved = build_settings.build_settings({"modern_officials": True})
        self.assertIs(build_settings.to_plan(saved, "s", "t").modern_officials, True)
        self.assertEqual((mo.DEFAULT_ENABLED, mo.CAVES, mo.REQUESTS, mo.RUNTIME_GLOBALS, mo.LABEL),
                         (False, (), (), (), "EXPERIMENTAL / UNWITNESSED"))

    def test_refusals_before_any_copy(self):
        from nfl2k5_throw_tuning_test import _build_synthetic_xbe
        with tempfile.TemporaryDirectory(prefix="officials-plan-") as raw:
            root = Path(raw)
            xbe = root / "default.xbe"
            xbe.write_bytes(_build_synthetic_xbe())
            with self.assertRaisesRegex(ValueError, "needs? a disc image"):
                mod_build.build(mod_build.BuildPlan(str(xbe), str(root / "out.xbe"), modern_officials=True))
            with self.assertRaisesRegex(ValueError, "must be Off or On"):
                mod_build.build(mod_build.BuildPlan(str(xbe), str(root / "out2.xbe"), modern_officials=1))
            self.assertEqual(mod_build.inspect(xbe)["modern_officials"], "needs_image")
            self.assertFalse((root / "out.xbe").exists())

    def test_the_build_step_and_panel_name_the_option(self):
        source = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        for needle in ("officials.apply_to_image(target, progress=progress)", '"step": "modern_officials"',
                       "officials.image_status(source)"):
            self.assertIn(needle, source)
        self.assertLess(source.index('"step": "modern_fans"'), source.index('"step": "modern_officials"'))
        panel = (ROOT / "mod_editor/gui/build_panel_qt.py").read_text(encoding="utf-8")
        for needle in ('"modern_officials": self.modern_officials_check',
                       "modern_officials=self._modern_officials_changed()", "def _modern_officials_changed(self)"):
            self.assertIn(needle, panel)


@unittest.skipUnless(HAVE_RETAIL, "retail USA image not present (NFL2K5_RETAIL_XISO)")
class RetailCompile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with mo._outer_image()(RETAIL) as archive:
            _entry, cls.raw = mo._archive_bytes(archive)
        cls.spans = {}
        for row in mo.pins()["parts"]:
            chunk = mo._find_chunk(cls.raw, row)
            cls.spans[row["part"]] = (row, chunk, cls.raw[chunk.offset:chunk.offset + row["span_size"]])

    def test_retail_image_reads_retail(self):
        self.assertEqual(mo.image_status(RETAIL), "retail")

    def test_every_part_compiles_to_its_pin_and_keeps_its_wrapper(self):
        tx, _fill = mo._tools()
        for part, (row, _chunk, span) in self.spans.items():
            with self.subTest(part=part):
                self.assertEqual(mo.sha(span), row["retail_sha256"])
                after, detail = mo.compile_part(row, span)
                self.assertEqual(mo.sha(after), row["applied_sha256"])
                self.assertEqual((len(after), after[:0x20]), (len(span), span[:0x20]))
                self.assertLessEqual(detail["fit"]["scratch_needed"], detail["fit"]["scratch_retail"])
                if row["kind"] != "SCNE":
                    ca, cr = tx.parse_chunks(after, allow_trailing=True)[0], tx.parse_chunks(span, allow_trailing=True)[0]
                    da, dr = tx.decode_chunk(after, ca)[0], tx.decode_chunk(span, cr)[0]
                    self.assertEqual(da[:ca.system_bytes], dr[:cr.system_bytes])   # header, names, descriptors kept

    def test_the_scene_changes_only_its_two_textures_and_the_uv_plan(self):
        """Positions, normals, skin, topology and every other scene byte stay retail."""
        import numpy as np
        tx, _fill = mo._tools()
        row, _chunk, span = self.spans["scene:referee"]
        after, _detail = mo.compile_part(row, span)
        _c, rec, before = mo._scene_parts(span)
        _c2, rec2, decoded = mo._scene_parts(after)
        allowed = np.zeros(len(before), bool)
        system = int(rec["system_bytes"])
        for tex in rec["embedded_textures"]:
            allowed[system + int(tex["pixel_offset"]):system + int(tex["palette_offset"]) + 1024] = True
        lanes = mo.uv_edit_lanes(rec, before)
        for lane in lanes:
            allowed[lane["at"]:lane["at"] + 4] = True
            self.assertEqual(list(struct.unpack_from("<2h", decoded, lane["at"])), lane["applied"])
        changed = np.frombuffer(before, np.uint8) != np.frombuffer(decoded, np.uint8)
        self.assertGreater(int(changed.sum()), 0)
        self.assertEqual(int((changed & ~allowed).sum()), 0)
        self.assertEqual([lane["retail"] for lane in lanes], [lane["retail"] for lane in row["uv_lanes"]])

    def test_the_uv_plan_vertex_sets_are_closed(self):
        """No triangle outside the plan's material uses a planned vertex (proved on the retail scene's own export)."""
        from mod_editor.core import nfl2k5_models as models
        row, chunk, span = self.spans["scene:referee"]
        key = models.model_key(346, chunk.index)
        source = models.ModelSpanSource({key: span})
        with tempfile.TemporaryDirectory(prefix="officials-gltf-") as raw:
            out = Path(raw) / "referee.gltf"
            models.export_model(source, key, out)
            gltf = models.GltfFile(out)
            document = json.loads(out.read_text(encoding="utf-8"))
            planned = {(shape, v): material for shape, material, vertices, _t in mo.UV_EDITS for v in vertices}
            seen = set()
            for mesh in document["meshes"]:
                for prim in mesh["primitives"]:
                    material = document["materials"][prim["material"]]["name"]
                    game = [int(v[0]) for v in gltf.accessor(prim["attributes"]["_NFL_VERTEX_INDEX"])]
                    index = [int(v[0]) for v in gltf.accessor(prim["indices"])]
                    used = {game[i] for i in index}
                    for vertex in used:
                        owner = planned.get((mesh["name"], vertex))
                        if owner is not None:
                            self.assertEqual(owner, material, f"{mesh['name']} vertex {vertex} is also {material}")
                            seen.add((mesh["name"], vertex))
            self.assertEqual(seen, set(planned))


if __name__ == "__main__":
    unittest.main()

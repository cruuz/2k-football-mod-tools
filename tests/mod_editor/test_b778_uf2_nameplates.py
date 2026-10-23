"""uf2 (b778): readable Jaguars nameplates and a solid hyphen in every nameplate.

Noah (10/22): "The last names on the Jaguars jerseys should be refined so they're more readable", and "on jerseys,
hyphens are like hollow ... It should be filled in the same fill color as the letters."

Gate: every kit's hyphen cell has no enclosed hole after the pass, and the four 2026 Jaguars atlases carry the
retail letter counters with the kit's fill and outline.
"""
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
from mod_editor.core import nfl2k5_glyph_fixes_2026 as glyphfix  # noqa: E402
from mod_editor.core import nfl2k5_kit_fixes_2026 as kitfix  # noqa: E402
from mod_editor.core import nfl2k5_nameplate_fixes_2026 as fixes  # noqa: E402
from nfl_txtr import decode_chunk, parse_chunks, parse_texture, texture_to_rgba  # noqa: E402

SEA_FONT = Path("/media/noah/Storage/.b76-research/u1/teams/_d8_fonts/sea_flat/"
                "NFL_Seattle_Seahawks_Flat[1].ttf")


def _cell(mask, width, height):
    array = np.zeros((height, width), bool)
    array[:] = mask
    return array


class StructureMasks(unittest.TestCase):
    def test_band_keeps_one_texel_outline_and_clears_counters_and_plate(self):
        height, width = 16, 16
        fill = np.zeros((height, width), bool)
        fill[5:11, 5:11] = True
        fill[7:9, 7:9] = False                       # a counter inside the glyph
        outline = np.ones((height, width), bool)      # the opaque plate around the fill
        outline[fill] = False
        kept_fill, keep, clear = fixes.structure_plan(fill, outline)
        self.assertTrue(kept_fill is fill)
        # one texel outside the fill is the outline
        self.assertTrue(keep[4, 5] and keep[5, 4] and keep[11, 10])
        # the plate two texels out and the whole counter become clear
        self.assertTrue(clear[3, 5] and clear[5, 3] and clear[0, 0])
        self.assertTrue(clear[7:9, 7:9].all())
        # the fill texels are neither outline nor clear (the counter inside them is clear)
        self.assertFalse(keep[5:11, 5:11].any())
        counter = np.zeros((height, width), bool)
        counter[7:9, 7:9] = True
        self.assertFalse((clear[5:11, 5:11] & ~counter[5:11, 5:11]).any())

    def test_enclosed_finds_only_the_inner_component(self):
        mask = np.zeros((8, 8), bool)
        mask[0:2, :] = True                          # touches the border
        mask[3:5, 3:5] = True                        # the inner component
        inner = fixes._enclosed(mask)
        self.assertTrue(inner[3:5, 3:5].all())
        self.assertFalse(inner[0:2, :].any())

    def test_hyphen_holes_are_enclosed_background(self):
        palette = np.zeros((256, 4), np.int64)
        palette[7] = (10, 42, 78, 255)
        indices = np.zeros((32, 32), np.uint8)
        indices[13:19, 4:11] = 7                     # a hollow bar
        indices[14:18, 5:10] = 0
        holes = fixes._hyphen_holes(indices, palette, 4, 7, 0)
        self.assertEqual(int(holes.sum()), 20)
        indices[14:18, 5:10] = 7
        self.assertEqual(int(fixes._hyphen_holes(indices, palette, 4, 7, 0).sum()), 0)

    def test_fill_index_is_the_opaque_letter_interior(self):
        palette = np.zeros((256, 4), np.int64)
        palette[5] = (200, 200, 200, 255)
        palette[7] = (10, 42, 78, 255)
        palette[9] = (0, 0, 0, 128)
        indices = np.zeros((32, 96), np.uint8)
        metrics = [(0, 8), (16, 8)] + [(16 + 32 * i, 16) for i in range(27)]
        for x, width in metrics[2:]:
            indices[6:26, x + 4:x + width - 4] = 7    # the fill
            indices[6:26, x:x + 1] = 9                # the outline
        self.assertEqual(fixes._fill_index(indices, palette, metrics), 7)


class Data(unittest.TestCase):
    def setUp(self):
        self.doc = fixes.spec()

    def test_rows_are_the_four_2026_jaguars_atlases(self):
        rows = {row["selector"]: row for row in fixes.structures(self.doc)}
        self.assertEqual(sorted(rows), ["12A0", "12A6", "12H0", "12H6"])
        for selector, row in rows.items():
            self.assertEqual((row["chunk"], row["kind"], row["texture"]), (43, "names_structure", "names"))
            self.assertEqual(row["retail_selector"], "12H0" if selector == "12H0" else "12A0")
            self.assertRegex(row["before_sha256"], "^[0-9a-f]{64}$")
            self.assertRegex(row["after_sha256"], "^[0-9a-f]{64}$")
            self.assertRegex(row["retail_sha256"], "^[0-9a-f]{64}$")
            self.assertNotEqual(row["before_sha256"], row["after_sha256"])
            self.assertEqual(row["fill_threshold"], 0.5)
        self.assertEqual((rows["12H0"]["fill"], rows["12H0"]["outline"]), ("#FFFFFF", "#000000"))
        self.assertEqual((rows["12A0"]["fill"], rows["12A0"]["outline"]), ("#101010", "#101010"))

    def test_no_private_paths_and_packaged(self):
        text = fixes.DATA.read_text(encoding="utf-8")
        self.assertNotIn("/home/", text)
        self.assertNotIn("/media/", text)
        self.assertTrue(text.isascii())
        allow = (ROOT / "packaging/release-allowlist.txt").read_text(encoding="utf-8").splitlines()
        self.assertIn("mod_editor/core/nfl2k5_nameplate_fixes_2026.py", allow)
        self.assertIn("data/nfl2k5_nameplate_fixes_2026.json", allow)
        digest = hashlib.sha256(fixes.DATA.read_bytes()).hexdigest()
        providers = (ROOT / "mod_editor/core/providers.py").read_text(encoding="utf-8")
        self.assertIn('"data/nfl2k5_nameplate_fixes_2026.json": "%s"' % digest, providers)
        module = hashlib.sha256(Path(fixes.__file__).read_bytes()).hexdigest()
        self.assertIn('"mod_editor/core/nfl2k5_nameplate_fixes_2026.py": "%s"' % module, providers)

    def test_studio_runs_after_the_anniversary_moment_kits(self):
        text = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        at = text.index("nameplate_fixes.apply_to_image(")
        moment = text.index("moment_kits.apply_to_image(target)")
        self.assertLess(moment, at)
        self.assertLess(text.index("kit_fixes.apply_nameplates(target)"), at)
        self.assertLess(at, text.index("if plan.roster_edits:", moment))

    def test_schema_refuses_a_missing_pin(self):
        broken = dict(self.doc, structures=[dict(self.doc["structures"][0])])
        del broken["structures"][0]["after_sha256"]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "broken.json"
            path.write_text(json.dumps(broken), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "after_sha256"):
                fixes.spec(path)


class FontHyphen(unittest.TestCase):
    def test_enclosed_holes_are_filled(self):
        from tools import nfl2k5_team_2026_art as art
        glyph = np.zeros((10, 10), np.uint8)
        glyph[1:9, 1:9] = 255
        glyph[3:7, 3:7] = 0
        filled = art.fill_enclosed_holes(glyph)
        self.assertTrue((filled[3:7, 3:7] == 255).all())

    @unittest.skipUnless(SEA_FONT.is_file(), "the Seahawks nameplate font is not present")
    def test_the_seahawks_hyphen_is_solid(self):
        from tools import nfl2k5_team_2026_art as art
        hollow = art.render_font_box(str(SEA_FONT), "-", 24, 12)
        solid = art.render_font_box(str(SEA_FONT), "-", 24, 12, fill_holes=True)
        self.assertEqual(float(hollow.min()), 0.0)
        self.assertGreater(float(solid.min()), 0.9)
        self.assertFalse(fixes._enclosed(solid > 0.5).any())


def read_kits(disc, selectors=None):
    from mod_editor.core import nfl2k5_bump_texture_writer as bump
    out = {}
    with bump._Image.open(Path(disc), writable=False) as image:
        index = bump._parsed_index(image)
        for entry in index.entries:
            name = bump.logical_name_for(entry.name_id) or ""
            stem = name[:-4] if name.endswith(".IFF") else ""
            if len(stem) in (4, 5) and stem[:2].isdigit() and stem[2] in "HA" and stem[3:].isdigit():
                if selectors is None or stem in selectors:
                    out[stem] = image.read_segments(index.sub_extents(entry, 0, entry.size))
    return out


def _uf1_fixed(kits):
    """The uf1 nameplate metrics layer applied in memory (the uf2 pass runs after it)."""
    doc = kitfix.nameplates()
    out = dict(kits)
    for selector in kitfix.selectors(doc):
        parts, _receipt = kitfix.compile_resource(selector, kits[selector], strict=True, document=doc,
                                                  kits={"07A0": kits["07A0"]})
        raw = bytearray(kits[selector])
        for offset, data in parts:
            raw[offset:offset + len(data)] = data
        out[selector] = bytes(raw)
    return out


def _atlas(raw):
    chunk, decoded, _info, texture = fixes._one_txtr(fixes._chunk_atlas(raw))
    rgba = np.frombuffer(texture_to_rgba(decoded, chunk, texture), np.uint8).reshape(texture.height, texture.width, 4)
    return rgba


RELEASE = os.environ.get("NFL2K5_V061_DISC")
RETAIL = os.environ.get("NFL2K5_RETAIL_XISO")


@unittest.skipUnless(RELEASE, "set NFL2K5_V061_DISC (the SOFTDRINK 2K28 v0.6.1 release disc, read only)")
class ReleaseDisc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = fixes.spec()
        cls.kits = read_kits(RELEASE)
        cls.retail_kits = read_kits(RETAIL, {"12H0", "12A0", "12H6", "12A6"}) if RETAIL else None
        cls.after = {}
        for selector, raw in _uf1_fixed(cls.kits).items():
            replacements, detail = fixes._compile_package(selector, raw, cls.doc, cls.retail_kits, strict=False)
            fixed = bytearray(raw)
            for offset, data in replacements:
                fixed[offset:offset + len(data)] = data
            cls.after[selector] = (bytes(fixed), detail)

    def test_the_release_has_only_the_six_seahawks_hollow_hyphens(self):
        # 07H7/07A7 are the Dallas metrics defect uf1 repairs; their atlas is 07A0's solid hyphen, so this pass
        # leaves them alone until uf1 has run (the gate below runs after it).
        hollow = sorted(selector for selector, raw in self.kits.items() if fixes.hyphen_report(raw))
        self.assertEqual(hollow, ["26A0", "26A3", "26A4", "26H0", "26H3", "26H4"])

    def test_every_kits_hyphen_has_fill_after_the_layer(self):
        self.assertGreater(len(self.after), 690)
        hollow = sorted(selector for selector, (raw, _detail) in self.after.items() if fixes.hyphen_report(raw))
        self.assertEqual(hollow, [])
        changed = sorted(selector for selector, (raw, detail) in self.after.items() if detail.get("hyphen") == "filled")
        self.assertEqual(changed, ["26A0", "26A3", "26A4", "26H0", "26H3", "26H4"])
        for selector, (raw, _detail) in self.after.items():
            self.assertTrue(kitfix.nameplate_layout(raw)[2], selector)

    @unittest.skipUnless(RETAIL, "set NFL2K5_RETAIL_XISO (the retail disc, read only)")
    def test_jaguars_letters_get_their_counters_and_outline(self):
        for row in fixes.structures(self.doc):
            replacements, detail = fixes._compile_package(row["selector"], self.kits[row["selector"]], self.doc,
                                                          self.retail_kits, strict=True)
            self.assertEqual(detail["structure"], "applied")
            self.assertEqual(len(replacements), 1)
            self.assertEqual(hashlib.sha256(replacements[0][1]).hexdigest(), row["after_sha256"])
        home_before = _atlas(self.kits["12H0"])
        home_after = _atlas(self.after["12H0"][0])
        name_chunk = next(c for c in parse_chunks(self.after["12H0"][0]) if c.kind == "NAME")
        metrics = kitfix.name_metrics(self.after["12H0"][0][name_chunk.offset:name_chunk.end_offset])
        x, width = metrics[17]                          # P
        before_cell = home_before[2:30, x:x + width]
        after_cell = home_after[2:30, x:x + width]
        self.assertEqual(int(fixes._enclosed(~(before_cell[..., 3] > 0)).sum()), 0)
        self.assertGreater(int(fixes._enclosed(~(after_cell[..., 3] > 0)).sum()), 0)
        opaque = after_cell[after_cell[..., 3] > 0]
        self.assertIn((0, 0, 0, 255), {tuple(int(v) for v in px) for px in opaque})
        self.assertEqual(tuple(int(v) for v in np.median(opaque[opaque[:, 0] > 200][:, :3], axis=0)), (255, 255, 255))
        away_after = _atlas(self.after["12A0"][0])
        away_cell = away_after[2:30, x:x + width]
        self.assertGreater(int(fixes._enclosed(~(away_cell[..., 3] > 0)).sum()), 0)
        dark = away_cell[(away_cell[..., 3] > 0)]
        self.assertLessEqual(int(dark[:, :3].max()), 32)

    @unittest.skipUnless(RETAIL, "set NFL2K5_RETAIL_XISO (the retail disc, read only)")
    def test_retail_kits_are_left_alone(self):
        for row in fixes.structures(self.doc):
            replacements, detail = fixes._compile_package(row["selector"], self.retail_kits[row["selector"]],
                                                          self.doc, self.retail_kits, strict=False)
            self.assertEqual((replacements, detail["structure"]), ([], "other_uniform"))
        hollow = [selector for selector, raw in self.retail_kits.items() if fixes.hyphen_report(raw)]
        self.assertEqual(hollow, [])


@unittest.skipUnless(RETAIL, "set NFL2K5_RETAIL_XISO (the retail disc, read only)")
class RetailDisc(unittest.TestCase):
    def test_every_retail_hyphen_is_solid_and_every_layout_fits(self):
        kits = read_kits(RETAIL)
        self.assertEqual(len(kits), 634)
        self.assertEqual([s for s, raw in kits.items() if fixes.hyphen_report(raw)], [])
        self.assertEqual([s for s, raw in kits.items() if not kitfix.nameplate_layout(raw)[2]], [])


if __name__ == "__main__":
    unittest.main()

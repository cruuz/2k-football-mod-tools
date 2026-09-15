"""Beta 70: the 2026 Monday Night Football scorebug (compact runtime owner, ESPN digits, wing panels).

Standalone: python3 tests/mod_editor/test_nfl2k5_scorebug_mnf.py -v
Retail-backed checks skip precisely when the extraction is absent.
"""
from __future__ import annotations

import os
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core import nfl2k5_scorebug_exact as exact  # noqa: E402
from mod_editor.core import nfl2k5_scorebug_mnf_font as mnf_font  # noqa: E402
from mod_editor.core import nfl2k5_scorebug_resources as resources  # noqa: E402
from mod_editor.core import nfl2k5_scorebug_runtime as runtime  # noqa: E402

INDEX = Path(os.environ.get("NFL2K5_RETAIL_INDEX") or str(ROOT / "extracted" / "ESPN NFL 2K5 (USA)" / "vc_53450030" / "0"))


def _retail_pack_head():
    if not INDEX.is_file():
        raise unittest.SkipTest(f"retail pack 0 not present at {INDEX}")
    with INDEX.open("rb") as stream:
        return stream.read(4 * 1024 * 1024)


class OwnerCodeTests(unittest.TestCase):
    def test_owner_fits_its_named_allocation_and_patches_its_pointers(self):
        code_va, data_va = 0x14BA2C0, 0x14BB000
        content, labels = runtime.code_for(code_va, data_va)
        self.assertEqual(len(content), runtime.CODE_SIZE)
        used = len(content.rstrip(b"\xcc"))
        self.assertLess(used, runtime.CODE_SIZE - 8)
        for side in (0, 1):
            at = labels[f"dash_callback{side}"] - code_va
            self.assertEqual(content[at:at + 2], b"\xc7\x05")
            self.assertEqual(struct.unpack_from("<I", content, at + 2)[0], runtime.CITY_CALLBACKS[side])
            self.assertEqual(struct.unpack_from("<I", content, at + 6)[0], labels[f"dash_text{side}"])
        at = labels["plate_table_ref"] - code_va
        self.assertEqual(struct.unpack_from("<I", content, at)[0], labels["plate_table"])
        table = struct.unpack_from("<40I", content, labels["plate_table"] - code_va)
        self.assertEqual(list(table), exact.plate_table())

    def test_plate_table_is_indexed_by_asset_code(self):
        table = exact.plate_table()
        self.assertEqual(len(table), 40)
        from mod_editor.core.nfl2k5_scorebug_ingame import TEAM_LOGOS
        self.assertEqual(table[int(TEAM_LOGOS["KC"]["asset_code"])], exact.plate_argb("KC"))
        self.assertEqual(table[int(TEAM_LOGOS["DEN"]["asset_code"])], exact.plate_argb("DEN"))
        self.assertTrue(all(word >> 24 == 0xFF for word in table))
        # Dark primaries are brightened along their hue, never toward grey.
        den = exact.plate_argb("DEN")
        self.assertGreater(den & 0xFF, (den >> 16) & 0xFF)

    def test_state_layout_fits_the_data_page(self):
        self.assertLess(runtime.PHASE + 4, runtime.DATA_SIZE)
        self.assertLessEqual(runtime.TEXTURES + 8, runtime.SCORES)

    def test_overrides_and_literals_are_recognized_fields(self):
        rows = runtime.override_edits()
        vas = {va for va, _old, _new, _ in rows}
        self.assertTrue(set(runtime.STATIC_OVERRIDES) <= vas)
        self.assertTrue(set(runtime.LITERALS) <= vas)
        for va, _old, new, _ in rows:
            if va in runtime.LITERALS:
                self.assertEqual(len(new), len((runtime.LITERALS[va][0] + "\0").encode("utf-16le")))


class ArtTests(unittest.TestCase):
    def test_atlas_and_panels(self):
        atlas = exact.atlas_mnf()
        self.assertEqual(atlas.size, (64, 64))
        self.assertLessEqual(len(set(atlas.getdata())), 256)
        ramp_row = sum(exact.MNF_WING_RAMP_ROWS) // 2
        for team, side in (("DEN", "away"), ("KC", "home"), (None, "away")):
            panel = exact.mnf_panel(team, side)
            self.assertEqual(panel.size, (64, 64))
            # The ramp rows carry the team colour at column 0 and the bar charcoal at column 63.
            self.assertEqual(panel.getpixel((63, ramp_row))[:3], exact.MNF_COLORS["body"])
            self.assertEqual(panel.getpixel((63, ramp_row))[3], 255)
        away = exact.mnf_panel("KC", "away")
        self.assertGreater(away.getpixel((0, ramp_row))[0], away.getpixel((63, ramp_row))[0])
        # The ESPN mark sits in the logo rows at its own aspect, over transparency.
        l0, l1 = exact.MNF_WING_LOGO_ROWS
        logo_box = away.crop((0, l0, 64, l1)).getchannel("A").getbbox()
        self.assertIsNotNone(logo_box)
        self.assertGreater(logo_box[2] - logo_box[0], 40)
        self.assertEqual(away.crop((0, l1, 64, exact.MNF_WING_RAMP_ROWS[0])).getchannel("A").getbbox(), None)

    def test_wing_strips_draw_exactly_the_fade_and_logo_quads(self):
        # Beta 71: each retail wing strip (32 vertices, repeated ids) must draw two quads only.
        from mod_editor.core import nfl2k5_scorebug_ingame as r
        rec = r.RESOURCES["score_bug"]
        with INDEX.open("rb") as stream:
            stream.seek(rec["pack_offset"]); span = stream.read(rec["span_size"])
        retail = r.pinned(span, rec)
        m = exact.mesh_mnf(retail)
        strips = [indices for _, indices in r.layout.strips(retail)]
        for side in ("away", "home"):
            layout = exact.MNF_WING_LAYOUT[side]
            indices = next(indices for indices in strips if layout["fade"][0] in indices)
            visible = [tuple(indices[i:i + 3]) for i in range(len(indices) - 2)
                       if len({tuple(m.pos[v][:2]) for v in indices[i:i + 3]}) == 3]
            fade, logo = layout["fade"], layout["logo"]
            self.assertEqual(visible, [fade[:3], fade[1:], logo[:3], logo[1:]], side)
            # The logo quad sits inside the wing box, at the measured 170x91 source-pixel box.
            xs = [m.pos[v][0] for v in logo]
            ys = [m.pos[v][1] for v in logo]
            wing = exact.MNF_PANELS[side]
            self.assertGreaterEqual(min(xs), wing[0] - 1e-6)
            self.assertLessEqual(max(xs), wing[2] + 1e-6)
            self.assertAlmostEqual(max(xs) - min(xs), (625 - 455) / 3, places=3)
            self.assertAlmostEqual(max(ys) - min(ys), (1037 - 946) * 448 / 1080, places=3)

    def test_layout_measurements_are_the_broadcast_ones(self):
        bar = exact.MNF_BAR
        self.assertAlmostEqual(bar[2] - bar[0], 1041 / 3, places=1)
        self.assertLess(bar[1], exact.MNF_STRIP[1])
        self.assertLess(exact.MNF_STRIP[3], exact.MNF_PLATE[1])

    def test_probe_sizes_for_the_compact_profile(self):
        count, appendix, growth = resources.probe_sizes("mnf")
        self.assertEqual(count, 66)
        self.assertEqual(appendix, 66 * resources.RUNTIME_TEXTURE_SPAN)
        self.assertLess(count * 5376, 400_000)
        self.assertEqual(growth % 2048, 0)


class RetailFontTests(unittest.TestCase):
    def test_fonts_restyle_in_place_and_are_pinned(self):
        pack = _retail_pack_head()
        for slot in mnf_font.FONTS:
            at, size = mnf_font.pack_offset(slot), mnf_font.span_size(slot)
            span = pack[at:at + size]
            self.assertEqual(mnf_font.status(span, slot), "retail")
            new, receipt = mnf_font.apply(span, slot)
            self.assertEqual(len(new), len(span))
            self.assertEqual(new[:32], span[:32])
            self.assertEqual(receipt["painted"], "0123456789")
            self.assertEqual(mnf_font.status(new, slot), "applied")
            self.assertEqual(mnf_font.apply(new, slot)[1]["status"], "already_applied")
            corrupted = bytearray(new); corrupted[200] ^= 0x55
            self.assertEqual(mnf_font.status(bytes(corrupted), slot), "foreign")

    def test_runtime_scene_and_atlas_refit(self):
        pack = _retail_pack_head()
        from mod_editor.core import nfl2k5_scorebug_ingame as r
        rec = r.RESOURCES["score_bug"]
        if rec["pack_offset"] + rec["span_size"] > len(pack):
            with INDEX.open("rb") as stream:
                stream.seek(rec["pack_offset"]); span = stream.read(rec["span_size"])
        else:
            span = pack[rec["pack_offset"]:rec["pack_offset"] + rec["span_size"]]
        new, info = r.stage_binding_scene(span, runtime=True)
        self.assertTrue(info["wrapper_identical"])
        self.assertEqual(len(new), len(span))
        self.assertEqual(info["sha256"], r.digest(new))
        arec = r.RESOURCES["score_buga"]
        with INDEX.open("rb") as stream:
            stream.seek(arec["pack_offset"]); aspan = stream.read(arec["span_size"])
        anew, ainfo = r.encode_atlas(aspan, exact.atlas_mnf())
        self.assertTrue(ainfo["wrapper_identical"])
        self.assertEqual(len(anew), len(aspan))


if __name__ == "__main__":
    unittest.main()

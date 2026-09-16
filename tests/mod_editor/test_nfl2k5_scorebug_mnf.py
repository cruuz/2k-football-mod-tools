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

    def test_plate_table_is_indexed_by_asset_code(self):
        table = exact.plate_table()
        self.assertEqual(len(table), 40)
        from mod_editor.core.nfl2k5_scorebug_ingame import TEAM_LOGOS
        self.assertEqual(table[int(TEAM_LOGOS["KC"]["asset_code"])], exact.plate_argb("KC"))
        self.assertEqual(table[int(TEAM_LOGOS["DEN"]["asset_code"])], exact.plate_argb("DEN"))
        self.assertTrue(all(word >> 24 == 0xFF for word in table))
        # Near-black primaries use the explicit secondary-colour table.
        den = exact.plate_argb("DEN")
        self.assertEqual(den, 0xFFFB4F14)

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
    def test_painted_atlas_masks_and_shared_logo_cells(self):
        atlas=exact.atlas_mnf()
        self.assertEqual(atlas.size,(256,512))
        a,b,c,d=exact.MNF_REGIONS['ramp']
        self.assertEqual(atlas.getpixel((a,(b+d)//2))[:3],(255,255,255))
        self.assertGreater(atlas.getpixel((a,(b+d)//2))[3],atlas.getpixel((c-1,(b+d)//2))[3])
        for team in ('DEN','KC'):
            left,right=exact.mnf_panel(team,'away'),exact.mnf_panel(team,'home')
            self.assertEqual(left.size,(64,64))
            self.assertEqual(left.tobytes(),right.tobytes())
            self.assertIsNotNone(left.getchannel('A').getbbox())
        self.assertIsNone(exact.mnf_panel(None,'home').getchannel('A').getbbox())

    def test_painted_strips_use_only_the_intended_quads(self):
        from mod_editor.core import nfl2k5_scorebug_ingame as r
        rec=r.RESOURCES['score_bug']
        with INDEX.open('rb') as stream:
            stream.seek(rec['pack_offset']);span=stream.read(rec['span_size'])
        mesh=exact.mesh_mnf(r.pinned(span,rec))
        counts=[]
        for k,indices in r.layout.strips(mesh.buf):
            count=0
            for i in range(len(indices)-2):
                a,b,c=[mesh.pos[v] for v in indices[i:i+3]]
                if abs((b[0]-a[0])*(c[1]-a[1])-(c[0]-a[0])*(b[1]-a[1]))>1e-5:count+=1
            counts.append(count)
        self.assertEqual(counts,[2,2,2,6,3,2,2,2,2,2,2])

    def test_layout_measurements_are_the_broadcast_ones(self):
        bar = exact.MNF_BAR
        self.assertAlmostEqual(bar[2] - bar[0], 1041 / 3, places=1)
        self.assertLess(bar[1], exact.MNF_STRIP[1])
        self.assertLess(exact.MNF_STRIP[3], exact.MNF_PLATE[1])

    def test_probe_sizes_for_the_compact_profile(self):
        count, appendix, growth = resources.probe_sizes("mnf")
        self.assertEqual(count, 33)
        # 66 wing panels plus the two appended clock fonts (FirstPersonComic and core_bug).
        self.assertEqual(appendix, 32 * 5280 + 2208 + 132256 + resources.CLOCK_FONT_SPAN_SIZE)
        self.assertEqual(resources.CLOCK_FONT_SPAN_SIZE, 80160 + 27040)
        self.assertLess(appendix, 413_569)
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
        self.assertEqual((ainfo["width"],ainfo["height"]),(256,512))
        self.assertEqual(len(anew), resources.MNF_ATLAS_SPAN_SIZE)


if __name__ == "__main__":
    unittest.main()

"""Nameplate font_albedo/font_normal: base-only DXN (packed_mips=False)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import apf_xenos_dxn_mip_layout as dxn  # noqa: E402

_APF_ROOT = ROOT / "extracted" / "All-Pro Football 2K8 (USA)"


class DxnBaseOnlyLayoutTests(unittest.TestCase):
    def test_base_only_layout_matches_font_albedo_pins(self) -> None:
        # Real outer 114 font_albedo pins (no retail bytes).
        meta = {
            "format": 49,
            "endianness": 1,
            "tiled": True,
            "stacked": False,
            "dimension": 1,
            "mip_min_level": 0,
            "packed_mips": False,
            "mip_max_level": 0,
            "mip_address_pages": 0,
            "vc_mip_data_length": 0,
            "width": 1681,
            "height": 128,
            "pitch_pixels": 1792,
            "vc_base_data_length": 229376,
        }
        locations = dxn.derive_layout(meta)
        self.assertEqual(len(locations), 1)
        loc = locations[0]
        self.assertEqual(loc.level, 0)
        self.assertEqual(loc.width, 1681)
        self.assertEqual(loc.height, 128)
        self.assertEqual(loc.allocation_length, 229376)
        self.assertFalse(loc.packed_tail)

    def test_helmet_class_still_requires_packed_mips(self) -> None:
        meta = {
            "format": 49,
            "endianness": 1,
            "tiled": True,
            "stacked": False,
            "dimension": 1,
            "mip_min_level": 0,
            "packed_mips": False,
            "mip_max_level": 6,  # not base-only
            "mip_address_pages": 0,
            "vc_mip_data_length": 0,
            "width": 256,
            "height": 1024,
            "pitch_pixels": 256,
            "vc_base_data_length": 262144,
        }
        with self.assertRaises(dxn.MipLayoutError) as ctx:
            dxn.derive_layout(meta)
        self.assertIn("packed_mips", str(ctx.exception))


@unittest.skipUnless(
    (_APF_ROOT / "0A").is_file(), "APF extracted 0A dump not present"
)
class RealApfNameFontPreviewTests(unittest.TestCase):
    """Real-dump: all font_albedo + font_normal previews succeed."""

    @classmethod
    def setUpClass(cls) -> None:
        from mod_editor.apf_studio.facade import ApfStudioFacade

        cls.fac = ApfStudioFacade()
        cls.cat = cls.fac.load_source(_APF_ROOT)

    def test_all_namefont_textures_preview(self) -> None:
        from PIL import Image

        fonts = [
            a
            for a in self.cat.assets
            if a.name in ("font_albedo", "font_normal") and a.type_name == "TXTR"
        ]
        self.assertGreaterEqual(len(fonts), 20)
        for asset in fonts:
            path = self.fac.preview_asset(asset.asset_id)
            im = Image.open(path)
            self.assertEqual(im.mode, "RGBA", msg=asset.asset_id)
            self.assertEqual(im.height, 128, msg=asset.asset_id)
            self.assertGreater(im.width, 1000, msg=asset.asset_id)
            # DXN decode pins B=0 A=255
            extrema = im.getextrema()
            self.assertEqual(extrema[2], (0, 0), msg=f"B channel {asset.asset_id}")
            self.assertEqual(extrema[3], (255, 255), msg=f"A channel {asset.asset_id}")

    def test_namefont_outer_ids_documented(self) -> None:
        # Pin community-facing asset IDs for wall docs / Discord replies.
        outers = sorted(
            {
                a.outer_index
                for a in self.cat.assets
                if a.type_name == "NameFont"
            }
        )
        self.assertEqual(
            outers,
            [114, 283, 504, 538, 609, 640, 937, 956, 963, 1312, 1383],
        )


if __name__ == "__main__":
    unittest.main()

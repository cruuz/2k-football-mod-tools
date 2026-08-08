"""General DXT5A preview (not only digital_font 128×128)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import apf_xenos_dxt5a as dxt5a  # noqa: E402

_APF_ROOT = ROOT / "extracted" / "All-Pro Football 2K8 (USA)"


class Dxt5aGeneralUnitTests(unittest.TestCase):
    def test_digital_font_path_still_requires_8192(self) -> None:
        with self.assertRaises(dxt5a.DXT5AError):
            dxt5a.extract_linear(b"\0" * 100)


@unittest.skipUnless((_APF_ROOT / "0A").is_file(), "APF 0A dump not present")
class RealDxt5aGeneralPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from mod_editor.apf_studio.facade import ApfStudioFacade

        cls.fac = ApfStudioFacade()
        cls.cat = cls.fac.load_source(_APF_ROOT)

    def test_non_font_dxt5a_previews(self) -> None:
        from PIL import Image

        for name, size in (
            ("coach_hair_occlusion", (512, 512)),
            ("field_radiance", (256, 256)),
        ):
            asset = next(a for a in self.cat.assets if a.name == name)
            path = self.fac.preview_asset(asset.asset_id)
            image = Image.open(path)
            self.assertEqual(image.size, size, msg=name)
            self.assertEqual(image.mode, "RGBA")

    def test_digital_font_still_previews(self) -> None:
        from PIL import Image

        path = self.fac.preview_digital_font()
        image = Image.open(path)
        self.assertEqual(image.size, (128, 128))


if __name__ == "__main__":
    unittest.main()

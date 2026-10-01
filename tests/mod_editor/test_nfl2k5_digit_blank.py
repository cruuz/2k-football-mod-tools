"""A deliberately blank number cell (a kit without sleeve or helmet numbers): fully transparent art is accepted
as a blank digit, while art whose faint alpha the cleanup removes is still refused. Synthetic images only."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from PIL import Image  # noqa: E402
from mod_editor.core import nfl2k5_digit_art as art  # noqa: E402
from mod_editor.core.errors import ValidationError  # noqa: E402


def reference(size: int = 32) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    image.paste((255, 255, 255, 255), (8, 4, 24, 28))
    return image


class BlankDigitTest(unittest.TestCase):
    def test_fully_transparent_art_is_a_blank_digit(self):
        prepared, receipt = art.prepare_digit(Image.new("RGBA", (32, 32), (0, 40, 120, 0)), reference())
        self.assertIsNone(prepared.getchannel("A").getbbox())
        self.assertTrue(receipt["registration"]["blank"])
        self.assertTrue(receipt["cleanup"]["blank"])

    def test_faint_alpha_removed_by_cleanup_is_still_refused(self):
        faint = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        faint.paste((255, 255, 255, 1), (10, 10, 12, 12))
        with self.assertRaises(ValidationError):
            art.prepare_digit(faint, reference())


if __name__ == "__main__":
    unittest.main()

"""The XBE boot logo stays decodable when caves take its bitmap, and disc names end in .iso."""

from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_boot_logo as logo  # noqa: E402

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "default.xbe"


class LogoFormatTests(unittest.TestCase):
    def test_the_retail_bitmap_is_the_100_by_17_logo(self) -> None:
        self.assertEqual(logo.decode_pixels(logo.RETAIL_LOGO), (1700, 0))

    def test_code_in_the_bitmap_does_not_decode(self) -> None:
        pixels, bad = logo.decode_pixels(bytes.fromhex("e87b810300a18002e6003b433875168b") * 40)
        self.assertNotEqual(pixels, 1700)


class TargetNameTests(unittest.TestCase):
    def test_bare_names_get_a_disc_suffix(self) -> None:
        self.assertEqual(mod_build.image_target_path("ESPN NFL 2K5 (modded)"), "ESPN NFL 2K5 (modded).xiso.iso")
        self.assertEqual(mod_build.image_target_path("/tmp/out/game"), "/tmp/out/game.xiso.iso")
        self.assertEqual(mod_build.image_target_path("game.xiso.iso"), "game.xiso.iso")
        self.assertEqual(mod_build.image_target_path("game.ISO"), "game.ISO")
        self.assertEqual(mod_build.image_target_path("game.img"), "game.img")
        self.assertEqual(mod_build.image_target_path("   "), "")


@unittest.skipUnless(XBE.is_file(), "retail extraction not present")
class RelocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = XBE.read_bytes()

    def test_retail_status_and_padding(self) -> None:
        self.assertEqual(logo.status(self.retail), "retail")
        self.assertTrue(logo.bitmap_is_retail(self.retail))
        self.assertFalse(logo.needed(self.retail))
        self.assertFalse(any(self.retail[logo.NEW_LOGO_VA - logo.BASE: logo.NEW_LOGO_VA - logo.BASE + logo.LOGO_SIZE]))

    def test_relocation_keeps_the_logo_decodable_and_is_idempotent(self) -> None:
        taken = bytearray(self.retail)
        taken[0xA10:0xA10 + 64] = bytes.fromhex("e87b810300a18002e6003b433875168b") * 4     # a cave in the bitmap
        taken = bytes(taken)
        self.assertTrue(logo.needed(taken))
        out, receipt = logo.apply(taken)
        self.assertEqual(logo.status(out), "applied")
        addr, size, headers = struct.unpack_from("<III", out, 0x170)[0], struct.unpack_from("<I", out, 0x174)[0], struct.unpack_from("<I", out, 0x108)[0]
        self.assertEqual((addr, size, headers), (logo.NEW_LOGO_VA, 690, 0xF82))
        self.assertEqual(logo.decode_pixels(out[addr - logo.BASE: addr - logo.BASE + size]), (1700, 0))
        self.assertEqual(out[0xA10:0xA10 + 64], taken[0xA10:0xA10 + 64])         # the cave is untouched
        self.assertEqual(out[0x1000:], taken[0x1000:])                             # nothing outside the header page
        again, receipt2 = logo.apply(out)
        self.assertEqual(again, out)
        self.assertTrue(receipt2.get("already_applied"))

    def test_a_tampered_header_is_refused(self) -> None:
        bad = bytearray(self.retail)
        struct.pack_into("<I", bad, 0x174, 12)
        self.assertEqual(logo.status(bytes(bad)), "foreign")
        with self.assertRaises(logo.BootLogoError):
            logo.apply(bytes(bad))

    def test_the_patch_pipeline_relocates_only_when_a_cave_took_the_bitmap(self) -> None:
        from mod_editor.core import nfl2k5_throw_tuning as tt
        patched, receipt = tt._apply_all(self.retail, None, catch_slider=True, draft_ai=True)
        self.assertEqual(receipt["boot_logo"]["status"], "applied")
        self.assertEqual(logo.status(patched), "applied")
        addr = struct.unpack_from("<I", patched, 0x170)[0]
        self.assertEqual(logo.decode_pixels(patched[addr - logo.BASE: addr - logo.BASE + 690]), (1700, 0))
        untouched, receipt = tt._apply_all(self.retail, None, catch_slider=False, returner_fix=True)
        self.assertEqual(receipt["boot_logo"]["status"], "retail")
        self.assertEqual(logo.status(untouched), "retail")
        twice, _r = tt._apply_all(patched, None, catch_slider=True, draft_ai=True)
        self.assertEqual(twice, patched)


if __name__ == "__main__":
    unittest.main()

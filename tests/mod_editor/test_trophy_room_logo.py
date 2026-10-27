"""b778-pg2: the authored TROPHY ROOM logo and its Crib texture edit.

The PNG is a 128x128 RGBA emblem for ``crib_external_texture:7:logo``. The project JSON is a
one-edit visual-mod project for the existing Crib standalone texture writer. When the private
retail source pack is available, the writer must fit the new pixels into the same 18,176-byte fixed
P8 TXTR allocation and return a preview.
"""

from __future__ import annotations

import json
import struct
import sys
import unittest
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core.nfl2k5_crib_standalone_texture_writer import (  # noqa: E402
    build_unified_crib_standalone_texture_imports,
)

LOGO = ROOT / "data/trophy_room_logo/logo.png"
PROJECT = ROOT / "data/trophy_room_logo/project.json"
SELECTOR = "crib_external_texture:7:logo"
PRIVATE_ROOT = Path(os.environ.get("NFL2K5_STUDIO_PRIVATE_ROOT", "/nonexistent"))


class TrophyRoomLogoTests(unittest.TestCase):
    def test_png_is_a_128_rgba_emblem(self):
        raw = LOGO.read_bytes()
        self.assertEqual(raw[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", raw[16:24])
        depth, colour = raw[24], raw[25]
        self.assertEqual((width, height, depth, colour), (128, 128, 8, 6))
        self.assertLess(len(raw), 32 * 1024 * 1024)
        # the PNG keeps an alpha channel; the transparent background is authored in the image

    def test_project_names_the_crib_logo_and_relative_png(self):
        doc = json.loads(PROJECT.read_text(encoding="utf-8"))
        self.assertEqual(doc["schema"], "nfl2k5_visual_mod_project/v1")
        self.assertEqual(len(doc["edits"]), 1)
        edit = doc["edits"][0]
        self.assertEqual(edit["kind"], "crib_standalone_texture")
        self.assertEqual(edit["selector"], SELECTOR)
        self.assertFalse(Path(edit["png"]).is_absolute())
        self.assertTrue((PROJECT.parent / edit["png"]).is_file())

    def test_writer_fits_the_fixed_p8_span(self):
        packs = tuple(PRIVATE_ROOT.glob("extracted/*/vc_53450030/0"))
        if len(packs) != 1:
            self.skipTest("the private retail Crib source pack is unavailable")
        built = build_unified_crib_standalone_texture_imports(packs[0], SELECTOR, LOGO)
        self.assertEqual(len(built), 1)
        replacement, previews, report, selector, target = built[0]
        self.assertEqual(selector, SELECTOR)
        self.assertEqual(len(replacement), 18176)
        self.assertEqual(report["target"]["selector"], SELECTOR)
        self.assertEqual(target["format"], "P8")
        self.assertEqual((target["width"], target["height"]), (128, 128))
        self.assertEqual(target["mip_levels"], 5)
        self.assertEqual(target["span_size"], 18176)
        self.assertEqual(target["pack_offset"], 169447936)
        self.assertTrue(report["claims"]["fixed_txtr_allocation_only"])
        self.assertLessEqual(report["replacement"]["palette_entries"], 256)
        self.assertTrue(previews[0][1].startswith(b"\x89PNG\r\n\x1a\n"))


if __name__ == "__main__":
    unittest.main()

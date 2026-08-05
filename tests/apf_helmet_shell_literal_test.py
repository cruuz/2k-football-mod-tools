"""Focused gates for the native-material (literal BC1) shell bake.

The literal lane repaints the retail helmet_color texture with literal RGB so
the shell material (DXN normal + specular lightmap) shades the crest natively.
These gates pin the opaque-body contract, the weight-to-literal compositing,
and the fail-closed source/structure checks of the writer.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import apf_helmet_crest_wrap_patch as wrap  # noqa: E402
import apf_helmet_shell_literal_patch as literal  # noqa: E402

INDEX = ROOT / "extracted/All-Pro Football 2K8 (USA)/0A"
RETAIL_AVAILABLE = INDEX.is_file()

CANVAS = 512 * 512


def synthetic_mask() -> bytearray:
    mask = bytearray(bytes((0, 0, 0, 255)) * CANVAS)
    base = (256 * 512 + 256) * 4
    mask[base : base + 4] = bytes((255, 0, 0, 255))    # light ink
    mask[base + 4 : base + 8] = bytes((0, 255, 0, 255))  # dark ink
    mask[base + 8 : base + 12] = bytes((136, 0, 0, 255))  # AA fringe weight
    return mask


class LiteralConversionTest(unittest.TestCase):
    def test_body_is_opaque_shell_color(self) -> None:
        out = wrap.literal_rgba_from_region_mask(synthetic_mask())
        self.assertEqual(len(out), CANVAS * 4)
        body = wrap.shell_color_rgba(wrap.DEFAULT_SHELL_COLOR_ARGB)
        self.assertEqual(out[:4], body)
        for offset in range(3, len(out), 4):
            self.assertEqual(out[offset], 255)

    def test_inks_composite_over_shell(self) -> None:
        out = wrap.literal_rgba_from_region_mask(synthetic_mask())
        base = (256 * 512 + 256) * 4
        self.assertEqual(tuple(out[base : base + 4]), (255, 255, 255, 255))
        self.assertEqual(tuple(out[base + 4 : base + 8]), (192, 192, 192, 255))
        fringe = tuple(out[base + 8 : base + 11])
        self.assertTrue(
            wrap.shell_color_rgba(wrap.DEFAULT_SHELL_COLOR_ARGB)[:3]
            != fringe != (255, 255, 255)
        )

    def test_transparent_literal_refused(self) -> None:
        bad = bytearray(bytes((0, 0, 0, 136)) * CANVAS)
        with self.assertRaises(wrap.PatchError):
            wrap._require_opaque_literal(bytes(bad), "test literal")


@unittest.skipUnless(RETAIL_AVAILABLE, "retail APF 0A not present")
class LiteralBakeRetailTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mask = bytes(synthetic_mask())
        cls.lit = wrap.literal_rgba_from_region_mask(cls.mask)

    def test_atlas_literal_opaque_with_art(self) -> None:
        system = wrap.read_source_outer(INDEX)
        parsed = wrap._parse_outer(system, source=True)
        atlas, report = wrap.bake_shell_atlas_literal(parsed.system, self.lit)
        self.assertEqual(report["schema"], wrap.LITERAL_SCHEMA)
        self.assertGreater(report["literal_art_texels"], 0)
        for offset in range(3, len(atlas), 4):
            self.assertEqual(atlas[offset], 255)

    def test_build_patch_rewrites_only_the_helmet_entry(self) -> None:
        result = literal.build_patch(INDEX, self.lit, 1)
        self.assertEqual(result.manifest["schema"], literal.SCHEMA)
        self.assertTrue(result.entry_bytes)

    def test_build_patch_refuses_transparent_literal(self) -> None:
        bad = bytes(bytes((0, 0, 0, 136)) * CANVAS)
        with self.assertRaises(Exception):
            literal.build_patch(INDEX, bad, 1)


if __name__ == "__main__":
    unittest.main()

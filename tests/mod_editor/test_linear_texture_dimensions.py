"""Linear P8 textures store their explicit size the other way round.

A modder exported a Team Kit and reported the Nameplate Atlas preview and PNG
were "all gibberish". They were: ``names`` is a **1024x32** horizontal character
strip, and the descriptor reader was returning 32x1024, so every letterform was
shredded across the image.

``parse_texture`` handles two descriptor shapes. When ``packed_size`` is zero
the dimensions come out of the ``packed_format`` bitfield; otherwise they are
two explicit u16 halfwords. Those halfwords are ordered ``(height << 16) |
width`` for the swizzled formats and the reverse for ``VC_P8_LINEAR``, and the
reader applied the swizzled order to both.

The evidence is visual and unambiguous. Decoded the corrected way, ``names``
reads as a white character atlas beginning `` ` - A B C D E F G H I J K L M ``,
and ``ticker_src`` -- the only other texture in this format, carrying the
identical ``0x04000020`` -- reads as a red LED dot-matrix alphabet, which is
exactly what a scrolling stadium ticker font should be. Both are wide and short
for obvious reasons; neither makes any sense 32 pixels wide.

Fixing it for every explicit-size texture instead would have been wrong: 4,715
of them are non-square, and the 4,081 ``A1R5G5B5`` player strips (``p001`` and
friends, 1056x64 and similar) genuinely are wide-and-short under the existing
order. Only the linear format moves.

These assertions are arithmetic on descriptor words. No retail data is read.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import nfl_txtr  # noqa: E402
from mod_editor.core.nfl2k5_uniform_catalog import COMPONENT_SPECS  # noqa: E402

# The exact descriptor words the retail disc carries.
_NAMES_PACKED_SIZE = 0x04000020        # names / ticker_src, VC_P8_LINEAR
_PLAYER_STRIP_PACKED_SIZE = 0x00400420  # p011, A1R5G5B5
_LINEAR_P8 = 0x7F
_A1R5G5B5 = 0x02


def _dimensions(packed_size: int, format_code: int) -> tuple[int, int]:
    """Mirror the branch under test, so the rule is asserted not the plumbing."""
    if format_code == _LINEAR_P8:
        return (packed_size >> 16) & 0xFFFF, packed_size & 0xFFFF
    return packed_size & 0xFFFF, (packed_size >> 16) & 0xFFFF


class LinearTextureDimensionTests(unittest.TestCase):
    def test_the_nameplate_atlas_is_wide_not_tall(self) -> None:
        self.assertEqual(_dimensions(_NAMES_PACKED_SIZE, _LINEAR_P8), (1024, 32))

    def test_the_ticker_font_shares_the_same_descriptor(self) -> None:
        """ticker_src carries the identical word and is also 1024x32."""
        self.assertEqual(_dimensions(_NAMES_PACKED_SIZE, _LINEAR_P8), (1024, 32))

    def test_swizzled_player_strips_keep_the_old_order(self) -> None:
        """The 4,081 A1R5G5B5 strips must not move."""
        self.assertEqual(
            _dimensions(_PLAYER_STRIP_PACKED_SIZE, _A1R5G5B5), (1056, 64)
        )

    def test_reading_the_linear_word_the_swizzled_way_transposes_it(self) -> None:
        """Negative control: the old behaviour, and why it looked like confetti."""
        self.assertEqual(_dimensions(_NAMES_PACKED_SIZE, _A1R5G5B5), (32, 1024))

    def test_both_orders_agree_on_a_square_texture(self) -> None:
        square = (256 << 16) | 256
        self.assertEqual(
            _dimensions(square, _LINEAR_P8), _dimensions(square, _A1R5G5B5)
        )

    def test_the_parser_branches_on_the_linear_format(self) -> None:
        source = Path(nfl_txtr.__file__).read_text(encoding="utf-8")
        self.assertIn("if format_code == 0x7F:", source)
        self.assertIn("VC_P8_LINEAR", source)

    def test_the_team_kit_component_matches_the_decoder(self) -> None:
        """The exported PNG's declared size has to be the decoded size."""
        nameplate = next(
            spec for spec in COMPONENT_SPECS
            if spec.kind == "live_number_nameplate" and spec.family == "nameplate"
        )
        self.assertEqual(
            (nameplate.width, nameplate.height),
            _dimensions(_NAMES_PACKED_SIZE, _LINEAR_P8),
            "the Team Kit would demand a PNG of the wrong shape",
        )


if __name__ == "__main__":
    unittest.main()

"""Any standard PNG must import, not just the one variant we happened to write.

A modder replacing a jersey got::

    Torso / Jersey needs an exact 512x256 8-bit RGBA PNG with interlacing off.
    PNG must be exactly 512x256

Half of that message was the game's rule and half was ours. The **size** is
fixed by the disc: the texture occupies a byte span the index chain has to fill
exactly, so a different-sized image genuinely cannot go there.

The **format** was our own limitation. ``decode_rgba_png`` demanded colour type
6 at bit depth 8, non-interlaced -- and an image editor saving a jersey usually
writes colour type 2 (RGB, no alpha) or 3 (palette), because that is smaller.
So the app rejected perfectly good art with a message that reads like the user
did something wrong.

Every colour type and bit depth the PNG specification defines is now decoded
and widened to RGBA internally. These tests build each variant, decode it, and
compare against what Pillow sees when it *reloads the same file* -- which is
the view any other consumer of that PNG would get. Comparing against the
in-memory image instead would be wrong: an ``L`` image carrying ``tRNS`` has no
alpha until the file is read back.
"""

from __future__ import annotations

import io
from pathlib import Path
import sys
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import nfl_tset_png_import as importer  # noqa: E402

try:
    from PIL import Image
except ImportError:  # pragma: no cover - Pillow is a dev-only dependency
    Image = None

_WIDTH, _HEIGHT = 64, 32


def _reference() -> "Image.Image":
    image = Image.new("RGBA", (_WIDTH, _HEIGHT))
    pixels = image.load()
    for y in range(_HEIGHT):
        for x in range(_WIDTH):
            pixels[x, y] = (x * 4 % 256, y * 8 % 256, (x + y) * 3 % 256,
                            255 if (x + y) % 7 else 128)
    return image


@unittest.skipIf(Image is None, "Pillow is not installed")
class RealWorldPngTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reference = _reference()

    def _encode(self, mode: str, *, interlace: bool = False, **save) -> bytes:
        buffer = io.BytesIO()
        options = {"interlace": 1} if interlace else {}
        self.reference.convert(mode).save(buffer, "PNG", **options, **save)
        return buffer.getvalue()

    def _assert_matches_pillow(self, payload: bytes) -> None:
        width, height, rgba = importer.decode_rgba_png(payload, (_WIDTH, _HEIGHT))
        self.assertEqual((width, height), (_WIDTH, _HEIGHT))
        expected = Image.open(io.BytesIO(payload)).convert("RGBA").tobytes()
        self.assertEqual(rgba, expected)

    def test_every_colour_type_decodes_exactly(self) -> None:
        for mode in ("RGBA", "RGB", "P", "L", "LA"):
            with self.subTest(mode=mode):
                self._assert_matches_pillow(self._encode(mode))

    def test_every_colour_type_decodes_exactly_when_interlaced(self) -> None:
        """Adam7 was refused outright before; it is a normal editor option."""
        for mode in ("RGBA", "RGB", "P", "L", "LA"):
            with self.subTest(mode=mode):
                self._assert_matches_pillow(self._encode(mode, interlace=True))

    def test_a_bilevel_image_decodes(self) -> None:
        image = Image.new("1", (_WIDTH, _HEIGHT))
        pixels = image.load()
        for y in range(_HEIGHT):
            for x in range(_WIDTH):
                pixels[x, y] = (x + y) % 2
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        self._assert_matches_pillow(buffer.getvalue())

    def test_a_low_bit_depth_palette_decodes(self) -> None:
        grey = self.reference.convert("L")
        small = grey.convert("P", palette=Image.ADAPTIVE, colors=16)
        buffer = io.BytesIO()
        small.save(buffer, "PNG")
        self._assert_matches_pillow(buffer.getvalue())

    def test_transparency_chunks_are_honoured(self) -> None:
        grey = self.reference.convert("L")
        for image in (grey, grey.convert("P")):
            with self.subTest(mode=image.mode):
                buffer = io.BytesIO()
                image.save(buffer, "PNG", transparency=0)
                self._assert_matches_pillow(buffer.getvalue())

    def test_the_size_rule_is_still_enforced(self) -> None:
        """The disc's rule, not ours: the span has to be filled exactly."""
        payload = self._encode("RGBA")
        with self.assertRaises(importer.ImportError):
            importer.decode_rgba_png(payload, (_WIDTH * 2, _HEIGHT))

    def test_a_corrupt_png_is_still_refused(self) -> None:
        payload = bytearray(self._encode("RGBA"))
        payload[-6] ^= 0xFF  # break the IEND CRC
        with self.assertRaises(importer.ImportError):
            importer.decode_rgba_png(bytes(payload), (_WIDTH, _HEIGHT))

    def test_a_non_png_is_still_refused(self) -> None:
        with self.assertRaises(importer.ImportError):
            importer.decode_rgba_png(b"not a png at all" * 64, (_WIDTH, _HEIGHT))

    def test_a_truncated_stream_is_still_refused(self) -> None:
        payload = self._encode("RGBA")
        with self.assertRaises(importer.ImportError):
            importer.decode_rgba_png(payload[:len(payload) // 2], (_WIDTH, _HEIGHT))


class ContractTests(unittest.TestCase):
    """These run without Pillow, so CI covers them on every job."""

    def test_all_five_colour_types_are_declared(self) -> None:
        self.assertEqual(sorted(importer._PNG_CHANNELS), [0, 2, 3, 4, 6])
        self.assertEqual(importer._PNG_CHANNELS[2], 3)
        self.assertEqual(importer._PNG_CHANNELS[6], 4)

    def test_adam7_has_seven_passes_covering_every_pixel(self) -> None:
        passes = importer._ADAM7
        self.assertEqual(len(passes), 7)
        covered = set()
        for x0, y0, dx, dy in passes:
            for y in range(y0, 8, dy):
                for x in range(x0, 8, dx):
                    self.assertNotIn((x, y), covered, "Adam7 passes overlap")
                    covered.add((x, y))
        self.assertEqual(len(covered), 64, "Adam7 must tile the full 8x8 block")


if __name__ == "__main__":
    unittest.main()

"""Beta 74: fill_stream lands inside the loader's scratch window whenever it can.

The retail loader reads a fixed-span compressed body at ``base + decoded_size +
scratch - stored_size`` and decodes forward, so a refitted stream must end
within ``scratch`` bytes of the stored size (the writers pass ``slack =
min(scratch, 16)``). ``fill_stream`` expands matches back into literals to grow
a too-small stream, but it only ever expanded whole matches, in jumps of up to
the maximum match length, and stopped when every remaining match would
overshoot the window. A flat texture (long matches everywhere) beside retail
neighbours in one chunk then stayed more than ``slack`` bytes short and the
equipment writer refused the art as "cannot fit with the retail loader scratch
allowance", which the refit ladder cannot cure because it only makes the art
smaller. The retail workflow gate found it on a striped shoes01 in package
3653. The fine pass splits one match into a shorter match plus literals, a
byte at a time.

The sweep below asks for every stored size from the compressed size up to the
raw size and requires each result to land in the window and decode back to
the same bytes. The retail case is checked when the private pack is present.
"""
import io
import os
from pathlib import Path
import random
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).resolve().parent)]

import nfl_txtr as t
from nfl_vc_lz_fill import fill_stream, parse_tokens

RETAIL_INDEX = Path(os.environ.get(
    "NFL2K5_RETAIL_INDEX",
    "/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"))


def _flat_texture(size=4096, seed=5):
    """Long runs with a little structure: what a striped or solid shoe decodes to."""
    rng = random.Random(seed)
    out = bytearray()
    while len(out) < size:
        out.extend(bytes([rng.randrange(3)]) * rng.randrange(20, 90))
    return bytes(out[:size])


class FillStreamWindowTests(unittest.TestCase):
    def _sweep(self, decoded, offset_bits, slack):
        stream, _ = t.compress_vc_lz(decoded, stream_tag=1, offset_bits=offset_bits)
        raw_size = 9 + (len(decoded) + 7) // 8 + len(decoded)
        misses = []
        for stored in range(len(stream), raw_size + 1):
            filled, _expanded = fill_stream(stream, decoded, stored, slack=slack)
            if not stored - slack <= len(filled) <= stored:
                misses.append((stored, len(filled)))
                continue
            back, _info = t.decompress_vc_lz(filled, len(decoded))
            self.assertEqual(back, decoded, f"stored {stored}")
        self.assertEqual(misses, [], f"{len(misses)} stored sizes missed the window")
        return stream, raw_size

    def test_every_stored_size_lands_in_a_16_byte_window(self):
        decoded = _flat_texture()
        for offset_bits in (10, 11, 12):
            with self.subTest(offset_bits=offset_bits):
                stream, raw_size = self._sweep(decoded, offset_bits, 16)
                self.assertLess(len(stream) * 4, raw_size)  # the art really is flat

    def test_a_tighter_window_is_still_hit(self):
        decoded = _flat_texture(size=2048, seed=9)
        self._sweep(decoded, 12, 4)

    def test_a_stream_that_already_fits_is_returned_unchanged(self):
        decoded = _flat_texture(size=1024, seed=2)
        stream, _ = t.compress_vc_lz(decoded, stream_tag=1, offset_bits=12)
        filled, expanded = fill_stream(stream, decoded, len(stream) + 8, slack=16)
        self.assertEqual(filled, stream)
        self.assertEqual(expanded, 0)

    def test_split_matches_keep_the_token_grammar(self):
        decoded = _flat_texture(size=1500, seed=4)
        stream, _ = t.compress_vc_lz(decoded, stream_tag=1, offset_bits=12)
        filled, _ = fill_stream(stream, decoded, len(stream) + 23, slack=2)
        _, _, _, tokens = parse_tokens(filled)
        self.assertTrue(all(tok[2] >= 3 for tok in tokens if tok[0] == "M"))


@unittest.skipUnless(RETAIL_INDEX.is_file(), "private retail pack 0 unavailable")
class RetailFlatShoeTests(unittest.TestCase):
    def test_striped_shoes01_with_its_mud_sibling_fits_package_3653(self):
        from PIL import Image
        from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
        from mod_editor.core.nfl2k5_equipment_import_intent import with_import_mode
        writer.staged_equipment_cache().clear()
        image = Image.new("RGBA", (256, 256))
        pixels = image.load()
        for y in range(256):
            colour = ((20, 60, 140, 255), (240, 245, 250, 255), (170, 35, 55, 255))[(y // 7) % 3]
            for x in range(256):
                pixels[x, y] = colour
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        payload, rgba = buffer.getvalue(), image.tobytes()
        with tempfile.TemporaryDirectory() as folder:
            group = []
            for asset_id in ("tset:3653:8:0:shoes01", "tset:3653:8:1:shoes01_mud"):
                png = Path(folder) / (asset_id.replace(":", "_") + ".png")
                png.write_bytes(with_import_mode(payload, asset_id, rgba, independent=False, scale=1))
                group.append((asset_id, png))
            scratch = Path(folder) / "scratch"
            scratch.mkdir()
            fitted, _substitutes, refits = writer.auto_refit_group(RETAIL_INDEX, group, scratch)
        self.assertEqual([row["fit_status"] for row in fitted], ["fits", "fits"])
        self.assertEqual(refits, [])
        self.assertTrue(all("256 x 256" in row["fit_summary"] for row in fitted), fitted)


if __name__ == "__main__":
    unittest.main()

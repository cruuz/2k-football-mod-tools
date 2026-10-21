"""The shared palette ladder treats a stream that fills its whole fixed span as no fit (fn1's native decoder model)."""
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
import nfl_tset_png_import as palette
from nfl_txtr import compress_vc_lz, decompress_vc_lz


def unsafe_exact_fill():
    """A payload whose VC-LZ stream, stored with no spare byte, ends on a full flag group (the retail decoder then
    fetches one more flag byte outside the span). Deterministic search."""
    rng = random.Random(5)
    for size in range(40, 400):
        for _trial in range(5):
            decoded = bytes(rng.choice(range(8)) for _ in range(size))
            compressed, _ = compress_vc_lz(decoded, stream_tag=1, offset_bits=12)
            if (not palette._native_decoder_safe(compressed, decoded, len(compressed))
                    and palette._native_decoder_safe(compressed, decoded, len(compressed) + 1)):
                return decoded, compressed
    raise AssertionError("no exact-fill example found")


class NativeSafeLadderTests(unittest.TestCase):
    def test_exact_fill_is_unsafe_and_one_spare_byte_is_safe(self):
        decoded, compressed = unsafe_exact_fill()
        self.assertFalse(palette._native_decoder_safe(compressed, decoded, len(compressed)))
        self.assertTrue(palette._native_decoder_safe(compressed, decoded, len(compressed) + 1))
        self.assertTrue(palette._native_decoder_safe(compressed, decoded, len(compressed) + 16))

    def test_the_ladder_steps_to_the_next_tier_instead_of_accepting_an_exact_fill(self):
        unsafe, compressed = unsafe_exact_fill()
        small = bytes(len(unsafe))                      # compresses far below the span
        payloads = {256: unsafe, 128: small}
        fit = palette.quantize_levels_to_vc_lz_bound(
            [object()], lambda colors, indices: payloads[len(colors)], stream_tag=1, offset_bits=12,
            max_encoded_size=len(compressed),
            quantizer=lambda levels, maximum: ([(0, 0, 0, 255)] * maximum, [b""], {}))
        self.assertEqual([row["result"] for row in fit.attempts], ["vc_lz_native_unsafe", "fit"])
        self.assertEqual(fit.attempts[-1]["maximum_palette_entries"], 128)
        self.assertEqual(fit.decoded, small)
        restored, info = decompress_vc_lz(fit.compressed, len(small))
        self.assertEqual(restored, small)

    def test_a_stream_with_a_spare_byte_is_accepted_at_the_first_tier(self):
        unsafe, compressed = unsafe_exact_fill()
        fit = palette.quantize_levels_to_vc_lz_bound(
            [object()], lambda colors, indices: unsafe, stream_tag=1, offset_bits=12,
            max_encoded_size=len(compressed) + 1,
            quantizer=lambda levels, maximum: ([(0, 0, 0, 255)] * maximum, [b""], {}))
        self.assertEqual([row["result"] for row in fit.attempts], ["fit"])
        self.assertEqual(fit.compressed, compressed)


if __name__ == "__main__":
    unittest.main()

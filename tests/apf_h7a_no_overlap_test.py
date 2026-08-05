#!/usr/bin/env python3
"""No APF H7A encoder may emit a match that overlaps its own output.

This is the bug that made modded APF textures come back as fine colour speckle
in game while every offline check passed.  An H7A match is a (distance, length)
back-reference.  When ``length > distance`` the run reads bytes it is still
writing -- the classic run-length idiom -- and a decoder that copies one byte at
a time reproduces it exactly.  Ours does, which is why ``decompress(compress(x))
== x`` never caught it.  The console's does not.

Retail settles what is allowed: the shipped 512x512 Americans crest VRAM block
contains 36,099 matches and not a single one overlaps, while a plain greedy
encoder over the identical bytes produces nearly eleven thousand, almost all at
distance 2.  So the rule is not a guess about the hardware, it is the discipline
the original compressor visibly kept.

Four separate encoders exist in this tree.  Fixing one and leaving the others
would leave jerseys, helmets, field art and fonts corrupting exactly the way
crests did, so all four are checked here.
"""

from __future__ import annotations

from pathlib import Path
import random
import sys
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import apf_inner  # noqa: E402
import apf_digital_font_transport  # noqa: E402
import apf_field_art_patch  # noqa: E402
import apf_logo_patch  # noqa: E402
import apf_texture_patch  # noqa: E402


ENCODERS = (
    ("apf_logo_patch", apf_logo_patch.compress_h7a),
    ("apf_field_art_patch", apf_field_art_patch.compress_h7a),
    ("apf_texture_patch", apf_texture_patch.compress_h7a),
    ("apf_digital_font_transport", apf_digital_font_transport.compress_h7a_bounded),
)

SHIFTS = (8, 9, 12)


def _samples() -> dict[str, bytes]:
    """Inputs chosen because they are what tempts an encoder to overlap.

    Flat fills and short cycles are exactly what a region-mask texture looks
    like, which is why crests tripped this and noisier art did not.
    """
    random.seed(7)
    return {
        "flat": bytes(4096),
        "two_byte_cycle": bytes([0xAB, 0xCD] * 2048),
        "three_byte_cycle": bytes([1, 2, 3] * 1400),
        "mask_like": bytes(([0x00] * 300 + [0xFF] * 300) * 8),
        "incompressible": bytes(random.randrange(256) for _ in range(4096)),
    }


def walk_matches(stream: bytes, shift: int):
    """Yield every (distance, length) back-reference in an H7A stream."""
    cursor = 0
    while cursor < len(stream):
        descriptor = stream[cursor]
        cursor += 1
        for bit in range(8):
            if cursor >= len(stream):
                return
            if descriptor >> bit & 1:
                if cursor + 2 > len(stream):
                    return
                word = (stream[cursor] << 8) | stream[cursor + 1]
                cursor += 2
                yield word & ((1 << shift) - 1), (word >> shift) + 3
            else:
                cursor += 1


class NoOverlappingMatchTests(unittest.TestCase):
    def test_no_encoder_emits_an_overlapping_match(self) -> None:
        for name, encode in ENCODERS:
            for label, data in _samples().items():
                for shift in SHIFTS:
                    with self.subTest(encoder=name, sample=label, shift=shift):
                        stream = encode(data, shift)
                        offenders = [
                            (distance, length)
                            for distance, length in walk_matches(stream, shift)
                            if length > distance
                        ]
                        self.assertEqual(
                            offenders[:5], [],
                            f"{name} emitted {len(offenders)} overlapping "
                            f"match(es) on {label} at shift {shift}",
                        )

    def test_every_encoder_still_round_trips(self) -> None:
        """The clamp must cost ratio, never correctness."""
        for name, encode in ENCODERS:
            for label, data in _samples().items():
                for shift in SHIFTS:
                    with self.subTest(encoder=name, sample=label, shift=shift):
                        stream = encode(data, shift)
                        self.assertEqual(
                            apf_inner.decompress_h7a(stream, len(data), shift),
                            data,
                        )

    def test_a_flat_region_still_compresses(self) -> None:
        """Guard against 'fixing' overlap by refusing to match at all."""
        data = bytes(4096)
        for name, encode in ENCODERS:
            with self.subTest(encoder=name):
                stream = encode(data, 9)
                self.assertLess(
                    len(stream), len(data) // 2,
                    f"{name} stopped compressing flat data",
                )


class RetailDisciplineTests(unittest.TestCase):
    def test_the_rule_matches_what_retail_shipped(self) -> None:
        """The pinned retail crest block, if the disc is available.

        Skipped rather than failed without the extracted volume, so the rule
        above still holds on machines that do not carry retail data.
        """
        volume = (_REPO_ROOT / "extracted" / "All-Pro Football 2K8 (USA)" / "0A")
        if not volume.exists():
            self.skipTest("retail 0A not extracted here")
        import apf_outer

        archive = apf_outer.parse_archive(volume)
        entry = archive.entries[1133]          # uniform_logo_30.iff, Americans
        with apf_inner.ArchiveReader(archive) as reader:
            record = apf_inner.parse_iff(reader, entry)
            block = record.blocks[1]           # the shared VRAM block
            stored = reader.read(entry, block.start_offset, block.compressed_length)
        matches = list(walk_matches(stored[16:], block.wrapper.shift))
        self.assertGreater(len(matches), 30_000)
        self.assertEqual(
            [(d, l) for d, l in matches if l > d], [],
            "retail itself emitted an overlapping match; the rule is wrong",
        )


if __name__ == "__main__":
    unittest.main()

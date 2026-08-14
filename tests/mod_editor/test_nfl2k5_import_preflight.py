"""Tell a user what a fixed slot will do to their art before the build does it.

Beta 41/42 replaced a hard build failure with a palette ladder: a replacement
that will not fit its fixed VC-LZ span is quantized down until it does. That is
lossy, and it shipped silent -- a user's jersey could lose 240 palette entries
with nothing said. Replacing a refusal with a quiet downgrade is not obviously
the better bargain unless the user is told which one happened.

This preflight runs the real quantizer and the real encoder against the real
slot contract, so for the modelled families it agrees with the importer by
construction, and it runs before the build rather than tens of seconds into it.
A family with no modelled contract is reported as unmodelled rather than
guessed at.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from mod_editor.core import nfl2k5_import_preflight as preflight


def _png(path: Path, width: int, height: int, colours: int) -> Path:
    """Write a PNG with a controlled number of distinct colours.

    Deliberately *noisy* rather than periodic. A tidy ``(x*7 + y*13)`` ramp has
    many colours but compresses to a fraction of its allocation, so it can only
    ever be "fits" or "impossible" -- it never exercises the middle of the
    ladder, which is the behaviour these tests exist to pin.
    """

    import random

    from PIL import Image

    rnd = random.Random(f"{width}x{height}:{colours}")
    palette = [
        (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256), 255)
        for _ in range(max(1, colours))
    ]
    image = Image.new("RGBA", (width, height))
    image.putdata([rnd.choice(palette) for _ in range(width * height)])
    image.save(path)
    return path


def _flat_png(path: Path, width: int, height: int, colours: int) -> Path:
    """Write a PNG of large flat blocks -- a team-colour jersey, in miniature."""

    from PIL import Image

    image = Image.new("RGBA", (width, height))
    pixels = image.load()
    band = max(1, height // max(1, colours))
    shades = [
        (40 + index * 50 % 216, 30 + index * 90 % 226, 60 + index * 30 % 196, 255)
        for index in range(max(1, colours))
    ]
    for y in range(height):
        colour = shades[min(y // band, len(shades) - 1)]
        for x in range(width):
            pixels[x, y] = colour
    image.save(path)
    return path


class ContractTests(unittest.TestCase):
    def test_the_modelled_families_match_their_importers(self) -> None:
        torso = preflight.CONTRACTS["torso"]
        self.assertEqual(torso.mip_dimensions[0], (512, 256))
        self.assertEqual(len(torso.mip_dimensions), 6)
        # 512x256 chain plus its five halvings, exactly what the importer pins.
        self.assertEqual(torso.index_chain_bytes, 174_720)
        # Two palettes: the jersey/pants TSETs carry clean and mud over one
        # shared index chain.
        self.assertEqual(torso.palette_count, 2)
        self.assertEqual(torso.decoded_bytes, 256 + 174_720 + 2048)

    def test_pants_and_sleeve_share_the_torso_shape(self) -> None:
        for kind in ("pants", "sleeve"):
            with self.subTest(kind=kind):
                self.assertEqual(
                    preflight.CONTRACTS[kind].decoded_bytes,
                    preflight.CONTRACTS["torso"].decoded_bytes,
                )

    def test_the_helmet_is_a_single_palette_family(self) -> None:
        helmet = preflight.CONTRACTS["live_helmet"]
        self.assertEqual(helmet.palette_count, 1)
        self.assertEqual(helmet.mip_dimensions[0], (256, 256))


class PredictionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="preflight-")
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.contract = preflight.CONTRACTS["torso"]

    def test_simple_art_fits_as_authored(self) -> None:
        # Large flat regions, not scattered noise: this is what a team-colour
        # jersey actually looks like, and it is the case that must never be
        # degraded. (Randomly *placed* colours blow up index entropy and the
        # mip chain blends new shades in, so even four scattered colours can
        # legitimately need a reduction -- see the busy case below.)
        png = _flat_png(self.root / "flat.png", 512, 256, 4)
        row = preflight.predict_slot(png, self.contract, 75_472, label="Flat")
        self.assertEqual(row.outcome, preflight.FULL)
        self.assertEqual(row.refused_tiers, ())
        self.assertFalse(row.needs_attention)
        self.assertIn("fits as authored", row.summary())
        self.assertGreater(row.headroom_bytes, 0)

    def test_busy_art_is_reported_as_reduced_with_the_number(self) -> None:
        png = _png(self.root / "busy.png", 512, 256, 250)
        row = preflight.predict_slot(png, self.contract, 40_000, label="Busy")
        self.assertEqual(row.outcome, preflight.REDUCED)
        self.assertTrue(row.needs_attention)
        self.assertTrue(row.refused_tiers)
        self.assertLess(row.palette_entries, row.source_colours)
        self.assertIn("reduced to", row.summary())
        self.assertIn("40,000-byte slot", row.summary())

    def test_an_impossible_slot_is_reported_as_refused(self) -> None:
        png = _png(self.root / "busy.png", 512, 256, 250)
        row = preflight.predict_slot(png, self.contract, 64, label="Tiny")
        self.assertEqual(row.outcome, preflight.REFUSED)
        self.assertTrue(row.needs_attention)
        self.assertIn("will not fit", row.summary())
        self.assertIn("gradients", row.detail)

    def test_a_prediction_never_claims_more_than_the_slot_allows(self) -> None:
        png = _png(self.root / "busy.png", 512, 256, 250)
        for allocation in (40_000, 60_000, 90_000):
            with self.subTest(allocation=allocation):
                row = preflight.predict_slot(
                    png, self.contract, allocation, label="Busy"
                )
                self.assertLessEqual(row.encoded_bytes, allocation)

    def test_an_unreadable_image_is_unmodelled_not_a_crash(self) -> None:
        broken = self.root / "broken.png"
        broken.write_bytes(b"not a png")
        row = preflight.predict_slot(broken, self.contract, 75_472, label="Broken")
        self.assertEqual(row.outcome, preflight.UNMODELLED)
        self.assertIn("could not be read", row.detail)


class BatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="preflight-batch-")
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def test_a_family_with_no_contract_is_reported_not_guessed(self) -> None:
        png = _png(self.root / "flat.png", 512, 256, 4)
        rows = preflight.predict_edits(
            [("a:1", "Some audio", "audo_audio", png, 0)]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].outcome, preflight.UNMODELLED)
        self.assertIsNone(rows[0].palette_entries)
        self.assertIn("no fixed-span prediction", rows[0].detail)

    def test_progress_is_reported_per_edit_and_completes(self) -> None:
        png = _png(self.root / "flat.png", 512, 256, 4)
        seen: list[tuple[str, int, int]] = []
        preflight.predict_edits(
            [("a:1", "One", "torso", png, 75_472),
             ("a:2", "Two", "audo_audio", png, 0)],
            progress=lambda message, done, total: seen.append((message, done, total)),
        )
        self.assertEqual(seen[0][1:], (0, 2))
        self.assertEqual(seen[-1][1:], (2, 2))

    def test_the_report_leads_with_what_blocks_the_build(self) -> None:
        busy = _png(self.root / "busy.png", 512, 256, 250)
        flat = _png(self.root / "flat.png", 512, 256, 4)
        rows = preflight.predict_edits([
            ("a:1", "Fine", "torso", flat, 75_472),
            ("a:2", "Lossy", "pants", busy, 40_000),
            ("a:3", "Impossible", "sleeve", busy, 64),
        ])
        text = preflight.report(rows)
        self.assertLess(text.index("will not fit"), text.index("lose colours"))
        self.assertIn("fit as authored", text)

    def test_an_empty_set_says_so(self) -> None:
        self.assertIn("nothing to check", preflight.report(()))


if __name__ == "__main__":
    unittest.main()

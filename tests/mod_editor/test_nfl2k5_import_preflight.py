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
import sys
import tempfile
import unittest

from mod_editor.core import nfl2k5_import_preflight as preflight

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import nfl_live_helmet_txtr_png_import as helmet_import  # noqa: E402
import nfl_pants_tset_png_import as pants_import  # noqa: E402
import nfl_sleeve_tset_png_import as sleeve_import  # noqa: E402
import nfl_tset_png_import as jersey_import  # noqa: E402


#: A deliberately tiny stand-in for a real slot.
#:
#: The ladder's cost is the mip chain and the VC-LZ encode, so exercising it
#: against the real 512x256 six-mip torso costs seconds per tier and minutes per
#: run. Every behaviour these tests pin -- fits, reduces, refuses, reports the
#: number -- is shape-independent, so they run against 128x64 and the *real*
#: contracts are pinned separately, by comparison against the importers that
#: own them.
SMALL = preflight.SlotContract("torso", 128, 64, 3, 256, 2)


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
    """Pin every contract against the importer that actually writes the slot.

    These assertions are derived from the importer modules rather than typed
    out, because a typed list is exactly how ``sleeve`` came to be modelled as a
    512x256 six-mip slot when the real one is 128x128 with five mips -- a 7x
    error that a hand-written expectation agreed with.
    """

    MODULES = {
        "torso": (jersey_import, 256, 2),
        "sleeve": (sleeve_import, 256, 2),
        "pants": (pants_import, 256, 2),
        "live_helmet": (helmet_import, 128, 1),
    }

    def test_every_contract_matches_its_importer(self) -> None:
        for kind, (module, system_bytes, palette_count) in self.MODULES.items():
            with self.subTest(kind=kind):
                contract = preflight.CONTRACTS[kind]
                self.assertEqual(contract.mip_dimensions,
                                 tuple(module.MIP_DIMENSIONS))
                self.assertEqual(contract.index_chain_bytes,
                                 module.INDEX_CHAIN_BYTES)
                self.assertEqual(contract.system_bytes, system_bytes)
                self.assertEqual(contract.palette_count, palette_count)
                # The importers all refuse a decoded payload that is not
                # exactly system_bytes + VIDEO_BYTES.
                self.assertEqual(contract.decoded_bytes,
                                 system_bytes + module.VIDEO_BYTES)

    def test_the_modelled_families_are_exactly_the_four_bounded_importers(self) -> None:
        self.assertEqual(set(preflight.CONTRACTS), set(self.MODULES))

    def test_the_sleeve_is_not_the_torso_shape(self) -> None:
        # The regression this file exists to prevent. Sleeves are a quarter-size
        # five-mip slot with a 64-byte gap between the clean and mud palettes;
        # predicting one against the torso contract is off by a factor of seven.
        sleeve = preflight.CONTRACTS["sleeve"]
        torso = preflight.CONTRACTS["torso"]
        self.assertEqual(sleeve.mip_dimensions[0], (128, 128))
        self.assertEqual(sleeve.mip_levels, 5)
        self.assertEqual(sleeve.interpalette_gap_bytes, 64)
        self.assertEqual(torso.interpalette_gap_bytes, 0)
        self.assertNotEqual(sleeve.decoded_bytes, torso.decoded_bytes)

    def test_pants_do_share_the_torso_shape(self) -> None:
        self.assertEqual(preflight.CONTRACTS["pants"].decoded_bytes,
                         preflight.CONTRACTS["torso"].decoded_bytes)

    def test_the_helmet_is_a_single_palette_family(self) -> None:
        helmet = preflight.CONTRACTS["live_helmet"]
        self.assertEqual(helmet.palette_count, 1)
        self.assertEqual(helmet.mip_dimensions[0], (256, 256))


class PredictionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="preflight-")
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.contract = SMALL

    def test_simple_art_fits_as_authored(self) -> None:
        # Large flat regions, not scattered noise: this is what a team-colour
        # jersey actually looks like, and it is the case that must never be
        # degraded. (Randomly *placed* colours blow up index entropy and the
        # mip chain blends new shades in, so even four scattered colours can
        # legitimately need a reduction -- see the busy case below.)
        png = _flat_png(self.root / "flat.png", 128, 64, 4)
        row = preflight.predict_slot(png, self.contract, 12_000, label="Flat")
        self.assertEqual(row.outcome, preflight.FULL)
        self.assertEqual(row.refused_tiers, ())
        self.assertFalse(row.needs_attention)
        self.assertIn("fits as authored", row.summary())
        self.assertGreater(row.headroom_bytes, 0)

    def test_busy_art_is_reported_as_reduced_with_the_number(self) -> None:
        png = _png(self.root / "busy.png", 128, 64, 250)
        row = preflight.predict_slot(png, self.contract, 8_000, label="Busy")
        self.assertEqual(row.outcome, preflight.REDUCED)
        self.assertTrue(row.needs_attention)
        self.assertTrue(row.refused_tiers)
        self.assertLess(row.palette_entries, row.source_colours)
        self.assertIn("reduced to", row.summary())
        self.assertIn("8,000-byte slot", row.summary())

    def test_the_reduced_detail_blames_shade_count_not_resolution(self) -> None:
        # The whole point of the copy: resizing a source image does not buy
        # back palette, because the editor resizes to the slot either way.
        png = _png(self.root / "busy.png", 128, 64, 250)
        row = preflight.predict_slot(png, self.contract, 8_000, label="Busy")
        self.assertIn("Distinct shade count", row.detail)
        self.assertIn("not", row.detail)
        self.assertIn("resolution", row.detail)

    def test_an_impossible_slot_is_reported_as_refused(self) -> None:
        png = _png(self.root / "busy.png", 128, 64, 250)
        row = preflight.predict_slot(png, self.contract, 64, label="Tiny")
        self.assertEqual(row.outcome, preflight.REFUSED)
        self.assertTrue(row.needs_attention)
        self.assertIn("will not fit", row.summary())
        self.assertIn("gradients", row.detail)

    def test_a_prediction_never_claims_more_than_the_slot_allows(self) -> None:
        png = _png(self.root / "busy.png", 128, 64, 250)
        for allocation in (5_000, 8_000, 12_000):
            with self.subTest(allocation=allocation):
                row = preflight.predict_slot(
                    png, self.contract, allocation, label="Busy"
                )
                self.assertLessEqual(row.encoded_bytes, allocation)

    def test_an_unreadable_image_is_unmodelled_not_a_crash(self) -> None:
        broken = self.root / "broken.png"
        broken.write_bytes(b"not a png")
        row = preflight.predict_slot(broken, self.contract, 12_000, label="Broken")
        self.assertEqual(row.outcome, preflight.UNMODELLED)
        self.assertIn("could not be read", row.detail)

    def test_the_interpalette_gap_reaches_the_encoded_payload(self) -> None:
        # The sleeve's 64-byte gap is part of the decoded size the importer
        # refuses to deviate from, so it has to reach the payload the encoder
        # sees -- not just the arithmetic in the dataclass.
        png = _flat_png(self.root / "flat.png", 128, 64, 4)
        gapped = preflight.SlotContract(
            "sleevelike", 128, 64, 3, 256, 2, interpalette_gap_bytes=64,
        )
        self.assertEqual(gapped.decoded_bytes, SMALL.decoded_bytes + 64)
        plain = preflight.predict_slot(png, SMALL, 12_000, label="Plain")
        with_gap = preflight.predict_slot(png, gapped, 12_000, label="Gapped")
        self.assertEqual(plain.outcome, preflight.FULL)
        self.assertEqual(with_gap.outcome, preflight.FULL)
        # 64 extra zero bytes are nearly free to an LZ encoder, but they are not
        # free, and identical output would mean the gap never reached it.
        self.assertNotEqual(plain.encoded_bytes, with_gap.encoded_bytes)


class BatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="preflight-batch-")
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        # Same three kinds the real table carries, at a size CI can afford.
        self.contracts = {"torso": SMALL, "pants": SMALL, "sleeve": SMALL}

    def test_a_family_with_no_contract_is_reported_not_guessed(self) -> None:
        png = _png(self.root / "flat.png", 128, 64, 4)
        rows = preflight.predict_edits(
            [("a:1", "Some audio", "audo_audio", png, 0)],
            contracts=self.contracts,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].outcome, preflight.UNMODELLED)
        self.assertIsNone(rows[0].palette_entries)
        self.assertIn("no fixed-span prediction", rows[0].detail)

    def test_progress_is_reported_per_edit_and_completes(self) -> None:
        png = _png(self.root / "flat.png", 128, 64, 4)
        seen: list[tuple[str, int, int]] = []
        preflight.predict_edits(
            [("a:1", "One", "torso", png, 12_000),
             ("a:2", "Two", "audo_audio", png, 0)],
            progress=lambda message, done, total: seen.append((message, done, total)),
            contracts=self.contracts,
        )
        self.assertEqual(seen[0][1:], (0, 2))
        self.assertEqual(seen[-1][1:], (2, 2))

    def test_the_report_leads_with_what_blocks_the_build(self) -> None:
        busy = _png(self.root / "busy.png", 128, 64, 250)
        flat = _flat_png(self.root / "flat.png", 128, 64, 4)
        rows = preflight.predict_edits([
            ("a:1", "Fine", "torso", flat, 12_000),
            ("a:2", "Lossy", "pants", busy, 8_000),
            ("a:3", "Impossible", "sleeve", busy, 64),
        ], contracts=self.contracts)
        self.assertEqual(
            [row.outcome for row in rows],
            [preflight.FULL, preflight.REDUCED, preflight.REFUSED],
        )
        text = preflight.report(rows)
        self.assertLess(text.index("will not fit"), text.index("lose colours"))
        self.assertIn("fit as authored", text)

    def test_the_real_table_is_used_when_no_contracts_are_supplied(self) -> None:
        # The injection point exists for speed, not to let a caller quietly
        # predict against a slot the game does not have.
        png = self.root / "missing.png"
        rows = preflight.predict_edits([("a:1", "Sleeve", "sleeve", png, 5_648)])
        self.assertEqual(rows[0].outcome, preflight.UNMODELLED)
        self.assertIn("could not be read", rows[0].detail)

    def test_an_empty_set_says_so(self) -> None:
        self.assertIn("nothing to check", preflight.report(()))


if __name__ == "__main__":
    unittest.main()

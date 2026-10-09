"""W2: rain-rate repair of the main ROST: derive, apply, idempotence, refusal, scope, and the pinned v0.5 manifest."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests" / "mod_editor")]
from test_nfl2k5_weather import synthetic  # noqa: E402
sys.path.insert(0, str(ROOT / "tools" / "b77"))
import w2_rain_rate_repair as w2  # noqa: E402
from mod_editor.core import nfl2k5_weather as weather  # noqa: E402

DISC = Path("/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.5 (2026-10-06).xiso.iso")


class SyntheticRepairTests(unittest.TestCase):
    def setUp(self):
        self.rost, _ = synthetic()
        self.manifest = w2.derive_sites(self.rost)

    def test_only_outdoor_precipitation_floats_are_owned(self):
        sites = self.manifest["sites"]
        self.assertTrue(sites)
        self.assertFalse(any(s["row"] == 1 for s in sites), "the roofed row is not owned")
        for site in sites:
            self.assertEqual(site["offset"] % 4, 0)
            self.assertLess(site["after_percent"], site["before_percent"])
            self.assertEqual(struct.unpack("<f", bytes.fromhex(site["after"]))[0], site["after_percent"])

    def test_apply_is_exact_idempotent_and_scoped(self):
        out, receipt = w2.apply_sites(self.rost, self.manifest)
        again, again_receipt = w2.apply_sites(out, self.manifest)
        self.assertEqual(out, again)
        self.assertTrue(all(r["already_applied"] for r in again_receipt["sites"]))
        owned = {s["offset"] + i for s in self.manifest["sites"] for i in range(4)}
        self.assertTrue(all(a == b for i, (a, b) in enumerate(zip(self.rost, out)) if i not in owned))
        self.assertEqual(receipt["changed_bytes"], sum(a != b for a, b in zip(self.rost, out)))
        # the reparsed table equals the Studio preset on the same source
        catalog = weather.inspect_resource(out, strict=False)
        for site in self.manifest["sites"]:
            row = catalog["rows"][site["row"]]
            slot = weather.MONTH_TO_SLOT[site["month"]]
            self.assertAlmostEqual(row["months"][slot]["precipitation_pct"], site["after_percent"], places=4)

    def test_unexpected_bytes_and_size_are_refused(self):
        site = self.manifest["sites"][0]
        broken = bytearray(self.rost)
        broken[site["offset"]] ^= 0xFF
        with self.assertRaisesRegex(ValueError, "unexpected bytes"):
            w2.apply_sites(bytes(broken), self.manifest)
        with self.assertRaisesRegex(ValueError, "size changed"):
            w2.apply_sites(self.rost + b"\0", self.manifest)

    def test_other_rost_edits_compose(self):
        edited = bytearray(self.rost)
        edited[0x8000] ^= 0x5A  # a byte no site owns
        out, _ = w2.apply_sites(bytes(edited), self.manifest)
        self.assertEqual(out[0x8000], edited[0x8000])


@unittest.skipUnless(DISC.is_file(), "v0.5 disc is not available")
class V05ManifestTests(unittest.TestCase):
    def test_pinned_manifest_matches_the_v05_rost(self):
        manifest = w2.load_manifest()
        self.assertEqual(hashlib.sha256(w2.MANIFEST.read_bytes()).hexdigest(), w2.MANIFEST_SHA256)
        with w2.bump._Image.open(DISC, writable=False) as image:
            index = w2.bump._parsed_index(image)
            entry = index.entries[w2.ROST_ENTRY]
            (ordinal, offset, length), = index.sub_extents(entry, 0, entry.size)
            rost = image.read_pack(ordinal, offset, length)
        self.assertEqual(hashlib.sha256(rost).hexdigest(), w2.V05_ROST_SHA256)
        derived = w2.derive_sites(rost)
        self.assertEqual(derived["sites"], manifest["sites"])
        out, receipt = w2.apply_sites(rost, manifest)
        self.assertEqual(receipt["owned_ranges"], len(manifest["sites"]))
        catalog = weather.inspect_resource(out, strict=False)
        indoor = [r for r in catalog["rows"] if r["indoor"]]
        before = weather.inspect_resource(rost, strict=False)["rows"]
        for row in indoor:
            self.assertEqual(row["months"], before[row["index"]]["months"], "roofed rows untouched")


if __name__ == "__main__":
    unittest.main()

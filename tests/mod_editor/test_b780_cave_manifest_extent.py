"""b780: the reservation manifest declares a stack extent that covers every span it records, and it loads.

Three regenerations on 2026-11-03 wrote a manifest whose v4 pool spans (from the larger probe compositions) ended at
0x1525000 while the document declared the final stack's own size (0x1500000), so the oracle's loader refused it with
"invalid reserved span" and every manifest reader failed. The generator now declares a covering extent and loads its
own document before returning it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_cave_manifest as cm  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import OracleError, ReservationManifest, XbeImage  # noqa: E402

MANIFEST = ROOT / "data" / "nfl2k5_cave_reservations.json"
_RETAIL_ENV = os.environ.get("NFL2K5_RETAIL_XBE")  # private retail default.xbe; the loader test skips without it
RETAIL_XBE = Path(_RETAIL_ENV) if _RETAIL_ENV else None


def _span(start: int, end: int) -> dict:
    return {"start": hex(start), "end": hex(end), "size": end - start, "owner": "nfl2k5_xbe_space", "basis": "test"}


class StackExtentTests(unittest.TestCase):
    final = SimpleNamespace(image_size=0x1500000, base=0x10000)

    def test_spans_inside_the_final_image_keep_its_size(self):
        self.assertEqual(cm.stack_extent(self.final, [_span(0x14D9000, 0x1510000)]), 0x1500000)

    def test_spans_past_the_final_image_extend_it_to_a_whole_page(self):
        self.assertEqual(cm.stack_extent(self.final, [_span(0x14D9000, 0x1525000)]), 0x1515000)
        self.assertEqual(cm.stack_extent(self.final, [_span(0x1524F00, 0x1525001)]), 0x1516000)

    def test_no_spans_keep_the_final_size(self):
        self.assertEqual(cm.stack_extent(self.final, []), 0x1500000)


@unittest.skipUnless(RETAIL_XBE is not None and RETAIL_XBE.is_file(), "the private retail default.xbe is needed (NFL2K5_RETAIL_XBE)")
class CommittedManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.retail = RETAIL_XBE.read_bytes()

    def test_the_committed_manifest_loads_and_its_extent_covers_every_span(self):
        cm.check_loadable(self.document, self.retail)
        image = XbeImage(self.retail)
        highest = max(int(row["end"], 0) for row in self.document["spans"])
        self.assertLessEqual(highest, image.base + self.document["stack_image_size"])
        self.assertEqual(self.document["stack_image_size"] % 0x1000, 0)

    def test_a_manifest_declaring_too_small_an_extent_is_refused(self):
        bad = dict(self.document, stack_image_size=self.document["allocator_layout"]["image_size"])
        highest = max(int(row["end"], 0) for row in self.document["spans"])
        if highest <= XbeImage(self.retail).base + bad["stack_image_size"]:
            self.skipTest("every span of this manifest lies inside the final image")
        with self.assertRaisesRegex(OracleError, "invalid reserved span"):
            ReservationManifest(bad, XbeImage(self.retail))


if __name__ == "__main__":
    unittest.main()

"""Exact existing 7-on-7 reservations against a freshly observed scratch manifest."""
import hashlib
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_cave_manifest as builder
from mod_editor.core import nfl2k5_seven_on_seven as seven
from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
from tests.mod_editor import test_nfl2k5_owner_pairwise_composition as pairs


class OwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = pairs.retail_xbe()
        cls.image = XbeImage(cls.retail)
        cls.manifest = ReservationManifest.load(
            Path(os.environ.get("NFL2K5_CAVE_MANIFEST", DEFAULT_MANIFEST)), cls.image, source_root=ROOT)

    def test_every_complete_site_and_rw_flag_are_exclusively_reserved(self):
        for label, va, before, _ in seven.sites():
            with self.subTest(site=label):
                self.assertEqual(self.image.read(va, len(before)), before)
                owned = self.manifest.overlaps(va, va + len(before))
                self.assertTrue(any(r.start <= va and va + len(before) <= r.end for r in owned))
                self.assertFalse(self.manifest.overlaps(va, va + len(before), exclude_owner=seven.OWNER))
        self.assertTrue(self.manifest.overlaps(seven.FLAG_VA, seven.FLAG_VA + 1))
        self.assertFalse(self.manifest.overlaps(seven.FLAG_VA, seven.FLAG_VA + 1, exclude_owner=seven.OWNER))

    def test_retired_rush_hooks_and_live_neighbor_are_not_owned(self):
        for va, size in ((0x232E5C, 5), (0x2333B3, 6), (0x1AC260, 16)):
            self.assertFalse(any(row.detail.startswith(seven.OWNER + ":")
                                 for row in self.manifest.overlaps(va, va + size)))

    def test_real_owner_writer_accounts_for_every_changed_byte(self):
        recorder = builder.Recorder(self.retail)
        result, receipt = recorder.wrapper(seven, "apply")(self.retail)
        rows = recorder.finish(result)
        self.assertEqual(recorder.steps[0]["changed_bytes"], receipt["changed_bytes"])
        self.assertEqual(recorder.steps[0]["after_sha256"], hashlib.sha256(result).hexdigest())
        self.assertTrue(any(row["owner"] == seven.OWNER and row["start"] == hex(seven.CAVE_VA)
                            and row["size"] == seven.CAVE_SIZE for row in rows))
        self.assertTrue(any(row["owner"] == seven.OWNER and row["start"] == hex(seven.FLAG_VA)
                            and row["size"] == 1 for row in rows))
        self.assertEqual(seven.apply(result)[0], result)


if __name__ == "__main__":
    unittest.main()

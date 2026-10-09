"""Native v0.5 PLAY repair for the v2 offense (b77 job p48o): manifest shape, refusals, one real book.

The real-book checks need the v0.5 disc, the retail disc and the retail default.xbe (paths below, override with
P48O_V05_ISO / P48O_RETAIL_ISO / P48O_RETAIL_XBE); without them only the manifest checks run.
"""
from pathlib import Path
import hashlib
import json
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from tools.b77 import p48o_repair as repair

V05 = Path(os.environ.get("P48O_V05_ISO", "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.5 (2026-10-06).xiso.iso"))
RETAIL = Path(os.environ.get("P48O_RETAIL_ISO", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
XBE = Path(os.environ.get("P48O_RETAIL_XBE", "/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe"))
MANIFEST = repair.manifest()
HAVE_DISCS = V05.is_file() and RETAIL.is_file() and XBE.is_file()


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ManifestShape(unittest.TestCase):
    def test_32_team_books_in_the_owned_range(self):
        books = MANIFEST["books"]
        self.assertEqual(len(books), 32)
        for key, row in books.items():
            self.assertTrue(307 <= int(key) <= 342)
            self.assertNotIn(int(key), (318, 320, 334, 335, 343))
            for field in ("v05_sha256", "retail_sha256", "after_sha256"):
                self.assertEqual(len(row[field]), 64, (key, field))
            self.assertNotEqual(row["v05_sha256"], row["after_sha256"])
        self.assertEqual(len({row["team"] for row in books.values()}), 32)

    def test_team_for_refuses_foreign_entries(self):
        for entry in (318, 320, 334, 335, 343, 1):
            with self.assertRaises(ValueError):
                repair.team_for(entry)
        self.assertEqual(repair.team_for(int(next(iter(MANIFEST["books"])))), next(iter(MANIFEST["books"].values()))["team"])

    def test_wrong_size_and_wrong_xbe_are_refused(self):
        with self.assertRaises(ValueError):
            repair.repair_resource(b"x", 307, b"y", b"z")
        blank = bytes(repair.RESOURCE_SIZE)
        with self.assertRaises(ValueError):
            repair.repair_resource(blank, 307, blank, b"not the retail xbe")


@unittest.skipUnless(HAVE_DISCS, "needs the v0.5 disc, the retail disc and the retail default.xbe")
class RealBook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
        cls.xbe = XBE.read_bytes()
        cls.entry = BOOK_ENTRIES["KC"]
        with OuterImage(V05) as v05, OuterImage(RETAIL) as retail:
            cls.raw, cls.retail = v05.read_entry(cls.entry), retail.read_entry(cls.entry)

    def test_known_hashes_idempotence_and_refusal(self):
        row = MANIFEST["books"][str(self.entry)]
        result, receipt = repair.repair_resource(self.raw, self.entry, self.retail, self.xbe)
        self.assertEqual((sha(self.raw), sha(result)), (row["v05_sha256"], row["after_sha256"]))
        self.assertEqual(receipt["status"], "applied")
        again, second = repair.repair_resource(result, self.entry, self.retail, self.xbe)
        self.assertEqual(again, result)
        self.assertEqual((second["status"], second["changed_bytes"]), ("already_applied", 0))
        self.assertFalse(receipt["preserved_decoded"]["plays_differing"])
        self.assertFalse(receipt["preserved_decoded"]["defensive_categories_differing"])
        with self.assertRaises(ValueError):
            repair.repair_resource(self.retail, self.entry, self.retail, self.xbe)


if __name__ == "__main__":
    unittest.main()

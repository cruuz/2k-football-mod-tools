"""b778-xs1: the Crib keeps only the Trophy Room side (catalog popup skipped, the two shop rows removed)."""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_crib_trophy_room as crib
from mod_editor.core import mod_build
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_my_career_fixture import XBE


def label(image, va):
    return image.read(va, 64).decode("utf-16-le", "replace").split("\0")[0]


@unittest.skipUnless(XBE.is_file(), "pinned USA XBE required")
class CribTrophyRoomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        cls.applied, cls.receipt = crib.apply(cls.retail)

    def test_status_edits_and_replay(self):
        self.assertEqual((crib.status(self.retail), crib.status(self.applied)), ("retail", "applied"))
        image = XbeImage(self.applied)
        self.assertEqual(image.read(0x277185, 2), bytes.fromhex("eb0e"))   # entering always goes to the room (state 3)
        self.assertEqual(image.read(0x2771FF, 2), bytes.fromhex("6a03"))   # first visit continues to the room
        self.assertEqual(crib.apply(self.applied)[0], self.applied)
        self.assertEqual(self.receipt["changed_bytes"], sum(a != b for a, b in zip(self.retail, self.applied)))
        from mod_editor.core.nfl2k5_bump_strength import _sections
        digests = [(x.header_offset + 36, x.header_offset + 56) for x in _sections(self.applied)]
        lo = image.offset(crib.OPTIONS, 6 * crib.ROW)
        sites = {image.offset(0x277185), image.offset(0x277185) + 1, image.offset(0x2771FF), image.offset(0x2771FF) + 1}
        for i, (a, b) in enumerate(zip(self.retail, self.applied)):
            if a != b:
                self.assertTrue(i in sites or lo <= i < lo + 6 * crib.ROW or any(x <= i < y for x, y in digests), hex(i))

    def test_options_keep_user_card_milestones_and_exit(self):
        retail, applied = XbeImage(self.retail), XbeImage(self.applied)
        rows = lambda img: [(struct.unpack_from("<I", img.read(crib.OPTIONS + i * crib.ROW, 4))[0],
                             struct.unpack_from("<I", img.read(crib.OPTIONS + i * crib.ROW + 4, 4))[0]) for i in range(6)]
        self.assertEqual([label(retail, l) for k, l in rows(retail)[:5]],
                         ["User Card", "Catalogs", "Crib Items", "Milestone Info", "Exit"])
        after = rows(applied)
        self.assertEqual([k for k, _ in after[:4]], [0, 0, 9, 3])
        self.assertEqual([label(applied, l) for _, l in after[:3]], ["User Card", "Milestone Info", "Exit"])
        self.assertFalse(any(applied.read(crib.OPTIONS + 4 * crib.ROW, 2 * crib.ROW)))
        # the kept rows are the retail rows byte for byte (submenus and the Exit action unchanged)
        for new, old in ((0, 0), (1, 3), (2, 4)):
            self.assertEqual(applied.read(crib.OPTIONS + new * crib.ROW, crib.ROW), retail.read(crib.OPTIONS + old * crib.ROW, crib.ROW))

    def test_foreign_and_mixed_refuse(self):
        image = XbeImage(self.applied)
        for va in (0x277185, 0x2771FF, crib.OPTIONS + 4):
            bad = bytearray(self.applied)
            bad[image.offset(va)] ^= 1
            with self.subTest(va=hex(va)):
                self.assertEqual(crib.status(bytes(bad)), "foreign")
                with self.assertRaises(ValueError):
                    crib.apply(bytes(bad))
        mixed = bytearray(self.retail)
        mixed[XbeImage(self.retail).offset(0x277185)] = 0xEB
        self.assertEqual(crib.status(bytes(mixed)), "foreign")

    def test_build_option_presets(self):
        self.assertFalse(mod_build.BuildPlan.__dataclass_fields__["crib_trophy_room"].default)
        for name in ("softdrink_basic", "softdrink_advanced", "softdrink_experimental"):
            self.assertTrue(mod_build.PRESETS[name]["crib_trophy_room"], name)


if __name__ == "__main__":
    unittest.main()

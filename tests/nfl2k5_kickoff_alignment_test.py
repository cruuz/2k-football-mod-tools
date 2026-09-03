"""Dynamic-kickoff alignment (playbook slot rewrite): geometry, byte-exact recognition, and a read-only
pass over the private base image when it is present."""

from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import nfl2k5_kickoff_alignment as ka  # noqa: E402

BASE_IMAGE = Path("/home/noah/2K5 Mod Studio Builds/NFL 2K5 Create-a-Play.xiso.iso")
YD = ka.YARD_CM


def _retail_block(xz) -> bytes:
    """A 154-byte slot block with retail-looking stance / mirror bytes and the given columns."""

    out = bytearray(ka.SLOTS_SIZE)
    for s, (x, z) in enumerate(xz):
        base = s * ka.SLOT_STRIDE
        out[base] = 0
        out[base + 1] = (s << 4) | 1
        struct.pack_into("<hhh", out, base + 2, x, x, x)
        struct.pack_into("<hhh", out, base + 8, z, z, z)
    return bytes(out)


class GeometryTests(unittest.TestCase):
    def test_retail_tables_are_the_35_yard_look(self) -> None:
        self.assertEqual(len(ka.RETAIL_KICKOFF_XZ), 11)
        self.assertEqual(len(ka.RETAIL_KICK_RETURN_XZ), 11)
        self.assertAlmostEqual(ka.RETAIL_KICKOFF_XZ[0][1] / YD, -8.92, places=2)     # kicker run-up
        self.assertTrue(all(z == -914 for _x, z in ka.RETAIL_KICKOFF_XZ[1:]))          # coverage 10 yd behind the ball
        self.assertAlmostEqual(ka.RETAIL_KICK_RETURN_XZ[0][1] / YD, 69.4, places=1)   # deep men

    def test_2026_kickoff_layout(self) -> None:
        xz = ka.kickoff_xz_2026()
        self.assertEqual(xz[0], (91, -457))                                   # 5.0 yd run-up (Noah: a little closer)
        self.assertTrue(all(z == 2286 for _x, z in xz[1:]))                   # the receiving 40 = 25 yd from the ball
        self.assertEqual([x for x, _z in xz[1:]], [x for x, _z in ka.RETAIL_KICKOFF_XZ[1:]])
        self.assertEqual(sum(1 for x, _z in xz[1:] if x > 0), 5, "five to each side of the ball")
        self.assertEqual(ka.kickoff_xz_2026(ka.RETAIL_KICKER_DEPTH_YD)[0][1], -816)
        with self.assertRaises(ka.recode.RecodeError):
            ka.kickoff_xz_2026(0.5)

    def test_2026_return_layout_obeys_the_setup_zone_rule(self) -> None:
        xz = ka.KICK_RETURN_XZ_2026
        on_line = [x for x, z in xz if z == 2743]
        in_zone = [x for x, z in xz if 2743 <= z <= 3200]
        returners = [(x, z) for x, z in xz if z > 4115]                      # inside the landing zone (goal..20 = 45..65 yd)
        self.assertEqual(len(on_line), 7, "seven on the restraining line (the receiving 35)")
        self.assertEqual(len(in_zone), 9, "nine in the setup zone")
        self.assertEqual(len(returners), 2)
        self.assertTrue(all(z <= 65 * YD for _x, z in returners))
        off_line = [x for x, z in xz if 2743 < z <= 3200]
        self.assertEqual(len(off_line), 2)
        self.assertTrue(min(off_line) < -600 and max(off_line) > 600, "one per outside third")
        self.assertEqual(sorted(x for x in on_line), [-2000, -1330, -670, 0, 670, 1330, 2000])
        self.assertTrue(all(abs(x) <= 2400 for x, _z in xz), "inside the sideline (26.7 yd)")

    def test_with_xz_only_touches_the_six_coordinate_words(self) -> None:
        block = _retail_block(ka.RETAIL_KICKOFF_XZ)
        new = ka.with_xz(block, ka.kickoff_xz_2026())
        for s in range(11):
            base = s * ka.SLOT_STRIDE
            self.assertEqual(new[base: base + 2], block[base: base + 2], "stance / mirror bytes kept")
        self.assertEqual(ka.slots_xz(new), ka.kickoff_xz_2026())
        self.assertEqual(ka.with_xz(new, ka.RETAIL_KICKOFF_XZ), block, "round trip")


class RecognitionTests(unittest.TestCase):
    def _ref(self, name, block):
        return ka.FormationRef("TST", 0, name, 8 if name == ka.KICKOFF_NAME else 9, 0, 0, block)

    def test_states(self) -> None:
        retail = _retail_block(ka.RETAIL_KICKOFF_XZ)
        self.assertEqual(ka._state_of(self._ref(ka.KICKOFF_NAME, retail)), ("retail", None))
        applied = ka.with_xz(retail, ka.kickoff_xz_2026(5.0))
        self.assertEqual(ka._state_of(self._ref(ka.KICKOFF_NAME, applied)), ("applied", 5.0))
        applied7 = ka.with_xz(retail, ka.kickoff_xz_2026(7.0))
        self.assertEqual(ka._state_of(self._ref(ka.KICKOFF_NAME, applied7)), ("applied", 7.0))
        broken = bytearray(applied)
        struct.pack_into("<h", broken, 3 * ka.SLOT_STRIDE + 8, 2000)      # one coverage man off the line
        self.assertEqual(ka._state_of(self._ref(ka.KICKOFF_NAME, bytes(broken)))[0], "foreign")
        broken = bytearray(retail)
        broken[2 * ka.SLOT_STRIDE + 2] ^= 1
        self.assertEqual(ka._state_of(self._ref(ka.KICKOFF_NAME, bytes(broken)))[0], "foreign")
        ret = _retail_block(ka.RETAIL_KICK_RETURN_XZ)
        self.assertEqual(ka._state_of(self._ref(ka.KICK_RETURN_NAME, ret)), ("retail", None))
        self.assertEqual(ka._state_of(self._ref(ka.KICK_RETURN_NAME, ka.with_xz(ret, ka.KICK_RETURN_XZ_2026))), ("applied", None))

    def test_a_column_1_or_2_edit_on_an_applied_block_is_foreign(self) -> None:
        retail = _retail_block(ka.RETAIL_KICKOFF_XZ)
        applied = bytearray(ka.with_xz(retail, ka.kickoff_xz_2026()))
        struct.pack_into("<h", applied, 4 * ka.SLOT_STRIDE + 10, 0)         # depth column 1 of slot 4
        self.assertEqual(ka._state_of(self._ref(ka.KICKOFF_NAME, bytes(applied)))[0], "foreign")


@unittest.skipUnless(BASE_IMAGE.is_file(), "private base image not present")
class BaseImageTests(unittest.TestCase):
    def test_base_image_is_retail_in_all_36_kicking_books(self) -> None:
        result = ka.status(BASE_IMAGE)
        self.assertEqual(result["status"], "retail")
        self.assertEqual(result["books"], 36)          # PRACTICE has no kickoff pair
        self.assertEqual(result["foreign"], [])
        rows = result["rows"]
        self.assertEqual(len(rows), 72)
        for row in rows:
            expected = ka.RETAIL_KICKOFF_XZ if row["formation"] == ka.KICKOFF_NAME else ka.RETAIL_KICK_RETURN_XZ
            self.assertEqual(row["slots_yd"], [(round(x / YD, 2), round(z / YD, 2)) for x, z in expected], row["book"])
        # the two records sit inside the outer archive's playbook entries: distinct offsets per book
        self.assertEqual(len({row["virtual_offset"] for row in rows}), 72)


if __name__ == "__main__":
    unittest.main()

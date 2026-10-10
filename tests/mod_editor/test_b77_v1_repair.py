"""b77 v1: the native goalposts repair (tools/b77/v1_repair.py) on a disc's pack 0 and default.xbe.

The scope helper runs on synthetic bytes. The repair itself needs the user's own files and skips without them:
NFL2K5_GAME_DIR (retail default.xbe and vc_53450030/0) and, for the exact SOFTDRINK 2K28 v0.5 receipts, B77_V05_DIR (a
folder holding that disc's extracted ``vc_53450030__0`` and ``default.xbe``).
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for _extra in (ROOT, ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from tools.b77 import v1_repair as repair  # noqa: E402
from mod_editor.core import nfl2k5_modern_goalposts as goal  # noqa: E402

GAME = Path(os.environ.get("NFL2K5_GAME_DIR", str(ROOT / "extracted" / "ESPN NFL 2K5 (USA)")))
HAVE_GAME = (GAME / "vc_53450030" / "0").is_file() and (GAME / "default.xbe").is_file()
V05 = Path(os.environ.get("B77_V05_DIR", "/nonexistent"))
HAVE_V05 = (V05 / "vc_53450030__0").is_file() and (V05 / "default.xbe").is_file()
V05_AFTER = {"vc_53450030__0": "f38bb38b5fe909649ca47abebdf55430b51bfa3763c39a50dae682091255f3f3",
             "default.xbe": "163e08abcc41cd92c0fdc8cb13d950187b204dce38b016c861bc8fcbd43070e3"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Scope(unittest.TestCase):
    def test_counts_inside_and_outside(self):
        before = bytes(range(64))
        after = bytearray(before)
        after[10] ^= 1; after[11] ^= 1; after[40] ^= 1
        result = repair.scope(before, bytes(after), [(8, 16)])
        self.assertEqual((result["bytes_changed_inside"], result["bytes_changed_outside"], result["first_outside"],
                          result["identical_outside"]), (2, 1, "0x28", False))
        self.assertTrue(repair.scope(before, before, [])["identical_outside"])
        with self.assertRaises(goal.ModernGoalpostsError):
            repair.scope(before, before + b"\0", [])


@unittest.skipUnless(HAVE_GAME, "needs the extracted retail default.xbe and vc_53450030/0 (NFL2K5_GAME_DIR)")
class RetailInputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack0 = (GAME / "vc_53450030" / "0").read_bytes()
        cls.xbe = (GAME / "default.xbe").read_bytes()
        cls.out = repair.repair(cls.pack0, cls.xbe)

    def test_only_the_declared_ranges_change(self):
        new_pack0, new_xbe, receipt = self.out
        self.assertEqual(receipt["status"], "OK")
        self.assertEqual(receipt["states_before"], {"goalpost": "retail", "goalpost_shadow": "retail", "xbe": "retail"})
        self.assertEqual(set(receipt["states_after"].values()), {"applied"})
        for name, before, after in (("vc_53450030__0", self.pack0, new_pack0), ("default.xbe", self.xbe, new_xbe)):
            with self.subTest(file=name):
                scope = receipt["files"][name]["scope"]
                self.assertTrue(scope["identical_outside"])
                self.assertGreater(scope["bytes_changed_inside"], 0)
                self.assertEqual(len(after), len(before))
        self.assertEqual(receipt["files"]["default.xbe"]["scope"]["bytes_changed_inside"], 29)   # 3 x 3 + digest
        self.assertEqual([r[2] for r in receipt["files"]["vc_53450030__0"]["scope"]["declared_ranges"]], [1968, 2832])

    def test_idempotent(self):
        new_pack0, new_xbe, _receipt = self.out
        again_pack0, again_xbe, receipt = repair.repair(new_pack0, new_xbe)
        self.assertEqual((again_pack0, again_xbe, receipt["status"]), (new_pack0, new_xbe, "ALREADY_APPLIED"))

    def test_refuses_unexpected_owned_bytes(self):
        new_pack0, _x, receipt = self.out
        at = receipt["files"]["vc_53450030__0"]["resources"][1]["pack0_offset"] + 100
        bad = bytearray(self.pack0); bad[at] ^= 0xFF
        with self.assertRaises(goal.ModernGoalpostsError):
            repair.repair(bytes(bad), self.xbe)
        offset = goal._xbe_offsets(self.xbe)(0x1C6A2E, 4)
        bad_xbe = bytearray(self.xbe); bad_xbe[offset] ^= 0xFF
        with self.assertRaises(goal.ModernGoalpostsError):
            repair.repair(self.pack0, bytes(bad_xbe))


@unittest.skipUnless(HAVE_V05, "needs the SOFTDRINK 2K28 v0.5 disc's extracted pack 0 and default.xbe (B77_V05_DIR)")
class V05Inputs(unittest.TestCase):
    def test_exact_v05_receipts(self):
        pack0, xbe = (V05 / "vc_53450030__0").read_bytes(), (V05 / "default.xbe").read_bytes()
        self.assertEqual((sha(pack0), sha(xbe)), (repair.V05_PACK0_SHA256, repair.V05_XBE_SHA256))
        new_pack0, new_xbe, receipt = repair.repair(pack0, xbe)
        self.assertEqual((sha(new_pack0), sha(new_xbe)), (V05_AFTER["vc_53450030__0"], V05_AFTER["default.xbe"]))
        self.assertTrue(all(receipt["files"][n]["scope"]["identical_outside"] for n in V05_AFTER))


if __name__ == "__main__":
    unittest.main()

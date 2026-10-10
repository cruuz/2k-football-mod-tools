"""b77 p9 native repair: Modern 2 on a v0.5-shaped default.xbe, scope receipt, idempotence, refusals, CLI.

The standalone checks start from the pinned USA retail default.xbe with the Modern owner applied (the shape of the v0.5 owner). The
optional disc check extracts the real default.xbe of the SOFTDRINK 2K28 v0.5 disc (read only) and pins the repaired file's hash.
"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "b77"))
from mod_editor.core import nfl2k5_cpu_money_downs as patch
from mod_editor.core import nfl2k5_xbe_space as space
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import repin_edit, retail_xbe
import p9_repair as repair

V05_DISC = Path("/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.5 (2026-10-06).xiso.iso")
V05_XBE_SHA256 = "2b0fbbbb89b5c72aaed7c454bf6e78dd2c97f1e417e2d761e515907ed81471ab"
# Output of the repair on the real v0.5 default.xbe for the final Modern 2 template (changes with the template: re-pin only with proof).
V05_REPAIRED_SHA256 = "2f7211c7bd432f332cb6a8495cfd069500ef3f4e25d33ea8d7a545c39bad864e"


class RepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.modern = patch.apply(cls.retail, level="modern")[0]
        cls.modern2 = patch.apply(cls.retail, level="modern2")[0]

    def test_repair_scope_receipt_and_equality_with_a_fresh_build(self):
        out, receipt = repair.repair(self.modern)
        self.assertEqual(out, self.modern2)
        self.assertEqual((receipt["status"], receipt["state_before"], receipt["state_after"]), ("OK", "modern", "modern2"))
        scope = receipt["files"]["default.xbe"]["scope"]
        self.assertTrue(scope["identical_outside"])
        self.assertEqual(scope["bytes_changed_outside"], 0)
        self.assertGreater(scope["bytes_changed_inside"], 1900)
        self.assertEqual(receipt["files"]["default.xbe"]["after_sha256"], hashlib.sha256(out).hexdigest())
        labels = [row["label"] for row in receipt["files"]["default.xbe"]["sites"]]
        for want in ("owner code allocation", "site two_point", "site fg_dispatch", "site fg_commit", "site exponent_front",
                     "site exponent_cover", "section digest of .text (derived)"):
            self.assertIn(want, labels)
        # the shotgun 10-yard rule (jne at 0x207F85, file offset 0x1F7F85) is not an owned range and its bytes are identical
        self.assertEqual(out[0x1F7F85:0x1F7F87], self.modern[0x1F7F85:0x1F7F87])
        self.assertEqual(out[0x1F7F85:0x1F7F87], bytes.fromhex("7520"))
        for start, end in [(int(a, 16), int(b, 16)) for a, b, _n in scope["declared_ranges"]]:
            self.assertFalse(start <= 0x1F7F85 < end)

    def test_idempotent_and_refuses_unexpected_input(self):
        out, receipt = repair.repair(self.modern)
        again, repeated = repair.repair(out)
        self.assertIs(again, out)
        self.assertEqual(repeated["status"], "ALREADY_APPLIED")
        self.assertEqual(repeated["files"]["default.xbe"]["scope"]["bytes_changed_inside"], 0)
        for bad in (self.retail, b"", repin_edit(self.modern, 0x20B670, b"\x00")):
            with self.assertRaises(ValueError):
                repair.repair(bad)

    def test_cli_writes_a_new_file_and_a_receipt(self):
        with tempfile.TemporaryDirectory(prefix="p9-repair-") as directory:
            work = Path(directory).resolve()
            source = work / "in.xbe"
            source.write_bytes(self.modern)
            args = ["--xbe", str(source), "--out-dir", str(work / "out"), "--receipt", str(work / "receipt.json")]
            self.assertEqual(repair.main(args), 0)
            self.assertEqual((work / "out" / "default.xbe").read_bytes(), self.modern2)
            receipt = json.loads((work / "receipt.json").read_text())
            self.assertEqual(receipt["status"], "OK")
            self.assertEqual(source.read_bytes(), self.modern)
            # second run on the output is a no-op
            self.assertEqual(repair.main(["--xbe", str(work / "out" / "default.xbe"), "--out-dir", str(work / "out2"),
                                          "--receipt", str(work / "receipt2.json")]), 0)
            self.assertEqual(json.loads((work / "receipt2.json").read_text())["status"], "ALREADY_APPLIED")
            self.assertEqual((work / "out2" / "default.xbe").read_bytes(), self.modern2)


@unittest.skipUnless(V05_DISC.is_file(), "the SOFTDRINK 2K28 v0.5 disc image is absent")
class RealV05Tests(unittest.TestCase):
    def test_real_default_xbe_of_the_v05_disc(self):
        from mod_editor.core import nfl2k5_throw_tuning as tt, platform_compat
        fd = os.open(V05_DISC, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        try:
            offset, length = tt.image_xbe_extent(fd, os.fstat(fd).st_size)
            xbe = platform_compat.pread(fd, length, offset)
        finally:
            os.close(fd)
        self.assertEqual(hashlib.sha256(xbe).hexdigest(), V05_XBE_SHA256)
        self.assertEqual(patch.read_settings(xbe)["level"], "modern")
        out, receipt = repair.repair(xbe)
        self.assertEqual(hashlib.sha256(out).hexdigest(), V05_REPAIRED_SHA256)
        self.assertEqual(receipt["files"]["default.xbe"]["scope"]["bytes_changed_outside"], 0)
        self.assertEqual(patch.read_settings(out)["level"], "modern2")
        self.assertEqual(space.status(out), "applied")


if __name__ == "__main__":
    unittest.main()

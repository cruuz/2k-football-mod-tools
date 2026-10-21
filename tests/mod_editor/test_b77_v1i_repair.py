"""V1I's bounded native repair, with optional private v0.6/stack fixtures."""
from pathlib import Path
import contextlib
import io
import os
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.b77 import v1i_repair as repair
from mod_editor.core import nfl2k5_honors as honors
from mod_editor.core import nfl2k5_rdata_sites as rdata
from mod_editor.core import nfl2k5_season_length as season
from tests.mod_editor.test_nfl2k5_honors import _retail, XBE

V06 = Path(os.environ.get("B771_V1I_XBE", "/nonexistent/v06_default.xbe"))


@unittest.skipUnless(XBE.is_file(), "pinned USA XBE required")
class SourceTests(unittest.TestCase):
    def test_retail_stays_on_week_17(self):
        raw = _retail()
        if raw is None:
            self.skipTest("retail pin differs")
        out, receipt = season.repair_awards_timing(raw)
        self.assertEqual(out, raw)
        self.assertEqual(receipt["award_week"], 17)
        self.assertTrue(receipt["already_applied"])

    def test_foreign_comparison_is_not_masked_by_honors_guard(self):
        raw = _retail()
        if raw is None:
            self.skipTest("retail pin differs")
        for before, after, va in ((b"\x10", b"\x12", season.AWARDS_WEEK_VA),
                                  (b"\xfd", b"\xfc", season.AWARDS_WEEK_VA - 1)):
            bad = rdata.apply(raw, [("foreign", va, before, after)], "test")[0]
            with self.assertRaisesRegex(ValueError, "foreign annual-awards"):
                season.repair_awards_timing(bad)
            self.assertEqual(honors.status(bad), "foreign")


@unittest.skipUnless(V06.is_file(), "B771_V1I_XBE enables private v0.6 repair checks")
class RepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = V06.read_bytes()
        if repair.sha(cls.raw) != repair.V06_SHA256:
            raise unittest.SkipTest("v0.6 fixture pin differs")
        cls.fixed, cls.receipt = repair.repair_xbe(cls.raw)

    def test_exact_scope_and_idempotence(self):
        changes = {i for i, (a, b) in enumerate(zip(self.raw, self.fixed)) if a != b}
        self.assertEqual(len(changes), 21)
        self.assertEqual(changes - set(range(0x394, 0x3A8)), {0x106D6E})
        self.assertEqual(self.fixed[0x106D6E], 17)
        self.assertEqual(repair.sha(self.fixed), "bb738a88557250f1598ee9c4328accad6d7cbbaa9e8ccd25d78bdea6c3eb4b49")
        again, receipt = repair.repair_xbe(self.fixed)
        self.assertEqual(again, self.fixed)
        self.assertEqual((receipt["status"], receipt["changed_bytes"]), ("already_repaired", 0))

    def test_refuses_short_foreign_and_unapproved_resealed_inputs(self):
        with self.assertRaisesRegex(ValueError, "size"):
            repair.repair_xbe(self.raw[:-1])
        broken = bytearray(self.raw)
        broken[0x106D6E] = 17  # no section digest repair
        with self.assertRaises(ValueError):
            repair.repair_xbe(bytes(broken))
        # Resealed padding after the dispatcher, outside its dependency span:
        # valid F5/calendar code, but not the approved complete executable.
        foreign = rdata.apply(self.raw, [("padding", 0x116E6A, b"\x90", b"\xcc")], "test")[0]
        self.assertEqual(honors.status(foreign), "applied")
        with self.assertRaisesRegex(ValueError, "unexpected input SHA-256"):
            repair.repair_xbe(foreign)
        repaired, _ = repair.repair_xbe(foreign, approved=(repair.sha(foreign),))
        with self.assertRaisesRegex(ValueError, "unexpected input SHA-256"):
            repair.repair_xbe(repaired)

    def test_cli_preserves_input_and_existing_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            src, out, log = (folder / name for name in ("input.xbe", "output.xbe", "receipt.json"))
            src.write_bytes(self.raw)
            args = ["--xbe", str(src), "--output", str(out), "--receipt", str(log)]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(repair.main(args), 0)
                self.assertEqual(repair.main(args), 0)
                log.write_text("existing user data\n", encoding="utf-8", newline="\n")
                self.assertEqual(repair.main(args), 2)
                self.assertEqual(repair.main(["--xbe", str(src), "--output", str(src), "--receipt", str(log)]), 2)
            self.assertEqual(src.read_bytes(), self.raw)
            self.assertEqual(out.read_bytes(), self.fixed)
            self.assertEqual(log.read_text(), "existing user data\n")

    def test_explicit_stacked_inputs_preserve_every_other_byte(self):
        paths = os.environ.get("B771_V1I_STACKS", "").split(os.pathsep)
        if not paths[0]:
            self.skipTest("B771_V1I_STACKS enables v1c/v1h composition fixtures")
        for path in paths:
            with self.subTest(path=path):
                raw = Path(path).read_bytes()
                digest = repair.sha(raw)
                out, receipt = repair.repair_xbe(raw, approved=(digest,))
                self.assertTrue(receipt["outside_scope_identical"])
                self.assertEqual(out[:0x394], raw[:0x394])
                self.assertEqual(out[0x3A8:0x106D6E], raw[0x3A8:0x106D6E])
                self.assertEqual(out[0x106D6F:], raw[0x106D6F:])
                self.assertEqual(repair.repair_xbe(out, approved=(digest,))[0], out)


if __name__ == "__main__":
    unittest.main()

"""Native d2 repair scope/refusal and short-pass classification regression checks."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.b765 import d2_repair as repair
from mod_editor.core import nfl2k5_abilities_runtime as abilities
from mod_editor.core import nfl2k5_throw_tuning as tuning
from mod_editor.core import nfl2k5_stock_books as books

V04 = Path(os.environ.get("B765_D2_V04_XBE", "/nonexistent-b765-d2-evidence"))


@unittest.skipUnless(V04.is_file(), "Set B765_D2_V04_XBE to the exact extracted v0.4 XBE")
class NativeRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = V04.read_bytes()
        if repair.sha(cls.before) != repair.V04_SHA256:
            raise ValueError("Foreign v0.4 fixture")
        cls.after, cls.receipt = repair.restore_base_moves(cls.before)

    def test_exact_repair_and_idempotence(self):
        self.assertEqual(repair.sha(self.after), repair.FIXED_SHA256)
        again, receipt = repair.restore_base_moves(self.after)
        self.assertEqual(again, self.after)
        self.assertEqual(receipt["changed_bytes"], 0)
        self.assertEqual(receipt["status"], "already_applied")

    def test_every_byte_outside_scopes_identical(self):
        allowed = set()
        for row in self.receipt["scopes"]:
            start = int(row["file_offset"], 16)
            allowed.update(range(start, start + row["size"]))
        self.assertEqual(len(self.before), len(self.after))
        differences = {i for i, (a, b) in enumerate(zip(self.before, self.after)) if a != b}
        self.assertEqual(len(differences), 106)
        self.assertFalse(differences - allowed)
        self.assertTrue(self.receipt["allocator_requests_unchanged"])
        settings = abilities.read_settings(self.after)
        self.assertFalse(settings["lock_right_stick"])
        self.assertFalse(settings["lock_special_moves"])
        self.assertTrue(settings["lock_speedster"])
        self.assertEqual(settings["abilities_off_week"], None)

    def test_foreign_owner_or_unsealed_image_refused(self):
        allocation = abilities.allocation(self.before)
        for at in (allocation["raw"], allocation["raw"] + 1288, 0xDB4):
            broken = bytearray(self.before)
            broken[at] ^= 1
            with self.subTest(offset=hex(at)), self.assertRaises(ValueError):
                repair.restore_base_moves(bytes(broken))

    def test_composes_with_independent_throw_distance_setting(self):
        curves = tuning.curves_for(tuning.TuningSettings(85))
        curves.pop("lobspeed")
        staged, _ = tuning.plan_patch(self.before, curves)
        repaired, _ = repair.restore_base_moves(staged)
        other_order, _ = tuning.plan_patch(self.after, curves)
        self.assertEqual(repaired, other_order)

    def test_combined_fix_exact_scope_and_idempotence(self):
        result, receipt = repair.repair_xbe(self.before)
        self.assertEqual(repair.sha(result), repair.COMBINED_SHA256)
        self.assertEqual(receipt["changed_bytes"], 333)
        self.assertEqual(books.status(result), "applied")
        self.assertEqual(repair.repair_xbe(result)[0], result)
        allowed = set()
        for row in receipt["scopes"]:
            start = int(row["file_offset"], 16)
            allowed.update(range(start, start + row["size"]))
        differences = {i for i, (a, b) in enumerate(zip(self.before, result)) if a != b}
        self.assertFalse(differences - allowed)
        owner = books.allocation(self.before)
        start, end = owner["raw"] + books.TABLE, owner["raw"] + owner["size"]
        self.assertEqual(self.before[start:end], result[start:end])

    def test_installed_book_prefix_is_read_only_code_with_no_absolute_writes(self):
        # The broad allocator fixture reserves this owner but does not install
        # it. Check the actual repaired v0.4 prefix as well as that union gate.
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage, absolute_writes
        result, _ = repair.repair_xbe(self.before)
        owner = books.allocation(result)
        section = XbeImage(result).section(owner["va"], books.CODE_SIZE)
        self.assertTrue(section.executable)
        self.assertFalse(section.writable)
        writes = absolute_writes(result, [(owner["va"], owner["va"] + books.TABLE)])
        # Existing bounded UTF-16 alias copy targets the caller's EDI buffer.
        # Unknown decoding or any additional/global store must fail this check.
        self.assertEqual(len(writes), 1)
        self.assertIsNone(writes[0]["target"])
        self.assertEqual(writes[0]["size"], 2)
        self.assertTrue(writes[0]["detail"].startswith("rep movsw "))

    def test_combined_fix_commutes_with_each_owner_and_independent_distance(self):
        result, _ = repair.repair_xbe(self.before)
        books_first, _ = books.apply(self.before)
        self.assertEqual(repair.restore_base_moves(books_first)[0], result)
        self.assertEqual(repair.repair_xbe(self.after)[0], result)
        curves = tuning.curves_for(tuning.TuningSettings(85))
        curves.pop("lobspeed")
        staged, _ = tuning.plan_patch(self.before, curves)
        self.assertEqual(repair.repair_xbe(staged)[0], tuning.plan_patch(result, curves)[0])

    def test_cli_unknown_whole_hash_refuses_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source, out, receipt = [folder / name for name in ("source.xbe", "out.xbe", "receipt.json")]
            source.write_bytes(b"foreign")
            run = subprocess.run([sys.executable, str(ROOT / "tools/b765/d2_repair.py"),
                                  str(source), str(out), "--receipt", str(receipt)],
                                 capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("Unexpected source SHA256", run.stderr)
            self.assertFalse(out.exists())
            self.assertFalse(receipt.exists())

    def test_live_phase_challenges_miscalled_forward_boundary_matches_retail(self):
        from tools.b765.d2_passing_probe import sample
        from tools.nfl2k5_back_throws_replay import NativeMachine, Scenario, DEFAULT_XBE, read_retail
        machines = [NativeMachine(read_retail(DEFAULT_XBE)), NativeMachine(self.before)]
        scenario = Scenario("stationary", "slightly_forward", (300, -399), (0, 0), 7)
        for direction in (-1, 1):
            for challenges in (0, 1):
                with self.subTest(direction=direction, challenges=challenges):
                    old, new = [sample(m, scenario, direction, 1, .5, phase=4,
                                       option=challenges, mode=4, referee_random=0.) for m in machines]
                    self.assertEqual(old, new)
                    self.assertEqual(new["kind"], 3 if challenges else 4)
                    self.assertEqual(new["classifier_calls"]["0x235350"], challenges)
                    self.assertEqual(new["classifier_calls"]["0x23687d"], 1)

    def test_native_short_targets_and_kind_boundary_match_retail(self):
        from tools.b765.d2_passing_probe import sample
        from tools.nfl2k5_back_throws_replay import NativeMachine, Scenario, DEFAULT_XBE, read_retail
        machines = [NativeMachine(read_retail(DEFAULT_XBE)), NativeMachine(self.before)]
        for direction in (-1, 1):
            for depth in (-401, -400, -399):
                scenario = Scenario("stationary", "boundary", (300, depth), (0, 0), 7)
                with self.subTest(direction=direction, depth=depth):
                    old, new = [sample(m, scenario, direction, 1, .5) for m in machines]
                    self.assertEqual(old, new)
                    self.assertEqual(new["kind"], 3 if depth < -400 else 4)


if __name__ == "__main__":
    unittest.main()

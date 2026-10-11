"""Pinned native repair, idempotence, scope and refusal checks."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.b77 import v1h_repair as repair

SOURCE = Path(os.environ.get("NFL2K5_V06_XBE", ".scratch/no-v06-input"))


class RefusalTests(unittest.TestCase):
    def test_unknown_input_refuses_before_allocator_or_owner_write(self):
        with patch.object(repair.space, "_seal_scaleout", side_effect=AssertionError("write")):
            with self.assertRaisesRegex(ValueError, "unrecognized"):
                repair.repair(b"not the supplied executable")

    def test_output_never_replaces_different_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "default.xbe"
            repair.write_new(path, b"first")
            repair.write_new(path, b"first")
            with self.assertRaisesRegex(ValueError, "refusing to replace"):
                repair.write_new(path, b"second")
            self.assertEqual(path.read_bytes(), b"first")


@unittest.skipUnless(SOURCE.is_file(), "NFL2K5_V06_XBE must name the private v0.6 executable")
class NativeTests(unittest.TestCase):
    def test_pinned_repair_preserves_f5_and_all_unrelated_reservations(self):
        original = SOURCE.read_bytes()
        result, receipt = repair.repair(original)
        self.assertEqual(repair.sha(result), repair.REPAIRED_SHA256)
        self.assertEqual(receipt["code_padding"], 87)
        self.assertTrue(receipt["scope"]["outside_scope_identical"])
        honors = [r for r in receipt["preserved_reservations"] if r["owner"] == "nfl2k5_honors"]
        self.assertEqual({r["kind"] for r in honors}, {"code", "data"})
        again, replay = repair.repair(result)
        self.assertEqual(again, result)
        self.assertEqual(replay["status"], "already_applied")
        self.assertEqual(replay["scope"]["changed_bytes"], 0)
        damaged = bytearray(original)
        damaged[receipt["code"]["raw"]] ^= 1
        with self.assertRaisesRegex(ValueError, "unrecognized"):
            repair.repair(bytes(damaged))


if __name__ == "__main__":
    unittest.main()

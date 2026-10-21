"""mc2 native repair: pinned inputs only, Studio-equal owner, idempotent replay and declared scope."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.b77 import mc2_repair as repair

SOURCE = Path(os.environ.get("NFL2K5_V061_XBE", ".scratch/no-v061-input"))


class RefusalTests(unittest.TestCase):
    def test_unknown_input_refuses_before_allocator_or_owner_write(self):
        with patch.object(repair.space, "_seal_scaleout", side_effect=AssertionError("write")):
            with self.assertRaisesRegex(ValueError, "unrecognized"):
                repair.repair(b"not the pinned executable")

    def test_pins_are_complete(self):
        for value in (repair.BASE_XBE_SHA256, repair.REPAIRED_XBE_SHA256,
                      repair.BASE_DISC_SHA256, repair.REPAIRED_DISC_SHA256):
            self.assertRegex(value, r"^[0-9a-f]{64}$")


@unittest.skipUnless(SOURCE.is_file(), "NFL2K5_V061_XBE must name the private v0.6.1 (2026-10-13) default.xbe")
class NativeTests(unittest.TestCase):
    def test_repair_matches_studio_owner_and_replays_to_zero(self):
        original = SOURCE.read_bytes()
        result, receipt = repair.repair(original)
        self.assertEqual(repair.sha(result), repair.REPAIRED_XBE_SHA256)
        self.assertTrue(receipt["scope"]["outside_scope_identical"])
        code, state = repair.mode.legacy.allocations(result)
        blob = repair.XbeImage(result).read(code["va"], repair.mode.CODE_SIZE)
        self.assertEqual(blob, repair.studio_owner(result, code, state)[0])
        self.assertEqual(repair.mode.status(result), "applied")
        again, replay = repair.repair(result)
        self.assertEqual(again, result)
        self.assertEqual(replay["scope"]["changed_bytes"], 0)

    def test_foreign_owner_bytes_refuse(self):
        damaged = bytearray(SOURCE.read_bytes())
        code, _state = repair.mode.legacy.allocations(bytes(damaged))
        damaged[code["raw"]] ^= 1
        with self.assertRaisesRegex(ValueError, "unrecognized"):
            repair.repair(bytes(damaged))


if __name__ == "__main__":
    unittest.main()

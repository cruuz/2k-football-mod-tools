"""Pinned real-disc bounded lifecycle proof; never embeds proprietary bytes."""
from pathlib import Path
import os
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.b765 import p2_lifecycle_proof as proof


class LifecycleEvidenceTests(unittest.TestCase):
    def test_foreign_xbe_refuses_before_native_execution(self):
        with self.assertRaisesRegex(ValueError, "exact p1-repaired"):
            proof.prove(b"foreign executable", b"foreign roster")

    def test_real_p1_lifecycle_and_contract_counterexample(self):
        executable = os.environ.get("B765_P2_XBE")
        roster = os.environ.get("B765_P2_ROSTER")
        if not executable or not roster:
            self.skipTest("set B765_P2_XBE and B765_P2_ROSTER to private extracted inputs")
        receipt = proof.prove(Path(executable).read_bytes(), Path(roster).read_bytes())
        timeline = receipt["timeline"]
        self.assertEqual(timeline["week_one"]["active"], 53)
        self.assertEqual(timeline["week_one"]["reserves"], 2)
        self.assertEqual(timeline["after_promotion"]["reserves"], 1)
        self.assertEqual(timeline["next_offseason"]["reserves"], 1)
        self.assertEqual(timeline["next_offseason"]["stage"], 1)
        self.assertEqual(len(timeline["serialized_roster_sha256"]), 3)
        self.assertTrue(timeline["full_active_promotion_refused_without_writes"])
        rollover = receipt["rollover"]
        self.assertEqual([row["remaining"] for row in rollover["before"]], [1, 3, 1, 3])
        self.assertEqual([row["remaining"] for row in rollover["after"]], [1, 3, 0, 2])
        for before, after in zip(rollover["before"], rollover["after"]):
            self.assertEqual(after["years_pro"], before["years_pro"] + 1)
        self.assertIn("allocator union", receipt["sixteen_slot_install_refusal"])


if __name__ == "__main__":
    unittest.main()

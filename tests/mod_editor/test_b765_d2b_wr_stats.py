"""Actual v0.4 receiving stat production, cache lifecycle and text checks."""
from pathlib import Path
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.b765 import d2b_wr_stats_probe as probe

V04 = Path(os.environ.get("B765_D2B_V04_XBE", "/nonexistent-b765-d2b-v04"))
RETAIL = Path(os.environ.get("B765_D2B_RETAIL_XBE", "/nonexistent-b765-d2b-retail"))


@unittest.skipUnless(V04.is_file() and RETAIL.is_file(),
                     "Set B765_D2B_V04_XBE and B765_D2B_RETAIL_XBE to the pinned private native fixtures")
class NativeReceivingStatLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail, cls.shipped = RETAIL.read_bytes(), V04.read_bytes()
        cls.proof = probe.proof(cls.retail, cls.shipped)

    def test_native_producer_cache_and_formatters_agree_with_retail(self):
        result = self.proof
        self.assertEqual(result["native_scenario_count"], 72)
        self.assertEqual(len(result["identical_complete_spans"]), 20)
        self.assertEqual(len(result["identical_selector_neighborhoods"]), 40)
        self.assertEqual(result["substituted_routines"], [])
        cases = result["native_scenarios"]
        before = [{k: v for k, v in case.items() if k != "image"} for case in cases if case["image"] == "retail"]
        after = [{k: v for k, v in case.items() if k != "image"} for case in cases if case["image"] == "v04"]
        self.assertEqual(before, after)
        for case in cases:
            self.assertEqual(case["native_resource_td_column"], case["native_td_column"], case)
        # Only the four installed defensive-try boundaries differ in every
        # executed original-text instruction; none is accepted as untouched.
        scopes = ((0xCB240, 0xCB247), (0xCB2D0, 0xCB2D7),
                  (0x1ECAF0, 0x1ECAF8), (0x1EEA96, 0x1EEA9C))
        self.assertGreater(result["executed_original_text_instruction_count"], 4000)
        for row in result["changed_executed_original_text_instructions"]:
            va = int(row["va"], 16)
            self.assertTrue(any(start <= va and va + row["size"] <= end for start, end in scopes), row)

    def test_append_retraction_and_before_commit_window(self):
        expected = {"before_first_commit": 0, "td_event_recorded_before_stat_commit": 0,
                    "append_first_td": 1, "second_td_before_stat_commit": 1,
                    "append_second_td": 2, "native_rebuild_after_td_retraction": 1}
        for case in self.proof["native_scenarios"]:
            if case["case"] in expected:
                self.assertEqual(case["native_value"], expected[case["case"]], case)
                self.assertEqual(case["native_td_column"], str(expected[case["case"]]), case)

    def test_uncached_scan_other_receivers_and_nonreceiving_tds(self):
        for case in self.proof["native_scenarios"]:
            if case["case"].startswith("uncached_fallback"):
                self.assertEqual(case["native_cache_pointer"], "0x0")
                self.assertEqual(case["native_value"], case["expected_receiving_td"])
            elif case["case"] in ("different_receiver_zero_td", "rushing_lateral_td", "interception_td"):
                self.assertEqual(case["native_value"], 0, case)
            elif case["case"] == "first_receiver_retains_td":
                self.assertEqual(case["native_value"], 1, case)
            if case["native_value"]:
                self.assertTrue(case["receiving_today"].endswith(f", {int(case['native_value'])} TD"), case)
            else:
                self.assertNotIn(" TD", case["receiving_today"], case)

    def test_foreign_native_inputs_refused(self):
        mutated = bytearray(self.shipped)
        mutated[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "Unexpected native evidence input hashes"):
            probe.validate_inputs(self.retail, bytes(mutated))
        with self.assertRaisesRegex(ValueError, "Unexpected native evidence input hashes"):
            probe.validate_inputs(self.shipped, self.retail)


if __name__ == "__main__":
    unittest.main()

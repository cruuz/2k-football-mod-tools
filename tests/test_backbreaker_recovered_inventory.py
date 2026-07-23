"""Tests for the recovered Backbreaker Ghidra-script inventory tool."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import backbreaker_recovered_inventory as inventory  # noqa: E402

TU2_MD5 = "4260a495ab98c6c3608b801628ea2200"
TU0_MD5 = "4d425702e7cbfeec805e73511cb4b69f"


class RecoveredInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inv = inventory.build_inventory()

    def test_all_fifteen_recovered_scripts_are_parsed(self) -> None:
        self.assertEqual(self.inv["script_count"], 15)
        self.assertEqual(self.inv["schema"], "backbreaker_recovered_inventory/v1")

    def test_both_source_revision_pins_are_present(self) -> None:
        self.assertEqual(
            self.inv["source_revision_md5s"], sorted([TU2_MD5, TU0_MD5])
        )

    def test_quarterback_camera_facts_are_recovered(self) -> None:
        active = next(
            script
            for script in self.inv["scripts"]
            if script["script"] == "BackbreakerTU2ActiveCameraTrace.java"
        )
        self.assertEqual(active["expected_md5"], TU2_MD5)
        # The pinned QB vtable word names the camera vtable 0x8205881C.
        meanings = " ".join(word["meaning"] for word in active["words"])
        self.assertIn("0x8205881C", meanings)
        # The 18-slot expected vtable is recovered, including the slot at 0x822D8D88.
        vtable = next(
            array
            for array in active["arrays"]
            if array["name"] == "QB_VTABLE_EXPECTED"
        )
        self.assertEqual(len(vtable["values"]), 18)
        self.assertIn("0x822D8D88", vtable["values"])

    def test_camera_dispatch_trace_pins_the_tu0_build(self) -> None:
        dispatch = next(
            script
            for script in self.inv["scripts"]
            if script["script"] == "BackbreakerCameraDispatchTrace.java"
        )
        self.assertEqual(dispatch["expected_md5"], TU0_MD5)

    def test_totals_are_nonzero(self) -> None:
        totals = self.inv["totals"]
        self.assertGreater(totals["words"], 0)
        self.assertGreater(totals["ranges"], 0)
        self.assertGreater(totals["named_addresses"], 0)
        self.assertGreater(totals["probes"], 0)
        self.assertGreater(totals["arrays"], 0)

    def test_tackle_define_pins_are_recovered(self) -> None:
        tackle = next(
            script
            for script in self.inv["scripts"]
            if script["script"] == "BackbreakerTU2TackleDefineAudit.java"
        )
        pins = {pin["name"]: pin["address"] for pin in tackle["pins"]}
        self.assertEqual(pins.get("tackle_type_store"), "0x823D9B84")
        self.assertEqual(pins.get("tackle_vtable"), "0x8205CAAC")
        self.assertEqual(tackle["pin_count"], 6)


if __name__ == "__main__":
    unittest.main()

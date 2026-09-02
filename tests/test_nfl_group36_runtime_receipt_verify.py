#!/usr/bin/env python3
"""Focused tests for headless Group 36 runtime-receipt reconstruction."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "tools"))
import nfl_group36_runtime_receipt_verify as receipt  # noqa: E402


class Group36RuntimeReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = json.loads(receipt.REPORT.read_bytes())

    def test_frozen_claim_boundary_accepts_only_the_narrow_result(self) -> None:
        receipt.validate_claim_boundary(self.report)
        for key in ("production_ready", "pixel_aligned_matched_pair_proved"):
            changed = copy.deepcopy(self.report)
            changed["claims"][key] = True
            with self.assertRaises(receipt.ReceiptError):
                receipt.validate_claim_boundary(changed)
        changed = copy.deepcopy(self.report)
        changed["runs"]["control"]["runtime"]["authored_wall_visible"] = True
        with self.assertRaisesRegex(receipt.ReceiptError, "visual observation"):
            receipt.validate_claim_boundary(changed)

    def test_retained_workflow_chain_is_exact(self) -> None:
        workflows = receipt.validate_workflows(self.report)
        self.assertEqual(len(workflows), 7)
        self.assertEqual(
            workflows["s42-visible-night-control-workflow.json"]["output"]["sha256"],
            receipt.CONTROL_SHA256,
        )
        self.assertEqual(
            workflows["expanded-wall-s42-visible-night-workflow.json"]["output"]["sha256"],
            receipt.EXPANDED_SHA256,
        )

    def test_chain_boundary_rejects_replay_or_reexecution(self) -> None:
        leaf = "group36_control_matched"
        value = {
            "schema": "nfl2k5_historical_xemu_hdd_chain_verify/v1",
            "leaf": leaf,
            "base_status": "missing",
            "chain_complete": False,
            "guest_content_replayable": False,
            "historical_runtime_reexecuted": False,
            "missing_base_reconstructed": False,
            "substitution_allowed": False,
            "layers": [
                {"id": name, "pin": None if index == 5 else {"sha256": "0" * 64}}
                for index, name in enumerate((
                    leaf, "group36_selection_seed", "group36_root", "scorebug_runtime",
                    "away_cacheclear", "jersey_tset_controller_base",
                ))
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "chain.json"
            path.write_text(json.dumps(value))
            receipt.validate_chain(path, leaf)
            value["guest_content_replayable"] = True
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(receipt.ReceiptError, "causal boundary"):
                receipt.validate_chain(path, leaf)

    def test_verifier_has_no_emulator_or_large_output_path(self) -> None:
        source = (ROOT / "tools/nfl_group36_runtime_receipt_verify.py").read_text()
        self.assertNotIn("subprocess", source)
        self.assertNotIn("flatpak run", source)
        self.assertNotIn("O_WRONLY", source)
        self.assertNotIn("O_CREAT", source)
        self.assertNotIn("PIL", source)


if __name__ == "__main__":
    unittest.main()

"""b77-g2 native repair of the v0.5 default.xbe: scope, determinism, idempotence and refusals.

The real v0.5 executable is read from NFL2K5_V05_XBE (default: the g2 scratch extraction). Tests that need it skip
when it is absent; the stacked/no-op tests only need the pinned retail executable.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_abilities_runtime as abilities
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
from tools.b77 import g2_repair as repair

V05 = Path(os.environ.get("NFL2K5_V05_XBE", str(ROOT / "extracted" / "softdrink-v05" / "default.xbe")))
RETAIL = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", str(ROOT / "extracted"))) / "ESPN NFL 2K5 (USA)/default.xbe"


def sha(data):
    return hashlib.sha256(data).hexdigest()


@unittest.skipUnless(V05.is_file() and sha(V05.read_bytes()) == repair.V05_XBE_SHA256 if V05.is_file() else False,
                     "the v0.5 default.xbe is required")
class V05Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = V05.read_bytes()
        cls.after, cls.receipt = repair.repair_xbe(cls.before, {repair.V05_XBE_SHA256})

    def test_v05_is_recognised_as_the_beta_765_template_with_no_star_rules(self):
        state = abilities.read_settings(self.before)
        self.assertEqual((state["status"], state["revision"]), ("applied", "beta-76.5"))
        self.assertFalse(any(state[k] for k in ("right_stick_stars_only", "charge_stars_only", "button_moves_stars_only")))
        self.assertEqual(sha(abilities.allocation(self.before) and
                             self.before[abilities.allocation(self.before)["raw"]:][:abilities.CODE_SIZE]),
                         abilities.LEGACY_V05_SHA256)

    def test_default_result_is_pinned_and_deterministic(self):
        self.assertEqual(sha(self.after), repair.V05_DEFAULT_RESULT_SHA256)
        again, _ = repair.repair_xbe(self.before, {repair.V05_XBE_SHA256})
        self.assertEqual(again, self.after)
        self.assertEqual(len(self.after), len(self.before))

    def test_settings_after_are_the_softdrink_defaults(self):
        state = abilities.read_settings(self.after)
        self.assertEqual(state["revision"], "star-gate")
        self.assertTrue(state["right_stick_stars_only"] and state["charge_stars_only"])
        self.assertFalse(state["button_moves_stars_only"])
        self.assertEqual(state["star_access"], abilities.DEFAULT_STAR_ACCESS)
        for key in ("lock_right_stick", "lock_special_moves"):
            self.assertFalse(state[key])
        self.assertTrue(state["lock_speedster"])

    def test_scope_only_owner_bytes_and_derived_seals(self):
        scope = self.receipt["scope"]
        self.assertTrue(scope["outside_scope_identical"])
        allocation = abilities.allocation(self.before)
        owner = range(allocation["raw"], allocation["raw"] + allocation["size"])
        changed = [i for i, (a, b) in enumerate(zip(self.before, self.after)) if a != b]
        self.assertEqual(len(changed), scope["changed_bytes"])
        derived = [i for i in changed if i not in owner]
        # only seals: allocator SHA-256 fields and per-section SHA-1 fields, never code or data
        self.assertLess(len(derived), 200)
        self.assertEqual(self.receipt["touched_disc_files"], ["default.xbe"])
        self.assertTrue(self.receipt["hooks_unchanged"])
        self.assertTrue(self.receipt["allocator_requests_unchanged"])

    def test_hooks_are_byte_identical(self):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        before, after = XbeImage(self.before), XbeImage(self.after)
        for name, (va, old) in abilities.HOOKS.items():
            self.assertEqual(before.read(va, len(old)), after.read(va, len(old)), name)

    def test_idempotent_and_stackable(self):
        again, receipt = repair.repair_xbe(self.after, {repair.V05_XBE_SHA256, sha(self.after)})
        self.assertEqual(again, self.after)
        self.assertTrue(receipt["already_applied"])
        stacked = bytearray(self.before)
        # an unrelated owner's accepted output hash is honoured only when listed
        with self.assertRaises(ValueError):
            repair.repair_xbe(bytes(stacked), {"0" * 64})

    def test_other_settings_install_and_read_back(self):
        out, _ = repair.repair_xbe(self.before, {repair.V05_XBE_SHA256}, right_stick_stars_only=False,
                                   charge_stars_only=False, button_moves_stars_only=True,
                                   star_access=("none", "charge", "flicks", "stick_hurdle"))
        state = abilities.read_settings(out)
        self.assertEqual((state["right_stick_stars_only"], state["charge_stars_only"], state["button_moves_stars_only"]),
                         (False, False, True))
        self.assertEqual(state["star_access"], ("none", "charge", "flicks", "stick_hurdle"))

    def test_refuses_tampered_owner_or_hash(self):
        allocation = abilities.allocation(self.before)
        tampered = bytearray(self.before)
        tampered[allocation["raw"] + 700] ^= 0xFF
        with self.assertRaises(ValueError):
            repair.repair_xbe(bytes(tampered), None)
        with self.assertRaises(ValueError):
            repair.repair_xbe(self.before, {"f" * 64})
        with self.assertRaises(ValueError):
            repair.repair_xbe(self.before[:-1], None)

    def test_cli_writes_new_files_and_refuses_overwriting_different_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            self.assertEqual(repair.main(["--xbe", str(V05), "--out-dir", str(out)]), 0)
            self.assertEqual(sha((out / "default.xbe").read_bytes()), repair.V05_DEFAULT_RESULT_SHA256)
            receipt = json.loads((out / "g2_receipt.json").read_text())
            self.assertEqual(receipt["files"]["default.xbe"]["after_sha256"], repair.V05_DEFAULT_RESULT_SHA256)
            self.assertEqual(repair.main(["--xbe", str(V05), "--out-dir", str(out)]), 0)       # identical: accepted
            with self.assertRaises(ValueError):
                repair.main(["--xbe", str(V05), "--out-dir", str(out), "--no-charge-stars-only"])


@unittest.skipUnless(RETAIL.is_file() and sha(RETAIL.read_bytes()) == RETAIL_SHA256, "pinned retail XBE required")
class StackedTests(unittest.TestCase):
    def test_star_gate_input_with_the_same_settings_is_a_recorded_noop(self):
        retail = RETAIL.read_bytes()
        gated = abilities.apply(retail, right_stick_stars_only=True, charge_stars_only=True)[0]
        again, receipt = repair.repair_xbe(gated, None)
        self.assertEqual(again, gated)
        self.assertTrue(receipt["already_applied"])

    def test_star_gate_input_with_other_settings_changes_only_the_owner_allocation(self):
        retail = RETAIL.read_bytes()
        gated = abilities.apply(retail, right_stick_stars_only=True)[0]
        out, receipt = repair.repair_xbe(gated, None, charge_stars_only=True)
        self.assertTrue(receipt["scope"]["outside_scope_identical"])
        self.assertEqual(abilities.read_settings(out)["charge_stars_only"], True)
        self.assertLess(receipt["owner_changed_bytes"], 40)

    def test_retail_is_refused(self):
        with self.assertRaises(ValueError):
            repair.repair_xbe(RETAIL.read_bytes(), None)


if __name__ == "__main__":
    unittest.main()

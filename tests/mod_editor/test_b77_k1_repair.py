"""b77-k1: the native repair of the v0.5 default.xbe (tools/b77/k1_repair.py).

The v0.5 disc is private, so the retail executable stands in for "an accepted input" by passing its hash; the
repair works on the bytes it owns, so the proof (declared ranges only, idempotent, refuses foreign input) is the same.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_name_keyboard as nk
from mod_editor.core.nfl2k5_practice_squad import RETAIL_SHA256

SCRIPT = ROOT / "tools" / "b77" / "k1_repair.py"
spec = importlib.util.spec_from_file_location("b77_k1_repair", SCRIPT)
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"


class ConstantTests(unittest.TestCase):
    def test_pinned_hashes_are_well_formed_and_distinct(self):
        for value in (repair.V05_XBE_SHA256, repair.V05_FIXED_XBE_SHA256):
            self.assertRegex(value, r"^[0-9a-f]{64}$")
        self.assertNotEqual(repair.V05_XBE_SHA256, repair.V05_FIXED_XBE_SHA256)
        self.assertEqual(repair.DISC_FILE, "default.xbe")

    def test_scope_receipt_refuses_changes_outside_the_declared_spans(self):
        before = bytes(range(64))
        after = bytearray(before)
        after[10] ^= 1
        self.assertTrue(repair.scope_receipt(before, bytes(after), [(8, 4)])["outside_scope_identical"])
        with self.assertRaises(ValueError):
            repair.scope_receipt(before, bytes(after), [(20, 4)])
        with self.assertRaises(ValueError):
            repair.scope_receipt(before, bytes(after) + b"\0", [(8, 4)])
        with self.assertRaises(ValueError):
            repair.scope_receipt(before, bytes(after), [(60, 8)])


@unittest.skipUnless(XBE.is_file(), "pinned retail default.xbe required")
class RepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        assert hashlib.sha256(cls.retail).hexdigest() == RETAIL_SHA256
        cls.accepted = {RETAIL_SHA256}
        cls.after, cls.receipt = repair.repair(cls.retail, cls.accepted)

    def test_output_is_the_studio_patch_and_the_scope_is_exact(self):
        self.assertEqual(self.after, nk.apply(self.retail)[0])
        scope = self.receipt["scope"]
        self.assertTrue(scope["outside_scope_identical"])
        self.assertEqual(scope["before_sha256"], RETAIL_SHA256)
        self.assertEqual(scope["after_sha256"], hashlib.sha256(self.after).hexdigest())
        self.assertEqual(scope["size"], len(self.retail))
        sizes = sorted(row["size"] for row in scope["scope"])
        self.assertEqual(sizes, [4, 20, 20, 224])
        self.assertEqual(self.receipt["touched_disc_files"], ["default.xbe"])
        self.assertTrue(self.receipt["section_digests_valid"])
        self.assertFalse(self.receipt["runtime_witnessed"])
        self.assertEqual(self.receipt["character_lists_after"], {"first_name": nk.NAME_CHARSET, "last_name": nk.NAME_CHARSET})
        self.assertEqual(self.receipt["character_lists_before"], {"first_name": nk.RETAIL_FIRST, "last_name": nk.RETAIL_LAST})

    def test_replay_is_a_recorded_noop(self):
        again, receipt = repair.repair(self.after, self.accepted | {hashlib.sha256(self.after).hexdigest()})
        self.assertEqual(again, self.after)
        self.assertTrue(receipt["already_applied"])
        self.assertEqual(receipt["scope"]["changed_bytes"], 0)

    def test_unexpected_input_hash_and_foreign_bytes_are_refused(self):
        with self.assertRaises(ValueError):
            repair.repair(self.retail, {repair.V05_XBE_SHA256})
        tampered = bytearray(self.retail)
        tampered[nk.rdata.offset_of(tampered, 0x248DA0) + 3] ^= 1           # inside the pinned key handler
        with self.assertRaises(ValueError):
            repair.repair(bytes(tampered), {hashlib.sha256(bytes(tampered)).hexdigest()})

    def test_command_line_writes_new_files_refuses_to_replace_and_replays(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source, out = tmp / "in" / "default.xbe", tmp / "out"
            source.parent.mkdir()
            source.write_bytes(self.retail)
            command = [sys.executable, str(SCRIPT), "--xbe", str(source), "--out-dir", str(out),
                       "--expected-xbe-sha256", RETAIL_SHA256]
            run = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout)["status"], "DONE")
            self.assertEqual((out / "default.xbe").read_bytes(), self.after)
            self.assertEqual(source.read_bytes(), self.retail)
            receipt = json.loads((out / "k1_receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["schema"], repair.SCHEMA)
            replay = subprocess.run(command, capture_output=True, text=True)         # identical output is accepted
            self.assertEqual(replay.returncode, 0, replay.stderr)
            (out / "default.xbe").write_bytes(b"different")
            refused = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("refusing to replace", refused.stderr)
            same_dir = subprocess.run([sys.executable, str(SCRIPT), "--xbe", str(source), "--out-dir", str(source.parent),
                                       "--expected-xbe-sha256", RETAIL_SHA256], capture_output=True, text=True)
            self.assertNotEqual(same_dir.returncode, 0)


if __name__ == "__main__":
    unittest.main()

"""Native v0.5 PLAY repair (b77 job p13): scopes, idempotence, refusals, lint and native checks.

Needs the extracted SOFTDRINK 2K28 v0.5 PACK0 PLAY entries (play-<entry>.bin) in
P13_V05_PLAY_DIR; the native checks also need that disc's default.xbe in P13_V05_XBE.
"""
from pathlib import Path
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_playbook_inspector as inspector
from mod_editor.core import nfl2k5_playbook_lint as lint
from tools.b77 import p13_repair as repair

PLAY_DIR = Path(os.environ.get("P13_V05_PLAY_DIR", "/home/noah/2k-worktrees/.b77-scratch/p13/v05"))
XBE = Path(os.environ.get("P13_V05_XBE", str(PLAY_DIR / "default.xbe")))
MANIFEST = json.loads(repair.MANIFEST.read_text())
TEAM_ENTRIES = [int(k) for k, v in MANIFEST["books"].items() if v["plays"]]
HAVE_BOOKS = all((PLAY_DIR / f"play-{k}.bin").is_file() for k in MANIFEST["books"])


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ManifestShape(unittest.TestCase):
    def test_manifest_covers_every_shipped_book_and_changes_only_team_books(self):
        self.assertEqual(len(MANIFEST["books"]), 69)
        changed = {k for k, v in MANIFEST["books"].items() if v["before_sha256"] != v["after_sha256"]}
        self.assertEqual(len(changed), 32)
        self.assertTrue(all(307 <= int(k) <= 342 and int(k) not in (318, 320, 334, 335) for k in changed))
        for k, v in MANIFEST["books"].items():
            self.assertLessEqual(v["new_node_count"], 3500)
            if k not in changed:
                self.assertEqual(v["plays"], 0)


@unittest.skipUnless(HAVE_BOOKS, "Set P13_V05_PLAY_DIR to the extracted v0.5 PLAY entries")
class RealBooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = {int(k): (PLAY_DIR / f"play-{k}.bin").read_bytes() for k in MANIFEST["books"]}
        cls.out = {k: repair.repair_resource(v, k) for k, v in cls.raw.items()}

    def test_known_hashes_scopes_and_idempotence(self):
        for k, raw in self.raw.items():
            with self.subTest(entry=k):
                result, receipt = self.out[k]
                row = MANIFEST["books"][str(k)]
                self.assertEqual((sha(raw), sha(result)), (row["before_sha256"], row["after_sha256"]))
                again, second = repair.repair_resource(result, k)
                self.assertEqual(again, result)
                self.assertEqual((second["status"], second["changed_bytes"]), ("already_applied", 0))
                changed = [i for i in range(len(raw)) if raw[i] != result[i]]
                for offset in changed:
                    self.assertTrue(any(int(s["file_offset"], 16) <= offset < int(s["file_offset"], 16) + s["size"]
                                        for s in receipt["scopes"]), offset)
                self.assertEqual(len(result), len(raw))

    def test_repaired_team_books_lint_clean_for_p1_to_p3(self):
        for k in TEAM_ENTRIES:
            with self.subTest(entry=k):
                report = lint.lint_resource(self.out[k][0], str(k))
                self.assertEqual([f.code for f in report.findings if f.code in lint.EXECUTION_CODES], [])
                before = lint.lint_resource(self.raw[k], str(k)).counts()
                self.assertTrue(set(before) & {"HANDOFF_FAR", "CHECKDOWN_BACKWARD", "SCREEN_DEPTH_MARGIN",
                                               "SCREEN_SIDE_CROSS"})

    def test_jax_video_play_is_retargeted_to_the_tight_end(self):
        result = self.out[323][0]
        book = inspector.parse_playbook_resource(result)
        self.assertEqual(book.plays[231].name, "24 End Around")
        view = next(v for v in lint.resource_views(result) if v.play == 231)
        self.assertEqual(lint.handoff_pairs(view), [(0, 6, 2, 1)])
        self.assertLess(lint.separation_yd(view, 0, 6), 7.1)
        old = next(v for v in lint.resource_views(self.raw[323]) if v.play == 231)
        self.assertEqual(lint.handoff_pairs(old)[0][1], 8)
        self.assertGreater(lint.separation_yd(old, 0, 8), 18)

    def test_unknown_stacked_and_damaged_inputs(self):
        raw = self.raw[310]
        with self.assertRaisesRegex(ValueError, "Unexpected PLAY input SHA256"):
            repair.repair_resource(raw[:-1] + b"\x01", 310)
        with self.assertRaisesRegex(ValueError, "Unknown"):
            repair.repair_resource(raw, 999)
        book = inspector.parse_playbook_resource(raw)
        tail = 32 + inspector.NODE_BASE + book.node_count * inspector.NODE_SIZE
        dirty = bytearray(raw); dirty[tail + 3] = 0x55
        with self.assertRaisesRegex(ValueError, "nonzero node-pool allocation tail"):
            repair.repair_resource(bytes(dirty), 310, expected_input_sha256=sha(bytes(dirty)))
        stacked = bytearray(raw); stacked[32 + 0x10900] ^= 0       # same bytes, explicit stacked hash path
        result, receipt = repair.repair_resource(bytes(stacked), 310, expected_input_sha256=sha(bytes(stacked)))
        self.assertEqual(result, self.out[310][0])

    def test_cli_writes_exclusive_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            out, rec = Path(temp) / "out.bin", Path(temp) / "rec.json"
            args = [sys.executable, str(ROOT / "tools/b77/p13_repair.py"), str(PLAY_DIR / "play-323.bin"), str(out),
                    "--entry-id", "323", "--receipt", str(rec)]
            done = subprocess.run(args, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(out.read_bytes(), self.out[323][0])
            self.assertEqual(json.loads(rec.read_text())["after_sha256"], MANIFEST["books"]["323"]["after_sha256"])
            self.assertNotEqual(subprocess.run(args, capture_output=True, text=True).returncode, 0)


@unittest.skipUnless(HAVE_BOOKS and XBE.is_file(), "Set P13_V05_XBE to the v0.5 default.xbe")
class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from tools.b77 import p13_handoff_probe as probe
        except ImportError as exc:                    # pragma: no cover - Unicorn missing
            raise unittest.SkipTest(str(exc))
        cls.probe = probe
        cls.machine = probe.HandoffMachine(XBE.read_bytes())
        cls.before = (PLAY_DIR / "play-323.bin").read_bytes()
        cls.after = repair.repair_resource(cls.before, 323)[0]

    def test_native_exchange_plan_before_and_after(self):
        old = next(v for v in lint.resource_views(self.before) if v.play == 231 and v.formation == 23)
        new = next(v for v in lint.resource_views(self.after) if v.play == 231 and v.formation == 23)
        a = self.probe.plan(self.machine, old, 0, 8)
        b = self.probe.plan(self.machine, new, 0, 6)
        self.assertEqual((a["giver_callback"], b["giver_callback"]), ("0x300810", "0x300810"))
        self.assertGreater(a["giver_travel_yd"], 10)
        self.assertGreater(a["target_travel_yd"], 9.5)
        self.assertLessEqual(b["giver_travel_yd"], lint.RETAIL_REVERSE_GIVER_TRAVEL_YD)
        self.assertLessEqual(b["target_travel_yd"], lint.RETAIL_REVERSE_RUNNER_TRAVEL_YD)

    def test_closed_loop_release_time(self):
        new = next(v for v in lint.resource_views(self.after) if v.play == 231 and v.formation == 23)
        result = self.probe.simulate(self.machine, new, 0, 6)
        self.assertIsNotNone(result["released"])
        self.assertLess(result["released"]["t"], 1.2)
        self.assertLess(result["released"]["separation_yd"], 1.7)

    def test_repaired_books_pass_the_native_scoring_gate(self):
        from mod_editor.core import nfl2k5_play_scoring as scoring
        xbe = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe")
        if not xbe.is_file():
            self.skipTest("retail default.xbe for the scoring gate is unavailable")
        for k in (310, 323, 329):
            with self.subTest(entry=k):
                result = scoring.require_safe(repair.repair_resource((PLAY_DIR / f"play-{k}.bin").read_bytes(), k)[0], xbe)
                self.assertEqual(result["faults"], [])


if __name__ == "__main__":
    unittest.main()

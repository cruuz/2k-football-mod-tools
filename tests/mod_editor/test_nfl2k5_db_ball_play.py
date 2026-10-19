"""Defender ball-play writer: exact bytes, replay and refusal. No game boot, no disc build.

The pinned USA retail default.xbe is read from NFL2K5_RETAIL_EXTRACTION (skipped when absent); NFL2K5_B775_XBE
optionally names the extracted b775 test-disc default.xbe.
"""
from pathlib import Path
import shutil
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_db_ball_play as ball
from mod_editor.core import nfl2k5_db_ball_play_code as assembly
from mod_editor.core import nfl2k5_cpu_qb_reads as reads
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe, repin_edit
from tests.mod_editor.test_nfl2k5_cpu_qb_reads import b775_xbe


class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.final, cls.receipt = ball.apply(cls.retail)

    def test_sites_code_and_receipt(self):
        self.assertEqual(ball.status(self.retail), "retail")
        self.assertEqual(ball.status(self.final), "applied")
        image = XbeImage(self.final)
        code = ball.allocation(self.final)["va"]
        self.assertEqual(image.read(code, ball.CODE_SIZE), ball.code_for(code))
        raw = image.read(0x2E978C, 9)
        self.assertEqual(raw[0], 0xE8)
        self.assertEqual(0x2E978C + 5 + struct.unpack_from("<i", raw, 1)[0], code + assembly.LABELS["point"])
        self.assertEqual(raw[5:], b"\x90" * 4)
        self.assertEqual(struct.unpack("<f", image.read(0x2E7463, 4))[0], 1.0)
        self.assertEqual(image.read(0x2E7462, 1), b"\x68")
        self.assertEqual(self.receipt["runtime_witnessed"], False)
        self.assertEqual({e["label"] for e in self.receipt["edits"]}, {"catch_point", "reaction_throttle"})
        self.assertEqual(space.status(self.final), "applied")

    def test_replay_and_foreign_refusal_before_mutation(self):
        again, receipt = ball.apply(self.final)
        self.assertEqual(again, self.final)
        self.assertEqual(receipt["status"], "already_applied")
        code = ball.allocation(self.final)["va"]
        for label, (va, content) in {"hook": (0x2E978C, b"\xe8\x00\x00\x00\x00"),
                                     "throttle": (0x2E7463, struct.pack("<f", 0.9)),
                                     "half": (0x2E7463, struct.pack("<f", 0.84)),
                                     "code": (code + 2, b"\x90"),
                                     "behavior 37": (0x2E9620, b"\x90"),
                                     "reaction task": (0x2E7300, b"\x90"),
                                     "catch store": (0x1F3B03, b"\x90")}.items():
            bad = repin_edit(self.final, va, content)
            self.assertEqual(ball.status(bad), "foreign", label)
            with self.assertRaises(ValueError):
                ball.apply(bad)
        retail_bad = repin_edit(self.retail, 0x2E7463, struct.pack("<f", 0.9))
        self.assertEqual(ball.status(retail_bad), "foreign")

    def test_composes_after_cpu_qb_reads_in_late_order(self):
        first, _ = reads.apply(self.retail, zone_windows=True, recheck=True)
        final, _ = ball.apply(first)
        self.assertEqual((reads.status(final), ball.status(final)), ("applied", "applied"))
        self.assertEqual(reads.allocations(final), reads.allocations(first))
        # the late order is fixed: reads before ball play
        with self.assertRaises(ValueError):
            reads.apply(self.final, recheck=True)

    @unittest.skipUnless(shutil.which("as"), "GNU as is required to reproduce the byte template")
    def test_assembler_reproduces_shipped_bytes(self):
        from nfl2k5_cpu_ai_assemble import template
        self.assertEqual((ROOT / "mod_editor/core/nfl2k5_db_ball_play_code.py").read_text(encoding="utf-8"),
                         template("nfl2k5_db_ball_play"))


class B775Tests(unittest.TestCase):
    def test_b775_late_append_keeps_every_allocation(self):
        b775 = b775_xbe()
        first, _ = reads.apply(b775, zone_windows=True, recheck=True)
        final, _ = ball.apply(first)
        before = {(a["owner"], a["kind"]): a for a in space.layout(first)["allocations"]}
        after = {(a["owner"], a["kind"]): a for a in space.layout(final)["allocations"]}
        for key, row in before.items():
            if key[0] != space.DIRECTORY_OWNER:
                self.assertEqual(after[key], row, key)
        self.assertEqual(ball.status(final), "applied")
        self.assertEqual(reads.status(final), "applied")


if __name__ == "__main__":
    unittest.main()

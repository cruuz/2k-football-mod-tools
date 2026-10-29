"""b779 up2: the released v0.7 game writes a fresh franchise save of 881,340 bytes whose Player Progress footer
is all zero ("no weekly history yet"). Studio must read it, change nothing, and Franchise > Upgrade must take it."""
from __future__ import annotations

import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_college_check as college  # noqa: E402
from mod_editor.core import nfl2k5_franchise_save as fs  # noqa: E402
from mod_editor.core import nfl2k5_franchise_upgrade as up  # noqa: E402
from mod_editor.core import nfl2k5_my_career_save as career  # noqa: E402
from mod_editor.core import nfl2k5_player_progression as pp  # noqa: E402
from mod_editor.core import nfl2k5_save_rost as sr  # noqa: E402
from mod_editor.core import nfl2k5_save_writer as writer  # noqa: E402
from tests.mod_editor.test_franchise_upgrade import capacity_fixture  # noqa: E402
from tests.mod_editor.test_nfl2k5_franchise_save import synthetic_franchise  # noqa: E402

ZERO = bytes(pp.FOOTER_SIZE)
#: a real game-written 881,340-byte save made with the released v0.7 disc in xemu; kept in scratch, never in the repo
REAL = Path(os.environ.get(
    "B779_UP2_REAL_SAVE",
    "/home/noah/2k-worktrees/.b77-scratch/b779/up2/fixture/v07_franchise1/SAVEGAME.DAT"))


def career_block(payload: bytes) -> bytes:
    doc = sr.decode(payload)
    player = doc.players[0].offset
    block = bytearray(career.SIZE)
    block[:8] = career.MAGIC
    struct.pack_into("<HH", block, 8, 1, career.SIZE)
    block[16] = 1
    block[36:40] = bytes((3, 0, 0, payload[player + 0x35]))
    for field, stored in ((0, 44), (16, 48), (20, 52)):
        struct.pack_into("<I", block, stored, doc.rel(player + field) - doc.layout.root)
    block[56:60] = payload[player + 4:player + 8]
    struct.pack_into("<I", block, 60, career.word(payload, player + 0x18) & career.BIRTH_MASK)
    block[74] = 255
    return career.seal(block)


class ZeroFooterCodec(unittest.TestCase):
    def test_a_zero_region_at_every_footer_size_means_no_history_yet(self):
        for size in pp.PPG_SAVE_SIZES + pp.PPG_CAREER_SAVE_SIZES:
            payload = bytearray(size)
            payload[:8] = b"native!!"                    # native bytes are not part of the footer
            at = size - pp.FOOTER_SIZE
            self.assertEqual(pp.footer_start(bytes(payload)), at, size)
            self.assertTrue(pp.is_empty_footer(bytes(payload)))
            record = pp.read_footer(bytes(payload))
            self.assertFalse(record["present"])
            self.assertTrue(record["empty"])
            self.assertEqual(record["footer_offset"], at)
            self.assertEqual(record["slots"], [])
            self.assertEqual(pp.strip_footer(bytes(payload)), (bytes(payload[:at]), ZERO))

    def test_only_a_known_total_size_and_a_fully_zero_region_count(self):
        payload = bytearray(pp.RETAIL_SAVE_SIZE + pp.FOOTER_SIZE)
        payload[-1] = 1                                  # one stray byte: not a footer
        self.assertIsNone(pp.footer_start(bytes(payload)))
        self.assertFalse(pp.is_empty_footer(bytes(payload)))
        odd = bytes(pp.RETAIL_SAVE_SIZE + pp.FOOTER_SIZE + 4)
        self.assertIsNone(pp.footer_start(odd))          # not a known container length
        for native in pp.NATIVE_SAVE_SIZES:
            self.assertIsNone(pp.footer_start(bytes(native)))   # a native save has no footer, zero or not
        self.assertIsNone(pp.footer_start(bytes(10)))

    def test_a_stamped_footer_still_reads_and_a_zero_one_can_not_be_appended_over(self):
        native = bytes(pp.RETAIL_SAVE_SIZE)
        grown, _ = pp.append_footer(native, pp.empty_footer(year=2027, team=3))
        self.assertEqual(pp.footer_start(grown), pp.RETAIL_SAVE_SIZE)
        self.assertFalse(pp.is_empty_footer(grown))
        self.assertTrue(pp.read_footer(grown)["present"])
        with self.assertRaises(pp.ProgressionError):
            pp.append_footer(native + ZERO, pp.empty_footer())

    def test_advance_week_starts_a_baseline_from_a_zero_footer(self):
        roster = [{"slot": s, "pbp_id": 1 + s, "position": 0, "jersey": s, "overall": 70,
                   "ratings": [60] * pp.RATING_COUNT} for s in range(pp.TEAM_SLOTS)]
        footer = pp.advance_week(ZERO, roster, week=1, team=2, year=2027)
        record = pp.read_footer(footer)
        self.assertTrue(record["present"])
        self.assertEqual(record["header"]["year"], 2027)


class ZeroFooterSaves(unittest.TestCase):
    def setUp(self):
        self.native, self.disc = capacity_fixture()      # a synthetic v0.7 capacity save (847,020 bytes)
        self.save = self.native + ZERO
        self.assertEqual(len(self.save), 881340)

    def test_franchise_save_reads_and_returns_the_same_bytes(self):
        loaded = fs.FranchiseSave(self.save)
        self.assertEqual(loaded.ppg_offset, len(self.native))
        self.assertIsNone(loaded.career_offset)
        self.assertEqual(loaded.to_bytes(), self.save)
        self.assertEqual(fs.FranchiseSave(self.native).header.display_year, loaded.header.display_year)
        self.assertTrue(fs.is_franchise_save(self.save))

    def test_save_writer_and_year_reader_see_a_franchise(self):
        self.assertEqual(writer.save_kind(self.save), "franchise")
        self.assertEqual(writer.read_franchise_fields(self.save), writer.read_franchise_fields(self.native))

    def test_broken_native_framing_before_the_footer_is_still_refused(self):
        corrupt = bytearray(self.save)
        corrupt[0x2E0:0x2E4] = b"XXXX"
        with self.assertRaises(fs.FranchiseSaveError):
            fs.FranchiseSave(bytes(corrupt))

    def test_college_check_repairs_around_the_zero_footer(self):
        scan = college.scan(self.save)
        self.assertEqual(scan.findings, ())
        fixed, receipt = college.repair(self.save)
        self.assertEqual(fixed, self.save)
        self.assertEqual(receipt["changed"], 0)

    def test_the_team_history_step_keeps_the_zero_footer_and_the_length(self):
        out, receipt = up.upgrade_team_history(self.save, self.disc)
        self.assertEqual(len(out), len(self.save))
        self.assertEqual(out[-pp.FOOTER_SIZE:], ZERO)
        self.assertEqual(receipt["used_after"], receipt["used_before"] + 1)

    def test_the_twin_with_a_mycareer_block_reads_too(self):
        base = synthetic_franchise()
        with_career, _ = career.append(base, career_block(base))
        save = with_career + ZERO
        self.assertEqual(len(save), 754492)
        self.assertEqual(pp.footer_start(save), len(with_career))
        self.assertEqual(career.native_size(save), len(base))
        career.read(save)
        loaded = fs.FranchiseSave(save)
        self.assertEqual(loaded.career_offset, len(base))
        self.assertEqual(loaded.to_bytes(), save)
        self.assertEqual(writer.save_kind(save), "franchise")


class RealV07Save(unittest.TestCase):
    """The real 881,340-byte save the released v0.7 disc wrote in xemu (skipped when the scratch file is absent)."""

    @classmethod
    def setUpClass(cls):
        if not REAL.is_file():
            raise unittest.SkipTest("the real v0.7 save is only kept in scratch")
        cls.data = REAL.read_bytes()

    def test_it_is_the_shape_the_players_have(self):
        self.assertEqual(len(self.data), 881340)
        self.assertFalse(any(self.data[-pp.FOOTER_SIZE:]))

    def test_studio_reads_it_and_upgrade_validation_accepts_it(self):
        loaded = fs.FranchiseSave(self.data)
        self.assertEqual(loaded.to_bytes(), self.data)
        self.assertEqual(loaded.ppg_offset, 847020)
        self.assertEqual(writer.save_kind(self.data), "franchise")
        report = up.validate_save(self.data)
        self.assertEqual(report["players"], 3299)
        self.assertGreaterEqual(report["exhibition_depth_lock_conflicts_not_enforced"], 0)
        self.assertEqual(college.scan(self.data).findings, ())


if __name__ == "__main__":
    unittest.main()

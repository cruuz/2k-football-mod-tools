"""b778-pg2: the Player Progression weekly-change record adapter (offline contract).

The adapter is pure Python: a provisional record layout, a fixed save-resident codec, and the
old-save behaviour. The native week-advance hook and the Front Office screen are the deferred final
wiring; these tests prove the record the two sides share is correct and that an old save (no record)
is read as an empty history without touching the save.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.core import nfl2k5_player_progression as pp  # noqa: E402

SAVE = Path("/home/noah/2k-worktrees/.b77-scratch/b778/pc2/src_mynfl3/SAVEGAME.DAT")


class CodecTests(unittest.TestCase):
    def test_empty_record_and_header(self) -> None:
        rec = pp.empty_record(2027, 3)
        self.assertEqual(len(rec), pp.RECORD_SIZE)
        self.assertTrue(pp.is_present(rec))
        self.assertEqual(pp.header_of(rec), {"base_year": 2027, "team_index": 3, "week_count": 0})
        self.assertEqual(pp.decode_weeks(rec), [[0] * pp.TEAM_SLOTS for _ in range(pp.WEEK_SLOTS)])

    def test_encode_decode_round_trip(self) -> None:
        weeks = [[0] * pp.TEAM_SLOTS for _ in range(4)]
        weeks[0][0], weeks[1][0], weeks[2][0], weeks[3][0] = 80, 82, 81, 85
        weeks[1][64] = 99
        rec = pp.encode_weeks(weeks, base_year=2026, team_index=7)
        self.assertEqual(pp.header_of(rec)["week_count"], 4)
        decoded = pp.decode_weeks(rec)
        self.assertEqual([decoded[w][0] for w in range(4)], [80, 82, 81, 85])
        self.assertEqual(decoded[1][64], 99)
        self.assertEqual(decoded[4][0], 0)

    def test_plan_rows_are_screen_ready(self) -> None:
        weeks = [[0] * pp.TEAM_SLOTS for _ in range(4)]
        weeks[0][2], weeks[1][2], weeks[2][2], weeks[3][2] = 90, 88, 90, 93
        rows = pp.plan_rows(weeks)
        self.assertEqual(rows[2], {"slot": 2, "opening_overall": 90, "weekly_changes": [-2, 2, 3]})

    def test_screen_rows_join_position_name_and_current_overall(self) -> None:
        weeks = [[0] * pp.TEAM_SLOTS for _ in range(4)]
        weeks[0][2], weeks[1][2], weeks[2][2], weeks[3][2] = 90, 88, 90, 93
        weeks[0][40], weeks[1][40] = 70, 71
        roster = [{"slot": 2, "position": "QB", "name": "Test QB"},
                  {"slot": 40, "position": "LB", "name": "Test LB"},
                  {"slot": 5, "position": "K", "name": "No History"}]
        rows = pp.screen_rows(weeks, roster)
        self.assertEqual(rows[0], {"slot": 2, "position": "QB", "name": "Test QB",
                                   "opening_overall": 90, "current_overall": 93,
                                   "weekly_changes": [-2, 2, 3]})
        self.assertEqual(rows[1]["current_overall"], 71)
        self.assertEqual(rows[1]["weekly_changes"], [1, None, None])
        self.assertEqual(rows[2]["current_overall"], 0)
        self.assertEqual(rows[2]["weekly_changes"], [None, None, None])
        self.assertEqual(pp.SCREEN_SCHEMA, "nfl2k5_player_progression/screen-v1")
        empty = pp.screen_rows([], [{"slot": 2, "position": "QB", "name": "Old Save"}])
        self.assertEqual(empty[0]["current_overall"], 0)
        self.assertEqual(empty[0]["weekly_changes"], [])
        with self.assertRaises(pp.ProgressionError):
            pp.screen_rows(weeks, [{"slot": 2, "position": "QB"}])
        with self.assertRaises(pp.ProgressionError):
            pp.screen_rows(weeks, roster + [{"slot": 2, "position": "QB", "name": "Dup"}])

    def test_bad_records_are_refused(self) -> None:
        rec = pp.empty_record(2027, 0)
        with self.assertRaises(pp.ProgressionError):
            pp.decode_weeks(rec[:-1])                       # wrong size
        bad = bytearray(rec)
        bad[0] = ord("X")
        with self.assertRaises(pp.ProgressionError):
            pp.decode_weeks(bytes(bad))                     # bad magic
        with self.assertRaises(pp.ProgressionError):
            pp.encode_weeks([[0] * (pp.TEAM_SLOTS - 1)], base_year=2027, team_index=0)

    def test_capture_week_is_in_place_and_idempotent(self) -> None:
        payload = bytearray(pp.PROGRESSION_REGION_SIZE + 64)
        baseline = [50] * pp.TEAM_SLOTS
        result, _ = pp.capture_week(bytes(payload), team_index=4, base_year=2027, week=0, overalls=baseline, offset=0)
        overalls = list(baseline)
        overalls[10] = 77
        result, receipt = pp.capture_week(result, team_index=4, base_year=2027, week=1, overalls=overalls, offset=0)
        self.assertEqual(len(result), len(payload))
        self.assertEqual(receipt["save_growth"], 0)
        self.assertEqual(receipt["weeks_recorded"], 2)
        again, again_receipt = pp.capture_week(result, team_index=4, base_year=2027, week=1, overalls=overalls, offset=0)
        self.assertEqual(again, result)
        self.assertEqual(again_receipt["changed_bytes"], 0)
        history = pp.read_history(result, offset=0)
        self.assertTrue(history["has_record"])
        self.assertEqual(history["weeks"][1][10], 77)

    def test_capture_week_refuses_a_foreign_region(self) -> None:
        payload = bytearray(pp.PROGRESSION_REGION_SIZE + 64)
        payload[0] = 0xAB
        with self.assertRaises(pp.ProgressionError):
            pp.capture_week(bytes(payload), team_index=0, base_year=2027, week=1, overalls=[0] * pp.TEAM_SLOTS, offset=0)


@unittest.skipUnless(SAVE.is_file(), "a real franchise save is not on this machine")
class OldSaveTests(unittest.TestCase):
    def test_a_real_save_has_no_record_and_is_unchanged(self) -> None:
        save = SAVE.read_bytes()
        self.assertEqual(len(save), 720_044)
        history = pp.read_history(save)
        self.assertFalse(history["has_record"])
        self.assertEqual(history["weeks"], [])
        # reading never mutates
        self.assertEqual(SAVE.read_bytes(), save)


if __name__ == "__main__":
    unittest.main()

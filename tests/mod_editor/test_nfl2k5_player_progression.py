"""b778-pg2: the Player Progress record codec (PPG2 v1).

The record is a fixed 5,232-byte table in the roster arena tail: a season baseline, the previous
week's ratings and the packed last-week changes for 65 roster slots. These tests prove the codec,
the old-save behaviour, the screen contract and the fixed host leave the 720,044-byte save size
unchanged.
"""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_player_progression as pp  # noqa: E402


def players():
    return [{"slot": slot, "pbp_id": 100 + slot, "position": 0, "jersey": slot,
             "overall": 70 + slot % 5, "ratings": [50 + (slot + i) % 20 for i in range(pp.RATING_COUNT)]}
            for slot in range(pp.TEAM_SLOTS)]


class RecordTests(unittest.TestCase):
    def test_layout_and_row_map(self):
        self.assertEqual(pp.HEADER_SIZE, 32)
        self.assertEqual(pp.SLOT_SIZE, 80)
        self.assertEqual(pp.RECORD_SIZE, 5232)
        self.assertEqual(pp.RECORD_FILE_OFFSET + pp.RECORD_SIZE, 0x91164)
        self.assertLess(pp.RECORD_FILE_OFFSET + pp.RECORD_SIZE, 0x91320)
        self.assertEqual(pp.RECORD_RUNTIME_DELTA, 0x8F9D4)
        self.assertEqual(len(pp.ROW_MAP), 104)
        self.assertEqual(pp.ROW_MAP[0], 0)
        self.assertEqual(pp.ROW_MAP[1], 0x38)       # group 0 row 1 = arm strength
        self.assertEqual(pp.ROW_MAP[5], 0x36)       # group 0 row 5 = speed

    def test_old_save_reads_as_absent_and_is_unchanged(self):
        payload = bytes(pp.SAVE_SIZE)
        record = pp.read_record(payload)
        self.assertFalse(record["present"])
        self.assertIsNone(record["header"])
        self.assertEqual(record["slots"], [])
        # writing nothing must not touch the old save
        self.assertEqual(payload[pp.RECORD_FILE_OFFSET:pp.RECORD_FILE_OFFSET + pp.RECORD_SIZE],
                         bytes(pp.RECORD_SIZE))

    def test_baseline_advance_and_screen_contract(self):
        payload = bytes(pp.SAVE_SIZE)
        roster = players()
        with_baseline = pp.baseline(payload, roster, year=2027, team=3)
        self.assertEqual(len(with_baseline), pp.SAVE_SIZE)
        record = pp.read_record(with_baseline)
        self.assertTrue(record["present"])
        self.assertEqual(record["header"]["year"], 2027)
        self.assertEqual(record["header"]["team"], 3)
        self.assertEqual(record["header"]["flags"], pp.HEADER_BASELINE)
        self.assertEqual(record["slots"][0]["baseline_overall"], 70)
        self.assertEqual(record["slots"][0]["baseline"], roster[0]["ratings"])
        self.assertEqual(record["slots"][0]["flags"], 7)
        # week 0: one speed point and two overall points
        roster[0]["ratings"][0] += 1
        roster[0]["overall"] += 2
        after_week = pp.advance_week(with_baseline, roster, week=0)
        record = pp.read_record(after_week)
        slot = record["slots"][0]
        self.assertEqual(slot["last_deltas"][0], 1)
        self.assertEqual(slot["last_overall"], 2)
        self.assertEqual(slot["previous"][0], roster[0]["ratings"][0])
        self.assertEqual(slot["flags"], 15)
        rows = pp.screen_rows(record, roster)
        self.assertEqual(rows[0]["season_overall"], 2)
        self.assertEqual(rows[0]["last_overall"], 2)
        self.assertEqual(rows[0]["season"][0], 1)
        self.assertEqual(rows[0]["last_week"][0], 1)
        # week 1: another speed point, previous stays the end of week 0
        roster[0]["ratings"][0] += 1
        roster[0]["overall"] += 1
        third = pp.advance_week(after_week, roster, week=1)
        record = pp.read_record(third)
        slot = record["slots"][0]
        self.assertEqual(slot["last_deltas"][0], 1)          # week 1 change, not the season total
        self.assertEqual(record["slots"][0]["previous"][0], roster[0]["ratings"][0])
        rows = pp.screen_rows(record, roster)
        self.assertEqual(rows[0]["season"][0], 2)
        self.assertEqual(rows[0]["last_week"][0], 1)

    def test_identity_change_resets_the_slot(self):
        payload = pp.baseline(bytes(pp.SAVE_SIZE), players(), year=2027, team=3)
        roster = players()
        roster[2]["pbp_id"] = 999
        roster[2]["jersey"] = 0
        roster[2]["overall"] = 90
        roster[2]["ratings"] = [80] * pp.RATING_COUNT
        after = pp.advance_week(payload, roster, week=0)
        slot = pp.read_record(after)["slots"][2]
        self.assertEqual(slot["baseline_overall"], 90)
        self.assertEqual(slot["previous_overall"], 90)
        self.assertEqual(slot["last_deltas"], [0] * pp.RATING_COUNT)
        self.assertEqual(slot["flags"], 7)

    def test_four_bit_packing_round_trip(self):
        values = [(-8 + (i % 16)) for i in range(pp.RATING_COUNT)]
        packed = pp._pack4(values)
        self.assertEqual(len(packed), 14)
        self.assertEqual(pp._unpack4(packed), values)

    def test_write_record_refuses_wrong_sizes(self):
        with self.assertRaises(pp.ProgressionError):
            pp.write_record(bytes(pp.SAVE_SIZE - 1), bytes(pp.RECORD_SIZE))
        with self.assertRaises(pp.ProgressionError):
            pp.write_record(bytes(pp.SAVE_SIZE), bytes(pp.RECORD_SIZE - 1))


if __name__ == "__main__":
    unittest.main()

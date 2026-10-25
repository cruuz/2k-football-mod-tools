"""b778-pg3: the Player Progress record and franchise footer (PPG3 v1 / PPGF0001).

The footer follows the complete native franchise container (and the MyCareer footer when present).
These tests prove the codec, the week ring, the screen contract, old-save behaviour and the exact
save sizes the native transaction writes.
"""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_my_career_save as career  # noqa: E402
from mod_editor.core import nfl2k5_player_progression as pp  # noqa: E402


def players():
    return [{"slot": slot, "pbp_id": 100 + slot, "position": 0, "jersey": slot,
             "overall": 70 + slot % 5, "ratings": [50 + (slot + i) % 20 for i in range(pp.RATING_COUNT)]}
            for slot in range(pp.TEAM_SLOTS)]


class RecordTests(unittest.TestCase):
    def test_layout_and_sizes(self):
        self.assertEqual(pp.RECORD_HEADER_SIZE, 32)
        self.assertEqual(pp.SNAPSHOT_SIZE, 29)
        self.assertEqual(pp.HISTORY_WEEKS, 17)
        self.assertEqual(pp.SLOT_SIZE, 527)
        self.assertEqual(pp.RECORD_SIZE, 34287)
        self.assertEqual(pp.FOOTER_HEADER_SIZE, 32)
        self.assertEqual(pp.FOOTER_SIZE, 34320)
        self.assertEqual(pp.PPG_SAVE_SIZES, (754364, 758460, 881340))
        self.assertEqual(pp.PPG_CAREER_SAVE_SIZES, (754492, 758588, 881468))
        self.assertIn(881340, career.CONTAINER_SIZES)
        self.assertIn(881468, career.CONTAINER_SIZES)

    def test_old_save_reads_as_absent(self):
        payload = bytes(pp.RETAIL_SAVE_SIZE)
        record = pp.read_footer(payload)
        self.assertFalse(record["present"])
        self.assertIsNone(record["header"])
        self.assertEqual(record["slots"], [])
        self.assertIsNone(pp.footer_start(payload))
        self.assertEqual(pp.strip_footer(payload), (payload, None))

    def test_append_only_grows_and_preserves_native_bytes(self):
        payload = bytes(pp.RETAIL_SAVE_SIZE)
        roster = players()
        footer = pp.baseline(roster, year=2027, team=3)
        grown, receipt = pp.append_footer(payload, footer)
        self.assertEqual(len(grown), 754364)
        self.assertEqual(grown[:-pp.FOOTER_SIZE], payload)
        self.assertEqual(receipt["footer_offset"], pp.RETAIL_SAVE_SIZE)
        record = pp.read_footer(grown)
        self.assertTrue(record["present"])
        self.assertEqual(record["header"]["year"], 2027)
        self.assertEqual(record["header"]["team"], 3)
        self.assertEqual(record["slots"][0]["baseline_overall"], 70)
        self.assertEqual(record["slots"][0]["baseline"], roster[0]["ratings"])
        self.assertEqual(pp.footer_start(grown), pp.RETAIL_SAVE_SIZE)
        self.assertEqual(pp.strip_footer(grown), (payload, grown[pp.RETAIL_SAVE_SIZE:]))
        with self.assertRaises(pp.ProgressionError):
            pp.append_footer(grown, footer)

    def test_baseline_week_ring_and_screen_contract(self):
        roster = players()
        footer = pp.baseline(roster, year=2027, team=3)
        record = pp.read_footer(footer)
        self.assertEqual(record["header"]["flags"], pp.HEADER_BASELINE)
        self.assertEqual(record["header"]["count"], 0)
        # week 0: one speed point and two overall points
        roster[0]["ratings"][0] += 1
        roster[0]["overall"] += 2
        footer = pp.advance_week(footer, roster, week=0)
        record = pp.read_footer(footer)
        self.assertEqual(record["header"]["count"], 1)
        self.assertEqual(record["header"]["head"], 1)
        self.assertEqual(record["header"]["week"], 0)
        rows = pp.screen_rows(record, roster, weeks_ago=0)
        self.assertEqual(rows[0]["season"][0], 1)
        self.assertEqual(rows[0]["season_overall"], 2)
        rows = pp.screen_rows(record, roster, weeks_ago=1)
        self.assertEqual(rows[0]["change"][0], 1)
        self.assertEqual(rows[0]["change_overall"], 2)
        self.assertEqual(rows[0]["previous"][0], 50)
        self.assertEqual(rows[0]["shown"][0], 51)
        # week 1: another speed point; week 2 no change
        roster[0]["ratings"][0] += 1
        roster[0]["overall"] += 1
        footer = pp.advance_week(footer, roster, week=1)
        roster[0]["ratings"][0] += 2
        footer = pp.advance_week(footer, roster, week=2)
        record = pp.read_footer(footer)
        self.assertEqual(record["header"]["count"], 3)
        self.assertEqual(record["header"]["head"], 3)
        week1 = pp.screen_rows(record, roster, weeks_ago=2)[0]
        week2 = pp.screen_rows(record, roster, weeks_ago=1)[0]
        season = pp.screen_rows(record, roster, weeks_ago=0)[0]
        self.assertEqual(week1["change"][0], 1)     # 50 -> 51
        self.assertEqual(week2["change"][0], 2)     # 52 -> 54
        self.assertEqual(season["change"][0], 4)    # 50 -> 54
        self.assertEqual(season["shown"][0], 54)
        self.assertEqual(season["previous"][0], 50)

    def test_identity_change_starts_a_new_slot_baseline(self):
        roster = players()
        footer = pp.baseline(roster, year=2027, team=3)
        roster[0]["pbp_id"] = 999
        roster[0]["ratings"][0] = 66
        footer = pp.advance_week(footer, roster, week=0)
        record = pp.read_footer(footer)
        slot = record["slots"][0]
        self.assertEqual(slot["baseline"][0], 66)
        self.assertEqual(slot["flags"], pp.FLAG_IDENTITY | pp.FLAG_BASELINE)
        row = pp.screen_rows(record, roster, weeks_ago=0)[0]
        self.assertEqual(row["season"][0], 0)

    def test_year_and_team_reset_the_baseline(self):
        roster = players()
        footer = pp.baseline(roster, year=2027, team=3)
        footer = pp.advance_week(footer, roster, week=2, team=9)
        record = pp.read_footer(footer)
        self.assertEqual(record["header"]["team"], 9)
        self.assertEqual(record["header"]["count"], 0)
        footer = pp.advance_week(footer, roster, week=2, year=2028)
        self.assertEqual(pp.read_footer(footer)["header"]["year"], 2028)

    def test_ring_wraps_at_seventeen_weeks(self):
        roster = players()
        footer = pp.baseline(roster, year=2027, team=3)
        for week in range(20):
            roster[0]["ratings"][0] = 50 + week
            footer = pp.advance_week(footer, roster, week=week)
        record = pp.read_footer(footer)
        self.assertEqual(record["header"]["count"], pp.HISTORY_WEEKS)
        self.assertEqual(record["header"]["head"], 20 % pp.HISTORY_WEEKS)
        self.assertEqual(pp.snapshot_index(record, 1), 2)
        self.assertIsNone(pp.snapshot_index(record, pp.HISTORY_WEEKS + 1))

    def test_wrong_sizes_are_refused(self):
        self.assertFalse(pp.read_footer(bytes(pp.FOOTER_SIZE - 1))["present"])
        with self.assertRaises(pp.ProgressionError):
            pp._wrap(bytes(pp.RECORD_SIZE - 1))
        with self.assertRaises(pp.ProgressionError):
            pp.advance_week(bytes(pp.FOOTER_SIZE - 1), players(), week=0)


if __name__ == "__main__":
    unittest.main()

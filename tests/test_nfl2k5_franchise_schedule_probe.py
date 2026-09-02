from __future__ import annotations

import datetime
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import nfl2k5_franchise_schedule_probe as probe  # noqa: E402


def synthetic_schedule() -> list[tuple[int, int, datetime.date]]:
    games = []
    for week in range(16):
        date = datetime.date(2004, 9, 12) + datetime.timedelta(weeks=week)
        for index in range(16):
            home = index if week < 8 else 16 + index
            away = 16 + (index + week) % 16 if week < 8 else (index + week) % 16
            games.append((home, away, date))
    return games


def build_synthetic_payload() -> bytes:
    payload = bytearray(b"\xff" * probe.FRANCHISE_SIZE)
    offset = 0x72A94
    for index, (home, away, date) in enumerate(synthetic_schedule()):
        hour, minute = (8, 30) if index % 16 == 15 else (1, 0)
        payload[offset:offset + 8] = bytes([
            probe.UPCOMING_TYPE, home, away, date.month, date.day,
            0x04, hour, minute,
        ])
        offset += 8
    played = 0x917CA
    payload[played:played + 32] = b"\x00" * 32
    slot = played + 32
    for week in range(16):
        for index, (home, away, date) in enumerate(
                synthetic_schedule()[week * 16:(week + 1) * 16]):
            payload[slot:slot + 8] = bytes([
                probe.PLAYED_TYPE, home, away, date.month, date.day,
                probe.PLAYED_REGULAR_SLOT_VALUE, 1, 0,
            ])
            slot += 8
        payload[slot:slot + 8] = probe.FILLER_SLOT
        slot += 8
    postseason = [
        (0, 16, 1, 8, 0, 30), (16, 1, 1, 8, 4, 5),
        (2, 18, 1, 9, 0, 35), (18, 3, 1, 9, 4, 15),
        (0, 17, 1, 15, 0, 35), (17, 2, 1, 15, 4, 15),
        (4, 19, 1, 16, 0, 40), (19, 5, 1, 16, 4, 15),
        (0, 20, 1, 23, 1, 35), (20, 6, 1, 23, 4, 15),
        (7, 8, 1, 30, 4, 0), (32, 33, 2, 6, 4, 0),
    ]
    for home, away, month, day, hour, minute in postseason:
        payload[slot:slot + 8] = bytes([
            probe.PLAYED_TYPE, home, away, month, day,
            probe.PLAYED_POSTSEASON_SLOT_VALUE, hour, minute,
        ])
        slot += 8
    return bytes(payload)


class FranchiseScheduleProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = build_synthetic_payload()
        cls.report = probe.build_report(cls.payload, "synthetic")

    def test_locates_both_tables_in_synthetic_payload(self) -> None:
        self.assertEqual(self.report["summary"]["upcoming_table_offset"],
                         "0x00072a94")
        self.assertEqual(self.report["summary"]["played_table_offset"],
                         "0x000917ca")
        self.assertEqual(self.report["summary"]["upcoming_games"], 256)
        self.assertEqual(self.report["summary"]["played_games"], 268)
        self.assertEqual(self.report["summary"]["upcoming_week_span"], [1, 16])

    def test_postseason_rounds_and_super_bowl_labeling(self) -> None:
        postseason = [row for row in self.report["games"]
                      if row["table"] == "played" and row["round"] != "regular"]
        rounds = [row["round"] for row in postseason]
        self.assertEqual(rounds, ["wild_card"] * 4 + ["divisional"] * 4
                         + ["conference"] * 2 + ["super_bowl", "all_star"])
        sb = self.report["summary"]["super_bowl_game"]
        self.assertEqual(sb["date"], "2005-01-30")
        self.assertEqual(sb["week"], 20)
        self.assertEqual(sb["kickoff"], "4:00 PM")
        self.assertFalse(sb["primetime"])

    def test_kickoff_fields_and_primetime_flag(self) -> None:
        night = [row for row in self.report["games"]
                 if row["hour_field"] == 8 and row["minute_field"] == 30]
        self.assertTrue(night)
        self.assertTrue(all(row["primetime"] for row in night))
        early = [row for row in self.report["games"]
                 if row["hour_field"] == 1 and row["minute_field"] == 0]
        self.assertTrue(early)
        self.assertFalse(any(row["primetime"] for row in early))

    def test_rejects_wrong_size_and_wrong_hash(self) -> None:
        with self.assertRaises(probe.ProbeError):
            probe.build_report(self.payload[:-4], "synthetic")
        with self.assertRaises(probe.ProbeError):
            probe.sha256_argument("0" * 63)

    def test_self_test_cli_and_read_only_source(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools/nfl2k5_franchise_schedule_probe.py"),
             "--self-test"],
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("NFL2K5_FRANCHISE_SCHEDULE_PROBE_SELF_TEST_OK",
                      result.stdout)
        source = (ROOT / "tools/nfl2k5_franchise_schedule_probe.py").read_text(
            encoding="utf-8")
        for forbidden in ("--apply", "O_RDWR", "r+b", "wb\""):
            self.assertNotIn(forbidden, source)
        self.assertIn('open("rb")', source)


if __name__ == "__main__":
    unittest.main()

"""The schedule template tool must decode retail, refuse foreign bytes and write only into a copy.

Synthetic fixture: a pack-shaped blob with a retail-shaped ROST outer entry (wrapper, inner tag, pool
link, schedule pair, template, zero tail) built by ``synthetic_pack``.  Retail smoke tests run only
when the private extraction and schedule JSON exist.
"""

from __future__ import annotations

import datetime as dt
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "tools"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import nfl2k5_franchise_schedule as fs  # noqa: E402

RETAIL_DISC = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)")
SCHEDULE_JSON = ROOT / "data" / "nfl_2026_schedule.json"
ROST = 0x800


def _retail_shaped_pack() -> bytes:
    """Synthetic pack whose template digest is patched into the retail constants for the test."""
    return fs.synthetic_pack(ROST)


class RecordTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        raw = fs.encode_record(21, 10, dt.date(2004, 9, 9), 9, 0)
        self.assertEqual(raw, bytes([0, 21, 10, 9, 9, 4, 9, 0]))
        rec = fs.decode_record(raw)
        self.assertEqual((rec["home_name"], rec["away_name"], rec["date"], rec["kickoff"]), ("Patriots", "Colts", "2004-09-09", "9:00"))
        self.assertEqual(fs.encode_record(0, 1, dt.date(2027, 1, 10), 12, 30)[5:], bytes([27, 0, 30]))
        with self.assertRaises(fs.ScheduleError):
            fs.encode_record(3, 3, dt.date(2026, 9, 13), 1, 0)

    def test_week_detector_matches_the_game(self) -> None:
        d = lambda m, day, y=2026: dt.date(y, m, day)  # noqa: E731
        self.assertFalse(fs.new_week(d(9, 10), d(9, 13)))          # Thu -> Sun
        self.assertFalse(fs.new_week(d(9, 13), d(9, 14)))          # Sun -> Mon
        self.assertTrue(fs.new_week(d(9, 14), d(9, 17)))           # Mon -> Thu
        self.assertTrue(fs.new_week(d(9, 14), d(9, 20)))           # Mon -> Sun (6 days)
        self.assertTrue(fs.new_week(d(9, 9), d(9, 10)))            # Wed -> Thu breaks: Wed must come last
        self.assertFalse(fs.new_week(d(9, 14), d(9, 9)))           # Mon -> Wed (earlier) stays
        self.assertFalse(fs.new_week(d(12, 19), d(12, 20)))        # Sat -> Sun
        self.assertTrue(fs.new_week(d(1, 4, 2027), d(1, 9, 2027)))  # Mon -> Sat
        self.assertFalse(fs.new_week(d(9, 13), d(9, 13)))

    def test_synthetic_season_shape(self) -> None:
        blob = fs.synthetic_season(2004, 16, 17)
        check = fs.validate_schedule(fs.decode_records(blob, 0, len(blob) // 8), 16)
        self.assertEqual((check["weeks"], check["games_per_team"]), (17, [16]))


class SyntheticPackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pack = fs.synthetic_pack(ROST)
        self.retail_sha = fs.RETAIL_TEMPLATE_SHA256
        # the synthetic template is not the 2004 season; pin the digest to it for the duration
        fs.RETAIL_TEMPLATE_SHA256 = fs.sha256(self.pack[ROST + fs.RETAIL_TEMPLATE_REL: ROST + fs.RETAIL_TEMPLATE_REL + 2048])

    def tearDown(self) -> None:
        fs.RETAIL_TEMPLATE_SHA256 = self.retail_sha

    def test_pool_resolution_and_status(self) -> None:
        count, ptr, hdr = fs.schedule_location(self.pack, ROST)
        self.assertEqual((count, ptr, hdr), (256, ROST + fs.RETAIL_TEMPLATE_REL, ROST + 0x60))
        self.assertEqual(struct.unpack_from("<I", self.pack, hdr + 0x2C)[0], 0x72749)   # the retail offset value
        self.assertEqual(fs.pack_status(self.pack, ROST)["state"], "retail")
        report = fs.inspect_blob(self.pack, ROST, "synthetic")
        self.assertEqual(report["validation"]["weeks"], 17)

    def test_apply_writes_only_the_tail_and_the_pair(self) -> None:
        template = fs.synthetic_season(2026, 17, 18)
        patched, receipt = fs.apply_pack(self.pack, template, ROST)
        self.assertEqual(receipt["records"], 272)
        self.assertEqual(receipt["placement"], f"0x{ROST + fs.TAIL_PLACEMENT_REL:x}")
        self.assertEqual(receipt["offset_value"], "0x8ef9d")
        self.assertEqual(fs.pack_status(patched, ROST)["state"], "applied")
        count, ptr, _hdr = fs.schedule_location(patched, ROST)
        self.assertEqual((count, ptr), (272, ROST + fs.TAIL_PLACEMENT_REL))
        self.assertEqual(patched[ptr: ptr + len(template)], template)
        changed = {i for i, (a, b) in enumerate(zip(self.pack, patched)) if a != b}
        allowed = set(range(ptr, ptr + len(template))) | set(range(ROST + 0x88, ROST + 0x90))
        self.assertTrue(changed <= allowed)
        self.assertEqual(len(patched), len(self.pack))
        self.assertEqual(patched[ROST: ROST + 0x88], self.pack[ROST: ROST + 0x88])   # wrapper and earlier pairs untouched
        with self.assertRaises(fs.ScheduleError):
            fs.apply_pack(patched, template, ROST)

    def test_preseason_block_is_written_after_the_template_and_reported(self) -> None:
        template = fs.synthetic_season(2026, 17, 18)
        block = _synthetic_preseason_block(2026)
        patched, receipt = fs.apply_pack(self.pack, template, ROST, preseason=block)
        self.assertEqual(receipt["preseason_games"], 49)
        count, ptr, _hdr = fs.schedule_location(patched, ROST)
        self.assertEqual(count, 272)
        self.assertEqual(patched[ptr + len(template): ptr + len(template) + len(block)], block)
        self.assertEqual(receipt["preseason_placement"], f"0x{ptr + len(template):x}")
        status = fs.pack_status(patched, ROST)
        self.assertEqual((status["state"], status["preseason_games"]), ("applied", 49))
        report = fs.inspect_blob(patched, ROST, "synthetic")
        self.assertEqual((report["preseason"]["games"], report["preseason"]["weeks"]), (49, 4))
        self.assertEqual(report["preseason"]["week_table"][0]["games"], 1)
        # without a block the pack is still "applied" and reports no preseason template
        plain, _ = fs.apply_pack(self.pack, template, ROST)
        self.assertEqual(fs.pack_status(plain, ROST)["preseason_games"], 0)
        self.assertEqual(fs.inspect_blob(plain, ROST, "synthetic")["preseason"]["games"], 0)
        # a corrupt block after the template is foreign
        bad = bytearray(patched)
        bad[ptr + len(template) + 4 + 1] = bad[ptr + len(template) + 4 + 2]     # HOF game: a team plays itself
        self.assertEqual(fs.pack_status(bytes(bad), ROST)["state"], "foreign")
        with self.assertRaises(fs.ScheduleError):
            fs.apply_pack(self.pack, template, ROST, preseason=block[:4] + block[12:])   # 48 games: a team short

    def test_foreign_and_oversize_are_refused(self) -> None:
        buf = bytearray(self.pack)
        buf[ROST + fs.TAIL_FREE_REL + 5] = 1
        self.assertEqual(fs.pack_status(bytes(buf), ROST)["state"], "foreign")
        with self.assertRaises(fs.ScheduleError):
            fs.apply_pack(bytes(buf), fs.synthetic_season(2026, 17, 18), ROST)
        with self.assertRaises(fs.ScheduleError):
            fs.apply_pack(self.pack, b"\0" * (fs.ROST_OUTER_SIZE - fs.TAIL_PLACEMENT_REL + 8), ROST)
        bad = bytearray(fs.synthetic_season(2026, 17, 18))
        bad[1] = bad[2]                                   # a team plays itself
        with self.assertRaises(fs.ScheduleError):
            fs.apply_pack(self.pack, bytes(bad), ROST)


def _synthetic_preseason_block(year: int) -> bytes:
    """HOF game (teams 0 v 1, Thursday) + three 16-game rounds a week apart (Thu/Fri/Sat mix)."""
    hof = dt.date(year, 8, 6)
    while hof.weekday() != 3:
        hof += dt.timedelta(days=1)
    blob = bytearray(fs.encode_record(0, 1, hof, 8, 0, kind=0))
    teams = list(range(32))
    for week in range(1, 4):
        thursday = hof + dt.timedelta(days=7 * week)
        pairs = [(teams[i], teams[31 - i]) for i in range(16)]
        for slot, (h, a) in enumerate(pairs):
            date = thursday + dt.timedelta(days=slot % 3)
            blob += fs.encode_record(h if week % 2 else a, a if week % 2 else h, date, 7, 30, kind=week)
        teams = [teams[0]] + [teams[-1]] + teams[1:-1]
    return struct.pack("<I", (fs.PRESEASON_TAG << 16) | 49) + bytes(blob)


class PreseasonTemplateTests(unittest.TestCase):
    def test_synthetic_block_round_trip(self) -> None:
        block = _synthetic_preseason_block(2026)
        decoded = fs.decode_preseason_block(block, 0)
        self.assertTrue(decoded["valid"])
        self.assertEqual((decoded["games"], decoded["weeks"]), (49, 4))
        self.assertEqual([w["games"] for w in decoded["week_table"]], [1, 16, 16, 16])
        self.assertEqual(decoded["records"][0]["type"], 0)
        self.assertEqual(decoded["records"][-1]["type"], 3)
        self.assertIsNone(fs.decode_preseason_block(b"\0" * 16, 0))                      # no tag
        self.assertIsNone(fs.decode_preseason_block(struct.pack("<I", (fs.PRESEASON_TAG << 16) | 69), 0))
        # the game's date detector would fold a Saturday -> Thursday boundary; the type byte carries the week
        records = decoded["records"]
        self.assertEqual(len(fs.preseason_weeks(records)), 4)
        with self.assertRaises(fs.ScheduleError):
            wrong = [dict(r, type=(r["type"] + 1) % 4) for r in records]
            fs.validate_preseason(wrong)

    @unittest.skipUnless(SCHEDULE_JSON.is_file(), "2026 schedule JSON missing")
    def test_2026_preseason_is_the_real_slate(self) -> None:
        doc = json.loads(SCHEDULE_JSON.read_text())
        block, info = fs.encode_preseason(doc)
        self.assertEqual(len(block), 4 + 49 * 8)
        self.assertEqual(struct.unpack_from("<I", block)[0], (fs.PRESEASON_TAG << 16) | 49)
        self.assertEqual((info["games"], info["weeks"]), (49, 4))
        table = info["validation"]["week_table"]
        self.assertEqual([w["games"] for w in table], [1, 16, 16, 16])
        self.assertEqual((table[0]["first_date"], table[1]["first_date"], table[1]["last_date"]),
                         ("2026-08-06", "2026-08-13", "2026-08-15"))
        self.assertEqual((table[2]["first_date"], table[2]["last_date"]), ("2026-08-20", "2026-08-23"))
        self.assertEqual((table[3]["first_date"], table[3]["last_date"]), ("2026-08-27", "2026-08-29"))
        hof = fs.decode_record(block[4:12])
        self.assertEqual((hof["away_name"], hof["home_name"], hof["date"], hof["kickoff"]), ("Panthers", "Cardinals", "2026-08-06", "8:00"))
        self.assertEqual(len(fs.split_weeks(fs.decode_records(block, 4, 49))), 3)   # why the type byte carries the week
        giants = [r for r in fs.decode_records(block, 4, 49) if 15 in (r["home"], r["away"])]
        self.assertEqual([(r["date"], r["away_name"], r["home_name"]) for r in giants],
                         [("2026-08-15", "Vikings", "Giants"), ("2026-08-22", "Giants", "Dolphins"), ("2026-08-28", "Giants", "Jets")])
        self.assertEqual(fs.encode_preseason({"preseason": None}), (b"", {"games": 0}))


@unittest.skipUnless(SCHEDULE_JSON.is_file(), "2026 schedule JSON missing")
class ScheduleJsonTests(unittest.TestCase):
    def test_2026_template_is_18_weeks_of_17_games(self) -> None:
        doc = json.loads(SCHEDULE_JSON.read_text())
        blob, info = fs.encode_schedule(doc)
        self.assertEqual(len(blob), 272 * 8)
        self.assertEqual(info["validation"]["weeks"], 18)
        self.assertEqual(info["validation"]["games_per_team"], [17])
        self.assertEqual(info["validation"]["home_games"], [8, 9])
        table = info["validation"]["week_table"]
        self.assertEqual(table[0]["first_date"], "2026-09-09")           # Wednesday opener kept in week 1
        self.assertEqual(table[0]["byes"], [])
        self.assertEqual(table[-1]["last_date"], "2027-01-10")
        self.assertEqual(sum(len(w["byes"]) for w in table), 32)
        self.assertTrue(all(w["games"] <= fs.GRID_SLOTS for w in table))
        first = fs.decode_record(blob[:8])
        self.assertEqual((first["date"], first["away_name"], first["home_name"]), ("2026-09-10", "49ers", "Rams"))
        self.assertEqual(blob[5], 26)
        self.assertEqual(blob[-3], 27)                                    # January 2027 year byte
        self.assertEqual(len(info["notes"]["am_kickoffs"]), 6)


@unittest.skipUnless((RETAIL_DISC / fs.PACK_REL).is_file(), "retail extraction not present")
class RetailPackSmokeTests(unittest.TestCase):
    def test_retail_pack_decodes_the_2004_season(self) -> None:
        payload = (RETAIL_DISC / fs.PACK_REL).read_bytes()
        status = fs.pack_status(payload)
        self.assertEqual(status["state"], "retail")
        count, ptr, hdr = fs.schedule_location(payload, fs.PACK_ROST_OFFSET)
        self.assertEqual((count, ptr, hdr), (256, 0x404FD4, 0x392860))
        records = fs.decode_records(payload, ptr, count)
        self.assertEqual((records[0]["date"], records[0]["away_name"], records[0]["home_name"]), ("2004-09-09", "Colts", "Patriots"))
        check = fs.validate_schedule(records, 16)
        self.assertEqual((check["weeks"], check["home_games"]), (17, [8]))
        self.assertEqual(check["week_table"][2]["byes"], ["Bills", "Jets", "Panthers", "Patriots"])
        self.assertFalse(any(payload[fs.PACK_ROST_OFFSET + fs.TAIL_FREE_REL: fs.PACK_ROST_OFFSET + fs.ROST_OUTER_SIZE]))
        if SCHEDULE_JSON.is_file():
            doc = json.loads(SCHEDULE_JSON.read_text())
            template, _ = fs.encode_schedule(doc)
            block, _ = fs.encode_preseason(doc)
            patched, receipt = fs.apply_pack(payload, template, preseason=block)
            self.assertEqual(receipt["status_after"]["state"], "applied")
            self.assertEqual(receipt["preseason_games"], 49)
            self.assertEqual(receipt["changed_bytes"], 8 + sum(1 for b in template + block if b))
            start = fs.PACK_ROST_OFFSET + fs.TAIL_PLACEMENT_REL
            self.assertEqual(patched[start + len(template): start + len(template) + len(block)], block)
            self.assertLess(start + len(template) + len(block), fs.PACK_ROST_OFFSET + fs.ROST_OUTER_SIZE)


if __name__ == "__main__":
    unittest.main()

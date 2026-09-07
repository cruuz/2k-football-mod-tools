"""Postseason save regression: real retail saves and bounded builder-shaped fixtures.

Run standalone with python3. Private saves skip precisely when unavailable.
The synthetic bracket uses the shipped owner's game table, flags and dates;
it is not evidence of an in-game save/reload.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_franchise_save as fs
from mod_editor.core import nfl2k5_playoffs14 as p14
from mod_editor.core import nfl2k5_season_length as season
from tests.mod_editor.test_nfl2k5_franchise_save import F0, F1, FRANCHISE1, synthetic_franchise


def put_game(data, row, slot, raw, flags=0x0101):
    cell = row * fs.GRID_SLOTS + slot
    offset = fs.SEASON_BLOCK + fs.S_GRID + cell * fs.GAME_SIZE
    data[offset:offset + fs.GAME_SIZE] = raw
    struct.pack_into('<H', data, fs.SEASON_BLOCK + fs.S_GRID_FLAGS + cell * 2, flags)


def synthetic_postseason(*, weeks=18, teams=14, year=2027, played=False, template=True):
    data = bytearray(synthetic_franchise(year_field=0))
    data[fs.SEASON_BLOCK + fs.S_STAGE] = 9
    # The builder leaves the full grid bound in the saved header, not 4/5.
    data[fs.SEASON_BLOCK + fs.S_STAGE_WEEKS] = 22
    data[fs.SEASON_BLOCK + fs.S_WEEK] = weeks
    if weeks == 18:
        for slot in range(16):
            put_game(data, 17, slot, bytes([3, 2 * slot, 2 * slot + 1, 1, 10, year - 2000, 1, 0]))
    if template:
        at = 0x80000
        count = 272 if weeks == 18 else 256
        struct.pack_into('<I', data, fs.ARENA_ROOT + 0x28, count)
        field = fs.ARENA_ROOT + 0x2C
        struct.pack_into('<i', data, field, at - field + 1)
        # Bounded template with distinct pairs; detection uses the saved count.
        data[at:at + count * 8] = bytes([0, 1, 2, 9, 10, 26, 1, 0]) * count
    table = p14.GAME_TABLE if teams == 14 else (
        (0, 0, 3, 4, 1, 1), (0, 1, 2, 5, 1, 1),
        (0, 2, 10, 11, 1, 1), (0, 3, 9, 12, 1, 1),
        (1, 0, 0, 255, 1, 0), (1, 1, 1, 255, 1, 0),
        (1, 2, 7, 255, 1, 0), (1, 3, 8, 255, 1, 0),
        (2, 0, 255, 255, 0, 0), (2, 1, 255, 255, 0, 0),
        (3, 0, 255, 255, 0, 0),
    )
    dates = p14.CALENDAR_2026_14 if teams == 14 else season.CALENDAR_2026[:-1]
    for (row, slot, home, away, hf, af), date in zip(table, dates):
        month, day, hour, minute = date
        raw = bytearray([0, home if hf else 0, away if af else 0, month, day, year - 2000, hour, minute])
        if played:
            raw[:3] = bytes([3, slot * 2 + 1, slot * 2 + 2])
            hf = af = 1
        put_game(data, weeks + row, slot, raw, hf | (af << 8))
    if weeks == 17:
        put_game(data, 21, 0, bytes([3 if played else 0, 32, 33, 2, 21, year - 2000, 4, 0]))
    return bytes(data)


def inventory(save):
    """Full fixed-grid audit independent of games()'s traversal/filter."""
    rows = []
    payload = save.to_bytes()
    for row in range(save.regular_season_weeks, 22):
        for slot in range(17):
            at = 0x917EA + 8 * (row * 17 + slot)
            raw = payload[at:at + 8]
            if raw[0] in (0, 3) and any(raw[1:4]):
                rows.append((row, slot, raw.hex()))
    return rows


class PostseasonCodecTests(unittest.TestCase):
    def test_every_round_and_date_time_round_trip_in_each_supported_layout(self):
        for weeks in (17, 18):
            for teams in (12, 14):
                with self.subTest(weeks=weeks, teams=teams):
                    original = synthetic_postseason(weeks=weeks, teams=teams)
                    save = fs.FranchiseSave(original, base_year=2026)
                    self.assertEqual(save.to_bytes(), original)
                    games = save.games(rows=range(weeks, 22))
                    expected = (11 if teams == 12 else 13) + (weeks == 17)
                    self.assertEqual(len(games), expected)
                    self.assertEqual([(g.row, g.slot) for g in games], [(r, s) for r, s, _ in inventory(save)])
                    self.assertEqual(save.regular_season_weeks, weeks)
                    allowed = set()
                    for game in games:
                        self.assertEqual(game.row_name, ('wild card', 'divisional', 'conference', 'super bowl', 'pro bowl')[game.row - weeks])
                        save.set_game(game.row, game.slot, month=3, day=4, hour=9, minute=56)
                        allowed.update(game.offset + n for n in (3, 4, 6, 7))
                    back = fs.FranchiseSave(save.to_bytes(), base_year=2026)
                    for game in back.games(rows=range(weeks, 22)):
                        self.assertEqual((game.month, game.day, game.hour, game.minute), (3, 4, 9, 56))
                        self.assertEqual(game.slot_code, 27)
                    self.assertEqual(len(back.to_bytes()), len(original))
                    self.assertEqual({i for i, (a, b) in enumerate(zip(original, back.to_bytes())) if a != b}, allowed)

    def test_placeholder_flags_preserved_including_the_real_team_zero(self):
        save = fs.FranchiseSave(synthetic_postseason())
        home_only = save.game(19, 0)
        self.assertEqual((home_only.home, home_only.away), (0, 0))
        self.assertTrue(home_only.home_known)  # Team zero really is the #1 seed.
        self.assertFalse(home_only.away_known)
        save.set_game(19, 0, day=25, minute=45)
        empty_matchup = save.game(19, 1)
        self.assertFalse(empty_matchup.home_known)
        self.assertFalse(empty_matchup.away_known)
        save.set_game(19, 1, day=26, hour=7)
        before = save.to_bytes()
        with self.assertRaisesRegex(fs.FranchiseSaveError, 'still to be decided'):
            save.set_game(19, 1, home=5)
        self.assertEqual(save.to_bytes(), before)

    def test_sparse_tail_and_last_record_never_spill_into_scores(self):
        data = bytearray(synthetic_postseason())
        # A retained filler must not hide a later saved game. This gap is synthetic.
        first = 0x917EA + 18 * 17 * 8
        data[first + 8:first + 16] = bytes([7]) + bytes(7)
        put_game(data, 21, 16, bytes([0, 5, 6, 2, 14, 27, 6, 30]))
        save = fs.FranchiseSave(data)
        self.assertEqual([g.slot for g in save.games(rows=[18])], [0, 2, 3, 4, 5])
        before = save.to_bytes()
        game = save.set_game(21, 16, minute=59)
        self.assertEqual(game.offset + 8, fs.SEASON_BLOCK + fs.S_SCORES)
        self.assertEqual(save.to_bytes()[:game.offset + 7], before[:game.offset + 7])
        self.assertEqual(save.to_bytes()[game.offset + 8:], before[game.offset + 8:])

    def test_refusals_are_atomic(self):
        save = fs.FranchiseSave(synthetic_postseason())
        for row, slot, fields in ((18, 0, {'day': 20, 'minute': 60}),
                                  (18, 0, {'home': 6, 'day': 20}),
                                  (18, 6, {'day': 20}), (18, 7, {'day': 20}),
                                  (22, 0, {'day': 20}), (-1, 0, {'day': 20}),
                                  (21, 17, {'day': 20})):
            with self.subTest(row=row, slot=slot, fields=fields):
                before = save.to_bytes()
                with self.assertRaises(fs.FranchiseSaveError):
                    save.set_game(row, slot, **fields)
                self.assertEqual(save.to_bytes(), before)
        data = bytearray(save.to_bytes())
        data[save.game(18, 0).offset] = 2
        save = fs.FranchiseSave(data)
        with self.assertRaisesRegex(fs.FranchiseSaveError, 'unsupported'):
            save.set_game(18, 0, day=20)
        self.assertEqual(save.to_bytes(), data)

    def test_layout_uses_save_evidence_and_calendar_byte_stays_unmodified(self):
        for weeks in (17, 18):
            for template in (False, True):
                save = fs.FranchiseSave(synthetic_postseason(weeks=weeks, template=template), base_year=2004)
                self.assertEqual(save.regular_season_weeks, weeks)
        for year in (2027, 2100, 2154):
            save = fs.FranchiseSave(synthetic_postseason(year=year), base_year=2026)
            save.set_game(21, 0, month=2, day=28, hour=0, minute=1)
            self.assertEqual(save.game(21, 0).slot_code, year - 2000)
        for weeks in (17, 18):
            data = bytearray(synthetic_franchise())
            data[fs.SEASON_BLOCK + fs.S_STAGE_WEEKS] = weeks
            self.assertEqual(fs.FranchiseSave(data, base_year=2026).regular_season_weeks, weeks)

    def test_played_guard_and_explicit_override_leave_results_unchanged(self):
        save = fs.FranchiseSave(synthetic_postseason(played=True))
        for game in save.games(rows=range(18, 22)):
            before = save.to_bytes()
            with self.assertRaisesRegex(fs.FranchiseSaveError, 'has been played'):
                save.set_game(game.row, game.slot, day=25, hour=7)
            self.assertEqual(save.to_bytes(), before)
            updated = save.set_game(game.row, game.slot, day=25, hour=7, allow_played=True)
            self.assertEqual((updated.kind, updated.flags, updated.scores), (game.kind, game.flags, game.scores))


class RealPostseasonTests(unittest.TestCase):
    def check_real(self, path, count):
        if not path.is_file():
            self.skipTest(f'private preserved franchise save missing: {path}')
        original = path.read_bytes()
        source_hash = hashlib.sha256(original).hexdigest()
        save = fs.FranchiseSave.load(path.parents[3])
        self.assertEqual(save.to_bytes(), original)
        self.assertEqual(save.regular_season_weeks, 17)
        games = save.games(rows=range(17, 22))
        self.assertEqual(len(games), count)
        self.assertEqual([(g.row, g.slot) for g in games], [(r, s) for r, s, _ in inventory(save)])
        allowed = set()
        for game in games:
            before = save.to_bytes()
            with self.assertRaisesRegex(fs.FranchiseSaveError, 'has been played'):
                save.set_game(game.row, game.slot, day=27, hour=8)
            self.assertEqual(save.to_bytes(), before)
            save.set_game(game.row, game.slot, month=3, day=27, hour=8, minute=59, allow_played=True)
            allowed.update(game.offset + n for n in (3, 4, 6, 7))
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp).resolve() / 'edited'
            receipt = save.write(target)
            self.assertTrue(receipt['signed'])
            back = fs.FranchiseSave.load(target)  # verifies EXTRA signature
            self.assertEqual(back.to_bytes(), save.to_bytes())
        self.assertEqual({i for i, (a, b) in enumerate(zip(original, save.to_bytes())) if a != b}, allowed)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), source_hash)

    def test_finn_before_ir_signed_noop_round_trip_no_postseason_exists(self):
        self.check_real(F0, 0)

    def test_finn_after_ir_signed_noop_round_trip_no_postseason_exists(self):
        self.check_real(F1, 0)

    def test_lions_every_postseason_game_signed_edit_round_trip(self):
        self.check_real(FRANCHISE1, 12)


if __name__ == '__main__':
    unittest.main()

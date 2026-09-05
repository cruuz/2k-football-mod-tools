"""nfl2k5_franchise_save: the franchise blocks beyond the roster arena.

Synthetic fixtures are built from the roster tests' ``synthetic_body`` (a small retail-shaped arena) plus
season / front-office blocks generated here from the documented layout.  The private class opens the real
saves under ``NFL2K5_SAVE_FIXTURES`` (skips when absent) and, among other things, reproduces Finn's IR move
between the two 8007Fran fixtures byte for byte.
"""

from __future__ import annotations

import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_franchise_save as fs  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from tests.mod_editor.test_nfl2k5_roster_records import synthetic_body, synthetic_save_v0  # noqa: E402

FIXTURES = Path(os.environ.get("NFL2K5_SAVE_FIXTURES", str(Path.home() / "Desktop" / "2K5-8 Editors" / "save_fixtures")))
F0 = FIXTURES / "f0" / "UDATA" / "53450030" / "0B8506889D40" / "SAVEGAME.DAT"
F1 = FIXTURES / "f1" / "UDATA" / "53450030" / "0B8506889D40" / "SAVEGAME.DAT"
FRANCHISE1 = FIXTURES / "256B40374FD6-Franchise1" / "UDATA" / "53450030" / "256B40374FD6" / "SAVEGAME.DAT"


def game_record(kind: int, home: int, away: int, month: int, day: int, code: int, hour: int, minute: int) -> bytes:
    return bytes([kind, home, away, month, day, code, hour, minute])


def synthetic_franchise(*, year_field: int = 7, user_team: int = 0) -> bytes:
    season = bytearray(fs.SEASON_BLOCK_SIZE)
    season[0:7] = bytes([2, 8, 0, 32, 17, 3, year_field])                  # franchise, regular season, week 3
    season[fs.S_SEEDS_A:fs.S_SEEDS_A + 24] = bytes([0xFF]) * 24
    struct.pack_into(f"<{fs.LEAGUE_SLOTS}I", season, fs.S_DIVISIONS, *[i % 8 for i in range(fs.LEAGUE_SLOTS)])
    struct.pack_into("<I", season, fs.S_USER_CONTROL + 4 * user_team, 1)
    season[fs.S_TEAM_ORDER:fs.S_TEAM_ORDER + 34] = bytes(range(32)) + b"\xff\xff"
    grid = fs.S_GRID
    season[grid:grid + 8] = game_record(3, 1, 0, 9, 12, 0x0A, 1, 0)         # played
    season[grid + 8:grid + 16] = game_record(0, 2, 3, 9, 12, 0x0A, 4, 15)   # scheduled
    season[grid + 16:grid + 24] = bytes([7]) + bytes(7)                     # row end
    for row in range(1, fs.GRID_ROWS):
        at = grid + row * fs.GRID_SLOTS * 8
        season[at:at + 8] = bytes([7]) + bytes(7)
    struct.pack_into("<H", season, fs.S_GRID_FLAGS, 0x0101)
    season[fs.S_SCORES:fs.S_SCORES + 10] = bytes([7, 0, 3, 7, 0, 0, 7, 7, 3, 0])
    office = bytearray(fs.FRONT_OFFICE_SIZE)
    struct.pack_into("<I", office, fs.F_SALARY_CAP, 80_500)
    for entry in range(fs.NFL_TEAMS * fs.IR_SLOTS):
        struct.pack_into("<H", office, fs.F_INJURED_RESERVE + entry * fs.IR_ENTRY, fs.IR_EMPTY)
    office[fs.F_TEAM_RANK:fs.F_TEAM_RANK + 32] = bytes(range(1, 33))
    struct.pack_into("<I", office, fs.F_LEDGER_COUNT, 1)
    struct.pack_into("<IHHB", office, fs.F_LEDGER, 0x8000002A, 0, 0, 0)
    return synthetic_save_v0(synthetic_body(), suffix=bytes(season) + bytes(office))


class LayoutTests(unittest.TestCase):
    def test_regions_tile_the_whole_file(self) -> None:
        self.assertTrue(fs.regions_cover_file())
        self.assertEqual(fs.REGIONS[-1].end, fs.FRANCHISE_SAVE_SIZE)
        self.assertEqual(fs.FRONT_OFFICE_BLOCK, 0x996FC)
        self.assertEqual(fs.SEASON_BLOCK + fs.S_GRID, 0x917EA)                  # Finn / the schedule probe
        self.assertEqual(fs.SEASON_BLOCK + fs.S_USER_CONTROL, 0x913CC)          # Finn's team control
        self.assertEqual(fs.FRONT_OFFICE_BLOCK + fs.F_SALARY_CAP, 0x9ACCC)      # Finn's cap
        self.assertEqual(fs.FRONT_OFFICE_BLOCK + fs.F_INJURED_RESERVE, 0x9E6CC) # Finn's IR slot
        statuses = {region.status for region in fs.REGIONS}
        self.assertEqual(statuses, {"PROVED", "HYPOTHESIS", "OPAQUE"})

    def test_refuses_non_franchise_bytes(self) -> None:
        with self.assertRaisesRegex(fs.FranchiseSaveError, "720,044"):
            fs.FranchiseSave(bytes(100))
        bad = bytearray(synthetic_franchise())
        bad[0x2E0:0x2E4] = b"XXXX"
        with self.assertRaisesRegex(fs.FranchiseSaveError, "wrapper"):
            fs.FranchiseSave(bytes(bad))
        bad = bytearray(synthetic_franchise())
        struct.pack_into("<I", bad, 0x310, 17)
        with self.assertRaisesRegex(fs.FranchiseSaveError, "version 0"):
            fs.FranchiseSave(bytes(bad))
        self.assertFalse(fs.is_franchise_save(bytes(bad)))
        self.assertTrue(fs.is_franchise_save(synthetic_franchise()))


class SyntheticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = synthetic_franchise()
        self.save = fs.FranchiseSave(self.payload, source="synthetic")

    def test_round_trip_is_byte_identical(self) -> None:
        self.assertEqual(self.save.to_bytes(), self.payload)
        self.assertEqual(self.save.changed_ranges(), [])
        self.assertEqual(len(self.payload), fs.FRANCHISE_SAVE_SIZE)

    def test_header_year_and_stage(self) -> None:
        header = self.save.header
        self.assertEqual((header.mode, header.stage, header.team_count, header.stage_weeks, header.week), (2, 8, 32, 17, 3))
        self.assertEqual((header.year_field, header.display_year, header.stage_name), (7, 2011, "regular season"))
        self.assertEqual(header.seeds_a, (0xFF,) * 12)
        self.save.set_display_year(2012)
        self.assertEqual(self.save.header.year_field, 8)
        self.assertEqual(self.save.changed_ranges(), [(fs.SEASON_BLOCK + fs.S_YEAR, fs.SEASON_BLOCK + fs.S_YEAR + 1)])
        with self.assertRaisesRegex(fs.FranchiseSaveError, "year field"):
            self.save.set_year_field(128)
        with self.assertRaises(fs.FranchiseSaveError):
            self.save.set_display_year(2003)

    def test_divisions_user_control_and_order(self) -> None:
        self.assertEqual(self.save.divisions[:9], (0, 1, 2, 3, 4, 5, 6, 7, 0))
        self.assertEqual(self.save.user_teams(), [0])
        self.save.set_user_control(0, False)
        self.save.set_user_control(5, True)
        self.assertEqual(self.save.user_teams(), [5])
        with self.assertRaises(fs.FranchiseSaveError):
            self.save.set_user_control(32, True)
        self.assertEqual(self.save.team_order[:3], (0, 1, 2))
        self.assertEqual(self.save.team_order[32:], (0xFF, 0xFF))

    def test_grid_games_scores_and_edit(self) -> None:
        games = self.save.games()
        self.assertEqual(len(games), 2)
        played, scheduled = games
        self.assertTrue(played.played)
        self.assertEqual((played.home, played.away, played.month, played.day, played.kickoff()), (1, 0, 9, 12, "1:00"))
        self.assertEqual(played.scores, ((7, 0, 3, 7, 0), (0, 7, 7, 3, 0)))
        self.assertEqual(played.flags, 0x0101)
        self.assertEqual(played.row_name, "week 1")
        self.assertIsNone(scheduled.scores)
        self.assertEqual(scheduled.kickoff(), "4:15")
        with self.assertRaisesRegex(fs.FranchiseSaveError, "played"):
            self.save.set_game(0, 0, home=4)
        with self.assertRaisesRegex(fs.FranchiseSaveError, "filler"):
            self.save.set_game(0, 2, home=4)
        with self.assertRaisesRegex(fs.FranchiseSaveError, "play itself"):
            self.save.set_game(0, 1, home=3)
        updated = self.save.set_game(0, 1, home=7, away=9, month=10, day=3, hour=8, minute=30)
        self.assertEqual((updated.home, updated.away, updated.month, updated.day, updated.kickoff()), (7, 9, 10, 3, "8:30"))
        self.assertEqual(self.save.changed_ranges(),                     # slot_code (+5) was left alone
                         [(updated.offset + 1, updated.offset + 5), (updated.offset + 6, updated.offset + 8)])
        edited = self.save.set_game(0, 0, home=5, allow_played=True)
        self.assertEqual(edited.home, 5)
        with self.assertRaises(fs.FranchiseSaveError):
            self.save.set_game(0, 1, month=13)
        with self.assertRaises(fs.FranchiseSaveError):
            self.save.game(22, 0)
        self.assertEqual(fs.FranchiseSave.cell(21, 16), 373)

    def test_salary_cap(self) -> None:
        self.assertEqual(self.save.salary_cap, 80_500)
        self.save.set_salary_cap(102_000)
        self.assertEqual(self.save.salary_cap, 102_000)
        self.assertEqual(self.save.changed_ranges(), [(0x9ACCC, 0x9ACCE)])
        with self.assertRaises(fs.FranchiseSaveError):
            self.save.set_salary_cap(0)
        self.assertEqual(self.save.summary()["salary_cap_text"], "$102.0M")

    def test_injured_reserve_place_and_activate(self) -> None:
        save = self.save
        team = 0
        count, slots = save._team_slots(team)
        self.assertGreaterEqual(count, 2)
        victim_offset = slots[0]
        victim = save.player_index(victim_offset)
        self.assertEqual(save.injured_reserve(), [])
        self.assertEqual(save.team_player_indices(team), [save.player_index(offset) for offset in slots[:count]])
        entry = save.place_on_injured_reserve(team, victim)
        self.assertEqual(save.team_player_indices(team), [save.player_index(offset) for offset in slots[1:count]])
        with self.assertRaises(fs.FranchiseSaveError):
            save.team_player_indices(31)
        self.assertEqual((entry.team, entry.slot, entry.player_index), (team, 0, victim))
        self.assertEqual(entry.name, save.player_name(victim))
        new_count, new_slots = save._team_slots(team)
        self.assertEqual(new_count, count - 1)
        self.assertEqual(new_slots[:count - 1], slots[1:count])               # compacted
        self.assertIsNone(new_slots[count - 1])                               # last slot cleared
        self.assertEqual(save.buffer[victim_offset + 0x28], fs.IR_MARK)
        self.assertEqual([(e.team, e.player_index) for e in save.injured_reserve()], [(team, victim)])
        self.assertEqual(save.u16(entry.offset), victim)
        with self.assertRaisesRegex(fs.FranchiseSaveError, "not on team"):
            save.place_on_injured_reserve(team, victim)
        # the reverse move
        save.activate_from_injured_reserve(team, victim)
        back_count, back_slots = save._team_slots(team)
        self.assertEqual(back_count, count)
        self.assertEqual(set(back_slots[:count]), set(slots[:count]))
        self.assertEqual(back_slots[count - 1], victim_offset)               # re-added at the end
        self.assertEqual(save.buffer[victim_offset + 0x28], 0)
        self.assertEqual(save.injured_reserve(), [])
        with self.assertRaisesRegex(fs.FranchiseSaveError, "not on team 0's injured reserve"):
            save.activate_from_injured_reserve(team, victim)
        # a full IR table is refused
        for slot in range(fs.IR_SLOTS):
            struct.pack_into("<H", save.buffer, fs.FRONT_OFFICE_BLOCK + fs.F_INJURED_RESERVE + slot * fs.IR_ENTRY, 1)
        with self.assertRaisesRegex(fs.FranchiseSaveError, "already has 5"):
            save.place_on_injured_reserve(team, victim)
        with self.assertRaises(fs.FranchiseSaveError):
            save.place_on_injured_reserve(31, victim)                          # not an NFL team in this arena

    def test_team_seasons_coaches_and_tables(self) -> None:
        seasons = self.save.team_seasons()
        self.assertEqual(len(seasons), self.save.league_team_count)
        self.assertEqual(seasons[0].games_played, 0)
        self.assertEqual(seasons[0].stat("passing_yards"), 0)
        self.assertEqual(set(seasons[0].stats), set(fs.TEAM_STAT_FIELDS.values()))
        self.save.set_team_record_ring(0, 0, 9)
        self.assertEqual(self.save.team_season(0).record_ring[0], 9)
        self.assertEqual(self.save.coaches(), [])                              # the synthetic arena has no coaches
        self.assertIsNone(self.save.coach_for_team(0))
        with self.assertRaises(fs.FranchiseSaveError):
            self.save.set_coach_field(0, "wins", 1)
        self.assertEqual(self.save.team_ranks(), tuple(range(1, 33)))
        self.assertEqual(self.save.order_table(0), (0,) * 32)
        self.assertEqual(len(self.save.trades()), 15)
        self.assertEqual(len(self.save.fa_bids()), 100)
        self.assertEqual(self.save.transactions(), [])
        ledger = self.save.ledger()
        self.assertEqual(len(ledger), 1)
        self.assertEqual(ledger[0]["packed"], 0x8000002A)
        self.assertEqual(self.save.template_table[0], 0)                       # synthetic body has no template

    def test_summary_and_one_line(self) -> None:
        summary = self.save.summary()
        self.assertEqual((summary["display_year"], summary["stage_name"], summary["user_teams"]), (2011, "regular season", [0]))
        self.assertEqual(summary["games_played"], 1)
        line = self.save.one_line()
        self.assertIn("2011", line)
        self.assertIn("$80.5M", line)
        self.assertIn("1/2 grid games played", line)


@unittest.skipUnless(F0.is_file() and F1.is_file(), f"private 8007Fran fixtures missing under {FIXTURES}")
class RealFinnFixtureTests(unittest.TestCase):
    def test_finn_ir_move_is_reproduced_byte_for_byte(self) -> None:
        f0 = fs.FranchiseSave.load(F0.parents[3])
        f1 = F1.read_bytes()
        self.assertEqual(f0.to_bytes(), F0.read_bytes())
        self.assertEqual(f0.header.display_year, 2004)
        self.assertEqual(f0.salary_cap, 80_500)
        self.assertEqual(f0.injured_reserve(), [])
        entry = f0.place_on_injured_reserve(0, 1369)
        self.assertEqual((entry.name, entry.offset), ("Harris Barton", 0x9E6CC))
        self.assertEqual(f0.to_bytes(), f1)
        # and back
        again = fs.FranchiseSave(f1)
        again.activate_from_injured_reserve(0, 1369)
        original = F0.read_bytes()
        self.assertEqual(again.to_bytes()[:0x44A8], original[:0x44A8])
        self.assertEqual(again.to_bytes()[0x44A8 + 0x104:], original[0x44A8 + 0x104:])
        self.assertEqual(again.injured_reserve(), [])

    def test_coach_records_carry_real_career_numbers(self) -> None:
        f0 = fs.FranchiseSave(F0.read_bytes())
        belichick = f0.coach_for_team(21)
        assert belichick is not None
        self.assertEqual(belichick.name, "Bill Belichick")
        self.assertEqual((belichick.fields["wins"], belichick.fields["losses"]), (75, 69))
        self.assertEqual((belichick.fields["super_bowls"], belichick.fields["playoff_wins"], belichick.fields["playoff_losses"]), (2, 7, 1))
        self.assertEqual(belichick.ratings["overall"], 99)
        self.assertIn(21, belichick.teams)
        self.assertEqual(len(f0.coaches()), 35)
        self.assertEqual(f0.template_table[0], 256)
        self.assertEqual(len(f0.games(rows=[0])), 16)
        self.assertEqual(f0.team_salary(21), 78_509)


@unittest.skipUnless(FRANCHISE1.is_file(), f"private Franchise1 fixture missing under {FIXTURES}")
class RealFranchise1Tests(unittest.TestCase):
    def test_year_seven_lions_franchise_decodes_and_resigns(self) -> None:
        save = fs.FranchiseSave.load(FRANCHISE1.parents[3])
        self.assertEqual(save.to_bytes(), FRANCHISE1.read_bytes())
        summary = save.summary()
        self.assertEqual((summary["display_year"], summary["stage"], summary["user_team_names"]), (2011, 1, ["DET"]))
        self.assertEqual(summary["salary_cap"], 88_113)                        # 80,500 x 1.013^7
        self.assertEqual(sorted(save.team_ranks()), list(range(1, 33)))
        self.assertEqual(sorted(save.order_table(0)), list(range(32)))
        coach = save.coach_for_team(18)
        assert coach is not None
        self.assertEqual(coach.name, "Steve Mariucci")
        self.assertGreater(coach.fields["wins"], 100)
        save.set_salary_cap(90_000)
        save.set_coach_field(coach.index, "wins", coach.fields["wins"] + 1)
        with tempfile.TemporaryDirectory() as td:
            receipt = save.write(Path(td) / "copy")
            self.assertTrue(receipt["signed"])
            back = fs.FranchiseSave.load(Path(td) / "copy")
            self.assertTrue(back.container is not None and back.container.verified)
            self.assertEqual(back.salary_cap, 90_000)
            assert back.coach_for_team(18) is not None
            self.assertEqual(back.coach_for_team(18).fields["wins"], coach.fields["wins"] + 1)
        self.assertEqual(FRANCHISE1.read_bytes(), save.original)             # the source is untouched


if __name__ == "__main__":
    unittest.main()

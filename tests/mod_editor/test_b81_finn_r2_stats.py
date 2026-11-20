"""Finn's Team Statistics tab and Boxscore editor on the Franchise page (b81 R41, parity rows I2 and H7).

Core tests run on the synthetic franchise save everywhere. The signed SOFTDRINK franchise saves are used when present
(skipped, with the path, when not): a simulated 2026 regular season (272 played games) and the Week 1 save whose
scores, quarter bytes and team totals FACTS.md cites. The native cold load of an edited copy (the game's own loader and
standings getters) is in the lane evidence, ``finn-r2/evidence/box_score_native.py``.
"""

from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor", ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication, QDialogButtonBox  # noqa: E402

from mod_editor.core import nfl2k5_franchise_save as fs  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_team_stats as ts  # noqa: E402
from mod_editor.gui.roster_editor_panel_qt import RosterEditorPanel  # noqa: E402
from test_nfl2k5_franchise_save import synthetic_franchise  # noqa: E402
from test_roster_editor_panel_franchise import write_container  # noqa: E402

SEASON_2026 = Path(os.environ.get(
    "NFL2K5_SOFTDRINK_SEASON_SAVE",
    "/media/noah/Storage/2K5-project/beta81/cpu-sim/catalog-disc-128-dynasty-signed/2026"))
WEEK_ONE = Path(os.environ.get(
    "NFL2K5_SOFTDRINK_FRANCHISE_SAVE",
    "/media/noah/Storage/2K5-project/beta81/cpu-sim/played-game-beta80/SAVEGAME.DAT"))

# Finn's installed ENFDefaultTeamStatViewSettings.ini, visible columns after Team, in order (receipt
# finn-facts/evidence/team-season-and-box/native-and-saved-fields.json "finn_visible_columns")
FINN_INI_COLUMNS = (
    ("TYO", "TYO"), ("PASS", "PASS"), ("AVGPASS", "AVG PASS"), ("RUSH", "RUSH"), ("AVGRUSH", "AVG RUSH"),
    ("TYD", "TYD"), ("DPA", "DPA"), ("DRA", "DRA"), ("FIRSTDOWNS", "1st"), ("THIRDATT", "3rd ATT"),
    ("THIRDMD", "3rd MD"), ("THIRDPERCENT", "3rd %"), ("FOURTHATT", "4th ATT"), ("FOURTHMD", "4th MD"),
    ("FOURTHPERCENT", "4th %"), ("RZA", "RZA"), ("RZTD", "RZTD"), ("RZFG", "RZFG"), ("RZPERCENT", "RZ %"),
    ("DRZ", "DRZ"), ("RZTA", "RZTA"), ("RZFGA", "RZFGA"), ("RZSPERCENT", "RZS %"), ("PEN", "PEN"), ("YD", "YD"),
    ("TURNOVER", "TO"), ("PTO", "PTO"), ("TPS", "TPS"), ("TPSA", "TPSA"), ("PPLY", "PPLY"), ("RPLY", "RPLY"),
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _changed(a: bytes, b: bytes) -> list[int]:
    return [i for i, (x, y) in enumerate(zip(a, b)) if x != y]


def _team_word(save: fs.FranchiseSave, team: int, rel: int) -> int:
    return save.u16(save.team_offset(team) + rel)


def synthetic_with_playoff() -> bytes:
    """The synthetic franchise (Week 1: team 1 hosts team 0, a 17-17 tie) plus a played wild-card game: team 2 beats
    visiting team 1, 21-10."""

    data = bytearray(synthetic_franchise())
    save = fs.FranchiseSave(bytes(data))
    block = save.season_block
    cell = save.cell(save.regular_season_weeks, 0)
    data[block + fs.S_GRID + 8 * cell:block + fs.S_GRID + 8 * cell + 8] = bytes([3, 2, 1, 1, 9, 0x0A, 1, 0])
    struct.pack_into("<H", data, block + fs.S_GRID_FLAGS + 2 * cell, 0x0101)
    data[block + fs.S_SCORES + 10 * cell:block + fs.S_SCORES + 10 * cell + 10] = bytes([7, 7, 0, 7, 0, 3, 0, 7, 0, 0])
    for team, points in ((0, (17, 17)), (1, (17, 17))):          # the season totals agree with the Week 1 tie
        base = save.team_offset(team)
        struct.pack_into("<HH", data, base + ts.TEAM_POINTS_FOR, *points)
    return bytes(data)


# --------------------------------------------------------------------------------------------- core
class ColumnTests(unittest.TestCase):
    def test_finns_31_columns_in_his_order_with_his_captions(self) -> None:
        self.assertEqual(tuple((c.key, c.caption) for c in ts.FINN_COLUMNS), FINN_INI_COLUMNS)

    def test_every_stored_word_shown_is_one_the_game_merges(self) -> None:
        stored = set(fs.TEAM_STAT_FIELDS.values())
        for column in ts.FINN_COLUMNS + ts.EXTRA_COLUMNS:
            self.assertTrue(set(column.numerator + column.denominator) <= stored, column.key)
        # the six counters with no caption in the game or Finn stay out of the table
        shown = {s for c in ts.FINN_COLUMNS + ts.EXTRA_COLUMNS for s in c.numerator + c.denominator}
        self.assertEqual(stored - shown, {0xB8, 0x30, 0x40, 0x3F, 0x16, 0x17})

    def test_rates_use_the_games_formulas_and_a_zero_denominator_is_a_dash(self) -> None:
        season = fs.TeamSeason(0, "SF", 0, (0,) * 7, 1, {0x4C: 0xFFF4, 0x50: 5, 0x53: 5, 0x27: 14, 0xB1: 1, 0xB2: 0,
                                                         0xB3: 1, 0x25: 0, 0x26: 2}, (0, 0, 0, 0))
        by_key = {c.key: c for c in ts.FINN_COLUMNS}
        self.assertEqual(ts.column_value(season, by_key["TYO"]), -7)          # FACTS: -12 + 5 reads as -7
        self.assertEqual(ts.column_value(season, by_key["THIRDPERCENT"]), 35.7)
        self.assertEqual(ts.column_value(season, by_key["RZPERCENT"]), 100.0)
        self.assertIsNone(ts.column_value(season, by_key["AVGPASS"]))
        self.assertEqual(ts.format_value(None, by_key["AVGPASS"]), "-")
        self.assertEqual(ts.column_value(season, by_key["AVGRUSH"]), 2.5)
        self.assertEqual(ts.format_value(35.7, by_key["THIRDPERCENT"]), "35.7%")


class BoxScoreCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = synthetic_with_playoff()
        self.save = fs.FranchiseSave(self.payload)

    def test_the_first_five_bytes_are_home_and_standings_count_them(self) -> None:
        box = ts.box_score(self.save, 0, 0)
        self.assertEqual((box.home, box.away, box.home_quarters, box.away_quarters), (1, 0, (7, 0, 3, 7, 0), (0, 7, 7, 3, 0)))
        self.assertIsNone(box.winner)
        self.assertEqual(ts.standings(self.save), {0: (0, 0, 1), 1: (0, 1, 1), 2: (1, 0, 0)})

    def test_an_edit_writes_ten_bytes_and_both_clubs_points_and_moves_the_standings(self) -> None:
        receipt = ts.set_box_score(self.save, 0, 0, [7, 0, 3, 7, 0], [0, 7, 7, 3, 7])
        after = self.save.to_bytes()
        score_at = self.save.season_block + fs.S_SCORES
        points = {self.save.team_offset(t) + rel + k for t in (0, 1) for rel in (ts.TEAM_POINTS_FOR, ts.TEAM_POINTS_AGAINST)
                  for k in (0, 1)}
        self.assertTrue(set(_changed(self.payload, after)) <= set(range(score_at, score_at + 10)) | points)
        self.assertEqual(after[score_at:score_at + 10], bytes([7, 0, 3, 7, 0, 0, 7, 7, 3, 7]))
        self.assertEqual(ts.standings(self.save)[0], (1, 0, 0))
        self.assertEqual(ts.standings(self.save)[1], (0, 2, 0))
        self.assertEqual((_team_word(self.save, 0, ts.TEAM_POINTS_FOR), _team_word(self.save, 0, ts.TEAM_POINTS_AGAINST)),
                         (24, 17))
        self.assertEqual((_team_word(self.save, 1, ts.TEAM_POINTS_FOR), _team_word(self.save, 1, ts.TEAM_POINTS_AGAINST)),
                         (17, 24))
        self.assertEqual(receipt["before"], [17, 17])
        self.assertEqual(receipt["after"], [24, 17])

    def test_season_points_can_be_left_alone(self) -> None:
        ts.set_box_score(self.save, 0, 0, [7, 0, 3, 7, 3], [0, 7, 7, 3, 0], season_points=False)
        self.assertEqual(_changed(self.payload, self.save.to_bytes()),
                         [self.save.season_block + fs.S_SCORES + 4])

    def test_refusals_change_nothing(self) -> None:
        cases = (
            ((0, 0, [256, 0, 0, 0, 0], [0] * 5), "outside 0..255"),
            ((0, 0, [1, 2, 3, 4], [0] * 5), "five numbers"),
            ((0, 1, [0] * 5, [0] * 5), "has not been played"),
            ((17, 0, [0] * 5, [0] * 5), "tie"),
            ((17, 0, [0] * 5, [21, 0, 0, 0, 0]), "keeps its winner"),
            ((0, 0, [0] * 5, [0] * 5), "outside 0..65535"),     # team 2 has no points to give back
        )
        struct.pack_into("<H", self.save.buffer, self.save.team_offset(1) + ts.TEAM_POINTS_FOR, 3)
        start = self.save.to_bytes()
        for (row, slot, home, away), words in cases:
            with self.subTest(words=words), self.assertRaisesRegex(fs.FranchiseSaveError, words):
                ts.set_box_score(self.save, row, slot, home, away)
            self.assertEqual(self.save.to_bytes(), start)

    def test_a_playoff_game_keeps_its_winner_and_its_season_points(self) -> None:
        receipt = ts.set_box_score(self.save, 17, 0, [7, 7, 0, 7, 3], [3, 0, 7, 0, 0])
        self.assertTrue(receipt["season_points_skipped"])
        self.assertEqual(receipt["season_points"], [])
        self.assertTrue(ts.box_score(self.save, 17, 0).postseason)

    def test_swapping_a_played_games_sides_keeps_each_clubs_score(self) -> None:
        ts.set_box_score(self.save, 0, 0, [7, 0, 3, 7, 3], [0, 7, 7, 3, 0], season_points=False)
        before = ts.standings(self.save)
        ts.swap_played_sides(self.save, 0, 0)
        box = ts.box_score(self.save, 0, 0)
        self.assertEqual((box.home, box.away, box.home_points, box.away_points), (0, 1, 17, 20))
        self.assertEqual(ts.standings(self.save), before)

    def test_csv_exports(self) -> None:
        lines = ts.csv_text(self.save).splitlines()
        self.assertEqual(lines[0].split(",")[:4], ["Team", "W-L-T", "GP", "TYO"])
        self.assertEqual(len(lines), 1 + self.save.league_team_count)
        scores = ts.scores_csv_text(self.save).splitlines()
        self.assertEqual(len(scores), 3)
        self.assertTrue(scores[1].startswith("Week 1,1,"), scores[1])


@unittest.skipUnless(SEASON_2026.is_dir(), f"simulated SOFTDRINK 2026 season save absent: {SEASON_2026}")
class SoftdrinkSeasonTests(unittest.TestCase):
    """A simulated SOFTDRINK 2026 regular season (272 played games), signed by the game's own save path."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.container = rr.SaveContainer.load(SEASON_2026)
        cls.save = fs.FranchiseSave(cls.container.savegame)

    def test_the_games_own_totals_equal_the_box_score_sums_for_every_club(self) -> None:
        self.assertTrue(self.container.verified)
        sums = {team: [0, 0, 0] for team in range(32)}
        for box in ts.box_scores(self.save):
            for team, mine, theirs in ((box.home, box.home_points, box.away_points),
                                       (box.away, box.away_points, box.home_points)):
                sums[team][0] += mine
                sums[team][1] += theirs
                sums[team][2] += 1
        rows = ts.league_table(self.save)
        self.assertEqual(len(rows), 32)
        for row in rows:
            self.assertEqual([row.values["TPS"], row.values["TPSA"], row.games_played], sums[row.team], row.abbreviation)
        records = [row.record for row in rows]
        self.assertEqual(tuple(map(sum, zip(*records))), (272, 272, 0))

    def test_the_sf_row_reads_the_stored_words(self) -> None:
        sf = ts.league_table(self.save)[0]
        season = self.save.team_season(0)
        self.assertEqual(sf.abbreviation, "SF")
        self.assertEqual(sf.values["TYO"], season.stats[0x4C] + season.stats[0x50])
        self.assertEqual(sf.values["TYD"], season.stats[0x45] + season.stats[0x46])
        self.assertEqual(sf.values["PEN"], season.stats[0x24])
        self.assertEqual(sf.values["THIRDPERCENT"], round(100 * season.stats[0x53] / season.stats[0x27], 1))


@unittest.skipUnless(WEEK_ONE.is_file(), f"signed SOFTDRINK Week 1 franchise absent: {WEEK_ONE}")
class SoftdrinkWeekOneTests(unittest.TestCase):
    def test_facts_md_scores_and_totals(self) -> None:
        save = fs.FranchiseSave(rr.SaveContainer.load(WEEK_ONE).savegame)
        box = ts.box_score(save, 0, 0)
        self.assertEqual((save.team_abbreviation(box.home), save.team_abbreviation(box.away)), ("LAR", "SF"))
        self.assertEqual((box.home_quarters, box.away_quarters), ((14, 10, 7, 3, 0), (0, 3, 0, 3, 0)))
        sf = ts.league_table(save)[0]
        self.assertEqual((sf.values["PASS"], sf.values["RUSH"], sf.values["TYO"], sf.values["YD"]), (128, 117, 245, 25))
        self.assertEqual((sf.values["TPS"], sf.values["TPSA"], sf.record), (6, 34, (0, 1, 0)))


# --------------------------------------------------------------------------------------------- screens
class StatsScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = _app()

    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.payload = synthetic_with_playoff()
        self.panel = RosterEditorPanel()
        self.assertTrue(self.panel.load_save(write_container(self.root / "fr", self.payload)))
        self.page = self.panel.franchise_panel

    def tearDown(self) -> None:
        self.panel.deleteLater()
        self.application.processEvents()
        self.folder.cleanup()

    def test_the_stats_tab_is_last_and_reads_the_save(self) -> None:
        tabs = self.page.tabs
        self.assertEqual(tabs.tabText(tabs.count() - 1), "Team Stats")
        self.assertEqual(tabs.tabText(4), "Checks")                          # the older tab positions stay put
        table = self.page.stats_page.table
        self.assertEqual(table.rowCount(), self.page.save.league_team_count)
        self.assertEqual(table.columnCount(), 3 + len(ts.FINN_COLUMNS) + len(ts.EXTRA_COLUMNS))
        self.assertEqual([table.horizontalHeaderItem(i).text() for i in range(3, 34)], [c for _k, c in FINN_INI_COLUMNS])
        texts = self.page.stats_page.row_texts()
        self.assertEqual([row[1] for row in texts], ["0-0-1", "0-1-1", "1-0-0"])
        tps = 3 + [key for key, _caption in FINN_INI_COLUMNS].index("TPS")
        self.assertEqual(texts[1][tps], "17")
        self.assertFalse(table.item(0, 5).flags() & Qt.ItemIsEditable)

    def test_sorting_is_numeric_and_survives_a_refresh(self) -> None:
        table = self.page.stats_page.table
        table.sortItems(1, Qt.DescendingOrder)                             # W-L-T, best first
        self.assertEqual([table.item(r, 1).text() for r in range(3)], ["1-0-0", "0-0-1", "0-1-1"])
        self.assertTrue(self.page.edit_box_score(0, 0, [7, 0, 3, 7, 0], [0, 7, 7, 3, 7]))   # team 0 wins Week 1 now
        self.assertEqual([table.item(r, 1).text() for r in range(3)], ["1-0-0", "1-0-0", "0-2-0"])
        self.page.stats_page.team_order()
        self.assertTrue(table.item(0, 0).text().startswith(self.page.save.team_abbreviation(0)))

    def test_box_score_dialog_and_apply_through_the_journal(self) -> None:
        self.page.tabs.setCurrentIndex(1)
        dialog = self.page.box_score_dialog(0, 0)
        ok = dialog.buttons.button(QDialogButtonBox.Ok)
        self.assertEqual((dialog.quarters("home"), dialog.quarters("away")), ((7, 0, 3, 7, 0), (0, 7, 7, 3, 0)))
        self.assertFalse(ok.isEnabled())                                   # nothing changed yet
        dialog.spins["away"][4].setValue(3)
        self.assertTrue(ok.isEnabled())
        self.assertIn("win 20-17", dialog.result_label.text())
        self.assertTrue(dialog.season_points())
        self.assertTrue(self.page.edit_box_score(0, 0, dialog.quarters("home"), dialog.quarters("away"),
                                                 season_points=dialog.season_points()))
        self.assertEqual(ts.box_score(self.page.save, 0, 0).away_points, 20)
        self.panel.undo()
        self.assertEqual(ts.box_score(self.page.save, 0, 0).away_points, 17)
        self.panel.redo()
        self.assertEqual(ts.box_score(self.page.save, 0, 0).away_points, 20)
        receipt = self.panel.write_copy_to(self.root / "copy")
        self.assertTrue(receipt["signed"])
        container = rr.SaveContainer.load(self.root / "copy")
        self.assertTrue(container.verified)
        back = fs.FranchiseSave(container.savegame)
        self.assertEqual(ts.box_score(back, 0, 0).away_quarters, (0, 7, 7, 3, 3))
        self.assertEqual(_team_word(back, 0, ts.TEAM_POINTS_FOR), 20)
        self.assertTrue(set(_changed(self.payload, container.savegame)) <=
                        set(range(back.season_block + fs.S_SCORES, back.season_block + fs.S_SCORES + 10))
                        | {back.team_offset(t) + r + k for t in (0, 1) for r in (0x1D8, 0x1DA) for k in (0, 1)})

    def test_a_playoff_box_score_refuses_a_new_winner_in_the_dialog(self) -> None:
        dialog = self.page.box_score_dialog(17, 0)
        ok = dialog.buttons.button(QDialogButtonBox.Ok)
        self.assertFalse(dialog.season_points_check.isEnabled())
        dialog.set_quarters("away", [21, 0, 0, 0, 0])
        self.assertIn("cannot end in a tie", dialog.problem())
        dialog.set_quarters("away", [22, 0, 0, 0, 0])
        self.assertFalse(ok.isEnabled())
        self.assertIn("keeps its winner", dialog.problem())
        dialog.set_quarters("away", [3, 0, 7, 0, 0])
        dialog.set_quarters("home", [7, 7, 0, 7, 3])
        self.assertTrue(ok.isEnabled())
        self.assertFalse(self.page.edit_box_score(17, 0, [0] * 5, [21, 0, 0, 0, 0]))
        self.assertIn("keeps its winner", self.page.status_label.text())

    def test_box_score_button_follows_the_selected_game_and_a_played_swap_moves_the_scores(self) -> None:
        self.page.week_combo.setCurrentIndex(0)
        self.page.schedule_table.selectRow(1)                               # the scheduled game
        self.assertFalse(self.page.box_score_button.isEnabled())
        self.page.schedule_table.selectRow(0)
        self.assertTrue(self.page.box_score_button.isEnabled())
        self.page.edit_box_score(0, 0, [7, 0, 3, 7, 3], [0, 7, 7, 3, 0], season_points=False)
        self.assertFalse(self.page.swap_home_away(0, 0))                    # played: needs the tick
        self.page.allow_played_check.setChecked(True)
        self.assertTrue(self.page.swap_home_away(0, 0))
        box = ts.box_score(self.page.save, 0, 0)
        self.assertEqual((box.home, box.home_points, box.away, box.away_points), (0, 17, 1, 20))
        score = self.page.schedule_table.item(0, 6).text()
        self.assertEqual(score, "20-17")                                    # away-home, like the columns


@unittest.skipUnless(SEASON_2026.is_dir(), f"simulated SOFTDRINK 2026 season save absent: {SEASON_2026}")
class SoftdrinkScreenTests(unittest.TestCase):
    def test_the_season_table_and_one_box_score_reach_a_signed_copy(self) -> None:
        application = _app()
        panel = RosterEditorPanel()
        try:
            self.assertTrue(panel.load_save(SEASON_2026))
            page = panel.franchise_panel
            self.assertEqual(page.stats_page.table.rowCount(), 32)
            first = ts.box_score(page.save, 0, 0)
            away = list(first.away_quarters)
            away[4] += 7
            self.assertTrue(page.edit_box_score(0, 0, list(first.home_quarters), away), page.status_label.text())
            with tempfile.TemporaryDirectory() as folder:
                receipt = panel.write_copy_to(Path(folder) / "copy")
                self.assertTrue(receipt["signed"])
                copy = rr.SaveContainer.load(Path(folder) / "copy")
                self.assertTrue(copy.verified)
                original = rr.SaveContainer.load(SEASON_2026).savegame
                back = fs.FranchiseSave(copy.savegame)
                score_byte = back.season_block + fs.S_SCORES + 9
                points = {back.team_offset(first.away) + ts.TEAM_POINTS_FOR + k for k in (0, 1)} | \
                    {back.team_offset(first.home) + ts.TEAM_POINTS_AGAINST + k for k in (0, 1)}
                changed = set(_changed(original, copy.savegame))
                self.assertIn(score_byte, changed)
                self.assertTrue(changed - {score_byte} and changed - {score_byte} <= points, changed)
                self.assertEqual(ts.box_score(back, 0, 0).away_points, first.away_points + 7)
                reread = panel.load_save(Path(folder) / "copy")
                self.assertTrue(reread)
        finally:
            panel.deleteLater()
            application.processEvents()


if __name__ == "__main__":
    unittest.main()

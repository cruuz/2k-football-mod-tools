"""Fixes from the independent review of b81 finn-r2 (rev-finn/REVIEW.md, findings F1 to F7).

Each test was written to fail on 60613c51a first (log: finn-r2/logs/review_fixes_before.log). The signed SOFTDRINK
franchise saves are used when present (skipped, with the path, when not).
"""

from __future__ import annotations

import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor", ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.core import nfl2k5_coach_file as cf  # noqa: E402
from mod_editor.core import nfl2k5_depth_file as df  # noqa: E402
from mod_editor.core import nfl2k5_franchise_save as fs  # noqa: E402
from mod_editor.core import nfl2k5_player_health as ph  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_team_stats as ts  # noqa: E402
from mod_editor.gui.franchise_stats_qt import TeamStatsPage  # noqa: E402
from mod_editor.gui.roster_editor_panel_qt import RosterEditorPanel  # noqa: E402
from test_nfl2k5_franchise_save import synthetic_franchise  # noqa: E402

CPU = Path("/media/noah/Storage/2K5-project/beta81/cpu-sim")
SEASON_2026 = Path(os.environ.get("NFL2K5_SOFTDRINK_SEASON_SAVE", str(CPU / "catalog-disc-128-dynasty-signed/2026")))
POSTSEASON_2029 = Path(os.environ.get("NFL2K5_SOFTDRINK_POSTSEASON_SAVE", str(CPU / "last-warning-off/2029")))
ROSTER_SAVE = Path(os.environ.get("NFL2K5_SOFTDRINK_ROSTER_SAVE",
                                  "/media/noah/Storage/2K5-project/beta81/isolated-data/FC3-native-roster.zip"))


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _club(save: fs.FranchiseSave, abbreviation: str) -> int:
    return next(t for t in range(save.league_team_count) if save.team_abbreviation(t) == abbreviation)


def _sums(save: fs.FranchiseSave, team: int) -> tuple[int, int, int]:
    """Points for, points against and games played over every played box score (regular season and playoffs)."""

    scored = allowed = played = 0
    for box in ts.box_scores(save):
        for club, mine, theirs in ((box.home, box.home_points, box.away_points),
                                   (box.away, box.away_points, box.home_points)):
            if club == team:
                scored, allowed, played = scored + mine, allowed + theirs, played + 1
    return scored, allowed, played


def _win_streak(save: fs.FranchiseSave, team: int) -> int:
    run = 0
    for game in sorted(save.games(), key=lambda g: (g.row, g.slot)):
        if game.played and team in (game.home, game.away):
            home, away = sum(game.scores[0]), sum(game.scores[1])
            mine, theirs = (home, away) if game.home == team else (away, home)
            run = run + 1 if mine > theirs else 0
    return run


def _coach_records(save: fs.FranchiseSave, team: int) -> tuple[tuple[int, ...], tuple[int, ...]]:
    offset = save._coach_offset(save.head_coach_index(team))
    return struct.unpack_from("<3H", save.buffer, offset + 0x20), struct.unpack_from("<3H", save.buffer, offset + 0x26)


# --------------------------------------------------------------------------------------------- F1
class F1HealAndInjuredReserveTests(unittest.TestCase):
    """An injury id whose low byte is 0xEE (the game's own id 750 = 0x2EE) is not Finn's IR marker."""

    def test_the_marker_rule_needs_finns_exact_value_on_a_player_who_is_not_hurt(self) -> None:
        hurt_750 = {"injured_reserve": 0xEE, "unknown_29_low": 2, "unknown_20_high": 0x305, "unknown_27_high": 4}
        self.assertEqual(ph.heal_refusal(hurt_750, on_listed_ir=False, franchise=True), "")
        self.assertEqual(ph.heal_refusal(hurt_750, on_listed_ir=False, franchise=False), "")
        self.assertEqual(ph.heal_refusal(hurt_750, on_listed_ir=True, franchise=True), ph.REASON_IR)
        finn = {"injured_reserve": 0xEE, "unknown_29_low": 0, "unknown_20_high": 0, "unknown_27_high": 4}
        self.assertEqual(ph.heal_refusal(finn, on_listed_ir=False, franchise=False), ph.REASON_IR)   # roster save
        self.assertEqual(ph.heal_refusal(finn, on_listed_ir=False, franchise=True), "")              # list decides
        self.assertTrue(rr.finn_ir_marker(finn) and not rr.finn_ir_marker(hurt_750))

    @unittest.skipUnless(SEASON_2026.is_dir(), f"simulated SOFTDRINK 2026 season absent: {SEASON_2026}")
    def test_tj_edwards_can_be_healed_released_and_batch_released(self) -> None:
        application = _app()
        panel = RosterEditorPanel()
        self.addCleanup(lambda: (panel.deleteLater(), application.processEvents()))
        self.assertTrue(panel.load_save(SEASON_2026))
        document = panel.document
        edwards = next(p for p in document.players if p.display == "T.J. Edwards" and p.pool == "primary")
        values = edwards.record.values
        self.assertEqual((values["injured_reserve"], values["unknown_29_low"]), (0xEE, 2))       # the game's id 750
        self.assertNotIn(edwards.index, panel.listed_ir_indices())
        self.assertEqual(panel.heal_reason(edwards), "")
        document.check_operation(edwards, "release")                                           # no IR refusal
        teammate = next(p for p in document.team_players(1) if p is not edwards
                        and not p.record.values["injured_reserve"])
        for row in range(panel.team_list.count()):                         # open the Chicago list
            if tuple(panel.team_list.item(row).data(Qt.UserRole) or ()) == ("team", 1):
                panel.team_list.setCurrentRow(row)
                break
        plan, problems = panel.release_problems([edwards, teammate])
        self.assertEqual(problems, [])
        self.assertEqual(len(plan), 2)
        self.assertEqual(panel.heal_players([edwards]), 1)
        self.assertFalse(ph.hurt(edwards.record))


# --------------------------------------------------------------------------------------------- F2 and F3
@unittest.skipUnless(POSTSEASON_2029.is_dir(), f"SOFTDRINK 2029 postseason save absent: {POSTSEASON_2029}")
class F2PlayoffTotalsTests(unittest.TestCase):
    """Playoff games count in points for, points against and games played (all 32 clubs of two postseason saves)."""

    def test_the_lv_at_lac_wild_card_keeps_both_clubs_totals_equal_to_their_box_scores(self) -> None:
        save = fs.FranchiseSave(rr.SaveContainer.load(POSTSEASON_2029).savegame)
        lv, lac = _club(save, "LV"), _club(save, "LAC")
        for club in range(32):
            season = save.team_season(club)
            self.assertEqual(_sums(save, club), (season.stats[0x5B], season.stats[0x5C], season.games_played))
        box = ts.box_score(save, 18, 0)
        self.assertEqual((box.away, box.home, box.away_points, box.home_points), (lv, lac, 17, 16))
        ts.set_box_score(save, 18, 0, list(box.home_quarters), [7, 7, 3, 3, 0])
        for club in (lv, lac):
            season = save.team_season(club)
            self.assertEqual(_sums(save, club), (season.stats[0x5B], season.stats[0x5C], season.games_played))
        self.assertEqual(save.team_season(lv).stats[0x5B], 413)
        self.assertEqual(save.team_season(lac).stats[0x5C], 395)

    def test_the_pro_bowl_still_moves_no_club_total(self) -> None:
        save = fs.FranchiseSave(synthetic_franchise())
        cell, block = save.cell(21, 0), save.season_block
        save.buffer[block + fs.S_GRID + 8 * cell:block + fs.S_GRID + 8 * cell + 8] = bytes([3, 32, 33, 2, 6, 0, 1, 0])
        save.buffer[block + fs.S_SCORES + 10 * cell:block + fs.S_SCORES + 10 * cell + 10] = bytes([7, 7, 7, 7, 0, 0, 3, 0, 3, 0])
        receipt = ts.set_box_score(save, 21, 0, [7, 7, 7, 14, 0], [0, 3, 0, 3, 0])
        self.assertEqual(receipt["season_points"], [])


@unittest.skipUnless(SEASON_2026.is_dir(), f"simulated SOFTDRINK 2026 season absent: {SEASON_2026}")
class F3RecordsTests(unittest.TestCase):
    """A flipped regular-season result moves both head coaches' season and career W-L-T and the win-streak byte
    (+0x1F1), the counters the game itself moves every game (finn-r2/evidence/f3/f3-week1.json)."""

    def setUp(self) -> None:
        self.save = fs.FranchiseSave(rr.SaveContainer.load(SEASON_2026).savegame)
        self.sf, self.lar = _club(self.save, "SF"), _club(self.save, "LAR")

    def test_a_flip_moves_both_coaches_records_and_the_streaks(self) -> None:
        save = self.save
        box = ts.box_score(save, 0, 0)
        self.assertEqual((box.away, box.home, box.winner), (self.sf, self.lar, "away"))
        career = {t: _coach_records(save, t)[0] for t in (self.sf, self.lar)}
        season = {t: _coach_records(save, t)[1] for t in (self.sf, self.lar)}
        home = list(box.home_quarters)
        home[3] += 14                                                           # LAR wins now
        plan = ts.plan_box_score(save, 0, 0, home, list(box.away_quarters))
        self.assertIn("Kyle Shanahan", " ".join(plan["changes"]))
        ts.set_box_score(save, 0, 0, home, list(box.away_quarters))
        for team, delta in ((self.sf, (-1, 1, 0)), (self.lar, (1, -1, 0))):
            after_career, after_season = _coach_records(save, team)
            self.assertEqual(tuple(a - b for a, b in zip(after_career, career[team])), delta)
            self.assertEqual(tuple(a - b for a, b in zip(after_season, season[team])), delta)
            self.assertEqual(save.team_season(team).streak_bytes[3], _win_streak(save, team))
            self.assertEqual(after_season, ts.standings(save)[team])      # no playoff games in this save

    def test_a_flip_in_the_last_week_moves_both_win_streaks(self) -> None:
        save = self.save
        box = ts.box_score(save, save.regular_season_weeks - 1, 0)
        winner, loser = (box.home, box.away) if box.winner == "home" else (box.away, box.home)
        self.assertEqual(save.team_season(winner).streak_bytes[3], _win_streak(save, winner))
        self.assertGreater(save.team_season(winner).streak_bytes[3], 0)
        margin = abs(box.home_points - box.away_points) + 3
        home, away = list(box.home_quarters), list(box.away_quarters)
        if box.winner == "home":
            away[3] += margin
        else:
            home[3] += margin
        plan = ts.plan_box_score(save, box.row, 0, home, away)
        self.assertIn("win streak", " ".join(plan["changes"]))
        ts.set_box_score(save, box.row, 0, home, away)
        self.assertEqual(save.team_season(winner).streak_bytes[3], 0)
        self.assertEqual(save.team_season(loser).streak_bytes[3], _win_streak(save, loser))
        self.assertGreater(save.team_season(loser).streak_bytes[3], 0)

    def test_a_coach_whose_record_does_not_match_the_box_scores_is_left_alone_and_the_plan_says_so(self) -> None:
        save = self.save
        offset = save._coach_offset(save.head_coach_index(self.sf))
        struct.pack_into("<H", save.buffer, offset + 0x26, 3)               # he did not coach all of SF's games
        before = _coach_records(save, self.sf)
        box = ts.box_score(save, 0, 0)
        home = list(box.home_quarters)
        home[3] += 14
        plan = ts.plan_box_score(save, 0, 0, home, list(box.away_quarters))
        self.assertTrue(any("Kyle Shanahan" in text for text in plan["kept"]), plan["kept"])
        ts.set_box_score(save, 0, 0, home, list(box.away_quarters))
        self.assertEqual(_coach_records(save, self.sf), before)

    def test_the_dialog_lists_what_moves_and_what_stays_before_apply(self) -> None:
        application = _app()
        panel = RosterEditorPanel()
        self.addCleanup(lambda: (panel.deleteLater(), application.processEvents()))
        self.assertTrue(panel.load_save(SEASON_2026))
        dialog = panel.franchise_panel.box_score_dialog(0, 0)
        dialog.spins["home"][3].setValue(dialog.box.home_quarters[3] + 14)
        text = dialog.effects_label.text()
        self.assertIn("Kyle Shanahan", text)
        self.assertIn("Stays as it is", text)
        dialog.season_points_check.setChecked(False)
        self.assertIn("option is off", dialog.effects_label.text())


@unittest.skipUnless(POSTSEASON_2029.is_dir(), f"SOFTDRINK 2029 postseason save absent: {POSTSEASON_2029}")
class F3BracketTests(unittest.TestCase):
    def test_a_regular_season_edit_after_the_playoffs_were_seeded_says_the_bracket_stays(self) -> None:
        save = fs.FranchiseSave(rr.SaveContainer.load(POSTSEASON_2029).savegame)
        box = ts.box_score(save, 0, 0)
        home = list(box.home_quarters)
        home[4] += 1
        plan = ts.plan_box_score(save, 0, 0, home, list(box.away_quarters))
        self.assertTrue(any("bracket" in text for text in plan["kept"]), plan["kept"])


# --------------------------------------------------------------------------------------------- F4
@unittest.skipUnless(SEASON_2026.is_dir(), f"simulated SOFTDRINK 2026 season absent: {SEASON_2026}")
class F4DepthImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = rr.load_save(SEASON_2026, detect=True)

    def test_unchanged_returners_get_no_new_lock_and_written_rows_equal_the_preview(self) -> None:
        document = self.document
        cooks = document.special_teams(0)["kr1"]
        self.assertEqual(cooks.record.values["unknown_52"] & 0x1C, 0)               # stored KR1 without a claim
        data = bytearray(df.export_depth_chart(document, 0))
        qbs = document.depth_order(0, 0)
        team = document.teams[0]
        for player, rank in ((qbs[0], 1), (qbs[1], 0)):                                 # swap QB1 and QB2 in the file
            data[4 * team.slots.index(player.offset) + 2] = rank
        plan = df.plan_depth_import(document, 0, bytes(data))
        self.assertEqual(plan.role_changes, [])
        before = {p.offset: p.record.values["unknown_52"] for p in document.team_players(0)}
        df.apply_depth_import(document, plan)
        listed = {row["offset"] for row in plan.rows}
        for player in document.team_players(0):
            if player.offset not in listed:
                self.assertEqual(player.record.values["unknown_52"], before[player.offset], player.display)

    def test_a_side_only_change_on_a_one_order_position_is_not_listed(self) -> None:
        document = self.document
        team = document.teams[0]
        safety = next(p for p in document.team_players(0) if p.record.values["position"] in (5, 6))
        data = bytearray(df.export_depth_chart(document, 0))
        data[4 * team.slots.index(safety.offset) + 3] = (safety.record.values["depth_side"] + 1) % 8
        plan = df.plan_depth_import(document, 0, bytes(data))
        self.assertEqual(plan.rows, [])
        self.assertEqual(plan.changes, 0)


# --------------------------------------------------------------------------------------------- F5, F6, F7
class LowFindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = _app()

    @unittest.skipUnless(ROSTER_SAVE.is_file(), f"SOFTDRINK roster save absent: {ROSTER_SAVE}")
    def test_f5_export_errors_become_a_status_line(self) -> None:
        panel = RosterEditorPanel()
        self.addCleanup(lambda: (panel.deleteLater(), self.application.processEvents()))
        self.assertTrue(panel.load_save(ROSTER_SAVE))
        panel.team_list.setCurrentRow(0)
        missing = Path(tempfile.gettempdir()) / "no-such-folder-b81-finn-r2" / "x"
        self.assertIsNone(panel.export_depth_chart(missing / f"SF{df.DEPTH_SUFFIX}"))
        self.assertIn("Not exported", panel.status_label.text())
        self.assertIsNone(panel.export_punt_returners(missing / f"all{df.PR_SUFFIX}"))
        self.assertIn("Not exported", panel.status_label.text())

    def test_f5_the_stats_csv_error_is_shown_on_the_page(self) -> None:
        page = TeamStatsPage()
        self.addCleanup(page.deleteLater)
        page.refresh(fs.FranchiseSave(synthetic_franchise()))
        self.assertIsNone(page.export_csv(Path(tempfile.gettempdir()) / "no-such-folder-b81-finn-r2" / "s.csv"))
        self.assertIn("Not exported", page.note_label.text())

    def test_f6_one_club_reads_club_s(self) -> None:
        save = fs.FranchiseSave(synthetic_franchise())
        plan = cf.ImportPlan()
        plan.changes.append(cf.CoachChange(0, "IND", 0, "Coach", "Wins", "wins", 1, 2))
        self.assertTrue(plan.summary().endswith("1 club's coach"), plan.summary())
        del save

    def test_f6_the_rosters_page_does_not_load_the_printing_module(self) -> None:
        code = ("import os, sys; os.environ['QT_QPA_PLATFORM']='offscreen'; sys.path.insert(0, %r); "
                "import mod_editor.gui.roster_editor_panel_qt; print('PyQt5.QtPrintSupport' in sys.modules)" % str(ROOT))
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300)
        self.assertEqual(out.stdout.strip().splitlines()[-1], "False", out.stderr[-2000:])

    def test_f7_the_record_column_says_it_counts_playoff_games_and_averages_are_marked(self) -> None:
        page = TeamStatsPage()
        self.addCleanup(page.deleteLater)
        headers = [page.table.horizontalHeaderItem(i) for i in range(page.table.columnCount())]
        self.assertIn("playoff", headers[1].toolTip())
        texts = [h.text() for h in headers]
        self.assertIn("AVG PASS (Studio)", texts)
        self.assertIn("AVG RUSH (Studio)", texts)
        self.assertIn("computed by the studio", headers[texts.index("AVG PASS (Studio)")].toolTip().lower())


if __name__ == "__main__":
    unittest.main()


# --------------------------------------------------------------------------------------------- F1, re-check: the screens
RETAIL_2501 = Path(os.environ.get(
    "NFL2K5_RETAIL_FRANCHISE_2501",
    "/media/noah/Storage/2K5-project/beta81/qb-system/evidence/phase1-scheduled-nov19/runs/retail/2501"))


def _select(panel: RosterEditorPanel, team: int, player: rr.Player) -> None:
    for row in range(panel.team_list.count()):
        if tuple(panel.team_list.item(row).data(Qt.UserRole) or ()) == ("team", team):
            panel.team_list.setCurrentRow(row)
            break
    panel.refresh_grid()
    assert panel.select_player(player), player.display


@unittest.skipUnless(SEASON_2026.is_dir(), f"simulated SOFTDRINK 2026 season absent: {SEASON_2026}")
class F1ScreenTests(unittest.TestCase):
    """Injury id 750 on a franchise save is an injury, not injured reserve, on the Rosters screen too (re-check F1)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = _app()

    def setUp(self) -> None:
        self.panel = RosterEditorPanel()
        self.addCleanup(lambda: (self.panel.deleteLater(), self.application.processEvents()))
        self.assertTrue(self.panel.load_save(SEASON_2026))
        document = self.panel.document
        self.edwards = next(p for p in document.players if p.display == "T.J. Edwards" and p.pool == "primary")
        self.assertEqual((self.edwards.record.values["injured_reserve"], self.edwards.record.values["unknown_29_low"]),
                         (0xEE, 2))
        _select(self.panel, 1, self.edwards)

    def test_release_swap_and_move_are_enabled(self) -> None:
        self.assertIs(self.panel.selected_player(), self.edwards)
        for button in (self.panel.release_button, self.panel.swap_button):
            self.assertTrue(button.isEnabled(), button.text())
        self.assertFalse(self.panel.document.is_on_injured_reserve(self.edwards))

    def test_place_on_ir_is_offered(self) -> None:
        self.assertEqual(self.panel.ir_place_reason(self.edwards), "")
        place = next(a for a in self.panel.grid_menu().actions() if a.text().startswith("Place on IR"))
        self.assertTrue(place.isEnabled())

    def test_the_grid_shows_the_injury_not_ir(self) -> None:
        self.assertFalse(self.panel._depth_text(self.edwards).endswith(" IR"))

    def test_show_my_changes_calls_his_heal_an_injury(self) -> None:
        self.assertEqual(self.panel.heal_players([self.edwards]), 1)
        self.panel.refresh_diff()
        text = self.panel.report.toPlainText()
        self.assertIn("Injury:", text)
        self.assertNotIn("Injured Reserve: 238", text)

    def test_a_listed_ir_player_still_reads_ir(self) -> None:
        document = self.panel.document
        listed = self.panel.listed_ir_indices()
        player = next(p for p in document.players if p.pool == "primary" and p.index in listed)
        self.assertTrue(document.is_on_injured_reserve(player))
        self.assertTrue(self.panel._depth_text(player).endswith(" IR"))
        self.assertIn("already on injured reserve", self.panel.ir_place_reason(player))


@unittest.skipUnless(RETAIL_2501.is_dir(), f"retail-size franchise 2501 absent: {RETAIL_2501}")
class F1LegacyIrTests(unittest.TestCase):
    """A 5-slot (legacy) IR save marks a placed player with 0xEE in the same byte injury id 750 ends in."""

    def test_the_older_save_says_why_it_cannot_place_him(self) -> None:
        application = _app()
        panel = RosterEditorPanel()
        self.addCleanup(lambda: (panel.deleteLater(), application.processEvents()))
        self.assertTrue(panel.load_save(RETAIL_2501))
        clements = next(p for p in panel.document.players if p.display == "Nate Clements" and p.pool == "primary")
        self.assertFalse(panel.document.is_on_injured_reserve(clements))
        self.assertFalse(panel._depth_text(clements).endswith(" IR"))
        self.assertIn("older", panel.ir_place_reason(clements))


# --------------------------------------------------------------------------------------------- follow-ups after bd08d4b8b
@unittest.skipUnless(SEASON_2026.is_dir(), f"simulated SOFTDRINK 2026 season absent: {SEASON_2026}")
class FollowUpTests(unittest.TestCase):
    """Copy/Paste Team and the practice-squad wording use the shared IR test (coordinator follow-up to F1)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.document = rr.load_save(SEASON_2026, detect=True)
        cls.edwards = next(p for p in cls.document.players if p.display == "T.J. Edwards" and p.pool == "primary")

    def test_chicago_copies_and_takes_a_paste_with_an_injury_750_player(self) -> None:
        from mod_editor.core import nfl2k5_team_transfer as tt
        chicago = tt.team_package(self.document, 1)
        entry = next(e for e in chicago["players"] if (e["first"], e["last"]) == ("T.J.", "Edwards"))
        self.assertFalse(entry["on_ir"])
        for team, package in ((0, chicago), (1, tt.team_package(self.document, 1))):
            refusals = tt.plan(self.document, team, package)["refusals"]
            self.assertFalse([r for r in refusals if "injured reserve" in r], refusals)

    def test_the_practice_squad_refusal_says_what_is_true(self) -> None:
        with self.assertRaises(rr.RosterRecordError) as caught:
            self.document.reserve_move_precheck(1, self.edwards.index, promote=False)
        words = str(caught.exception)
        self.assertNotIn("marked injured reserve", words)
        self.assertIn("practice squad screen", words)
        self.assertIn("heal him", words)


class LineEndingTests(unittest.TestCase):
    def test_the_team_package_is_written_with_lf_newlines(self) -> None:
        import ast
        tree = ast.parse((ROOT / "mod_editor/core/nfl2k5_team_transfer.py").read_text(encoding="utf-8"))
        writes = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "write_text"]
        self.assertTrue(writes)
        for call in writes:
            self.assertIn("newline", {k.arg for k in call.keywords}, call.lineno)

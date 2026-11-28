"""Finn's depth chart Export / Import (.2k5dc) and Backup / Restore Punt Returners (.NFL2k5PR) (b81 R43, row F13).

The formats come from Finn's program (lane receipt finn-r2/re/RE_FACTS.md section 5). Synthetic rosters everywhere;
the signed SOFTDRINK roster save when present (skipped, with the path, when not).
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor", ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.core import nfl2k5_depth_file as df  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.gui.roster_editor_panel_qt import RosterEditorPanel  # noqa: E402

SOFTDRINK_ROSTER_SAVE = Path(os.environ.get(
    "NFL2K5_SOFTDRINK_ROSTER_SAVE",
    "/media/noah/Storage/2K5-project/beta81/isolated-data/FC3-native-roster.zip"))


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _state(document: rr.RosterDocument, team_index: int) -> tuple:
    team = document.teams[team_index]
    rows = tuple((offset, document.by_offset[offset].record.values["depth_rank"],
                  document.by_offset[offset].record.values["depth_side"]) for offset in team.slots)
    return rows, tuple(document._specialists(team))


@unittest.skipUnless(SOFTDRINK_ROSTER_SAVE.is_file(), f"SOFTDRINK roster save absent: {SOFTDRINK_ROSTER_SAVE}")
class DepthFileCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = rr.load_save(SOFTDRINK_ROSTER_SAVE, detect=True)
        self.team = 0                                                # SF

    def test_finns_layout_four_bytes_a_player_then_the_six_role_bytes(self) -> None:
        data = df.export_depth_chart(self.document, self.team)
        team = self.document.teams[self.team]
        self.assertEqual(len(data), 4 * len(team.slots) + 6)
        first = self.document.by_offset[team.slots[0]].record.values
        self.assertEqual(tuple(data[:4]), (0, first["position"], first["depth_rank"], first["depth_side"]))
        self.assertEqual(list(data[-6:]), self.document._specialists(team))

    def test_reimporting_an_unchanged_file_changes_nothing(self) -> None:
        data = df.export_depth_chart(self.document, self.team)
        plan = df.plan_depth_import(self.document, self.team, data)
        self.assertEqual((plan.changes, plan.problems), (0, []))

    def test_a_chart_exported_before_a_move_puts_the_move_back(self) -> None:
        saved = df.export_depth_chart(self.document, self.team)
        before = _state(self.document, self.team)
        body = self.document.to_body()
        qbs = self.document.depth_order(self.team, 0)
        self.document.place_in_depth(qbs[1], 0)                      # QB2 to QB1, as the Rosters arrow does
        returners = self.document.special_teams(self.team)
        self.assertNotEqual(_state(self.document, self.team), before)
        plan = df.plan_depth_import(self.document, self.team, saved)
        self.assertEqual({row["player"].display for row in plan.rows}, {qbs[0].display, qbs[1].display})
        df.apply_depth_import(self.document, plan)
        self.assertEqual(_state(self.document, self.team), before)
        self.assertEqual(self.document.depth_order(self.team, 0)[0], qbs[0])
        self.assertEqual(self.document.special_teams(self.team)["pr"], returners["pr"])
        self.document.check_depth_locks()
        # the depth rows and the moved players' lock bits are the only record changes
        changed = [i for i, (a, b) in enumerate(zip(body, self.document.to_body())) if a != b]
        allowed = {q.offset + off for q in qbs[:2] for off in (0x29, 0x52)}
        self.assertTrue(set(changed) <= allowed, [hex(i) for i in changed])

    def test_a_returner_from_the_file_takes_the_lock_claim_with_him(self) -> None:
        team = self.document.teams[self.team]
        st = self.document.special_teams(self.team)
        candidates = [p for p in self.document.team_players(self.team)
                      if p.record.values["position"] in rr.RosterDocument.RETURNER_CODES and p is not st["pr"]]
        data = bytearray(df.export_depth_chart(self.document, self.team))
        new_pr = candidates[0]
        data[-1] = team.slots.index(new_pr.offset)
        plan = df.plan_depth_import(self.document, self.team, bytes(data))
        self.assertEqual(plan.rows, [])
        self.assertEqual(plan.role_changes, [f"PR: {new_pr.display}"])
        df.apply_depth_import(self.document, plan)
        self.assertIs(self.document.special_teams(self.team)["pr"], new_pr)
        self.assertTrue(new_pr.record.depth_locks["pr"])               # the claim the SOFTDRINK weekly pass follows
        if st["pr"] is not None:
            self.assertFalse(st["pr"].record.depth_locks["pr"])
        self.document.check_depth_locks()

    def test_a_lineman_as_returner_or_a_place_past_the_list_is_refused_and_nothing_changes(self) -> None:
        team = self.document.teams[self.team]
        body = self.document.to_body()
        lineman = next(p for p in self.document.team_players(self.team)
                       if p.record.values["position"] not in rr.RosterDocument.RETURNER_CODES)
        data = bytearray(df.export_depth_chart(self.document, self.team))
        data[-1] = team.slots.index(lineman.offset)
        plan = df.plan_depth_import(self.document, self.team, bytes(data))
        self.assertTrue(plan.problems and "returners are" in plan.problems[0], plan.problems)
        with self.assertRaises(rr.RosterRecordError):
            df.apply_depth_import(self.document, plan)
        data[-1] = len(team.slots) + 3
        self.assertIn("points at place", df.plan_depth_import(self.document, self.team, bytes(data)).problems[0])
        self.assertEqual(self.document.to_body(), body)

    def test_a_position_that_no_longer_matches_is_left_alone(self) -> None:
        data = bytearray(df.export_depth_chart(self.document, self.team))
        data[1] = (data[1] + 1) % 20                                  # the file says another position at place 1
        data[2] = 6
        plan = df.plan_depth_import(self.document, self.team, bytes(data))
        self.assertTrue(any("(place 1)" in text for text in plan.skipped), plan.skipped)
        self.assertEqual(plan.rows, [])

    def test_not_a_finn_file_is_refused(self) -> None:
        with self.assertRaisesRegex(rr.RosterRecordError, "not a Finn depth chart file"):
            df.plan_depth_import(self.document, self.team, b"\x00\x01\x02")
        bad = bytearray(df.export_depth_chart(self.document, self.team))
        bad[4] = 9
        with self.assertRaisesRegex(rr.RosterRecordError, "numbered"):
            df.plan_depth_import(self.document, self.team, bytes(bad))

    def test_punt_returners_round_trip_by_finns_rule(self) -> None:
        text = df.export_punt_returners(self.document)
        lines = text.split("\r\n")
        self.assertEqual(len([line for line in lines if line]), 32)
        self.assertTrue(lines[0].startswith("0="))
        self.assertEqual(df.plan_punt_returner_restore(self.document, text)["restore"], [])
        st = self.document.special_teams(self.team)
        other = next(p for p in self.document.team_players(self.team)
                     if p.record.values["position"] in df.FINN_PR_CODES and p is not st["pr"])
        self.document.set_special_role(self.team, "pr", other)
        plan = df.plan_punt_returner_restore(self.document, text)
        self.assertEqual(len(plan["restore"]), 1)
        df.apply_punt_returner_restore(self.document, plan)
        self.assertIs(self.document.special_teams(self.team)["pr"], st["pr"])
        self.document.check_depth_locks()
        lineman = next(p for p in self.document.team_players(self.team) if p.record.values["position"] in (10, 11))
        bad = text.replace(f"0={st['bytes']['pr']}", f"0={self.document.teams[0].slots.index(lineman.offset)}", 1)
        refused = df.plan_punt_returner_restore(self.document, bad)
        self.assertEqual(refused["restore"], [])
        self.assertTrue(refused["refused"] and lineman.display in refused["refused"][0])


@unittest.skipUnless(SOFTDRINK_ROSTER_SAVE.is_file(), f"SOFTDRINK roster save absent: {SOFTDRINK_ROSTER_SAVE}")
class DepthFileScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = _app()

    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.panel = RosterEditorPanel()
        self.assertTrue(self.panel.load_save(SOFTDRINK_ROSTER_SAVE))
        self.panel.team_list.setCurrentRow(0)
        self.assertEqual(self.panel._selected_club(), 0)

    def tearDown(self) -> None:
        self.panel.deleteLater()
        self.application.processEvents()
        self.folder.cleanup()

    def test_the_club_menu_offers_the_four_finn_files(self) -> None:
        texts = [action.text() for action in self.panel.club_menu().actions()]
        for words in ("Export depth chart", "Import depth chart", "Back up punt returners", "Restore punt returners"):
            self.assertTrue(any(text.startswith(words) for text in texts), (words, texts))

    def test_export_move_import_undo_redo_and_a_signed_copy(self) -> None:
        panel, document = self.panel, self.panel.document
        saved = panel.export_depth_chart(self.root / f"SF{df.DEPTH_SUFFIX}")
        before = _state(document, 0)
        qbs = document.depth_order(0, 0)
        document.place_in_depth(qbs[1], 0)
        moved = _state(document, 0)
        self.assertTrue(panel.import_depth_chart(saved, confirm=False), panel.status_label.text())
        self.assertEqual(_state(document, 0), before)
        panel.undo()
        self.assertEqual(_state(document, 0), moved)
        panel.redo()
        self.assertEqual(_state(document, 0), before)
        receipt = panel.write_copy_to(self.root / "copy.zip")
        self.assertTrue(receipt["signed"])
        back = rr.load_save(self.root / "copy.zip")
        self.assertEqual(back.depth_order(0, 0)[0].display, qbs[0].display)

    def test_punt_returner_backup_and_restore_through_the_page(self) -> None:
        panel, document = self.panel, self.panel.document
        saved = panel.export_punt_returners(self.root / f"all{df.PR_SUFFIX}")
        st = document.special_teams(0)
        other = next(p for p in document.team_players(0)
                     if p.record.values["position"] in df.FINN_PR_CODES and p is not st["pr"])
        document.set_special_role(0, "pr", other)
        self.assertTrue(panel.restore_punt_returners(saved, confirm=False), panel.status_label.text())
        self.assertIs(document.special_teams(0)["pr"], st["pr"])
        panel.undo()
        self.assertIs(document.special_teams(0)["pr"], other)


if __name__ == "__main__":
    unittest.main()


SEASON_2026 = Path(os.environ.get(
    "NFL2K5_SOFTDRINK_SEASON_SAVE",
    "/media/noah/Storage/2K5-project/beta81/cpu-sim/catalog-disc-128-dynasty-signed/2026"))


class ClearRookieStatsTests(unittest.TestCase):
    """Finn's Tools > Auto-update > Clear Rookie Stats (row J6): his selection, the Studio's safe clear, and no pool
    words spent on a rookie who has no career history yet."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = _app()

    def _panel(self, path: Path) -> RosterEditorPanel:
        panel = RosterEditorPanel()
        self.addCleanup(panel.deleteLater)
        self.assertTrue(panel.load_save(path))
        return panel

    @unittest.skipUnless(SOFTDRINK_ROSTER_SAVE.is_file(), f"SOFTDRINK roster save absent: {SOFTDRINK_ROSTER_SAVE}")
    def test_a_roster_whose_rookies_have_no_history_changes_nothing(self) -> None:
        panel = self._panel(SOFTDRINK_ROSTER_SAVE)
        rookies = panel.rookie_players()
        self.assertTrue(rookies)
        for player in rookies:
            values = player.record.values
            self.assertLess(values["years_pro"] | values["unknown_25_high"] << 5, 2)
            self.assertIsNotNone(panel.document.club_of(player))
        before = panel.document.to_body()
        done, message = panel.clear_rookie_stats(confirm=False)
        self.assertFalse(done)
        self.assertIn("none with a career history", message)
        self.assertEqual(panel.document.to_body(), before)

    @unittest.skipUnless(SEASON_2026.is_dir(), f"simulated SOFTDRINK 2026 season save absent: {SEASON_2026}")
    def test_a_played_season_clears_the_rookies_with_stats_in_one_undo(self) -> None:
        panel = self._panel(SEASON_2026)
        document = panel.document
        rookies = panel.rookie_players()
        with_history = [p for p in rookies if p.record.values["history_pointer"]]
        self.assertTrue(with_history and len(with_history) < len(rookies))
        veteran = next(p for p in document.team_players(0) if p.record.values["years_pro"] >= 2)
        self.assertNotIn(veteran, rookies)
        before = document.to_body()
        links = {p.offset: p.record.values["history_pointer"] for p in rookies}
        done, message = panel.clear_rookie_stats(confirm=False)
        self.assertTrue(done, message)
        self.assertIn(f"{len(with_history)} players", message)
        for player in rookies:
            if not links[player.offset]:
                self.assertEqual(player.record.values["history_pointer"], 0)
            else:
                self.assertTrue(document.history_is_clear(player))
        panel.undo()
        self.assertEqual(document.to_body(), before)

"""Finn's coach file (Export / Import Coaches, parity row G5) and Clear Cap Penalty (row F9) on the Franchise page (b81 R2).

Core tests run on a synthetic franchise save with three real-shaped coach records (all five text fields, so the Studio's
coach-text writer works on it) and on the lane's synthetic roster save.  The signed SOFTDRINK saves are used when present
(skipped, with the path, when not): the expanded roster save in coaches-only mode and the simulated 2026 franchise.  Those
saves have zero dead cap everywhere (CPU-only sims never accrue it), so the dead-cap tests plant their own values.
The native check of the game's own cap getter 0x13ECA0 was not run in this lane (see REVIEW_ME.md).
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

from PyQt5.QtWidgets import QApplication, QDialogButtonBox  # noqa: E402

from mod_editor.core import nfl2k5_coach_file as cf  # noqa: E402
from mod_editor.core import nfl2k5_franchise_save as fs  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_team_stats as ts  # noqa: E402
from mod_editor.gui.franchise_panel_qt import FranchiseEdit  # noqa: E402
from mod_editor.gui.roster_editor_panel_qt import RosterEditorPanel  # noqa: E402
from test_franchise_panel_qt import COACH_AT, COACH_STRINGS_AT, _rel  # noqa: E402
from test_nfl2k5_franchise_save import synthetic_franchise  # noqa: E402
from test_roster_editor_panel_franchise import write_container  # noqa: E402

SOFTDRINK_ROSTER_SAVE = Path(os.environ.get(
    "NFL2K5_SOFTDRINK_ROSTER_SAVE", "/media/noah/Storage/2K5-project/beta81/isolated-data/FC3-native-roster.zip"))
SEASON_2026 = Path(os.environ.get(
    "NFL2K5_SOFTDRINK_SEASON_SAVE",
    "/media/noah/Storage/2K5-project/beta81/cpu-sim/catalog-disc-128-dynasty-signed/2026"))


TEXT_AT = COACH_AT + 0x400                   # after the coach records (0xA8 each)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _changed(a: bytes, b: bytes) -> list[int]:
    return [i for i, (x, y) in enumerate(zip(a, b)) if x != y]


def graft_coaches(data: bytearray, team_offsets: list[int], *, records: int | None = None) -> bytearray:
    """Coach records at COACH_AT (0xA8 each), one a club in ``team_offsets`` order, every one of the five text fields
    pointing at its own string (empty ones too), the strings laid end to end the way the game's are."""

    count = records or len(team_offsets)
    cursor = TEXT_AT
    names = [("Bill", "Belichick"), ("Andy", "Reid"), ("Sean", "McVay"), ("Mike", "Vrabel")]
    for k in range(count):
        base = COACH_AT + k * fs.COACH_SIZE
        first, last = names[k]
        for rel, text in ((0, first), (4, last), (8, f"Info {k} a"), (0xC, f"Info {k} b"), (0x10, "")):
            raw = text.encode("utf-16-le") + b"\0\0"
            data[cursor:cursor + len(raw)] = raw
            _rel(data, base + rel, cursor)
            cursor += len(raw)
        struct.pack_into("<H", data, base + fs.COACH_FIELDS["body"][0], 7 + k)
        for j, name in enumerate(("seasons_with_team", "total_seasons", "wins", "losses", "ties", "winning_seasons",
                                  "super_bowls", "playoff_wins", "playoff_losses", "super_bowl_wins",
                                  "super_bowl_losses", "photo")):
            rel, fmt = fs.COACH_FIELDS[name]
            struct.pack_into(fmt, data, base + rel, 10 * k + j + 1)
        for j in range(len(fs.COACH_RATINGS)):
            data[base + fs.COACH_RATINGS_OFFSET + j] = 50 + 10 * k + j
        for j in range(fs.COACH_TENDENCY_COUNT):
            data[base + fs.COACH_TENDENCIES_OFFSET + j] = 10 * (j % 5 + 1) if j < 5 else 10 * (5 - j % 5)
    struct.pack_into("<I", data, fs.ARENA_ROOT + 0x30, count)
    _rel(data, fs.ARENA_ROOT + 0x34, COACH_AT)
    for team, offset in enumerate(team_offsets):
        _rel(data, offset + rr.TEAM_COACH, COACH_AT + min(team, count - 1) * fs.COACH_SIZE)
    return data


def synthetic_coaches(*, shared: bool = False) -> bytes:
    """The synthetic franchise (three clubs 'Team0'..'Team2') with a coach each; ``shared`` has club 2 lead club 1's coach."""

    data = bytearray(synthetic_franchise(year_field=7, user_team=0))
    save = fs.FranchiseSave(bytes(data))
    offsets = [save.team_offset(t) for t in range(3)]
    graft_coaches(data, offsets, records=2 if shared else 3)
    return bytes(data)


def finn_text(save: fs.FranchiseSave) -> str:
    return cf.export_coaches(save)


def edit_text(text: str, **sections: dict[str, str]) -> str:
    """Change ``key=value`` lines of the named sections in a Finn file (keys are Finn's)."""

    out, current = [], ""
    for line in text.split("\r\n"):
        if line.startswith("["):
            current = line[1:-1]
        elif "=" in line and current in sections and line.split("=")[0] in sections[current]:
            line = f"{line.split('=')[0]}={sections[current][line.split('=')[0]]}"
        out.append(line)
    return "\r\n".join(out)


def written_savegame(copy: Path) -> bytes:
    return next(copy.rglob("SAVEGAME.DAT")).read_bytes()


# --------------------------------------------------------------------------------------------- the file, core
class ExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = synthetic_coaches()
        self.save = fs.FranchiseSave(self.payload)
        self.text = cf.export_coaches(self.save)

    def test_the_key_map_is_finns_in_finns_order_and_agrees_with_the_studio_map(self) -> None:
        names = [k.key for k in cf.KEYS]
        self.assertEqual(names[:15], ["First", "Last", "Body", "Photo", "Wins", "Losses", "Ties", "SeasonsWithTeam",
                                      "TotalSeasons", "WinningSeasons", "SuperBowlAppearances", "PlayOffWins",
                                      "PlayOffLosses", "SuperBowlWins", "SuperBowlLosses"])
        self.assertEqual(names[15], "OverallRating")
        self.assertEqual(names[38:], ["RushingShotgun", "RushingSplitBacks", "RushingIForm", "RushingLoneBack",
                                      "RushingEmpty", "PassingShotgun", "PassingSplitBacks", "PassingIForm",
                                      "PassingLoneBack", "PassingEmpty"])
        self.assertEqual(len(names), 48)
        for key in cf.KEYS:                       # each offset is where the Studio keeps the same field
            if key.kind == "text":
                continue
            if key.field in fs.COACH_FIELDS:
                self.assertEqual(key.offset, fs.COACH_FIELDS[key.field][0], key.key)
            elif key.field in fs.COACH_RATINGS:
                self.assertEqual(key.offset, fs.COACH_RATINGS_OFFSET + fs.COACH_RATINGS.index(key.field), key.key)
            else:
                self.assertEqual(key.offset, fs.COACH_TENDENCIES_OFFSET + fs.COACH_TENDENCIES.index(key.field), key.key)

    def test_crlf_sections_by_nickname_and_the_values_of_each_clubs_coach(self) -> None:
        self.assertTrue(self.text.endswith("\r\n"))
        self.assertNotIn("\n", self.text.replace("\r\n", ""))
        lines = self.text.split("\r\n")
        self.assertEqual([line for line in lines if line.startswith("[")], ["[Team0]", "[Team1]", "[Team2]"])
        self.assertEqual(lines[1:4], ["First=Bill", "Last=Belichick", "Body=7"])
        self.assertEqual(self.text.count("PassingEmpty="), 3)
        coaches = {c.index: c for c in self.save.coaches()}
        sections = cf.parse_ini(self.text)
        for team in range(3):
            coach, body = coaches[team], sections[f"team{team}"]
            self.assertEqual(body["first"], coach.first)
            self.assertEqual(int(body["body"]), coach.fields["body"] & 0xFF)
            self.assertEqual(int(body["photo"]), coach.fields["photo"])
            self.assertEqual(int(body["superbowlappearances"]), coach.fields["super_bowls"])
            self.assertEqual(int(body["strating"]), coach.ratings["special_teams"])
            self.assertEqual(int(body["leadership"]), coach.ratings["leadership"])
            self.assertEqual(int(body["rushingloneback"]), coach.tendencies["run_one_back"])
            self.assertEqual(int(body["passingempty"]), coach.tendencies["pass_no_back"])

    def test_an_unchanged_export_changes_nothing(self) -> None:
        plan = cf.plan_import(self.save, self.text)
        self.assertTrue(plan.ok)
        self.assertEqual((plan.changes, plan.skipped, plan.sections, plan.matched), ([], [], 3, 3))
        receipt = cf.import_coaches(self.save, self.text)
        self.assertEqual(receipt["changes_written"], 0)
        self.assertEqual(self.save.to_bytes(), self.payload)

    def test_the_ansi_file_round_trips_and_a_utf8_one_reads_too(self) -> None:
        raw = cf.encode_file(self.text)
        self.assertEqual(cf.decode_file(raw), self.text)
        self.assertEqual(cf.decode_file(b"\xef\xbb\xbf" + raw), self.text)
        self.assertEqual(cf.decode_file("[Team0]\r\nFirst=Jos\xe9\r\n".encode("cp1252")), "[Team0]\r\nFirst=Jos\xe9\r\n")


class ImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = synthetic_coaches()
        self.save = fs.FranchiseSave(self.payload)
        self.text = cf.export_coaches(self.save)

    def record(self, index: int) -> range:
        offset = self.save._coach_offset(index)
        return range(offset, offset + fs.COACH_SIZE)

    def test_edited_numbers_change_exactly_those_bytes_of_those_coach_records(self) -> None:
        text = edit_text(self.text, Team0={"Wins": "100", "OverallRating": "91", "Body": "20", "RushingEmpty": "55"},
                         Team2={"Photo": "7777", "Respect": "3"})
        plan = cf.plan_import(self.save, text)
        self.assertEqual([(c.club, c.key, c.new) for c in plan.changes],
                         [("Team0", "Body", 20), ("Team0", "Wins", 100), ("Team0", "OverallRating", 91),
                          ("Team0", "RushingEmpty", 55), ("Team2", "Photo", 7777), ("Team2", "Respect", 3)])
        self.assertEqual({c.club for c in plan.changes}, {"Team0", "Team2"})
        receipt = cf.apply_import(self.save, plan)
        self.assertEqual((receipt["numbers"], receipt["names_skipped"]), (6, []))
        after = self.save.to_bytes()
        wanted = {self.save._coach_offset(0) + fs.COACH_FIELDS["body"][0], self.save._coach_offset(0) + 0x20,
                  self.save._coach_offset(0) + 0x20 + 1, self.save._coach_offset(0) + fs.COACH_RATINGS_OFFSET,
                  self.save._coach_offset(0) + fs.COACH_TENDENCIES_OFFSET + 4,
                  self.save._coach_offset(2) + 0x40, self.save._coach_offset(2) + 0x41,
                  self.save._coach_offset(2) + fs.COACH_RATINGS_OFFSET + 22}
        self.assertTrue(set(_changed(self.payload, after)) <= wanted, set(_changed(self.payload, after)) - wanted)
        coaches = {c.index: c for c in self.save.coaches()}
        self.assertEqual((coaches[0].fields["wins"], coaches[0].fields["body"], coaches[0].ratings["overall"],
                          coaches[0].tendencies["run_no_back"]), (100, 20, 91, 55))
        self.assertEqual((coaches[2].fields["photo"], coaches[2].ratings["respect"]), (7777, 3))
        self.assertEqual(coaches[1].fields, fs.FranchiseSave(self.payload).coaches()[1].fields)   # Team1 untouched
        # the same file again is now a no-op
        self.assertEqual(cf.plan_import(self.save, text).changes, [])

    def test_body_keeps_the_high_byte_of_the_word(self) -> None:
        data = bytearray(self.payload)
        data[self.save._coach_offset(0) + 0x19] = 0x03            # the word is 0x0307; Finn's Body is the low byte
        save = fs.FranchiseSave(bytes(data))
        cf.import_coaches(save, edit_text(self.text, Team0={"Body": "9"}))
        self.assertEqual(struct.unpack_from("<H", save.buffer, save._coach_offset(0) + 0x18)[0], 0x0309)

    def test_missing_keys_missing_sections_and_unknown_ones_leave_everything_alone(self) -> None:
        finn_shaped = "[Team1]\r\nwins=99\r\nNotAKey=5\r\n\r\n[Nobody]\r\nWins=1\r\n; a comment\r\n"
        plan = cf.plan_import(self.save, finn_shaped)
        self.assertEqual([(c.club, c.key, c.new) for c in plan.changes], [("Team1", "Wins", 99)])
        self.assertEqual(plan.matched, 1)
        self.assertEqual(plan.skipped, ["[Nobody] names no club in this save"])
        cf.apply_import(self.save, plan)
        self.assertEqual(set(_changed(self.payload, self.save.to_bytes())) - set(self.record(1)), set())
        self.assertEqual(self.save.coaches()[1].fields["wins"], 99)
        self.assertEqual(self.save.coaches()[1].fields["losses"], 14)

    def test_an_lf_only_file_with_odd_case_and_spacing_reads_like_windows(self) -> None:
        plan = cf.plan_import(self.save, "  [TEAM0]  \nOVERALLRATING = 77 \nPhoto=\"500\"\n")
        self.assertEqual([(c.key, c.new) for c in plan.changes], [("Photo", 500), ("OverallRating", 77)])

    def test_out_of_range_and_non_numbers_are_refused_with_the_key_and_the_section_and_nothing_is_written(self) -> None:
        for key, value in (("OverallRating", "100"), ("Wins", "-1"), ("Photo", "65536"), ("Body", "256"),
                           ("RushingGun", "1"), ("PassingEmpty", "101"), ("Wins", "many"), ("Losses", "")):
            if key == "RushingGun":
                continue                                           # not one of Finn's keys: ignored, not refused
            text = edit_text(self.text, Team0={"Ties": "4"}, Team1={key: value})
            plan = cf.plan_import(self.save, text)
            self.assertFalse(plan.ok, (key, value))
            self.assertIn(f"[Team1] {key}", plan.refusals[0])
            with self.assertRaises(fs.FranchiseSaveError):
                cf.apply_import(self.save, plan)
            self.assertEqual(self.save.to_bytes(), self.payload, "the valid Team0 line was not written either")

    def test_the_head_coach_pairs_with_the_club_after_a_swap_not_the_list_position(self) -> None:
        self.save.swap_head_coaches(0, 1)
        swapped = self.save.to_bytes()
        text = cf.export_coaches(self.save)
        self.assertTrue(text.startswith("[Team0]\r\nFirst=Andy\r\nLast=Reid\r\n"))      # Team0 now has coach 1
        plan = cf.plan_import(self.save, edit_text(text, Team0={"Wins": "88"}, Team1={"Wins": "77"}))
        self.assertEqual({(c.team, c.coach) for c in plan.changes}, {(0, 1), (1, 0)})
        cf.apply_import(self.save, plan)
        coaches = {c.index: c for c in self.save.coaches()}
        self.assertEqual((coaches[1].fields["wins"], coaches[0].fields["wins"]), (88, 77))
        self.assertEqual(set(_changed(swapped, self.save.to_bytes())) - set(self.record(0)) - set(self.record(1)), set())

    def test_names_go_through_the_coach_text_writer_in_place_and_when_they_grow(self) -> None:
        self.assertEqual(self.save.coach_text_problem(), "")
        same_room = edit_text(self.text, Team1={"First": "Andr", "Last": "Reid"})
        cf.import_coaches(self.save, same_room)
        self.assertEqual(self.save.coaches()[1].name, "Andr Reid")
        grow = edit_text(cf.export_coaches(self.save), Team0={"First": "Billy Bob", "Last": "Belichick the Elder"}, Team2={"Last": "Mc"})
        receipt = cf.import_coaches(self.save, grow)
        self.assertEqual((receipt["names"], receipt["names_skipped"]), (3, []))
        coaches = {c.index: c for c in self.save.coaches()}
        self.assertEqual((coaches[0].name, coaches[2].name), ("Billy Bob Belichick the Elder", "Sean Mc"))
        self.assertEqual(coaches[0].info, ("Info 0 a", "Info 0 b", ""), "the biography lines are left as they were")
        self.assertEqual(coaches[1].name, "Andr Reid")
        self.assertEqual(self.save.coach_text_problem(), "")
        # every club still leads the coach it led, and no number moved
        self.assertEqual(self.save.head_coaches(), {0: 0, 1: 1, 2: 2})
        self.assertEqual({c.index: c.fields for c in self.save.coaches()},
                         {c.index: c.fields for c in fs.FranchiseSave(self.payload).coaches()})

    def test_text_the_game_cannot_show_is_refused_like_a_bad_number(self) -> None:
        for value in ("", "x" * 25, "José"):
            plan = cf.plan_import(self.save, edit_text(self.text, Team0={"Wins": "9"}).replace("First=Bill", f"First={value}"))
            self.assertFalse(plan.ok, value)
            self.assertIn("[Team0] First", plan.refusals[0])

    def test_a_save_whose_names_cannot_be_rewritten_still_takes_the_numbers_and_lists_the_names(self) -> None:
        data = bytearray(self.payload)
        struct.pack_into("<i", data, COACH_AT + 0x10, 0)           # coach 0 has no fifth text
        save = fs.FranchiseSave(bytes(data))
        self.assertIn("no readable text", save.coach_text_problem())
        text = edit_text(cf.export_coaches(save), Team0={"Wins": "50", "First": "Billy"})
        plan = cf.plan_import(save, text)
        self.assertEqual((len(plan.number_changes), len(plan.name_changes)), (1, 1))
        self.assertIn("no readable text", plan.name_problem)
        receipt = cf.apply_import(save, plan)
        self.assertEqual(save.coaches()[0].fields["wins"], 50)
        self.assertEqual(save.coaches()[0].first, "Bill")
        self.assertEqual((receipt["numbers"], receipt["names"]), (1, 0))
        self.assertEqual(len(receipt["names_skipped"]), 1)
        self.assertIn("Team0: First Bill -> Billy", receipt["names_skipped"][0])

    def test_a_name_that_does_not_fit_the_game_region_is_skipped_and_the_numbers_stay(self) -> None:
        data = bytearray(self.payload)
        save = fs.FranchiseSave(bytes(data))
        layout = save._coach_text_layout()
        # fill the writable room with a long first name for every coach, 24 characters each, plus the 52-character info lines
        long = "A" * 24
        changed = edit_text(self.text, Team0={"First": long, "Last": long}, Team1={"First": long, "Last": long, "Wins": "5"},
                            Team2={"First": long, "Last": long})
        # make the writer's room tiny by putting a nonzero byte right after the strings
        data[layout["strings_end"] + 2] = 1
        tight = fs.FranchiseSave(bytes(data))
        plan = cf.plan_import(tight, changed)
        receipt = cf.apply_import(tight, plan)
        self.assertEqual(tight.coaches()[1].fields["wins"], 5)
        self.assertEqual(len(receipt["names_skipped"]), 6)
        self.assertEqual(tight.coaches()[0].name, "Bill Belichick")

    def test_a_coach_record_two_clubs_lead_is_never_changed_through_one_club(self) -> None:
        shared = fs.FranchiseSave(synthetic_coaches(shared=True))
        self.assertEqual(shared.head_coach_index(1), shared.head_coach_index(2))
        text = cf.export_coaches(shared)
        plan = cf.plan_import(shared, edit_text(text, Team0={"Wins": "9"}, Team1={"Wins": "9"}, Team2={"Losses": "9"}))
        self.assertEqual([(c.club, c.key) for c in plan.changes], [("Team0", "Wins")])
        self.assertEqual(len(plan.skipped), 2)
        self.assertIn("also leads", plan.skipped[0])
        self.assertIn("SF", plan.skipped[0])           # Team2 is SF in the synthetic save
        cf.apply_import(shared, plan)
        self.assertEqual(shared.coaches()[1].fields["wins"], 13)       # unchanged

    def test_clubs_with_the_same_nickname_get_their_abbreviation_and_a_bare_nickname_is_listed_not_guessed(self) -> None:
        data = bytearray(self.payload)
        save = fs.FranchiseSave(bytes(data))
        nick1 = save.rel(save.team_offset(1) + rr.TEAM_NICKNAME)
        nick0 = save.rel(save.team_offset(0) + rr.TEAM_NICKNAME)
        struct.pack_into("<i", data, save.team_offset(1) + rr.TEAM_NICKNAME, nick0 - (save.team_offset(1) + rr.TEAM_NICKNAME) + 1)
        same = fs.FranchiseSave(bytes(data))
        self.assertNotEqual(nick1, nick0)
        text = cf.export_coaches(same)
        self.assertIn("[Team0 (IND)]", text)
        self.assertIn("[Team0 (ATL)]", text)
        plan = cf.plan_import(same, edit_text(text, **{"Team0 (ATL)": {"Wins": "42"}}) + "[Team0]\r\nWins=1\r\n")
        self.assertEqual([(c.team, c.new) for c in plan.changes], [(1, 42)])
        self.assertIn("more than one club", plan.skipped[0])


# --------------------------------------------------------------------------------------------- the page, synthetic
class _PanelCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = _app()

    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.panel = RosterEditorPanel()

    def tearDown(self) -> None:
        self.panel.deleteLater()
        self.application.processEvents()
        self.folder.cleanup()

    @property
    def page(self):
        return self.panel.franchise_panel

    def load(self, payload: bytes, name: str = "fr") -> bytes:
        self.assertTrue(self.panel.load_save(write_container(self.root / name, payload)))
        self.application.processEvents()
        return payload


class CoachPageTests(_PanelCase):
    def setUp(self) -> None:
        super().setUp()
        self.payload = self.load(synthetic_coaches())

    def test_the_coaches_tab_has_both_buttons_and_export_writes_a_dot_coaches_file(self) -> None:
        page = self.page
        self.assertEqual(page.coach_export_button.text(), "Export coaches…")
        self.assertEqual(page.coach_import_button.text(), "Import coaches…")
        self.assertTrue(page.coach_export_button.isEnabled())
        target = page.export_coaches_to(self.root / "mine")
        self.assertEqual(target.name, "mine.Coaches")
        raw = target.read_bytes()
        self.assertEqual(raw, cf.encode_file(cf.export_coaches(fs.FranchiseSave(self.payload))))
        self.assertEqual(page.export_coaches_to(self.root / "other.2k5Coaches").name, "other.2k5Coaches")
        # a page with no save has nothing to export
        page.clear()
        self.assertEqual(page.export_coaches_text(), "")

    def test_import_shows_a_preview_then_applies_as_one_undoable_edit_that_reaches_the_signed_copy(self) -> None:
        page = self.page
        text = edit_text(cf.decode_file((page.export_coaches_to(self.root / "a")).read_bytes()),
                         Team0={"Wins": "100", "Photo": "123"}, Team1={"OverallRating": "95", "First": "Andrew"},
                         Team2={"Respect": "11"})
        dialog = page.coach_import_dialog(text, "a.Coaches")
        rows = dialog.rows()
        self.assertEqual(rows[0][:3], ["Team0", "Bill Belichick", "Photo id (Photo)"])
        self.assertEqual(rows[0][4], "123")
        self.assertEqual(len(rows), 5)
        self.assertIn(["Team1", "Andy Reid", "First name (First)", "Andy", "Andrew"], rows)
        self.assertIn(["Team1", "Andy Reid", "Overall (OverallRating)", "60", "95"], rows)
        ok = dialog.buttons.button(QDialogButtonBox.Ok)
        self.assertTrue(ok.isEnabled())
        self.assertIn("5 changes to 3 clubs", dialog.summary_label.text())
        depth = len(page.edits)
        self.assertTrue(page.import_coaches(text))
        self.assertEqual(len(page.edits), depth + 1, "one journaled edit for the whole file")
        self.assertEqual(page.edits[-1].kind, "coaches_import")
        self.assertIn("5 changes", page.edits[-1].label)
        coaches = {c.index: c for c in page.save.coaches()}
        self.assertEqual((coaches[0].fields["wins"], coaches[0].fields["photo"], coaches[1].first), (100, 123, "Andrew"))
        # the page's own list shows the new name
        self.assertTrue(any("Andrew Reid" in page.coach_list.item(i).text() for i in range(page.coach_list.count())))
        self.panel.undo()
        self.assertEqual(page.save.to_bytes(), self.payload)
        self.panel.redo()
        self.assertEqual({c.index: c.fields["wins"] for c in page.save.coaches()}[0], 100)
        receipt = self.panel.write_copy_to(self.root / "copy")
        self.assertTrue(receipt["signed"])
        container = rr.SaveContainer.load(self.root / "copy")
        self.assertTrue(container.verified)
        back = fs.FranchiseSave(container.savegame)
        self.assertEqual((back.coaches()[1].name, back.coaches()[0].fields["photo"], back.coaches()[2].ratings["respect"]),
                         ("Andrew Reid", 123, 11))
        reread = fs.FranchiseSave(self.payload)
        changed = set(_changed(self.payload, container.savegame))
        coach_bytes = {c.offset + k for c in reread.coaches() for k in range(fs.COACH_SIZE)}
        layout = reread._coach_text_layout()
        text_bytes = set(range(layout["start"], layout["writable_end"]))
        self.assertTrue(changed <= coach_bytes | text_bytes, "only coach records and the coach text region moved")
        self.assertTrue(changed & coach_bytes and changed & text_bytes)

    def test_a_refused_file_says_why_in_the_dialog_and_the_status_and_writes_nothing(self) -> None:
        page = self.page
        text = edit_text(cf.export_coaches(page.save), Team1={"OverallRating": "150"})
        dialog = page.coach_import_dialog(text)
        self.assertFalse(dialog.buttons.button(QDialogButtonBox.Ok).isEnabled())
        self.assertIn("[Team1] OverallRating=150 is outside 0..99", dialog.notes.toPlainText())
        depth = self.panel.undo_stack.depth
        self.assertFalse(page.import_coaches(text))
        self.assertIn("Refused: [Team1] OverallRating", page.status_label.text())
        self.assertEqual(self.panel.undo_stack.depth, depth)
        self.assertEqual(page.save.to_bytes(), self.payload)
        self.assertFalse(page.import_coaches(cf.export_coaches(page.save)))
        self.assertIn("Nothing", page.status_label.text())

    def test_a_journal_replay_gives_the_same_bytes(self) -> None:
        page = self.page
        text = edit_text(cf.export_coaches(page.save), Team0={"Wins": "100", "First": "Billy"})
        self.assertTrue(page.import_coaches(text))
        live = page.save.to_bytes()
        self.assertTrue(page._rebuild())
        self.assertEqual(page.save.to_bytes(), live)
        self.assertEqual(FranchiseEdit("coaches_import", "x", {"text": text}).kind, "coaches_import")


# --------------------------------------------------------------------------------------------- roster save, synthetic
class RosterSaveCoachPageTests(_PanelCase):
    def test_a_roster_saves_coaches_export_and_import_in_coaches_only_mode(self) -> None:
        from test_b81_finn_parity import roster_save_with_coach
        payload = roster_save_with_coach()
        self.assertTrue(self.panel.load_save(write_container(self.root / "ro", payload)))
        page = self.page
        self.assertTrue(page.coaches_only)
        text = page.export_coaches_text()
        self.assertTrue(text.startswith("[") and "First=Bill\r\nLast=Belichick" in text, text[:80])
        self.assertEqual(cf.plan_import(page.save, text).changes, [])
        edited = edit_text(text, **{text.split("]")[0][1:]: {"Wins": "80", "OverallRating": "70"}})
        self.assertTrue(page.import_coaches(edited), page.status_label.text())
        self.assertEqual((page.save.coaches()[0].fields["wins"], page.save.coaches()[0].ratings["overall"]), (80, 70))
        self.panel.undo()
        self.assertEqual(page.save.coaches()[0].fields["wins"], 75)
        self.panel.redo()
        receipt = self.panel.write_copy_to(self.root / "copy")
        self.assertTrue(receipt["signed"])
        back = fs.FranchiseSave.roster_save(rr.SaveContainer.load(self.root / "copy").savegame)
        self.assertEqual(back.coaches()[0].fields["wins"], 80)


# --------------------------------------------------------------------------------------------- the real saves
@unittest.skipUnless(SOFTDRINK_ROSTER_SAVE.is_file(), f"SOFTDRINK roster save absent: {SOFTDRINK_ROSTER_SAVE}")
class SoftdrinkRosterCoachTests(unittest.TestCase):
    def test_export_is_a_clean_round_trip_and_one_changed_number_reaches_a_signed_copy(self) -> None:
        application = _app()
        panel = RosterEditorPanel()
        try:
            self.assertTrue(panel.load_save(SOFTDRINK_ROSTER_SAVE))
            page = panel.franchise_panel
            self.assertTrue(page.coaches_only)
            text = page.export_coaches_text()
            self.assertEqual(text.count("\r\n["), 31)
            self.assertTrue(text.startswith("[49ers]\r\n"))
            self.assertEqual(cf.plan_import(page.save, text).changes, [], "an untouched export changes nothing")
            self.assertEqual(len(cf.plan_import(page.save, text).skipped), 0)
            head = page.save.head_coach_index(0)
            coach = page.save.coaches()[head]
            wanted = coach.fields["wins"] + 3
            self.assertTrue(page.import_coaches(edit_text(text, **{"49ers": {"Wins": str(wanted)}})), page.status_label.text())
            with tempfile.TemporaryDirectory() as folder:
                receipt = panel.write_copy_to(Path(folder) / "copy.zip")
                self.assertTrue(receipt["signed"])
                copy = rr.SaveContainer.load(Path(folder) / "copy.zip")
                self.assertTrue(copy.verified)
                back = fs.FranchiseSave.roster_save(copy.savegame)
                self.assertEqual(back.coaches()[head].fields["wins"], wanted)
                source = rr.SaveContainer.load(SOFTDRINK_ROSTER_SAVE).savegame
                self.assertEqual(_changed(source, copy.savegame), [back._coach_offset(head) + 0x20],
                                 "one byte: his Wins")
                self.assertTrue(panel.load_save(Path(folder) / "copy.zip"))
                self.assertEqual(panel.franchise_panel.save.coaches()[head].fields["wins"], wanted)
        finally:
            panel.deleteLater()
            application.processEvents()

    def test_a_new_name_is_written_through_the_text_writer_and_only_coach_bytes_move(self) -> None:
        application = _app()
        panel = RosterEditorPanel()
        try:
            self.assertTrue(panel.load_save(SOFTDRINK_ROSTER_SAVE))
            page = panel.franchise_panel
            text = page.export_coaches_text()
            self.assertTrue(page.import_coaches(edit_text(text, **{"Bears": {"First": "Benjamin", "Last": "Johnsonian"}})),
                            page.status_label.text())
            self.assertEqual(page.last_import_receipt["names"], 2)
            head = page.save.head_coach_index(1)
            self.assertEqual(page.save.coaches()[head].name, "Benjamin Johnsonian")
            with tempfile.TemporaryDirectory() as folder:
                panel.write_copy_to(Path(folder) / "copy.zip")
                copy = rr.SaveContainer.load(Path(folder) / "copy.zip")
                back = fs.FranchiseSave.roster_save(copy.savegame)
                self.assertEqual(back.coaches()[head].name, "Benjamin Johnsonian")
                self.assertEqual(back.head_coaches(), fs.FranchiseSave.roster_save(
                    rr.SaveContainer.load(SOFTDRINK_ROSTER_SAVE).savegame).head_coaches())
                self.assertEqual(back.coach_text_problem(), "")
        finally:
            panel.deleteLater()
            application.processEvents()


@unittest.skipUnless(SEASON_2026.is_dir(), f"simulated SOFTDRINK 2026 season save absent: {SEASON_2026}")
class Softdrink2026CoachTests(unittest.TestCase):
    def test_a_head_coach_changed_number_round_trips_through_a_signed_copy(self) -> None:
        application = _app()
        panel = RosterEditorPanel()
        try:
            self.assertTrue(panel.load_save(SEASON_2026))
            page = panel.franchise_panel
            self.assertTrue(page.active)
            text = page.export_coaches_text()
            self.assertEqual(text.count("\r\n["), 31)
            self.assertEqual(cf.plan_import(page.save, text).changes, [])
            head = page.save.head_coach_index(2)
            wanted = page.save.coaches()[head].ratings["overall"] - 4
            self.assertTrue(page.import_coaches(edit_text(text, Bengals={"OverallRating": str(wanted)})),
                            page.status_label.text())
            with tempfile.TemporaryDirectory() as folder:
                receipt = panel.write_copy_to(Path(folder) / "copy")
                self.assertTrue(receipt["signed"])
                copy = rr.SaveContainer.load(Path(folder) / "copy")
                self.assertTrue(copy.verified)
                back = fs.FranchiseSave(copy.savegame)
                self.assertEqual(back.coaches()[head].ratings["overall"], wanted)
                source = rr.SaveContainer.load(SEASON_2026).savegame
                self.assertEqual(_changed(source, copy.savegame), [back._coach_offset(head) + fs.COACH_RATINGS_OFFSET])
                self.assertTrue(panel.load_save(Path(folder) / "copy"))
                self.assertEqual(panel.franchise_panel.save.coaches()[head].ratings["overall"], wanted)
        finally:
            panel.deleteLater()
            application.processEvents()


# --------------------------------------------------------------------------------------------- dead cap, core
def plant(payload: bytes, team: int, amounts: tuple[int, ...]) -> bytes:
    data = bytearray(payload)
    save = fs.FranchiseSave(payload)
    struct.pack_into("<7H", data, save.team_offset(team) + fs.TEAM_RECORD_RING, *amounts)
    return bytes(data)


class DeadCapCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        payload = synthetic_franchise(year_field=7, user_team=0)
        payload = plant(payload, 0, (1500, 400, 0, 0, 0, 0, 20))
        self.payload = plant(payload, 1, (0, 2500, 0, 0, 0, 0, 0))
        self.save = fs.FranchiseSave(self.payload)

    def test_dead_cap_reads_seven_seasons_this_season_first(self) -> None:
        self.assertEqual(ts.dead_cap(self.save, 0), (1500, 400, 0, 0, 0, 0, 20))
        self.assertEqual(ts.dead_cap(self.save, 2), (0,) * 7)
        self.assertEqual(self.save.team_offset(0) + 0x19C, self.save.team_offset(0) + fs.TEAM_RECORD_RING)
        with self.assertRaises(fs.FranchiseSaveError):
            ts.dead_cap(self.save, 3)

    def test_clear_zeroes_all_seven_seasons_and_only_those_bytes(self) -> None:
        receipt = ts.clear_dead_cap(self.save, 0)
        self.assertEqual((receipt["before"], receipt["after"]), ([1500, 400, 0, 0, 0, 0, 20], [0] * 7))
        self.assertEqual(ts.dead_cap(self.save, 0), (0,) * 7)
        ring = self.save.team_offset(0) + fs.TEAM_RECORD_RING
        self.assertTrue(set(_changed(self.payload, self.save.to_bytes())) <= set(range(ring, ring + 14)))
        self.assertEqual(ts.dead_cap(self.save, 1), (0, 2500, 0, 0, 0, 0, 0), "another club is not touched")
        self.assertEqual(ts.clear_dead_cap(self.save, 2)["before"], [0] * 7)             # nothing to clear: no change
        finn_would_show = 400 * 65536 + 1500            # Finn's u32 view of club 0: the wrong total this fixes
        self.assertNotEqual(finn_would_show, 1500)


class DeadCapPageTests(_PanelCase):
    def setUp(self) -> None:
        super().setUp()
        payload = plant(synthetic_franchise(year_field=7, user_team=0), 0, (1500, 400, 0, 0, 0, 0, 20))
        self.payload = plant(payload, 1, (750, 0, 0, 0, 0, 0, 0))
        self.load(self.payload)

    def test_the_column_and_tooltip_show_the_amounts_and_the_button_follows_the_selection(self) -> None:
        page = self.page
        table = page.salary_table
        self.assertEqual(table.horizontalHeaderItem(4).text(), "Dead cap")
        self.assertEqual([table.item(r, 4).text() for r in range(3)], ["$1.5M", "$750k", "-"])
        tip = table.item(0, 4).toolTip()
        self.assertIn("(this season): $1.5M", tip)
        self.assertIn("$400k", tip)
        self.assertIn("$20k", tip)
        self.assertIn("none", tip)
        self.assertIn("Only clubs a person controls", tip)
        self.assertIn("user-controlled", tip)
        self.assertIn("run by the CPU", table.item(1, 4).toolTip())
        self.assertEqual(table.item(0, 3).text(), "user-controlled")                      # the old columns stay put
        self.assertFalse(page.clear_cap_button.isEnabled())                               # nothing selected
        table.selectRow(0)
        self.assertTrue(page.clear_cap_button.isEnabled())
        self.assertIn("$1.5M", page.dead_cap_label.text())
        table.selectRow(2)
        self.assertFalse(page.clear_cap_button.isEnabled())
        self.assertIn("no dead cap", page.dead_cap_label.text())

    def test_the_confirmation_lists_each_season_and_clearing_is_one_undoable_edit(self) -> None:
        page = self.page
        text = page.cap_penalty_text(0)
        self.assertIn("(this season): $1.5M", text)
        self.assertIn("$400k", text)
        self.assertIn("$20k", text)
        self.assertNotIn("none", text)
        depth = len(page.edits)
        self.assertTrue(page.clear_cap_penalty(0))
        self.assertEqual(len(page.edits), depth + 1)
        self.assertEqual(page.edits[-1].kind, "dead_cap_clear")
        self.assertEqual(ts.dead_cap(page.save, 0), (0,) * 7)
        self.assertEqual(page.salary_table.item(0, 4).text(), "-")
        self.assertEqual(ts.dead_cap(page.save, 1)[0], 750)
        page.salary_table.selectRow(0)
        self.assertFalse(page.clear_cap_button.isEnabled(), "nothing left to clear")
        self.assertFalse(page.clear_cap_penalty(0))
        self.panel.undo()
        self.assertEqual(ts.dead_cap(page.save, 0), (1500, 400, 0, 0, 0, 0, 20))
        self.assertEqual(page.save.to_bytes(), self.payload)
        self.panel.redo()
        self.assertEqual(ts.dead_cap(page.save, 0), (0,) * 7)

    def test_the_signed_copy_reloads_with_zeros_and_nothing_else_changed(self) -> None:
        page = self.page
        self.assertTrue(page.clear_cap_penalty(0))
        receipt = self.panel.write_copy_to(self.root / "copy")
        self.assertTrue(receipt["signed"])
        container = rr.SaveContainer.load(self.root / "copy")
        self.assertTrue(container.verified)
        back = fs.FranchiseSave(container.savegame)
        self.assertEqual(ts.dead_cap(back, 0), (0,) * 7)
        self.assertEqual(ts.dead_cap(back, 1), (750, 0, 0, 0, 0, 0, 0))
        ring = back.team_offset(0) + fs.TEAM_RECORD_RING
        self.assertEqual(set(_changed(self.payload, container.savegame)), set(range(ring, ring + 14)) - {
            i for i in range(ring, ring + 14) if self.payload[i] == 0})
        self.assertTrue(self.panel.load_save(self.root / "copy"))
        self.assertEqual(ts.dead_cap(self.panel.franchise_panel.save, 0), (0,) * 7)

    def test_a_roster_save_has_no_cap_penalty_to_clear(self) -> None:
        from test_b81_finn_parity import roster_save_with_coach
        self.assertTrue(self.panel.load_save(write_container(self.root / "ro", roster_save_with_coach())))
        self.assertFalse(self.page.clear_cap_button.isEnabled())
        self.assertFalse(self.page.clear_cap_penalty(0))


@unittest.skipUnless(SEASON_2026.is_dir(), f"simulated SOFTDRINK 2026 season save absent: {SEASON_2026}")
class Softdrink2026DeadCapTests(unittest.TestCase):
    def test_planted_dead_cap_on_the_real_save_clears_through_a_signed_copy(self) -> None:
        application = _app()
        source = rr.SaveContainer.load(SEASON_2026).savegame
        save = fs.FranchiseSave(source)
        self.assertTrue(all(not any(ts.dead_cap(save, t)) for t in range(32)), "the fixture has no dead cap")
        planted = plant(plant(source, 5, (3200, 1000, 0, 0, 0, 0, 0)), 9, (0, 0, 640, 0, 0, 0, 0))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            panel = RosterEditorPanel()
            try:
                self.assertTrue(panel.load_save(write_container(root / "fr", planted)))
                page = panel.franchise_panel
                self.assertEqual(page.salary_table.item(5, 4).text(), "$3.2M")
                self.assertEqual(page.salary_table.item(9, 4).text(), "-", "this season's column reads slot 0 only")
                self.assertIn("$640k", page.salary_table.item(9, 4).toolTip())
                self.assertTrue(page.clear_cap_penalty(5))
                self.assertTrue(page.clear_cap_penalty(9))
                receipt = panel.write_copy_to(root / "copy")
                self.assertTrue(receipt["signed"])
                copy = rr.SaveContainer.load(root / "copy")
                self.assertTrue(copy.verified)
                back = fs.FranchiseSave(copy.savegame)
                self.assertTrue(all(not any(ts.dead_cap(back, t)) for t in range(32)))
                self.assertEqual(copy.savegame, source, "clearing returns the save to the fixture, byte for byte")
                self.assertTrue(panel.load_save(root / "copy"))
            finally:
                panel.deleteLater()
                application.processEvents()


if __name__ == "__main__":
    unittest.main()

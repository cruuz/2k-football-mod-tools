"""b780 c4-staffui: the staff document the Rosters > Coaches page edits (``nfl2k5_staff_ui``).

Pure data: the 32 clubs, the roster read, and every function that turns one staff document into the next.  The
invariants the build checks (one head coach and one coordinator per club, nobody in two seats, nobody lost without
being replaced) are asserted after every kind of move.  The last class is the contract with the build-time engine
(``nfl2k5_coach_staff``, job c2-staff): it runs only where that module exists.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_staff_ui as ui  # noqa: E402
from b780_staff_fixture import PASS_MIX, RUN_MIX, synthetic_staff_franchise  # noqa: E402
from test_roster_editor_panel_franchise import write_container  # noqa: E402

DISC = Path(os.environ.get("NFL2K5_SOFTDRINK_DISC", "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.8 (2026-10-31).xiso.iso"))


def rows_2026() -> list[ui.HeadCoachRow]:
    """The 32 clubs with their 2026 head coaches, as a SOFTDRINK roster holds them."""

    homes = {code: name for name, code in ui.head_coach_homes().items()}
    return [ui.HeadCoachRow(club, f"{club.code} club", index, *homes[club.code].split(" ", 1), career={"wins": 10 + index},
                            run_share=40 + index % 10) for index, club in enumerate(ui.CLUBS)]


def book(name: str) -> str:
    return ui.club(name).book


class ClubTests(unittest.TestCase):
    def test_the_32_clubs_in_the_games_team_order(self) -> None:
        self.assertEqual(len(ui.CLUBS), 32)
        self.assertEqual([c.index for c in ui.CLUBS], list(range(32)))
        self.assertEqual(len({c.book for c in ui.CLUBS}), 32)
        self.assertEqual(len({c.code for c in ui.CLUBS}), 32)
        self.assertEqual((ui.CLUBS[7].book, ui.CLUBS[7].code), ("ARZ", "ARI"))
        self.assertEqual((ui.CLUBS[22].book, ui.CLUBS[22].code), ("OAK", "LV"))
        self.assertEqual(ui.CLUBS[25].nickname, "Commanders")

    def test_a_club_resolves_from_any_spelling(self) -> None:
        for spelling in ("LV", "lv", "OAK", "Raiders", "raiders", 22, ui.CLUBS[22]):
            self.assertEqual(ui.club(spelling).book, "OAK", spelling)
        self.assertEqual(ui.club("Redskins").code, "WAS")
        for bad in ("XYZ", "", 32, -1, None, True):
            with self.assertRaises(ui.StaffUiError):
                ui.club(bad)

    def test_the_studios_2026_data_covers_every_club(self) -> None:
        people = ui.coordinators()
        self.assertEqual(sorted(people), sorted(c.book for c in ui.CLUBS))
        self.assertTrue(all(p.name for p in people.values()))
        homes = ui.head_coach_homes()
        self.assertEqual(sorted(homes.values()), sorted(c.code for c in ui.CLUBS))
        for code in homes.values():
            self.assertIsNotNone(ui.face_path(code), code)


class ReadTests(unittest.TestCase):
    def test_the_head_coaches_come_out_of_a_loaded_roster(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            source = write_container(Path(td) / "save", synthetic_staff_franchise())
            document = rr.SaveContainer.load(source).document()
            rows = ui.read_head_coaches(document)
        self.assertEqual([r.club.code for r in rows], ["SF", "CHI", "CIN"])             # the synthetic league has three teams
        self.assertEqual([r.name for r in rows], ["Bill Belichick", "Andy Reid", "Kyle Shanahan"])
        belichick = rows[0]
        self.assertEqual((belichick.record, belichick.photo, belichick.body, belichick.flags), (0, 7016, 21, 0))
        self.assertEqual(belichick.bio, ("One of the winningest coaches", "in football history", ""))
        self.assertEqual((belichick.career["wins"], belichick.career["losses"], belichick.career["super_bowls"]), (75, 69, 2))
        self.assertEqual(belichick.ratings["overall"], 50)
        self.assertEqual(belichick.run_share, 40)
        self.assertEqual(rows[2].run_share, 42)

    def test_the_ten_formation_bytes_are_read_under_their_true_names(self) -> None:
        """Shares of his run calls by formation, then shares of his pass calls (job c1-coachdata); never run / pass pairs."""

        with tempfile.TemporaryDirectory() as td:
            source = write_container(Path(td) / "save", synthetic_staff_franchise())
            rows = ui.read_head_coaches(rr.SaveContainer.load(source).document())
        classes = ("gun", "split_backs", "i_form", "one_back", "no_back")
        run_names, pass_names = [f"run_{c}" for c in classes], [f"pass_{c}" for c in classes]
        belichick, reid = rows[0], rows[1]
        self.assertEqual(list(belichick.tendencies), run_names + pass_names)
        self.assertEqual([belichick.tendencies[n] for n in run_names], list(RUN_MIX))
        self.assertEqual([belichick.tendencies[n] for n in pass_names], list(PASS_MIX))
        for row in rows:                                         # each set of five is its own distribution of 100
            self.assertEqual(sum(row.tendencies[n] for n in run_names), 100, row.name)
            self.assertEqual(sum(row.tendencies[n] for n in pass_names), 100, row.name)
        # the fixture rotates both sets by one class per coach: Reid's first byte is Belichick's second
        self.assertEqual((reid.tendencies["run_gun"], reid.tendencies["pass_gun"]), (RUN_MIX[1], PASS_MIX[1]))


class SwapMoveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = rows_2026()
        self.names = {r.club.book: r.name for r in self.rows}

    def check(self, staff) -> None:
        self.assertEqual(ui.problems(self.rows, staff), [])
        self.assertEqual(staff["schema"], ui.SCHEMA)

    def test_nothing_changed_is_an_empty_document(self) -> None:
        staff = ui.empty()
        self.assertTrue(ui.is_empty(staff))
        self.assertTrue(ui.is_empty(None))
        self.check(staff)
        self.assertEqual(ui.describe(self.rows, staff), [])
        self.assertEqual(ui.head_seats(self.rows, staff)["KC"], ("coach", self.names["KC"]))

    def test_a_swap_writes_two_entries_in_club_order_and_swapping_back_empties_the_document(self) -> None:
        staff = ui.swap_head_coaches(self.rows, ui.empty(), "LV", "KC")
        self.check(staff)
        self.assertEqual(staff["head_coaches"], [{"team": "KC", "coach": self.names["OAK"]},
                                                 {"team": "OAK", "coach": self.names["KC"]}])    # the engine's own canonical form
        self.assertEqual(staff["created_coaches"], [])
        lines = ui.describe(self.rows, staff)
        self.assertEqual(lines, [f"KC head coach: {self.names['KC']} → {self.names['OAK']} (from LV)",
                                 f"LV head coach: {self.names['OAK']} → {self.names['KC']} (from KC)"])
        again = ui.swap_head_coaches(self.rows, staff, "KC", "LV")
        self.assertTrue(ui.is_empty(again))
        self.assertEqual(again, ui.empty())
        with self.assertRaisesRegex(ui.StaffUiError, "two different clubs"):
            ui.swap_head_coaches(self.rows, ui.empty(), "KC", "kc")

    def test_chained_swaps_keep_everybody_employed_once(self) -> None:
        staff = ui.empty()
        for a, b in (("KC", "DAL"), ("DAL", "PHI"), ("SF", "KC")):
            staff = ui.swap_head_coaches(self.rows, staff, a, b)
            self.check(staff)
            seats = ui.head_seats(self.rows, staff)
            self.assertEqual(len(set(seats.values())), 32)
        self.assertEqual(ui.let_go(self.rows, staff), [])

    def test_moving_a_coach_to_a_club_swaps_the_two_clubs(self) -> None:
        staff = ui.move_head_coach(self.rows, ui.empty(), self.names["TB"], "KC")
        self.check(staff)
        seats = ui.head_seats(self.rows, staff)
        self.assertEqual((seats["KC"], seats["TB"]), (("coach", self.names["TB"]), ("coach", self.names["KC"])))
        with self.assertRaisesRegex(ui.StaffUiError, "already coaches"):
            ui.move_head_coach(self.rows, ui.empty(), self.names["KC"], "KC")

    def test_a_coach_who_was_let_go_can_be_hired_again(self) -> None:
        staff, _id = ui.hire_created_coach(self.rows, ui.empty(), "KC", {"first": "Pat", "last": "Shurmur"})
        self.assertEqual(ui.let_go(self.rows, staff), [self.names["KC"]])
        again = ui.move_head_coach(self.rows, staff, self.names["KC"], "DAL")
        self.check(again)
        seats = ui.head_seats(self.rows, again)
        self.assertEqual(seats["DAL"], ("coach", self.names["KC"]))
        self.assertEqual(ui.let_go(self.rows, again), [self.names["DAL"]])
        self.assertIn(f"{self.names['DAL']} is let go and leaves the roster", ui.describe(self.rows, again))

    def test_a_person_cannot_be_hired_into_two_seats(self) -> None:
        with self.assertRaisesRegex(ui.StaffUiError, "already coaches a club"):
            ui.hire_head_coach(self.rows, ui.empty(), "KC", ("coach", self.names["DAL"]))
        with self.assertRaisesRegex(ui.StaffUiError, "not a head coach on this roster"):
            ui.hire_head_coach(self.rows, ui.empty(), "KC", ("coach", "Nobody Atall"))
        with self.assertRaisesRegex(ui.StaffUiError, "no new coach"):
            ui.hire_head_coach(self.rows, ui.empty(), "KC", ("created", "ghost"))


class NewCoachTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = rows_2026()

    def test_a_new_coach_takes_the_seat_and_the_old_coach_is_let_go(self) -> None:
        staff, new_id = ui.hire_created_coach(self.rows, ui.empty(), "NYG",
                                              {"first": " Pat ", "last": "Shurmur", "bio": ["A fine mind", "", ""], "body": 21,
                                               "style": "SF", "ratings": {"overall": 70}, "playcalling_run": 40})
        self.assertEqual(new_id, "pat-shurmur")
        self.assertEqual(staff["head_coaches"], [{"team": "NYG", "created": "pat-shurmur"}])
        spec = staff["created_coaches"][0]
        self.assertEqual((spec["id"], spec["first"], spec["last"], spec["bio"], spec["body"], spec["photo"], spec["style"],
                          spec["ratings"], spec["playcalling_run"]),
                         ("pat-shurmur", "Pat", "Shurmur", ["A fine mind", "", ""], 21, 8999, "SF", {"overall": 70}, 40))
        self.assertEqual(ui.problems(self.rows, staff), [])
        self.assertEqual(ui.describe(self.rows, staff)[0], f"NYG head coach: {self.rows[15].name} → Pat Shurmur (new coach)")
        self.assertEqual(ui.let_go(self.rows, staff), [self.rows[15].name])

    def test_ids_are_unique_and_a_displaced_new_coach_leaves_the_document(self) -> None:
        staff, first = ui.hire_created_coach(self.rows, ui.empty(), "KC", {"first": "Pat", "last": "Shurmur"})
        staff, second = ui.hire_created_coach(self.rows, staff, "DAL", {"first": "Pat", "last": "Shurmur."})   # same slug, other name
        self.assertEqual((first, second), ("pat-shurmur", "pat-shurmur-2"))
        self.assertEqual([c["id"] for c in staff["created_coaches"]], ["pat-shurmur", "pat-shurmur-2"])
        staff, third = ui.hire_created_coach(self.rows, staff, "KC", {"first": "Wes", "last": "Welker"})
        ids = {c["id"] for c in staff["created_coaches"]}
        self.assertNotIn("pat-shurmur", ids)                                   # displaced: he is simply gone
        self.assertEqual(ids, {"pat-shurmur-2", third})
        self.assertEqual(ui.problems(self.rows, staff), [])

    def test_a_new_coach_can_move_on_with_a_swap(self) -> None:
        staff, new_id = ui.hire_created_coach(self.rows, ui.empty(), "KC", {"first": "Pat", "last": "Shurmur"})
        staff = ui.swap_head_coaches(self.rows, staff, "KC", "DAL")
        seats = ui.head_seats(self.rows, staff)
        self.assertEqual((seats["DAL"], seats["KC"]), (("created", new_id), ("coach", self.rows[11].name)))
        self.assertEqual(ui.problems(self.rows, staff), [])

    def test_checked_in_plain_words(self) -> None:
        cases = (
            (dict(first="", last="Quinn"), "type the coach's first name"),
            (dict(first="Dan", last=" "), "type the coach's last name"),
            (dict(first="D" * 25, last="Quinn"), "longer than 24"),
            (dict(first="Dan", last="Quinn", bio=["x" * 53]), "longer than 52"),
            (dict(first="Dan", last="Qu\x00inn"), "character the game cannot show"),
            (dict(first="Dan", last="Quinn", body=99), "not one the game has"),
            (dict(first="Dan", last="Quinn", overall=100), "0 to 99"),
            (dict(first="Dan", last="Quinn", playcalling_run=101), "0 to 100"),
            (dict(first="Dan", last="Quinn", style="XYZ"), "not one of the 32 clubs"),
        )
        for kwargs, message in cases:
            with self.assertRaisesRegex(ui.StaffUiError, message):
                ui.new_coach_spec(**kwargs)
        self.assertEqual(ui.new_coach_spec("Dan", "Quinn")["body"], ui.DEFAULT_BODY)
        self.assertIn(50, ui.COACH_BODIES)
        self.assertNotIn(31, ui.COACH_BODIES)


class NameRuleTests(unittest.TestCase):
    """A staff plan tells coaches apart by name, so the page never builds an ambiguous one."""

    def test_two_clubs_with_one_head_coach_name_cannot_be_moved_by_name(self) -> None:
        rows = rows_2026()
        twin = rows[8].name                                                    # SD gets the name KC already has
        rows[8] = ui.HeadCoachRow(rows[8].club, "SD club", 8, *rows[9].name.split(" ", 1))
        self.assertEqual(rows[8].name, rows[9].name)
        for call in (lambda: ui.swap_head_coaches(rows, ui.empty(), "KC", "DAL"),
                     lambda: ui.swap_head_coaches(rows, ui.empty(), "DAL", "SD"),
                     lambda: ui.move_head_coach(rows, ui.empty(), rows[9].name, "DAL")):
            with self.assertRaisesRegex(ui.StaffUiError, "more than one club on this roster"):
                call()
        self.assertNotEqual(twin, rows[8].name)
        # clubs that do not involve the twins still work
        self.assertEqual(ui.problems(rows, ui.swap_head_coaches(rows, ui.empty(), "DAL", "PHI")), [])

    def test_a_new_coach_cannot_take_a_name_the_plan_already_has(self) -> None:
        rows = rows_2026()
        with self.assertRaisesRegex(ui.StaffUiError, "already a head coach's name"):
            ui.hire_created_coach(rows, ui.empty(), "NYG", {"first": rows[9].name.split(" ", 1)[0], "last": rows[9].name.split(" ", 1)[1]})
        staff, _id = ui.hire_created_coach(rows, ui.empty(), "NYG", {"first": "Pat", "last": "Shurmur"})
        with self.assertRaisesRegex(ui.StaffUiError, "already a head coach's name"):
            ui.hire_created_coach(rows, staff, "DAL", {"first": "pat", "last": "SHURMUR"})

    def test_a_new_coach_brings_a_playbook_only_with_a_play_calling_style(self) -> None:
        rows = rows_2026()
        plain, _id = ui.hire_created_coach(rows, ui.empty(), "NYG", {"first": "Pat", "last": "Shurmur"})
        with self.assertRaisesRegex(ui.StaffUiError, "calls plays like another coach"):
            ui.set_playbook(rows, plain, "NYG", "coach")
        styled, _id = ui.hire_created_coach(rows, ui.empty(), "NYG", {"first": "Pat", "last": "Shurmur", "style": "SF"})
        brought = ui.set_playbook(rows, styled, "NYG", "coach")
        self.assertEqual(brought["head_coaches"], [{"team": "NYG", "created": "pat-shurmur", "playbook": "coach"}])
        self.assertEqual(ui.problems(rows, brought), [])
        broken = json.loads(json.dumps(brought))
        del broken["created_coaches"][0]["style"]
        self.assertTrue(any("calls plays like another coach" in line for line in ui.problems(rows, broken)))


class CoordinatorAndPlaybookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = rows_2026()
        self.people = ui.coordinators()

    def test_a_coordinator_change_is_a_swap_of_two_defenses(self) -> None:
        staff = ui.set_coordinator(self.rows, ui.empty(), "KC", "PHI")
        self.assertEqual(ui.problems(self.rows, staff), [])
        self.assertEqual([(e["team"], e["dc"]) for e in staff["defensive_coordinators"]], [("KC", "PHI"), ("PHI", "KC")])
        seats = ui.dc_seats(staff)
        self.assertEqual((seats["KC"], seats["PHI"]), ("PHI", "KC"))
        lines = ui.describe(self.rows, staff)
        self.assertEqual(lines, [f"KC defensive coordinator: {self.people['KC'].name} → {self.people['PHI'].name} (from PHI)",
                                 f"PHI defensive coordinator: {self.people['PHI'].name} → {self.people['KC'].name} (from KC)"])
        back = ui.set_coordinator(self.rows, staff, "KC", "KC")
        self.assertTrue(ui.is_empty(back))
        with self.assertRaisesRegex(ui.StaffUiError, "already runs this defense"):
            ui.set_coordinator(self.rows, ui.empty(), "KC", "KC")

    def test_a_dc_swap_through_the_old_oakland_code_is_the_same_club(self) -> None:
        staff = ui.set_coordinator(self.rows, ui.empty(), "LV", "KC")
        self.assertEqual({e["team"] for e in staff["defensive_coordinators"]}, {"KC", "OAK"})

    def test_only_an_arriving_coach_can_bring_his_playbook(self) -> None:
        with self.assertRaisesRegex(ui.StaffUiError, "only a coach who arrives"):
            ui.set_playbook(self.rows, ui.empty(), "KC", "coach")
        staff = ui.swap_head_coaches(self.rows, ui.empty(), "KC", "DAL")
        staff = ui.set_playbook(self.rows, staff, "KC", "coach")
        self.assertEqual({e["team"]: e.get("playbook", "club") for e in staff["head_coaches"]}, {"KC": "coach", "DAL": "club"})
        self.assertIn("brings his playbook", ui.describe(self.rows, staff)[0])
        self.assertEqual(ui.problems(self.rows, staff), [])
        with self.assertRaisesRegex(ui.StaffUiError, "playbook must be"):
            ui.set_playbook(self.rows, staff, "KC", "both")
        # a new arrival resets the choice, and swapping the pair back empties the document
        staff = ui.swap_head_coaches(self.rows, staff, "KC", "PHI")
        self.assertEqual({e["team"]: e.get("playbook", "club") for e in staff["head_coaches"]}.get("KC"), "club")
        self.assertTrue(ui.is_empty(ui.reset(staff)))


class ProblemTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = rows_2026()
        self.names = {r.club.book: r.name for r in self.rows}

    def staff(self, **sections) -> dict:
        doc = ui.empty()
        doc.update(sections)
        return doc

    def test_every_kind_of_wrong_document_is_named(self) -> None:
        names = self.names
        cases = (
            (self.staff(head_coaches=[{"team": "XYZ", "coach": names["KC"]}]), "names a club that does not exist"),
            (self.staff(head_coaches=[{"team": "KC", "coach": "Nobody Atall"}]), "who is not a head coach on this roster"),
            (self.staff(head_coaches=[{"team": "KC", "created": "ghost"}]), "does not define"),
            (self.staff(head_coaches=[{"team": "KC"}]), "nobody in it"),
            (self.staff(head_coaches=[{"team": "KC", "coach": names["DAL"]}]), f"DAL lost {names['DAL']} and nobody replaces him"),
            (self.staff(head_coaches=[{"team": "KC", "coach": names["DAL"]}, {"team": "PHI", "coach": names["DAL"]}]),
             f"{names['DAL']} would coach both KC and PHI"),
            (self.staff(head_coaches=[{"team": "KC", "coach": names["DAL"], "playbook": "x"}, {"team": "DAL", "coach": names["KC"]}]),
             "playbook choice must be club or coach"),
            (self.staff(head_coaches=[{"team": "KC", "coach": names["DAL"]}, {"team": "kc", "coach": names["DAL"]}]),
             "KC has two head coach entries"),
            (self.staff(defensive_coordinators=[{"team": "KC", "dc": "PHI"}]), "would run 2 defenses"),
            (self.staff(defensive_coordinators=[{"team": "KC", "dc": "XYZ"}]), "names a club that does not exist"),
            ({"schema": "other/v9", "head_coaches": []}, "this Studio writes"),
        )
        for doc, message in cases:
            found = ui.problems(self.rows, doc)
            self.assertTrue(any(message in line for line in found), (message, found))
        self.assertEqual(ui.problems(self.rows, "not a document"), ["the staff file is not a staff document"])

    def test_a_full_valid_document_has_no_problems(self) -> None:
        names = self.names
        doc = self.staff(head_coaches=[{"team": "KC", "coach": names["DAL"], "playbook": "coach"},
                                       {"team": "DAL", "coach": names["KC"], "playbook": "club"},
                                       {"team": "NYG", "created": "pat-shurmur"}],
                         defensive_coordinators=[{"team": "KC", "dc": "PHI"}, {"team": "PHI", "dc": "KC"}],
                         created_coaches=[{"id": "pat-shurmur", "first": "Pat", "last": "Shurmur"}])
        self.assertEqual(ui.problems(self.rows, doc), [])


class FileTests(unittest.TestCase):
    def test_a_staff_file_round_trips_and_a_roster_edits_file_carries_one(self) -> None:
        rows = rows_2026()
        staff = ui.swap_head_coaches(rows, ui.empty(), "KC", "DAL")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "staff.json"
            ui.write_file(path, staff)
            self.assertEqual(ui.read_file(path), staff)
            self.assertNotIn(b"\r", path.read_bytes())
            wrapped = Path(td) / "roster_edits.json"
            wrapped.write_text(json.dumps({"schema": rr.EDITS_SCHEMA, "edits": [], "staff": staff}), encoding="utf-8")
            self.assertEqual(ui.read_file(wrapped), staff)
            other = Path(td) / "other.json"
            other.write_text(json.dumps({"schema": "x/v1", "edits": []}), encoding="utf-8")
            with self.assertRaisesRegex(ui.StaffUiError, "not a staff file"):
                ui.read_file(other)
            other.write_text("[1, 2]", encoding="utf-8")
            with self.assertRaisesRegex(ui.StaffUiError, "JSON object"):
                ui.read_file(other)


class EngineContractTests(unittest.TestCase):
    """What c2-staff's ``nfl2k5_coach_staff`` promised in its report, checked where the module exists."""

    def test_without_the_engine_the_page_still_judges_the_document_itself(self) -> None:
        if ui.engine() is not None:
            self.skipTest("the build-time engine is installed; the contract tests below cover it")
        self.assertIsNone(ui.engine())
        rows = rows_2026()
        staff = ui.swap_head_coaches(rows, ui.empty(), "KC", "DAL")
        self.assertEqual(ui.engine_plan(staff, b""), ui.EnginePlan())
        self.assertEqual(ui.engine_normalized(staff), staff)

    @unittest.skipUnless(ui.engine() is not None and DISC.is_file(),
                         "needs nfl2k5_coach_staff (job b780-c2-staff) and the released disc")
    def test_the_engine_accepts_the_pages_documents_and_makes_the_same_ones(self) -> None:
        engine = ui.engine()
        document = rr.load_image(DISC)
        rows = ui.read_head_coaches(document)
        body = document.to_body()
        staff = ui.swap_head_coaches(rows, ui.empty(), "KC", "DAL")
        staff, new_id = ui.hire_created_coach(rows, staff, "NYG", {"first": "Pat", "last": "Shurmur", "body": 21, "style": "SF",
                                                                    "ratings": {"overall": 70}, "bio": ["A patient play caller."]})
        staff = ui.set_coordinator(rows, staff, "KC", "PHI")
        staff = ui.set_playbook(rows, staff, "KC", "coach")
        staff = ui.set_playbook(rows, staff, "NYG", "coach")
        normal = engine.normalize(staff)                          # raises StaffError when the engine disagrees
        self.assertEqual(normal["head_coaches"], staff["head_coaches"])
        self.assertEqual(normal["defensive_coordinators"], staff["defensive_coordinators"])
        self.assertEqual([c["id"] for c in normal["created_coaches"]], [new_id])
        # the released disc's roster has grown (the capacity arena), where a created coach cannot be written: the plan says
        # so, as apply_to_body does (b780 studio1; before, the plan passed it and the build stopped in its roster step)
        grown = ("a created coach can be written only on a roster before its capacity growth (build from your retail disc); "
                 "this roster has grown")
        plan = engine.plan(staff, body)
        self.assertEqual(list(plan.errors), [grown])
        answer = ui.engine_plan(staff, body)
        self.assertEqual((answer.errors, len(answer.clubs)), ((grown,), 32))
        plain = ui.swap_head_coaches(rows, ui.empty(), "KC", "DAL")          # moves of the clubs' own coaches write on it
        plain = ui.set_coordinator(rows, plain, "KC", "PHI")
        plain = ui.set_playbook(rows, plain, "KC", "coach")
        self.assertEqual(list(engine.plan(plain, body).errors), [])
        self.assertEqual(ui.engine_plan(plain, body).errors, ())
        for key in ("team", "playbook_from", "profile", "native_reason"):
            self.assertIn(key, answer.clubs["KC"])
        self.assertEqual(answer.clubs["KC"]["playbook_from"], "DAL")
        # the engine's own editing helpers write the documents the page writes
        self.assertEqual(engine.swap_head_coaches(engine.empty(), "KC", "DAL", body), ui.swap_head_coaches(rows, ui.empty(), "KC", "DAL"))
        self.assertEqual(engine.set_defensive_coordinator(engine.empty(), "KC", "PHI"), ui.set_coordinator(rows, ui.empty(), "KC", "PHI"))
        self.assertEqual(engine.move_head_coach(engine.empty(), rows[11].name, "KC", body), ui.move_head_coach(rows, ui.empty(), rows[11].name, "KC"))
        self.assertEqual(engine.hire_created_coach(engine.empty(), "NYG", ui.created_coaches(staff)[new_id])["head_coaches"],
                         [{"team": "NYG", "created": new_id}])
        # and refuses what the page refuses
        for bad in (dict(ui.empty(), head_coaches=[{"team": "KC", "coach": rows[11].name}]),):
            self.assertTrue(engine.plan(bad, body).errors)
            self.assertTrue(ui.problems(rows, bad))


@unittest.skipUnless(DISC.is_file(), f"the released SOFTDRINK disc is not at {DISC}")
class RealDiscTests(unittest.TestCase):
    """Read-only: the 32 head coaches out of the released v0.8 disc's own roster."""

    def test_the_released_disc_has_the_2026_head_coaches_in_club_order(self) -> None:
        document = rr.load_image(DISC)
        rows = ui.read_head_coaches(document)
        self.assertEqual(len(rows), 32)
        homes = ui.head_coach_homes()
        self.assertEqual([r.name for r in rows], [next(n for n, c in homes.items() if c == r.club.code) for r in rows])
        self.assertTrue(all(r.record is not None for r in rows))
        staff = ui.swap_head_coaches(rows, ui.empty(), "KC", "DAL")
        self.assertEqual(ui.problems(rows, staff), [])


if __name__ == "__main__":
    unittest.main()

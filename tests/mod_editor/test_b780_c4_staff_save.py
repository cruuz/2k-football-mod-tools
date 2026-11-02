"""b780 c4-staffui: Fire / Hire / Swap a head coach inside a franchise save (``FranchiseSave``).

A coach is a record the clubs' ``+0x14C`` pointers aim at, so a swap is two pointer changes plus the new-job counters.
These tests prove, on a synthetic arena with a real-shaped coach table and on the real franchise fixtures (skipped
when ``NFL2K5_SAVE_FIXTURES`` is absent): exactly which bytes change, every refusal, that a refusal changes nothing,
that the coach text writer keeps every other coach's text, and that a signed copy reloads with the move in it.
"""

from __future__ import annotations

import contextlib
import io
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_franchise_save as fs  # noqa: E402
from mod_editor.core import nfl2k5_practice_squad as ps  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from b780_staff_fixture import COACH_AT, PASS_MIX, RUN_MIX, STAFF, STRINGS_AT, synthetic_staff_franchise  # noqa: E402
from test_nfl2k5_franchise_save import F0, FIXTURES, FRANCHISE1  # noqa: E402
from test_roster_editor_panel_franchise import write_container  # noqa: E402


def team_field(save: fs.FranchiseSave, team: int) -> int:
    return save.team_offset(team) + rr.TEAM_COACH


def coach_record(index: int) -> int:
    return COACH_AT + index * fs.COACH_SIZE


def point(buffer: bytearray, field: int, target: int) -> None:
    struct.pack_into("<i", buffer, field, target - field + 1)


def texts(save: fs.FranchiseSave) -> list[tuple[str, str, tuple[str, str, str]]]:
    return [(c.first, c.last, c.info) for c in save.coaches()]


def changed_bytes(before: bytes, after: bytes) -> set[int]:
    return {i for i, (a, b) in enumerate(zip(before, after)) if a != b}


class SwapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = synthetic_staff_franchise()
        self.save = fs.FranchiseSave(self.payload)

    def test_the_fixture_reads_as_a_league(self) -> None:
        save = self.save
        self.assertEqual(save.head_coaches(), {0: 0, 1: 1, 2: 2})
        self.assertEqual([c.name for c in save.coaches()][:4], ["Bill Belichick", "Andy Reid", "Kyle Shanahan", "Mike Holmgren"])
        self.assertEqual([c.name for c in save.unemployed_coaches()], ["Mike Holmgren"])
        self.assertEqual([c.placeholder for c in save.coaches()], [False, False, False, False, True, True])
        self.assertEqual(save.coaches()[0].teams, (0,))
        self.assertEqual(save.coaches()[3].teams, ())

    def test_a_swap_changes_two_pointers_and_the_new_job_counters_and_nothing_else(self) -> None:
        save = self.save
        receipt = save.swap_head_coaches(0, 1)
        self.assertEqual(save.head_coaches(), {0: 1, 1: 0, 2: 2})
        self.assertEqual(save.coach_for_team(0).name, "Andy Reid")
        self.assertEqual(save.coach_for_team(1).name, "Bill Belichick")
        self.assertEqual(receipt["operation"], "swap_head_coaches")
        self.assertEqual([(t["abbreviation"], t["before"]["name"], t["after"]["name"]) for t in receipt["teams"]],
                         [("IND", "Bill Belichick", "Andy Reid"), ("ATL", "Andy Reid", "Bill Belichick")])
        # the same swap done by hand on the raw bytes
        expected = bytearray(self.payload)
        point(expected, team_field(save, 0), coach_record(1))
        point(expected, team_field(save, 1), coach_record(0))
        for index in (0, 1):
            for name in fs.COACH_WITH_TEAM:
                rel, fmt = fs.COACH_FIELDS[name]
                struct.pack_into(fmt, expected, coach_record(index) + rel, 0)
            expected[coach_record(index) + fs.COACH_FLAGS] |= fs.COACH_FLAG_NO_NAME
        self.assertEqual(save.to_bytes(), bytes(expected))
        # career totals, ratings and play-calling travel with him
        reid = save.coach_for_team(0)
        self.assertEqual((reid.fields["wins"], reid.fields["losses"], reid.fields["super_bowls"]), (279, 157, 6))
        self.assertEqual((reid.fields["seasons_with_team"], reid.fields["total_seasons"]), (0, 27))
        self.assertEqual((reid.fields["season_wins"], reid.fields["season_losses"]), (0, 0))
        self.assertEqual(reid.ratings["overall"], 53)
        self.assertEqual(reid.fields["playcalling_run"], 41)
        self.assertEqual(sorted(receipt["restarted"]), ["0", "1"])
        self.assertEqual(receipt["announcer_flagged"], [0, 1])

    def test_a_swap_can_keep_the_counters_and_the_announcer(self) -> None:
        save = self.save
        save.swap_head_coaches(1, 2, restart=False, announcer_generic=False)
        expected = bytearray(self.payload)
        point(expected, team_field(save, 1), coach_record(2))
        point(expected, team_field(save, 2), coach_record(1))
        self.assertEqual(save.to_bytes(), bytes(expected))
        changed = changed_bytes(self.payload, save.to_bytes())
        windows = set(range(team_field(save, 1), team_field(save, 1) + 4)) | set(range(team_field(save, 2), team_field(save, 2) + 4))
        self.assertTrue(changed and changed <= windows)               # two pointers, nothing else

    def test_swapping_twice_puts_every_pointer_back(self) -> None:
        save = self.save
        save.swap_head_coaches(0, 2, restart=False, announcer_generic=False)
        save.swap_head_coaches(2, 0, restart=False, announcer_generic=False)
        self.assertEqual(save.to_bytes(), self.payload)

    def test_every_refusal_says_why_and_changes_nothing(self) -> None:
        save = self.save
        for args, message in (((0, 0), "two different clubs"), ((0, 3), "not one of the 3 league clubs"),
                              ((-1, 1), "not one of the 3 league clubs"), ((0, "x"), "not one of the 3 league clubs"),
                              ((1.0, 2), "not one of the 3 league clubs")):
            with self.assertRaisesRegex(fs.FranchiseSaveError, message):
                save.swap_head_coaches(*args)
            self.assertEqual(save.to_bytes(), self.payload)
        shared = fs.FranchiseSave(synthetic_staff_franchise(shared_record=True))
        before = shared.to_bytes()
        with self.assertRaisesRegex(fs.FranchiseSaveError, "IND and SF share one coach record"):
            shared.swap_head_coaches(0, 2)
        self.assertEqual(shared.to_bytes(), before)

    def test_an_exhibition_squad_pointer_is_not_moved_by_a_swap(self) -> None:
        # the three-club arena has no exhibition squads; the alias rule is proved on the real saves below
        self.assertEqual(self.save.coaches()[0].other_teams, ())


class HireTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = synthetic_staff_franchise()
        self.save = fs.FranchiseSave(self.payload)

    def test_hiring_an_unemployed_coach_fires_the_old_one_but_keeps_him_on_file(self) -> None:
        save = self.save
        receipt = save.hire_head_coach(1, 3)
        self.assertEqual(save.head_coaches(), {0: 0, 1: 3, 2: 2})
        self.assertEqual((receipt["fired"]["name"], receipt["hired"]["name"]), ("Andy Reid", "Mike Holmgren"))
        self.assertEqual([c.name for c in save.unemployed_coaches()], ["Andy Reid"])
        holmgren = save.coach_for_team(1)
        self.assertEqual((holmgren.fields["wins"], holmgren.fields["seasons_with_team"], holmgren.fields["total_seasons"]), (174, 0, 31))
        self.assertTrue(holmgren.flags & fs.COACH_FLAG_NO_NAME)
        reid = save.coaches()[1]
        self.assertEqual((reid.fields["wins"], reid.fields["seasons_with_team"], reid.flags), (279, 13, 0))   # untouched, still on file
        self.assertEqual(texts(save), texts(fs.FranchiseSave(self.payload)))                             # no text moved
        # and he can be hired back
        save.hire_head_coach(1, 1, restart=False)
        self.assertEqual(save.head_coaches(), {0: 0, 1: 1, 2: 2})
        self.assertEqual([c.name for c in save.unemployed_coaches()], ["Mike Holmgren"])

    def test_hire_refusals(self) -> None:
        save = self.save
        for args, message in (((0, 0), "already coaches IND"), ((0, 1), "already coaches ATL; swap the two clubs"),
                              ((0, 4), "empty placeholder"), ((0, 5), "empty placeholder"),
                              ((0, 6), "outside 0..5"), ((0, -1), "outside 0..5"), ((3, 3), "not one of the 3 league clubs"),
                              ((0, True), "outside|already coaches")):
            with self.assertRaisesRegex(fs.FranchiseSaveError, message):
                save.hire_head_coach(*args)
            self.assertEqual(save.to_bytes(), self.payload)

    def test_hire_changes_only_the_pointer_the_counters_and_the_flag(self) -> None:
        save = self.save
        save.hire_head_coach(2, 3)
        expected = bytearray(self.payload)
        point(expected, team_field(save, 2), coach_record(3))
        for name in fs.COACH_WITH_TEAM:
            rel, fmt = fs.COACH_FIELDS[name]
            struct.pack_into(fmt, expected, coach_record(3) + rel, 0)
        expected[coach_record(3) + fs.COACH_FLAGS] |= fs.COACH_FLAG_NO_NAME
        self.assertEqual(save.to_bytes(), bytes(expected))


class ReplaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = synthetic_staff_franchise()
        self.save = fs.FranchiseSave(self.payload)

    def region(self) -> tuple[int, int]:
        layout = self.save._coach_text_layout()
        return layout["start"], layout["writable_end"]

    def test_a_new_coach_takes_the_record_with_a_first_year_career(self) -> None:
        save = self.save
        before_texts = texts(save)
        receipt = save.replace_head_coach(2, "Dan", "Quinn", ["A defensive mind."])
        coach = save.coach_for_team(2)
        self.assertEqual((coach.first, coach.last, coach.info), ("Dan", "Quinn", ("A defensive mind.", "", "")))
        self.assertEqual(coach.index, 2)
        for name in fs.COACH_CAREER:
            self.assertEqual(coach.fields[name], 0, name)
        self.assertEqual(coach.fields["photo"], fs.COACH_NO_PHOTO)
        self.assertTrue(coach.flags & fs.COACH_FLAG_NO_NAME)
        # he keeps the seat's ratings, play-calling and sideline body
        old = fs.FranchiseSave(self.payload).coaches()[2]
        self.assertEqual((coach.ratings, coach.tendencies, coach.fields["body"], coach.fields["playcalling_run"]),
                         (old.ratings, old.tendencies, old.fields["body"], old.fields["playcalling_run"]))
        # nobody else's text changed
        after = texts(save)
        self.assertEqual([t for i, t in enumerate(after) if i != 2], [t for i, t in enumerate(before_texts) if i != 2])
        self.assertEqual((receipt["fired"]["name"], receipt["hired"]["name"]), ("Kyle Shanahan", "Dan Quinn"))
        self.assertEqual(receipt["shared_with"], [])
        self.assertEqual(save.head_coaches(), {0: 0, 1: 1, 2: 2})

    def test_only_the_coach_record_and_the_text_region_change(self) -> None:
        save = self.save
        start, end = self.region()
        save.replace_head_coach(1, "Jon", "Gruden", ["Chucky"])
        allowed = set(range(coach_record(1), coach_record(1) + fs.COACH_SIZE)) | set(range(start, end))
        for index in range(len(STAFF)):                       # the region was laid out again: every text pointer may move
            for field in fs.COACH_STRING_FIELDS:
                allowed |= set(range(coach_record(index) + field, coach_record(index) + field + 4))
        changed = changed_bytes(self.payload, save.to_bytes())
        self.assertFalse(changed - allowed)
        self.assertFalse(any(b in changed for b in range(team_field(save, 0), team_field(save, 0) + 4)))   # no club pointer moved
        ps.validate_save_edit(self.payload, save.to_bytes())                       # the roster codec still accepts it

    def test_a_new_name_that_fits_the_old_room_moves_no_pointer(self) -> None:
        save = self.save
        pointers_before = [save.rel(coach_record(i) + f) for i in range(len(STAFF)) for f in fs.COACH_STRING_FIELDS]
        receipt = save.replace_head_coach(0, "Bo", "Pelini")
        self.assertEqual(receipt["text"]["mode"], "in place")
        self.assertEqual(pointers_before, [save.rel(coach_record(i) + f) for i in range(len(STAFF)) for f in fs.COACH_STRING_FIELDS])
        self.assertEqual(save.coach_for_team(0).name, "Bo Pelini")
        self.assertEqual(save.coach_for_team(0).info, ("", "", ""))             # the 2004 biography is gone with the man

    def test_a_longer_name_lays_the_region_out_again_and_every_other_coach_keeps_his_text(self) -> None:
        save = self.save
        before_texts = texts(save)
        receipt = save.replace_head_coach(2, "Jonathan Christopher", "Hasselbeck-Longname",
                                          ["x" * 50, "y" * 40, "z" * 30])
        self.assertEqual(receipt["text"]["mode"], "region rewritten")
        after = texts(save)
        self.assertEqual([t for i, t in enumerate(after) if i != 2], [t for i, t in enumerate(before_texts) if i != 2])
        self.assertEqual(after[2], ("Jonathan Christopher", "Hasselbeck-Longname", ("x" * 50, "y" * 40, "z" * 30)))
        start, end = self.region()
        self.assertEqual((start, end - start), (STRINGS_AT, fs.COACH_STRING_REGION))
        self.assertFalse(any(save.buffer[STRINGS_AT + receipt["text"]["used"]:STRINGS_AT + fs.COACH_STRING_REGION]))
        # a second edit still works after the first one moved things
        save.replace_head_coach(0, "Bo", "Pelini")
        self.assertEqual(save.coach_for_team(0).name, "Bo Pelini")
        self.assertEqual(texts(save)[2], after[2])

    def test_edits_in_place_leave_zero_padding_that_later_edits_accept(self) -> None:
        save = self.save
        save.replace_head_coach(0, "Bo", "Pelini")                              # shorter than Bill Belichick: padding
        save.replace_head_coach(1, "Jonathan Christopher", "Hasselbeck-Longname", ["x" * 50])
        self.assertEqual(save.coach_for_team(0).name, "Bo Pelini")
        self.assertEqual(save.coach_for_team(1).first, "Jonathan Christopher")

    def test_refusals_say_why_and_change_nothing(self) -> None:
        save = self.save
        cases = (
            ((0, "", "Quinn"), "type the coach's first name"),
            ((0, "Dan", "   "), "type the coach's last name"),
            ((0, "D" * 25, "Quinn"), "longer than 24"),
            ((0, "Dan", "Q" * 25), "longer than 24"),
            ((0, "Dan", "Quinn", ["b" * 53]), "longer than 52"),
            ((0, "Dán", "Quinn"), "character the game cannot show"),
            ((0, "Dan", "Quinn—"), "character the game cannot show"),
            ((0, "Da\x00n", "Quinn"), "character the game cannot show"),
            ((3, "Dan", "Quinn"), "not one of the 3 league clubs"),
        )
        for args, message in cases:
            with self.assertRaisesRegex(fs.FranchiseSaveError, message):
                save.replace_head_coach(*args)
            self.assertEqual(save.to_bytes(), self.payload, args)

    def test_a_save_that_keeps_its_coach_text_in_pieces_is_refused_but_swaps_still_work(self) -> None:
        for variant, message in ((dict(contiguous=False), "more than one place"), (dict(shared_text=True), "used by another record")):
            payload = synthetic_staff_franchise(**variant)
            save = fs.FranchiseSave(payload)
            with self.assertRaisesRegex(fs.FranchiseSaveError, message):
                save.replace_head_coach(0, "Dan", "Quinn")
            self.assertEqual(save.to_bytes(), payload)
            save.swap_head_coaches(0, 1)
            self.assertEqual(save.coach_for_team(0).name, "Andy Reid")

    def test_a_full_region_refuses_text_it_cannot_hold(self) -> None:
        payload = synthetic_staff_franchise(free_tail=False)
        save = fs.FranchiseSave(payload)
        with self.assertRaisesRegex(fs.FranchiseSaveError, r"needs [\d,]+ bytes and this save has room for [\d,]+"):
            save.replace_head_coach(2, "Jonathan Christopher", "Hasselbeck-Longname", ["x" * 50, "y" * 40, "z" * 30])
        self.assertEqual(save.to_bytes(), payload)
        save.replace_head_coach(2, "Dan", "Quinn")                              # what fits still goes in
        self.assertEqual(save.coach_for_team(2).name, "Dan Quinn")

    def test_two_clubs_on_one_record_cannot_be_renamed_together(self) -> None:
        payload = synthetic_staff_franchise(shared_record=True)
        save = fs.FranchiseSave(payload)
        with self.assertRaisesRegex(fs.FranchiseSaveError, "IND, SF lead with the same coach record"):
            save.replace_head_coach(0, "Dan", "Quinn")
        self.assertEqual(save.to_bytes(), payload)

    def test_a_placeholder_seat_has_nobody_to_fire(self) -> None:
        payload = bytearray(synthetic_staff_franchise())
        save = fs.FranchiseSave(bytes(payload))
        point(payload, team_field(save, 2), coach_record(4))
        save = fs.FranchiseSave(bytes(payload))
        with self.assertRaisesRegex(fs.FranchiseSaveError, "empty placeholder; nobody is being fired"):
            save.replace_head_coach(2, "Dan", "Quinn")


class RoundTripTests(unittest.TestCase):
    def test_a_signed_copy_carries_the_swap_and_the_source_is_untouched(self) -> None:
        payload = synthetic_staff_franchise()
        with tempfile.TemporaryDirectory() as td:
            source = write_container(Path(td) / "source", payload)
            save = fs.FranchiseSave.load(source)
            self.assertTrue(save.container is not None and save.container.verified)
            save.swap_head_coaches(0, 2)
            target = Path(td) / "copy"
            receipt = save.write(target)
            self.assertTrue(receipt["signed"])
            back = fs.FranchiseSave.load(target)                                # load() verifies the EXTRA signature
            self.assertTrue(back.container is not None and back.container.verified)
            self.assertEqual(back.head_coaches(), {0: 2, 1: 1, 2: 0})
            self.assertEqual(back.coach_for_team(0).name, "Kyle Shanahan")
            self.assertEqual(back.to_bytes(), save.to_bytes())
            ps.validate_save(back.to_bytes())
            self.assertEqual((source / "53450030" / "0001" / "SAVEGAME.DAT").read_bytes(), payload)
            # every byte but the swap's own is the source's
            allowed = {team_field(back, 0) + k for k in range(4)} | {team_field(back, 2) + k for k in range(4)}
            for index in (0, 2):
                allowed |= {coach_record(index) + fs.COACH_FLAGS}
                for name in fs.COACH_WITH_TEAM:
                    rel, fmt = fs.COACH_FIELDS[name]
                    allowed |= {coach_record(index) + rel + k for k in range(struct.calcsize(fmt))}
            self.assertFalse(changed_bytes(payload, back.to_bytes()) - allowed)

    def test_a_replaced_coach_survives_a_signed_round_trip(self) -> None:
        payload = synthetic_staff_franchise()
        with tempfile.TemporaryDirectory() as td:
            source = write_container(Path(td) / "source", payload)
            save = fs.FranchiseSave.load(source)
            save.replace_head_coach(1, "Dan", "Quinn", ["Defence first."])
            save.hire_head_coach(0, 3)
            save.write(Path(td) / "copy")
            back = fs.FranchiseSave.load(Path(td) / "copy")
            self.assertEqual((back.coach_for_team(1).name, back.coach_for_team(1).info[0]), ("Dan Quinn", "Defence first."))
            self.assertEqual(back.coach_for_team(0).name, "Mike Holmgren")
            self.assertEqual([c.name for c in back.unemployed_coaches()], ["Bill Belichick"])


#: Every name of the ten formation bytes and the record offset it reads and writes (c1-coachdata proved the layout with the
#: game's own routine: +0x83..+0x87 are the formation shares of RUN calls, +0x88..+0x8C of PASS calls, five classes each).
FORMATION_BYTES = {
    "run_gun": 0x83, "run_split_backs": 0x84, "run_i_form": 0x85, "run_one_back": 0x86, "run_no_back": 0x87,
    "pass_gun": 0x88, "pass_split_backs": 0x89, "pass_i_form": 0x8A, "pass_one_back": 0x8B, "pass_no_back": 0x8C,
}
OLD_NAMES = ("shotgun_run", "shotgun_pass", "split_back_run", "split_back_pass", "i_form_run", "i_form_pass",
             "lone_back_run", "lone_back_pass", "empty_run", "empty_pass")


class FormationBytesTests(unittest.TestCase):
    """The ten bytes at +0x83..+0x8C are two five-class distributions, run then pass, not run / pass pairs."""

    def test_each_name_is_pinned_to_its_byte(self) -> None:
        self.assertEqual(fs.COACH_TENDENCIES, tuple(FORMATION_BYTES))
        self.assertEqual((fs.COACH_TENDENCIES_OFFSET, fs.COACH_TENDENCY_COUNT), (0x83, 10))
        self.assertEqual(fs.COACH_FORMATION_CLASSES, ("gun", "split_backs", "i_form", "one_back", "no_back"))
        self.assertEqual(fs.COACH_FORMATION_GROUPS, {"formation_run": 0x83, "formation_pass": 0x88})
        for index, (name, offset) in enumerate(FORMATION_BYTES.items()):
            self.assertEqual(fs.COACH_TENDENCIES_OFFSET + index, offset, name)
        self.assertEqual(sorted(FORMATION_BYTES.values()), list(range(0x83, 0x8D)))
        for old in OLD_NAMES:                                        # Finn's alternating labels are gone
            self.assertNotIn(old, fs.COACH_TENDENCIES)

    def test_the_reader_puts_each_byte_under_its_name(self) -> None:
        payload = bytearray(synthetic_staff_franchise())
        for offset in FORMATION_BYTES.values():                      # ten different bytes in coach 0
            payload[coach_record(0) + offset] = offset - 0x40
        coach = fs.FranchiseSave(bytes(payload)).coaches()[0]
        self.assertEqual(coach.tendencies, {name: offset - 0x40 for name, offset in FORMATION_BYTES.items()})
        self.assertEqual(coach.tendencies["run_gun"], 0x43)
        self.assertEqual(coach.tendencies["pass_no_back"], 0x4C)

    def test_the_writer_changes_exactly_the_named_byte(self) -> None:
        for name, offset in FORMATION_BYTES.items():
            save = fs.FranchiseSave(synthetic_staff_franchise())
            before = save.to_bytes()
            current = save.coaches()[1].tendencies[name]
            save.set_coach_field(1, name, 77 if current != 77 else 78)
            changed = changed_bytes(before, save.to_bytes())
            self.assertEqual(changed, {coach_record(1) + offset}, name)
            self.assertEqual(save.buffer[coach_record(1) + offset], 77 if current != 77 else 78)
            with self.assertRaisesRegex(fs.FranchiseSaveError, "outside 0..100"):
                save.set_coach_field(1, name, 101)
            self.assertEqual(save.buffer[coach_record(1) + offset], 77 if current != 77 else 78)

    def test_the_old_names_are_not_fields_any_more(self) -> None:
        save = fs.FranchiseSave(synthetic_staff_franchise())
        before = save.to_bytes()
        for old in OLD_NAMES:
            with self.assertRaisesRegex(fs.FranchiseSaveError, "unknown coach field"):
                save.set_coach_field(0, old, 50)
        self.assertEqual(save.to_bytes(), before)

    def test_the_synthetic_coaches_hold_two_distributions_that_add_up_to_100(self) -> None:
        for coach in fs.FranchiseSave(synthetic_staff_franchise()).coaches()[:4]:
            self.assertEqual(sum(coach.tendencies[f"run_{c}"] for c in fs.COACH_FORMATION_CLASSES), sum(RUN_MIX))
            self.assertEqual(sum(coach.tendencies[f"pass_{c}"] for c in fs.COACH_FORMATION_CLASSES), sum(PASS_MIX))
        self.assertEqual((sum(RUN_MIX), sum(PASS_MIX)), (100, 100))

    def test_the_roster_editors_group_names_and_offsets_agree_when_c1_is_merged(self) -> None:
        groups = getattr(rr, "COACH_TENDENCY_GROUPS", None)
        if groups is None:
            self.skipTest("nfl2k5_roster_records.COACH_TENDENCY_GROUPS (job b780-c1-coachdata) is not in this tree")
        for name, offset in fs.COACH_FORMATION_GROUPS.items():
            self.assertEqual(groups[name][:2], (offset, 5), name)

    @unittest.skipUnless(FRANCHISE1.is_file() and F0.is_file(), f"private save fixtures missing under {FIXTURES}")
    def test_every_coach_the_game_ships_adds_up_to_100_in_each_set_of_five(self) -> None:
        """The evidence for the layout in the game's own data: the 32 club coaches of each of two saves."""

        for path in (F0.parents[3], FRANCHISE1.parents[3]):
            checked = 0
            for coach in fs.FranchiseSave.load(path).coaches():
                if coach.placeholder:
                    continue
                self.assertEqual(sum(coach.tendencies[f"run_{c}"] for c in fs.COACH_FORMATION_CLASSES), 100, coach.name)
                self.assertEqual(sum(coach.tendencies[f"pass_{c}"] for c in fs.COACH_FORMATION_CLASSES), 100, coach.name)
                checked += 1
            self.assertEqual(checked, 32, path)


class CommandLineTests(unittest.TestCase):
    """``python3 -m mod_editor.core.nfl2k5_franchise_save``: the same moves from a terminal, always into a new folder."""

    def run_cli(self, *argv: str) -> tuple[int, str]:
        text = io.StringIO()
        with contextlib.redirect_stdout(text):
            code = fs.main(list(argv))
        return code, text.getvalue()

    def test_list_swap_hire_and_replace_write_signed_copies_and_never_the_source(self) -> None:
        payload = synthetic_staff_franchise()
        with tempfile.TemporaryDirectory() as td:
            source = write_container(Path(td) / "source", payload)
            code, text = self.run_cli("coaches", str(source))
            self.assertEqual(code, 0)
            self.assertIn(" 0 IND  Bill Belichick", text)
            self.assertIn("no club  #3  Mike Holmgren", text)
            code, text = self.run_cli("swap", str(source), str(Path(td) / "a"), "IND", "sf")
            self.assertEqual((code, "swap_head_coaches: done" in text), (0, True))
            back = fs.FranchiseSave.load(Path(td) / "a")
            self.assertEqual((back.coach_for_team(0).name, back.coach_for_team(2).name), ("Kyle Shanahan", "Bill Belichick"))
            code, _text = self.run_cli("hire", str(source), str(Path(td) / "b"), "1", "3")
            self.assertEqual(code, 0)
            self.assertEqual(fs.FranchiseSave.load(Path(td) / "b").coach_for_team(1).name, "Mike Holmgren")
            code, _text = self.run_cli("replace", str(source), str(Path(td) / "c"), "SF", "Dan", "Quinn", "A defensive mind.")
            self.assertEqual(code, 0)
            self.assertEqual(fs.FranchiseSave.load(Path(td) / "c").coach_for_team(2).info[0], "A defensive mind.")
            self.assertEqual((source / "53450030" / "0001" / "SAVEGAME.DAT").read_bytes(), payload)

    def test_refusals_print_a_reason_and_return_one(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            source = write_container(Path(td) / "source", synthetic_staff_franchise())
            for argv, message in ((("swap", str(source), str(Path(td) / "x"), "IND", "XYZ"), "not a club in this save"),
                                  (("swap", str(source), str(Path(td) / "x"), "IND"), "swap needs two clubs"),
                                  (("hire", str(source), str(Path(td) / "x"), "IND", "4"), "empty placeholder"),
                                  (("replace", str(source), str(Path(td) / "x"), "IND", "Dan"), "replace needs a club"),
                                  (("swap", str(source)), "give the folder")):
                code, text = self.run_cli(*argv)
                self.assertEqual(code, 1, argv)
                self.assertIn(message, text)
            self.assertFalse((Path(td) / "x").exists())
            first, _ = self.run_cli("swap", str(source), str(Path(td) / "once"), "IND", "SF")
            again, text = self.run_cli("swap", str(source), str(Path(td) / "once"), "IND", "SF")
            self.assertEqual((first, again), (0, 1))
            self.assertIn("exists", text)


@unittest.skipUnless(FRANCHISE1.is_file(), f"private Franchise1 fixture missing under {FIXTURES}")
class RealFranchiseTests(unittest.TestCase):
    """The year-7 Lions franchise: 52 teams (the 32 clubs, two created slots, eighteen exhibition squads)."""

    def setUp(self) -> None:
        self.save = fs.FranchiseSave.load(FRANCHISE1.parents[3])
        self.original = self.save.to_bytes()

    def test_exhibition_squads_keep_the_record_they_borrow(self) -> None:
        save = self.save
        belichick_team = next(t for t in range(32) if save.coach_for_team(t).name == "Bill Belichick")
        borrowers = save.coach_for_team(belichick_team).other_teams
        self.assertTrue(borrowers)
        other = (belichick_team + 1) % 32
        before = {t: save.head_coach_index(t) for t in borrowers}
        save.swap_head_coaches(belichick_team, other)
        self.assertEqual({t: save.head_coach_index(t) for t in borrowers}, before)
        self.assertEqual(save.coaches()[before[borrowers[0]]].other_teams, borrowers)

    def test_a_swap_a_hire_and_a_new_coach_on_the_real_save_round_trip_signed(self) -> None:
        save = self.save
        names_before = {t: save.coach_for_team(t).name for t in range(32)}
        save.swap_head_coaches(0, 1)
        receipt = save.replace_head_coach(2, "Dan", "Quinn", ["A defensive mind."])
        self.assertEqual(receipt["text"]["mode"], "in place")
        save.replace_head_coach(3, "Jonathan Christopher", "Hasselbeck-Longname", ["x" * 30])
        with tempfile.TemporaryDirectory() as td:
            result = save.write(Path(td) / "copy")
            self.assertTrue(result["signed"])
            back = fs.FranchiseSave.load(Path(td) / "copy")
            self.assertTrue(back.container is not None and back.container.verified)
            self.assertEqual(back.coach_for_team(0).name, names_before[1])
            self.assertEqual(back.coach_for_team(1).name, names_before[0])
            self.assertEqual(back.coach_for_team(2).name, "Dan Quinn")
            self.assertEqual(back.coach_for_team(3).first, "Jonathan Christopher")
            for team in range(4, 32):
                self.assertEqual(back.coach_for_team(team).name, names_before[team])
            ps.validate_save(back.to_bytes())
        self.assertEqual(FRANCHISE1.read_bytes(), self.original)                 # the fixture is untouched

    def test_the_other_coaches_text_survives_a_region_rewrite(self) -> None:
        save = self.save
        before = texts(save)
        save.replace_head_coach(3, "Jonathan Christopher", "Hasselbeck-Longname", ["x" * 30, "y" * 20])
        after = texts(save)
        self.assertEqual([t for i, t in enumerate(after) if i != 3], [t for i, t in enumerate(before) if i != 3])


@unittest.skipUnless(F0.is_file(), f"private 8007Fran fixture missing under {FIXTURES}")
class RealFinnSaveTests(unittest.TestCase):
    """Finn's 2004 save keeps its coach text in pieces: swaps work, renames say why not."""

    def test_swaps_work_and_a_rename_is_refused_with_the_reason(self) -> None:
        save = fs.FranchiseSave.load(F0.parents[3])
        original = save.to_bytes()
        with self.assertRaisesRegex(fs.FranchiseSaveError, "more than one place"):
            save.replace_head_coach(2, "Dan", "Quinn")
        self.assertEqual(save.to_bytes(), original)
        names = (save.coach_for_team(21).name, save.coach_for_team(0).name)
        save.swap_head_coaches(21, 0)
        self.assertEqual((save.coach_for_team(21).name, save.coach_for_team(0).name), names[::-1])
        self.assertTrue(save.coach_for_team(0).other_teams)                         # the exhibition squads stay on his record
        with tempfile.TemporaryDirectory() as td:
            save.write(Path(td) / "copy")
            back = fs.FranchiseSave.load(Path(td) / "copy")
            self.assertEqual(back.coach_for_team(21).name, names[1])
        self.assertEqual(F0.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()

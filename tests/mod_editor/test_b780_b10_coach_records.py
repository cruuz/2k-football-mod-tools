"""b780 b10-profile: Franchise > Upgrade copies the 2026 coach ratings, play-calling habits and announcer line.

c1-coachdata puts every head coach's own ratings, tendencies and the generic announcer line into the disc's coach records.
A franchise keeps its own copy of those records, so it would keep the old ones (a 2004 coach's numbers under a 2026 name).
``sync_coach_records`` copies them by full name, per rating, per tendency group and for the announcer line, and only where
the franchise still holds the value the older discs had; a value changed in the Studio or the game stays.  These tests cover
the step on synthetic franchises (every rule), the shipped baseline of the older discs' values, the narrowed coach sync
(the flags byte is the records step's), the preview text, and, when the environment names them, real files:

  B780_B10_DISC_ROST   the released v0.8 disc's roster body (the older discs' values)
  B780_B10_V07         a real v0.7 franchise save (SAVEGAME.DAT), B780_B10_RESAVED the same franchise saved by the v0.8 game
  B780_B10_C1_ROST     that roster after c1-coachdata's own writer (apply_coach_records) gave the 32 coaches their 2026 records
  B780_B10_C1_DATA     c1's data/nfl2k5_coaches_2026.json

Real files are only read; nothing is written outside a temporary directory.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_franchise_upgrade as up  # noqa: E402
from mod_editor.core import nfl2k5_franchise_upgrade_io as service  # noqa: E402
from mod_editor.core import nfl2k5_save_rost as sr  # noqa: E402
from tests.mod_editor.test_franchise_upgrade import disc_roster, fixture, signed_folder, with_coaches  # noqa: E402

REAL_V07 = Path(os.environ.get("B780_B10_V07", ""))
REAL_RESAVED = Path(os.environ.get("B780_B10_RESAVED", ""))
REAL_DISC_ROST = Path(os.environ.get("B780_B10_DISC_ROST", ""))
REAL_C1_ROST = Path(os.environ.get("B780_B10_C1_ROST", ""))
REAL_C1_DATA = Path(os.environ.get("B780_B10_C1_DATA", ""))

STRIDE = 0xA8
#: every byte the step may write: the ratings, the tendency groups and the announcer line
DECLARED = ([(up.COACH_RATINGS_AT, up.COACH_RATINGS_AT + len(up.COACH_RATING_NAMES))]
            + [(at, at + count) for at, count in up.COACH_TENDENCY_GROUPS.values()] + [(up.COACH_FLAGS_AT, up.COACH_FLAGS_AT + 1)])
#: bytes of a coach record the 2026 data does not author; the step must never read or write them
UNAUTHORED = (0x14, 0x15, 0x16, 0x17, 0x3C, 0x3E, 0x71, 0x75, 0x7A, 0x7D, 0xA3, 0xA4, 0xA6, 0xA7)


def old_ratings(seed):
    return [40 + (seed * 7 + k * 3) % 50 for k in range(len(up.COACH_RATING_NAMES))]


def new_ratings(seed):
    old = old_ratings(seed)
    return [v if k % 5 == 0 else v + 7 for k, v in enumerate(old)]           # every fifth rating is the same on the new disc


def old_groups(seed):
    return {name: [(seed * 13 + k * 5 + len(name)) % 60 + 5 for k in range(count)]
            for name, (_at, count) in up.COACH_TENDENCY_GROUPS.items()}


def new_groups(seed):
    old = old_groups(seed)
    return {name: values if name == "run_share" else [v + 1 for v in values] for name, values in old.items()}


def write_record(buf, at, ratings, groups, generic, flags=0):
    for k, value in enumerate(ratings):
        buf[at + up.COACH_RATINGS_AT + k] = value
    for name, (off, count) in up.COACH_TENDENCY_GROUPS.items():
        buf[at + off:at + off + count] = bytes(groups[name])
    buf[at + up.COACH_FLAGS_AT] = flags | (up.COACH_FLAG_GENERIC if generic else 0)


def coach_table(payload, **decode):
    document = sr.decode(payload, **decode)
    table = document.tables["coaches"]
    return table.offset


def save_with(names, values):
    """A synthetic franchise whose coach table holds ``names`` with the (ratings, groups, generic) in ``values``."""
    payload = bytearray(with_coaches(fixture()[0], [(first, last, 10 + i, 7000 + i) for i, (first, last) in enumerate(names)]))
    for i, (ratings, groups, generic) in enumerate(values):
        write_record(payload, coach_table(bytes(payload)) + i * STRIDE, ratings, groups, generic)
    return bytes(payload)


def disc_with(names, values):
    body = bytearray(disc_roster(with_coaches(fixture()[0], [(first, last, 20 + i, 8000 + i) for i, (first, last) in enumerate(names)])))
    start = coach_table(bytes(body), preamble=0, reference_year=2026)
    for i, (ratings, groups, generic) in enumerate(values):
        write_record(body, start + i * STRIDE, ratings, groups, generic)
    return bytes(body)


ANN, BEN, CY, DEE, EVE = ("Ann", "One"), ("Ben", "Two"), ("Cy", "Three"), ("Dee", "Four"), ("Eve", "Five")


def old(seed):
    return old_ratings(seed), old_groups(seed), False


def new(seed):
    return new_ratings(seed), new_groups(seed), True


def baseline():
    """The older discs' values for Ann, Ben and Cy (not Dee: she is a coach the older discs did not have)."""
    older = disc_with([ANN, BEN, CY], [old(1), old(2), old(3)])
    return up.parse_coach_record_baseline(up.coach_record_baseline_from_rost(older), "synthetic")


def spans(record):
    return [(record + a, record + b) for a, b in DECLARED]


def differing(before, after):
    return [i for i, (a, b) in enumerate(zip(before, after)) if a != b]


class StepTests(unittest.TestCase):
    """A save with Ann, Ben, Cy and Dee against a disc with Ann, Ben, Dee and Eve."""

    @classmethod
    def setUpClass(cls):
        cls.saved = save_with([ANN, BEN, CY, DEE], [old(1), old(2), old(3), old(4)])
        cls.disc = disc_with([ANN, BEN, DEE, EVE], [new(1), new(2), new(4), new(5)])
        cls.baseline = baseline()
        cls.table = coach_table(cls.saved)

    def record(self, index):
        return self.table + index * STRIDE

    def test_the_fixture_is_the_old_state_and_the_disc_is_the_new_one(self):
        self.assertNotEqual(old_ratings(1), new_ratings(1))
        self.assertEqual(old_groups(1)["run_share"], new_groups(1)["run_share"])         # one group the disc leaves alone
        self.assertEqual(sorted(self.baseline["coaches"]), sorted([ANN, BEN, CY]))
        self.assertEqual(self.baseline["coaches"][ANN]["announcer"], "named")

    def test_old_values_are_replaced_by_name_and_only_the_declared_bytes_move(self):
        out, step = up.sync_coach_records(self.saved, self.disc, self.baseline)
        self.assertEqual(len(out), len(self.saved))
        allowed = {i for index in (0, 1) for lo, hi in spans(self.record(index)) for i in range(lo, hi)}
        self.assertLessEqual(set(differing(self.saved, out)), allowed)
        for index, seed in ((0, 1), (1, 2)):
            at = self.record(index)
            self.assertEqual(list(out[at + up.COACH_RATINGS_AT:at + up.COACH_RATINGS_AT + 23]), new_ratings(seed))
            for name, (off, count) in up.COACH_TENDENCY_GROUPS.items():
                self.assertEqual(list(out[at + off:at + off + count]), new_groups(seed)[name], name)
            self.assertTrue(out[at + up.COACH_FLAGS_AT] & up.COACH_FLAG_GENERIC)
        # Cy is not on the disc and Dee is not in the baseline: both stay exactly as they were
        for index in (2, 3):
            self.assertEqual(out[self.record(index):self.record(index) + STRIDE],
                             self.saved[self.record(index):self.record(index) + STRIDE])
        self.assertEqual((step["coaches_changed"], step["fields_kept"], step["reason"]), (2, 0, ""))
        self.assertEqual([c["coach"] for c in step["unmatched_preserved"]], ["Cy Three"])
        self.assertEqual([c["coach"] for c in step["no_baseline_preserved"]], ["Dee Four"])
        self.assertTrue(step["outside_declared_fields_identical"])
        self.assertEqual(step["changed_bytes"], len(differing(self.saved, out)))

    def test_the_counts_follow_what_the_disc_really_changes(self):
        _out, step = up.sync_coach_records(self.saved, self.disc, self.baseline)
        ratings = sum(1 for seed in (1, 2) for a, b in zip(old_ratings(seed), new_ratings(seed)) if a != b)
        groups = sum(1 for seed in (1, 2) for name in up.COACH_TENDENCY_GROUPS if old_groups(seed)[name] != new_groups(seed)[name])
        kinds = [c["field"].split(".")[0] for c in step["changes"]]
        self.assertEqual((kinds.count("ratings"), kinds.count("tendencies"), kinds.count("announcer")), (ratings, groups, 2))
        first = step["changes"][0]
        # the first rating is one the disc leaves alone (every fifth is the same), so the first change is the second rating
        self.assertEqual((first["coach"], first["field"], first["before"], first["after"]),
                         ("Ann One", "ratings.offense", old_ratings(1)[1], new_ratings(1)[1]))
        group = next(c for c in step["changes"] if c["field"] == "tendencies.run_lane" and c["coach"] == "Ann One")
        self.assertEqual((group["before"], group["after"]), (old_groups(1)["run_lane"], new_groups(1)["run_lane"]))
        self.assertEqual(group["offset"], self.record(0) + up.COACH_TENDENCY_GROUPS["run_lane"][0])
        announcer = next(c for c in step["changes"] if c["field"] == "announcer")
        self.assertEqual((announcer["before"], announcer["after"]), ("named", "generic"))

    def test_a_value_the_franchise_changed_is_kept_and_listed(self):
        edited = bytearray(self.saved)
        at = self.record(0)
        edited[at + up.COACH_RATINGS_AT + 3] = 99                                # Ann's pass_for: neither old nor new
        lane = at + up.COACH_TENDENCY_GROUPS["run_lane"][0]
        edited[lane + 2] = 7                                                     # one cell of Ann's run lanes
        both = self.record(1) + up.COACH_TENDENCY_GROUPS["formation_pass"][0]    # Ben already has the disc's formation_pass
        edited[both:both + 5] = bytes(new_groups(2)["formation_pass"])
        out, step = up.sync_coach_records(bytes(edited), self.disc, self.baseline)
        self.assertEqual(out[at + up.COACH_RATINGS_AT + 3], 99)
        self.assertEqual(list(out[lane:lane + 5]), list(edited[lane:lane + 5]))     # the whole group stays, not just the cell
        kept = {(k["coach"], k["field"]): k for k in step["kept"]}
        self.assertEqual(set(kept), {("Ann One", "ratings.pass_for"), ("Ann One", "tendencies.run_lane")})
        self.assertEqual(kept[("Ann One", "ratings.pass_for")]["franchise"], [99])
        self.assertEqual(kept[("Ann One", "ratings.pass_for")]["older_discs"], [old_ratings(1)[3]])
        self.assertEqual(kept[("Ann One", "ratings.pass_for")]["disc"], [new_ratings(1)[3]])
        self.assertEqual(kept[("Ann One", "tendencies.run_lane")]["franchise"][2], 7)
        self.assertEqual(step["fields_kept"], 2)
        self.assertEqual(step["already_current"], 1)                                # Ben's formation_pass
        self.assertFalse(any(c["coach"] == "Ann One" and c["field"] in ("ratings.pass_for", "tendencies.run_lane")
                             for c in step["changes"]))
        # everything else of Ann's still took the disc's value
        self.assertEqual(out[at + up.COACH_RATINGS_AT + 2], new_ratings(1)[2])

    def test_a_franchise_that_changed_everything_keeps_everything(self):
        edited = bytearray(self.saved)
        at = self.record(0)
        for k in range(23):
            edited[at + up.COACH_RATINGS_AT + k] = 99
        for name, (off, count) in up.COACH_TENDENCY_GROUPS.items():
            edited[at + off:at + off + count] = bytes([7]) * count
        edited[at + up.COACH_FLAGS_AT] = up.COACH_FLAG_GENERIC                    # the announcer line is a two-state switch
        out, step = up.sync_coach_records(bytes(edited), self.disc, self.baseline)
        self.assertEqual(out[at:at + STRIDE], bytes(edited[at:at + STRIDE]))
        self.assertEqual({c["coach"] for c in step["changes"]}, {"Ben Two"})
        self.assertGreater(step["fields_kept"], 20)

    def test_when_every_value_is_the_franchises_own_nothing_changes_and_the_reason_says_so(self):
        # a franchise whose "Ann One" is another coach's record (a save made before the 2026 names): not the older discs'
        # numbers, so none of them is replaced; this is what an old retail-named franchise's "Andy Reid" looks like
        other = save_with([ANN, BEN], [old(7), old(8)])
        out, step = up.sync_coach_records(other, self.disc, self.baseline)
        at = coach_table(other)
        flags = {at + up.COACH_FLAGS_AT, at + STRIDE + up.COACH_FLAGS_AT}
        # only the announcer line (a two-state switch whose old state it holds) is replaced; every rating and group is kept
        self.assertEqual({c["field"] for c in step["changes"]}, {"announcer"})
        self.assertEqual(set(differing(other, out)), flags)
        self.assertGreater(step["fields_kept"], 40)
        fully = bytearray(other)
        for index in (0, 1):
            fully[at + index * STRIDE + up.COACH_FLAGS_AT] = up.COACH_FLAG_GENERIC       # and the line is already on
        out, step = up.sync_coach_records(bytes(fully), self.disc, self.baseline)
        self.assertEqual((out, step["changes"]), (bytes(fully), []))
        self.assertIn("so all are kept", step["reason"])

    def test_the_announcer_line_changes_only_its_own_bit(self):
        edited = bytearray(self.saved)
        at = self.record(0)
        edited[at + up.COACH_FLAGS_AT] = 0x84                                      # other flag bits the game or a tool set
        out, _step = up.sync_coach_records(bytes(edited), self.disc, self.baseline)
        self.assertEqual(out[at + up.COACH_FLAGS_AT], 0x86)
        # the other way: the older discs had the line on and the disc turns it off
        flipped = {**self.baseline["coaches"], ANN: {**self.baseline["coaches"][ANN], "announcer": "generic"}}
        silent_disc = bytearray(self.disc)
        disc_at = coach_table(self.disc, preamble=0, reference_year=2026)
        silent_disc[disc_at + up.COACH_FLAGS_AT] = 0x04
        edited[at + up.COACH_FLAGS_AT] = 0x86
        out, step = up.sync_coach_records(bytes(edited), bytes(silent_disc), {"sha256": "", "coaches": flipped})
        self.assertEqual(out[at + up.COACH_FLAGS_AT], 0x84)
        self.assertIn(("Ann One", "named"), {(c["coach"], c["after"]) for c in step["changes"] if c["field"] == "announcer"})

    def test_a_second_run_changes_nothing(self):
        once, first = up.sync_coach_records(self.saved, self.disc, self.baseline)
        twice, second = up.sync_coach_records(once, self.disc, self.baseline)
        self.assertEqual(twice, once)
        self.assertEqual(second["changes"], [])
        self.assertEqual(second["already_current"], len(first["changes"]))
        self.assertEqual(second["reason"], "every coach already has this disc's values")

    def test_a_disc_without_new_coach_data_changes_nothing_and_says_so(self):
        older = disc_with([ANN, BEN], [old(1), old(2)])
        out, step = up.sync_coach_records(self.saved, older, self.baseline)
        self.assertEqual(out, self.saved)
        self.assertEqual(step["changes"], [])
        self.assertIn("no 2026 coach data", step["reason"])

    def test_bytes_the_data_does_not_author_are_never_touched(self):
        saved, disc = bytearray(self.saved), bytearray(self.disc)
        disc_at = coach_table(self.disc, preamble=0, reference_year=2026)
        for rel in UNAUTHORED:
            saved[self.table + rel] = 0xA1
            disc[disc_at + rel] = 0x5C
            saved[self.record(1) + rel] = 0xA2
            disc[disc_at + STRIDE + rel] = 0x5D
        out, _step = up.sync_coach_records(bytes(saved), bytes(disc), self.baseline)
        for rel in UNAUTHORED:
            self.assertEqual(out[self.table + rel], 0xA1, hex(rel))
            self.assertEqual(out[self.record(1) + rel], 0xA2, hex(rel))
        # the name pointers, body id and portrait are the coach sync's, not this step's (and the flags byte is only touched
        # in its announcer bit)
        flags = self.table + up.COACH_FLAGS_AT
        self.assertEqual(out[self.table:flags], bytes(saved[self.table:flags]))
        self.assertEqual(out[flags + 1:self.table + 0x42], bytes(saved[flags + 1:self.table + 0x42]))

    def test_no_matching_coach_refuses(self):
        strangers = disc_with([("Zed", "Nine")], [new(9)])
        with self.assertRaisesRegex(up.UpgradeRefused, "no matching coach identities"):
            up.sync_coach_records(self.saved, strangers, self.baseline)

    def test_duplicate_named_coaches_refuse(self):
        twins = save_with([ANN, ANN], [old(1), old(1)])
        with self.assertRaisesRegex(up.UpgradeRefused, "duplicate coach"):
            up.sync_coach_records(twins, self.disc, self.baseline)

    def test_a_disc_that_is_not_a_roster_refuses(self):
        with self.assertRaises(ValueError):
            up.sync_coach_records(self.saved, self.saved, self.baseline)

    def test_the_default_baseline_is_the_shipped_file(self):
        shipped = up.coach_record_baseline()
        with patch.object(up, "coach_record_baseline", return_value=shipped) as load:
            up.sync_coach_records(self.saved, self.disc)
        load.assert_called_once_with()


class CoachSyncFlagsTests(unittest.TestCase):
    """The coach sync copies the body id and portrait only; the byte after the body id is the records step's."""

    def test_the_coach_sync_never_writes_the_flags_byte(self):
        saved = save_with([ANN, BEN], [old(1), old(2)])
        disc = bytearray(disc_with([ANN, BEN], [new(1), new(2)]))            # flags 0x02 on the disc, 0x00 in the save
        out, step = up.sync_coaches(saved, bytes(disc))
        table = coach_table(saved)
        for index in (0, 1):
            at = table + index * STRIDE
            self.assertEqual(out[at + up.COACH_FLAGS_AT], 0)
            self.assertEqual(out[at + 0x1B], 0)
        self.assertEqual([c["field"] for c in step["changes"]], ["body_id", "portrait_id"] * 2)
        self.assertEqual([c["after"] for c in step["changes"] if c["field"] == "body_id"], [20, 21])   # small ids, no flag bits

    def test_a_flag_the_franchise_has_is_not_cleared_by_the_coach_sync(self):
        saved = bytearray(save_with([ANN], [new(1)]))
        disc = disc_with([ANN], [old(1)])
        out, _step = up.sync_coaches(bytes(saved), disc)
        self.assertTrue(out[coach_table(bytes(saved)) + up.COACH_FLAGS_AT] & up.COACH_FLAG_GENERIC)

    def test_the_two_steps_together_set_the_line_once(self):
        saved = save_with([ANN, BEN], [old(1), old(2)])
        disc = disc_with([ANN, BEN], [new(1), new(2)])
        mid, _ = up.sync_coaches(saved, disc)
        out, step = up.sync_coach_records(mid, disc, baseline())
        at = coach_table(saved)
        self.assertTrue(out[at + up.COACH_FLAGS_AT] & up.COACH_FLAG_GENERIC)
        self.assertEqual(len([c for c in step["changes"] if c["field"] == "announcer"]), 2)


class BaselineFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = up.COACH_RECORD_BASELINE.read_text(encoding="utf-8")
        cls.data = json.loads(cls.text)

    def test_the_shipped_file_loads_and_names_the_32_head_coaches(self):
        loaded = up.coach_record_baseline()
        self.assertEqual(len(loaded["coaches"]), 32)
        self.assertIn(("Andy", "Reid"), loaded["coaches"])
        self.assertEqual({c["announcer"] for c in loaded["coaches"].values()}, {"named"})
        self.assertEqual(len(loaded["sha256"]), 64)

    def test_every_coach_has_every_field_in_the_games_range(self):
        for entry in self.data["coaches"]:
            self.assertEqual(len(entry["ratings"]), 23)
            self.assertTrue(all(0 <= v <= 99 for v in entry["ratings"]), entry["last"])
            for name, (_at, count) in up.COACH_TENDENCY_GROUPS.items():
                values = entry["tendencies"][name]
                self.assertEqual(len(values), count, (entry["last"], name))
                self.assertTrue(all(0 <= v <= 100 for v in values), (entry["last"], name))

    def test_the_distributions_add_up_to_100(self):
        for entry in self.data["coaches"]:
            for name in ("run_lane", "formation_run", "formation_pass"):
                self.assertEqual(sum(entry["tendencies"][name]), 100, (entry["last"], name))

    def test_the_file_is_its_own_canonical_text(self):
        rebuilt = up.coach_record_baseline_text(self.data)
        self.assertEqual(rebuilt, self.text)
        self.assertNotIn("—", self.text)                                  # no em dashes in shipped text

    def test_a_damaged_or_foreign_baseline_refuses_instead_of_guessing(self):
        def broken(change):
            data = json.loads(self.text)
            change(data)
            return data
        cases = {
            "unknown": lambda d: d.update(schema="other/v1"),
            "another layout": lambda d: d["layout"]["tendencies"].update(run_lane=4),
            "short ratings": lambda d: d["coaches"][0].update(ratings=d["coaches"][0]["ratings"][:-1]),
            "a missing group": lambda d: d["coaches"][0]["tendencies"].pop("run_lane"),
            "a long group": lambda d: d["coaches"][0]["tendencies"].update(run_lane=[20] * 6),
            "a byte out of range": lambda d: d["coaches"][0]["ratings"].__setitem__(0, 300),
            "a repeated coach": lambda d: d["coaches"].append(dict(d["coaches"][0])),
            "an unknown announcer": lambda d: d["coaches"][0].update(announcer="loud"),
            "no coaches": lambda d: d.update(coaches=[]),
            "a nameless coach": lambda d: d["coaches"][0].update(first=""),
        }
        for label, change in cases.items():
            with self.subTest(label), self.assertRaises(up.UpgradeRefused):
                up.parse_coach_record_baseline(broken(change))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "baseline.json"
            path.write_text("{ not json", encoding="utf-8")
            with self.assertRaisesRegex(up.UpgradeRefused, "cannot be read"):
                up.coach_record_baseline(path)

    def test_the_layout_is_c1s_when_the_writer_is_merged(self):
        from mod_editor.core import nfl2k5_roster_records as rr
        if not hasattr(rr, "COACH_TENDENCY_GROUPS"):
            self.skipTest("c1-coachdata's coach record layout is not merged into this branch yet")
        self.assertEqual({name: (at, count) for name, (at, count, _kind) in rr.COACH_TENDENCY_GROUPS.items()},
                         up.COACH_TENDENCY_GROUPS)
        self.assertEqual((rr.COACH_RATINGS_AT, tuple(rr.COACH_RATING_NAMES)), (up.COACH_RATINGS_AT, up.COACH_RATING_NAMES))
        self.assertEqual((rr.COACH_FLAGS_AT, rr.COACH_FLAG_GENERIC), (up.COACH_FLAGS_AT, up.COACH_FLAG_GENERIC))


class WiringTests(unittest.TestCase):
    """The step through ``plan_upgrade`` on a signed synthetic folder (the full Studio validation is patched out, as the
    other synthetic Upgrade tests do: the synthetic arena has no coaches)."""

    STEP_NAMES = {"upgrade_years": "years", "sync_playbooks": "playbooks", "upgrade_team_history": "team_history",
                  "sync_coaches": "coach_sync", "sync_coach_pool": "coach_pool", "sync_hair_styles": "hair_styles",
                  "sync_honors": "honors",
                  "sync_rookie_templates": "rookie_templates", "sync_free_agents": "free_agents",
                  "sync_champions": "champions", "sync_game_settings": "game_settings"}

    def plan(self, command, **kw):
        saved = save_with([ANN, BEN], [old(1), old(2)])
        disc = disc_with([ANN, BEN], [new(1), new(2)])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = signed_folder(root / "source", saved)
            image = root / "disc.iso"
            image.write_bytes(b"synthetic disc fingerprint")
            cohort = root / "cohort.json"
            cohort.write_text('{"schema": "stub"}', encoding="utf-8")
            kw.setdefault("cohort_path", cohort)
            with patch.object(service, "load_disc", return_value=(disc, {})), \
                    patch.object(service, "load_disc_defaults", return_value={"state": "retail", "values": {}}), \
                    patch.object(up, "validate_save", return_value={}), \
                    patch.object(up, "coach_record_baseline", return_value=baseline()):
                return service.plan_upgrade(source, image, command=command, **kw), saved

    def test_coach_records_is_a_command_of_its_own_and_the_cli_knows_it(self):
        self.assertIn("coach-records", service.COMMANDS)
        import tools.nfl2k5_franchise_upgrade as cli
        self.assertEqual(cli.COMMANDS, service.COMMANDS)
        plan, saved = self.plan("coach-records")
        self.assertEqual([s["operation"] for s in plan.receipt["steps"]], ["coach_records"])
        step = plan.receipt["steps"][0]
        self.assertEqual((step["coaches_changed"], plan.receipt["changed_fields"]), (2, len(step["changes"])))
        self.assertEqual(step["after_sha256"], up.sha(plan.payload))
        self.assertEqual(step["baseline_sha256"], "synthetic")
        self.assertEqual(plan.receipt["output_extra_sha256"], up.sha(service.rr.sign_save(plan.payload)))
        self.assertEqual(plan.container.savegame, saved)                                 # the input is only read

    def test_the_preview_says_what_the_step_did(self):
        from mod_editor.gui.franchise_upgrade_dialog_qt import preview_text
        plan, _saved = self.plan("coach-records")
        plan.receipt["validation"] = {"after": {"findings": []}}
        self.assertIn("Coach ratings and play-calling from the disc: 2 coaches updated", preview_text(plan))

    def test_team_evidence_is_refused_for_it(self):
        with self.assertRaisesRegex(up.UpgradeRefused, "TEAM evidence"):
            self.plan("coach-records", team_history_path=Path("evidence.json"))

    def test_upgrade_runs_it_right_after_the_coach_sync_and_before_the_hair_styles(self):
        def stub(name):
            return lambda payload, *args, **kw: (payload, {"operation": name, "changes": []})
        patches = [patch.object(up, attr, stub(op)) for attr, op in self.STEP_NAMES.items()]
        patches.append(patch.object(up, "check_career_block", lambda before, after: None))
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        plan, _saved = self.plan("upgrade", game_defaults=False)
        operations = [s["operation"] for s in plan.receipt["steps"]]
        self.assertEqual(operations.count("coach_records"), 1)
        # b780-int: c6-carousel's hiring-pool copy runs inside the coach sync command, right after the body/portrait sync
        self.assertEqual(operations[operations.index("coach_sync") + 1], "coach_pool")
        self.assertEqual(operations[operations.index("coach_pool") + 1], "coach_records")
        self.assertEqual(operations[operations.index("coach_records") + 1], "hair_styles")


class DialogTextTests(unittest.TestCase):
    @staticmethod
    def step(**kw):
        base = {"operation": "coach_records", "changes": [], "kept": [], "fields_kept": 0, "coaches_changed": 0,
                "no_baseline_preserved": [], "reason": "every coach already has this disc's values"}
        return {**base, **kw}

    def test_nothing_changed_says_why(self):
        from mod_editor.gui.franchise_upgrade_dialog_qt import coach_records_lines
        lines = coach_records_lines(self.step())
        self.assertEqual(lines, ["Coach ratings and play-calling: not changed (every coach already has this disc's values)."])

    def test_the_counts_and_the_kept_values_are_in_plain_words(self):
        from mod_editor.gui.franchise_upgrade_dialog_qt import coach_records_lines
        changes = ([{"field": "ratings.overall"}] * 5 + [{"field": "tendencies.run_lane"}] * 3 + [{"field": "announcer"}] * 2)
        lines = coach_records_lines(self.step(changes=changes, coaches_changed=2, fields_kept=4))
        self.assertEqual(lines, ["Coach ratings and play-calling from the disc: 2 coaches updated "
                                 "(5 ratings, 3 play-calling groups, 2 announcer lines); "
                                 "4 values that differ from the older discs' defaults are kept as they are."])

    def test_coaches_without_older_values_are_named(self):
        from mod_editor.gui.franchise_upgrade_dialog_qt import coach_records_lines
        rows = [{"coach": f"Coach {n}"} for n in range(8)]
        lines = coach_records_lines(self.step(changes=[{"field": "announcer"}], coaches_changed=1, no_baseline_preserved=rows))
        self.assertEqual(len(lines), 2)
        self.assertIn("Coach 0, Coach 1, Coach 2, Coach 3, Coach 4, Coach 5 and 2 more", lines[1])

    def test_the_preview_carries_the_step_and_has_no_em_dashes(self):
        from mod_editor.gui.franchise_upgrade_dialog_qt import preview_text
        receipt = {"steps": [self.step(changes=[{"field": "ratings.overall"}], coaches_changed=1)], "changed_fields": 1,
                   "validation": {"after": {"findings": []}}, "disc": "disc.iso", "input": "save"}
        plan = service.UpgradePlan(None, Path("disc.iso"), b"", receipt)
        text = preview_text(plan)
        self.assertIn("Coach ratings and play-calling from the disc: 1 coaches updated", text)
        self.assertNotIn("—", text)


# --- real files -----------------------------------------------------------------------------------------------------
def named_records(payload, **decode):
    document = sr.decode(payload, **decode)
    rows, _unnamed = up.coach_rows(document)
    size = document.tables["coaches"].stride
    return {key: payload[at:at + size] for key, (_index, at) in rows.items()}


def fields_of(record):
    out = {name: bytes(record[rel:rel + size]) for name, rel, size in up.coach_record_fields()}
    out["announcer"] = "generic" if record[up.COACH_FLAGS_AT] & up.COACH_FLAG_GENERIC else "named"
    return out


@unittest.skipUnless(REAL_DISC_ROST.is_file(), "the released disc's roster is not named in B780_B10_DISC_ROST")
class RealBaselineTests(unittest.TestCase):
    def test_the_shipped_baseline_is_the_released_discs_roster(self):
        data = up.coach_record_baseline_from_rost(REAL_DISC_ROST.read_bytes())
        self.assertEqual(up.coach_record_baseline_text(data), up.COACH_RECORD_BASELINE.read_text(encoding="utf-8"))

    @unittest.skipUnless(REAL_V07.is_file(), "a real v0.7 franchise save is not named in B780_B10_V07")
    def test_a_real_old_franchise_holds_exactly_the_baseline_and_the_released_disc_has_nothing_new(self):
        saved = REAL_V07.read_bytes()
        baseline = up.coach_record_baseline()
        records = named_records(saved, base_year=2026)
        self.assertEqual(len(records), 32)
        for key, record in records.items():
            old = baseline["coaches"][key]
            mine = fields_of(record)
            self.assertEqual({k: v for k, v in mine.items() if k != "announcer"}, old["fields"], key)
            self.assertEqual(mine["announcer"], old["announcer"], key)
        out, step = up.sync_coach_records(saved, REAL_DISC_ROST.read_bytes())
        self.assertEqual(out, saved)
        self.assertEqual((step["changes"], step["fields_kept"]), ([], 0))
        self.assertIn("no 2026 coach data", step["reason"])

    @unittest.skipUnless(REAL_V07.is_file(), "a real v0.7 franchise save is not named in B780_B10_V07")
    def test_the_v07_save_and_the_v08_disc_roster_agree_on_every_authored_field(self):
        disc = named_records(REAL_DISC_ROST.read_bytes(), preamble=0, reference_year=2026)
        saved = named_records(REAL_V07.read_bytes(), base_year=2026)
        self.assertEqual(set(disc), set(saved))
        for key in saved:
            self.assertEqual(fields_of(saved[key]), fields_of(disc[key]), key)


@unittest.skipUnless(REAL_V07.is_file() and REAL_C1_ROST.is_file() and REAL_DISC_ROST.is_file(),
                     "a real save and c1's roster are not named in B780_B10_V07, B780_B10_DISC_ROST and B780_B10_C1_ROST")
class RealFranchiseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = REAL_V07.read_bytes()
        cls.disc = REAL_C1_ROST.read_bytes()
        cls.older = REAL_DISC_ROST.read_bytes()

    def test_the_older_disc_is_the_new_disc_with_only_coach_record_bytes_changed(self):
        changed = differing(self.older, self.disc)
        records = named_records(self.disc, preamble=0, reference_year=2026)
        document = sr.decode(self.disc, preamble=0, reference_year=2026)
        rows, _ = up.coach_rows(document)
        allowed = {at + i for (_index, at) in rows.values() for lo, hi in DECLARED for i in range(lo, hi)}
        self.assertLessEqual(set(changed), allowed)
        self.assertEqual(len(records), 32)
        self.assertGreater(len(changed), 2000)

    def test_all_32_coaches_take_the_2026_records_and_nothing_else_moves(self):
        out, step = up.sync_coach_records(self.saved, self.disc)
        self.assertEqual((step["coaches_changed"], step["fields_kept"], step["reason"]), (32, 0, ""))
        self.assertEqual((len(step["matched"]), step["unmatched_preserved"], step["no_baseline_preserved"]), (32, [], []))
        # exactly the bytes the disc's writer changed relative to the older disc are the bytes this step changed
        self.assertEqual(step["changed_bytes"], len(differing(self.older, self.disc)))
        disc = named_records(self.disc, preamble=0, reference_year=2026)
        new = named_records(out, base_year=2026)
        for key, record in new.items():
            self.assertEqual(fields_of(record), fields_of(disc[key]), key)
        document = sr.decode(self.saved, base_year=2026)
        rows, _ = up.coach_rows(document)
        allowed = {at + i for (_index, at) in rows.values() for lo, hi in DECLARED for i in range(lo, hi)}
        self.assertLessEqual(set(differing(self.saved, out)), allowed)
        self.assertEqual(len(out), len(self.saved))

    def test_a_second_run_finds_nothing(self):
        once, first = up.sync_coach_records(self.saved, self.disc)
        twice, second = up.sync_coach_records(once, self.disc)
        self.assertEqual(twice, once)
        self.assertEqual((second["changes"], second["already_current"]), ([], len(first["changes"])))

    def test_changes_made_in_the_franchise_survive(self):
        document = sr.decode(self.saved, base_year=2026)
        rows, _ = up.coach_rows(document)
        reid = rows[("Andy", "Reid")][1]
        harbaugh = rows[("John", "Harbaugh")][1]
        edited = bytearray(self.saved)
        edited[reid + up.COACH_RATINGS_AT] = 99                                       # a player made Reid a 99
        lane = harbaugh + up.COACH_TENDENCY_GROUPS["run_lane"][0]
        edited[lane:lane + 5] = bytes([0, 0, 100, 0, 0])                              # and Harbaugh a middle runner
        out, step = up.sync_coach_records(bytes(edited), self.disc)
        self.assertEqual(out[reid + up.COACH_RATINGS_AT], 99)
        self.assertEqual(list(out[lane:lane + 5]), [0, 0, 100, 0, 0])
        kept = {(k["coach"], k["field"]) for k in step["kept"]}
        self.assertEqual(kept, {("Andy Reid", "ratings.overall"), ("John Harbaugh", "tendencies.run_lane")})
        self.assertEqual(step["coaches_changed"], 32)
        # the rest of Reid and Harbaugh did take the 2026 values
        disc = named_records(self.disc, preamble=0, reference_year=2026)
        reid_after = fields_of(named_records(out, base_year=2026)[("Andy", "Reid")])
        reid_disc = fields_of(disc[("Andy", "Reid")])
        self.assertEqual({k: v for k, v in reid_after.items() if k != "ratings.overall"},
                         {k: v for k, v in reid_disc.items() if k != "ratings.overall"})

    def test_the_whole_command_runs_through_plan_upgrade_and_writes_a_signed_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = signed_folder(root / "save", self.saved)
            disc_file = root / "disc.iso"
            disc_file.write_bytes(b"synthetic disc image")
            with patch.object(service, "load_disc", return_value=(self.disc, {})):
                plan = service.plan_upgrade(source, disc_file, command="coach-records")
                step = plan.receipt["steps"][-1]
                self.assertEqual((step["operation"], step["coaches_changed"]), ("coach_records", 32))
                self.assertEqual(plan.receipt["changed_fields"], len(step["changes"]))
                self.assertEqual(plan.receipt["output_extra_sha256"], up.sha(service.rr.sign_save(plan.payload)))
                receipt = service.write_plan(plan, root / "out", root / "out.upgrade.json")
            written = (root / "out" / "SAVEGAME.DAT").read_bytes()
            self.assertEqual(up.sha(written), receipt["output_savegame_sha256"])
            self.assertEqual((root / "out" / "EXTRA").read_bytes(), service.rr.sign_save(written))
            self.assertEqual((source / "SAVEGAME.DAT").read_bytes(), self.saved)         # the original is untouched

    @unittest.skipUnless(REAL_C1_DATA.is_file(), "c1's coach data is not named in B780_B10_C1_DATA")
    def test_every_value_equals_c1s_data_file(self):
        data = json.loads(REAL_C1_DATA.read_text(encoding="utf-8"))
        out, _step = up.sync_coach_records(self.saved, self.disc)
        records = named_records(out, base_year=2026)
        for club in data["coaches"].values():
            first, last = club["coach"].split(" ", 1)
            mine = fields_of(records[(first, last)])
            for name, value in club["ratings"].items():
                self.assertEqual(mine[f"ratings.{name}"], bytes((value,)), (club["coach"], name))
            for group, value in club["tendencies"].items():
                values = value if isinstance(value, list) else [value]
                self.assertEqual(mine[f"tendencies.{group}"], bytes(values), (club["coach"], group))
            self.assertEqual(mine["announcer"], club["announcer"], club["coach"])

    @unittest.skipUnless(REAL_RESAVED.is_file(), "the game-resaved franchise is not named in B780_B10_RESAVED")
    def test_the_franchise_the_v08_game_saved_takes_them_too(self):
        resaved = REAL_RESAVED.read_bytes()
        out, step = up.sync_coach_records(resaved, self.disc)
        self.assertEqual((step["coaches_changed"], step["fields_kept"]), (32, 0))
        disc = named_records(self.disc, preamble=0, reference_year=2026)
        for key, record in named_records(out, base_year=2026).items():
            self.assertEqual(fields_of(record), fields_of(disc[key]), key)
        self.assertEqual(len(out), len(resaved))


if __name__ == "__main__":
    unittest.main()

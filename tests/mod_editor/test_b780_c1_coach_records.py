"""b780 c1-coachdata: the coach record writer (ratings, tendency block, announcer flag, height and weight).

Pure tests run anywhere.  The disc tests need the private retail disc (NFL2K5_RETAIL_XISO) and, for the grown-roster
and "32 clubs" checks, the released SOFTDRINK v0.8 disc (NFL2K5_V08_XISO); each skips when its disc is absent."""
from __future__ import annotations

import os
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_franchise_save as fs  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402

_XISO = Path(os.environ.get("NFL2K5_RETAIL_XISO", str(ROOT / "ESPN NFL 2K5 (USA).xiso.iso")))
_V08 = Path(os.environ.get("NFL2K5_V08_XISO", "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.8 (2026-10-31).xiso.iso"))

RATINGS = {name: 60 + index for index, name in enumerate(rr.COACH_RATING_NAMES)}
TENDENCIES = {"run_share": 34, "run_by_score": [30, 31, 32, 33, 34, 35], "run_redzone": 41,
              "run_by_down_distance": list(range(40, 56)), "run_lane": [20, 25, 30, 15, 10],
              "formation_run": [5, 0, 10, 80, 5], "formation_pass": [82, 0, 3, 15, 0], "no_huddle": 3}
FULL = {"ratings": RATINGS, "tendencies": TENDENCIES, "announcer": "generic", "height_in": 74, "weight_lb": 225}


class PlanTests(unittest.TestCase):
    """plan_coach_record is pure: every refusal names the field."""

    def test_the_rating_and_tendency_maps_agree_with_the_franchise_editor(self) -> None:
        self.assertEqual(rr.COACH_RATING_NAMES, fs.COACH_RATINGS)
        self.assertEqual(rr.COACH_RATINGS_AT, fs.COACH_RATINGS_OFFSET)
        self.assertEqual(rr.COACH_RECORD_SIZE, fs.COACH_SIZE)
        spans = sorted((at, at + count, name) for name, (at, count, _kind) in rr.COACH_TENDENCY_GROUPS.items())
        for (_a, end, name), (start, _b, other) in zip(spans, spans[1:]):
            self.assertLessEqual(end, start, f"{name} overlaps {other}")
        self.assertGreaterEqual(spans[0][0], 0x59)
        self.assertLessEqual(spans[-1][1], 0xA8)
        # the editor's old alternating run/pass labels sit on the two formation groups
        self.assertEqual(fs.COACH_TENDENCIES_OFFSET, rr.COACH_TENDENCY_GROUPS["formation_run"][0])

    def test_a_full_entry_plans_every_span(self) -> None:
        writes, generic = rr.plan_coach_record(FULL)
        self.assertIs(generic, True)
        self.assertEqual(writes[0x42], bytes(range(60, 83)[:1]))
        self.assertEqual(writes[0x14], struct.pack("<H", 74))
        self.assertEqual(writes[0x16], struct.pack("<H", 225))
        self.assertEqual(writes[0x59], bytes((34,)))
        self.assertEqual(writes[0x61], bytes(range(40, 56)))
        self.assertEqual(writes[0x83], bytes((5, 0, 10, 80, 5)))
        self.assertEqual(writes[0xA5], bytes((3,)))
        self.assertEqual(rr.plan_coach_record({"announcer": "named"})[1], False)
        self.assertEqual(rr.plan_coach_record({"team": "KC", "first": "Andy"}), ({}, None))

    def test_every_bad_value_is_refused_with_its_name(self) -> None:
        bad = [({"ratings": {"charisma": 80}}, "charisma"),
               ({"ratings": {"overall": 100}}, "overall=100"),
               ({"ratings": {"overall": -1}}, "overall=-1"),
               ({"ratings": {"overall": 80.5}}, "overall=80.5"),
               ({"ratings": {"overall": True}}, "overall=True"),
               ({"ratings": [1, 2, 3]}, "ratings must be an object"),
               ({"tendencies": {"punt_rate": 5}}, "punt_rate"),
               ({"tendencies": {"run_share": 101}}, "run_share"),
               ({"tendencies": {"run_by_score": [1, 2, 3]}}, "run_by_score"),
               ({"tendencies": {"run_lane": [20, 20, 20, 20, 19]}}, "add up to 100"),
               ({"tendencies": {"formation_pass": [50, 50, 50, 0, 0]}}, "add up to 100"),
               ({"tendencies": {"no_huddle": "3"}}, "no_huddle"),
               ({"announcer": "loud"}, "announcer"),
               ({"height_in": 20}, "height_in"),
               ({"weight_lb": 90}, "weight_lb")]
        for entry, word in bad:
            with self.assertRaises(rr.RosterRecordError, msg=str(entry)) as raised:
                rr.plan_coach_record(entry)
            self.assertIn(word, str(raised.exception))


@unittest.skipUnless(_XISO.is_file(), "private retail NFL 2K5 disc absent (set NFL2K5_RETAIL_XISO)")
class RetailRosterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = rr.load_image(_XISO).to_body()
        cls.document = rr.RosterDocument(cls.base)
        ob = cls.document.obj_base
        cls.table = cls.document.rel(ob + rr.OBJ_OFF + 0x34)

    def apply(self, entries, body=None):
        return rr.apply_body(self.base if body is None else body,
                             {"schema": rr.EDITS_SCHEMA, "edits": [], "coaches": entries})

    def record_of(self, abbreviation: str) -> int:
        return next(t for t in self.document.teams if t.abbreviation == abbreviation).coach_offset

    def changed(self, new: bytes) -> list[int]:
        return [i for i, (a, b) in enumerate(zip(self.base, new)) if a != b]

    def test_one_entry_changes_only_its_planned_bytes(self) -> None:
        new, receipt = self.apply([dict(FULL, team="KC")])
        self.assertEqual(receipt["log"], [])
        self.assertEqual(receipt["coach_records_written"], 1)
        self.assertEqual(receipt["coach_names_written"], 0, "a record-only entry is not a name edit")
        record = self.record_of("KC")
        planned = set()
        writes, _generic = rr.plan_coach_record(FULL)
        for rel, data in writes.items():
            planned.update(range(record + rel, record + rel + len(data)))
        planned.add(record + 0x1A)
        self.assertEqual(set(self.changed(new)) - planned, set(), "a byte outside the plan changed")
        self.assertEqual(struct.unpack_from("<HH", new, record + 0x14), (74, 225))
        self.assertEqual(new[record + 0x1A], self.base[record + 0x1A] | 0x02)
        self.assertEqual(list(new[record + 0x42: record + 0x59]), list(range(60, 83)))
        self.assertEqual(new[record + 0x59], 34)
        self.assertEqual(list(new[record + 0x5A: record + 0x60]), [30, 31, 32, 33, 34, 35])
        self.assertEqual(list(new[record + 0x83: record + 0x8D]), [5, 0, 10, 80, 5, 82, 0, 3, 15, 0])
        self.assertEqual(new[record + 0xA5], 3)
        # what the plan leaves alone keeps the 2004 bytes: pass target zones, categories, motion, defense flags
        self.assertEqual(new[record + 0x71: record + 0x7E], self.base[record + 0x71: record + 0x7E])
        self.assertEqual(new[record + 0x8D: record + 0xA5], self.base[record + 0x8D: record + 0xA5])
        self.assertEqual(new[record + 0xA6: record + 0xA8], self.base[record + 0xA6: record + 0xA8])
        # the roster still parses and every other coach record is byte-identical
        rr.RosterDocument(new)

    def test_a_bare_disc_body_finds_its_own_roster_object(self) -> None:
        """c2-staff calls the writer the way apply_coach_names is called: (body, teams, entries, log), no object base."""
        body = bytearray(self.base)
        log: list[str] = []
        self.assertEqual(rr.apply_coach_records(body, self.document.teams, [dict(FULL, team="KC")], log), 1)
        self.assertEqual(log, [])
        self.assertEqual(bytes(body), self.apply([dict(FULL, team="KC")])[0])
        broken = bytearray(self.base)
        broken[0x14:0x18] = bytes(4)                         # a null roster root pointer
        log = []
        self.assertEqual(rr.apply_coach_records(broken, self.document.teams, [dict(FULL, team="KC")], log), 0)
        self.assertTrue(log, "an unreadable roster object is logged, not guessed")
        self.assertEqual(bytes(broken[0x18:]), self.base[0x18:])

    def test_names_and_records_in_one_entry_both_land(self) -> None:
        entry = dict(FULL, team="NYG", first="John", last="Harbaugh", fields={"wins": 180})
        new, receipt = self.apply([entry])
        self.assertEqual(receipt["log"], [])
        self.assertEqual((receipt["coach_names_written"], receipt["coach_records_written"]), (1, 1))
        record = self.record_of("NYG")
        self.assertEqual(struct.unpack_from("<H", new, record + 0x20)[0], 180)
        self.assertEqual(list(new[record + 0x42: record + 0x59]), list(range(60, 83)))
        document = rr.RosterDocument(new)
        nyg = next(t for t in document.teams if t.abbreviation == "NYG")
        self.assertEqual(document._string_at(nyg.coach_offset + 4), "Harbaugh")

    def test_the_announcer_flag_sets_and_clears_only_its_own_bit(self) -> None:
        record = self.record_of("DEN")
        marked = bytearray(self.base)
        marked[record + 0x1A] = 0x04          # a bit that is neither free nor generic must survive
        marked = bytes(marked)
        new, receipt = self.apply([{"team": "DEN", "announcer": "generic"}], marked)
        self.assertEqual((receipt["log"], new[record + 0x1A]), ([], 0x06))
        again, _ = self.apply([{"team": "DEN", "announcer": "named"}], new)
        self.assertEqual(again[record + 0x1A], 0x04)
        self.assertEqual([i for i, (a, b) in enumerate(zip(marked, new)) if a != b], [record + 0x1A])

    def test_a_free_create_team_record_is_refused(self) -> None:
        free = [t for t in self.document.teams if t.coach_offset is not None and self.base[t.coach_offset + 0x1A] & 1]
        self.assertTrue(free, "the retail roster has teams on free coach records")
        new, receipt = self.apply([dict(FULL, team=free[0].abbreviation)])
        self.assertEqual(receipt["coach_records_written"], 0)
        self.assertTrue(any("free Create Team record" in line for line in receipt["log"]), receipt["log"])
        self.assertEqual(new, self.base)

    def test_a_bad_entry_is_skipped_whole_and_the_others_still_land(self) -> None:
        entries = [dict(FULL, team="KC"), {"team": "DEN", "ratings": {"overall": 120}}, dict(FULL, team="XYZ")]
        new, receipt = self.apply(entries)
        self.assertEqual(receipt["coach_records_written"], 1)
        text = "\n".join(receipt["log"])
        self.assertIn("DEN", text)
        self.assertIn("overall=120", text)
        self.assertIn("XYZ", text)
        den = self.record_of("DEN")
        self.assertEqual(new[den: den + rr.COACH_RECORD_SIZE], self.base[den: den + rr.COACH_RECORD_SIZE])

    def test_two_entries_for_one_shared_record_must_agree(self) -> None:
        shared = [t.abbreviation for t in self.document.teams if t.coach_offset == self.record_of("NE")]
        self.assertGreater(len(shared), 1, "NE shares its coach record with historic teams")
        other = next(a for a in shared if a != "NE")
        same, receipt = self.apply([dict(FULL, team="NE"), dict(FULL, team=other)])
        self.assertEqual((receipt["log"], receipt["coach_records_written"]), ([], 1))
        clash, receipt = self.apply([dict(FULL, team="NE"), dict(FULL, team=other, ratings={"overall": 70})])
        self.assertEqual(receipt["coach_records_written"], 0)
        self.assertTrue(any("different values" in line for line in receipt["log"]), receipt["log"])
        self.assertEqual(clash, self.base)

    def test_a_foreign_coach_table_writes_nothing(self) -> None:
        tampered = bytearray(self.base)
        count_at = self.document.obj_base + rr.OBJ_OFF + 0x30
        struct.pack_into("<I", tampered, count_at, 34)
        new, receipt = self.apply([dict(FULL, team="KC")], bytes(tampered))
        self.assertEqual(receipt["coach_records_written"], 0)
        self.assertTrue(any("not the supported 35 records" in line for line in receipt["log"]), receipt["log"])
        self.assertEqual(new, bytes(tampered))

    def test_a_coach_pointer_off_the_record_boundary_is_skipped(self) -> None:
        tampered = bytearray(self.base)
        kc = next(t for t in self.document.teams if t.abbreviation == "KC")
        field = kc.offset + rr.TEAM_COACH
        struct.pack_into("<i", tampered, field, struct.unpack_from("<i", tampered, field)[0] + 4)
        new, receipt = self.apply([dict(FULL, team="KC")], bytes(tampered))
        self.assertEqual(receipt["coach_records_written"], 0)
        self.assertTrue(any("not a coach record" in line for line in receipt["log"]), receipt["log"])
        self.assertEqual(new, bytes(tampered))


@unittest.skipUnless(_V08.is_file(), "released SOFTDRINK 2K28 v0.8 disc absent (set NFL2K5_V08_XISO)")
class ReleasedRosterTests(unittest.TestCase):
    """The grown version-18 roster the released v0.8 disc carries: 32 clubs, nothing else moves."""

    def test_thirty_two_clubs_get_flags_and_ratings_and_nothing_else_moves(self) -> None:
        base = rr.load_image(_V08).to_body()
        document = rr.RosterDocument(base)
        self.assertEqual(document.version, 18)
        clubs = [t for t in document.teams if t.index < 32]
        entries = [{"team": t.abbreviation, "ratings": {"overall": 70 + (t.index % 20)},
                    "announcer": "generic"} for t in clubs]
        new, receipt = rr.apply_body(base, {"schema": rr.EDITS_SCHEMA, "edits": [], "coaches": entries})
        self.assertEqual(receipt["log"], [])
        self.assertEqual(receipt["coach_records_written"], 32)
        changed = [i for i, (a, b) in enumerate(zip(base, new)) if a != b]
        records = {t.coach_offset for t in clubs}
        self.assertEqual(len(records), 32)
        allowed = set()
        for record in records:
            allowed.update((record + 0x1A, record + 0x42))
        self.assertLessEqual(set(changed), allowed)
        after = rr.RosterDocument(new)
        for team in after.teams[:32]:
            self.assertTrue(new[team.coach_offset + 0x1A] & 0x02)
            self.assertEqual(new[team.coach_offset + 0x42], 70 + (team.index % 20))


_SAVE = Path(os.environ.get("NFL2K5_FRANCHISE_SAVE",
                            "/home/noah/2k-worktrees/.b77-scratch/b780/c6-carousel/fixtures/v08_save/SAVEGAME.DAT"))


@unittest.skipUnless(_SAVE.is_file(), "a franchise SAVEGAME.DAT is absent (set NFL2K5_FRANCHISE_SAVE)")
class FranchiseArenaTests(unittest.TestCase):
    """The same writer on a real franchise save: the roster arena (version 1) at +0x300 of SAVEGAME.DAT."""

    def test_the_arena_takes_the_records_and_nothing_else_moves(self) -> None:
        raw = _SAVE.read_bytes()
        document = rr.RosterDocument(raw, base=rr.SAVE_BLOCK_OFFSET, source="save")
        clubs = [t for t in document.teams if t.index < 32]
        entries = [{"team": t.abbreviation, "ratings": {"overall": 60 + t.index}, "announcer": "generic",
                    "tendencies": {"run_share": 40 + t.index % 10}} for t in clubs]
        log: list[str] = []
        self.assertEqual(rr.apply_coach_records(document.body, document.teams, entries, log, obj_base=document.obj_base), 32)
        self.assertEqual(log, [])
        new = bytes(document.body)
        records = {t.coach_offset for t in clubs}
        self.assertEqual(len(records), 32)
        changed = [i for i, (a, b) in enumerate(zip(raw, new)) if a != b]
        self.assertTrue(changed)
        for index in changed:
            owner = next((r for r in records if r <= index < r + rr.COACH_RECORD_SIZE), None)
            self.assertIsNotNone(owner, f"byte 0x{index:X} outside the coach records changed")
            self.assertIn(index - owner, (0x1A, 0x42, 0x59))
        for team in clubs:
            self.assertEqual(new[team.coach_offset + 0x42], 60 + team.index)
            self.assertTrue(new[team.coach_offset + 0x1A] & 2)


if __name__ == "__main__":
    unittest.main()

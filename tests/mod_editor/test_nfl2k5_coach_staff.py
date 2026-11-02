"""b780 c2-staff: coaching staff (move, swap, create head coaches; a DC per club) and the per-club 2026 profiles.

The document, directory and kernel-table checks run everywhere. The roster checks need the user's private retail disc
(NFL2K5_RETAIL_XISO, skipped without it); the compile check on final books also needs a built SOFTDRINK disc
(NFL2K5_COACH_AI_IMAGE)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_coach_ai as ai  # noqa: E402
from mod_editor.core import nfl2k5_coach_ai_code as assembly  # noqa: E402
from mod_editor.core import nfl2k5_coach_staff as st  # noqa: E402

_XISO = Path(os.environ.get("NFL2K5_RETAIL_XISO", str(ROOT / "ESPN NFL 2K5 (USA).xiso.iso")))


def directory_coaches():
    """The roster-edits ``coaches`` list that names the 32 2026 head coaches at their 2026 clubs."""
    out = []
    for row in st.head_coach_directory():
        first, last = row["name"].split(" ", 1)
        out.append({"team": row["home"], "first": first, "last": last})
    return out


class ClubsAndDirectory(unittest.TestCase):
    def test_32_clubs_in_book_order_with_every_spelling(self):
        clubs = st.clubs()
        self.assertEqual([c.index for c in clubs], list(range(32)))
        self.assertEqual(tuple(c.book for c in clubs), st.BOOK_CODES)
        rows = sorted(ai.portrait_rows(), key=lambda r: r["book_index"])
        self.assertEqual([c.team for c in clubs], [r["team"] for r in rows])
        self.assertEqual([c.asset for c in clubs], [r["asset"] for r in rows])
        for spelling in ("OAK", "LV", "lv", "Raiders", "Las Vegas", 22, "las vegas raiders"):
            self.assertEqual(st.club(spelling).book, "OAK", spelling)
        for spelling, book in (("ARI", "ARZ"), ("LAC", "SD"), ("LAR", "STL"), ("WSH", "WAS"), ("Commanders", "WAS")):
            self.assertEqual(st.club(spelling).book, book)
        for bad in ("XYZ", 32, -1, "", None, 3.0):
            with self.assertRaises(st.StaffError):
                st.club(bad)

    def test_directories_name_32_distinct_people(self):
        coaches, dcs = st.head_coach_directory(), st.coordinator_directory()
        self.assertEqual(len({c["name"] for c in coaches}), 32)
        self.assertEqual(len({c["name"] for c in dcs}), 32)
        self.assertEqual(st.directory_coach("Andy Reid")["id"], "KC")
        self.assertEqual(st.directory_coach("LV")["name"], "Klint Kubiak")
        self.assertEqual(st.coordinator("Vic Fangio")["id"], "PHI")
        self.assertEqual(st.coordinator("Eagles")["name"], "Vic Fangio")
        for row in coaches:
            self.assertEqual(row["identity"], next(r["identity"] for r in ai.portrait_rows() if r["team"] == row["id"]))


class Document(unittest.TestCase):
    def test_normalize_is_canonical_and_strict(self):
        value = st.normalize({"head_coaches": [{"team": "Raiders", "coach": "Andy Reid", "playbook": "coach"},
                                               {"team": "kc", "coach": "Klint Kubiak"}],
                              "defensive_coordinators": [{"team": "Cowboys", "dc": "Vic Fangio"}]})
        self.assertEqual(value["head_coaches"], [{"team": "KC", "coach": "Klint Kubiak"},
                                                 {"team": "OAK", "coach": "Andy Reid", "playbook": "coach"}])
        self.assertEqual(value["defensive_coordinators"], [{"team": "DAL", "dc": "PHI"}])
        self.assertEqual(st.normalize(value), value)
        self.assertTrue(st.is_empty(None) and st.is_empty({}) and st.is_empty(st.empty()))
        for bad in ({"schema": "other/v1"}, {"extra": 1}, {"head_coaches": [{"team": "KC"}]},
                    {"head_coaches": [{"team": "KC", "coach": "A B", "created": "x"}]},
                    {"head_coaches": [{"team": "KC", "created": "nobody"}]},
                    {"head_coaches": [{"team": "KC", "coach": "A B"}, {"team": "Chiefs", "coach": "C D"}]},
                    {"head_coaches": [{"team": "KC", "coach": "A B"}, {"team": "NE", "coach": "a b"}]},
                    {"head_coaches": [{"team": "KC", "coach": "A B", "playbook": "theirs"}]},
                    {"defensive_coordinators": [{"team": "KC", "dc": "Nobody Here"}]},
                    {"defensive_coordinators": [{"team": "KC", "dc": "PHI"}, {"team": "Chiefs", "dc": "DAL"}]}):
            with self.assertRaises(st.StaffError, msg=bad):
                st.normalize(bad)

    def test_created_coach_spec_checks(self):
        good = {"id": "pat", "first": "Pat", "last": "Shurmur", "style": "Giants", "ratings": {"overall": 70},
                "tendencies": {"shotgun_pass": 30}, "fields": {"wins": 20}, "playcalling_run": 40,
                "height_in": 72, "weight_lb": 200, "bio": ["Former Giants head coach"]}
        value = st.normalize({"created_coaches": [good], "head_coaches": [{"team": "NYG", "created": "pat",
                                                                            "playbook": "coach"}]})
        spec = value["created_coaches"][0]
        self.assertEqual((spec["style"], spec["body"], spec["photo"]), ("NYG", st.CREATED_BODY, st.NO_PHOTO))
        for change in ({"body": 31}, {"body": "50"}, {"photo": 70000}, {"first": ""}, {"first": "x" * 25},
                       {"last": "A\nB"}, {"ratings": {"overall": 100}}, {"ratings": {"speed": 50}},
                       {"tendencies": {"shotgun_pass": 101}}, {"style": "Nobody"}, {"bio": ["a", "b", "c", "d"]},
                       {"height_in": 20}, {"weight_lb": 1000}, {"colour": "red"}):
            with self.assertRaises(st.StaffError, msg=change):
                st.normalize({"created_coaches": [dict(good, **change)]})
        no_style = dict(good)
        no_style.pop("style")
        with self.assertRaisesRegex(st.StaffError, "play-calling style"):
            st.normalize({"created_coaches": [no_style], "head_coaches": [{"team": "NYG", "created": "pat",
                                                                           "playbook": "coach"}]})

    def test_created_record_starts_from_the_game_template(self):
        template = bytearray(st.RECORD_SIZE)
        template[st.FLAGS] = st.FLAG_FREE
        struct.pack_into("<HH", template, st.HEIGHT, 74, 210)
        for at in range(st.RATINGS, st.RATINGS + 23):
            template[at] = 50
        template[st.TENDENCY_BLOCK[0]:st.TENDENCY_BLOCK[1]] = bytes(range(1, 1 + st.RECORD_SIZE - 0x59))
        style = bytearray(st.RECORD_SIZE)
        style[st.TENDENCY_BLOCK[0]:] = b"\x07" * (st.RECORD_SIZE - 0x59)
        spec = st.normalize({"created_coaches": [{"id": "a", "first": "A", "last": "B", "ratings": {"respect": 80},
                                                  "fields": {"wins": 9}, "playcalling_run": 44}]})["created_coaches"][0]
        out = bytes(st.CONTENT_START) + st.created_record(spec, bytes(template), bytes(style))
        self.assertEqual(out[st.FLAGS], st.FLAG_GENERIC_NAME)
        self.assertEqual(struct.unpack_from("<H", out, st.BODY)[0], st.CREATED_BODY)
        self.assertEqual(struct.unpack_from("<H", out, st.PHOTO)[0], st.NO_PHOTO)
        self.assertEqual(struct.unpack_from("<H", out, 0x20)[0], 9)
        self.assertEqual(out[st.RATINGS + 22], 80)
        self.assertEqual(out[st.RATINGS], 50)
        self.assertEqual(out[st.PLAYCALLING_RUN], 44)
        self.assertEqual(out[0x5A:st.RECORD_SIZE], b"\x07" * (st.RECORD_SIZE - 0x5A))
        self.assertEqual(struct.unpack_from("<HH", out, st.HEIGHT), (74, 210))

    def test_hire_record_resets_only_the_with_team_counters(self):
        raw = bytearray(range(st.RECORD_SIZE))
        raw[st.FLAGS] = st.FLAG_FREE
        out = bytes(st.CONTENT_START) + st.hire_record(bytes(raw))
        for at in st.WITH_TEAM_FIELDS:
            self.assertEqual(struct.unpack_from("<H", out, at)[0], 0)
        self.assertEqual(out[st.FLAGS], st.FLAG_GENERIC_NAME)
        changed = {i for i in range(st.CONTENT_START, st.RECORD_SIZE) if out[i] != raw[i]}
        allowed = {st.FLAGS} | {a + k for a in st.WITH_TEAM_FIELDS for k in (0, 1)}
        self.assertLessEqual(changed, allowed)


class KernelTable(unittest.TestCase):
    def test_default_table_round_trip_and_location(self):
        rows = ai.default_table()
        raw = ai.encode_table(rows)
        self.assertEqual(len(raw), ai.TABLE_SIZE)
        self.assertEqual(ai.decode_table(raw), rows)
        for variant, code in (("b778", assembly.CODE), ("v061", assembly.CODE_V061)):
            at = ai.table_offset(variant)
            self.assertEqual(code[at:at + ai.TABLE_SIZE], raw)
            self.assertEqual(code.count(raw), 1)
            self.assertEqual(ai.code_for(0x400000, 0x500000, 0, variant, table=rows),
                             ai.code_for(0x400000, 0x500000, 0, variant))

    def test_assigned_and_vacant_rows_change_only_the_table(self):
        rows = ai.default_table()
        rows[9], rows[22] = dict(rows[22], book_index=9, asset=rows[9]["asset"]), dict(rows[9], book_index=22,
                                                                                         asset=rows[22]["asset"])
        rows[21] = ai.vacant_row(21)
        ai.check_table(rows)
        self.assertEqual(ai.decode_table(ai.encode_table(rows)), rows)
        for variant in ("b778", "v061"):
            base = ai.code_for(0x400000, 0x500000, 0x600000, variant)
            moved = ai.code_for(0x400000, 0x500000, 0x600000, variant, table=rows)
            at = ai.table_offset(variant)
            diff = [i for i, (a, b) in enumerate(zip(base, moved)) if a != b]
            self.assertTrue(diff and min(diff) >= at and max(diff) < at + ai.TABLE_SIZE)
        vacant = ai.encode_table(rows)[21 * ai.TABLE_ROW_SIZE:22 * ai.TABLE_ROW_SIZE]
        self.assertEqual(struct.unpack_from("<IIHHHH", vacant), (0, 0, 21, ai.VACANT_ASSET, 0, 0))
        self.assertEqual(vacant[16:42], b"\xff\xff" * 13)

    def test_junk_tables_refuse(self):
        def bad(index, **change):
            rows = ai.default_table()
            rows[index] = dict(rows[index], **change)
            return rows
        cases = [bad(3, book_index=4), bad(3, asset=7), bad(3, identity=0), bad(3, name=""), bad(3, name="x" * 13),
                 bad(3, portrait=0), bad(4, identity=ai.default_table()[3]["identity"]),
                 bad(5, identity=0, legacy_identity=0, asset=ai.VACANT_ASSET, portrait=0, name=None, alternate_portrait=7),
                 ai.default_table()[:31]]
        for rows in cases:
            with self.assertRaises(ai.CoachAIError):
                ai.check_table(rows)
        raw = bytearray(ai.encode_table(ai.default_table()))
        raw[42] = 1                      # row 0 padding
        with self.assertRaises(ai.CoachAIError):
            ai.decode_table(bytes(raw))
        raw = bytearray(ai.encode_table(ai.default_table()))
        raw[16 + 2 * 12] = 0x41           # row 0 name: a unit after the end of the name
        with self.assertRaises(ai.CoachAIError):
            ai.decode_table(bytes(raw))


@unittest.skipUnless(_XISO.is_file(), "private retail NFL 2K5 disc absent (set NFL2K5_RETAIL_XISO)")
class RetailRoster(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_roster_records as rr
        cls.rr = rr
        cls.retail = rr.load_image(_XISO).to_body()
        doc = rr.RosterDocument(cls.retail)
        cls.teams = doc.teams
        body = bytearray(cls.retail)
        cls.coaches_list = directory_coaches()
        rr.apply_coach_names(body, cls.teams, cls.coaches_list, [])
        cls.base = bytes(body)

    def body(self):
        return bytearray(self.base)

    def names(self, body):
        return {c.club.book: c.name for c in st.read_roster(body, self.teams)}

    STAFF = {"head_coaches": [{"team": "OAK", "coach": "Andy Reid"}, {"team": "KC", "coach": "Klint Kubiak"},
                              {"team": "NYG", "created": "pat"}],
             "defensive_coordinators": [{"team": "DAL", "dc": "Vic Fangio"}, {"team": "PHI", "dc": "DAL"}],
             "created_coaches": [{"id": "pat", "first": "Pat", "last": "Shurmur", "style": "NYG",
                                  "bio": ["Created for a what-if"]}]}

    def test_every_2026_coach_is_recognized_on_his_club(self):
        coaches = st.read_roster(self.base, self.teams)
        self.assertEqual([c.directory_id for c in coaches], [c.team for c in st.clubs()])
        retail = st.read_roster(self.retail, self.teams)
        self.assertTrue(all(c.directory_id is None for c in retail))     # 2004 names: no 2026 profile
        self.assertEqual(retail[9].name, "Dick Vermeil")

    def test_moves_carry_the_whole_record_and_start_with_team_counters(self):
        body = self.body()
        before = {c.club.book: c for c in st.read_roster(body, self.teams)}
        receipt = st.apply_to_body(body, self.teams, self.STAFF, [])
        after = {c.club.book: c for c in st.read_roster(body, self.teams)}
        self.assertEqual(receipt["head_coaches_changed"], 3)
        self.assertEqual(receipt["fired"], ["John Harbaugh"])
        reid, old = after["OAK"], before["KC"]
        self.assertEqual((reid.name, reid.bio, reid.photo, reid.body, reid.ratings, reid.tendencies,
                          reid.playcalling_run), (old.name, old.bio, old.photo, old.body, old.ratings,
                                                   old.tendencies, old.playcalling_run))
        self.assertEqual(reid.fields["seasons_with_team"], 0)
        self.assertEqual({k: v for k, v in reid.fields.items() if k != "seasons_with_team"},
                         {k: v for k, v in old.fields.items() if k != "seasons_with_team"})
        self.assertEqual(reid.flags, st.FLAG_GENERIC_NAME)
        self.assertEqual(reid.directory_id, "KC")
        self.assertEqual(after["KC"].directory_id, "LV")
        pat = after["NYG"]
        self.assertEqual((pat.name, pat.photo, pat.body, pat.flags, pat.bio[0]),
                         ("Pat Shurmur", st.NO_PHOTO, st.CREATED_BODY, st.FLAG_GENERIC_NAME, "Created for a what-if"))
        for code in set(after) - {"OAK", "KC", "NYG"}:
            self.assertEqual(after[code].__dict__ | {"record_offset": 0},
                             before[code].__dict__ | {"record_offset": 0}, code)
        # nothing outside the coach records and their text region changed; team pointers did not move
        changed = [i for i, (a, b) in enumerate(zip(self.base, bytes(body))) if a != b]
        table = st._coach_table(body)
        region = (0x2AD0 + 35 * 0xA8, len(body))
        self.assertTrue(all(table["offset"] <= i < table["end"] or region[0] <= i < region[1] for i in changed))
        self.assertEqual([t.coach_offset for t in self.rr.RosterDocument(bytes(body)).teams],
                         [t.coach_offset for t in self.teams])

    def test_the_same_staff_twice_changes_nothing(self):
        body = self.body()
        st.apply_to_body(body, self.teams, self.STAFF, [])
        once = bytes(body)
        self.assertEqual(st.apply_to_body(body, self.teams, self.STAFF, [])["changed_bytes"], 0)
        self.assertEqual(bytes(body), once)

    def test_vacancy_unknown_and_duplicates_refuse_in_plain_words(self):
        cases = (({"head_coaches": [{"team": "OAK", "coach": "Andy Reid"}]}, "Kansas City has no head coach"),
                 ({"head_coaches": [{"team": "OAK", "coach": "Bill Belichick"}]}, "no head coach named Bill Belichick"),
                 ({"head_coaches": [{"team": "OAK", "created": "x"}],
                   "created_coaches": [{"id": "x", "first": "Andy", "last": "Reid"}]}, "two clubs would have"),
                 ({"defensive_coordinators": [{"team": "DAL", "dc": "Vic Fangio"}]}, "Give Philadelphia another"))
        for staff, words in cases:
            result = st.plan(staff, self.base, self.teams)
            self.assertFalse(result.ok)
            self.assertIn(words, " ".join(result.errors))
            body = self.body()
            with self.assertRaises(st.StaffError):
                st.apply_to_body(body, self.teams, staff, [])
            self.assertEqual(bytes(body), self.base)

    def test_profile_bindings_follow_the_coach_and_the_coordinator(self):
        body = self.body()
        st.apply_to_body(body, self.teams, self.STAFF, [])
        bindings, reasons = st.profile_bindings(body, self.teams, self.STAFF)
        self.assertEqual(reasons, [])
        by = {b.club.book: b for b in bindings}
        self.assertEqual((by["OAK"].tendency, by["OAK"].profile_name, by["OAK"].defense, by["OAK"].portrait),
                         ("KC", "KC Reid", "OAK", 7013))
        self.assertEqual((by["KC"].tendency, by["KC"].defense), ("LV", "KC"))
        self.assertEqual((by["NYG"].tendency, by["NYG"].profile_name, by["NYG"].portrait), ("NYG", "NYG Shurmur",
                                                                                          st.NO_PHOTO))
        self.assertEqual((by["DAL"].defense, by["PHI"].defense), ("PHI", "DAL"))
        rows = [b.table_row() for b in bindings]
        ai.check_table(rows)
        self.assertEqual(rows[22]["identity"], ai.default_table()[9]["identity"])
        self.assertEqual(rows[22]["asset"], ai.default_table()[22]["asset"])
        # a created coach without a style and a 2004 coach play native, only at their own clubs
        staff = {"head_coaches": [{"team": "NYG", "created": "x"}],
                 "created_coaches": [{"id": "x", "first": "Pat", "last": "Shurmur"}]}
        body = self.body()
        st.apply_to_body(body, self.teams, staff, [])
        bindings, reasons = st.profile_bindings(body, self.teams, staff)
        self.assertEqual([b is None for b in bindings].count(True), 1)
        self.assertIsNone(bindings[15])
        self.assertIn("without a play-calling style", reasons[0])
        bindings, reasons = st.profile_bindings(self.retail, self.teams, None)
        self.assertTrue(all(b is None for b in bindings))
        self.assertEqual(len(reasons), 32)

    def test_editing_helpers_keep_the_document_minimal(self):
        staff = st.move_head_coach(None, "Andy Reid", "Raiders", self.base, self.teams)
        self.assertEqual(staff["head_coaches"], [{"team": "KC", "coach": "Klint Kubiak"},
                                                 {"team": "OAK", "coach": "Andy Reid"}])
        self.assertTrue(st.plan(staff, self.base, self.teams).ok)
        self.assertEqual(st.swap_head_coaches(staff, "KC", "LV", self.base, self.teams)["head_coaches"], [])
        staff = st.move_head_coach(None, "Andy Reid", "LV", self.base, self.teams, vacancy="error")
        self.assertIn("Kansas City has no head coach", " ".join(st.plan(staff, self.base, self.teams).errors))
        staff = st.fire_head_coach(staff, "KC", {"id": "c", "first": "Pat", "last": "Shurmur", "style": "KC"},
                                   self.base, self.teams)
        result = st.plan(staff, self.base, self.teams)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.fired, ["Klint Kubiak"])
        staff = st.set_playbook(staff, "LV", "coach")
        self.assertEqual(st.plan(staff, self.base, self.teams).clubs[22].playbook_from.book, "KC")
        staff = st.set_defensive_coordinator(staff, "DAL", "Vic Fangio")
        self.assertEqual(staff["defensive_coordinators"], [{"team": "DAL", "dc": "PHI"}, {"team": "PHI", "dc": "DAL"}])
        self.assertEqual(st.reset(staff), st.empty())

    def test_roster_edits_apply_body_writes_names_then_staff(self):
        document = {"schema": self.rr.EDITS_SCHEMA, "edits": [], "coaches": self.coaches_list, "staff": self.STAFF}
        out, receipt = self.rr.apply_body(self.retail, document)
        self.assertEqual(receipt["coach_staff"]["head_coaches_changed"], 3)
        names = self.names(out)
        self.assertEqual((names["OAK"], names["KC"], names["NYG"]), ("Andy Reid", "Klint Kubiak", "Pat Shurmur"))
        with self.assertRaises(self.rr.RosterRecordError):
            self.rr.read_edits(dict(document, staff={"head_coaches": [{"team": "Nowhere", "coach": "A B"}]}))

    def test_locate_directory_coach_finds_him_where_he_heads_a_club(self):
        body = self.body()
        st.apply_to_body(body, self.teams, self.STAFF, [])
        oak = next(t for t in self.teams if t.abbreviation == "OAK")
        self.assertEqual(st.locate_directory_coach(body, self.teams, "KC"), oak.coach_offset)
        self.assertIsNone(st.locate_directory_coach(body, self.teams, "NYG"))      # John Harbaugh: no club
        self.assertIsNone(st.locate_directory_coach(self.retail, self.teams, "KC"))  # 2004 names


@unittest.skipUnless(_XISO.is_file() and os.environ.get("NFL2K5_COACH_AI_IMAGE"),
                     "needs the retail disc (NFL2K5_RETAIL_XISO) and a built disc's final books (NFL2K5_COACH_AI_IMAGE)")
class ProfilesOnFinalBooks(unittest.TestCase):
    """Three moves and one coordinator change on the final playbooks of a built disc: 32 books, the moved coaches'
    offense fitted to their host books, the host's (or the assigned) coordinator's rings, a valid kernel table."""

    def test_moved_coaches_compile_on_their_host_books(self):
        from mod_editor.core import nfl2k5_playbook_pack as packs, nfl2k5_roster_records as rr
        module = packs._outer_image()
        real = module.OuterImage
        image = os.environ["NFL2K5_COACH_AI_IMAGE"]
        retail = rr.load_image(_XISO).to_body()
        teams = rr.RosterDocument(retail).teams
        body = bytearray(retail)
        rr.apply_coach_names(body, teams, directory_coaches(), [])
        staff = {"head_coaches": [{"team": "OAK", "coach": "Andy Reid"}, {"team": "KC", "coach": "Klint Kubiak"},
                                  {"team": "CIN", "coach": "Kyle Shanahan"}, {"team": "SF", "coach": "Zac Taylor"}],
                 "defensive_coordinators": [{"team": "DAL", "dc": "Vic Fangio"}, {"team": "PHI", "dc": "DAL"}]}
        st.apply_to_body(body, teams, staff, [])
        with real(image) as source:
            wrapper = source.read_entry(5)[:32]
        roster = wrapper + bytes(body)

        class Archive:
            def __init__(self, *_args, **_kw):
                self.inner = real(image)

            def __enter__(self):
                self.inner.__enter__()
                return self

            def __exit__(self, *exc):
                return self.inner.__exit__(*exc)

            def read_entry(self, index):
                return roster if index == 5 else self.inner.read_entry(index)

        with patch.object(module, "OuterImage", Archive):
            prepared = ai.plan_profiles(image, staff=staff)
        self.assertEqual(len(prepared), 32)
        self.assertEqual(prepared.native, [])
        receipts = {r[3]["team"]: r[3] for r in prepared}
        self.assertEqual(receipts["LV"]["staff"]["play_calling"], "KC")
        self.assertEqual(receipts["LV"]["defense_identity"]["team"], "OAK")
        self.assertEqual(receipts["CIN"]["staff"]["play_calling"], "SF")
        self.assertEqual(receipts["DAL"]["defense_identity"]["dc"], "Vic Fangio")
        self.assertEqual(receipts["PHI"]["defense_identity"]["team"], "DAL")
        rows = prepared.table
        ai.check_table(rows)
        for index, before, after, receipt in prepared:
            info = ai.inspect_profile(after, rows)
            self.assertEqual(info["book_index"], ai.default_table()[info["book_index"]]["book_index"])
            self.assertEqual(ai.strip_profile(after), ai.strip_profile(before))
        self.assertEqual(rows[22]["name"], "KC Reid")
        self.assertEqual(rows[0]["name"], "CIN Taylor")


if __name__ == "__main__":
    unittest.main()

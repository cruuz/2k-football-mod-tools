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
        moved = st.move_head_coach(staff, "Pat Shurmur", "NYG", self.base, self.teams)    # a created coach moves too
        self.assertIn({"team": "NYG", "created": "c"}, moved["head_coaches"])
        self.assertIn({"team": "KC", "coach": "John Harbaugh"}, moved["head_coaches"])
        self.assertTrue(st.plan(moved, self.base, self.teams).ok)
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


_XBE = os.environ.get("NFL2K5_COACH_AI_XBE")
_V061 = os.environ.get("NFL2K5_V061_XBE")


def _swapped_rows():
    rows = ai.default_table()
    kc, lv = rows[9], rows[22]
    rows[9] = dict(lv, book_index=9, asset=kc["asset"])
    rows[22] = dict(kc, book_index=22, asset=lv["asset"])
    rows[21] = ai.vacant_row(21)
    return rows


@unittest.skipUnless(_XBE, "Set NFL2K5_COACH_AI_XBE to an executable with (or ready for) the coach AI kernel")
class InstalledKernelTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = Path(_XBE).read_bytes()
        if ai.status(payload) != "applied":
            payload = ai.apply(payload)[0]
        cls.payload = payload

    def test_an_assigned_table_installs_reseals_and_reads_back(self):
        from mod_editor.core import nfl2k5_xbe_space as space
        rows = _swapped_rows()
        result, receipt = ai.install_table(self.payload, rows)
        self.assertEqual(len(result), len(self.payload))
        self.assertEqual((ai.status(result), space.status(result)), ("applied", "applied"))
        self.assertEqual(ai.installed_table(result), rows)
        self.assertEqual(receipt["vacant_rows"], 1)
        self.assertEqual([r["book_index"] for r in receipt["assigned"]], [9, 21, 22])
        again, second = ai.install_table(result, rows)
        self.assertEqual((again, second["status"], second["changed_bytes"]), (result, "already_applied", 0))
        back, _ = ai.install_table(result, ai.default_table())
        self.assertEqual(ai.installed_table(back), ai.default_table())
        self.assertEqual(ai.apply(result)[0], result)              # an installed kernel is not reinstalled
        self.assertEqual(ai.normalized_sites(result), ai.normalized_sites(self.payload))

    def test_junk_in_the_table_is_foreign(self):
        from mod_editor.core import nfl2k5_xbe_space as space
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        rows = ai.default_table()
        rows[4] = dict(rows[4], identity=rows[3]["identity"])     # one coach in two rows
        at = ai.allocations(self.payload)["code"]["va"] + ai.table_offset()
        buf = bytearray(self.payload)
        offset = XbeImage(self.payload).offset(at, ai.TABLE_SIZE)
        buf[offset:offset + ai.TABLE_SIZE] = b"".join(ai._encode_row(r) for r in rows)
        space._seal_scaleout(buf, space._read_scale_directory(self.payload))
        for section in _sections(buf):
            buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
        self.assertEqual(space.status(bytes(buf)), "applied")
        self.assertEqual(ai.status(bytes(buf)), "foreign")
        with self.assertRaises(ai.CoachAIError):
            ai.apply(bytes(buf))
        with self.assertRaises(ai.CoachAIError):
            ai.install_table(self.payload, rows)


@unittest.skipUnless(_V061, "Set NFL2K5_V061_XBE to the beta-77.1 (v0.6.1) executable")
class UpgradeCarriesTheTable(unittest.TestCase):
    def test_the_upgrade_keeps_an_assigned_table(self):
        payload = Path(_V061).read_bytes()
        self.assertEqual(ai.installed_variant(payload), "v061")
        rows = _swapped_rows()
        assigned, _ = ai.install_table(payload, rows)
        self.assertEqual(ai.installed_variant(assigned), "v061")
        upgraded, receipt = ai.upgrade(assigned)
        self.assertEqual(receipt["status"], "upgraded")
        self.assertEqual((ai.status(upgraded), ai.installed_variant(upgraded)), ("applied", "b778"))
        self.assertEqual(ai.installed_table(upgraded), rows)
        plain, _ = ai.upgrade(payload)
        self.assertEqual(ai.installed_table(plain), ai.default_table())


class PlaybookCopies(unittest.TestCase):
    """Bring his playbook: one snapshot, so a swap where both coaches bring their books is exact; shapes must match."""

    def test_copies_come_from_one_snapshot_and_clear_the_profile_tail(self):
        from mod_editor.core import nfl2k5_playbook_pack as packs
        module = packs._outer_image()
        size = ai.BODY_SIZE + 32
        def book(fill):
            raw = bytearray(size)
            raw[32 + 12:32 + 16] = b"PLAY"
            raw[32 + 0x40:32 + 0x8000] = bytes([fill]) * (0x8000 - 0x40)
            return bytes(raw)
        store = {index: book(n) for n, index in enumerate(module.BOOK_ENTRIES[c.book] for c in st.clubs())}
        writes = []

        class Entry:
            def __init__(self, index):
                self.virtual_offset = index * 0x100000

        class Archive:
            def __init__(self, *_args, **_kw):
                self.entries = {i: Entry(i) for i in store}

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read_entry(self, index):
                return store[index]

            def write(self, offset, data):
                index = offset // 0x100000
                writes.append(index)
                base = offset - index * 0x100000
                store[index] = store[index][:base] + data + store[index][base + len(data):]

        kc, lv = module.BOOK_ENTRIES["KC"], module.BOOK_ENTRIES["OAK"]
        before = dict(store)
        plan = st.StaffPlan(staff=st.empty())
        for c in st.clubs():
            source = {9: st.club("OAK"), 22: st.club("KC")}.get(c.index, c)
            plan.clubs.append(st.ClubPlan(c, "x", source, None, c.index in (9, 22), c.book, "y", source, None,
                                          None, None))
        with patch.object(module, "OuterImage", Archive):
            receipt = st.apply_playbooks_to_image("unused.iso", plan)
        self.assertEqual(store[kc], before[lv])
        self.assertEqual(store[lv], before[kc])
        self.assertEqual(sorted(writes), sorted([kc, lv]))
        self.assertEqual({r["team"]: r["book_from"] for r in receipt["copies"]}, {"KC": "OAK", "OAK": "KC"})
        bad = dict(store)
        store[kc] = store[kc][:31] + b"\x01" + store[kc][32:]
        with patch.object(module, "OuterImage", Archive), self.assertRaises(st.StaffError):
            st.apply_playbooks_to_image("unused.iso", plan)
        store.update(bad)


@unittest.skipUnless(_XISO.is_file(), "private retail NFL 2K5 disc absent (set NFL2K5_RETAIL_XISO)")
class BuildPreflight(unittest.TestCase):
    def test_a_staff_with_a_vacancy_stops_the_build_before_any_write(self):
        import tempfile
        from mod_editor.core import mod_build, nfl2k5_roster_records as rr
        document = {"schema": rr.EDITS_SCHEMA, "edits": [], "coaches": directory_coaches(),
                    "staff": {"head_coaches": [{"team": "OAK", "coach": "Andy Reid"}]}}
        with tempfile.TemporaryDirectory(prefix="c2-staff-") as raw:
            path = Path(raw) / "roster-edits.json"
            path.write_text(json.dumps(document), encoding="utf-8", newline="\n")
            plan = mod_build.BuildPlan(str(_XISO), str(Path(raw) / "out.xiso.iso"), roster_edits=str(path))
            with self.assertRaisesRegex(ValueError, r"Coaching staff \(Rosters > Coaches\): Kansas City has no head"):
                mod_build._coach_staff_plan(plan, _XISO)
            document["staff"]["head_coaches"].append({"team": "KC", "coach": "Klint Kubiak", "playbook": "coach"})
            path.write_text(json.dumps(document), encoding="utf-8", newline="\n")
            result = mod_build._coach_staff_plan(plan, _XISO)
            self.assertTrue(result.ok)
            self.assertEqual([(h.book, d.book) for h, d in st.playbook_copies(result)], [("KC", "OAK")])
            self.assertIsNotNone(mod_build._coach_staff_document(plan))
            plan = mod_build.BuildPlan(str(_XISO), str(Path(raw) / "out.xiso.iso"), coach_ai=True,
                                       roster_edits=str(path))
            out, step = mod_build._coach_ai_decision(plan)
            self.assertTrue(out.coach_ai)
            self.assertIsNone(step)                       # every club has its 2026 coach (two of them moved)


@unittest.skipUnless(_XISO.is_file(), "private retail NFL 2K5 disc absent (set NFL2K5_RETAIL_XISO)")
class ModernCoachesFollowTheCoach(unittest.TestCase):
    """modern_coaches writes each 2026 coach's body (and the DAL/WAS picture) at the record that holds HIM."""

    def sites(self, body, teams):
        from mod_editor.core import nfl2k5_modern_coaches as mc, nfl2k5_roster_records as rr
        doc = rr.RosterDocument(bytes(body))
        with patch.object(mc, "_roster", return_value=(1000, doc)):
            return {team: (mc._coach_body_site(None, team), mc._coach_photo_site(None, team))
                    for team in ("KC", "LV", "DAL", "NYG", "SF")}

    def test_moved_fired_and_2004_rosters(self):
        from mod_editor.core import nfl2k5_roster_records as rr
        retail = rr.load_image(_XISO).to_body()
        teams = rr.RosterDocument(retail).teams
        offset = {t.abbreviation: t.coach_offset for t in teams[:32]}
        body = bytearray(retail)
        rr.apply_coach_names(body, teams, directory_coaches(), [])
        unmoved = self.sites(body, teams)
        self.assertEqual(unmoved["KC"][0][0], 1000 + offset["KC"] + 0x18)
        self.assertEqual(unmoved["DAL"][1], (1000 + offset["DAL"] + 0x40, 7007))
        staff = {"head_coaches": [{"team": "OAK", "coach": "Andy Reid"}, {"team": "KC", "coach": "Klint Kubiak"},
                                  {"team": "NE", "coach": "Brian Schottenheimer"}, {"team": "DAL", "coach": "Mike Vrabel"},
                                  {"team": "NYG", "created": "x"}],
                 "created_coaches": [{"id": "x", "first": "Pat", "last": "Shurmur"}]}
        st.apply_to_body(body, teams, staff, [])
        moved = self.sites(body, teams)
        self.assertEqual(moved["KC"][0], (1000 + offset["OAK"] + 0x18, 13))       # Reid's record is at LV now
        self.assertEqual(moved["LV"][0], (1000 + offset["KC"] + 0x18, 20))        # Kubiak's at KC
        self.assertEqual(moved["DAL"][1], (1000 + offset["NE"] + 0x40, 7007))     # Schottenheimer's picture id
        self.assertEqual(moved["NYG"], ((None, None), (None, None)))              # John Harbaugh: no club employs him
        self.assertEqual(moved["SF"], unmoved["SF"])
        old = self.sites(retail, teams)                                           # a 2004 roster: per club, as before
        self.assertEqual(old["KC"][0], (1000 + offset["KC"] + 0x18, 13))

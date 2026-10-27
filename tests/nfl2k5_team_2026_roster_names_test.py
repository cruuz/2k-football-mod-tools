"""The 2026 team roster tool (tools/nfl2k5_team_2026_roster.py): names written (listed first names, whole
surnames with their generational suffix, over-long names fitted to the game's 15-character buffers) and
roster.overrides."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "tools", ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import nfl2k5_team_2026_roster as roster  # noqa: E402


def row(first: str, last: str, full: str) -> dict:
    return {"first_name": first, "last_name": last, "full_name": full}


class WrittenNamesTest(unittest.TestCase):
    def test_overlong_hyphenated_surname_keeps_its_first_part(self):
        names, shortened = roster.written_names({7: row("Easton", "Mascarenas-Arnold", "Easton Mascarenas-Arnold")})
        self.assertEqual(names, {7: ("Easton", "Mascarenas")})
        self.assertEqual(shortened, ["Easton Mascarenas-Arnold -> Easton Mascarenas"])

    def test_overlong_hyphenated_surname_with_a_suffix(self):
        # last_name is only the start of the surname, full_name carries the whole of it and a suffix; the broadcast
        # short form keeps the suffix ("MASCARENAS JR" on the real nameplate)
        names, shortened = roster.written_names({3: row("Easton", "Mascarenas", "Easton Mascarenas-Arnold Jr.")})
        self.assertEqual(names, {3: ("Easton", "Mascarenas Jr.")})
        self.assertEqual(shortened, ["Easton Mascarenas-Arnold Jr. -> Easton Mascarenas Jr."])

    def test_overlong_surname_without_a_hyphen_keeps_the_suffix(self):
        names, shortened = roster.written_names({4: row("Al", "Abcdefghijklmnop", "Al Abcdefghijklmnop Jr.")})
        self.assertEqual(names[4], ("Al", "Abcdefghijk Jr."))
        self.assertEqual(len(names[4][1]), 15)
        self.assertEqual(shortened, ["Al Abcdefghijklmnop Jr. -> Al Abcdefghijk Jr."])

    def test_overlong_name_without_a_hyphen_is_cut_at_15(self):
        names, shortened = roster.written_names({1: row("Abcdefghijklmnopq", "Smith", "Abcdefghijklmnopq Smith")})
        self.assertEqual(names[1], ("Abcdefghijklmno", "Smith"))
        self.assertEqual(len(shortened), 1)

    def test_listed_first_name_and_suffix(self):
        names, shortened = roster.written_names({2: row("Joshua", "Conerly", "Josh Conerly Jr.")})
        self.assertEqual(names, {2: ("Josh", "Conerly Jr.")})
        self.assertEqual(shortened, [])

    def test_suffix_spellings_are_canonical(self):
        rows = {0: row("A", "One", "A One Jr"), 1: row("B", "Two", "B Two Sr."),
                2: row("C", "Three", "C Three II"), 3: row("D", "Four", "D Four III"),
                4: row("E", "Five", "E Five IV"), 5: row("F", "Six", "F Six V")}
        names, shortened = roster.written_names(rows)
        self.assertEqual([names[i][1] for i in range(6)],
                         ["One Jr.", "Two Sr.", "Three II", "Four III", "Five IV", "Six V"])
        self.assertEqual(shortened, [])

    def test_every_listed_player_gets_the_suffix(self):
        players = roster.load_suffix_players(ROOT / "data/nfl2k5_player_suffixes_2026.json")
        rows = {index: row(player["first"], player["last"], player["name"])
                for index, player in enumerate(players)}
        names, shortened = roster.written_names(rows)
        self.assertEqual(shortened, [])
        for index, player in enumerate(players):
            first, last = names[index]
            self.assertEqual((first, roster.split_suffix(last)[1]), (player["first"], player["suffix"]),
                             player["name"])
            self.assertLessEqual(len(last), 15)

    def test_whole_surname_when_last_name_is_its_start(self):
        names, shortened = roster.written_names({5: row("Sebastian", "Joseph", "Sebastian Joseph-Day")})
        self.assertEqual(names, {5: ("Sebastian", "Joseph-Day")})
        self.assertEqual(shortened, [])


class NameplateWidthTest(unittest.TestCase):
    # The jersey nameplate compositor (0x1C2140) draws a player's last name at the kit's NAME metric
    # advances into one of the 22 native 256x32 generated surfaces (o3c164..185). These are the widest
    # advances per character across the 634 NAME metric objects of the released v0.6.1 disc; the space
    # uses the hyphen's advance (NAME metric index 1), and a period is skipped with no advance. The
    # uf2 hyphen rule (a solid hyphen glyph) changes the atlas art only, not these advances.
    WIDTH = 256
    ADVANCE = {"'": 22, "-": 50, "A": 17, "B": 15, "C": 14, "D": 15, "E": 14, "F": 14, "G": 16, "H": 17,
               "I": 8, "J": 14, "K": 16, "L": 14, "M": 23, "N": 18, "O": 17, "P": 15, "Q": 17, "R": 16,
               "S": 14, "T": 16, "U": 15, "V": 18, "W": 25, "X": 17, "Y": 17, "Z": 16}

    def width(self, text: str) -> int:
        return sum(0 if c == "." else self.ADVANCE["-" if c == " " else c] for c in text.upper())

    def test_every_listed_surname_fits_the_256_pixel_nameplate(self):
        players = roster.load_suffix_players(ROOT / "data/nfl2k5_player_suffixes_2026.json")
        rows = {index: row(player["first"], player["last"], player["name"])
                for index, player in enumerate(players)}
        names, _ = roster.written_names(rows)
        widest = ("", 0)
        for index, player in enumerate(players):
            last = names[index][1]
            self.assertTrue(set(last) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz '-."), last)
            width = self.width(last)
            self.assertLessEqual(width, self.WIDTH, f"{last} renders {width}px on a {self.WIDTH}px nameplate")
            widest = max(widest, (last, width), key=lambda pair: pair[1])
        self.assertEqual(widest, ("Washington Jr.", 246))


class CommentarySuffixTests(unittest.TestCase):
    def test_every_listed_surname_matches_the_same_audio_key(self):
        from mod_editor.core import nfl2k5_roster_records as rr
        players = roster.load_suffix_players(ROOT / "data/nfl2k5_player_suffixes_2026.json")
        for player in players:
            self.assertEqual(rr.commentary_surname(f"{player['last']} {player['suffix']}"),
                             rr.commentary_surname(player["last"]), player["name"])

    def test_cue_uses_the_surname_only(self):
        bank = {"harrison": 123, "thomas": 456, "cushenberry": 789}
        self.assertEqual(roster.pbp_for("Harrison Jr.", 18, bank), (123, "recorded surname bank"))
        self.assertEqual(roster.pbp_for("Thomas V", 24, bank), (456, "recorded surname bank"))
        self.assertEqual(roster.pbp_for("Cushenberry III", 79, bank), (789, "recorded surname bank"))
        self.assertEqual(roster.pbp_for("Harrison", 18, bank), roster.pbp_for("Harrison Jr.", 18, bank))

    def test_suffix_is_not_part_of_the_audio_key(self):
        from mod_editor.core import nfl2k5_roster_records as rr
        for text, key in (("Harrison Jr.", "harrison"), ("Walker III", "walker"), ("DeWalt IV", "dewalt"),
                          ("Thomas V", "thomas"), ("Pitts Sr.", "pitts"), ("Foster Jr", "foster")):
            self.assertEqual(rr.commentary_surname(text), key)


class SuffixDocumentTests(unittest.TestCase):
    def players(self):
        return [
            {"name": "Marvin Harrison Jr.", "first": "Marvin", "last": "Harrison", "suffix": "Jr."},
            {"name": "Cedrick Wilson Jr.", "first": "Cedrick", "last": "Wilson", "suffix": "Jr."},
            {"name": "Robert Henry Jr.", "first": "Robert", "last": "Henry", "suffix": "Jr."},
        ]

    def document(self):
        from mod_editor.core import nfl2k5_roster_records as rr
        return {
            "schema": rr.EDITS_SCHEMA,
            "edits": [
                {"pool": "primary", "index": 5, "first": "Bryant", "last": "Johnson", "fields": {},
                 "names": {"first": "Bly", "last": "Bly"}},
                {"pool": "primary", "index": 5, "first": "Bly", "last": "Bly", "fields": {"jersey": 18},
                 "names": {"first": "Marvin", "last": "Harrison"}},
                {"pool": "primary", "index": 5, "first": "Marvin", "last": "Harrison",
                 "fields": {"height": 75}},
                {"pool": "primary", "index": 9, "first": "Cedrick", "last": "Wilson", "fields": {}},
                {"pool": "primary", "index": 7, "first": "Robert", "last": "Henry", "fields": {}},
            ],
            "college_updates": [{"pool": "primary", "index": 5, "first": "Marvin", "last": "Harrison",
                                 "college": "Ohio State"}],
            "free_agent_pool": [{"pool": "primary", "index": 9, "first": "Cedrick", "last": "Wilson"}],
            "special_teams": [{"team_index": 0, "team": "SF", "roles": {
                "kr1": {"pool": "primary", "index": 5, "first": "Marvin", "last": "Harrison"}}}],
            "franchise_history": {"players": [{"pool": "primary", "index": 5, "first": "Marvin",
                                               "last": "Harrison"}]},
            "moves": [{"pool": "primary", "index": 5, "first": "Marvin", "last": "Harrison",
                       "free_agent": True}],
            "roster_refresh": {
                "players": [
                    {"index": 5, "first": "Marvin", "last": "Harrison", "source_name": "Marvin Harrison Jr.",
                     "new": False},
                    {"index": 9, "first": "Cedrick", "last": "Wilson", "source_name": "Cedrick Wilson",
                     "new": False},
                    {"index": 7, "first": "Robert", "last": "Henry", "source_name": "Robert Henry Jr.",
                     "new": True},
                ],
                "identity_guards": [[5, "Marvin", "Harrison", "2002-08-11"],
                                    [9, "Cedrick", "Wilson", "1996-03-15"]],
                "contract_initializations": [{"index": 7, "name": "Robert Henry Jr."}],
            },
        }

    def test_suffix_reaches_every_later_identity_check(self):
        out, receipt = roster.apply_suffixes(self.document(), self.players())
        self.assertEqual(receipt["players"], 3)
        self.assertEqual(receipt["name_pairs_added"], 1)
        finals = [entry for entry in out["edits"] if entry.get("index") == 5
                  and (entry.get("names") or {}).get("last") == "Harrison Jr."]
        self.assertEqual(len(finals), 1)
        layer = [entry for entry in out["edits"] if entry.get("index") == 5 and entry.get("fields", {}).get("height") == 75]
        self.assertEqual(len(layer), 1)
        self.assertEqual(layer[0]["last"], "Harrison Jr.")
        self.assertEqual(out["edits"][0]["last"], "Johnson")
        added = [entry for entry in out["edits"]
                 if entry.get("index") == 9 and (entry.get("names") or {}).get("last") == "Wilson Jr."]
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]["names"], {"first": "Cedrick", "last": "Wilson Jr."})
        self.assertEqual(out["free_agent_pool"][0]["last"], "Wilson Jr.")
        self.assertEqual(out["college_updates"][0]["last"], "Harrison Jr.")
        self.assertEqual(out["special_teams"][0]["roles"]["kr1"]["last"], "Harrison Jr.")
        self.assertEqual(out["franchise_history"]["players"][0]["last"], "Harrison Jr.")
        self.assertEqual(out["moves"][0]["last"], "Harrison")
        rows = {row["index"]: row for row in out["roster_refresh"]["players"]}
        self.assertEqual(rows[5]["last"], "Harrison Jr.")
        self.assertEqual(rows[7]["last"], "Henry Jr.")
        self.assertEqual(rows[9]["last"], "Wilson Jr.")
        guards = {guard[0]: guard for guard in out["roster_refresh"]["identity_guards"]}
        self.assertEqual(guards[5][2], "Harrison Jr.")
        self.assertEqual(guards[9][2], "Wilson Jr.")
        self.assertEqual(out["roster_refresh"]["contract_initializations"][0]["name"], "Robert Henry Jr.")

    def test_applying_twice_changes_nothing(self):
        once, _ = roster.apply_suffixes(self.document(), self.players())
        twice, receipt = roster.apply_suffixes(once, self.players())
        self.assertEqual(twice, once)
        self.assertEqual(receipt["name_pairs_added"], 0)

    def test_a_listed_player_absent_from_the_document_is_refused(self):
        players = self.players() + [{"name": "Nobody Here Jr.", "first": "Nobody", "last": "Here",
                                     "suffix": "Jr."}]
        with self.assertRaises(SystemExit):
            roster.apply_suffixes(self.document(), players)


class OverridesTest(unittest.TestCase):
    def rows(self):
        return [{"gsis_id": "00-0039489", "full_name": "Hayden Rucci", "jersey_number": "83", "status": "ACT"},
                {"gsis_id": "00-0034375", "full_name": "David Njoku", "jersey_number": "83", "status": "ACT"}]

    def test_jersey_override_corrects_the_row(self):
        rows = self.rows()
        notes = roster.apply_source_overrides(rows, {"00-0039489": {"jersey": 40}})
        self.assertEqual(rows[0]["jersey_number"], "40")
        self.assertEqual(rows[1]["jersey_number"], "83")
        self.assertEqual(notes, ["00-0039489 Hayden Rucci: jersey_number '83' -> '40'"])

    def test_rating_override_after_the_model(self):
        rows = self.rows()
        roster.apply_source_overrides(rows, {"00-0034375": {"speed": 90}})
        rows[1]["ratings"] = {"speed": 70}
        notes = roster.apply_rating_overrides(rows, {"00-0034375": {"speed": 90}})
        self.assertEqual(rows[1]["ratings"]["speed"], 90)
        self.assertEqual(notes, ["00-0034375 David Njoku: speed 70 -> 90"])

    def test_unknown_field_is_refused(self):
        with self.assertRaises(SystemExit):
            roster.apply_source_overrides(self.rows(), {"00-0039489": {"jersy": 40}})

    def test_player_not_on_the_team_is_a_warning(self):
        notes = roster.apply_source_overrides(self.rows(), {"00-0000001": {"jersey": 1}})
        self.assertEqual(notes, ["00-0000001: not on the team's rows (ignored)"])


if __name__ == "__main__":
    unittest.main()

"""The 2026 team roster tool (tools/nfl2k5_team_2026_roster.py): names written (listed first names, whole surnames,
generational suffixes dropped, over-long names fitted to the game's 15-character buffers) and roster.overrides."""

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
        # last_name is only the start of the surname, full_name carries the whole of it and a suffix
        names, shortened = roster.written_names({3: row("Easton", "Mascarenas", "Easton Mascarenas-Arnold Jr.")})
        self.assertEqual(names, {3: ("Easton", "Mascarenas")})
        self.assertEqual(shortened, ["Easton Mascarenas-Arnold Jr. -> Easton Mascarenas"])

    def test_overlong_name_without_a_hyphen_is_cut_at_15(self):
        names, shortened = roster.written_names({1: row("Abcdefghijklmnopq", "Smith", "Abcdefghijklmnopq Smith")})
        self.assertEqual(names[1], ("Abcdefghijklmno", "Smith"))
        self.assertEqual(len(shortened), 1)

    def test_listed_first_name_and_no_suffix(self):
        names, shortened = roster.written_names({2: row("Joshua", "Conerly", "Josh Conerly Jr.")})
        self.assertEqual(names, {2: ("Josh", "Conerly")})
        self.assertEqual(shortened, [])

    def test_whole_surname_when_last_name_is_its_start(self):
        names, shortened = roster.written_names({5: row("Sebastian", "Joseph", "Sebastian Joseph-Day")})
        self.assertEqual(names, {5: ("Sebastian", "Joseph-Day")})
        self.assertEqual(shortened, [])


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

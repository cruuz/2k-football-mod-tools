"""Head coach names through the roster edits document (``coaches``), on the user's retail roster.

The coach strings are one back-to-back region of singly referenced strings; apply_coach_names rewrites it as one
piece. These tests need the private retail disc (skipped without it)."""
from __future__ import annotations

import os
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402

_XISO = Path(os.environ.get("NFL2K5_RETAIL_XISO", str(ROOT / "ESPN NFL 2K5 (USA).xiso.iso")))


@unittest.skipUnless(_XISO.is_file(), "private retail NFL 2K5 disc absent (set NFL2K5_RETAIL_XISO)")
class CoachNameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import nfl_coach_roster_name_workflow as cw
        cls.cw = cw
        cls.base = rr.load_image(_XISO).to_body()

    def coaches(self, body: bytes) -> list[tuple[str, str, str]]:
        tables = self.cw.parse_roster_body(body)
        records = self.cw.parse_coach_records(body, tables, self.cw.known_string_pointer_references(body, tables))
        out = []
        for index, record in enumerate(records):
            offset = tables["coaches"]["offset"] + index * self.cw.COACH_STRIDE
            bio = self.cw.utf16z(body, self.cw.relative_target(body, offset + 8, "bio"), "bio")
            out.append((record["first_name"], record["last_name"], bio))
        return out

    def test_the_region_takes_every_2026_coach_and_nothing_else_moves(self) -> None:
        entries = [{"team": "NYG", "first": "John", "last": "Harbaugh"},
                   {"team": "DAL", "first": "Brian", "last": "Schottenheimer"},
                   {"team": "MIN", "first": "Kevin", "last": "O'Connell", "bio": ["Line one", "Line two"]}]
        new, receipt = rr.apply_body(self.base, {"schema": rr.EDITS_SCHEMA, "edits": [], "coaches": entries})
        self.assertEqual(receipt["log"], [])
        self.assertEqual(receipt["coach_names_written"], 3)
        coaches = self.coaches(new)
        self.assertEqual(coaches[15][:2], ("John", "Harbaugh"))
        self.assertEqual(coaches[15][2], "", "a replaced coach's 2004 biography is cleared")
        self.assertEqual(coaches[11][:2], ("Brian", "Schottenheimer"))
        self.assertEqual(coaches[31], ("Kevin", "O'Connell", "Line one"))
        self.assertEqual(self.coaches(self.base)[13], coaches[13], "an untouched coach reads the same")
        # the players, teams and every other string keep their bytes
        document = rr.RosterDocument(new)
        self.assertEqual(len(document.players), len(rr.RosterDocument(self.base).players))
        tables = self.cw.parse_roster_body(new)
        coach_table = tables["coaches"]
        pointer_fields = {coach_table["offset"] + i * self.cw.COACH_STRIDE + f
                          for i in range(coach_table["count"]) for f in (0, 4, 8, 12, 16)}
        region = [t for f in pointer_fields for t in [self.cw.relative_target(self.base, f, "c")]]
        lo = min(region)
        hi = max(region) + 2 * (len(self.cw.utf16z(self.base, max(region), "c")) + 1)
        for index, (a, b) in enumerate(zip(self.base, new)):
            if a != b:
                inside = lo <= index < hi or any(f <= index < f + 4 for f in pointer_fields)
                self.assertTrue(inside, f"byte 0x{index:x} outside the coach region changed")

    def test_career_numbers_land_in_the_record(self) -> None:
        fields = {"wins": 180, "losses": 113, "ties": 0, "total_seasons": 18, "playoff_wins": 13,
                  "playoff_losses": 11, "super_bowl_wins": 1, "super_bowls": 1}
        new, receipt = rr.apply_body(self.base, {"schema": rr.EDITS_SCHEMA, "edits": [], "coaches": [
            {"team": "NYG", "first": "John", "last": "Harbaugh", "fields": fields}]})
        self.assertEqual(receipt["log"], [])
        tables = self.cw.parse_roster_body(new)
        record = tables["coaches"]["offset"] + 15 * self.cw.COACH_STRIDE
        for name, value in fields.items():
            self.assertEqual(struct.unpack_from("<H", new, record + rr.COACH_NUMBER_FIELDS[name])[0], value, name)
        self.assertEqual(struct.unpack_from("<H", new, record + 0x40)[0], 7018, "the identity code stays")
        _new, bad = rr.apply_body(self.base, {"schema": rr.EDITS_SCHEMA, "edits": [], "coaches": [
            {"team": "NYG", "first": "John", "last": "Harbaugh", "fields": {"photo": 1}}]})
        self.assertEqual(bad["coach_names_written"], 0, "the identity code is not a writable number")

    def test_an_unknown_team_is_logged_and_writes_nothing(self) -> None:
        new, receipt = rr.apply_body(self.base, {"schema": rr.EDITS_SCHEMA, "edits": [],
                                                 "coaches": [{"team": "XYZ", "first": "A", "last": "B"}]})
        self.assertEqual(receipt["coach_names_written"], 0)
        self.assertTrue(any("XYZ" in line for line in receipt["log"]))
        self.assertEqual(new, self.base)

    def test_text_that_cannot_fit_the_region_writes_nothing(self) -> None:
        huge = "x" * 4000
        new, receipt = rr.apply_body(self.base, {"schema": rr.EDITS_SCHEMA, "edits": [], "coaches": [
            {"team": "NYG", "first": "John", "last": "Harbaugh", "bio": [huge]}]})
        self.assertEqual(receipt["coach_names_written"], 0)
        self.assertTrue(any("region holds" in line for line in receipt["log"]))
        self.assertEqual(new, self.base)
        self.assertEqual(struct.unpack_from("<I", new, 0)[0], struct.unpack_from("<I", self.base, 0)[0])


if __name__ == "__main__":
    unittest.main()

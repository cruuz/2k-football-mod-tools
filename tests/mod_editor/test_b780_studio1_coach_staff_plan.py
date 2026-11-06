"""b780 studio1: the coaching staff plan and the writer agree about a grown roster.

``nfl2k5_coach_staff.plan`` promises "no errors means apply_to_body writes exactly this plan", and Rosters > Coaches and the
build's preflight both trust it.  A created coach cannot be written on a roster whose capacity arena has grown (the
SOFTDRINK pack disc, any built disc): the text region cannot be laid out again.  The plan used to say nothing, so the page
offered "Create a new coach" on the pack disc, the preflight passed, and the build stopped in its roster step.  Stubbed
roster records, so no disc is needed.
"""

from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_coach_staff as st  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402

GROWN = ("a created coach can be written only on a roster before its capacity growth (build from your retail disc); "
         "this roster has grown")


@dataclass
class _Coach:
    name: str
    directory_id: str | None


def _records():
    """The 32 clubs' 2026 head coaches, as a roster reads them."""
    return {club.index: _Coach(row["name"], row["id"]) for club, row in
            zip(st.clubs(), st.head_coach_directory())}


CREATED = {
    "head_coaches": [{"team": "NYG", "created": "pat"}],
    "created_coaches": [{"id": "pat", "first": "Pat", "last": "Shurmur", "style": "NYG"}],
}
SWAP = {"head_coaches": [{"team": "KC", "coach": "Nick Sirianni"}, {"team": "PHI", "coach": "Andy Reid"}]}


class GrownRosterPlanTests(unittest.TestCase):
    def plan(self, staff, size):
        with mock.patch.object(st, "coach_records", return_value=_records()):
            return st.plan(staff, bytes(size), None)

    def test_a_created_coach_on_a_grown_roster_is_an_error_in_the_plan(self) -> None:
        retail_size = rr._coach_tool().ROST_BODY_SIZE
        grown = self.plan(CREATED, retail_size + 0x40000)           # the capacity arena of a built disc
        self.assertEqual(grown.errors, [GROWN])
        self.assertFalse(grown.ok)

    def test_the_same_staff_on_a_retail_sized_roster_plans(self) -> None:
        plan = self.plan(CREATED, rr._coach_tool().ROST_BODY_SIZE)
        self.assertEqual(plan.errors, [])
        self.assertTrue(any("created coach" in note for note in plan.notes))

    def test_moves_of_the_clubs_own_coaches_still_plan_on_a_grown_roster(self) -> None:
        plan = self.plan(SWAP, rr._coach_tool().ROST_BODY_SIZE + 0x40000)
        self.assertEqual(plan.errors, [])
        self.assertEqual(self.plan(st.empty() if hasattr(st, "empty") else {}, 100).errors, [])

    def test_apply_to_body_refuses_it_with_the_same_words_before_it_writes(self) -> None:
        body = bytearray(rr._coach_tool().ROST_BODY_SIZE + 0x40000)
        with mock.patch.object(st, "coach_records", return_value=_records()):
            with self.assertRaises(st.StaffError) as caught:
                st.apply_to_body(body, ("stub teams",), CREATED, [])
        self.assertIn(GROWN, str(caught.exception))
        self.assertEqual(bytes(body), bytes(len(body)))             # nothing was written


if __name__ == "__main__":
    unittest.main()

"""Stale per-team and per-stadium booth lines (b81 sb-booth, audit part 2). No emulator.

Retail-free tests check the rule table against the pinned retail context lists and the decisions on synthetic disc
facts. Retail tests (skipped without the user-owned USA disc folder) read the real ``lines`` speech index: every rule
key uses exactly its pinned lists, no other key shares them, the patch changes only rule contexts, a second patch
changes nothing, a foreign list refuses, and a synthetic disc carrying the real speech index round-trips.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import struct
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import build_steps  # noqa: E402
from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_stale_speech as s  # noqa: E402
from mod_editor.core import nfl2k5_stadium_welcome as w  # noqa: E402

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", ROOT / "extracted")) / "ESPN NFL 2K5 (USA)" / "vc_53450030"
HAVE_RETAIL = (RETAIL / "0").is_file()


def retail_facts() -> dict:
    teams = {c: {"city": s.RETAIL_PLACES.get(c, "Somewhere"), "nickname": s.RETAIL_NICKNAMES.get(c, "Team"),
                 "coach": s.RETAIL_COACHES[c]} for c in s.TEAMS_2004}
    rows = {n: name for n, name in s.RETAIL_ROWS.items()}
    return {"rows": rows, "teams": teams}


def modern_facts() -> dict:
    facts = retail_facts()
    facts["rows"] = {n: f"Renamed {n}" for n in s.RETAIL_ROWS}
    for c, team in facts["teams"].items():
        team["coach"] = f"Coach {c}"
    facts["teams"][20]["city"] = "Las Vegas"
    facts["teams"][23]["city"] = "Los Angeles"
    facts["teams"][24]["city"] = "Los Angeles"
    facts["teams"][29]["nickname"] = "Commanders"
    return facts


class Table(unittest.TestCase):
    def test_every_rule_context_is_in_its_retail_lists(self):
        for key, rule in s.RULES.items():
            values = set()
            for index in s._LIST_KEYS[key]:
                values |= set(s.retail_values(index))
            self.assertEqual(sorted(set(rule) - values), [], key)
            if key != 9455:                                               # only 9455 must drop its generic
                self.assertNotIn(999, rule)
        self.assertEqual(s.RULES[38506], s.RULES[38550])                  # one shared list
        self.assertEqual(sorted(s.RULES[13850]), sorted(s.TEAMS_2004))

    def test_washington_keeps_its_correct_calls(self):
        """Only the 'Redskins' lines with lists of their own move; none of the PA 'Washington' keys is touched."""
        for key in (9003, 9012, 9015, 9017, 9018, 9051, 9213, 9252, 9333, 9335, 9336, 9400, 38502):
            self.assertNotIn(29, s.RULES.get(key, {}), key)
        for key in (9454, 38507, 38540, 38541, 38247, 38248, 38503, 38539, 38583, 38585, 38853, 38854):
            self.assertNotIn(key, s.RULES)                                # their generic says "created team/players"
        shared = (9405, 9413, 9424, 9425, 9426, 9474, 9475, 9476, 38851, 38852, 38859, 38860, 38996, 38997, 38998,
                  38999, 39360, 39361, 39362, 39363, 53051, 53052, 51010, 51112, 51155, 51161)
        for key in shared:                                                # shared lists, all "Redskins" lines
            self.assertEqual(s.RULES[key], {29: s.N}, key)

    def test_decisions_follow_the_disc(self):
        retail = s.decide(retail_facts())
        self.assertEqual({k: sorted(v) for k, v in retail.items()},
                         {9453: [2, 4, 16, 21, 22, 25], 38506: [25], 38550: [25]})      # only 'always'
        modern = s.decide(modern_facts())
        self.assertEqual(sorted(modern[13850]), sorted(s.TEAMS_2004))
        self.assertEqual(sorted(modern[38502]), [20, 23, 24])
        for key in (512, 1201, 9414, 9427, 9444, 9456, 9467, 9468, 50020, 9424, 38859, 39361, 51161):
            self.assertEqual(sorted(modern[key]), [29])
        self.assertNotIn(29, s.RULES[38800])                              # "suburban Washington, D.C." stays
        self.assertNotIn(20, modern[38803])                               # the Raiders' blurb names no city: kept

    def test_the_2004_team_intro_is_skipped_for_real_clubs_only(self):
        modern = s.decide(modern_facts())[9455]
        self.assertTrue(set(s.TEAMS_2004) <= set(modern))
        self.assertIn(999, modern)                                         # else they would fall back to "created team"
        self.assertFalse({c for c in modern if 100 <= c <= 168})           # the dated classic teams keep their intro
        self.assertNotIn(9455, s.decide(retail_facts()))

    def test_list_state(self):
        index = 2302
        retail = s.retail_values(index)
        self.assertEqual(s.list_state(index, retail), "retail")
        applied = tuple(s.SKIP if v in (1, 3) else v for v in retail)
        self.assertEqual(s.list_state(index, applied), "applied")
        foreign = tuple(s.SKIP if v == 9 else v for v in retail)          # Ford Field is not a rule context
        self.assertEqual(s.list_state(index, foreign), "foreign")


class BuildWiring(unittest.TestCase):
    def test_step_runs_after_the_welcome_on_every_disc_build(self):
        source = (ROOT / "mod_editor" / "core" / "mod_build.py").read_text(encoding="utf-8")
        lines = source.splitlines()
        call = [i for i, line in enumerate(lines) if '_optional(receipt, target, progress, "stale_speech")' in line]
        welcome = [i for i, line in enumerate(lines) if '_optional(receipt, target, progress, "stadium_welcome")' in line]
        self.assertEqual((len(call), len(welcome)), (1, 1))
        self.assertLess(welcome[0], call[0])
        gate = max(i for i in range(call[0]) if re.match(r"    if \S", lines[i]))
        self.assertEqual(lines[gate].strip(), "if tt.is_disc_image(target):")
        self.assertIn("stale_speech", mod_build.OPTIONAL_STEPS)
        self.assertIn("stale_speech", build_steps.STEP_LABELS)
        self.assertTrue(build_steps.KEPT["stale_speech"].startswith("Your "))


@unittest.skipUnless(HAVE_RETAIL, "needs the user-owned USA disc folder")
class Retail(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from nfl2k5_playbook_position_recode import OuterImage
        with OuterImage(RETAIL) as archive:
            cls.outer3 = archive.read_entry(w.SPCI_OUTER_INDEX)
        at = w.find_spci(cls.outer3)
        cls.at = at
        cls.body = cls.outer3[at + 0x20:at + 0x20 + w.SPCI_STORED]

    def test_pinned_lists_and_ownership(self):
        plan = s.plan_lists(self.body)
        self.assertEqual(sorted(plan), sorted({i for v in s._LIST_KEYS.values() for i in v}))
        for index, values in plan.items():
            self.assertEqual(values, s.retail_values(index))

    def test_patch_is_idempotent_and_touches_only_rule_contexts(self):
        decisions = s.decide(modern_facts())
        once, receipt = s.patch_body(self.body, decisions)
        self.assertEqual(receipt["changed_bytes"], 352)
        by_key, _users, lists = s.context_lists(once)
        for index in s.plan_lists(once):
            touched = any(c in s.retail_values(index) for key, ctxs in decisions.items()
                          if index in s._LIST_KEYS[key] for c in ctxs)
            self.assertEqual(s.list_state(index, s.list_values(once, lists, index)),
                             "applied" if touched else "retail", index)   # 9414's first-variant list has no 29
        changed = [i for i, (a, b) in enumerate(zip(self.body, once)) if a != b]
        self.assertTrue(all(once[i] == 0xFF for i in changed))
        twice, receipt = s.patch_body(once, decisions)
        self.assertEqual(twice, once)

    def test_refuses_a_foreign_list(self):
        _by_key, _users, lists = s.context_lists(self.body)
        out = bytearray(self.body)
        at = lists + 2 * 2302 + 2 + 2 * s.retail_values(2302).index(9)  # Ford Field, not a rule context
        struct.pack_into("<H", out, at, 77)
        with self.assertRaises(s.StaleSpeechError):
            s.plan_lists(bytes(out))

    def test_round_trip_on_a_synthetic_disc(self):
        from nfl2k5_xiso_fixture import SyntheticXiso
        with tempfile.TemporaryDirectory() as tmp:
            entries = [(0, b"\x00" * 16), (1, b"\x01" * 16), (2, b"\x02" * 16), (3, self.outer3), (4, b"\x04" * 16)]
            size = 0x800 * 8 + len(self.outer3)
            size += -size % 0x800
            image = SyntheticXiso(Path(tmp), entries, pack_sizes=(size,), pack_sectors=(64,))
            before = image.path.read_bytes()
            with mock.patch.object(s, "disc_facts", return_value=modern_facts()):
                receipt = s.apply_to_image(image.path)
                self.assertEqual((receipt["state"], receipt["changed_bytes"]), ("applied", 352))
                after = image.path.read_bytes()
                self.assertEqual(sum(1 for x, y in zip(before, after) if x != y), 352)
                self.assertEqual(s.apply_to_image(image.path)["changed_bytes"], 0)
            with mock.patch.object(s, "disc_facts", side_effect=ValueError("no roster")):
                self.assertEqual(s.apply_to_image(image.path)["state"], "skipped")
            self.assertEqual(image.path.read_bytes(), after)


if __name__ == "__main__":
    unittest.main()

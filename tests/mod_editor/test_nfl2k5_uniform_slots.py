"""Uniform style slots (job u3s, beta 77): the game's cycle and label rules, slot classes, the plan rules and the
committed slot decisions.

The model tests need nothing. The native tests run the game's own Team Select routines (0xE2FB0, 0xE2F70, 0xE3700 ->
0xE3530 with its real formatter, 0xE2F20) under Unicorn on the retail executable and check the model against them.
The disc census test reads the SOFTDRINK v0.5 image and the retail image; it is slow (both discs are read through
the XDVDFS reader) and runs only with ``U3S_DISC_TESTS=1``."""

from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import sys
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tools"), str(REPO / "tools/b77")]

from mod_editor.core import nfl2k5_uniform_slots as us  # noqa: E402

RETAIL_ROOT = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted"))
XBE = RETAIL_ROOT / "ESPN NFL 2K5 (USA)" / "default.xbe"
V05_DISC = Path(os.environ.get("NFL2K5_V05_DISC",
                               "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.5 (2026-10-06).xiso.iso"))
RETAIL_DISC = Path(os.environ.get("NFL2K5_RETAIL_DISC", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
DECISIONS = REPO / "data/nfl2k5_uniform_slots_2026.json"
ALTERNATES = REPO / "data/nfl2k5_uniform_alternates_2026.json"

try:
    import unicorn  # noqa: F401
    HAVE_UNICORN = True
except Exception:  # noqa: BLE001
    HAVE_UNICORN = False


def pairs_from(table: dict[int, tuple[int, int]]) -> list[tuple[int, int]]:
    return [table.get(s, (0, 0)) for s in range(1, us.MAX_STYLE + 1)]


def record_with(table: dict[int, tuple[int, int]]) -> bytes:
    record = bytearray(us.TEAM_SIZE)
    for style, (first, last) in table.items():
        struct.pack_into("<HH", record, us.TABLE + 4 * (style - 1), first, last)
    return bytes(record)


def franchise(owners=None, kits=None, table=None, retail_kits=None) -> us.Franchise:
    table = table or {1: (1981, 1997), 2: (1979, 1980), 3: (2004, 1), 4: (2004, 2)}
    f = us.Franchise("06", "CIN", 2, pairs_from(table))
    f.kits = {s: (100, 100) for s in (kits if kits is not None else [0, 1, 2, 3, 4, 6])}
    f.retail_kits = set(retail_kits if retail_kits is not None else [0, 1, 2, 3, 4, 6])
    f.members = {s: 9 for s in f.kits}
    f.owners = {0: ["2026 primary set (style 0)"]}
    for style, why in (owners or {}).items():
        f.owners.setdefault(style, []).append(why)
    return f


class LabelAndCycleModelTests(unittest.TestCase):
    def test_labels_follow_the_four_rules(self) -> None:
        self.assertEqual(us.style_label(0), "Current Uniform")
        self.assertEqual(us.style_label(1, 1981, 1997), "1981 - 1997 Uniform")
        self.assertEqual(us.style_label(3, 1995, 1995), "1995 Uniform")
        self.assertEqual(us.style_label(5, 2026, 1), "2026  Alternate 1")      # the retail format has two spaces
        self.assertEqual(us.style_label(9, 2004, 2), "2004  Alternate 2")

    def test_the_cycle_skips_zero_pairs_and_the_loader_steps_down(self) -> None:
        pairs = pairs_from({1: (2001, 2002), 2: (2004, 1), 5: (2026, 1)})
        self.assertEqual(us.offered_styles(pairs), [0, 1, 2, 5])
        self.assertEqual([us.loaded_style(pairs, s) for s in range(7)], [0, 1, 2, 2, 2, 5, 5])
        self.assertEqual(us.offered_labels(pairs)[-1], (5, "2026  Alternate 1"))

    def test_retail_alternates_are_told_from_eras(self) -> None:
        self.assertTrue(us.is_retail_alternate((2004, 1)))
        self.assertTrue(us.is_retail_alternate((2026, 3)))
        self.assertFalse(us.is_retail_alternate((1995, 1995)))
        self.assertFalse(us.is_retail_alternate((1960, 1963)))


class SlotClassTests(unittest.TestCase):
    def test_free_slots_by_class(self) -> None:
        f = franchise(owners={1: "historic team file h-06-1981-bengals-1.iff (style byte)",
                              8: "m1 spare style"}, kits=[0, 1, 2, 3, 4, 6, 7, 8], retail_kits=[0, 1, 2, 3, 4, 6, 7])
        free = us.free_slots(f)
        self.assertEqual(free["retail_alternates"], [3, 4])
        self.assertEqual(free["eras"], [2])
        self.assertEqual(free["orphans"], [6, 7])
        self.assertEqual(free["append"], [5, 9, 10, 11, 12, 13, 14])

    def test_an_orphan_needs_all_nine_members(self) -> None:
        f = franchise()
        f.members[6] = 8
        self.assertEqual(us.free_slots(f)["orphans"], [])


class PlanRuleTests(unittest.TestCase):
    def plan(self, *assignments) -> dict:
        return {"teams": {"CIN": {"assignments": list(assignments)}}}

    def test_a_good_plan_passes(self) -> None:
        f = franchise()
        plan = self.plan({"style": 4, "method": "repurpose", "pair": [2026, 1]},
                         {"style": 6, "method": "enable_orphan", "pair": [2026, 2]},
                         {"style": 9, "method": "append", "pair": [2026, 3]})
        self.assertEqual(us.validate_plan(plan, {"06": f}), [])

    def test_owned_slots_missing_art_and_repeats_are_refused(self) -> None:
        f = franchise(owners={1: "Anniversary moment row 12 home (bengals 1988) kit"})
        cases = [
            ({"style": 1, "method": "repurpose", "pair": [2026, 1]}, "owned by"),
            ({"style": 5, "method": "repurpose", "pair": [2026, 1]}, "repurpose needs"),
            ({"style": 3, "method": "enable_orphan", "pair": [2026, 1]}, "enable_orphan needs"),
            ({"style": 6, "method": "append", "pair": [2026, 1]}, "append needs"),
            ({"style": 15, "method": "repurpose", "pair": [2026, 1]}, "not a style"),
            ({"style": 4, "method": "paint", "pair": [2026, 1]}, "unknown method"),
        ]
        for assignment, expected in cases:
            problems = us.validate_plan(self.plan(assignment), {"06": f})
            self.assertTrue(any(expected in p for p in problems), (assignment, problems))
        problems = us.validate_plan(self.plan({"style": 4, "method": "repurpose", "pair": [2026, 1]},
                                              {"style": 4, "method": "repurpose", "pair": [2026, 2]}), {"06": f})
        self.assertTrue(any("used twice" in p for p in problems), problems)

    def test_a_shipped_alternate_is_only_accepted_as_authored(self) -> None:
        f = franchise(table={1: (1981, 1997), 3: (2026, 1)})
        f.owners[3] = ["2026 alternate already on the disc (2026  Alternate 1)"]
        self.assertEqual(us.validate_plan(self.plan({"style": 3, "method": "authored"}), {"06": f}), [])
        self.assertTrue(us.validate_plan(self.plan({"style": 3, "method": "repurpose", "pair": [2026, 2]}),
                                         {"06": f}))

    def test_a_team_missing_from_the_plan_is_reported(self) -> None:
        self.assertEqual(us.validate_plan({"teams": {}}, {"06": franchise()}), ["CIN: missing from the plan"])

    def test_roster_entries_relabel_and_enable(self) -> None:
        f = franchise()
        plan = self.plan({"style": 4, "method": "repurpose", "pair": [2026, 1]},
                         {"style": 6, "method": "enable_orphan", "pair": [2026, 2]},
                         {"style": 9, "method": "append", "pair": [2026, 3]})
        entries = us.roster_team_entries(plan, {"06": f})
        self.assertEqual(entries, [{"team_index": 2, "uniform_years": {"4": [2026, 1], "6": [2026, 2]},
                                    "enable_styles": [6]}])
        self.assertEqual(us.plan_pairs(f, plan["teams"]["CIN"])[8], (2026, 3))


class CommittedDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.doc = json.loads(DECISIONS.read_text(encoding="utf-8"))
        cls.alternates = json.loads(ALTERNATES.read_text(encoding="utf-8"))

    def test_every_team_has_a_well_formed_entry(self) -> None:
        self.assertEqual(self.doc["schema"], "nfl2k5_uniform_slots_2026/v1")
        self.assertEqual(sorted(self.doc["teams"]), sorted(us.FRANCHISES.values()))
        for abbr, entry in self.doc["teams"].items():
            styles = [a["style"] for a in entry["assignments"]]
            self.assertEqual(len(styles), len(set(styles)), abbr)
            for a in entry["assignments"]:
                self.assertIn(a["method"], us.METHODS, abbr)
                self.assertTrue(1 <= a["style"] <= us.MAX_STYLE, abbr)
                self.assertIn(a["build_type"], ("derive", "modernize", "new"), abbr)
                self.assertIn(a["tier"], (1, 2, 3), abbr)
                for key in ("set", "home_kit", "away_kit", "slot_choice", "status"):
                    self.assertTrue(a.get(key), (abbr, key))
            for item in entry.get("already_in_game", []):
                self.assertTrue(item["set"] and item["label"] and item["why"], abbr)
            for item in entry.get("not_assigned", []):
                self.assertTrue(item["set"] and item["why"], abbr)

    def test_each_alternate_recipe_matches_a_planned_slot(self) -> None:
        self.assertEqual(self.alternates["schema"], "nfl2k5_uniform_alternates_2026/v1")
        for key, recipe in self.alternates["alternates"].items():
            team, style = key.split(":")
            self.assertEqual((recipe["team"], recipe["style"]), (team, int(style)))
            self.assertEqual(us.FRANCHISES[recipe["code"]], team)
            planned = {a["style"]: a for a in self.doc["teams"][team]["assignments"]}
            self.assertIn(recipe["style"], planned, key)
            self.assertEqual(recipe["set"].split(" (")[0], planned[recipe["style"]]["set"].split(" (")[0], key)
            self.assertEqual(recipe["label"][0], us.ALTERNATE_YEAR)
            self.assertTrue(recipe["sources"], key)


@unittest.skipUnless(HAVE_UNICORN and XBE.is_file(), "unicorn or the retail extraction is not present")
class NativeCycleTests(unittest.TestCase):
    """The model against the game's own Team Select code on retail team-record bytes."""

    @classmethod
    def setUpClass(cls) -> None:
        import u3s_slots
        cls.machine = u3s_slots.Machine(XBE.read_bytes())

    def check(self, table: dict[int, tuple[int, int]]) -> dict:
        result = self.machine.cycle(record_with(table))
        pairs = pairs_from(table)
        self.assertEqual([list(x) for x in result["order"]],
                         [[s, us.style_label(s, *(pairs[s - 1] if s else (0, 0)))] for s in us.offered_styles(pairs)])
        self.assertEqual(result["reverse"], list(reversed(us.offered_styles(pairs))))
        self.assertEqual(result["clamp"], [us.loaded_style(pairs, s) for s in range(us.MAX_STYLE + 1)])
        return result

    def test_a_retail_shaped_table(self) -> None:
        self.check({1: (1981, 1997), 2: (1979, 1980), 3: (1968, 1978), 4: (2004, 1), 5: (2004, 2)})

    def test_relabels_an_enabled_orphan_and_a_gap(self) -> None:
        result = self.check({1: (1981, 1997), 2: (1979, 1980), 4: (2004, 1), 5: (2026, 1), 6: (2026, 2),
                             13: (2026, 3)})
        self.assertEqual(result["order"][-1], (13, "2026  Alternate 3"))

    def test_an_empty_table_offers_only_the_current_uniform(self) -> None:
        result = self.check({})
        self.assertEqual(result["order"], [(0, "Current Uniform")])


@unittest.skipUnless(os.environ.get("U3S_DISC_TESTS") == "1" and V05_DISC.is_file() and RETAIL_DISC.is_file(),
                     "set U3S_DISC_TESTS=1 with the v0.5 and retail images present")
class DiscPlanTests(unittest.TestCase):
    def test_the_committed_decisions_validate_on_the_v05_disc(self) -> None:
        import u3s_slots
        census = u3s_slots.census_doc(V05_DISC, RETAIL_DISC)
        plan = u3s_slots.build_plan(census, json.loads(DECISIONS.read_text(encoding="utf-8")))
        self.assertEqual(plan["validation"]["problems"], [])
        rams = census["franchises"]["LAR"]["owners"]
        self.assertTrue(any("2026 alternate" in o for o in rams["10"]))
        self.assertTrue(any("m1 spare" in o for o in census["franchises"]["NE"]["owners"]["12"]))


if __name__ == "__main__":
    unittest.main()

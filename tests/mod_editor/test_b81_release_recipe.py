"""b81 #43 (integration tasks 5 and 6): the SOFTDRINK release recipe turns on every beta 81 option the release ships.

The combined lead's B build (022022548, xbe d40f9e44) left CPU team building off: a stock preset derives team_building
from that preset's own franchise_economy and draft_ai (mod_build.py, b81 team building), softdrink_experimental has the
economy off, and the release recipe turned the economy on without naming team building. A recipe is the preset plus its
overrides (modpack_sources.build_plan), so every beta 81 option whose preset value is not the release's must be named.

- GateRecipe: the softdrink gate in data/nfl2k5_release_gates.json (the source the staged recipe copies are regenerated
  from) builds a plan with every release option on. Runs everywhere.
- StagedRecipes: the staged release sources (NFL2K5_B81_STANDARD_SOURCES, v10-sources-128 and its v10-sources-64 sibling)
  are the reviewed files (sha256 pins) and each of their three recipe documents builds that plan.
- FinalBuild: a finished build's own readback (NFL2K5_B81_FINAL_BUILD: the disc image or its default.xbe) reads
  "applied" for every beta 81 franchise owner its recipe turns on, never "retail"; with NFL2K5_B81_FINAL_RECEIPT, no
  beta 81 step of the Studio receipt was left out. The readback is taken again here: a full build takes its receipt
  readback before the late owner steps (team building, injured reserve), so the receipt's own copy can be stale.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import mod_build, modpack_sources  # noqa: E402

STANDARD_SOURCES = Path(os.environ.get("NFL2K5_B81_STANDARD_SOURCES",
                                       "/media/noah/Storage/2K5-project/beta81/v10-sources-128"))
DOCUMENTS = ("recipe.json", "assets/documents/frozen-recipe.json", "SOFTDRINK-build-recipe.json")

# The release's beta 81 options and the value each 128 MB build must carry (integration task 6; each lane's REVIEW_ME
# names its option key).
RELEASE_128 = {
    "team_building": True,            # #31 CPU clubs draft and sign for need (the owner's Chiefs WR fix), #43
    "franchise_economy": True,        # #34 economy revision 10
    "draft_ai": True,                 # team building runs inside the draft AI
    "modern_numbers": "modern",       # #32 modern numbers (128 MB only)
    "honors_page": True,              # #38 the season award vote installs with the honors owner
    "season_2026": True,              # #37 SportsCenter news; the booth, stadium welcome and stale-speech lines
    "sportscenter_lineup": True,      # #37 SportsCenter lines
    "sim_realism": True,              # #35 simulated outcomes and #27 fullback targets ride with season realism
    "sim_qb_injuries": "realistic",   # qb34; the room and CPU trades follow it (below)
    "classic_crowd": True,            # #33 the classic Seamen's crowd
    "modern_gillette": False,         # #24 Noah: "the games original is far better"
    "weekly_progression": True,       # #40 league aging
    "player_progress": True,          # #40 league aging
    "star_career": True,              # #40 star_career re-derived from the aging curves
    "modern_injured_reserve": True,   # the QB floor's needs; modern numbers' IR rule
    "helmet_side_numbers": True,
    "show_block_guard": True,         # #22 the playoff overtime crash fix
    "rookie_faces": True,             # #30
}
# Unnamed, these follow the quarterback option (DESIGN_CHANGES C1, ruling R6); on the release recipe they resolve to:
DERIVED_128 = {"qb_room": "realistic", "cpu_trades": "realistic"}
# The 64 MB edition is the 128 MB recipe fitted by the memory model (nfl2k5_console_memory.recommended_profile), which
# turns the 128 MB owners off; these must still hold there.
RELEASE_64 = {key: RELEASE_128[key] for key in (
    "team_building", "franchise_economy", "draft_ai", "season_2026", "sportscenter_lineup", "classic_crowd",
    "modern_gillette", "weekly_progression", "helmet_side_numbers", "show_block_guard", "rookie_faces")}
RELEASE_64["modern_numbers"] = False

# The reviewed staged recipe documents (#43: team_building true and modern_gillette false added to the overrides of
# each, nothing else changed; regenerate the pins with the folder, never by hand).
STAGED_SHA256 = {
    128: {
        "recipe.json": "db157e71c391b8b762eb4f4e42c3f8d737f667186fed9547b1f578bdec45c847",
        "assets/documents/frozen-recipe.json": "9c1f544001b530179a552641d9ae5e203bd43a8c09ab56dd250bed677ce22d03",
        "SOFTDRINK-build-recipe.json": "4fb2a3781a1f287c5abf85cc945e6c21809d8450489ae27ba36835c6f50620ca",
    },
    64: {
        "recipe.json": "bbc7161946f16b1e37b19de3b449d30e205e318fc4e5358d9c3c8674533cb544",
        "assets/documents/frozen-recipe.json": "4ebb2620234d7b17e5aa00d4c9a584886089d65103b6f5fddbf34c294f40465b",
        "SOFTDRINK-build-recipe.json": "70599893cbbc410fa51247d4a0909b250b826a86abc22a5dc167dc8f423fd6db",
    },
}

# Beta 81 franchise owners in a finished build's readback (mod_build.inspect keys) and when the recipe turns each on.
READBACK_OWNERS = {
    "team_building": lambda p: p.team_building,
    "franchise_economy": lambda p: p.franchise_economy,
    "draft_ai": lambda p: p.draft_ai,
    "cpu_trades": lambda p: mod_build._cpu_trades_plan(p)[0] == "realistic",
    "qb_room": lambda p: mod_build._qb_room_level(p) == "realistic",
    "modern_numbers": lambda p: p.modern_numbers == "modern",
    "honors_page": lambda p: p.honors_page,
    "sim_realism": lambda p: p.sim_realism,
    "sim_outcomes": lambda p: p.sim_realism and p.console_memory == 128,
    "sim_qb_injuries": lambda p: p.sim_qb_injuries not in (None, "retail"),
    "player_progress": lambda p: p.player_progress,
    "weekly_progression": lambda p: p.weekly_progression,
    "star_career": lambda p: p.star_career,
    "modern_injured_reserve": lambda p: p.modern_injured_reserve,
    "sportscenter_lineup": lambda p: p.sportscenter_lineup,
    "rookie_faces": lambda p: p.rookie_faces,
    "show_block_guard": lambda p: p.show_block_guard,
}
# Owners the readback has no key for, read with their own status function on the finished executable.
MODULE_OWNERS = {
    "nfl2k5_awards": lambda p: p.honors_page,
    "nfl2k5_sportscenter_news": lambda p: p.console_memory == 128 and p.season_2026,
}


def _gate_recipe():
    gates = json.loads((ROOT / "data/nfl2k5_release_gates.json").read_text(encoding="utf-8"))["gates"]
    gate = next(g for g in gates if g["id"] == "softdrink")
    # {"given": true} marks a source asset the staged folder supplies (an intro, a marks pack): not a plan value here
    overrides = {k: v for k, v in gate["overrides"].items() if not (isinstance(v, dict) and v.get("given"))}
    return {"preset": gate["preset"], "overrides": overrides}


class _Assert:
    def assert_release(self, plan, wanted, derived=None):
        got = {key: getattr(plan, key) for key in wanted}
        self.assertEqual({k: v for k, v in got.items() if v != wanted[k]}, {})
        for key, value in (derived or {}).items():
            level = mod_build._qb_room_level(plan) if key == "qb_room" else mod_build._cpu_trades_plan(plan)[0]
            self.assertEqual(level, value, key)


class GateRecipe(_Assert, unittest.TestCase):
    def test_the_release_gate_turns_on_every_beta_81_option_it_ships(self):
        plan = modpack_sources.build_plan(_gate_recipe())
        self.assertEqual(plan.console_memory, 128)
        self.assert_release(plan, RELEASE_128, DERIVED_128)

    def test_the_gate_names_team_building_because_the_preset_derives_it_off(self):
        # The preset rule stays (ruling a): softdrink_experimental has the economy off, so it derives team building off;
        # the recipe that turns the economy on must name team building itself.
        preset = mod_build.apply_preset(mod_build.BuildPlan("", ""), "softdrink_experimental")
        self.assertEqual((preset.franchise_economy, preset.team_building), (False, False))
        self.assertIs(_gate_recipe()["overrides"].get("team_building"), True)

    def test_every_option_whose_preset_value_is_not_the_releases_is_named(self):
        # The sweep's rule as a test: an option left unnamed takes the preset's value (or build_plan's: an unnamed
        # sim_qb_injuries reads None), so each release option the preset or build_plan leaves elsewhere is named.
        recipe = _gate_recipe()
        bare = modpack_sources.build_plan({"preset": recipe["preset"], "overrides": {}})
        unnamed = sorted(key for key, value in RELEASE_128.items()
                         if getattr(bare, key) != value and key not in recipe["overrides"])
        self.assertEqual(unnamed, [])


@unittest.skipUnless((STANDARD_SOURCES / "recipe.json").is_file(), "private release sources absent: NFL2K5_B81_STANDARD_SOURCES")
class StagedRecipes(_Assert, unittest.TestCase):
    def editions(self):
        for memory, wanted, derived in ((128, RELEASE_128, DERIVED_128), (64, RELEASE_64, None)):
            root = STANDARD_SOURCES.parent / f"v10-sources-{memory}"
            if (root / "recipe.json").is_file():
                yield memory, root, wanted, derived

    def test_the_staged_documents_are_the_reviewed_files(self):
        for memory, root, _wanted, _derived in self.editions():
            for name in DOCUMENTS:
                with self.subTest(memory=memory, document=name):
                    self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), STAGED_SHA256[memory][name])

    def test_each_staged_document_builds_the_release(self):
        for memory, root, wanted, derived in self.editions():
            for name in DOCUMENTS:
                with self.subTest(memory=memory, document=name):
                    plan = modpack_sources.build_plan(json.loads((root / name).read_text(encoding="utf-8")))
                    self.assertEqual(plan.console_memory, memory)
                    self.assert_release(plan, wanted, derived)
                    if memory == 128:
                        # The staged 64 MB recipe does not fit by the memory model (326 KB over at NRG Stadium s37, before
                        # and after #43; reported to the coordinator 11/27): its plan check waits for that ruling.
                        self.assertEqual(mod_build.validate_plan(plan), [])


FINAL_BUILD = os.environ.get("NFL2K5_B81_FINAL_BUILD")
FINAL_RECIPE = os.environ.get("NFL2K5_B81_FINAL_RECIPE", str(STANDARD_SOURCES / "SOFTDRINK-build-recipe.json"))
FINAL_RECEIPT = os.environ.get("NFL2K5_B81_FINAL_RECEIPT")


@unittest.skipUnless(FINAL_BUILD and Path(FINAL_BUILD).is_file() and Path(FINAL_RECIPE).is_file(),
                     "set NFL2K5_B81_FINAL_BUILD to the final disc (or its default.xbe); NFL2K5_B81_FINAL_RECIPE defaults to "
                     "the staged 128 MB build recipe")
class FinalBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = modpack_sources.build_plan(json.loads(Path(FINAL_RECIPE).read_text(encoding="utf-8")))
        cls.readback = mod_build.inspect(FINAL_BUILD)
        cls.xbe = mod_build._xbe_bytes(Path(FINAL_BUILD))

    def test_every_beta_81_franchise_owner_the_recipe_turns_on_reads_applied(self):
        wanted = [key for key, on in READBACK_OWNERS.items() if on(self.plan)]
        self.assertIn("team_building", wanted)
        self.assertEqual({key: self.readback.get(key) for key in wanted if self.readback.get(key) != "applied"}, {})
        import importlib
        states = {name: importlib.import_module("mod_editor.core." + name).status(self.xbe)
                  for name, on in MODULE_OWNERS.items() if on(self.plan)}
        self.assertEqual({name: state for name, state in states.items() if state != "applied"}, {})

    def test_no_beta_81_franchise_owner_reads_retail(self):
        self.assertEqual(sorted(key for key in READBACK_OWNERS if self.readback.get(key) == "retail"
                                and READBACK_OWNERS[key](self.plan)), [])

    @unittest.skipUnless(FINAL_RECEIPT and Path(FINAL_RECEIPT).is_file(), "set NFL2K5_B81_FINAL_RECEIPT to the Studio receipt")
    def test_no_step_of_the_build_was_left_out(self):
        receipt = json.loads(Path(FINAL_RECEIPT).read_text(encoding="utf-8"))
        problems = [f"plan.{key} = {receipt['plan'].get(key)!r}" for key, value in RELEASE_128.items()
                    if receipt["plan"].get("console_memory", 128) == 128 and receipt["plan"].get(key) != value]
        problems += [f"{step['step']} left out: {step.get('reason') or step.get('user_notes')}"
                     for step in receipt["steps"] if step.get("status") == "left_out"]
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()

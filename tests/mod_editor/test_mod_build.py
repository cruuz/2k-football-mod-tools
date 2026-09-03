"""One build plan applies every executable patch to one copy and returns one receipt."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import mod_build, nfl2k5_throw_tuning as tt  # noqa: E402
from nfl2k5_edge_rename_test import build_edge_synthetic_xbe  # noqa: E402
from nfl2k5_throw_tuning_test import _build_synthetic_xbe  # noqa: E402


class ModBuildTests(unittest.TestCase):
    def test_plan_applies_all_xbe_patches_in_one_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "default.xbe"
            source.write_bytes(build_edge_synthetic_xbe())     # seeds the throw, cave and EDGE retail sites
            target = Path(tmp) / "built.xbe"
            plan = mod_build.BuildPlan(str(source), str(target), throw=True, max_deep_yards=80.0, realistic_flight=True,
                                       catch_slider=True, accel_ramp=True, draft_ai=True, edge_rename=True,
                                       returner_fix=True, name="test")
            events = []
            receipt = mod_build.build(plan, lambda msg, a, b: events.append(msg))
            self.assertEqual(receipt["steps"][0]["step"], "xbe")
            self.assertEqual(receipt["steps"][0]["catch_slider"], "applied")
            self.assertEqual(receipt["steps"][0]["accel_ramp"], "applied")
            self.assertEqual(receipt["steps"][0]["draft_ai"], "applied")
            self.assertEqual(receipt["steps"][0]["edge_rename"], "applied")
            self.assertEqual(receipt["steps"][0]["returner_fix"], "applied")
            state = mod_build.inspect(target)
            self.assertEqual(state["throw"], tt.TuningSettings(80.0, 0.0, True))
            self.assertEqual(state["draft_ai"], "applied")
            self.assertEqual(state["edge_rename"], "applied")
            self.assertEqual(state["returner_fix"], "applied")
            self.assertEqual(state["progression"], "foreign")      # the EDGE fixture has no aging tables
            self.assertTrue(events)
            self.assertEqual(receipt["plan"]["name"], "test")
            self.assertNotIn("source", receipt["plan"])

    def test_refuses_same_file_and_scorebug_on_bare_xbe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "default.xbe"
            source.write_bytes(_build_synthetic_xbe())
            with self.assertRaises(ValueError):
                mod_build.build(mod_build.BuildPlan(str(source), str(source), throw=True))
            with self.assertRaises(ValueError):
                mod_build.build(mod_build.BuildPlan(str(source), str(Path(tmp) / "x.xbe"), scorebug=True))

    def test_availability_reports_optional_modules(self) -> None:
        avail = mod_build.availability()
        self.assertTrue(avail["throw"] and avail["catch_slider"])
        # the ESPN scorebug needs its repainted art and the retail mesh, which developer trees have and
        # release trees / CI checkouts deliberately do not: availability must say so, never fail later
        scorebug_inputs = ((mod_build.ROOT / "mod_editor" / "assets" / "nfl2k5_scorebug_espn" / "shield_espn_modern.png").exists()
                           and (mod_build.ROOT / "assets" / "intermediate" / "nfl2k5" / "models" / "0346_0078_score_bug.gltf").exists())
        self.assertEqual(avail["scorebug"], scorebug_inputs)
        self.assertIn("edge_rename", avail)
        self.assertIn("commentary", avail)


if __name__ == "__main__":
    unittest.main()


class PresetTests(unittest.TestCase):
    """SOFTDRINK presets: basic = the 2004 game + the 2K5 fixes; advanced = everything modern; experimental = + rough edges."""

    def test_basic_keeps_the_game_in_2004(self) -> None:
        plan = mod_build.apply_preset(mod_build.BuildPlan(source="s", target="t"), "softdrink_basic")
        self.assertTrue(plan.throw and plan.realistic_flight and plan.catch_slider and plan.draft_ai
                        and plan.returner_fix and plan.kick_power)
        # nothing that changes the 2004 rules, names or presentation
        self.assertFalse(plan.edge_rename or plan.kick_rules or plan.overtime or plan.accel_ramp or plan.progression
                         or plan.scorebug or plan.arc_by_distance or plan.scheme_labels or plan.camera
                         or plan.position_pools or plan.season_2026 or plan.widescreen or plan.kickoff_alignment)
        self.assertEqual(plan.max_deep_yards, 80.0)
        self.assertEqual((plan.source, plan.target), ("s", "t"))
        self.assertIn("basic", plan.name)

    def test_advanced_is_a_superset_of_basic_except_the_kick_split(self) -> None:
        basic = mod_build.PRESETS["softdrink_basic"]
        advanced = mod_build.PRESETS["softdrink_advanced"]
        for key, value in basic.items():
            if value is True and key != "kick_power":
                self.assertTrue(advanced.get(key), key)
        # advanced carries the modern spots (which include the power re-spacing), not the power-only fix
        self.assertTrue(advanced["kick_rules"]); self.assertFalse(advanced["kick_power"])
        plan = mod_build.apply_preset(mod_build.BuildPlan(source="s", target="t"), "softdrink_advanced")
        self.assertTrue(plan.accel_ramp and plan.progression and plan.scorebug and plan.arc_by_distance and plan.position_pools
                        and plan.season_2026 and plan.edge_rename and plan.overtime and plan.camera and plan.scheme_labels)
        self.assertFalse(plan.widescreen or plan.kickoff_alignment)

    def test_experimental_is_advanced_plus_widescreen_and_kickoff_lineup(self) -> None:
        advanced = mod_build.PRESETS["softdrink_advanced"]
        experimental = mod_build.PRESETS["softdrink_experimental"]
        for key, value in advanced.items():
            if value is True:
                self.assertTrue(experimental.get(key), key)
        plan = mod_build.apply_preset(mod_build.BuildPlan(source="s", target="t"), "softdrink_experimental")
        self.assertTrue(plan.widescreen and plan.kickoff_alignment)
        self.assertIn("experimental", plan.name)

    def test_every_preset_names_every_toggle(self) -> None:
        toggles = {k for k in mod_build.PRESETS["softdrink_experimental"]}
        for name, values in mod_build.PRESETS.items():
            self.assertEqual(set(values), toggles, name)
            self.assertIn(name, mod_build.PRESET_TITLES)

    def test_unknown_preset_is_refused_and_names_are_kept(self) -> None:
        with self.assertRaises(KeyError):
            mod_build.apply_preset(mod_build.BuildPlan(source="s", target="t"), "nope")
        plan = mod_build.apply_preset(mod_build.BuildPlan(source="s", target="t", name="mine"), "softdrink_basic")
        self.assertEqual(plan.name, "mine")

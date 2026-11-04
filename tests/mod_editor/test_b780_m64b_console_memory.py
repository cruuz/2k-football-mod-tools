"""b780-m64b: the console memory target in BuildPlan (128 MB xemu, the default; 64 MB experimental).

Noah, 2026-11-03: "We need an option in the editor to limit a few things to allow the 64 MB option for Xbox and Android
... maybe let people pick and choose what must be removed to get 64 to work." The 128 MB build stays the main product
with every feature and is the default; a 128 plan, its recipe and its saved settings must be exactly what they were
before the option existed. These are the core checks (no Qt); the Build tab's are in the _qt file beside this one.
"""
from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from dataclasses import asdict, fields
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import modpack_sources  # noqa: E402
from mod_editor.core import nfl2k5_build_settings as saved  # noqa: E402
from mod_editor.core import nfl2k5_console_memory as cm  # noqa: E402

MODEL = "mod_editor.core.nfl2k5_memory_budget"


def fake_model(*, fits=True, spare=412 * 1024, over=0, suggestions=(), costs=None, requires=None, profile=None):
    """A stand-in for the b780-m64a memory model with the agreed API (REQUIRES_128, option_costs, predict,
    recommended_64_profile), so the target's behaviour is tested without its numbers."""
    module = types.ModuleType(MODEL)
    module.REQUIRES_128 = dict(requires or {})
    module.calls = []

    def option_costs(plan=None, target_mb=64):
        table = dict(costs or {})
        if plan is None:
            return table
        return {key: size for key, size in table.items() if cm.is_on(plan, key)}

    def predict(plan, target_mb=64):
        module.calls.append(plan)
        return {"fits": fits, "spare_bytes": spare, "over_bytes": over, "hardest": "Lambeau Field (s10)",
                "suggestions": list(suggestions), "target_mb": target_mb, "evidence": "MODELLED", "notes": []}

    module.option_costs = option_costs
    module.predict = predict
    module.recommended_64_profile = lambda: dict(profile or {})
    return module


def _text(recipe) -> str:
    """A recipe as JSON text (tuples and lists both read as arrays, as in a saved project or pack)."""
    return json.dumps(recipe, sort_keys=True, default=str)


def without_model():
    """No memory model in this build (also hides a real one while the test runs)."""
    return mock.patch.dict(sys.modules, {MODEL: None})


def with_model(module):
    return mock.patch.dict(sys.modules, {MODEL: module})


class PlanField(unittest.TestCase):
    def test_default_is_128_and_the_recipe_of_a_128_plan_has_no_key(self):
        plan = mod_build.BuildPlan("source.iso", "target.iso")
        self.assertEqual(plan.console_memory, 128)
        self.assertEqual(cm.of(plan), 128)
        self.assertNotIn("console_memory", plan.to_recipe())
        self.assertNotIn("console_memory", json.dumps(plan.to_recipe(), default=str))

    def test_a_128_recipe_is_exactly_the_recipe_the_plan_had_before_the_option(self):
        # the recipe before b780-m64b was asdict minus source, target and overwrite; a 128 plan's recipe must equal that,
        # key for key and value for value, for the bare plan and for every preset (the SOFTDRINK recipe's base)
        plans = [mod_build.BuildPlan("s", "t")] + [mod_build.apply_preset(mod_build.BuildPlan("s", "t"), name)
                                                    for name in sorted(mod_build.PRESETS)]
        for plan in plans:
            with self.subTest(name=plan.name or "bare"):
                before = {key: value for key, value in asdict(plan).items()
                          if key not in ("source", "target", "overwrite", "console_memory")}
                self.assertEqual(plan.to_recipe(), before)
                self.assertEqual(json.dumps(plan.to_recipe(), sort_keys=True, default=str),
                                 json.dumps(before, sort_keys=True, default=str))

    def test_presets_leave_the_target_alone(self):
        for name, values in mod_build.PRESETS.items():
            self.assertNotIn("console_memory", values, name)
            plan = mod_build.apply_preset(mod_build.BuildPlan("s", "t", console_memory=64), name)
            self.assertEqual(plan.console_memory, 64, name)
            self.assertEqual(mod_build.apply_preset(mod_build.BuildPlan("s", "t"), name).console_memory, 128, name)

    def test_a_64_plan_round_trips_through_its_recipe(self):
        plan = mod_build.BuildPlan("s", "t", console_memory=64, throw=True)
        recipe = plan.to_recipe()
        self.assertEqual(recipe["console_memory"], 64)
        restored = mod_build.BuildPlan("s", "t", **json.loads(json.dumps(recipe)))
        self.assertEqual(restored.console_memory, 64)
        self.assertEqual(_text(restored.to_recipe()), _text(recipe))

    def test_pack_recipe_overrides_reach_the_plan(self):
        recipe = {"preset": "softdrink_experimental", "overrides": {"console_memory": 64}}
        self.assertEqual(modpack_sources.build_plan(recipe).console_memory, 64)
        self.assertEqual(cm.of(recipe), 64)
        self.assertEqual(modpack_sources.build_plan({"preset": "softdrink_experimental", "overrides": {}}).console_memory,
                         128)


class SavedSettings(unittest.TestCase):
    def test_project_settings_of_a_128_plan_are_unchanged_and_old_projects_read_128(self):
        plan = mod_build.apply_preset(mod_build.BuildPlan("s", "t"), "softdrink_experimental")
        state = saved.from_plan(plan)
        self.assertNotIn("console_memory", state)
        self.assertIn("console_memory", saved.FEATURE_KEYS)
        old_project = dict(state)            # a project saved before the option existed has no key
        self.assertEqual(saved.to_plan(old_project, "s", "t").console_memory, 128)
        self.assertEqual(_text(saved.to_plan(old_project, "s", "t").to_recipe()), _text(plan.to_recipe()))

    def test_a_64_project_round_trips_and_bad_values_are_refused(self):
        plan = mod_build.BuildPlan("s", "t", console_memory=64)
        state = saved.from_plan(plan)
        self.assertEqual(state["console_memory"], 64)
        self.assertEqual(saved.to_plan(json.loads(json.dumps(state)), "s", "t").console_memory, 64)
        for bad in (65, 0, True, "64", 64.0, None):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                saved.build_settings({"console_memory": bad})


class Validation(unittest.TestCase):
    def test_128_plans_validate_exactly_as_before(self):
        with without_model():
            plan = mod_build.BuildPlan("s", "t", k128_memory=True, k128_roster_heap=True, guardian_overlay=True,
                                       reserves_16=True, created_teams_extra=2)
            self.assertEqual(mod_build.validate_plan(plan), [])
        model = fake_model(fits=False, over=900 * 1024, suggestions=[("hair_styles", 900 * 1024)])
        with with_model(model):
            self.assertEqual(mod_build.validate_plan(mod_build.apply_preset(mod_build.BuildPlan("s", "t"),
                                                                            "softdrink_experimental")), [])
            self.assertEqual(model.calls, [], "a 128 plan never asks the 64 MB model")

    def test_bad_target_values_are_refused(self):
        for bad in (32, 65, True):
            with self.subTest(value=bad):
                problems = mod_build.validate_plan(mod_build.BuildPlan("s", "t", console_memory=bad))
                self.assertEqual(len(problems), 1)
                self.assertIn("Console memory must be 128 or 64", problems[0])

    def test_64_refuses_every_option_that_needs_128_by_name(self):
        with without_model():
            plan = mod_build.BuildPlan("s", "t", console_memory=64, k128_memory=True, k128_roster_heap=True,
                                       k128_early=True, guardian_overlay=True, reserves_16=True, created_teams_extra=2)
            problems = mod_build.validate_plan(plan)
        self.assertEqual(len(problems), 1)
        text = problems[0]
        for caption in ("128 MB memory (K128, xemu set to 128 MB)", "Roster block in the extra memory",
                        "Bigger graphics memory (K128 early form)", "Guardian caps (experimental)",
                        "16 reserves (experimental)", "Two extra created teams (experimental)"):
            self.assertIn(caption, text)
        self.assertIn("Turn them off, or choose Console memory 128 MB", text)
        self.assertNotIn("\u2014", text)

    def test_the_forced_off_list_covers_k128_and_the_options_that_fail_at_64(self):
        with without_model():
            rules = cm.requires_128()
        self.assertEqual(set(rules), {"k128_memory", "k128_roster_heap", "k128_early", "guardian_overlay",
                                      "reserves_16", "created_teams_extra"})
        # the 128 MB and 4627 start-up stop screens are K128's require entry: with K128 off a 64 MB disc has neither
        from mod_editor.core import nfl2k5_throw_tuning as tt
        self.assertTrue(tt.k128_requires_128(guardian_overlay=True))
        self.assertTrue(tt.k128_requires_128(reserves_16=True))
        self.assertTrue(tt.k128_requires_128(created_teams_extra=2))
        self.assertTrue(tt.k128_requires_128(roster_capacity=True))

    def test_a_64_plan_without_them_and_with_no_model_is_accepted(self):
        with without_model():
            plan = mod_build.BuildPlan("s", "t", console_memory=64, throw=True, catch_slider=True)
            self.assertEqual(mod_build.validate_plan(plan), [])

    def test_64_refuses_roster_edits_that_grow_the_roster_file(self):
        with tempfile.TemporaryDirectory() as folder:
            grown = Path(folder) / "softdrink-rosters.json"
            grown.write_text(json.dumps({"schema": "x", "edits": [], "free_agent_capacity": {
                "schema": "nfl2k5.free_agent_capacity.v1", "records": 612}}))
            plain = Path(folder) / "my-rosters.json"
            plain.write_text(json.dumps({"schema": "x", "edits": []}))
            with without_model():
                self.assertEqual(cm.capacity_records(mod_build.BuildPlan("s", "t", roster_edits=str(grown))), 612)
                problems = cm.problems(mod_build.BuildPlan("s", "t", console_memory=64, roster_edits=str(grown)))
                self.assertEqual(len(problems), 1)
                self.assertIn("softdrink-rosters.json", problems[0])
                self.assertIn("612 more records", problems[0])
                self.assertIn("Untick Include exported \u2605 Rosters edits", problems[0])
                self.assertEqual(cm.problems(mod_build.BuildPlan("s", "t", console_memory=64, roster_edits=str(plain))),
                                 [])
                # 128 keeps its own rule (capacity growth needs K128), untouched by this option
                self.assertEqual(cm.problems(mod_build.BuildPlan("s", "t", roster_edits=str(grown))), [])

    def test_64_refuses_a_selection_the_model_says_will_not_fit_naming_what_to_turn_off(self):
        model = fake_model(fits=False, spare=0, over=300 * 1024 + 1,
                           suggestions=[("modern_lambeau", 200 * 1024), ("hair_styles", 150 * 1024), ("rookie_faces", 9)])
        with with_model(model):
            problems = mod_build.validate_plan(mod_build.BuildPlan("s", "t", console_memory=64, modern_lambeau=True,
                                                                   hair_styles=True, rookie_faces=True))
        self.assertEqual(len(problems), 1)
        text = problems[0]
        self.assertTrue(text.startswith("The 64 MB build will not fit: remove 301 KB"), text)
        self.assertIn("Lambeau Field (s10)", text)
        self.assertIn("for example turn off", text)
        self.assertIn("(200 KB)", text)
        self.assertIn("(150 KB)", text)
        self.assertNotIn("rookie", text.lower(), "two suggestions already cover the shortfall")
        self.assertIn("estimate", text)

    def test_the_model_is_asked_with_the_forced_off_options_off(self):
        model = fake_model()
        with with_model(model):
            problems = cm.problems(mod_build.BuildPlan("s", "t", console_memory=64, k128_memory=True))
        self.assertEqual(len(problems), 1)          # the K128 refusal; the fit is fine
        self.assertFalse(model.calls[-1].k128_memory)

    def test_build_refuses_before_any_disc_work(self):
        with without_model(), tempfile.TemporaryDirectory() as folder:
            plan = mod_build.BuildPlan(str(Path(folder) / "missing.iso"), str(Path(folder) / "out.iso"),
                                       console_memory=64, guardian_overlay=True)
            with self.assertRaises(ValueError) as caught:
                mod_build.build(plan)
            self.assertIn("The 64 MB build cannot include Guardian caps (experimental)", str(caught.exception))
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()), [])

    def test_build_refuses_a_selection_that_will_not_fit_before_any_disc_work(self):
        model = fake_model(fits=False, spare=0, over=64 * 1024, suggestions=[("hair_styles", 84_736)])
        with with_model(model), tempfile.TemporaryDirectory() as folder:
            plan = mod_build.BuildPlan(str(Path(folder) / "missing.iso"), str(Path(folder) / "out.iso"),
                                       console_memory=64, hair_styles=True)
            with self.assertRaises(ValueError) as caught:
                mod_build.build(plan)
            text = str(caught.exception)
            self.assertIn("The 64 MB build will not fit: remove 64 KB", text)
            self.assertIn("Hair styles (83 KB)", text)
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()), [])
            # the same selection at 128 MB is not asked about and reaches the usual source check
            with self.assertRaises(ValueError) as caught:
                mod_build.build(mod_build.BuildPlan(plan.source, plan.target, hair_styles=True))
            self.assertNotIn("64 MB", str(caught.exception))


class Model(unittest.TestCase):
    def test_the_model_adds_rules_and_its_wording_wins(self):
        model = fake_model(requires={"guardian_overlay": "Needs the >64 MB region.", "module_loader": "needs the 4627 kernel",
                                     "roster_capacity": "the bigger roster needs 128 MB", "not_a_field": "x"})
        with with_model(model):
            rules = cm.requires_128()
            self.assertEqual(rules["guardian_overlay"], "needs the >64 MB region")
            self.assertEqual(rules["module_loader"], "needs the 4627 kernel")
            self.assertNotIn("not_a_field", rules)
            self.assertNotIn("roster_capacity", rules)
            self.assertIn("k128_memory", rules)   # the built-in rules stay
            self.assertEqual(cm.capacity_reason(), "the bigger roster needs 128 MB")
            # the badge keeps a few words; the model's whole reason is the tooltip's
            self.assertEqual(cm.lock_badge(rules["guardian_overlay"], "guardian_overlay"), "Off at 64 MB: needs 128 MB")
            self.assertEqual(cm.lock_badge("It loads a section. Then more.", "module_loader"),
                             "Off at 64 MB: loads a section")

    def test_budget_lines(self):
        with with_model(fake_model(fits=True, spare=412 * 1024 + 1023)):
            line = cm.budget_line(cm.predict(mod_build.BuildPlan("s", "t", console_memory=64)))
        self.assertTrue(line.startswith("Predicted to fit with 412 KB to spare at the hardest stadium, "
                                        "Lambeau Field (s10)."), line)
        self.assertIn("estimate", line)
        with without_model():
            self.assertIsNone(cm.predict(mod_build.BuildPlan("s", "t", console_memory=64)))
            self.assertIn("cannot predict", cm.budget_line(None))

    def test_costs_and_the_recommended_profile(self):
        model = fake_model(costs={"hair_styles": 150 * 1024, "rookie_faces": 512, "k128_memory": 1},
                           profile={"hair_styles": False, "not_a_field": True, "source": "x"})
        with with_model(model):
            self.assertEqual(cm.option_costs()["hair_styles"], 150 * 1024)
            self.assertEqual(cm.option_costs(mod_build.BuildPlan("s", "t", rookie_faces=True)), {"rookie_faces": 512})
            self.assertEqual(cm.cost_text(150 * 1024), "Memory at 64 MB: 150 KB (estimate)")
            self.assertEqual(cm.cost_text(512), "Memory at 64 MB: under 1 KB (estimate)")
            profile = cm.recommended_profile()
        self.assertEqual(profile["console_memory"], 64)
        self.assertIs(profile["hair_styles"], False)
        self.assertNotIn("not_a_field", profile)
        self.assertNotIn("source", profile)
        for key in ("k128_memory", "k128_roster_heap", "k128_early", "guardian_overlay", "reserves_16"):
            self.assertIs(profile[key], False)
        self.assertEqual(profile["created_teams_extra"], 0)
        names = {item.name for item in fields(mod_build.BuildPlan)}
        self.assertLessEqual(set(profile), names)

    def test_a_broken_model_never_breaks_the_target(self):
        module = types.ModuleType(MODEL)
        module.REQUIRES_128 = "not a table"
        module.predict = lambda plan, target_mb=64: 1 / 0
        module.option_costs = lambda plan=None, target_mb=64: ["not", "a", "table"]
        module.recommended_64_profile = lambda: 1 / 0
        with with_model(module):
            self.assertIn("k128_memory", cm.requires_128())
            self.assertIsNone(cm.predict(mod_build.BuildPlan("s", "t", console_memory=64)))
            self.assertEqual(cm.option_costs(), {})
            self.assertEqual(cm.recommended_profile()["console_memory"], 64)

    def test_text_is_plain(self):
        texts = [cm.HELP_TEXT, cm.NOTE_128, cm.NOTE_64, cm.SHARE_NOTE, cm.NEXT_STEPS_64, cm.RECOMMENDED_HELP,
                 cm.SHARE_CHOICE_HELP, *cm.LABELS.values(), *cm.OWN_REQUIRES_128.values(), cm.CAPACITY_REASON]
        for text in texts:
            self.assertNotIn("\u2014", text)
            self.assertNotIn("\u2013", text)
        self.assertIn("untested on a real Xbox and in hakuX", cm.NOTE_64)
        self.assertIn("For the full experience use xemu at 128 MB", cm.NOTE_64)
        self.assertEqual(cm.LABELS[128], "128 MB, xemu (full SOFTDRINK)")
        self.assertEqual(cm.LABELS[64], "64 MB, original Xbox and Android hakuX (experimental)")
        self.assertIn("2026 rosters need 128 MB for now", cm.SHARE_NOTE)


if __name__ == "__main__":
    unittest.main()

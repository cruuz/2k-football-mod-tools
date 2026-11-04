"""b780-m64b: the console memory target in BuildPlan (128 MB xemu, the default; 64 MB experimental).

Noah, 2026-11-03: "We need an option in the editor to limit a few things to allow the 64 MB option for Xbox and Android
... maybe let people pick and choose what must be removed to get 64 to work." The 128 MB build stays the main product
with every feature and is the default; a 128 plan, its recipe and its saved settings must be exactly what they were
before the option existed. These are the core checks (no Qt); the Build tab's are in the _qt file beside this one.
"""
from __future__ import annotations

import hashlib
import json
import os
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
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402

MODEL = "mod_editor.core.nfl2k5_memory_budget"


def fake_model(*, fits=True, spare=412 * 1024, over=0, suggestions=(), costs=None, requires=None, profile=None,
               primary_margin=None):
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
        answer = {"fits": fits, "spare_bytes": spare, "over_bytes": over, "hardest": "Lambeau Field (s10)",
                  "suggestions": list(suggestions), "target_mb": target_mb, "evidence": "MODELLED", "notes": []}
        if primary_margin is not None:   # the model's default-uniforms (style 0) case and its safety margin
            answer.update(safety_bytes=65_536, primary_uniforms={"margin": primary_margin, "hardest": "NRG Stadium (s37)"})
        return answer

    module.option_costs = option_costs
    module.predict = predict
    module.recommended_64_profile = lambda: dict(profile or {})
    return module


def grown_roster_edits(records=612):
    """A small roster-edits document whose dated refresh puts its free agents in appended (capacity) records, the way
    the SOFTDRINK pack's does: fittable to the retail size (only the depth free agents need the appended records)."""
    def depth(priority, index):
        return {"index": index, "new": True, "first": f"F{priority}", "last": f"L{priority}", "fa3_priority": priority,
                "fields": {"photo_id": 20000 + index, "jersey": priority}}
    rows = [{"index": 2464, "new": True, "first": "Signed", "last": "Player", "fields": {}}]
    rows += [depth(p, i) for p, i in enumerate((2554, 2619, 2700), 1)]
    return {"schema": rr.EDITS_SCHEMA, "edits": [],
            "roster_refresh": {"schema": "nfl2k5.roster_refresh.v1", "players": rows,
                               "free_agents": [7, 2464, 2554, 2619, 2700], "identity_guards": [[0, "A", "B", "2000-01-01"]],
                               "teams": [{"index": 0, "team": "SF", "active": [1, 2, 3], "reserves": [4],
                                          "specialists": {"k": 3}}]},
            "free_agent_capacity": {"schema": "nfl2k5.free_agent_capacity.v1", "records": records},
            "draft_pick_ownership": {"schema": "x"}, "hback_roles": {"schema": "y"}}


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

    def test_64_fits_roster_edits_that_grow_the_roster_file_instead_of_refusing_them(self):
        with tempfile.TemporaryDirectory() as folder:
            grown = Path(folder) / "softdrink-rosters.json"
            grown.write_text(json.dumps(grown_roster_edits(records=612)))
            plain = Path(folder) / "my-rosters.json"
            plain.write_text(json.dumps({"schema": rr.EDITS_SCHEMA, "edits": []}))
            plan64 = mod_build.BuildPlan("s", "t", console_memory=64, roster_edits=str(grown))
            plan128 = mod_build.BuildPlan("s", "t", roster_edits=str(grown))
            with without_model():
                self.assertEqual(cm.capacity_records(plan64), 612)
                self.assertTrue(cm.roster_fit_applies(plan64))
                self.assertFalse(cm.roster_fit_applies(plan128))
                self.assertEqual(cm.roster_fit_problem(plan64), "")
                self.assertEqual(mod_build.validate_plan(plan64), [])          # kept: the build fits them
                self.assertEqual(cm.problems(mod_build.BuildPlan("s", "t", console_memory=64, roster_edits=str(plain))), [])
            # no arena growth and no K128 demand at 64 MB; 128 MB keeps its capacity growth exactly as before
            self.assertEqual(mod_build._roster_capacity_records(plan64), 0)
            self.assertEqual(mod_build._requested_capacity_records(plan64), 612)
            self.assertEqual(mod_build._roster_capacity_records(plan128), 612)
            self.assertTrue(mod_build._roster_fit_applies(plan64))
            self.assertFalse(mod_build._roster_fit_applies(plan128))
            # the model is asked about the fitted roster: no capacity growth, no draft-pick or backfield sections
            flat = cm.model_plan(plan64)
            self.assertEqual((flat["roster_capacity"], flat["roster_draft_pick_ownership"], flat["roster_hback_roles"]),
                             (False, False, False))
            self.assertEqual(flat["roster_edits"], str(grown))
            self.assertIs(cm.model_plan(plan128), plan128)
            self.assertIn("free agents beyond the original game's count", cm.ROSTER_FIT_NOTE)
            self.assertIn("draft-pick ownership and the backfield labels fall back to the 2004 game's", cm.ROSTER_FIT_NOTE)

    def test_64_refuses_roster_edits_only_when_the_fit_does(self):
        with tempfile.TemporaryDirectory() as folder:
            document = grown_roster_edits(records=612)
            document["edits"].append({"index": 2620, "pool": "primary"})       # a non-free-agent row in an appended record
            grown = Path(folder) / "grown.json"
            grown.write_text(json.dumps(document))
            with without_model():
                problems = mod_build.validate_plan(mod_build.BuildPlan("s", "t", console_memory=64, roster_edits=str(grown)))
            self.assertEqual(len(problems), 1)
            self.assertTrue(problems[0].startswith("The 64 MB build cannot fit the roster edits grown.json to the original "
                                                   "game's roster size (612 more records asked for): "), problems[0])
            self.assertIn("appended capacity records", problems[0])
            self.assertIn("Untick Include exported \u2605 Rosters edits, or choose Console memory 128 MB", problems[0])

    def test_the_build_fits_the_refresh_on_its_own_roster_and_drops_the_two_xbe_sections(self):
        """The dated refresh pass of a 64 MB build: the fit runs on the main roster the build made (load_image of the
        target), the fitted refresh is what gets written, the receipt and the user notes say what was dropped; 128 MB
        writes the document's own refresh and runs the draft-pick and backfield steps as before."""
        with tempfile.TemporaryDirectory() as folder:
            grown = Path(folder) / "softdrink-rosters.json"
            grown.write_text(json.dumps(grown_roster_edits(records=612)))
            fitted = {"roster_refresh": {"fitted": True}}
            fit_receipt = {"depth_kept": 1, "depth_candidates": 3, "signed_depth_kept": []}
            calls = {}

            class Image:
                def to_body(self):
                    return b"BODY"

            def fake_fit(document, base, *, source_sha256=""):
                calls["fit"] = (base, source_sha256, sorted(document))
                return fitted, fit_receipt

            def fake_apply(target, directive, **_kwargs):
                calls["directive"] = directive
                return {"written": True}

            def no_xbe(_target):
                raise AssertionError("the 64 MB build must not run the draft-pick or backfield XBE steps")
            for memory in (64, 128):
                calls.clear()
                plan = mod_build.BuildPlan("s", "t", console_memory=memory, roster_edits=str(grown), position_pools=True)
                receipt = {"steps": []}
                with mock.patch.object(rr, "load_image", lambda _path: Image()), \
                        mock.patch.object(rr, "apply", fake_apply), mock.patch.object(cm, "fit_roster_edits", fake_fit):
                    mod_build._apply_roster_refresh(plan, Path(folder) / "out.iso", receipt, lambda *_a: None)
                    if memory == 64:
                        with mock.patch.object(mod_build, "_xbe_bytes", no_xbe):
                            mod_build._apply_draft_pick_ownership(plan, Path(folder) / "out.iso", receipt, lambda *_a: None)
                            mod_build._apply_hback_roles(plan, Path(folder) / "out.iso", receipt, lambda *_a: None)
                if memory == 64:
                    self.assertEqual(calls["fit"][0], b"BODY")
                    self.assertEqual(calls["fit"][1], hashlib.sha256(grown.read_bytes()).hexdigest())
                    self.assertEqual(calls["directive"]["roster_refresh"], {"fitted": True})
                    self.assertEqual(receipt["steps"][0], {"step": "roster_retail_fit", **fit_receipt})
                    self.assertEqual(receipt["user_notes"], [cm.roster_fit_note(fit_receipt)])
                else:
                    self.assertNotIn("fit", calls)
                    self.assertEqual(calls["directive"]["roster_refresh"], grown_roster_edits()["roster_refresh"])
                    self.assertNotIn("user_notes", receipt)

    def test_a_fit_that_fails_in_the_build_refuses_with_the_reason(self):
        with tempfile.TemporaryDirectory() as folder:
            grown = Path(folder) / "softdrink-rosters.json"
            grown.write_text(json.dumps(grown_roster_edits(records=612)))

            class Image:
                def to_body(self):
                    return b"BODY"

            def failing_fit(document, base, *, source_sha256=""):
                raise ValueError("the refresh alone keeps fewer than 116 import vacancies at retail capacity")
            plan = mod_build.BuildPlan("s", "t", console_memory=64, roster_edits=str(grown), position_pools=True)
            with mock.patch.object(rr, "load_image", lambda _path: Image()), \
                    mock.patch.object(cm, "fit_roster_edits", failing_fit):
                with self.assertRaises(ValueError) as caught:
                    mod_build._apply_roster_refresh(plan, Path(folder) / "out.iso", {"steps": []}, lambda *_a: None)
            self.assertIn("The 64 MB build could not fit the roster edits to the original game's roster size: the "
                          "refresh alone keeps fewer than 116", str(caught.exception))

    def test_the_fit_note_counts_what_was_kept(self):
        note = cm.roster_fit_note({"depth_kept": 19, "depth_candidates": 533, "signed_depth_kept": [1] * 7})
        self.assertTrue(note.startswith(cm.ROSTER_FIT_NOTE))
        self.assertIn("This build keeps 19 of the 533 dated free agents (7 of them signed to clubs).", note)

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


class AlternateKits(unittest.TestCase):
    """The model's hardest game includes a uniform a player picks; the default uniforms are a separate case."""

    def model(self):
        return fake_model(fits=False, spare=0, over=56 * 1024, primary_margin=65_536 + 124 * 1024)

    def test_fits_with_the_default_uniforms_builds_with_a_warning(self):
        with with_model(self.model()):
            plan = mod_build.BuildPlan("s", "t", console_memory=64)
            prediction = cm.predict(plan)
            self.assertTrue(cm.alternate_kit_shortfall(prediction))
            self.assertTrue(cm.ALLOW_ALTERNATE_KIT_SHORTFALL)
            self.assertFalse(cm.refuses(prediction))
            self.assertEqual(mod_build.validate_plan(plan), [])
            line = cm.budget_line(prediction)
        self.assertTrue(line.startswith(
            "Predicted to fit with the default uniforms (124 KB to spare at the hardest stadium, NRG Stadium (s37)). A "
            "player-picked alternate kit at Lambeau Field (s10) may not fit (56 KB short); if a game loops on the stadium "
            "shots, use the default uniforms."), line)
        self.assertIn("estimate", line)

    def test_the_strict_rule_refuses_it(self):
        with with_model(self.model()), mock.patch.object(cm, "ALLOW_ALTERNATE_KIT_SHORTFALL", False):
            plan = mod_build.BuildPlan("s", "t", console_memory=64)
            prediction = cm.predict(plan)
            self.assertTrue(cm.refuses(prediction))
            problems = mod_build.validate_plan(plan)
            self.assertEqual(len(problems), 1)
            self.assertTrue(problems[0].startswith("The 64 MB build will not fit: Will not fit with every uniform."),
                            problems[0])

    def test_a_shortfall_with_the_default_uniforms_too_refuses(self):
        with with_model(fake_model(fits=False, spare=0, over=56 * 1024, primary_margin=1024)):
            prediction = cm.predict(mod_build.BuildPlan("s", "t", console_memory=64))
            self.assertFalse(cm.alternate_kit_shortfall(prediction))
            self.assertTrue(cm.refuses(prediction))


class RealModel(unittest.TestCase):
    """The memory model this build carries (b780-m64a), through the adapter: shapes and the rule, not its numbers."""

    def setUp(self):
        if cm.model() is None:
            self.skipTest("no memory model in this build")

    def test_the_adapter_reads_the_model(self):
        rules = cm.requires_128()
        self.assertLessEqual(set(cm.OWN_REQUIRES_128), set(rules))
        self.assertTrue(cm.capacity_reason())
        for name in sorted(mod_build.PRESETS):
            plan = cm.without_forced(mod_build.apply_preset(mod_build.BuildPlan("s", "t", console_memory=64), name))
            prediction = cm.predict(plan)
            self.assertIsNotNone(prediction, name)
            self.assertEqual(set(prediction) >= {"fits", "spare_bytes", "over_bytes", "hardest", "suggestions"}, True)
            self.assertIn("estimate", cm.budget_line(prediction))
            refused = any(text.startswith("The 64 MB build will not fit") for text in cm.problems(plan))
            self.assertEqual(refused, cm.refuses(prediction), name)
            for key, size in cm.option_costs(plan).items():
                self.assertIs(type(size), int, key)

    def test_the_recommended_set_is_the_target_with_the_forced_options_off(self):
        plan = mod_build.apply_preset(mod_build.BuildPlan("s", "t"), "softdrink_experimental")
        profile = cm.recommended_profile(plan)
        self.assertEqual(profile["console_memory"], 64)
        for key in cm.requires_128():
            self.assertFalse(cm.is_on(type("P", (), {key: profile[key]})(), key), key)
        names = {item.name for item in fields(mod_build.BuildPlan)}
        self.assertLessEqual(set(profile), names)


# b780 rst2: the proof runs on the release inputs: the 128 MB release roster edits and the 64 MB file fitted from it
# (tools/nfl2k5_roster_retail_fit.py fit --drop-xbe-sections), both in rst2/release/ (sha256 a8be08ed... and below).
RELEASE = Path("/home/noah/2k-worktrees/.b77-scratch/b780/rst2/release-deadline")
HEALTHY = Path(os.environ.get("NFL2K5_B780_ROSTER_EDITS_HEALTHY", str(RELEASE / "roster-edits-b780-rst2-deadline-20261104.json")))
FITTED_64 = Path(os.environ.get("NFL2K5_B780_ROSTER_64MB",
                                str(RELEASE / "roster-edits-b780-rst2-deadline-20261104-retail-capacity-64mb.json")))
REFRESH_BASE = Path(os.environ.get("NFL2K5_B780_REFRESH_BASE",
                                   "/home/noah/2k-worktrees/.b77-scratch/i4/inputs/ro1/baseline.body"))
RETAIL = Path(os.environ.get("NFL2K5_RETAIL_XISO", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
FITTED_64_SHA256 = "26522689b76cb8791cc2936058513a47f4c3c89fc58a1f47fc4a7622f3737c20"


def _proof_inputs():
    return (HEALTHY.is_file() and FITTED_64.is_file() and REFRESH_BASE.is_file()
            and hashlib.sha256(FITTED_64.read_bytes()).hexdigest() == FITTED_64_SHA256)


def users_dump_base(source: dict) -> bytes:
    """The main roster the build makes from the user's own retail dump before the dated refresh: the build's roster
    edits pass (refresh deferred, the 2026 free agents and spare capacity it adds) and the 2026 team names pass."""
    from mod_editor.core import nfl2k5_free_agents, nfl2k5_team_names_2026 as names
    retail = rr.load_image(RETAIL).to_body()
    edits = {k: v for k, v in source.items() if k not in ("roster_refresh", "created_history")}
    if nfl2k5_free_agents.is_pack_input(edits):
        edits = dict(edits, modern_free_agents="2026-10-05")
    if edits.get("modern_free_agents"):
        edits = dict(edits, restore_historic_spare_capacity=True)
    body, _receipt = rr.apply_body(retail, edits, scheme="one_pool", refresh_follows=True)
    with rr._outer_image()(RETAIL) as archive:
        entry = rr._entry(archive)
        header = archive.read(entry.virtual_offset, 32)
    payload, _ = names.apply(header + body)
    return payload[32:]


@unittest.skipUnless(_proof_inputs(), "the 64 MB roster proof needs the release pack roster, its validated 64 MB file "
                                      "(26522689) and the refresh's pinned base")
class SoftdrinkRosterFitProof(unittest.TestCase):
    """Coordinator 11/03: the 64 MB build keeps the pack's 2026 rosters. The Studio's fit (nfl2k5_console_memory.
    fit_roster_edits, M64A's retail fit as a library) on the healthy pack roster equals M64A's validated 64 MB file."""

    @classmethod
    def setUpClass(cls):
        cls.raw = HEALTHY.read_bytes()
        cls.source = json.loads(cls.raw.decode("utf-8"))
        cls.want = json.loads(FITTED_64.read_text(encoding="utf-8"))
        cls.sha = hashlib.sha256(cls.raw).hexdigest()

    def test_on_the_refresh_pinned_base_it_is_the_validated_file_byte_for_byte(self):
        variant, receipt = cm.fit_roster_edits(self.source, REFRESH_BASE.read_bytes(), source_sha256=self.sha)
        text = json.dumps(variant, indent=1, ensure_ascii=False) + "\n"
        self.assertEqual(hashlib.sha256(text.encode("utf-8")).hexdigest(), FITTED_64_SHA256)
        self.assertEqual((receipt["depth_candidates"], receipt["depth_kept"], receipt["club_players_kept"],
                          receipt["club_players_dropped"]), (533, 0, 19, 100))
        self.assertEqual(receipt["dropped_xbe_sections"], ["draft_pick_ownership", "hback_roles"])

    @unittest.skipUnless(RETAIL.is_file(), "needs the retail disc image (NFL2K5_RETAIL_XISO)")
    def test_on_the_users_own_dump_the_fitted_rosters_are_the_same(self):
        base = users_dump_base(self.source)
        variant, receipt = cm.fit_roster_edits(self.source, base, source_sha256=self.sha)
        self.assertEqual(variant["roster_refresh"], self.want["roster_refresh"])
        self.assertEqual(sorted(k for k in set(variant) | set(self.want) if variant.get(k) != self.want.get(k)),
                         ["fa3_free_agent_depth"])
        mine, theirs = variant["fa3_free_agent_depth"], self.want["fa3_free_agent_depth"]
        # the only difference: the receipt records the base the fit ran on (this build's roster, not the authoring disc)
        self.assertEqual(sorted(k for k in set(mine) | set(theirs) if mine.get(k) != theirs.get(k)),
                         ["base_sha256", "final_body_sha256", "retail_capacity"])
        self.assertEqual(sorted(k for k in set(mine["retail_capacity"]) | set(theirs["retail_capacity"])
                                if mine["retail_capacity"].get(k) != theirs["retail_capacity"].get(k)),
                         ["base_sha256", "final_body_sha256"])
        self.assertEqual((receipt["club_players_kept"], receipt["import_vacancies_after_floor"]), (19, 116))

    def test_the_fitted_64_mb_plan_validates_and_fits_with_the_default_uniforms(self):
        if cm.model() is None:
            self.skipTest("no memory model in this build")
        plan = mod_build.apply_preset(mod_build.BuildPlan("s", "t", console_memory=64), "softdrink_experimental")
        plan = mod_build.BuildPlan(**{**{f.name: getattr(plan, f.name) for f in fields(plan)}, "roster_edits": str(HEALTHY)})
        plan = mod_build.BuildPlan(**{**{f.name: getattr(plan, f.name) for f in fields(plan)},
                                      **cm.recommended_profile(plan)})
        self.assertTrue(cm.roster_fit_applies(plan))
        self.assertEqual(mod_build.validate_plan(plan), [])
        prediction = cm.predict(cm.model_plan(plan))
        self.assertIsNotNone(prediction)
        self.assertFalse(cm.refuses(prediction), cm.budget_line(prediction))
        self.assertTrue(prediction["fits"] or prediction["primary_fits"], cm.budget_line(prediction))


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
        self.assertEqual(cm.STATUS_64, "experimental, estimated, not yet tested on a real Xbox or hakuX")
        for text in (cm.NOTE_64, cm.HELP_TEXT, cm.SHARE_NOTE, cm.NEXT_STEPS_64, cm.LABELS[64]):
            self.assertIn(cm.STATUS_64, text)
        self.assertIn("For the full experience use xemu at 128 MB", cm.NOTE_64)
        self.assertEqual(cm.LABELS[128], "128 MB, xemu (full SOFTDRINK)")
        self.assertEqual(cm.LABELS[64], "64 MB, original Xbox and Android hakuX (experimental, estimated, not yet "
                                        "tested on a real Xbox or hakuX)")
        self.assertIn("the 2026 rosters, fitted to the original game's roster size", cm.SHARE_NOTE)
        for text in (cm.ROSTER_FIT_NOTE, cm.SHARE_NOTE):
            self.assertNotIn("\u2014", text)


if __name__ == "__main__":
    unittest.main()

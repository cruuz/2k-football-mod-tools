"""b81 #43 (coordinator ruling 2, 11/27): a 64 MB build fits again under v0.10 code.

Noah (11/18): "only update the 128 megabyte version for the time being". Two beta 81 fixed pages at the top of the
scale-out pool, helmet side numbers (#18, 0x152D000) and the classic Seamen's crowd (#33, 0x1532000), were on in the
presets at 64 MB and cost a 64 MB build about 356 KB at NRG Stadium (s37): the v0.9 64 MB recipe no longer fit. They are
now 128 MB only, like modern numbers (review M1) and the gadget plays: a 64 MB plan clears them, the memory model refuses
them, and their steps refuse them in place. A plan that does not fit names a set of options that, turned off together,
makes it fit (computed and checked by the model), and points 64 MB players to the v0.9 64 MB pack (R56).
"""
import json
import os
import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import mod_build, modpack_sources  # noqa: E402
from mod_editor.core import nfl2k5_console_memory as cm, nfl2k5_memory_budget as mb  # noqa: E402

PAGES = ("helmet_side_numbers", "classic_crowd")
SOURCES = Path(os.environ.get("NFL2K5_B81_STANDARD_SOURCES",
                              "/media/noah/Storage/2K5-project/beta81/v10-sources-128")).parent


class OneHundredTwentyEightOnly(unittest.TestCase):
    def test_both_pages_need_128_mb(self):
        rules = cm.requires_128()
        for key in PAGES:
            self.assertIn(key, rules)
            self.assertIn("fixed page", mb.REQUIRES_128[key])

    def test_every_preset_clears_them_at_64_mb_and_the_experimental_keeps_them_at_128(self):
        for name in mod_build.PRESETS:
            plan = mod_build.apply_preset(mod_build.BuildPlan("s", "t", console_memory=64), name)
            with self.subTest(preset=name):
                self.assertEqual([key for key in PAGES if getattr(plan, key)], [])
        full = mod_build.apply_preset(mod_build.BuildPlan("s", "t"), "softdrink_experimental")
        self.assertEqual([getattr(full, key) for key in PAGES], [True, True])

    def test_a_64_mb_plan_that_asks_for_them_is_refused_before_any_disc_work(self):
        base = mod_build.apply_preset(mod_build.BuildPlan("s", "t", console_memory=64), "softdrink_basic")
        for key, words in (("helmet_side_numbers", "Helmet side numbers"), ("classic_crowd", "classic Seamen")):
            with self.subTest(option=key):
                problems = cm.problems(replace(base, **{key: True}), fit=False)
                self.assertEqual(len(problems), 1)
                self.assertIn("cannot include", problems[0])

    def test_the_helmet_sides_step_refuses_in_place_at_64_mb(self):
        plan = mod_build.BuildPlan("s", "t", console_memory=64, helmet_side_numbers=True)
        with self.assertRaises(ValueError) as caught:
            mod_build._apply_helmet_side_numbers(plan, Path("t.iso"), {"steps": [], "result": {}}, lambda *_: None)
        self.assertEqual(str(caught.exception), mod_build.HELMET_SIDES_NEED_128)

    def test_the_crowd_step_refuses_in_place_at_64_mb_rather_than_leaving_it_out(self):
        import inspect
        source = inspect.getsource(mod_build._build)
        refusal = source.index("raise ValueError(CLASSIC_CROWD_NEEDS_128)")
        self.assertLess(refusal, source.index('_optional(receipt, target, progress, "classic_crowd")'))


class RefusalAdvice(unittest.TestCase):
    """The memory model itself (no game files): an over-budget 64 MB plan names a checked, minimal set."""

    @classmethod
    def setUpClass(cls):
        base = mod_build.apply_preset(mod_build.BuildPlan("s", "t", console_memory=64), "softdrink_basic")
        cls.plan = cm.without_forced(replace(base, scorebug=True, hair_styles=True, modern_lambeau=True, my_career=True))
        cls.prediction = mb.predict(cls.plan, 64)

    def test_the_named_set_turned_off_together_fits_and_each_member_is_needed(self):
        self.assertFalse(self.prediction["fits"])
        found = self.prediction["fitting_set"]
        self.assertTrue(found)
        off = lambda groups: replace(self.plan, **{f: mb.off_value(f) for g in groups for f in g})  # noqa: E731
        self.assertTrue(mb.predict(off(found), 64)["fits"])
        for group in found:
            with self.subTest(dropped=group[0]):
                self.assertFalse(mb.predict(off([g for g in found if g is not group]), 64)["fits"])

    def test_the_refusal_names_that_set_and_the_64_mb_pack(self):
        text = cm.refusal(cm.predict(self.plan))
        self.assertIn("together makes it fit (the memory model checked this set)", text)
        for group in self.prediction["fitting_set"]:
            self.assertIn(cm.label(group[0]), text)
        self.assertNotIn("for example", text)
        self.assertTrue(text.endswith(cm.POINTER_64), text)
        self.assertIn("SOFTDRINK-2K28-v0.9-64MB.2k5patch", cm.POINTER_64)

    def test_a_plan_that_fits_has_no_set_to_name(self):
        fitting = mb.predict(mod_build.apply_preset(mod_build.BuildPlan("s", "t", console_memory=64), "softdrink_basic"), 64)
        self.assertTrue(fitting["fits"])
        self.assertEqual(fitting["fitting_set"], [])


@unittest.skipUnless((SOURCES / "v09-sources-64" / "SOFTDRINK-build-recipe.json").is_file(),
                     "private release sources absent: NFL2K5_B81_STANDARD_SOURCES")
class SixtyFourMegabyteRecipes(unittest.TestCase):
    def test_the_v09_and_v010_64_mb_recipes_validate_under_this_code(self):
        for folder in ("v09-sources-64", "v10-sources-64"):
            path = SOURCES / folder / "SOFTDRINK-build-recipe.json"
            if not path.is_file():
                continue
            with self.subTest(recipe=folder):
                plan = modpack_sources.build_plan(json.loads(path.read_text(encoding="utf-8")))
                self.assertEqual(plan.console_memory, 64)
                self.assertEqual([key for key in PAGES if getattr(plan, key)], [])
                self.assertEqual(mod_build.validate_plan(plan), [])


if __name__ == "__main__":
    unittest.main()

"""b81 gillette-off: the SOFTDRINK 2K28 release build keeps the game's own Gillette Stadium.

The owner's ruling after playing: the custom Gillette Stadium model looked wrong and the game's original is far better.
The model stays in the Studio as an experimental option that is off by default; the release recipe must not turn it on.
Synthetic data only (no game files)."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_project_check as pc  # noqa: E402

GATES = ROOT / "data" / "nfl2k5_release_gates.json"


class SoftdrinkKeepsRetailGillette(unittest.TestCase):
    def test_the_softdrink_release_recipe_does_not_enable_modern_gillette(self):
        document = json.loads(GATES.read_text(encoding="utf-8"))
        recipe = next(g for g in document["gates"] if g["id"] == "softdrink")
        self.assertIs(recipe["overrides"].get("modern_gillette"), False)
        softdrink = next(g for g in pc.release_gates() if g["id"] == "softdrink")
        self.assertIs(softdrink["options"]["modern_gillette"], False)

    def test_the_recipe_builds_a_plan_with_the_option_off(self):
        document = json.loads(GATES.read_text(encoding="utf-8"))
        recipe = next(g for g in document["gates"] if g["id"] == "softdrink")
        plan = mod_build.apply_preset(mod_build.BuildPlan("a.iso", "b.iso"), recipe["preset"])
        for key, value in recipe["overrides"].items():
            if key in {"modern_gillette", "modern_venues_2026"}:
                setattr(plan, key, value)
        self.assertIs(plan.modern_gillette, False)

    def test_no_preset_and_no_default_enable_it(self):
        self.assertIs(mod_build.BuildPlan("a.iso", "b.iso").modern_gillette, False)
        for name, values in mod_build.PRESETS.items():
            self.assertIs(values.get("modern_gillette"), False, name)

    def test_the_model_stays_available_as_an_option(self):
        self.assertIn("modern_gillette", mod_build.availability())

    def test_with_it_off_the_venue_art_treats_the_patriots_like_every_other_club(self):
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        art = dict(venues={p: None for p in ("s16", "s12", "s13")}, league={"nfl_shield": {}}, skipped=[])
        off = [p for p, _t in mv.venues_to_write(art, gillette=False)]
        on = [p for p, _t in mv.venues_to_write(art, gillette=True)]
        self.assertIn("s16", off)
        self.assertNotIn("s16", on)
        self.assertEqual(set(off) - set(on), {"s16"})

    def test_a_project_that_turns_it_on_is_named_untested(self):
        plan = mod_build.BuildPlan("r.iso", "o.iso", modern_gillette=True)
        found = pc.untested_options(plan, platform="linux")
        self.assertIn("modern_gillette", {i["option"] for i in found["options"]})


if __name__ == "__main__":
    unittest.main()

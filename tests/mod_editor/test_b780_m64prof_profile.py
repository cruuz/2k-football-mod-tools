"""b780 m64prof: the recommended 64 MB profile leaves no option on without what it needs.

ship10's 64 MB build 1 (11/04) stopped in the pre-build checks: the profile turned owners off but left the values that
depend on them ("a collision level requires momentum_collisions", "Historic season rosters require historic local Team
Select") and named two off values None ("Jersey number sizes must be an object of kit: scale"). A user's 64 MB Studio
build would have hit the same refusals. The profile now closes over the build's own dependency rules
(nfl2k5_build_settings.build_requires: the Studio's option table and the value rules) and uses the BuildPlan's own off
values. The slow test runs every shipped preset with the 64 MB set through the build's preflight (retail source needed).
"""
from __future__ import annotations

import dataclasses
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools", ROOT / "tests" / "mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_build_settings as settings  # noqa: E402
from mod_editor.core import nfl2k5_console_memory as cm  # noqa: E402
from mod_editor.core import nfl2k5_memory_budget as mb  # noqa: E402

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_XISO", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
FIELDS = {f.name: f for f in dataclasses.fields(mod_build.BuildPlan)}


def default_of(name):
    item = FIELDS[name]
    return item.default_factory() if item.default_factory is not dataclasses.MISSING else item.default


def preset_plan(name, source="retail.iso", target="out.iso"):
    return mod_build.apply_preset(mod_build.BuildPlan(str(source), str(target)), name)


def with_64_set(plan):
    """What the Studio does with the recommended 64 MB set: the product wrapper's profile on the plan."""
    return dataclasses.replace(plan, **cm.recommended_profile(plan))


def plans():
    yield "the v0.9 pack", None
    for name in mod_build.PRESETS:
        yield name, preset_plan(name)


class Closure(unittest.TestCase):
    def test_the_dependency_table_lives_in_core_and_the_pages_read_it(self):
        from mod_editor.gui import beta62_options as r62_ui
        self.assertIs(r62_ui.REQUIRES, settings.REQUIRES)
        rules = settings.build_requires()
        self.assertEqual(rules["historic_rosters_2026"], ("historic_teams_quick_game",))
        self.assertEqual(rules["momentum_collision_level"], ("momentum_collisions",))
        self.assertEqual(rules["momentum_contact"], ("momentum",))

    def test_no_option_stays_on_without_what_it_needs(self):
        rules = settings.build_requires()
        for label, plan in plans():
            merged = {**mb.options(plan), **mb.recommended_64_profile(plan)}
            for child, parents in rules.items():
                if mb.on(merged, child):
                    for parent in parents:
                        self.assertTrue(mb.on(merged, parent), f"{label}: {child} stays on without {parent}")

    def test_the_three_refusals_of_64_mb_build_1(self):
        profile = mb.recommended_64_profile(None)
        merged = {**mb.options(None), **profile}
        self.assertFalse(mb.on(merged, "historic_teams_quick_game"))
        self.assertIs(merged["historic_rosters_2026"], False)
        self.assertFalse(merged["momentum_collisions"] and merged["momentum_collision_level"])
        if not merged["momentum_collisions"]:
            self.assertEqual(merged["momentum_collision_level"], 0)
        self.assertEqual(profile["team_number_scale"], {})
        self.assertNotIn(None, profile.values())
        # the off value of each option the model can turn off is the BuildPlan's own (never None)
        for key in ("team_number_scale", "modern_venues_2026", "momentum_collision_level"):
            self.assertEqual(mb.off_value(key), default_of(key), key)

    def test_every_profile_value_has_the_build_plan_type(self):
        for label, plan in plans():
            for key, value in mb.recommended_64_profile(plan).items():
                if key in FIELDS:
                    self.assertIsInstance(value, type(default_of(key)), f"{label}: {key}={value!r}")

    def test_the_off_values_are_fresh_copies(self):
        a, b = mb.recommended_64_profile(None), mb.recommended_64_profile(None)
        a["team_number_scale"]["13H0"] = 1.1
        self.assertEqual(b["team_number_scale"], {})
        self.assertEqual(mb.OFF_VALUES["team_number_scale"], {})

    def test_a_rule_added_to_the_table_is_followed(self):
        """A future dependency cannot reopen this: a rule added to the one table is closed over with no other change."""
        plan = preset_plan("softdrink_experimental")
        merged = {**mb.options(plan), **mb.recommended_64_profile(plan)}
        kept = next(f for f in mb.PROFILE_64_PATCHES if mb.on(merged, f))
        gone = next(f for f in mb.PROFILE_64_TRIM if mb.on(mb.options(plan), f))
        rules = dict(settings.REQUIRES, **{kept: (gone,)})
        with mock.patch.object(settings, "REQUIRES", rules):
            profile = mb.recommended_64_profile(plan)
        self.assertEqual(profile[kept], mb.off_value(kept))

    def test_validate_plan_accepts_every_preset_with_the_64_mb_set(self):
        for name in mod_build.PRESETS:
            plan = with_64_set(preset_plan(name))
            self.assertEqual(plan.console_memory, 64)
            self.assertEqual(mod_build.validate_plan(plan), [], name)

    def test_128_mb_plans_are_untouched(self):
        for name in mod_build.PRESETS:
            plan = preset_plan(name)
            self.assertEqual(plan.console_memory, 128)
            self.assertNotIn("console_memory", plan.to_recipe())


@unittest.skipUnless(RETAIL.is_file(), "retail XISO absent (set NFL2K5_RETAIL_XISO)")
class Preflight(unittest.TestCase):
    """Every shipped preset with the 64 MB set passes the build's own preflight (about 156 s each)."""

    def test_every_preset_with_the_64_mb_set_passes_the_build_preflight(self):
        for name in mod_build.PRESETS:
            with self.subTest(preset=name), tempfile.TemporaryDirectory() as folder:
                plan = with_64_set(preset_plan(name, RETAIL, Path(folder) / "out.xiso.iso"))
                self.assertEqual(mod_build.validate_plan(plan), [], name)
                receipt = mod_build._build(plan, None, _preflight_only=True)
                self.assertIsInstance(receipt, dict, name)
                self.assertFalse(Path(plan.target).exists(), name)


class Page(unittest.TestCase):
    """The Build tab at 64 MB: the recommended set leaves the dependent options off, and the page's plan is accepted."""

    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_the_recommended_set_turns_the_dependent_options_off_with_their_parents(self):
        from mod_editor.gui.build_panel_qt import BuildPanel
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        source = Path(folder.name) / "retail.iso"
        source.write_bytes(b"\0" * 4096)
        panel = BuildPanel()
        self.addCleanup(lambda: (panel.deleteLater(), self.app.processEvents()))
        state = {key: "retail" for key in panel._boxes()}
        state.update(path=str(source), container="xiso", throw=None, speed_threshold="retail")
        panel.apply_state(state)
        panel.target_field.setText(str(Path(folder.name) / "out.iso"))
        panel.apply_preset("softdrink_experimental")
        ticked = []
        for key in ("historic_teams_quick_game", "historic_rosters_2026", "momentum_collisions"):
            box = getattr(panel, key + "_check", None)
            if box is not None and box.isEnabled():
                box.setChecked(True)
                ticked.append(key)
        self.assertIn("momentum_collisions", ticked)
        before = panel.plan()
        self.assertTrue(before.momentum_collisions and before.momentum_collision_level > 0)
        panel.set_console_memory(64)
        panel.apply_recommended_64()
        plan = panel.plan()
        rules = settings.build_requires()
        flat = mb.options(plan)
        for child, parents in rules.items():
            if mb.on(flat, child):
                for parent in parents:
                    self.assertTrue(mb.on(flat, parent), f"{child} stays on without {parent}")
        for key in ticked:
            if not mb.on(flat, rules.get(key, (key,))[0]) or key in mb.recommended_64_profile(before):
                box = getattr(panel, key + "_check")
                self.assertFalse(box.isChecked() and not all(mb.on(flat, p) for p in rules.get(key, ())), key)
        if not plan.momentum_collisions:
            self.assertEqual(plan.momentum_collision_level, 0)
            self.assertFalse(panel.momentum_collision_level.isEnabled() and panel.momentum_collisions_check.isChecked())
        if not plan.historic_teams_quick_game:
            self.assertFalse(plan.historic_rosters_2026)
            self.assertFalse(panel.historic_rosters_2026_check.isChecked())
        self.assertIsInstance(plan.team_number_scale, dict)
        self.assertIsInstance(plan.modern_venues_2026, str)
        self.assertEqual(mod_build.validate_plan(plan), [])


if __name__ == "__main__":
    unittest.main()

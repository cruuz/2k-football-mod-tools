"""b780-m64b: the Build tab's console memory target, offscreen.

"128 MB, xemu (full SOFTDRINK)" is the default; "64 MB, original Xbox and Android hakuX (experimental)" turns off and
greys out every option that needs 128 MB or the real Xbox kernel (with a plain reason), shows what each remaining option
costs from the memory model, says whether the selection is predicted to fit, applies the recommended 64 MB set, and
refuses a selection that will not fit. Back at 128 MB the page, its plan and its recipe are exactly what they were.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests" / "mod_editor", ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_console_memory as cm  # noqa: E402
from mod_editor.gui.build_panel_qt import BuildPanel  # noqa: E402
from test_b780_m64b_console_memory import fake_model, with_model, without_model  # noqa: E402

FORCED = ("k128_memory", "k128_roster_heap", "k128_early", "guardian_overlay", "reserves_16", "created_teams_extra")


class _Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / "retail.iso"
        self.source.write_bytes(b"\0" * 4096)

    def page(self) -> BuildPanel:
        panel = BuildPanel()
        self.addCleanup(lambda: (panel.deleteLater(), self.app.processEvents()))
        state = {key: "retail" for key in panel._boxes()}
        state.update(path=str(self.source), container="xiso", throw=None, speed_threshold="retail")
        panel.apply_state(state)
        panel.target_field.setText(str(Path(self.tmp.name) / "out.iso"))
        return panel

    def softdrink(self, panel: BuildPanel) -> None:
        """The SOFTDRINK 2K28 recipe's base (Experimental) plus every option that needs 128 MB (its recipe has K128 and
        the roster heap on; the others are ticked here so each lock is seen)."""
        panel.apply_preset("softdrink_experimental")
        for key in FORCED:
            getattr(panel, key + "_check").setChecked(True)


class Selector(_Page):
    def test_the_selector_offers_both_targets_and_defaults_to_128(self):
        with without_model():
            panel = self.page()
            combo = panel.console_memory_combo
            self.assertEqual([combo.itemText(i) for i in range(combo.count())],
                             ["128 MB, xemu (full SOFTDRINK)", "64 MB, original Xbox and Android hakuX (experimental)"])
            self.assertEqual([combo.itemData(i) for i in range(combo.count())], [128, 64])
            self.assertEqual(panel.console_memory(), 128)
            self.assertEqual(panel.plan().console_memory, 128)
            self.assertNotIn("console_memory", panel.plan().to_recipe())
            self.assertEqual(panel.console_memory_caption.text(), "Console memory")
            self.assertEqual(combo.accessibleName(), "Console memory")
            self.assertIn("untested on a real Xbox and in hakuX", combo.toolTip())
            self.assertEqual(panel.console_memory_note.text(), cm.NOTE_128)
            self.assertFalse(panel.memory_budget_label.isVisibleTo(panel))
            self.assertFalse(panel.memory_recommended_button.isVisibleTo(panel))

    def test_choosing_64_shows_the_experimental_note(self):
        with without_model():
            panel = self.page()
            panel.console_memory_combo.setCurrentIndex(panel.console_memory_combo.findData(64))
            self.assertEqual(panel.console_memory(), 64)
            self.assertEqual(panel.plan().console_memory, 64)
            self.assertEqual(panel.plan().to_recipe()["console_memory"], 64)
            self.assertEqual(panel.console_memory_note.text(), cm.NOTE_64)
            self.assertIn("EXPERIMENTAL", panel.console_memory_note.text())
            self.assertIn("For the full experience use xemu at 128 MB", panel.console_memory_note.text())
            self.assertTrue(panel.memory_budget_label.isVisibleTo(panel))
            self.assertTrue(panel.memory_recommended_button.isVisibleTo(panel))
            self.assertEqual(panel.memory_recommended_button.text(), "Use the recommended 64 MB set")
            text = panel.confirmation_text(panel.plan())
            self.assertIn("Console memory: 64 MB, original Xbox and Android hakuX (experimental)", text)
            self.assertIn("Untested on a real Xbox and in hakuX", text)


class ForcedOff(_Page):
    def test_64_turns_off_and_greys_out_every_option_that_needs_128_with_the_reason(self):
        with without_model():
            panel = self.page()
            self.softdrink(panel)
            before = panel.plan()
            self.assertTrue(all(getattr(before, key) for key in FORCED))
            panel.set_console_memory(64)
            plan = panel.plan()
            for key in FORCED:
                box = getattr(panel, key + "_check")
                with self.subTest(option=key):
                    self.assertFalse(box.isChecked())
                    self.assertFalse(box.isEnabled())
                    self.assertFalse(getattr(plan, key))
                    self.assertTrue(panel._badges[key].text().startswith("Off at 64 MB: "), panel._badges[key].text())
                    self.assertIn("Off for the 64 MB build", box.toolTip())
                    self.assertIn("Choose Console memory 128 MB", box.toolTip())
            self.assertEqual(panel._badges["k128_memory"].text(),
                             "Off at 64 MB: needs xemu at 128 MB and the real Xbox kernel")
            self.assertEqual(panel._badges["guardian_overlay"].text(), "Off at 64 MB: needs 128 MB")
            self.assertEqual(panel._badges["k128_roster_heap"].text(), "Off at 64 MB: needs the memory above 64 MB")
            self.assertEqual(mod_build.validate_plan(plan), [])
            # everything else the preset ticked is still ticked
            for key in ("throw", "catch_slider", "hair_styles", "modern_coaches", "scorebug"):
                self.assertTrue(getattr(plan, key), key)
            # a ticked option the target refuses cannot be ticked back while 64 MB is chosen
            panel.k128_memory_check.setChecked(True)
            self.assertFalse(panel.plan().k128_memory)

    def test_back_to_128_gives_every_option_back_exactly(self):
        with without_model():
            panel = self.page()
            self.softdrink(panel)
            plan = panel.plan()
            recipe = json.dumps(plan.to_recipe(), sort_keys=True, default=str)
            badges = {key: panel._badges[key].text() for key in FORCED}
            tips = {key: getattr(panel, key + "_check").toolTip() for key in FORCED}
            panel.set_console_memory(64)
            panel.set_console_memory(128)
            again = panel.plan()
            self.assertEqual(again.console_memory, 128)
            self.assertEqual(json.dumps(again.to_recipe(), sort_keys=True, default=str), recipe)
            for key in FORCED:
                box = getattr(panel, key + "_check")
                self.assertTrue(box.isEnabled(), key)
                self.assertTrue(box.isChecked(), key)
                self.assertEqual(panel._badges[key].text(), badges[key])
                self.assertEqual(box.toolTip(), tips[key])
            self.assertEqual(panel.console_memory_note.text(), cm.NOTE_128)

    def test_presets_at_64_name_the_reason_and_come_back_at_128(self):
        with without_model():
            panel = self.page()
            panel.set_console_memory(64)
            result = panel.apply_preset("softdrink_experimental")
            panel.guardian_overlay_check.setChecked(True)     # disabled at 64: stays off
            self.assertFalse(panel.plan().guardian_overlay)
            self.assertNotIn("guardian_overlay", result["applied"])

    def test_a_disc_that_already_has_k128_cannot_make_a_64_mb_build(self):
        with without_model():
            panel = self.page()
            state = {key: "retail" for key in panel._boxes()}
            state.update(path=str(self.source), container="xiso", throw=None, speed_threshold="retail",
                         k128_memory="applied")
            panel.apply_state(state)
            panel.target_field.setText(str(Path(self.tmp.name) / "out.iso"))
            panel.throw_check.setChecked(True)
            panel.set_console_memory(64)
            self.assertTrue(panel.k128_memory_check.isChecked())     # it is on the disc; the page says so
            blocker = panel.blocker()
            self.assertIn("This disc already has 128 MB memory (K128, xemu set to 128 MB)", blocker)
            self.assertIn("unmodified game disc", blocker)
            self.assertFalse(panel.build_button.isEnabled())
            panel.set_console_memory(128)
            self.assertEqual(panel.blocker(), "")


class Budget(_Page):
    def test_each_remaining_option_shows_its_memory_cost_at_64_only(self):
        model = fake_model(costs={"hair_styles": 150 * 1024, "modern_coaches": 600, "k128_memory": 4096})
        with with_model(model):
            panel = self.page()
            for key in ("hair_styles", "modern_coaches", "k128_memory"):
                getattr(panel, key + "_check").setChecked(True)
            self.assertEqual(panel._memory_cost_labels, {})
            panel.set_console_memory(64)
            self.assertTrue(panel.wait_for_memory_budget())
            hair = panel._memory_cost_labels["hair_styles"]
            self.assertTrue(hair.isVisibleTo(panel))
            self.assertEqual(hair.text(), "Memory at 64 MB: 150 KB (estimate)")
            self.assertEqual(panel._memory_cost_labels["modern_coaches"].text(), "Memory at 64 MB: under 1 KB (estimate)")
            self.assertNotIn("k128_memory", panel._memory_cost_labels)  # forced off: its reason, not a cost
            panel.set_console_memory(128)
            self.assertFalse(hair.isVisibleTo(panel))

    def test_budget_line_when_it_fits(self):
        with with_model(fake_model(fits=True, spare=412 * 1024)):
            panel = self.page()
            panel.throw_check.setChecked(True)
            panel.set_console_memory(64)
            # the model answers off the page thread: until then the line says so and Make my disc waits
            self.assertEqual(panel.memory_budget_label.text(), cm.CHECKING)
            self.assertEqual(panel.blocker(), cm.CHECKING)
            self.assertFalse(panel.build_button.isEnabled())
            self.assertTrue(panel.wait_for_memory_budget())
            self.assertEqual(panel.memory_budget_label.text(),
                             "Predicted to fit with 412 KB to spare at the hardest stadium, Lambeau Field (s10). This is "
                             "an estimate from the memory model, not a measurement on a console.")
            self.assertEqual(panel.blocker(), "")
            self.assertTrue(panel.build_button.isEnabled())

    def test_budget_line_and_refusal_when_it_does_not_fit(self):
        model = fake_model(fits=False, spare=0, over=300 * 1024,
                           suggestions=[("hair_styles", 200 * 1024), ("modern_coaches", 150 * 1024)])
        with with_model(model):
            panel = self.page()
            panel.hair_styles_check.setChecked(True)
            panel.modern_coaches_check.setChecked(True)
            panel.set_console_memory(64)
            self.assertTrue(panel.wait_for_memory_budget())
            line = panel.memory_budget_label.text()
            self.assertTrue(line.startswith("Will not fit: remove 300 KB (hardest stadium, Lambeau Field (s10)); for "
                                            "example turn off "), line)
            self.assertIn(panel.hair_styles_check.text() + " (200 KB)", line)
            self.assertIn(panel.modern_coaches_check.text() + " (150 KB)", line)
            blocker = panel.blocker()
            self.assertTrue(blocker.startswith("The 64 MB build will not fit: remove 300 KB"), blocker)
            self.assertIn(panel.hair_styles_check.text(), blocker)
            self.assertFalse(panel.build_button.isEnabled())
            self.assertEqual(panel.blocker_label.text(), blocker)
            # a changed selection is a new question: the old answer is never shown for it
            panel.throw_check.setChecked(True)
            self.assertEqual(panel.memory_budget_label.text(), cm.CHECKING)
            self.assertTrue(panel.wait_for_memory_budget())
            self.assertTrue(panel.memory_budget_label.text().startswith("Will not fit"))
            panel.set_console_memory(128)
            self.assertEqual(panel.blocker(), "")      # the 128 MB build never asks the 64 MB model
            self.assertFalse(panel.memory_budget_label.isVisibleTo(panel))

    def test_no_model_says_so(self):
        with without_model():
            panel = self.page()
            panel.set_console_memory(64)
            self.assertIn("cannot predict whether this selection fits in 64 MB", panel.memory_budget_label.text())

    def test_the_recommended_set_applies_the_model_profile(self):
        model = fake_model(profile={"hair_styles": False, "modern_coaches": False, "throw": True})
        with with_model(model):
            panel = self.page()
            self.softdrink(panel)
            self.assertTrue(panel.hair_styles_check.isChecked())
            result = panel.apply_recommended_64()
            plan = panel.plan()
            self.assertEqual(plan.console_memory, 64)
            self.assertFalse(plan.hair_styles)
            self.assertFalse(plan.modern_coaches)
            self.assertTrue(plan.throw)
            for key in FORCED:
                self.assertFalse(getattr(plan, key), key)
            self.assertIn("hair_styles", result["off"])
            self.assertIn("Recommended 64 MB set applied: turned off", panel.memory_action_label.text())
            self.assertIn(panel.hair_styles_check.text(), panel.memory_action_label.text())
            # the set's own choices stay when going back to 128 MB; only what 64 MB forced off comes back
            panel.set_console_memory(128)
            self.assertFalse(panel.plan().hair_styles)
            for key in FORCED:
                self.assertTrue(getattr(panel.plan(), key), key)

    def test_the_recommended_set_without_a_model(self):
        with without_model():
            panel = self.page()
            panel.apply_recommended_64()
            self.assertEqual(panel.console_memory(), 64)
            self.assertIn("no recommendation in this build", panel.memory_action_label.text())


class SavedAndShared(_Page):
    def test_project_settings_round_trip_and_old_projects_read_128(self):
        with without_model():
            panel = self.page()
            self.softdrink(panel)
            old = panel.project_build_settings()
            self.assertNotIn("console_memory", old)
            panel.set_console_memory(64)
            saved64 = panel.project_build_settings()
            self.assertEqual(saved64["console_memory"], 64)
            panel.restore_project_build_settings(old)       # a project saved before the option: 128 MB
            self.assertEqual(panel.console_memory(), 128)
            self.assertTrue(panel.k128_memory_check.isEnabled())
            self.assertTrue(panel.plan().k128_memory)
            panel.restore_project_build_settings(saved64)
            self.assertEqual(panel.console_memory(), 64)
            self.assertFalse(panel.plan().k128_memory)
            self.assertFalse(panel.k128_memory_check.isEnabled())

    def test_customize_softdrink_for_64_mb_sets_the_build_tab(self):
        with without_model():
            panel = self.page()
            project = Path(self.tmp.name) / "league.json"
            project.write_text("{}")
            recipe = {"preset": "softdrink_experimental", "project": str(project),
                      "overrides": {"k128_memory": True, "k128_roster_heap": True}}
            panel.load_softdrink_sources({**recipe, "console_memory": 64})
            self.assertEqual(panel.console_memory(), 64)
            self.assertFalse(panel.plan().k128_memory)
            panel.set_console_memory(128)                   # the pack's 128 MB options come back
            self.assertTrue(panel.plan().k128_memory)
            self.assertTrue(panel.plan().k128_roster_heap)
            panel.load_softdrink_sources(recipe)            # no choice: the full 128 MB build
            self.assertEqual(panel.console_memory(), 128)

    def test_share_offers_the_choice_and_says_the_pack_is_128(self):
        from mod_editor.gui.share_panel_qt import SharePanel
        share = SharePanel()
        self.addCleanup(share.deleteLater)
        combo = share.customize_memory_combo
        self.assertEqual([combo.itemData(i) for i in range(combo.count())], [128, 64])
        self.assertEqual(share.customize_memory(), 128)
        self.assertEqual(share.customize_memory_caption.text(), "Build for")
        self.assertIn("full 128 MB build for xemu", share.memory_note.text())
        self.assertIn("2026 rosters need 128 MB for now", share.memory_note.text())
        combo.setCurrentIndex(combo.findData(64))
        self.assertEqual(share.customize_memory(), 64)

    def test_next_steps_of_a_64_mb_disc(self):
        from mod_editor.gui.ux_text import disc_next_steps
        self.assertEqual(disc_next_steps("x.iso"), disc_next_steps("x.iso", console_memory=128))
        self.assertIn("System Memory to 128 MiB", disc_next_steps("x.iso"))
        text = disc_next_steps("x.iso", console_memory=64)
        self.assertIn("EXPERIMENTAL 64 MB build", text)
        self.assertIn("untested on both", text)
        self.assertNotIn("\u2014", text)


if __name__ == "__main__":
    unittest.main()

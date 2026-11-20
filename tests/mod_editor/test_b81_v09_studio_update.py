"""A released v0.9 disc accepts only the explicitly selected native updates."""
import contextlib
import io
import itertools
import os
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication

from mod_editor.core import mod_build as build, modpack_sources
from mod_editor.gui.build_panel_qt import BuildPanel
from tools import nfl2k5_modpack as cli


class ReleasedUpdates(unittest.TestCase):
    def test_cli_preserves_exact_selections(self):
        for title, ir, cards in itertools.product((False, True), repeat=3):
            with self.subTest(title=title, ir=ir, cards=cards), patch.object(build, "build", return_value={}) as run:
                args = ["update-v09", "--source", "old.iso", "--out", "new.iso", "--json"]
                if title:
                    args.append("--save-list-guard")
                if cards:
                    args.append("--backfield-cards")
                if ir:
                    args.append("--modern-ir")
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(cli.main(args), 0 if title or ir or cards else 2)
                if title or ir or cards:
                    plan = run.call_args.args[0]
                    self.assertIsInstance(plan, build._ReleasedV09Update)
                    self.assertEqual((plan.save_list_type_guard, plan.modern_injured_reserve, plan.backfield_cards),
                                     (title, ir, cards))
                else:
                    run.assert_not_called()

    def test_v09_native_updates_and_quarterback_setting_share_one_copy(self):
        for mode in ("retail", "realistic", "custom"):
            args = ["update-v09", "--source", "old.iso", "--out", "new.iso", "--modern-ir",
                    "--save-list-guard", "--backfield-cards", "--sim-qb-injuries", mode, "--json"]
            if mode == "custom":
                args += ["--qb-injury-rate", "0"]
            with self.subTest(mode=mode), patch.object(build, "build", return_value={}) as run:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(cli.main(args), 0)
                plan = run.call_args.args[0]
                self.assertIsInstance(plan, build._ReleasedV09Update)
                self.assertTrue(all(getattr(plan, key) for key in build.V09_UPDATE_CHOICES))
                self.assertEqual((plan.sim_qb_injuries, plan.sim_realism), (mode, mode != "retail"))
                if mode == "custom":
                    self.assertEqual(plan.sim_qb_injury_rate, 0)

    def test_share_and_mixed_plans_keep_the_complete_recipe(self):
        recipe = {"preset": "softdrink_experimental", "overrides": {"modern_injured_reserve": True,
                                                                    "backfield_cards": True, "helmet_finish": "glossy"}}
        plan = modpack_sources.build_plan(recipe, "src", "dst")
        self.assertIs(type(plan), build.BuildPlan)
        self.assertTrue(plan.modern_injured_reserve and plan.backfield_cards and plan.sim_realism)
        scoped = build.v09_disc_update("src", "dst", backfield_cards=True)
        with self.assertRaisesRegex(ValueError, "additional v0.9 changes"):
            build.preflight_plan(replace(scoped, music_unlock=True))
        with self.assertRaisesRegex(ValueError, "league artwork"):
            modpack_sources.build_project(scoped, "project.json", None)
        with self.assertRaisesRegex(ValueError, "include project changes"), patch.object(build, "_xbe_bytes") as read:
            build.build(scoped, _project_builder=Mock())
        read.assert_not_called()

    def test_refuses_unrecognized_executable_before_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "old.iso"
            source.write_bytes(b"changed")
            plan = build.v09_disc_update(source, source.with_name("new.iso"), modern_injured_reserve=True)
            with patch.object(build, "_xbe_bytes", return_value=b"changed"), patch.object(
                    build, "_copy_private_build_source") as copying, self.assertRaisesRegex(ValueError, "released"):
                build.preflight_plan(plan)
            copying.assert_not_called()
            self.assertFalse(Path(plan.target).exists())

    def test_refuses_foreign_or_current_title_guard_before_copy(self):
        guard, ir, cards = Mock(), Mock(), Mock()
        ir.status.return_value = "previous"
        cards.status.return_value = "retail"
        modules = {"nfl2k5_injured_reserve": ir, "nfl2k5_backfield_cards": cards,
                   "nfl2k5_save_list_type_guard": guard}
        plan = build.v09_disc_update("v09.iso", "copy.iso", save_list_type_guard=True)
        with (patch.object(build.tt, "is_disc_image", return_value=True),
              patch.object(build, "_v09_reference", return_value={"image_sha256": "known original"}),
              patch.object(build.tt.k128_patch, "read_settings", return_value={"require_128": True}),
              patch.object(build, "_xbe_bytes", return_value=b"source"),
              patch.object(build, "_core_module", side_effect=modules.get),
              patch.object(build, "_copy_private_build_source") as copying):
            for state in ("retail", "foreign", "applied"):
                with self.subTest(state=state), self.assertRaisesRegex(ValueError, "boot save-list"):
                    guard.status.return_value = state
                    build._update_v09_disc(plan, lambda *_: None, preflight=False, project=False)
            guard.apply.assert_not_called()
            copying.assert_not_called()

    def test_source_hash_is_checked_before_the_first_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "v09.iso"
            source.write_bytes(b"other contents")
            plan = build.v09_disc_update(source, source.with_name("new.iso"), backfield_cards=True)
            ir, cards = Mock(), Mock()
            ir.status.return_value = "previous"
            cards.status.return_value = "retail"
            cards.apply.return_value = (b"patched", {})
            modules = {"nfl2k5_injured_reserve": ir, "nfl2k5_backfield_cards": cards}
            with (patch.object(build, "_v09_reference", return_value={"image_sha256": "released"}),
                  patch.object(build.tt, "is_disc_image", return_value=True),
                  patch.object(build, "_core_module", side_effect=modules.get),
                  patch.object(build, "_xbe_bytes", return_value=b"original"),
                  patch.object(build.tt.k128_patch, "read_settings", return_value={"require_128": True}),
                  patch.object(build, "_copy_private_build_source") as copier,
                  patch.object(build, "_apply_backfield_cards") as writing):
                with self.assertRaisesRegex(ValueError, "differs"):
                    build._update_v09_disc(plan, lambda *_: None, preflight=True, project=False)
                copier.assert_not_called()
                with self.assertRaisesRegex(ValueError, "copied image differs"):
                    build._update_v09_disc(plan, lambda *_: None, preflight=False, project=False)
                copier.assert_called_once()
                writing.assert_not_called()


class BuildChoices(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "standard.iso"
        self.source.write_bytes(bytes(4096))
        self.panel = BuildPanel(available={})
        self.addCleanup(self.panel.deleteLater)
        self.state = dict(path=str(self.source), container="xiso", v09_standard_update=True,
                          modern_practice_field="foreign", modern_practice_field_team_logo="applied",
                          save_list_type_guard="previous", modern_injured_reserve="previous", backfield_cards="retail")
        self.panel.begin_reading(self.source)
        self.panel.apply_state(self.state)
        self.panel.target_field.setText(str(self.source.with_name("new.iso")))

    def test_released_disc_allows_the_quarterback_choice_alone_or_with_the_other_updates(self):
        self.panel.apply_state({**self.state, "sim_realism": "legacy", "k128_memory": "applied",
                                "k128_settings": {"require_128": True, "early": True, "roster_heap": True},
                                "sim_qb_injury_settings": {"status": "retail", "mode": "retail"}})
        mode = self.panel.qb_injury_mode
        mode.setCurrentIndex(mode.findData("realistic"))
        for other_updates in (False, True):
            for key in build.V09_UPDATE_CHOICES:
                box = self.panel._boxes()[key]
                if box.isChecked() != other_updates:
                    box.click()
            with self.subTest(other_updates=other_updates):
                self.assertFalse(self.panel.blocker())
                self.assertTrue(self.panel.build_button.isEnabled())
                self.assertIn("Simulated injuries (Realistic)", self.panel.selected_labels())
                plan = self.panel._plan_for_build()
                self.assertIsInstance(plan, build._ReleasedV09Update)
                self.assertEqual((plan.sim_qb_injuries, plan.sim_realism), ("realistic", True))
                self.assertEqual(tuple(getattr(plan, k) for k in build.V09_UPDATE_CHOICES), (other_updates,) * 3)

    def test_make_my_disc_selects_the_supported_options_independently(self):
        for flags in itertools.product((False, True), repeat=len(build.V09_UPDATE_CHOICES)):
            with self.subTest(flags=flags):
                for key, enabled in zip(build.V09_UPDATE_CHOICES, flags):
                    box = self.panel._boxes()[key]
                    self.assertTrue(box.isEnabled())
                    if box.isChecked() != enabled:
                        box.click()
                plan = self.panel._plan_for_build()
                self.assertEqual(isinstance(plan, build._ReleasedV09Update), any(flags))
                self.assertEqual(self.panel.build_button.isEnabled(), any(flags))
                if any(flags):
                    self.assertEqual(tuple(getattr(plan, key) for key in build.V09_UPDATE_CHOICES), flags)
                    self.assertEqual(len(self.panel.selected_labels()), sum(flags))

    def test_an_explicit_neighbor_even_at_default_or_an_authored_project_stays_full(self):
        self.panel.backfield_cards_check.click()
        self.panel.ceiling_spin.editingFinished.emit()
        self.assertIsInstance(self.panel._plan_for_build(), build._ReleasedV09Update)
        finish = self.panel.helmet_finish_combo
        finish.activated.emit(finish.currentIndex())
        self.assertIs(type(self.panel._plan_for_build()), build.BuildPlan)
        self.assertFalse(self.panel.build_button.isEnabled())
        self.panel.restore_project_build_settings({"backfield_cards": True, "helmet_finish": "glossy"})
        self.assertIs(type(self.panel._plan_for_build()), build.BuildPlan)

    def test_compact_or_an_unrecognized_disc_does_not_get_the_update(self):
        self.panel.apply_state({**self.state, "v09_standard_update": False})
        self.assertFalse(self.panel.modern_injured_reserve_check.isEnabled())
        self.assertFalse(self.panel._boxes()["save_list_type_guard"].isEnabled())
        self.panel.backfield_cards_check.click()
        self.assertFalse(self.panel.build_button.isEnabled())
        self.assertIs(type(self.panel._plan_for_build()), build.BuildPlan)


if __name__ == "__main__":
    unittest.main()

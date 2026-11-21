"""The scheduled-QB setting through projects, Build, Share sources and the rebuild CLI."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from mod_editor.core import mod_build, modpack_sources
from mod_editor.core import nfl2k5_build_settings as saved, nfl2k5_memory_budget as memory
from mod_editor.gui.build_panel_qt import BuildPanel
from tools import nfl2k5_modpack as cli


class ProjectSettings(unittest.TestCase):
    def test_old_source_files_preserve_existing_simulator(self):
        for preset in mod_build.PRESETS:
            for target in (64, 128):
                overrides = {"console_memory": target}
                plan = modpack_sources.build_plan({"preset": preset, "overrides": overrides}, "src", "dst")
                with self.subTest(preset=preset, target=target):
                    self.assertIsNone(plan.sim_qb_injuries)
                    self.assertNotIn("sim_qb_injuries", plan.to_recipe())
                    self.assertNotIn("sim_qb_injury_rate", plan.to_recipe())
        self.assertIsNone(saved.to_plan({}, "src", "dst").sim_qb_injuries)

    def test_preset_defaults_by_edition_and_explicit_choices(self):
        for preset in mod_build.PRESETS:
            for memory_target in (64, 128):
                initial = mod_build.BuildPlan("src", "dst", console_memory=memory_target)
                plan = mod_build.apply_preset(initial, preset)
                with self.subTest(preset=preset, memory=memory_target):
                    enabled = preset == "softdrink_experimental" and memory_target == 128
                    self.assertEqual(plan.sim_qb_injuries, "realistic" if enabled else None)
                    self.assertEqual(plan.k128_memory, enabled)
                    if enabled:
                        self.assertTrue(plan.sim_realism)
        for mode in ("retail", "custom"):
            overrides = {"console_memory": 128, "sim_qb_injuries": mode, "sim_qb_injury_rate": 0}
            plan = modpack_sources.build_plan({"preset": "softdrink_experimental", "overrides": overrides})
            self.assertEqual((plan.sim_qb_injuries, plan.sim_qb_injury_rate), (mode, 0))

    def test_real_standard_source_documents_freeze_the_same_128_mb_default(self):
        directory = os.environ.get("NFL2K5_B81_STANDARD_SOURCES")
        if not directory:
            self.skipTest("private SOFTDRINK standard source documents are absent")
        for name in ("SOFTDRINK-build-recipe.json", "recipe.json", "assets/documents/frozen-recipe.json"):
            with self.subTest(document=name):
                recipe = json.loads((Path(directory)/name).read_text(encoding="utf-8"))
                self.assertEqual(recipe["overrides"]["sim_qb_injuries"], "realistic")
                plan = modpack_sources.build_plan(recipe)
                self.assertEqual((plan.console_memory, plan.k128_memory, plan.sim_realism, plan.sim_qb_injuries),
                                 (128, True, True, "realistic"))

    def test_standard_setting_upgrades_the_released_and_reviewed_simulators(self):
        from mod_editor.core import nfl2k5_sim_realism as simulator, nfl2k5_sim_qb_injuries as medical
        from mod_editor.core import nfl2k5_xbe_space as space

        cases = (("NFL2K5_V09_XISO", "d78088f9ba47c6197e99ea540d0bc3d2c9255f7cd49152a77946be70dacab866", "legacy"),
                 ("NFL2K5_B81_REVIEWED_TEST_DISC", "98dd732945fb665a8d7fe771650d61c1098015cda4917ac83037059db477008e", "applied"))
        if any(not os.environ.get(variable) for variable, _, _ in cases):
            self.skipTest("private released and reviewed standard disc images are absent")
        for variable, digest, source_state in cases:
            source = Path(os.environ[variable])
            with self.subTest(source=variable):
                before = mod_build._xbe_bytes(source)
                self.assertEqual(hashlib.sha256(before).hexdigest(), digest)
                self.assertEqual(simulator.status(before), source_state)
                mod_build._sim_realism_preflight(source, lambda *_: None)
                modern, _ = simulator.apply(before)
                mode = mod_build.apply_preset(mod_build.BuildPlan(str(source), "copy.iso"),
                                              "softdrink_experimental").sim_qb_injuries
                current, _ = medical.apply(modern, mode)
                self.assertEqual(medical.read_settings(current)["mode"], "realistic")
                self.assertEqual(medical.apply(current, mode)[0], current)
                prior_rows = space.layout(modern)["allocations"]
                surviving = [row for row in space.layout(current)["allocations"] if row["owner"] != medical.OWNER]
                self.assertEqual(surviving, prior_rows)
                with tempfile.TemporaryDirectory() as directory:
                    target = Path(directory) / "private-copy.iso"
                    plan = mod_build.sim_qb_disc_edit(str(source), str(target), mode)
                    receipt = mod_build.preflight_plan(plan)
                    self.assertEqual(receipt["sim_qb_source_update"], {
                        "source_sha256": digest, "result_sha256": hashlib.sha256(current).hexdigest(),
                        "source_simulator": source_state, "simulator_upgraded": source_state == "legacy",
                        "settings": medical.read_settings(current),
                    })
                    self.assertFalse(target.exists())

    def test_pack_freezes_the_disc_setting_and_rejects_a_conflicting_recipe(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            project = root / "league.json"
            project.write_text('{"edits":[]}', encoding="utf-8")
            recipe = root / "frozen.json"
            source = {"preset": "softdrink_basic", "overrides": {},
                      "inputs": {"teams_2026": {"project": str(project)}}}
            recipe.write_text(json.dumps(source), encoding="utf-8")
            state = {"status": "applied", "mode": "custom", "custom_rate": 0.0}
            from mod_editor.core import nfl2k5_backfield_cards as cards
            with patch.object(mod_build, "_xbe_bytes", return_value=b"private standard executable"), \
                    patch.object(cards, "status", return_value="retail"), patch.object(mod_build, "_core_module") as core:
                core.return_value.read_settings.return_value = state
                portable, assets = modpack_sources.prepare(recipe, root / "work", patched_image=root / "copy.iso")
                bundle = root / "sources.2k5sources"
                info = modpack_sources.write_bundle(bundle, portable, assets)
                extracted = root / "unpacked"
                document = modpack_sources.extract_bundle(bundle, extracted, info)
                editable = modpack_sources.materialize(document, extracted)
                plan = modpack_sources.build_plan(editable)
                self.assertEqual((plan.sim_qb_injuries, plan.sim_qb_injury_rate), ("custom", 0.0))
                self.assertTrue(plan.sim_realism and plan.k128_memory)
                source["overrides"] = {"sim_qb_injuries": "realistic"}
                recipe.write_text(json.dumps(source), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "different simulated quarterback"):
                    modpack_sources.prepare(recipe, root / "mismatch", patched_image=root / "copy.iso")

    def test_permitted_units_and_round_trip_across_project_and_pack(self):
        for rate in (0, .001, .309, .310, .311, 99.999, 100):
            settings = dict(sim_qb_injuries="custom", sim_qb_injury_rate=rate, sim_realism=True, k128_memory=True)
            with self.subTest(rate=rate):
                project = saved.to_plan(settings, "src", "dst")
                self.assertEqual(saved.from_plan(project)["sim_qb_injury_rate"], rate)
                rebuilt = modpack_sources.build_plan({"preset": "softdrink_basic", "overrides": project.to_recipe()})
                self.assertEqual(rebuilt.to_recipe(), project.to_recipe())
                self.assertEqual(mod_build.validate_plan(rebuilt), [])
        for bad in (True, "3", float("nan"), float("inf"), -.001, 100.001, .3101):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                saved.build_settings({"sim_qb_injuries": "custom", "sim_qb_injury_rate": bad})
        for mode in ("retail", "realistic"):
            result = saved.to_plan(dict(sim_qb_injuries=mode, sim_qb_injury_rate="stale"), "src", "dst")
            self.assertNotIn("sim_qb_injury_rate", result.to_recipe())

    def test_dependencies_and_recommended_compact_profile(self):
        plan = mod_build.BuildPlan("src", "dst", sim_qb_injuries="custom", sim_qb_injury_rate=0.0)
        self.assertTrue(mod_build.validate_plan(plan))
        plan.k128_memory = plan.sim_realism = True
        self.assertEqual(mod_build.validate_plan(plan), [])
        self.assertTrue(mod_build._r62_plan_options(plan)["sim_qb_standard"])
        self.assertTrue(mod_build.tt.k128_requires_128(sim_qb_standard=True))
        self.assertIn("sim_qb_injuries", memory.forced_off(plan, 64))
        self.assertIsNone(memory.recommended_64_profile(plan)["sim_qb_injuries"])
        plan.console_memory = 64
        self.assertIn("128 MB", mod_build.validate_plan(plan)[0])
        plan.sim_qb_injuries = "retail"
        self.assertFalse(mod_build._r62_plan_options(plan)["sim_qb_standard"])

    def test_cli_uses_recipe_or_explicit_overrides_without_changing_input(self):
        with tempfile.TemporaryDirectory() as t:
            recipe = Path(t) / "author.json"
            original = json.dumps({"schema": "softdrink_sources/v1", "preset": "softdrink_basic",
                                   "overrides": {}, "project": "league.json"})
            recipe.write_text(original, encoding="utf-8")
            base = ["build-sources", "--recipe", str(recipe), "--source", "base.iso", "--out", "copy.iso"]
            with patch.object(modpack_sources, "build_project", return_value={"ok": True}) as build:
                for args, expected, rate in (([], None, .310), (["--sim-qb-injuries", "retail"], "retail", .310),
                        (["--sim-qb-injuries", "custom", "--qb-injury-rate", "0.000"], "custom", 0.0)):
                    with self.subTest(args=args), contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(cli.main(base + args), 0)
                        plan = build.call_args.args[0]
                        self.assertEqual((plan.sim_qb_injuries, plan.sim_qb_injury_rate), (expected, rate))
                        if expected == "custom":
                            self.assertTrue(plan.k128_memory and plan.sim_realism)
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(cli.main(base + ["--qb-injury-rate", "1"]), 2)
                self.assertEqual(build.call_count, 3)
            self.assertEqual(recipe.read_text(encoding="utf-8"), original)

    def test_exact_reservation_is_preserved_for_an_installed_disc(self):
        from mod_editor.core import nfl2k5_xbe_space as space
        from mod_editor.core import nfl2k5_throw_tuning as tuning
        request = space.QB_INJURY_REQUEST
        keys = ("owner", "kind", "size", "align")
        rows = []
        for index, value in enumerate(("other_owner", "read_only", request[2] // 2, request[3] // 2)):
            other = list(request)
            other[index] = value
            rows.append(dict(zip(keys, other)))
        with patch.object(space, "is_scaleout", return_value=True), \
                patch.object(space, "layout", return_value={"allocations": rows}):
            self.assertFalse(tuning._has_qb_reservation(b"image"))
            rows.append(dict(zip(keys, request)))
            self.assertTrue(tuning._has_qb_reservation(b"image"))
        with patch.object(space, "is_scaleout", return_value=False), patch.object(space, "layout") as layout:
            self.assertFalse(tuning._has_qb_reservation(b"original"))
            layout.assert_not_called()

    def test_single_setting_is_explicit_and_refuses_foreign_code_before_copying(self):
        from unittest.mock import Mock
        solo = mod_build.sim_qb_disc_edit("source.iso", "out.iso", "custom", custom_rate=0)
        self.assertTrue(mod_build._only_sim_qb_changes(solo))
        recipe = {"preset": "softdrink_basic", "overrides": {**solo.to_recipe(), "helmet_finish": "glossy"}}
        self.assertFalse(mod_build._only_sim_qb_changes(modpack_sources.build_plan(recipe)))
        solo.backfield_cards = True
        self.assertFalse(mod_build._only_sim_qb_changes(solo))
        solo.backfield_cards = False
        base, qb = Mock(), Mock()
        base.status.return_value = "applied"
        qb.apply.side_effect = ValueError("unrecognized quarterback helper")
        with patch.object(mod_build.tt.k128_patch, "read_settings",
                          return_value={"status": "applied", "require_128": True, "early": True, "roster_heap": True}), \
                patch.object(mod_build, "_core_module", side_effect=[base, qb]), \
                patch.object(mod_build, "_copy_private_build_source") as copy:
            with self.assertRaisesRegex(ValueError, "unrecognized"):
                mod_build._edit_installed_sim_qb(solo, solo.source, solo.target, b"foreign", {}, lambda *_: None,
                                                 preflight=False, consume=False, reference=solo.source)
            copy.assert_not_called()

    def test_standalone_cli_requests_only_the_named_option(self):
        args = ["edit-sim-qb", "--source", "built.iso", "--out", "copy.iso", "--mode", "custom",
                "--qb-injury-rate", "0.000"]
        with patch.object(mod_build, "build", return_value={"ok": True}) as build:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(args), 0)
            plan = build.call_args.args[0]
            self.assertTrue(mod_build._only_sim_qb_changes(plan))
            self.assertEqual((plan.sim_qb_injuries, plan.sim_qb_injury_rate), ("custom", 0))
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main([*args[:6], "retail", *args[7:]]), 2)
            self.assertEqual(build.call_count, 1)


class StudioControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.panel = BuildPanel(available={})
        self.addCleanup(self.panel.deleteLater)
        self.source = Path(self.temp.name) / "game.iso"
        self.source.write_bytes(bytes(4096))
        self.retail_state = {key: "retail" for key in self.panel._boxes()}
        self.retail_state.update(path=str(self.source), container="xiso", throw=None, sim_qb_injuries="retail",
                                 sim_qb_injury_settings={"status": "retail", "mode": "retail", "custom_rate": .310})
        self.panel.apply_state(dict(self.retail_state))

    def test_experimental_button_enables_realistic_on_a_fresh_or_upgradeable_standard_disc(self):
        for state_name in ("retail", "legacy"):
            with self.subTest(simulator=state_name):
                self.panel.apply_state(dict(self.retail_state, sim_realism=state_name))
                self.panel.apply_preset("softdrink_experimental")
                plan = self.panel._plan_for_build()
                self.assertEqual((plan.sim_qb_injuries, plan.sim_realism, plan.k128_memory),
                                 ("realistic", True, True))
        self.panel.apply_preset("softdrink_basic")
        self.assertIsNone(self.panel._plan_for_build().sim_qb_injuries)
        self.panel.set_console_memory(64)
        self.panel.apply_preset("softdrink_experimental")
        compact = self.panel._plan_for_build()
        self.assertEqual((compact.console_memory, compact.sim_qb_injuries, compact.k128_memory), (64, None, False))

    def test_modes_tell_the_user_the_scope_and_dependencies(self):
        panel = self.panel
        mode = panel.qb_injury_mode
        self.assertIn("original 2K5 simulation", mode.itemText(mode.findData("retail")))
        self.assertIn("realistic passing, your injury rate", mode.itemText(mode.findData("custom")))
        panel.qb_injury_mode.setCurrentIndex(panel.qb_injury_mode.findData("custom"))
        panel.qb_injury_rate.setValue(.411)
        plan = panel._plan_for_build()
        self.assertTrue(plan.sim_realism and plan.k128_memory)
        self.assertEqual((plan.sim_qb_injuries, plan.sim_qb_injury_rate), ("custom", .411))
        self.assertTrue(panel.has_work())
        self.assertIn("Simulated injuries (Custom, 0.411%)", panel.selected_labels())
        self.assertIn("your own club is treated like every other club", panel.qb_injury_help.text())
        self.assertIn("every position except kickers and punters", panel.qb_injury_help.text())
        self.assertIn("cornerbacks and safeties", panel.qb_injury_help.text())
        self.assertIn("Injuries in games you play are not changed", panel.qb_injury_help.text())  # b81 qb34 review item 4
        self.assertFalse(panel.qb_injury_rate.isHidden())
        panel.sim_realism_check.click()
        self.assertIsNone(panel.plan().sim_qb_injuries)
        self.assertTrue(panel.qb_injury_rate.isHidden())

    def test_share_project_restore_and_compact_switch(self):
        panel = self.panel
        recipe = {"preset": "softdrink_basic", "project": str(self.source.with_suffix(".json")),
                  "overrides": {"sim_qb_injuries": "custom", "sim_qb_injury_rate": 0.0,
                                "sim_realism": True, "k128_memory": True}}
        panel.load_softdrink_sources(recipe)
        self.assertEqual((panel.plan().sim_qb_injuries, panel.plan().sim_qb_injury_rate), ("custom", 0.0))
        stored = panel.project_build_settings()
        panel.set_console_memory(64)
        self.assertIsNone(panel.plan().sim_qb_injuries)
        self.assertFalse(panel.qb_injury_mode.isEnabled())
        panel.set_console_memory(128)
        panel.restore_project_build_settings(stored)
        self.assertEqual((panel.plan().sim_qb_injuries, panel.plan().sim_qb_injury_rate), ("custom", 0.0))
        panel.load_softdrink_sources({**recipe, "overrides": {}})
        self.assertIsNone(panel.plan().sim_qb_injuries)

    def test_can_restore_an_installed_mode_and_leave_foreign_data_unselected(self):
        panel = self.panel
        panel.apply_state({**self.retail_state, "sim_qb_injuries": "applied",
                           "sim_qb_injury_settings": {"status": "applied", "mode": "custom", "custom_rate": .700}})
        self.assertIn("Custom", panel.qb_injury_mode.itemText(0))
        self.assertEqual(panel.qb_injury_rate.value(), .700)
        self.assertIsNone(panel.plan().sim_qb_injuries)
        panel.qb_injury_mode.setCurrentIndex(panel.qb_injury_mode.findData("retail"))
        self.assertEqual(panel.plan().sim_qb_injuries, "retail")
        self.assertTrue(panel.has_work())
        self.assertIn("Simulated injuries (Retail)", panel.selected_labels())
        # A slice 1 or slice 2 install (revision 1 or 2) at the same mode is still a change: Build upgrades it in place.
        for revision, labelled in ((1, True), (2, True), (3, False)):
            with self.subTest(installed_revision=revision):
                panel.apply_state({**self.retail_state, "sim_qb_injuries": "applied", "sim_qb_injury_settings": {
                    "status": "applied", "mode": "realistic", "custom_rate": .310, "revision": revision}})
                panel.qb_injury_mode.setCurrentIndex(panel.qb_injury_mode.findData("realistic"))
                self.assertEqual("Simulated injuries (Realistic)" in panel.selected_labels(), labelled)
        panel.apply_state({**self.retail_state, "sim_qb_injuries": "foreign", "sim_qb_injury_settings": {"status": "foreign"}})
        self.assertFalse(panel.qb_injury_mode.isEnabled())
        self.assertIsNone(panel.plan().sim_qb_injuries)

    def test_a_pending_scan_keeps_the_choice_only_on_the_same_disc(self):
        panel = self.panel
        panel.qb_injury_mode.setCurrentIndex(panel.qb_injury_mode.findData("custom"))
        panel.qb_injury_rate.setValue(.513)
        panel._reading = True
        panel.apply_state(dict(self.retail_state))
        restored = panel.plan()
        self.assertEqual((restored.sim_qb_injuries, restored.sim_qb_injury_rate), ("custom", .513))
        self.assertTrue(restored.sim_realism and restored.k128_memory)
        second = self.source.with_name("another.iso")
        second.write_bytes(bytes(4096))
        panel.apply_state({**self.retail_state, "path": str(second)})
        self.assertIsNone(panel.plan().sim_qb_injuries)
        self.assertEqual(panel.qb_injury_rate.value(), .310)
        for state in ({"sim_realism": "foreign"}, {"sim_realism": "previous"}, {"k128_memory": "foreign"},
                      {"k128_memory": "applied", "k128_settings": {"require_128": False}},
                      {"container": "xbe"}, {"sim_qb_injuries": "unavailable"}):
            with self.subTest(state=state):
                panel.apply_state({**self.retail_state, **state})
                self.assertFalse(panel.qb_injury_mode.isEnabled())
                self.assertTrue(panel.qb_injury_help.text())

    def test_a_second_explicit_default_or_authored_project_keeps_the_full_build(self):
        standard = self.source.with_name("standard.iso")
        standard.write_bytes(bytes(4096))
        state = {**self.retail_state, "path": str(standard), "sim_realism": "applied",
                 "k128_memory": "applied", "k128_settings": {"require_128": True, "early": True, "roster_heap": True}}
        self.panel.apply_state(state)
        mode = self.panel.qb_injury_mode
        mode.setCurrentIndex(mode.findData("realistic"))
        self.assertTrue(mod_build._only_sim_qb_changes(self.panel._plan_for_build()))
        self.panel.apply_state({**state, "sim_realism": "legacy"})
        mode.setCurrentIndex(mode.findData("realistic"))
        self.assertTrue(mod_build._only_sim_qb_changes(self.panel._plan_for_build()))
        # Looking at another number and leaving it unchanged is not a second edit.
        self.panel.ceiling_spin.editingFinished.emit()
        self.assertTrue(mod_build._only_sim_qb_changes(self.panel._plan_for_build()))
        finish = self.panel.helmet_finish_combo
        self.assertEqual(finish.currentData(), mod_build.BuildPlan.helmet_finish)
        finish.activated.emit(finish.currentIndex())
        self.assertFalse(mod_build._only_sim_qb_changes(self.panel._plan_for_build()))
        self.panel.restore_project_build_settings({"sim_qb_injuries": "realistic", "k128_memory": True,
                                                  "sim_realism": True, "helmet_finish": "glossy"})
        self.assertFalse(mod_build._only_sim_qb_changes(self.panel._plan_for_build()))


if __name__ == "__main__":
    unittest.main()

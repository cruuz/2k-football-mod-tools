"""Beta 66 (maumau78 / xevan): the Helmet finish choice through BuildPlan, presets, both panels, project settings and a build."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mod_editor.core import mod_build, nfl2k5_build_settings as saved

RETAIL_XBE = ROOT / "extracted" / "ESPN NFL 2K5 (USA)" / "default.xbe"


class PlanTests(unittest.TestCase):
    def test_default_presets_and_availability(self):
        self.assertEqual(mod_build.BuildPlan("in.iso", "out.iso").helmet_finish, "glossy")
        for name in mod_build.PRESETS:
            self.assertEqual(mod_build.PRESETS[name]["helmet_finish"], "glossy", name)
            self.assertEqual(mod_build.apply_preset(mod_build.BuildPlan("in.iso", "out.iso"), name).helmet_finish, "glossy")
        self.assertTrue(mod_build.availability()["helmet_finish"])
        self.assertTrue(mod_build.BuildPlan("in.iso", "out.iso", helmet_finish="matte").wants_xbe_patch())
        self.assertFalse(mod_build.BuildPlan("in.iso", "out.iso").wants_xbe_patch())

    def test_invalid_value_refuses_before_any_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "default.xbe"
            source.write_bytes(b"XBEH" + bytes(64))
            target = Path(folder) / "out.xbe"
            with self.assertRaisesRegex(ValueError, "glossy or matte"):
                mod_build.build(mod_build.BuildPlan(str(source), str(target), helmet_finish="shiny"))
            self.assertFalse(target.exists())

    def test_project_settings_persist_the_choice_and_refuse_garbage(self):
        plan = mod_build.BuildPlan("in.iso", "out.iso", helmet_finish="matte")
        stored = saved.from_plan(plan)
        self.assertEqual(stored["helmet_finish"], "matte")
        self.assertEqual(saved.to_plan(saved.build_settings(stored), "a", "b").helmet_finish, "matte")
        with self.assertRaisesRegex(Exception, "glossy or matte"):
            saved.build_settings({**stored, "helmet_finish": "chrome"})


@unittest.skipUnless(RETAIL_XBE.is_file(), "retail USA default.xbe evidence absent")
class RetailBuildTests(unittest.TestCase):
    def test_matte_then_glossy_round_trip_on_the_executable(self):
        from mod_editor.core import nfl2k5_helmet_finish as finish
        retail = RETAIL_XBE.read_bytes()
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "default.xbe"
            source.write_bytes(retail)
            matte = Path(folder) / "matte.xbe"
            receipt = mod_build.build(mod_build.BuildPlan(str(source), str(matte), helmet_finish="matte"))
            self.assertIn("helmet_finish", [step["step"] for step in receipt["steps"]])
            self.assertEqual(finish.status(matte.read_bytes()), "applied")
            self.assertEqual(mod_build.inspect(matte)["helmet_finish"], "applied")
            self.assertEqual(mod_build.inspect(source)["helmet_finish"], "retail")
            glossy = Path(folder) / "glossy.xbe"
            receipt = mod_build.build(mod_build.BuildPlan(str(matte), str(glossy), helmet_finish="glossy"))
            self.assertIn("helmet_finish", [step["step"] for step in receipt["steps"]])
            self.assertEqual(glossy.read_bytes(), retail)
            self.assertEqual(source.read_bytes(), retail)


try:
    from PyQt5.QtWidgets import QApplication
except ImportError:  # pragma: no cover
    QApplication = None


@unittest.skipUnless(QApplication is not None, "PyQt5 is absent")
class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _panels(self):
        from mod_editor.gui.build_panel_qt import BuildPanel
        from mod_editor.gui.gameplay_patches_panel_qt import GameplayPatchesPanel
        build, game = BuildPanel(), GameplayPatchesPanel()
        self.addCleanup(build.deleteLater)
        self.addCleanup(game.deleteLater)
        return build, game

    def test_controls_default_to_glossy_and_follow_each_other(self):
        from mod_editor.gui.gameplay_project_ui import GameplayBuildLink
        build, game = self._panels()
        state = {"container": "xiso", "path": "synthetic.iso", "helmet_finish": "retail"}
        for p in (build, game):
            p._state = state
            p.source_field.setText("synthetic.iso")
            p.target_field.setText("out.iso")
        build._available = dict(mod_build.availability())
        build.apply_state({**state, **{k: "retail" for k in ("read_option_runtime", "qb_spy", "playbook_pair")}})
        game.apply_state({**state, **{k: "retail" for k in ("read_option_runtime", "qb_spy", "playbook_pair")}})
        for p in (build, game):
            self.assertTrue(p.helmet_finish_combo.isEnabled(), type(p).__name__)
            self.assertEqual(p.helmet_finish_combo.currentData(), "glossy")
            self.assertEqual(p.plan().helmet_finish, "glossy")
        self.assertFalse(build._helmet_finish_changed())
        link = GameplayBuildLink(build, game, lambda: None)
        build.helmet_finish_combo.setCurrentIndex(1)
        self.assertTrue(build.helmet_finish_check.isChecked())
        self.assertEqual(build.plan().helmet_finish, "matte")
        self.assertTrue(game.checks["helmet_finish"].isChecked())
        self.assertEqual(game.helmet_finish_combo.currentData(), "matte")
        self.assertEqual(game.plan().helmet_finish, "matte")
        self.assertTrue(build._helmet_finish_changed())
        self.assertTrue(build.has_work())
        self.assertIn("Matte helmet finish", " ".join(build._selected_labels()) if hasattr(build, "_selected_labels") else "Matte helmet finish")
        game.checks["helmet_finish"].setChecked(False)
        self.assertEqual(build.plan().helmet_finish, "glossy")
        del link

    def test_a_matte_source_offers_glossy_restoration(self):
        build, game = self._panels()
        state = {"container": "xiso", "path": "matte.iso", "helmet_finish": "applied"}
        build._available = dict(mod_build.availability())
        build.apply_state({**state, **{k: "retail" for k in ("read_option_runtime", "qb_spy", "playbook_pair")}})
        game.apply_state({**state, **{k: "retail" for k in ("read_option_runtime", "qb_spy", "playbook_pair")}})
        for p in (build, game):
            self.assertEqual(p.helmet_finish_combo.currentData(), "matte")
            self.assertEqual(p.plan().helmet_finish, "matte")
            self.assertFalse(p._helmet_finish_changed())
        build.helmet_finish_combo.setCurrentIndex(0)
        self.assertEqual(build.plan().helmet_finish, "glossy")
        self.assertTrue(build._helmet_finish_changed())
        self.assertTrue(build.has_work())

    def test_presets_leave_the_finish_glossy(self):
        build, _game = self._panels()
        build._available = dict(mod_build.availability())
        build.apply_state({"container": "xiso", "path": "synthetic.iso", "helmet_finish": "retail",
                           **{k: "retail" for k in ("read_option_runtime", "qb_spy", "playbook_pair")}})
        build.helmet_finish_combo.setCurrentIndex(1)
        for name in mod_build.PRESETS:
            build.apply_preset(name)
            self.assertEqual(build.helmet_finish_combo.currentData(), "glossy", name)
            self.assertFalse(build.helmet_finish_check.isChecked(), name)


@unittest.skipUnless(QApplication is not None, "PyQt5 is absent")
class StudioMirrorTests(unittest.TestCase):
    """The Uniforms & Equipment tab's Helmet finish combo is the Build tab's choice (D2 wiring)."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_uniforms_and_build_combos_follow_each_other(self):
        from mod_editor.gui.studio_qt import BrowseOnlyFacade, StudioMainWindow
        window = StudioMainWindow(eager_pages=True, facade=BrowseOnlyFacade(), offer_recovery=False)
        self.addCleanup(window.deleteLater)
        self.app.processEvents()
        uniforms, build = window._uniform_helmet_finish, window._build_panel.helmet_finish_combo
        self.assertEqual((uniforms.currentData(), build.currentData()), ("glossy", "glossy"))
        uniforms.setCurrentIndex(1)
        self.assertEqual(build.currentData(), "matte")
        self.assertTrue(window._build_panel.helmet_finish_check.isChecked())
        build.setCurrentIndex(0)
        self.assertEqual(uniforms.currentData(), "glossy")
        self.assertFalse(window._build_panel.helmet_finish_check.isChecked())
        # a signal-quiet restore is mirrored explicitly
        build.blockSignals(True)
        build.setCurrentIndex(1)
        build.blockSignals(False)
        window._sync_uniform_helmet_finish()
        self.assertEqual(uniforms.currentData(), "matte")
        self.assertEqual(uniforms.isEnabled(), build.isEnabled())


if __name__ == "__main__":
    unittest.main()

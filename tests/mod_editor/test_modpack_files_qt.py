"""Offscreen installation, cancellation, 64-bit progress and source customization."""
import os
import json
from pathlib import Path
import sys
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).parent)]
from PyQt5.QtWidgets import QApplication, QFileDialog
from mod_editor.gui.share_panel_qt import SharePanel
import test_modpack_files as fixtures


class FilePackQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.fixture = fixtures.FilePackTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.panel = SharePanel()
        self.panel._notify = lambda *args: None
        self.panel._confirm = lambda *args: True
        self.addCleanup(self.panel.deleteLater)

    def wait(self):
        deadline = time.monotonic() + 30
        while self.panel.busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.app.processEvents()
        self.assertFalse(self.panel.busy)

    def test_one_click_dialog_route_installs_without_separate_check(self):
        out = self.fixture.root / "SOFTDRINK.iso"
        with mock.patch.object(QFileDialog, "getOpenFileName", side_effect=[(str(self.fixture.base), ""), (str(self.fixture.pack), "")]), \
             mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(out), "")):
            self.panel.install_softdrink_button.click()
        self.wait()
        self.assertTrue(self.panel.last_apply["target"]["all_game_files_verified"])
        self.assertEqual(out.read_bytes(), self.fixture.built.read_bytes())
        self.assertTrue(self.panel.install_softdrink_button.isEnabled())

    def test_install_and_build_guards_without_resolve(self):
        from mod_editor.gui.build_panel_qt import _resolved_build_file, BuildPanel
        from mod_editor.core import modpack_files as f
        panel = BuildPanel(available={})
        self.addCleanup(panel.deleteLater)
        out = self.fixture.root / "résultat.iso"
        self.panel.load_pack(self.fixture.pack)
        self.panel.source_field.setText(str(self.fixture.base))
        self.panel.target_field.setText(str(out))
        with mock.patch.object(Path, "resolve", side_effect=OSError(234, "More data available")):
            self.assertEqual(_resolved_build_file(self.fixture.base, "Source"), self.fixture.base)
            self.panel.start_file_install()
            self.wait()
            self.assertTrue(self.panel.last_apply["target"]["all_game_files_verified"])
            alias = self.fixture.root / "hardlink.iso"
            os.link(self.fixture.base, alias)
            self.panel.target_field.setText(str(alias))
            with mock.patch.object(self.panel, "_start") as start:
                self.panel.start_file_install()
                start.assert_not_called()
            self.assertIn("different file", self.panel.apply_status.text())
            panel.source_field.setText(str(self.fixture.base))
            panel._state = {"path": str(self.fixture.base), "container": "xiso"}
            panel.target_field.setText(str(alias))
            self.assertIn("same file", panel.blocker())
        self.assertEqual(f._path(out).read_bytes(), self.fixture.built.read_bytes())

    def test_negative_worker_message_and_progress_beyond_four_gib(self):
        self.panel._on_progress("Installing", 5 * 1024**3, 6 * 1024**3)
        self.assertEqual(self.panel.progress_bar.value(), 83)
        self.assertIn("time left", self.panel.progress_label.text())
        self.panel.load_pack(self.fixture.pack)
        self.panel.source_field.setText(str(self.fixture.built))
        self.panel.target_field.setText(str(self.fixture.root / "bad.iso"))
        self.panel.start_file_install()
        self.wait()
        for label in ("Detected:", "Incompatible:", "Next:"):
            self.assertIn(label, self.panel.apply_status.text())
        self.assertFalse((self.fixture.root / "bad.iso").exists())

    def test_worker_signal_retains_large_python_ints(self):
        received = []
        original = self.panel._on_progress
        def record(stage, done, total):
            received.append((done, total))
            original(stage, done, total)
        self.panel._on_progress = record
        self.panel._start(lambda progress: progress("Large", 5_000_000_000, 6_000_000_000), lambda _: None, self.fail)
        self.wait()
        self.assertEqual(received, [(5_000_000_000, 6_000_000_000)])

    def test_custom_sources_populate_build_choices_and_project(self):
        from mod_editor.gui.build_panel_qt import BuildPanel
        from mod_editor.core import modpack_sources
        panel = BuildPanel(available={})
        try:
            recipe = dict(preset="softdrink_experimental", overrides=dict(coin_defer=True),
                          project=str(self.fixture.root / "league.json"))
            panel.load_softdrink_sources(recipe)
            self.assertTrue(panel.softdrink_project_check.isChecked())
            self.assertEqual(panel.softdrink_project_field.text(), recipe["project"])
            self.assertTrue(panel.plan().coin_defer)
            state = {key: "retail" for key in panel._boxes()}
            state.update(path="retail.iso", container="xiso", throw=None)
            panel.apply_state(state)
            self.assertTrue(panel.plan().coin_defer)
            self.assertEqual(panel.softdrink_project_field.text(), recipe["project"])
            panel.coin_defer_check.setChecked(False)
            self.assertFalse(panel.plan().coin_defer)
            panel.softdrink_project_check.setChecked(False)
            self.assertFalse(panel.softdrink_project_check.isChecked())
            plan = modpack_sources.build_plan(recipe)
            with mock.patch.object(modpack_sources, "build_project", return_value={"target": "stub.iso"}) as build, \
                 mock.patch("mod_editor.core.studio_inspection.inspect_source", return_value={}):
                def progress(*args): pass
                panel._build_operation(plan, progress, softdrink_project=recipe["project"])
            build.assert_called_once_with(plan, recipe["project"], progress)
        finally:
            panel.deleteLater()

    def test_cancel_removes_incomplete_output(self):
        output = self.fixture.root / "cancel.iso"
        self.panel.load_pack(self.fixture.pack)
        self.panel.source_field.setText(str(self.fixture.base))
        self.panel.target_field.setText(str(output))
        self.panel.start_file_install()
        self.panel.cancel_button.click()
        self.wait()
        self.assertIsNone(self.panel.last_apply)
        self.assertFalse(output.exists())

    def test_source_inspection_preserves_gated_artwork_choices(self):
        from mod_editor.gui.build_panel_qt import BuildPanel, VENUE_BUILD_KEYS
        panel = BuildPanel(available={key: True for key in (*VENUE_BUILD_KEYS, "modern_metlife", "modern_venues_2026", "custom_intro")})
        self.addCleanup(panel.deleteLater)
        recipe = dict(preset="softdrink_experimental", project="league.json",
                      overrides=dict(modern_metlife=True, modern_venues_2026=str(self.fixture.root), custom_intro="intro.wmv",
                                     **{key: True for key in VENUE_BUILD_KEYS}))
        panel.load_softdrink_sources(recipe)
        self.assertTrue(panel.modern_metlife_check.isChecked())
        self.assertTrue(panel.modern_venues_check.isChecked())
        self.assertTrue(panel.custom_intro_check.isChecked())
        # Users can also omit a part before opening their disc.
        panel.custom_intro_check.setChecked(False)
        state = {key: "retail" for key in panel._boxes()}
        state.update(path=str(self.fixture.base), container="xiso", throw=None)
        panel.apply_state(state)
        self.assertTrue(panel.plan().modern_metlife)
        self.assertEqual(panel.plan().modern_venues_2026, str(self.fixture.root))
        self.assertEqual(panel.plan().custom_intro, "")
        self.assertTrue(all(getattr(panel.plan(), key) for key in VENUE_BUILD_KEYS))
        panel.modern_sofi_check.setChecked(False)
        self.assertFalse(panel.plan().modern_sofi)

    def test_artwork_selection_keeps_original_and_writes_selected_edits(self):
        from mod_editor.gui.modpack_sources_qt import SourceSelection
        from PyQt5.QtCore import Qt
        source = self.fixture.root / "art.json"
        document = dict(schema="nfl2k5_visual_mod_project/v1", edits=[dict(kind="torso", asset_code="00"), dict(kind="torso", asset_code="01")])
        source.write_text(json.dumps(document))
        dialog = SourceSelection(source)
        self.addCleanup(dialog.deleteLater)
        dialog.items[0].setCheckState(0, Qt.Unchecked)
        output = self.fixture.root / "selected.json"
        self.assertEqual(dialog.save(output), 1)
        self.assertEqual(json.loads(output.read_text())["edits"], document["edits"][1:])
        self.assertEqual(json.loads(source.read_text()), document)


if __name__ == "__main__":
    unittest.main()

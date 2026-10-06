"""The three-prompt install ends with a launch of the verified image, offscreen."""
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).parent)]
from PyQt5.QtWidgets import QApplication, QFileDialog
from mod_editor.gui.share_panel_qt import SharePanel
from mod_editor.gui.studio_qt import StudioMainWindow
from mod_editor.gui.build_panel_qt import BuildPanel
from mod_editor.gui.ux_text import disc_next_steps
from mod_editor.studio.facade import Nfl2k5StudioFacade
from mod_editor.studio import xemu_settings
import test_modpack_files as fixtures


class SetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_install_file_picker_and_latest_launch_use_new_output(self):
        fixture = fixtures.FilePackTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        launcher = Mock()
        facade = Nfl2k5StudioFacade(uniform_catalog=object(), xemu_command=("xemu",), process_launcher=launcher)
        facade.register_external_build(fixture.base)
        panel = SharePanel(facade)
        self.addCleanup(panel.deleteLater)
        notices = []
        panel._notify = lambda *args: notices.append(args)
        host = SimpleNamespace(facade=facade, _refresh_action_states=Mock(), _set_status=Mock())
        panel.disc_written.connect(lambda image: StudioMainWindow._register_external_disc(host, image))
        output = fixture.root / "SOFTDRINK 2K28.xiso.iso"
        with patch.object(QFileDialog, "getOpenFileName", side_effect=[(str(fixture.base), ""), (str(fixture.pack), "")]) as picker, \
             patch.object(QFileDialog, "getSaveFileName", return_value=(str(output.with_suffix('').with_suffix('')), "")):
            panel.install_softdrink_button.click()
        # No directory picker or extraction is involved; .2k5patch is accepted directly.
        self.assertIn("*.2k5patch", picker.call_args_list[1].args[3])
        self.assertIn("2 of 3", picker.call_args_list[1].args[1])
        deadline = time.monotonic() + 30
        while panel.busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.app.processEvents()
        self.assertFalse(panel.busy)
        self.assertEqual(output.read_bytes(), fixture.built.read_bytes())
        self.assertEqual(facade.last_build_output, output)
        self.assertIn(str(output), notices[-1][2])
        self.assertIn("load the disc roster", notices[-1][2])
        self.assertIn("fresh franchise", notices[-1][2])
        with patch.object(xemu_settings, "config_path", return_value=fixture.root / "private-xemu.toml"), \
             patch("mod_editor.studio.facade._validate_xemu_executable"):
            facade.launch_xemu(lambda *_: None)
        self.assertEqual(launcher.call_args.args[0], ("xemu", "-dvd_path", str(output)))
        self.assertIn("fresh franchise", panel.apply_status.text())

    def test_build_completion_names_next_steps(self):
        panel = BuildPanel(available={})
        self.addCleanup(panel.deleteLater)
        panel._requested_build_labels = []
        panel._requested_build_summary = "Test build"
        panel.apply_state = Mock()
        panel._point_at_the_next_source = Mock()
        with patch("mod_editor.core.build_feedback.completion", return_value=("Disc ready", "Build complete")), \
             patch("mod_editor.gui.build_panel_qt.tt.is_disc_image", return_value=True), \
             patch("mod_editor.gui.build_panel_qt.QMessageBox.information") as message:
            panel._done(dict(target="new SOFTDRINK.xiso.iso", steps=[]))
        body = message.call_args.args[2]
        self.assertIn("Machine > Load Disc", body)
        self.assertIn("new SOFTDRINK.xiso.iso", body)
        self.assertIn("disc roster", body)
        self.assertIn("fresh franchise", body)

    def test_heartbeat_changes_even_without_worker_events(self):
        panel = BuildPanel(available={})
        self.addCleanup(panel.deleteLater)
        panel._task = SimpleNamespace(latest_progress="Encoding textures", started=100., last_update=101.)
        with patch("mod_editor.gui.build_panel_qt.time.monotonic", return_value=107.):
            panel._heartbeat()
        first = panel.progress_label.text()
        with patch("mod_editor.gui.build_panel_qt.time.monotonic", return_value=108.):
            panel._heartbeat()
        self.assertNotEqual(first, panel.progress_label.text())
        self.assertIn("Still working", panel.progress_label.text())
        panel._task = None

    def test_completed_image_registration_survives_cwd_changes(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            disc = folder / "new.iso"
            disc.write_bytes(b"synthetic")
            original = Path.cwd()
            facade = Nfl2k5StudioFacade(uniform_catalog=object(), xemu_command=())
            try:
                os.chdir(folder)
                facade.register_external_build(Path("new.iso"))
                os.chdir(original)
                self.assertEqual(facade.last_build_output, disc)
                self.assertTrue(facade.last_build_output.is_file())
            finally:
                os.chdir(original)


if __name__ == "__main__":
    unittest.main()

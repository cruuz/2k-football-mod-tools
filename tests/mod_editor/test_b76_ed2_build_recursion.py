"""Offscreen regression for the equipment refresh -> Build settings signal loop."""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import os
import unittest
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication
from mod_editor.gui.build_panel_qt import BuildPanel
from mod_editor.gui.gameplay_project_ui import observe_build_choices
from mod_editor.gui.studio_qt import StudioMainWindow


class BuildRecursionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.build = BuildPanel()
        self.addCleanup(self.build.deleteLater)
        self.addCleanup(self.build._hires_budget_timer.stop)
        session = SimpleNamespace(modified_count=0)
        self.setter = Mock()
        self.host = SimpleNamespace(
            facade=SimpleNamespace(source_ready=True, _session=session,
                                   set_project_build_settings=self.setter),
            _build_panel=self.build, _restoring_music_playlist=False,
            _workspace_revision=0, _workspace_dirty=False, _blocking=False,
            _embedded_operation_is_busy=lambda: False,
            _refit_project_equipment=Mock(), _save_recovery_snapshot=Mock(),
            statusBar=lambda: SimpleNamespace(showMessage=Mock()))
        for name in ("_refresh_build_includes", "_capture_music_build_settings",
                     "_mark_workspace_changed", "_gameplay_build_changed"):
            setattr(self.host, name, MethodType(getattr(StudioMainWindow, name), self.host))
        self.host._refresh_edit_state = lambda **kwargs: self.host._refresh_build_includes()
        self.addCleanup(patch.stopall)
        patch("mod_editor.core.equipment_reporting.project_fit_labels", return_value={}).start()
        self.rows = [{"fit_status": "needs refit", "set_selector": "ARI",
                      "asset_id": "equipment:" + name} for name in ("helmet", "gloves")]
        patch("mod_editor.core.equipment_staging.cached_equipment_fit_rows",
              return_value=self.rows).start()
        # Studio populates this action picker BEFORE it observes Build settings.
        self.host._refresh_build_includes()
        self.build.equipment_refit_choice.setCurrentIndex(1)
        self.errors = []
        self.stopped = False

        def exception(kind, value, tb):
            self.errors.append(value)
            self.stopped = True

        def changed(*args):
            if not self.stopped:
                try:
                    self.host._gameplay_build_changed(*args)
                except RecursionError as exc:
                    exception(type(exc), exc, exc.__traceback__)

        patch.object(sys, "excepthook", exception).start()
        observe_build_choices(self.build, changed)

    def test_refit_refresh_does_not_reenter_or_lose_authored_settings(self):
        from mod_editor.core import nfl2k5_music_playlist as playlist
        selection = playlist.default_options()
        self.build._music_shuffle_selection = selection
        self.build.notes_field.setPlainText("Keep my build notes")
        self.assertEqual(self.errors, [], repr(self.errors[:1]))
        self.assertEqual(self.setter.call_count, 1)
        self.assertEqual(self.host._workspace_revision, 1)
        self.assertEqual(self.setter.call_args.args[0]["notes"], "Keep my build notes")
        self.assertEqual(self.setter.call_args.args[0]["music_shuffle_selection"], selection)
        self.assertEqual(self.build.equipment_refit_choice.currentData(), "equipment:gloves")
        self.build.catch_check.setChecked(True)
        self.assertTrue(self.setter.call_args.args[0]["catch_slider"])
        self.assertEqual(self.setter.call_args.args[0]["notes"], "Keep my build notes")

    def test_refit_picker_is_an_action_target_not_a_saved_build_choice(self):
        self.build.equipment_refit_choice.setCurrentIndex(0)
        self.assertEqual(self.errors, [], repr(self.errors[:1]))
        self.setter.assert_not_called()

    def test_guard_releases_after_validation_failure_and_ignores_reentrant_refresh(self):
        original = self.host._capture_music_build_settings
        self.host._capture_music_build_settings = Mock(side_effect=ValueError("bad choice"))
        self.host._gameplay_build_changed()
        self.assertEqual(self.host._workspace_revision, 0)
        self.host._capture_music_build_settings = original
        self.host._refresh_edit_state = lambda **kwargs: self.host._gameplay_build_changed()
        self.host._gameplay_build_changed()
        self.assertEqual(self.host._workspace_revision, 1)
        self.assertEqual(self.setter.call_count, 1)


if __name__ == "__main__":
    unittest.main()

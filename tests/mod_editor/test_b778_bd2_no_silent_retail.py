"""b778-bd2: Make my disc must never finish with a silent retail copy.

tinpanalley (Discord, 10/23-24): opening the retail ISO, choosing Modern, ticking
options and pressing "Make My Disc" produced "the same original game"; later a
Windows build "take over an hour ... and it failed". These tests pin the two halves
of the answer: a selection made while the disc is still being read survives the
read, an empty or already-applied selection is refused before any copy, an
unchanged copy is never published or handed to "Play latest disc", and a folder the
long build cannot finish in (full, or OneDrive) is refused up front with the fix.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.gui.build_panel_qt import BuildPanel  # noqa: E402
from nfl2k5_throw_tuning_test import _build_synthetic_xbe  # noqa: E402

RETAIL_ISO = Path(os.environ.get(
    "NFL2K5_RETAIL_ISO", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))


def _retail_image_state(panel: BuildPanel, path: Path) -> dict:
    """A disc-image inspection with nothing installed, as mod_build.inspect returns it."""

    state = {key: "retail" for key in panel._boxes()}
    state.update(path=str(path), container="xiso", throw=None)
    return state


class BuildTabNeverWritesARetailCopyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.source = Path(self.tmp.name) / "retail.iso"
        self.source.write_bytes(b"\0" * 4096)
        self.target = Path(self.tmp.name) / "built.iso"
        self.panel = BuildPanel()
        self.panel.apply_state(_retail_image_state(self.panel, self.source))
        self.panel.target_field.setText(str(self.target))

    def tearDown(self) -> None:
        self.panel.deleteLater()
        self.app.processEvents()
        self.tmp.cleanup()

    def test_an_empty_selection_is_refused_with_the_pack_pointer(self) -> None:
        blocker = self.panel.blocker()
        self.assertIn("Nothing is selected", blocker)
        self.assertIn("unchanged", blocker)
        self.assertIn("Install SOFTDRINK 2K28", blocker)
        self.assertFalse(self.panel.build_button.isEnabled())
        self.assertEqual(self.panel.build_button.toolTip(), blocker)

    def test_modern_on_a_retail_disc_is_real_work(self) -> None:
        result = self.panel.apply_preset("softdrink_advanced")
        self.assertGreater(len(result["applied"]), 20)
        self.assertTrue(self.panel.has_work())
        self.assertTrue(self.panel.throw_check.isChecked())
        self.assertTrue(self.panel.plan().throw)
        self.assertEqual(self.panel.blocker(), "", self.panel.blocker())
        self.assertTrue(self.panel.build_button.isEnabled())

    def test_inspect_reports_the_options_the_modern_preset_needs(self) -> None:
        """The page disables a box whose state the read does not report.

        b778-bd2: `inspect` omitted crib_trophy_room, star_career and honors_history, so
        the Modern preset silently left all three out of every build made in the UI.
        """
        from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "default.xbe"
            source.write_bytes(retail_xbe())
            state = mod_build.inspect(source)
        for key in ("crib_trophy_room", "star_career", "module_loader"):
            self.assertIn(key, state)
            self.assertEqual(state[key], "retail", key)
        self.assertEqual(state["honors_history"], "n/a")  # a bare executable cannot carry it

    @unittest.skipUnless(RETAIL_ISO.is_file(), "private USA retail ISO is absent")
    def test_the_modern_preset_on_a_real_retail_image_skips_nothing(self) -> None:
        panel = BuildPanel()
        self.addCleanup(panel.deleteLater)
        panel.begin_reading(RETAIL_ISO)
        panel.apply_state(mod_build.inspect(RETAIL_ISO))
        result = panel.apply_preset("softdrink_advanced")
        self.assertEqual(result["skipped"], [])
        for key in ("crib_trophy_room", "star_career", "honors_history"):
            self.assertIn(key, result["applied"], key)
        self.assertEqual(panel._state["honors_history"], "retail")
        panel.target_field.setText(str(Path(self.tmp.name) / "modern.iso"))
        self.assertEqual(panel.blocker(), "", panel.blocker())
        self.assertTrue(panel.has_work())

    def test_a_tick_made_while_the_disc_is_reading_survives_the_result(self) -> None:
        panel = self.panel
        state = _retail_image_state(panel, self.source)
        panel.begin_reading(self.source)
        panel.throw_check.setChecked(True)
        panel.catch_check.setChecked(True)
        panel.apply_state(state)
        self.assertTrue(panel.throw_check.isChecked(), "the read must not clear a selection made while it ran")
        self.assertTrue(panel.catch_check.isChecked())
        self.assertTrue(panel.has_work())

    def test_a_tick_the_finished_read_cannot_take_is_dropped_and_named(self) -> None:
        panel = self.panel
        state = _retail_image_state(panel, self.source)
        panel.begin_reading(self.source)
        panel.modern_color_check.setEnabled(True)
        panel.modern_color_check.setChecked(True)
        panel.apply_state(dict(state, modern_color="foreign"))
        self.assertFalse(panel.modern_color_check.isChecked())
        note = panel.preset_note.text()
        self.assertIn("could not be kept", note)
        self.assertIn("Modern colour and lighting", note)
        self.assertIn("unrecognized source data", note)

    def test_an_already_installed_tick_is_not_called_dropped(self) -> None:
        panel = self.panel
        state = _retail_image_state(panel, self.source)
        panel.begin_reading(self.source)
        panel.modern_color_check.setEnabled(True)
        panel.modern_color_check.setChecked(True)
        panel.preset_note.setText("base")
        panel.apply_state(dict(state, modern_color="applied"))
        self.assertNotIn("could not be kept", panel.preset_note.text())
        self.assertFalse(panel._modern_color_changed())

    def test_opening_a_different_disc_clears_the_previous_selection(self) -> None:
        panel = self.panel
        panel.throw_check.setChecked(True)
        other = Path(self.tmp.name) / "other.iso"
        other.write_bytes(b"\0" * 4096)
        panel.begin_reading(other)
        panel.apply_state(_retail_image_state(panel, other))
        self.assertFalse(panel.throw_check.isChecked())

    def test_a_onedrive_output_folder_is_refused_with_a_plain_folder(self) -> None:
        panel = self.panel
        panel.throw_check.setChecked(True)
        with mock.patch.object(mod_build.platform_compat, "IS_WINDOWS", True), \
             mock.patch("mod_editor.core.nfl2k5_build_service._cloud_synced_root",
                        return_value=(Path("C:/Users/test/OneDrive"), "the OneDrive folder")):
            problem = mod_build.local_output_problem(self.target)
        self.assertIn("OneDrive", problem)
        self.assertIn("C:\\2K5", problem)
        self.assertIn("Nothing was written", problem)
        # and the Build button names it before any work starts
        with mock.patch.object(mod_build, "local_output_problem", return_value=problem):
            blocker = panel.blocker()
        self.assertEqual(blocker, problem)

    def test_too_little_free_space_is_refused_before_the_copy(self) -> None:
        from nfl2k5_xiso_fixture import SyntheticXiso

        fixture = SyntheticXiso(Path(self.tmp.name), [])
        target = Path(self.tmp.name) / "built.iso"
        with mock.patch.object(mod_build.platform_compat, "available_bytes", return_value=1024):
            with self.assertRaisesRegex(ValueError, "not have enough free space"):
                mod_build.build(mod_build.BuildPlan(str(fixture.path), str(target)), require_change=True)
        self.assertFalse(target.exists())

    def test_an_unchanged_copy_is_refused_and_never_published(self) -> None:
        source = Path(self.tmp.name) / "default.xbe"
        source.write_bytes(_build_synthetic_xbe())
        target = Path(self.tmp.name) / "copy.xbe"
        with self.assertRaisesRegex(ValueError, "identical to the source"):
            mod_build.build(mod_build.BuildPlan(str(source), str(target)), require_change=True)
        self.assertFalse(target.exists(), "a refused unchanged build must not be published")

    def test_the_core_still_makes_a_verified_copy_when_not_required(self) -> None:
        source = Path(self.tmp.name) / "default.xbe"
        source.write_bytes(_build_synthetic_xbe())
        target = Path(self.tmp.name) / "copy.xbe"
        receipt = mod_build.build(mod_build.BuildPlan(str(source), str(target)))
        self.assertEqual(receipt["outcome"]["status"], "unchanged")
        self.assertTrue(target.is_file())

    def test_an_unchanged_build_is_not_the_latest_disc(self) -> None:
        from mod_editor.gui.studio_qt import StudioMainWindow

        class Stub:
            def __init__(self) -> None:
                self.facade = SimpleNamespace(register_external_build=mock.Mock())
                self.status = ""

            def _set_status(self, message: str) -> None:
                self.status = message

            def _refresh_action_states(self) -> None:
                raise AssertionError("an unchanged copy must not refresh Play latest")

        stub = Stub()
        StudioMainWindow._on_build_tab_built(stub, {"target": str(self.target),
                                                    "outcome": {"status": "unchanged"}})
        stub.facade.register_external_build.assert_not_called()
        self.assertIn("unchanged", stub.status)

    def test_a_copy_of_the_open_source_is_not_the_latest_disc(self) -> None:
        from mod_editor.gui.studio_qt import StudioMainWindow

        class Stub:
            def __init__(self) -> None:
                self.facade = SimpleNamespace(register_external_build=mock.Mock())
                self.status = ""

            def _set_status(self, message: str) -> None:
                self.status = message

            def _refresh_action_states(self) -> None:
                raise AssertionError("the source disc must not become Play latest")

        stub = Stub()
        StudioMainWindow._on_build_tab_built(stub, {"target": str(self.target), "source": str(self.target),
                                                    "outcome": {"status": "changed"}})
        stub.facade.register_external_build.assert_not_called()
        self.assertIn("open source disc", stub.status)


if __name__ == "__main__":
    unittest.main()

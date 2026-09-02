"""Product seam tests for the APF save packed-player editor."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.apf_studio.save_roster_players_qt import (  # noqa: E402
    SaveRosterPlayersPanel,
)
from tests.mod_editor.test_apf_save_roster_players import roster_save  # noqa: E402
from tests.test_apf_save_custom_team_appearance import synthetic_stfs  # noqa: E402


class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    @staticmethod
    def _immediate_runner(label, operation, on_success=None, blocking=True):
        del label, blocking
        result = operation(lambda *_args: None)
        if on_success is not None:
            on_success(result)
        return True

    def test_panel_exposes_all_fields_text_and_safe_membership_swaps(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "Roster.ROS"
            source.write_bytes(roster_save())
            panel = SaveRosterPlayersPanel(self._immediate_runner)
            try:
                panel.load_path(source)
                self.application.processEvents()
                self.assertEqual(panel.field.count(), 149)
                self.assertEqual(panel.first_slot.count(), 42)
                self.assertEqual(panel.player_name.text(), "Alpha")
                self.assertFalse(panel.write_button.isEnabled())

                field_index = panel.field.findData("jersey_number")
                panel.field.setCurrentIndex(field_index)
                panel.value_number.setValue(12)
                panel._stage_field()
                panel.text_field.setCurrentIndex(
                    panel.text_field.findData("first_name")
                )
                panel.text_value.setText("Beta")
                panel._stage_text()
                panel._stage_swap()
                self.assertEqual(panel.staged_list.count(), 3)
                self.assertTrue(panel.write_button.isEnabled())
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_hash_verified_stfs_is_editable_as_explicit_raw_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "signed.CON"
            source.write_bytes(synthetic_stfs(roster_save()))
            panel = SaveRosterPlayersPanel(self._immediate_runner)
            try:
                panel.load_path(source)
                self.application.processEvents()
                self.assertIsNotNone(panel.document)
                self.assertTrue(panel.document.signed_container)  # type: ignore[union-attr]
                self.assertTrue(panel.stage_field.isEnabled())
                self.assertIn("raw payload", panel.boundary.text())
                self.assertIn("resigning", panel.boundary.text())
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_roster_workspace_exposes_save_players_tab(self) -> None:
        from mod_editor.apf_studio.gui import InspectorCategoryPage
        from mod_editor.apf_studio.models import ApfCategory

        class _Facade:
            pass

        page = InspectorCategoryPage(
            _Facade(),  # type: ignore[arg-type]
            ApfCategory.ROSTERS,
            self._immediate_runner,
            "Roster inspector",
            lambda _service: ("Roster", None),  # type: ignore[arg-type]
        )
        try:
            self.assertEqual(
                [
                    page.workspace_tabs.tabText(index)  # type: ignore[union-attr]
                    for index in range(page.workspace_tabs.count())  # type: ignore[union-attr]
                ],
                [
                    "Roster + Base Ratings",
                    "Save Players",
                    "53-player Planner",
                    "&Raw Roster Assets",
                ],
            )
            self.assertIsInstance(page.save_roster_players, SaveRosterPlayersPanel)
            page.open_workspace("save-players")
            self.assertEqual(page.workspace_tabs.currentIndex(), 1)  # type: ignore[union-attr]
            page.open_workspace("roster-planner")
            self.assertEqual(page.workspace_tabs.currentIndex(), 2)  # type: ignore[union-attr]
        finally:
            page.deleteLater()
            self.application.processEvents()


class PackagingTests(unittest.TestCase):
    def test_release_allowlist_ships_save_player_service_and_panel(self) -> None:
        root = Path(__file__).resolve().parents[2]
        lines = {
            line.strip()
            for line in (root / "packaging/apf2k8-release-allowlist.txt")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertTrue(
            {
                "mod_editor/apf_studio/save_roster_players.py",
                "mod_editor/apf_studio/save_roster_players_qt.py",
            }
            <= lines
        )


if __name__ == "__main__":
    unittest.main()

"""Headless control-level checks for the all-team equipment-color panel."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QLabel

from mod_editor.apf_studio.backend import ensure_tools_importable
from mod_editor.apf_studio.uniform_equipment_colors_qt import (
    UniformEquipmentColorsPanel,
)


ensure_tools_importable()
import apf_uniform_equipment_color_patch as writer  # type: ignore  # noqa: E402


class _Facade:
    source_ready = True

    def __init__(self) -> None:
        self.modified_asset_ids: frozenset[str] = frozenset()
        self.value = writer.UniformEquipmentColors(
            0,
            writer.EquipmentColorBank(0, 3),
            writer.EquipmentColorBank(1, 4),
        )
        self.target = writer.UniformEquipmentColorTarget(
            writer.asset_id(0), 0, 0, 1, 0, 45, 31, 42, 28
        )
        self.inspection = writer.UniformEquipmentColorInspection(
            self.target,
            self.value,
            (
                0xFFC0C0C0,
                0xFF101010,
                0xFFFFFFFF,
                0xFF004C54,
                0xFF112233,
                0xFF223344,
                0xFF334455,
                0xFF445566,
                0xFF556677,
                0xFF667788,
            ),
            (
                0xFFFFFFFF,
                0xFF000000,
                0xFF010203,
                0xFF102030,
                0xFF203040,
                0xFF304050,
                0xFF405060,
                0xFF506070,
                0xFF607080,
                0xFF708090,
            ),
        )

    def uniform_equipment_color_inspection(self, team_index: int):
        target = writer.UniformEquipmentColorTarget(
            writer.asset_id(team_index), team_index, team_index, 1, 0, 45, 31, 42, 28
        )
        return writer.UniformEquipmentColorInspection(
            target,
            writer.UniformEquipmentColors(team_index, self.value.home, self.value.away),
            self.inspection.home_palette,
            self.inspection.away_palette,
        )

    def uniform_equipment_color_value(self, team_index: int):
        return writer.UniformEquipmentColors(team_index, self.value.home, self.value.away)

    def replace_uniform_equipment_colors(self, value, progress):
        progress("stage", 0, 1)
        self.value = value
        self.modified_asset_ids = frozenset({writer.asset_id(value.team_index)})
        progress("stage", 1, 1)
        return value

    def revert(self, target_id: str, progress):
        progress("revert", 0, 1)
        self.modified_asset_ids = frozenset()
        progress("revert", 1, 1)
        return True


def _run_task(_title, operation, success, _cancellable):
    success(operation(lambda *_args: None))


class UniformEquipmentColorsPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_all_teams_palette_context_and_visor_boundary_are_visible(self) -> None:
        facade = _Facade()
        panel = UniformEquipmentColorsPanel(facade, _run_task)
        self.assertEqual(panel.team.count(), 40)
        self.assertEqual(panel.team.itemText(0), "Americans · slot 0")
        self.assertEqual(panel.team.itemText(23), "Werewolves · slot 23")
        self.assertEqual(panel.team.itemText(24), "Custom / unused team slot 24")
        self.assertEqual(panel.home.facemask.count(), 10)
        self.assertEqual(
            panel.home.facemask.itemText(0), "0 · White / silver · #C0C0C0"
        )
        self.assertEqual(panel.home.facemask.itemText(1), "1 · Black · #101010")
        text = " ".join(label.text() for label in panel.findChildren(QLabel))
        self.assertIn("Player visors remain None, Clear, or Dark", text)
        self.assertIn("no verified per-uniform visor-tint field", text)
        panel.deleteLater()

    def test_stage_and_revert_use_one_team_scoped_asset(self) -> None:
        facade = _Facade()
        panel = UniformEquipmentColorsPanel(facade, _run_task)
        panel.home.facemask.setCurrentIndex(8)
        panel.away.turtleneck.setCurrentIndex(9)
        panel._stage()
        self.assertEqual(facade.value.home.facemask_palette_index, 8)
        self.assertEqual(facade.value.away.team_turtleneck_palette_index, 9)
        self.assertIn(writer.asset_id(0), facade.modified_asset_ids)
        panel._revert()
        self.assertFalse(facade.modified_asset_ids)
        panel.deleteLater()


if __name__ == "__main__":
    unittest.main()

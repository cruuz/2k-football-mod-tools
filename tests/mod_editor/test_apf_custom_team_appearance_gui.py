"""Headless UI contract for the bounded custom-team appearance panel."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import sip  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.apf_studio.custom_team_appearance_qt import (  # noqa: E402
    CustomTeamAppearancePanel,
    apf_custom_team_appearance_patch as writer,
)
from tests.test_apf_save_custom_team_appearance import (  # noqa: E402
    synthetic_save,
    synthetic_stfs,
)


def _bank(asset: int) -> writer.AppearanceBank:
    return writer.AppearanceBank(
        tuple(0xFF000000 + index for index in range(10)),
        bytes((asset, 3, 2, 0, 9, 0, 0, 0)),
        bytes((80, 0, 0, 3, 2, 1, 0, 0)),
    )


class _Facade:
    source_ready = True

    def __init__(self) -> None:
        self.values = {
            slot: writer.CustomTeamAppearance(slot, _bank(7), _bank(19))
            for slot in writer.USER_SLOTS
        }
        self.modified_asset_ids: frozenset[str] = frozenset()

    def custom_team_appearance_value(self, slot: int):
        return self.values[slot]

    def replace_custom_team_appearance(self, appearance, progress):
        progress("checking", 0, 1)
        self.values[appearance.slot] = appearance
        self.modified_asset_ids = self.modified_asset_ids.union(
            {writer.asset_id(appearance.slot)}
        )
        progress("checking", 1, 1)
        return appearance

    def revert(self, asset_id: str, progress):
        self.modified_asset_ids = self.modified_asset_ids.difference({asset_id})
        return True


def _run_task(_label, operation, success=None, _blocking=True):
    result = operation(lambda *_args: None)
    if success is not None:
        success(result)
    return True


class CustomTeamAppearanceGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.application.quit()
        sip.delete(cls.application)
        cls.application = None

    def test_panel_has_only_safe_slots_and_exact_banks(self) -> None:
        panel = CustomTeamAppearancePanel(_Facade(), _run_task)
        try:
            self.assertEqual(panel.slot.count(), 8)
            self.assertEqual(
                [panel.slot.itemData(index) for index in range(panel.slot.count())],
                list(range(32, 40)),
            )
            self.assertEqual(panel.banks.count(), 2)
            self.assertEqual(len(panel.home.palette), 10)
            self.assertEqual(len(panel.away.palette), 10)
            self.assertEqual(len(panel.home.helmet), 8)
            self.assertEqual(len(panel.home.logo), 8)
            self.assertIn("proved", panel.home.helmet[0].toolTip())
            self.assertIn("opaque", panel.home.logo[1].toolTip().lower())
        finally:
            panel.deleteLater()

    def test_eagles_preset_preserves_helmet_assets_and_stages_project(self) -> None:
        facade = _Facade()
        panel = CustomTeamAppearancePanel(facade, _run_task)
        events: list[bool] = []
        panel.modifiedChanged.connect(lambda: events.append(True))
        try:
            panel.preset_button.click()
            self.assertEqual(panel.home.helmet[0].value(), 7)
            self.assertEqual(panel.away.helmet[0].value(), 19)
            self.assertEqual(panel.home.helmet[1].value(), 8)
            self.assertEqual(panel.home.logo[0].value(), 30)
            self.assertEqual(panel.home.palette[8].text(), "FF004C54")
            panel.stage_button.click()
            self.assertIn("apf:custom-team-appearance:32", facade.modified_asset_ids)
            self.assertEqual(events, [True])
            self.assertIn("Staged", panel.status.text())
        finally:
            panel.deleteLater()

    def test_unloaded_panel_never_enables_mutation(self) -> None:
        facade = _Facade()
        facade.source_ready = False
        panel = CustomTeamAppearancePanel(facade, _run_task)
        try:
            # Slot/preset stay disabled without a source; Stage/Revert never
            # silent-gray — clickable with disableReason teaching Load.
            self.assertFalse(panel.preset_button.isEnabled())
            self.assertTrue(panel.stage_button.isEnabled())
            self.assertTrue(panel.revert_button.isEnabled())
            self.assertIn(
                "Load",
                str(panel.stage_button.property("disableReason") or ""),
            )
            self.assertIn(
                "Load",
                str(panel.revert_button.property("disableReason") or ""),
            )
        finally:
            panel.deleteLater()

    def test_raw_save_mode_loads_runtime_slots_without_staging_project(self) -> None:
        facade = _Facade()
        facade.source_ready = False
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "Roster.ROS"
            source.write_bytes(synthetic_save())
            panel = CustomTeamAppearancePanel(facade, _run_task)
            try:
                panel.source_kind.setCurrentIndex(panel.source_kind.findData("raw_save"))
                panel.load_raw_path(source)
                self.assertEqual(panel.slot.count(), 8)
                self.assertEqual(panel.slot.itemData(0), 32)
                self.assertIn("User team 24", panel.slot.itemText(0))
                self.assertIn("occupied", panel.slot.itemText(0))
                self.assertFalse(panel.write_raw_button.isHidden())
                self.assertTrue(panel.write_raw_button.isEnabled())
                self.assertTrue(panel.stage_button.isHidden())
                panel.preset_button.click()
                self.assertEqual(panel.home.logo[0].value(), 30)
                self.assertEqual(facade.modified_asset_ids, frozenset())
                self.assertIn("accepted-team candidate", panel.status.text())
            finally:
                panel.deleteLater()

    def test_stfs_mode_exposes_verified_slots_and_raw_handoff_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "signed-save.bin"
            source.write_bytes(synthetic_stfs(synthetic_save(), b"LIVE"))
            panel = CustomTeamAppearancePanel(_Facade(), _run_task)
            try:
                panel.source_kind.setCurrentIndex(panel.source_kind.findData("raw_save"))
                panel.load_raw_path(source)
                self.assertEqual(panel.slot.count(), 8)
                self.assertTrue(panel.write_raw_button.isEnabled())
                self.assertTrue(panel.preset_button.isEnabled())
                self.assertTrue(panel.extract_raw_button.isEnabled())
                self.assertIn("raw handoff", panel.write_raw_button.text())
                self.assertIn("external STFS reinjection", panel.status.text())
                self.assertIn("does not write the signed container", panel.raw_boundary.text())

                extracted = Path(directory) / "extracted.Roster.ROS"
                receipt = panel._extract_raw_operation(
                    panel.raw_document, extracted, lambda *_args: None
                )
                self.assertTrue(receipt.verification_passed)
                self.assertEqual(extracted.read_bytes(), synthetic_save())
            finally:
                panel.deleteLater()


if __name__ == "__main__":
    unittest.main()

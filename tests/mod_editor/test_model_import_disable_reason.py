"""Model import never looks dead without an explanation (APF panel)."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.apf_studio.model_export_qt import (  # noqa: E402
    PlayerEquipmentModelExportPanel,
)


class ModelImportDisableReasonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    @staticmethod
    def _runner(*_args):
        return True

    def test_import_without_source_stays_clickable_with_explain_tooltip(self) -> None:
        """Never silent-gray: enabled + tooltip + click-to-explain dialog path."""

        class _Facade:
            source_ready = False
            source = None

        panel = PlayerEquipmentModelExportPanel(_Facade(), self._runner)
        try:
            for button in panel.import_buttons.values():
                # Stay clickable so a disabled-looking control is never a dead no-op.
                self.assertTrue(button.isEnabled())
                tip = button.toolTip()
                self.assertTrue(tip.strip(), "import must explain why source is required")
                self.assertIn("Load", tip)
                self.assertIn("0A", tip)
                reason = button.property("disableReason")
                self.assertTrue(str(reason or "").strip())
                self.assertIn("Load", str(reason))
        finally:
            panel.deleteLater()
            self.application.processEvents()

    def test_import_enabled_with_source_still_describes_contract(self) -> None:
        class _Source:
            index_0a = Path("/private/game/0A")

        class _Facade:
            source_ready = True
            source = _Source()

        panel = PlayerEquipmentModelExportPanel(_Facade(), self._runner)
        try:
            for button in panel.import_buttons.values():
                self.assertTrue(button.isEnabled())
                self.assertIn("topology", button.toolTip().casefold())
        finally:
            panel.deleteLater()
            self.application.processEvents()


class TwoK5StadiumImportExplainContractTests(unittest.TestCase):
    """2K5 Stadium model Import/Export must never be silent-gray (shipped source)."""

    def test_stadium_import_export_use_disable_reason_and_stay_enabled(self) -> None:
        root = Path(__file__).resolve().parents[2]
        source = (root / "mod_editor/gui/studio_qt.py").read_text(encoding="utf-8")
        # Construction: buttons start enabled (not permanently gray).
        self.assertIn("import_scene_button.setEnabled(True)", source)
        self.assertIn("export_scene_button.setEnabled(True)", source)
        # Refresh path sets disableReason for click-to-explain.
        self.assertIn('_stadium_import_scene_button', source)
        self.assertIn('"disableReason"', source)
        self.assertIn("Import edited model", source)
        # Click handler reads disableReason before dialog.
        self.assertIn(
            'str(import_scene.property("disableReason") or "").strip()',
            source,
        )


class ApfStadiumMeshImportExplainContractTests(unittest.TestCase):
    """APF Stadium Studio mesh Import/Export never silent-gray."""

    def test_apf_stadium_mesh_buttons_use_disable_reason(self) -> None:
        root = Path(__file__).resolve().parents[2]
        source = (root / "mod_editor/apf_studio/gui.py").read_text(encoding="utf-8")
        self.assertIn("def _refresh_mesh_action_buttons", source)
        self.assertIn('setProperty("disableReason", block)', source)
        self.assertIn("Cannot import stadium mesh yet", source)
        self.assertIn("Cannot export stadium mesh yet", source)
        # Buttons stay enabled in the refresh path (never setEnabled(False)).
        self.assertIn("self.import_model_button.setEnabled(True)", source)
        self.assertIn("self.export_model_button.setEnabled(True)", source)

    def test_apf_stadium_mesh_panel_without_source_stays_clickable(self) -> None:
        class _Facade:
            source_ready = False
            source = None

        def _runner(*_args, **_kwargs):
            return True

        # Import late to keep module import cost out of other tests' setUp.
        from mod_editor.apf_studio.gui import StadiumStudioPage  # noqa: WPS433

        panel = StadiumStudioPage(_Facade(), _runner)  # type: ignore[arg-type]
        try:
            self.assertTrue(panel.import_model_button.isEnabled())
            self.assertTrue(panel.export_model_button.isEnabled())
            tip = panel.import_model_button.toolTip()
            self.assertIn("Load", tip)
            reason = str(panel.import_model_button.property("disableReason") or "")
            self.assertTrue(reason.strip())
            self.assertIn("Load", reason)
        finally:
            panel.deleteLater()
            self.application.processEvents()

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])


class ApfWordmarkImportExplainContractTests(unittest.TestCase):
    """Wordmark Import/Export never silent-gray when game not loaded."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_wordmark_import_export_without_source_stay_clickable(self) -> None:
        class _Facade:
            source_ready = False
            source = None
            modified_asset_ids = frozenset()

            def uniform_assets(self, family=None):
                return ()

        def _runner(*_args, **_kwargs):
            return True

        from mod_editor.apf_studio.gui import ApfTextLogoPanel  # noqa: WPS433

        panel = ApfTextLogoPanel(_Facade(), _runner)  # type: ignore[arg-type]
        try:
            self.assertTrue(panel.import_button.isEnabled())
            self.assertTrue(panel.export_button.isEnabled())
            tip = panel.import_button.toolTip()
            self.assertIn("Load", tip)
            reason = str(panel.import_button.property("disableReason") or "")
            self.assertIn("Load", reason)
        finally:
            panel.deleteLater()
            self.application.processEvents()


if __name__ == "__main__":
    unittest.main()

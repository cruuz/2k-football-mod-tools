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


if __name__ == "__main__":
    unittest.main()

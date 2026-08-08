from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import sip  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.apf_studio.gui import InspectorBrowser  # noqa: E402
from mod_editor.apf_studio.inspectors import PagedModel, _row  # noqa: E402

import apf_txt_loc_patch as writer  # noqa: E402


class _TextFacade:
    def __init__(self) -> None:
        self.allocation = writer.TextAllocation(
            asset_id="apf:text-pool:1127:0:10",
            outer_index=1127,
            inner_index=0,
            table_name="English",
            pool_index=10,
            text="HOME",
            allocation_bytes=10,
            maximum_utf16_units=4,
            reference_count=6,
            editable=True,
            note="Shared by six labels.",
        )
        self.modified_asset_ids: frozenset[str] = frozenset()
        self.export_calls: list[Path] = []
        self.import_calls: list[Path] = []

    def localization_text_allocations(self) -> tuple[object, ...]:
        return (self.allocation,)

    def localization_text_value(self, _asset_id: str) -> str:
        return "HOME"

    def export_localization_text_sheet(
        self, destination: Path, _progress: object
    ) -> object:
        self.export_calls.append(destination)
        return SimpleNamespace(destination=destination, allocation_count=2413)

    def import_localization_text_sheet(
        self, source: Path, _progress: object
    ) -> object:
        self.import_calls.append(source)
        self.modified_asset_ids = frozenset({self.allocation.asset_id})
        return SimpleNamespace(
            row_count=2413,
            replacement_count=7,
            revert_count=2,
            changed_count=9,
        )


class ApfTextSheetGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.application.quit()
        sip.delete(cls.application)
        cls.application = None

    @staticmethod
    def _model() -> PagedModel:
        return PagedModel(
            (
                _row(
                    "apf:text-pool:1127:0:10",
                    "localization_pool_string",
                    "HOME",
                    "English pool 10",
                    {
                        "bank_type": "TXT loc system",
                        "pool_index": 10,
                    },
                ),
            )
        )

    def test_text_sheet_buttons_enable_only_with_a_loaded_text_model(self) -> None:
        facade = _TextFacade()
        browser = InspectorBrowser(
            "Universal text",
            facade,  # type: ignore[arg-type]
            lambda *_args, **_kwargs: None,
            text_mode=True,
        )
        try:
            # Never silent-gray: unload state stays clickable with disableReason.
            self.assertTrue(browser.export_text_sheet_button.isEnabled())
            self.assertTrue(browser.import_text_sheet_button.isEnabled())
            self.assertTrue(
                str(browser.export_text_sheet_button.property("disableReason") or "").strip()
            )
            self.assertTrue(
                str(browser.import_text_sheet_button.property("disableReason") or "").strip()
            )
            browser.set_model(self._model(), "fixture")
            self.assertTrue(browser.export_text_sheet_button.isEnabled())
            self.assertTrue(browser.import_text_sheet_button.isEnabled())
            self.assertFalse(
                str(browser.export_text_sheet_button.property("disableReason") or "").strip()
            )
            self.assertIn("every owned", browser.export_text_sheet_button.toolTip())
            self.assertIn("one Undo", browser.import_text_sheet_button.toolTip())
            browser.set_unavailable("unavailable")
            self.assertTrue(browser.export_text_sheet_button.isEnabled())
            self.assertTrue(browser.import_text_sheet_button.isEnabled())
            self.assertTrue(
                str(browser.export_text_sheet_button.property("disableReason") or "").strip()
            )
            self.assertTrue(
                str(browser.import_text_sheet_button.property("disableReason") or "").strip()
            )
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_text_sheet_gui_dispatches_export_and_one_batch_import_signal(self) -> None:
        facade = _TextFacade()

        def run_task(
            _title: str,
            operation: object,
            complete: object,
            _blocking: bool,
        ) -> None:
            result = operation(lambda *_progress: None)  # type: ignore[operator]
            complete(result)  # type: ignore[operator]

        browser = InspectorBrowser(
            "Universal text",
            facade,  # type: ignore[arg-type]
            run_task,
            text_mode=True,
        )
        modified_events: list[str] = []
        browser.modifiedChanged.connect(lambda: modified_events.append("modified"))
        try:
            browser.set_model(self._model(), "fixture")
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                export_path = root / "sheet.csv"
                import_path = root / "edited.csv"
                import_path.write_text("test", encoding="utf-8")
                with (
                    patch(
                        "mod_editor.apf_studio.gui.QFileDialog.getSaveFileName",
                        return_value=(str(export_path), "APF Text Sheet (*.csv)"),
                    ),
                    patch(
                        "mod_editor.apf_studio.gui.QFileDialog.getOpenFileName",
                        return_value=(str(import_path), "APF Text Sheet (*.csv)"),
                    ),
                    patch(
                        "mod_editor.apf_studio.gui.QMessageBox.information",
                        return_value=0,
                    ) as information,
                ):
                    browser._export_text_sheet()
                    browser._import_text_sheet()
                self.assertEqual(facade.export_calls, [export_path])
                self.assertEqual(facade.import_calls, [import_path])
                self.assertEqual(modified_events, ["modified"])
                messages = "\n".join(
                    str(call.args[2]) for call in information.call_args_list
                )
                self.assertIn("keep it private", messages)
                self.assertIn("one Undo action", messages)
        finally:
            browser.deleteLater()
            self.application.processEvents()



    def test_text_apply_and_sheet_buttons_never_silent_gray_at_construction(self) -> None:
        facade = _TextFacade()
        browser = InspectorBrowser(
            "Universal text",
            facade,  # type: ignore[arg-type]
            lambda *_args, **_kwargs: None,
            text_mode=True,
        )
        try:
            self.assertTrue(browser.apply_text_button.isEnabled())
            self.assertTrue(
                str(browser.apply_text_button.property("disableReason") or "").strip()
            )
            self.assertTrue(browser.export_text_sheet_button.isEnabled())
            self.assertTrue(
                str(browser.export_text_sheet_button.property("disableReason") or "").strip()
            )
        finally:
            browser.deleteLater()
            self.application.processEvents()


if __name__ == "__main__":
    unittest.main()

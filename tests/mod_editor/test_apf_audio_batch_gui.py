from __future__ import annotations

import os
import inspect
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import sip  # noqa: E402
from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.apf_studio.gui import (  # noqa: E402
    ApfStudioMainWindow,
    InspectorBrowser,
)
from mod_editor.apf_studio.inspectors import (  # noqa: E402
    ExportIdentity,
    InspectorRow,
    PagedModel,
)
from mod_editor.apf_studio.models import (  # noqa: E402
    ExternalAudioBankIdentity,
    ExternalAudioBankOwner,
)


def _audio_row(
    row_id: str,
    kind: str,
    *,
    identity: ExportIdentity | None = None,
    external_identity: ExternalAudioBankIdentity | None = None,
) -> InspectorRow:
    return InspectorRow(
        row_id=row_id,
        kind=kind,
        title=row_id.replace(":", " ").title(),
        subtitle="Synthetic source-owned audio metadata",
        fields={
            "outer_table_index": identity.outer_table_index if identity else 0,
            "inner_file_index": identity.inner_file_index if identity else 0,
            "substream_index": identity.substream_index if identity else None,
            "substream_count": 1 if kind == "ausb_bank" else 0,
            "sample_rate": 48_000,
            "derived_channel_count": 2,
            "duration_seconds": 1.0,
            "role_id": "fixture",
            "role_label": "Fixture audio",
            "audio_source_id": "fixture-source",
            "audio_source_label": "Fixture source",
        },
        export_identity=identity,
        external_bank_identity=external_identity,
        _search_text=row_id,
    )


def _audio_model() -> PagedModel:
    return PagedModel(
        (
            _audio_row(
                "audio:audo:1",
                "audo",
                identity=ExportIdentity("audo", 4, 1, None, "audo-1"),
            ),
            _audio_row("audio:ausb-index:1", "ausb_bank"),
            _audio_row(
                "audio:ausb-stream:1",
                "ausb_substream",
                identity=ExportIdentity(
                    "ausb_substream", 8, 2, 1, "ausb-stream-1"
                ),
            ),
            _audio_row(
                "audio:physical-bank:1",
                "external_bank",
                external_identity=ExternalAudioBankIdentity(
                    "jukeboxmusic.bin",
                    14,
                    0x1234ABCD,
                    4_096,
                    (
                        ExternalAudioBankOwner(
                            8,
                            2,
                            "jukeboxmusic",
                            15,
                            48_000,
                            2,
                        ),
                    ),
                ),
            ),
        ),
        ("The fixture exposes every semantic row to the GUI.",),
    )


class _AudioBatchFacade:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.bank_calls: list[dict[str, object]] = []

    def export_audio_batch(
        self,
        rows: tuple[InspectorRow, ...],
        destination: Path,
        *,
        output_extension: str,
        batch_name: str,
        progress: object,
        cancel_requested: object,
    ) -> object:
        selected = tuple(rows)
        self.calls.append(
            {
                "rows": selected,
                "destination": destination,
                "output_extension": output_extension,
                "batch_name": batch_name,
                "cancel_requested": cancel_requested,
            }
        )
        progress("Fixture complete", len(selected), len(selected))  # type: ignore[operator]
        return SimpleNamespace(
            path=destination,
            requested=len(selected),
            succeeded=1,
            failed=1,
            unsupported=2,
            cancelled=0,
            was_cancelled=False,
            payload_bytes=4_096,
            catalog_record_count=len(selected),
            playlist_record_count=1,
        )

    def export_external_audio_bank_bundle(
        self,
        identities: tuple[ExternalAudioBankIdentity, ...],
        destination: Path,
        *,
        bundle_name: str,
        progress: object,
        cancel_requested: object,
    ) -> object:
        selected = tuple(identities)
        self.bank_calls.append(
            {
                "identities": selected,
                "destination": destination,
                "bundle_name": bundle_name,
                "cancel_requested": cancel_requested,
            }
        )
        progress("Fixture banks complete", len(selected), len(selected))  # type: ignore[operator]
        return SimpleNamespace(
            path=destination,
            requested=len(selected),
            succeeded=len(selected),
            failed=0,
            cancelled=0,
            was_cancelled=False,
            encoded_bytes=sum(identity.encoded_size for identity in selected),
        )


class ApfAudioBatchGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.application.quit()
        sip.delete(cls.application)
        cls.application = None

    def _browser(
        self,
    ) -> tuple[
        InspectorBrowser,
        _AudioBatchFacade,
        list[tuple[str, bool, tuple[tuple[str, int, int], ...]]],
    ]:
        facade = _AudioBatchFacade()
        tasks: list[tuple[str, bool, tuple[tuple[str, int, int], ...]]] = []

        def run_task(
            title: str,
            operation: object,
            complete: object,
            blocking: bool,
        ) -> None:
            progress_events: list[tuple[str, int, int]] = []
            result = operation(  # type: ignore[operator]
                lambda stage, completed, total: progress_events.append(
                    (stage, completed, total)
                )
            )
            tasks.append((title, blocking, tuple(progress_events)))
            complete(result)  # type: ignore[operator]

        browser = InspectorBrowser(
            "Complete audio inventory",
            facade,  # type: ignore[arg-type]
            run_task,
            audio_mode=True,
        )
        browser.set_model(_audio_model(), "4 fixture rows")
        self.application.processEvents()
        return browser, facade, tasks

    def test_complete_catalog_action_is_audio_only_and_explains_boundaries(self) -> None:
        browser, _facade, _tasks = self._browser()
        non_audio = InspectorBrowser(
            "Generic inspector",
            _AudioBatchFacade(),  # type: ignore[arg-type]
            lambda *_args: None,
        )
        try:
            self.assertFalse(browser.export_complete_audio_catalog_button.isHidden())
            self.assertTrue(browser.export_complete_audio_catalog_button.isEnabled())
            self.assertEqual(
                browser.export_complete_audio_catalog_button.text(),
                "Export complete audio catalog…",
            )
            combined_copy = (
                browser.complete_audio_catalog_note.text()
                + " "
                + browser.export_complete_audio_catalog_button.toolTip()
            )
            self.assertIn("47,814", combined_copy)
            self.assertIn("20 AUSB index", combined_copy)
            self.assertIn("19 physical-bank", combined_copy)
            self.assertIn("unsupported", combined_copy)
            self.assertIn("shareable project", combined_copy)
            self.assertIn("catalog.csv", combined_copy)
            self.assertIn("playlist.m3u8", combined_copy)
            self.assertIn("checksums", combined_copy)
            self.assertEqual(
                browser.export_original_audio_banks_button.text(),
                "Export all original banks (1)…",
            )
            self.assertTrue(browser.export_original_audio_banks_button.isEnabled())
            self.assertIn(
                "soundtrack banks",
                browser.export_original_audio_banks_button.toolTip(),
            )
            self.assertFalse(browser.cancel_audio_export_button.isEnabled())
            self.assertTrue(
                non_audio.export_complete_audio_catalog_button.isHidden()
            )
            self.assertTrue(non_audio.complete_audio_catalog_note.isHidden())
            self.assertTrue(non_audio.export_original_audio_banks_button.isHidden())
            self.assertTrue(non_audio.cancel_audio_export_button.isHidden())
            self.assertIsNotNone(browser.detail_scroll)
            assert browser.detail_scroll is not None
            self.assertEqual(
                browser.detail_scroll.horizontalScrollBarPolicy(),
                Qt.ScrollBarAlwaysOff,
            )
            self.assertGreaterEqual(
                browser.detail_scroll.widget().minimumHeight(), 620
            )
            self.assertIsNone(non_audio.detail_scroll)
        finally:
            browser.deleteLater()
            non_audio.deleteLater()
            self.application.processEvents()

    def test_product_theme_keeps_native_information_dialogs_high_contrast(self) -> None:
        style_source = inspect.getsource(ApfStudioMainWindow._apply_style)
        self.assertIn("QMessageBox QLabel", style_source)
        self.assertIn("QMessageBox QPushButton:default", style_source)
        self.assertIn("background: #101827", style_source)
        self.assertIn("color: #eef4ff", style_source)

    def test_original_xma_export_uses_every_model_row_and_blocking_progress(self) -> None:
        browser, facade, tasks = self._browser()
        model_rows = browser.model.rows if browser.model is not None else ()
        with tempfile.TemporaryDirectory() as name:
            destination_without_suffix = Path(name) / "complete-audio"
            messages: list[tuple[str, str]] = []
            try:
                with patch(
                    "mod_editor.apf_studio.gui.QFileDialog.getSaveFileName",
                    return_value=(
                        str(destination_without_suffix),
                        "Original XMA1 audio catalog ZIP (*.zip)",
                    ),
                ), patch(
                    "mod_editor.apf_studio.gui.QMessageBox.information",
                    side_effect=lambda _owner, title, message: messages.append(
                        (title, message)
                    ),
                ):
                    browser._export_complete_audio_catalog()

                self.assertEqual(len(facade.calls), 1)
                call = facade.calls[0]
                self.assertEqual(call["rows"], model_rows)
                self.assertEqual(len(call["rows"]), 4)  # type: ignore[arg-type]
                self.assertEqual(
                    call["destination"], destination_without_suffix.with_suffix(".zip")
                )
                self.assertEqual(call["output_extension"], ".xma")
                self.assertEqual(
                    call["batch_name"], "APF 2K8 complete audio catalog"
                )
                self.assertTrue(callable(call["cancel_requested"]))
                self.assertEqual(tasks[0][0], "Exporting complete APF audio catalog")
                self.assertTrue(tasks[0][1])
                self.assertEqual(tasks[0][2][-1], ("Fixture complete", 4, 4))
                self.assertEqual(messages[0][0], "Complete audio catalog exported")
                for count_line in (
                    "Requested: 4",
                    "Success: 1",
                    "Failure: 1",
                    "Unsupported: 2",
                    "Cancelled: 0",
                    "Catalog CSV rows: 4",
                    "Playlist entries: 1",
                    "Exact exported sound bytes: 4.0 KB",
                ):
                    self.assertIn(count_line, messages[0][1])
                self.assertIn("manifest and catalog.csv account for every", messages[0][1])
                self.assertIn("SHA-256", messages[0][1])
                self.assertIn("playlist.m3u8", messages[0][1])
                self.assertIn("not stored in a shareable", messages[0][1])
            finally:
                browser.deleteLater()
                self.application.processEvents()

    def test_verified_wav_filter_is_forwarded_without_changing_shortlist_limits(self) -> None:
        browser, facade, _tasks = self._browser()
        with tempfile.TemporaryDirectory() as name:
            destination = Path(name) / "complete-wav.zip"
            try:
                with patch(
                    "mod_editor.apf_studio.gui.QFileDialog.getSaveFileName",
                    return_value=(
                        str(destination),
                        "Decoder-verified WAV audio catalog ZIP (*.zip)",
                    ),
                ), patch(
                    "mod_editor.apf_studio.gui.QMessageBox.information"
                ):
                    browser._export_complete_audio_catalog()

                self.assertEqual(facade.calls[0]["output_extension"], ".wav")
                self.assertEqual(len(browser._matching_audio_rows()), 2)
                self.assertEqual(
                    browser.export_matching_button.text(),
                    "Export matching sounds (2)…",
                )
                self.assertEqual(browser.shortlist_count.text(), "Selected 0 / 256")
                self.assertTrue(browser.replace_audio_button.isEnabled())
                self.assertEqual(
                    browser.replace_audio_button.text(), "Replace with XMA1…"
                )
                self.assertIn(
                    "pre-encoded RIFF XMA1",
                    browser.replace_audio_button.toolTip(),
                )
            finally:
                browser.deleteLater()
                self.application.processEvents()

    def test_all_original_bank_bundle_uses_only_physical_identities_and_reports_bytes(self) -> None:
        browser, facade, tasks = self._browser()
        with tempfile.TemporaryDirectory() as name:
            destination_without_suffix = Path(name) / "all-original-banks"
            messages: list[tuple[str, str]] = []
            try:
                with patch(
                    "mod_editor.apf_studio.gui.QFileDialog.getSaveFileName",
                    return_value=(
                        str(destination_without_suffix),
                        "Original APF XMA1 bank bundle ZIP (*.zip)",
                    ),
                ), patch(
                    "mod_editor.apf_studio.gui.QMessageBox.information",
                    side_effect=lambda _owner, title, message: messages.append(
                        (title, message)
                    ),
                ):
                    browser._export_all_original_audio_banks()

                self.assertEqual(len(facade.bank_calls), 1)
                call = facade.bank_calls[0]
                identities = call["identities"]
                self.assertEqual(len(identities), 1)  # type: ignore[arg-type]
                self.assertEqual(
                    identities[0].external_filename,  # type: ignore[index,union-attr]
                    "jukeboxmusic.bin",
                )
                self.assertEqual(
                    call["destination"], destination_without_suffix.with_suffix(".zip")
                )
                self.assertEqual(
                    call["bundle_name"], "APF 2K8 original external audio banks"
                )
                self.assertTrue(callable(call["cancel_requested"]))
                self.assertEqual(
                    tasks[-1][0], "Exporting all original APF audio banks"
                )
                self.assertEqual(tasks[-1][2][-1], ("Fixture banks complete", 1, 1))
                self.assertEqual(messages[0][0], "Original audio banks exported")
                for expected in (
                    "Requested banks: 1",
                    "Success: 1",
                    "Failure: 0",
                    "Cancelled: 0",
                    "Exact bank bytes: 4.0 KB",
                    "soundtrack banks",
                    "not directly playable or replaceable",
                    "not stored in a shareable",
                ):
                    self.assertIn(expected, messages[0][1])
            finally:
                browser.deleteLater()
                self.application.processEvents()

    def test_bulk_audio_cancel_control_is_cooperative_and_recovers(self) -> None:
        browser, _facade, _tasks = self._browser()
        try:
            browser._audio_export_started()
            self.assertFalse(browser.export_complete_audio_catalog_button.isEnabled())
            self.assertFalse(browser.export_original_audio_banks_button.isEnabled())
            self.assertTrue(browser.cancel_audio_export_button.isEnabled())

            browser.cancel_audio_export_button.click()
            self.assertTrue(browser._audio_export_cancel.is_set())
            self.assertFalse(browser.cancel_audio_export_button.isEnabled())
            self.assertEqual(browser.cancel_audio_export_button.text(), "Cancelling…")

            browser._audio_export_finished()
            self.assertFalse(browser._audio_export_cancel.is_set())
            self.assertTrue(browser.export_complete_audio_catalog_button.isEnabled())
            self.assertTrue(browser.export_original_audio_banks_button.isEnabled())
            self.assertFalse(browser.cancel_audio_export_button.isEnabled())
            self.assertEqual(
                browser.cancel_audio_export_button.text(), "Cancel audio export"
            )
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_existing_destination_is_refused_before_the_batch_task_starts(self) -> None:
        browser, facade, tasks = self._browser()
        with tempfile.TemporaryDirectory() as name:
            destination = Path(name) / "already-there.zip"
            destination.write_bytes(b"keep")
            messages: list[tuple[str, str]] = []
            try:
                with patch(
                    "mod_editor.apf_studio.gui.QFileDialog.getSaveFileName",
                    return_value=(
                        str(destination),
                        "Original XMA1 audio catalog ZIP (*.zip)",
                    ),
                ), patch(
                    "mod_editor.apf_studio.gui.QMessageBox.information",
                    side_effect=lambda _owner, title, message: messages.append(
                        (title, message)
                    ),
                ):
                    browser._export_complete_audio_catalog()

                self.assertEqual(destination.read_bytes(), b"keep")
                self.assertEqual(facade.calls, [])
                self.assertEqual(tasks, [])
                self.assertEqual(messages[0][0], "Choose a new filename")
                self.assertIn("never overwrite", messages[0][1])
            finally:
                browser.deleteLater()
                self.application.processEvents()


if __name__ == "__main__":
    unittest.main()

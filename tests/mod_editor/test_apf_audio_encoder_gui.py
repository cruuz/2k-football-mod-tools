"""Headless GUI coverage for APF's user-supplied XMA1 encoder bridge."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import sip  # noqa: E402
from PyQt5.QtCore import QSettings  # noqa: E402
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

from mod_editor.apf_studio.audio_encoding import ExternalXma1Encoder  # noqa: E402
from mod_editor.apf_studio.gui import (  # noqa: E402
    AUDIO_REPLACEMENT_IMPORT_CONFIRMATION_CONTRACT,
    CATEGORY_BLURBS,
    ExternalXma1EncoderDialog,
    InspectorBrowser,
)
from mod_editor.apf_studio.inspectors import (  # noqa: E402
    ExportIdentity,
    InspectorRow,
    PagedModel,
)
from mod_editor.apf_studio.models import ApfCategory  # noqa: E402


ROW_ID = "audio:audo:pcm-authoring-fixture"


def _audio_model() -> PagedModel:
    identity = ExportIdentity(
        "audo",
        4,
        1,
        None,
        "pcm-authoring-fixture",
    )
    return PagedModel(
        (
            InspectorRow(
                row_id=ROW_ID,
                kind="audo",
                title="PCM authoring fixture",
                subtitle="Synthetic audio identity",
                fields={
                    "outer_table_index": 4,
                    "inner_file_index": 1,
                    "sample_rate": 48_000,
                    "derived_channel_count": 2,
                    "duration_seconds": 1.0,
                    "encoded_size": 0x800,
                    "role_id": "fixture",
                    "role_label": "Fixture audio",
                    "audio_source_id": "fixture-source",
                    "audio_source_label": "Fixture source",
                },
                export_identity=identity,
                _search_text="pcm authoring fixture",
            ),
        ),
        ("Synthetic audio model for GUI dispatch only.",),
    )


class _EncoderGuiFacade:
    def __init__(self) -> None:
        self.modified_asset_ids: frozenset[str] = frozenset()
        self.template_calls: list[dict[str, object]] = []
        self.replace_calls: list[dict[str, object]] = []
        self.pack_import_calls: list[dict[str, object]] = []
        self.pack_preview_calls: list[dict[str, object]] = []
        self.pack_input_kind = "xma1"
        self.pack_would_change = 1
        self.cancel_hook: object | None = None

    def export_audio_pcm_template(
        self,
        identity: ExportIdentity,
        destination: Path,
        progress: object,
    ) -> object:
        self.template_calls.append(
            {"identity": identity, "destination": destination}
        )
        progress("Fixture template", 1, 1)  # type: ignore[operator]
        return SimpleNamespace(
            path=destination,
            byte_size=192_044,
            sha256="a" * 64,
            channels=2,
            sample_rate=48_000,
            frame_count=48_000,
            encoded_size=0x800,
            contains_retail_audio=False,
        )

    def replace_audio_from_pcm(
        self,
        identity: ExportIdentity,
        source: Path,
        encoder: ExternalXma1Encoder,
        progress: object,
        *,
        cancel_requested: object,
    ) -> object:
        call = {
            "identity": identity,
            "source": source,
            "encoder": encoder,
            "cancel_requested": cancel_requested,
        }
        self.replace_calls.append(call)
        if callable(self.cancel_hook):
            self.cancel_hook()
        if cancel_requested():  # type: ignore[operator]
            call["cancel_observed"] = True
            raise ValueError("Fixture cancellation staged no edit")
        progress("Fixture exact-slot validation", 1, 1)  # type: ignore[operator]
        self.modified_asset_ids = frozenset({ROW_ID})
        return SimpleNamespace(asset_id=ROW_ID)

    def preview_audio_replacement_pack(
        self,
        root: Path,
        progress: object,
        *,
        encoder: ExternalXma1Encoder | None = None,
        cancel_requested: object,
    ) -> object:
        call = {
            "root": root,
            "encoder": encoder,
            "cancel_requested": cancel_requested,
            "input_kind": self.pack_input_kind,
        }
        self.pack_preview_calls.append(call)
        if self.pack_input_kind == "pcm16" and encoder is None:
            raise ValueError(
                "PCM16 audio replacement pack requires a configured "
                "ExternalXma1Encoder; choose Configure XMA1 encoder first"
            )
        progress("Fixture replacement-pack preview", 1, 1)  # type: ignore[operator]
        return SimpleNamespace(
            template_entry_count=1,
            supplied_count=1,
            would_change_count=self.pack_would_change,
            already_current_count=1 - self.pack_would_change,
            current_modified_audio_count=0,
            resulting_modified_audio_count=self.pack_would_change,
            missing_count=0,
            validated_count=1,
            confirmation_token="e" * 64,
            was_cancelled=False,
            input_kind=self.pack_input_kind,
        )

    def import_audio_replacement_pack(
        self,
        root: Path,
        progress: object,
        *,
        encoder: ExternalXma1Encoder | None = None,
        cancel_requested: object,
        confirmation_token: str,
    ) -> object:
        call = {
            "root": root,
            "encoder": encoder,
            "cancel_requested": cancel_requested,
            "input_kind": self.pack_input_kind,
            "confirmation_token": confirmation_token,
        }
        self.pack_import_calls.append(call)
        progress("Fixture replacement-pack apply", 1, 1)  # type: ignore[operator]
        self.modified_asset_ids = frozenset({ROW_ID})
        return SimpleNamespace(
            template_entry_count=1,
            supplied_count=1,
            staged_count=1,
            unchanged_count=0,
            missing_count=0,
            validated_count=1,
            was_cancelled=False,
            input_kind=self.pack_input_kind,
        )


class ApfAudioEncoderGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.application.quit()
        sip.delete(cls.application)
        cls.application = None

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="apf-audio-encoder-gui-"
        )
        self.root = Path(self.temporary.name)
        self.settings = QSettings(
            str(self.root / "audio-authoring.ini"), QSettings.IniFormat
        )
        self.settings.clear()
        self.settings.sync()
        self.browsers: list[InspectorBrowser] = []

    def tearDown(self) -> None:
        for browser in self.browsers:
            browser.close()
            sip.delete(browser)
        self.settings.sync()
        self.temporary.cleanup()

    def _tool(self, name: str = "fixture-encoder") -> Path:
        path = self.root / name
        path.write_bytes(b"synthetic external tool")
        path.chmod(0o700)
        return path

    def _browser(
        self,
    ) -> tuple[
        InspectorBrowser,
        _EncoderGuiFacade,
        list[tuple[str, bool]],
        list[Exception],
    ]:
        facade = _EncoderGuiFacade()
        tasks: list[tuple[str, bool]] = []
        errors: list[Exception] = []

        def run_task(
            title: str,
            operation: object,
            complete: object,
            blocking: bool,
        ) -> None:
            tasks.append((title, blocking))
            try:
                result = operation(lambda *_args: None)  # type: ignore[operator]
            except Exception as exc:
                errors.append(exc)
                return
            complete(result)  # type: ignore[operator]

        browser = InspectorBrowser(
            "Complete audio inventory",
            facade,  # type: ignore[arg-type]
            run_task,
            audio_mode=True,
            audio_settings=self.settings,
        )
        browser.set_model(_audio_model(), "1 synthetic sound")
        browser.table.selectRow(0)
        self.application.processEvents()
        self.browsers.append(browser)
        return browser, facade, tasks, errors

    def test_audio_detail_exposes_complete_no_terminal_authoring_flow(self) -> None:
        browser, _facade, _tasks, _errors = self._browser()

        self.assertEqual(
            browser.export_pcm_template_button.text(),
            "Export PCM authoring template…",
        )
        self.assertEqual(
            browser.replace_pcm_audio_button.text(), "Replace from audio…"
        )
        self.assertIn(
            "WAV, MP3, FLAC, OGG, M4A",
            browser.replace_pcm_audio_button.toolTip(),
        )
        self.assertEqual(
            browser.configure_audio_encoder_button.text(),
            "Configure XMA1 encoder…",
        )
        self.assertEqual(browser.replace_audio_button.text(), "Replace with XMA1…")
        self.assertTrue(browser.export_pcm_template_button.isEnabled())
        self.assertTrue(browser.replace_pcm_audio_button.isEnabled())
        self.assertTrue(browser.cancel_pcm_encoding_button.isHidden())
        self.assertIn("Not configured", browser.audio_encoder_status.text())
        self.assertIn("No encoder ships", browser.audio_replace_note.text())
        self.assertIn("every slot gate", browser.replace_pcm_audio_button.toolTip())
        self.assertIn("folder or ZIP", CATEGORY_BLURBS[ApfCategory.AUDIO])
        self.assertEqual(
            browser.audio_replacement_pack_input.currentData(), "xma1"
        )
        self.assertEqual(
            browser.audio_replacement_pack_input.currentText(),
            "Pre-encoded XMA1",
        )
        self.assertIn(
            "FLAC and MP3 cannot be imported directly",
            browser.audio_replacement_pack_note.text(),
        )
        self.assertIn(
            "not copyright clearance", browser.audio_replacement_pack_note.text()
        )
        self.assertEqual(
            AUDIO_REPLACEMENT_IMPORT_CONFIRMATION_CONTRACT,
            "fully_validated_read_only_preview_then_explicit_apply",
        )
        self.assertIn("Review replacement", browser.import_audio_replacement_pack_button.text())
        self.assertIn("Cancel changes nothing", browser.audio_replacement_pack_note.text())

    def test_settings_round_trip_custom_argv_timeout_and_detect_stale_state(self) -> None:
        browser, _facade, _tasks, _errors = self._browser()
        tool = self._tool()
        configured = ExternalXma1Encoder(
            tool,
            arguments=("--input", "{input}", "--output={output}", "--rate", "{sample_rate}"),
            timeout_seconds=900,
        )
        browser._save_external_xma1_encoder(configured)

        restored = browser._external_xma1_encoder()
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.executable, tool)
        self.assertEqual(restored.arguments, configured.arguments)
        self.assertEqual(restored.timeout_seconds, 900.0)
        browser._update_audio_encoder_status()
        self.assertIn("custom arguments", browser.audio_encoder_status.text())
        self.assertIn("900s timeout", browser.audio_encoder_status.text())

        self.settings.setValue(
            "external_xma1_encoder/arguments_json", "not valid JSON"
        )
        self.settings.sync()
        browser._update_audio_encoder_status()
        self.assertIn("Needs attention", browser.audio_encoder_status.text())
        with self.assertRaisesRegex(ValueError, "malformed"):
            browser._external_xma1_encoder()

        self.settings.setValue(
            "external_xma1_encoder/arguments_json", '["{input}","{output}"]'
        )
        self.settings.sync()
        tool.unlink()
        browser._update_audio_encoder_status()
        self.assertIn("Needs attention", browser.audio_encoder_status.text())
        self.assertIn("Could not open", browser.audio_encoder_status.toolTip())

    def test_advanced_dialog_is_literal_argv_and_unchecked_restores_defaults(self) -> None:
        tool = self._tool()
        dialog = ExternalXma1EncoderDialog(
            encoder_path=tool,
            arguments=("--in", "{input}", "--out", "{output}"),
            timeout_seconds=960,
        )
        try:
            self.assertTrue(dialog.advanced_checkbox.isChecked())
            self.assertIn("not a command line", dialog.arguments_note.text())
            dialog._accept_configuration()
            self.assertEqual(dialog.result(), QDialog.Accepted)
            self.assertEqual(
                dialog.encoder.arguments,
                ("--in", "{input}", "--out", "{output}"),
            )
            self.assertEqual(dialog.encoder.timeout_seconds, 960.0)
        finally:
            sip.delete(dialog)

        default_dialog = ExternalXma1EncoderDialog(
            encoder_path=tool,
            arguments=("--stale", "{input}", "{output}"),
            timeout_seconds=1200,
        )
        try:
            default_dialog.advanced_checkbox.setChecked(False)
            default_dialog._accept_configuration()
            self.assertEqual(default_dialog.result(), QDialog.Accepted)
            self.assertEqual(default_dialog.encoder.arguments, ("{input}", "{output}"))
            self.assertEqual(default_dialog.encoder.timeout_seconds, 600.0)
        finally:
            sip.delete(default_dialog)

        timeout_dialog = ExternalXma1EncoderDialog(
            encoder_path=tool,
            timeout_seconds=900,
        )
        try:
            self.assertTrue(timeout_dialog.advanced_checkbox.isChecked())
            timeout_dialog._accept_configuration()
            self.assertEqual(timeout_dialog.encoder.arguments, ("{input}", "{output}"))
            self.assertEqual(timeout_dialog.encoder.timeout_seconds, 900.0)
        finally:
            sip.delete(timeout_dialog)

    def test_windows_encoder_picker_resolves_detected_wine_symlink(self) -> None:
        encoder_exe = self._tool("fixture-xmaencode.exe")
        real_wine = self._tool("wine-stable")
        wine_link = self.root / "wine"
        wine_link.symlink_to(real_wine)
        dialog = ExternalXma1EncoderDialog()
        try:
            with (
                patch(
                    "mod_editor.apf_studio.gui.QFileDialog.getOpenFileName",
                    return_value=(str(encoder_exe), "Windows XMA1 encoder (*.exe)"),
                ),
                patch(
                    "mod_editor.apf_studio.gui.shutil.which",
                    return_value=str(wine_link),
                ),
            ):
                dialog._browse_encoder()
            self.assertTrue(dialog.use_wine_checkbox.isChecked())
            self.assertEqual(Path(dialog.wine_path.text()), real_wine.resolve())
            dialog._accept_configuration()
            self.assertEqual(dialog.result(), QDialog.Accepted)
            self.assertEqual(dialog.encoder.wine_executable, real_wine.resolve())
        finally:
            sip.delete(dialog)

    def test_template_and_pcm_replace_dispatch_through_exact_slot_facade(self) -> None:
        browser, facade, tasks, errors = self._browser()
        destination = self.root / "fixture-authoring.wav"
        with (
            patch(
                "mod_editor.apf_studio.gui.QFileDialog.getSaveFileName",
                return_value=(str(destination), "PCM16 WAV authoring template (*.wav)"),
            ),
            patch("mod_editor.apf_studio.gui.QMessageBox.information") as information,
        ):
            browser._export_audio_pcm_template()
        self.assertEqual(facade.template_calls[0]["destination"], destination)
        self.assertIn("Exporting exact PCM", tasks[0][0])
        self.assertIn("no retail audio", information.call_args.args[2])

        tool = self._tool()
        browser._save_external_xma1_encoder(
            ExternalXma1Encoder(tool, timeout_seconds=600)
        )
        source = self.root / "authored.wav"
        source.write_bytes(b"synthetic PCM fixture")
        with (
            patch(
                "mod_editor.apf_studio.gui.QFileDialog.getOpenFileName",
                return_value=(str(source), "PCM16 WAV audio (*.wav)"),
            ),
            patch("mod_editor.apf_studio.gui.QMessageBox.information") as information,
        ):
            browser._replace_audio_from_pcm()
        self.assertFalse(errors)
        self.assertEqual(facade.replace_calls[0]["source"], source)
        self.assertTrue(callable(facade.replace_calls[0]["cancel_requested"]))
        self.assertEqual(
            facade.replace_calls[0]["encoder"].timeout_seconds, 600.0  # type: ignore[union-attr]
        )
        self.assertIn("passed the exact allocation", information.call_args.args[2])
        self.assertIn(ROW_ID, facade.modified_asset_ids)

    def test_pack_import_auto_detects_legacy_and_pcm_encoder_requirement(self) -> None:
        browser, facade, tasks, errors = self._browser()

        with (
            patch(
                "mod_editor.apf_studio.gui.QFileDialog.getExistingDirectory",
                return_value=str(self.root / "legacy-pack"),
            ),
            patch(
                "mod_editor.apf_studio.gui.QMessageBox.information"
            ) as information,
            patch(
                "mod_editor.apf_studio.gui.QMessageBox.question",
                return_value=QMessageBox.Apply,
            ) as question,
        ):
            browser._import_audio_replacement_pack()
            self.assertEqual(len(facade.pack_preview_calls), 1)
            self.assertEqual(facade.pack_import_calls, [])
            question.assert_not_called()
            for _index in range(3):
                self.application.processEvents()
        self.assertFalse(errors)
        self.assertIsNone(facade.pack_import_calls[-1]["encoder"])
        self.assertEqual(
            facade.pack_import_calls[-1]["confirmation_token"], "e" * 64
        )
        self.assertIn("Supplied XMA1 files: 1", information.call_args.args[2])
        self.assertIn("Checking APF", tasks[-2][0])
        self.assertIn("Revalidating and applying", tasks[-1][0])
        self.assertIn("Would change: 1", question.call_args.args[2])
        self.assertEqual(question.call_args.args[-1], QMessageBox.Cancel)

        facade.pack_input_kind = "pcm16"
        with (
            patch(
                "mod_editor.apf_studio.gui.QFileDialog.getExistingDirectory",
                return_value=str(self.root / "pcm-pack"),
            ),
            patch("mod_editor.apf_studio.gui.QMessageBox.information"),
        ):
            browser._import_audio_replacement_pack()
        self.assertEqual(len(errors), 1)
        self.assertIn("Configure XMA1 encoder first", str(errors[-1]))
        self.assertIsNone(facade.pack_preview_calls[-1]["encoder"])

        browser._save_external_xma1_encoder(
            ExternalXma1Encoder(self._tool(), timeout_seconds=600)
        )
        errors.clear()
        with (
            patch(
                "mod_editor.apf_studio.gui.QFileDialog.getExistingDirectory",
                return_value=str(self.root / "pcm-pack"),
            ),
            patch(
                "mod_editor.apf_studio.gui.QMessageBox.information"
            ) as information,
            patch(
                "mod_editor.apf_studio.gui.QMessageBox.question",
                return_value=QMessageBox.Apply,
            ),
        ):
            browser._import_audio_replacement_pack()
            for _index in range(3):
                self.application.processEvents()
        self.assertFalse(errors)
        supplied_encoder = facade.pack_import_calls[-1]["encoder"]
        self.assertIsInstance(supplied_encoder, ExternalXma1Encoder)
        self.assertEqual(supplied_encoder.executable, self.root / "fixture-encoder")
        self.assertIn("Supplied PCM16 WAV files: 1", information.call_args.args[2])
        self.assertIn("external encoding checks", information.call_args.args[2])
        self.assertIn("not copyright clearance", information.call_args.args[2])

    def test_pack_preview_cancel_and_unchanged_result_never_stage_an_edit(self) -> None:
        browser, facade, _tasks, errors = self._browser()
        with (
            patch(
                "mod_editor.apf_studio.gui.QFileDialog.getExistingDirectory",
                return_value=str(self.root / "cancelled-pack"),
            ),
            patch(
                "mod_editor.apf_studio.gui.QMessageBox.question",
                return_value=QMessageBox.Cancel,
            ) as question,
            patch("mod_editor.apf_studio.gui.QMessageBox.information"),
        ):
            browser._import_audio_replacement_pack()
            for _index in range(2):
                self.application.processEvents()
        self.assertFalse(errors)
        question.assert_called_once()
        self.assertEqual(facade.pack_import_calls, [])
        self.assertEqual(facade.modified_asset_ids, frozenset())

        facade.pack_would_change = 0
        with (
            patch(
                "mod_editor.apf_studio.gui.QFileDialog.getExistingDirectory",
                return_value=str(self.root / "already-current-pack"),
            ),
            patch(
                "mod_editor.apf_studio.gui.QMessageBox.question"
            ) as unchanged_question,
            patch(
                "mod_editor.apf_studio.gui.QMessageBox.information"
            ) as information,
        ):
            browser._import_audio_replacement_pack()
            for _index in range(2):
                self.application.processEvents()
        unchanged_question.assert_not_called()
        self.assertEqual(facade.pack_import_calls, [])
        self.assertIn("Would change: 0", information.call_args.args[2])
        self.assertIn("Apply is unavailable", information.call_args.args[2])

    def test_cancel_control_reaches_backend_callback_and_stages_no_edit(self) -> None:
        browser, facade, _tasks, errors = self._browser()
        browser._save_external_xma1_encoder(
            ExternalXma1Encoder(self._tool(), timeout_seconds=600)
        )
        source = self.root / "authored.wav"
        source.write_bytes(b"synthetic PCM fixture")
        def request_cancel() -> None:
            self.assertFalse(browser.cancel_pcm_encoding_button.isHidden())
            self.assertTrue(browser.cancel_pcm_encoding_button.isEnabled())
            browser._cancel_running_pcm_encoding()
            self.assertFalse(browser.cancel_pcm_encoding_button.isEnabled())

        facade.cancel_hook = request_cancel
        with (
            patch(
                "mod_editor.apf_studio.gui.QFileDialog.getOpenFileName",
                return_value=(str(source), "PCM16 WAV audio (*.wav)"),
            ),
            patch("mod_editor.apf_studio.gui.QMessageBox.information"),
        ):
            browser._replace_audio_from_pcm()
        self.assertEqual(len(errors), 1)
        self.assertTrue(facade.replace_calls[0]["cancel_observed"])
        self.assertNotIn(ROW_ID, facade.modified_asset_ids)
        self.assertFalse(browser._pcm_encoding_running)
        self.assertFalse(browser._pcm_encoding_cancel.is_set())
        self.assertFalse(browser.cancel_pcm_encoding_button.isEnabled())
        self.assertTrue(browser.cancel_pcm_encoding_button.isHidden())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

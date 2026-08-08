from __future__ import annotations

from array import array
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import wave


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import sip  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.apf_studio.gui import InspectorBrowser  # noqa: E402
from mod_editor.apf_studio.inspectors import (  # noqa: E402
    ExportIdentity,
    PagedModel,
    _row,
)
from mod_editor.apf_studio.models import (  # noqa: E402
    ExternalAudioBankIdentity,
    ExternalAudioBankOwner,
)
from mod_editor.gui.apf_audio_waveform_qt import (  # noqa: E402
    AudioWaveformPreview,
    WaveformCancelled,
    WaveformRequest,
    read_pcm16_waveform,
)


def _write_pcm16(path: Path, *, channels: int = 1, frames: int = 4096) -> None:
    samples = array("h")
    for frame in range(frames):
        for channel in range(channels):
            magnitude = 24_000 if (frame // 64 + channel) % 2 else -18_000
            samples.append(magnitude)
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(2)
        writer.setframerate(48_000)
        writer.writeframes(samples.tobytes())


def _playable_row(index: int, *, kind: str = "audo") -> object:
    substream = index if kind == "ausb_substream" else None
    return _row(
        f"apf:audio:{kind}:{index}",
        kind,
        f"sound_{index:03d}",
        "fixture sound",
        {
            "outer_table_index": 5,
            "inner_file_index": index,
            "substream_index": substream,
            "audio_source_id": "audo:standalone",
            "audio_source_label": "Standalone AUDO",
            "role_id": "ui_menu_sfx",
            "role_label": "UI & Menu SFX",
            "sample_rate": 48_000,
            "derived_channel_count": 1,
            "duration_seconds": 1.0,
        },
        export_identity=ExportIdentity(
            kind,
            5,
            index,
            substream,
            f"sound-{index:03d}",
        ),
    )


class WaveformReaderTests(unittest.TestCase):
    def test_pcm16_reader_is_bounded_and_retains_channel_envelopes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "private.wav"
            _write_pcm16(source, channels=2, frames=48_000)
            before = source.stat()
            envelope = read_pcm16_waveform(
                source,
                max_points=128,
                frames_per_point=256,
            )
            after = source.stat()

        self.assertEqual(envelope.channel_count, 2)
        self.assertEqual(envelope.point_count, 128)
        self.assertEqual(envelope.frame_count, 48_000)
        self.assertEqual(envelope.sample_rate, 48_000)
        self.assertLessEqual(envelope.sampled_frame_count, 128 * 256)
        self.assertTrue(all(low < 0 < high for low, high in envelope.channel_peaks[0]))
        self.assertEqual(
            (before.st_size, before.st_mtime_ns),
            (after.st_size, after.st_mtime_ns),
        )

    def test_reader_rejects_links_and_non_pcm16(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pcm = root / "private.wav"
            _write_pcm16(pcm)
            link = root / "linked.wav"
            link.symlink_to(pcm)
            with self.assertRaisesRegex(ValueError, "non-link"):
                read_pcm16_waveform(link)

            pcm8 = root / "eight-bit.wav"
            with wave.open(str(pcm8), "wb") as writer:
                writer.setnchannels(1)
                writer.setsampwidth(1)
                writer.setframerate(8_000)
                writer.writeframes(bytes([128]) * 800)
            with self.assertRaisesRegex(ValueError, "PCM16"):
                read_pcm16_waveform(pcm8)

    def test_reader_honors_cooperative_cancellation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "private.wav"
            _write_pcm16(source)
            request = WaveformRequest()
            request.cancel()
            with self.assertRaises(WaveformCancelled):
                read_pcm16_waveform(source, cancelled=lambda: request.cancelled)


class WaveformWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.application.quit()
        sip.delete(cls.application)
        cls.application = None

    def test_widget_states_contain_no_path_or_audio_bytes(self) -> None:
        widget = AudioWaveformPreview()
        try:
            widget.set_error("fixture decode failed")
            self.assertEqual(widget.state, "error")
            self.assertIn("fixture decode", widget.toolTip())
            with tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "private.wav"
                _write_pcm16(source, frames=256)
                envelope = read_pcm16_waveform(source, max_points=64)
            widget.set_envelope(envelope)
            self.assertEqual(widget.state, "ready")
            self.assertNotIn("private.wav", widget.toolTip())
            self.assertIn("does not play automatically", widget.toolTip())
        finally:
            widget.deleteLater()
            self.application.processEvents()

    def test_browser_loads_only_on_click_and_never_autoplays_or_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            wav = Path(directory) / "private.wav"
            _write_pcm16(wav, frames=1024)
            calls: list[ExportIdentity] = []
            queued: dict[str, object] = {}

            callbacks: list[object] = []

            def prepare(
                identity: ExportIdentity,
                _progress: object,
                *,
                cancel_requested: object,
            ) -> Path:
                calls.append(identity)
                callbacks.append(cancel_requested)
                return wav

            def run_task(
                title: str, operation: object, complete: object, blocking: bool
            ) -> None:
                queued.update(
                    title=title,
                    operation=operation,
                    complete=complete,
                    blocking=blocking,
                )

            browser = InspectorBrowser(
                "Complete audio",
                SimpleNamespace(prepare_audio_preview=prepare),
                run_task,
                audio_mode=True,
            )
            try:
                browser.set_model(PagedModel((_playable_row(1),)), "fixture")
                self.assertEqual(calls, [])
                self.assertEqual(browser.waveform_preview.state, "empty")
                self.assertTrue(browser.load_waveform_button.isEnabled())
                self.assertEqual(browser.play_audio_button.text(), "Play")

                browser.load_waveform_button.click()
                self.assertEqual(calls, [])
                self.assertFalse(bool(queued["blocking"]))
                result = queued["operation"](lambda *_args: None)  # type: ignore[operator]
                self.assertEqual(len(calls), 1)
                self.assertFalse(callbacks[0]())  # type: ignore[operator]
                self.assertEqual(browser.play_audio_button.text(), "Play")
                queued["complete"](result)  # type: ignore[operator]
                self.assertEqual(browser.waveform_preview.state, "ready")
                self.assertEqual(browser.load_waveform_button.text(), "Reload waveform")
                self.assertEqual(browser.play_audio_button.text(), "Play")
            finally:
                browser.deleteLater()
                self.application.processEvents()

    def test_stale_result_is_discarded_after_fast_selection_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            wav = Path(directory) / "private.wav"
            _write_pcm16(wav, frames=1024)
            queued: dict[str, object] = {}
            callbacks: list[object] = []

            def prepare(
                _identity: object,
                _progress: object,
                *,
                cancel_requested: object,
            ) -> Path:
                callbacks.append(cancel_requested)
                return wav

            def run_task(
                _title: str, operation: object, complete: object, _blocking: bool
            ) -> None:
                queued.update(operation=operation, complete=complete)

            browser = InspectorBrowser(
                "Complete audio",
                SimpleNamespace(prepare_audio_preview=prepare),
                run_task,
                audio_mode=True,
            )
            try:
                browser.set_model(
                    PagedModel((_playable_row(1), _playable_row(2))), "fixture"
                )
                browser.load_waveform_button.click()
                result = queued["operation"](lambda *_args: None)  # type: ignore[operator]
                browser.table.selectRow(1)
                self.application.processEvents()
                self.assertTrue(callbacks[0]())  # type: ignore[operator]
                queued["complete"](result)  # type: ignore[operator]

                self.assertEqual(browser._selected_row().row_id, "apf:audio:audo:2")
                self.assertIsNone(browser.waveform_preview.envelope)
                self.assertEqual(browser.waveform_preview.state, "empty")
                self.assertTrue(browser.load_waveform_button.isEnabled())
            finally:
                browser.deleteLater()
                self.application.processEvents()

    def test_waveform_button_cancels_pending_decode_and_is_retryable(self) -> None:
        queued: dict[str, object] = {}

        def run_task(
            _title: str, operation: object, complete: object, _blocking: bool
        ) -> None:
            queued.update(operation=operation, complete=complete)

        browser = InspectorBrowser(
            "Complete audio",
            SimpleNamespace(
                prepare_audio_preview=lambda *_args, **_kwargs: Path("unused.wav")
            ),
            run_task,
            audio_mode=True,
        )
        try:
            browser.set_model(PagedModel((_playable_row(1),)), "fixture")
            browser.load_waveform_button.click()
            self.assertEqual(browser.load_waveform_button.text(), "Cancel waveform")
            self.assertTrue(browser.load_waveform_button.isEnabled())

            browser.load_waveform_button.click()
            self.assertEqual(browser.load_waveform_button.text(), "Cancelling…")
            # Never silent-gray during cancel: stay enabled with explain tip.
            self.assertTrue(browser.load_waveform_button.isEnabled())
            self.assertTrue(
                str(browser.load_waveform_button.property("disableReason") or "").strip()
            )
            result = queued["operation"](lambda *_args: None)  # type: ignore[operator]
            self.assertEqual(result, ("cancelled", None))
            queued["complete"](result)  # type: ignore[operator]
            self.assertEqual(browser.load_waveform_button.text(), "Load waveform")
            self.assertTrue(browser.load_waveform_button.isEnabled())
            self.assertEqual(browser.waveform_preview.state, "empty")
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_decode_failure_is_shown_inline_and_can_retry(self) -> None:
        queued: dict[str, object] = {}

        def run_task(
            _title: str, operation: object, complete: object, _blocking: bool
        ) -> None:
            queued.update(operation=operation, complete=complete)

        def fail(
            _identity: object,
            _progress: object,
            *,
            cancel_requested: object,
        ) -> Path:
            self.assertFalse(cancel_requested())  # type: ignore[operator]
            raise ValueError("fixture XMA decoder rejected this cue")

        browser = InspectorBrowser(
            "Complete audio",
            SimpleNamespace(prepare_audio_preview=fail),
            run_task,
            audio_mode=True,
        )
        try:
            browser.set_model(PagedModel((_playable_row(1),)), "fixture")
            browser.load_waveform_button.click()
            result = queued["operation"](lambda *_args: None)  # type: ignore[operator]
            queued["complete"](result)  # type: ignore[operator]
            self.assertEqual(browser.waveform_preview.state, "error")
            self.assertIn("decoder rejected", browser.waveform_preview.toolTip())
            self.assertEqual(browser.load_waveform_button.text(), "Retry waveform")
            self.assertTrue(browser.load_waveform_button.isEnabled())
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_physical_external_bank_never_offers_waveform(self) -> None:
        owner = ExternalAudioBankOwner(
            descriptor_outer_index=1310,
            descriptor_inner_index=143,
            bank_name="lines",
            substream_count=1,
            sample_rate=22_050,
            channel_count=1,
        )
        identity = ExternalAudioBankIdentity(
            external_filename="lines.bin",
            outer_table_index=579,
            name_id=0x12345678,
            encoded_size=1024,
            owners=(owner,),
        )
        external = _row(
            "apf:audio:external:579",
            "external_bank",
            "lines.bin",
            "physical bank",
            {
                "outer_table_index": 579,
                "external_filename": "lines.bin",
                "encoded_size": 1024,
            },
            external_bank_identity=identity,
        )
        browser = InspectorBrowser(
            "Complete audio",
            object(),  # type: ignore[arg-type]
            lambda *_args: None,
            audio_mode=True,
        )
        try:
            browser.set_model(PagedModel((external,)), "fixture")
            # Never silent-gray: clickable + disableReason teaches substream pick.
            self.assertTrue(browser.load_waveform_button.isEnabled())
            self.assertIn(
                "substream",
                str(browser.load_waveform_button.property("disableReason") or "").casefold(),
            )
            self.assertEqual(browser.waveform_preview.state, "unavailable")
            self.assertIn("physical external bank", browser.waveform_preview.toolTip())
            self.assertFalse(browser.play_audio_button.isVisibleTo(browser))
        finally:
            browser.deleteLater()
            self.application.processEvents()


if __name__ == "__main__":
    unittest.main()

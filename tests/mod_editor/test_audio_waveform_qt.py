"""Retail-free tests for the shared PCM waveform and 2K5 Audio panel route."""

from __future__ import annotations

from array import array
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.core.nfl2k5_audio_catalog import Nfl2k5AudioService  # noqa: E402
from mod_editor.gui.audio_panel_qt import (  # noqa: E402
    AudioPanel,
    CatalogAudioPanelHost,
)
from mod_editor.gui.audio_waveform_qt import (  # noqa: E402
    WaveformCancelled,
    WaveformRequest,
    read_pcm16_waveform,
)
from tests.mod_editor.test_nfl2k5_audio_catalog import AudioFixture  # noqa: E402


def _write_pcm16(
    path: Path,
    *,
    channels: int = 1,
    frames: int = 4096,
) -> Path:
    samples = array("h")
    for frame in range(frames):
        for channel in range(channels):
            samples.append(
                24_000 if (frame // 64 + channel) % 2 else -18_000
            )
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(2)
        writer.setframerate(48_000)
        writer.writeframes(samples.tobytes())
    return path


class WaveformReaderTests(unittest.TestCase):
    def test_reader_is_bounded_read_only_and_keeps_channel_envelopes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = _write_pcm16(
                Path(directory) / "private.wav",
                channels=2,
                frames=48_000,
            )
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
        self.assertTrue(
            all(low < 0 < high for low, high in envelope.channel_peaks[0])
        )
        self.assertEqual(
            (before.st_size, before.st_mtime_ns),
            (after.st_size, after.st_mtime_ns),
        )

    def test_reader_rejects_links_and_honors_cooperative_cancellation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _write_pcm16(root / "private.wav")
            link = root / "linked.wav"
            link.symlink_to(source)
            with self.assertRaisesRegex(ValueError, "non-link"):
                read_pcm16_waveform(link)

            request = WaveformRequest()
            request.cancel()
            with self.assertRaises(WaveformCancelled):
                read_pcm16_waveform(
                    source,
                    cancelled=lambda: request.cancelled,
                )

    def test_full_scale_negative_bucket_stays_inside_normalized_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "negative-full-scale.wav"
            samples = array("h", [-32768] * 64)
            with wave.open(str(source), "wb") as writer:
                writer.setnchannels(1)
                writer.setsampwidth(2)
                writer.setframerate(48_000)
                writer.writeframes(samples.tobytes())

            envelope = read_pcm16_waveform(
                source,
                max_points=16,
                frames_per_point=64,
            )

        self.assertTrue(
            all(low == -1.0 and high == -1.0 for low, high in envelope.channel_peaks[0])
        )


class Nfl2k5AudioWaveformPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def _panel(
        self,
        root: Path,
        *,
        page_size: int = 2,
    ) -> tuple[AudioPanel, CatalogAudioPanelHost]:
        source_root = root / "source"
        source_root.mkdir()
        fixture = AudioFixture(source_root)
        catalog = fixture.catalog()
        service = Nfl2k5AudioService(fixture.cache, catalog)
        host = CatalogAudioPanelHost(
            catalog,
            service,
            root / "user-replacements",
        )
        return AudioPanel(host, page_size=page_size), host

    def test_load_is_explicit_never_autoplays_and_never_mutates_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wav = _write_pcm16(root / "private.wav", frames=2048)
            panel, host = self._panel(root)
            queued: dict[str, object] = {}
            prepare_calls: list[str] = []

            def prepare(asset_id: str, _progress: object) -> Path:
                prepare_calls.append(asset_id)
                return wav

            def queue(
                operation: object,
                complete: object,
                **_kwargs: object,
            ) -> None:
                queued.update(operation=operation, complete=complete)

            host.prepare_audio = prepare  # type: ignore[method-assign]
            panel._run = queue  # type: ignore[method-assign]
            try:
                before = host.modified_audio_asset_ids
                self.assertEqual(panel.waveform_preview.state, "empty")
                self.assertTrue(panel.load_waveform_button.isEnabled())
                self.assertEqual(prepare_calls, [])
                with patch.object(panel._audio_process, "start") as autoplay:
                    panel.load_waveform_button.click()
                    self.assertEqual(prepare_calls, [])
                    result = queued["operation"](  # type: ignore[operator]
                        lambda *_args: None
                    )
                    self.assertEqual(prepare_calls, [panel.selected_asset_id])
                    queued["complete"](result)  # type: ignore[operator]
                    autoplay.assert_not_called()

                self.assertEqual(panel.waveform_preview.state, "ready")
                self.assertEqual(
                    panel.load_waveform_button.text(), "Reload waveform"
                )
                self.assertEqual(panel.play_button.text(), "Play")
                self.assertEqual(host.modified_audio_asset_ids, before)
                self.assertFalse((root / "user-replacements").exists())
                self.assertIn(
                    "does not play automatically",
                    panel.waveform_preview.toolTip(),
                )
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_fast_selection_change_cancels_and_discards_stale_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wav = _write_pcm16(root / "private.wav", frames=1024)
            panel, host = self._panel(root)
            queued: dict[str, object] = {}
            host.prepare_audio = (  # type: ignore[method-assign]
                lambda _asset_id, _progress: wav
            )
            panel._run = (  # type: ignore[method-assign]
                lambda operation, complete, **_kwargs: queued.update(
                    operation=operation,
                    complete=complete,
                )
            )
            try:
                first_id = panel.selected_asset_id
                panel.load_waveform_button.click()
                result = queued["operation"](  # type: ignore[operator]
                    lambda *_args: None
                )
                panel.table.selectRow(1)
                self.application.processEvents()
                self.assertNotEqual(panel.selected_asset_id, first_id)
                queued["complete"](result)  # type: ignore[operator]

                self.assertIsNone(panel.waveform_preview.envelope)
                self.assertEqual(panel.waveform_preview.state, "empty")
                self.assertTrue(panel.load_waveform_button.isEnabled())
                self.assertEqual(host.modified_audio_asset_ids, ())
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_cancel_is_retryable_and_source_decode_limit_is_explained(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            panel, host = self._panel(root)
            queued: dict[str, object] = {}
            panel._run = (  # type: ignore[method-assign]
                lambda operation, complete, **_kwargs: queued.update(
                    operation=operation,
                    complete=complete,
                )
            )
            try:
                panel.load_waveform_button.click()
                self.assertEqual(
                    panel.load_waveform_button.text(), "Cancel waveform"
                )
                self.assertIn(
                    "cannot be interrupted",
                    panel.waveform_preview.toolTip()
                    + panel.load_waveform_button.toolTip(),
                )
                panel.load_waveform_button.click()
                self.assertEqual(
                    panel.load_waveform_button.text(), "Cancelling…"
                )
                result = queued["operation"](  # type: ignore[operator]
                    lambda *_args: None
                )
                self.assertEqual(result, ("cancelled", None))
                queued["complete"](result)  # type: ignore[operator]
                self.assertEqual(
                    panel.load_waveform_button.text(), "Load waveform"
                )
                self.assertTrue(panel.load_waveform_button.isEnabled())
                self.assertEqual(panel.waveform_preview.state, "empty")
                self.assertEqual(host.modified_audio_asset_ids, ())
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_unplayable_bank_and_decode_failure_are_explained_inline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            panel, host = self._panel(root, page_size=1)
            queued: dict[str, object] = {}
            try:
                panel.scope_filter.setCurrentIndex(
                    panel.scope_filter.findData("streaming")
                )
                self.application.processEvents()
                self.assertEqual(panel.waveform_preview.state, "unavailable")
                self.assertIn(
                    "complete streaming bank",
                    panel.waveform_preview.toolTip().casefold(),
                )
                # Never silent-gray: Load waveform stays clickable and teaches bank wall.
                self.assertTrue(panel.load_waveform_button.isEnabled())
                self.assertTrue(
                    str(
                        panel.load_waveform_button.property("disableReason") or ""
                    ).strip()
                    or "bank" in panel.load_waveform_button.toolTip().casefold()
                )

                panel.scope_filter.setCurrentIndex(
                    panel.scope_filter.findData("standalone")
                )
                self.application.processEvents()

                def fail(_asset_id: str, _progress: object) -> Path:
                    raise ValueError("fixture PCM route rejected this sound")

                host.prepare_audio = fail  # type: ignore[method-assign]
                panel._run = (  # type: ignore[method-assign]
                    lambda operation, complete, **_kwargs: queued.update(
                        operation=operation,
                        complete=complete,
                    )
                )
                panel.load_waveform_button.click()
                result = queued["operation"](  # type: ignore[operator]
                    lambda *_args: None
                )
                queued["complete"](result)  # type: ignore[operator]
                self.assertEqual(panel.waveform_preview.state, "error")
                self.assertIn("PCM route rejected", panel.waveform_preview.toolTip())
                self.assertEqual(
                    panel.load_waveform_button.text(), "Retry waveform"
                )
                self.assertEqual(host.modified_audio_asset_ids, ())
            finally:
                panel.deleteLater()
                self.application.processEvents()


if __name__ == "__main__":
    unittest.main()

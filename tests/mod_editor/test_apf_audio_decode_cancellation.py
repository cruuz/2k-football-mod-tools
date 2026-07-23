from __future__ import annotations

from pathlib import Path
import stat
import struct
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import apf_audio  # noqa: E402
import apf_audo_exact_slot  # noqa: E402
import apf_ausb_audio  # noqa: E402
import apf_ausb_exact_slot  # noqa: E402


def _packet_payload() -> bytes:
    packet = bytearray(apf_audio.XMA_PACKET_SIZE)
    struct.pack_into(">I", packet, 0, 0x08000000)
    packet[4:] = bytes((index % 251) + 1 for index in range(len(packet) - 4))
    return bytes(packet)


class DecoderCancellationTests(unittest.TestCase):
    def test_callback_exception_becomes_clear_audio_error(self) -> None:
        calls = 0

        def broken_callback() -> bool:
            nonlocal calls
            calls += 1
            if calls > 1:
                raise RuntimeError("synthetic callback failure")
            return False

        started = time.monotonic()
        with self.assertRaisesRegex(
            apf_audio.AudioError, "synthetic callback failure"
        ):
            apf_audio.run_cancellable_subprocess(
                [sys.executable, "-c", "import time; time.sleep(60)"],
                cancel_requested=broken_callback,
            )
        self.assertLess(time.monotonic() - started, 3.0)

    def test_cancellable_runner_timeout_stops_term_resistant_process(self) -> None:
        started = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            apf_audio.run_cancellable_subprocess(
                [
                    sys.executable,
                    "-c",
                    "import signal, time; "
                    "signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)",
                ],
                cancel_requested=lambda: False,
                timeout_seconds=0.2,
            )
        self.assertLess(time.monotonic() - started, 3.0)

    def test_cancel_stops_detached_stdio_helper_in_same_process_group(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            marker = Path(directory_name) / "helper.pid"
            program = (
                "import pathlib, signal, subprocess, sys, time; "
                "child=subprocess.Popen([sys.executable, '-c', "
                "'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                "time.sleep(60)'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
                "stderr=subprocess.DEVNULL); "
                f"pathlib.Path({str(marker)!r}).write_text(str(child.pid)); "
                "time.sleep(60)"
            )
            started = time.monotonic()
            with self.assertRaises(apf_audio.AudioCancelled):
                apf_audio.run_cancellable_subprocess(
                    [sys.executable, "-c", program],
                    cancel_requested=marker.exists,
                )
            self.assertLess(time.monotonic() - started, 3.0)
            helper_pid = int(marker.read_text(encoding="ascii"))
            status = Path(f"/proc/{helper_pid}/stat")
            deadline = time.monotonic() + 1.0
            while status.exists() and time.monotonic() < deadline:
                fields = status.read_text(encoding="ascii").split()
                if len(fields) > 2 and fields[2] == "Z":
                    break
                time.sleep(0.02)
            if status.exists():
                self.assertEqual(status.read_text(encoding="ascii").split()[2], "Z")

    def test_cancellable_stock_export_publishes_nothing_after_cancel(self) -> None:
        calls = 0

        def cancel_requested() -> bool:
            nonlocal calls
            calls += 1
            return calls >= 2

        def staged_export(
            _index: Path,
            _outer: int,
            _inner: int,
            xma: Path,
            wav: Path | None,
            _maximum: int,
            **_kwargs: object,
        ) -> dict[str, object]:
            xma.write_bytes(b"complete xma")
            assert wav is not None
            wav.write_bytes(b"complete wav")
            return {
                "xma": {"path": str(xma)},
                "wav": {"path": str(wav), "status": "decoder_verified"},
            }

        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            xma = directory / "published.xma"
            wav = directory / "published.wav"
            with (
                mock.patch.object(
                    apf_audio, "_export_selected_impl", side_effect=staged_export
                ),
                self.assertRaises(apf_audio.AudioCancelled),
            ):
                apf_audio.export_selected(
                    Path("0A"),
                    1,
                    2,
                    xma,
                    wav,
                    1024,
                    cancel_requested=cancel_requested,
                )
            self.assertFalse(xma.exists())
            self.assertFalse(wav.exists())

    def test_exact_slot_cancel_kills_decoder_group_and_removes_partial_wav(self) -> None:
        payload = _packet_payload()
        target = apf_audo_exact_slot.ExactSlotTarget(
            channels=2,
            sample_rate=48_000,
            encoded_size=len(payload),
            declared_sample_count=512,
            loop_start_bit=32,
            loop_end_bit=len(payload) * 8 - 32,
            loop_subframe=3,
        )
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            marker = directory / "decoder-ready.txt"
            fake_ffmpeg = directory / "fake-ffmpeg"
            fake_ffmpeg.write_text(
                "#!/usr/bin/env python3\n"
                "import os, pathlib, subprocess, sys, time\n"
                f"marker = pathlib.Path({str(marker)!r})\n"
                "output = pathlib.Path(sys.argv[-1])\n"
                "output.write_bytes(b'partial pcm')\n"
                "child = subprocess.Popen([sys.executable, '-c', "
                "'import time; time.sleep(60)'])\n"
                "marker.write_text(f'{os.getpid()} {child.pid}', encoding='ascii')\n"
                "time.sleep(60)\n",
                encoding="utf-8",
            )
            fake_ffmpeg.chmod(
                fake_ffmpeg.stat().st_mode
                | stat.S_IXUSR
                | stat.S_IXGRP
                | stat.S_IXOTH
            )
            destination = directory / "preview.wav"

            started = time.monotonic()
            with self.assertRaises(apf_audio.AudioCancelled):
                apf_audo_exact_slot.decode_stored_payload_to_wav(
                    payload,
                    target,
                    destination,
                    ffmpeg_path=fake_ffmpeg,
                    cancel_requested=marker.exists,
                )
            self.assertLess(time.monotonic() - started, 3.0)
            self.assertTrue(marker.is_file())
            self.assertFalse(destination.exists())
            self.assertEqual(
                sorted(path.name for path in directory.iterdir()),
                ["decoder-ready.txt", "fake-ffmpeg"],
            )

    def test_ausb_exact_slot_preserves_same_cancellation_class(self) -> None:
        cancellation = apf_audio.AudioCancelled("synthetic cancellation")

        def cancel_requested() -> bool:
            return False

        fingerprints = SimpleNamespace(payload_sha256s=frozenset())
        with (
            mock.patch.object(apf_ausb_exact_slot, "reject_source_audio_reuse"),
            mock.patch.object(
                apf_ausb_exact_slot,
                "validate_stored_payload",
                return_value=b"user packets",
            ),
            mock.patch.object(
                apf_ausb_exact_slot,
                "_audo_target",
                return_value=SimpleNamespace(),
            ),
            mock.patch.object(
                apf_audo_exact_slot,
                "decode_stored_payload_to_wav",
                side_effect=cancellation,
            ) as nested,
            self.assertRaises(apf_audio.AudioCancelled) as raised,
        ):
            apf_ausb_exact_slot.decode_stored_payload_to_wav(
                b"user packets",
                SimpleNamespace(target=SimpleNamespace()),
                fingerprints,
                Path("preview.wav"),
                cancel_requested=cancel_requested,
            )
        self.assertIs(raised.exception, cancellation)
        self.assertIs(nested.call_args.kwargs["cancel_requested"], cancel_requested)

    def test_audo_and_ausb_default_exports_keep_legacy_direct_path(self) -> None:
        audo_result = {"xma": {}, "wav": None}
        ausb_result = {"xma": {}, "wav": None}
        with (
            mock.patch.object(
                apf_audio, "_export_selected_impl", return_value=audo_result
            ) as audo,
            mock.patch.object(
                apf_ausb_audio,
                "_export_substream_impl",
                return_value=ausb_result,
            ) as ausb,
        ):
            self.assertIs(
                apf_audio.export_selected(
                    Path("0A"), 1, 2, Path("sound.xma"), None, 1024
                ),
                audo_result,
            )
            self.assertIs(
                apf_ausb_audio.export_substream(
                    Path("0A"), 1, 2, 3, Path("sound.xma"), None, 1024
                ),
                ausb_result,
            )
        self.assertNotIn("cancel_requested", audo.call_args.kwargs)
        self.assertNotIn("cancel_requested", ausb.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()

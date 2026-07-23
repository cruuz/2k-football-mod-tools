"""Focused hostile tests for the user-supplied APF XMA1 encoder bridge."""

from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import time
import tempfile
import unittest
from unittest.mock import patch

from mod_editor.apf_studio.audio_encoding import (
    AudioEncodingCancelled,
    AudioEncodingError,
    ExternalXma1Encoder,
    Pcm16Target,
    export_pcm16_template,
)


def _riff_chunks(data: bytes) -> dict[bytes, bytes]:
    chunks: dict[bytes, bytes] = {}
    cursor = 12
    while cursor < len(data):
        name = data[cursor : cursor + 4]
        size = struct.unpack_from("<I", data, cursor + 4)[0]
        start = cursor + 8
        chunks[name] = data[start : start + size]
        cursor = start + size + (size & 1)
    return chunks


def _wait_pid_gone(pid: int, timeout_seconds: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.02)
    return False


class ApfAudioEncodingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="apf-audio-encoding-")
        self.root = Path(self.temporary.name)
        self.target = Pcm16Target(
            channels=2,
            sample_rate=48_000,
            frame_count=8,
            encoded_size=0x800,
        )
        self.source = self.root / "authored.wav"
        export_pcm16_template(self.source, self.target)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _script(self, name: str, body: str) -> Path:
        path = self.root / name
        path.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
        path.chmod(0o700)
        return path

    def _copy_encoder(self) -> Path:
        return self._script(
            "copy-encoder",
            "import shutil, sys\nshutil.copyfile(sys.argv[1], sys.argv[2])\n",
        )

    def test_template_is_exact_deterministic_silence_and_retail_free(self) -> None:
        first = self.source.read_bytes()
        second_path = self.root / "second.wav"
        second = export_pcm16_template(second_path, self.target)
        self.assertEqual(first, second_path.read_bytes())
        self.assertEqual(second.byte_size, 44 + self.target.data_size)
        self.assertEqual(second.encoded_size, 0x800)
        self.assertEqual(second.schema, "apf2k8_audio_pcm16_template/v1")
        self.assertFalse(second.contains_retail_audio)
        self.assertEqual(first[:4], b"RIFF")
        self.assertEqual(struct.unpack_from("<I", first, 4)[0], len(first) - 8)
        self.assertEqual(first[8:12], b"WAVE")
        chunks = _riff_chunks(first)
        self.assertEqual(set(chunks), {b"fmt ", b"data"})
        self.assertEqual(chunks[b"data"], b"\0" * self.target.data_size)
        self.assertEqual(
            struct.unpack("<HHIIHH", chunks[b"fmt "]),
            (1, 2, 48_000, 192_000, 4, 16),
        )

    def test_template_refuses_overwrite_and_cancel_leaves_no_file(self) -> None:
        with self.assertRaisesRegex(AudioEncodingError, "already exists"):
            export_pcm16_template(self.source, self.target)
        cancelled = self.root / "cancelled.wav"
        with self.assertRaises(AudioEncodingCancelled):
            export_pcm16_template(
                cancelled,
                self.target,
                cancel_requested=lambda: True,
            )
        self.assertFalse(cancelled.exists())
        self.assertFalse(tuple(self.root.glob(".cancelled.wav.*")))

    def test_direct_encoder_receives_argv_not_a_shell_and_returns_private_bytes(self) -> None:
        marker = self.root / "shell-was-used"
        encoder = ExternalXma1Encoder(
            self._copy_encoder(),
            arguments=("{input}", "{output}", f";touch {marker}"),
        )
        result = encoder.encode(self.source, self.target)
        self.assertEqual(result.xma1_riff, self.source.read_bytes())
        self.assertFalse(marker.exists())
        self.assertTrue(result.receipt["no_shell"])
        self.assertFalse(result.receipt["encoder_binary_bundled"])
        self.assertFalse(result.receipt["bridge_reads_loaded_game"])
        self.assertFalse(result.receipt["bridge_passes_loaded_game_path"])
        self.assertTrue(result.receipt["encoder_input_is_user_selected_pcm"])
        self.assertFalse(result.receipt["input_audio_content_classified"])
        self.assertEqual(result.receipt["retail_audio_classification"], "not_evaluated")
        self.assertNotIn("contains_retail_audio", result.receipt)
        receipt_text = json.dumps(result.receipt, sort_keys=True)
        self.assertNotIn(str(self.root), receipt_text)
        self.assertNotIn("copy-encoder", receipt_text)

    def test_pcm_with_ancillary_chunk_is_canonicalized_before_encoding(self) -> None:
        original = self.source.read_bytes()
        fmt = _riff_chunks(original)[b"fmt "]
        payload = _riff_chunks(original)[b"data"]
        body = (
            b"WAVE"
            + b"JUNK"
            + struct.pack("<I", 3)
            + b"abc\0"
            + b"fmt "
            + struct.pack("<I", len(fmt))
            + fmt
            + b"data"
            + struct.pack("<I", len(payload))
            + payload
        )
        source = self.root / "with-junk.wav"
        source.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
        result = ExternalXma1Encoder(self._copy_encoder()).encode(source, self.target)
        self.assertEqual(result.xma1_riff, original)
        self.assertNotIn(b"JUNK", result.xma1_riff)

    def test_wine_mode_uses_user_exe_as_a_plain_argument(self) -> None:
        encoder_exe = self.root / "xmaencode.exe"
        encoder_exe.write_bytes(b"MZ synthetic user tool")
        wine = self._script(
            "wine-loader",
            "import shutil, sys\n"
            "assert sys.argv[1].endswith('.exe')\n"
            "assert sys.argv[2].startswith('Z:\\\\')\n"
            "assert sys.argv[3].startswith('Z:\\\\')\n"
            "source = sys.argv[2][2:].replace('\\\\', '/')\n"
            "target = sys.argv[3][2:].replace('\\\\', '/')\n"
            "shutil.copyfile(source, target)\n",
        )
        adapter = ExternalXma1Encoder(
            encoder_exe,
            wine_executable=wine,
        )
        self.assertEqual(adapter.validate()["mode"], "wine")
        result = adapter.encode(self.source, self.target)
        self.assertEqual(result.xma1_riff, self.source.read_bytes())
        self.assertEqual(result.receipt["mode"], "wine")

    def test_successful_encoder_parent_cannot_leave_background_child(self) -> None:
        pid_file = self.root / "background-child.pid"
        encoder = self._script(
            "background-child-encoder",
            "import pathlib, shutil, subprocess, sys\n"
            "child = subprocess.Popen(['sleep', '17'])\n"
            "pathlib.Path(sys.argv[3]).write_text(str(child.pid), encoding='ascii')\n"
            "shutil.copyfile(sys.argv[1], sys.argv[2])\n",
        )
        result = ExternalXma1Encoder(
            encoder,
            arguments=("{input}", "{output}", str(pid_file)),
        ).encode(self.source, self.target)
        self.assertEqual(result.xma1_riff, self.source.read_bytes())
        background_pid = int(pid_file.read_text(encoding="ascii"))
        self.assertTrue(
            _wait_pid_gone(background_pid),
            f"background encoder child {background_pid} survived encode()",
        )

    def test_encoder_and_wine_links_are_rejected(self) -> None:
        real = self._copy_encoder()
        linked = self.root / "linked-encoder"
        linked.symlink_to(real)
        with self.assertRaisesRegex(AudioEncodingError, "regular file, not a link"):
            ExternalXma1Encoder(linked).validate()

        exe = self.root / "tool.exe"
        exe.write_bytes(b"MZ")
        wine_link = self.root / "wine"
        wine_link.symlink_to(real)
        with self.assertRaisesRegex(AudioEncodingError, "regular file, not a link"):
            ExternalXma1Encoder(exe, wine_executable=wine_link).validate()

    def test_direct_encoder_must_be_executable_and_exe_requires_wine(self) -> None:
        plain = self.root / "not-executable"
        plain.write_bytes(b"tool")
        with self.assertRaisesRegex(AudioEncodingError, "not executable"):
            ExternalXma1Encoder(plain).validate()
        exe = self.root / "tool.exe"
        exe.write_bytes(b"MZ")
        with self.assertRaisesRegex(AudioEncodingError, "needs a separate Wine"):
            ExternalXma1Encoder(exe).validate()

    def test_timeout_stops_encoder_and_discards_output(self) -> None:
        slow = self._script(
            "slow-encoder",
            "import time\ntime.sleep(10)\n",
        )
        adapter = ExternalXma1Encoder(slow, timeout_seconds=0.05)
        with self.assertRaisesRegex(AudioEncodingError, "timed out"):
            adapter.encode(self.source, self.target)

    def test_cancel_before_launch_does_not_start_encoder(self) -> None:
        adapter = ExternalXma1Encoder(self._copy_encoder())
        with (
            patch("mod_editor.apf_studio.audio_encoding.subprocess.Popen") as popen,
            self.assertRaises(AudioEncodingCancelled),
        ):
            adapter.encode(
                self.source,
                self.target,
                cancel_requested=lambda: True,
            )
        popen.assert_not_called()

    def test_cancel_during_process_stops_it(self) -> None:
        slow = self._script(
            "cancel-encoder",
            "import time\ntime.sleep(10)\n",
        )
        checks = 0

        def cancelled() -> bool:
            nonlocal checks
            checks += 1
            return checks >= 4

        with self.assertRaisesRegex(AudioEncodingCancelled, "no project edit"):
            ExternalXma1Encoder(slow).encode(
                self.source,
                self.target,
                cancel_requested=cancelled,
            )

    def test_missing_or_oversized_output_is_actionable(self) -> None:
        missing = self._script("missing-output", "pass\n")
        with self.assertRaisesRegex(AudioEncodingError, "did not create"):
            ExternalXma1Encoder(missing).encode(self.source, self.target)

        oversized = self._script(
            "oversized-output",
            "import pathlib, sys\n"
            f"pathlib.Path(sys.argv[2]).write_bytes(b'x' * {0x800 + 1024 * 1024 + 1})\n",
        )
        with self.assertRaisesRegex(AudioEncodingError, "larger than this slot"):
            ExternalXma1Encoder(oversized).encode(self.source, self.target)

    def test_nonzero_exit_reports_bounded_diagnostic(self) -> None:
        failing = self._script(
            "failing-encoder",
            "import sys\nsys.stderr.write('unsupported target shape')\nsys.exit(7)\n",
        )
        with self.assertRaisesRegex(AudioEncodingError, "unsupported target shape"):
            ExternalXma1Encoder(failing).encode(self.source, self.target)

    def test_wrong_pcm_shape_and_linked_input_fail_before_encoder_runs(self) -> None:
        mono_target = Pcm16Target(1, 48_000, 8, 0x800)
        adapter = ExternalXma1Encoder(self._copy_encoder())
        with (
            patch("mod_editor.apf_studio.audio_encoding.subprocess.Popen") as popen,
            self.assertRaisesRegex(AudioEncodingError, "shape does not match"),
        ):
            adapter.encode(self.source, mono_target)
        popen.assert_not_called()

        linked = self.root / "linked.wav"
        linked.symlink_to(self.source)
        with self.assertRaisesRegex(AudioEncodingError, "not a link"):
            adapter.encode(linked, self.target)

    def test_argument_template_is_explicit_and_bounded(self) -> None:
        tool = self._copy_encoder()
        for arguments, message in (
            (("{input}",), "exactly once"),
            (("{input}", "{output}", "{unknown}"), "Unsupported"),
            (("{input!r}", "{output}"), "Unsupported"),
        ):
            with self.subTest(arguments=arguments):
                with self.assertRaisesRegex(AudioEncodingError, message):
                    ExternalXma1Encoder(tool, arguments=arguments)
        with self.assertRaisesRegex(AudioEncodingError, "must be absolute"):
            ExternalXma1Encoder(Path("relative-tool")).validate()


if __name__ == "__main__":
    unittest.main()

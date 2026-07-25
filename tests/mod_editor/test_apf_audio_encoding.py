"""Focused hostile tests for the user-supplied APF XMA1 encoder bridge."""

from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import struct
import sys
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
from mod_editor.core import platform_compat


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


def _pid_alive(pid: int) -> bool:
    """Is *pid* still running?  A read-only probe on both process models.

    POSIX signal 0 checks for existence and delivers nothing.  Windows has no
    equivalent signal: ``os.kill`` there is ``TerminateProcess``, so the POSIX
    spelling ``os.kill(pid, 0)`` would *end* the very process we are trying to
    observe.  Opening the process for SYNCHRONIZE and waiting on it with a zero
    timeout is the read-only equivalent -- a handle that cannot be opened, or
    one that is already signalled, means the process has exited.
    """

    if not platform_compat.IS_WINDOWS:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True
    synchronize = 0x00100000
    wait_object_0 = 0x00000000
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel32.WaitForSingleObject.restype = ctypes.c_ulong
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    handle = kernel32.OpenProcess(synchronize, False, pid)
    if not handle:
        return False
    try:
        return kernel32.WaitForSingleObject(handle, 0) != wait_object_0
    finally:
        kernel32.CloseHandle(handle)


def _wait_pid_gone(pid: int, timeout_seconds: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(0.02)
    return not _pid_alive(pid)


def _fixture_invocation(script: Path) -> tuple[Path, tuple[str, ...]]:
    """The (executable, leading argv) that runs one fabricated fixture program.

    The fixtures below are Python programs written into a temporary directory.
    POSIX makes such a file an executable in its own right: the ``#!`` line
    names the interpreter and the executable bit lets ``exec`` use it, so the
    script *is* the tool.  Windows has neither mechanism -- handing a script to
    CreateProcess fails with WinError 193, "%1 is not a valid Win32
    application".  Naming the interpreter explicitly behaves identically on
    both platforms, and, unlike a ``.bat``/``.cmd`` wrapper, it does not route
    the launch through ``cmd.exe``, which would quietly destroy the no-shell
    property several of these tests exist to prove.  The fixture bodies are
    unaffected either way: Python drops its own argv[0], so ``sys.argv`` inside
    the script is the same list on both platforms.
    """

    if platform_compat.IS_WINDOWS:
        # ``.resolve()`` because the adapter refuses a tool path that is a
        # link, and a packaged interpreter is reached through one on some
        # installs.  It is a no-op for a plain python.exe.
        return Path(sys.executable).resolve(), (str(script),)
    return script, ()


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

    def _encoder(
        self,
        script: Path,
        *arguments: str,
        timeout_seconds: float = 120.0,
    ) -> ExternalXma1Encoder:
        """Configure the adapter to run one fabricated fixture *script*.

        See :func:`_fixture_invocation`: POSIX runs the script directly, and
        Windows runs it through this interpreter, which is exactly how a
        Windows user configures a script-based encoder.
        """

        executable, prefix = _fixture_invocation(script)
        return ExternalXma1Encoder(
            executable,
            arguments=(*prefix, *(arguments or ("{input}", "{output}"))),
            timeout_seconds=timeout_seconds,
        )

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
        encoder = self._encoder(
            self._copy_encoder(),
            "{input}",
            "{output}",
            f";touch {marker}",
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
        result = self._encoder(self._copy_encoder()).encode(source, self.target)
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
        if platform_compat.IS_WINDOWS:
            # Wine is how a *Unix* host runs a Windows .exe; it does not exist
            # on Windows, so the loader itself cannot run here.  The contract
            # this test is named for is still asserted from the argv the adapter
            # builds: the user's .exe stays a plain argv[1] to the loader --
            # never a shell string -- and the two private paths stay two
            # separate argv entries rather than one packed command line.  What
            # is *not* asserted here is the Z: drive mapping of those paths:
            # that is a POSIX-host concept and lives in the companion test
            # below, which is skipped on Windows for the reason stated there.
            with (
                patch(
                    "mod_editor.apf_studio.audio_encoding.subprocess.Popen",
                    side_effect=OSError(8, "%1 is not a valid Win32 application"),
                ) as popen,
                self.assertRaisesRegex(AudioEncodingError, "Could not start"),
            ):
                adapter.encode(self.source, self.target)
            command = popen.call_args.args[0]
            self.assertEqual(tuple(command[:2]), (str(wine), str(encoder_exe)))
            self.assertEqual(len(command), 4, command)
            return
        result = adapter.encode(self.source, self.target)
        self.assertEqual(result.xma1_riff, self.source.read_bytes())
        self.assertEqual(result.receipt["mode"], "wine")

    @unittest.skipIf(
        platform_compat.IS_WINDOWS,
        # Wine's Z: drive is the drive letter Wine points at the *Unix* root, so
        # the drive-mapped argv asserted below only means anything on a POSIX
        # host: a Windows host has no Unix root to map and no Wine loader to run
        # (the adapter's POSIX-only "Z:" + path spelling would produce
        # Z:C:\Users\... there, which is a path on neither OS).  Skipping is
        # honest about that rather than pinning a spelling nothing consumes;
        # the plain-argv/no-shell contract this mapping rides on stays asserted
        # on Windows by test_wine_mode_uses_user_exe_as_a_plain_argument above.
        "Wine's Z: drive maps the Unix root; wine mode cannot apply on a "
        "Windows host",
    )
    def test_wine_mode_hands_the_private_paths_over_drive_mapped(self) -> None:
        encoder_exe = self.root / "xmaencode.exe"
        encoder_exe.write_bytes(b"MZ synthetic user tool")
        wine = self._script("wine-loader", "raise SystemExit(0)\n")
        adapter = ExternalXma1Encoder(encoder_exe, wine_executable=wine)
        with (
            patch(
                "mod_editor.apf_studio.audio_encoding.subprocess.Popen",
                side_effect=OSError(2, "no such file or directory"),
            ) as popen,
            self.assertRaisesRegex(AudioEncodingError, "Could not start"),
        ):
            adapter.encode(self.source, self.target)
        command = popen.call_args.args[0]
        self.assertEqual(tuple(command[:2]), (str(wine), str(encoder_exe)))
        self.assertTrue(
            all(argument.startswith("Z:\\") for argument in command[2:]),
            command,
        )

    def test_successful_encoder_parent_cannot_leave_background_child(self) -> None:
        pid_file = self.root / "background-child.pid"
        encoder = self._script(
            "background-child-encoder",
            # The backgrounded child is another copy of this interpreter rather
            # than /bin/sleep, which does not exist on Windows.  The guarantee
            # under test is unchanged: a launcher that exits successfully must
            # not be able to leave that child running.
            "import pathlib, shutil, subprocess, sys\n"
            "child = subprocess.Popen(\n"
            "    [sys.executable, '-c', 'import time; time.sleep(17)']\n"
            ")\n"
            "pathlib.Path(sys.argv[3]).write_text(str(child.pid), encoding='ascii')\n"
            "shutil.copyfile(sys.argv[1], sys.argv[2])\n",
        )
        result = self._encoder(
            encoder,
            "{input}",
            "{output}",
            str(pid_file),
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
        exe = self.root / "tool.exe"
        exe.write_bytes(b"MZ")
        if platform_compat.IS_WINDOWS:
            # Neither POSIX refusal applies on Windows, and asserting them here
            # would assert a fiction.  There is no executable permission bit --
            # os.access(path, os.X_OK) is "does this file exist" there, so it
            # can never refuse -- and a .exe is Windows' *native* direct mode,
            # not something that needs a Wine loader.  What must still hold is
            # the guarantee those refusals protect: a file the OS cannot launch
            # never becomes a staged edit.  Windows enforces it at CreateProcess
            # (WinError 193) and the adapter turns that into the same
            # fail-closed AudioEncodingError.
            self.assertEqual(ExternalXma1Encoder(exe).validate()["mode"], "direct")
            self.assertEqual(ExternalXma1Encoder(plain).validate()["mode"], "direct")
            with self.assertRaisesRegex(AudioEncodingError, "Could not start"):
                ExternalXma1Encoder(plain).encode(self.source, self.target)
            return
        with self.assertRaisesRegex(AudioEncodingError, "not executable"):
            ExternalXma1Encoder(plain).validate()
        with self.assertRaisesRegex(AudioEncodingError, "needs a separate Wine"):
            ExternalXma1Encoder(exe).validate()

    def test_timeout_stops_encoder_and_discards_output(self) -> None:
        slow = self._script(
            "slow-encoder",
            "import time\ntime.sleep(10)\n",
        )
        adapter = self._encoder(slow, timeout_seconds=0.05)
        with self.assertRaisesRegex(AudioEncodingError, "timed out"):
            adapter.encode(self.source, self.target)

    def test_cancel_before_launch_does_not_start_encoder(self) -> None:
        adapter = self._encoder(self._copy_encoder())
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
            self._encoder(slow).encode(
                self.source,
                self.target,
                cancel_requested=cancelled,
            )

    def test_missing_or_oversized_output_is_actionable(self) -> None:
        missing = self._script("missing-output", "pass\n")
        with self.assertRaisesRegex(AudioEncodingError, "did not create"):
            self._encoder(missing).encode(self.source, self.target)

        oversized = self._script(
            "oversized-output",
            "import pathlib, sys\n"
            f"pathlib.Path(sys.argv[2]).write_bytes(b'x' * {0x800 + 1024 * 1024 + 1})\n",
        )
        with self.assertRaisesRegex(AudioEncodingError, "larger than this slot"):
            self._encoder(oversized).encode(self.source, self.target)

    def test_nonzero_exit_reports_bounded_diagnostic(self) -> None:
        failing = self._script(
            "failing-encoder",
            "import sys\nsys.stderr.write('unsupported target shape')\nsys.exit(7)\n",
        )
        with self.assertRaisesRegex(AudioEncodingError, "unsupported target shape"):
            self._encoder(failing).encode(self.source, self.target)

    def test_wrong_pcm_shape_and_linked_input_fail_before_encoder_runs(self) -> None:
        mono_target = Pcm16Target(1, 48_000, 8, 0x800)
        adapter = self._encoder(self._copy_encoder())
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

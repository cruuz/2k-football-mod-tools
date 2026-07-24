"""Session/facade admission tests for privately encoded APF audio."""

from __future__ import annotations

import ctypes
import hashlib
import os
from pathlib import Path
import struct
import sys
import time
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from mod_editor.apf_studio.audio_encoding import (
    AudioEncodingCancelled,
    ExternalEncodingResult,
    ExternalXma1Encoder,
    Pcm16Target,
    export_pcm16_template,
)
from mod_editor.apf_studio.catalog import ApfCatalog
from mod_editor.apf_studio.facade import ApfStudioFacade
from mod_editor.apf_studio.inspectors import ExportIdentity
from mod_editor.apf_studio.models import ApfSource, Modification
from mod_editor.apf_studio.session import ApfSession, SessionError
from mod_editor.core import platform_compat
import apf_audo_exact_slot as audo_writer
import apf_ausb_exact_slot as ausb_writer


def _packets(fill: int) -> bytes:
    packet = bytearray([fill] * 0x800)
    struct.pack_into(">I", packet, 0, 2 << 26)
    return bytes(packet)


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

    The encoder fixture below is a Python program written into a temporary
    directory.  POSIX makes such a file an executable in its own right -- the
    ``#!`` line names the interpreter and the executable bit lets ``exec`` use
    it -- while Windows has neither mechanism and fails the launch with
    WinError 193, "%1 is not a valid Win32 application".  Naming the
    interpreter explicitly behaves identically on both platforms and keeps the
    launch shell-free, unlike a ``.bat``/``.cmd`` wrapper.  Python drops its
    own argv[0], so ``sys.argv`` inside the fixture is the same list either
    way.
    """

    if platform_compat.IS_WINDOWS:
        # ``.resolve()`` because the adapter refuses a tool path that is a
        # link, and a packaged interpreter is reached through one on some
        # installs.  It is a no-op for a plain python.exe.
        return Path(sys.executable).resolve(), (str(script),)
    return script, ()


class ApfAudioPcmProductBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="apf-pcm-product-")
        self.root = Path(self.temporary.name)
        game = self.root / "game"
        game.mkdir()
        index = game / "0A"
        index.write_bytes(b"synthetic index")
        self.source = ApfSource(
            selected_path=game,
            game_root=game,
            index_0a=index,
            source_sha256="1" * 64,
            source_size=index.stat().st_size,
            xex_sha256="2" * 64,
            display_name="Synthetic APF",
        )
        self.catalog = ApfCatalog(
            source_sha256=self.source.source_sha256,
            outer_count=0,
            iff_count=0,
            non_iff_count=0,
            inner_count=0,
            assets=(),
            uniform_assets=(),
            capabilities=(),
            audio_selection_manifest=self.root / "selection.json",
        )
        self.audo_identity = ExportIdentity("audo", 10, 3, None, "synthetic-audo")
        self.audo_target = audo_writer.ExactSlotTarget(
            channels=1,
            sample_rate=22_050,
            encoded_size=0x800,
            declared_sample_count=16,
            loop_start_bit=0,
            loop_end_bit=0x800 * 8,
            loop_subframe=0,
        )
        self.audo_resolved = audo_writer.ResolvedExactSlot(
            asset_id="apf:audio:audo:10:3",
            name="synthetic-audo",
            outer_index=10,
            inner_index=3,
            target=self.audo_target,
            pack_name="0A",
            pack_offset=0,
            encoded_size=0x800,
            source_payload_sha256="a" * 64,
        )
        owner = ausb_writer.AusbOwner(
            descriptor_outer_index=20,
            descriptor_inner_index=4,
            substream_index=2,
            bank_name="synthetic-bank",
            external_filename="synthetic.bin",
            channels=2,
            sample_rate=48_000,
            duration_value_bits=0x3A83126F,
            duration_seconds=16 / 48_000,
            declared_sample_count=16,
        )
        self.ausb_identity = ExportIdentity(
            "ausb_substream", 20, 4, 2, "synthetic-bank-00002"
        )
        self.ausb_resolved = ausb_writer.ResolvedExactSlot(
            asset_id=owner.asset_id,
            requested_owner=owner,
            owners=(owner,),
            canonical_physical_id="apf:audio:ausb:physical:99:0:2048",
            external_outer_index=99,
            external_range_offset=0,
            target=ausb_writer.ExactSlotTarget(
                channels=2,
                sample_rate=48_000,
                encoded_size=0x800,
                declared_sample_count=16,
            ),
            physical_spans=(ausb_writer.PhysicalSpan("0A", 0, 0x800, 0),),
            source_payload_sha256="b" * 64,
        )
        self.wav = self.root / "user.wav"
        self.wav.write_bytes(b"synthetic PCM fixture")
        self.encoder = ExternalXma1Encoder(Path("/not-run-user-encoder"))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _encoding_result(data: bytes = b"RIFF user XMA1") -> ExternalEncodingResult:
        return ExternalEncodingResult(
            xma1_riff=data,
            receipt={"status": "encoded_pending_exact_slot_validation"},
        )

    @staticmethod
    def _audo_result(payload: bytes) -> audo_writer.ExactSlotImportResult:
        return audo_writer.ExactSlotImportResult(
            payload=payload,
            receipt={
                "replacement": {"payload_sha256": hashlib.sha256(payload).hexdigest()}
            },
        )

    @staticmethod
    def _ausb_result(payload: bytes) -> ausb_writer.ExactSlotImportResult:
        return ausb_writer.ExactSlotImportResult(
            payload=payload,
            receipt={
                "replacement": {"payload_sha256": hashlib.sha256(payload).hexdigest()}
            },
        )

    def test_audo_pcm_is_encoded_then_exact_slot_validated_before_one_set(self) -> None:
        session = ApfSession(self.source, self.catalog, cache_root=self.root / "cache")
        payload = _packets(0x44)
        try:
            with (
                patch.object(
                    self.encoder, "encode", return_value=self._encoding_result()
                ) as encode,
                patch(
                    "mod_editor.apf_studio.session.apf_audo_exact_slot.resolve_target",
                    return_value=self.audo_resolved,
                ),
                patch(
                    "mod_editor.apf_studio.session.apf_audo_exact_slot.validate_exact_slot_import",
                    return_value=self._audo_result(payload),
                ) as validate,
                patch.object(
                    session, "_protected_audo_fingerprints", return_value=object()
                ) as fingerprints,
                patch.object(
                    session, "_protected_audo_payload_hashes", return_value=frozenset()
                ),
                patch.object(session, "_reject_any_source_audio_reuse") as reject,
            ):
                modification = session.replace_audio_from_pcm(
                    self.audo_identity, self.wav, self.encoder
                )
            expected_target = Pcm16Target(1, 22_050, 16, 0x800)
            encode.assert_called_once_with(
                self.wav,
                expected_target,
                progress=None,
                cancel_requested=None,
            )
            validate.assert_called_once_with(
                b"RIFF user XMA1", self.audo_resolved.target, fingerprints.return_value
            )
            reject.assert_called_once_with(payload)
            self.assertEqual(modification.replacement_path.read_bytes(), payload)
            self.assertEqual(session.modified_asset_ids, {self.audo_resolved.asset_id})
            self.assertTrue(session.can_undo)
            self.assertNotIn("encoder", modification.metadata)
        finally:
            session.close()

    def test_ausb_pcm_dispatches_to_ausb_validator_and_preserves_alias_metadata(self) -> None:
        session = ApfSession(self.source, self.catalog, cache_root=self.root / "cache")
        payload = _packets(0x55)
        try:
            with (
                patch.object(
                    self.encoder, "encode", return_value=self._encoding_result()
                ),
                patch(
                    "mod_editor.apf_studio.session.apf_ausb_exact_slot.resolve_target",
                    return_value=self.ausb_resolved,
                ),
                patch(
                    "mod_editor.apf_studio.session.apf_ausb_exact_slot.validate_exact_slot_import",
                    return_value=self._ausb_result(payload),
                ) as validate,
                patch.object(
                    session, "_protected_ausb_fingerprints", return_value=object()
                ) as fingerprints,
                patch.object(
                    session, "_protected_ausb_payload_hashes", return_value=frozenset()
                ),
                patch.object(session, "_reject_any_source_audio_reuse"),
            ):
                modification = session.replace_audio_from_pcm(
                    self.ausb_identity, self.wav, self.encoder
                )
            validate.assert_called_once_with(
                b"RIFF user XMA1", self.ausb_resolved, fingerprints.return_value
            )
            self.assertEqual(
                modification.metadata["shared_owner_asset_ids"],
                [self.ausb_resolved.asset_id],
            )
            self.assertEqual(modification.replacement_path.read_bytes(), payload)
        finally:
            session.close()

    def test_validator_failure_or_cancel_never_changes_edit_map_or_undo(self) -> None:
        session = ApfSession(self.source, self.catalog, cache_root=self.root / "cache")
        try:
            with (
                patch.object(
                    self.encoder, "encode", return_value=self._encoding_result()
                ),
                patch(
                    "mod_editor.apf_studio.session.apf_audo_exact_slot.resolve_target",
                    return_value=self.audo_resolved,
                ),
                patch(
                    "mod_editor.apf_studio.session.apf_audo_exact_slot.validate_exact_slot_import",
                    side_effect=audo_writer.ExactSlotImportError("malformed XMA1"),
                ),
                patch.object(
                    session, "_protected_audo_fingerprints", return_value=object()
                ),
            ):
                with self.assertRaisesRegex(SessionError, "malformed XMA1"):
                    session.replace_audio_from_pcm(
                        self.audo_identity, self.wav, self.encoder
                    )
            self.assertEqual(session.modified_count, 0)
            self.assertFalse(session.can_undo)

            with (
                patch.object(
                    self.encoder,
                    "encode",
                    side_effect=AudioEncodingCancelled(
                        "Audio encoding was cancelled; no project edit was staged"
                    ),
                ),
                patch(
                    "mod_editor.apf_studio.session.apf_audo_exact_slot.resolve_target",
                    return_value=self.audo_resolved,
                ),
            ):
                with self.assertRaisesRegex(SessionError, "cancelled"):
                    session.replace_audio_from_pcm(
                        self.audo_identity, self.wav, self.encoder
                    )
            self.assertEqual(session.modified_count, 0)
            self.assertFalse(session.can_undo)
        finally:
            session.close()

    def test_cancel_after_encoder_returns_skips_validator_and_stages_nothing(self) -> None:
        session = ApfSession(self.source, self.catalog, cache_root=self.root / "cache")
        try:
            with (
                patch.object(
                    self.encoder, "encode", return_value=self._encoding_result()
                ),
                patch(
                    "mod_editor.apf_studio.session.apf_audo_exact_slot.resolve_target",
                    return_value=self.audo_resolved,
                ),
                patch(
                    "mod_editor.apf_studio.session.apf_audo_exact_slot.validate_exact_slot_import"
                ) as validate,
            ):
                with self.assertRaisesRegex(SessionError, "cancelled"):
                    session.replace_audio_from_pcm(
                        self.audo_identity,
                        self.wav,
                        self.encoder,
                        cancel_requested=lambda: True,
                    )
            validate.assert_not_called()
            self.assertEqual(session.modified_count, 0)
            self.assertFalse(session.can_undo)
            self.assertFalse(tuple(session.replacements_root.glob("*.xma1-packets")))
        finally:
            session.close()

    def test_validator_side_effect_cancel_removes_only_new_uncommitted_payload(self) -> None:
        session = ApfSession(self.source, self.catalog, cache_root=self.root / "cache")
        payload = _packets(0x66)
        sentinel_data = b"preexisting unreferenced packet cache"
        sentinel_digest = hashlib.sha256(sentinel_data).hexdigest()
        sentinel = session._store_payload(  # type: ignore[attr-defined]
            sentinel_digest,
            sentinel_data,
            ".xma1-packets",
        )
        cancelled = False

        def validate_with_late_cancel(*_args: object) -> audo_writer.ExactSlotImportResult:
            nonlocal cancelled
            cancelled = True
            return self._audo_result(payload)

        facade = ApfStudioFacade(cache_root=self.root / "facade-cache")
        facade.session = session
        prior_build = object()
        facade.last_build = prior_build  # type: ignore[assignment]
        try:
            with (
                patch.object(
                    self.encoder, "encode", return_value=self._encoding_result()
                ),
                patch(
                    "mod_editor.apf_studio.session.apf_audo_exact_slot.resolve_target",
                    return_value=self.audo_resolved,
                ),
                patch(
                    "mod_editor.apf_studio.session.apf_audo_exact_slot.validate_exact_slot_import",
                    side_effect=validate_with_late_cancel,
                ),
                patch.object(
                    session, "_protected_audo_fingerprints", return_value=object()
                ),
                patch.object(
                    session, "_protected_audo_payload_hashes", return_value=frozenset()
                ),
                patch.object(session, "_reject_any_source_audio_reuse"),
            ):
                with self.assertRaisesRegex(SessionError, "cancelled"):
                    facade.replace_audio_from_pcm(
                        self.audo_identity,
                        self.wav,
                        self.encoder,
                        cancel_requested=lambda: cancelled,
                    )
            self.assertEqual(session.modified_count, 0)
            self.assertFalse(session.can_undo)
            self.assertIs(facade.last_build, prior_build)
            self.assertTrue(sentinel.is_file())
            self.assertEqual(sentinel.read_bytes(), sentinel_data)
            self.assertEqual(
                tuple(session.replacements_root.glob("*.xma1-packets")),
                (sentinel,),
            )
        finally:
            session.close()

    def test_background_only_encoder_output_cannot_become_a_project_edit(self) -> None:
        session = ApfSession(self.source, self.catalog, cache_root=self.root / "cache")
        valid_wav = self.root / "valid-user.wav"
        export_pcm16_template(valid_wav, Pcm16Target(1, 22_050, 16, 0x800))
        pid_file = self.root / "delayed-child.pid"
        encoder_script = self.root / "delayed-output-encoder"
        encoder_script.write_text(
            "#!/usr/bin/env python3\n"
            "import pathlib, subprocess, sys\n"
            "code = (\"import shutil,sys,time;time.sleep(5);\"\n"
            "        \"shutil.copyfile(sys.argv[1],sys.argv[2])\")\n"
            "child = subprocess.Popen([sys.executable, '-c', code, sys.argv[1], sys.argv[2]])\n"
            "pathlib.Path(sys.argv[3]).write_text(str(child.pid), encoding='ascii')\n",
            encoding="utf-8",
        )
        encoder_script.chmod(0o700)
        executable, prefix = _fixture_invocation(encoder_script)
        encoder = ExternalXma1Encoder(
            executable,
            arguments=(*prefix, "{input}", "{output}", str(pid_file)),
        )
        try:
            with patch(
                "mod_editor.apf_studio.session.apf_audo_exact_slot.resolve_target",
                return_value=self.audo_resolved,
            ):
                with self.assertRaisesRegex(SessionError, "did not create"):
                    session.replace_audio_from_pcm(
                        self.audo_identity,
                        valid_wav,
                        encoder,
                    )
            self.assertEqual(session.modified_count, 0)
            self.assertFalse(session.can_undo)
            background_pid = int(pid_file.read_text(encoding="ascii"))
            self.assertTrue(
                _wait_pid_gone(background_pid),
                f"delayed encoder child {background_pid} survived failed import",
            )
        finally:
            session.close()

    def test_target_and_template_are_derived_from_exact_identity(self) -> None:
        session = ApfSession(self.source, self.catalog, cache_root=self.root / "cache")
        destination = self.root / "template.wav"
        try:
            with patch(
                "mod_editor.apf_studio.session.apf_audo_exact_slot.resolve_target",
                return_value=self.audo_resolved,
            ):
                target = session.audio_pcm_target(self.audo_identity)
                receipt = session.export_audio_pcm_template(
                    self.audo_identity, destination
                )
            self.assertEqual(target, Pcm16Target(1, 22_050, 16, 0x800))
            self.assertEqual(receipt.frame_count, 16)
            self.assertEqual(receipt.encoded_size, 0x800)
            self.assertEqual(destination.stat().st_size, 44 + 16 * 2)
            self.assertEqual(destination.read_bytes()[-32:], b"\0" * 32)
        finally:
            session.close()

    def test_container_identity_is_rejected_without_running_encoder(self) -> None:
        session = ApfSession(self.source, self.catalog, cache_root=self.root / "cache")
        container = ExportIdentity("ausb", 20, 4, None, "synthetic-bank")
        try:
            with (
                patch.object(self.encoder, "encode") as encode,
                self.assertRaisesRegex(SessionError, "one standalone AUDO"),
            ):
                session.replace_audio_from_pcm(container, self.wav, self.encoder)
            encode.assert_not_called()
        finally:
            session.close()

    def test_facade_routes_target_template_and_replace_and_invalidates_build(self) -> None:
        facade = ApfStudioFacade(cache_root=self.root / "facade-cache")
        fake_session = MagicMock()
        target = Pcm16Target(1, 22_050, 16, 0x800)
        fake_session.audio_pcm_target.return_value = target
        fake_session.export_audio_pcm_template.return_value = object()
        fake_modification = Modification(
            asset_id="apf:audio:audo:10:3",
            kind="audo_exact_slot_xma1",
            replacement_path=self.wav,
            replacement_sha256="3" * 64,
            metadata={},
        )
        fake_session.replace_audio_from_pcm.return_value = fake_modification
        facade.session = fake_session
        facade.last_build = object()  # type: ignore[assignment]

        self.assertEqual(facade.audio_pcm_target(self.audo_identity), target)
        destination = self.root / "facade-template.wav"
        template = facade.export_audio_pcm_template(
            self.audo_identity, destination
        )
        self.assertIs(template, fake_session.export_audio_pcm_template.return_value)
        result = facade.replace_audio_from_pcm(
            self.audo_identity, self.wav, self.encoder
        )
        self.assertIs(result, fake_modification)
        self.assertIsNone(facade.last_build)
        fake_session.export_audio_pcm_template.assert_called_once()
        fake_session.replace_audio_from_pcm.assert_called_once()


if __name__ == "__main__":
    unittest.main()

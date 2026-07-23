"""Synthetic, retail-free tests for final NFL 2K5 AUSB composition."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass, replace
from functools import cache
import hashlib
import io
from pathlib import Path
import struct
from types import MappingProxyType
import unittest
from unittest.mock import patch

from mod_editor.core import nfl2k5_ausb_build_adapter as adapter
from mod_editor.core.nfl2k5_audio_containment_fingerprints import (
    PcmContainmentPolicy,
    ShortCueAnchorShape,
    SourcePcmCueInput,
    build_private_containment_inventory,
)
from mod_editor.core.nfl2k5_audio_origin_authorization import (
    AudioOriginAuthorizationError,
    AuthorizedPcm16Wav,
    authorize_strict_pcm16_wav,
)
from mod_editor.core.nfl2k5_audio_source_fingerprints import (
    AudioSourceFingerprintInventory,
)
from mod_editor.core.nfl2k5_ausb_fixed_slots import (
    CanonicalStreamingSlot,
    LogicalStreamingOwner,
    StreamingEncodeCancelled,
    StreamingPackSpan,
)


@dataclass(frozen=True, slots=True)
class _UnsealedFixture:
    wav_bytes: bytes
    pcm16le: bytes
    channels: int
    sample_rate: int
    frame_count: int
    wav_sha256: str
    pcm_sha256: str


def _owner(index: int) -> LogicalStreamingOwner:
    return LogicalStreamingOwner(
        asset_id=f"nfl2k5.audio.ausb.o{10 + index:04d}.c0000.r00000",
        descriptor_asset_id=f"nfl2k5.audio.ausb.o{10 + index:04d}.c0000",
        descriptor_outer_index=10 + index,
        descriptor_chunk_index=0,
        range_index=0,
    )


def _slot(*, channels: int, seam: bool, shared: bool) -> CanonicalStreamingSlot:
    encoded_size = 72 * channels
    owners = (_owner(0), _owner(1)) if shared else (_owner(0),)
    if seam:
        first_length = 50
        spans = (
            StreamingPackSpan("0", 0, 206, first_length, 0),
            StreamingPackSpan(
                "1", 1, 0, encoded_size - first_length, first_length
            ),
        )
    else:
        spans = (StreamingPackSpan("4", 4, 91, encoded_size, 0),)
    return CanonicalStreamingSlot(
        canonical_id=(
            "nfl2k5.audio.ausb.physical.o0077."
            f"s0000000100.n{encoded_size:010x}"
        ),
        external_outer_index=77,
        external_outer_id=0x1234ABCD,
        range_start=256,
        range_end=256 + encoded_size,
        channels=channels,
        sample_rate=22_050,
        frame_count=128,
        owners=owners,
        physical_spans=spans,
    )


def _wav(*, channels: int, frames: int = 128) -> bytes:
    samples = tuple(
        ((frame * 503 + channel * 7_001) % 30_001) - 15_000
        for frame in range(frames)
        for channel in range(channels)
    )
    pcm = struct.pack(f"<{len(samples)}h", *samples)
    return (
        b"RIFF"
        + struct.pack("<I", 36 + len(pcm))
        + b"WAVEfmt "
        + struct.pack(
            "<IHHIIHH",
            16,
            1,
            channels,
            22_050,
            22_050 * channels * 2,
            channels * 2,
            16,
        )
        + b"data"
        + struct.pack("<I", len(pcm))
        + pcm
    )


@cache
def _origin_inventories():
    source_sha256 = hashlib.sha256(b"synthetic AUSB adapter source").hexdigest()
    exact = AudioSourceFingerprintInventory(
        source_sha256=source_sha256,
        path=Path("/private/synthetic-ausb-adapter-fingerprints.json"),
        standalone=(),
        streaming_slots=(),
        by_asset_id=MappingProxyType({}),
        by_pcm_sha256=MappingProxyType({}),
    )
    policy = PcmContainmentPolicy(short_anchor_shapes=(
        ShortCueAnchorShape(1, 22_050, 128),
        ShortCueAnchorShape(2, 22_050, 128),
    ))
    cues = tuple(
        SourcePcmCueInput(
            owner_asset_ids=(f"synthetic.source.{channels}ch",),
            channels=channels,
            sample_rate=22_050,
            frame_count=128,
            pcm16le=struct.pack(
                f"<{128 * channels}h",
                *(
                    10_000 + channels * 1_000 + index
                    for index in range(128 * channels)
                ),
            ),
        )
        for channels in (1, 2)
    )
    containment = build_private_containment_inventory(
        source_sha256,
        policy,
        cues,
        expected_cue_count=2,
        expected_owner_count=2,
    )
    return exact, containment


def _authorized(*, channels: int) -> AuthorizedPcm16Wav:
    wav = _wav(channels=channels)
    exact, containment = _origin_inventories()
    return authorize_strict_pcm16_wav(
        wav,
        target_channels=channels,
        target_sample_rate=22_050,
        target_frame_count=128,
        source_fingerprints=exact,
        containment_fingerprints=containment,
    )


def _unsealed(value: AuthorizedPcm16Wav) -> _UnsealedFixture:
    return _UnsealedFixture(
        wav_bytes=value.wav_bytes,
        pcm16le=value.pcm16le,
        channels=value.channels,
        sample_rate=value.sample_rate,
        frame_count=value.frame_count,
        wav_sha256=value.wav_sha256,
        pcm_sha256=value.pcm_sha256,
    )


def _compile(
    slot: CanonicalStreamingSlot,
    snapshot: adapter.AuthorizedWavSnapshot,
    **kwargs: object,
) -> adapter.CompiledStreamingSlotEdit:
    return adapter._compile_authorized_streaming_slot(  # noqa: SLF001
        slot, snapshot, **kwargs
    )


class Nfl2k5AusbBuildAdapterTests(unittest.TestCase):
    def test_mono_one_span_compiles_and_independently_verifies(self) -> None:
        slot = _slot(channels=1, seam=False, shared=False)
        real_verifier = adapter.verify_xbox_ima_stream
        with patch.object(
            adapter,
            "verify_xbox_ima_stream",
            wraps=real_verifier,
        ) as verifier:
            compiled = _compile(slot, _authorized(channels=1))

        verifier.assert_called_once()
        self.assertEqual(len(compiled.pack_slices), 1)
        payload_slice = compiled.pack_slices[0]
        plan = slot.physical_spans[0]
        self.assertEqual(
            (
                payload_slice.pack_name,
                payload_slice.pack_ordinal,
                payload_slice.pack_offset,
                payload_slice.payload_offset,
                payload_slice.length,
            ),
            (
                plan.pack_name,
                plan.pack_ordinal,
                plan.pack_offset,
                plan.payload_offset,
                plan.length,
            ),
        )
        self.assertFalse(compiled.shared_owner_effect)
        self.assertEqual(compiled.affected_asset_ids, (_owner(0).asset_id,))
        with self.assertRaises(FrozenInstanceError):
            compiled.frame_count = 64  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            payload_slice.pack_offset = 0  # type: ignore[misc]
        adapter.validate_compiled_streaming_slot(slot, compiled)

    def test_stereo_seam_slices_and_all_aliases_resolve_to_one_result(self) -> None:
        slot = _slot(channels=2, seam=True, shared=True)
        compiled = _compile(slot, _authorized(channels=2))

        self.assertEqual(
            [
                (
                    value.pack_name,
                    value.pack_ordinal,
                    value.pack_offset,
                    value.payload_offset,
                    value.length,
                )
                for value in compiled.pack_slices
            ],
            [("0", 0, 206, 0, 50), ("1", 1, 0, 50, 94)],
        )
        self.assertEqual(
            b"".join(value.payload for value in compiled.pack_slices),
            compiled.pack_slices[0].payload + compiled.pack_slices[1].payload,
        )
        self.assertTrue(compiled.shared_owner_effect)
        self.assertEqual(compiled.affected_asset_ids, tuple(
            owner.asset_id for owner in slot.owners
        ))
        self.assertIn("2 aliased logical audio assets", compiled.owner_effect_summary)
        self.assertIs(compiled.resolve_asset_id(slot.canonical_id), compiled)
        for owner in slot.owners:
            self.assertIs(compiled.resolve_asset_id(owner.asset_id), compiled)
        with self.assertRaises(adapter.Nfl2k5AusbBuildAdapterError):
            compiled.resolve_asset_id("nfl2k5.audio.ausb.not-owned")

    def test_reversed_duplicate_and_gapped_physical_plans_fail_closed(self) -> None:
        seam = _slot(channels=2, seam=True, shared=False)
        first, second = seam.physical_spans
        reversed_plan = replace(
            seam,
            physical_spans=(
                replace(second, payload_offset=0),
                replace(first, payload_offset=second.length),
            ),
        )
        mono = _slot(channels=1, seam=False, shared=False)
        duplicate_plan = replace(
            mono,
            physical_spans=(
                StreamingPackSpan("4", 4, 91, 36, 0),
                StreamingPackSpan("4", 4, 91, 36, 36),
            ),
        )
        gapped_plan = replace(
            mono,
            physical_spans=(
                StreamingPackSpan("4", 4, 91, 36, 0),
                StreamingPackSpan("4", 4, 131, 36, 36),
            ),
        )

        for label, slot, snapshot in (
            ("reversed", reversed_plan, _authorized(channels=2)),
            ("duplicate", duplicate_plan, _authorized(channels=1)),
            ("gap", gapped_plan, _authorized(channels=1)),
        ):
            with self.subTest(label=label):
                result = None
                with self.assertRaises(adapter.Nfl2k5AusbBuildAdapterError):
                    result = _compile(slot, snapshot)
                self.assertIsNone(result)

    def test_unreviewed_plan_and_alias_metadata_fail_before_encoding(self) -> None:
        mono = _slot(channels=1, seam=False, shared=False)
        owner = mono.owners[0]
        cases = {
            "three spans": replace(
                mono,
                physical_spans=(
                    StreamingPackSpan("2", 2, 100, 24, 0),
                    StreamingPackSpan("3", 3, 0, 24, 24),
                    StreamingPackSpan("4", 4, 0, 24, 48),
                ),
            ),
            "path-like pack name": replace(
                mono,
                physical_spans=(
                    StreamingPackSpan("../../cache", 4, 91, 72, 0),
                ),
            ),
            "unsupported pack": replace(
                mono,
                physical_spans=(StreamingPackSpan("G", 16, 91, 72, 0),),
            ),
            "canonical identity": replace(mono, canonical_id="changed"),
            "owner identity": replace(
                mono,
                owners=(replace(owner, descriptor_asset_id="changed"),),
            ),
            "unreviewed alias count": replace(
                mono,
                owners=(_owner(0), _owner(1), _owner(2)),
            ),
        }
        snapshot = _authorized(channels=1)
        for label, slot in cases.items():
            with self.subTest(label=label), patch.object(
                adapter, "encode_strict_pcm16_wav"
            ) as encoder:
                with self.assertRaises(adapter.Nfl2k5AusbBuildAdapterError):
                    _compile(slot, snapshot)
                encoder.assert_not_called()

    def test_encode_cancellation_rolls_staging_back_to_empty_and_returns_nothing(self) -> None:
        slot = _slot(channels=2, seam=True, shared=False)
        completed: list[int] = []
        observed_failed_payloads: list[bytes] = []
        real_encoder = adapter.encode_strict_pcm16_wav

        def observing_encoder(*args: object, **kwargs: object):
            output = args[1]
            assert isinstance(output, io.BytesIO)
            try:
                return real_encoder(*args, **kwargs)
            except BaseException:
                observed_failed_payloads.append(output.getvalue())
                raise

        result = None
        with patch.object(
            adapter, "encode_strict_pcm16_wav", side_effect=observing_encoder
        ):
            with self.assertRaisesRegex(StreamingEncodeCancelled, "before block 2"):
                result = _compile(
                    slot,
                    _authorized(channels=2),
                    progress=lambda value: completed.append(value.completed_blocks),
                    cancelled=lambda: completed == [0, 1],
                    progress_interval_blocks=1,
                )
        self.assertIsNone(result)
        self.assertEqual(completed, [0, 1])
        self.assertEqual(observed_failed_payloads, [b""])

    def test_verification_failure_erases_staging_and_returns_nothing(self) -> None:
        slot = _slot(channels=1, seam=False, shared=False)
        cleared: list[bytes] = []

        def clear_spy(buffer: io.BytesIO) -> None:
            buffer.seek(0)
            buffer.truncate(0)
            cleared.append(buffer.getvalue())
            buffer.close()

        result = None
        with patch.object(
            adapter,
            "verify_xbox_ima_stream",
            side_effect=adapter.Nfl2k5AusbBuildAdapterError(
                "synthetic verification failure"
            ),
        ), patch.object(adapter, "_clear_staging_buffer", side_effect=clear_spy):
            with self.assertRaisesRegex(
                adapter.Nfl2k5AusbBuildAdapterError,
                "synthetic verification failure",
            ):
                result = _compile(slot, _authorized(channels=1))

        self.assertIsNone(result)
        self.assertEqual(cleared, [b""])

    def test_snapshot_shape_identity_and_hashes_are_all_bound(self) -> None:
        slot = _slot(channels=1, seam=False, shared=False)
        issued = _authorized(channels=1)
        valid = _unsealed(issued)
        cases = {
            "shape": replace(valid, frame_count=64),
            "WAV/PCM identity": replace(valid, pcm16le=bytes(len(valid.pcm16le))),
            "WAV hash": replace(valid, wav_sha256="0" * 64),
            "PCM hash": replace(valid, pcm_sha256="0" * 64),
        }
        # The issuer independently owns its seal tests.  This mock isolates the
        # adapter's second-line byte/shape/hash checks without adding any raw-
        # WAV entry point to product code.
        with patch.object(
            adapter, "require_authorized_pcm16_wav", side_effect=lambda value: value
        ):
            for label, snapshot in cases.items():
                with self.subTest(label=label):
                    with self.assertRaises(adapter.Nfl2k5AusbBuildAdapterError):
                        _compile(slot, snapshot)

        with self.assertRaisesRegex(
            AudioOriginAuthorizationError, "module-issued"
        ):
            adapter._compile_authorized_streaming_slot(  # noqa: SLF001
                slot, issued.wav_bytes  # type: ignore[arg-type]
            )

    def test_module_issued_seal_is_required_before_any_encoding(self) -> None:
        slot = _slot(channels=1, seam=False, shared=False)
        issued = _authorized(channels=1)
        events: list[str] = []
        real_require = adapter.require_authorized_pcm16_wav
        real_encoder = adapter.encode_strict_pcm16_wav

        def require_spy(value: object):
            events.append("seal")
            return real_require(value)  # type: ignore[arg-type]

        def encode_spy(*args: object, **kwargs: object):
            events.append("encode")
            return real_encoder(*args, **kwargs)

        with patch.object(
            adapter, "require_authorized_pcm16_wav", side_effect=require_spy
        ), patch.object(
            adapter, "encode_strict_pcm16_wav", side_effect=encode_spy
        ):
            _compile(slot, issued)
        self.assertEqual(events[:2], ["seal", "encode"])

        events.clear()
        with patch.object(
            adapter, "encode_strict_pcm16_wav", side_effect=encode_spy
        ):
            with self.assertRaises(AudioOriginAuthorizationError):
                _compile(slot, _unsealed(issued))
        self.assertEqual(events, [])

        tampered = _authorized(channels=1)
        object.__setattr__(
            tampered,
            "wav_bytes",
            tampered.wav_bytes[:44] + bytes(len(tampered.pcm16le)),
        )
        with patch.object(
            adapter, "encode_strict_pcm16_wav", side_effect=encode_spy
        ):
            with self.assertRaises(AudioOriginAuthorizationError):
                _compile(slot, tampered)
        self.assertEqual(events, [])

    def test_compiled_identity_owner_shape_and_payload_tampering_are_rejected(self) -> None:
        slot = _slot(channels=2, seam=True, shared=True)
        compiled = _compile(slot, _authorized(channels=2))
        changed_payload = bytes([compiled.pack_slices[0].payload[0] ^ 1]) \
            + compiled.pack_slices[0].payload[1:]
        cases = {
            "canonical ID": replace(compiled, canonical_id="changed"),
            "owners": replace(compiled, owners=(slot.owners[0],)),
            "shape": replace(compiled, frame_count=64),
            "payload": replace(
                compiled,
                pack_slices=(
                    replace(compiled.pack_slices[0], payload=changed_payload),
                    compiled.pack_slices[1],
                ),
            ),
        }
        for label, changed in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(adapter.Nfl2k5AusbBuildAdapterError):
                    adapter.validate_compiled_streaming_slot(slot, changed)

    def test_compilation_hashes_and_slices_are_deterministic(self) -> None:
        mono_slot = _slot(channels=1, seam=False, shared=False)
        stereo_slot = _slot(channels=2, seam=True, shared=True)
        mono_first = _compile(mono_slot, _authorized(channels=1))
        mono_second = _compile(mono_slot, _authorized(channels=1))
        stereo_first = _compile(stereo_slot, _authorized(channels=2))
        stereo_second = _compile(stereo_slot, _authorized(channels=2))

        self.assertEqual(mono_first, mono_second)
        self.assertEqual(stereo_first, stereo_second)
        self.assertEqual(
            (
                mono_first.encoded_sha256,
                mono_first.decoded_pcm_sha256,
                mono_first.composition_sha256,
            ),
            (
                "7a755dd6771066fc3f2d64d7222757cb19ab40d11876272ee121a54134116eed",
                "71d49649dd06575add329df7ceb935c4a015c2ef47ced6e422896dcff8b96ccc",
                "c8c62514eba364b620199f4aea1da7098c2b5ba7b3706be8374ac5b7bc268191",
            ),
        )
        self.assertEqual(
            (
                stereo_first.encoded_sha256,
                stereo_first.decoded_pcm_sha256,
                stereo_first.composition_sha256,
            ),
            (
                "f0a8fe33e90c5735f0252bc81b873a3396cf76d721beca969c6139dc44b15326",
                "b19f0576fb31ceab03dae21c2e4b3373bae1be6e7e62b8cbb63ece45a245f8cb",
                "3d691e877545f531f1b8d7ccd14cf10f64e874cd9cd8e2e45d35edc3dd126202",
            ),
        )


if __name__ == "__main__":
    unittest.main()

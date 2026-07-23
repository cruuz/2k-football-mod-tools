"""Retail-free tests for the final in-memory 2K5 audio origin boundary."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import hashlib
from pathlib import Path
import struct
import tempfile
from types import MappingProxyType
import unittest
from unittest import mock

from mod_editor.core import nfl2k5_audio_origin_authorization as authorization_module
from mod_editor.core.nfl2k5_audio_containment_fingerprints import (
    PcmContainmentInventory,
    PcmContainmentPolicy,
    SourcePcmContainmentError,
    SourcePcmCueInput,
    build_private_containment_inventory,
)
from mod_editor.core.nfl2k5_audio_origin_authorization import (
    AudioOriginAuthorizationError,
    AuthorizedPcm16Wav,
    MAX_PCM_BYTES,
    authorize_strict_pcm16_wav,
    require_authorized_pcm16_wav,
)
from mod_editor.core.nfl2k5_audio_source_fingerprints import (
    AudioSourceFingerprintInventory,
    SourceDerivedPcmError,
    SourcePcmMatch,
    StandalonePcmFingerprint,
)


SAMPLE_RATE = 32
SOURCE_SHA256 = hashlib.sha256(b"synthetic source xiso identity").hexdigest()
SOURCE_OWNER = "nfl2k5.audio.audo.o0003.c0001"


def _pcm(frame_count: int, *, seed: int) -> bytes:
    samples = []
    for frame in range(frame_count):
        value = ((frame * 977 + seed * 7_919) % 60_000) - 30_000
        samples.append(value or 1)
    return struct.pack(f"<{len(samples)}h", *samples)


def _wav(
    pcm16le: bytes,
    *,
    channels: int = 1,
    sample_rate: int = SAMPLE_RATE,
) -> bytes:
    block_align = channels * 2
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(pcm16le),
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        sample_rate * block_align,
        block_align,
        16,
        b"data",
        len(pcm16le),
    ) + pcm16le


def _source_inventories(source_pcm: bytes):
    frame_count = len(source_pcm) // 2
    digest = hashlib.sha256(source_pcm).hexdigest()
    row = StandalonePcmFingerprint(
        asset_id=SOURCE_OWNER,
        channels=1,
        sample_rate=SAMPLE_RATE,
        frame_count=frame_count,
        pcm_sha256=digest,
    )
    match = SourcePcmMatch(
        family="standalone",
        canonical_id=SOURCE_OWNER,
        owner_asset_ids=(SOURCE_OWNER,),
        channels=1,
        sample_rate=SAMPLE_RATE,
        frame_count=frame_count,
        pcm_sha256=digest,
    )
    exact = AudioSourceFingerprintInventory(
        source_sha256=SOURCE_SHA256,
        path=Path("/private/synthetic-fingerprints.json"),
        standalone=(row,),
        streaming_slots=(),
        by_asset_id=MappingProxyType({SOURCE_OWNER: match}),
        by_pcm_sha256=MappingProxyType({digest: (match,)}),
    )
    containment = build_private_containment_inventory(
        SOURCE_SHA256,
        PcmContainmentPolicy(short_anchor_shapes=()),
        (
            SourcePcmCueInput(
                owner_asset_ids=(SOURCE_OWNER,),
                channels=1,
                sample_rate=SAMPLE_RATE,
                frame_count=frame_count,
                pcm16le=source_pcm,
            ),
        ),
        expected_cue_count=1,
        expected_owner_count=1,
    )
    return exact, containment


def _authorize(candidate_pcm: bytes, exact, containment):
    return authorize_strict_pcm16_wav(
        _wav(candidate_pcm),
        target_channels=1,
        target_sample_rate=SAMPLE_RATE,
        target_frame_count=len(candidate_pcm) // 2,
        source_fingerprints=exact,
        containment_fingerprints=containment,
    )


class AudioOriginAuthorizationBehaviorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source_pcm = _pcm(96, seed=3)
        self.exact, self.containment = _source_inventories(self.source_pcm)

    def test_unchanged_source_is_rejected_by_full_pcm_inventory(self) -> None:
        with self.assertRaises(SourceDerivedPcmError):
            _authorize(self.source_pcm, self.exact, self.containment)

    def test_trim_padding_and_concatenation_are_rejected(self) -> None:
        candidates = {
            "middle trim": self.source_pcm[13 * 2:90 * 2],
            "silence padding": b"\0" * 10 + self.source_pcm + b"\0" * 14,
            "concatenation": _pcm(11, seed=41) + self.source_pcm + _pcm(7, seed=43),
        }
        for label, candidate in candidates.items():
            with self.subTest(label=label):
                with self.assertRaises(SourcePcmContainmentError):
                    _authorize(candidate, self.exact, self.containment)

    def test_user_authored_pcm_passes_and_returns_one_frozen_snapshot(self) -> None:
        authored = _pcm(96, seed=101)
        supplied_wav = _wav(authored)
        with mock.patch(
            "mod_editor.core.nfl2k5_audio_origin_authorization._parse_strict_pcm16_wav",
            wraps=authorization_module._parse_strict_pcm16_wav,
        ) as parser:
            authorized = authorize_strict_pcm16_wav(
                supplied_wav,
                target_channels=1,
                target_sample_rate=SAMPLE_RATE,
                target_frame_count=96,
                source_fingerprints=self.exact,
                containment_fingerprints=self.containment,
            )

        parser.assert_called_once()
        self.assertIs(authorized.wav_bytes, supplied_wav)
        self.assertEqual(authorized.wav_bytes, supplied_wav)
        self.assertEqual(authorized.pcm16le, authored)
        self.assertEqual(
            authorized.wav_sha256, hashlib.sha256(supplied_wav).hexdigest()
        )
        self.assertEqual(
            authorized.pcm_sha256, hashlib.sha256(authored).hexdigest()
        )
        with self.assertRaises(FrozenInstanceError):
            authorized.frame_count = 1
        self.assertIs(require_authorized_pcm16_wav(authorized), authorized)

    def test_both_origin_gates_receive_the_same_returned_pcm_object(self) -> None:
        authored = _pcm(96, seed=102)
        seen = []
        exact_method = AudioSourceFingerprintInventory.reject_exact_source_pcm
        containment_method = PcmContainmentInventory.reject_contained_source_pcm

        def exact_spy(inventory, pcm16le, **shape):
            seen.append(("exact", pcm16le))
            return exact_method(inventory, pcm16le, **shape)

        def containment_spy(inventory, pcm16le, **shape):
            seen.append(("containment", pcm16le))
            return containment_method(inventory, pcm16le, **shape)

        with mock.patch.object(
            AudioSourceFingerprintInventory,
            "reject_exact_source_pcm",
            exact_spy,
        ), mock.patch.object(
            PcmContainmentInventory,
            "reject_contained_source_pcm",
            containment_spy,
        ):
            authorized = _authorize(authored, self.exact, self.containment)

        self.assertEqual(tuple(label for label, _pcm_bytes in seen), (
            "exact", "containment",
        ))
        self.assertIs(seen[0][1], seen[1][1])
        self.assertIs(seen[0][1], authorized.pcm16le)

    def test_candidate_file_mutation_is_irrelevant_after_bytes_snapshot(self) -> None:
        authored = _pcm(96, seed=103)
        original_wav = _wav(authored)
        replacement_wav = _wav(_pcm(96, seed=107))
        with tempfile.TemporaryDirectory() as temporary:
            candidate_path = Path(temporary) / "candidate.wav"
            candidate_path.write_bytes(original_wav)
            immutable_snapshot = candidate_path.read_bytes()
            authorized = authorize_strict_pcm16_wav(
                immutable_snapshot,
                target_channels=1,
                target_sample_rate=SAMPLE_RATE,
                target_frame_count=96,
                source_fingerprints=self.exact,
                containment_fingerprints=self.containment,
            )
            candidate_path.write_bytes(replacement_wav)

        self.assertEqual(authorized.wav_bytes, original_wav)
        self.assertEqual(authorized.pcm16le, authored)
        self.assertNotEqual(authorized.wav_bytes, replacement_wav)


class AudioOriginAuthorizationFormatTests(unittest.TestCase):
    def setUp(self) -> None:
        source_pcm = _pcm(96, seed=5)
        self.exact, self.containment = _source_inventories(source_pcm)
        self.authored = _pcm(96, seed=109)

    def _call(self, payload: bytes, **shape):
        values = {
            "target_channels": 1,
            "target_sample_rate": SAMPLE_RATE,
            "target_frame_count": 96,
        }
        values.update(shape)
        return authorize_strict_pcm16_wav(
            payload,
            source_fingerprints=self.exact,
            containment_fingerprints=self.containment,
            **values,
        )

    def test_malformed_riff_metadata_and_trailing_bytes_fail_closed(self) -> None:
        canonical = _wav(self.authored)
        malformed = b"NOPE" + canonical[4:]

        fmt_payload = canonical[20:36]
        metadata_body = (
            b"WAVEfmt "
            + struct.pack("<I", 16)
            + fmt_payload
            + b"JUNK"
            + struct.pack("<I", 2)
            + b"xx"
            + b"data"
            + struct.pack("<I", len(self.authored))
            + self.authored
        )
        metadata = b"RIFF" + struct.pack("<I", len(metadata_body)) + metadata_body
        trailing = canonical + b"x"

        for label, payload in {
            "malformed RIFF": malformed,
            "metadata chunk": metadata,
            "trailing byte": trailing,
        }.items():
            with self.subTest(label=label):
                with self.assertRaises(AudioOriginAuthorizationError):
                    self._call(payload)

    def test_exact_target_shape_is_required(self) -> None:
        canonical = _wav(self.authored)
        for label, shape in {
            "channels": {"target_channels": 2},
            "sample rate": {"target_sample_rate": SAMPLE_RATE + 1},
            "frame count": {"target_frame_count": 95},
        }.items():
            with self.subTest(label=label):
                with self.assertRaises(AudioOriginAuthorizationError):
                    self._call(canonical, **shape)

    def test_mutable_input_and_pcm_larger_than_64_mib_are_refused(self) -> None:
        with self.assertRaisesRegex(
            AudioOriginAuthorizationError, "immutable bytes"
        ):
            self._call(bytearray(_wav(self.authored)))

        oversized_frames = MAX_PCM_BYTES // 2 + 1
        with self.assertRaisesRegex(AudioOriginAuthorizationError, "64 MiB"):
            self._call(
                _wav(self.authored),
                target_frame_count=oversized_frames,
            )

        exact_stereo_frames = MAX_PCM_BYTES // 4
        self.assertEqual(
            authorization_module._target_shape(
                2, 192_000, exact_stereo_frames
            ),
            (2, 192_000, exact_stereo_frames, MAX_PCM_BYTES),
        )


class AudioOriginAuthorizationSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source_pcm = _pcm(96, seed=7)
        self.exact, self.containment = _source_inventories(self.source_pcm)
        self.authored = _pcm(96, seed=113)

    def test_mismatched_inventory_source_bindings_fail_before_parsing(self) -> None:
        wrong = replace(
            self.containment,
            source_binding_sha256="0" * 64,
        )
        with mock.patch(
            "mod_editor.core.nfl2k5_audio_origin_authorization._parse_strict_pcm16_wav"
        ) as parser:
            with self.assertRaisesRegex(
                AudioOriginAuthorizationError, "different source XISOs"
            ):
                authorize_strict_pcm16_wav(
                    _wav(self.authored),
                    target_channels=1,
                    target_sample_rate=SAMPLE_RATE,
                    target_frame_count=96,
                    source_fingerprints=self.exact,
                    containment_fingerprints=wrong,
                )
        parser.assert_not_called()

    def test_inventory_subclasses_cannot_override_the_required_gates(self) -> None:
        class ExactBypass(AudioSourceFingerprintInventory):
            def reject_exact_source_pcm(self, *args, **kwargs):
                del args, kwargs
                return None

        class ContainmentBypass(PcmContainmentInventory):
            def reject_contained_source_pcm(self, *args, **kwargs):
                del args, kwargs
                return None

        fake_exact = ExactBypass(
            self.exact.source_sha256,
            self.exact.path,
            self.exact.standalone,
            self.exact.streaming_slots,
            self.exact.by_asset_id,
            self.exact.by_pcm_sha256,
        )
        fake_containment = ContainmentBypass(
            self.containment.source_binding_sha256,
            self.containment.policy,
            self.containment.source_cue_count,
            self.containment.source_owner_ids,
            self.containment.all_zero_owner_ids,
            self.containment.fingerprints,
            self.containment._by_shape_checksum,
        )
        for label, exact, containment in (
            ("exact subclass", fake_exact, self.containment),
            ("containment subclass", self.exact, fake_containment),
        ):
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                    AudioOriginAuthorizationError, "validated private"
                ):
                    authorize_strict_pcm16_wav(
                        _wav(self.authored),
                        target_channels=1,
                        target_sample_rate=SAMPLE_RATE,
                        target_frame_count=96,
                        source_fingerprints=exact,
                        containment_fingerprints=containment,
                    )

    def test_public_type_and_reflective_lookalike_are_not_authority(self) -> None:
        with self.assertRaisesRegex(TypeError, "issued only"):
            AuthorizedPcm16Wav()

        authorized = _authorize(
            self.authored, self.exact, self.containment
        )
        forged = object.__new__(AuthorizedPcm16Wav)
        for name in (
            "wav_bytes", "pcm16le", "channels", "sample_rate", "frame_count",
            "wav_sha256", "pcm_sha256", "source_sha256",
            "containment_binding_sha256", "containment_policy_sha256",
        ):
            object.__setattr__(forged, name, getattr(authorized, name))
        object.__setattr__(forged, "_authorization_seal", b"\0" * 32)
        with self.assertRaisesRegex(
            AudioOriginAuthorizationError, "authorization seal"
        ):
            require_authorized_pcm16_wav(forged)

        incomplete = object.__new__(AuthorizedPcm16Wav)
        with self.assertRaisesRegex(
            AudioOriginAuthorizationError, "complete module-issued"
        ):
            require_authorized_pcm16_wav(incomplete)

    def test_malformed_inventory_digest_is_normalized(self) -> None:
        malformed = replace(self.exact, source_sha256="not-a-sha")
        with self.assertRaisesRegex(
            AudioOriginAuthorizationError, "invalid exact-inventory"
        ):
            authorize_strict_pcm16_wav(
                _wav(self.authored),
                target_channels=1,
                target_sample_rate=SAMPLE_RATE,
                target_frame_count=96,
                source_fingerprints=malformed,
                containment_fingerprints=self.containment,
            )


if __name__ == "__main__":
    unittest.main()

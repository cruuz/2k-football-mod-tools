"""Cross-family retail-packet safety tests for APF shareable audio edits."""

from __future__ import annotations

import hashlib
import struct
import unittest
from unittest.mock import patch

from mod_editor.apf_studio.build import ApfBuildService, BuildError
from mod_editor.apf_studio.session import ApfSession, SessionError
import apf_audo_exact_slot
import apf_ausb_exact_slot


def _packet(fill: int) -> bytes:
    packet = bytearray([fill] * 0x800)
    struct.pack_into(">I", packet, 0, 0x08000000)
    return bytes(packet)


def _fingerprints(
    domain: str,
    payload: bytes,
    *,
    payload_occurrences: int,
) -> apf_audo_exact_slot.SourceAudioFingerprints:
    return apf_audo_exact_slot.SourceAudioFingerprints(
        domain=domain,
        payload_sha256s=frozenset({hashlib.sha256(payload).hexdigest()}),
        packet_sha256s=frozenset(
            hashlib.sha256(payload[offset : offset + 0x800]).digest()
            for offset in range(0, len(payload), 0x800)
        ),
        payload_occurrence_count=payload_occurrences,
        packet_occurrence_count=len(payload) // 0x800,
    )


class ApfCrossDomainAudioSafetyTests(unittest.TestCase):
    def _session(
        self,
        audo: apf_audo_exact_slot.SourceAudioFingerprints,
        ausb: apf_audo_exact_slot.SourceAudioFingerprints,
    ) -> ApfSession:
        session = ApfSession.__new__(ApfSession)
        session._audo_source_fingerprints = audo
        session._ausb_source_fingerprints = ausb
        return session

    def test_ausb_source_packet_cannot_enter_an_audo_replacement(self) -> None:
        candidate = _packet(0x21) + _packet(0x22)
        safe_audo = _packet(0x31) + _packet(0x32)
        ausb_source = _packet(0x21) + _packet(0x41)
        session = self._session(
            _fingerprints(
                apf_audo_exact_slot.SOURCE_AUDIO_DOMAIN,
                safe_audo,
                payload_occurrences=apf_audo_exact_slot.EXPECTED_STANDALONE_AUDO_COUNT,
            ),
            _fingerprints(
                apf_ausb_exact_slot.SOURCE_AUDIO_DOMAIN,
                ausb_source,
                payload_occurrences=apf_ausb_exact_slot.EXPECTED_CANONICAL_RANGE_COUNT,
            ),
        )
        with (
            patch.object(
                apf_ausb_exact_slot,
                "EXPECTED_UNIQUE_SOURCE_PAYLOAD_HASH_COUNT",
                1,
            ),
            self.assertRaisesRegex(SessionError, "reuses a complete 0x800-byte"),
        ):
            session._reject_any_source_audio_reuse(candidate)

    def test_audo_source_packet_cannot_enter_an_ausb_replacement(self) -> None:
        candidate = _packet(0x51) + _packet(0x52)
        audo_source = _packet(0x51) + _packet(0x61)
        safe_ausb = _packet(0x71) + _packet(0x72)
        session = self._session(
            _fingerprints(
                apf_audo_exact_slot.SOURCE_AUDIO_DOMAIN,
                audo_source,
                payload_occurrences=apf_audo_exact_slot.EXPECTED_STANDALONE_AUDO_COUNT,
            ),
            _fingerprints(
                apf_ausb_exact_slot.SOURCE_AUDIO_DOMAIN,
                safe_ausb,
                payload_occurrences=apf_ausb_exact_slot.EXPECTED_CANONICAL_RANGE_COUNT,
            ),
        )
        with self.assertRaisesRegex(SessionError, "reuses a complete 0x800-byte"):
            session._reject_any_source_audio_reuse(candidate)

    def test_independently_authored_packets_clear_both_source_domains(self) -> None:
        candidate = _packet(0x11) + _packet(0x12)
        session = self._session(
            _fingerprints(
                apf_audo_exact_slot.SOURCE_AUDIO_DOMAIN,
                _packet(0x31) + _packet(0x32),
                payload_occurrences=apf_audo_exact_slot.EXPECTED_STANDALONE_AUDO_COUNT,
            ),
            _fingerprints(
                apf_ausb_exact_slot.SOURCE_AUDIO_DOMAIN,
                _packet(0x41) + _packet(0x42),
                payload_occurrences=apf_ausb_exact_slot.EXPECTED_CANONICAL_RANGE_COUNT,
            ),
        )
        with patch.object(
            apf_ausb_exact_slot,
            "EXPECTED_UNIQUE_SOURCE_PAYLOAD_HASH_COUNT",
            1,
        ):
            session._reject_any_source_audio_reuse(candidate)

    def test_build_gate_also_rejects_cross_domain_source_packets(self) -> None:
        candidate = _packet(0x21) + _packet(0x22)
        service = ApfBuildService.__new__(ApfBuildService)
        service._audo_source_fingerprints = _fingerprints(
            apf_audo_exact_slot.SOURCE_AUDIO_DOMAIN,
            _packet(0x31) + _packet(0x32),
            payload_occurrences=apf_audo_exact_slot.EXPECTED_STANDALONE_AUDO_COUNT,
        )
        service._ausb_source_fingerprints = _fingerprints(
            apf_ausb_exact_slot.SOURCE_AUDIO_DOMAIN,
            _packet(0x21) + _packet(0x41),
            payload_occurrences=apf_ausb_exact_slot.EXPECTED_CANONICAL_RANGE_COUNT,
        )
        with (
            patch.object(
                apf_ausb_exact_slot,
                "EXPECTED_UNIQUE_SOURCE_PAYLOAD_HASH_COUNT",
                1,
            ),
            self.assertRaisesRegex(BuildError, "reuses a complete 0x800-byte"),
        ):
            service._reject_any_source_audio_reuse(candidate)


if __name__ == "__main__":
    unittest.main()

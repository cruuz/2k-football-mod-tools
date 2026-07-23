"""In-memory source-origin authorization for NFL 2K5 replacement audio.

The final encoder must consume the same immutable bytes that passed the
private source-origin checks.  This module therefore accepts bytes, not a
path, parses one canonical PCM16 WAV exactly once, checks its owned PCM
snapshot against both private inventories, and returns a frozen authorization
object containing the only snapshots a later encoder should consume.

No source payload, fingerprint value, or game byte is embedded here.  The
returned object is deliberately an in-memory hand-off, not a serializable
project or release artifact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import hmac
import secrets
import struct
from typing import Callable

from .errors import ValidationError
from .nfl2k5_audio_containment_fingerprints import (
    PcmContainmentInventory,
    PcmContainmentPolicy,
    PcmContainmentProgress,
)
from .nfl2k5_audio_source_fingerprints import AudioSourceFingerprintInventory


MAX_PCM_BYTES = 64 * 1024 * 1024
MAX_WAV_BYTES = MAX_PCM_BYTES + 44
MAX_SAMPLE_RATE = 192_000

_CANONICAL_WAV_HEADER = struct.Struct("<4sI4s4sIHHIIHH4sI")
_AUTHORIZATION_SEAL_KEY = secrets.token_bytes(32)
_AUTHORIZATION_SEAL_CONTEXT = b"2k5-mod-studio/audio-origin-authorization/v1\0"


class AudioOriginAuthorizationError(ValidationError):
    """A replacement cannot cross the final in-memory audio boundary."""


@dataclass(frozen=True, slots=True, init=False)
class AuthorizedPcm16Wav:
    """Owned immutable bytes approved for one exact target PCM shape.

    ``wav_bytes`` is byte-for-byte identical to the caller's immutable input.
    ``pcm16le`` is an owned immutable slice of its data chunk.  A later encoder
    must use one of these fields directly instead of reopening an input path or
    trusting a cached boolean verdict.
    """

    wav_bytes: bytes
    pcm16le: bytes
    channels: int
    sample_rate: int
    frame_count: int
    wav_sha256: str
    pcm_sha256: str
    source_sha256: str
    containment_binding_sha256: str
    containment_policy_sha256: str
    _authorization_seal: bytes = field(repr=False, compare=False)

    def __new__(cls, *args: object, **kwargs: object) -> "AuthorizedPcm16Wav":
        del args, kwargs
        raise TypeError(
            "AuthorizedPcm16Wav is issued only by authorize_strict_pcm16_wav"
        )


@dataclass(frozen=True, slots=True)
class _ParsedStrictPcm16Wav:
    wav_bytes: bytes
    pcm16le: bytes
    channels: int
    sample_rate: int
    frame_count: int


CancellationCheck = Callable[[], bool]
ContainmentProgressSink = Callable[[PcmContainmentProgress], None]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AudioOriginAuthorizationError(message)


def _target_shape(
    channels: object,
    sample_rate: object,
    frame_count: object,
) -> tuple[int, int, int, int]:
    _require(
        type(channels) is int and channels in (1, 2),
        "Target PCM channels must be 1 or 2",
    )
    _require(
        type(sample_rate) is int and 1 <= sample_rate <= MAX_SAMPLE_RATE,
        f"Target PCM sample rate must be between 1 and {MAX_SAMPLE_RATE:,} Hz",
    )
    _require(
        type(frame_count) is int and frame_count > 0,
        "Target PCM frame count must be a positive integer",
    )
    pcm_bytes = channels * frame_count * 2
    _require(
        pcm_bytes <= MAX_PCM_BYTES,
        f"Target PCM exceeds the {MAX_PCM_BYTES // (1024 * 1024)} MiB bound",
    )
    return channels, sample_rate, frame_count, pcm_bytes


def _sha256_text(value: object, label: str) -> str:
    _require(
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value),
        f"Authorized PCM has an invalid {label}",
    )
    return value


def _authorization_seal(
    *,
    channels: int,
    sample_rate: int,
    frame_count: int,
    wav_sha256: str,
    pcm_sha256: str,
    source_sha256: str,
    containment_binding_sha256: str,
    containment_policy_sha256: str,
) -> bytes:
    """Authenticate the small immutable hand-off metadata for this process."""

    message = b"".join((
        _AUTHORIZATION_SEAL_CONTEXT,
        struct.pack("<III", channels, sample_rate, frame_count),
        bytes.fromhex(wav_sha256),
        bytes.fromhex(pcm_sha256),
        bytes.fromhex(source_sha256),
        bytes.fromhex(containment_binding_sha256),
        bytes.fromhex(containment_policy_sha256),
    ))
    return hmac.digest(_AUTHORIZATION_SEAL_KEY, message, "sha256")


def _parse_strict_pcm16_wav(
    wav_bytes: bytes,
    *,
    target_channels: int,
    target_sample_rate: int,
    target_frame_count: int,
) -> _ParsedStrictPcm16Wav:
    """Parse exactly one canonical ``fmt`` + ``data`` RIFF/WAVE snapshot."""

    _require(
        type(wav_bytes) is bytes,
        "Replacement WAV must be supplied as immutable bytes",
    )
    channels, sample_rate, frame_count, expected_pcm_bytes = _target_shape(
        target_channels,
        target_sample_rate,
        target_frame_count,
    )
    _require(
        44 <= len(wav_bytes) <= MAX_WAV_BYTES,
        "Replacement WAV size is outside the bounded canonical input limit",
    )

    (
        riff_id,
        riff_size,
        wave_id,
        fmt_id,
        fmt_size,
        format_tag,
        wav_channels,
        wav_sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        data_id,
        data_size,
    ) = _CANONICAL_WAV_HEADER.unpack_from(wav_bytes)

    _require(
        riff_id == b"RIFF" and wave_id == b"WAVE",
        "Replacement is not a little-endian RIFF/WAVE file",
    )
    _require(
        riff_size + 8 == len(wav_bytes),
        "RIFF size does not equal the complete replacement WAV; trailing bytes are forbidden",
    )
    _require(
        fmt_id == b"fmt " and data_id == b"data" and fmt_size == 16,
        "Strict WAV must contain exactly a 16-byte fmt chunk followed by data; remove metadata chunks",
    )
    _require(format_tag == 1, "WAV must use integer PCM format tag 1")
    _require(
        wav_channels == channels,
        f"WAV must have exactly {channels} channel(s)",
    )
    _require(
        wav_sample_rate == sample_rate,
        f"WAV must be exactly {sample_rate:,} Hz",
    )
    expected_block_align = channels * 2
    _require(
        bits_per_sample == 16
        and block_align == expected_block_align
        and byte_rate == sample_rate * expected_block_align,
        "WAV must be canonical little-endian PCM16",
    )
    _require(
        data_size == expected_pcm_bytes,
        f"WAV must contain exactly {frame_count:,} PCM frame(s)",
    )
    _require(
        len(wav_bytes) == 44 + data_size and riff_size == 36 + data_size,
        "Strict WAV chunks do not exactly tile the input; metadata and trailing bytes are forbidden",
    )

    # Slicing immutable bytes creates an owned immutable PCM snapshot.  Both
    # source checks and the eventual encoder hand-off below share these exact
    # values; no caller-owned mutable view survives authorization.
    pcm16le = wav_bytes[44:]
    return _ParsedStrictPcm16Wav(
        wav_bytes=wav_bytes,
        pcm16le=pcm16le,
        channels=channels,
        sample_rate=sample_rate,
        frame_count=frame_count,
    )


def require_authorized_pcm16_wav(
    value: AuthorizedPcm16Wav,
) -> AuthorizedPcm16Wav:
    """Validate a module-issued hand-off before an encoder consumes it.

    Python object types are not security capabilities by themselves: callers
    can invoke ``object.__new__`` or bypass a frozen dataclass with reflection.
    The process-local seal makes such lookalikes fail closed.  The seal is
    intentionally not portable across processes or suitable for serialization.
    """

    _require(
        type(value) is AuthorizedPcm16Wav,
        "Final audio encoding requires a module-issued authorization token",
    )
    try:
        wav_bytes = value.wav_bytes
        pcm16le = value.pcm16le
        value_channels = value.channels
        value_sample_rate = value.sample_rate
        value_frame_count = value.frame_count
        value_wav_sha256 = value.wav_sha256
        value_pcm_sha256 = value.pcm_sha256
        value_source_sha256 = value.source_sha256
        value_binding_sha256 = value.containment_binding_sha256
        value_policy_sha256 = value.containment_policy_sha256
        value_seal = value._authorization_seal
    except AttributeError as exc:
        raise AudioOriginAuthorizationError(
            "Final audio encoding requires a complete module-issued authorization token"
        ) from exc
    channels, sample_rate, frame_count, expected_pcm_bytes = _target_shape(
        value_channels,
        value_sample_rate,
        value_frame_count,
    )
    _require(
        type(wav_bytes) is bytes and type(pcm16le) is bytes,
        "Authorized PCM snapshots must remain immutable bytes",
    )
    _require(
        len(pcm16le) == expected_pcm_bytes,
        "Authorized PCM byte length no longer matches its shape",
    )
    _require(
        len(wav_bytes) == 44 + expected_pcm_bytes
        and wav_bytes[44:] == pcm16le,
        "Authorized WAV and PCM snapshots no longer describe the same bytes",
    )
    wav_sha256 = _sha256_text(value_wav_sha256, "WAV SHA-256")
    pcm_sha256 = _sha256_text(value_pcm_sha256, "PCM SHA-256")
    source_sha256 = _sha256_text(value_source_sha256, "source SHA-256")
    binding_sha256 = _sha256_text(
        value_binding_sha256,
        "containment source binding SHA-256",
    )
    policy_sha256 = _sha256_text(
        value_policy_sha256,
        "containment policy SHA-256",
    )
    _require(
        source_sha256 == binding_sha256,
        "Authorized PCM inventories no longer share one source binding",
    )
    _require(
        hmac.compare_digest(hashlib.sha256(wav_bytes).hexdigest(), wav_sha256)
        and hmac.compare_digest(
            hashlib.sha256(pcm16le).hexdigest(), pcm_sha256
        ),
        "Authorized PCM snapshot digest no longer matches its bytes",
    )
    expected_seal = _authorization_seal(
        channels=channels,
        sample_rate=sample_rate,
        frame_count=frame_count,
        wav_sha256=wav_sha256,
        pcm_sha256=pcm_sha256,
        source_sha256=source_sha256,
        containment_binding_sha256=binding_sha256,
        containment_policy_sha256=policy_sha256,
    )
    _require(
        type(value_seal) is bytes
        and hmac.compare_digest(value_seal, expected_seal),
        "Final audio encoding requires a valid module-issued authorization seal",
    )
    return value


def authorize_strict_pcm16_wav(
    wav_bytes: bytes,
    *,
    target_channels: int,
    target_sample_rate: int,
    target_frame_count: int,
    source_fingerprints: AudioSourceFingerprintInventory,
    containment_fingerprints: PcmContainmentInventory,
    cancel: CancellationCheck | None = None,
    progress: ContainmentProgressSink | None = None,
) -> AuthorizedPcm16Wav:
    """Authorize one immutable WAV snapshot against both private inventories.

    Exact full-cue matching runs first, followed by exact indexed-window
    containment.  Their typed source-derived errors intentionally propagate as
    user-facing refusals.  A successful return is the authorization token and
    byte hand-off; callers must never reduce it to a boolean.
    """

    _require(
        type(source_fingerprints) is AudioSourceFingerprintInventory
        and source_fingerprints.private is True
        and source_fingerprints.shareable is False,
        "A validated private exact-PCM source inventory is required",
    )
    _require(
        type(containment_fingerprints) is PcmContainmentInventory
        and type(containment_fingerprints.policy) is PcmContainmentPolicy
        and containment_fingerprints.private is True
        and containment_fingerprints.shareable is False,
        "A validated private PCM-containment inventory is required",
    )
    source_sha256 = _sha256_text(
        source_fingerprints.source_sha256, "exact-inventory source SHA-256"
    )
    containment_binding_sha256 = _sha256_text(
        containment_fingerprints.source_binding_sha256,
        "containment-inventory source SHA-256",
    )
    containment_policy_sha256 = _sha256_text(
        containment_fingerprints.policy.sha256,
        "containment policy SHA-256",
    )
    _require(
        source_sha256 == containment_binding_sha256,
        "Exact and containment inventories belong to different source XISOs",
    )

    parsed = _parse_strict_pcm16_wav(
        wav_bytes,
        target_channels=target_channels,
        target_sample_rate=target_sample_rate,
        target_frame_count=target_frame_count,
    )

    source_fingerprints.reject_exact_source_pcm(
        parsed.pcm16le,
        channels=parsed.channels,
        sample_rate=parsed.sample_rate,
        frame_count=parsed.frame_count,
    )
    containment_fingerprints.reject_contained_source_pcm(
        parsed.pcm16le,
        channels=parsed.channels,
        sample_rate=parsed.sample_rate,
        frame_count=parsed.frame_count,
        cancel=cancel,
        progress=progress,
    )

    # Mint only here, after both source-origin gates return successfully.  The
    # public dataclass constructor is disabled and consumers must validate the
    # process-local seal with ``require_authorized_pcm16_wav``.
    wav_sha256 = hashlib.sha256(parsed.wav_bytes).hexdigest()
    pcm_sha256 = hashlib.sha256(parsed.pcm16le).hexdigest()
    seal = _authorization_seal(
        channels=parsed.channels,
        sample_rate=parsed.sample_rate,
        frame_count=parsed.frame_count,
        wav_sha256=wav_sha256,
        pcm_sha256=pcm_sha256,
        source_sha256=source_sha256,
        containment_binding_sha256=containment_binding_sha256,
        containment_policy_sha256=containment_policy_sha256,
    )
    value = object.__new__(AuthorizedPcm16Wav)
    for name, item in (
        ("wav_bytes", parsed.wav_bytes),
        ("pcm16le", parsed.pcm16le),
        ("channels", parsed.channels),
        ("sample_rate", parsed.sample_rate),
        ("frame_count", parsed.frame_count),
        ("wav_sha256", wav_sha256),
        ("pcm_sha256", pcm_sha256),
        ("source_sha256", source_sha256),
        ("containment_binding_sha256", containment_binding_sha256),
        ("containment_policy_sha256", containment_policy_sha256),
        ("_authorization_seal", seal),
    ):
        object.__setattr__(value, name, item)
    return value


__all__ = [
    "AudioOriginAuthorizationError",
    "AuthorizedPcm16Wav",
    "MAX_PCM_BYTES",
    "MAX_SAMPLE_RATE",
    "MAX_WAV_BYTES",
    "authorize_strict_pcm16_wav",
    "require_authorized_pcm16_wav",
]

"""Transactional, retail-free composition for NFL 2K5 AUSB slot edits.

This module is the narrow hand-off between source-origin authorization and a
future XISO builder.  It accepts no paths and reads no game/cache data.  The
only input payload is an immutable strict-WAV snapshot that the caller has
just authorized.  Structural conformance to :class:`AuthorizedWavSnapshot`
is *not* proof of authorization; ``_compile_authorized_streaming_slot`` is an
internal API and must remain immediately downstream of the origin gate.

Successful compilation produces immutable, ordered, per-pack payload slices.
Failures return nothing and erase the caller-invisible staging buffer.  No
retail bytes are copied into the result: every payload byte is encoded from
the user's replacement PCM.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
import re
from typing import Callable, Protocol

from .nfl2k5_ausb_fixed_slots import (
    CanonicalStreamingSlot,
    LogicalStreamingOwner,
    Nfl2k5AusbFixedSlotError,
    StreamingEncodeProgress,
    StreamingPackSpan,
    encode_strict_pcm16_wav,
    streaming_slot_write_plan,
    verify_xbox_ima_stream,
)
from .nfl2k5_audio_origin_authorization import (
    AuthorizedPcm16Wav,
    require_authorized_pcm16_wav,
)


COMPOSITION_SCHEMA = "2k5_mod_studio_ausb_compiled_slot/v1"
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_PACK_NAMES = "0123456789ABCDEF"


class Nfl2k5AusbBuildAdapterError(Nfl2k5AusbFixedSlotError):
    """An authorized snapshot, physical plan, or compiled edit is inconsistent."""


class AuthorizedWavSnapshot(Protocol):
    """Read-only shape consumed immediately after source-origin authorization.

    The existing ``AuthorizedPcm16Wav`` object satisfies this protocol.  The
    protocol deliberately exposes only immutable authored bytes, proven PCM
    shape, and their hashes.  It neither grants nor attempts authorization.
    """

    @property
    def wav_bytes(self) -> bytes: ...

    @property
    def pcm16le(self) -> bytes: ...

    @property
    def channels(self) -> int: ...

    @property
    def sample_rate(self) -> int: ...

    @property
    def frame_count(self) -> int: ...

    @property
    def wav_sha256(self) -> str: ...

    @property
    def pcm_sha256(self) -> str: ...


@dataclass(frozen=True, slots=True)
class CompiledStreamingPackSlice:
    """One immutable authored payload slice for one exact pack destination."""

    pack_name: str
    pack_ordinal: int
    pack_offset: int
    payload_offset: int
    payload: bytes
    payload_sha256: str

    @property
    def length(self) -> int:
        return len(self.payload)


@dataclass(frozen=True, slots=True)
class CompiledStreamingSlotEdit:
    """One physical AUSB edit shared by its canonical and logical asset IDs."""

    canonical_id: str
    external_outer_index: int
    external_outer_id: int
    range_start: int
    range_end: int
    channels: int
    sample_rate: int
    frame_count: int
    owners: tuple[LogicalStreamingOwner, ...]
    affected_asset_ids: tuple[str, ...]
    shared_owner_effect: bool
    pack_slices: tuple[CompiledStreamingPackSlice, ...]
    input_wav_sha256: str
    input_pcm_sha256: str
    encoded_sha256: str
    decoded_pcm_sha256: str
    composition_sha256: str

    @property
    def encoded_size(self) -> int:
        return self.range_end - self.range_start

    @property
    def owner_effect_summary(self) -> str:
        count = len(self.affected_asset_ids)
        if count == 1:
            return f"Changes 1 logical audio asset: {self.affected_asset_ids[0]}"
        return (
            f"Changes {count} aliased logical audio assets together: "
            + ", ".join(self.affected_asset_ids)
        )

    def resolve_asset_id(self, asset_id: str) -> CompiledStreamingSlotEdit:
        """Resolve the canonical ID or any owner alias to this one result."""

        _require(
            type(asset_id) is str
            and (
                asset_id == self.canonical_id
                or asset_id in self.affected_asset_ids
            ),
            f"Compiled AUSB slot does not own asset ID: {asset_id!r}",
        )
        return self


ProgressCallback = Callable[[StreamingEncodeProgress], None]
CancellationCallback = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class _SnapshotValues:
    wav_bytes: bytes
    pcm16le: bytes
    channels: int
    sample_rate: int
    frame_count: int
    wav_sha256: str
    pcm_sha256: str


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Nfl2k5AusbBuildAdapterError(message)


def _require_sha256(value: object, label: str) -> str:
    _require(
        type(value) is str and _SHA256_RE.fullmatch(value) is not None,
        f"{label} must be a lowercase SHA-256 digest",
    )
    return value


def _validate_owner(owner: object) -> LogicalStreamingOwner:
    _require(
        type(owner) is LogicalStreamingOwner,
        "Streaming slot owner metadata has the wrong type",
    )
    assert type(owner) is LogicalStreamingOwner
    _require(
        type(owner.asset_id) is str
        and bool(owner.asset_id)
        and type(owner.descriptor_asset_id) is str
        and bool(owner.descriptor_asset_id)
        and type(owner.descriptor_outer_index) is int
        and owner.descriptor_outer_index >= 0
        and type(owner.descriptor_chunk_index) is int
        and owner.descriptor_chunk_index >= 0
        and type(owner.range_index) is int
        and owner.range_index >= 0,
        "Streaming slot owner metadata is invalid",
    )
    expected_descriptor_id = (
        "nfl2k5.audio.ausb."
        f"o{owner.descriptor_outer_index:04d}.c{owner.descriptor_chunk_index:04d}"
    )
    _require(
        owner.descriptor_asset_id == expected_descriptor_id
        and owner.asset_id
        == f"{expected_descriptor_id}.r{owner.range_index:05d}",
        "Streaming slot owner IDs disagree with their descriptor/range metadata",
    )
    return owner


def _validated_slot_identity(
    slot: CanonicalStreamingSlot,
) -> tuple[LogicalStreamingOwner, ...]:
    _require(
        type(slot) is CanonicalStreamingSlot,
        "A reviewed canonical streaming slot is required",
    )
    _require(
        type(slot.range_start) is int
        and type(slot.range_end) is int
        and 0 <= slot.range_start < slot.range_end,
        "Streaming slot range is invalid",
    )
    _require(
        type(slot.external_outer_index) is int
        and slot.external_outer_index >= 0
        and type(slot.external_outer_id) is int
        and 0 <= slot.external_outer_id <= 0xFFFFFFFF,
        "Streaming slot external identity is invalid",
    )
    expected_canonical_id = (
        "nfl2k5.audio.ausb.physical."
        f"o{slot.external_outer_index:04d}.s{slot.range_start:010x}."
        f"n{slot.range_end - slot.range_start:010x}"
    )
    _require(
        type(slot.canonical_id) is str
        and slot.canonical_id == expected_canonical_id,
        "Streaming slot canonical ID disagrees with its physical identity",
    )
    _require(
        type(slot.owners) is tuple and len(slot.owners) in (1, 2),
        "Streaming slot must have one owner or one reviewed two-owner alias",
    )
    owners = tuple(_validate_owner(owner) for owner in slot.owners)
    owner_ids = tuple(owner.asset_id for owner in owners)
    descriptor_ids = tuple(owner.descriptor_asset_id for owner in owners)
    _require(
        len(set(owner_ids)) == len(owner_ids)
        and len(set(descriptor_ids)) == len(descriptor_ids),
        "Streaming slot repeats a logical owner or descriptor",
    )
    _require(
        owner_ids == tuple(sorted(owner_ids)),
        "Streaming slot logical owners are not in canonical order",
    )
    _require(
        slot.canonical_id not in owner_ids,
        "Streaming canonical ID collides with a logical owner",
    )
    return owners


def _validated_write_plan(
    slot: CanonicalStreamingSlot,
) -> tuple[StreamingPackSpan, ...]:
    """Validate both payload tiling and unambiguous physical destination order."""

    plan = streaming_slot_write_plan(slot)
    _require(
        type(plan) is tuple and len(plan) in (1, 2),
        "AUSB write plan must contain exactly one span or one two-pack seam",
    )
    payload_cursor = 0
    prior: StreamingPackSpan | None = None
    seen_pack_names: set[str] = set()
    ordinal_names: dict[int, str] = {}
    name_ordinals: dict[str, int] = {}

    for span in plan:
        _require(
            type(span) is StreamingPackSpan
            and type(span.pack_name) is str
            and type(span.pack_ordinal) is int
            and 0 <= span.pack_ordinal < len(_PACK_NAMES)
            and span.pack_name == _PACK_NAMES[span.pack_ordinal]
            and type(span.pack_offset) is int
            and span.pack_offset >= 0
            and type(span.length) is int
            and span.length > 0
            and type(span.payload_offset) is int,
            "AUSB write plan contains malformed pack metadata",
        )
        _require(
            span.payload_offset == payload_cursor,
            "AUSB payload slices are reordered, overlapping, or gapped",
        )
        _require(
            ordinal_names.get(span.pack_ordinal, span.pack_name) == span.pack_name
            and name_ordinals.get(span.pack_name, span.pack_ordinal)
            == span.pack_ordinal,
            "AUSB write plan disagrees about pack identity",
        )
        ordinal_names[span.pack_ordinal] = span.pack_name
        name_ordinals[span.pack_name] = span.pack_ordinal

        if prior is not None:
            _require(
                span.pack_ordinal == prior.pack_ordinal + 1
                and span.pack_name != prior.pack_name
                and span.pack_offset == 0
                and prior.pack_name not in seen_pack_names
                and span.pack_name not in seen_pack_names,
                "AUSB seam must continue at byte zero of the next ordered pack",
            )
            seen_pack_names.add(prior.pack_name)
        prior = span
        payload_cursor += span.length

    _require(
        payload_cursor == slot.encoded_size,
        "AUSB payload slices do not cover the complete fixed allocation",
    )
    return plan


def _snapshot_values(
    snapshot: AuthorizedWavSnapshot,
    slot: CanonicalStreamingSlot,
) -> _SnapshotValues:
    # Structural Protocol conformance is not authorization.  Only the origin
    # module can validate its process-local seal, and it must do so before any
    # snapshot field is consumed by the encoder boundary.
    issued: AuthorizedPcm16Wav = require_authorized_pcm16_wav(
        snapshot  # type: ignore[arg-type]
    )
    try:
        wav_bytes = issued.wav_bytes
        pcm16le = issued.pcm16le
        channels = issued.channels
        sample_rate = issued.sample_rate
        frame_count = issued.frame_count
        wav_sha256 = issued.wav_sha256
        pcm_sha256 = issued.pcm_sha256
    except (AttributeError, TypeError) as exc:
        raise Nfl2k5AusbBuildAdapterError(
            "Internal AUSB compiler requires the just-authorized WAV snapshot object"
        ) from exc

    _require(
        type(wav_bytes) is bytes and type(pcm16le) is bytes,
        "Authorized WAV and PCM snapshots must be immutable bytes",
    )
    _require(
        type(channels) is int
        and type(sample_rate) is int
        and type(frame_count) is int,
        "Authorized WAV snapshot shape must use exact integers",
    )
    _require(
        (channels, sample_rate, frame_count)
        == (slot.channels, slot.sample_rate, slot.frame_count),
        "Authorized WAV snapshot shape differs from its canonical streaming slot",
    )
    expected_pcm_size = slot.frame_count * slot.channels * 2
    _require(
        len(wav_bytes) == 44 + expected_pcm_size
        and len(pcm16le) == expected_pcm_size
        and wav_bytes[44:] == pcm16le,
        "Authorized WAV bytes and owned PCM snapshot are not identical",
    )
    wav_sha256 = _require_sha256(wav_sha256, "Authorized WAV hash")
    pcm_sha256 = _require_sha256(pcm_sha256, "Authorized PCM hash")
    _require(
        hashlib.sha256(wav_bytes).hexdigest() == wav_sha256,
        "Authorized WAV snapshot hash changed before AUSB compilation",
    )
    _require(
        hashlib.sha256(pcm16le).hexdigest() == pcm_sha256,
        "Authorized PCM snapshot hash changed before AUSB compilation",
    )
    return _SnapshotValues(
        wav_bytes=wav_bytes,
        pcm16le=pcm16le,
        channels=channels,
        sample_rate=sample_rate,
        frame_count=frame_count,
        wav_sha256=wav_sha256,
        pcm_sha256=pcm_sha256,
    )


def _slice_manifest_row(payload_slice: CompiledStreamingPackSlice) -> dict[str, object]:
    return {
        "length": payload_slice.length,
        "pack_name": payload_slice.pack_name,
        "pack_offset": payload_slice.pack_offset,
        "pack_ordinal": payload_slice.pack_ordinal,
        "payload_offset": payload_slice.payload_offset,
        "payload_sha256": payload_slice.payload_sha256,
    }


def _owner_manifest_row(owner: LogicalStreamingOwner) -> dict[str, object]:
    return {
        "asset_id": owner.asset_id,
        "descriptor_asset_id": owner.descriptor_asset_id,
        "descriptor_chunk_index": owner.descriptor_chunk_index,
        "descriptor_outer_index": owner.descriptor_outer_index,
        "range_index": owner.range_index,
    }


def _composition_sha256(
    *,
    canonical_id: str,
    external_outer_index: int,
    external_outer_id: int,
    range_start: int,
    range_end: int,
    channels: int,
    sample_rate: int,
    frame_count: int,
    owners: tuple[LogicalStreamingOwner, ...],
    pack_slices: tuple[CompiledStreamingPackSlice, ...],
    input_wav_sha256: str,
    input_pcm_sha256: str,
    encoded_sha256: str,
    decoded_pcm_sha256: str,
) -> str:
    manifest = {
        "canonical_id": canonical_id,
        "decoded_pcm_sha256": decoded_pcm_sha256,
        "encoded_sha256": encoded_sha256,
        "external_outer_id": external_outer_id,
        "external_outer_index": external_outer_index,
        "frame_count": frame_count,
        "input_pcm_sha256": input_pcm_sha256,
        "input_wav_sha256": input_wav_sha256,
        "owners": [_owner_manifest_row(owner) for owner in owners],
        "pack_slices": [_slice_manifest_row(value) for value in pack_slices],
        "range_end": range_end,
        "range_start": range_start,
        "sample_rate": sample_rate,
        "schema": COMPOSITION_SCHEMA,
        "channels": channels,
    }
    canonical = json.dumps(
        manifest,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(canonical).hexdigest()


def _compiled_slices(
    plan: tuple[StreamingPackSpan, ...],
    encoded: bytes,
) -> tuple[CompiledStreamingPackSlice, ...]:
    slices = tuple(
        CompiledStreamingPackSlice(
            pack_name=span.pack_name,
            pack_ordinal=span.pack_ordinal,
            pack_offset=span.pack_offset,
            payload_offset=span.payload_offset,
            payload=encoded[
                span.payload_offset:span.payload_offset + span.length
            ],
            payload_sha256=hashlib.sha256(
                encoded[span.payload_offset:span.payload_offset + span.length]
            ).hexdigest(),
        )
        for span in plan
    )
    _require(
        sum(value.length for value in slices) == len(encoded),
        "Compiled AUSB slices do not cover the encoded payload",
    )
    return slices


def _metadata_matches_slot(
    slot: CanonicalStreamingSlot,
    compiled: CompiledStreamingSlotEdit,
    plan: tuple[StreamingPackSpan, ...],
) -> bytes:
    owners = _validated_slot_identity(slot)
    _require(
        (
            compiled.canonical_id,
            compiled.external_outer_index,
            compiled.external_outer_id,
            compiled.range_start,
            compiled.range_end,
            compiled.channels,
            compiled.sample_rate,
            compiled.frame_count,
            compiled.owners,
        )
        == (
            slot.canonical_id,
            slot.external_outer_index,
            slot.external_outer_id,
            slot.range_start,
            slot.range_end,
            slot.channels,
            slot.sample_rate,
            slot.frame_count,
            owners,
        ),
        "Compiled AUSB identity, owners, or PCM shape differs from its slot",
    )
    affected = tuple(owner.asset_id for owner in owners)
    _require(
        compiled.affected_asset_ids == affected
        and compiled.shared_owner_effect is (len(owners) > 1),
        "Compiled AUSB shared-owner effect metadata is inconsistent",
    )
    _require(
        type(compiled.pack_slices) is tuple
        and len(compiled.pack_slices) == len(plan),
        "Compiled AUSB pack-slice count differs from its write plan",
    )
    payload_parts: list[bytes] = []
    for span, value in zip(plan, compiled.pack_slices, strict=True):
        _require(
            type(value) is CompiledStreamingPackSlice
            and (
                value.pack_name,
                value.pack_ordinal,
                value.pack_offset,
                value.payload_offset,
                value.length,
            )
            == (
                span.pack_name,
                span.pack_ordinal,
                span.pack_offset,
                span.payload_offset,
                span.length,
            ),
            "Compiled AUSB pack slices do not exactly match the ordered write plan",
        )
        _require(
            type(value.payload) is bytes
            and _require_sha256(value.payload_sha256, "Pack-slice hash")
            == hashlib.sha256(value.payload).hexdigest(),
            "Compiled AUSB pack-slice payload hash changed",
        )
        payload_parts.append(value.payload)
    encoded = b"".join(payload_parts)
    _require(
        len(encoded) == slot.encoded_size,
        "Compiled AUSB pack slices do not cover the fixed allocation",
    )
    return encoded


def validate_compiled_streaming_slot(
    slot: CanonicalStreamingSlot,
    compiled: CompiledStreamingSlotEdit,
) -> None:
    """Independently validate a compiled edit before a future builder uses it."""

    _require(
        type(compiled) is CompiledStreamingSlotEdit,
        "Compiled AUSB edit has the wrong type",
    )
    plan = _validated_write_plan(slot)
    encoded = _metadata_matches_slot(slot, compiled, plan)
    encoded_sha256 = _require_sha256(
        compiled.encoded_sha256, "Compiled encoded hash"
    )
    decoded_pcm_sha256 = _require_sha256(
        compiled.decoded_pcm_sha256, "Compiled decoded-PCM hash"
    )
    _require_sha256(compiled.input_wav_sha256, "Compiled input-WAV hash")
    _require_sha256(compiled.input_pcm_sha256, "Compiled input-PCM hash")
    _require(
        hashlib.sha256(encoded).hexdigest() == encoded_sha256,
        "Compiled AUSB encoded payload hash changed",
    )
    verified = verify_xbox_ima_stream(io.BytesIO(encoded), slot)
    _require(
        verified.encoded_size == slot.encoded_size
        and verified.block_count == slot.block_count
        and verified.frame_count == slot.frame_count
        and verified.encoded_sha256 == encoded_sha256
        and verified.decoded_pcm_sha256 == decoded_pcm_sha256,
        "Independent AUSB verification disagrees with the compiled result",
    )
    expected_composition = _composition_sha256(
        canonical_id=compiled.canonical_id,
        external_outer_index=compiled.external_outer_index,
        external_outer_id=compiled.external_outer_id,
        range_start=compiled.range_start,
        range_end=compiled.range_end,
        channels=compiled.channels,
        sample_rate=compiled.sample_rate,
        frame_count=compiled.frame_count,
        owners=compiled.owners,
        pack_slices=compiled.pack_slices,
        input_wav_sha256=compiled.input_wav_sha256,
        input_pcm_sha256=compiled.input_pcm_sha256,
        encoded_sha256=compiled.encoded_sha256,
        decoded_pcm_sha256=compiled.decoded_pcm_sha256,
    )
    _require(
        _require_sha256(compiled.composition_sha256, "Composition hash")
        == expected_composition,
        "Compiled AUSB composition metadata changed",
    )


def _clear_staging_buffer(buffer: io.BytesIO) -> None:
    try:
        buffer.seek(0)
        buffer.truncate(0)
    finally:
        buffer.close()


def _compile_authorized_streaming_slot(
    slot: CanonicalStreamingSlot,
    snapshot: AuthorizedWavSnapshot,
    *,
    progress: ProgressCallback | None = None,
    cancelled: CancellationCallback | None = None,
    progress_interval_blocks: int = 1024,
) -> CompiledStreamingSlotEdit:
    """INTERNAL: compose the snapshot returned immediately by the origin gate.

    This function cannot establish authorization and must never be exposed as
    a raw-WAV product endpoint.  It snapshots and cross-checks every protocol
    field once, performs a transactional encode, then runs the independent
    structural decoder over the exact bytes split for the physical write plan.
    """

    owners = _validated_slot_identity(slot)
    plan = _validated_write_plan(slot)
    authorized = _snapshot_values(snapshot, slot)
    staging = io.BytesIO()
    try:
        encoded_result = encode_strict_pcm16_wav(
            io.BytesIO(authorized.wav_bytes),
            staging,
            slot,
            progress=progress,
            cancelled=cancelled,
            progress_interval_blocks=progress_interval_blocks,
        )
        encoded = staging.getvalue()
        _require(
            encoded_result.encoded_size == slot.encoded_size
            and encoded_result.block_count == slot.block_count
            and encoded_result.frame_count == slot.frame_count
            and encoded_result.input_pcm_sha256 == authorized.pcm_sha256
            and encoded_result.encoded_sha256
            == hashlib.sha256(encoded).hexdigest(),
            "AUSB encoder result disagrees with its authorized input or output",
        )
        pack_slices = _compiled_slices(plan, encoded)
        affected = tuple(owner.asset_id for owner in owners)
        composition_sha256 = _composition_sha256(
            canonical_id=slot.canonical_id,
            external_outer_index=slot.external_outer_index,
            external_outer_id=slot.external_outer_id,
            range_start=slot.range_start,
            range_end=slot.range_end,
            channels=slot.channels,
            sample_rate=slot.sample_rate,
            frame_count=slot.frame_count,
            owners=owners,
            pack_slices=pack_slices,
            input_wav_sha256=authorized.wav_sha256,
            input_pcm_sha256=authorized.pcm_sha256,
            encoded_sha256=encoded_result.encoded_sha256,
            decoded_pcm_sha256=encoded_result.decoded_pcm_sha256,
        )
        compiled = CompiledStreamingSlotEdit(
            canonical_id=slot.canonical_id,
            external_outer_index=slot.external_outer_index,
            external_outer_id=slot.external_outer_id,
            range_start=slot.range_start,
            range_end=slot.range_end,
            channels=slot.channels,
            sample_rate=slot.sample_rate,
            frame_count=slot.frame_count,
            owners=owners,
            affected_asset_ids=affected,
            shared_owner_effect=len(owners) > 1,
            pack_slices=pack_slices,
            input_wav_sha256=authorized.wav_sha256,
            input_pcm_sha256=authorized.pcm_sha256,
            encoded_sha256=encoded_result.encoded_sha256,
            decoded_pcm_sha256=encoded_result.decoded_pcm_sha256,
            composition_sha256=composition_sha256,
        )
        validate_compiled_streaming_slot(slot, compiled)
        return compiled
    finally:
        _clear_staging_buffer(staging)


__all__ = [
    "AuthorizedWavSnapshot",
    "COMPOSITION_SCHEMA",
    "CompiledStreamingPackSlice",
    "CompiledStreamingSlotEdit",
    "Nfl2k5AusbBuildAdapterError",
    "validate_compiled_streaming_slot",
]

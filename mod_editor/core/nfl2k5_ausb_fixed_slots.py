"""Retail-free fixed-allocation authoring primitives for NFL 2K5 AUSB ranges.

The audio catalog owns logical ranges inside external streaming-bank entries.
This module turns those logical owners into canonical physical slots, including
the one known case where two descriptors address the same external bank.  A
slot may cross an outer-archive pack seam; its write plan therefore consists
of one or more exact physical spans.

Only metadata and caller-supplied PCM are accepted here.  The module neither
reads retail data nor patches an archive.  Product/build integration must bind
the returned spans to a separately authenticated source and preserve every
byte outside them.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import struct
from types import MappingProxyType
from typing import TYPE_CHECKING, BinaryIO, Callable, Iterable, Mapping, Any


if TYPE_CHECKING:  # Imports are intentionally type-only; the codec is standalone.
    from .nfl2k5_audio_catalog import Nfl2k5StreamingAudioRange


SAMPLE_RATE = 22_050
BLOCK_FRAMES = 64
CHANNEL_BLOCK_BYTES = 36
IMA_INDEX_TABLE = (-1, -1, -1, -1, 2, 4, 6, 8)
IMA_STEP_TABLE = (
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31,
    34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130,
    143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449,
    494, 544, 598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411,
    1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026,
    4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442,
    11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623,
    27086, 29794, 32767,
)


class Nfl2k5AusbFixedSlotError(ValueError):
    """A streaming owner, strict WAV, encoded block, or write plan is invalid."""


class StreamingEncodeCancelled(Nfl2k5AusbFixedSlotError):
    """The caller cancelled at a deterministic Xbox IMA block boundary."""


@dataclass(frozen=True, slots=True)
class LogicalStreamingOwner:
    """One catalog-visible descriptor/range name for a physical slot."""

    asset_id: str
    descriptor_asset_id: str
    descriptor_outer_index: int
    descriptor_chunk_index: int
    range_index: int


@dataclass(frozen=True, slots=True)
class StreamingPackSpan:
    """One exact pack extent receiving a contiguous slice of encoded payload."""

    pack_name: str
    pack_ordinal: int
    pack_offset: int
    length: int
    payload_offset: int


@dataclass(frozen=True, slots=True)
class CanonicalStreamingSlot:
    """One unique external-entry range, possibly exposed by multiple owners."""

    canonical_id: str
    external_outer_index: int
    external_outer_id: int
    range_start: int
    range_end: int
    channels: int
    sample_rate: int
    frame_count: int
    owners: tuple[LogicalStreamingOwner, ...]
    physical_spans: tuple[StreamingPackSpan, ...]

    @property
    def encoded_size(self) -> int:
        return self.range_end - self.range_start

    @property
    def block_count(self) -> int:
        return self.encoded_size // (CHANNEL_BLOCK_BYTES * self.channels)

    @property
    def shared_effect(self) -> bool:
        """Replacing this physical slot changes more than one logical owner."""

        return len(self.owners) > 1

    @property
    def duration_seconds(self) -> float:
        return self.frame_count / self.sample_rate


@dataclass(frozen=True, slots=True)
class StreamingSlotCatalog:
    """Canonical slots plus an immutable logical/canonical-ID lookup."""

    slots: tuple[CanonicalStreamingSlot, ...]
    by_asset_id: Mapping[str, CanonicalStreamingSlot]

    def resolve(self, asset_id: str) -> CanonicalStreamingSlot:
        try:
            return self.by_asset_id[asset_id]
        except KeyError as exc:
            raise Nfl2k5AusbFixedSlotError(
                f"Unknown NFL 2K5 streaming range: {asset_id}"
            ) from exc


@dataclass(frozen=True, slots=True)
class StreamingEncodeProgress:
    completed_blocks: int
    total_blocks: int
    encoded_bytes: int
    completed_frames: int


@dataclass(frozen=True, slots=True)
class StreamingEncodeResult:
    encoded_size: int
    block_count: int
    frame_count: int
    input_pcm_sha256: str
    encoded_sha256: str
    decoded_pcm_sha256: str


@dataclass(frozen=True, slots=True)
class StreamingVerifyResult:
    encoded_size: int
    block_count: int
    frame_count: int
    encoded_sha256: str
    decoded_pcm_sha256: str


ProgressCallback = Callable[[StreamingEncodeProgress], None]
CancellationCallback = Callable[[], bool]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Nfl2k5AusbFixedSlotError(message)


def _is_integer(value: object) -> bool:
    return type(value) is int


def _external_id(value: object) -> int:
    _require(isinstance(value, str), "Streaming external entry ID is not text")
    try:
        parsed = int(value, 0)
    except ValueError as exc:
        raise Nfl2k5AusbFixedSlotError(
            "Streaming external entry ID is not hexadecimal"
        ) from exc
    _require(0 <= parsed <= 0xFFFFFFFF, "Streaming external entry ID is out of range")
    return parsed


def _bank_signature(bank: Any) -> tuple[object, ...]:
    return (
        bank.outer_index,
        bank.chunk_index,
        bank.external_outer_index,
        bank.external_outer_id,
        bank.external_size,
        bank.entry_count,
        bank.sample_rate,
        bank.channel_word,
        bank.unknown_word,
        bank.unit_word,
        bank.boundaries,
        bank.descriptor_sha256,
    )


def _validate_entry_segments(entry: Any, archive: Any) -> None:
    packs = archive.packs
    _require(isinstance(packs, tuple) and packs,
             "Archive has no ordered virtual pack map")
    seen_ordinals: set[int] = set()
    seen_names: set[str] = set()
    previous_virtual_end: int | None = None
    for pack in packs:
        _require(
            _is_integer(pack.ordinal) and pack.ordinal >= 0
            and isinstance(pack.name, str) and bool(pack.name)
            and _is_integer(pack.virtual_start) and pack.virtual_start >= 0
            and _is_integer(pack.size) and pack.size > 0,
            "Archive pack has invalid virtual-range metadata",
        )
        _require(pack.ordinal not in seen_ordinals, "Archive repeats a pack ordinal")
        _require(pack.name not in seen_names, "Archive repeats a pack name")
        _require(
            previous_virtual_end is None
            or pack.virtual_start == previous_virtual_end,
            "Archive pack virtual ranges are not ordered and contiguous",
        )
        seen_ordinals.add(pack.ordinal)
        seen_names.add(pack.name)
        previous_virtual_end = pack.virtual_start + pack.size

    _require(
        _is_integer(entry.virtual_offset) and entry.virtual_offset >= 0
        and _is_integer(entry.size) and entry.size > 0,
        "External entry has an invalid virtual allocation",
    )
    entry_end = entry.virtual_offset + entry.size
    _require(
        entry.virtual_offset >= packs[0].virtual_start
        and previous_virtual_end is not None
        and entry_end <= previous_virtual_end,
        "External entry virtual allocation is outside the archive packs",
    )

    expected: list[tuple[int, str, int, int]] = []
    for pack in packs:
        pack_end = pack.virtual_start + pack.size
        overlap_start = max(entry.virtual_offset, pack.virtual_start)
        overlap_end = min(entry_end, pack_end)
        if overlap_start < overlap_end:
            expected.append((
                pack.ordinal,
                pack.name,
                overlap_start - pack.virtual_start,
                overlap_end - overlap_start,
            ))

    actual: list[tuple[int, str, int, int]] = []
    _require(isinstance(entry.segments, tuple) and entry.segments,
             "External entry has no physical pack projection")
    for segment in entry.segments:
        _require(
            _is_integer(segment.pack_ordinal)
            and isinstance(segment.pack_name, str)
            and _is_integer(segment.pack_offset)
            and _is_integer(segment.size),
            "External entry segment has invalid projection metadata",
        )
        actual.append((
            segment.pack_ordinal,
            segment.pack_name,
            segment.pack_offset,
            segment.size,
        ))
    _require(
        actual == expected,
        "External entry segments are not the exact ordered virtual projection",
    )


def _validate_bank(bank: Any, entry: Any, archive: Any) -> None:
    _require(isinstance(bank.asset_id, str) and bank.asset_id,
             "Streaming descriptor has no stable asset ID")
    _require(
        _is_integer(bank.entry_count) and bank.entry_count > 0
        and _is_integer(bank.channel_word) and bank.channel_word in (1, 2)
        and bank.sample_rate == SAMPLE_RATE
        and bank.unit_word == 0x12000,
        f"Streaming descriptor {bank.asset_id} has an unsupported codec shape",
    )
    _require(
        _is_integer(bank.external_outer_index)
        and bank.external_outer_index == entry.table_index
        and _external_id(bank.external_outer_id) == entry.name_id
        and bank.external_size == entry.size,
        f"Streaming descriptor {bank.asset_id} does not own its external entry",
    )
    boundaries = bank.boundaries
    _require(
        isinstance(boundaries, tuple)
        and len(boundaries) == bank.entry_count + 1
        and boundaries[0] == 0
        and boundaries[-1] == entry.size,
        f"Streaming descriptor {bank.asset_id} has an invalid boundary table",
    )
    block_align = CHANNEL_BLOCK_BYTES * bank.channel_word
    for left, right in zip(boundaries, boundaries[1:]):
        _require(
            _is_integer(left) and _is_integer(right)
            and 0 <= left < right <= entry.size
            and (right - left) % block_align == 0,
            f"Streaming descriptor {bank.asset_id} has a non-encodable range",
        )
    _validate_entry_segments(entry, archive)


def _map_pack_spans(entry: Any, start: int, end: int) \
        -> tuple[StreamingPackSpan, ...]:
    spans: list[StreamingPackSpan] = []
    logical_cursor = 0
    for segment in entry.segments:
        segment_end = logical_cursor + segment.size
        overlap_start = max(start, logical_cursor)
        overlap_end = min(end, segment_end)
        if overlap_start < overlap_end:
            spans.append(StreamingPackSpan(
                pack_name=segment.pack_name,
                pack_ordinal=segment.pack_ordinal,
                pack_offset=segment.pack_offset + overlap_start - logical_cursor,
                length=overlap_end - overlap_start,
                payload_offset=overlap_start - start,
            ))
        logical_cursor = segment_end
    _require(
        spans
        and sum(span.length for span in spans) == end - start
        and all(
            span.payload_offset == sum(previous.length for previous in spans[:index])
            for index, span in enumerate(spans)
        ),
        "Streaming range could not be mapped completely across archive packs",
    )
    return tuple(spans)


def build_streaming_slot_catalog(
    ranges: Iterable["Nfl2k5StreamingAudioRange"], archive: Any
) -> StreamingSlotCatalog:
    """Canonicalize catalog ranges and derive metadata-only physical write plans.

    Identical ``(external entry, start, end)`` ranges become one slot with
    multiple logical owners.  Any non-identical overlap fails closed.
    """

    entries: dict[int, Any] = {}
    for entry in archive.entries:
        _require(_is_integer(entry.table_index) and entry.table_index >= 0,
                 "Archive entry has an invalid table index")
        _require(entry.table_index not in entries, "Archive repeats an entry index")
        entries[entry.table_index] = entry

    bank_signatures: dict[str, tuple[object, ...]] = {}
    groups: dict[tuple[int, int, int], dict[str, object]] = {}
    seen_owner_ids: set[str] = set()
    for logical_range in ranges:
        bank = logical_range.bank
        entry = entries.get(bank.external_outer_index)
        _require(entry is not None,
                 f"Streaming descriptor {bank.asset_id} names an absent entry")
        signature = _bank_signature(bank)
        previous_signature = bank_signatures.get(bank.asset_id)
        if previous_signature is None:
            _validate_bank(bank, entry, archive)
            bank_signatures[bank.asset_id] = signature
        else:
            _require(previous_signature == signature,
                     f"Streaming descriptor ID {bank.asset_id} has conflicting metadata")

        _require(
            _is_integer(logical_range.range_index)
            and 0 <= logical_range.range_index < bank.entry_count,
            f"Streaming range {logical_range.asset_id} has an invalid index",
        )
        expected_start = bank.boundaries[logical_range.range_index]
        expected_end = bank.boundaries[logical_range.range_index + 1]
        _require(
            logical_range.start == expected_start and logical_range.end == expected_end,
            f"Streaming range {logical_range.asset_id} differs from its boundary table",
        )
        owner = LogicalStreamingOwner(
            asset_id=logical_range.asset_id,
            descriptor_asset_id=bank.asset_id,
            descriptor_outer_index=bank.outer_index,
            descriptor_chunk_index=bank.chunk_index,
            range_index=logical_range.range_index,
        )
        _require(owner.asset_id not in seen_owner_ids,
                 f"Streaming logical owner is duplicated: {owner.asset_id}")
        seen_owner_ids.add(owner.asset_id)
        key = (entry.table_index, expected_start, expected_end)
        group = groups.get(key)
        if group is None:
            groups[key] = {
                "entry": entry,
                "channels": bank.channel_word,
                "sample_rate": bank.sample_rate,
                "owners": [owner],
            }
        else:
            _require(
                group["channels"] == bank.channel_word
                and group["sample_rate"] == bank.sample_rate
                and group["entry"] is entry,
                "Aliased streaming owners disagree about the physical slot shape",
            )
            owners = group["owners"]
            assert isinstance(owners, list)
            owners.append(owner)

    ordered_keys = sorted(groups)
    previous_by_entry: dict[int, tuple[int, int]] = {}
    for entry_index, start, end in ordered_keys:
        previous = previous_by_entry.get(entry_index)
        _require(previous is None or previous[1] <= start,
                 "Non-identical streaming ranges overlap in one external entry")
        previous_by_entry[entry_index] = (start, end)

    slots: list[CanonicalStreamingSlot] = []
    lookup: dict[str, CanonicalStreamingSlot] = {}
    for entry_index, start, end in ordered_keys:
        group = groups[(entry_index, start, end)]
        entry = group["entry"]
        channels = int(group["channels"])
        sample_rate = int(group["sample_rate"])
        owners_raw = group["owners"]
        assert isinstance(owners_raw, list)
        owners = tuple(sorted(owners_raw, key=lambda owner: owner.asset_id))
        size = end - start
        canonical_id = (
            f"nfl2k5.audio.ausb.physical.o{entry_index:04d}."
            f"s{start:010x}.n{size:010x}"
        )
        slot = CanonicalStreamingSlot(
            canonical_id=canonical_id,
            external_outer_index=entry_index,
            external_outer_id=entry.name_id,
            range_start=start,
            range_end=end,
            channels=channels,
            sample_rate=sample_rate,
            frame_count=size // (CHANNEL_BLOCK_BYTES * channels) * BLOCK_FRAMES,
            owners=owners,
            physical_spans=_map_pack_spans(entry, start, end),
        )
        _validate_slot_shape(slot)
        _require(canonical_id not in lookup,
                 "Canonical streaming slot ID collides with a logical owner")
        lookup[canonical_id] = slot
        for owner in owners:
            _require(owner.asset_id not in lookup,
                     "Streaming logical/canonical IDs collide")
            lookup[owner.asset_id] = slot
        slots.append(slot)

    return StreamingSlotCatalog(tuple(slots), MappingProxyType(lookup))


def streaming_slot_write_plan(
    slot: CanonicalStreamingSlot,
) -> tuple[StreamingPackSpan, ...]:
    """Return the exact ordered pack spans for later authenticated builders."""

    _validate_slot_shape(slot)
    return slot.physical_spans


def _validate_slot_shape(slot: CanonicalStreamingSlot) -> None:
    _require(
        slot.channels in (1, 2)
        and slot.sample_rate == SAMPLE_RATE
        and _is_integer(slot.range_start)
        and _is_integer(slot.range_end)
        and 0 <= slot.range_start < slot.range_end,
        "Streaming slot has an unsupported codec/allocation shape",
    )
    align = CHANNEL_BLOCK_BYTES * slot.channels
    _require(
        slot.encoded_size % align == 0
        and slot.frame_count == slot.encoded_size // align * BLOCK_FRAMES,
        "Streaming slot frame count differs from its fixed allocation",
    )
    cursor = 0
    for span in slot.physical_spans:
        _require(
            span.length > 0 and span.payload_offset == cursor
            and span.pack_ordinal >= 0 and span.pack_offset >= 0
            and bool(span.pack_name),
            "Streaming slot pack spans are not contiguous",
        )
        cursor += span.length
    _require(cursor == slot.encoded_size,
             "Streaming slot pack spans do not tile its allocation")


def _expand_nibble(predictor: int, index: int, nibble: int) -> tuple[int, int]:
    step = IMA_STEP_TABLE[index]
    difference = step >> 3
    if nibble & 1:
        difference += step >> 2
    if nibble & 2:
        difference += step >> 1
    if nibble & 4:
        difference += step
    predictor = predictor - difference if nibble & 8 else predictor + difference
    predictor = max(-32_768, min(32_767, predictor))
    index = max(0, min(88, index + IMA_INDEX_TABLE[nibble & 7]))
    return predictor, index


def _choose_nibble(target: int, predictor: int, index: int) -> tuple[int, int, int]:
    step = IMA_STEP_TABLE[index]
    delta = target - predictor
    nibble = 8 if delta < 0 else 0
    magnitude = abs(delta)
    if magnitude >= step:
        nibble |= 4
        magnitude -= step
    if magnitude >= step >> 1:
        nibble |= 2
        magnitude -= step >> 1
    if magnitude >= step >> 2:
        nibble |= 1
    decoded, new_index = _expand_nibble(predictor, index, nibble)
    return nibble, decoded, new_index


def _encode_channel_block(samples: tuple[int, ...]) -> bytes:
    _require(len(samples) == BLOCK_FRAMES,
             "Encoder channel block must contain exactly 64 frames")
    initial_predictor = samples[0]
    best_error: int | None = None
    best_index = 0
    best_nibbles: list[int] = []
    for initial_index in range(89):
        predictor = initial_predictor
        index = initial_index
        nibbles: list[int] = []
        squared_error = 0
        for target in samples[1:]:
            nibble, predictor, index = _choose_nibble(target, predictor, index)
            nibbles.append(nibble)
            squared_error += (target - predictor) ** 2
        final_nibble, _, _ = _choose_nibble(samples[-1], predictor, index)
        nibbles.append(final_nibble)
        if best_error is None or (squared_error, initial_index) < (best_error, best_index):
            best_error = squared_error
            best_index = initial_index
            best_nibbles = nibbles
    encoded = bytearray(struct.pack("<hH", initial_predictor, best_index))
    encoded.extend(
        best_nibbles[index] | (best_nibbles[index + 1] << 4)
        for index in range(0, BLOCK_FRAMES, 2)
    )
    _require(len(encoded) == CHANNEL_BLOCK_BYTES,
             "Encoder emitted the wrong channel-block size")
    return bytes(encoded)


def decode_xbox_ima_time_block(payload: bytes, channels: int) -> bytes:
    """Validate/decode one 64-frame mono or stereo Xbox IMA time block."""

    _require(channels in (1, 2), "Xbox IMA channel count must be one or two")
    _require(len(payload) == CHANNEL_BLOCK_BYTES * channels,
             "Xbox IMA time block has the wrong byte length")
    decoded_channels: list[list[int]] = []
    for channel in range(channels):
        start = channel * CHANNEL_BLOCK_BYTES
        predictor, index = struct.unpack_from("<hH", payload, start)
        _require(index <= 88, "Xbox IMA step index exceeds 88")
        decoded = [predictor]
        for value in payload[start + 4:start + CHANNEL_BLOCK_BYTES]:
            for nibble in (value & 0x0F, value >> 4):
                predictor, index = _expand_nibble(predictor, index, nibble)
                if len(decoded) < BLOCK_FRAMES:
                    decoded.append(predictor)
        _require(len(decoded) == BLOCK_FRAMES,
                 "Xbox IMA channel block emitted the wrong frame count")
        decoded_channels.append(decoded)
    interleaved = [
        decoded_channels[channel][frame]
        for frame in range(BLOCK_FRAMES)
        for channel in range(channels)
    ]
    return struct.pack(f"<{len(interleaved)}h", *interleaved)


def _read_exact(stream: BinaryIO, size: int, label: str) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        _require(isinstance(chunk, bytes), f"{label} stream did not return bytes")
        if not chunk:
            raise Nfl2k5AusbFixedSlotError(f"Truncated {label}")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _write_all(stream: BinaryIO, payload: bytes) -> None:
    view = memoryview(payload)
    written = 0
    while written < len(view):
        count = stream.write(view[written:])
        if count is None:
            count = len(view) - written
        _require(type(count) is int and 0 < count <= len(view) - written,
                 "Encoded output stream rejected a block")
        written += count


def _strict_wav_header(stream: BinaryIO, slot: CanonicalStreamingSlot) -> None:
    expected_pcm = slot.frame_count * slot.channels * 2
    header = _read_exact(stream, 44, "WAV header")
    _require(
        header[:4] == b"RIFF" and header[8:16] == b"WAVEfmt "
        and header[36:40] == b"data",
        "Strict WAV must contain exactly fmt then data; remove metadata chunks",
    )
    _require(struct.unpack_from("<I", header, 4)[0] == 36 + expected_pcm,
             "RIFF size does not equal the exact required WAV")
    _require(struct.unpack_from("<I", header, 16)[0] == 16,
             "Strict WAV fmt chunk must use the 16-byte PCM form")
    tag, channels, rate, byte_rate, block_align, bits = struct.unpack_from(
        "<HHIIHH", header, 20
    )
    _require(tag == 1, "WAV must use integer PCM format tag 1")
    _require(channels == slot.channels,
             f"WAV must have exactly {slot.channels} channel(s)")
    _require(rate == slot.sample_rate,
             f"WAV must be exactly {slot.sample_rate:,} Hz")
    _require(
        bits == 16 and block_align == channels * 2
        and byte_rate == rate * block_align,
        "WAV must be canonical little-endian PCM16",
    )
    _require(struct.unpack_from("<I", header, 40)[0] == expected_pcm,
             f"WAV must contain exactly {slot.frame_count:,} frames")


def _prepare_empty_output(stream: BinaryIO) -> None:
    try:
        position = stream.tell()
        stream.seek(0, 2)
        end = stream.tell()
        stream.seek(position)
    except (AttributeError, OSError) as exc:
        raise Nfl2k5AusbFixedSlotError(
            "Encoded output must be a seekable caller-owned binary stream"
        ) from exc
    _require(position == 0 and end == 0,
             "Encoded output stream must be empty and positioned at byte zero")


def _rollback_output(stream: BinaryIO) -> None:
    try:
        stream.seek(0)
        stream.truncate(0)
    except Exception:
        # Preserve the original encode exception. Product callers should use a
        # temporary regular file, where seek/truncate are guaranteed.
        pass


def _progress(
    callback: ProgressCallback | None,
    completed: int,
    slot: CanonicalStreamingSlot,
) -> None:
    if callback is not None:
        callback(StreamingEncodeProgress(
            completed_blocks=completed,
            total_blocks=slot.block_count,
            encoded_bytes=completed * CHANNEL_BLOCK_BYTES * slot.channels,
            completed_frames=completed * BLOCK_FRAMES,
        ))


def encode_strict_pcm16_wav(
    input_stream: BinaryIO,
    output_stream: BinaryIO,
    slot: CanonicalStreamingSlot,
    *,
    progress: ProgressCallback | None = None,
    cancelled: CancellationCallback | None = None,
    progress_interval_blocks: int = 1024,
) -> StreamingEncodeResult:
    """Stream a strict WAV into an exact fixed allocation.

    At most one 64-frame PCM time block, its one/two channel tuples, and one
    encoded time block are retained.  Any validation, callback, cancellation,
    or write failure truncates the caller-owned output back to empty.
    """

    _validate_slot_shape(slot)
    _require(type(progress_interval_blocks) is int and progress_interval_blocks > 0,
             "Progress interval must be a positive block count")
    _prepare_empty_output(output_stream)
    input_hash = hashlib.sha256()
    encoded_hash = hashlib.sha256()
    decoded_hash = hashlib.sha256()
    block_pcm_bytes = BLOCK_FRAMES * slot.channels * 2
    try:
        _strict_wav_header(input_stream, slot)
        _progress(progress, 0, slot)
        for block_index in range(slot.block_count):
            if cancelled is not None and cancelled():
                raise StreamingEncodeCancelled(
                    f"Streaming encode cancelled before block {block_index + 1:,}"
                )
            pcm = _read_exact(input_stream, block_pcm_bytes, "WAV PCM data")
            input_hash.update(pcm)
            samples = struct.unpack(f"<{BLOCK_FRAMES * slot.channels}h", pcm)
            encoded_parts = []
            for channel in range(slot.channels):
                channel_samples = tuple(
                    samples[frame * slot.channels + channel]
                    for frame in range(BLOCK_FRAMES)
                )
                encoded_parts.append(_encode_channel_block(channel_samples))
            encoded = b"".join(encoded_parts)
            decoded = decode_xbox_ima_time_block(encoded, slot.channels)
            _write_all(output_stream, encoded)
            encoded_hash.update(encoded)
            decoded_hash.update(decoded)
            completed = block_index + 1
            if completed == slot.block_count \
                    or completed % progress_interval_blocks == 0:
                _progress(progress, completed, slot)
        _require(input_stream.read(1) == b"",
                 "Strict WAV contains bytes after its exact PCM data")
        _require(output_stream.tell() == slot.encoded_size,
                 "Encoder output size differs from the fixed allocation")
        flush = getattr(output_stream, "flush", None)
        if flush is not None:
            flush()
    except BaseException:
        _rollback_output(output_stream)
        raise
    return StreamingEncodeResult(
        encoded_size=slot.encoded_size,
        block_count=slot.block_count,
        frame_count=slot.frame_count,
        input_pcm_sha256=input_hash.hexdigest(),
        encoded_sha256=encoded_hash.hexdigest(),
        decoded_pcm_sha256=decoded_hash.hexdigest(),
    )


def verify_xbox_ima_stream(
    encoded_stream: BinaryIO, slot: CanonicalStreamingSlot, *,
    cancelled: CancellationCallback | None = None,
) -> StreamingVerifyResult:
    """Stream-validate exact length, step indices, framing, and decoded shape."""

    _validate_slot_shape(slot)
    encoded_hash = hashlib.sha256()
    decoded_hash = hashlib.sha256()
    block_bytes = CHANNEL_BLOCK_BYTES * slot.channels
    for _ in range(slot.block_count):
        if cancelled is not None and cancelled():
            raise StreamingEncodeCancelled("Music verification cancelled")
        payload = _read_exact(encoded_stream, block_bytes, "Xbox IMA payload")
        decoded = decode_xbox_ima_time_block(payload, slot.channels)
        encoded_hash.update(payload)
        decoded_hash.update(decoded)
    _require(encoded_stream.read(1) == b"",
             "Xbox IMA payload has trailing bytes beyond the fixed allocation")
    return StreamingVerifyResult(
        encoded_size=slot.encoded_size,
        block_count=slot.block_count,
        frame_count=slot.frame_count,
        encoded_sha256=encoded_hash.hexdigest(),
        decoded_pcm_sha256=decoded_hash.hexdigest(),
    )


__all__ = [
    "BLOCK_FRAMES",
    "CHANNEL_BLOCK_BYTES",
    "CanonicalStreamingSlot",
    "LogicalStreamingOwner",
    "Nfl2k5AusbFixedSlotError",
    "SAMPLE_RATE",
    "StreamingEncodeCancelled",
    "StreamingEncodeProgress",
    "StreamingEncodeResult",
    "StreamingPackSpan",
    "StreamingSlotCatalog",
    "StreamingVerifyResult",
    "build_streaming_slot_catalog",
    "decode_xbox_ima_time_block",
    "encode_strict_pcm16_wav",
    "streaming_slot_write_plan",
    "verify_xbox_ima_stream",
]

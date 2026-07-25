#!/usr/bin/env python3
"""Strict, bounded APF 2K8 standalone-AUDO XMA1 slot importer.

This module deliberately implements only the safe import shape supported by
the current APF evidence: a user supplies a pre-encoded, one-stream RIFF XMA1
file whose channel count, sample rate, and encoded packet length exactly match
one existing standalone ``AUDO`` allocation.  The user file is parsed rather
than copied blindly, its raw packets must match APF's packet-header contract,
and those packets are rewrapped with the selected slot's 44-byte sidecar
semantics before a complete ``ffmpeg -xerror`` decode.

The returned ``payload`` is the exact raw packet span a project stores and a
build compiler may place in the selected SRAM allocation.  The RIFF wrapper
made with target loop/valid-bit metadata exists only in memory for the FFmpeg
validation call; it is never returned for project storage.  The payload never
contains the selected slot's original packets or any other retail preimage.
Receipts contain only public shape metadata, counts, and hashes; they never
contain audio bytes, paths, or the target loop/valid-bit metadata.

This is not an encoder.  PCM WAV/FLAC input and size-changing XMA input are
outside this writer's contract.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
from typing import Iterable, Iterator, Mapping

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mod_editor.core.platform_compat import fsync_path  # noqa: E402

import apf_audio  # noqa: E402
import apf_inner  # noqa: E402
import apf_outer  # noqa: E402


SCHEMA = "apf2k8_audo_exact_slot_import/v1"
WAV_EXPORT_SCHEMA = "apf2k8_audo_exact_slot_pcm_export/v1"
MODIFICATION_KIND = "audo_exact_slot_xma1"
XMA1_FORMAT_TAG = 0x0165
XMA1_STREAM_DESCRIPTOR_SIZE = 20
XMA1_BASE_FORMAT_SIZE = 12
XMA1_ONE_STREAM_FORMAT_SIZE = XMA1_BASE_FORMAT_SIZE + XMA1_STREAM_DESCRIPTOR_SIZE
MAX_RIFF_CHUNKS = 64
MAX_PAYLOAD_BYTES = 64 * 1024 * 1024
MAX_SAMPLE_RATE = 384_000
DECODE_SAMPLE_TOLERANCE = 127
DEFAULT_DECODE_TIMEOUT_SECONDS = 120
EXPECTED_STANDALONE_AUDO_COUNT = 2_261
ASSET_ID_PREFIX = "apf:audio:audo"
SOURCE_AUDIO_DOMAIN = "standalone_audo"
SOURCE_PACKET_SIZE = 0x800


class ExactSlotImportError(ValueError):
    """The replacement left the bounded APF standalone-AUDO contract."""


@dataclass(frozen=True)
class ExactSlotTarget:
    """Retail-free shape needed to validate one existing AUDO slot."""

    channels: int
    sample_rate: int
    encoded_size: int
    declared_sample_count: int
    loop_start_bit: int
    loop_end_bit: int
    loop_subframe: int


@dataclass(frozen=True)
class ParsedXma1Riff:
    """Strictly parsed one-stream RIFF XMA1 input."""

    channels: int
    sample_rate: int
    bits_per_sample: int
    encode_options: int
    largest_skip: int
    loop_count: int
    encoder_version: int
    pseudo_bytes_per_second: int
    loop_start_bit: int
    loop_end_bit: int
    loop_subframe: int
    channel_mask: int
    payload: bytes
    ancillary_chunk_count: int


@dataclass(frozen=True)
class ExactSlotImportResult:
    """Canonical raw-packet project replacement and retail-free receipt."""

    payload: bytes
    receipt: Mapping[str, object]

    @property
    def receipt_bytes(self) -> bytes:
        """Return the deterministic, newline-terminated JSON receipt."""

        return encode_receipt(self.receipt)


@dataclass(frozen=True)
class SourceAudioFingerprints:
    """Retail-free hashes for one complete source-audio domain scan.

    Packet fingerprints are raw 32-byte SHA-256 digests instead of hexadecimal
    strings.  This materially reduces the long-lived session cache for AUSB's
    hundreds of thousands of packets while retaining exact membership tests.
    No source bytes, offsets, names, paths, or preimages are retained.
    """

    domain: str
    payload_sha256s: frozenset[str]
    packet_sha256s: frozenset[bytes]
    payload_occurrence_count: int
    packet_occurrence_count: int


@dataclass(frozen=True)
class ResolvedExactSlot:
    """One source-owned, physically contiguous standalone AUDO target."""

    asset_id: str
    name: str
    outer_index: int
    inner_index: int
    target: ExactSlotTarget
    pack_name: str
    pack_offset: int
    encoded_size: int
    source_payload_sha256: str


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _packet_sha256s(payload: bytes) -> Iterator[bytes]:
    """Hash complete APF XMA packets without copying packet slices."""

    if len(payload) % SOURCE_PACKET_SIZE:
        raise ExactSlotImportError(
            "Source audio payload is not a complete 0x800-byte packet sequence"
        )
    view = memoryview(payload)
    for offset in range(0, len(payload), SOURCE_PACKET_SIZE):
        yield hashlib.sha256(
            view[offset : offset + SOURCE_PACKET_SIZE]
        ).digest()


def _validated_source_audio_fingerprints(
    fingerprints: SourceAudioFingerprints,
    *,
    expected_domain: str,
    expected_payload_occurrences: int,
    expected_unique_payloads: int | None = None,
) -> SourceAudioFingerprints:
    """Fail closed unless a complete scanner-produced fingerprint set is present."""

    if not isinstance(fingerprints, SourceAudioFingerprints):
        raise ExactSlotImportError(
            "Source audio protection requires a complete packet fingerprint inventory"
        )
    if (
        fingerprints.domain != expected_domain
        or type(fingerprints.payload_occurrence_count) is not int
        or fingerprints.payload_occurrence_count != expected_payload_occurrences
        or type(fingerprints.packet_occurrence_count) is not int
        or fingerprints.packet_occurrence_count <= 0
        or not isinstance(fingerprints.payload_sha256s, frozenset)
        or not fingerprints.payload_sha256s
        or len(fingerprints.payload_sha256s) > fingerprints.payload_occurrence_count
        or not isinstance(fingerprints.packet_sha256s, frozenset)
        or not fingerprints.packet_sha256s
        or len(fingerprints.packet_sha256s) > fingerprints.packet_occurrence_count
        or (
            expected_unique_payloads is not None
            and len(fingerprints.payload_sha256s) != expected_unique_payloads
        )
    ):
        raise ExactSlotImportError(
            "Source audio protection requires a complete packet fingerprint inventory"
        )
    if any(
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
        for value in fingerprints.payload_sha256s
    ) or any(
        not isinstance(value, bytes) or len(value) != hashlib.sha256().digest_size
        for value in fingerprints.packet_sha256s
    ):
        raise ExactSlotImportError("Source audio fingerprint inventory is malformed")
    return fingerprints


def _reject_source_audio_reuse(
    payload: bytes,
    fingerprints: SourceAudioFingerprints,
    *,
    expected_domain: str,
    expected_payload_occurrences: int,
    expected_unique_payloads: int | None = None,
) -> None:
    """Reject exact retail payloads and any reused complete retail packet."""

    protected = _validated_source_audio_fingerprints(
        fingerprints,
        expected_domain=expected_domain,
        expected_payload_occurrences=expected_payload_occurrences,
        expected_unique_payloads=expected_unique_payloads,
    )
    if _sha256(payload) in protected.payload_sha256s:
        raise ExactSlotImportError(
            "Replacement matches a complete audio payload from the selected game"
        )
    for packet_index, digest in enumerate(_packet_sha256s(payload)):
        if digest in protected.packet_sha256s:
            raise ExactSlotImportError(
                "Replacement reuses a complete 0x800-byte audio packet from the "
                f"selected game (replacement packet {packet_index})"
            )


def reject_source_audio_reuse(
    payload: bytes,
    fingerprints: SourceAudioFingerprints,
) -> None:
    """Apply the standalone-AUDO whole-payload and packet reuse gate."""

    _reject_source_audio_reuse(
        payload,
        fingerprints,
        expected_domain=SOURCE_AUDIO_DOMAIN,
        expected_payload_occurrences=EXPECTED_STANDALONE_AUDO_COUNT,
    )


def _plain_int(value: object, label: str) -> int:
    if type(value) is not int:
        raise ExactSlotImportError(f"{label} must be a whole number")
    return value


def _metadata_value(
    metadata: Mapping[str, object], primary: str, alias: str | None = None
) -> int:
    present = [name for name in (primary, alias) if name is not None and name in metadata]
    if not present:
        names = primary if alias is None else f"{primary} (or {alias})"
        raise ExactSlotImportError(f"Target metadata is missing {names}")
    values = [_plain_int(metadata[name], f"Target {name}") for name in present]
    if any(value != values[0] for value in values[1:]):
        raise ExactSlotImportError(
            f"Target metadata disagrees between {primary} and {alias}"
        )
    return values[0]


def target_from_metadata(metadata: Mapping[str, object]) -> ExactSlotTarget:
    """Normalize an :func:`apf_audio.parse_metadata` result into a target.

    The shorter public field names are also accepted so a project/build layer
    need not retain research-oriented ``*_candidate`` labels.  If both forms
    are supplied they must agree exactly.
    """

    if not isinstance(metadata, Mapping):
        raise ExactSlotImportError("Target AUDO metadata must be a mapping")
    target = ExactSlotTarget(
        channels=_metadata_value(metadata, "channels", "derived_channel_count"),
        sample_rate=_metadata_value(metadata, "sample_rate"),
        encoded_size=_metadata_value(metadata, "encoded_size"),
        declared_sample_count=_metadata_value(metadata, "declared_sample_count"),
        loop_start_bit=_metadata_value(
            metadata, "loop_start_bit", "xma1_loop_start_bit_candidate"
        ),
        loop_end_bit=_metadata_value(
            metadata, "loop_end_bit", "xma1_loop_end_bit_candidate"
        ),
        loop_subframe=_metadata_value(
            metadata, "loop_subframe", "xma1_loop_subframe_candidate"
        ),
    )
    return validate_target(target)


def validate_target(target: ExactSlotTarget) -> ExactSlotTarget:
    """Fail closed on malformed or nonsensical target-side shape metadata."""

    if not isinstance(target, ExactSlotTarget):
        raise ExactSlotImportError("AUDO target must be an ExactSlotTarget")
    for field_name in (
        "channels",
        "sample_rate",
        "encoded_size",
        "declared_sample_count",
        "loop_start_bit",
        "loop_end_bit",
        "loop_subframe",
    ):
        _plain_int(getattr(target, field_name), f"Target {field_name}")
    if target.channels not in (1, 2):
        raise ExactSlotImportError("Target AUDO must have one or two channels")
    if not 1 <= target.sample_rate <= MAX_SAMPLE_RATE:
        raise ExactSlotImportError("Target AUDO sample rate is out of bounds")
    if (
        target.encoded_size <= 0
        or target.encoded_size > MAX_PAYLOAD_BYTES
        or target.encoded_size % apf_audio.XMA_PACKET_SIZE
    ):
        raise ExactSlotImportError(
            "Target AUDO encoded size must be a nonempty 0x800-byte packet multiple"
        )
    if not 1 <= target.declared_sample_count <= 0xFFFFFFFF:
        raise ExactSlotImportError("Target AUDO declared sample count is out of bounds")
    payload_bits = target.encoded_size * 8
    if not 0 <= target.loop_start_bit <= target.loop_end_bit <= payload_bits:
        raise ExactSlotImportError("Target AUDO bit bounds leave its encoded allocation")
    if not 0 <= target.loop_subframe <= 0xFF:
        raise ExactSlotImportError("Target AUDO loop subframe is out of bounds")
    return target


def _as_bytes(data: object) -> bytes:
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise ExactSlotImportError("Replacement must be RIFF XMA1 bytes")
    result = bytes(data)
    if len(result) > MAX_PAYLOAD_BYTES + 1024 * 1024:
        raise ExactSlotImportError("Replacement RIFF XMA1 file is unreasonably large")
    return result


def parse_xma1_riff(data: bytes) -> ParsedXma1Riff:
    """Parse one bounded RIFF/WAVE XMA1 stream and return its raw packets.

    Ancillary RIFF chunks are accepted but discarded by canonicalization.  A
    file must have exactly one ``fmt `` chunk and exactly one ``data`` chunk;
    duplicate or truncated chunks, trailing bytes, and malformed RIFF padding
    are rejected.
    """

    raw = _as_bytes(data)
    if len(raw) < 12 or raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ExactSlotImportError("Replacement is not a little-endian RIFF WAVE file")
    declared_size = struct.unpack_from("<I", raw, 4)[0]
    if declared_size != len(raw) - 8:
        raise ExactSlotImportError("Replacement RIFF size does not match the file length")

    fmt_chunks: list[bytes] = []
    data_chunks: list[bytes] = []
    ancillary_count = 0
    cursor = 12
    chunk_count = 0
    while cursor < len(raw):
        if cursor + 8 > len(raw):
            raise ExactSlotImportError("Replacement has a truncated RIFF chunk header")
        chunk_count += 1
        if chunk_count > MAX_RIFF_CHUNKS:
            raise ExactSlotImportError("Replacement has too many RIFF chunks")
        chunk_id = raw[cursor : cursor + 4]
        chunk_size = struct.unpack_from("<I", raw, cursor + 4)[0]
        start = cursor + 8
        end = start + chunk_size
        padded_end = end + (chunk_size & 1)
        if end > len(raw) or padded_end > len(raw):
            raise ExactSlotImportError("Replacement RIFF chunk extends beyond the file")
        if chunk_size & 1 and raw[end] != 0:
            raise ExactSlotImportError("Replacement RIFF chunk has nonzero pad data")
        chunk = raw[start:end]
        if chunk_id == b"fmt ":
            fmt_chunks.append(chunk)
        elif chunk_id == b"data":
            data_chunks.append(chunk)
        else:
            ancillary_count += 1
        cursor = padded_end
    if cursor != len(raw):
        raise ExactSlotImportError("Replacement RIFF has trailing bytes")
    if len(fmt_chunks) != 1:
        raise ExactSlotImportError("Replacement must contain exactly one fmt chunk")
    if len(data_chunks) != 1:
        raise ExactSlotImportError("Replacement must contain exactly one data chunk")

    fmt = fmt_chunks[0]
    if len(fmt) != XMA1_ONE_STREAM_FORMAT_SIZE:
        raise ExactSlotImportError(
            "Replacement XMA1 fmt chunk must describe exactly one stream"
        )
    (
        format_tag,
        bits_per_sample,
        encode_options,
        largest_skip,
        stream_count,
        loop_count,
        encoder_version,
    ) = struct.unpack_from("<HHHHHBB", fmt)
    if format_tag != XMA1_FORMAT_TAG:
        raise ExactSlotImportError(
            f"Replacement format tag is 0x{format_tag:04x}, expected XMA1 0x0165"
        )
    if stream_count != 1:
        raise ExactSlotImportError("Replacement XMA1 must contain exactly one stream")
    if bits_per_sample != 16:
        raise ExactSlotImportError("Replacement XMA1 must declare 16-bit output")
    (
        pseudo_bytes_per_second,
        sample_rate,
        loop_start_bit,
        loop_end_bit,
        loop_subframe,
        channels,
        channel_mask,
    ) = struct.unpack_from("<IIIIBBH", fmt, XMA1_BASE_FORMAT_SIZE)
    if channels not in (1, 2):
        raise ExactSlotImportError(
            "Replacement one-stream XMA1 must contain one or two channels"
        )
    if not 1 <= sample_rate <= MAX_SAMPLE_RATE:
        raise ExactSlotImportError("Replacement XMA1 sample rate is out of bounds")
    expected_pseudo = sample_rate * channels // 2
    if pseudo_bytes_per_second != expected_pseudo:
        raise ExactSlotImportError(
            "Replacement XMA1 pseudo-byte rate is inconsistent with its stream layout"
        )

    payload = data_chunks[0]
    if (
        not payload
        or len(payload) > MAX_PAYLOAD_BYTES
        or len(payload) % apf_audio.XMA_PACKET_SIZE
    ):
        raise ExactSlotImportError(
            "Replacement XMA1 data must be a nonempty 0x800-byte packet multiple"
        )
    if not 0 <= loop_start_bit <= loop_end_bit <= len(payload) * 8:
        raise ExactSlotImportError("Replacement XMA1 bit bounds leave its data chunk")
    return ParsedXma1Riff(
        channels=channels,
        sample_rate=sample_rate,
        bits_per_sample=bits_per_sample,
        encode_options=encode_options,
        largest_skip=largest_skip,
        loop_count=loop_count,
        encoder_version=encoder_version,
        pseudo_bytes_per_second=pseudo_bytes_per_second,
        loop_start_bit=loop_start_bit,
        loop_end_bit=loop_end_bit,
        loop_subframe=loop_subframe,
        channel_mask=channel_mask,
        payload=payload,
        ancillary_chunk_count=ancillary_count,
    )


def _packet_contract(payload: bytes) -> dict[str, object]:
    try:
        summary = apf_audio.summarize_packets(payload)
    except apf_audio.AudioError as exc:
        raise ExactSlotImportError(f"Replacement packet framing is invalid: {exc}") from exc
    packet_count = int(summary["packet_count"])
    if not bool(summary["all_packets_classify_xma1"]):
        raise ExactSlotImportError("Every replacement packet must classify as XMA1")
    if not bool(summary["all_xma1_metadata_is_2"]):
        raise ExactSlotImportError("Every replacement packet must use XMA1 metadata value 2")
    if not bool(summary["all_xma1_packet_skips_are_zero"]):
        raise ExactSlotImportError("Every replacement packet must use packet skip 0")
    if summary["xma1_sequence_distribution"] != {"0": packet_count}:
        raise ExactSlotImportError("Every replacement packet must use APF sequence nibble 0")
    return summary


def _normalize_target(
    target: ExactSlotTarget | Mapping[str, object],
) -> ExactSlotTarget:
    if isinstance(target, ExactSlotTarget):
        return validate_target(target)
    return target_from_metadata(target)


def asset_id(outer_index: int, inner_index: int) -> str:
    """Return the product's stable standalone-AUDO asset identity."""

    if type(outer_index) is not int or outer_index < 0:
        raise ExactSlotImportError("AUDO outer index must be a nonnegative whole number")
    if type(inner_index) is not int or inner_index < 0:
        raise ExactSlotImportError("AUDO inner index must be a nonnegative whole number")
    return f"{ASSET_ID_PREFIX}:{outer_index}:{inner_index}"


def _physical_pack_span(
    entry: apf_outer.Entry, relative_offset: int, length: int
) -> tuple[str, int]:
    """Map one entry-relative range to exactly one physical pack span."""

    wanted_start = relative_offset
    wanted_end = relative_offset + length
    entry_cursor = 0
    matches: list[tuple[str, int, int]] = []
    for segment in entry.segments:
        segment_start = entry_cursor
        segment_end = segment_start + segment.size
        start = max(wanted_start, segment_start)
        end = min(wanted_end, segment_end)
        if start < end:
            matches.append(
                (
                    segment.pack_name,
                    segment.pack_offset + start - segment_start,
                    end - start,
                )
            )
        entry_cursor = segment_end
    if len(matches) != 1 or matches[0][2] != length:
        raise ExactSlotImportError(
            "AUDO SRAM payload is not one physically contiguous pack span"
        )
    return matches[0][0], matches[0][1]


def _resolve_item(
    reader: apf_inner.ArchiveReader,
    record: apf_inner.IFFRecord,
    item: apf_inner.DataFile,
    cache: dict[int, bytes],
) -> tuple[ExactSlotTarget, bytes, str, int]:
    if item.type_name != apf_audio.AUDO_TYPE:
        raise ExactSlotImportError("Selected inner resource is not standalone AUDO")
    try:
        metadata_part, payload_part = apf_audio._identify_parts(record, item)  # type: ignore[attr-defined]
    except apf_audio.AudioError as exc:
        raise ExactSlotImportError(f"AUDO source parts are unsupported: {exc}") from exc
    block = record.blocks[payload_part.block_index]
    if block.is_compressed:
        raise ExactSlotImportError(
            "AUDO SRAM payload is compressed; exact physical-slot import is unavailable"
        )
    if (
        payload_part.offset < 0
        or payload_part.length <= 0
        or payload_part.offset + payload_part.length > block.uncompressed_length
    ):
        raise ExactSlotImportError("AUDO SRAM part leaves its owning block")
    try:
        metadata_bytes = apf_audio._read_part(  # type: ignore[attr-defined]
            reader,
            record,
            metadata_part,
            cache,
            apf_inner.DEFAULT_MAX_DECOMPRESSED,
        )
        payload = apf_audio._read_part(  # type: ignore[attr-defined]
            reader,
            record,
            payload_part,
            cache,
            apf_inner.DEFAULT_MAX_DECOMPRESSED,
        )
        target = target_from_metadata(apf_audio.parse_metadata(metadata_bytes))
    except (apf_audio.AudioError, apf_inner.FormatError) as exc:
        raise ExactSlotImportError(f"Could not read standalone AUDO source: {exc}") from exc
    if target.encoded_size != payload_part.length or len(payload) != target.encoded_size:
        raise ExactSlotImportError("AUDO source metadata and SRAM allocation sizes disagree")
    validate_stored_payload(payload, target)
    entry_relative = block.start_offset + payload_part.offset
    pack_name, pack_offset = _physical_pack_span(
        record.entry, entry_relative, payload_part.length
    )
    if pack_name != "0A":
        raise ExactSlotImportError(
            f"AUDO SRAM payload is in {pack_name}, not the bounded 0A target"
        )
    return target, payload, pack_name, pack_offset


def resolve_target(
    index_0a: Path, outer_index: int, inner_index: int
) -> ResolvedExactSlot:
    """Resolve one source AUDO to its exact, uncompressed physical 0A span."""

    return resolve_targets(index_0a, ((outer_index, inner_index),))[
        (outer_index, inner_index)
    ]


def resolve_targets(
    index_0a: Path,
    coordinates: Iterable[tuple[int, int]],
) -> Mapping[tuple[int, int], ResolvedExactSlot]:
    """Resolve a bounded coordinate batch with one archive/reader pass."""

    try:
        supplied = tuple(coordinates)
    except TypeError as exc:
        raise ExactSlotImportError("AUDO target coordinates must be iterable") from exc
    if len(supplied) > EXPECTED_STANDALONE_AUDO_COUNT:
        raise ExactSlotImportError(
            f"At most {EXPECTED_STANDALONE_AUDO_COUNT} AUDO targets may be resolved"
        )
    normalized: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for coordinate in supplied:
        if not isinstance(coordinate, tuple) or len(coordinate) != 2:
            raise ExactSlotImportError(
                "Each AUDO target coordinate must be an (outer_index, inner_index) tuple"
            )
        outer_index, inner_index = coordinate
        asset_id(outer_index, inner_index)
        if coordinate in seen:
            raise ExactSlotImportError(
                f"AUDO target coordinate was selected twice: {outer_index}:{inner_index}"
            )
        seen.add(coordinate)
        normalized.append(coordinate)
    normalized.sort()
    if not normalized:
        return {}

    grouped: dict[int, list[int]] = {}
    for outer_index, inner_index in normalized:
        grouped.setdefault(outer_index, []).append(inner_index)
    resolved: dict[tuple[int, int], ResolvedExactSlot] = {}
    try:
        archive = apf_outer.parse_archive(index_0a)
        entry_by_index = {entry.table_index: entry for entry in archive.entries}
        if len(entry_by_index) != len(archive.entries):
            raise ExactSlotImportError("Source has duplicate outer table indices")
        with apf_inner.ArchiveReader(archive) as reader:
            for outer_index in sorted(grouped):
                entry = entry_by_index.get(outer_index)
                if entry is None:
                    raise ExactSlotImportError(
                        f"Source has no unique outer entry {outer_index}"
                    )
                record = apf_inner.parse_iff(reader, entry)
                if record.warnings:
                    raise ExactSlotImportError(
                        f"Outer {outer_index} has unsupported IFF warnings"
                    )
                cache: dict[int, bytes] = {}
                for inner_index in grouped[outer_index]:
                    try:
                        item = record.files[inner_index]
                    except IndexError as exc:
                        raise ExactSlotImportError(
                            f"Outer {outer_index} has no inner file {inner_index}"
                        ) from exc
                    if item.index != inner_index:
                        raise ExactSlotImportError(
                            "AUDO inner indices are no longer contiguous"
                        )
                    target, payload, pack_name, pack_offset = _resolve_item(
                        reader, record, item, cache
                    )
                    coordinate = (outer_index, inner_index)
                    resolved[coordinate] = ResolvedExactSlot(
                        asset_id=asset_id(*coordinate),
                        name=str(item.name or f"file_{inner_index:04d}"),
                        outer_index=outer_index,
                        inner_index=inner_index,
                        target=target,
                        pack_name=pack_name,
                        pack_offset=pack_offset,
                        encoded_size=target.encoded_size,
                        source_payload_sha256=_sha256(payload),
                    )
    except ExactSlotImportError:
        raise
    except (
        OSError,
        apf_audio.AudioError,
        apf_inner.FormatError,
        apf_outer.FormatError,
    ) as exc:
        raise ExactSlotImportError(f"Could not resolve standalone AUDO target: {exc}") from exc
    return resolved


def _scan_original_audio_fingerprints(
    index_0a: Path,
    *,
    include_packets: bool,
) -> tuple[frozenset[str], frozenset[bytes], int, int]:
    """Hash the complete standalone-AUDO domain in one bounded archive pass."""

    payload_hashes: set[str] = set()
    packet_hashes: set[bytes] = set()
    occurrence_count = 0
    packet_occurrence_count = 0
    try:
        archive = apf_outer.parse_archive(index_0a)
        with apf_inner.ArchiveReader(archive) as reader:
            for entry in archive.entries:
                if entry.head_hex != f"{apf_inner.IFF_MAGIC:08x}":
                    continue
                record = apf_inner.parse_iff(reader, entry)
                if record.warnings:
                    raise ExactSlotImportError(
                        f"Outer {entry.table_index} has unsupported IFF warnings"
                    )
                cache: dict[int, bytes] = {}
                for item in record.files:
                    if item.type_name != apf_audio.AUDO_TYPE:
                        continue
                    _target, payload, _pack_name, _pack_offset = _resolve_item(
                        reader, record, item, cache
                    )
                    payload_hashes.add(_sha256(payload))
                    if include_packets:
                        for fingerprint in _packet_sha256s(payload):
                            packet_hashes.add(fingerprint)
                            packet_occurrence_count += 1
                    occurrence_count += 1
    except ExactSlotImportError:
        raise
    except (
        OSError,
        apf_audio.AudioError,
        apf_inner.FormatError,
        apf_outer.FormatError,
    ) as exc:
        raise ExactSlotImportError(
            f"Could not inventory source AUDO payload hashes: {exc}"
        ) from exc
    if occurrence_count != EXPECTED_STANDALONE_AUDO_COUNT:
        raise ExactSlotImportError(
            "Source standalone-AUDO inventory changed: found "
            f"{occurrence_count}, expected {EXPECTED_STANDALONE_AUDO_COUNT}"
        )
    return (
        frozenset(payload_hashes),
        frozenset(packet_hashes),
        occurrence_count,
        packet_occurrence_count,
    )


def original_audio_fingerprints(index_0a: Path) -> SourceAudioFingerprints:
    """Fingerprint all standalone sounds and their complete 0x800-byte packets.

    The payload and packet digests are computed together, so a product session
    does not perform separate source scans for exact-retail and near-retail
    protection.  Only digests and aggregate counts survive the scan.
    """

    payloads, packets, occurrence_count, packet_occurrence_count = (
        _scan_original_audio_fingerprints(index_0a, include_packets=True)
    )
    inventory = SourceAudioFingerprints(
        domain=SOURCE_AUDIO_DOMAIN,
        payload_sha256s=payloads,
        packet_sha256s=packets,
        payload_occurrence_count=occurrence_count,
        packet_occurrence_count=packet_occurrence_count,
    )
    return _validated_source_audio_fingerprints(
        inventory,
        expected_domain=SOURCE_AUDIO_DOMAIN,
        expected_payload_occurrences=EXPECTED_STANDALONE_AUDO_COUNT,
    )


def original_payload_hashes(index_0a: Path) -> frozenset[str]:
    """Hash every source standalone-AUDO payload without retaining packets."""

    payloads, _packets, _occurrences, _packet_occurrences = (
        _scan_original_audio_fingerprints(index_0a, include_packets=False)
    )
    return payloads


def _validate_shape(
    parsed: ParsedXma1Riff, target: ExactSlotTarget
) -> dict[str, object]:
    if parsed.channels != target.channels:
        raise ExactSlotImportError(
            f"Replacement has {parsed.channels} channel(s); this slot requires {target.channels}"
        )
    if parsed.sample_rate != target.sample_rate:
        raise ExactSlotImportError(
            f"Replacement sample rate is {parsed.sample_rate} Hz; this slot requires "
            f"{target.sample_rate} Hz"
        )
    if len(parsed.payload) != target.encoded_size:
        raise ExactSlotImportError(
            f"Replacement encoded data is {len(parsed.payload)} bytes; this exact slot "
            f"requires {target.encoded_size} bytes"
        )
    return _packet_contract(parsed.payload)


def _prepare_validation_riff(
    data: bytes,
    target: ExactSlotTarget | Mapping[str, object],
) -> tuple[bytes, bytes, dict[str, object]]:
    """Structurally validate and rewrap user packets with target metadata.

    This internal function does not authorize a replacement by itself because
    it does not invoke a decoder.  The target-derived RIFF it returns is an
    ephemeral decoder input, never a project payload.
    """

    normalized = _normalize_target(target)
    parsed = parse_xma1_riff(data)
    packet_summary = _validate_shape(parsed, normalized)
    try:
        canonical = apf_audio.make_xma1_riff(
            parsed.payload,
            normalized.channels,
            normalized.sample_rate,
            normalized.loop_start_bit,
            normalized.loop_end_bit,
            normalized.loop_subframe,
        )
    except apf_audio.AudioError as exc:
        raise ExactSlotImportError(f"Could not rewrap replacement packets: {exc}") from exc
    return canonical, parsed.payload, packet_summary


def validate_stored_payload(
    data: bytes,
    target: ExactSlotTarget | Mapping[str, object],
) -> bytes:
    """Validate and return one stored raw ``.xma1-packets`` payload.

    This inexpensive build-time gate repeats the exact target-length and APF
    packet checks but intentionally does not rerun FFmpeg.  The costly complete
    decode belongs at user RIFF import time.  Target metadata remains sourced
    from the user's game and is not embedded in ``data``.
    """

    normalized = _normalize_target(target)
    payload = _as_bytes(data)
    if len(payload) != normalized.encoded_size:
        raise ExactSlotImportError(
            f"Stored XMA1 packet payload is {len(payload)} bytes; this exact slot "
            f"requires {normalized.encoded_size} bytes"
        )
    _packet_contract(payload)
    return payload


def _resolve_ffmpeg(ffmpeg_path: str | Path | None) -> str:
    if ffmpeg_path is None:
        executable = shutil.which("ffmpeg")
        if executable is None:
            raise ExactSlotImportError(
                "FFmpeg is required to verify pre-encoded XMA1 replacements"
            )
        return executable
    executable = str(ffmpeg_path)
    if not executable:
        raise ExactSlotImportError("FFmpeg executable path is empty")
    return executable


def _decode_to_path(
    canonical_riff: bytes,
    target: ExactSlotTarget,
    output_path: Path,
    *,
    ffmpeg_path: str | Path | None,
    timeout_seconds: int,
    cancel_requested: apf_audio.CancelRequested | None = None,
) -> dict[str, object]:
    if type(timeout_seconds) is not int or timeout_seconds <= 0:
        raise ExactSlotImportError("FFmpeg decode timeout must be a positive whole number")
    executable = _resolve_ffmpeg(ffmpeg_path)

    try:
        command = [
            executable,
            "-hide_banner",
            "-nostdin",
            "-v",
            "error",
            "-xerror",
            "-y",
            "-i",
            "pipe:0",
            "-map",
            "0:a:0",
            "-map_metadata",
            "-1",
            "-c:a",
            "pcm_s16le",
            "-f",
            "wav",
            str(output_path),
        ]
        if cancel_requested is None:
            completed = subprocess.run(
                command,
                input=canonical_riff,
                capture_output=True,
                check=False,
                timeout=timeout_seconds,
            )
        else:
            completed = apf_audio.run_cancellable_subprocess(
                command,
                cancel_requested=cancel_requested,
                input_data=canonical_riff,
                timeout_seconds=timeout_seconds,
            )
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        if completed.returncode != 0 or stderr or not output_path.is_file():
            detail = stderr or f"FFmpeg exited with status {completed.returncode}"
            raise ExactSlotImportError(
                f"Replacement XMA1 did not decode cleanly with FFmpeg: {detail}"
            )
        try:
            wav = apf_audio.parse_pcm_wav(output_path)
        except (OSError, apf_audio.AudioError) as exc:
            raise ExactSlotImportError(
                f"FFmpeg output could not be validated as PCM WAV: {exc}"
            ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ExactSlotImportError(
            f"Replacement XMA1 decode exceeded {timeout_seconds} seconds"
        ) from exc
    except OSError as exc:
        raise ExactSlotImportError(f"Could not run FFmpeg: {exc}") from exc

    if wav["bits_per_sample"] != 16:
        raise ExactSlotImportError("FFmpeg did not produce 16-bit PCM")
    if wav["channels"] != target.channels:
        raise ExactSlotImportError(
            f"Decoded replacement has {wav['channels']} channel(s); target requires "
            f"{target.channels}"
        )
    if wav["sample_rate"] != target.sample_rate:
        raise ExactSlotImportError(
            f"Decoded replacement is {wav['sample_rate']} Hz; target requires "
            f"{target.sample_rate} Hz"
        )
    decoded_samples = int(wav["sample_count_per_channel"])
    if decoded_samples <= 0:
        raise ExactSlotImportError("Decoded replacement contains no audio frames")
    delta = target.declared_sample_count - decoded_samples
    if abs(delta) > DECODE_SAMPLE_TOLERANCE:
        raise ExactSlotImportError(
            "Decoded replacement duration does not fit this exact slot: "
            f"target minus decoded is {delta} samples (allowed -127 through 127)"
        )
    if delta == 0:
        status = "decoder_verified_exact_target_samples"
    elif delta > 0:
        status = "decoder_verified_with_target_tail_gap"
    else:
        status = "decoder_verified_with_padding_tail"
    return {
        "status": status,
        "channels": wav["channels"],
        "sample_rate": wav["sample_rate"],
        "bits_per_sample": wav["bits_per_sample"],
        "decoded_sample_count_per_channel": decoded_samples,
        "target_minus_decoded_samples": delta,
        "sample_tolerance": DECODE_SAMPLE_TOLERANCE,
        "ffmpeg_xerror": True,
    }


def _decode_complete(
    canonical_riff: bytes,
    target: ExactSlotTarget,
    *,
    ffmpeg_path: str | Path | None,
    timeout_seconds: int,
) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="apf-xma1-verify-") as directory:
        return _decode_to_path(
            canonical_riff,
            target,
            Path(directory) / "decoded.wav",
            ffmpeg_path=ffmpeg_path,
            timeout_seconds=timeout_seconds,
        )


def _validate_exact_slot_import_for_source_audio(
    data: bytes,
    target: ExactSlotTarget | Mapping[str, object],
    source_fingerprints: SourceAudioFingerprints,
    *,
    expected_domain: str,
    expected_payload_occurrences: int,
    expected_unique_payloads: int | None = None,
    ffmpeg_path: str | Path | None = None,
    timeout_seconds: int = DEFAULT_DECODE_TIMEOUT_SECONDS,
) -> ExactSlotImportResult:
    """Shared decoder contract with a caller-selected complete source domain."""

    normalized = _normalize_target(target)
    parsed_input = parse_xma1_riff(data)
    canonical, payload, packet_summary = _prepare_validation_riff(data, normalized)
    _reject_source_audio_reuse(
        payload,
        source_fingerprints,
        expected_domain=expected_domain,
        expected_payload_occurrences=expected_payload_occurrences,
        expected_unique_payloads=expected_unique_payloads,
    )
    decode = _decode_complete(
        canonical,
        normalized,
        ffmpeg_path=ffmpeg_path,
        timeout_seconds=timeout_seconds,
    )
    return _accepted_result(
        payload,
        normalized,
        packet_summary,
        decode,
        input_kind="riff_xma1",
        ancillary_chunks_discarded=parsed_input.ancillary_chunk_count,
    )


def validate_exact_slot_import(
    data: bytes,
    target: ExactSlotTarget | Mapping[str, object],
    source_fingerprints: SourceAudioFingerprints,
    *,
    _expected_source_domain: str = SOURCE_AUDIO_DOMAIN,
    _expected_payload_occurrences: int = EXPECTED_STANDALONE_AUDO_COUNT,
    _expected_unique_payloads: int | None = None,
    ffmpeg_path: str | Path | None = None,
    timeout_seconds: int = DEFAULT_DECODE_TIMEOUT_SECONDS,
) -> ExactSlotImportResult:
    """Authorize one standalone-AUDO exact-slot pre-encoded replacement."""

    return _validate_exact_slot_import_for_source_audio(
        data,
        target,
        source_fingerprints,
        expected_domain=_expected_source_domain,
        expected_payload_occurrences=_expected_payload_occurrences,
        expected_unique_payloads=_expected_unique_payloads,
        ffmpeg_path=ffmpeg_path,
        timeout_seconds=timeout_seconds,
    )


def _validate_stored_payload_complete_for_source_audio(
    payload: bytes,
    target: ExactSlotTarget | Mapping[str, object],
    source_fingerprints: SourceAudioFingerprints,
    *,
    expected_domain: str,
    expected_payload_occurrences: int,
    expected_unique_payloads: int | None = None,
    ffmpeg_path: str | Path | None = None,
    timeout_seconds: int = DEFAULT_DECODE_TIMEOUT_SECONDS,
) -> ExactSlotImportResult:
    """Shared raw-project decoder contract with complete source protection."""

    normalized = _normalize_target(target)
    checked = validate_stored_payload(payload, normalized)
    _reject_source_audio_reuse(
        checked,
        source_fingerprints,
        expected_domain=expected_domain,
        expected_payload_occurrences=expected_payload_occurrences,
        expected_unique_payloads=expected_unique_payloads,
    )
    packet_summary = _packet_contract(checked)
    try:
        validation_riff = apf_audio.make_xma1_riff(
            checked,
            normalized.channels,
            normalized.sample_rate,
            normalized.loop_start_bit,
            normalized.loop_end_bit,
            normalized.loop_subframe,
        )
    except apf_audio.AudioError as exc:
        raise ExactSlotImportError(f"Could not rewrap stored XMA1 packets: {exc}") from exc
    decode = _decode_complete(
        validation_riff,
        normalized,
        ffmpeg_path=ffmpeg_path,
        timeout_seconds=timeout_seconds,
    )
    return _accepted_result(
        checked,
        normalized,
        packet_summary,
        decode,
        input_kind="raw_xma1_packets",
        ancillary_chunks_discarded=0,
    )


def validate_stored_payload_complete(
    payload: bytes,
    target: ExactSlotTarget | Mapping[str, object],
    source_fingerprints: SourceAudioFingerprints,
    *,
    _expected_source_domain: str = SOURCE_AUDIO_DOMAIN,
    _expected_payload_occurrences: int = EXPECTED_STANDALONE_AUDO_COUNT,
    _expected_unique_payloads: int | None = None,
    ffmpeg_path: str | Path | None = None,
    timeout_seconds: int = DEFAULT_DECODE_TIMEOUT_SECONDS,
) -> ExactSlotImportResult:
    """Reauthorize a standalone-AUDO raw project payload with a complete decode."""

    return _validate_stored_payload_complete_for_source_audio(
        payload,
        target,
        source_fingerprints,
        expected_domain=_expected_source_domain,
        expected_payload_occurrences=_expected_payload_occurrences,
        expected_unique_payloads=_expected_unique_payloads,
        ffmpeg_path=ffmpeg_path,
        timeout_seconds=timeout_seconds,
    )


def decode_stored_payload_to_wav(
    payload: bytes,
    target: ExactSlotTarget | Mapping[str, object],
    destination: Path,
    *,
    ffmpeg_path: str | Path | None = None,
    timeout_seconds: int = DEFAULT_DECODE_TIMEOUT_SECONDS,
    cancel_requested: apf_audio.CancelRequested | None = None,
) -> Mapping[str, object]:
    """Decode a staged raw replacement to a new, verified PCM WAV atomically.

    The destination must not already exist.  FFmpeg receives the ephemeral
    target-metadata wrapper through stdin and writes to a hidden sibling temp
    file.  Only after the complete decode and channel/rate/sample validation
    pass is that PCM file hard-linked into the caller's requested path with
    no-replace semantics.  The target wrapper is never written to disk.
    """

    apf_audio.check_cancel_requested(cancel_requested)
    if not isinstance(destination, Path):
        raise ExactSlotImportError("PCM WAV destination must be a Path")
    if destination.suffix.lower() != ".wav" or not destination.name:
        raise ExactSlotImportError("PCM preview destination must end in .wav")
    if destination.exists() or destination.is_symlink():
        raise ExactSlotImportError("PCM preview destination already exists")
    parent = destination.parent
    if not parent.is_dir():
        raise ExactSlotImportError("PCM preview destination directory does not exist")

    normalized = _normalize_target(target)
    checked = validate_stored_payload(payload, normalized)
    apf_audio.check_cancel_requested(cancel_requested)
    try:
        validation_riff = apf_audio.make_xma1_riff(
            checked,
            normalized.channels,
            normalized.sample_rate,
            normalized.loop_start_bit,
            normalized.loop_end_bit,
            normalized.loop_subframe,
        )
    except apf_audio.AudioError as exc:
        raise ExactSlotImportError(f"Could not rewrap stored XMA1 packets: {exc}") from exc

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    linked = False
    try:
        decode = _decode_to_path(
            validation_riff,
            normalized,
            temporary,
            ffmpeg_path=ffmpeg_path,
            timeout_seconds=timeout_seconds,
            cancel_requested=cancel_requested,
        )
        apf_audio.check_cancel_requested(cancel_requested)
        wav_size = temporary.stat().st_size
        wav_sha256 = _sha256(temporary.read_bytes())
        apf_audio.check_cancel_requested(cancel_requested)
        # The decoded WAV must be durable before the hard link publishes it.
        # ``fsync_path`` keeps the POSIX read-only flush and opens read-write
        # only on Windows, where ``FlushFileBuffers`` rejects a read-only handle
        # with ``EBADF``.
        fsync_path(temporary)
        try:
            apf_audio.check_cancel_requested(cancel_requested)
            os.link(temporary, destination)
        except FileExistsError as exc:
            raise ExactSlotImportError(
                "PCM preview destination was created by another process"
            ) from exc
        except OSError as exc:
            raise ExactSlotImportError(
                f"Could not atomically publish decoded PCM WAV: {exc}"
            ) from exc
        linked = True
        return {
            "schema": WAV_EXPORT_SCHEMA,
            "status": "decoder_verified_pcm_wav",
            "payload_sha256": _sha256(checked),
            "wav_size": wav_size,
            "wav_sha256": wav_sha256,
            "channels": normalized.channels,
            "sample_rate": normalized.sample_rate,
            "bits_per_sample": 16,
            "decoded_sample_count_per_channel": decode[
                "decoded_sample_count_per_channel"
            ],
            "target_minus_decoded_samples": decode[
                "target_minus_decoded_samples"
            ],
            "ffmpeg_xerror": True,
            "atomic_no_replace": True,
            "contains_target_wrapper": False,
            "contains_original_payload": False,
            "contains_source_path": False,
        }
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            # A successful destination is already a complete independent link;
            # failure to clean a hidden temp should not make callers overwrite it.
            if not linked:
                raise


def _accepted_result(
    payload: bytes,
    target: ExactSlotTarget,
    packet_summary: Mapping[str, object],
    decode: Mapping[str, object],
    *,
    input_kind: str,
    ancillary_chunks_discarded: int,
) -> ExactSlotImportResult:
    packet_count = int(packet_summary["packet_count"])
    receipt: dict[str, object] = {
        "schema": SCHEMA,
        "status": "accepted",
        "contract": "standalone_audo_preencoded_xma1_exact_slot",
        "target": {
            "channels": target.channels,
            "sample_rate": target.sample_rate,
            "encoded_size": target.encoded_size,
            "declared_sample_count": target.declared_sample_count,
        },
        "replacement": {
            "payload_size": len(payload),
            "payload_sha256": _sha256(payload),
            "packet_count": packet_count,
        },
        "validation": {
            "input_kind": input_kind,
            "stream_count": 1,
            "input_ancillary_chunks_discarded": ancillary_chunks_discarded,
            "all_packets_classify_xma1": True,
            "all_packet_metadata_is_2": True,
            "all_packet_sequences_are_zero": True,
            "all_packet_skips_are_zero": True,
            "decode": decode,
        },
        "retail_data": {
            "contains_original_payload": False,
            "contains_preimage": False,
            "contains_source_path": False,
        },
    }
    return ExactSlotImportResult(
        payload=payload,
        receipt=receipt,
    )


def encode_receipt(receipt: Mapping[str, object]) -> bytes:
    """Encode a receipt in the product's canonical JSON form."""

    if not isinstance(receipt, Mapping) or receipt.get("schema") != SCHEMA:
        raise ExactSlotImportError("Exact-slot import receipt has the wrong schema")
    try:
        encoded = json.dumps(
            receipt,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ExactSlotImportError(f"Exact-slot import receipt is not canonical JSON: {exc}") from exc
    return (encoded + "\n").encode("ascii")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index_0a", type=Path, help="path to the user's APF 0A file")
    parser.add_argument("--entry", type=int, required=True, help="AUDO outer index")
    parser.add_argument("--file", type=int, required=True, help="AUDO inner index")
    parser.add_argument(
        "--input-xma",
        type=Path,
        required=True,
        help="pre-encoded one-stream RIFF XMA1 replacement",
    )
    parser.add_argument(
        "--validate-exact-slot",
        action="store_true",
        required=True,
        help="run strict target, packet, retail-data, and FFmpeg validation",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        resolved = resolve_target(args.index_0a, args.entry, args.file)
        info = args.input_xma.lstat()
        if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise ExactSlotImportError("Input XMA1 replacement must be a regular file")
        if info.st_size > resolved.encoded_size + 1024 * 1024:
            raise ExactSlotImportError("Input XMA1 replacement is too large for this slot")
        supplied = args.input_xma.read_bytes()
        source_fingerprints = original_audio_fingerprints(args.index_0a)
        result = validate_exact_slot_import(
            supplied,
            resolved.target,
            source_fingerprints,
        )
        # Keep the CLI boundary safe even if a future validator wrapper is
        # replaced or mocked: authorization always ends with the packet gate.
        reject_source_audio_reuse(result.payload, source_fingerprints)
        print(result.receipt_bytes.decode("ascii"), end="")
        return 0
    except (OSError, ExactSlotImportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

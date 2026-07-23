#!/usr/bin/env python3
"""Strict APF 2K8 external-AUSB XMA1 exact-slot writer.

APF's 20 ``AUSB`` descriptors address 45,514 substream rows in 19 physical
external banks.  This module discovers those descriptors from the user's own
source, resolves each row to a canonical physical range (including ranges that
cross pack files), validates pre-encoded one-stream RIFF XMA1 replacements, and
compiles raw user packets into exact pack-local writes.

The contract never repacks a bank and never edits an AUSB descriptor.  Channel
count, sample rate, encoded packet length, and duration-derived sample count
must remain exact.  AUSB exposes no explicit per-substream loop fields, so an
ephemeral zero-loop RIFF wrapper is used only for complete FFmpeg validation.
Projects store only user packets and retail-free metadata.

One recognized physical range, ``cwdloop`` external outer 717 range 0, has two
descriptor owners.  Resolved targets therefore carry a canonical physical ID
and every owner.  Overlapping edits are deduplicated only when their replacement
bytes agree; divergent alias edits fail closed.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
from typing import Collection, Iterable, Mapping
import zlib

import apf_audio
import apf_audo_exact_slot
import apf_inner
import apf_outer


SCHEMA = "apf2k8_ausb_exact_slot_import/v1"
WAV_EXPORT_SCHEMA = "apf2k8_ausb_exact_slot_pcm_export/v1"
MODIFICATION_KIND = "ausb_exact_slot_xma1"
ASSET_ID_PREFIX = "apf:audio:ausb"
EXPECTED_DESCRIPTOR_COUNT = 20
EXPECTED_OWNER_ROW_COUNT = 45_514
EXPECTED_CANONICAL_RANGE_COUNT = 45_513
EXPECTED_EXTERNAL_BANK_COUNT = 19
EXPECTED_UNIQUE_SOURCE_PAYLOAD_HASH_COUNT = 40_316
SOURCE_AUDIO_DOMAIN = "external_ausb"
XMA_PACKET_SIZE = apf_audio.XMA_PACKET_SIZE
DEFAULT_DECODE_TIMEOUT_SECONDS = 300
PAIR_DURATION_TOLERANCE_SECONDS = 0.001
JUKEBOX_STEREO_NAME = "jukeboxmusic"
JUKEBOX_MONO_NAME = "jukebox22"


class AusbExactSlotError(ValueError):
    """The request left the bounded APF AUSB exact-slot contract."""


@dataclass(frozen=True, order=True)
class AusbOwner:
    """One semantic descriptor row that consumes a physical AUSB range."""

    descriptor_outer_index: int
    descriptor_inner_index: int
    substream_index: int
    bank_name: str
    external_filename: str
    channels: int
    sample_rate: int
    duration_value_bits: int
    duration_seconds: float
    declared_sample_count: int

    @property
    def asset_id(self) -> str:
        return asset_id(
            self.descriptor_outer_index,
            self.descriptor_inner_index,
            self.substream_index,
        )

    @property
    def coordinates(self) -> tuple[int, int, int]:
        return (
            self.descriptor_outer_index,
            self.descriptor_inner_index,
            self.substream_index,
        )


@dataclass(frozen=True)
class PhysicalSpan:
    """One physical pack slice of a canonical substream range."""

    pack_name: str
    pack_offset: int
    length: int
    payload_offset: int


@dataclass(frozen=True)
class ExactSlotTarget:
    """Retail-free target shape for one canonical AUSB allocation."""

    channels: int
    sample_rate: int
    encoded_size: int
    declared_sample_count: int


@dataclass(frozen=True)
class ResolvedExactSlot:
    """One requested row plus all owners of its canonical physical range."""

    asset_id: str
    requested_owner: AusbOwner
    owners: tuple[AusbOwner, ...]
    canonical_physical_id: str
    external_outer_index: int
    external_range_offset: int
    target: ExactSlotTarget
    physical_spans: tuple[PhysicalSpan, ...]
    source_payload_sha256: str

    @property
    def shared_effect(self) -> bool:
        return len(self.owners) > 1

    @property
    def bank_name(self) -> str:
        return self.requested_owner.bank_name

    @property
    def substream_index(self) -> int:
        return self.requested_owner.substream_index


@dataclass(frozen=True)
class ExactSlotImportResult:
    """Canonical user packet payload and a retail-free receipt."""

    payload: bytes
    receipt: Mapping[str, object]

    @property
    def receipt_bytes(self) -> bytes:
        return encode_receipt(self.receipt)


@dataclass(frozen=True)
class CompiledAusbWrite:
    """One exact pack-local write for a disposable staged build copy."""

    pack_name: str
    pack_offset: int
    payload: bytes
    canonical_physical_id: str
    side_payload_offset: int

    @property
    def length(self) -> int:
        return len(self.payload)


@dataclass(frozen=True)
class PairedSoundtrackImportResult:
    """Both accepted encodings for one logical jukebox track."""

    stereo: ExactSlotImportResult
    mono: ExactSlotImportResult
    receipt: Mapping[str, object]

    @property
    def receipt_bytes(self) -> bytes:
        return encode_paired_receipt(self.receipt)


@dataclass(frozen=True)
class _RangeBlueprint:
    external: apf_outer.Entry
    offset: int
    length: int
    owners: tuple[AusbOwner, ...]
    physical_spans: tuple[PhysicalSpan, ...]

    @property
    def canonical_physical_id(self) -> str:
        return (
            f"{ASSET_ID_PREFIX}:physical:{self.external.table_index}:"
            f"{self.offset}:{self.length}"
        )


@dataclass(frozen=True)
class _SourceCatalog:
    archive: apf_outer.Archive
    by_coordinate: Mapping[tuple[int, int, int], _RangeBlueprint]
    canonical_ranges: tuple[_RangeBlueprint, ...]
    bank_coordinates: Mapping[str, tuple[tuple[int, int], ...]]


@dataclass
class _MutableBlueprint:
    external: apf_outer.Entry
    offset: int
    length: int
    owners: list[AusbOwner]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _plain_nonnegative(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise AusbExactSlotError(f"{label} must be a nonnegative whole number")
    return value


def asset_id(outer_index: int, inner_index: int, substream_index: int) -> str:
    """Return the stable semantic identity for one AUSB descriptor row."""

    _plain_nonnegative(outer_index, "AUSB outer index")
    _plain_nonnegative(inner_index, "AUSB inner index")
    _plain_nonnegative(substream_index, "AUSB substream index")
    return f"{ASSET_ID_PREFIX}:{outer_index}:{inner_index}:{substream_index}"


def _physical_spans(
    entry: apf_outer.Entry, relative_offset: int, length: int
) -> tuple[PhysicalSpan, ...]:
    if relative_offset < 0 or length <= 0 or relative_offset + length > entry.size:
        raise AusbExactSlotError("AUSB range leaves its external bank")
    wanted_end = relative_offset + length
    entry_cursor = 0
    payload_cursor = 0
    spans: list[PhysicalSpan] = []
    for segment in entry.segments:
        segment_start = entry_cursor
        segment_end = segment_start + segment.size
        start = max(relative_offset, segment_start)
        end = min(wanted_end, segment_end)
        if start < end:
            span_length = end - start
            spans.append(
                PhysicalSpan(
                    pack_name=segment.pack_name,
                    pack_offset=segment.pack_offset + start - segment_start,
                    length=span_length,
                    payload_offset=payload_cursor,
                )
            )
            payload_cursor += span_length
        entry_cursor = segment_end
        if entry_cursor >= wanted_end:
            break
    if payload_cursor != length or not spans:
        raise AusbExactSlotError("AUSB range could not be mapped to physical packs")
    for previous, current in zip(spans, spans[1:]):
        if current.payload_offset != previous.payload_offset + previous.length:
            raise AusbExactSlotError("AUSB physical spans are not payload-contiguous")
    return tuple(spans)


def _require_no_outer_alias(
    archive: apf_outer.Archive, external: apf_outer.Entry
) -> None:
    overlaps = [
        entry.table_index
        for entry in archive.entries
        if entry.table_index != external.table_index
        and max(entry.virtual_offset, external.virtual_offset)
        < min(entry.virtual_end, external.virtual_end)
    ]
    if overlaps:
        raise AusbExactSlotError(
            f"External bank outer {external.table_index} overlaps {overlaps}"
        )


def _duration_bits(boundary: Mapping[str, object]) -> tuple[int, float]:
    bits = int(str(boundary["value_bits"]), 16)
    value = float(boundary["value_float"])
    if struct.unpack(">f", struct.pack(">I", bits))[0] != value:
        raise AusbExactSlotError("AUSB duration float and bit pattern disagree")
    if not 0.0 < value < 24 * 60 * 60:
        raise AusbExactSlotError("AUSB duration is out of bounds")
    return bits, value


def _discover_source(index_0a: Path) -> _SourceCatalog:
    if not isinstance(index_0a, Path):
        raise AusbExactSlotError("APF source index must be a Path")
    try:
        archive = apf_outer.parse_archive(index_0a)
        external_by_id: dict[int, list[apf_outer.Entry]] = {}
        for entry in archive.entries:
            external_by_id.setdefault(entry.name_id, []).append(entry)

        mutable: dict[tuple[int, int, int], _MutableBlueprint] = {}
        coordinates: dict[tuple[int, int, int], tuple[int, int, int]] = {}
        bank_coordinate_lists: dict[str, list[tuple[int, int]]] = {}
        descriptor_count = 0
        external_indices: set[int] = set()
        owner_row_count = 0
        with apf_inner.ArchiveReader(archive) as reader:
            for entry in archive.entries:
                if entry.head_hex != f"{apf_inner.IFF_MAGIC:08x}":
                    continue
                record = apf_inner.parse_iff(reader, entry)
                if record.warnings:
                    raise AusbExactSlotError(
                        f"AUSB discovery IFF outer {entry.table_index} has warnings"
                    )
                cache: dict[int, bytes] = {}
                for item in record.files:
                    if item.type_name != apf_audio.AUSB_TYPE:
                        continue
                    descriptor_count += 1
                    if len(item.parts) != 1:
                        raise AusbExactSlotError(
                            f"AUSB {entry.table_index}:{item.index} has multiple parts"
                        )
                    part = item.parts[0]
                    if record.blocks[part.block_index].type_hash != (
                        zlib.crc32(b"DRAM") & 0xFFFFFFFF
                    ):
                        raise AusbExactSlotError(
                            f"AUSB {entry.table_index}:{item.index} is outside DRAM"
                        )
                    descriptor = apf_audio._read_part(  # type: ignore[attr-defined]
                        reader,
                        record,
                        part,
                        cache,
                        apf_inner.DEFAULT_MAX_DECOMPRESSED,
                    )
                    parsed = apf_audio.parse_ausb(descriptor)
                    if (
                        int(parsed["constant_48"]) != 1
                        or int(parsed["unknown_50"]) != 4096
                        or parsed["derived_channel_count"] not in (1, 2)
                        or int(parsed["sample_rate"]) <= 0
                    ):
                        raise AusbExactSlotError(
                            f"AUSB {entry.table_index}:{item.index} header changed"
                        )
                    filename = str(parsed["external_filename"])
                    external_id = int(
                        str(parsed["external_filename_crc32_upper_ascii"]), 16
                    )
                    matches = external_by_id.get(external_id, [])
                    if len(matches) != 1:
                        raise AusbExactSlotError(
                            f"AUSB {entry.table_index}:{item.index} resolves to "
                            f"{len(matches)} external banks"
                        )
                    external = matches[0]
                    _require_no_outer_alias(archive, external)
                    external_indices.add(external.table_index)
                    bank_name = str(item.name or f"file_{item.index:04d}")
                    normalized_name = bank_name.casefold()
                    coordinate_pair = (entry.table_index, item.index)
                    bank_coordinate_lists.setdefault(normalized_name, []).append(
                        coordinate_pair
                    )

                    boundaries = list(parsed["entries"])
                    terminal = parsed["terminal_boundary"]
                    if len(boundaries) != int(parsed["entry_count"]):
                        raise AusbExactSlotError("AUSB boundary count changed")
                    if int(terminal["packet_offset"]) != external.size:
                        raise AusbExactSlotError(
                            f"AUSB {entry.table_index}:{item.index} does not cover its bank"
                        )
                    previous_end = 0
                    for substream_index, boundary in enumerate(boundaries):
                        next_boundary = (
                            boundaries[substream_index + 1]
                            if substream_index + 1 < len(boundaries)
                            else terminal
                        )
                        start = int(boundary["packet_offset"])
                        end = int(next_boundary["packet_offset"])
                        if (
                            start != previous_end
                            or not 0 <= start < end <= external.size
                            or start % XMA_PACKET_SIZE
                            or end % XMA_PACKET_SIZE
                        ):
                            raise AusbExactSlotError(
                                f"AUSB {entry.table_index}:{item.index}:{substream_index} "
                                "has noncontiguous packet boundaries"
                            )
                        bits, duration = _duration_bits(next_boundary)
                        owner = AusbOwner(
                            descriptor_outer_index=entry.table_index,
                            descriptor_inner_index=item.index,
                            substream_index=substream_index,
                            bank_name=bank_name,
                            external_filename=filename,
                            channels=int(parsed["derived_channel_count"]),
                            sample_rate=int(parsed["sample_rate"]),
                            duration_value_bits=bits,
                            duration_seconds=duration,
                            declared_sample_count=round(
                                duration * int(parsed["sample_rate"])
                            ),
                        )
                        physical_key = (external.table_index, start, end - start)
                        builder = mutable.get(physical_key)
                        if builder is None:
                            builder = _MutableBlueprint(
                                external=external,
                                offset=start,
                                length=end - start,
                                owners=[],
                            )
                            mutable[physical_key] = builder
                        elif builder.external != external:
                            raise AusbExactSlotError("Canonical AUSB owner changed external bank")
                        builder.owners.append(owner)
                        coordinate = owner.coordinates
                        if coordinate in coordinates:
                            raise AusbExactSlotError("Duplicate AUSB semantic coordinate")
                        coordinates[coordinate] = physical_key
                        owner_row_count += 1
                        previous_end = end
                    if previous_end != external.size:
                        raise AusbExactSlotError("AUSB descriptor leaves an external-bank gap")

        if descriptor_count != EXPECTED_DESCRIPTOR_COUNT:
            raise AusbExactSlotError(
                f"Source exposes {descriptor_count} AUSB descriptors, expected "
                f"{EXPECTED_DESCRIPTOR_COUNT}"
            )
        if owner_row_count != EXPECTED_OWNER_ROW_COUNT:
            raise AusbExactSlotError(
                f"Source exposes {owner_row_count} AUSB rows, expected "
                f"{EXPECTED_OWNER_ROW_COUNT}"
            )
        if len(mutable) != EXPECTED_CANONICAL_RANGE_COUNT:
            raise AusbExactSlotError(
                f"Source exposes {len(mutable)} canonical AUSB ranges, expected "
                f"{EXPECTED_CANONICAL_RANGE_COUNT}"
            )
        if len(external_indices) != EXPECTED_EXTERNAL_BANK_COUNT:
            raise AusbExactSlotError(
                f"Source exposes {len(external_indices)} AUSB external banks, expected "
                f"{EXPECTED_EXTERNAL_BANK_COUNT}"
            )

        # No two distinct canonical ranges may overlap.  Exact aliases were
        # already collapsed into one mutable blueprint above.
        by_external: dict[int, list[_MutableBlueprint]] = {}
        for value in mutable.values():
            by_external.setdefault(value.external.table_index, []).append(value)
        for external_index, values in by_external.items():
            previous_end = -1
            for value in sorted(values, key=lambda row: row.offset):
                if value.offset < previous_end:
                    raise AusbExactSlotError(
                        f"External bank {external_index} has partially overlapping ranges"
                    )
                previous_end = value.offset + value.length

        frozen_by_key: dict[tuple[int, int, int], _RangeBlueprint] = {}
        for key, value in mutable.items():
            owners = tuple(sorted(value.owners))
            first = owners[0]
            if any(
                (
                    owner.channels,
                    owner.sample_rate,
                    owner.duration_value_bits,
                    owner.declared_sample_count,
                )
                != (
                    first.channels,
                    first.sample_rate,
                    first.duration_value_bits,
                    first.declared_sample_count,
                )
                for owner in owners[1:]
            ):
                raise AusbExactSlotError("Aliased AUSB owners disagree on playback shape")
            frozen_by_key[key] = _RangeBlueprint(
                external=value.external,
                offset=value.offset,
                length=value.length,
                owners=owners,
                physical_spans=_physical_spans(
                    value.external, value.offset, value.length
                ),
            )
        by_coordinate = {
            coordinate: frozen_by_key[key] for coordinate, key in coordinates.items()
        }
        canonical_ranges = tuple(
            frozen_by_key[key] for key in sorted(frozen_by_key)
        )
        return _SourceCatalog(
            archive=archive,
            by_coordinate=by_coordinate,
            canonical_ranges=canonical_ranges,
            bank_coordinates={
                name: tuple(sorted(set(values)))
                for name, values in bank_coordinate_lists.items()
            },
        )
    except AusbExactSlotError:
        raise
    except (
        OSError,
        apf_audio.AudioError,
        apf_inner.FormatError,
        apf_outer.FormatError,
        IndexError,
        KeyError,
        TypeError,
        ValueError,
        UnicodeError,
    ) as exc:
        raise AusbExactSlotError(f"Could not discover APF AUSB source: {exc}") from exc


def _normalize_coordinates(
    coordinates: Iterable[tuple[int, int, int]],
) -> tuple[tuple[int, int, int], ...]:
    try:
        supplied = tuple(coordinates)
    except TypeError as exc:
        raise AusbExactSlotError("AUSB target coordinates must be iterable") from exc
    if len(supplied) > EXPECTED_OWNER_ROW_COUNT:
        raise AusbExactSlotError(
            f"At most {EXPECTED_OWNER_ROW_COUNT} AUSB rows may be resolved"
        )
    result = []
    seen = set()
    for coordinate in supplied:
        if not isinstance(coordinate, tuple) or len(coordinate) != 3:
            raise AusbExactSlotError(
                "Each AUSB target must be an (outer, inner, substream) tuple"
            )
        asset_id(*coordinate)
        if coordinate in seen:
            raise AusbExactSlotError(f"AUSB target selected twice: {coordinate}")
        seen.add(coordinate)
        result.append(coordinate)
    return tuple(sorted(result))


def _source_target(blueprint: _RangeBlueprint) -> ExactSlotTarget:
    owner = blueprint.owners[0]
    return ExactSlotTarget(
        channels=owner.channels,
        sample_rate=owner.sample_rate,
        encoded_size=blueprint.length,
        declared_sample_count=owner.declared_sample_count,
    )


def _audo_target(target: ExactSlotTarget) -> apf_audo_exact_slot.ExactSlotTarget:
    if not isinstance(target, ExactSlotTarget):
        raise AusbExactSlotError("AUSB target shape has the wrong type")
    return apf_audo_exact_slot.ExactSlotTarget(
        channels=target.channels,
        sample_rate=target.sample_rate,
        encoded_size=target.encoded_size,
        declared_sample_count=target.declared_sample_count,
        loop_start_bit=0,
        loop_end_bit=0,
        loop_subframe=0,
    )


def _validate_source_payload(payload: bytes, target: ExactSlotTarget) -> bytes:
    try:
        return apf_audo_exact_slot.validate_stored_payload(
            payload, _audo_target(target)
        )
    except apf_audo_exact_slot.ExactSlotImportError as exc:
        raise AusbExactSlotError(f"Source AUSB packets are invalid: {exc}") from exc


def _resolve_with_catalog(
    catalog: _SourceCatalog,
    coordinates: tuple[tuple[int, int, int], ...],
) -> Mapping[tuple[int, int, int], ResolvedExactSlot]:
    if not coordinates:
        return {}
    selected: dict[tuple[int, int, int], _RangeBlueprint] = {}
    for coordinate in coordinates:
        blueprint = catalog.by_coordinate.get(coordinate)
        if blueprint is None:
            raise AusbExactSlotError(f"Source has no AUSB row {coordinate}")
        selected[coordinate] = blueprint
    payload_hashes: dict[str, str] = {}
    with apf_inner.ArchiveReader(catalog.archive) as reader:
        for blueprint in sorted(
            set(selected.values()),
            key=lambda value: (
                value.external.table_index,
                value.offset,
                value.length,
            ),
        ):
            payload = reader.read(
                blueprint.external, blueprint.offset, blueprint.length
            )
            _validate_source_payload(payload, _source_target(blueprint))
            payload_hashes[blueprint.canonical_physical_id] = _sha256(payload)
    result = {}
    for coordinate, blueprint in selected.items():
        requested = next(
            owner for owner in blueprint.owners if owner.coordinates == coordinate
        )
        result[coordinate] = ResolvedExactSlot(
            asset_id=requested.asset_id,
            requested_owner=requested,
            owners=blueprint.owners,
            canonical_physical_id=blueprint.canonical_physical_id,
            external_outer_index=blueprint.external.table_index,
            external_range_offset=blueprint.offset,
            target=_source_target(blueprint),
            physical_spans=blueprint.physical_spans,
            source_payload_sha256=payload_hashes[blueprint.canonical_physical_id],
        )
    return result


def resolve_targets(
    index_0a: Path,
    coordinates: Iterable[tuple[int, int, int]],
) -> Mapping[tuple[int, int, int], ResolvedExactSlot]:
    """Resolve a coordinate batch and disclose every exact physical alias."""

    normalized = _normalize_coordinates(coordinates)
    if not normalized:
        return {}
    return _resolve_with_catalog(_discover_source(index_0a), normalized)


def resolve_target(
    index_0a: Path,
    outer_index: int,
    inner_index: int,
    substream_index: int,
) -> ResolvedExactSlot:
    """Resolve one semantic AUSB row to its canonical multi-pack allocation."""

    coordinate = (outer_index, inner_index, substream_index)
    return resolve_targets(index_0a, (coordinate,))[coordinate]


def resolve_jukebox_pair(
    index_0a: Path, track_index: int
) -> tuple[ResolvedExactSlot, ResolvedExactSlot]:
    """Resolve the 48 kHz stereo and 22.05 kHz mono sides of one soundtrack track."""

    if type(track_index) is not int or not 0 <= track_index < 15:
        raise AusbExactSlotError("Jukebox track index must be 0 through 14")
    catalog = _discover_source(index_0a)
    try:
        stereo_pairs = catalog.bank_coordinates[JUKEBOX_STEREO_NAME]
        mono_pairs = catalog.bank_coordinates[JUKEBOX_MONO_NAME]
    except KeyError as exc:
        raise AusbExactSlotError("Source no longer has both paired jukebox banks") from exc
    if len(stereo_pairs) != 1 or len(mono_pairs) != 1:
        raise AusbExactSlotError("Source has ambiguous paired jukebox descriptors")
    stereo_pair = stereo_pairs[0]
    mono_pair = mono_pairs[0]
    coordinates = (
        (stereo_pair[0], stereo_pair[1], track_index),
        (mono_pair[0], mono_pair[1], track_index),
    )
    resolved = _resolve_with_catalog(catalog, tuple(sorted(coordinates)))
    stereo = resolved[coordinates[0]]
    mono = resolved[coordinates[1]]
    if (
        stereo.target.channels != 2
        or stereo.target.sample_rate != 48_000
        or mono.target.channels != 1
        or mono.target.sample_rate != 22_050
        or abs(
            stereo.requested_owner.duration_seconds
            - mono.requested_owner.duration_seconds
        )
        > PAIR_DURATION_TOLERANCE_SECONDS
    ):
        raise AusbExactSlotError("Jukebox stereo/mono pairing shape changed")
    return stereo, mono


def _scan_original_audio_fingerprints(
    index_0a: Path,
    *,
    include_packets: bool,
) -> tuple[frozenset[str], frozenset[bytes], int, int]:
    """Hash every canonical AUSB range in one bounded external-bank pass."""

    catalog = _discover_source(index_0a)
    payload_hashes: set[str] = set()
    packet_hashes: set[bytes] = set()
    occurrence_count = 0
    packet_occurrence_count = 0
    with apf_inner.ArchiveReader(catalog.archive) as reader:
        for blueprint in catalog.canonical_ranges:
            payload = reader.read(
                blueprint.external, blueprint.offset, blueprint.length
            )
            _validate_source_payload(payload, _source_target(blueprint))
            payload_hashes.add(_sha256(payload))
            if include_packets:
                for fingerprint in apf_audo_exact_slot._packet_sha256s(payload):
                    packet_hashes.add(fingerprint)
                    packet_occurrence_count += 1
            occurrence_count += 1
    if occurrence_count != EXPECTED_CANONICAL_RANGE_COUNT:
        raise AusbExactSlotError("Canonical AUSB source range count changed")
    if len(payload_hashes) != EXPECTED_UNIQUE_SOURCE_PAYLOAD_HASH_COUNT:
        raise AusbExactSlotError(
            f"Source has {len(payload_hashes)} unique AUSB payload hashes, expected "
            f"{EXPECTED_UNIQUE_SOURCE_PAYLOAD_HASH_COUNT}"
        )
    return (
        frozenset(payload_hashes),
        frozenset(packet_hashes),
        occurrence_count,
        packet_occurrence_count,
    )


def original_audio_fingerprints(
    index_0a: Path,
) -> apf_audo_exact_slot.SourceAudioFingerprints:
    """Fingerprint all canonical AUSB payloads and complete 0x800-byte packets."""

    payloads, packets, occurrence_count, packet_occurrence_count = (
        _scan_original_audio_fingerprints(index_0a, include_packets=True)
    )
    inventory = apf_audo_exact_slot.SourceAudioFingerprints(
        domain=SOURCE_AUDIO_DOMAIN,
        payload_sha256s=payloads,
        packet_sha256s=packets,
        payload_occurrence_count=occurrence_count,
        packet_occurrence_count=packet_occurrence_count,
    )
    try:
        return apf_audo_exact_slot._validated_source_audio_fingerprints(
            inventory,
            expected_domain=SOURCE_AUDIO_DOMAIN,
            expected_payload_occurrences=EXPECTED_CANONICAL_RANGE_COUNT,
            expected_unique_payloads=EXPECTED_UNIQUE_SOURCE_PAYLOAD_HASH_COUNT,
        )
    except apf_audo_exact_slot.ExactSlotImportError as exc:
        raise AusbExactSlotError(
            f"AUSB source packet fingerprint inventory is invalid: {exc}"
        ) from exc


def original_payload_hashes(index_0a: Path) -> frozenset[str]:
    """Hash every canonical source AUSB range without retaining packet hashes."""

    payloads, _packets, _occurrences, _packet_occurrences = (
        _scan_original_audio_fingerprints(index_0a, include_packets=False)
    )
    return payloads


def reject_source_audio_reuse(
    payload: bytes,
    fingerprints: apf_audo_exact_slot.SourceAudioFingerprints,
) -> None:
    """Reject any complete AUSB payload or packet reused from the source game."""

    try:
        apf_audo_exact_slot._reject_source_audio_reuse(
            payload,
            fingerprints,
            expected_domain=SOURCE_AUDIO_DOMAIN,
            expected_payload_occurrences=EXPECTED_CANONICAL_RANGE_COUNT,
            expected_unique_payloads=EXPECTED_UNIQUE_SOURCE_PAYLOAD_HASH_COUNT,
        )
    except apf_audo_exact_slot.ExactSlotImportError as exc:
        raise AusbExactSlotError(str(exc)) from exc


def _validate_hash_gate(source_hashes: Collection[str]) -> frozenset[str]:
    try:
        normalized = frozenset(source_hashes)
    except TypeError as exc:
        raise AusbExactSlotError("AUSB source payload hashes must be a collection") from exc
    if len(normalized) != EXPECTED_UNIQUE_SOURCE_PAYLOAD_HASH_COUNT:
        raise AusbExactSlotError(
            "AUSB retail-byte gate requires the complete source payload hash set"
        )
    if any(
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
        for value in normalized
    ):
        raise AusbExactSlotError("AUSB source payload hashes are malformed")
    return normalized


def _target_receipt(
    target: ResolvedExactSlot,
    payload: bytes,
    nested_receipt: Mapping[str, object],
    *,
    input_kind: str,
) -> Mapping[str, object]:
    validation = nested_receipt.get("validation")
    if not isinstance(validation, Mapping):
        raise AusbExactSlotError("Nested XMA1 validation receipt is malformed")
    return {
        "schema": SCHEMA,
        "status": "accepted",
        "contract": "ausb_preencoded_xma1_exact_slot",
        "modification_kind": MODIFICATION_KIND,
        "asset_id": target.asset_id,
        "canonical_physical_id": target.canonical_physical_id,
        "shared_effect": target.shared_effect,
        "owner_asset_ids": [owner.asset_id for owner in target.owners],
        "target": {
            "channels": target.target.channels,
            "sample_rate": target.target.sample_rate,
            "encoded_size": target.target.encoded_size,
            "declared_sample_count": target.target.declared_sample_count,
            "physical_span_count": len(target.physical_spans),
        },
        "replacement": {
            "payload_size": len(payload),
            "payload_sha256": _sha256(payload),
            "packet_count": len(payload) // XMA_PACKET_SIZE,
        },
        "descriptor_policy": {
            "descriptor_bytes_changed": False,
            "boundary_table_changed": False,
            "explicit_substream_loop_fields_present": False,
            "ephemeral_validation_loop_values": [0, 0, 0],
        },
        "validation": {
            "input_kind": input_kind,
            **dict(validation),
        },
        "retail_data": {
            "contains_original_payload": False,
            "contains_preimage": False,
            "contains_source_path": False,
            "contains_descriptor_bytes": False,
        },
    }


def validate_exact_slot_import(
    data: bytes,
    target: ResolvedExactSlot,
    source_fingerprints: apf_audo_exact_slot.SourceAudioFingerprints,
    *,
    ffmpeg_path: str | Path | None = None,
    timeout_seconds: int = DEFAULT_DECODE_TIMEOUT_SECONDS,
) -> ExactSlotImportResult:
    """Authorize one pre-encoded RIFF XMA1 exact-slot replacement."""

    if not isinstance(target, ResolvedExactSlot):
        raise AusbExactSlotError("AUSB target has the wrong type")
    try:
        nested = apf_audo_exact_slot.validate_exact_slot_import(
            data,
            _audo_target(target.target),
            source_fingerprints,
            _expected_source_domain=SOURCE_AUDIO_DOMAIN,
            _expected_payload_occurrences=EXPECTED_CANONICAL_RANGE_COUNT,
            _expected_unique_payloads=EXPECTED_UNIQUE_SOURCE_PAYLOAD_HASH_COUNT,
            ffmpeg_path=ffmpeg_path,
            timeout_seconds=timeout_seconds,
        )
    except apf_audo_exact_slot.ExactSlotImportError as exc:
        raise AusbExactSlotError(f"AUSB replacement is invalid: {exc}") from exc
    # Keep this wrapper safe even if the nested decoder validator is replaced:
    # the final authorization boundary always repeats the AUSB-domain gate.
    reject_source_audio_reuse(nested.payload, source_fingerprints)
    return ExactSlotImportResult(
        payload=nested.payload,
        receipt=_target_receipt(
            target,
            nested.payload,
            nested.receipt,
            input_kind="riff_xma1",
        ),
    )


def validate_stored_payload(
    payload: bytes,
    target: ResolvedExactSlot,
    source_payload_hashes: Collection[str],
) -> bytes:
    """Run the inexpensive build-time target, packet, and retail-byte gates."""

    if not isinstance(target, ResolvedExactSlot):
        raise AusbExactSlotError("AUSB target has the wrong type")
    forbidden = _validate_hash_gate(source_payload_hashes)
    try:
        checked = apf_audo_exact_slot.validate_stored_payload(
            payload, _audo_target(target.target)
        )
    except apf_audo_exact_slot.ExactSlotImportError as exc:
        raise AusbExactSlotError(f"Stored AUSB replacement is invalid: {exc}") from exc
    if _sha256(checked) in forbidden:
        raise AusbExactSlotError("Stored replacement matches retail AUSB audio")
    return checked


def validate_stored_payload_complete(
    payload: bytes,
    target: ResolvedExactSlot,
    source_fingerprints: apf_audo_exact_slot.SourceAudioFingerprints,
    *,
    ffmpeg_path: str | Path | None = None,
    timeout_seconds: int = DEFAULT_DECODE_TIMEOUT_SECONDS,
) -> ExactSlotImportResult:
    """Completely reauthorize one raw project payload after project load."""

    if not isinstance(target, ResolvedExactSlot):
        raise AusbExactSlotError("AUSB target has the wrong type")
    try:
        nested = apf_audo_exact_slot.validate_stored_payload_complete(
            payload,
            _audo_target(target.target),
            source_fingerprints,
            _expected_source_domain=SOURCE_AUDIO_DOMAIN,
            _expected_payload_occurrences=EXPECTED_CANONICAL_RANGE_COUNT,
            _expected_unique_payloads=EXPECTED_UNIQUE_SOURCE_PAYLOAD_HASH_COUNT,
            ffmpeg_path=ffmpeg_path,
            timeout_seconds=timeout_seconds,
        )
    except apf_audo_exact_slot.ExactSlotImportError as exc:
        raise AusbExactSlotError(f"Stored AUSB replacement is invalid: {exc}") from exc
    reject_source_audio_reuse(nested.payload, source_fingerprints)
    return ExactSlotImportResult(
        payload=nested.payload,
        receipt=_target_receipt(
            target,
            nested.payload,
            nested.receipt,
            input_kind="raw_xma1_packets",
        ),
    )


def decode_stored_payload_to_wav(
    payload: bytes,
    target: ResolvedExactSlot,
    source_fingerprints: apf_audo_exact_slot.SourceAudioFingerprints,
    destination: Path,
    *,
    ffmpeg_path: str | Path | None = None,
    timeout_seconds: int = DEFAULT_DECODE_TIMEOUT_SECONDS,
    cancel_requested: apf_audio.CancelRequested | None = None,
) -> Mapping[str, object]:
    """Decode a staged user payload to a new verified PCM WAV atomically."""

    apf_audio.check_cancel_requested(cancel_requested)
    reject_source_audio_reuse(payload, source_fingerprints)
    checked = validate_stored_payload(
        payload,
        target,
        source_fingerprints.payload_sha256s,
    )
    apf_audio.check_cancel_requested(cancel_requested)
    try:
        nested = apf_audo_exact_slot.decode_stored_payload_to_wav(
            checked,
            _audo_target(target.target),
            destination,
            ffmpeg_path=ffmpeg_path,
            timeout_seconds=timeout_seconds,
            cancel_requested=cancel_requested,
        )
    except apf_audo_exact_slot.ExactSlotImportError as exc:
        raise AusbExactSlotError(f"Could not decode AUSB replacement: {exc}") from exc
    return {
        "schema": WAV_EXPORT_SCHEMA,
        "status": nested["status"],
        "asset_id": target.asset_id,
        "canonical_physical_id": target.canonical_physical_id,
        "shared_effect": target.shared_effect,
        "payload_sha256": nested["payload_sha256"],
        "wav_sha256": nested["wav_sha256"],
        "channels": nested["channels"],
        "sample_rate": nested["sample_rate"],
        "bits_per_sample": nested["bits_per_sample"],
        "decoded_sample_count_per_channel": nested[
            "decoded_sample_count_per_channel"
        ],
        "target_minus_decoded_samples": nested["target_minus_decoded_samples"],
        "ffmpeg_xerror": True,
        "atomic_no_replace": True,
        "contains_original_payload": False,
        "contains_source_path": False,
    }


def compile_physical_writes(
    payload: bytes,
    target: ResolvedExactSlot,
    source_payload_hashes: Collection[str],
) -> tuple[CompiledAusbWrite, ...]:
    """Split user packets into exact pack-local writes without opening packs."""

    checked = validate_stored_payload(payload, target, source_payload_hashes)
    writes = []
    for span in target.physical_spans:
        end = span.payload_offset + span.length
        if end > len(checked):
            raise AusbExactSlotError("AUSB physical span leaves replacement payload")
        writes.append(
            CompiledAusbWrite(
                pack_name=span.pack_name,
                pack_offset=span.pack_offset,
                payload=checked[span.payload_offset:end],
                canonical_physical_id=target.canonical_physical_id,
                side_payload_offset=span.payload_offset,
            )
        )
    if sum(write.length for write in writes) != target.target.encoded_size:
        raise AusbExactSlotError("Compiled AUSB writes do not cover the exact slot")
    return tuple(writes)


def merge_compiled_writes(
    groups: Iterable[Iterable[CompiledAusbWrite]],
) -> tuple[CompiledAusbWrite, ...]:
    """Dedupe identical aliases and reject all divergent physical overlaps."""

    flattened = []
    for group in groups:
        for write in group:
            if not isinstance(write, CompiledAusbWrite) or write.length <= 0:
                raise AusbExactSlotError("Compiled AUSB write has the wrong shape")
            flattened.append(write)
    flattened.sort(key=lambda value: (value.pack_name, value.pack_offset, value.length))
    merged: list[CompiledAusbWrite] = []
    for write in flattened:
        if merged and write.pack_name == merged[-1].pack_name:
            prior = merged[-1]
            prior_end = prior.pack_offset + prior.length
            if write.pack_offset < prior_end:
                if (
                    write.pack_offset == prior.pack_offset
                    and write.length == prior.length
                    and write.payload == prior.payload
                    and write.canonical_physical_id == prior.canonical_physical_id
                ):
                    continue
                raise AusbExactSlotError(
                    "Divergent AUSB edits overlap the same physical pack bytes"
                )
        merged.append(write)
    return tuple(merged)


def validate_paired_soundtrack_import(
    stereo_riff: bytes,
    mono_riff: bytes,
    stereo_target: ResolvedExactSlot,
    mono_target: ResolvedExactSlot,
    source_fingerprints: apf_audo_exact_slot.SourceAudioFingerprints,
    *,
    ffmpeg_path: str | Path | None = None,
    timeout_seconds: int = DEFAULT_DECODE_TIMEOUT_SECONDS,
) -> PairedSoundtrackImportResult:
    """Atomically validate both encodings of one paired jukebox track."""

    if (
        stereo_target.bank_name.casefold() != JUKEBOX_STEREO_NAME
        or mono_target.bank_name.casefold() != JUKEBOX_MONO_NAME
        or stereo_target.substream_index != mono_target.substream_index
        or stereo_target.target.channels != 2
        or stereo_target.target.sample_rate != 48_000
        or mono_target.target.channels != 1
        or mono_target.target.sample_rate != 22_050
        or abs(
            stereo_target.requested_owner.duration_seconds
            - mono_target.requested_owner.duration_seconds
        )
        > PAIR_DURATION_TOLERANCE_SECONDS
    ):
        raise AusbExactSlotError("Selected targets are not one paired jukebox track")
    # No pair object is returned until both strict decoder passes succeed.
    stereo = validate_exact_slot_import(
        stereo_riff,
        stereo_target,
        source_fingerprints,
        ffmpeg_path=ffmpeg_path,
        timeout_seconds=timeout_seconds,
    )
    mono = validate_exact_slot_import(
        mono_riff,
        mono_target,
        source_fingerprints,
        ffmpeg_path=ffmpeg_path,
        timeout_seconds=timeout_seconds,
    )
    receipt = {
        "schema": f"{SCHEMA}/paired-jukebox",
        "status": "accepted",
        "contract": "paired_jukebox_preencoded_xma1_exact_slots",
        "track_index": stereo_target.substream_index,
        "track_number": stereo_target.substream_index + 1,
        "stereo": stereo.receipt,
        "mono": mono.receipt,
        "retail_data": {
            "contains_original_payload": False,
            "contains_preimage": False,
            "contains_source_path": False,
            "contains_descriptor_bytes": False,
        },
    }
    return PairedSoundtrackImportResult(stereo=stereo, mono=mono, receipt=receipt)


def encode_receipt(receipt: Mapping[str, object]) -> bytes:
    """Encode one canonical retail-free exact-slot receipt."""

    if not isinstance(receipt, Mapping) or receipt.get("schema") != SCHEMA:
        raise AusbExactSlotError("AUSB receipt has the wrong schema")
    return _encode_json(receipt)


def encode_paired_receipt(receipt: Mapping[str, object]) -> bytes:
    """Encode one paired-jukebox retail-free receipt."""

    if (
        not isinstance(receipt, Mapping)
        or receipt.get("schema") != f"{SCHEMA}/paired-jukebox"
    ):
        raise AusbExactSlotError("Paired AUSB receipt has the wrong schema")
    return _encode_json(receipt)


def _encode_json(receipt: Mapping[str, object]) -> bytes:
    try:
        encoded = json.dumps(
            receipt,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise AusbExactSlotError(f"AUSB receipt is not canonical JSON: {exc}") from exc
    return (encoded + "\n").encode("ascii")


__all__ = [
    "ASSET_ID_PREFIX",
    "AusbExactSlotError",
    "AusbOwner",
    "CompiledAusbWrite",
    "ExactSlotImportResult",
    "ExactSlotTarget",
    "MODIFICATION_KIND",
    "PairedSoundtrackImportResult",
    "PhysicalSpan",
    "ResolvedExactSlot",
    "SCHEMA",
    "WAV_EXPORT_SCHEMA",
    "asset_id",
    "compile_physical_writes",
    "decode_stored_payload_to_wav",
    "encode_receipt",
    "merge_compiled_writes",
    "original_audio_fingerprints",
    "original_payload_hashes",
    "reject_source_audio_reuse",
    "resolve_jukebox_pair",
    "resolve_target",
    "resolve_targets",
    "validate_exact_slot_import",
    "validate_paired_soundtrack_import",
    "validate_stored_payload",
    "validate_stored_payload_complete",
]

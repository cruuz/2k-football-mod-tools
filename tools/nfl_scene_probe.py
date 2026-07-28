#!/usr/bin/env python3
"""Bounded semantic probe for NFL 2K5 scene, shape, skeleton, and audio chunks.

The outer archive and shared Visual Concepts resource wrapper are parsed by
``nfl_outer`` and ``nfl_txtr``.  This tool adds conservative inner probes for
SCNE, SHAP, TSET, SKEL, and AUDO without pretending that unknown mesh or
animation fields have been recovered.

It can also validate explicitly supplied fixed-slot arrays.  The two arrays
used by this probe are outer entry 3108 (624 0x200-byte SHAP slots) and outer
entry 4291 (236 0x18500-byte SCNE slots).  The canonical v2 resource inventory
generalizes zero-padding traversal across the whole corpus; explicit slot
sizes remain useful as independent checks and are arguments rather than
guesses.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
import sys
import wave
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

# The shipped Windows runtime is an embeddable CPython whose ._pth file
# defines sys.path outright and, unlike a normal interpreter, does NOT add
# this script's own directory -- so the sibling imports below fail there
# with ModuleNotFoundError unless the directory is put back explicitly.
import sys as _sys
from pathlib import Path as _Path
_here = str(_Path(__file__).resolve().parent)
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from nfl_outer import Archive, Entry, FormatError, parse_archive
from nfl_txtr import (
    COMPRESSED_SENTINEL,
    HEADER,
    XBOX_FORMAT_NAMES,
    Chunk,
    TxtrError,
    decode_chunk,
)


SUPPORTED_KINDS = ("SCNE", "SHAP", "TSET", "SKEL", "AUDO")
MAX_UTF16_STRINGS = 96
XBOX_IMA_CHANNEL_BYTES = 36
XBOX_IMA_SAMPLES_PER_BLOCK = 64
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


class ProbeError(ValueError):
    """Raised when a bounded semantic assertion fails."""


@dataclass(frozen=True)
class ResourceRecord:
    outer_index: int
    outer_id: str
    outer_size: int
    chunk_index: int
    chunk_offset: int
    kind: str
    stored_size: int
    word_08: int
    word_0c: int
    word_10: int
    word_14: int
    source: str = "inventory"
    slot_size: int | None = None

    @property
    def end_offset(self) -> int:
        return self.chunk_offset + HEADER.size + self.stored_size

    @property
    def compressed(self) -> bool:
        return self.word_10 == COMPRESSED_SENTINEL

    @property
    def output_size(self) -> int:
        return self.word_08 + self.word_0c

    def as_chunk(self) -> Chunk:
        return Chunk(
            index=self.chunk_index,
            offset=0,
            kind=self.kind,
            stored_size=self.stored_size,
            system_bytes=self.word_08,
            video_bytes=self.word_0c,
            compression_magic=self.word_10,
            overlap_scratch_bytes=self.word_14,
            reserved0=0,
            reserved1=0,
        )


def parse_int(value: str) -> int:
    return int(value, 0)


def s32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def f32(data: bytes, offset: int) -> float:
    return struct.unpack_from("<f", data, offset)[0]


def entry_by_index(archive: Archive, index: int) -> Entry:
    if not 0 <= index < len(archive.entries):
        raise ProbeError(f"outer index {index} is out of range")
    return archive.entries[index]


def read_entry_range(archive: Archive, entry: Entry, offset: int, size: int) -> bytes:
    """Read a bounded relative range from an entry, including split volumes."""
    if offset < 0 or size < 0 or offset + size > entry.size:
        raise ProbeError(
            f"outer {entry.table_index}: range 0x{offset:x}+0x{size:x} "
            f"exceeds 0x{entry.size:x} bytes"
        )
    wanted_start = offset
    wanted_end = offset + size
    relative = 0
    result = bytearray()
    for segment in entry.segments:
        segment_start = relative
        segment_end = relative + segment.size
        overlap_start = max(wanted_start, segment_start)
        overlap_end = min(wanted_end, segment_end)
        if overlap_start < overlap_end:
            pack = archive.packs[segment.pack_ordinal]
            within = overlap_start - segment_start
            with pack.path.open("rb") as stream:
                stream.seek(segment.pack_offset + within)
                part = stream.read(overlap_end - overlap_start)
            if len(part) != overlap_end - overlap_start:
                raise ProbeError(
                    f"outer {entry.table_index}: short read in pack {pack.name}"
                )
            result.extend(part)
        relative = segment_end
        if relative >= wanted_end:
            break
    if len(result) != size:
        raise ProbeError(
            f"outer {entry.table_index}: read 0x{len(result):x}, expected 0x{size:x}"
        )
    return bytes(result)


def parse_inventory(path: Path) -> tuple[dict[str, object], list[ResourceRecord]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema") != "nfl2k5_resource_chunk_inventory/v1":
        raise ProbeError(f"unsupported inventory schema in {path}")
    records: list[ResourceRecord] = []
    for item in raw.get("chunks", []):
        magic = item["word_10"]
        if isinstance(magic, str):
            magic = int(magic, 0)
        records.append(
            ResourceRecord(
                outer_index=int(item["outer_index"]),
                outer_id=str(item["outer_id"]),
                outer_size=int(item["outer_size"]),
                chunk_index=int(item["chunk_index"]),
                chunk_offset=int(item["chunk_offset"]),
                kind=str(item["kind"]),
                stored_size=int(item["stored_size"]),
                word_08=int(item["word_08"]),
                word_0c=int(item["word_0c"]),
                word_10=int(magic),
                word_14=int(item["word_14"]),
            )
        )
    return raw, records


def record_from_header(
    archive: Archive,
    outer_index: int,
    chunk_index: int,
    chunk_offset: int,
    source: str,
    slot_size: int | None = None,
) -> ResourceRecord:
    entry = entry_by_index(archive, outer_index)
    header = read_entry_range(archive, entry, chunk_offset, HEADER.size)
    kind, stored, word08, word0c, word10, word14, reserved0, reserved1 = HEADER.unpack(header)
    if reserved0 != 0 or reserved1 != 0:
        raise ProbeError(
            f"outer {outer_index} offset 0x{chunk_offset:x}: reserved wrapper words are nonzero"
        )
    try:
        text_kind = kind.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ProbeError(
            f"outer {outer_index} offset 0x{chunk_offset:x}: non-ASCII FourCC"
        ) from exc
    return ResourceRecord(
        outer_index=outer_index,
        outer_id=f"0x{entry.name_id:08x}",
        outer_size=entry.size,
        chunk_index=chunk_index,
        chunk_offset=chunk_offset,
        kind=text_kind,
        stored_size=stored,
        word_08=word08,
        word_0c=word0c,
        word_10=word10,
        word_14=word14,
        source=source,
        slot_size=slot_size,
    )


def validate_padded_array(
    archive: Archive, outer_index: int, slot_size: int, kind: str
) -> tuple[list[ResourceRecord], dict[str, object]]:
    entry = entry_by_index(archive, outer_index)
    if slot_size <= HEADER.size or entry.size % slot_size:
        raise ProbeError(
            f"outer {outer_index}: size 0x{entry.size:x} is not a multiple of slot 0x{slot_size:x}"
        )
    records: list[ResourceRecord] = []
    nonzero_padding: list[int] = []
    for slot_index, offset in enumerate(range(0, entry.size, slot_size)):
        record = record_from_header(
            archive, outer_index, slot_index, offset, "fixed_slot", slot_size
        )
        if record.kind != kind:
            raise ProbeError(
                f"outer {outer_index} slot {slot_index}: {record.kind}, expected {kind}"
            )
        if record.end_offset > offset + slot_size:
            raise ProbeError(
                f"outer {outer_index} slot {slot_index}: resource end 0x{record.end_offset:x} "
                f"exceeds slot end 0x{offset + slot_size:x}"
            )
        inner = read_entry_range(archive, entry, offset + HEADER.size + 0x0C, 4)
        if inner != kind.encode("ascii"):
            raise ProbeError(
                f"outer {outer_index} slot {slot_index}: inner marker {inner!r} at +0x2c"
            )
        padding_size = offset + slot_size - record.end_offset
        if padding_size:
            padding = read_entry_range(archive, entry, record.end_offset, padding_size)
            if any(padding):
                nonzero_padding.append(slot_index)
        records.append(record)
    if nonzero_padding:
        raise ProbeError(
            f"outer {outer_index}: nonzero padding in slots {nonzero_padding[:16]}"
        )
    return records, {
        "outer_index": outer_index,
        "outer_id": f"0x{entry.name_id:08x}",
        "kind": kind,
        "slot_size": slot_size,
        "slot_count": len(records),
        "all_wrappers_valid": True,
        "all_inner_markers_match": True,
        "all_padding_zero": True,
    }


def utf16z(data: bytes, offset: int, limit: int | None = None) -> tuple[str, int]:
    if offset < 0 or offset + 2 > len(data) or offset % 2:
        raise ProbeError(f"invalid UTF-16LE offset 0x{offset:x}")
    end_limit = min(len(data), limit if limit is not None else len(data))
    cursor = offset
    while cursor + 1 < end_limit and data[cursor : cursor + 2] != b"\0\0":
        cursor += 2
    if cursor + 1 >= end_limit:
        raise ProbeError(f"unterminated UTF-16LE string at 0x{offset:x}")
    try:
        value = data[offset:cursor].decode("utf-16le")
    except UnicodeDecodeError as exc:
        raise ProbeError(f"invalid UTF-16LE string at 0x{offset:x}") from exc
    return value, cursor + 2


def named_inner(data: bytes, expected: str) -> tuple[str, int, int]:
    if len(data) < 0x22:
        raise ProbeError(f"{expected}: decoded body shorter than 0x22 bytes")
    inner = data[0x0C:0x10]
    if inner != expected.encode("ascii"):
        raise ProbeError(f"{expected}: inner marker at +0x0c is {inner!r}")
    relative = s32(data, 0x10)
    name_offset = 0x0F + relative
    name, name_end = utf16z(data, name_offset)
    return name, name_offset, name_end


def credible_text(value: str) -> bool:
    if len(value) < 3 or len(value) > 160:
        return False
    if not any(character.isalpha() for character in value):
        return False
    return all(
        character.isalnum() or character in " _.-:/\\[]()#'"
        for character in value
    )


def scan_utf16_strings(data: bytes, limit: int) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    seen_ranges: list[tuple[int, int]] = []
    limit = min(limit, len(data))
    offset = 0
    while offset + 6 <= limit:
        if any(start <= offset < end for start, end in seen_ranges):
            offset += 2
            continue
        cursor = offset
        chars: list[str] = []
        while cursor + 1 < limit:
            code = struct.unpack_from("<H", data, cursor)[0]
            if code == 0:
                break
            if not (0x20 <= code <= 0x7E):
                chars = []
                break
            chars.append(chr(code))
            if len(chars) > 160:
                chars = []
                break
            cursor += 2
        if chars and cursor + 1 < limit and data[cursor : cursor + 2] == b"\0\0":
            value = "".join(chars)
            if credible_text(value):
                result.append({"offset": offset, "value": value})
                seen_ranges.append((offset, cursor + 2))
                if len(result) >= MAX_UTF16_STRINGS:
                    break
                offset = cursor + 2
                continue
        offset += 2
    return result


def decode_resource(span: bytes, record: ResourceRecord) -> tuple[bytes, dict[str, object]]:
    if len(span) != HEADER.size + record.stored_size:
        raise ProbeError(
            f"{record.kind}: full span is 0x{len(span):x}; expected 0x{HEADER.size + record.stored_size:x}"
        )
    fields = HEADER.unpack_from(span)
    if fields[0].decode("ascii") != record.kind or fields[1] != record.stored_size:
        raise ProbeError(f"{record.kind}: inventory/header disagreement")
    output, info = decode_chunk(span, record.as_chunk())
    detail: dict[str, object] = {
        "decoded_size": len(output),
        "decoded_sha256": hashlib.sha256(output).hexdigest(),
    }
    if info is not None:
        detail["lz"] = asdict(info)
        detail["unused_stored_bytes"] = record.stored_size - info.consumed_bytes
    return output, detail


def probe_scne(data: bytes, record: ResourceRecord) -> dict[str, object]:
    name, name_offset, _ = named_inner(data, "SCNE")
    system_size = record.word_08 if record.word_08 else len(data)
    system_size = min(system_size, len(data))
    strings = scan_utf16_strings(data, system_size)
    markers = {
        marker.decode("ascii"): data.find(marker, 0, system_size)
        for marker in (b"ANIMATION {", b"KEYFRAME {", b"BINDING =", b"TANGENTS {")
        if data.find(marker, 0, system_size) >= 0
    }
    return {
        "role": "scene/geometry resource",
        "name": name,
        "name_offset": name_offset,
        "system_bytes": record.word_08,
        "video_bytes": record.word_0c,
        "utf16_strings": strings,
        "ascii_animation_markers": markers,
        "portme": [
            "PORTME: identify SCNE node/object tables and their self-relative fields.",
            "PORTME: recover vertex declarations, index buffers, skin weights, and material bindings before glTF export.",
            "PORTME: prove whether embedded Maya-style ANIMATION text is source data, debug residue, or runtime-consumed scripting.",
        ],
    }


def texture_descriptor(data: bytes, descriptor_offset: int) -> dict[str, object]:
    if descriptor_offset < 0 or descriptor_offset + 0x18 > len(data):
        raise ProbeError(f"texture descriptor 0x{descriptor_offset:x} is out of bounds")
    unknown0, pixel_offset, palette_offset, packed_format, packed_size, flags = struct.unpack_from(
        "<6I", data, descriptor_offset
    )
    format_code = (packed_format >> 8) & 0xFF
    return {
        "offset": descriptor_offset,
        "unknown0": unknown0,
        "pixel_offset": pixel_offset,
        "palette_offset": palette_offset,
        "packed_format": f"0x{packed_format:08x}",
        "packed_size": packed_size,
        "flags": f"0x{flags:08x}",
        "dimensions": (packed_format >> 4) & 0xF,
        "format_code": format_code,
        "format_name": XBOX_FORMAT_NAMES.get(format_code, f"UNKNOWN_0x{format_code:02X}"),
        "mip_levels": (packed_format >> 16) & 0xF,
        "width": 1 << ((packed_format >> 20) & 0xF),
        "height": 1 << ((packed_format >> 24) & 0xF),
        "depth": 1 << ((packed_format >> 28) & 0xF),
    }


def probe_tset(data: bytes, record: ResourceRecord) -> dict[str, object]:
    if len(data) < 0x20:
        raise ProbeError("TSET: decoded body is too short")
    version = u32(data, 0)
    count = u32(data, 4)
    if version != 0x0D:
        raise ProbeError(f"TSET: word +0x00 is 0x{version:x}, expected observed 0x0d")
    if count > 4096:
        raise ProbeError(f"TSET: implausible reference count {count}")
    refs: list[dict[str, object]] = []
    for index in range(count):
        base = 0x18 + index * 0x24
        if base + 0x18 > len(data):
            raise ProbeError(f"TSET: reference {index} exceeds decoded system data")
        if data[base : base + 4] != b"TXTR":
            raise ProbeError(f"TSET: reference {index} lacks TXTR marker at 0x{base:x}")
        # Each pointer is self-relative to its own field, biased by -1.  The
        # same convention appears in standalone TXTR/SCNE/AUDO objects.
        name_offset = base + 3 + s32(data, base + 4)
        descriptor_offset = base + 7 + s32(data, base + 8)
        root_offset = base + 0x13 + s32(data, base + 0x14)
        name, _ = utf16z(data, name_offset, record.word_08 or len(data))
        refs.append(
            {
                "index": index,
                "record_offset": base,
                "name": name,
                "name_offset": name_offset,
                "root_offset": root_offset,
                "descriptor": texture_descriptor(data, descriptor_offset),
            }
        )
    return {
        "role": "embedded texture-set aggregate",
        "version_word": version,
        "reference_count": count,
        "references": refs,
        "system_bytes": record.word_08,
        "video_bytes": record.word_0c,
        "portme": [
            "PORTME: name the remaining TSET record words and prove ownership/lifetime semantics.",
            "PORTME: map each descriptor's video-buffer offsets to the corresponding extracted PNG/glTF material slot.",
        ],
    }


def probe_shap(data: bytes, _record: ResourceRecord) -> dict[str, object]:
    name, name_offset, name_end = named_inner(data, "SHAP")
    # The second serialized relative field at +0x14 resolves to the padding
    # immediately before the first 12-byte channel record; observed bodies
    # place the first record four bytes later.  This handles names whose end
    # does not fall on an eight-byte boundary (for example
    # ``player_body_medium``) without guessing alignment.
    cursor = 0x17 + s32(data, 0x14)
    if cursor < name_end or cursor >= len(data):
        raise ProbeError(
            f"SHAP {name!r}: record offset 0x{cursor:x} from +0x14 is invalid"
        )
    record_offset = cursor
    records: list[dict[str, object]] = []
    terminated = False
    while cursor + 12 <= len(data):
        channel_id, value, flags = struct.unpack_from("<IfI", data, cursor)
        if not math.isfinite(value):
            raise ProbeError(f"SHAP {name!r}: non-finite value at 0x{cursor + 4:x}")
        records.append(
            {
                "offset": cursor,
                "channel_id": f"0x{channel_id:08x}",
                "value": value,
                "flags": flags,
            }
        )
        cursor += 12
        if flags == 3:
            terminated = True
            break
        if flags != 0:
            raise ProbeError(f"SHAP {name!r}: unrecognized flags 0x{flags:x}")
        if len(records) > 4096:
            raise ProbeError(f"SHAP {name!r}: runaway record list")
    if not terminated:
        raise ProbeError(f"SHAP {name!r}: no flags=3 terminating record")
    footer = data[cursor:]
    if len(footer) % 4 or not 0 <= len(footer) <= 0x20:
        raise ProbeError(
            f"SHAP {name!r}: unbounded footer size 0x{len(footer):x}"
        )
    footer_words = struct.unpack(f"<{len(footer) // 4}I", footer)
    return {
        "role": "named shape/morph parameter set (semantic inference from names/values)",
        "name": name,
        "name_offset": name_offset,
        "record_offset": record_offset,
        "record_count": len(records),
        "records": records,
        "footer_words": [f"0x{word:08x}" for word in footer_words],
        "footer_all_zero": not any(footer),
        "portme": [
            "PORTME: identify the channel_id algorithm/table; do not call these CRCs without proof.",
            "PORTME: name flags=3 and the final three footer words.",
            "PORTME: map shape channel values to glTF morph-target weights.",
        ],
    }


def probe_skel(data: bytes, _record: ResourceRecord) -> dict[str, object]:
    name, name_offset, _ = named_inner(data, "SKEL")
    if len(data) < 0x50:
        raise ProbeError("SKEL: decoded body is shorter than 0x50")
    count = u32(data, 0x40)
    if 0x50 + count * 0x10 != len(data):
        raise ProbeError(
            f"SKEL {name!r}: count {count} implies 0x{0x50 + count * 0x10:x} bytes, "
            f"body has 0x{len(data):x}"
        )
    vectors: list[dict[str, object]] = []
    for index in range(count):
        offset = 0x50 + index * 0x10
        values = struct.unpack_from("<4f", data, offset)
        norm3 = math.sqrt(sum(value * value for value in values[:3]))
        vectors.append(
            {
                "index": index,
                "offset": offset,
                "values": list(values),
                "xyz_norm": norm3,
            }
        )
    return {
        "role": "skeleton-associated normalized-vector table; exact semantics unknown",
        "name": name,
        "name_offset": name_offset,
        "record_count": count,
        "record_stride": 0x10,
        "records": vectors,
        "all_w_zero": all(abs(record["values"][3]) < 1e-7 for record in vectors),
        "max_xyz_norm_error": max((abs(record["xyz_norm"] - 1.0) for record in vectors), default=0.0),
        "portme": [
            "PORTME: prove whether the normalized xyz records are bone directions, bind-pose axes, or another skeleton table.",
            "PORTME: locate bone names/parents; this lone SKEL object contains no recovered hierarchy.",
        ],
    }


def parse_audo_descriptor(data: bytes, system_bytes: int) -> tuple[int, tuple[int, ...]]:
    if len(data) < 0x18:
        raise ProbeError("AUDO: decoded body is too short for descriptor pointer")
    # Like the name pointer, +0x14 is field-local and biased by -1:
    # target = field_address - 1 + signed_relative.
    descriptor_offset = 0x13 + s32(data, 0x14)
    if descriptor_offset < 0 or descriptor_offset + 0x20 > min(len(data), system_bytes):
        raise ProbeError(
            f"AUDO: descriptor pointer resolves to unavailable 0x{descriptor_offset:x}"
        )
    return descriptor_offset, struct.unpack_from("<8I", data, descriptor_offset)


def probe_audo(data: bytes, record: ResourceRecord, fully_read: bool) -> dict[str, object]:
    name, name_offset, _ = named_inner(data, "AUDO")
    descriptor_offset, words = parse_audo_descriptor(data, record.word_08)
    channels = words[1]
    codec_word = words[2]
    codec_flags = words[3]
    data_size = words[4]
    data_offset = words[5]
    per_channel_size = words[6]
    sample_rate = words[7]
    if not 1 <= channels <= 8:
        raise ProbeError(f"AUDO {name!r}: implausible channel count {channels}")
    block_align = XBOX_IMA_CHANNEL_BYTES * channels
    block_count, remainder = divmod(data_size, block_align)
    payload_offset = record.word_08 + data_offset
    first_header_valid = None
    first_predictors: list[int] = []
    first_step_indices: list[int] = []
    if payload_offset + channels * XBOX_IMA_CHANNEL_BYTES <= len(data):
        for channel in range(channels):
            # NFL 2K5 stores one complete 36-byte mono sub-block per channel.
            # Stereo channel 1 therefore starts at +0x24, not +0x04.
            predictor, step_index = struct.unpack_from(
                "<hH", data, payload_offset + channel * XBOX_IMA_CHANNEL_BYTES
            )
            first_predictors.append(predictor)
            first_step_indices.append(step_index)
        first_header_valid = all(index <= 88 for index in first_step_indices)
    tail_bytes = record.stored_size - record.word_08 - record.word_0c
    confidence = "high" if (
        codec_word == 0x11
        and words[0] == channels
        and data_size == record.word_0c
        and per_channel_size * channels == data_size
        and remainder == 0
        and first_header_valid is True
    ) else "candidate"
    result: dict[str, object] = {
        "role": "named audio sample",
        "name": name,
        "name_offset": name_offset,
        "descriptor_offset": descriptor_offset,
        "descriptor_words": [f"0x{word:08x}" for word in words],
        "channels": channels,
        "codec_word": f"0x{codec_word:08x}",
        "codec_flags": f"0x{codec_flags:08x}",
        "data_size": data_size,
        "data_offset": data_offset,
        "per_channel_data_size": per_channel_size,
        "sample_rate": sample_rate,
        "wrapper_video_bytes": record.word_0c,
        "wrapper_tail_bytes": tail_bytes,
        "xbox_ima_block_align": block_align,
        "xbox_ima_block_count": block_count,
        "block_remainder": remainder,
        "first_block_predictors": first_predictors,
        "first_block_step_indices": first_step_indices,
        "first_block_step_indices_valid": first_header_valid,
        "codec_inference": f"Xbox IMA ADPCM ({confidence} confidence)",
        "fully_read": fully_read,
        "portme": [
            "PORTME: name descriptor words +0x00 and codec_flags 0x35 from executable call sites.",
            "PORTME: identify loop points/gain/pan metadata; none is assigned from this bounded descriptor alone.",
        ],
    }
    return result


def expand_ima_nibble(predictor: int, step_index: int, nibble: int) -> tuple[int, int]:
    step = IMA_STEP_TABLE[step_index]
    diff = step >> 3
    if nibble & 1:
        diff += step >> 2
    if nibble & 2:
        diff += step >> 1
    if nibble & 4:
        diff += step
    predictor = predictor - diff if nibble & 8 else predictor + diff
    predictor = max(-32768, min(32767, predictor))
    step_index = max(0, min(88, step_index + IMA_INDEX_TABLE[nibble & 7]))
    return predictor, step_index


def decode_xbox_ima(data: bytes, channels: int) -> list[int]:
    """Decode NFL 2K5's per-channel Xbox IMA sub-block framing.

    A 36-byte/channel block contains one predictor/index header and 32 coded
    bytes.  NFL 2K5 places complete channel sub-blocks consecutively.  FFmpeg's
    Xbox IMA sample accounting reports 64 output samples per block: the
    initial predictor plus the first 63 expanded samples; the final nibble is
    decoded for state consistency but is not emitted.
    """
    block_align = XBOX_IMA_CHANNEL_BYTES * channels
    if len(data) % block_align:
        raise ProbeError(
            f"Xbox IMA payload 0x{len(data):x} is not divisible by block align {block_align}"
        )
    interleaved: list[int] = []
    for block_offset in range(0, len(data), block_align):
        channel_samples: list[list[int]] = []
        for channel in range(channels):
            channel_offset = block_offset + channel * XBOX_IMA_CHANNEL_BYTES
            predictor, index = struct.unpack_from("<hH", data, channel_offset)
            if index > 88:
                raise ProbeError(
                    f"Xbox IMA block 0x{block_offset:x} channel {channel}: step index {index}"
                )
            samples = [predictor]
            for value in data[channel_offset + 4 : channel_offset + XBOX_IMA_CHANNEL_BYTES]:
                for nibble in (value & 0x0F, value >> 4):
                    predictor, index = expand_ima_nibble(predictor, index, nibble)
                    samples.append(predictor)
            channel_samples.append(samples)
        for sample in range(XBOX_IMA_SAMPLES_PER_BLOCK):
            for channel in range(channels):
                interleaved.append(channel_samples[channel][sample])
    return interleaved


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return value or "unnamed"


def write_audo_wav(
    directory: Path,
    record: ResourceRecord,
    body: bytes,
    semantic: dict[str, object],
) -> Path:
    channels = int(semantic["channels"])
    sample_rate = int(semantic["sample_rate"])
    data_offset = record.word_08 + int(semantic["data_offset"])
    data_size = int(semantic["data_size"])
    if data_offset + data_size > len(body):
        raise ProbeError(
            f"AUDO {semantic['name']!r}: payload exceeds fully read body"
        )
    samples = decode_xbox_ima(body[data_offset : data_offset + data_size], channels)
    pcm = struct.pack(f"<{len(samples)}h", *samples)
    filename = (
        f"outer_{record.outer_index:04d}_chunk_{record.chunk_index:04d}_"
        f"{safe_name(str(semantic['name']))}.wav"
    )
    path = directory / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(pcm)
    return path


def semantic_probe(data: bytes, record: ResourceRecord, fully_read: bool) -> dict[str, object]:
    if record.kind == "SCNE":
        return probe_scne(data, record)
    if record.kind == "TSET":
        return probe_tset(data, record)
    if record.kind == "SHAP":
        return probe_shap(data, record)
    if record.kind == "SKEL":
        return probe_skel(data, record)
    if record.kind == "AUDO":
        return probe_audo(data, record, fully_read)
    raise ProbeError(f"PORTME: no semantic probe for {record.kind}")


def select_stratified(records: list[ResourceRecord], count: int) -> list[ResourceRecord]:
    ordered = sorted(records, key=lambda item: (item.stored_size, item.outer_index, item.chunk_index))
    if count >= len(ordered):
        return ordered
    if count <= 1:
        return [ordered[len(ordered) // 2]]
    positions = {round(index * (len(ordered) - 1) / (count - 1)) for index in range(count)}
    return [ordered[index] for index in sorted(positions)]


def parse_selector(value: str) -> tuple[int, int]:
    try:
        outer, chunk = value.split(":", 1)
        return int(outer, 0), int(chunk, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("selector must be OUTER_INDEX:CHUNK_INDEX") from exc


def parse_padded(value: str) -> tuple[int, int, str]:
    try:
        outer, slot, kind = value.split(":", 2)
        if len(kind) != 4:
            raise ValueError
        return int(outer, 0), int(slot, 0), kind
    except ValueError as exc:
        raise argparse.ArgumentTypeError("padded array must be OUTER_INDEX:SLOT_SIZE:FOURCC") from exc


def probe_record(
    archive: Archive,
    record: ResourceRecord,
    max_stored: int,
    max_output: int,
    audio_prefix: bool,
    wav_dir: Path | None,
) -> dict[str, object]:
    base: dict[str, object] = {
        "outer_index": record.outer_index,
        "outer_id": record.outer_id,
        "outer_size": record.outer_size,
        "chunk_index": record.chunk_index,
        "chunk_offset": record.chunk_offset,
        "kind": record.kind,
        "stored_size": record.stored_size,
        "system_bytes": record.word_08,
        "video_bytes": record.word_0c,
        "compression_magic": f"0x{record.word_10:08x}",
        "overlap_scratch_bytes": record.word_14,
        "compressed": record.compressed,
        "source": record.source,
    }
    if record.slot_size is not None:
        base["slot_size"] = record.slot_size
    entry = entry_by_index(archive, record.outer_index)
    if record.outer_size != entry.size or int(record.outer_id, 0) != entry.name_id:
        base["status"] = "blocked"
        base["portme"] = "PORTME: inventory entry identity does not match parsed outer archive"
        return base
    if record.stored_size > max_stored:
        base["status"] = "blocked"
        base["portme"] = (
            f"PORTME: stored resource is 0x{record.stored_size:x} bytes; "
            f"bounded limit is 0x{max_stored:x}"
        )
        return base
    if record.compressed and record.output_size > max_output:
        base["status"] = "blocked"
        base["portme"] = (
            f"PORTME: decoded resource would be 0x{record.output_size:x} bytes; "
            f"bounded limit is 0x{max_output:x}"
        )
        return base

    fully_read = True
    read_size = HEADER.size + record.stored_size
    if record.kind == "AUDO" and not record.compressed and audio_prefix and wav_dir is None:
        # The descriptor sits in the system buffer.  One maximum-size channel
        # header group plus encoded bytes is sufficient to validate framing.
        read_size = min(read_size, HEADER.size + record.word_08 + 0x200)
        fully_read = read_size == HEADER.size + record.stored_size
    span = read_entry_range(archive, entry, record.chunk_offset, read_size)
    try:
        if fully_read:
            body, detail = decode_resource(span, record)
        elif record.compressed:
            raise ProbeError("compressed resources cannot be prefix-probed")
        else:
            body = span[HEADER.size:]
            detail = {
                "decoded_size": None,
                "decoded_sha256": None,
                "prefix_bytes_read": len(body),
            }
        semantic = semantic_probe(body, record, fully_read)
        base.update(detail)
        base["semantic"] = semantic
        if wav_dir is not None and record.kind == "AUDO":
            if not fully_read:
                raise ProbeError("AUDO WAV export requires a full body")
            path = write_audo_wav(wav_dir, record, body, semantic)
            base["wav_output"] = str(path)
        base["status"] = "decoded" if record.compressed else "parsed"
    except (ProbeError, TxtrError, struct.error, UnicodeDecodeError) as exc:
        base["status"] = "blocked"
        base["portme"] = f"PORTME: {exc}"
    return base


def summarize(records: list[dict[str, object]]) -> dict[str, object]:
    kinds = Counter(str(record["kind"]) for record in records)
    statuses = Counter(str(record["status"]) for record in records)
    names = Counter()
    audo_rates = Counter()
    audo_channels = Counter()
    audo_codec_words = Counter()
    shap_record_counts = Counter()
    tset_refs = 0
    for record in records:
        semantic = record.get("semantic")
        if not isinstance(semantic, dict):
            continue
        if isinstance(semantic.get("name"), str):
            names[str(semantic["name"])] += 1
        if record["kind"] == "AUDO":
            audo_rates[str(semantic.get("sample_rate"))] += 1
            audo_channels[str(semantic.get("channels"))] += 1
            audo_codec_words[str(semantic.get("codec_word"))] += 1
        elif record["kind"] == "SHAP":
            shap_record_counts[str(semantic.get("record_count"))] += 1
        elif record["kind"] == "TSET":
            tset_refs += int(semantic.get("reference_count", 0))
    return {
        "record_count": len(records),
        "kind_counts": dict(sorted(kinds.items())),
        "status_counts": dict(sorted(statuses.items())),
        "unique_name_count": len(names),
        "duplicate_names": {name: count for name, count in names.items() if count > 1},
        "audo_sample_rate_counts": dict(sorted(audo_rates.items())),
        "audo_channel_counts": dict(sorted(audo_channels.items())),
        "audo_codec_word_counts": dict(sorted(audo_codec_words.items())),
        "shap_record_count_distribution": dict(
            sorted(shap_record_counts.items(), key=lambda item: int(item[0]))
        ),
        "tset_reference_total": tset_refs,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path, help="path to vc_53450030/0")
    parser.add_argument(
        "--inventory",
        type=Path,
        default=Path("reports/assets/nfl2k5_resource_chunks_v2.json"),
    )
    parser.add_argument("--kind", action="append", choices=SUPPORTED_KINDS)
    parser.add_argument("--select", action="append", type=parse_selector, default=[])
    parser.add_argument("--all", action="store_true", help="probe all inventory records of selected kinds")
    parser.add_argument("--per-kind", type=int, default=5, help="stratified samples per kind without --all")
    parser.add_argument(
        "--padded",
        action="append",
        type=parse_padded,
        default=[],
        metavar="OUTER:SLOT:FOURCC",
        help="validate and add every resource in an explicitly sized fixed-slot array",
    )
    parser.add_argument("--max-stored", type=parse_int, default=0x800000)
    parser.add_argument("--max-output", type=parse_int, default=0x2000000)
    parser.add_argument(
        "--full-audio",
        action="store_true",
        help="read full AUDO payloads instead of bounded descriptor/first-block prefixes",
    )
    parser.add_argument(
        "--wav-dir",
        type=Path,
        help="decode selected AUDO payloads to PCM16 WAV (implies full audio reads)",
    )
    parser.add_argument("--output", type=Path, help="JSON report path; stdout if omitted")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.per_kind <= 0:
        raise ProbeError("--per-kind must be positive")
    archive = parse_archive(args.index)
    raw_inventory, inventory = parse_inventory(args.inventory)
    requested_kinds = args.kind or list(SUPPORTED_KINDS)
    selected: list[ResourceRecord] = []

    if args.select:
        by_key = {(record.outer_index, record.chunk_index): record for record in inventory}
        for key in args.select:
            record = by_key.get(key)
            if record is None:
                raise ProbeError(f"inventory has no chunk selector {key[0]}:{key[1]}")
            selected.append(record)
    else:
        for kind in requested_kinds:
            candidates = [record for record in inventory if record.kind == kind]
            if args.all:
                selected.extend(candidates)
            else:
                selected.extend(select_stratified(candidates, args.per_kind))

    padded_validation: list[dict[str, object]] = []
    for outer_index, slot_size, kind in args.padded:
        records, validation = validate_padded_array(archive, outer_index, slot_size, kind)
        selected.extend(records)
        padded_validation.append(validation)

    # Preserve explicit fixed-slot records in preference to the inventory's
    # first-slot duplicate, then emit a deterministic order.
    deduplicated: dict[tuple[int, int], ResourceRecord] = {}
    for record in selected:
        key = (record.outer_index, record.chunk_offset)
        if key not in deduplicated or record.source == "fixed_slot":
            deduplicated[key] = record
    selected = sorted(
        deduplicated.values(),
        key=lambda item: (item.outer_index, item.chunk_offset, item.chunk_index),
    )

    results = [
        probe_record(
            archive,
            record,
            args.max_stored,
            args.max_output,
            audio_prefix=not args.full_audio,
            wav_dir=args.wav_dir,
        )
        for record in selected
    ]
    report = {
        "schema": "nfl2k5_scene_probe/v1",
        "source_index": str(args.index),
        "source_inventory": str(args.inventory),
        "source_inventory_summary": raw_inventory.get("summary"),
        "limits": {
            "max_stored": args.max_stored,
            "max_output": args.max_output,
            "audio_prefix_mode": not args.full_audio and args.wav_dir is None,
        },
        "padded_arrays": padded_validation,
        "summary": summarize(results),
        "records": results,
    }
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8", newline="\n")
        print(
            f"wrote {len(results)} probe record(s) to {args.output}; "
            f"statuses={report['summary']['status_counts']}"
        )
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, FormatError, ProbeError, TxtrError, json.JSONDecodeError) as exc:
        raise SystemExit(f"error: {exc}") from exc

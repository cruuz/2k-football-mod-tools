#!/usr/bin/env python3
"""Strict NFL 2K5 uniform-package inventory and optional TSET PNG exporter.

The tool consumes the canonical v2 chunk inventory rather than rescanning
zero padding heuristically.  It decodes every ``Unif``, ``TSET``, and ``NAME``
wrapper in the 634-file uniform corpus, joins the already-verified standalone
TXTR inventory, and preserves every still-opaque scalar as raw data.

This is deliberately read-only.  It does not claim a safe serializer or patch
the game archives.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import struct
import sys
import zlib
from collections import Counter, OrderedDict, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# The shipped Windows runtime is an embeddable CPython whose ._pth file
# defines sys.path outright and, unlike a normal interpreter, does NOT add
# this script's own directory -- so the sibling imports below fail there
# with ModuleNotFoundError unless the directory is put back explicitly.
import sys as _sys
from pathlib import Path as _Path
_here = str(_Path(__file__).resolve().parent)
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from nfl_outer import Archive, parse_archive
from nfl_scene_probe import ResourceRecord, read_entry_range
from nfl_txtr import (
    COMPRESSED_SENTINEL,
    HEADER,
    XBOX_FORMAT_NAMES,
    TextureInfo,
    decode_chunk,
    safe_texture_name,
    texture_to_rgba,
    write_png,
)
from xbe_info import Xbe


INVENTORY_SCHEMA = "nfl2k5_resource_chunk_inventory/v1"
TXTR_SCHEMA = "nfl2k5_all_txtr_inventory/v1"
OUTPUT_SCHEMA = "nfl2k5_uniform_inventory/v1"
UNIF_COUNT = 634
PAIR_COUNT = 317
FIRST_OUTER = 3613
LAST_OUTER = 4246
PAIR_DELTA = 317
CHUNKS_PER_PACKAGE = 53
TSETS_PER_PACKAGE = 10
TSET_REFS_PER_PACKAGE = 51
TXTR_PER_PACKAGE = 41
NAME_METRICS = 29
XBE_MD5 = "444064a9ec984dd29d2c05a43f5c96e8"

TSET_NAMES = {
    1: ("jersey00", "jersey00_mud"),
    2: ("pants00", "pants00_mud"),
    3: ("sleeve00", "sleeve00_mud"),
    4: ("socks00", "socks00_mud"),
    5: tuple(
        name
        for number in range(1, 8)
        for name in (f"elbowpad{number:02d}", f"elbowpad{number:02d}_mud")
    ),
    6: tuple(f"glove{number:02d}" for number in range(1, 9)),
    7: tuple(
        name
        for number in range(1, 4)
        for name in (f"longsleeve{number:02d}", f"longsleeve{number:02d}_mud")
    ),
    8: tuple(
        name
        for number in (1, 4, 9)
        for name in (f"shoes{number:02d}", f"shoes{number:02d}_mud")
    ),
    9: tuple(
        name
        for number in (2, 3, 10)
        for name in (f"shoes{number:02d}", f"shoes{number:02d}_mud")
    ),
    10: ("wristband01", "wristband02", "wristband09"),
}

STANDALONE_NAMES = {
    11: "helmet00",
    12: "helmet02",
    **{13 + index: str(48 + index) for index in range(10)},
    **{23 + index: f"hn{48 + index}" for index in range(10)},
    **{33 + index: f"an{48 + index}" for index in range(10)},
    43: "names",
    45: "bump_jersey",
    46: "bump_sleeve",
    47: "bump_pants",
    48: "bump_sock",
    49: "logo",
    50: "chiclet",
    51: "splayer",
    52: "flipchip",
}

XBE_ANCHORS = {
    0x00038570: "c701ffffffffc3",
    0x00038580: "8b01560fb6d28bf081e6ff00000033f2",
    0x000385C0: "8b01f7d0c3",
    0x00038650: "51538bd98d4c2404e813ffffff",
    0x00043D20: "578bf88b461085c074078d44300f894610",
    0x00043E10: "8b44240453566a018bda8bf1e8fffeffff",
    0x0007BD91: "685833e600ba556e6966b94c33e600e83b8cfcff",
    0x0007BDBF: "685833e600ba556e6966b96833e600",
    0x0008E830: "8b0c85b052b6008b410cc3",
    0x0008E840: "8b0c85b052b6008b4108c3",
    0x0008E850: "8b0c85b052b6008b01c3",
    0x0008E860: "8b0c85b052b6008b4104c3",
    0x0008E870: "8b0c85b052b6008b4114c3",
    0x0011A0AC: "687828e700ba556e6966b96c28e700",
    0x0011A0C0: "687828e700ba556e6966b98828e700",
    0x00166420: "8bc28b512085d28bc87408e84024eeff",
    0x00166450: "56578bf28bf9e875d3edff8b56048bc8",
    0x00166490: "6850641600ba556e6966b9f4b6bd00e8fcd1edffc3",
    0x001664B0: "b9f4b6bd00e936d2edff",
}


class UniformError(ValueError):
    """Raised when a uniform-corpus invariant or bounds check fails."""


@dataclass(frozen=True)
class LogicalName:
    name: str
    name_id: int
    asset_code: str
    side_code: str
    side_context: str
    variant_id: int
    pair_key: str


def parse_int(value: str | int) -> int:
    return int(value, 0) if isinstance(value, str) else int(value)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise UniformError(message)


def s32(data: bytes, offset: int) -> int:
    require(0 <= offset <= len(data) - 4, f"s32 at 0x{offset:x} is out of bounds")
    return struct.unpack_from("<i", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    require(0 <= offset <= len(data) - 4, f"u32 at 0x{offset:x} is out of bounds")
    return struct.unpack_from("<I", data, offset)[0]


def relative_pointer(data: bytes, field: int, label: str) -> int | None:
    """Resolve the XBE 0x43D20 field-local, minus-one-biased pointer."""
    value = s32(data, field)
    if value == 0:
        return None
    target = field + value - 1
    require(0 <= target < len(data), f"{label} resolves outside body: 0x{target:x}")
    return target


def utf16z(data: bytes, offset: int | None, limit: int, label: str) -> str:
    require(offset is not None, f"{label} is null")
    assert offset is not None
    require(offset % 2 == 0, f"{label} offset 0x{offset:x} is unaligned")
    require(0 <= offset < limit <= len(data), f"{label} has invalid bounds")
    end = offset
    while end + 1 < limit and data[end : end + 2] != b"\0\0":
        end += 2
    require(end + 1 < limit, f"{label} is unterminated")
    try:
        value = data[offset:end].decode("utf-16le")
    except UnicodeDecodeError as exc:
        raise UniformError(f"{label} is invalid UTF-16LE") from exc
    require(all(character.isprintable() for character in value), f"{label} is not printable")
    return value


def uniform_name_id(name: str) -> int:
    """XBE 0x38650: CRC32 of uppercased UTF-16LE code units, no terminator."""
    return zlib.crc32(name.upper().encode("utf-16le")) & 0xFFFFFFFF


def logical_name_candidates() -> dict[int, LogicalName]:
    global _LOGICAL_NAME_CANDIDATES
    if _LOGICAL_NAME_CANDIDATES is not None:
        return _LOGICAL_NAME_CANDIDATES
    result: dict[int, LogicalName] = {}
    for code in range(100):
        for side_code, context in (("H", "HOME"), ("A", "AWAY")):
            for variant in range(100):
                name = f"{code:02d}{side_code}{variant}.IFF"
                name_id = uniform_name_id(name)
                item = LogicalName(
                    name=name,
                    name_id=name_id,
                    asset_code=f"{code:02d}",
                    side_code=side_code,
                    side_context=context,
                    variant_id=variant,
                    pair_key=f"{code:02d}:{variant}",
                )
                if name_id in result:
                    raise UniformError(
                        f"logical-name candidate collision 0x{name_id:08x}: "
                        f"{result[name_id].name}/{name}"
                    )
                result[name_id] = item
    # Pure function of nothing: computed once per process and shared.  Every
    # caller treats the table as read-only.
    _LOGICAL_NAME_CANDIDATES = result
    return result


_LOGICAL_NAME_CANDIDATES: dict[int, LogicalName] | None = None


class _InventoryRows:
    """The chunk rows of one memoized inventory document, indexed on demand.

    The index is built by the first lookup -- which happens after the caller's
    schema check, exactly where the historical linear scan ran -- and applies
    the very same coercions, so a malformed row raises the very same
    KeyError/TypeError/ValueError it always did.  Later lookups answer in
    O(1).
    """

    def __init__(self, value: dict[str, object]) -> None:
        self._value = value
        self._index: "dict[tuple[int, int], list[dict[str, object]]] | None" = (
            None
        )

    def rows_for(
        self, outer_index: int, chunk_index: int
    ) -> list[dict[str, object]]:
        if self._index is None:
            index: dict[tuple[int, int], list[dict[str, object]]] = {}
            for row in self._value["chunks"]:
                chunk_key = (int(row["outer_index"]), int(row["chunk_index"]))
                index.setdefault(chunk_key, []).append(row)
            self._index = index
        return list(self._index.get((outer_index, chunk_index), ()))


# The canonical chunk inventory is ~55 MB of JSON.  A multi-edit build used to
# re-read and re-parse it once per edit and then linearly scan all ~87k chunk
# rows per edit.  The parsed document is memoized per file identity and its
# row index is built once on first use, so N edits pay one parse and O(1) row
# lookups.  A rewrite moves size/mtime and misses the cache.
_INVENTORY_CACHE_LIMIT = 4
_INVENTORY_CACHE: "OrderedDict[tuple[object, ...], dict[str, object]]" = (
    OrderedDict()
)
_INVENTORY_ROWS_BY_ID: dict[int, _InventoryRows] = {}


def clear_inventory_cache() -> None:
    """Forget every memoized inventory document (tests and fresh sessions)."""

    _INVENTORY_ROWS_BY_ID.clear()
    _INVENTORY_CACHE.clear()


def load_inventory_document(path: Path) -> dict[str, object]:
    """The parsed chunk inventory at *path*, memoized per file identity."""

    info = path.stat()
    key = (str(path), info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    cached = _INVENTORY_CACHE.get(key)
    if cached is not None:
        _INVENTORY_CACHE.move_to_end(key)
        return cached
    value = json.loads(path.read_bytes())
    _INVENTORY_CACHE[key] = value
    _INVENTORY_CACHE.move_to_end(key)
    _INVENTORY_ROWS_BY_ID[id(value)] = _InventoryRows(value)
    while len(_INVENTORY_CACHE) > _INVENTORY_CACHE_LIMIT:
        _key, evicted = _INVENTORY_CACHE.popitem(last=False)
        _INVENTORY_ROWS_BY_ID.pop(id(evicted), None)
    return value


def inventory_chunk_rows(
    inventory_value: dict[str, object], outer_index: int, chunk_index: int
) -> list[dict[str, object]]:
    """The chunk rows for one (outer_index, chunk_index) pair.

    Documents produced by :func:`load_inventory_document` answer in O(1) from
    their memoized row index; any other dict keeps the historical linear scan
    with exactly the same filter semantics.
    """

    rows = _INVENTORY_ROWS_BY_ID.get(id(inventory_value))
    if rows is not None:
        return rows.rows_for(outer_index, chunk_index)
    chunks = inventory_value["chunks"]
    return [
        row for row in chunks
        if int(row["outer_index"]) == outer_index
        and int(row["chunk_index"]) == chunk_index
    ]


def load_inventory(path: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    require(raw.get("schema") == INVENTORY_SCHEMA, f"unsupported inventory schema in {path}")
    chunks = raw.get("chunks")
    require(isinstance(chunks, list), "inventory chunks are absent")
    return raw, chunks


def load_txtr_rows(path: Path, wanted: set[int]) -> dict[int, list[dict[str, str]]]:
    result: dict[int, list[dict[str, str]]] = defaultdict(list)
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        required = {
            "outer_index", "outer_id", "outer_head", "chunk_index", "chunk_offset",
            "name", "format_name", "width", "height", "depth", "mip_levels",
            "exported_mip_levels", "pixel_offset", "palette_offset", "conversion_status",
            "decoded_sha256", "rgba_sha256", "png_path",
        }
        require(reader.fieldnames is not None and required <= set(reader.fieldnames),
                f"TXTR TSV {path} lacks required fields")
        for row in reader:
            outer = int(row["outer_index"])
            if outer in wanted:
                result[outer].append(row)
    return result


def load_roster_rows(path: Path) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = defaultdict(list)
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        required = {
            "resource_label", "team_index", "nickname", "abbreviation", "asset_code",
            "city", "team_kind_code", "raw_hex",
        }
        require(reader.fieldnames is not None and required <= set(reader.fieldnames),
                f"roster TSV {path} lacks required fields")
        for row in reader:
            result[row["asset_code"]].append(row)
    return result


def main_roster_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row["resource_label"] == "roster"]


def style_label(
    logical: LogicalName, roster_rows: list[dict[str, str]]
) -> tuple[str, str, int | None, int | None]:
    """Reproduce XBE 0xE3530 labels without claiming a style for unknown codes."""
    mains = main_roster_rows(roster_rows)
    if not mains:
        return "", "no roster team carries this asset code", None, None
    if logical.variant_id == 0:
        return "Current Uniform", "XBE 0x000E354D", None, None
    if logical.variant_id > 14:
        return "", "XBE label switch only covers variants 0..14", None, None
    raw = bytes.fromhex(mains[0]["raw_hex"])
    offset = 0x15A + (logical.variant_id - 1) * 4
    require(offset + 4 <= len(raw), "roster team style pair is truncated")
    first, second = struct.unpack_from("<HH", raw, offset)
    if first != second and first != 0:
        if second < 1900:
            label = f"{first}  Alternate {second}"
            evidence = "XBE 0x000E365C format at 0x00E69B94"
        else:
            label = f"{first} - {second} Uniform"
            evidence = "XBE 0x000E367A format at 0x00E69BB8"
    else:
        label = f"{second} Uniform"
        evidence = "XBE 0x000E3698 format at 0x00E69B7C"
    if first == 0 and second == 0:
        evidence += "; zero pair retained verbatim (possibly non-selectable)"
    return label, evidence, first, second


def inventory_record(item: dict[str, object]) -> ResourceRecord:
    return ResourceRecord(
        outer_index=int(item["outer_index"]),
        outer_id=str(item["outer_id"]),
        outer_size=int(item["outer_size"]),
        chunk_index=int(item["chunk_index"]),
        chunk_offset=int(item["chunk_offset"]),
        kind=str(item["kind"]),
        stored_size=int(item["stored_size"]),
        word_08=int(item["word_08"]),
        word_0c=int(item["word_0c"]),
        word_10=parse_int(item["word_10"]),
        word_14=int(item["word_14"]),
    )


def read_and_validate_header(
    archive: Archive, item: dict[str, object]
) -> ResourceRecord:
    """Re-read one canonical-v2 wrapper and require every header field."""
    record = inventory_record(item)
    entry = archive.entries[record.outer_index]
    require(entry.size == record.outer_size, f"outer {record.outer_index}: size disagreement")
    require(entry.name_id == parse_int(record.outer_id), f"outer {record.outer_index}: ID disagreement")
    header = read_entry_range(archive, entry, record.chunk_offset, HEADER.size)
    fields = HEADER.unpack(header)
    expected = (
        record.kind.encode("ascii"), record.stored_size, record.word_08,
        record.word_0c, record.word_10, record.word_14, 0, 0,
    )
    require(fields == expected, f"outer {record.outer_index} chunk {record.chunk_index}: wrapper disagreement")
    require(record.end_offset <= entry.size,
            f"outer {record.outer_index} chunk {record.chunk_index}: wrapper body exceeds outer entry")
    return record


def read_and_validate_span(
    archive: Archive, item: dict[str, object]
) -> tuple[ResourceRecord, bytes, bytes, object | None]:
    record = read_and_validate_header(archive, item)
    entry = archive.entries[record.outer_index]
    span = read_entry_range(
        archive, entry, record.chunk_offset, HEADER.size + record.stored_size
    )
    body, info = decode_chunk(span, record.as_chunk())
    if record.compressed:
        require(len(body) == record.word_08 + record.word_0c,
                f"outer {record.outer_index} chunk {record.chunk_index}: decoded size mismatch")
        require(info is not None and info.consumed_bytes <= record.stored_size,
                f"outer {record.outer_index} chunk {record.chunk_index}: invalid LZ consumption")
    else:
        require(info is None and len(body) == record.stored_size,
                f"outer {record.outer_index} chunk {record.chunk_index}: raw size mismatch")
    return record, span, body, info


def parse_unif(body: bytes, record: ResourceRecord) -> dict[str, object]:
    require(record.stored_size == 0x50 and len(body) == 0x50, "Unif body is not 0x50 bytes")
    require(body[0x0C:0x10] == b"Unif", "Unif inner marker is absent")
    require(body[0:0x0C] == b"\0" * 0x0C, "Unif prefix words are nonzero")
    name_offset = relative_pointer(body, 0x10, "Unif name")
    payload_offset = relative_pointer(body, 0x14, "Unif payload")
    require(name_offset == 0x20 and payload_offset == 0x30,
            f"Unif pointer targets are {name_offset!r}/{payload_offset!r}")
    require(body[0x18:0x20] == b"\0" * 8, "Unif on-disk callback slots are nonzero")
    name = utf16z(body, name_offset, payload_offset, "Unif name")
    require(name == "uniform", f"unexpected Unif name {name!r}")
    payload = struct.unpack_from("<8I", body, payload_offset)
    require(payload[6:] == (0, 0), "Unif payload tail words are nonzero")
    scale = struct.unpack_from("<f", body, payload_offset + 0x10)[0]
    require(math.isfinite(scale), "Unif payload scale is non-finite")
    return {
        "name": name,
        "stored_name_relative": s32(body, 0x10),
        "name_offset": name_offset,
        "stored_payload_relative": s32(body, 0x14),
        "payload_offset": payload_offset,
        "color_word_0": f"0x{payload[0]:08x}",
        "color_word_1": f"0x{payload[1]:08x}",
        "selector_08": payload[2],
        "selector_0c": payload[3],
        "scale_10": scale,
        "flag_14": payload[5],
        "reserved_18": payload[6],
        "reserved_1c": payload[7],
        "body_sha256": sha256(body),
        "raw_hex": body.hex(),
    }


def parse_name(body: bytes, record: ResourceRecord) -> tuple[dict[str, object], list[dict[str, object]]]:
    require(record.stored_size == 0xA0 and len(body) == 0xA0, "NAME body is not 0xA0 bytes")
    require(body[0x0C:0x10] == b"NAME", "NAME inner marker is absent")
    require(body[0:0x0C] == b"\0" * 0x0C, "NAME prefix words are nonzero")
    name_offset = relative_pointer(body, 0x10, "NAME name")
    table_offset = relative_pointer(body, 0x14, "NAME metric table")
    require(name_offset == 0x20 and table_offset == 0x2C,
            f"NAME pointer targets are {name_offset!r}/{table_offset!r}")
    require(body[0x18:0x20] == b"\0" * 8, "NAME on-disk callback slots are nonzero")
    name = utf16z(body, name_offset, table_offset, "NAME name")
    require(name == "names", f"unexpected NAME object name {name!r}")
    require((len(body) - table_offset) % 4 == 0, "NAME metric table is not 4-byte strided")
    count = (len(body) - table_offset) // 4
    require(count == NAME_METRICS, f"NAME has {count} metric pairs, expected {NAME_METRICS}")
    metrics: list[dict[str, object]] = []
    for index in range(count):
        atlas_offset, advance = struct.unpack_from("<HH", body, table_offset + index * 4)
        if index == 0:
            characters = "'"
        elif index == 1:
            characters = "-"
        elif 2 <= index <= 27:
            characters = chr(ord("A") + index - 2) + "/" + chr(ord("a") + index - 2)
        else:
            characters = "PORTME: unmapped index 28"
        metrics.append({
            "metric_index": index,
            "characters": characters,
            "record_offset": table_offset + index * 4,
            "atlas_offset_u16": atlas_offset,
            "advance_metric_u16": advance,
        })
    return ({
        "name": name,
        "name_offset": name_offset,
        "table_offset": table_offset,
        "metric_count": count,
        "body_sha256": sha256(body),
        "raw_hex": body.hex(),
    }, metrics)


def parse_tset(
    body: bytes,
    record: ResourceRecord,
    logical: LogicalName,
    png_dir: Path | None,
) -> tuple[dict[str, object], list[dict[str, object]], int]:
    require(len(body) == record.word_08 + record.word_0c, "TSET decoded size mismatch")
    require(record.word_08 >= 0x20, "TSET system buffer is too short")
    version, count = struct.unpack_from("<II", body, 0)
    require(version == 0x0D, f"TSET version is 0x{version:x}, expected 0x0d")
    expected_names = TSET_NAMES.get(record.chunk_index)
    require(expected_names is not None, f"unexpected TSET chunk index {record.chunk_index}")
    require(count == len(expected_names),
            f"TSET chunk {record.chunk_index}: {count} refs, expected {len(expected_names)}")
    video = body[record.word_08 : record.word_08 + record.word_0c]
    references: list[dict[str, object]] = []
    png_count = 0
    for index in range(count):
        base = 0x18 + index * 0x24
        require(base + 0x18 <= record.word_08,
                f"TSET chunk {record.chunk_index} ref {index} exceeds system buffer")
        require(body[base : base + 4] == b"TXTR", "TSET embedded TXTR marker is absent")
        name_offset = relative_pointer(body, base + 4, "TSET embedded name")
        descriptor_offset = relative_pointer(body, base + 8, "TSET descriptor")
        root_offset = relative_pointer(body, base + 0x14, "TSET root")
        name = utf16z(body, name_offset, record.word_08, "TSET texture name")
        require(name == expected_names[index],
                f"TSET chunk {record.chunk_index} ref {index}: {name!r}, expected {expected_names[index]!r}")
        require(descriptor_offset is not None and descriptor_offset + 0x18 <= record.word_08,
                f"TSET {name}: descriptor is outside system buffer")
        assert descriptor_offset is not None
        unknown0, pixel_offset, palette_offset, packed_format, packed_size, flags = struct.unpack_from(
            "<6I", body, descriptor_offset
        )
        dimensions = (packed_format >> 4) & 0xF
        format_code = (packed_format >> 8) & 0xFF
        mip_levels = (packed_format >> 16) & 0xF
        if packed_size:
            width = packed_size & 0xFFFF
            height = packed_size >> 16
        else:
            width = 1 << ((packed_format >> 20) & 0xF)
            height = 1 << ((packed_format >> 24) & 0xF)
        depth = 1 << ((packed_format >> 28) & 0xF)
        format_name = XBOX_FORMAT_NAMES.get(format_code, f"UNKNOWN_0x{format_code:02X}")
        require(dimensions == 2 and depth == 1, f"TSET {name}: unsupported dimensionality")
        require(format_code == 0x0B, f"TSET {name}: expected P8, found {format_name}")
        base_bytes = width * height
        require(pixel_offset + base_bytes <= len(video), f"TSET {name}: base pixels out of bounds")
        require(palette_offset + 0x400 <= len(video), f"TSET {name}: palette out of bounds")
        pixel_hash = sha256(video[pixel_offset : pixel_offset + base_bytes])
        palette_hash = sha256(video[palette_offset : palette_offset + 0x400])
        if png_dir is not None:
            texture = TextureInfo(
                name=name,
                name_offset=name_offset if name_offset is not None else 0,
                descriptor_offset=descriptor_offset,
                pixel_offset=pixel_offset,
                palette_offset=palette_offset,
                packed_format=packed_format,
                packed_size=packed_size,
                descriptor_flags=flags,
                dimensions=dimensions,
                format_code=format_code,
                format_name=format_name,
                mip_levels=mip_levels,
                width=width,
                height=height,
                depth=depth,
            )
            rgba = texture_to_rgba(body, record.as_chunk(), texture)
            target = (
                png_dir / logical.name.removesuffix(".IFF")
                / f"tset_{record.chunk_index:02d}_{index:02d}_{safe_texture_name(name, str(index))}.png"
            )
            write_png(target, width, height, rgba)
            png_count += 1
        references.append({
            "tset_chunk_index": record.chunk_index,
            "reference_index": index,
            "record_offset": base,
            "name": name,
            "name_offset": name_offset,
            "descriptor_offset": descriptor_offset,
            "root_offset": root_offset,
            "unknown0": f"0x{unknown0:08x}",
            "pixel_offset": pixel_offset,
            "palette_offset": palette_offset,
            "packed_format": f"0x{packed_format:08x}",
            "packed_size": packed_size,
            "descriptor_flags": f"0x{flags:08x}",
            "dimensions": dimensions,
            "format_code": format_code,
            "format_name": format_name,
            "mip_levels": mip_levels,
            "width": width,
            "height": height,
            "depth": depth,
            "base_pixel_sha256": pixel_hash,
            "palette_bgra_sha256": palette_hash,
        })
    summary = {
        "chunk_index": record.chunk_index,
        "chunk_offset": record.chunk_offset,
        "stored_size": record.stored_size,
        "system_bytes": record.word_08,
        "video_bytes": record.word_0c,
        "reference_count": count,
        "decoded_sha256": sha256(body),
    }
    return summary, references, png_count


def verify_xbe(path: Path) -> dict[str, object]:
    xbe = Xbe(path)
    md5 = hashlib.md5(xbe.data).hexdigest()  # nosec: identity, not security
    require(md5 == XBE_MD5, f"unexpected XBE MD5 {md5}")
    anchors: list[dict[str, object]] = []
    for address, expected_hex in XBE_ANCHORS.items():
        expected = bytes.fromhex(expected_hex)
        offset = xbe.va_to_offset(address, len(expected))
        actual = xbe.data[offset : offset + len(expected)]
        require(actual == expected,
                f"XBE anchor 0x{address:08x}: {actual.hex()} != {expected_hex}")
        anchors.append({"address": f"0x{address:08x}", "bytes": expected_hex})
    strings = {
        0x00E61060: "%s%c%d.iff",
        0x00E615F4: "CROWDHOME",
        0x00E61608: "CROWDAWAY",
        0x00E6162C: "HOME",
        0x00E61638: "AWAY",
        0x00E6334C: "HOME",
        0x00E63358: "uniform",
        0x00E63368: "AWAY",
        0x00E63E60: "lo_body",
        0x00E63E70: "hi_body",
        0x00E655C4: "uniform",
        0x00E655D4: "names",
        0x00E69B5C: "Current Uniform",
        0x00E69B7C: "%d Uniform",
        0x00E69B94: "%d  Alternate %d",
        0x00E69BB8: "%d - %d Uniform",
        0x00E7286C: "HOME",
        0x00E72878: "uniform",
        0x00E72888: "AWAY",
    }
    for address, expected in strings.items():
        require(xbe.utf16z_va(address) == expected,
                f"XBE string 0x{address:08x} is not {expected!r}")
    return {
        "path": str(path),
        "md5": md5,
        "sha256": sha256(xbe.data),
        "anchors": anchors,
        "strings": {f"0x{address:08x}": value for address, value in strings.items()},
    }


def joined(values: Iterable[str]) -> str:
    return ";".join(value for value in values if value)


def write_tsv(path: Path, fields: list[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def build(args: argparse.Namespace) -> dict[str, object]:
    inventory_raw, chunks = load_inventory(args.inventory)
    archive = parse_archive(args.index)
    require(str(inventory_raw.get("source_index")) == str(args.index),
            "canonical inventory source path differs from requested index")

    unif_items = [
        item for item in chunks
        if item.get("kind") == "Unif" and FIRST_OUTER <= int(item["outer_index"]) <= LAST_OUTER
    ]
    require(len(unif_items) == UNIF_COUNT, f"found {len(unif_items)} Unif chunks, expected {UNIF_COUNT}")
    require([int(item["outer_index"]) for item in unif_items] == list(range(FIRST_OUTER, LAST_OUTER + 1)),
            "Unif outer indices are not the exact contiguous 3613..4246 range")
    wanted = {int(item["outer_index"]) for item in unif_items}
    grouped: dict[int, list[dict[str, object]]] = defaultdict(list)
    for item in chunks:
        outer = int(item["outer_index"])
        if outer in wanted:
            grouped[outer].append(item)
    txtr_rows = load_txtr_rows(args.txtr_tsv, wanted)
    roster = load_roster_rows(args.roster_teams)
    logical_by_id = logical_name_candidates()
    xbe = verify_xbe(args.xbe)

    png_selected = set(args.png_outer_index or [])
    if args.png_dir is not None and not png_selected:
        raise UniformError("--png-dir requires at least one --png-outer-index")
    require(png_selected <= wanted, f"PNG outer indices outside uniform corpus: {sorted(png_selected - wanted)}")

    package_rows: list[dict[str, object]] = []
    tset_rows: list[dict[str, object]] = []
    txtr_output_rows: list[dict[str, object]] = []
    name_rows: list[dict[str, object]] = []
    package_json: list[dict[str, object]] = []
    package_by_pair_side: dict[tuple[str, str], dict[str, object]] = {}
    tset_by_pair_side: dict[tuple[str, str], dict[tuple[int, str], dict[str, object]]] = {}
    txtr_by_pair_side: dict[tuple[str, str], dict[str, dict[str, str]]] = {}
    png_count = 0

    for outer_index in range(FIRST_OUTER, LAST_OUTER + 1):
        entry = archive.entries[outer_index]
        logical = logical_by_id.get(entry.name_id)
        require(logical is not None,
                f"outer {outer_index} ID 0x{entry.name_id:08x} has no uniform filename candidate")
        assert logical is not None
        items = sorted(grouped[outer_index], key=lambda item: int(item["chunk_index"]))
        require(len(items) == CHUNKS_PER_PACKAGE,
                f"outer {outer_index}: {len(items)} chunks, expected {CHUNKS_PER_PACKAGE}")
        require([int(item["chunk_index"]) for item in items] == list(range(CHUNKS_PER_PACKAGE)),
                f"outer {outer_index}: chunk indices are not 0..52")
        expected_kinds = ["Unif"] + ["TSET"] * 10 + ["TXTR"] * 33 + ["NAME"] + ["TXTR"] * 8
        require([str(item["kind"]) for item in items] == expected_kinds,
                f"outer {outer_index}: unexpected 53-chunk kind sequence")
        cursor = 0
        for item in items:
            require(int(item["chunk_offset"]) == cursor,
                    f"outer {outer_index}: gap before chunk {item['chunk_index']}")
            cursor = int(item["chunk_offset"]) + HEADER.size + int(item["stored_size"])
        require(cursor == entry.size, f"outer {outer_index}: final chunk does not end at outer size")

        unif_record, _, unif_body, _ = read_and_validate_span(archive, items[0])
        require(unif_record.word_08 == unif_record.word_0c == unif_record.word_10 == unif_record.word_14 == 0,
                f"outer {outer_index}: Unif wrapper words are not all zero")
        unif = parse_unif(unif_body, unif_record)

        per_tset: list[dict[str, object]] = []
        per_tset_refs: list[dict[str, object]] = []
        for item in items[1:11]:
            record, _, body, info = read_and_validate_span(archive, item)
            require(record.word_10 == COMPRESSED_SENTINEL, f"outer {outer_index}: TSET is not compressed")
            summary, refs, created = parse_tset(
                body, record, logical, args.png_dir if outer_index in png_selected else None
            )
            if info is not None:
                summary["lz_consumed_bytes"] = info.consumed_bytes
                summary["lz_unused_bytes"] = record.stored_size - info.consumed_bytes
            per_tset.append(summary)
            per_tset_refs.extend(refs)
            png_count += created
        require(len(per_tset_refs) == TSET_REFS_PER_PACKAGE,
                f"outer {outer_index}: {len(per_tset_refs)} TSET refs, expected {TSET_REFS_PER_PACKAGE}")

        name_item = items[44]
        name_record, _, name_body, _ = read_and_validate_span(archive, name_item)
        require(name_record.word_08 == name_record.word_0c == name_record.word_10 == name_record.word_14 == 0,
                f"outer {outer_index}: NAME wrapper words are not all zero")
        name_object, metrics = parse_name(name_body, name_record)

        external_txtrs = sorted(txtr_rows.get(outer_index, []), key=lambda row: int(row["chunk_index"]))
        require(len(external_txtrs) == TXTR_PER_PACKAGE,
                f"outer {outer_index}: {len(external_txtrs)} TXTR rows, expected {TXTR_PER_PACKAGE}")
        require([int(row["chunk_index"]) for row in external_txtrs] == sorted(STANDALONE_NAMES),
                f"outer {outer_index}: standalone TXTR chunk index set differs")
        for row in external_txtrs:
            chunk_index = int(row["chunk_index"])
            wrapper = read_and_validate_header(archive, items[chunk_index])
            require(wrapper.kind == "TXTR" and wrapper.compressed,
                    f"outer {outer_index} chunk {chunk_index}: standalone TXTR wrapper is not compressed TXTR")
            require(int(row["chunk_offset"]) == wrapper.chunk_offset,
                    f"outer {outer_index} chunk {chunk_index}: TXTR TSV offset differs from wrapper")
            require(row["name"] == STANDALONE_NAMES[chunk_index],
                    f"outer {outer_index} chunk {chunk_index}: TXTR name mismatch")
            require(parse_int(row["outer_id"]) == entry.name_id and row["outer_head"] == "Unif",
                    f"outer {outer_index} chunk {chunk_index}: TXTR outer identity mismatch")
            require(row["conversion_status"] == "base_level_supported",
                    f"outer {outer_index} chunk {chunk_index}: TXTR conversion unsupported")

        code_roster = roster.get(logical.asset_code, [])
        mains = main_roster_rows(code_roster)
        display, display_evidence, style_first, style_second = style_label(logical, code_roster)
        current_names = [f"{row['city']} {row['nickname']}" for row in mains]
        current_abbreviations = [row["abbreviation"] for row in mains]
        historic_abbreviations = [
            row["abbreviation"] for row in code_roster if row["resource_label"] != "roster"
        ]
        pair_outer = outer_index + PAIR_DELTA if logical.side_code == "H" else outer_index - PAIR_DELTA
        base = {
            "outer_index": outer_index,
            "outer_id": f"0x{entry.name_id:08x}",
            "logical_name": logical.name,
            "expected_name_id": f"0x{uniform_name_id(logical.name):08x}",
            "asset_code": logical.asset_code,
            "side_code": logical.side_code,
            "side_context": logical.side_context,
            "variant_id": logical.variant_id,
            "pair_key": logical.pair_key,
            "pair_outer_index": pair_outer,
            "roster_current_names": joined(current_names),
            "roster_current_abbreviations": joined(current_abbreviations),
            "roster_historic_abbreviations": joined(historic_abbreviations),
            "style_display": display,
            "style_label_evidence": display_evidence,
            "style_pair_first": style_first if style_first is not None else "",
            "style_pair_second": style_second if style_second is not None else "",
        }
        package_row = {
            **base,
            "outer_size": entry.size,
            "unif_name": unif["name"],
            "color_word_0": unif["color_word_0"],
            "color_word_1": unif["color_word_1"],
            "selector_08": unif["selector_08"],
            "selector_0c": unif["selector_0c"],
            "scale_10": format(float(unif["scale_10"]), ".9g"),
            "flag_14": unif["flag_14"],
            "unif_body_sha256": unif["body_sha256"],
            "unif_raw_hex": unif["raw_hex"],
            "name_body_sha256": name_object["body_sha256"],
            "tset_count": len(per_tset),
            "tset_texture_count": len(per_tset_refs),
            "standalone_txtr_count": len(external_txtrs),
        }
        package_rows.append(package_row)
        package_by_pair_side[(logical.pair_key, logical.side_code)] = package_row

        tset_index: dict[tuple[int, str], dict[str, object]] = {}
        for ref in per_tset_refs:
            row = {**base, **ref}
            tset_rows.append(row)
            tset_index[(int(ref["tset_chunk_index"]), str(ref["name"]))] = ref
        tset_by_pair_side[(logical.pair_key, logical.side_code)] = tset_index

        txtr_index: dict[str, dict[str, str]] = {}
        for row in external_txtrs:
            output = {**base, **row}
            txtr_output_rows.append(output)
            txtr_index[row["name"]] = row
        txtr_by_pair_side[(logical.pair_key, logical.side_code)] = txtr_index

        for metric in metrics:
            name_rows.append({**base, **metric, "name_body_sha256": name_object["body_sha256"]})

        package_json.append({
            **base,
            "outer_size": entry.size,
            "unif": unif,
            "name_object": name_object,
            "tsets": per_tset,
            "standalone_txtr_names": [row["name"] for row in external_txtrs],
        })

    require(png_count == len(png_selected) * TSET_REFS_PER_PACKAGE,
            f"created {png_count} embedded PNGs, expected {len(png_selected) * TSET_REFS_PER_PACKAGE}")

    pair_keys = sorted({row["pair_key"] for row in package_rows}, key=lambda key: (int(key.split(":")[0]), int(key.split(":")[1])))
    require(len(pair_keys) == PAIR_COUNT, f"found {len(pair_keys)} pairs, expected {PAIR_COUNT}")
    pair_rows: list[dict[str, object]] = []
    for key in pair_keys:
        home = package_by_pair_side.get((key, "H"))
        away = package_by_pair_side.get((key, "A"))
        require(home is not None and away is not None, f"pair {key} lacks H or A")
        assert home is not None and away is not None
        require(int(away["outer_index"]) - int(home["outer_index"]) == PAIR_DELTA,
                f"pair {key} is not separated by +317")
        htx = txtr_by_pair_side[(key, "H")]
        atx = txtr_by_pair_side[(key, "A")]
        require(set(htx) == set(atx) == set(STANDALONE_NAMES.values()), f"pair {key}: TXTR name mismatch")
        matching_txtr = sorted(name for name in htx if htx[name]["rgba_sha256"] == atx[name]["rgba_sha256"])
        differing_txtr = sorted(set(htx) - set(matching_txtr))
        htset = tset_by_pair_side[(key, "H")]
        atset = tset_by_pair_side[(key, "A")]
        require(set(htset) == set(atset), f"pair {key}: TSET reference mismatch")
        matching_pixels = sum(
            htset[item]["base_pixel_sha256"] == atset[item]["base_pixel_sha256"] for item in htset
        )
        matching_palettes = sum(
            htset[item]["palette_bgra_sha256"] == atset[item]["palette_bgra_sha256"] for item in htset
        )
        pair_rows.append({
            "pair_key": key,
            "asset_code": home["asset_code"],
            "variant_id": home["variant_id"],
            "roster_current_names": home["roster_current_names"],
            "style_display": home["style_display"],
            "home_logical_name": home["logical_name"],
            "home_outer_index": home["outer_index"],
            "home_outer_id": home["outer_id"],
            "away_logical_name": away["logical_name"],
            "away_outer_index": away["outer_index"],
            "away_outer_id": away["outer_id"],
            "logo_rgba_match": htx["logo"]["rgba_sha256"] == atx["logo"]["rgba_sha256"],
            "unif_body_match": home["unif_body_sha256"] == away["unif_body_sha256"],
            "name_body_match": home["name_body_sha256"] == away["name_body_sha256"],
            "matching_standalone_txtr_count": len(matching_txtr),
            "matching_standalone_txtr_names": joined(matching_txtr),
            "differing_standalone_txtr_names": joined(differing_txtr),
            "matching_tset_base_pixel_count": matching_pixels,
            "matching_tset_palette_count": matching_palettes,
            "tset_reference_count": len(htset),
        })
    require(all(bool(row["logo_rgba_match"]) for row in pair_rows),
            "one or more H/A pairs have different logo RGBA hashes")

    code_rows: list[dict[str, object]] = []
    for code in sorted({str(row["asset_code"]) for row in package_rows}, key=int):
        rows = [row for row in package_rows if row["asset_code"] == code and row["side_code"] == "H"]
        roster_rows = roster.get(code, [])
        mains = main_roster_rows(roster_rows)
        code_rows.append({
            "asset_code": code,
            "pair_count": len(rows),
            "variant_ids": joined(str(row["variant_id"]) for row in sorted(rows, key=lambda row: int(row["variant_id"]))),
            "roster_current_names": joined(f"{row['city']} {row['nickname']}" for row in mains),
            "roster_current_abbreviations": joined(row["abbreviation"] for row in mains),
            "roster_historic_abbreviations": joined(
                row["abbreviation"] for row in roster_rows if row["resource_label"] != "roster"
            ),
            "roster_match": bool(roster_rows),
        })

    package_fields = [
        "outer_index", "outer_id", "logical_name", "expected_name_id", "outer_size",
        "asset_code", "side_code", "side_context", "variant_id", "pair_key", "pair_outer_index",
        "roster_current_names", "roster_current_abbreviations", "roster_historic_abbreviations",
        "style_display", "style_label_evidence", "style_pair_first", "style_pair_second",
        "unif_name", "color_word_0", "color_word_1", "selector_08", "selector_0c",
        "scale_10", "flag_14", "unif_body_sha256", "name_body_sha256", "tset_count",
        "tset_texture_count", "standalone_txtr_count", "unif_raw_hex",
    ]
    base_fields = [
        "outer_index", "outer_id", "logical_name", "asset_code", "side_code", "side_context",
        "variant_id", "pair_key", "pair_outer_index", "roster_current_names",
        "roster_current_abbreviations", "roster_historic_abbreviations", "style_display",
    ]
    tset_fields = base_fields + [
        "tset_chunk_index", "reference_index", "record_offset", "name", "name_offset",
        "descriptor_offset", "root_offset", "unknown0", "pixel_offset", "palette_offset",
        "packed_format", "packed_size", "descriptor_flags", "dimensions", "format_code",
        "format_name", "mip_levels", "width", "height", "depth", "base_pixel_sha256",
        "palette_bgra_sha256",
    ]
    txtr_fields = base_fields + [
        "outer_head", "chunk_index", "chunk_offset", "name", "format_name", "width", "height",
        "depth", "mip_levels", "exported_mip_levels", "pixel_offset", "palette_offset",
        "conversion_status", "decoded_sha256", "rgba_sha256", "png_path",
    ]
    name_fields = base_fields + [
        "metric_index", "characters", "record_offset", "atlas_offset_u16", "advance_metric_u16",
        "name_body_sha256",
    ]
    pair_fields = [
        "pair_key", "asset_code", "variant_id", "roster_current_names", "style_display",
        "home_logical_name", "home_outer_index", "home_outer_id", "away_logical_name",
        "away_outer_index", "away_outer_id", "logo_rgba_match", "unif_body_match",
        "name_body_match", "matching_standalone_txtr_count", "matching_standalone_txtr_names",
        "differing_standalone_txtr_names", "matching_tset_base_pixel_count",
        "matching_tset_palette_count", "tset_reference_count",
    ]
    code_fields = [
        "asset_code", "pair_count", "variant_ids", "roster_current_names",
        "roster_current_abbreviations", "roster_historic_abbreviations", "roster_match",
    ]
    write_tsv(args.packages_tsv, package_fields, package_rows)
    write_tsv(args.tset_tsv, tset_fields, tset_rows)
    write_tsv(args.standalone_tsv, txtr_fields, txtr_output_rows)
    write_tsv(args.name_metrics_tsv, name_fields, name_rows)
    write_tsv(args.pairs_tsv, pair_fields, pair_rows)
    write_tsv(args.codes_tsv, code_fields, code_rows)

    summary = {
        "uniform_package_count": len(package_rows),
        "logical_pair_count": len(pair_rows),
        "asset_code_count": len(code_rows),
        "home_package_count": sum(row["side_code"] == "H" for row in package_rows),
        "away_package_count": sum(row["side_code"] == "A" for row in package_rows),
        "tset_count": UNIF_COUNT * TSETS_PER_PACKAGE,
        "tset_texture_reference_count": len(tset_rows),
        "standalone_txtr_count": len(txtr_output_rows),
        "name_metric_count": len(name_rows),
        "pair_logo_rgba_match_count": sum(bool(row["logo_rgba_match"]) for row in pair_rows),
        "exact_unif_body_pair_match_count": sum(bool(row["unif_body_match"]) for row in pair_rows),
        "exact_name_body_pair_match_count": sum(bool(row["name_body_match"]) for row in pair_rows),
        "unif_selector_08_counts": dict(sorted(Counter(str(row["selector_08"]) for row in package_rows).items())),
        "unif_selector_0c_counts": dict(sorted(Counter(str(row["selector_0c"]) for row in package_rows).items())),
        "unif_scale_counts": dict(sorted(Counter(str(row["scale_10"]) for row in package_rows).items())),
        "unif_flag_14_counts": dict(sorted(Counter(str(row["flag_14"]) for row in package_rows).items())),
        "embedded_pngs_written": png_count,
    }
    report = {
        "schema": OUTPUT_SCHEMA,
        "source_index": str(args.index),
        "canonical_inventory": str(args.inventory),
        "standalone_txtr_inventory": str(args.txtr_tsv),
        "roster_team_inventory": str(args.roster_teams),
        "summary": summary,
        "proved_layout": {
            "wrapper_size": 0x20,
            "unif_body_size": 0x50,
            "unif_name_relative_field": 0x10,
            "unif_payload_relative_field": 0x14,
            "unif_payload_offset": 0x30,
            "unif_payload_size": 0x20,
            "name_body_size": 0xA0,
            "name_metric_table_offset": 0x2C,
            "name_metric_stride": 4,
            "name_metric_count": NAME_METRICS,
            "package_chunk_sequence": "Unif, 10*TSET, 33*TXTR, NAME, 8*TXTR",
            "standalone_txtr_names_by_chunk": {str(key): value for key, value in STANDALONE_NAMES.items()},
            "tset_names_by_chunk": {str(key): list(value) for key, value in TSET_NAMES.items()},
        },
        "name_id_algorithm": {
            "description": "CRC32 of uppercase UTF-16LE logical filename without terminator",
            "xbe_crc_initializer": "0xffffffff",
            "xbe_crc_final_xor": "bitwise complement",
            "xbe_uppercase_crc_function": "0x00038650",
            "matched_ids": UNIF_COUNT,
            "unmatched_ids": 0,
            "candidate_collisions": 0,
        },
        "xbe_evidence": xbe,
        "portme": [
            "PORTME: assign semantic names to payload selectors +0x08/+0x0c and flag +0x14 only after their rendering branches are fully typed.",
            "PORTME: prove the exact physical meaning/unit of NAME metric word 0 and the unused index-28 mapping; the consumer proves indexing and advance use, not a complete font schema.",
            "PORTME: no SCNE is embedded in these packages; finish material-to-mesh binding against shared lo_body/hi_body scenes before claiming a model link.",
            "PORTME: implement a separately validated archive writer before attempting in-place replacement; this inventory is read-only.",
        ],
        "asset_codes": code_rows,
        "packages": package_json,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inventory all 634 NFL 2K5 uniform packages")
    parser.add_argument("index", type=Path, help="vc_53450030/0 archive index")
    parser.add_argument("--inventory", type=Path, required=True, help="canonical v2 chunk inventory JSON")
    parser.add_argument("--txtr-tsv", type=Path, required=True, help="canonical all-TXTR TSV")
    parser.add_argument("--roster-teams", type=Path, required=True, help="strict roster team TSV")
    parser.add_argument("--xbe", type=Path, required=True, help="NFL 2K5 default.xbe")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--packages-tsv", type=Path, required=True)
    parser.add_argument("--tset-tsv", type=Path, required=True)
    parser.add_argument("--standalone-tsv", type=Path, required=True)
    parser.add_argument("--name-metrics-tsv", type=Path, required=True)
    parser.add_argument("--pairs-tsv", type=Path, required=True)
    parser.add_argument("--codes-tsv", type=Path, required=True)
    parser.add_argument("--png-dir", type=Path, help="optionally export embedded TSET textures")
    parser.add_argument(
        "--png-outer-index", type=int, action="append",
        help="uniform outer index to export (repeatable; requires --png-dir)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = build(args)
    except (UniformError, OSError, json.JSONDecodeError, UnicodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    summary = report["summary"]
    print(
        "NFL2K5_UNIFORM_INVENTORY_OK "
        f"packages={summary['uniform_package_count']} pairs={summary['logical_pair_count']} "
        f"tset_refs={summary['tset_texture_reference_count']} "
        f"standalone_txtr={summary['standalone_txtr_count']} "
        f"pngs={summary['embedded_pngs_written']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Same-footprint jersey bump-map writer for NFL 2K5 uniform packages.

Every uniform package carries four A8R8G8B8 swizzled tangent-space bump maps
(``bump_jersey``, ``bump_pants``, ``bump_sleeve``, ``bump_sock``) as VC-LZ
compressed TXTR chunks.  The A10 research proved that one of these chunks can
be rebuilt at its exact retail span -- box-filter mip chain, NV2A Morton
swizzle, VC-LZ recompression into the fixed stored body -- and that the edit
is loaded and rendered by the retail title.  This module productizes that
proof: it discovers the uniform packages and their bump chunks from the entry
tables (no hardcoded outer indices), exports them to PNG, and imports authored
PNGs back with a fail-closed pipeline.

The 634 uniform packages live in whichever ``vc_53450030`` pack the entry
table places them (retail spreads them over packs 9/A/B/C plus one early
volume), so every operation resolves the OWNING pack per entry.  The three
retail packages whose entries cross a pack extent (outers 3625, 3832, 4136)
are supported too: reads and writes are segmented at pack boundaries, still
touching only the exact span.

Two image shapes are accepted, both read through the same entry-table
discovery:

* a complete XISO disc image: ``vc_53450030/0`` (the index volume) and the
  pack files are located in the XDVDFS tree, and span offsets are absolute
  image bytes;
* an extracted set: a directory holding the index volume ``0`` and whichever
  pack files are addressed; span offsets are pack-relative.

Safety is fail-closed throughout: the source image is opened read-only; a
target that IS the source (same path or same file) is refused; the PNG must
carry the slot's exact dimensions; the recompressed stream must fit inside the
retail stored size; the wrapper is preserved except for the loader scratch
word, which may only grow; and only the exact span is written, at the offset
re-derived from the target's own entry table.

Bump strength is data-driven (per-material detail-scale floats in the XBE
binding chain), not texture-driven, and is out of scope here.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
import argparse
import bisect
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
import zlib

_ROOT = Path(__file__).resolve().parents[2]
_TOOLS = _ROOT / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from nfl_all_texture_xiso_workflow import generate_mips  # noqa: E402
from nfl_tset_png_import import MAX_PNG_BYTES, decode_rgba_png  # noqa: E402
from nfl_txtr import (  # noqa: E402
    COMPRESSED_SENTINEL,
    HEADER,
    Chunk,
    TextureInfo,
    TxtrError,
    decode_chunk,
    encode_rgba_png,
    parse_chunks,
    parse_texture,
    rebuild_compressed_chunk_fixed_span,
    swizzle_2d,
    texture_to_rgba,
)
import nfl_uniform_color_xiso_direct_patch as xiso  # noqa: E402


CATALOG_SCHEMA = "nfl2k5_bump_texture_catalog/v1"
EXPORT_SCHEMA = "nfl2k5_bump_texture_export/v1"
IMPORT_SCHEMA = "nfl2k5_bump_texture_import/v1"
VERIFY_SCHEMA = "nfl2k5_bump_texture_verify/v1"
TEMPLATE_SCHEMA = "nfl2k5_bump_authoring_template/v1"

# Authoring zones observed on the retail bump_jersey art (A10 E4c).  The pixel
# boxes are A_PROVEN retail decode; the semantic labels are B_INFERENCE.
AUTHORING_ZONES: dict[str, tuple[dict[str, object], ...]] = {
    "bump_jersey": (
        {
            "label": "front V-neck collar band",
            "x": 120, "y": 0, "w": 96, "h": 96,
            "grade": "B_INFERENCE (A10 E4c)",
        },
        {
            "label": "NFL shield tab",
            "x": 155, "y": 75, "w": 21, "h": 21,
            "grade": "B_INFERENCE (A10 E4c)",
        },
        {
            "label": "back round collar",
            "x": 330, "y": 0, "w": 81, "h": 61,
            "grade": "B_INFERENCE (A10 E4c)",
        },
    ),
    "bump_pants": (),
    "bump_sleeve": (),
    "bump_sock": (),
}
TEMPLATE_FLAT_NORMAL = (128, 128, 255, 255)

SECTOR_SIZE = 0x800
INDEX_VOLUME = "0"
PACK_SLOT_COUNT = 36
INDEX_HEADER_SIZE = 0x0C + PACK_SLOT_COUNT * 4
ENTRY_STRIDE = 12
MAX_ENTRIES = 1_000_000
PACK_NAMES = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
PACK_B_ORDINAL = PACK_NAMES.index("B")
PACK_B_NAME = PACK_NAMES[PACK_B_ORDINAL]
INDEX_PACK_PATH = "vc_53450030/0"

BUMP_FORMAT_CODE = 0x06
BUMP_BYTES_PER_PIXEL = 4
BUMP_CHUNK_NAMES = ("bump_jersey", "bump_pants", "bump_sleeve", "bump_sock")
BUMP_SLOT_DIMENSIONS = {
    "bump_jersey": (512, 256),
    "bump_pants": (512, 256),
    "bump_sleeve": (128, 128),
    "bump_sock": (128, 128),
}
RETAIL_XISO_SHA256 = xiso.EXPECTED_XISO_SHA256
RETAIL_XISO_SIZE = xiso.EXPECTED_XISO_SIZE

# Retail identity pins for test fixtures ONLY. Discovery in catalog/export/
# import/verify always goes through the entry tables, never these constants.
RETAIL_FIXTURE_OUTER_INDEX = 4002
RETAIL_FIXTURE_CHUNK_INDEX = 45
RETAIL_FIXTURE_CHUNK_NAME = "bump_jersey"


class BumpTextureWriterError(ValueError):
    """Raised when a bump target, PNG, span, or write fails closed."""


ProgressSink = Callable[[str, int, int], None]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BumpTextureWriterError(message)


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _regular_non_link(path: Path) -> os.stat_result:
    info = path.lstat()
    _require(
        stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
        f"Not a regular, non-link file: {path}",
    )
    return info


@dataclass(frozen=True, slots=True)
class BumpChunkRecord:
    outer_index: int
    chunk_index: int
    name: str
    width: int
    height: int
    mip_levels: int
    format_code: int
    format_name: str
    packed_format: int
    system_bytes: int
    video_bytes: int
    stored_size: int
    span_size: int
    chunk_offset: int
    decoded_sha256: str
    span_sha256: str


@dataclass(frozen=True, slots=True)
class BumpPackageRecord:
    outer_index: int
    name_id: int
    logical_name: str
    pack_name: str
    size: int
    pack_offset: int
    chunk_count: int
    chunks: tuple[BumpChunkRecord, ...]
    cross_extent: bool = False


@dataclass(frozen=True, slots=True)
class _IndexEntry:
    table_index: int
    name_id: int
    size: int
    offset_blocks: int

    @property
    def virtual_offset(self) -> int:
        return self.offset_blocks * SECTOR_SIZE

    @property
    def virtual_end(self) -> int:
        return self.virtual_offset + self.size


@dataclass(frozen=True, slots=True)
class _IndexPack:
    entry_count: int
    pack_count: int
    slots: tuple[int, ...]
    pack_starts: tuple[int, ...]
    entries: tuple[_IndexEntry, ...]

    def owner_pack(self, virtual_offset: int) -> int:
        ordinal = bisect.bisect_right(self.pack_starts, virtual_offset) - 1
        if ordinal < 0:
            raise BumpTextureWriterError(
                f"virtual offset 0x{virtual_offset:x} precedes every pack"
            )
        return ordinal

    def pack_end(self, ordinal: int) -> int:
        return self.pack_starts[ordinal] + self.slots[ordinal] * SECTOR_SIZE

    def entry_extents(
        self, entry: "_IndexEntry"
    ) -> tuple[tuple[int, int, int], ...]:
        """(ordinal, pack offset, length) segments covering one entry.

        Entries are contiguous in the virtual space, so a cross-extent entry
        simply continues at offset zero of the next pack.  The bump writers
        support at most two segments (the retail maximum observed).
        """

        segments: list[tuple[int, int, int]] = []
        cursor = entry.virtual_offset
        end = entry.virtual_end
        while cursor < end:
            ordinal = self.owner_pack(cursor)
            _require(
                ordinal < self.pack_count,
                f"entry {entry.table_index} runs past the last pack",
            )
            limit = min(end, self.pack_end(ordinal))
            _require(
                limit > cursor,
                f"entry {entry.table_index} has an empty extent segment",
            )
            segments.append(
                (ordinal, cursor - self.pack_starts[ordinal], limit - cursor)
            )
            cursor = limit
        _require(
            len(segments) <= 2,
            f"entry {entry.table_index} spans {len(segments)} packs; "
            "only one boundary crossing is supported",
        )
        return tuple(segments)

    def sub_extents(
        self, entry: "_IndexEntry", start: int, size: int
    ) -> tuple[tuple[int, int, int], ...]:
        """Segments covering ``entry[start:start+size]`` in entry bytes."""

        _require(
            0 <= start and size >= 0 and start + size <= entry.size,
            f"entry sub-range 0x{start:x}+0x{size:x} exceeds the entry",
        )
        segments: list[tuple[int, int, int]] = []
        cursor = 0
        for ordinal, offset, length in self.entry_extents(entry):
            seg_start = max(start, cursor)
            seg_end = min(start + size, cursor + length)
            if seg_end > seg_start:
                segments.append(
                    (ordinal, offset + (seg_start - cursor),
                     seg_end - seg_start)
                )
            cursor += length
        return tuple(segments)


@dataclass(frozen=True, slots=True)
class _ResolvedBump:
    package: BumpPackageRecord
    pack_ordinal: int
    chunk: Chunk
    package_bytes: bytes
    span: bytes
    decoded: bytes
    texture: TextureInfo
    rgba: bytes
    absolute_span_offset: int | None
    span_segments: tuple[tuple[int, int, int], ...] = ()
    cross_extent: bool = False


_LOGICAL_NAME_CACHE: dict[int, str] | None = None


def logical_name_for(name_id: int) -> str | None:
    """The XBE 0x38650 name space: CRC32 of uppercased UTF-16LE ``NN[HA]NN.IFF``."""

    global _LOGICAL_NAME_CACHE
    if _LOGICAL_NAME_CACHE is None:
        names: dict[int, str] = {}
        for code in range(100):
            for side in ("H", "A"):
                for variant in range(100):
                    name = f"{code:02d}{side}{variant}.IFF"
                    candidate_id = (
                        zlib.crc32(name.upper().encode("utf-16le")) & 0xFFFFFFFF
                    )
                    _require(
                        candidate_id not in names,
                        f"logical-name candidate collision 0x{candidate_id:08x}",
                    )
                    names[candidate_id] = name
        _LOGICAL_NAME_CACHE = names
    return _LOGICAL_NAME_CACHE.get(name_id)


def _read_index_table(image: "_Image") -> bytes:
    """Only the entry table is layout: never materialize the whole volume."""

    head = image.read_index_range(0, INDEX_HEADER_SIZE)
    entry_count, reserved, pack_count = struct.unpack_from("<III", head, 0)
    _require(1 <= entry_count <= MAX_ENTRIES,
             f"implausible index entry count {entry_count}")
    _require(reserved == 0, f"index reserved field is 0x{reserved:08x}, not zero")
    _require(1 <= pack_count <= PACK_SLOT_COUNT,
             f"implausible index pack count {pack_count}")
    return image.read_index_range(
        0, INDEX_HEADER_SIZE + entry_count * ENTRY_STRIDE
    )


def _parse_index_pack(data: bytes) -> _IndexPack:
    _require(len(data) >= INDEX_HEADER_SIZE, "index volume is truncated")
    entry_count, reserved, pack_count = struct.unpack_from("<III", data, 0)
    _require(1 <= entry_count <= MAX_ENTRIES,
             f"implausible index entry count {entry_count}")
    _require(reserved == 0, f"index reserved field is 0x{reserved:08x}, not zero")
    _require(1 <= pack_count <= PACK_SLOT_COUNT,
             f"implausible index pack count {pack_count}")
    slots = struct.unpack_from(f"<{PACK_SLOT_COUNT}I", data, 0x0C)
    _require(all(blocks == 0 for blocks in slots[pack_count:]),
             "an unused index pack slot is nonzero")
    _require(any(blocks > 0 for blocks in slots[:pack_count]),
             "index declares no populated packs")
    _require(
        len(data) >= INDEX_HEADER_SIZE + entry_count * ENTRY_STRIDE,
        "index entry table is truncated",
    )
    entries: list[_IndexEntry] = []
    previous_end = 0
    seen_ids: set[int] = set()
    for table_index in range(entry_count):
        name_id, size, offset_blocks = struct.unpack_from(
            "<III", data, INDEX_HEADER_SIZE + table_index * ENTRY_STRIDE
        )
        _require(size > 0, f"entry {table_index} has zero size")
        _require(name_id not in seen_ids, f"duplicate entry ID 0x{name_id:08x}")
        seen_ids.add(name_id)
        entry = _IndexEntry(table_index, name_id, size, offset_blocks)
        _require(entry.virtual_offset >= previous_end,
                 f"entry {table_index} overlaps or is out of order")
        entries.append(entry)
        previous_end = entry.virtual_end
    pack_starts: list[int] = []
    virtual_start = 0
    for blocks in slots[:pack_count]:
        pack_starts.append(virtual_start)
        virtual_start += blocks * SECTOR_SIZE
    return _IndexPack(
        entry_count=entry_count,
        pack_count=pack_count,
        slots=slots,
        pack_starts=tuple(pack_starts),
        entries=tuple(entries),
    )


# Parsed index volumes are image-constant, but every catalog/list/export/
# import/verify call used to re-read and re-parse the entry table.  A bounded
# identity-keyed cache memoizes the parsed ``_IndexPack`` so N operations
# against the same image pay one parse.  The key is the index volume's own
# identity: for an extracted set the ``0`` file, for an XISO the image file
# plus the extent offset/size that locates the index volume inside it.  Any
# rewrite moves st_size or st_mtime_ns and misses the cache, so the fail-closed
# re-validation is unchanged.  Pack bytes are never cached: every span read
# still goes to the live image and is hash-checked downstream.
_INDEX_CACHE_LIMIT = 8
_INDEX_CACHE: "OrderedDict[tuple[object, ...], _IndexPack]" = OrderedDict()


def clear_index_cache() -> None:
    """Forget every memoized parsed index volume (tests and fresh sessions)."""

    _INDEX_CACHE.clear()


def _index_cache_key(image: "_Image") -> tuple[object, ...]:
    info = os.fstat(image._descriptor)
    if image.kind == "xiso":
        return (
            "xiso",
            str(image.path),
            info.st_dev,
            info.st_ino,
            info.st_size,
            info.st_mtime_ns,
            image.index_offset,
            image.index_size,
        )
    return (
        "extracted",
        str(image.path / INDEX_VOLUME),
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
    )


def _parsed_index(image: "_Image") -> _IndexPack:
    key = _index_cache_key(image)
    cached = _INDEX_CACHE.get(key)
    if cached is not None:
        _INDEX_CACHE.move_to_end(key)
        return cached
    index = _parse_index_pack(_read_index_table(image))
    _INDEX_CACHE[key] = index
    _INDEX_CACHE.move_to_end(key)
    while len(_INDEX_CACHE) > _INDEX_CACHE_LIMIT:
        _INDEX_CACHE.popitem(last=False)
    return index


def _entry_first_ordinal(index: _IndexPack, entry: _IndexEntry) -> int:
    """The pack ordinal holding the entry's first byte."""

    return index.owner_pack(entry.virtual_offset)


def _entry_crosses(index: _IndexPack, entry: _IndexEntry) -> bool:
    return len(index.entry_extents(entry)) > 1


def _uniform_entries(
    index: _IndexPack,
) -> list[tuple[_IndexEntry, int]]:
    """Uniform-named entries with the ordinal of their first pack."""

    result: list[tuple[_IndexEntry, int]] = []
    for entry in index.entries:
        if logical_name_for(entry.name_id) is None:
            continue
        result.append((entry, _entry_first_ordinal(index, entry)))
    return result


class _Image:
    """One opened disc image or extracted pack set, read-only or writable."""

    def __init__(
        self,
        path: Path,
        *,
        writable: bool,
        kind: str,
        descriptor: int,
        index_offset: int,
        index_size: int,
        xiso_entries: dict[str, object] | None = None,
        directory: Path | None = None,
    ) -> None:
        self.path = path
        self.writable = writable
        self.kind = kind
        self._descriptor = descriptor
        self._pack_fds: dict[int, int] = {}
        self._pack_paths: dict[int, Path] = {}
        self.index_offset = index_offset
        self.index_size = index_size
        self._xiso_entries = xiso_entries
        self._directory = directory

    @classmethod
    def open(cls, path: Path, *, writable: bool) -> "_Image":
        resolved = path.expanduser()
        _require(resolved.exists(), f"Missing image: {resolved}")
        _require(not resolved.is_symlink(), f"Refusing a symlink image: {resolved}")
        if resolved.is_dir():
            return cls._open_extracted(resolved, writable=writable)
        return cls._open_xiso(resolved, writable=writable)

    @classmethod
    def _open_extracted(cls, directory: Path, *, writable: bool) -> "_Image":
        index_path = directory / INDEX_VOLUME
        _require(index_path.is_file() and not index_path.is_symlink(),
                 f"Extracted image needs an index volume named '0': {directory}")
        _regular_non_link(index_path)
        descriptor = os.open(
            index_path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
        )
        try:
            index_size = os.fstat(descriptor).st_size
        except BaseException:
            os.close(descriptor)
            raise
        return cls(
            directory,
            writable=writable,
            kind="extracted",
            descriptor=descriptor,
            index_offset=0,
            index_size=index_size,
            directory=directory,
        )

    @classmethod
    def _open_xiso(cls, image_path: Path, *, writable: bool) -> "_Image":
        info = _regular_non_link(image_path)
        flags = os.O_RDWR if writable else os.O_RDONLY
        descriptor = os.open(
            image_path,
            flags | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_BINARY", 0),
        )
        try:
            opened = os.fstat(descriptor)
            _require(
                (opened.st_dev, opened.st_ino, opened.st_size)
                == (info.st_dev, info.st_ino, info.st_size),
                f"Image changed while opening: {image_path}",
            )
            try:
                entries, _directory = xiso.parse_xdvdfs(descriptor, opened.st_size)
            except xiso.PatchError as exc:
                raise BumpTextureWriterError(
                    f"Not a readable Xbox XDVDFS image: {image_path} ({exc})"
                ) from exc
            index_entry = entries.get(INDEX_PACK_PATH)
            _require(
                index_entry is not None,
                "Image lacks vc_53450030/0; it is not an NFL 2K5 disc image",
            )
            assert index_entry is not None
            _require(index_entry.size > 0, "vc_53450030 index extent is empty")
            return cls(
                image_path,
                writable=writable,
                kind="xiso",
                descriptor=descriptor,
                index_offset=index_entry.byte_offset,
                index_size=index_entry.size,
                xiso_entries=entries,
            )
        except BaseException:
            os.close(descriptor)
            raise

    def read_index_range(self, offset: int, size: int) -> bytes:
        _require(
            0 <= offset and size >= 0 and offset + size <= self.index_size,
            f"index volume range 0x{offset:x}+0x{size:x} exceeds the volume",
        )
        return xiso.read_exact(self._descriptor, self.index_offset + offset, size)

    def _pack_extent(self, ordinal: int):
        _require(self._xiso_entries is not None, "image carries no XDVDFS tree")
        name = PACK_NAMES[ordinal]
        entry = self._xiso_entries.get(f"vc_53450030/{name}".casefold())
        _require(
            entry is not None,
            f"image lacks the vc_53450030/{name} pack",
        )
        return entry

    def _extracted_pack_path(self, ordinal: int) -> Path:
        _require(self._directory is not None, "image carries no directory")
        path = self._directory / PACK_NAMES[ordinal]
        _require(
            path.is_file() and not path.is_symlink(),
            f"extracted image lacks the pack file '{PACK_NAMES[ordinal]}'",
        )
        return path

    def _pack_fd(self, ordinal: int) -> tuple[int, int]:
        """Return (descriptor, absolute byte base) for one pack."""

        if self.kind == "xiso":
            extent = self._pack_extent(ordinal)
            return self._descriptor, extent.byte_offset
        cached = self._pack_fds.get(ordinal)
        if cached is None:
            path = self._extracted_pack_path(ordinal)
            _regular_non_link(path)
            flags = os.O_RDWR if self.writable else os.O_RDONLY
            cached = os.open(
                path,
                flags | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
            )
            self._pack_fds[ordinal] = cached
            self._pack_paths[ordinal] = path
        return cached, 0

    def pack_size(self, ordinal: int) -> int:
        if self.kind == "xiso":
            return self._pack_extent(ordinal).size
        descriptor, _base = self._pack_fd(ordinal)
        return os.fstat(descriptor).st_size

    def read_pack(self, ordinal: int, offset: int, size: int) -> bytes:
        _require(offset >= 0 and size >= 0, "negative pack range")
        descriptor, base = self._pack_fd(ordinal)
        _require(
            offset + size <= self.pack_size(ordinal),
            f"pack {PACK_NAMES[ordinal]} range 0x{offset:x}+0x{size:x} "
            "exceeds the pack",
        )
        return xiso.read_exact(descriptor, base + offset, size)

    def write_pack(self, ordinal: int, offset: int, data: bytes) -> None:
        _require(self.writable, "image is read-only")
        _require(offset >= 0, "negative pack offset")
        descriptor, base = self._pack_fd(ordinal)
        _require(
            offset + len(data) <= self.pack_size(ordinal),
            f"pack {PACK_NAMES[ordinal]} write 0x{offset:x}+0x{len(data):x} "
            "exceeds the pack",
        )
        written = xiso.pwrite(descriptor, data, base + offset)
        _require(written == len(data), "short write on the replacement span")
        os.fsync(descriptor)

    def pack_absolute_base(self, ordinal: int) -> int:
        """Byte offset of this pack inside the image file (0 when extracted)."""

        if self.kind == "xiso":
            return self._pack_extent(ordinal).byte_offset
        return 0

    def read_segments(
        self, segments: Iterable[tuple[int, int, int]]
    ) -> bytes:
        """Concatenated reads of (ordinal, pack offset, length) segments."""

        parts = [
            self.read_pack(ordinal, offset, length)
            for ordinal, offset, length in segments
        ]
        return b"".join(parts)

    def write_segments(
        self, segments: Iterable[tuple[int, int, int]], data: bytes
    ) -> None:
        """Write ``data`` split across (ordinal, pack offset, length)."""

        total = sum(length for _ordinal, _offset, length in segments)
        _require(total == len(data),
                 "segment lengths do not match the write payload")
        position = 0
        for ordinal, offset, length in segments:
            self.write_pack(ordinal, offset, data[position : position + length])
            position += length

    def identity(self, ordinal: int) -> tuple[int, int]:
        descriptor, _base = self._pack_fd(ordinal)
        info = os.fstat(descriptor)
        return info.st_dev, info.st_ino

    def close(self) -> None:
        if self._descriptor >= 0:
            os.close(self._descriptor)
            self._descriptor = -1
        for descriptor in self._pack_fds.values():
            os.close(descriptor)
        self._pack_fds.clear()

    def __enter__(self) -> "_Image":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _entry_for(index: _IndexPack, outer_index: int) -> tuple[_IndexEntry, int]:
    _require(
        0 <= outer_index < len(index.entries),
        f"outer index {outer_index} is outside the entry table "
        f"(0..{len(index.entries) - 1})",
    )
    entry = index.entries[outer_index]
    _require(
        logical_name_for(entry.name_id) is not None,
        f"entry {outer_index} is not a uniform package",
    )
    return entry, _entry_first_ordinal(index, entry)


def _decompress_prefix(stream: bytes, expected_size: int, prefix: int) -> bytes:
    """The retail VC-LZ decoder stopped at ``prefix`` output bytes.

    Only the leading system buffer is needed to read a TXTR name, so the full
    body is never expanded for chunks that are not bump maps.
    """

    if len(stream) < 10:
        raise BumpTextureWriterError("compressed stream shorter than its prefix")
    output_size, _stream_tag = struct.unpack_from("<II", stream, 0)
    if output_size != expected_size:
        raise BumpTextureWriterError("stream/header output size mismatch")
    offset_bits = stream[8]
    if not 1 <= offset_bits <= 15:
        raise BumpTextureWriterError(f"invalid offset bit count {offset_bits}")
    distance_mask = (1 << offset_bits) - 1
    length_mask = (1 << (16 - offset_bits)) - 1
    limit = min(prefix, output_size)
    out = bytearray(limit)
    src = 9
    flags = stream[src]
    src += 1
    flag_mask = 1
    dst = 0
    while dst < limit:
        if flags & flag_mask:
            if src + 2 > len(stream):
                raise BumpTextureWriterError("truncated match token in prefix decode")
            code = struct.unpack_from("<H", stream, src)[0]
            src += 2
            distance = code & distance_mask
            length = ((code >> offset_bits) & length_mask) + 3
            if distance == 0 or distance > dst:
                raise BumpTextureWriterError(
                    "invalid match distance in prefix decode"
                )
            writable = min(length, limit - dst)
            for index in range(writable - 1, -1, -1):
                out[dst + index] = out[dst - distance + index]
            dst += length
        else:
            if src >= len(stream):
                raise BumpTextureWriterError("truncated literal in prefix decode")
            out[dst] = stream[src]
            src += 1
            dst += 1
        flag_mask = (flag_mask << 1) & 0xFF
        if flag_mask == 0 and dst < limit:
            if src >= len(stream):
                raise BumpTextureWriterError("missing flag byte in prefix decode")
            flags = stream[src]
            src += 1
            flag_mask = 1
    return bytes(out)


def _prefix_texture_name(decoded_prefix: bytes) -> str | None:
    if len(decoded_prefix) < 0x18 or decoded_prefix[0x0C:0x10] != b"TXTR":
        return None
    name_offset = struct.unpack_from("<I", decoded_prefix, 0x10)[0] + 0x0F
    descriptor_offset = struct.unpack_from("<I", decoded_prefix, 0x14)[0] + 0x13
    if not 0x18 <= name_offset < descriptor_offset:
        return None
    limit = min(descriptor_offset, len(decoded_prefix))
    for offset in range(name_offset, limit - 1, 2):
        if decoded_prefix[offset : offset + 2] == b"\0\0":
            try:
                return decoded_prefix[name_offset:offset].decode("utf-16le")
            except UnicodeDecodeError:
                return None
    return None


def _mip_chain_bytes(width: int, height: int, mip_levels: int) -> int:
    _require(mip_levels >= 1, "texture declares no mip levels")
    total = 0
    level_width, level_height = width, height
    for level in range(mip_levels):
        _require(level_width >= 1 and level_height >= 1,
                 "mip chain halved below one texel")
        total += level_width * level_height * BUMP_BYTES_PER_PIXEL
        if level + 1 < mip_levels:
            _require(level_width % 2 == 0 and level_height % 2 == 0,
                     f"{width}x{height} cannot be halved {mip_levels - 1} times")
            level_width //= 2
            level_height //= 2
    return total


def _validate_bump_descriptor(
    chunk: Chunk, texture: TextureInfo, *, slot_name: str | None = None
) -> None:
    name = texture.name
    _require(name in BUMP_CHUNK_NAMES, f"chunk is {name!r}, not a bump map")
    if slot_name is not None:
        _require(name == slot_name, f"chunk is {name!r}; expected {slot_name!r}")
    expected_dimensions = BUMP_SLOT_DIMENSIONS[name]
    _require(
        texture.format_code == BUMP_FORMAT_CODE
        and texture.dimensions == 2
        and texture.depth == 1
        and texture.packed_size == 0
        and texture.pixel_offset == 0,
        f"{name} is not the proved swizzled A8R8G8B8 bump descriptor",
    )
    _require(
        (texture.width, texture.height) == expected_dimensions,
        f"{name} is {texture.width}x{texture.height}; the slot requires "
        f"{expected_dimensions[0]}x{expected_dimensions[1]}",
    )
    _require(
        _mip_chain_bytes(texture.width, texture.height, texture.mip_levels)
        == chunk.video_bytes,
        f"{name} mip chain disagrees with the wrapper's video bytes",
    )


def _find_bump_chunks(
    package: bytes, *, strict: bool
) -> list[tuple[Chunk, bytes, TextureInfo]]:
    """Decode every TXTR name cheaply; fully decode only the bump family."""

    chunks = parse_chunks(package, allow_trailing=not strict)
    found: list[tuple[Chunk, bytes, TextureInfo]] = []
    seen_names: set[str] = set()
    for chunk in chunks:
        if chunk.kind != "TXTR" or not chunk.compressed:
            continue
        name: str | None = None
        try:
            prefix = _decompress_prefix(
                package[chunk.body_offset : chunk.end_offset],
                chunk.output_size,
                min(chunk.system_bytes, 256),
            )
            name = _prefix_texture_name(prefix)
        except BumpTextureWriterError:
            name = None
        if name not in BUMP_CHUNK_NAMES:
            continue
        decoded, info = decode_chunk(package, chunk)
        _require(info is not None, f"bump chunk {chunk.index} is not compressed")
        texture = parse_texture(decoded, chunk)
        _validate_bump_descriptor(chunk, texture)
        _require(texture.name not in seen_names,
                 f"package repeats bump chunk {texture.name!r}")
        seen_names.add(texture.name)
        found.append((chunk, decoded, texture))
    return found


def _package_detail(
    image: _Image, index: _IndexPack, entry: _IndexEntry, ordinal: int
) -> BumpPackageRecord:
    extents = index.entry_extents(entry)
    pack_offset = entry.virtual_offset - index.pack_starts[ordinal]
    package = image.read_segments(extents)
    _require(package[:4] == b"Unif",
             f"entry {entry.table_index} is not a Unif package")
    found = _find_bump_chunks(package, strict=True)
    chunks = tuple(
        sorted(
            (
                BumpChunkRecord(
                    outer_index=entry.table_index,
                    chunk_index=chunk.index,
                    name=texture.name,
                    width=texture.width,
                    height=texture.height,
                    mip_levels=texture.mip_levels,
                    format_code=texture.format_code,
                    format_name=texture.format_name,
                    packed_format=texture.packed_format,
                    system_bytes=chunk.system_bytes,
                    video_bytes=chunk.video_bytes,
                    stored_size=chunk.stored_size,
                    span_size=HEADER.size + chunk.stored_size,
                    chunk_offset=chunk.offset,
                    decoded_sha256=_digest(decoded),
                    span_sha256=_digest(package[chunk.offset : chunk.end_offset]),
                )
                for chunk, decoded, texture in found
            ),
            key=lambda record: record.chunk_index,
        )
    )
    return BumpPackageRecord(
        outer_index=entry.table_index,
        name_id=entry.name_id,
        logical_name=logical_name_for(entry.name_id) or "",
        pack_name=PACK_NAMES[ordinal],
        size=entry.size,
        pack_offset=pack_offset,
        chunk_count=len(parse_chunks(package, allow_trailing=True)),
        chunks=chunks,
        cross_extent=len(extents) > 1,
    )


def list_packages(disc_image_path: Path | str) -> list[dict[str, object]]:
    """Enumerate uniform packages from the entry table (no decode)."""

    with _Image.open(Path(disc_image_path), writable=False) as image:
        index = _parsed_index(image)
        return [
            {
                "outer_index": entry.table_index,
                "name_id": f"0x{entry.name_id:08x}",
                "logical_name": logical_name_for(entry.name_id) or "",
                "pack_name": PACK_NAMES[ordinal],
                "size": entry.size,
                "pack_offset": entry.virtual_offset
                - index.pack_starts[ordinal],
                "cross_extent": _entry_crosses(index, entry),
            }
            for entry, ordinal in _uniform_entries(index)
        ]


def package_bump_slots(
    disc_image_path: Path | str, outer_index: int
) -> dict[str, object]:
    """Fully decode the bump chunks of one package (read-only)."""

    with _Image.open(Path(disc_image_path), writable=False) as image:
        index = _parsed_index(image)
        entry, ordinal = _entry_for(index, outer_index)
        return asdict(_package_detail(image, index, entry, ordinal))


def catalog(
    disc_image_path: Path | str,
    *,
    progress: ProgressSink | None = None,
    outer_indices: Iterable[int] | None = None,
) -> dict[str, object]:
    """Enumerate uniform packages and their bump chunks (read-only)."""

    def report(stage: str, done: int, total: int) -> None:
        if progress is not None:
            progress(stage, done, total)

    with _Image.open(Path(disc_image_path), writable=False) as image:
        index = _parsed_index(image)
        pairs = _uniform_entries(index)
        if outer_indices is not None:
            wanted = {int(value) for value in outer_indices}
            pairs = [
                (entry, ordinal)
                for entry, ordinal in pairs
                if entry.table_index in wanted
            ]
        packages: list[dict[str, object]] = []
        skipped = 0
        total = len(pairs)
        for position, (entry, ordinal) in enumerate(pairs, 1):
            report("Scanning uniform packages", position, total)
            try:
                packages.append(
                    asdict(_package_detail(image, index, entry, ordinal))
                )
            except BumpTextureWriterError:
                skipped += 1
        return {
            "schema": CATALOG_SCHEMA,
            "image": {
                "path": str(Path(disc_image_path).expanduser()),
                "size": Path(disc_image_path).expanduser().stat().st_size,
            },
            "index": {
                "entry_count": index.entry_count,
                "pack_count": index.pack_count,
            },
            "package_count": len(packages),
            "skipped_package_count": skipped,
            "packages": packages,
        }


def _resolve_bump(
    image: _Image, outer_index: int, chunk_name: str
) -> tuple[_ResolvedBump, _IndexPack, _IndexEntry]:
    _require(chunk_name in BUMP_CHUNK_NAMES,
             f"{chunk_name!r} is not one of {', '.join(BUMP_CHUNK_NAMES)}")
    index = _parsed_index(image)
    entry, ordinal = _entry_for(index, outer_index)
    extents = index.entry_extents(entry)
    pack_offset = entry.virtual_offset - index.pack_starts[ordinal]
    package_bytes = image.read_segments(extents)
    _require(package_bytes[:4] == b"Unif",
             f"entry {entry.table_index} is not a Unif package")
    found = _find_bump_chunks(package_bytes, strict=True)
    match = [
        (chunk, decoded, texture)
        for chunk, decoded, texture in found
        if texture.name == chunk_name
    ]
    _require(len(match) == 1, f"entry {outer_index} has no {chunk_name!r} chunk")
    chunk, decoded, texture = match[0]
    record = BumpPackageRecord(
        outer_index=entry.table_index,
        name_id=entry.name_id,
        logical_name=logical_name_for(entry.name_id) or "",
        pack_name=PACK_NAMES[ordinal],
        size=entry.size,
        pack_offset=pack_offset,
        chunk_count=len(parse_chunks(package_bytes, allow_trailing=True)),
        chunks=(),
        cross_extent=len(extents) > 1,
    )
    span_extents = index.sub_extents(entry, chunk.offset,
                                     chunk.end_offset - chunk.offset)
    absolute_span_offset: int | None
    if len(span_extents) == 1:
        span_ordinal, span_pack_offset, _length = span_extents[0]
        absolute_span_offset = (
            image.pack_absolute_base(span_ordinal) + span_pack_offset
        )
    else:
        absolute_span_offset = None
    resolved = _ResolvedBump(
        package=record,
        pack_ordinal=ordinal,
        chunk=chunk,
        package_bytes=package_bytes,
        span=package_bytes[chunk.offset : chunk.end_offset],
        decoded=decoded,
        texture=texture,
        rgba=texture_to_rgba(decoded, chunk, texture),
        absolute_span_offset=absolute_span_offset,
        span_segments=span_extents,
        cross_extent=record.cross_extent,
    )
    return resolved, index, entry


def export_bump(
    disc_image_path: Path | str, outer_index: int, chunk_name: str
) -> tuple[bytes, dict[str, object]]:
    """Export one bump chunk's top mip as PNG bytes plus identity metadata."""

    with _Image.open(Path(disc_image_path), writable=False) as image:
        resolved, _index, _entry = _resolve_bump(image, outer_index, chunk_name)
    png = encode_rgba_png(resolved.texture.width, resolved.texture.height,
                          resolved.rgba)
    metadata = {
        "schema": EXPORT_SCHEMA,
        "outer_index": outer_index,
        "logical_name": resolved.package.logical_name,
        "pack_name": resolved.package.pack_name,
        "chunk_name": chunk_name,
        "chunk_index": resolved.chunk.index,
        "width": resolved.texture.width,
        "height": resolved.texture.height,
        "mip_levels": resolved.texture.mip_levels,
        "format": resolved.texture.format_name,
        "decoded_sha256": _digest(resolved.decoded),
        "rgba_sha256": _digest(resolved.rgba),
        "span_sha256": _digest(resolved.span),
        "span_size": len(resolved.span),
    }
    return png, metadata


def authoring_template(chunk_name: str) -> tuple[bytes, dict[str, object]]:
    """A flat-normal starter PNG with the retail collar/shield zones marked.

    The base is tangent-space flat (128,128,255), the neutral value that adds
    no bump.  Proven retail zone boxes (A10 E4c) are outlined so an artist can
    place shield/collar detail in the same UV positions the retail art uses.
    """

    _require(chunk_name in BUMP_CHUNK_NAMES,
             f"{chunk_name!r} is not one of {', '.join(BUMP_CHUNK_NAMES)}")
    from PIL import Image, ImageDraw  # noqa: PLC0415 (heavy import, deferred)

    width, height = BUMP_SLOT_DIMENSIONS[chunk_name]
    zones = AUTHORING_ZONES.get(chunk_name, ())
    image = Image.new("RGBA", (width, height), TEMPLATE_FLAT_NORMAL)
    draw = ImageDraw.Draw(image)
    zone_colors = ((255, 96, 64, 255), (64, 220, 120, 255), (96, 160, 255, 255))
    annotated = []
    for position, zone in enumerate(zones):
        color = zone_colors[position % len(zone_colors)]
        x, y, w, h = int(zone["x"]), int(zone["y"]), int(zone["w"]), int(zone["h"])
        for inset in range(2):
            draw.rectangle([x + inset, y + inset, x + w - 1 - inset,
                            y + h - 1 - inset], outline=color)
        label = str(zone["label"])
        text_y = y + h + 3 if y + h + 12 < height else max(0, y - 12)
        draw.text((x, text_y), label, fill=color)
        annotated.append({
            "label": label,
            "x": x, "y": y, "w": w, "h": h,
            "grade": zone.get("grade", "UNKNOWN"),
        })
    rgba = image.tobytes()
    png = encode_rgba_png(width, height, rgba)
    metadata = {
        "schema": TEMPLATE_SCHEMA,
        "chunk_name": chunk_name,
        "width": width,
        "height": height,
        "base": "tangent-space flat normal (128,128,255)",
        "zones": annotated,
        "note": (
            "Zone boxes are A10 E4c retail observations; labels are "
            "B_INFERENCE. Keep the import at these exact dimensions."
        ),
    }
    return png, metadata


def _read_authored_png(png_path: Path, width: int, height: int) -> bytes:
    resolved = png_path.expanduser().resolve(strict=True)
    info = _regular_non_link(resolved)
    _require(info.st_size <= MAX_PNG_BYTES, "PNG exceeds the 32 MiB file bound")
    payload = resolved.read_bytes()
    try:
        parsed_width, parsed_height, rgba = decode_rgba_png(payload, (width, height))
    except ValueError as exc:
        raise BumpTextureWriterError(
            f"PNG must be exactly {width}x{height} for this bump slot: {exc}"
        ) from exc
    _require(
        (parsed_width, parsed_height) == (width, height)
        and len(rgba) == width * height * 4,
        "PNG decode returned an unexpected shape",
    )
    return rgba


def _read_png_any_size(png_path: Path) -> bytes:
    resolved = png_path.expanduser().resolve(strict=True)
    info = _regular_non_link(resolved)
    _require(info.st_size <= MAX_PNG_BYTES, "PNG exceeds the 32 MiB file bound")
    payload = resolved.read_bytes()
    try:
        _width, _height, rgba = decode_rgba_png(payload, None)
    except ValueError as exc:
        raise BumpTextureWriterError(f"PNG could not be decoded: {exc}") from exc
    return rgba


def _build_replacement_span(
    resolved: _ResolvedBump, authored_rgba: bytes
) -> tuple[bytes, bytes, dict[str, object]]:
    """Rebuild the chunk's decoded body and recompress it into the fixed span."""

    chunk = resolved.chunk
    texture = resolved.texture
    try:
        levels = generate_mips(
            authored_rgba, texture.width, texture.height, texture.mip_levels
        )
    except ValueError as exc:
        raise BumpTextureWriterError(str(exc)) from exc
    chain = b"".join(
        swizzle_2d(level.rgba, level.width, level.height, BUMP_BYTES_PER_PIXEL)
        for level in levels
    )
    _require(
        len(chain) == chunk.video_bytes,
        "authored mip chain does not fill the retail video allocation",
    )
    rebuilt_decoded = resolved.decoded[: chunk.system_bytes] + chain
    _require(len(rebuilt_decoded) == len(resolved.decoded),
             "rebuilt decoded body changed size")
    try:
        rebuilt_span, rebuild_info = rebuild_compressed_chunk_fixed_span(
            resolved.span, rebuilt_decoded
        )
    except TxtrError as exc:
        raise BumpTextureWriterError(
            f"Authored bump map cannot fit the retail {chunk.stored_size:,}-byte "
            f"span: {exc}"
        ) from exc
    _require(len(rebuilt_span) == len(resolved.span), "span size changed")
    original_header = HEADER.unpack_from(resolved.span)
    rebuilt_header = HEADER.unpack_from(rebuilt_span)
    _require(
        original_header[:5] == rebuilt_header[:5]
        and original_header[6:] == rebuilt_header[6:],
        "wrapper words changed outside the scratch field",
    )
    _require(rebuilt_header[5] >= original_header[5],
             "overlap scratch word decreased")
    rebuilt_chunk = Chunk(
        index=chunk.index,
        offset=0,
        kind=chunk.kind,
        stored_size=chunk.stored_size,
        system_bytes=chunk.system_bytes,
        video_bytes=chunk.video_bytes,
        compression_magic=chunk.compression_magic,
        overlap_scratch_bytes=rebuilt_header[5],
        reserved0=0,
        reserved1=0,
    )
    redecoded, redecode_info = decode_chunk(rebuilt_span, rebuilt_chunk)
    _require(
        redecode_info is not None and redecoded == rebuilt_decoded,
        "rebuilt span failed its independent round-trip decode",
    )
    retexture = parse_texture(redecoded, rebuilt_chunk)
    _require(
        retexture.name == texture.name
        and retexture.width == texture.width
        and retexture.height == texture.height
        and retexture.mip_levels == texture.mip_levels
        and retexture.packed_format == texture.packed_format,
        "rebuilt descriptor identity changed",
    )
    _require(
        texture_to_rgba(redecoded, rebuilt_chunk, retexture) == authored_rgba,
        "rebuilt pixels differ from the authored pattern",
    )
    statistics = {
        "recompressed_bytes": rebuild_info.recompressed_bytes,
        "zero_padding_bytes": rebuild_info.zero_padding_bytes,
        "overlap_scratch_bytes_before": original_header[5],
        "overlap_scratch_bytes_after": rebuilt_header[5],
    }
    return rebuilt_span, rebuilt_decoded, statistics


def _refuse_same_file(source_path: Path, target_path: Path) -> None:
    source = source_path.expanduser()
    target = target_path.expanduser()
    _require(
        str(source.resolve()) != str(target.resolve()),
        "source and target are the same path; the target must be a copy",
    )
    source_info = source.lstat()
    target_info = target.lstat()
    _require(
        (source_info.st_dev, source_info.st_ino)
        != (target_info.st_dev, target_info.st_ino),
        "source and target are the same file; the target must be a copy",
    )


def _assert_layout_matches(
    source: _Image, target: _Image, ordinals: Iterable[int]
) -> None:
    for ordinal in sorted(set(ordinals)):
        _require(
            target.pack_size(ordinal) == source.pack_size(ordinal),
            f"target pack {PACK_NAMES[ordinal]} size differs from the "
            "source layout",
        )
    # The parse is pure validation of the source table; the memoized parse
    # already proved these exact bytes (same identity) when the source was
    # resolved.  The byte-for-byte comparison below still reads both tables
    # live, so a drifted target is refused exactly as before.
    _parsed_index(source)
    source_table = _read_index_table(source)
    target_table = target.read_index_range(0, len(source_table))
    _require(
        target_table == source_table,
        "target index entry table differs from the source; layouts disagree",
    )


def _assert_target_span_geometry(
    target: _Image,
    index: _IndexPack,
    entry: _IndexEntry,
    resolved: _ResolvedBump,
) -> None:
    chunk = resolved.chunk
    span_segments = index.sub_extents(
        entry, chunk.offset, chunk.end_offset - chunk.offset
    )
    current = target.read_segments(span_segments)
    _require(len(current) == len(resolved.span), "target span size differs")
    source_fields = HEADER.unpack_from(resolved.span)
    target_fields = HEADER.unpack_from(current)
    _require(
        target_fields[:5] == source_fields[:5]
        and target_fields[4] == COMPRESSED_SENTINEL,
        "target span wrapper geometry differs from the source span",
    )


def import_bump(
    source_path: Path | str,
    target_path: Path | str,
    outer_index: int,
    chunk_name: str,
    png_path: Path | str,
) -> dict[str, object]:
    """Replace one bump chunk in a copy, writing only the exact retail span."""

    source = Path(source_path)
    target = Path(target_path)
    _refuse_same_file(source, target)
    with _Image.open(source, writable=False) as source_image:
        resolved, index, entry = _resolve_bump(source_image, outer_index,
                                               chunk_name)
        _validate_bump_descriptor(
            resolved.chunk, resolved.texture, slot_name=chunk_name
        )
        authored_rgba = _read_authored_png(
            Path(png_path), resolved.texture.width, resolved.texture.height
        )
        rebuilt_span, rebuilt_decoded, statistics = _build_replacement_span(
            resolved, authored_rgba
        )
        changed_byte_count = sum(
            1 for a, b in zip(resolved.span, rebuilt_span) if a != b
        )
        _require(changed_byte_count > 0, "replacement equals the retail span")
        with _Image.open(target, writable=True) as target_image:
            extent_ordinals = {
                ordinal for ordinal, _offset, _length in resolved.span_segments
            }
            for ordinal in sorted(extent_ordinals):
                _require(
                    source_image.identity(ordinal)
                    != target_image.identity(ordinal),
                    "source and target resolve to the same file; the target "
                    "must be a copy",
                )
            _assert_layout_matches(source_image, target_image, extent_ordinals)
            _assert_target_span_geometry(target_image, index, entry, resolved)
            target_image.write_segments(resolved.span_segments, rebuilt_span)
            readback = target_image.read_segments(resolved.span_segments)
            _require(
                readback == rebuilt_span,
                "post-write readback does not match the replacement span",
            )
            span_extent_rows = [
                {
                    "pack_name": PACK_NAMES[ordinal],
                    "pack_offset": offset,
                    "size": length,
                    "absolute_offset": (
                        target_image.pack_absolute_base(ordinal) + offset
                    ),
                }
                for ordinal, offset, length in resolved.span_segments
            ]
            target_absolute = (
                span_extent_rows[0]["absolute_offset"]
                if len(span_extent_rows) == 1
                else None
            )
            target_kind = target_image.kind
    return {
        "schema": IMPORT_SCHEMA,
        "source": {"path": str(source.expanduser()), "kind": source_image.kind},
        "target": {
            "path": str(target.expanduser()),
            "kind": target_kind,
            "pack_name": resolved.package.pack_name,
            "pack_byte_offset_in_image": (
                target_absolute - span_extent_rows[0]["pack_offset"]
                if len(span_extent_rows) == 1
                else None
            ),
            "outer_pack_rel_offset": resolved.package.pack_offset,
            "chunk_offset_in_outer": resolved.chunk.offset,
            "pack_relative_span_offset": (
                span_extent_rows[0]["pack_offset"]
                if len(span_extent_rows) == 1
                else None
            ),
            "absolute_span_offset": target_absolute,
            "span_extents": span_extent_rows,
            "cross_extent": resolved.cross_extent,
            "span_size": len(rebuilt_span),
        },
        "outer_index": outer_index,
        "logical_name": resolved.package.logical_name,
        "chunk_name": chunk_name,
        "chunk_index": resolved.chunk.index,
        "retail_span_sha256": _digest(resolved.span),
        "replacement_span_sha256": _digest(rebuilt_span),
        "decoded_sha256": _digest(rebuilt_decoded),
        "authored_rgba_sha256": _digest(authored_rgba),
        "changed_byte_count": changed_byte_count,
        "wrapper_preserved_except_scratch": True,
        "post_write_readback_matches": True,
        "statistics": statistics,
    }


def preview_import(
    disc_image_path: Path | str,
    outer_index: int,
    chunk_name: str,
    png_path: Path | str,
) -> dict[str, object]:
    """Before/after preview payloads for an import that has not been written."""

    with _Image.open(Path(disc_image_path), writable=False) as image:
        resolved, _index, _entry = _resolve_bump(image, outer_index, chunk_name)
        _validate_bump_descriptor(
            resolved.chunk, resolved.texture, slot_name=chunk_name
        )
        authored_rgba = _read_authored_png(
            Path(png_path), resolved.texture.width, resolved.texture.height
        )
    return {
        "outer_index": outer_index,
        "chunk_name": chunk_name,
        "width": resolved.texture.width,
        "height": resolved.texture.height,
        "retail_png": encode_rgba_png(
            resolved.texture.width, resolved.texture.height, resolved.rgba
        ),
        "authored_png": encode_rgba_png(
            resolved.texture.width, resolved.texture.height, authored_rgba
        ),
        "retail_rgba": resolved.rgba,
        "authored_rgba": authored_rgba,
        "retail_rgba_sha256": _digest(resolved.rgba),
        "authored_rgba_sha256": _digest(authored_rgba),
    }


def verify_write(
    target_path: Path | str,
    outer_index: int,
    chunk_name: str,
    expected_top_rgba: bytes,
) -> dict[str, object]:
    """Independently re-decode the span from the target and compare pixels."""

    with _Image.open(Path(target_path), writable=False) as image:
        resolved, _index, _entry = _resolve_bump(image, outer_index, chunk_name)
    texture = resolved.texture
    checks = {
        "chunk_name": texture.name == chunk_name,
        "format_code": texture.format_code == BUMP_FORMAT_CODE,
        "dimensions": (texture.width, texture.height)
        == BUMP_SLOT_DIMENSIONS.get(chunk_name, (-1, -1)),
        "pixels_equal": resolved.rgba == expected_top_rgba,
    }
    return {
        "schema": VERIFY_SCHEMA,
        "outer_index": outer_index,
        "chunk_name": chunk_name,
        "chunk_index": resolved.chunk.index,
        "width": texture.width,
        "height": texture.height,
        "mip_levels": texture.mip_levels,
        "decoded_sha256": _digest(resolved.decoded),
        "rgba_sha256": _digest(resolved.rgba),
        "span_sha256": _digest(resolved.span),
        "absolute_span_offset": resolved.absolute_span_offset,
        "checks": checks,
        "ok": all(checks.values()),
    }


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Catalog, export, import, and verify NFL 2K5 uniform bump maps. "
            "Images may be XISO disc images or extracted directories holding "
            "the index volume '0' and the addressed pack files."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    list_parser = commands.add_parser("list", help="catalog bump chunks")
    list_parser.add_argument("image", type=Path)
    list_parser.add_argument("--outer", type=int, action="append", default=None)
    list_parser.add_argument("--json", action="store_true")

    packages_parser = commands.add_parser(
        "packages", help="list uniform packages without decoding"
    )
    packages_parser.add_argument("image", type=Path)

    export_parser = commands.add_parser("export", help="export one bump chunk")
    export_parser.add_argument("image", type=Path)
    export_parser.add_argument("outer_index", type=int)
    export_parser.add_argument("--chunk", required=True, choices=BUMP_CHUNK_NAMES)
    export_parser.add_argument("--output", type=Path, required=True)

    import_parser = commands.add_parser(
        "import", help="import a PNG into a copy of the image"
    )
    import_parser.add_argument("source", type=Path)
    import_parser.add_argument("target", type=Path)
    import_parser.add_argument("outer_index", type=int)
    import_parser.add_argument("--chunk", required=True, choices=BUMP_CHUNK_NAMES)
    import_parser.add_argument("--png", type=Path, required=True)
    import_parser.add_argument("--evidence", type=Path, default=None)

    verify_parser = commands.add_parser(
        "verify", help="re-decode a written span and compare it to a PNG"
    )
    verify_parser.add_argument("target", type=Path)
    verify_parser.add_argument("outer_index", type=int)
    verify_parser.add_argument("--chunk", required=True, choices=BUMP_CHUNK_NAMES)
    verify_parser.add_argument("--png", type=Path, required=True)

    template_parser = commands.add_parser(
        "template", help="write a flat-normal authoring template PNG"
    )
    template_parser.add_argument("--chunk", required=True,
                                 choices=BUMP_CHUNK_NAMES)
    template_parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _argument_parser().parse_args(argv)
    if args.command == "list":
        result = catalog(args.image, outer_indices=args.outer)
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(
                f"{result['package_count']} uniform package(s) with bump chunks"
            )
            for package in result["packages"]:
                names = ", ".join(
                    f"{chunk['chunk_index']}:{chunk['name']}"
                    for chunk in package["chunks"]
                )
                print(
                    f"outer {package['outer_index']} "
                    f"{package['logical_name'] or package['name_id']} "
                    f"(pack {package['pack_name']}): {names}"
                )
        return 0
    if args.command == "packages":
        for row in list_packages(args.image):
            print(
                f"{row['outer_index']}\t{row['logical_name']}\t"
                f"{row['name_id']}\t{row['pack_name']}\t{row['size']}"
            )
        return 0
    if args.command == "export":
        png, metadata = export_bump(args.image, args.outer_index, args.chunk)
        output = args.output.expanduser()
        _require(not output.exists(), f"output already exists: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(png)
        print(json.dumps(metadata, indent=2, sort_keys=True))
        return 0
    if args.command == "import":
        evidence = import_bump(
            args.source, args.target, args.outer_index, args.chunk, args.png
        )
        if args.evidence is not None:
            receipt = args.evidence.expanduser()
            _require(not receipt.exists(), f"receipt already exists: {receipt}")
            receipt.parent.mkdir(parents=True, exist_ok=True)
            receipt.write_bytes(
                (json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode(
                    "utf-8"
                )
            )
        print(json.dumps(evidence, indent=2, sort_keys=True))
        return 0
    if args.command == "verify":
        rgba = _read_png_any_size(args.png)
        result = verify_write(args.target, args.outer_index, args.chunk, rgba)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["ok"] else 1
    if args.command == "template":
        png, metadata = authoring_template(args.chunk)
        output = args.output.expanduser()
        _require(not output.exists(), f"output already exists: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(png)
        print(json.dumps(metadata, indent=2, sort_keys=True))
        return 0
    raise BumpTextureWriterError(f"unknown command {args.command!r}")


__all__ = [
    "AUTHORING_ZONES",
    "BUMP_CHUNK_NAMES",
    "BUMP_SLOT_DIMENSIONS",
    "BumpChunkRecord",
    "BumpPackageRecord",
    "BumpTextureWriterError",
    "CATALOG_SCHEMA",
    "IMPORT_SCHEMA",
    "RETAIL_FIXTURE_CHUNK_INDEX",
    "RETAIL_FIXTURE_CHUNK_NAME",
    "RETAIL_FIXTURE_OUTER_INDEX",
    "RETAIL_XISO_SHA256",
    "RETAIL_XISO_SIZE",
    "TEMPLATE_SCHEMA",
    "VERIFY_SCHEMA",
    "authoring_template",
    "catalog",
    "clear_index_cache",
    "export_bump",
    "import_bump",
    "list_packages",
    "logical_name_for",
    "package_bump_slots",
    "preview_import",
    "verify_write",
]


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BumpTextureWriterError, OSError) as exc:
        raise SystemExit(f"error: {exc}") from exc

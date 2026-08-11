#!/usr/bin/env python3
"""Safely replace one team's logo textures inside the APF 2K8 ``uniform_logocache``.

``uniform_logocache`` is a prebuilt, on-disc, runtime-resident aggregate of the
same 236 team-logo textures the ``uniform_logo_NN.iff`` packages hold (each
catalog index N contributes ``N_logo_l0`` and ``N_logo_l1``, Xenos ``4_4_4_4``,
512x512, packed mips).  It is a DIRECTORY + PAYLOAD pair inside the ``0A`` volume:

* outer entry 171 ``uniform_logocache.iff`` (40,960 B, magic ``F0985030``) is the
  directory: a fixed header, 236 file descriptors (aggregate DRAM/VRAM slots), 236
  auxiliary records (``[stream_a, len_a, stream_b, len_b]`` byte offsets into the
  payload), the internal name ``uniform_logocache.cdf`` and an ``AA171516`` name
  footer whose per-name CRC32 equals each descriptor's file id;
* outer entry 213 ``uniform_logocache.cdf`` (10,356,736 B = ``0x9E0800``) is the
  payload: 236 contiguous ``[H7A(DRAM 0xE0)][H7A(VRAM 0xAC000)]`` sub-block pairs
  (total ``0x9E04A6``, zero-padded to the fixed outer allocation), each part an
  independent H7A block (its own ``shift``; the DRAM part is always ``0x71`` B).

The decompressed VRAM sub-blocks are byte-identical to the package logo layers
(proven: cache ``01_logo_l0`` VRAM base hash equals the pinned package
``EXPECTED_BASE_SHA256``).  This writer rewrites the base level(s) of one catalog
index inside a COPY of the volume and regenerates that entry's packed mip tail
from the new base -- byte-preserving the tail leaves the RETAIL crest in every
level below mip 0, so a modded crest still showed the old logo on any surface
that drew it small.  It byte-preserves every DRAM part and every other catalog
entry, updates only the affected auxiliary records, recompresses each edited VRAM part once (with that part's original H7A
shift), and fails closed if the repacked payload would exceed its fixed
``0x9E0800`` allocation.  The retail source is never opened for writing, and the
copied volume is byte-diffed against the source so only the two fixed extents
change.  An independent verifier (``tools/apf_logocache_verify.py``) reproves this
with its own ``F0985030``/H7A parse.

Whether a given runtime surface (frontend team-select grid, in-game scorebug,
helmet crest) samples the cache aggregate or a freshly package-loaded texture is
NOT statically recoverable; that is the package-vs-cache-vs-both Xenia
differential (see the build plan).  This writer only proves the exact bytes it
changes and makes no in-game claim without a Xenia capture.

The transport (``encode_4444_base``/``decode_4444_base``), the greedy H7A encoder,
and the copy-only output-safety primitives are imported from ``apf_logo_patch``
rather than duplicated; the strict ``F0985030`` directory parse is self-contained
and gated by pinned exact-retail directory and payload hashes.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
import struct
import sys
import zlib

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from mod_editor.core import platform_compat  # noqa: E402

try:
    from PIL import __version__ as PILLOW_VERSION
except ImportError as exc:  # pragma: no cover - exercised by the CLI error path.
    raise SystemExit("error: Pillow is required for PNG import") from exc

import apf_inner  # noqa: E402
import apf_outer  # noqa: E402

# Reuse the proven, non-duplicated machinery from the package logo writer.
from apf_logo_patch import (  # noqa: E402
    BASE_LEN,
    MIP_LEN,
    cleared_detail_rgba,
    rebuild_mip_tail,
    OutputReservation,
    PatchError,
    _abort_reserved,
    _commit_reserved,
    _close_reserved,
    _copy_fd_metadata,
    _fd_identity,
    _load_png,
    _path_is_owned_inode,
    _pread_exact,
    _preflight_output_paths,
    _pwrite_all,
    _reserve_new,
    _sha256_fd,
    _sha256_fd_range,
    _strict_descriptor,
    _unlink_owned_path,
    _write_new,
    compress_h7a,
    decode_4444_base,
    encode_4444_base,
    sha256_bytes,
)


SCHEMA = "apf_logocache_patch/v1"

# --- Outer directory entry (uniform_logocache.iff, F0985030) ---
DIR_TABLE_INDEX = 171
DIR_NAME = "uniform_logocache.iff"
DIR_NAME_ID = 0x1C247977
DIR_SIZE = 0xA000  # 40,960 B, fixed outer allocation
DIR_PACK_OFFSET = 53221376
DIR_MAGIC = 0xF0985030
DIR_HEADER_SIZE = 0x2924
DIR_INTERNAL_NAME = "uniform_logocache.cdf"

# --- Outer payload entry (uniform_logocache.cdf) ---
PAYLOAD_TABLE_INDEX = 213
PAYLOAD_NAME = "uniform_logocache.cdf"
PAYLOAD_NAME_ID = 0x23859E23  # CRC32("UNIFORM_LOGOCACHE.CDF")
PAYLOAD_SIZE = 0x9E0800  # 10,356,736 B, fixed outer allocation
PAYLOAD_PACK_OFFSET = 1039226880

# --- Catalog / block invariants ---
FILE_COUNT = 236
CATALOG_COUNT = 118
DRAM_STRIDE = 0xE0
VRAM_STRIDE = 0xAC000
AUX_LEN_A = 0x71  # every DRAM part stores in exactly 0x71 B
TXTR_TYPE_HASH = 0x5C369069
NAME_FOOTER_MAGIC = apf_inner.NAME_FOOTER_MAGIC
H7A_MAGIC = apf_inner.H7A_MAGIC
H7A_HEADER_SIZE = apf_inner.H7A_HEADER_SIZE  # 0x14

# Exact-retail gate: this writer only operates on the pinned retail cache pair.
EXPECTED_DIR_SHA256 = (
    "3ddd89aabd6ba3b39ef9b1571ef8a9f1d3009baefd43aaa61c066a45d0ef09e5"
)
EXPECTED_PAYLOAD_SHA256 = (
    "572111c49e32dc341a1111ac7f420b3fa4396fff8fe0db3c965fbfccd98d7982"
)

_PORTME = [
    "validate this changed copied volume in Xenia and on user-owned hardware "
    "before describing any in-game/runtime effect as proved",
    "the package-only / cache-only / both Xenia differential identifies, per "
    "surface (frontend team-select grid, in-game scorebug, on-field helmet crest), "
    "whether the live source is the uniform_logo package or this cache aggregate",
    "the greedy H7A encoder does not reproduce retail compressed bytes; edited "
    "VRAM parts are proved by round-trip (decompress==intended) + fixed-allocation "
    "fail-closed, not by matching retail's compressor output",
]


# ---------------------------------------------------------------------------
# Self-contained strict F0985030 directory parse.  Mirrors the field validations
# of tools/apf_uniform_inventory.py::_parse_logo_cache (lines ~443-569) and is
# gated by the pinned exact-retail directory hash, so it operates only on bytes
# proven identical to retail.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CacheEntry:
    index: int  # descriptor / stream / footer-name index (0..235)
    name: str  # e.g. "01_logo_l0"
    catalog_index: int
    level: int  # 0 or 1
    file_id: int
    descriptor_offset: int
    aggregate_slot: int
    aggregate_dram_offset: int
    aggregate_vram_offset: int
    aux_offset: int
    stream_a: int
    len_a: int
    stream_b: int
    len_b: int


@dataclass(frozen=True)
class CacheDirectory:
    header_size: int
    file_length: int
    entries: tuple[CacheEntry, ...]
    total_stream_length: int  # end of the last sub-block (== 0x9E04A6 at retail)
    footer_offset: int
    footer_total: int


def _crc32(text: str) -> int:
    return zlib.crc32(text.encode("ascii")) & 0xFFFFFFFF


def parse_cache_directory(raw: bytes) -> CacheDirectory:
    """Strictly parse the F0985030 directory; reject any structural deviation."""

    if len(raw) != DIR_SIZE:
        raise PatchError(f"logo cache directory is 0x{len(raw):x}, expected 0x{DIR_SIZE:x}")
    if len(raw) < 0x28:
        raise PatchError("logo cache directory is shorter than its custom header")
    (
        magic,
        header_size,
        file_length,
        zero,
        block_count,
        block_pointer,
        file_count,
        file_pointer,
        auxiliary_pointer,
        cache_name_pointer,
    ) = struct.unpack_from(">10I", raw, 0)
    if magic != DIR_MAGIC:
        raise PatchError(f"logo cache magic is 0x{magic:08x}, expected F0985030")
    if header_size != file_length or header_size != DIR_HEADER_SIZE or zero != 0:
        raise PatchError("logo cache header/file length or zero field changed")
    if block_count != 2 or file_count != FILE_COUNT:
        raise PatchError("logo cache does not contain two virtual blocks and 236 files")

    block_table = 0x14 + block_pointer - 1
    file_pointer_table = 0x1C + file_pointer - 1
    auxiliary_pointer_table = 0x20 + auxiliary_pointer - 1
    cache_name_offset = 0x24 + cache_name_pointer - 1
    if block_table != 0x28 or file_pointer_table != 0x68:
        raise PatchError("logo cache block/file pointer tables moved")
    if auxiliary_pointer_table != 0x1688 or cache_name_offset != 0x28F8:
        raise PatchError("logo cache auxiliary/name targets moved")

    strides = []
    type_hashes = []
    for block_index in range(block_count):
        values = struct.unpack_from(">8I", raw, block_table + block_index * 0x20)
        type_hashes.append(values[1])
        strides.append(values[3])
    if strides != [DRAM_STRIDE, VRAM_STRIDE]:
        raise PatchError("logo cache virtual block strides changed")
    if type_hashes != [0xBB05A9C1, 0x411536D5]:
        raise PatchError("logo cache virtual blocks are not DRAM/VRAM")

    descriptor_start = file_pointer_table + file_count * 4
    descriptor_cursor = descriptor_start
    descriptors: list[tuple[int, int, int, int]] = []  # (offset, file_id, dram_off, vram_off)
    for index in range(file_count):
        pointer_field = file_pointer_table + index * 4
        descriptor = pointer_field + struct.unpack_from(">I", raw, pointer_field)[0] - 1
        if descriptor != descriptor_cursor:
            raise PatchError(f"logo cache file descriptor {index} is not packed")
        file_id, type_hash, offset_count, dram_offset, vram_offset = struct.unpack_from(
            ">5I", raw, descriptor
        )
        if type_hash != TXTR_TYPE_HASH or offset_count != 2:
            raise PatchError(f"logo cache file descriptor {index} is not TXTR/2-part")
        if dram_offset % DRAM_STRIDE or vram_offset % VRAM_STRIDE:
            raise PatchError(f"logo cache file descriptor {index} has unaligned offsets")
        if dram_offset // DRAM_STRIDE != vram_offset // VRAM_STRIDE:
            raise PatchError(f"logo cache file descriptor {index} block slots disagree")
        descriptors.append((descriptor, file_id, dram_offset, vram_offset))
        descriptor_cursor += 0x14
    if descriptor_cursor != auxiliary_pointer_table:
        raise PatchError("logo cache file descriptors do not end at auxiliary table")
    if {dram // DRAM_STRIDE for _, _, dram, _ in descriptors} != set(range(file_count)):
        raise PatchError("logo cache aggregate slots are not a 0..235 permutation")

    auxiliary_start = auxiliary_pointer_table + file_count * 4
    auxiliary_cursor = auxiliary_start
    auxiliary: list[tuple[int, int, int, int, int]] = []  # (offset, sa, la, sb, lb)
    previous_end = 0
    for index in range(file_count):
        pointer_field = auxiliary_pointer_table + index * 4
        descriptor = pointer_field + struct.unpack_from(">I", raw, pointer_field)[0] - 1
        if descriptor != auxiliary_cursor:
            raise PatchError(f"logo cache auxiliary descriptor {index} is not packed")
        stream_a, length_a, stream_b, length_b = struct.unpack_from(">4I", raw, descriptor)
        if stream_a != previous_end or stream_b != stream_a + length_a:
            raise PatchError(f"logo cache auxiliary stream {index} is not contiguous")
        if length_a != AUX_LEN_A:
            raise PatchError(f"logo cache auxiliary DRAM length {index} is not 0x71")
        previous_end = stream_b + length_b
        auxiliary.append((descriptor, stream_a, length_a, stream_b, length_b))
        auxiliary_cursor += 0x10
    if auxiliary_cursor != cache_name_offset:
        raise PatchError("logo cache auxiliary descriptors do not end at cache name")

    name_end = cache_name_offset
    while name_end + 1 < len(raw) and raw[name_end : name_end + 2] != b"\0\0":
        name_end += 2
    try:
        cache_name = raw[cache_name_offset:name_end].decode("utf-16be")
    except UnicodeDecodeError as exc:
        raise PatchError("logo cache internal name is not valid UTF-16BE") from exc
    if cache_name != DIR_INTERNAL_NAME or name_end + 2 != header_size:
        raise PatchError("logo cache internal CDF name does not end at header boundary")

    if file_length + 8 > len(raw):
        raise PatchError("logo cache has no name footer")
    footer_magic = struct.unpack_from(">I", raw, file_length)[0]
    footer_size = struct.unpack_from("<I", raw, file_length + 4)[0]
    if footer_magic != NAME_FOOTER_MAGIC:
        raise PatchError("logo cache name footer magic changed")
    footer_end = file_length + 8 + footer_size
    if footer_end > len(raw):
        raise PatchError("logo cache name footer extends outside the outer entry")
    names = apf_inner._parse_footer_names(  # type: ignore[attr-defined]
        raw[file_length + 8 : footer_end], file_count
    )
    expected_names = {
        (f"{catalog:02d}_logo_l{level}", "TXTR")
        for catalog in range(CATALOG_COUNT)
        for level in range(2)
    }
    if set(names) != expected_names or len(set(names)) != file_count:
        raise PatchError("logo cache footer is not the exact 118 x 2 logo catalog")
    if any(raw[footer_end:]):
        raise PatchError("logo cache alignment tail contains nonzero bytes")

    entries: list[CacheEntry] = []
    for index in range(file_count):
        name, type_name = names[index]
        descriptor_offset, file_id, dram_offset, vram_offset = descriptors[index]
        aux_offset, stream_a, length_a, stream_b, length_b = auxiliary[index]
        if file_id != _crc32(name) or type_name != "TXTR":
            raise PatchError(f"logo cache file {index} id/type does not match {name}")
        if "_logo_l" not in name:
            raise PatchError(f"logo cache filename {name!r} has unknown syntax")
        index_text, level_text = name.split("_logo_l", 1)
        if not index_text.isdigit() or level_text not in ("0", "1"):
            raise PatchError(f"logo cache filename {name!r} has unknown syntax")
        entries.append(
            CacheEntry(
                index=index,
                name=name,
                catalog_index=int(index_text),
                level=int(level_text),
                file_id=file_id,
                descriptor_offset=descriptor_offset,
                aggregate_slot=dram_offset // DRAM_STRIDE,
                aggregate_dram_offset=dram_offset,
                aggregate_vram_offset=vram_offset,
                aux_offset=aux_offset,
                stream_a=stream_a,
                len_a=length_a,
                stream_b=stream_b,
                len_b=length_b,
            )
        )
    return CacheDirectory(
        header_size=header_size,
        file_length=file_length,
        entries=tuple(entries),
        total_stream_length=previous_end,
        footer_offset=file_length,
        footer_total=8 + footer_size,
    )


# ---------------------------------------------------------------------------
# H7A sub-block helpers (payload part A / part B).
# ---------------------------------------------------------------------------
def _decompress_part(stored: bytes, expected_len: int, what: str) -> tuple[bytes, int, int]:
    """Decompress one payload sub-block; return (bytes, shift, unknown_codec)."""

    if len(stored) < H7A_HEADER_SIZE:
        raise PatchError(f"{what} is shorter than its 0x14-byte H7A wrapper")
    magic, uncompressed, compressed, unknown, shift = struct.unpack_from(">5I", stored, 0)
    if magic != H7A_MAGIC:
        raise PatchError(f"{what} has bad H7A magic 0x{magic:08x}")
    if uncompressed != expected_len:
        raise PatchError(
            f"{what} declares 0x{uncompressed:x} bytes, expected 0x{expected_len:x}"
        )
    if compressed != len(stored):
        raise PatchError(f"{what} wrapper length disagrees with the stored sub-block")
    if not 1 <= shift <= 15:
        raise PatchError(f"{what} has invalid H7A shift {shift}")
    body = stored[H7A_HEADER_SIZE:]
    decoded = apf_inner.decompress_h7a(body, uncompressed, shift)
    if len(decoded) != expected_len:
        raise PatchError(f"{what} decoded to 0x{len(decoded):x}, expected 0x{expected_len:x}")
    return decoded, shift, unknown


def _compress_part(vram: bytes, shift: int, unknown: int, what: str) -> bytes:
    """Re-compress an edited VRAM sub-block, preserving the block's H7A shift."""

    if len(vram) != VRAM_STRIDE:
        raise PatchError(f"{what} is 0x{len(vram):x}, expected 0x{VRAM_STRIDE:x}")
    body = compress_h7a(vram, shift)
    stored = struct.pack(
        ">5I", H7A_MAGIC, len(vram), H7A_HEADER_SIZE + len(body), unknown, shift
    ) + body
    if apf_inner.decompress_h7a(body, len(vram), shift) != vram:
        raise PatchError(f"{what} H7A encode/decode round-trip failed")
    return stored


# ---------------------------------------------------------------------------
# Writer.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CachePatchResult:
    directory_bytes: bytes
    payload_bytes: bytes
    manifest: dict[str, object]


@dataclass(frozen=True)
class _CacheLayerTarget:
    entry: CacheEntry
    metadata: dict[str, object]
    stored_part_a: bytes
    stored_part_b: bytes
    base: bytes
    mip_tail: bytes
    shift: int
    unknown: int
    rgba: bytes


def _read_pair(index_path: Path) -> tuple[apf_outer.Archive, apf_outer.Entry, apf_outer.Entry, bytes, bytes]:
    archive = apf_outer.parse_archive(index_path)
    dir_matches = [e for e in archive.entries if e.name_id == DIR_NAME_ID]
    pay_matches = [e for e in archive.entries if e.name_id == PAYLOAD_NAME_ID]
    if len(dir_matches) != 1 or len(pay_matches) != 1:
        raise PatchError("logo cache directory/payload outer entries are not both unique")
    dir_entry, pay_entry = dir_matches[0], pay_matches[0]
    if dir_entry.table_index != DIR_TABLE_INDEX or pay_entry.table_index != PAYLOAD_TABLE_INDEX:
        raise PatchError("logo cache outer table indices moved")
    for entry, size, offset, label in (
        (dir_entry, DIR_SIZE, DIR_PACK_OFFSET, "directory"),
        (pay_entry, PAYLOAD_SIZE, PAYLOAD_PACK_OFFSET, "payload"),
    ):
        if len(entry.segments) != 1 or entry.segments[0].pack_name != "0A":
            raise PatchError(f"logo cache {label} is not in one 0A segment")
        if entry.size != size:
            raise PatchError(f"logo cache {label} is 0x{entry.size:x}, expected 0x{size:x}")
        if entry.segments[0].pack_offset != offset:
            raise PatchError(f"logo cache {label} pack offset moved")
    with apf_inner.ArchiveReader(archive) as reader:
        dir_raw = reader.read(dir_entry, 0, dir_entry.size)
        pay_raw = reader.read(pay_entry, 0, pay_entry.size)
    if sha256_bytes(dir_raw) != EXPECTED_DIR_SHA256:
        raise PatchError("logo cache directory hash is not the pinned retail data; refusing")
    if sha256_bytes(pay_raw) != EXPECTED_PAYLOAD_SHA256:
        raise PatchError("logo cache payload hash is not the pinned retail data; refusing")
    return archive, dir_entry, pay_entry, dir_raw, pay_raw


def _extract_target(
    directory: CacheDirectory, payload: bytes, name: str, expected_base_sha: str | None
) -> _CacheLayerTarget:
    matches = [e for e in directory.entries if e.name == name]
    if len(matches) != 1:
        raise PatchError(f"logo cache has {len(matches)} entries named {name!r}")
    entry = matches[0]
    stored_a = payload[entry.stream_a : entry.stream_a + entry.len_a]
    stored_b = payload[entry.stream_b : entry.stream_b + entry.len_b]
    if len(stored_a) != entry.len_a or len(stored_b) != entry.len_b:
        raise PatchError(f"{name} sub-blocks are outside the payload allocation")
    dram, _, _ = _decompress_part(stored_a, DRAM_STRIDE, f"{name} DRAM part")
    vram, shift, unknown = _decompress_part(stored_b, VRAM_STRIDE, f"{name} VRAM part")
    metadata = apf_inner.parse_txtr_metadata(dram)
    _strict_descriptor(metadata)
    base = vram[:BASE_LEN]
    mip_tail = vram[BASE_LEN:]
    if len(mip_tail) != MIP_LEN:
        raise PatchError(f"{name} packed mip tail is not the expected length")
    if expected_base_sha is not None and sha256_bytes(base) != expected_base_sha:
        raise PatchError(f"{name} base hash is not the pinned retail data")
    # Transport gate: the Xenos untile/endian/tile path must round-trip this exact
    # retail base before any edit is trusted.
    rgba = decode_4444_base(metadata, base)
    if encode_4444_base(metadata, rgba) != base:
        raise PatchError(f"Xenos 4_4_4_4 transport is not bit-exact for {name}")
    return _CacheLayerTarget(
        entry=entry,
        metadata=metadata,
        stored_part_a=stored_a,
        stored_part_b=stored_b,
        base=base,
        mip_tail=mip_tail,
        shift=shift,
        unknown=unknown,
        rgba=rgba,
    )


def _repack_payload(
    directory: CacheDirectory,
    payload: bytes,
    edits: dict[int, bytes],
) -> tuple[bytes, dict[int, tuple[int, int, int, int]]]:
    """Rebuild the payload in stream order, substituting edited VRAM sub-blocks.

    Returns the new fixed-size payload and the new auxiliary values keyed by
    entry index.  Fails closed if the repacked contiguous stream would exceed the
    fixed ``0x9E0800`` outer allocation.
    """

    order = sorted(directory.entries, key=lambda e: e.stream_a)
    new_payload = bytearray()
    new_aux: dict[int, tuple[int, int, int, int]] = {}
    for entry in order:
        stream_a = len(new_payload)
        part_a = payload[entry.stream_a : entry.stream_a + entry.len_a]
        if len(part_a) != entry.len_a:
            raise PatchError(f"entry {entry.index} DRAM part is truncated")
        new_payload += part_a
        stream_b = len(new_payload)
        part_b = edits.get(entry.index, payload[entry.stream_b : entry.stream_b + entry.len_b])
        if entry.index not in edits and len(part_b) != entry.len_b:
            raise PatchError(f"entry {entry.index} VRAM part is truncated")
        new_payload += part_b
        new_aux[entry.index] = (stream_a, entry.len_a, stream_b, len(part_b))
    total = len(new_payload)
    if total > PAYLOAD_SIZE:
        raise PatchError(
            "repacked logo cache payload is 0x{:x}, exceeds the fixed 0x{:x} outer "
            "allocation by {} bytes; refusing output".format(
                total, PAYLOAD_SIZE, total - PAYLOAD_SIZE
            )
        )
    new_payload += b"\0" * (PAYLOAD_SIZE - total)
    return bytes(new_payload), new_aux


def _rewrite_directory(
    dir_raw: bytes,
    directory: CacheDirectory,
    new_aux: dict[int, tuple[int, int, int, int]],
) -> bytes:
    new_dir = bytearray(dir_raw)
    for entry in directory.entries:
        stream_a, length_a, stream_b, length_b = new_aux[entry.index]
        struct.pack_into(">4I", new_dir, entry.aux_offset, stream_a, length_a, stream_b, length_b)
    if len(new_dir) != DIR_SIZE:
        raise PatchError("rewritten logo cache directory changed size")
    return bytes(new_dir)


def build_cache_patch(
    index_path: Path,
    catalog_index: int,
    png_l0: Path,
    png_l1: Path | None = None,
    clear_l1: bool = False,
) -> CachePatchResult:
    """Rewrite catalog ``N``'s logo_l0 (and optionally logo_l1) inside the cache.

    ``clear_l1`` clears the cached detail layer's region masks while keeping its
    alpha, matching the package writer's treatment of one supplied mark.  The
    two copies of a crest have to agree, or the frontend tile and the helmet
    disagree about how many times the mark is drawn.
    """

    if png_l1 is not None and clear_l1:
        raise PatchError(
            "choose one detail-layer treatment: supply logo_l1 art, or clear it"
        )
    if not 0 <= catalog_index < CATALOG_COUNT:
        raise PatchError(f"catalog index {catalog_index} is outside 0..{CATALOG_COUNT - 1}")

    archive, dir_entry, pay_entry, dir_raw, pay_raw = _read_pair(index_path)
    directory = parse_cache_directory(dir_raw)
    if directory.total_stream_length > PAYLOAD_SIZE:
        raise PatchError("retail logo cache stream already exceeds its allocation")

    name_l0 = f"{catalog_index:02d}_logo_l0"
    name_l1 = f"{catalog_index:02d}_logo_l1"
    # A target's art is either a PNG the caller supplied or exact RGBA this
    # writer derived from the cached retail layer.
    targets: list[tuple[_CacheLayerTarget, Path | bytes]] = [
        (_extract_target(directory, pay_raw, name_l0, None), png_l0)
    ]
    if png_l1 is not None:
        targets.append((_extract_target(directory, pay_raw, name_l1, None), png_l1))
    elif clear_l1:
        detail = _extract_target(directory, pay_raw, name_l1, None)
        targets.append((detail, cleared_detail_rgba(detail.rgba)))

    edits: dict[int, bytes] = {}
    # (target, wanted_rgba, new_base, new_stored_b)
    changed: list[tuple[_CacheLayerTarget, bytes, bytes, bytes, bytes]] = []
    for target, art in targets:
        wanted = art if isinstance(art, bytes) else _load_png(art, 512, 512)
        if wanted == target.rgba:
            continue
        new_base = encode_4444_base(target.metadata, wanted)
        if new_base == target.base:
            raise PatchError(
                f"no-op detection inconsistent for {target.entry.name}: encode "
                "reproduced retail base"
            )
        # Regenerate the packed mip levels from the new base.  Preserving
        # them keeps the RETAIL logo in every level below mip 0, so the cached
        # copy still serves the old crest to any surface that draws it small --
        # exactly the bug that made modded crests look like they had not
        # applied.  The package writer does the same, so both copies of a crest
        # stay identical.
        new_tail = rebuild_mip_tail(target.metadata, wanted, target.mip_tail)
        new_vram = new_base + new_tail
        if len(new_vram) != VRAM_STRIDE:
            raise PatchError(f"VRAM stride invariant failed for {target.entry.name}")
        new_stored_b = _compress_part(
            new_vram, target.shift, target.unknown, f"{target.entry.name} VRAM part"
        )
        edits[target.entry.index] = new_stored_b
        changed.append((target, wanted, new_base, new_stored_b, new_tail))

    common_source = {
        "archive_index": str(index_path),
        "physical_volume": "0A",
        "catalog_index": catalog_index,
        "directory_entry_index": DIR_TABLE_INDEX,
        "payload_entry_index": PAYLOAD_TABLE_INDEX,
        "directory_sha256": sha256_bytes(dir_raw),
        "payload_sha256": sha256_bytes(pay_raw),
        "targets": [t.entry.name for t, _ in targets],
    }

    if not edits:
        manifest = {
            "schema": SCHEMA,
            "mode": "no_op",
            "source": common_source,
            "validation": {
                "xenos_transport_bit_exact": True,
                "input_matches_decoded_source": True,
                "directory_bit_exact": True,
                "payload_bit_exact": True,
                "source_opened_read_only": True,
            },
            "backend": {"png": f"Pillow {PILLOW_VERSION}"},
            "portme": _PORTME,
        }
        return CachePatchResult(dir_raw, pay_raw, manifest)

    new_payload, new_aux = _repack_payload(directory, pay_raw, edits)
    new_dir = _rewrite_directory(dir_raw, directory, new_aux)

    # --- Internal reparse gate (independent of the arithmetic above) ---
    new_directory = parse_cache_directory(new_dir)
    edited_indices = set(edits)
    for old_entry, new_entry in zip(directory.entries, new_directory.entries):
        if old_entry.index != new_entry.index or old_entry.name != new_entry.name:
            raise PatchError("directory entry order changed during rewrite")
        old_a = pay_raw[old_entry.stream_a : old_entry.stream_a + old_entry.len_a]
        new_a = new_payload[new_entry.stream_a : new_entry.stream_a + new_entry.len_a]
        if new_a != old_a:
            raise PatchError(f"entry {new_entry.name} DRAM part changed; refusing")
        old_b = pay_raw[old_entry.stream_b : old_entry.stream_b + old_entry.len_b]
        new_b = new_payload[new_entry.stream_b : new_entry.stream_b + new_entry.len_b]
        if new_entry.index in edited_indices:
            old_vram, _, _ = _decompress_part(old_b, VRAM_STRIDE, f"{new_entry.name} old VRAM")
            new_vram, _, _ = _decompress_part(new_b, VRAM_STRIDE, f"{new_entry.name} new VRAM")
            expected_tail = next(
                tail for t, _w, _base, _s, tail in changed
                if t.entry.index == new_entry.index
            )
            if new_vram[BASE_LEN:] != expected_tail:
                raise PatchError(
                    f"{new_entry.name} mip tail is not the intended regeneration; "
                    "refusing"
                )
            expected_base = next(
                base for t, _w, base, _s, _tail in changed
                if t.entry.index == new_entry.index
            )
            if new_vram[:BASE_LEN] != expected_base:
                raise PatchError(f"{new_entry.name} base is not the intended edit; refusing")
        else:
            if new_b != old_b:
                raise PatchError(f"unedited entry {new_entry.name} changed; refusing")

    # Directory: only the edited entries' aux records may differ from retail.
    changed_aux = [
        e.name
        for e in directory.entries
        if new_aux[e.index] != (e.stream_a, e.len_a, e.stream_b, e.len_b)
    ]
    _assert_directory_only_aux_changed(dir_raw, new_dir, directory)

    layers_report: dict[str, object] = {}
    for target, png in targets:
        edited = target.entry.index in edited_indices
        report: dict[str, object] = {
            "cache_entry_index": target.entry.index,
            "aggregate_slot": target.entry.aggregate_slot,
            "aggregate_vram_offset": target.entry.aggregate_vram_offset,
            "h7a_shift": target.shift,
            "base_sha256_before": sha256_bytes(target.base),
            "mip_tail_sha256": sha256_bytes(target.mip_tail),
            "mip_tail_preserved": False,
            "mip_tail_regenerated": True,
            "changed": edited,
            "stored_part_b_len_before": target.entry.len_b,
        }
        if edited:
            wanted, new_base, new_stored_b = next(
                (w, base, stored)
                for t, w, base, stored, _tail in changed
                if t is target
            )
            decoded_back = decode_4444_base(target.metadata, new_base)
            report["base_sha256_after"] = sha256_bytes(new_base)
            report["stored_part_b_len_after"] = len(new_stored_b)
            report["decode_back_max_abs_error"] = max(
                (abs(a - b) for a, b in zip(wanted, decoded_back)),
                default=0,
            )
        layers_report[target.entry.name] = report

    manifest = {
        "schema": SCHEMA,
        "mode": "patched",
        "source": common_source,
        "layers": layers_report,
        "payload": {
            "allocation_size": PAYLOAD_SIZE,
            "stream_length_before": directory.total_stream_length,
            "stream_length_after": _stream_length(new_directory),
            "allocation_slack_after": PAYLOAD_SIZE - _stream_length(new_directory),
            "sha256_before": sha256_bytes(pay_raw),
            "sha256_after": sha256_bytes(new_payload),
        },
        "directory": {
            "allocation_size": DIR_SIZE,
            "sha256_before": sha256_bytes(dir_raw),
            "sha256_after": sha256_bytes(new_dir),
            "auxiliary_records_changed": changed_aux,
            "descriptors_footer_names_preserved": True,
        },
        "binary_patch_manifest": {
            "physical_volume": "0A",
            "extents": [
                {
                    "label": "uniform_logocache.iff (directory)",
                    "physical_offset": DIR_PACK_OFFSET,
                    "replacement_length": DIR_SIZE,
                    "original_sha256": sha256_bytes(dir_raw),
                    "replacement_sha256": sha256_bytes(new_dir),
                    **_changed_extents(dir_raw, new_dir),
                },
                {
                    "label": "uniform_logocache.cdf (payload)",
                    "physical_offset": PAYLOAD_PACK_OFFSET,
                    "replacement_length": PAYLOAD_SIZE,
                    "original_sha256": sha256_bytes(pay_raw),
                    "replacement_sha256": sha256_bytes(new_payload),
                    **_changed_extents(pay_raw, new_payload),
                },
            ],
            "contains_replacement_bytes": False,
        },
        "validation": {
            "xenos_transport_bit_exact": True,
            "h7a_decode_encode_decode_exact": True,
            "directory_reparsed": True,
            "every_dram_part_preserved": True,
            "every_unedited_vram_part_preserved": True,
            "edited_mip_tails_preserved": False,
            "edited_mip_tails_regenerated": True,
            "descriptors_aggregate_footer_preserved": True,
            "fixed_outer_allocation": True,
            "changed_cache_entries": sorted(edited_indices),
            "source_opened_read_only": True,
        },
        "backend": {
            "png": f"Pillow {PILLOW_VERSION}",
            "encoder": (
                "exact 4_4_4_4 nibble pack (uncompressed, lossless for retail; "
                "PNG->4bit quantized)"
            ),
            "h7a": "project-native greedy H7A encoder (per-block original shift)",
        },
        "portme": _PORTME,
    }
    return CachePatchResult(new_dir, new_payload, manifest)


def _stream_length(directory: CacheDirectory) -> int:
    return max((e.stream_b + e.len_b for e in directory.entries), default=0)


def _assert_directory_only_aux_changed(
    dir_before: bytes, dir_after: bytes, directory: CacheDirectory
) -> None:
    """Every changed directory byte must lie inside an auxiliary record."""

    aux_spans = [(e.aux_offset, e.aux_offset + 0x10) for e in directory.entries]
    for index in range(len(dir_before)):
        if dir_before[index] == dir_after[index]:
            continue
        if not any(lo <= index < hi for lo, hi in aux_spans):
            raise PatchError(
                f"logo cache directory changed outside an auxiliary record at 0x{index:x}"
            )


def _changed_extents(before: bytes, after: bytes) -> dict[str, object]:
    if len(before) != len(after):
        raise PatchError("changed-extent inputs differ in length")
    changed = [index for index in range(len(before)) if before[index] != after[index]]
    return {
        "changed_byte_count": len(changed),
        "first_changed_offset": changed[0] if changed else None,
        "last_changed_offset": changed[-1] if changed else None,
    }


# ---------------------------------------------------------------------------
# Copy-only volume write: replace the two fixed extents in a NEW volume, keeping
# every safeguard of apf_logo_patch._write_copied_volume (source opened read-only
# and hashed before/after, bytes outside every extent hashed equal, output size
# unchanged, refuse overwrite/aliasing).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Extent:
    label: str
    offset: int
    replacement: bytes


def _write_copied_volume_extents(
    source_volume: Path, output_volume: Path, extents: list[Extent]
) -> dict[str, object]:
    if source_volume.resolve() == output_volume.resolve():
        raise PatchError("refusing to patch the source APF volume")
    if not extents:
        raise PatchError("no extents to write")
    ordered = sorted(extents, key=lambda extent: extent.offset)
    for earlier, later in zip(ordered, ordered[1:]):
        if earlier.offset + len(earlier.replacement) > later.offset:
            raise PatchError("refusing overlapping replacement extents")

    output_volume.parent.mkdir(parents=True, exist_ok=True)
    source_descriptor = os.open(source_volume, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0))
    output_descriptor: int | None = None
    output_identity: tuple[int, int] | None = None
    try:
        source_metadata = os.fstat(source_descriptor)
        if not stat.S_ISREG(source_metadata.st_mode):
            raise PatchError("source APF volume is not a regular file")
        source_identity = _fd_identity(source_descriptor)
        source_size = source_metadata.st_size
        source_sha_before = _sha256_fd(source_descriptor)
        for extent in ordered:
            if extent.offset < 0 or extent.offset + len(extent.replacement) > source_size:
                raise PatchError(f"{extent.label} extent is outside the copied volume")
        try:
            output_descriptor = os.open(
                output_volume,
                os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
                stat.S_IMODE(source_metadata.st_mode),
            )
        except FileExistsError as exc:
            raise PatchError(
                f"refusing to overwrite existing output volume: {output_volume}"
            ) from exc
        output_identity = _fd_identity(output_descriptor)

        cursor = 0
        while cursor < source_size:
            chunk = platform_compat.pread(
                source_descriptor, min(8 * 1024 * 1024, source_size - cursor), cursor
            )
            if not chunk:
                raise PatchError("unexpected end of source volume during copy")
            _pwrite_all(output_descriptor, chunk, cursor)
            cursor += len(chunk)
        os.ftruncate(output_descriptor, source_size)

        extent_reports: list[dict[str, object]] = []
        for extent in ordered:
            before = _pread_exact(output_descriptor, len(extent.replacement), extent.offset)
            mode = (
                "bit_exact_no_op"
                if sha256_bytes(before) == sha256_bytes(extent.replacement)
                else "replaced"
            )
            _pwrite_all(output_descriptor, extent.replacement, extent.offset)
            extent_reports.append(
                {
                    "label": extent.label,
                    "offset": extent.offset,
                    "length": len(extent.replacement),
                    "mode": mode,
                }
            )
        os.fsync(output_descriptor)

        if os.fstat(output_descriptor).st_size != source_size:
            raise PatchError("copied volume size changed")
        for extent, report in zip(ordered, extent_reports):
            written = _pread_exact(output_descriptor, len(extent.replacement), extent.offset)
            if written != extent.replacement:
                raise PatchError(f"{extent.label} read-back does not match replacement")
            report["read_back_sha256"] = sha256_bytes(written)

        # Every byte OUTSIDE the union of extents must match the source exactly.
        gaps: list[tuple[int, int]] = []
        cursor = 0
        for extent in ordered:
            if extent.offset > cursor:
                gaps.append((cursor, extent.offset))
            cursor = extent.offset + len(extent.replacement)
        if cursor < source_size:
            gaps.append((cursor, source_size))
        outside_reports: list[dict[str, object]] = []
        for start, end in gaps:
            length = end - start
            source_sha = _sha256_fd_range(source_descriptor, start, length)
            output_sha = _sha256_fd_range(output_descriptor, start, length)
            if source_sha != output_sha:
                raise PatchError(
                    f"bytes outside the extents changed in the copied volume at 0x{start:x}"
                )
            outside_reports.append(
                {"offset": start, "length": length, "sha256": source_sha}
            )

        output_sha = _sha256_fd(output_descriptor)
        source_sha_after = _sha256_fd(source_descriptor)
        if source_sha_after != source_sha_before:
            raise PatchError("source APF volume changed during copied-volume patch")
        if not _path_is_owned_inode(source_volume, source_identity):
            raise PatchError("source APF volume pathname changed during copy")

        _copy_fd_metadata(
            source_descriptor, output_descriptor, source_metadata, output_volume
        )
        os.fsync(output_descriptor)
        if not _path_is_owned_inode(output_volume, output_identity):
            raise PatchError("output volume pathname changed during copied-volume patch")
        return {
            "source_volume": str(source_volume),
            "output_volume": str(output_volume),
            "volume_size": source_size,
            "source_volume_sha256_before": source_sha_before,
            "source_volume_sha256_after": source_sha_after,
            "output_volume_sha256": output_sha,
            "extents": extent_reports,
            "outside_extents": outside_reports,
            "outside_extents_match_source": True,
        }
    except Exception:
        if output_identity is not None:
            _unlink_owned_path(output_volume, output_identity)
        raise
    finally:
        if output_descriptor is not None:
            os.close(output_descriptor)
        os.close(source_descriptor)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path, help="user-owned APF 0A")
    parser.add_argument("--catalog-index", required=True, type=int, help="team logo catalog index 0..117")
    parser.add_argument("--png", required=True, type=Path, help="edited 512x512 RGBA PNG for N_logo_l0")
    parser.add_argument("--png-l1", type=Path, help="optional edited 512x512 RGBA PNG for N_logo_l1")
    parser.add_argument("--output-directory-entry", type=Path, help="write rebuilt uniform_logocache.iff")
    parser.add_argument("--output-payload-entry", type=Path, help="write rebuilt uniform_logocache.cdf")
    parser.add_argument(
        "--output-volume",
        type=Path,
        help="copy 0A to this new path, then replace only the two fixed cache extents",
    )
    parser.add_argument("--manifest", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest_reservation: OutputReservation | None = None
    manifest_path = args.manifest.expanduser()
    try:
        index_path = args.index.expanduser()
        png_path = args.png.expanduser()
        png_l1 = args.png_l1.expanduser() if args.png_l1 is not None else None
        output_dir_entry = (
            args.output_directory_entry.expanduser()
            if args.output_directory_entry is not None
            else None
        )
        output_pay_entry = (
            args.output_payload_entry.expanduser()
            if args.output_payload_entry is not None
            else None
        )
        output_volume = (
            args.output_volume.expanduser() if args.output_volume is not None else None
        )
        inputs = [index_path, png_path] + ([png_l1] if png_l1 is not None else [])
        _preflight_output_paths(
            inputs,
            [
                ("manifest", manifest_path),
                ("output directory entry", output_dir_entry),
                ("output payload entry", output_pay_entry),
                ("output volume", output_volume),
            ],
        )
        manifest_reservation = _reserve_new(manifest_path)
        result = build_cache_patch(index_path, args.catalog_index, png_path, png_l1)
        document = result.manifest
        if output_dir_entry is not None:
            _write_new(output_dir_entry, result.directory_bytes)
            document["output_directory_entry"] = {
                "path": str(output_dir_entry),
                "sha256": sha256_bytes(result.directory_bytes),
                "size": len(result.directory_bytes),
            }
        if output_pay_entry is not None:
            _write_new(output_pay_entry, result.payload_bytes)
            document["output_payload_entry"] = {
                "path": str(output_pay_entry),
                "sha256": sha256_bytes(result.payload_bytes),
                "size": len(result.payload_bytes),
            }
        if output_volume is not None:
            document["copied_volume"] = _write_copied_volume_extents(
                index_path,
                output_volume,
                [
                    Extent("uniform_logocache.iff", DIR_PACK_OFFSET, result.directory_bytes),
                    Extent("uniform_logocache.cdf", PAYLOAD_PACK_OFFSET, result.payload_bytes),
                ],
            )
        _commit_reserved(
            manifest_path,
            manifest_reservation,
            (json.dumps(document, indent=2) + "\n").encode("utf-8"),
        )
        _close_reserved(manifest_reservation)
        manifest_reservation = None
        layers = "l0+l1" if png_l1 is not None else "l0"
        print(
            "APF_LOGOCACHE_PATCH_PASS "
            f"mode={document['mode']} catalog={args.catalog_index} layers={layers} "
            f"dir_sha256={sha256_bytes(result.directory_bytes)} "
            f"payload_sha256={sha256_bytes(result.payload_bytes)}"
        )
    except (PatchError, apf_inner.FormatError, apf_outer.FormatError, OSError) as exc:
        if manifest_reservation is not None:
            _abort_reserved(manifest_path, manifest_reservation)
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

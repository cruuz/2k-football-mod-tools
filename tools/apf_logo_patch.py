#!/usr/bin/env python3
"""Safely replace the proven APF 2K8 team-logo base texture in a copied volume.

This is an evidence-bounded writer for one selected ``uniform_logo_NN.iff``
package and its ``logo_l0`` layer: a tiled, uncompressed Xenos ``4_4_4_4``
(16-bit RGBA, one nibble per channel) 512x512 base level with a packed mip tail.
It rewrites the selected base level, regenerates the 0x2C000 packed mip tail,
and byte-preserves the entire sibling ``logo_l1`` layer unless a second PNG is
explicitly supplied.  It recompresses only the affected VRAM H7A block, rebuilds
the IFF block offsets/footer inside the fixed outer allocation, independently
reparses the rebuilt entry in RAM, and can only write a newly copied ``0A``
volume.  The retail source is never opened for writing.

In All-Pro Football 2K8 the helmet crest is this same shared team-logo texture
(the helmet family carries only ``helmet_color`` + ``helmet_normal``; there is no
separate helmet-logo TXTR), so a correct ``uniform_logo`` base write IS the
helmet-crest write.  The scorebug also samples the team logo, but whether the
runtime resolves it from this package or from the separate ``uniform_logocache``
container is unresolved (see ``portme``); this writer therefore proves the exact
bytes it changes, and makes no in-game/runtime claim without a Xenia capture.

This module is intentionally decoupled from ``apf_texture_patch.py``: the small,
format-agnostic H7A/tiling/IFF-safety helpers are copied verbatim rather than
imported so the writer neither edits nor couples to that file.  The genuinely new
code is the ``4_4_4_4`` encode/decode transport, proven bit-exact against retail
this session.  Unsupported descriptor variants are rejected with PORTME errors
rather than guessed.
"""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
from concurrent.futures import Future, ProcessPoolExecutor
from dataclasses import dataclass
import hashlib
import json
import math
import multiprocessing
import os
from pathlib import Path
import stat
import struct
import sys
from typing import Callable, Iterable
import zlib

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from mod_editor.core import platform_compat  # noqa: E402

try:
    from PIL import Image, __version__ as PILLOW_VERSION
except ImportError as exc:  # pragma: no cover - exercised by the CLI error path.
    raise SystemExit("error: Pillow is required for PNG import") from exc

import apf_inner  # noqa: E402
import apf_outer  # noqa: E402
import apf_xenos_4444_mip_layout as mip4444  # noqa: E402


SCHEMA = "apf_logo_patch/v1"
ENTRY_INDEX = 36
FILE_INDEX = 1
ENTRY_NAME = "uniform_logo_01.iff"
INNER_NAME = "logo_l0"
SIBLING_NAME = "logo_l1"
EXPECTED_ENTRY_SHA256 = (
    "5683eb73e670d9ece595f707f15d9302522a5243b7fb872f70e3cd31a5632287"
)
EXPECTED_BASE_SHA256 = (
    "5683fb638cf72e4532149f757ac49d702a6d158043faa930c58745a1b81f9037"
)
# The pinned hashes above describe uniform_logo_01 and only uniform_logo_01.
# There are 236 team crests on the disc and every one of them has the identical
# structure, so requiring logo_01's bytes made the writer refuse the other 235
# targets -- including uniform_logo_30, the crest the Americans actually wear.
# The pin is therefore checked when the caller is working on logo_01 and
# skipped otherwise; what does the real work on any entry is the per-extent
# evidence that follows, which is stronger than a whole-container hash:
# the strict Xenos descriptor, the exact DRAM/VRAM part lengths, and the
# transport gate that must reproduce that entry's own retail base bit-for-bit
# before a single byte is written.  The observed hashes are recorded in the
# manifest either way, so provenance survives.
PINNED_ENTRIES: dict[int, dict[str, str]] = {
    ENTRY_INDEX: {
        "entry": EXPECTED_ENTRY_SHA256,
        INNER_NAME: EXPECTED_BASE_SHA256,
    },
}
# The sibling ``logo_l1`` base level (inner file 0, VRAM at block1 offset
# 0xAC000).  Its Xenos descriptor is byte-for-byte identical to ``logo_l0`` (both
# tiled 4_4_4_4 512x512), so the same encoder writes it.
SIBLING_FILE_INDEX = 0
EXPECTED_BASE_L1_SHA256 = (
    "5462580af5374c8b18ae35f43d517408bcc446ceb0d6a339f87c3db7703b3b03"
)
PINNED_ENTRIES[ENTRY_INDEX][SIBLING_NAME] = EXPECTED_BASE_L1_SHA256


def pinned_base_sha(entry_index: int, inner_name: str) -> str | None:
    """The retail base hash for this exact layer, when one has been pinned."""

    return PINNED_ENTRIES.get(entry_index, {}).get(inner_name)


def resolve_outer_name(entry: apf_outer.Entry) -> str:
    """Recover the crest package's real name from its stored name id.

    The manifest is evidence, so it must not label uniform_logo_30 as
    uniform_logo_01.  Outer names are stored only as a CRC32 of the uppercase
    ASCII filename, and the crest family is a known template, so the name comes
    back by matching the checksum rather than by assuming the target.
    """

    for asset_index in range(0, 256):
        candidate = f"uniform_logo_{asset_index:02d}.iff"
        if zlib.crc32(candidate.upper().encode("ascii")) & 0xFFFFFFFF == entry.name_id:
            return candidate
    return f"<outer entry {entry.table_index}, name id 0x{entry.name_id:08x}>"


def resolve_layer_indices(record: apf_inner.IFFRecord) -> tuple[int, int]:
    """Find logo_l0 and logo_l1 by name rather than by position.

    The two inner files are not stored in a consistent order across the crest
    packages, so a fixed index silently reads the wrong layer on some teams.
    """

    found: dict[str, int] = {}
    for index, inner in enumerate(record.files):
        if inner.name in (INNER_NAME, SIBLING_NAME):
            found[inner.name] = index
    missing = {INNER_NAME, SIBLING_NAME} - set(found)
    if missing:
        raise PatchError(
            f"PORTME: crest IFF is missing {sorted(missing)}; found "
            f"{[inner.name for inner in record.files]}"
        )
    return found[INNER_NAME], found[SIBLING_NAME]
BASE_LEN = 0x80000
MIP_LEN = 0x2C000
PAYLOAD_LEN = 0xAC000
DRAM_PART_LEN = 0xE0
WIDTH = 512
HEIGHT = 512
PITCH = 512
FORMAT = 15
ENDIAN = 1
SWIZZLE = [2, 1, 0, 3]
MAX_H7A_CANDIDATES = 256

STRICT_DESCRIPTOR = {
    "format": FORMAT,
    "width": WIDTH,
    "height": HEIGHT,
    "pitch_pixels": PITCH,
    "endianness": ENDIAN,
    "tiled": True,
    "stacked": False,
    "dimension": 1,
    "vc_base_data_length": BASE_LEN,
    "vc_mip_data_length": MIP_LEN,
    "swizzle_components": SWIZZLE,
    "packed_mips": True,
}

PRODUCTION_ENCODER_CAVEAT = (
    "The 4_4_4_4 encoder is lossless for retail data (nibbles are exact multiples "
    "of 17); an arbitrary PNG is quantized to 4 bits per channel, so inspect the "
    "reported decode-back error before broad release."
)

_PORTME = [
    "validate this changed copied volume in Xenia and on user-owned hardware "
    "before describing any in-game/runtime effect as proved",
    "resolve which runtime surface (frontend team-select grid, in-game scorebug, "
    "helmet crest) samples this package texture vs the uniform_logocache aggregate; "
    "the cache is separately writable via tools/apf_logocache_patch.py and the "
    "package-vs-cache-vs-both Xenia differential closes which source each surface reads",
    PRODUCTION_ENCODER_CAVEAT,
]


# ---------------------------------------------------------------------------
# Copied verbatim from tools/apf_texture_patch.py (format-agnostic; copied to
# avoid editing/coupling to that concurrently-edited module).
# ---------------------------------------------------------------------------
class PatchError(ValueError):
    """Raised when a proposed patch cannot be proved safe."""


class BytesReader:
    """Minimal entry-relative reader used to validate a rebuilt entry in RAM."""

    def __init__(self, data: bytes):
        self.data = data

    def read(self, entry: apf_outer.Entry, offset: int, size: int) -> bytes:
        if offset < 0 or size < 0 or offset + size > len(self.data):
            raise apf_inner.FormatError("memory entry read is out of bounds")
        return self.data[offset : offset + size]


@dataclass(frozen=True)
class PatchResult:
    entry_bytes: bytes
    manifest: dict[str, object]


@dataclass(frozen=True)
class OutputReservation:
    """An exclusively created path and the identity of its owned inode."""

    descriptor: int
    identity: tuple[int, int]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _match_length(data: bytes, current: int, candidate: int, maximum: int) -> int:
    length = 0
    # Overlapping LZ copies are legal: once the match reaches current, the
    # decoder reads bytes it just emitted.  Since the full intended output is
    # already available here, candidate + length names that same byte directly.
    while length < maximum:
        if data[current + length] != data[candidate + length]:
            break
        length += 1
    return length


def compress_h7a(
    data: bytes,
    shift: int,
    *,
    candidate_limit: int = MAX_H7A_CANDIDATES,
) -> bytes:
    """Greedy encoder for the H7A stream consumed by ``decompress_h7a``.

    ``candidate_limit`` lets callers with unusually tight fixed allocations
    trade additional CPU time for a denser stream.  The historical default is
    retained for texture workflows, whose allocations do not need the slower
    exhaustive pass used by the large APF string banks.
    """

    if not 1 <= shift <= 15:
        raise PatchError(f"invalid H7A shift {shift}")
    if candidate_limit <= 0:
        raise PatchError("H7A candidate limit must be positive")
    max_distance = (1 << shift) - 1
    max_length = ((1 << (16 - shift)) - 1) + 3
    positions: dict[bytes, deque[int]] = defaultdict(deque)
    output = bytearray()
    cursor = 0

    def remember(position: int) -> None:
        if position + 3 > len(data):
            return
        key = data[position : position + 3]
        bucket = positions[key]
        bucket.append(position)
        oldest = position - max_distance
        while bucket and bucket[0] < oldest:
            bucket.popleft()

    while cursor < len(data):
        descriptor_offset = len(output)
        output.append(0)
        descriptor = 0
        for bit in range(8):
            if cursor >= len(data):
                break
            best_length = 0
            best_distance = 0
            if cursor + 3 <= len(data):
                key = data[cursor : cursor + 3]
                bucket = positions.get(key)
                if bucket:
                    minimum = cursor - max_distance
                    candidates = 0
                    for candidate in reversed(bucket):
                        if candidate < minimum:
                            break
                        distance = cursor - candidate
                        if distance <= 0:
                            continue
                        length = _match_length(
                            data,
                            cursor,
                            candidate,
                            min(max_length, len(data) - cursor),
                        )
                        # Never emit a match that reads bytes it is still
                        # writing.  Our decoder copies one byte at a time and
                        # so reproduces an overlapping run correctly, which is
                        # why this round-tripped perfectly offline while the
                        # rebuilt texture came back as fine speckle in game.
                        # Retail settles it: the shipped 512x512 crest block
                        # holds 36,099 matches and not one overlaps, where a
                        # plain greedy encoder emits nearly eleven thousand --
                        # almost all at distance 2, the run-length idiom.
                        # Clamping to the distance costs a little ratio and
                        # buys a stream the console decodes the way it decodes
                        # retail's.
                        if length > distance:
                            length = distance
                        if length < 3:
                            continue
                        # On a tie prefer the FARTHER match.  Both encode to
                        # the same two bytes, but since a match may no longer
                        # overlap, the reachable length at the next position is
                        # bounded by the distance -- so taking the near copy
                        # caps every following match at the same short length
                        # and a run ramps up far more slowly.
                        if length > best_length or (
                            length == best_length and distance > best_distance
                        ):
                            best_length = length
                            best_distance = distance
                            if best_length == max_length:
                                break
                        candidates += 1
                        if candidates >= candidate_limit:
                            break
            if best_length >= 3:
                descriptor |= 1 << bit
                word = ((best_length - 3) << shift) | best_distance
                output.extend(word.to_bytes(2, "big"))
                consumed = best_length
            else:
                output.append(data[cursor])
                consumed = 1
            for position in range(cursor, cursor + consumed):
                remember(position)
            cursor += consumed
        output[descriptor_offset] = descriptor
    return bytes(output)


def _inverse_swizzle_pixels(
    rgba: bytes, selectors: Iterable[int]
) -> list[tuple[int, int, int, int]]:
    selectors_tuple = tuple(selectors)
    if sorted(selectors_tuple) != [0, 1, 2, 3]:
        raise PatchError(
            "PORTME: texture import currently requires a permutation-only RGBA swizzle"
        )
    pixels: list[tuple[int, int, int, int]] = []
    for offset in range(0, len(rgba), 4):
        displayed = rgba[offset : offset + 4]
        raw = [0, 0, 0, 0]
        for output_component, raw_component in enumerate(selectors_tuple):
            raw[raw_component] = displayed[output_component]
        pixels.append(tuple(raw))  # type: ignore[arg-type]
    return pixels


def _tile_2d(
    linear: bytes,
    width: int,
    height: int,
    pitch_pixels: int,
    block_width: int,
    block_height: int,
    bytes_per_block: int,
    allocation_size: int,
) -> bytes:
    width_blocks = (width + block_width - 1) // block_width
    height_blocks = (height + block_height - 1) // block_height
    expected_linear = width_blocks * height_blocks * bytes_per_block
    if len(linear) != expected_linear:
        raise PatchError(
            f"linear texture is 0x{len(linear):x}, expected 0x{expected_linear:x}"
        )
    pitch_blocks = (pitch_pixels + block_width - 1) // block_width
    pitch_aligned = apf_inner._align_up(pitch_blocks, 32)  # type: ignore[attr-defined]
    height_aligned = apf_inner._align_up(height_blocks, 32)  # type: ignore[attr-defined]
    required = pitch_aligned * height_aligned * bytes_per_block
    if allocation_size != required:
        raise PatchError(
            "PORTME: TXTR base allocation has padding or mip-tail semantics not "
            f"covered by this writer (0x{allocation_size:x} != 0x{required:x})"
        )
    output = bytearray(allocation_size)
    log2_size = bytes_per_block.bit_length() - 1
    visited: set[int] = set()
    for y in range(height_blocks):
        for x in range(width_blocks):
            destination = apf_inner._tiled_2d_offset(  # type: ignore[attr-defined]
                x, y, pitch_aligned, log2_size
            )
            if destination in visited:
                raise PatchError("Xenos tile mapping aliases two source blocks")
            visited.add(destination)
            source = (y * width_blocks + x) * bytes_per_block
            output[destination : destination + bytes_per_block] = linear[
                source : source + bytes_per_block
            ]
    if len(visited) * bytes_per_block != allocation_size:
        raise PatchError("PORTME: Xenos tile mapping does not cover the full allocation")
    return bytes(output)


def _rgba_metrics(wanted: bytes, decoded: bytes) -> dict[str, object]:
    if len(wanted) != len(decoded):
        raise PatchError("RGBA metric buffers differ in length")
    errors = [abs(first - second) for first, second in zip(wanted, decoded)]
    squared = sum(error * error for error in errors)
    rmse = math.sqrt(squared / len(errors)) if errors else 0.0
    psnr = None if rmse == 0 else 20.0 * math.log10(255.0 / rmse)
    return {
        "compared_components": len(errors),
        "different_components": sum(error != 0 for error in errors),
        "maximum_absolute_error": max(errors, default=0),
        "mean_absolute_error": sum(errors) / len(errors) if errors else 0.0,
        "rmse": rmse,
        "psnr_db": psnr,
    }


def _changed_extents(before: bytes, after: bytes) -> dict[str, object]:
    changed = [index for index, pair in enumerate(zip(before, after)) if pair[0] != pair[1]]
    return {
        "changed_byte_count": len(changed),
        "first_changed_offset": changed[0] if changed else None,
        "last_changed_offset": changed[-1] if changed else None,
    }


def _file_part_hashes(
    record: apf_inner.IFFRecord, blocks: list[bytes]
) -> dict[tuple[int, int], str]:
    result: dict[tuple[int, int], str] = {}
    for file in record.files:
        for part_index, part in enumerate(file.parts):
            payload = blocks[part.block_index][part.offset : part.offset + part.length]
            result[(file.index, part_index)] = sha256_bytes(payload)
    return result


def _load_png(path: Path, expected_width: int, expected_height: int) -> bytes:
    with Image.open(path) as image:
        image.load()
        if image.size != (expected_width, expected_height):
            raise PatchError(
                f"PNG is {image.width}x{image.height}; target is "
                f"{expected_width}x{expected_height}"
            )
        return image.convert("RGBA").tobytes()


# ---------------------------------------------------------------------------
# New code: the 4_4_4_4 base transport (proven bit-exact against retail this
# session).  ``decode_4444_base`` mirrors the decoder in
# tools/apf_uniform_inventory.py:695-729; ``encode_4444_base`` is its exact
# inverse (inverse-swizzle -> 8->4-bit quantize -> pack little-endian u16 ->
# Xenos endian swap -> Xenos 2-byte-per-texel tile).
# ---------------------------------------------------------------------------
def decode_4444_base(metadata: dict[str, object], base: bytes) -> bytes:
    """Decode a tiled Xenos 4_4_4_4 base level to display-order RGBA bytes."""

    width = int(metadata["width"])
    height = int(metadata["height"])
    linear = apf_inner._untile_2d(  # type: ignore[attr-defined]
        base, width, height, int(metadata["pitch_pixels"]), 1, 1, 2
    )
    linear = apf_inner._endian_swap(  # type: ignore[attr-defined]
        linear, int(metadata["endianness"])
    )
    selectors = list(metadata["swizzle_components"])
    output = bytearray(width * height * 4)
    for pixel_index in range(width * height):
        value = int.from_bytes(linear[pixel_index * 2 : pixel_index * 2 + 2], "little")
        pixel = (
            (value & 0xF) * 17,
            ((value >> 4) & 0xF) * 17,
            ((value >> 8) & 0xF) * 17,
            ((value >> 12) & 0xF) * 17,
        )
        pixel = apf_inner._swizzle_pixel(pixel, selectors)  # type: ignore[attr-defined]
        output[pixel_index * 4 : pixel_index * 4 + 4] = bytes(pixel)
    return bytes(output)


def encode_4444_base(metadata: dict[str, object], rgba_display: bytes) -> bytes:
    """Encode display-order RGBA bytes into a tiled Xenos 4_4_4_4 base level.

    Exact inverse of :func:`decode_4444_base`.  For retail data (channel values
    that are exact multiples of 17) this is bit-exact; an arbitrary PNG is
    quantized to 4 bits per channel with round-to-nearest.
    """

    if len(rgba_display) != WIDTH * HEIGHT * 4:
        raise PatchError(
            f"RGBA buffer is 0x{len(rgba_display):x}, expected "
            f"0x{WIDTH * HEIGHT * 4:x}"
        )
    raw_pixels = _inverse_swizzle_pixels(
        rgba_display, metadata["swizzle_components"]  # type: ignore[arg-type]
    )
    quantize = lambda value: (value * 15 + 127) // 255  # noqa: E731 - inline, inspectable
    linear = bytearray(WIDTH * HEIGHT * 2)
    for index, (raw_r, raw_g, raw_b, raw_a) in enumerate(raw_pixels):
        packed = (
            quantize(raw_r)
            | quantize(raw_g) << 4
            | quantize(raw_b) << 8
            | quantize(raw_a) << 12
        )
        linear[index * 2 : index * 2 + 2] = packed.to_bytes(2, "little")
    on_disc = apf_inner._endian_swap(  # type: ignore[attr-defined]
        bytes(linear), int(metadata["endianness"])
    )
    return _tile_2d(on_disc, WIDTH, HEIGHT, PITCH, 1, 1, 2, BASE_LEN)


def encode_4444_linear(
    metadata: dict[str, object], rgba_display: bytes, texels: int
) -> bytes:
    """Encode display-order RGBA into row-major on-disc 4_4_4_4 halfwords.

    Same transport as :func:`encode_4444_base` but without the base level's
    fixed dimensions, so a mip level can be encoded before being tiled into
    its own place in the packed tail.
    """

    if len(rgba_display) != texels * 4:
        raise PatchError(
            f"RGBA buffer is 0x{len(rgba_display):x}, expected 0x{texels * 4:x}"
        )
    raw_pixels = _inverse_swizzle_pixels(
        rgba_display, metadata["swizzle_components"]  # type: ignore[arg-type]
    )
    quantize = lambda value: (value * 15 + 127) // 255  # noqa: E731
    linear = bytearray(texels * 2)
    for index, (raw_r, raw_g, raw_b, raw_a) in enumerate(raw_pixels):
        packed = (
            quantize(raw_r)
            | quantize(raw_g) << 4
            | quantize(raw_b) << 8
            | quantize(raw_a) << 12
        )
        linear[index * 2 : index * 2 + 2] = packed.to_bytes(2, "little")
    return apf_inner._endian_swap(  # type: ignore[attr-defined]
        bytes(linear), int(metadata["endianness"])
    )


def rebuild_mip_tail(
    metadata: dict[str, object], rgba_base: bytes, original_tail: bytes
) -> bytes:
    """Regenerate every stored mip level from a replacement base level.

    Byte-preserving the tail looks conservative, but it is the reason modded
    crests appear not to work: the tail still holds the *retail* logo, and the
    GPU samples it for every draw smaller than full size -- the team-select
    tile, the logo carousel, and a helmet more than a few yards out.  Only the
    levels the descriptor actually addresses are written; the page-rounded
    slack at the end of the allocation stays byte-identical to retail.
    """

    locations = mip4444.derive_layout(metadata)
    padding = mip4444.tail_padding(locations, int(metadata["vc_mip_data_length"]))
    if len(original_tail) != int(metadata["vc_mip_data_length"]):
        raise PatchError("mip tail length does not match the descriptor")

    base = Image.frombytes(
        "RGBA", (int(metadata["width"]), int(metadata["height"])), rgba_base
    )
    # The payload buffer the layout addresses starts at the base level, so the
    # tail is written through a full-length view and sliced back off at the end.
    payload = bytearray(locations[0].allocation_length) + bytearray(original_tail)
    for location in locations[1:]:
        # BOX is an area average, which is what a mip level is; a sharper
        # filter would ring on flat mask edges and quantize to stray nibbles.
        level = base.resize((location.width, location.height), Image.BOX)
        linear = encode_4444_linear(
            metadata, level.tobytes(), location.width * location.height
        )
        mip4444.write_level(payload, location, linear)

    rebuilt = bytes(payload[locations[0].allocation_length:])
    if padding and rebuilt[len(rebuilt) - padding:] != original_tail[len(original_tail) - padding:]:
        raise PatchError("mip regeneration wrote into the tail's unused slack")
    return rebuilt


def _strict_descriptor(metadata: dict[str, object]) -> None:
    disagreements = {
        key: (metadata.get(key), expected)
        for key, expected in STRICT_DESCRIPTOR.items()
        if metadata.get(key) != expected
    }
    if disagreements:
        raise PatchError(
            f"PORTME: uniform_logo_01 logo_l0 descriptor changed: {disagreements}"
        )


@dataclass(frozen=True)
class _LayerTarget:
    """A validated, transport-round-tripped logo layer inside the shared block1."""

    file_index: int
    name: str
    type_name: str
    metadata: dict[str, object]
    base: bytes
    mip_tail: bytes
    vram_offset: int
    rgba: bytes


@dataclass(frozen=True)
class _RebuildResult:
    """Outcome of recompressing block1 and rebuilding/reparsing the IFF entry."""

    rebuilt_entry: bytes
    new_file_length: int
    footer_bytes: bytes
    footer_after: bytes
    footer_total: int
    active_len: int
    block_report: list[dict[str, object]]
    before_parts: dict[tuple[int, int], str]
    after_parts: dict[tuple[int, int], str]
    changed_parts: list[tuple[int, int]]


def _open_entry(
    index_path: Path, entry_index: int
) -> tuple[
    apf_outer.Archive,
    apf_outer.Entry,
    apf_inner.IFFRecord,
    bytes,
    list[bytes],
    list[bytes],
]:
    """Parse the pinned uniform_logo outer entry and decode its two blocks."""

    archive = apf_outer.parse_archive(index_path)
    try:
        entry = archive.entries[entry_index]
    except IndexError as exc:
        raise PatchError(f"outer archive has no entry {entry_index}") from exc
    if len(entry.segments) != 1 or entry.segments[0].pack_name != "0A":
        raise PatchError("PORTME: uniform_logo target is not in one 0A segment")

    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        original_entry = reader.read(entry, 0, entry.size)
        original_blocks = [
            apf_inner.decode_block(reader, record, index, 1 << 30)
            for index in range(record.block_count)
        ]
        original_stored = [
            reader.read(entry, block.start_offset, block.stored_length)
            for block in record.blocks
        ]

    expected_entry = PINNED_ENTRIES.get(entry_index, {}).get("entry")
    if expected_entry is not None and sha256_bytes(original_entry) != expected_entry:
        raise PatchError(
            f"source entry {entry_index} does not match its pinned retail hash; "
            "refusing"
        )
    if record.file_count != 2 or record.block_count != 2:
        raise PatchError("PORTME: uniform_logo IFF structure changed")
    return archive, entry, record, original_entry, original_blocks, original_stored


def _extract_layer(
    record: apf_inner.IFFRecord,
    original_blocks: list[bytes],
    file_index: int,
    inner_name: str,
    expected_base_sha: str | None,
) -> _LayerTarget:
    """Validate one logo layer: DRAM/VRAM pairing, descriptor, base hash, transport."""

    try:
        target = record.files[file_index]
    except IndexError as exc:
        raise PatchError(f"IFF has no inner file {file_index}") from exc
    if target.name != inner_name or target.type_name != "TXTR":
        raise PatchError(
            f"expected {inner_name!r}/TXTR, got {target.name!r}/{target.type_name!r}"
        )
    if (
        len(target.parts) != 2
        or target.parts[0].block_index != 0
        or target.parts[1].block_index != 1
    ):
        raise PatchError(f"PORTME: {inner_name} TXTR DRAM/VRAM pairing changed")

    dram_part, vram_part = target.parts
    if dram_part.length != DRAM_PART_LEN:
        raise PatchError(
            f"PORTME: {inner_name} DRAM part is 0x{dram_part.length:x}, expected "
            f"0x{DRAM_PART_LEN:x}"
        )
    if vram_part.length != PAYLOAD_LEN:
        raise PatchError(
            f"PORTME: {inner_name} VRAM part is 0x{vram_part.length:x}, expected "
            f"0x{PAYLOAD_LEN:x}"
        )

    dram = original_blocks[0][dram_part.offset : dram_part.offset + dram_part.length]
    payload = original_blocks[1][vram_part.offset : vram_part.offset + PAYLOAD_LEN]
    if len(payload) != PAYLOAD_LEN:
        raise PatchError(f"{inner_name} VRAM payload does not cover base+mip tail")
    metadata = apf_inner.parse_txtr_metadata(dram)
    _strict_descriptor(metadata)

    base = payload[:BASE_LEN]
    mip_tail = payload[BASE_LEN:]
    if len(mip_tail) != MIP_LEN:
        raise PatchError(f"{inner_name} packed mip tail is not the expected length")
    if expected_base_sha is not None and sha256_bytes(base) != expected_base_sha:
        raise PatchError(f"decoded {inner_name} base hash is not the pinned retail data")

    # Transport gate: the Xenos untile/endian/tile path must round-trip the exact
    # retail base bytes before any edit to this layer is trusted.
    rgba = decode_4444_base(metadata, base)
    if encode_4444_base(metadata, rgba) != base:
        raise PatchError(
            f"Xenos 4_4_4_4 untile/endian/tile path is not bit-exact for {inner_name}"
        )
    return _LayerTarget(
        file_index=file_index,
        name=target.name,
        type_name=target.type_name,
        metadata=metadata,
        base=base,
        mip_tail=mip_tail,
        vram_offset=vram_part.offset,
        rgba=rgba,
    )


def read_logo_layers(
    index_path: Path,
    entry_index: int,
) -> tuple[bytes, bytes]:
    """Decode both retail crest layers without writing or copying a volume."""

    _archive, _entry, record, _raw, blocks, _stored = _open_entry(
        Path(index_path), entry_index
    )
    l0_index, l1_index = resolve_layer_indices(record)
    l0 = _extract_layer(
        record,
        blocks,
        l0_index,
        INNER_NAME,
        pinned_base_sha(entry_index, INNER_NAME),
    )
    l1 = _extract_layer(
        record,
        blocks,
        l1_index,
        SIBLING_NAME,
        pinned_base_sha(entry_index, SIBLING_NAME),
    )
    return l0.rgba, l1.rgba


def _recompress_rebuild_reparse(
    entry: apf_outer.Entry,
    record: apf_inner.IFFRecord,
    original_entry: bytes,
    original_blocks: list[bytes],
    original_stored: list[bytes],
    new_blocks: list[bytes],
) -> _RebuildResult:
    """Recompress changed blocks, rebuild the IFF in-allocation, and reparse-gate.

    Only blocks whose decoded bytes changed are re-H7A-compressed; the stored
    bytes of unchanged blocks are preserved verbatim (so, e.g., the DRAM block 0
    is never re-encoded).  The rebuilt entry is independently reparsed and its
    decoded blocks must equal ``new_blocks`` exactly.
    """

    new_stored: list[bytes] = []
    for block, orig_stored, orig_dec, new_dec in zip(
        record.blocks, original_stored, original_blocks, new_blocks
    ):
        if new_dec == orig_dec:
            new_stored.append(orig_stored)
            continue
        if not block.is_compressed:
            if len(new_dec) != block.uncompressed_length:
                raise PatchError("uncompressed IFF block changed allocation unexpectedly")
            new_stored.append(new_dec)
            continue
        if block.wrapper is None:
            raise PatchError("PORTME: logo VRAM block is not H7A-compressed")
        shift = block.wrapper.shift
        compressed = compress_h7a(new_dec, shift)
        stored = struct.pack(
            ">5I",
            apf_inner.H7A_MAGIC,
            len(new_dec),
            apf_inner.H7A_HEADER_SIZE + len(compressed),
            block.unknown_10,
            shift,
        ) + compressed
        if apf_inner.decompress_h7a(compressed, len(new_dec), shift) != new_dec:
            raise PatchError("H7A encode/decode round-trip failed")
        new_stored.append(stored)

    header = bytearray(original_entry[: record.header_size])
    body = bytearray()
    cursor = record.header_size
    block_report: list[dict[str, object]] = []
    for index, (block, stored) in enumerate(zip(record.blocks, new_stored)):
        start = cursor
        compressed_length = (
            len(stored) if block.is_compressed else block.uncompressed_length
        )
        if not block.is_compressed and len(stored) != block.uncompressed_length:
            raise PatchError("uncompressed IFF block changed allocation unexpectedly")
        struct.pack_into(
            ">8I",
            header,
            apf_inner.IFF_HEADER_SIZE + index * apf_inner.IFF_BLOCK_SIZE,
            block.name_hash,
            block.type_hash,
            block.unknown_08,
            block.uncompressed_length,
            block.unknown_10,
            start,
            compressed_length,
            block.indexed,
        )
        body.extend(stored)
        cursor += len(stored)
        block_report.append(
            {
                "index": index,
                "start_before": block.start_offset,
                "start_after": start,
                "stored_length_before": len(original_stored[index]),
                "stored_length_after": len(stored),
                "stored_sha256_before": sha256_bytes(original_stored[index]),
                "stored_sha256_after": sha256_bytes(stored),
                "decoded_sha256_before": sha256_bytes(original_blocks[index]),
                "decoded_sha256_after": sha256_bytes(new_blocks[index]),
            }
        )

    new_file_length = record.header_size + len(body)
    struct.pack_into(">I", header, 0x08, new_file_length)
    if record.footer is None:
        raise PatchError("PORTME: uniform_logo IFF has no validated name footer")
    footer_total = 8 + record.footer.payload_size
    footer_bytes = original_entry[
        record.file_length : record.file_length + footer_total
    ]
    old_tail = original_entry[record.file_length + footer_total :]
    if any(old_tail):
        raise PatchError("PORTME: uniform_logo outer allocation tail is nonzero")
    active = bytes(header) + bytes(body) + footer_bytes
    if len(active) > entry.size:
        raise PatchError(
            "rebuilt uniform_logo IFF exceeds its fixed outer allocation by "
            f"{len(active) - entry.size} bytes; refusing output"
        )
    rebuilt_entry = active + b"\0" * (entry.size - len(active))

    memory_reader = BytesReader(rebuilt_entry)
    rebuilt_record = apf_inner.parse_iff(memory_reader, entry)
    rebuilt_blocks = [
        apf_inner.decode_block(memory_reader, rebuilt_record, index, 1 << 30)
        for index in range(rebuilt_record.block_count)
    ]
    if rebuilt_blocks != new_blocks:
        raise PatchError("rebuilt uniform_logo IFF does not decode as intended")
    before_parts = _file_part_hashes(record, original_blocks)
    after_parts = _file_part_hashes(rebuilt_record, rebuilt_blocks)
    changed_parts = sorted(
        key for key in before_parts if before_parts[key] != after_parts[key]
    )
    footer_after = rebuilt_entry[new_file_length : new_file_length + footer_total]
    return _RebuildResult(
        rebuilt_entry=rebuilt_entry,
        new_file_length=new_file_length,
        footer_bytes=footer_bytes,
        footer_after=footer_after,
        footer_total=footer_total,
        active_len=len(active),
        block_report=block_report,
        before_parts=before_parts,
        after_parts=after_parts,
        changed_parts=changed_parts,
    )


def build_patch(
    index_path: Path,
    png_path: Path,
    entry_index: int = ENTRY_INDEX,
    file_index: int | None = None,
    png_path_l1: Path | None = None,
    file_index_l1: int | None = None,
    regenerate_mips: bool = True,
) -> PatchResult:
    """Build a rebuilt uniform_logo entry with ``logo_l0`` (and optionally ``logo_l1``).

    With ``png_path_l1`` omitted this writes only ``logo_l0`` (inner file 1) and
    byte-preserves the sibling ``logo_l1`` layer, exactly as before.  With
    ``png_path_l1`` supplied it co-writes both shared scorebug/crest sampler
    layers: both base levels are re-encoded, both 0x2C000 packed mip tails are
    regenerated from their corresponding edited base, and the single shared
    VRAM block is recompressed once inside the fixed outer allocation (or the
    writer fails closed).
    """

    archive, entry, record, original_entry, original_blocks, original_stored = (
        _open_entry(index_path, entry_index)
    )
    # Positions differ between crest packages, so name lookup is the default and
    # an explicit index is only an override.
    found_l0, found_l1 = resolve_layer_indices(record)
    if file_index is None:
        file_index = found_l0
    if file_index_l1 is None:
        file_index_l1 = found_l1
    if png_path_l1 is None:
        return _build_single_layer(
            index_path,
            png_path,
            entry_index,
            file_index,
            entry,
            record,
            original_entry,
            original_blocks,
            original_stored,
            regenerate_mips,
        )
    return _build_dual_layer(
        index_path,
        png_path,
        png_path_l1,
        entry_index,
        file_index,
        file_index_l1,
        entry,
        record,
        original_entry,
        original_blocks,
        original_stored,
        regenerate_mips,
    )


def _build_single_layer(
    index_path: Path,
    png_path: Path,
    entry_index: int,
    file_index: int,
    entry: apf_outer.Entry,
    record: apf_inner.IFFRecord,
    original_entry: bytes,
    original_blocks: list[bytes],
    original_stored: list[bytes],
    regenerate_mips: bool = True,
) -> PatchResult:
    target = _extract_layer(
        record, original_blocks, file_index, INNER_NAME,
        pinned_base_sha(entry_index, INNER_NAME),
    )
    metadata = target.metadata
    base = target.base
    mip_tail = target.mip_tail
    original_rgba = target.rgba
    wanted_rgba = _load_png(png_path, WIDTH, HEIGHT)

    common_source = {
        "archive_index": str(index_path),
        "physical_volume": entry.segments[0].pack_name,
        "outer_entry_index": entry_index,
        "outer_name": resolve_outer_name(entry),
        "inner_file_index": file_index,
        "inner_name": INNER_NAME,
        "entry_sha256": sha256_bytes(original_entry),
        "base_sha256": sha256_bytes(base),
        "png_rgba_sha256": sha256_bytes(wanted_rgba),
    }

    if wanted_rgba == original_rgba:
        manifest = {
            "schema": SCHEMA,
            "mode": "no_op",
            "source": common_source,
            "target": {
                "name": target.name,
                "type": target.type_name,
                "txtr": metadata,
            },
            "validation": {
                "xenos_transport_bit_exact": True,
                "input_matches_decoded_source": True,
                "entry_bit_exact": True,
                "mip_tail_preserved": True,
                "other_level_l1_preserved": True,
                "source_opened_read_only": True,
            },
            "backend": {
                "png": f"Pillow {PILLOW_VERSION}",
                "encoder": "not invoked for bit-exact no-op",
                "h7a": "not invoked for bit-exact no-op",
            },
            "portme": _PORTME,
        }
        return PatchResult(original_entry, manifest)

    new_base = encode_4444_base(metadata, wanted_rgba)
    # Same contract as the dual-layer path: regenerate the packed levels from
    # the new base, or a one-layer edit still serves the retail crest to every
    # draw smaller than mip 0.
    new_tail = (
        rebuild_mip_tail(metadata, wanted_rgba, mip_tail)
        if regenerate_mips else mip_tail
    )
    new_payload = new_base + new_tail
    if len(new_payload) != PAYLOAD_LEN:
        raise PatchError("payload length invariant failed")
    if not regenerate_mips and new_payload[BASE_LEN:] != mip_tail:
        raise PatchError("mip-tail preservation invariant failed")
    if new_base == base:
        raise PatchError("no-op detection was inconsistent: encode reproduced retail base")

    new_block1 = bytearray(original_blocks[1])
    new_block1[target.vram_offset : target.vram_offset + PAYLOAD_LEN] = new_payload
    new_blocks = [original_blocks[0], bytes(new_block1)]

    result = _recompress_rebuild_reparse(
        entry, record, original_entry, original_blocks, original_stored, new_blocks
    )
    if result.changed_parts != [(file_index, 1)]:
        raise PatchError(
            f"unrelated inner payload changed; changed part keys are "
            f"{result.changed_parts}"
        )

    shift = record.blocks[1].wrapper.shift  # type: ignore[union-attr]
    decoded_new_rgba = decode_4444_base(metadata, new_base)
    manifest = {
        "schema": SCHEMA,
        "mode": "patched",
        "source": common_source,
        "target": {
            "name": target.name,
            "type": target.type_name,
            "txtr": metadata,
            "sibling_layer": SIBLING_NAME,
        },
        "base_data": {
            "length": BASE_LEN,
            "sha256_before": sha256_bytes(base),
            "sha256_after": sha256_bytes(new_base),
            "decoded_rgba_sha256_before": sha256_bytes(original_rgba),
            "decoded_rgba_sha256_after": sha256_bytes(decoded_new_rgba),
            "decode_back_metrics": _rgba_metrics(wanted_rgba, decoded_new_rgba),
        },
        "mip_tail": {
            "length": MIP_LEN,
            "sha256": sha256_bytes(mip_tail),
            "sha256_after": sha256_bytes(new_tail),
            "bit_exact": new_tail == mip_tail,
            "regenerated": regenerate_mips,
        },
        "iff": {
            "allocation_size": entry.size,
            "file_length_before": record.file_length,
            "file_length_after": result.new_file_length,
            "allocation_slack_after": entry.size - result.active_len,
            "h7a_shift": shift,
            "footer_sha256_before": sha256_bytes(result.footer_bytes),
            "footer_sha256_after": sha256_bytes(result.footer_after),
            "footer_bit_exact": result.footer_after == result.footer_bytes,
            "blocks": result.block_report,
        },
        "binary_patch_manifest": {
            "physical_volume": entry.segments[0].pack_name,
            "physical_offset": entry.segments[0].pack_offset,
            "replacement_length": entry.size,
            "original_sha256": sha256_bytes(original_entry),
            "replacement_sha256": sha256_bytes(result.rebuilt_entry),
            **_changed_extents(original_entry, result.rebuilt_entry),
            "contains_replacement_bytes": False,
        },
        "validation": {
            "xenos_transport_bit_exact": True,
            "h7a_decode_encode_decode_exact": True,
            "rebuilt_iff_reparsed": True,
            "footer_bit_exact": result.footer_after == result.footer_bytes,
            "mip_tail_preserved": new_tail == mip_tail,
            "mip_tail_regenerated": regenerate_mips,
            "other_level_l1_preserved": result.before_parts[(0, 1)]
            == result.after_parts[(0, 1)],
            "unrelated_inner_part_count": len(result.before_parts) - 1,
            "unrelated_inner_parts_preserved": True,
            "changed_inner_parts": [
                {"file_index": file_index, "part_index": 1, "block_index": 1}
            ],
            "fixed_outer_allocation": True,
            "source_opened_read_only": True,
        },
        "backend": {
            "png": f"Pillow {PILLOW_VERSION}",
            "encoder": (
                "exact 4_4_4_4 nibble pack (uncompressed, lossless for retail; "
                "PNG->4bit quantized)"
            ),
            "encoder_caveat": PRODUCTION_ENCODER_CAVEAT,
            "h7a": "project-native greedy H7A encoder",
        },
        "portme": _PORTME,
    }
    return PatchResult(result.rebuilt_entry, manifest)


def _build_dual_layer_rgba_opened(
    index_path: Path,
    rgba_l0: bytes,
    rgba_l1: bytes,
    entry_index: int,
    file_index: int,
    file_index_l1: int,
    entry: apf_outer.Entry,
    record: apf_inner.IFFRecord,
    original_entry: bytes,
    original_blocks: list[bytes],
    original_stored: list[bytes],
    regenerate_mips: bool = True,
    extracted_layers: tuple[_LayerTarget, _LayerTarget] | None = None,
) -> PatchResult:
    if file_index == file_index_l1:
        raise PatchError("logo_l0 and logo_l1 must be distinct inner files")
    if extracted_layers is None:
        l0 = _extract_layer(
            record, original_blocks, file_index, INNER_NAME,
            pinned_base_sha(entry_index, INNER_NAME),
        )
        l1 = _extract_layer(
            record, original_blocks, file_index_l1, SIBLING_NAME,
            pinned_base_sha(entry_index, SIBLING_NAME),
        )
    else:
        l0, l1 = extracted_layers
        if (l0.file_index, l0.name, l1.file_index, l1.name) != (
            file_index, INNER_NAME, file_index_l1, SIBLING_NAME
        ):
            raise PatchError("predecoded dual-layer ownership differs")
    if len(rgba_l0) != WIDTH * HEIGHT * 4 or len(rgba_l1) != WIDTH * HEIGHT * 4:
        raise PatchError("dual-layer RGBA inputs must both be exactly 512x512")
    wanted = {l0.name: bytes(rgba_l0), l1.name: bytes(rgba_l1)}

    common_source = {
        "archive_index": str(index_path),
        "physical_volume": entry.segments[0].pack_name,
        "outer_entry_index": entry_index,
        "outer_name": resolve_outer_name(entry),
        "layers": [
            {"inner_file_index": layer.file_index, "inner_name": layer.name}
            for layer in (l0, l1)
        ],
        "entry_sha256": sha256_bytes(original_entry),
        "base_sha256": {l0.name: sha256_bytes(l0.base), l1.name: sha256_bytes(l1.base)},
        "png_rgba_sha256": {
            l0.name: sha256_bytes(wanted[l0.name]),
            l1.name: sha256_bytes(wanted[l1.name]),
        },
    }

    # Apply each layer edit into the shared VRAM block.
    new_block1 = bytearray(original_blocks[1])
    changed: list[tuple[_LayerTarget, bytes]] = []  # (layer, new_base)
    new_tails: dict[str, bytes] = {}
    for layer in (l0, l1):
        if wanted[layer.name] == layer.rgba:
            continue
        new_base = encode_4444_base(layer.metadata, wanted[layer.name])
        if new_base == layer.base:
            raise PatchError(
                f"no-op detection was inconsistent for {layer.name}: "
                "encode reproduced retail base"
            )
        if regenerate_mips:
            new_tail = rebuild_mip_tail(
                layer.metadata, wanted[layer.name], layer.mip_tail
            )
        else:
            new_tail = layer.mip_tail
        new_payload = new_base + new_tail
        if len(new_payload) != PAYLOAD_LEN:
            raise PatchError(f"payload length invariant failed for {layer.name}")
        if not regenerate_mips and new_payload[BASE_LEN:] != layer.mip_tail:
            raise PatchError(f"mip-tail preservation invariant failed for {layer.name}")
        new_block1[layer.vram_offset : layer.vram_offset + PAYLOAD_LEN] = new_payload
        changed.append((layer, new_base))
        new_tails[layer.name] = new_tail

    layers_report: dict[str, object] = {}
    for layer in (l0, l1):
        edited = any(layer is candidate for candidate, _ in changed)
        after_tail = new_tails.get(layer.name, layer.mip_tail)
        entry_report: dict[str, object] = {
            "file_index": layer.file_index,
            "vram_offset_in_block1": layer.vram_offset,
            "base_sha256_before": sha256_bytes(layer.base),
            "mip_tail_sha256": sha256_bytes(layer.mip_tail),
            "mip_tail_preserved": after_tail == layer.mip_tail,
            "mip_tail_regenerated": edited and regenerate_mips,
            "mip_tail_sha256_after": sha256_bytes(after_tail),
            "changed": edited,
        }
        layers_report[layer.name] = entry_report

    if not changed:
        manifest = {
            "schema": SCHEMA,
            "mode": "no_op",
            "source": common_source,
            "target": {
                "outer_name": resolve_outer_name(entry),
                "layers": [l0.name, l1.name],
                "shared_vram_block": True,
                "txtr": l0.metadata,
            },
            "layers": layers_report,
            "validation": {
                "xenos_transport_bit_exact": True,
                "input_matches_decoded_source": True,
                "entry_bit_exact": True,
                "mip_tails_preserved": True,
                "source_opened_read_only": True,
            },
            "backend": {
                "png": f"Pillow {PILLOW_VERSION}",
                "encoder": "not invoked for bit-exact no-op",
                "h7a": "not invoked for bit-exact no-op",
            },
            "portme": _PORTME,
        }
        return PatchResult(original_entry, manifest)

    new_blocks = [original_blocks[0], bytes(new_block1)]
    result = _recompress_rebuild_reparse(
        entry, record, original_entry, original_blocks, original_stored, new_blocks
    )
    expected_changed = sorted((layer.file_index, 1) for layer, _ in changed)
    if result.changed_parts != expected_changed:
        raise PatchError(
            f"unexpected inner payload change; changed part keys are "
            f"{result.changed_parts}, expected {expected_changed}"
        )

    # Fill in per-layer after-edit evidence for the layers that changed.
    for layer, new_base in changed:
        decoded_new_rgba = decode_4444_base(layer.metadata, new_base)
        report = layers_report[layer.name]
        assert isinstance(report, dict)
        report["base_data"] = {
            "length": BASE_LEN,
            "sha256_before": sha256_bytes(layer.base),
            "sha256_after": sha256_bytes(new_base),
            "decoded_rgba_sha256_after": sha256_bytes(decoded_new_rgba),
            "decode_back_metrics": _rgba_metrics(wanted[layer.name], decoded_new_rgba),
        }

    shift = record.blocks[1].wrapper.shift  # type: ignore[union-attr]
    changed_file_indices = {layer.file_index for layer, _ in changed}
    manifest = {
        "schema": SCHEMA,
        "mode": "patched",
        "source": common_source,
        "target": {
            "outer_name": resolve_outer_name(entry),
            "layers": [l0.name, l1.name],
            "shared_vram_block": True,
            "txtr": l0.metadata,
        },
        "layers": layers_report,
        "iff": {
            "allocation_size": entry.size,
            "file_length_before": record.file_length,
            "file_length_after": result.new_file_length,
            "allocation_slack_after": entry.size - result.active_len,
            "h7a_shift": shift,
            "footer_sha256_before": sha256_bytes(result.footer_bytes),
            "footer_sha256_after": sha256_bytes(result.footer_after),
            "footer_bit_exact": result.footer_after == result.footer_bytes,
            "blocks": result.block_report,
        },
        "binary_patch_manifest": {
            "physical_volume": entry.segments[0].pack_name,
            "physical_offset": entry.segments[0].pack_offset,
            "replacement_length": entry.size,
            "original_sha256": sha256_bytes(original_entry),
            "replacement_sha256": sha256_bytes(result.rebuilt_entry),
            **_changed_extents(original_entry, result.rebuilt_entry),
            "contains_replacement_bytes": False,
        },
        "validation": {
            "xenos_transport_bit_exact": True,
            "h7a_decode_encode_decode_exact": True,
            "rebuilt_iff_reparsed": True,
            "footer_bit_exact": result.footer_after == result.footer_bytes,
            "mip_tails_preserved": all(
                bool(report["mip_tail_preserved"])
                for report in layers_report.values()
                if isinstance(report, dict) and report["changed"]
            ),
            "edited_mip_tails_regenerated": regenerate_mips,
            "dram_headers_preserved": (
                result.before_parts[(l0.file_index, 0)]
                == result.after_parts[(l0.file_index, 0)]
                and result.before_parts[(l1.file_index, 0)]
                == result.after_parts[(l1.file_index, 0)]
            ),
            "changed_inner_parts": [
                {"file_index": layer.file_index, "part_index": 1, "block_index": 1}
                for layer, _ in changed
            ],
            "preserved_inner_parts": [
                {"file_index": layer.file_index, "part_index": 1, "block_index": 1}
                for layer in (l0, l1)
                if layer.file_index not in changed_file_indices
            ],
            "unrelated_inner_parts_preserved": True,
            "fixed_outer_allocation": True,
            "source_opened_read_only": True,
        },
        "backend": {
            "png": f"Pillow {PILLOW_VERSION}",
            "encoder": (
                "exact 4_4_4_4 nibble pack (uncompressed, lossless for retail; "
                "PNG->4bit quantized)"
            ),
            "encoder_caveat": PRODUCTION_ENCODER_CAVEAT,
            "h7a": "project-native greedy H7A encoder",
        },
        "portme": _PORTME,
    }
    return PatchResult(result.rebuilt_entry, manifest)


def _build_dual_layer(
    index_path: Path,
    png_path: Path,
    png_path_l1: Path,
    entry_index: int,
    file_index: int,
    file_index_l1: int,
    entry: apf_outer.Entry,
    record: apf_inner.IFFRecord,
    original_entry: bytes,
    original_blocks: list[bytes],
    original_stored: list[bytes],
    regenerate_mips: bool = True,
) -> PatchResult:
    """PNG boundary for the in-memory dual-layer writer."""

    return _build_dual_layer_rgba_opened(
        index_path,
        _load_png(png_path, WIDTH, HEIGHT),
        _load_png(png_path_l1, WIDTH, HEIGHT),
        entry_index,
        file_index,
        file_index_l1,
        entry,
        record,
        original_entry,
        original_blocks,
        original_stored,
        regenerate_mips,
    )


def build_patch_rgba(
    index_path: Path,
    rgba_l0: bytes,
    rgba_l1: bytes,
    *,
    entry_index: int,
    regenerate_mips: bool = True,
) -> PatchResult:
    """Rebuild both crest layers from RGBA without temporary PNG files."""

    archive, entry, record, original_entry, original_blocks, original_stored = (
        _open_entry(Path(index_path), entry_index)
    )
    del archive
    file_index, file_index_l1 = resolve_layer_indices(record)
    return _build_dual_layer_rgba_opened(
        Path(index_path),
        bytes(rgba_l0),
        bytes(rgba_l1),
        entry_index,
        file_index,
        file_index_l1,
        entry,
        record,
        original_entry,
        original_blocks,
        original_stored,
        regenerate_mips,
    )


@dataclass(frozen=True)
class _PreparedBatchBuild:
    """Pickle-safe, source-free input for one package rebuild worker."""

    index_path: Path
    rgba_l0: bytes
    rgba_l1: bytes
    entry_index: int
    file_index: int
    file_index_l1: int
    entry: apf_outer.Entry
    record: apf_inner.IFFRecord
    original_entry: bytes
    original_blocks: tuple[bytes, ...]
    original_stored: tuple[bytes, ...]
    regenerate_mips: bool
    extracted_layers: tuple[_LayerTarget, _LayerTarget]


def _build_prepared_batch_package(
    prepared: _PreparedBatchBuild,
) -> tuple[int, PatchResult]:
    """Process-worker seam: rebuild/reparse one already decoded package in RAM."""

    return prepared.entry_index, _build_dual_layer_rgba_opened(
        prepared.index_path,
        prepared.rgba_l0,
        prepared.rgba_l1,
        prepared.entry_index,
        prepared.file_index,
        prepared.file_index_l1,
        prepared.entry,
        prepared.record,
        prepared.original_entry,
        list(prepared.original_blocks),
        list(prepared.original_stored),
        prepared.regenerate_mips,
        prepared.extracted_layers,
    )


def build_patch_rgba_batch(
    index_path: Path,
    entry_indices: Iterable[int],
    transform: Callable[[int, bytes, bytes], tuple[bytes, bytes]],
    *,
    regenerate_mips: bool = True,
    max_workers: int = 1,
) -> dict[int, PatchResult]:
    """Decode, transform, and rebuild many crest packages in one archive pass.

    ``max_workers`` is deliberately bounded to four. The parent process remains
    the sole read-only archive owner and performs every source pin and atlas
    transform. Spawned workers receive only already-decoded bytes and rebuild
    one fixed package in RAM; at most twice the worker count is in flight, and
    results are returned in the caller's exact input order.
    """

    wanted_indices = tuple(entry_indices)
    if not wanted_indices or len(set(wanted_indices)) != len(wanted_indices):
        raise PatchError("batch crest entry indices must be nonempty and unique")
    if type(max_workers) is not int or not 1 <= max_workers <= 4:
        raise PatchError("batch crest max_workers must be an integer from 1 to 4")
    archive = apf_outer.parse_archive(Path(index_path))
    results: dict[int, PatchResult] = {}

    def prepare(
        reader: apf_inner.ArchiveReader, entry_index: int
    ) -> _PreparedBatchBuild:
        try:
            entry = archive.entries[entry_index]
        except IndexError as exc:
            raise PatchError(f"outer archive has no entry {entry_index}") from exc
        if len(entry.segments) != 1 or entry.segments[0].pack_name != "0A":
            raise PatchError("PORTME: uniform_logo target is not in one 0A segment")
        record = apf_inner.parse_iff(reader, entry)
        original_entry = reader.read(entry, 0, entry.size)
        original_blocks = [
            apf_inner.decode_block(reader, record, index, 1 << 30)
            for index in range(record.block_count)
        ]
        original_stored = [
            reader.read(entry, block.start_offset, block.stored_length)
            for block in record.blocks
        ]
        expected_entry = PINNED_ENTRIES.get(entry_index, {}).get("entry")
        if expected_entry is not None and sha256_bytes(original_entry) != expected_entry:
            raise PatchError(
                f"source entry {entry_index} does not match its pinned retail hash; refusing"
            )
        if record.file_count != 2 or record.block_count != 2:
            raise PatchError("PORTME: uniform_logo IFF structure changed")
        file_index, file_index_l1 = resolve_layer_indices(record)
        l0 = _extract_layer(
            record, original_blocks, file_index, INNER_NAME,
            pinned_base_sha(entry_index, INNER_NAME),
        )
        l1 = _extract_layer(
            record, original_blocks, file_index_l1, SIBLING_NAME,
            pinned_base_sha(entry_index, SIBLING_NAME),
        )
        rgba_l0, rgba_l1 = transform(entry_index, l0.rgba, l1.rgba)
        return _PreparedBatchBuild(
            Path(index_path), bytes(rgba_l0), bytes(rgba_l1), entry_index,
            file_index, file_index_l1, entry, record, original_entry,
            tuple(original_blocks), tuple(original_stored), regenerate_mips,
            (l0, l1),
        )

    with apf_inner.ArchiveReader(archive) as reader:
        if max_workers == 1:
            for entry_index in wanted_indices:
                rebuilt_index, result = _build_prepared_batch_package(
                    prepare(reader, entry_index)
                )
                results[rebuilt_index] = result
            return {entry_index: results[entry_index] for entry_index in wanted_indices}

        context = multiprocessing.get_context("spawn")
        pending: deque[tuple[int, Future[tuple[int, PatchResult]]]] = deque()

        def collect_oldest() -> None:
            expected_index, future = pending.popleft()
            rebuilt_index, result = future.result()
            if rebuilt_index != expected_index:
                raise PatchError("parallel crest worker returned the wrong package")
            results[rebuilt_index] = result

        # Context manager + explicit cancel on error so worker processes never
        # outlive the batch (monorepo suite hangs were contaminated by leftover
        # ProcessPool workers after parallel crest builds).
        with ProcessPoolExecutor(
            max_workers=max_workers, mp_context=context
        ) as executor:
            try:
                for entry_index in wanted_indices:
                    pending.append(
                        (
                            entry_index,
                            executor.submit(
                                _build_prepared_batch_package,
                                prepare(reader, entry_index),
                            ),
                        )
                    )
                    if len(pending) >= max_workers * 2:
                        collect_oldest()
                while pending:
                    collect_oldest()
            except BaseException:
                for _entry_index, future in pending:
                    future.cancel()
                raise
    return {entry_index: results[entry_index] for entry_index in wanted_indices}

# ---------------------------------------------------------------------------
# Output safety, copied verbatim from tools/apf_texture_patch.py:742-1031.
# ---------------------------------------------------------------------------
def _write_new(path: Path, data: bytes) -> None:
    reservation = _reserve_new(path)
    try:
        _commit_reserved(path, reservation, data)
    except Exception:
        _abort_reserved(path, reservation)
        raise
    _close_reserved(reservation)


def _preflight_output_paths(
    inputs: list[Path], outputs: list[tuple[str, Path | None]]
) -> None:
    """Refuse input/output aliases, duplicate outputs, and existing outputs."""
    input_keys = {path.expanduser().resolve(strict=False) for path in inputs}
    output_keys: dict[Path, str] = {}
    for label, optional_path in outputs:
        if optional_path is None:
            continue
        path = optional_path.expanduser()
        key = path.resolve(strict=False)
        if key in input_keys:
            raise PatchError(f"refusing {label} path that aliases an input: {path}")
        if key in output_keys:
            raise PatchError(
                f"refusing colliding output paths: {output_keys[key]} and {label}"
            )
        if os.path.lexists(path):
            raise PatchError(f"refusing to overwrite existing {label}: {path}")
        output_keys[key] = label


def _reserve_new(path: Path) -> OutputReservation:
    """Atomically reserve a new output pathname and capture its inode."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            path,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
            0o644,
        )
    except FileExistsError as exc:
        raise PatchError(f"refusing to overwrite existing output: {path}") from exc
    return OutputReservation(descriptor, _fd_identity(descriptor))


def _commit_reserved(
    path: Path, reservation: OutputReservation, data: bytes
) -> None:
    """Write/fsync the owned fd and require its pathname identity to survive."""
    os.ftruncate(reservation.descriptor, 0)
    _pwrite_all(reservation.descriptor, data, 0)
    os.ftruncate(reservation.descriptor, len(data))
    os.fsync(reservation.descriptor)
    if not _path_is_owned_inode(path, reservation.identity):
        raise PatchError("reserved output pathname changed during write")


def _close_reserved(reservation: OutputReservation) -> None:
    os.close(reservation.descriptor)


def _abort_reserved(path: Path, reservation: OutputReservation) -> None:
    """Close a failed reservation, deleting only its still-owned path.

    The order is deliberate and platform-dependent. On POSIX the unlink runs
    while the descriptor is still open: the fd keeps the inode alive, so no
    window exists in which the name could be swapped between the identity check
    and the unlink itself. Windows refuses to unlink a file any descriptor still
    holds open, and the resulting PermissionError is an OSError that
    ``_unlink_owned_path`` reports as "not removed" -- which is how a failed
    build there used to leave a stray partial output behind, so the next attempt
    hit "refusing to overwrite existing output" with nothing obviously wrong.
    Hence a second attempt after the close rather than a plain reorder: POSIX
    keeps its window-free guarantee, and Windows still gets cleaned up. The
    identity check guards both attempts, so neither can remove a file this
    reservation does not own.
    """
    removed = _unlink_owned_path(path, reservation.identity)
    try:
        os.close(reservation.descriptor)
    except OSError:
        pass
    if not removed:
        _unlink_owned_path(path, reservation.identity)


def _fd_identity(descriptor: int) -> tuple[int, int]:
    metadata = os.fstat(descriptor)
    return metadata.st_dev, metadata.st_ino


def _path_is_owned_inode(path: Path, identity: tuple[int, int]) -> bool:
    """Return true only when the directory entry itself is the owned inode."""
    try:
        metadata = os.stat(path, follow_symlinks=False)
    except OSError:
        return False
    return stat.S_ISREG(metadata.st_mode) and (
        metadata.st_dev,
        metadata.st_ino,
    ) == identity


def _unlink_owned_path(path: Path, identity: tuple[int, int]) -> bool:
    """Best-effort cleanup which never knowingly unlinks a replacement path."""
    if not _path_is_owned_inode(path, identity):
        return False
    try:
        path.unlink()
    except OSError:
        return False
    return True


def _pread_exact(descriptor: int, size: int, offset: int) -> bytes:
    if size < 0 or offset < 0:
        raise PatchError("negative descriptor read range")
    chunks: list[bytes] = []
    remaining = size
    cursor = offset
    while remaining:
        chunk = platform_compat.pread(descriptor, min(1024 * 1024, remaining), cursor)
        if not chunk:
            raise PatchError("unexpected end of file during descriptor read")
        chunks.append(chunk)
        cursor += len(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _pwrite_all(descriptor: int, data: bytes, offset: int) -> None:
    if offset < 0:
        raise PatchError("negative descriptor write offset")
    view = memoryview(data)
    written = 0
    while written < len(view):
        count = platform_compat.pwrite(descriptor, view[written:], offset + written)
        if count <= 0:
            raise PatchError("short descriptor write")
        written += count


def _sha256_fd_range(descriptor: int, offset: int, size: int) -> str:
    metadata = os.fstat(descriptor)
    if offset < 0 or size < 0 or offset + size > metadata.st_size:
        raise PatchError("descriptor hash range is out of bounds")
    digest = hashlib.sha256()
    remaining = size
    cursor = offset
    while remaining:
        chunk = platform_compat.pread(descriptor, min(1024 * 1024, remaining), cursor)
        if not chunk:
            raise PatchError("unexpected end of file during descriptor hash")
        digest.update(chunk)
        cursor += len(chunk)
        remaining -= len(chunk)
    return digest.hexdigest()


def _sha256_fd(descriptor: int) -> str:
    return _sha256_fd_range(descriptor, 0, os.fstat(descriptor).st_size)


def _copy_fd_metadata(
    source_descriptor: int,
    output_descriptor: int,
    source_metadata: os.stat_result,
) -> None:
    """Copy mode, available extended attributes, and timestamps by fd."""
    platform_compat.fchmod(
        output_descriptor, stat.S_IMODE(source_metadata.st_mode), path=None
    )
    if all(hasattr(os, name) for name in ("listxattr", "getxattr", "setxattr")):
        try:
            names = os.listxattr(source_descriptor)
        except OSError:
            names = []
        for name in names:
            try:
                value = os.getxattr(source_descriptor, name)
                os.setxattr(output_descriptor, name, value)
            except OSError:
                # Match shutil.copystat's best-effort behavior for attributes
                # unavailable to the current user or destination filesystem.
                continue
    os.utime(
        output_descriptor,
        ns=(source_metadata.st_atime_ns, source_metadata.st_mtime_ns),
    )


def _write_copied_volume(
    source_volume: Path,
    output_volume: Path,
    entry: apf_outer.Entry,
    replacement: bytes,
) -> dict[str, object]:
    if source_volume.resolve() == output_volume.resolve():
        raise PatchError("refusing to patch the source APF volume")
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

        prefix_length = entry.segments[0].pack_offset
        suffix_offset = prefix_length + len(replacement)
        if prefix_length < 0 or suffix_offset > source_size:
            raise PatchError("replacement entry range is outside the copied volume")
        before = _pread_exact(output_descriptor, len(replacement), prefix_length)
        mode = (
            "bit_exact_no_op"
            if sha256_bytes(before) == sha256_bytes(replacement)
            else "replaced_entry"
        )
        _pwrite_all(output_descriptor, replacement, prefix_length)
        os.fsync(output_descriptor)

        if os.fstat(output_descriptor).st_size != source_size:
            raise PatchError("copied volume size changed")
        written = _pread_exact(output_descriptor, len(replacement), prefix_length)
        if written != replacement:
            raise PatchError("copied-volume read-back does not match replacement entry")
        suffix_length = source_size - suffix_offset
        source_prefix_sha = _sha256_fd_range(source_descriptor, 0, prefix_length)
        output_prefix_sha = _sha256_fd_range(output_descriptor, 0, prefix_length)
        source_suffix_sha = _sha256_fd_range(
            source_descriptor, suffix_offset, suffix_length
        )
        output_suffix_sha = _sha256_fd_range(
            output_descriptor, suffix_offset, suffix_length
        )
        if source_prefix_sha != output_prefix_sha or source_suffix_sha != output_suffix_sha:
            raise PatchError("bytes outside the selected entry changed in the copied volume")
        output_sha = _sha256_fd(output_descriptor)
        source_sha_after = _sha256_fd(source_descriptor)
        if source_sha_after != source_sha_before:
            raise PatchError("source APF volume changed during copied-volume patch")
        if not _path_is_owned_inode(source_volume, source_identity):
            raise PatchError("source APF volume pathname changed during copy")

        _copy_fd_metadata(source_descriptor, output_descriptor, source_metadata)
        os.fsync(output_descriptor)
        if not _path_is_owned_inode(output_volume, output_identity):
            raise PatchError("output volume pathname changed during copied-volume patch")
        return {
            "mode": mode,
            "source_volume": str(source_volume),
            "output_volume": str(output_volume),
            "volume_size": source_size,
            "replacement_read_back_sha256": sha256_bytes(written),
            "source_volume_sha256_before": source_sha_before,
            "source_volume_sha256_after": source_sha_after,
            "output_volume_sha256": output_sha,
            "outside_replacement": {
                "prefix_length": prefix_length,
                "prefix_sha256": source_prefix_sha,
                "suffix_offset": suffix_offset,
                "suffix_length": suffix_length,
                "suffix_sha256": source_suffix_sha,
                "source_and_output_match": True,
            },
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
    parser.add_argument(
        "--png", required=True, type=Path, help="edited 512x512 RGBA PNG for logo_l0"
    )
    parser.add_argument(
        "--png-l1",
        type=Path,
        help="optional edited 512x512 RGBA PNG for logo_l1; co-writes both shared layers",
    )
    parser.add_argument("--entry-index", type=int, default=ENTRY_INDEX)
    # Left unset the layers are found by name, which is what makes the writer
    # work on every crest package rather than only the one whose inner-file
    # order these constants happen to describe.
    parser.add_argument(
        "--preserve-mips",
        action="store_true",
        help="keep the retail packed mip tail byte-for-byte instead of "
             "regenerating it from the new base; the crest will then still "
             "show the retail logo at any draw smaller than full size",
    )
    parser.add_argument("--file-index", type=int, default=None)
    parser.add_argument("--file-index-l1", type=int, default=None)
    parser.add_argument("--output-entry", type=Path, help="write rebuilt logical IFF entry")
    parser.add_argument(
        "--output-volume",
        type=Path,
        help="copy 0A to this new path, then replace only the fixed logo entry",
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
        png_path_l1 = args.png_l1.expanduser() if args.png_l1 is not None else None
        output_entry = (
            args.output_entry.expanduser() if args.output_entry is not None else None
        )
        output_volume = (
            args.output_volume.expanduser() if args.output_volume is not None else None
        )
        inputs = [index_path, png_path]
        if png_path_l1 is not None:
            inputs.append(png_path_l1)
        _preflight_output_paths(
            inputs,
            [("manifest", manifest_path), ("output entry", output_entry),
             ("output volume", output_volume)],
        )
        manifest_reservation = _reserve_new(manifest_path)
        result = build_patch(
            index_path,
            png_path,
            args.entry_index,
            args.file_index,
            png_path_l1=png_path_l1,
            file_index_l1=args.file_index_l1,
            regenerate_mips=not args.preserve_mips,
        )
        archive = apf_outer.parse_archive(index_path)
        entry = archive.entries[args.entry_index]
        document = result.manifest
        if output_entry is not None:
            _write_new(output_entry, result.entry_bytes)
            document["output_entry"] = {
                "path": str(output_entry),
                "sha256": sha256_bytes(result.entry_bytes),
                "size": len(result.entry_bytes),
            }
        if output_volume is not None:
            document["copied_volume"] = _write_copied_volume(
                index_path,
                output_volume,
                entry,
                result.entry_bytes,
            )
        _commit_reserved(
            manifest_path,
            manifest_reservation,
            (json.dumps(document, indent=2) + "\n").encode("utf-8"),
        )
        _close_reserved(manifest_reservation)
        manifest_reservation = None
        layers = "l0+l1" if png_path_l1 is not None else "l0"
        print(
            "APF_LOGO_PATCH_PASS "
            f"mode={document['mode']} entry={args.entry_index} layers={layers} "
            f"sha256={sha256_bytes(result.entry_bytes)}"
        )
    except (PatchError, apf_inner.FormatError, apf_outer.FormatError, OSError) as exc:
        if manifest_reservation is not None:
            _abort_reserved(manifest_path, manifest_reservation)
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Safely replace one proven APF 2K8 tiled BC3 texture in a copied archive.

This is deliberately a narrow first writer, not a general APF repacker.  It
accepts the retail archive supplied by the user and an RGBA PNG, preserves
unchanged BC3 blocks, recompresses only the containing H7A block, rebuilds the
IFF block offsets/footer placement, and optionally applies the rebuilt logical
entry to a newly copied volume.  The source volume is never opened for write.

The evidence-backed initial target is outer entry 810 (``franchise.iff``),
inner file 117 (``draft_logo``): tiled 128x128 Xenos DXT4_5/BC3, 8-in-16,
identity swizzle, one base level, no mips.  Unsupported descriptor variants are
rejected with PORTME errors rather than guessed.
"""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
import sys
from typing import Iterable

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mod_editor.core import platform_compat  # noqa: E402

try:
    from PIL import Image, __version__ as PILLOW_VERSION
except ImportError as exc:  # pragma: no cover - exercised by the CLI error path.
    raise SystemExit("error: Pillow is required for PNG import") from exc

# The shipped Windows runtime is an embeddable CPython whose ._pth file
# defines sys.path outright and, unlike a normal interpreter, does NOT add
# this script's own directory -- so the sibling imports below fail there
# with ModuleNotFoundError unless the directory is put back explicitly.
import sys as _sys
from pathlib import Path as _Path
_here = str(_Path(__file__).resolve().parent)
if _here not in _sys.path:
    _sys.path.insert(0, _here)

import apf_inner
import apf_outer


SCHEMA = "apf_texture_patch/v1"
DEFAULT_ENTRY_INDEX = 810
DEFAULT_FILE_INDEX = 117
DEFAULT_NAME = "draft_logo"
MAX_H7A_CANDIDATES = 256


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_range(path: Path, offset: int, size: int) -> str:
    if offset < 0 or size < 0 or offset + size > path.stat().st_size:
        raise PatchError("file hash range is out of bounds")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        stream.seek(offset)
        remaining = size
        while remaining:
            chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk:
                raise PatchError("short read while hashing file range")
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest()


def _rgb565_encode(red: int, green: int, blue: int) -> int:
    return (
        ((red * 31 + 127) // 255) << 11
        | ((green * 63 + 127) // 255) << 5
        | ((blue * 31 + 127) // 255)
    )


def _color_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return sum((a[index] - b[index]) ** 2 for index in range(3))


def encode_bc3_block(pixels: list[tuple[int, int, int, int]]) -> bytes:
    """Encode one 4x4 RGBA block as deterministic, valid BC3.

    The endpoint search is intentionally small and inspectable.  This proof
    writer preserves every unchanged source block, so this provisional encoder
    affects only 4x4 blocks touched by an edit.  A production importer should
    replace it with a perceptual high-quality BC3 backend.
    """

    if len(pixels) != 16:
        raise PatchError("BC3 input must contain exactly 16 pixels")
    if any(len(pixel) != 4 or any(not 0 <= value <= 255 for value in pixel) for pixel in pixels):
        raise PatchError("BC3 input contains an invalid RGBA value")

    alphas_in = [pixel[3] for pixel in pixels]
    alpha_0 = max(alphas_in)
    alpha_1 = min(alphas_in)
    if alpha_0 > alpha_1:
        alpha_palette = [alpha_0, alpha_1]
        alpha_palette.extend(
            (alpha_0 * (7 - index) + alpha_1 * index) // 7
            for index in range(1, 7)
        )
    else:
        alpha_palette = [alpha_0, alpha_1, alpha_0, alpha_0, alpha_0, alpha_0, 0, 255]
    alpha_indices = 0
    for index, alpha in enumerate(alphas_in):
        selector = min(
            range(8),
            key=lambda candidate: (abs(alpha - alpha_palette[candidate]), candidate),
        )
        alpha_indices |= selector << (index * 3)

    colors = [(pixel[0], pixel[1], pixel[2]) for pixel in pixels]
    endpoint_a = colors[0]
    endpoint_b = colors[0]
    best_distance = -1
    for first in range(16):
        for second in range(first + 1, 16):
            distance = _color_distance(colors[first], colors[second])
            if distance > best_distance:
                best_distance = distance
                endpoint_a, endpoint_b = colors[first], colors[second]
    color_0 = _rgb565_encode(*endpoint_a)
    color_1 = _rgb565_encode(*endpoint_b)
    # BC3 always uses the four-color interpretation.  Ordering the endpoints
    # makes the serialized block conventional and deterministic.
    if color_0 < color_1:
        color_0, color_1 = color_1, color_0
    palette_rgba, _ = apf_inner._bc_color_table(  # type: ignore[attr-defined]
        struct.pack("<HHI", color_0, color_1, 0), True
    )
    palette = [entry[:3] for entry in palette_rgba]
    color_indices = 0
    for index, color in enumerate(colors):
        selector = min(
            range(4),
            key=lambda candidate: (_color_distance(color, palette[candidate]), candidate),
        )
        color_indices |= selector << (index * 2)

    return (
        bytes((alpha_0, alpha_1))
        + alpha_indices.to_bytes(6, "little")
        + struct.pack("<HHI", color_0, color_1, color_indices)
    )


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
                        # writing.  Our decoder copies one byte at a time and so
                        # reproduces an overlapping run correctly, which is why
                        # this round-trips offline while the rebuilt asset comes
                        # back as fine speckle in game.  Retail settles it: the
                        # shipped 512x512 crest block holds 36,099 matches and
                        # not one overlaps, where a plain greedy encoder emits
                        # nearly eleven thousand, almost all at distance 2.
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


# Greedy parsing is normally both fast and small enough for APF's fixed outer
# allocations.  A handful of large textures sit within a few hundred bytes of
# their bounds after a safe (non-overlapping) edit, however, and require a
# minimum-cost parse.  Keep the slower encoder out of the common path: callers
# first try ``compress_h7a`` and pass that result back here only when it does
# not fit.
_OPTIMAL_BINARY = Path(__file__).resolve().parent / "apf_h7a_optimal"
_OPTIMAL_BINARY_SIZE = 14_472
_OPTIMAL_BINARY_SHA256 = (
    "9061866e31f1a2930eceaa4fb8652ef1b7aa9b04cbce0174cc0eae125f8e49ab"
)


def _optimal_binary() -> Path | None:
    """Return the exact reviewed Linux encoder bundled with the editor."""
    import platform

    if not sys.platform.startswith("linux") or platform.machine() not in {
        "x86_64",
        "amd64",
    }:
        return None
    try:
        info = _OPTIMAL_BINARY.lstat()
    except OSError:
        return None
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_nlink != 1
        or info.st_size != _OPTIMAL_BINARY_SIZE
        or info.st_mode & 0o022
        or not info.st_mode & stat.S_IXUSR
    ):
        return None
    if sha256_file(_OPTIMAL_BINARY) != _OPTIMAL_BINARY_SHA256:
        return None
    return _OPTIMAL_BINARY


def compress_h7a_best(
    data: bytes,
    shift: int,
    *,
    greedy: bytes | None = None,
) -> bytes:
    """Return the smaller verified safe parse, never worse than ``greedy``."""
    import subprocess

    baseline = compress_h7a(data, shift) if greedy is None else greedy
    binary = _optimal_binary()
    if binary is None:
        return baseline
    try:
        finished = subprocess.run(
            [str(binary), str(shift)],
            input=data,
            capture_output=True,
            timeout=180,
        )
    except (OSError, subprocess.SubprocessError):
        return baseline
    candidate = finished.stdout
    if (
        finished.returncode != 0
        or not candidate
        or len(candidate) >= len(baseline)
    ):
        return baseline
    try:
        if apf_inner.decompress_h7a(candidate, len(data), shift) != data:
            return baseline
    except Exception:  # noqa: BLE001 - any decode failure means fall back
        return baseline
    return candidate


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


def build_patch(index_path: Path, png_path: Path, entry_index: int, file_index: int) -> PatchResult:
    archive = apf_outer.parse_archive(index_path)
    try:
        entry = archive.entries[entry_index]
    except IndexError as exc:
        raise PatchError(f"outer archive has no entry {entry_index}") from exc
    if len(entry.segments) != 1:
        raise PatchError("PORTME: patch target spans multiple APF volumes")

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

    try:
        target = record.files[file_index]
    except IndexError as exc:
        raise PatchError(f"IFF has no inner file {file_index}") from exc
    if target.name != DEFAULT_NAME or target.type_name != "TXTR":
        raise PatchError(
            f"narrow writer expected {DEFAULT_NAME!r}/TXTR, got "
            f"{target.name!r}/{target.type_name!r}"
        )
    if len(target.parts) != 2 or target.parts[0].block_index != 0 or target.parts[1].block_index != 1:
        raise PatchError("PORTME: target TXTR does not use the proved DRAM/VRAM pairing")

    dram_part, vram_part = target.parts
    dram = original_blocks[dram_part.block_index][
        dram_part.offset : dram_part.offset + dram_part.length
    ]
    original_base = original_blocks[vram_part.block_index][
        vram_part.offset : vram_part.offset + vram_part.length
    ]
    metadata = apf_inner.parse_txtr_metadata(dram)
    required = {
        "width": 128,
        "height": 128,
        "pitch_pixels": 128,
        "format": 20,
        "endianness": 1,
        "tiled": True,
        "stacked": False,
        "dimension": 1,
        "vc_base_data_length": 16384,
        "vc_mip_data_length": 0,
        "mip_min_level": 0,
        "mip_max_level": 0,
        "packed_mips": False,
    }
    disagreements = {
        key: (metadata.get(key), expected)
        for key, expected in required.items()
        if metadata.get(key) != expected
    }
    if disagreements:
        raise PatchError(f"PORTME: target TXTR descriptor changed: {disagreements}")
    if list(metadata["swizzle_components"]) != [0, 1, 2, 3]:
        raise PatchError("PORTME: initial target no longer has identity RGBA swizzle")
    if vram_part.length != int(metadata["vc_base_data_length"]):
        raise PatchError("TXTR VRAM part length does not equal declared base allocation")

    width = int(metadata["width"])
    height = int(metadata["height"])
    original_width, original_height, original_rgba = apf_inner.decode_txtr_base_rgba(
        metadata, original_base
    )
    if (original_width, original_height) != (width, height):
        raise PatchError("forward decoder returned inconsistent dimensions")
    wanted_rgba = _load_png(png_path, width, height)
    raw_wanted_pixels = _inverse_swizzle_pixels(
        wanted_rgba, metadata["swizzle_components"]  # type: ignore[arg-type]
    )

    tiled_linear = apf_inner._untile_2d(  # type: ignore[attr-defined]
        original_base, width, height, int(metadata["pitch_pixels"]), 4, 4, 16
    )
    original_linear_bc3 = apf_inner._endian_swap(  # type: ignore[attr-defined]
        tiled_linear, int(metadata["endianness"])
    )
    transport_roundtrip = _tile_2d(
        apf_inner._endian_swap(  # type: ignore[attr-defined]
            original_linear_bc3, int(metadata["endianness"])
        ),
        width,
        height,
        int(metadata["pitch_pixels"]),
        4,
        4,
        16,
        len(original_base),
    )
    if transport_roundtrip != original_base:
        raise PatchError("Xenos untile/endian/inverse path is not bit-exact")

    width_blocks = width // 4
    height_blocks = height // 4
    new_linear_bc3 = bytearray(original_linear_bc3)
    changed_blocks: list[int] = []
    for block_y in range(height_blocks):
        for block_x in range(width_blocks):
            pixel_indices = [
                (block_y * 4 + local_y) * width + block_x * 4 + local_x
                for local_y in range(4)
                for local_x in range(4)
            ]
            if all(
                wanted_rgba[index * 4 : index * 4 + 4]
                == original_rgba[index * 4 : index * 4 + 4]
                for index in pixel_indices
            ):
                continue
            block_index = block_y * width_blocks + block_x
            encoded = encode_bc3_block([raw_wanted_pixels[index] for index in pixel_indices])
            start = block_index * 16
            new_linear_bc3[start : start + 16] = encoded
            changed_blocks.append(block_index)

    new_base = _tile_2d(
        apf_inner._endian_swap(  # type: ignore[attr-defined]
            bytes(new_linear_bc3), int(metadata["endianness"])
        ),
        width,
        height,
        int(metadata["pitch_pixels"]),
        4,
        4,
        16,
        len(original_base),
    )

    if not changed_blocks:
        if wanted_rgba != original_rgba or new_base != original_base:
            raise PatchError("no-op detection was inconsistent")
        manifest = {
            "schema": SCHEMA,
            "mode": "no_op",
            "source": {
                "archive_index": str(index_path),
                "outer_entry_index": entry_index,
                "inner_file_index": file_index,
                "entry_sha256": sha256_bytes(original_entry),
                "png_rgba_sha256": sha256_bytes(wanted_rgba),
            },
            "target": {"name": target.name, "type": target.type_name, "txtr": metadata},
            "validation": {
                "xenos_transport_bit_exact": True,
                "input_matches_decoded_source": True,
                "entry_bit_exact": True,
                "unrelated_inner_parts_preserved": True,
            },
            "backend": {
                "png": f"Pillow {PILLOW_VERSION}",
                "bc3": "project-native deterministic touched-block encoder",
                "h7a": "not invoked for bit-exact no-op",
            },
            "portme": [
                "generalize beyond the pinned draft_logo descriptor",
                "replace the provisional BC3 endpoint search with a perceptual production encoder",
            ],
        }
        return PatchResult(original_entry, manifest)

    new_blocks = list(original_blocks)
    patched_vram_block = bytearray(new_blocks[vram_part.block_index])
    patched_vram_block[
        vram_part.offset : vram_part.offset + vram_part.length
    ] = new_base
    new_blocks[vram_part.block_index] = bytes(patched_vram_block)

    changed_block_index = vram_part.block_index
    changed_descriptor = record.blocks[changed_block_index]
    if not changed_descriptor.is_compressed or changed_descriptor.wrapper is None:
        raise PatchError("PORTME: target VRAM block is not H7A-compressed")
    compressed_payload = compress_h7a(
        new_blocks[changed_block_index], changed_descriptor.wrapper.shift
    )
    new_stored = list(original_stored)
    new_stored[changed_block_index] = struct.pack(
        ">5I",
        apf_inner.H7A_MAGIC,
        len(new_blocks[changed_block_index]),
        apf_inner.H7A_HEADER_SIZE + len(compressed_payload),
        changed_descriptor.unknown_10,
        changed_descriptor.wrapper.shift,
    ) + compressed_payload
    if apf_inner.decompress_h7a(
        compressed_payload,
        len(new_blocks[changed_block_index]),
        changed_descriptor.wrapper.shift,
    ) != new_blocks[changed_block_index]:
        raise PatchError("H7A encode/decode round-trip failed")

    rebuilt_header = bytearray(original_entry[: record.header_size])
    cursor = record.header_size
    rebuilt_body = bytearray()
    block_manifest: list[dict[str, object]] = []
    for index, (descriptor, stored) in enumerate(zip(record.blocks, new_stored)):
        old_start = descriptor.start_offset
        new_start = cursor
        new_compressed_length = len(stored) if descriptor.is_compressed else descriptor.uncompressed_length
        if not descriptor.is_compressed and len(stored) != descriptor.uncompressed_length:
            raise PatchError("uncompressed IFF block changed allocation unexpectedly")
        struct.pack_into(
            ">8I",
            rebuilt_header,
            apf_inner.IFF_HEADER_SIZE + index * apf_inner.IFF_BLOCK_SIZE,
            descriptor.name_hash,
            descriptor.type_hash,
            descriptor.unknown_08,
            descriptor.uncompressed_length,
            descriptor.unknown_10,
            new_start,
            new_compressed_length,
            descriptor.indexed,
        )
        rebuilt_body.extend(stored)
        cursor += len(stored)
        block_manifest.append(
            {
                "index": index,
                "decoded_sha256_before": sha256_bytes(original_blocks[index]),
                "decoded_sha256_after": sha256_bytes(new_blocks[index]),
                "stored_sha256_before": sha256_bytes(original_stored[index]),
                "stored_sha256_after": sha256_bytes(stored),
                "stored_length_before": len(original_stored[index]),
                "stored_length_after": len(stored),
                "start_before": old_start,
                "start_after": new_start,
            }
        )

    new_file_length = record.header_size + len(rebuilt_body)
    struct.pack_into(">I", rebuilt_header, 0x08, new_file_length)
    if record.footer is None:
        raise PatchError("PORTME: target IFF has no validated name footer")
    footer_total = 8 + record.footer.payload_size
    footer_bytes = original_entry[
        record.file_length : record.file_length + footer_total
    ]
    old_padding = original_entry[record.file_length + footer_total :]
    if any(old_padding):
        raise PatchError("PORTME: outer entry tail contains nonzero allocation data")
    active = bytes(rebuilt_header) + bytes(rebuilt_body) + footer_bytes
    if len(active) > entry.size:
        raise PatchError(
            f"rebuilt IFF exceeds fixed outer allocation by {len(active) - entry.size} bytes"
        )
    rebuilt_entry = active + b"\0" * (entry.size - len(active))

    memory_reader = BytesReader(rebuilt_entry)
    rebuilt_record = apf_inner.parse_iff(memory_reader, entry)
    rebuilt_blocks = [
        apf_inner.decode_block(memory_reader, rebuilt_record, index, 1 << 30)
        for index in range(rebuilt_record.block_count)
    ]
    if rebuilt_blocks != new_blocks:
        raise PatchError("rebuilt IFF does not decode to the intended block corpus")
    before_parts = _file_part_hashes(record, original_blocks)
    after_parts = _file_part_hashes(rebuilt_record, rebuilt_blocks)
    changed_parts = [key for key in before_parts if before_parts[key] != after_parts[key]]
    expected_changed_part = (file_index, 1)
    if changed_parts != [expected_changed_part]:
        raise PatchError(
            f"unrelated inner payload changed; changed part keys are {changed_parts}"
        )

    _, _, decoded_new_rgba = apf_inner.decode_txtr_base_rgba(metadata, new_base)
    manifest = {
        "schema": SCHEMA,
        "mode": "patched",
        "source": {
            "archive_index": str(index_path),
            "outer_entry_index": entry_index,
            "inner_file_index": file_index,
            "entry_sha256": sha256_bytes(original_entry),
            "png_rgba_sha256": sha256_bytes(wanted_rgba),
        },
        "target": {
            "name": target.name,
            "type": target.type_name,
            "txtr": metadata,
            "changed_bc3_block_count": len(changed_blocks),
            "changed_bc3_block_indices": changed_blocks,
            "base_data_sha256_before": sha256_bytes(original_base),
            "base_data_sha256_after": sha256_bytes(new_base),
            "decoded_rgba_sha256_before": sha256_bytes(original_rgba),
            "decoded_rgba_sha256_after": sha256_bytes(decoded_new_rgba),
            "decode_back_metrics": _rgba_metrics(wanted_rgba, decoded_new_rgba),
        },
        "iff": {
            "allocation_size": entry.size,
            "file_length_before": record.file_length,
            "file_length_after": new_file_length,
            "footer_sha256_before": sha256_bytes(footer_bytes),
            "footer_sha256_after": sha256_bytes(
                rebuilt_entry[new_file_length : new_file_length + footer_total]
            ),
            "blocks": block_manifest,
        },
        "binary_patch_manifest": {
            "physical_volume": entry.segments[0].pack_name,
            "physical_offset": entry.segments[0].pack_offset,
            "replacement_length": entry.size,
            "original_sha256": sha256_bytes(original_entry),
            "replacement_sha256": sha256_bytes(rebuilt_entry),
            **_changed_extents(original_entry, rebuilt_entry),
            "contains_replacement_bytes": False,
        },
        "validation": {
            "xenos_transport_bit_exact": True,
            "h7a_decode_encode_decode_exact": True,
            "rebuilt_iff_reparsed": True,
            "footer_bit_exact": True,
            "unrelated_inner_part_count": len(before_parts) - 1,
            "unrelated_inner_parts_preserved": True,
            "changed_inner_parts": [
                {"file_index": file_index, "part_index": 1, "block_index": 1}
            ],
        },
        "backend": {
            "png": f"Pillow {PILLOW_VERSION}",
            "bc3": "project-native deterministic touched-block encoder",
            "h7a": "project-native greedy H7A encoder",
        },
        "portme": [
            "generalize beyond the pinned draft_logo descriptor",
            "replace the provisional BC3 endpoint search with a perceptual production encoder",
            "validate the copied volume in Xenia and on hardware before calling the archive patch runtime-proved",
            "implement mip generation, non-BC3 formats, nonidentity swizzles, arrays, cubes, 3D and packed mip tails",
        ],
    }
    return PatchResult(rebuilt_entry, manifest)


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
        source_prefix_sha = _sha256_fd_range(
            source_descriptor, 0, prefix_length
        )
        output_prefix_sha = _sha256_fd_range(
            output_descriptor, 0, prefix_length
        )
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
    parser.add_argument("--index", required=True, type=Path, help="user-supplied APF 0A")
    parser.add_argument("--png", required=True, type=Path, help="edited 128x128 RGBA PNG")
    parser.add_argument("--entry-index", type=int, default=DEFAULT_ENTRY_INDEX)
    parser.add_argument("--file-index", type=int, default=DEFAULT_FILE_INDEX)
    parser.add_argument("--output-entry", type=Path, help="write rebuilt logical IFF entry")
    parser.add_argument(
        "--output-volume",
        type=Path,
        help="copy 0A to this new path, then replace the fixed entry in the copy",
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
        output_entry = (
            args.output_entry.expanduser() if args.output_entry is not None else None
        )
        output_volume = (
            args.output_volume.expanduser() if args.output_volume is not None else None
        )
        _preflight_output_paths(
            [index_path, png_path],
            [("manifest", manifest_path), ("output entry", output_entry),
             ("output volume", output_volume)],
        )
        manifest_reservation = _reserve_new(manifest_path)
        result = build_patch(
            index_path,
            png_path,
            args.entry_index,
            args.file_index,
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
        print(
            "APF_TEXTURE_PATCH_PASS "
            f"mode={document['mode']} entry={args.entry_index} file={args.file_index} "
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

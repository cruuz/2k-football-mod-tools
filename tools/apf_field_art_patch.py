#!/usr/bin/env python3
"""Safely replace one proven APF 2K8 field-art base texture in a copied volume.

This is an evidence-bounded, fail-closed writer for the *writable* field-art
``TXTR`` families enumerated in ``mod_editor/apf_studio/field_art.py``.  Every
target is pinned by a frozen per-slot contract (outer entry, inner file, Xenos
descriptor, base/mip lengths, part layout, and retail entry/base SHA-256); the
writer refuses anything that disagrees with its pin.  It rewrites only the base
mip level of one texture, byte-preserves the descriptor pad, the packed mip
tail, and every sibling inner part, recompresses only the single containing H7A
block, rebuilds the IFF inside its fixed outer allocation, independently
reparses the rebuilt entry in RAM, and can only ever write a newly *copied* 0A
volume.  The retail source is never opened for writing.

Shipped families (proved bit-exact this session against
``All-Pro Football 2K8 (USA)``):

* ``endzone_l0`` / ``endzone_l1`` -- Xenos DXT1 (format 18), 2048x512, identity
  swizzle, shared VRAM block, packed mip tail (the money asset).
* ``pc_field_goal`` -- Xenos DXT1 (format 18), 256x256, packed mip tail.
* ``Field_Pass_text`` / ``Stride_number_field`` -- Xenos DXT4_5/BC3 (format 20),
  128x128, packed mip tail (identical codec to the proven draft_logo writer).
* ``divots`` -- Xenos 8_8_8_8 (format 6), 64x64, permutation (BGRA) swizzle,
  single-part descriptor+base+mip layout (uncompressed, so lossless).

Deliberately OUT OF SCOPE (documented, not guessed): ``field_radiance``
(format 59 DXT5A) and the ``divot_Grass*`` weather textures (format 4 5_6_5)
need a new single-channel/RGB565 codec *and* a non-permutation const-channel
swizzle path; the ``field`` / practice SCNE families and the penalty CurveAnim
have no serializer.  Those raise a typed PORTME refusal rather than a guess.

Only the base mip is regenerated; the packed mip tail is byte-preserved (stale
relative to an edit) until a Xenos packed-mip regenerator lands.  Like the
sibling ``apf_texture_patch``/``apf_logo_patch`` writers, this module makes no
in-game/runtime claim without a Xenia capture -- it proves the exact bytes it
changes.  The small, format-agnostic H7A/tiling/IFF/output-safety helpers are
copied verbatim from ``apf_texture_patch.py`` so this writer neither edits nor
couples to that concurrently-merged module; only the stable ``apf_inner`` and
``apf_outer`` parsing libraries are imported.
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
from typing import Callable, Iterable

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


SCHEMA = "apf_field_art_patch/v1"
# Field art's blocks are over a megabyte and their fixed allocation has almost
# no slack, so the encoder has to search harder here than elsewhere.  At 256 the
# no-overlap rule costs 162 bytes against retail and the rebuild overflows by
# 185; at 1024 it comes in 4 bytes *under* retail's own compressor.  Raising it
# further changes nothing, so this is the knee of the curve, not a guess.
MAX_H7A_CANDIDATES = 1024


# ---------------------------------------------------------------------------
# Per-slot fail-closed contract.  Generalizing to the other 117 endzone
# packages is purely additive: append one row per slot with its pinned entry
# and base SHA-256 (the descriptor is identical across the family).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FieldArtContract:
    """One evidence-bounded, writable field-art TXTR slot."""

    entry_index: int
    file_index: int
    name: str
    type_name: str
    kind: str
    codec: str  # "dxt1" | "bc3" | "rgba8888"
    format: int
    width: int
    height: int
    pitch_pixels: int
    endianness: int
    swizzle: tuple[int, int, int, int]
    base_len: int
    mip_len: int
    part_layout: str  # "dram_vram" (2 parts) | "single" (1 part)
    head_len: int
    entry_sha256: str
    base_sha256: str
    sibling_name: str | None

    @property
    def block_dims(self) -> tuple[int, int, int]:
        if self.codec == "dxt1":
            return (4, 4, 8)
        if self.codec == "bc3":
            return (4, 4, 16)
        if self.codec == "rgba8888":
            return (1, 1, 4)
        raise PatchError(f"unsupported codec {self.codec!r}")

    @property
    def pixel_part_index(self) -> int:
        return 1 if self.part_layout == "dram_vram" else 0


_CONTRACTS: dict[tuple[int, int], FieldArtContract] = {
    (6, 0): FieldArtContract(
        entry_index=6, file_index=0, name="endzone_l0", type_name="TXTR",
        kind="ENDZONE_TEXTURE", codec="dxt1", format=18, width=2048, height=512,
        pitch_pixels=2048, endianness=1, swizzle=(0, 1, 2, 3),
        base_len=0x80000, mip_len=0x30000, part_layout="dram_vram", head_len=0,
        entry_sha256="d8fb70d2bdb180306f49aa2b268d287b35eb33289c69959a74fd6c7dcac9af26",
        base_sha256="d23684a00cc500c8b5430e56291f105dea69e30e7b13ee23fef91ac36ada4adb",
        sibling_name="endzone_l1",
    ),
    (6, 1): FieldArtContract(
        entry_index=6, file_index=1, name="endzone_l1", type_name="TXTR",
        kind="ENDZONE_TEXTURE", codec="dxt1", format=18, width=2048, height=512,
        pitch_pixels=2048, endianness=1, swizzle=(0, 1, 2, 3),
        base_len=0x80000, mip_len=0x30000, part_layout="dram_vram", head_len=0,
        entry_sha256="d8fb70d2bdb180306f49aa2b268d287b35eb33289c69959a74fd6c7dcac9af26",
        base_sha256="765f574fa14020e1451cd0a3fc32f4afe21da1aba284b827748d04b9f929f8cd",
        sibling_name="endzone_l0",
    ),
    (659, 18): FieldArtContract(
        entry_index=659, file_index=18, name="pc_field_goal", type_name="TXTR",
        kind="PRACTICE_FIELD_OVERLAY", codec="dxt1", format=18, width=256,
        height=256, pitch_pixels=256, endianness=1, swizzle=(0, 1, 2, 3),
        base_len=0x8000, mip_len=0x8000, part_layout="dram_vram", head_len=0,
        entry_sha256="7077a50912167a6c9ad06014277b9e838bb45e6d9d9dc10d5e0da5ec9f398177",
        base_sha256="fbd169fd1cd0a0f24264d939e70b51c993273d107d44ffdb20813fc5bcdbbe1c",
        sibling_name=None,
    ),
    (659, 23): FieldArtContract(
        entry_index=659, file_index=23, name="Field_Pass_text", type_name="TXTR",
        kind="PRACTICE_FIELD_OVERLAY", codec="bc3", format=20, width=128,
        height=128, pitch_pixels=128, endianness=1, swizzle=(0, 1, 2, 3),
        base_len=0x4000, mip_len=0xC000, part_layout="dram_vram", head_len=0,
        entry_sha256="7077a50912167a6c9ad06014277b9e838bb45e6d9d9dc10d5e0da5ec9f398177",
        base_sha256="5c2d695a7fc0682a9b506d8c93c0f34a2ab6dd6fbc9486b57ced866c06c52280",
        sibling_name=None,
    ),
    (659, 252): FieldArtContract(
        entry_index=659, file_index=252, name="Stride_number_field",
        type_name="TXTR", kind="PRACTICE_FIELD_OVERLAY", codec="bc3", format=20,
        width=128, height=128, pitch_pixels=128, endianness=1,
        swizzle=(0, 1, 2, 3), base_len=0x4000, mip_len=0xC000,
        part_layout="dram_vram", head_len=0,
        entry_sha256="7077a50912167a6c9ad06014277b9e838bb45e6d9d9dc10d5e0da5ec9f398177",
        base_sha256="617df24b1099f7ffc96f59b68533b954e4180018cded3226281b0de2856ff769",
        sibling_name=None,
    ),
    (53, 0): FieldArtContract(
        entry_index=53, file_index=0, name="divots", type_name="TXTR",
        kind="DIVOT_WEATHER_TEXTURE", codec="rgba8888", format=6, width=64,
        height=64, pitch_pixels=64, endianness=2, swizzle=(2, 1, 0, 3),
        base_len=0x4000, mip_len=0x2000, part_layout="single", head_len=0x1000,
        entry_sha256="c0600767a720266b704bc6bb6ece23d43a410f8235080f99d6b434aa0f41155b",
        base_sha256="c6c1f33758c18719605751bd6bea174d0a39fef25f265948bf47cdcd4e911aa6",
        sibling_name=None,
    ),
}

def writable_locations() -> dict[tuple[int, int], str]:
    """``(outer entry, inner file) -> slot name`` for every writable slot.

    The editor's asset browser lists these rows beside thousands it cannot
    write, and it has to tell a modder which ones a proved writer already owns.
    Reading the pinned contract keys is the only honest way to answer that: the
    answer moves with this table instead of with a copy of it.
    """

    return {key: contract.name for key, contract in _CONTRACTS.items()}


# Named refusals for the field-art families intentionally not shipped tonight.
_UNSUPPORTED_KINDS = {
    "field_radiance": "format 59 DXT5A + broadcast/const-channel swizzle [0,0,0,5]",
    "divot_GrassRain": "format 4 5_6_5 + const-alpha swizzle [2,1,0,5]",
    "divot_GrassSnow": "format 4 5_6_5 + const-alpha swizzle [2,1,0,5]",
    "divot_GrassDry": "format 4 5_6_5 + const-alpha swizzle [2,1,0,5]",
}

_PORTME = [
    "validate each changed copied volume in Xenia and on user-owned hardware "
    "before describing any in-game/runtime effect as proved",
    "implement packed-mip regeneration: the mip tail is currently byte-preserved "
    "(stale relative to an edit), not downsampled+re-tiled from the new base",
    "add field_radiance (DXT5A) and divot_Grass* weather (5_6_5): both need a new "
    "codec AND a non-permutation const-channel swizzle path",
    "replace the provisional DXT1/BC3 touched-block endpoint search with a "
    "perceptual production encoder (uncompressed 8_8_8_8 divots are already lossless)",
    "generalize the endzone contract to all 118 packages by appending one pinned "
    "row per slot (the descriptor is identical across the family)",
    "co-editing several textures inside one shared package (e.g. entry 659) means "
    "chaining outputs so each edit re-pins the previous rebuild as its retail source",
]


# ---------------------------------------------------------------------------
# Copied verbatim from tools/apf_texture_patch.py (format-agnostic core; copied
# to avoid editing/coupling to that concurrently-merged writer module).
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
    """Greedy encoder for the H7A stream consumed by ``decompress_h7a``."""

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
                        # On a tie prefer the FARTHER match: both encode to the
                        # same two bytes, but the reachable length at the next
                        # position is now bounded by the distance, so the near
                        # copy caps every following match.
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


# The optional minimum-cost encoder.  Greedy parsing lands 21 bytes over
# endzone_l0's fixed allocation once overlapping matches are (correctly)
# forbidden, and no candidate-limit setting closes that gap -- greedy simply
# cannot trade a shorter match now for a longer one immediately after.
# tools/apf_h7a_optimal.c does that trade as a shortest path and recovers about
# 585 bytes on that block, which is what makes endzone_l0 editable at all.  It is
# used when the exact reviewed Linux helper bundled in the release is available
# and its output round-trips; otherwise the greedy encoder is used unchanged.
#
# The gain is ~0.5%, so it only decides fit for edits near the allocation.  See
# docs/research/apf_h7a_allocation_budget.md for the measured budget: a 900x220
# region tolerates 16 distinct 4x4 blocks with this parse and 12 with greedy.
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
    if hashlib.sha256(_OPTIMAL_BINARY.read_bytes()).hexdigest() != _OPTIMAL_BINARY_SHA256:
        return None
    return _OPTIMAL_BINARY


def compress_h7a_best(data: bytes, shift: int) -> bytes:
    """The smaller of the greedy and minimum-cost parses, both verified.

    Never returns a stream that does not decode back to ``data``, and never
    returns the optimal parse unless it is actually smaller, so this can only
    improve on the greedy result or match it.
    """
    greedy = compress_h7a(data, shift)
    binary = _optimal_binary()
    if binary is None:
        return greedy
    import subprocess

    try:
        finished = subprocess.run(
            # The largest real block, endzone_l0 at 1.44 MB, takes about 30s, so
            # this is a generous ceiling.  Kept low deliberately: exceeding it
            # falls back to greedy rather than stalling a caller or a test run.
            [str(binary), str(shift)], input=data,
            capture_output=True, timeout=180,
        )
    except (OSError, subprocess.SubprocessError):
        return greedy
    candidate = finished.stdout
    if finished.returncode != 0 or not candidate or len(candidate) >= len(greedy):
        return greedy
    try:
        if apf_inner.decompress_h7a(candidate, len(data), shift) != data:
            return greedy
    except Exception:  # noqa: BLE001 - any decode failure means fall back
        return greedy
    return candidate


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
# New codecs.  BC1/BC3 touched-block encoders are provisional (they only touch
# 4x4 blocks an edit changes; unchanged blocks are copied byte-for-byte).  The
# 8_8_8_8 encoder is a lossless permutation+endian+tile transform.
# ---------------------------------------------------------------------------
def _rgb565_encode(red: int, green: int, blue: int) -> int:
    return (
        ((red * 31 + 127) // 255) << 11
        | ((green * 63 + 127) // 255) << 5
        | ((blue * 31 + 127) // 255)
    )


def _color_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return sum((a[index] - b[index]) ** 2 for index in range(3))


def _farthest_endpoints(
    colors: list[tuple[int, int, int]]
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    endpoint_a = endpoint_b = colors[0]
    best_distance = -1
    for first in range(16):
        for second in range(first + 1, 16):
            distance = _color_distance(colors[first], colors[second])
            if distance > best_distance:
                best_distance = distance
                endpoint_a, endpoint_b = colors[first], colors[second]
    return endpoint_a, endpoint_b


def encode_dxt1_block(pixels: list[tuple[int, int, int, int]]) -> bytes:
    """Encode one 4x4 RGBA block as deterministic, opaque DXT1/BC1 (8 bytes).

    The palette used for index selection is built with the *same*
    ``force_four_colors=False`` interpretation ``apf_inner._decode_bc1`` uses, so
    encode and decode agree by construction.  Endpoints are ordered
    ``color_0 >= color_1``; the degenerate equal-endpoint (flat) block decodes
    exactly because every palette entry equals the flat colour and selector 3
    (the punch-through slot) is never nearest.
    """

    if len(pixels) != 16:
        raise PatchError("DXT1 input must contain exactly 16 pixels")
    if any(len(pixel) != 4 or any(not 0 <= value <= 255 for value in pixel) for pixel in pixels):
        raise PatchError("DXT1 input contains an invalid RGBA value")

    colors = [(pixel[0], pixel[1], pixel[2]) for pixel in pixels]
    endpoint_a, endpoint_b = _farthest_endpoints(colors)
    color_0 = _rgb565_encode(*endpoint_a)
    color_1 = _rgb565_encode(*endpoint_b)
    if color_0 < color_1:
        color_0, color_1 = color_1, color_0
    palette_rgba, _ = apf_inner._bc_color_table(  # type: ignore[attr-defined]
        struct.pack("<HHI", color_0, color_1, 0), False
    )
    palette = [entry[:3] for entry in palette_rgba]
    indices = 0
    for index, color in enumerate(colors):
        selector = min(
            range(4),
            key=lambda candidate: (_color_distance(color, palette[candidate]), candidate),
        )
        indices |= selector << (index * 2)
    return struct.pack("<HHI", color_0, color_1, indices)


def encode_bc3_block(pixels: list[tuple[int, int, int, int]]) -> bytes:
    """Encode one 4x4 RGBA block as deterministic, valid BC3 (16 bytes).

    Copied verbatim from ``apf_texture_patch.encode_bc3_block``: provisional
    endpoint search, applied only to 4x4 blocks an edit touches.
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
            (alpha_0 * (7 - index) + alpha_1 * index) // 7 for index in range(1, 7)
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
    endpoint_a, endpoint_b = _farthest_endpoints(colors)
    color_0 = _rgb565_encode(*endpoint_a)
    color_1 = _rgb565_encode(*endpoint_b)
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


_BC_ENCODERS: dict[str, Callable[[list[tuple[int, int, int, int]]], bytes]] = {
    "dxt1": encode_dxt1_block,
    "bc3": encode_bc3_block,
}


def encode_8888_base(
    metadata: dict[str, object], rgba_display: bytes, base_len: int
) -> bytes:
    """Encode display-order RGBA into a tiled Xenos 8_8_8_8 base level (lossless).

    Exact inverse of ``apf_inner.decode_txtr_base_rgba``'s format-6 path:
    inverse permutation swizzle -> pack raw RGBA -> Xenos endian swap -> tile.
    """

    width = int(metadata["width"])
    height = int(metadata["height"])
    if len(rgba_display) != width * height * 4:
        raise PatchError(
            f"RGBA buffer is 0x{len(rgba_display):x}, expected 0x{width * height * 4:x}"
        )
    raw_pixels = _inverse_swizzle_pixels(
        rgba_display, metadata["swizzle_components"]  # type: ignore[arg-type]
    )
    linear = bytearray(width * height * 4)
    for index, pixel in enumerate(raw_pixels):
        linear[index * 4 : index * 4 + 4] = bytes(pixel)
    on_disc = apf_inner._endian_swap(  # type: ignore[attr-defined]
        bytes(linear), int(metadata["endianness"])
    )
    return _tile_2d(
        on_disc, width, height, int(metadata["pitch_pixels"]), 1, 1, 4, base_len
    )


# ---------------------------------------------------------------------------
# Transport + base-edit helpers (the universal generalization).
# ---------------------------------------------------------------------------
def _transport_roundtrip_ok(
    metadata: dict[str, object],
    base: bytes,
    block_width: int,
    block_height: int,
    bytes_per_block: int,
) -> bool:
    """Prove untile -> endian -> endian -> tile reproduces the base bit-exact."""

    width = int(metadata["width"])
    height = int(metadata["height"])
    pitch = int(metadata["pitch_pixels"])
    endian = int(metadata["endianness"])
    tiled = apf_inner._untile_2d(  # type: ignore[attr-defined]
        base, width, height, pitch, block_width, block_height, bytes_per_block
    )
    linear = apf_inner._endian_swap(tiled, endian)  # type: ignore[attr-defined]
    rebuilt = _tile_2d(
        apf_inner._endian_swap(linear, endian),  # type: ignore[attr-defined]
        width, height, pitch, block_width, block_height, bytes_per_block, len(base),
    )
    return rebuilt == base


def _encode_bc_base(
    contract: FieldArtContract,
    metadata: dict[str, object],
    original_base: bytes,
    original_rgba: bytes,
    wanted_rgba: bytes,
) -> tuple[bytes, list[int]]:
    """Rewrite only the 4x4 blocks an edit changes; copy the rest verbatim."""

    width = int(metadata["width"])
    height = int(metadata["height"])
    pitch = int(metadata["pitch_pixels"])
    endian = int(metadata["endianness"])
    block_width, block_height, block_size = contract.block_dims
    encoder = _BC_ENCODERS[contract.codec]

    raw_wanted_pixels = _inverse_swizzle_pixels(
        wanted_rgba, metadata["swizzle_components"]  # type: ignore[arg-type]
    )
    tiled_linear = apf_inner._untile_2d(  # type: ignore[attr-defined]
        original_base, width, height, pitch, block_width, block_height, block_size
    )
    original_linear = apf_inner._endian_swap(tiled_linear, endian)  # type: ignore[attr-defined]
    new_linear = bytearray(original_linear)
    width_blocks = width // block_width
    height_blocks = height // block_height
    changed_blocks: list[int] = []
    for block_y in range(height_blocks):
        for block_x in range(width_blocks):
            pixel_indices = [
                (block_y * block_height + local_y) * width + block_x * block_width + local_x
                for local_y in range(block_height)
                for local_x in range(block_width)
            ]
            if all(
                wanted_rgba[index * 4 : index * 4 + 4]
                == original_rgba[index * 4 : index * 4 + 4]
                for index in pixel_indices
            ):
                continue
            block_index = block_y * width_blocks + block_x
            encoded = encoder([raw_wanted_pixels[index] for index in pixel_indices])
            start = block_index * block_size
            new_linear[start : start + block_size] = encoded
            changed_blocks.append(block_index)

    new_base = _tile_2d(
        apf_inner._endian_swap(bytes(new_linear), endian),  # type: ignore[attr-defined]
        width, height, pitch, block_width, block_height, block_size, len(original_base),
    )
    return new_base, changed_blocks


def _changed_pixels(original_rgba: bytes, wanted_rgba: bytes) -> int:
    return sum(
        1
        for index in range(0, len(original_rgba), 4)
        if original_rgba[index : index + 4] != wanted_rgba[index : index + 4]
    )


def _resolve_target(
    record: apf_inner.IFFRecord,
    original_blocks: list[bytes],
    contract: FieldArtContract,
) -> tuple[apf_inner.DataFile, apf_inner.FilePart, bytes, bytes, dict[str, object]]:
    """Return (target file, pixel part, descriptor bytes, pixel bytes, metadata)."""

    try:
        target = record.files[contract.file_index]
    except IndexError as exc:
        raise PatchError(f"IFF has no inner file {contract.file_index}") from exc
    if target.name != contract.name or target.type_name != contract.type_name:
        raise PatchError(
            f"expected {contract.name!r}/{contract.type_name}, got "
            f"{target.name!r}/{target.type_name!r}"
        )
    expected_parts = 2 if contract.part_layout == "dram_vram" else 1
    if len(target.parts) != expected_parts:
        raise PatchError(
            f"PORTME: {contract.name} expected {expected_parts} part(s), "
            f"found {len(target.parts)}"
        )

    descriptor_part = target.parts[0]
    descriptor_bytes = original_blocks[descriptor_part.block_index][
        descriptor_part.offset : descriptor_part.offset + descriptor_part.length
    ]
    pixel_part = target.parts[contract.pixel_part_index]
    pixel_bytes = original_blocks[pixel_part.block_index][
        pixel_part.offset : pixel_part.offset + pixel_part.length
    ]
    metadata = apf_inner.parse_txtr_metadata(descriptor_bytes)
    return target, pixel_part, descriptor_bytes, pixel_bytes, metadata


def _validate_descriptor(contract: FieldArtContract, metadata: dict[str, object]) -> None:
    required = {
        "format": contract.format,
        "width": contract.width,
        "height": contract.height,
        "pitch_pixels": contract.pitch_pixels,
        "endianness": contract.endianness,
        "tiled": True,
        "stacked": False,
        "dimension": 1,
        "vc_base_data_length": contract.base_len,
        "vc_mip_data_length": contract.mip_len,
    }
    disagreements = {
        key: (metadata.get(key), value)
        for key, value in required.items()
        if metadata.get(key) != value
    }
    if disagreements:
        raise PatchError(
            f"PORTME: {contract.name} descriptor changed: {disagreements}"
        )
    if tuple(metadata["swizzle_components"]) != contract.swizzle:  # type: ignore[arg-type]
        raise PatchError(
            f"PORTME: {contract.name} swizzle changed from {list(contract.swizzle)}"
        )


def build_field_art_patch(
    index_path: Path,
    png_path: Path,
    entry_index: int,
    file_index: int,
) -> PatchResult:
    """Build a bit-exact copied-volume patch for one pinned field-art TXTR."""

    contract = _CONTRACTS.get((entry_index, file_index))
    if contract is None:
        raise PatchError(
            f"PORTME: (entry {entry_index}, file {file_index}) is not a pinned, "
            "writable field-art slot; supported slots are "
            f"{sorted(_CONTRACTS)} (field_radiance / weather divots need new codecs)"
        )

    archive = apf_outer.parse_archive(index_path)
    try:
        entry = archive.entries[entry_index]
    except IndexError as exc:
        raise PatchError(f"outer archive has no entry {entry_index}") from exc
    if len(entry.segments) != 1 or entry.segments[0].pack_name != "0A":
        raise PatchError(f"PORTME: {contract.name} target is not in one 0A segment")

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

    if sha256_bytes(original_entry) != contract.entry_sha256:
        raise PatchError(
            f"source entry hash is not the pinned retail {contract.name} package; refusing"
        )

    target, pixel_part, descriptor_bytes, pixel_bytes, metadata = _resolve_target(
        record, original_blocks, contract
    )
    _validate_descriptor(contract, metadata)

    if len(pixel_bytes) != pixel_part.length:
        raise PatchError("pixel part length mismatch")
    head_len = len(pixel_bytes) - contract.base_len - contract.mip_len
    if head_len != contract.head_len:
        raise PatchError(
            f"PORTME: {contract.name} head/base/mip split is 0x{head_len:x}, "
            f"expected 0x{contract.head_len:x}"
        )
    preserved_head = pixel_bytes[:head_len]
    base = pixel_bytes[head_len : head_len + contract.base_len]
    mip_tail = pixel_bytes[head_len + contract.base_len :]
    if len(base) != contract.base_len or len(mip_tail) != contract.mip_len:
        raise PatchError(f"{contract.name} base/mip lengths do not cover the pixel part")
    if sha256_bytes(base) != contract.base_sha256:
        raise PatchError(f"decoded {contract.name} base hash is not the pinned retail data")

    block_width, block_height, bytes_per_block = contract.block_dims
    if not _transport_roundtrip_ok(metadata, base, block_width, block_height, bytes_per_block):
        raise PatchError(
            f"Xenos untile/endian/tile transport for {contract.name} is not bit-exact"
        )

    _, _, original_rgba = apf_inner.decode_txtr_base_rgba(metadata, base)
    wanted_rgba = _load_png(png_path, contract.width, contract.height)

    common_source = {
        "archive_index": str(index_path),
        "physical_volume": entry.segments[0].pack_name,
        "outer_entry_index": entry_index,
        "inner_file_index": file_index,
        "inner_name": contract.name,
        "kind": contract.kind,
        "codec": contract.codec,
        "entry_sha256": sha256_bytes(original_entry),
        "base_sha256": sha256_bytes(base),
        "png_rgba_sha256": sha256_bytes(wanted_rgba),
    }

    if wanted_rgba == original_rgba:
        manifest = {
            "schema": SCHEMA,
            "mode": "no_op",
            "source": common_source,
            "target": {"name": contract.name, "type": contract.type_name, "txtr": metadata},
            "validation": {
                "xenos_transport_bit_exact": True,
                "input_matches_decoded_source": True,
                "entry_bit_exact": True,
                "mip_tail_preserved": True,
                "descriptor_preserved": True,
                "siblings_preserved": True,
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

    # Encode the edit into a new base, preserving head, mip tail, and siblings.
    if contract.codec == "rgba8888":
        new_base = encode_8888_base(metadata, wanted_rgba, contract.base_len)
        changed_block_count = _changed_pixels(original_rgba, wanted_rgba)
    else:
        new_base, changed_blocks = _encode_bc_base(
            contract, metadata, base, original_rgba, wanted_rgba
        )
        changed_block_count = len(changed_blocks)

    if new_base == base:
        raise PatchError("no-op detection was inconsistent: encode reproduced retail base")
    new_pixel = preserved_head + new_base + mip_tail
    if (
        len(new_pixel) != pixel_part.length
        or new_pixel[:head_len] != preserved_head
        or new_pixel[head_len + contract.base_len :] != mip_tail
    ):
        raise PatchError("head/base/mip preservation invariant failed")

    new_blocks = list(original_blocks)
    patched_block = bytearray(new_blocks[pixel_part.block_index])
    patched_block[pixel_part.offset : pixel_part.offset + pixel_part.length] = new_pixel
    new_blocks[pixel_part.block_index] = bytes(patched_block)

    changed_block_descriptor = record.blocks[pixel_part.block_index]
    if not changed_block_descriptor.is_compressed or changed_block_descriptor.wrapper is None:
        raise PatchError(f"PORTME: {contract.name} pixel block is not H7A-compressed")
    shift = changed_block_descriptor.wrapper.shift
    compressed = compress_h7a_best(new_blocks[pixel_part.block_index], shift)
    if apf_inner.decompress_h7a(
        compressed, len(new_blocks[pixel_part.block_index]), shift
    ) != new_blocks[pixel_part.block_index]:
        raise PatchError("H7A encode/decode round-trip failed")
    encoded_stored = struct.pack(
        ">5I",
        apf_inner.H7A_MAGIC,
        len(new_blocks[pixel_part.block_index]),
        apf_inner.H7A_HEADER_SIZE + len(compressed),
        changed_block_descriptor.unknown_10,
        shift,
    ) + compressed
    new_stored = list(original_stored)
    new_stored[pixel_part.block_index] = encoded_stored

    # Rebuild the IFF inside the fixed outer allocation.
    header = bytearray(original_entry[: record.header_size])
    body = bytearray()
    cursor = record.header_size
    block_report: list[dict[str, object]] = []
    for index, (block, stored) in enumerate(zip(record.blocks, new_stored)):
        start = cursor
        compressed_length = len(stored) if block.is_compressed else block.uncompressed_length
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
        raise PatchError(f"PORTME: {contract.name} IFF has no validated name footer")
    footer_total = 8 + record.footer.payload_size
    footer_bytes = original_entry[record.file_length : record.file_length + footer_total]
    old_tail = original_entry[record.file_length + footer_total :]
    if any(old_tail):
        raise PatchError(f"PORTME: {contract.name} outer allocation tail is nonzero")
    active = bytes(header) + bytes(body) + footer_bytes
    if len(active) > entry.size:
        raise PatchError(
            f"rebuilt {contract.name} IFF exceeds its fixed outer allocation by "
            f"{len(active) - entry.size} bytes; refusing output"
        )
    rebuilt_entry = active + b"\0" * (entry.size - len(active))

    # Reparse gate: rebuilt entry must decode to the intended blocks and change
    # only the target pixel part.
    memory_reader = BytesReader(rebuilt_entry)
    rebuilt_record = apf_inner.parse_iff(memory_reader, entry)
    rebuilt_blocks = [
        apf_inner.decode_block(memory_reader, rebuilt_record, index, 1 << 30)
        for index in range(rebuilt_record.block_count)
    ]
    if rebuilt_blocks != new_blocks:
        raise PatchError(f"rebuilt {contract.name} IFF does not decode as intended")
    before_parts = _file_part_hashes(record, original_blocks)
    after_parts = _file_part_hashes(rebuilt_record, rebuilt_blocks)
    changed_parts = [key for key in before_parts if before_parts[key] != after_parts[key]]
    expected_changed_part = (file_index, contract.pixel_part_index)
    if changed_parts != [expected_changed_part]:
        raise PatchError(
            f"unrelated inner payload changed; changed part keys are {changed_parts}"
        )

    _, _, decoded_new_rgba = apf_inner.decode_txtr_base_rgba(metadata, new_base)
    footer_after = rebuilt_entry[new_file_length : new_file_length + footer_total]
    manifest = {
        "schema": SCHEMA,
        "mode": "patched",
        "source": common_source,
        "target": {
            "name": contract.name,
            "type": contract.type_name,
            "txtr": metadata,
            "sibling_name": contract.sibling_name,
            "changed_base_block_count": changed_block_count,
        },
        "base_data": {
            "length": contract.base_len,
            "sha256_before": sha256_bytes(base),
            "sha256_after": sha256_bytes(new_base),
            "decoded_rgba_sha256_before": sha256_bytes(original_rgba),
            "decoded_rgba_sha256_after": sha256_bytes(decoded_new_rgba),
            "decode_back_metrics": _rgba_metrics(wanted_rgba, decoded_new_rgba),
        },
        "mip_tail": {
            "length": contract.mip_len,
            "sha256": sha256_bytes(mip_tail),
            "bit_exact": True,
        },
        "descriptor_pad": {
            "length": head_len,
            "sha256": sha256_bytes(preserved_head),
            "bit_exact": True,
        },
        "iff": {
            "allocation_size": entry.size,
            "file_length_before": record.file_length,
            "file_length_after": new_file_length,
            "allocation_slack_after": entry.size - len(active),
            "h7a_shift": shift,
            "footer_sha256_before": sha256_bytes(footer_bytes),
            "footer_sha256_after": sha256_bytes(footer_after),
            "footer_bit_exact": footer_after == footer_bytes,
            "blocks": block_report,
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
            "footer_bit_exact": footer_after == footer_bytes,
            "mip_tail_preserved": True,
            "descriptor_pad_preserved": head_len == 0 or preserved_head == pixel_bytes[:head_len],
            "unrelated_inner_part_count": len(before_parts) - 1,
            "unrelated_inner_parts_preserved": True,
            "changed_inner_parts": [
                {
                    "file_index": file_index,
                    "part_index": contract.pixel_part_index,
                    "block_index": pixel_part.block_index,
                }
            ],
            "fixed_outer_allocation": True,
            "source_opened_read_only": True,
        },
        "backend": {
            "png": f"Pillow {PILLOW_VERSION}",
            "encoder": {
                "dxt1": "project-native deterministic touched-block DXT1 encoder (provisional)",
                "bc3": "project-native deterministic touched-block BC3 encoder (provisional)",
                "rgba8888": "exact 8_8_8_8 permutation+endian+tile (lossless)",
            }[contract.codec],
            "h7a": "project-native greedy H7A encoder",
        },
        "portme": _PORTME,
    }
    return PatchResult(rebuilt_entry, manifest)


# ---------------------------------------------------------------------------
# Output safety, copied verbatim from tools/apf_texture_patch.py.
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


def _commit_reserved(path: Path, reservation: OutputReservation, data: bytes) -> None:
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
        source_suffix_sha = _sha256_fd_range(source_descriptor, suffix_offset, suffix_length)
        output_suffix_sha = _sha256_fd_range(output_descriptor, suffix_offset, suffix_length)
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
    parser.add_argument("--png", required=True, type=Path, help="exact-dimension RGBA PNG")
    parser.add_argument("--entry-index", required=True, type=int)
    parser.add_argument("--file-index", required=True, type=int)
    parser.add_argument("--output-entry", type=Path, help="write rebuilt logical IFF entry")
    parser.add_argument(
        "--output-volume",
        type=Path,
        help="copy 0A to this new path, then replace only the fixed field-art entry",
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
        result = build_field_art_patch(
            index_path, png_path, args.entry_index, args.file_index
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
                index_path, output_volume, entry, result.entry_bytes
            )
        _commit_reserved(
            manifest_path,
            manifest_reservation,
            (json.dumps(document, indent=2) + "\n").encode("utf-8"),
        )
        _close_reserved(manifest_reservation)
        manifest_reservation = None
        print(
            "APF_FIELD_ART_PATCH_PASS "
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

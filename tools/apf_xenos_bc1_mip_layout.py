#!/usr/bin/env python3
"""Evidence-bounded Xenos BC1 mip addressing for APF 2K8 pants.

This is the BC1/8-byte-block counterpart to ``apf_xenos_mip_layout.py``.
The formulas are transcribed from Xenia commit
``95a5c3ee250f80c3b9d139658649d9ffb6db3eec`` and deliberately accept only
the tiled, packed, 2D DXT1 descriptor class used by ``pants_color``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
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

import apf_inner


XENIA_COMMIT = "95a5c3ee250f80c3b9d139658649d9ffb6db3eec"
BLOCK_WIDTH = 4
BLOCK_HEIGHT = 4
BYTES_PER_BLOCK = 8
STORAGE_ALIGNMENT_BLOCKS = 32


class MipLayoutError(ValueError):
    """Raised when a BC1 texture is outside the proved descriptor class."""


@dataclass(frozen=True)
class MipLocation:
    level: int
    width: int
    height: int
    data_offset: int
    allocation_length: int
    pitch_blocks: int
    origin_block_x: int
    origin_block_y: int
    packed_tail: bool

    @property
    def width_blocks(self) -> int:
        return (self.width + BLOCK_WIDTH - 1) // BLOCK_WIDTH

    @property
    def height_blocks(self) -> int:
        return (self.height + BLOCK_HEIGHT - 1) // BLOCK_HEIGHT

    @property
    def logical_block_count(self) -> int:
        return self.width_blocks * self.height_blocks

    def manifest(self) -> dict[str, object]:
        result = asdict(self)
        result.update(
            {
                "data_offset_hex": f"0x{self.data_offset:x}",
                "allocation_length_hex": f"0x{self.allocation_length:x}",
                "logical_block_count": self.logical_block_count,
            }
        )
        return result


def _align_up(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def _next_pow2(value: int) -> int:
    if value <= 0:
        raise MipLayoutError("texture dimensions must be positive")
    return 1 << (value - 1).bit_length()


def _extent_bytes(width: int, height: int) -> int:
    width_blocks = _align_up(
        (width + BLOCK_WIDTH - 1) // BLOCK_WIDTH, STORAGE_ALIGNMENT_BLOCKS
    )
    height_blocks = _align_up(
        (height + BLOCK_HEIGHT - 1) // BLOCK_HEIGHT, STORAGE_ALIGNMENT_BLOCKS
    )
    return width_blocks * height_blocks * BYTES_PER_BLOCK


def get_packed_tile_offset(
    width: int, height: int, packed_tile: int
) -> tuple[bool, int, int]:
    """Return Xenia's packed-tail origin in BC1 blocks."""

    if packed_tile < 0:
        raise MipLayoutError("packed-tile index is negative")
    log2_width = (width - 1).bit_length()
    log2_height = (height - 1).bit_length()
    if min(log2_width, log2_height) > 4:
        return False, 0, 0
    if packed_tile < 3:
        if log2_width > log2_height:
            offset_x_pixels, offset_y_pixels = 0, 16 >> packed_tile
        else:
            offset_x_pixels, offset_y_pixels = 16 >> packed_tile, 0
    else:
        if log2_width > log2_height:
            offset_x_pixels, offset_y_pixels = 16 >> (packed_tile - 2), 0
        else:
            offset_x_pixels, offset_y_pixels = 0, 16 >> (packed_tile - 2)
    return True, offset_x_pixels // BLOCK_WIDTH, offset_y_pixels // BLOCK_HEIGHT


def derive_layout(metadata: dict[str, object]) -> tuple[MipLocation, ...]:
    required = {
        "format": 18,
        "endianness": 1,
        "tiled": True,
        "stacked": False,
        "dimension": 1,
        "mip_min_level": 0,
        "packed_mips": True,
    }
    disagreements = {
        key: (metadata.get(key), expected)
        for key, expected in required.items()
        if metadata.get(key) != expected
    }
    if disagreements:
        raise MipLayoutError(
            f"PORTME: unsupported Xenos BC1 descriptor fields: {disagreements}"
        )

    width = int(metadata["width"])
    height = int(metadata["height"])
    pitch_pixels = int(metadata["pitch_pixels"])
    base_length = int(metadata["vc_base_data_length"])
    mip_length = int(metadata["vc_mip_data_length"])
    mip_max = int(metadata["mip_max_level"])
    if width <= 0 or height <= 0 or mip_max <= 0:
        raise MipLayoutError("PORTME: descriptor does not contain a mip chain")
    if pitch_pixels < width or pitch_pixels % BLOCK_WIDTH:
        raise MipLayoutError("PORTME: base pitch cannot be routed as BC1 blocks")

    base_pitch_blocks = _align_up(pitch_pixels // BLOCK_WIDTH, 32)
    base_height_blocks = _align_up((height + 3) // 4, 32)
    calculated_base = base_pitch_blocks * base_height_blocks * BYTES_PER_BLOCK
    if base_length != calculated_base:
        raise MipLayoutError(
            "PORTME: declared BC1 base allocation differs from tiled extent "
            f"(0x{base_length:x} != 0x{calculated_base:x})"
        )
    if int(metadata["mip_address_pages"]) << 12 != base_length:
        raise MipLayoutError(
            "PORTME: BC1 mip address does not immediately follow base allocation"
        )

    locations = [
        MipLocation(0, width, height, 0, base_length, base_pitch_blocks, 0, 0, False)
    ]
    width_pow2 = _next_pow2(width)
    height_pow2 = _next_pow2(height)
    for mip in range(1, mip_max + 1):
        address_offset = 0
        packed_mip_base = 1
        for prior in range(1, mip):
            prior_width = max(width_pow2 >> prior, 1)
            prior_height = max(height_pow2 >> prior, 1)
            if min(prior_width, prior_height) <= 16:
                break
            address_offset += _extent_bytes(prior_width, prior_height)
            packed_mip_base += 1

        mip_width = max(width_pow2 >> mip, 1)
        mip_height = max(height_pow2 >> mip, 1)
        packed, origin_x, origin_y = get_packed_tile_offset(
            mip_width, mip_height, mip - packed_mip_base
        )
        if packed:
            allocation_length = 32 * 32 * BYTES_PER_BLOCK
            pitch_blocks = 32
        else:
            allocation_length = _extent_bytes(mip_width, mip_height)
            pitch_blocks = _align_up((mip_width + 3) // 4, 32)
        locations.append(
            MipLocation(
                mip,
                mip_width,
                mip_height,
                base_length + address_offset,
                allocation_length,
                pitch_blocks,
                origin_x,
                origin_y,
                packed,
            )
        )

    calculated_end = max(
        item.data_offset + item.allocation_length for item in locations[1:]
    )
    if calculated_end != base_length + mip_length:
        raise MipLayoutError(
            "PORTME: Xenia-derived BC1 mip span differs from declaration "
            f"(0x{calculated_end - base_length:x} != 0x{mip_length:x})"
        )
    _validate_active_blocks_do_not_alias(locations)
    return tuple(locations)


def _active_transport_offsets(location: MipLocation) -> set[int]:
    offsets: set[int] = set()
    for block_y in range(location.height_blocks):
        for block_x in range(location.width_blocks):
            relative = apf_inner._tiled_2d_offset(  # type: ignore[attr-defined]
                block_x + location.origin_block_x,
                block_y + location.origin_block_y,
                location.pitch_blocks,
                3,
            )
            if relative < 0 or relative + 8 > location.allocation_length:
                raise MipLayoutError(
                    f"mip {location.level} tiled address leaves its allocation"
                )
            absolute = location.data_offset + relative
            if absolute in offsets:
                raise MipLayoutError(f"mip {location.level} aliases BC1 blocks")
            offsets.add(absolute)
    return offsets


def _validate_active_blocks_do_not_alias(
    locations: Iterable[MipLocation],
) -> None:
    owner: dict[int, int] = {}
    for location in locations:
        for offset in _active_transport_offsets(location):
            if offset in owner:
                raise MipLayoutError(
                    f"active BC1 mip blocks alias at 0x{offset:x}: "
                    f"{owner[offset]} and {location.level}"
                )
            owner[offset] = location.level


def extract_linear_bc1(texture: bytes, location: MipLocation) -> bytes:
    if location.data_offset + location.allocation_length > len(texture):
        raise MipLayoutError(f"mip {location.level} allocation exceeds texture")
    output = bytearray(location.logical_block_count * 8)
    for block_y in range(location.height_blocks):
        for block_x in range(location.width_blocks):
            relative = apf_inner._tiled_2d_offset(  # type: ignore[attr-defined]
                block_x + location.origin_block_x,
                block_y + location.origin_block_y,
                location.pitch_blocks,
                3,
            )
            source = location.data_offset + relative
            destination = (block_y * location.width_blocks + block_x) * 8
            output[destination : destination + 8] = texture[source : source + 8]
    return apf_inner._endian_swap(bytes(output), 1)  # type: ignore[attr-defined]


def insert_linear_bc1(
    texture: bytes, location: MipLocation, linear_bc1: bytes
) -> bytes:
    expected = location.logical_block_count * 8
    if len(linear_bc1) != expected:
        raise MipLayoutError(
            f"mip {location.level} BC1 length is 0x{len(linear_bc1):x}; "
            f"expected 0x{expected:x}"
        )
    transport = apf_inner._endian_swap(linear_bc1, 1)  # type: ignore[attr-defined]
    output = bytearray(texture)
    for block_y in range(location.height_blocks):
        for block_x in range(location.width_blocks):
            relative = apf_inner._tiled_2d_offset(  # type: ignore[attr-defined]
                block_x + location.origin_block_x,
                block_y + location.origin_block_y,
                location.pitch_blocks,
                3,
            )
            destination = location.data_offset + relative
            source = (block_y * location.width_blocks + block_x) * 8
            output[destination : destination + 8] = transport[source : source + 8]
    return bytes(output)


def transport_roundtrip(
    texture: bytes, locations: Iterable[MipLocation]
) -> bytes:
    rebuilt = texture
    for location in locations:
        rebuilt = insert_linear_bc1(
            rebuilt, location, extract_linear_bc1(texture, location)
        )
    return rebuilt

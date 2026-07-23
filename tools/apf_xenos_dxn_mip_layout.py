#!/usr/bin/env python3
"""Evidence-bounded Xenos DXN (BC5) mip addressing for APF helmet colors.

DXN uses the same 4x4, 16-byte block geometry as BC3, but the payload is two
independent BC4 channels.  The formulas are transcribed from Xenia commit
``95a5c3ee250f80c3b9d139658649d9ffb6db3eec`` and accept only the tiled,
packed, 2D, 8-in-16 descriptor class used by APF ``helmet_color``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import apf_inner


XENIA_COMMIT = "95a5c3ee250f80c3b9d139658649d9ffb6db3eec"
BLOCK_WIDTH = 4
BLOCK_HEIGHT = 4
BYTES_PER_BLOCK = 16
STORAGE_ALIGNMENT_BLOCKS = 32


class MipLayoutError(ValueError):
    """Raised when a DXN texture leaves the proved descriptor class."""


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
        return (self.width + 3) // 4

    @property
    def height_blocks(self) -> int:
        return (self.height + 3) // 4

    @property
    def logical_block_count(self) -> int:
        return self.width_blocks * self.height_blocks

    def manifest(self) -> dict[str, object]:
        result = asdict(self)
        result.update({
            "data_offset_hex": f"0x{self.data_offset:x}",
            "allocation_length_hex": f"0x{self.allocation_length:x}",
            "logical_block_count": self.logical_block_count,
        })
        return result


def _align_up(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def _next_pow2(value: int) -> int:
    if value <= 0:
        raise MipLayoutError("texture dimensions must be positive")
    return 1 << (value - 1).bit_length()


def _extent_bytes(width: int, height: int) -> int:
    width_blocks = _align_up((width + 3) // 4, 32)
    height_blocks = _align_up((height + 3) // 4, 32)
    return width_blocks * height_blocks * 16


def get_packed_tile_offset(
    width: int, height: int, packed_tile: int
) -> tuple[bool, int, int]:
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
    return True, offset_x_pixels // 4, offset_y_pixels // 4


def derive_layout(metadata: dict[str, object]) -> tuple[MipLocation, ...]:
    required = {
        "format": 49,
        "endianness": 1,
        "tiled": True,
        "stacked": False,
        "dimension": 1,
        "mip_min_level": 0,
        "packed_mips": True,
    }
    disagreements = {
        key: (metadata.get(key), wanted)
        for key, wanted in required.items()
        if metadata.get(key) != wanted
    }
    if disagreements:
        raise MipLayoutError(
            f"PORTME: unsupported Xenos DXN descriptor fields: {disagreements}"
        )
    width = int(metadata["width"])
    height = int(metadata["height"])
    pitch_pixels = int(metadata["pitch_pixels"])
    base_length = int(metadata["vc_base_data_length"])
    mip_length = int(metadata["vc_mip_data_length"])
    mip_max = int(metadata["mip_max_level"])
    if width <= 0 or height <= 0 or mip_max <= 0:
        raise MipLayoutError("PORTME: descriptor does not contain a mip chain")
    if pitch_pixels < width or pitch_pixels % 4:
        raise MipLayoutError("PORTME: base pitch cannot be routed as DXN blocks")

    base_pitch_blocks = _align_up(pitch_pixels // 4, 32)
    base_height_blocks = _align_up((height + 3) // 4, 32)
    calculated_base = base_pitch_blocks * base_height_blocks * 16
    if calculated_base != base_length:
        raise MipLayoutError(
            "PORTME: declared DXN base allocation differs from tiled extent "
            f"(0x{base_length:x} != 0x{calculated_base:x})"
        )
    if int(metadata["mip_address_pages"]) << 12 != base_length:
        raise MipLayoutError("PORTME: DXN mip address does not follow the base")

    result = [MipLocation(0, width, height, 0, base_length,
                          base_pitch_blocks, 0, 0, False)]
    width_pow2, height_pow2 = _next_pow2(width), _next_pow2(height)
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
        allocation = 32 * 32 * 16 if packed else _extent_bytes(mip_width, mip_height)
        pitch_blocks = 32 if packed else _align_up((mip_width + 3) // 4, 32)
        result.append(MipLocation(
            mip, mip_width, mip_height, base_length + address_offset,
            allocation, pitch_blocks, origin_x, origin_y, packed,
        ))
    calculated_end = max(item.data_offset + item.allocation_length
                         for item in result[1:])
    if calculated_end != base_length + mip_length:
        raise MipLayoutError(
            "PORTME: Xenia-derived DXN mip span differs from declaration "
            f"(0x{calculated_end-base_length:x} != 0x{mip_length:x})"
        )
    _validate_no_alias(result)
    return tuple(result)


def _offsets(location: MipLocation) -> set[int]:
    result: set[int] = set()
    for y in range(location.height_blocks):
        for x in range(location.width_blocks):
            relative = apf_inner._tiled_2d_offset(  # type: ignore[attr-defined]
                x + location.origin_block_x, y + location.origin_block_y,
                location.pitch_blocks, 4,
            )
            if relative < 0 or relative + 16 > location.allocation_length:
                raise MipLayoutError(f"mip {location.level} leaves its allocation")
            absolute = location.data_offset + relative
            if absolute in result:
                raise MipLayoutError(f"mip {location.level} aliases DXN blocks")
            result.add(absolute)
    return result


def _validate_no_alias(locations: Iterable[MipLocation]) -> None:
    owner: dict[int, int] = {}
    for location in locations:
        for offset in _offsets(location):
            if offset in owner:
                raise MipLayoutError(
                    f"active DXN blocks alias at 0x{offset:x}: "
                    f"{owner[offset]} and {location.level}"
                )
            owner[offset] = location.level


def extract_linear_dxn(texture: bytes, location: MipLocation) -> bytes:
    if location.data_offset + location.allocation_length > len(texture):
        raise MipLayoutError(f"mip {location.level} allocation exceeds texture")
    output = bytearray(location.logical_block_count * 16)
    for y in range(location.height_blocks):
        for x in range(location.width_blocks):
            relative = apf_inner._tiled_2d_offset(  # type: ignore[attr-defined]
                x + location.origin_block_x, y + location.origin_block_y,
                location.pitch_blocks, 4,
            )
            source = location.data_offset + relative
            destination = (y * location.width_blocks + x) * 16
            output[destination:destination + 16] = texture[source:source + 16]
    return apf_inner._endian_swap(bytes(output), 1)  # type: ignore[attr-defined]


def insert_linear_dxn(
    texture: bytes, location: MipLocation, linear_dxn: bytes
) -> bytes:
    expected = location.logical_block_count * 16
    if len(linear_dxn) != expected:
        raise MipLayoutError(
            f"mip {location.level} DXN length is 0x{len(linear_dxn):x}; "
            f"expected 0x{expected:x}"
        )
    transport = apf_inner._endian_swap(linear_dxn, 1)  # type: ignore[attr-defined]
    output = bytearray(texture)
    for y in range(location.height_blocks):
        for x in range(location.width_blocks):
            relative = apf_inner._tiled_2d_offset(  # type: ignore[attr-defined]
                x + location.origin_block_x, y + location.origin_block_y,
                location.pitch_blocks, 4,
            )
            destination = location.data_offset + relative
            source = (y * location.width_blocks + x) * 16
            output[destination:destination + 16] = transport[source:source + 16]
    return bytes(output)


def transport_roundtrip(
    texture: bytes, locations: Iterable[MipLocation]
) -> bytes:
    rebuilt = texture
    for location in locations:
        rebuilt = insert_linear_dxn(
            rebuilt, location, extract_linear_dxn(texture, location)
        )
    return rebuilt

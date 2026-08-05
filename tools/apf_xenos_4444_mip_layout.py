#!/usr/bin/env python3
"""Xenos packed-mip addressing for APF 2K8's uncompressed ``4_4_4_4`` textures.

The team crests (``uniform_logo_NN.iff`` / ``logo_l0`` and ``logo_l1``) are
512x512 Xenos ``4_4_4_4``: sixteen bits per texel, one nibble per channel, no
block compression.  The existing :mod:`apf_xenos_mip_layout` transcribes the
same Xenia addressing but only for BC3, where a "block" is 4x4 texels in 16
bytes; here a block is a single texel in 2 bytes.  The addressing math is
identical once those constants change, so this module keeps the BC3 writer
byte-for-byte untouched rather than making it generic underneath a proved
lane.

Why this exists at all: the crest writer byte-preserves the 0x2C000 packed mip
tail, which means a modded crest only replaces what the GPU samples at mip 0.
Every smaller draw -- the team-select tile, the logo carousel, a helmet more
than a few yards from the camera -- keeps sampling the *retail* logo out of the
untouched tail, so a mod appears not to have worked at all.  Regenerating the
tail from the new base is what makes a crest actually change on screen.

Transcribed from Xenia ``TextureInfo::GetMipLocation``,
``TextureInfo::GetPackedTileOffset`` and ``texture_address::Tiled2D`` at commit
``95a5c3ee250f80c3b9d139658649d9ffb6db3eec``, the same commit the BC3 module
cites.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import sys as _sys
from pathlib import Path as _Path
_here = str(_Path(__file__).resolve().parent)
if _here not in _sys.path:
    _sys.path.insert(0, _here)

import apf_inner


XENIA_COMMIT = "95a5c3ee250f80c3b9d139658649d9ffb6db3eec"
# One texel per block, two bytes per texel: the whole difference from BC3.
BLOCK_WIDTH = 1
BLOCK_HEIGHT = 1
BYTES_PER_BLOCK = 2
BYTES_PER_BLOCK_LOG2 = 1
STORAGE_ALIGNMENT_BLOCKS = 32
FORMAT_4_4_4_4 = 15


class MipLayoutError(ValueError):
    """Raised when texture addressing cannot be proved from the descriptor."""


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

    def manifest(self) -> dict[str, object]:
        result = asdict(self)
        result.update({
            "data_offset_hex": f"0x{self.data_offset:x}",
            "allocation_length_hex": f"0x{self.allocation_length:x}",
        })
        return result


def _align_up(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def _next_pow2(value: int) -> int:
    if value <= 0:
        raise MipLayoutError("texture dimensions must be positive")
    return 1 << (value - 1).bit_length()


def _extent_bytes(width: int, height: int) -> int:
    width_blocks = _align_up(width, STORAGE_ALIGNMENT_BLOCKS)
    height_blocks = _align_up(height, STORAGE_ALIGNMENT_BLOCKS)
    return width_blocks * height_blocks * BYTES_PER_BLOCK


def get_packed_tile_offset(
    width: int, height: int, packed_tile: int
) -> tuple[bool, int, int]:
    """Transcribe Xenia ``TextureInfo::GetPackedTileOffset``."""

    if packed_tile < 0:
        raise MipLayoutError("packed-tile index is negative")
    log2_width = (width - 1).bit_length()
    log2_height = (height - 1).bit_length()
    if min(log2_width, log2_height) > 4:
        return False, 0, 0
    if packed_tile < 3:
        if log2_width > log2_height:
            offset_x, offset_y = 0, 16 >> packed_tile
        else:
            offset_x, offset_y = 16 >> packed_tile, 0
    else:
        if log2_width > log2_height:
            offset_x, offset_y = 16 >> (packed_tile - 2), 0
        else:
            offset_x, offset_y = 0, 16 >> (packed_tile - 2)
    return True, offset_x // BLOCK_WIDTH, offset_y // BLOCK_HEIGHT


def derive_layout(metadata: dict[str, object]) -> tuple[MipLocation, ...]:
    """Every stored level of a ``4_4_4_4`` crest, base first."""

    required = {
        "format": FORMAT_4_4_4_4,
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
            f"PORTME: unsupported Xenos mip descriptor fields: {disagreements}"
        )

    width = int(metadata["width"])
    height = int(metadata["height"])
    pitch_pixels = int(metadata["pitch_pixels"])
    base_length = int(metadata["vc_base_data_length"])
    mip_length = int(metadata["vc_mip_data_length"])
    mip_max = int(metadata["mip_max_level"])
    if width <= 0 or height <= 0 or mip_max <= 0:
        raise MipLayoutError("PORTME: descriptor does not contain a mip chain")
    if pitch_pixels < width:
        raise MipLayoutError("PORTME: base pitch is narrower than the texture")

    base_pitch_blocks = _align_up(pitch_pixels, STORAGE_ALIGNMENT_BLOCKS)
    base_height_blocks = _align_up(height, STORAGE_ALIGNMENT_BLOCKS)
    calculated_base = base_pitch_blocks * base_height_blocks * BYTES_PER_BLOCK
    if base_length != calculated_base:
        raise MipLayoutError(
            "PORTME: declared base allocation differs from the Xenos tiled "
            f"extent (0x{base_length:x} != 0x{calculated_base:x})"
        )

    locations = [MipLocation(
        level=0, width=width, height=height, data_offset=0,
        allocation_length=base_length, pitch_blocks=base_pitch_blocks,
        origin_block_x=0, origin_block_y=0, packed_tail=False,
    )]
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
            allocation_length = (
                STORAGE_ALIGNMENT_BLOCKS * STORAGE_ALIGNMENT_BLOCKS
                * BYTES_PER_BLOCK
            )
            pitch_blocks = STORAGE_ALIGNMENT_BLOCKS
        else:
            allocation_length = _extent_bytes(mip_width, mip_height)
            pitch_blocks = _align_up(mip_width, STORAGE_ALIGNMENT_BLOCKS)
        locations.append(MipLocation(
            level=mip, width=mip_width, height=mip_height,
            data_offset=base_length + address_offset,
            allocation_length=allocation_length, pitch_blocks=pitch_blocks,
            origin_block_x=origin_x, origin_block_y=origin_y,
            packed_tail=packed,
        ))

    span = max(l.data_offset + l.allocation_length for l in locations[1:])
    used = span - base_length
    if used > mip_length:
        raise MipLayoutError(
            "PORTME: Xenos-derived mip span overruns the declared payload "
            f"(0x{used:x} > 0x{mip_length:x})"
        )
    # A declared tail longer than the addressed levels is normal: the
    # allocation is page-rounded.  The slack is never written, so it stays
    # byte-identical to retail.
    return tuple(locations)


def tail_padding(locations: tuple[MipLocation, ...], mip_length: int) -> int:
    base_length = locations[0].allocation_length
    span = max(l.data_offset + l.allocation_length for l in locations[1:])
    return mip_length - (span - base_length)


def _tiled_offset(location: MipLocation, block_x: int, block_y: int) -> int:
    return apf_inner._tiled_2d_offset(  # type: ignore[attr-defined]
        block_x + location.origin_block_x,
        block_y + location.origin_block_y,
        location.pitch_blocks,
        BYTES_PER_BLOCK_LOG2,
    )


def read_level(payload: bytes, location: MipLocation) -> bytes:
    """Untile one level into linear ``width * height * 2`` on-disc bytes."""

    out = bytearray(location.width * location.height * BYTES_PER_BLOCK)
    for y in range(location.height):
        for x in range(location.width):
            src = location.data_offset + _tiled_offset(location, x, y)
            dst = (y * location.width + x) * BYTES_PER_BLOCK
            out[dst:dst + BYTES_PER_BLOCK] = payload[src:src + BYTES_PER_BLOCK]
    return bytes(out)


def write_level(payload: bytearray, location: MipLocation,
                linear: bytes) -> None:
    """Tile one level back into the payload, touching only its own texels."""

    expected = location.width * location.height * BYTES_PER_BLOCK
    if len(linear) != expected:
        raise MipLayoutError(
            f"level {location.level} needs 0x{expected:x} linear bytes, "
            f"got 0x{len(linear):x}"
        )
    for y in range(location.height):
        for x in range(location.width):
            dst = location.data_offset + _tiled_offset(location, x, y)
            src = (y * location.width + x) * BYTES_PER_BLOCK
            payload[dst:dst + BYTES_PER_BLOCK] = linear[src:src + BYTES_PER_BLOCK]

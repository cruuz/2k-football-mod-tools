"""Exact APF 2K8 stadium surface-to-embedded-texture ownership and writer.

The proved venue is the retail outer-14/inner-8 ``stadium`` SCNE.  Its DRAM
part owns 78 anonymous TXTR descriptors and its VRAM part owns their pixel
allocations.  Each of the 84 serialized material records points to a bounded
GPU-command payload; those payloads contain the embedded TXTR identifiers
directly.  Draw word ``+0x20`` selects one of those material records.

This module closes that entire static join and exposes full-mip replacement for
all 78 owned descriptors: BC1, BC3, DXN/BC5 (tiled and the separately pinned
linear class), DXT5A/BC4, 8-bit, 8+8, RGB565, and RGBA8888.  A replacement
creates a new copied ``1A`` and never writes the user's source game.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import struct
from typing import Any, Iterable

from PIL import Image, __version__ as PILLOW_VERSION

from .backend import ensure_tools_importable


ensure_tools_importable()
import apf_inner  # type: ignore  # noqa: E402
import apf_helmet_color_transport as dxn_codec  # type: ignore  # noqa: E402
import apf_outer  # type: ignore  # noqa: E402
import apf_pants_color_transport as bc1_transport  # type: ignore  # noqa: E402
import apf_scene  # type: ignore  # noqa: E402
import apf_stadium_static_position_patch as stadium_container  # type: ignore  # noqa: E402
import apf_texture_patch as archive_patch  # type: ignore  # noqa: E402
import apf_uniform_mip_patch as bc3_transport  # type: ignore  # noqa: E402
import apf_xenos_bc1_mip_layout as bc1_mips  # type: ignore  # noqa: E402
import apf_xenos_dxn_mip_layout as dxn_mips  # type: ignore  # noqa: E402
import apf_xenos_dxt5a as dxt5a_codec  # type: ignore  # noqa: E402
import apf_xenos_mip_layout as bc3_mips  # type: ignore  # noqa: E402
import nfl_dxt1  # type: ignore  # noqa: E402


SCHEMA = "apf2k8_stadium_embedded_texture_patch/v1"
MANIFEST_NAME = "apf2k8_stadium_embedded_texture_manifest.json"
OUTPUT_PACK_NAME = "1A"
TEXTURE_RECORD_SIZE = 0xE0
MATERIAL_RECORD_SIZE = 0x28
DRAW_RECORD_SIZE = 0x30
EDITABLE_FORMATS = frozenset(
    {"DXT1", "DXT4_5", "DXN", "DXT5A", "8", "8_8", "5_6_5", "8_8_8_8"}
)
OUTER_INDEX = stadium_container.OUTER_INDEX
INNER_INDEX = stadium_container.INNER_INDEX
SYSTEM_SHA256 = stadium_container.SYSTEM_SHA256
VRAM_SHA256 = stadium_container.VRAM_SHA256
OUTER_SHA256 = stadium_container.OUTER_SHA256
OUTER_LENGTH = stadium_container.OUTER_LENGTH
SOURCE_FILE_LENGTH = stadium_container.SOURCE_FILE_LENGTH
FOOTER_TOTAL = stadium_container.FOOTER_TOTAL
FOOTER_SHA256 = stadium_container.FOOTER_SHA256


class StadiumTextureError(ValueError):
    """The source, ownership join, image, or copied output left the proof."""


@dataclass(frozen=True, slots=True)
class EmbeddedTexture:
    index: int
    texture_id: int
    record_offset: int
    video_offset: int
    payload_length: int
    width: int
    height: int
    format_name: str
    metadata: dict[str, object]
    material_slots: tuple[int, ...]

    @property
    def selector(self) -> str:
        return f"outer14.inner8.texture{self.index:03d}"

    @property
    def editable(self) -> bool:
        return _is_editable_metadata(self.metadata)

    @property
    def label(self) -> str:
        return (
            f"Embedded {self.index:02d} · {self.width}×{self.height} · "
            f"{self.format_name}"
        )


@dataclass(frozen=True, slots=True)
class MaterialBinding:
    slot: int
    identity_hash: int
    shader_family_hash: int
    payload_offset: int
    payload_length: int
    texture_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class SurfaceBinding:
    node_index: int
    node_name: str
    material_slots: tuple[int, ...]
    texture_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class StadiumTextureCatalog:
    textures: tuple[EmbeddedTexture, ...]
    materials: tuple[MaterialBinding, ...]
    surfaces: tuple[SurfaceBinding, ...]
    shader_family_count: int
    system_sha256: str
    vram_sha256: str

    def textures_for_nodes(self, node_indices: Iterable[int]) -> tuple[EmbeddedTexture, ...]:
        wanted = {int(value) for value in node_indices}
        indices = {
            texture
            for surface in self.surfaces
            if surface.node_index in wanted
            for texture in surface.texture_indices
        }
        return tuple(self.textures[index] for index in sorted(indices))


@dataclass(frozen=True, slots=True)
class StadiumTextureReceipt:
    output_directory: Path
    output_pack: Path
    manifest_path: Path
    texture: EmbeddedTexture
    mode: str
    changed_vram_bytes: int
    manifest: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _GenericMipLocation:
    level: int
    width: int
    height: int
    data_offset: int
    allocation_length: int
    pitch_blocks: int
    origin_block_x: int
    origin_block_y: int
    packed_tail: bool
    block_width: int
    block_height: int
    bytes_per_block: int

    @property
    def width_blocks(self) -> int:
        return (self.width + self.block_width - 1) // self.block_width

    @property
    def height_blocks(self) -> int:
        return (self.height + self.block_height - 1) // self.block_height

    @property
    def logical_block_count(self) -> int:
        return self.width_blocks * self.height_blocks


_GENERIC_FORMATS: dict[str, tuple[int, int, int, int, int]] = {
    # format number, block width, block height, bytes per block, endian mode
    "8": (2, 1, 1, 1, 0),
    "5_6_5": (4, 1, 1, 2, 1),
    "8_8_8_8": (6, 1, 1, 4, 2),
    "8_8": (10, 1, 1, 2, 1),
    "DXT5A": (59, 4, 4, 8, 1),
}


def _align_up(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def _next_pow2(value: int) -> int:
    if value <= 0:
        raise StadiumTextureError("texture dimensions must be positive")
    return 1 << (value - 1).bit_length()


def _packed_origin(
    width: int, height: int, packed_tile: int, block_width: int, block_height: int
) -> tuple[bool, int, int]:
    if packed_tile < 0:
        raise StadiumTextureError("packed-mip index is negative")
    log2_width = (width - 1).bit_length()
    log2_height = (height - 1).bit_length()
    if min(log2_width, log2_height) > 4:
        return False, 0, 0
    if packed_tile < 3:
        x, y = ((0, 16 >> packed_tile) if log2_width > log2_height else (16 >> packed_tile, 0))
    else:
        x, y = (
            (16 >> (packed_tile - 2), 0)
            if log2_width > log2_height
            else (0, 16 >> (packed_tile - 2))
        )
    return True, x // block_width, y // block_height


def _generic_extent(
    width: int, height: int, block_width: int, block_height: int, bytes_per_block: int
) -> int:
    blocks_wide = _align_up((width + block_width - 1) // block_width, 32)
    blocks_high = _align_up((height + block_height - 1) // block_height, 32)
    # APF's uncompressed small levels retain a full 4-KiB Xenos page.
    return max(0x1000, blocks_wide * blocks_high * bytes_per_block)


def _derive_generic_layout(
    metadata: dict[str, object], format_name: str
) -> tuple[_GenericMipLocation, ...]:
    try:
        format_value, block_width, block_height, bytes_per_block, endian = _GENERIC_FORMATS[
            format_name
        ]
    except KeyError as exc:
        raise StadiumTextureError(f"no generic mip transport for {format_name}") from exc
    required = {
        "format": format_value,
        "endianness": endian,
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
        raise StadiumTextureError(
            f"unsupported {format_name} stadium descriptor fields: {disagreements}"
        )
    width = int(metadata["width"])
    height = int(metadata["height"])
    pitch_pixels = int(metadata["pitch_pixels"])
    base_length = int(metadata["vc_base_data_length"])
    mip_length = int(metadata["vc_mip_data_length"])
    mip_max = int(metadata["mip_max_level"])
    if width <= 0 or height <= 0 or mip_max <= 0:
        raise StadiumTextureError(f"{format_name} descriptor has no full mip chain")
    if pitch_pixels < width or pitch_pixels % block_width:
        raise StadiumTextureError(f"{format_name} base pitch cannot be routed")
    pitch_blocks = _align_up(pitch_pixels // block_width, 32)
    height_blocks = _align_up((height + block_height - 1) // block_height, 32)
    calculated_base = max(0x1000, pitch_blocks * height_blocks * bytes_per_block)
    if calculated_base != base_length:
        raise StadiumTextureError(
            f"{format_name} base allocation differs from its tiled extent"
        )
    if int(metadata["mip_address_pages"]) << 12 != base_length:
        raise StadiumTextureError(f"{format_name} mip allocation does not follow base")
    result = [
        _GenericMipLocation(
            0, width, height, 0, base_length, pitch_blocks, 0, 0, False,
            block_width, block_height, bytes_per_block,
        )
    ]
    width_pow2, height_pow2 = _next_pow2(width), _next_pow2(height)
    for mip in range(1, mip_max + 1):
        address_offset = 0
        packed_mip_base = 1
        for prior in range(1, mip):
            prior_width = max(width_pow2 >> prior, 1)
            prior_height = max(height_pow2 >> prior, 1)
            if min(prior_width, prior_height) <= 16:
                break
            address_offset += _generic_extent(
                prior_width, prior_height, block_width, block_height, bytes_per_block
            )
            packed_mip_base += 1
        mip_width = max(width_pow2 >> mip, 1)
        mip_height = max(height_pow2 >> mip, 1)
        packed, origin_x, origin_y = _packed_origin(
            mip_width, mip_height, mip - packed_mip_base, block_width, block_height
        )
        allocation = (
            max(0x1000, 32 * 32 * bytes_per_block)
            if packed
            else _generic_extent(
                mip_width, mip_height, block_width, block_height, bytes_per_block
            )
        )
        result.append(
            _GenericMipLocation(
                mip,
                mip_width,
                mip_height,
                base_length + address_offset,
                allocation,
                32
                if packed
                else _align_up((mip_width + block_width - 1) // block_width, 32),
                origin_x,
                origin_y,
                packed,
                block_width,
                block_height,
                bytes_per_block,
            )
        )
    if max(item.data_offset + item.allocation_length for item in result[1:]) != (
        base_length + mip_length
    ):
        raise StadiumTextureError(
            f"{format_name} packed-mip span differs from its descriptor"
        )
    owners: dict[int, int] = {}
    for location in result:
        for y in range(location.height_blocks):
            for x in range(location.width_blocks):
                relative = apf_inner._tiled_2d_offset(  # type: ignore[attr-defined]
                    x + location.origin_block_x,
                    y + location.origin_block_y,
                    location.pitch_blocks,
                    bytes_per_block.bit_length() - 1,
                )
                absolute = location.data_offset + relative
                if relative + bytes_per_block > location.allocation_length:
                    raise StadiumTextureError(f"{format_name} mip address leaves allocation")
                if absolute in owners:
                    raise StadiumTextureError(f"{format_name} active mip blocks alias")
                owners[absolute] = location.level
    return tuple(result)


def _generic_extract(
    texture: bytes, location: _GenericMipLocation, endian: int
) -> bytes:
    output = bytearray(location.logical_block_count * location.bytes_per_block)
    for y in range(location.height_blocks):
        for x in range(location.width_blocks):
            relative = apf_inner._tiled_2d_offset(  # type: ignore[attr-defined]
                x + location.origin_block_x,
                y + location.origin_block_y,
                location.pitch_blocks,
                location.bytes_per_block.bit_length() - 1,
            )
            source = location.data_offset + relative
            destination = (y * location.width_blocks + x) * location.bytes_per_block
            output[destination : destination + location.bytes_per_block] = texture[
                source : source + location.bytes_per_block
            ]
    return apf_inner._endian_swap(bytes(output), endian)  # type: ignore[attr-defined]


def _generic_insert(
    texture: bytes, location: _GenericMipLocation, linear: bytes, endian: int
) -> bytes:
    expected = location.logical_block_count * location.bytes_per_block
    if len(linear) != expected:
        raise StadiumTextureError("linear generic mip length changed")
    stored = apf_inner._endian_swap(linear, endian)  # type: ignore[attr-defined]
    output = bytearray(texture)
    for y in range(location.height_blocks):
        for x in range(location.width_blocks):
            relative = apf_inner._tiled_2d_offset(  # type: ignore[attr-defined]
                x + location.origin_block_x,
                y + location.origin_block_y,
                location.pitch_blocks,
                location.bytes_per_block.bit_length() - 1,
            )
            destination = location.data_offset + relative
            source = (y * location.width_blocks + x) * location.bytes_per_block
            output[destination : destination + location.bytes_per_block] = stored[
                source : source + location.bytes_per_block
            ]
    return bytes(output)


def _generic_roundtrip(
    texture: bytes,
    locations: Iterable[_GenericMipLocation],
    endian: int,
) -> bytes:
    rebuilt = texture
    for location in locations:
        rebuilt = _generic_insert(
            rebuilt, location, _generic_extract(texture, location, endian), endian
        )
    return rebuilt


def _derive_linear_dxn_layout(
    metadata: dict[str, object],
) -> tuple[dxn_mips.MipLocation, ...]:
    """Validate the one stadium linear DXN class and recover its packed tail."""

    required = {
        "format": 49,
        "endianness": 1,
        "tiled": False,
        "stacked": False,
        "dimension": 1,
        "mip_min_level": 0,
        "packed_mips": True,
        "width": 32,
        "height": 32,
        "pitch_pixels": 128,
        "vc_base_data_length": 0x4000,
        "vc_mip_data_length": 0x4000,
        "mip_max_level": 3,
        "mip_address_pages": 4,
        "swizzle_components": [0, 1, 2, 3],
    }
    disagreements = {
        key: (metadata.get(key), expected)
        for key, expected in required.items()
        if metadata.get(key) != expected
    }
    if disagreements:
        raise StadiumTextureError(
            f"unsupported linear DXN stadium descriptor fields: {disagreements}"
        )
    result = [dxn_mips.MipLocation(0, 32, 32, 0, 0x4000, 32, 0, 0, False)]
    for level, size in ((1, 16), (2, 8), (3, 4)):
        packed, origin_x, origin_y = _packed_origin(size, size, level - 1, 4, 4)
        if not packed:
            raise StadiumTextureError("linear DXN packed-tail derivation changed")
        result.append(
            dxn_mips.MipLocation(
                level, size, size, 0x4000, 0x4000, 32,
                origin_x, origin_y, True,
            )
        )
    owners: dict[int, int] = {}
    for location in result:
        for y in range(location.height_blocks):
            for x in range(location.width_blocks):
                offset = location.data_offset + (
                    (y + location.origin_block_y) * location.pitch_blocks
                    + x
                    + location.origin_block_x
                ) * 16
                if offset + 16 > location.data_offset + location.allocation_length:
                    raise StadiumTextureError("linear DXN mip leaves its allocation")
                if offset in owners:
                    raise StadiumTextureError("linear DXN active mip blocks alias")
                owners[offset] = location.level
    return tuple(result)


def _linear_dxn_extract(texture: bytes, location: dxn_mips.MipLocation) -> bytes:
    output = bytearray(location.logical_block_count * 16)
    for y in range(location.height_blocks):
        for x in range(location.width_blocks):
            source = location.data_offset + (
                (y + location.origin_block_y) * location.pitch_blocks
                + x
                + location.origin_block_x
            ) * 16
            destination = (y * location.width_blocks + x) * 16
            output[destination : destination + 16] = texture[source : source + 16]
    return apf_inner._endian_swap(bytes(output), 1)  # type: ignore[attr-defined]


def _linear_dxn_insert(
    texture: bytes, location: dxn_mips.MipLocation, linear: bytes
) -> bytes:
    if len(linear) != location.logical_block_count * 16:
        raise StadiumTextureError("linear DXN mip length changed")
    stored = apf_inner._endian_swap(linear, 1)  # type: ignore[attr-defined]
    output = bytearray(texture)
    for y in range(location.height_blocks):
        for x in range(location.width_blocks):
            destination = location.data_offset + (
                (y + location.origin_block_y) * location.pitch_blocks
                + x
                + location.origin_block_x
            ) * 16
            source = (y * location.width_blocks + x) * 16
            output[destination : destination + 16] = stored[source : source + 16]
    return bytes(output)


def _linear_dxn_roundtrip(
    texture: bytes, locations: Iterable[dxn_mips.MipLocation]
) -> bytes:
    rebuilt = texture
    for location in locations:
        rebuilt = _linear_dxn_insert(
            rebuilt, location, _linear_dxn_extract(texture, location)
        )
    return rebuilt


def _is_editable_metadata(metadata: dict[str, object]) -> bool:
    try:
        name = str(metadata["format_name"])
        if name == "DXT1":
            bc1_mips.derive_layout(metadata)
        elif name == "DXT4_5":
            bc3_mips.derive_layout(metadata)
        elif name == "DXN":
            if metadata.get("tiled"):
                dxn_mips.derive_layout(metadata)
            else:
                _derive_linear_dxn_layout(metadata)
        elif name in _GENERIC_FORMATS:
            _derive_generic_layout(metadata, name)
        else:
            return False
    except (ValueError, KeyError):
        return False
    return True


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _u32(data: bytes, offset: int, label: str) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise StadiumTextureError(f"{label}: u32 is outside the SCNE system part")
    return struct.unpack_from(">I", data, offset)[0]


def _relative(data: bytes, field: int, label: str) -> int:
    raw = _u32(data, field, label)
    if raw == 0:
        raise StadiumTextureError(f"{label}: required relative pointer is null")
    target = field + raw - 1
    if not 0 <= target < len(data):
        raise StadiumTextureError(f"{label}: relative pointer leaves the SCNE system part")
    return target


def _part_hashes(
    record: apf_inner.IFFRecord, blocks: list[bytes]
) -> dict[tuple[int, int], str]:
    return {
        (item.index, part_index): _sha256(
            blocks[part.block_index][part.offset : part.offset + part.length]
        )
        for item in record.files
        for part_index, part in enumerate(item.parts)
    }


def _source(
    game_root: Path,
) -> tuple[
    apf_outer.Entry,
    apf_inner.IFFRecord,
    bytes,
    list[bytes],
    list[bytes],
    bytes,
    bytes,
]:
    game_root = Path(game_root)
    _archive, entry = stadium_container._validate_archive(game_root)  # type: ignore[attr-defined]
    archive = apf_outer.parse_archive(game_root / "0A")
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        original_entry = reader.read(entry, 0, entry.size)
        blocks = [
            apf_inner.decode_block(reader, record, index, 1 << 30)
            for index in range(record.block_count)
        ]
        stored = [
            reader.read(entry, block.start_offset, block.stored_length)
            for block in record.blocks
        ]
    if _sha256(original_entry) != OUTER_SHA256:
        raise StadiumTextureError("retail outer-14 stadium package identity changed")
    if (
        record.header_size != 292
        or record.file_length != SOURCE_FILE_LENGTH
        or record.block_count != 2
        or record.file_count != 9
    ):
        raise StadiumTextureError("retail stadium IFF envelope changed")
    item = record.files[INNER_INDEX]
    if (
        item.name != "stadium"
        or item.type_name != "SCNE"
        or len(item.parts) != 2
        or item.parts[0] != apf_inner.FilePart(0, 0, stadium_container.SYSTEM_LENGTH)
        or item.parts[1] != apf_inner.FilePart(1, 0, stadium_container.VRAM_LENGTH)
    ):
        raise StadiumTextureError("retail stadium SCNE DRAM/VRAM ownership changed")
    system = blocks[0][: stadium_container.SYSTEM_LENGTH]
    vram = blocks[1][: stadium_container.VRAM_LENGTH]
    if _sha256(system) != SYSTEM_SHA256 or _sha256(vram) != VRAM_SHA256:
        raise StadiumTextureError("retail stadium SCNE identity changed")
    return entry, record, original_entry, blocks, stored, system, vram


def _material_payload_end(scene: dict[str, object], final_start: int, size: int) -> int:
    offsets: list[int] = []
    for node in scene["nodes"]:  # type: ignore[index]
        for key in (
            "offset",
            "draw_record_offset",
            "mesh_descriptor_offset",
            "index_offset",
        ):
            value = node.get(key)
            if isinstance(value, int) and value > final_start:
                offsets.append(value)
        hierarchy = node.get("hierarchy")
        if isinstance(hierarchy, dict):
            value = hierarchy.get("offset")
            if isinstance(value, int) and value > final_start:
                offsets.append(value)
        for declaration in node.get("vertex_declarations", []):
            value = declaration.get("offset")
            if isinstance(value, int) and value > final_start:
                offsets.append(value)
        for mesh in node.get("meshes", []):
            for stream in mesh.get("streams", []):
                value = stream.get("start")
                if isinstance(value, int) and value > final_start:
                    offsets.append(value)
    if not offsets:
        raise StadiumTextureError("could not bound the final material command payload")
    end = min(offsets)
    if end <= final_start or end > size:
        raise StadiumTextureError("final material command payload has an invalid extent")
    return end


def _catalog_from_parts(system: bytes, vram: bytes) -> StadiumTextureCatalog:
    scene = apf_scene.parse_scene_system_part(
        system,
        outer_index=OUTER_INDEX,
        inner_index=INNER_INDEX,
        capture_geometry=False,
    )
    if scene.get("root_name") != "stadium" or scene.get("scene_node_count") != 89:
        raise StadiumTextureError("outer-14 stadium node roster changed")

    texture_count = _u32(system, 0x20, "embedded texture count")
    texture_start = _relative(system, 0x24, "embedded texture table")
    if (texture_count, texture_start) != (78, 0x5B0):
        raise StadiumTextureError("outer-14 embedded texture table changed")
    raw_textures: list[dict[str, Any]] = []
    texture_id_to_index: dict[int, int] = {}
    allocations: list[tuple[int, int, int]] = []
    for index in range(texture_count):
        start = texture_start + index * TEXTURE_RECORD_SIZE
        raw = system[start : start + TEXTURE_RECORD_SIZE]
        if len(raw) != TEXTURE_RECORD_SIZE:
            raise StadiumTextureError("embedded TXTR descriptor table is truncated")
        metadata = apf_inner.parse_txtr_metadata(raw)
        texture_id = _u32(raw, 0, f"embedded texture {index} ID")
        if texture_id in texture_id_to_index:
            raise StadiumTextureError("embedded texture IDs are not unique")
        texture_id_to_index[texture_id] = index
        address = _u32(raw, 0x6C, f"embedded texture {index} VRAM address")
        if address & 0xFFF != 1:
            raise StadiumTextureError("embedded texture VRAM address flags changed")
        offset = address & ~0xFFF
        length = int(metadata["vc_base_data_length"]) + int(
            metadata["vc_mip_data_length"]
        )
        if length <= 0 or offset + length > len(vram):
            raise StadiumTextureError("embedded texture allocation leaves stadium VRAM")
        allocations.append((offset, offset + length, index))
        raw_textures.append(
            {
                "index": index,
                "texture_id": texture_id,
                "record_offset": start,
                "video_offset": offset,
                "payload_length": length,
                "width": int(metadata["width"]),
                "height": int(metadata["height"]),
                "format_name": str(metadata["format_name"]),
                "metadata": metadata,
            }
        )
    ordered = sorted(allocations)
    if any(first[1] > second[0] for first, second in zip(ordered, ordered[1:])):
        raise StadiumTextureError("embedded stadium texture allocations overlap")

    shader_count = _u32(system, 0x28, "shader family count")
    shader_start = _relative(system, 0x2C, "shader family table")
    material_count = _u32(system, 0x30, "material count")
    if _u32(system, 0x34, "legacy material pointer") != 0:
        raise StadiumTextureError("outer-14 legacy material pointer is no longer null")
    material_start = _relative(system, 0x38, "material table")
    if (shader_count, shader_start, material_count, material_start) != (
        20,
        0x49F0,
        84,
        0x4DB0,
    ):
        raise StadiumTextureError("outer-14 shader/material tables changed")
    if shader_start + shader_count * 0x30 != material_start:
        raise StadiumTextureError("shader-family table no longer ends at materials")
    if material_start + material_count * MATERIAL_RECORD_SIZE != 0x5AD0:
        raise StadiumTextureError("serialized material table extent changed")

    payload_starts = [
        _relative(
            system,
            material_start + slot * MATERIAL_RECORD_SIZE + 0x20,
            f"material {slot} command payload",
        )
        for slot in range(material_count)
    ]
    if payload_starts != sorted(payload_starts) or len(set(payload_starts)) != material_count:
        raise StadiumTextureError("material command payload pointers are not strictly ordered")
    final_end = _material_payload_end(scene, payload_starts[-1], len(system))
    payload_ends = payload_starts[1:] + [final_end]
    materials: list[MaterialBinding] = []
    texture_materials: list[list[int]] = [[] for _ in raw_textures]
    for slot, (start, end) in enumerate(zip(payload_starts, payload_ends)):
        if start >= end or start & 0xF or end > len(system):
            raise StadiumTextureError("material command payload extent changed")
        indices: list[int] = []
        for offset in range(start, end - 3, 4):
            index = texture_id_to_index.get(_u32(system, offset, "material payload word"))
            if index is not None and index not in indices:
                indices.append(index)
        if not indices:
            raise StadiumTextureError(f"material slot {slot} has no embedded texture owner")
        for index in indices:
            texture_materials[index].append(slot)
        record = material_start + slot * MATERIAL_RECORD_SIZE
        materials.append(
            MaterialBinding(
                slot=slot,
                identity_hash=_u32(system, record, "material identity"),
                shader_family_hash=_u32(system, record + 8, "material shader family"),
                payload_offset=start,
                payload_length=end - start,
                texture_indices=tuple(indices),
            )
        )
    if any(not owners for owners in texture_materials):
        raise StadiumTextureError("one or more embedded textures have no material owner")

    surfaces: list[SurfaceBinding] = []
    referenced_materials: set[int] = set()
    for node in scene["nodes"]:  # type: ignore[index]
        draw_count = int(node["draw_record_count"])
        draw_start = node["draw_record_offset"]
        if draw_count and not isinstance(draw_start, int):
            raise StadiumTextureError("node draw table is missing")
        slots: list[int] = []
        for draw in range(draw_count):
            slot = _u32(
                system,
                int(draw_start) + draw * DRAW_RECORD_SIZE + 0x20,
                "draw material slot",
            )
            if slot >= material_count:
                raise StadiumTextureError("draw material slot exceeds the material table")
            if slot not in slots:
                slots.append(slot)
            referenced_materials.add(slot)
        texture_indices = sorted(
            {
                texture
                for slot in slots
                for texture in materials[slot].texture_indices
            }
        )
        surfaces.append(
            SurfaceBinding(
                node_index=int(node["index"]),
                node_name=str(node["name"]),
                material_slots=tuple(slots),
                texture_indices=tuple(texture_indices),
            )
        )
    if referenced_materials != set(range(material_count)):
        raise StadiumTextureError("not every serialized material is owned by a draw")
    textures = tuple(
        EmbeddedTexture(
            **row,
            material_slots=tuple(texture_materials[int(row["index"])]),
        )
        for row in raw_textures
    )
    return StadiumTextureCatalog(
        textures=textures,
        materials=tuple(materials),
        surfaces=tuple(surfaces),
        shader_family_count=shader_count,
        system_sha256=_sha256(system),
        vram_sha256=_sha256(vram),
    )


def load_catalog(game_root: Path) -> StadiumTextureCatalog:
    """Authenticate and recover the full outer-14 static ownership graph."""

    *_unused, system, vram = _source(Path(game_root))
    return _catalog_from_parts(system, vram)


def _texture_bytes(vram: bytes, texture: EmbeddedTexture) -> bytes:
    payload = vram[
        texture.video_offset : texture.video_offset + texture.payload_length
    ]
    if len(payload) != texture.payload_length:
        raise StadiumTextureError("embedded texture payload is truncated")
    return payload


def _swizzle(raw: tuple[int, int, int, int], selectors: Iterable[int]) -> bytes:
    values = (*raw, 0, 255, 0, 0)
    return bytes(values[int(selector)] for selector in selectors)


def _decode_generic_level(
    texture: EmbeddedTexture, payload: bytes, location: _GenericMipLocation
) -> bytes:
    name = texture.format_name
    endian = _GENERIC_FORMATS[name][4]
    linear = _generic_extract(payload, location, endian)
    selectors = tuple(int(value) for value in texture.metadata["swizzle_components"])
    if name == "DXT5A":
        rgba = bytearray(location.width * location.height * 4)
        for block_y in range(location.height_blocks):
            for block_x in range(location.width_blocks):
                block_index = block_y * location.width_blocks + block_x
                values = dxt5a_codec.decode_block(
                    linear[block_index * 8 : block_index * 8 + 8]
                )
                for local_y in range(4):
                    for local_x in range(4):
                        x, y = block_x * 4 + local_x, block_y * 4 + local_y
                        if x < location.width and y < location.height:
                            scalar = values[local_y * 4 + local_x]
                            offset = (y * location.width + x) * 4
                            rgba[offset : offset + 4] = _swizzle(
                                (scalar, 0, 0, 0), selectors
                            )
        return bytes(rgba)
    rgba = bytearray(location.width * location.height * 4)
    for pixel in range(location.width * location.height):
        if name == "8":
            raw = (linear[pixel], 0, 0, 0)
        elif name == "8_8":
            raw = (linear[pixel * 2], linear[pixel * 2 + 1], 0, 0)
        elif name == "5_6_5":
            value = int.from_bytes(linear[pixel * 2 : pixel * 2 + 2], "little")
            raw = (*apf_inner._rgb565(value), 255)  # type: ignore[attr-defined]
        elif name == "8_8_8_8":
            raw = tuple(linear[pixel * 4 : pixel * 4 + 4])
        else:  # pragma: no cover - routed by the generic format table
            raise StadiumTextureError(f"no decoder for {name}")
        rgba[pixel * 4 : pixel * 4 + 4] = _swizzle(raw, selectors)
    return bytes(rgba)


def _decode_texture_base(texture: EmbeddedTexture, payload: bytes) -> bytes:
    if texture.format_name in {"DXT1", "DXT4_5"}:
        base_length = int(texture.metadata["vc_base_data_length"])
        width, height, rgba = apf_inner.decode_txtr_base_rgba(
            texture.metadata, payload[:base_length]
        )
        if (width, height) != (texture.width, texture.height):
            raise StadiumTextureError("embedded texture decoded dimensions changed")
        return rgba
    if texture.format_name == "DXN":
        if texture.metadata.get("tiled"):
            locations = dxn_mips.derive_layout(texture.metadata)
            linear = dxn_mips.extract_linear_dxn(payload, locations[0])
        else:
            locations = _derive_linear_dxn_layout(texture.metadata)
            linear = _linear_dxn_extract(payload, locations[0])
        return dxn_codec.decode_linear_dxn(linear, locations[0])
    if texture.format_name in _GENERIC_FORMATS:
        locations = _derive_generic_layout(texture.metadata, texture.format_name)
        return _decode_generic_level(texture, payload, locations[0])
    raise StadiumTextureError(
        f"{texture.format_name} has no proved PNG decoder for this descriptor"
    )


def decoded_rgba(game_root: Path, texture_index: int) -> tuple[EmbeddedTexture, bytes]:
    """Return exact base-level RGBA for one authenticated embedded texture."""

    *_prefix, _system, vram = _source(Path(game_root))
    catalog = _catalog_from_parts(_system, vram)
    if not 0 <= texture_index < len(catalog.textures):
        raise StadiumTextureError("embedded texture index must be in 0..77")
    texture = catalog.textures[texture_index]
    payload = _texture_bytes(vram, texture)
    return texture, _decode_texture_base(texture, payload)


def export_png(game_root: Path, texture_index: int, destination: Path) -> Path:
    """Write a new private PNG without ever overwriting an existing path."""

    texture, rgba = decoded_rgba(game_root, texture_index)
    destination = Path(destination)
    if destination.suffix.casefold() != ".png":
        raise StadiumTextureError("embedded stadium texture exports require .png")
    if os.path.lexists(destination):
        raise StadiumTextureError("stadium texture export never overwrites a file")
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise StadiumTextureError("stadium texture export parent must be a real directory")
    image = Image.frombytes("RGBA", (texture.width, texture.height), rgba)
    encoded = io.BytesIO()
    image.save(encoded, format="PNG", optimize=False)
    archive_patch._write_new(destination, encoded.getvalue())  # type: ignore[attr-defined]
    return destination


def stage_replacement_png(
    game_root: Path,
    texture_index: int,
    source_png: Path,
    destination: Path,
) -> tuple[Path, tuple[int, int]]:
    """Validate, auto-resize, and snapshot a replacement to a new private PNG."""

    catalog = load_catalog(game_root)
    if not 0 <= texture_index < len(catalog.textures):
        raise StadiumTextureError("embedded texture index must be in 0..77")
    texture = catalog.textures[texture_index]
    if not texture.editable:
        raise StadiumTextureError("embedded texture descriptor has no proved writer")
    rgba, source_size = _load_and_resize_png(Path(source_png), texture)
    destination = Path(destination)
    if destination.suffix.casefold() != ".png" or os.path.lexists(destination):
        raise StadiumTextureError("staged stadium replacement must be a new .png")
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise StadiumTextureError("staged stadium replacement parent must be real")
    encoded = io.BytesIO()
    Image.frombytes("RGBA", (texture.width, texture.height), rgba).save(
        encoded, format="PNG", optimize=False
    )
    archive_patch._write_new(destination, encoded.getvalue())  # type: ignore[attr-defined]
    return destination, source_size


def _load_and_resize_png(path: Path, texture: EmbeddedTexture) -> tuple[bytes, tuple[int, int]]:
    try:
        info = path.lstat()
    except OSError as exc:
        raise StadiumTextureError(f"could not inspect replacement PNG: {exc}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_size > 64 * 1024 * 1024:
        raise StadiumTextureError("replacement PNG must be a bounded regular non-symlink file")
    with Image.open(path) as image:
        if image.format != "PNG":
            raise StadiumTextureError("replacement image must be PNG")
        source_size = image.size
        if (
            source_size[0] <= 0
            or source_size[1] <= 0
            or source_size[0] > 8192
            or source_size[1] > 8192
            or source_size[0] * source_size[1] > 32 * 1024 * 1024
        ):
            raise StadiumTextureError(
                "replacement PNG dimensions exceed the 8192×8192 / 32-megapixel bound"
            )
        image.load()
        converted = image.convert("RGBA")
        if converted.size != (texture.width, texture.height):
            converted = converted.resize(
                (texture.width, texture.height), Image.Resampling.LANCZOS
            )
        rgba = converted.tobytes()
    if texture.format_name == "DXT1" and any(
        rgba[index] != 255 for index in range(3, len(rgba), 4)
    ):
        raise StadiumTextureError(
            "DXT1 stadium textures require opaque artwork; flatten transparency first"
        )
    return rgba, source_size


def _resize_level(
    rgba: bytes, source_size: tuple[int, int], target_size: tuple[int, int]
) -> bytes:
    if source_size == target_size:
        return rgba
    return Image.frombytes("RGBA", source_size, rgba).resize(
        target_size, Image.Resampling.LANCZOS
    ).tobytes()


def _encode_bc1_level(rgba: bytes, location: Any) -> bytes:
    output = bytearray()
    for block_y in range(location.height_blocks):
        for block_x in range(location.width_blocks):
            pixels = []
            for local_y in range(4):
                for local_x in range(4):
                    x = min(block_x * 4 + local_x, location.width - 1)
                    y = min(block_y * 4 + local_y, location.height - 1)
                    offset = (y * location.width + x) * 4
                    pixels.append(tuple(rgba[offset : offset + 3]))
            encoded, _error, _pairs, _selectors = nfl_dxt1.encode_block(pixels)
            output.extend(encoded)
    return bytes(output)


def _encode_bc3_level(rgba: bytes, location: Any) -> bytes:
    output = bytearray()
    for block_y in range(location.height_blocks):
        for block_x in range(location.width_blocks):
            pixels = []
            for local_y in range(4):
                for local_x in range(4):
                    x = min(block_x * 4 + local_x, location.width - 1)
                    y = min(block_y * 4 + local_y, location.height - 1)
                    offset = (y * location.width + x) * 4
                    pixels.append(tuple(rgba[offset : offset + 4]))
            output.extend(archive_patch.encode_bc3_block(pixels))
    return bytes(output)


def _luma(red: int, green: int, blue: int) -> int:
    return (77 * red + 150 * green + 29 * blue + 128) >> 8


def _encode_dxn_level(rgba: bytes, location: Any) -> bytes:
    output = bytearray()
    for block_y in range(location.height_blocks):
        for block_x in range(location.width_blocks):
            pairs = []
            for local_y in range(4):
                for local_x in range(4):
                    x = min(block_x * 4 + local_x, location.width - 1)
                    y = min(block_y * 4 + local_y, location.height - 1)
                    offset = (y * location.width + x) * 4
                    pairs.append((rgba[offset], rgba[offset + 1]))
            encoded, _metrics = dxn_codec.encode_dxn(tuple(pairs))
            output.extend(encoded)
    return bytes(output)


def _encode_generic_level(
    texture: EmbeddedTexture, rgba: bytes, location: _GenericMipLocation
) -> bytes:
    name = texture.format_name
    if name == "DXT5A":
        output = bytearray()
        for block_y in range(location.height_blocks):
            for block_x in range(location.width_blocks):
                samples = []
                for local_y in range(4):
                    for local_x in range(4):
                        x = min(block_x * 4 + local_x, location.width - 1)
                        y = min(block_y * 4 + local_y, location.height - 1)
                        offset = (y * location.width + x) * 4
                        samples.append(_luma(*rgba[offset : offset + 3]))
                encoded, _error = dxt5a_codec.encode_block(tuple(samples))
                output.extend(encoded)
        return bytes(output)
    output = bytearray()
    selectors = tuple(int(value) for value in texture.metadata["swizzle_components"])
    for pixel in range(location.width * location.height):
        rgba_pixel = tuple(rgba[pixel * 4 : pixel * 4 + 4])
        if name == "8":
            output.append(_luma(*rgba_pixel[:3]))
        elif name == "8_8":
            output.extend((_luma(*rgba_pixel[:3]), rgba_pixel[3]))
        elif name == "5_6_5":
            # Stadium 565 uses BGR fetch swizzle [2,1,0,5].
            if selectors != (2, 1, 0, 5):
                raise StadiumTextureError("unsupported 565 stadium channel swizzle")
            raw_red, raw_green, raw_blue = (
                rgba_pixel[2],
                rgba_pixel[1],
                rgba_pixel[0],
            )
            packed = (
                ((raw_red * 31 + 127) // 255) << 11
                | ((raw_green * 63 + 127) // 255) << 5
                | ((raw_blue * 31 + 127) // 255)
            )
            output.extend(packed.to_bytes(2, "little"))
        elif name == "8_8_8_8":
            if sorted(selectors) != [0, 1, 2, 3]:
                raise StadiumTextureError("unsupported 8888 stadium channel swizzle")
            raw = [0, 0, 0, 0]
            for displayed, source in enumerate(selectors):
                raw[source] = rgba_pixel[displayed]
            output.extend(raw)
        else:  # pragma: no cover - routed by _GENERIC_FORMATS
            raise StadiumTextureError(f"no encoder for {name}")
    return bytes(output)


def _encode_texture(
    texture: EmbeddedTexture, original: bytes, wanted: bytes
) -> tuple[bytes, list[dict[str, Any]]]:
    if texture.format_name == "DXT1":
        layout = bc1_mips.derive_layout(texture.metadata)
        extract = bc1_mips.extract_linear_bc1
        insert = bc1_mips.insert_linear_bc1
        transport = bc1_mips.transport_roundtrip
        encode = _encode_bc1_level
        decode = bc1_transport.decode_linear_bc1
        codec = "BC1"
    elif texture.format_name == "DXT4_5":
        layout = bc3_mips.derive_layout(texture.metadata)
        extract = bc3_mips.extract_linear_bc3
        insert = bc3_mips.insert_linear_bc3
        transport = bc3_mips.transport_roundtrip
        encode = _encode_bc3_level
        decode = bc3_transport._decode_linear_bc3  # type: ignore[attr-defined]
        codec = "BC3"
    elif texture.format_name == "DXN":
        if texture.metadata.get("tiled"):
            layout = dxn_mips.derive_layout(texture.metadata)
            extract = dxn_mips.extract_linear_dxn
            insert = dxn_mips.insert_linear_dxn
            transport = dxn_mips.transport_roundtrip
        else:
            layout = _derive_linear_dxn_layout(texture.metadata)
            extract = _linear_dxn_extract
            insert = _linear_dxn_insert
            transport = _linear_dxn_roundtrip
        encode = _encode_dxn_level
        decode = dxn_codec.decode_linear_dxn
        codec = "DXN/BC5"
    elif texture.format_name in _GENERIC_FORMATS:
        format_name = texture.format_name
        endian = _GENERIC_FORMATS[format_name][4]
        layout = _derive_generic_layout(texture.metadata, format_name)
        extract = lambda body, location: _generic_extract(  # noqa: E731
            body, location, endian
        )
        insert = lambda body, location, linear: _generic_insert(  # noqa: E731
            body, location, linear, endian
        )
        transport = lambda body, locations: _generic_roundtrip(  # noqa: E731
            body, locations, endian
        )
        encode = lambda rgba, location: _encode_generic_level(  # noqa: E731
            texture, rgba, location
        )
        decode = lambda linear, location: _decode_generic_level(  # noqa: E731
            texture,
            _generic_insert(bytes(texture.payload_length), location, linear, endian),
            location,
        )
        codec = format_name
    else:
        raise StadiumTextureError(
            f"{texture.format_name} has no proved stadium writer; export remains available"
        )
    if len(original) != texture.payload_length or transport(original, layout) != original:
        raise StadiumTextureError(f"retail {codec} packed-mip transport is not bit-exact")
    output = original
    levels: list[dict[str, Any]] = []
    for location in layout:
        wanted_level = _resize_level(
            wanted,
            (texture.width, texture.height),
            (location.width, location.height),
        )
        linear = encode(wanted_level, location)
        output = insert(output, location, linear)
        decoded = decode(linear, location)
        levels.append(
            {
                "level": location.level,
                "width": location.width,
                "height": location.height,
                "packed_tail": location.packed_tail,
                "linear_sha256": _sha256(linear),
                "wanted_rgba_sha256": _sha256(wanted_level),
                "decoded_rgba_sha256": _sha256(decoded),
                "decode_back_metrics": archive_patch._rgba_metrics(  # type: ignore[attr-defined]
                    wanted_level, decoded
                ),
            }
        )
    if transport(output, layout) != output:
        raise StadiumTextureError(f"patched {codec} packed-mip transport is not bit-exact")
    return output, levels


def _rebuild_vram_entry(
    entry: apf_outer.Entry,
    record: apf_inner.IFFRecord,
    original_entry: bytes,
    original_blocks: list[bytes],
    original_stored: list[bytes],
    new_block1: bytes,
) -> tuple[bytes, list[bytes], int, dict[str, int]]:
    if len(new_block1) != len(original_blocks[1]):
        raise StadiumTextureError("stadium VRAM block length changed")
    descriptor = record.blocks[1]
    if (
        not descriptor.is_compressed
        or descriptor.wrapper is None
        or descriptor.wrapper.shift != 10
    ):
        raise StadiumTextureError("stadium VRAM H7A profile changed")
    retail_payload = original_stored[1][apf_inner.H7A_HEADER_SIZE :]
    compressed, compression = apf_inner.encode_h7a_preserving_tokens(
        retail_payload,
        original_blocks[1],
        new_block1,
        10,
    )
    if apf_inner.decompress_h7a(compressed, len(new_block1), 10) != new_block1:
        raise StadiumTextureError("stadium VRAM H7A encode/decode round-trip failed")
    new_stored = list(original_stored)
    new_stored[1] = struct.pack(
        ">5I",
        apf_inner.H7A_MAGIC,
        len(new_block1),
        apf_inner.H7A_HEADER_SIZE + len(compressed),
        descriptor.unknown_10,
        10,
    ) + compressed
    header = bytearray(original_entry[: record.header_size])
    body = bytearray()
    cursor = record.header_size
    for index, (old, stored) in enumerate(zip(record.blocks, new_stored)):
        struct.pack_into(
            ">8I",
            header,
            apf_inner.IFF_HEADER_SIZE + index * apf_inner.IFF_BLOCK_SIZE,
            old.name_hash,
            old.type_hash,
            old.unknown_08,
            old.uncompressed_length,
            old.unknown_10,
            cursor,
            len(stored),
            old.indexed,
        )
        body.extend(stored)
        cursor += len(stored)
    new_file_length = record.header_size + len(body)
    struct.pack_into(">I", header, 0x08, new_file_length)
    footer = original_entry[record.file_length : record.file_length + FOOTER_TOTAL]
    tail = original_entry[record.file_length + FOOTER_TOTAL :]
    if _sha256(footer) != FOOTER_SHA256 or any(tail):
        raise StadiumTextureError("stadium footer or fixed-allocation tail changed")
    active = bytes(header) + bytes(body) + footer
    if len(active) > entry.size:
        raise StadiumTextureError(
            "replacement cannot fit the fixed stadium package allocation; choose "
            "simpler artwork or another texture"
        )
    rebuilt = active + bytes(entry.size - len(active))
    memory = archive_patch.BytesReader(rebuilt)
    rebuilt_record = apf_inner.parse_iff(memory, entry)
    rebuilt_blocks = [
        apf_inner.decode_block(memory, rebuilt_record, index, 1 << 30)
        for index in range(rebuilt_record.block_count)
    ]
    if rebuilt_blocks != [original_blocks[0], new_block1]:
        raise StadiumTextureError("rebuilt stadium IFF did not reopen to intended blocks")
    compression = {
        **compression,
        "retail_payload_bytes": len(retail_payload),
        "output_payload_bytes": len(compressed),
        "payload_growth_bytes": len(compressed) - len(retail_payload),
    }
    return rebuilt, new_stored, new_file_length, compression


def build_patch(
    game_root: Path, png_path: Path, texture_index: int
) -> tuple[bytes, dict[str, Any], EmbeddedTexture]:
    """Build and independently reopen one outer-14 embedded texture edit."""

    (
        entry,
        record,
        original_entry,
        original_blocks,
        original_stored,
        system,
        vram,
    ) = _source(Path(game_root))
    catalog = _catalog_from_parts(system, vram)
    if not 0 <= texture_index < len(catalog.textures):
        raise StadiumTextureError("embedded texture index must be in 0..77")
    texture = catalog.textures[texture_index]
    if not texture.editable:
        raise StadiumTextureError(
            f"{texture.format_name} descriptor has no proved full-mip stadium writer"
        )
    wanted, input_size = _load_and_resize_png(Path(png_path), texture)
    original_texture = _texture_bytes(vram, texture)
    original_rgba = _decode_texture_base(texture, original_texture)
    mode = "no_op" if wanted == original_rgba else "changed"
    before_parts = _part_hashes(record, original_blocks)
    if mode == "no_op":
        rebuilt = original_entry
        rebuilt_blocks = original_blocks
        new_stored = original_stored
        new_file_length = record.file_length
        levels: list[dict[str, Any]] = []
        compression: dict[str, int] = {
            "retail_payload_bytes": len(original_stored[1])
            - apf_inner.H7A_HEADER_SIZE,
            "output_payload_bytes": len(original_stored[1])
            - apf_inner.H7A_HEADER_SIZE,
            "payload_growth_bytes": 0,
        }
    else:
        new_texture, levels = _encode_texture(texture, original_texture, wanted)
        if new_texture == original_texture:
            raise StadiumTextureError("changed PNG encoded to the original texture bytes")
        new_block1 = bytearray(original_blocks[1])
        start = texture.video_offset
        end = start + texture.payload_length
        new_block1[start:end] = new_texture
        changed_offsets = {
            index
            for index, (before, after) in enumerate(
                zip(original_blocks[1], new_block1)
            )
            if before != after
        }
        if not changed_offsets or min(changed_offsets) < start or max(changed_offsets) >= end:
            raise StadiumTextureError("stadium VRAM edit escaped its texture allocation")
        rebuilt, new_stored, new_file_length, compression = _rebuild_vram_entry(
            entry,
            record,
            original_entry,
            original_blocks,
            original_stored,
            bytes(new_block1),
        )
        memory = archive_patch.BytesReader(rebuilt)
        reopened = apf_inner.parse_iff(memory, entry)
        rebuilt_blocks = [
            apf_inner.decode_block(memory, reopened, index, 1 << 30)
            for index in range(reopened.block_count)
        ]
        record = reopened
    after_parts = _part_hashes(record, rebuilt_blocks)
    changed_parts = sorted(
        key for key in before_parts if before_parts[key] != after_parts[key]
    )
    expected_parts = [] if mode == "no_op" else [(INNER_INDEX, 1)]
    if changed_parts != expected_parts:
        raise StadiumTextureError(f"unexpected stadium inner parts changed: {changed_parts}")
    output_system = rebuilt_blocks[0][: stadium_container.SYSTEM_LENGTH]
    output_vram = rebuilt_blocks[1][: stadium_container.VRAM_LENGTH]
    if output_system != system:
        raise StadiumTextureError("stadium DRAM/material ownership bytes changed")
    catalog_after = _catalog_from_parts(output_system, output_vram)
    after_texture = catalog_after.textures[texture_index]
    if after_texture != texture:
        raise StadiumTextureError("embedded TXTR descriptor/ownership changed")
    output_payload = _texture_bytes(output_vram, after_texture)
    output_rgba = _decode_texture_base(texture, output_payload)
    footer = rebuilt[new_file_length : new_file_length + FOOTER_TOTAL]
    tail = rebuilt[new_file_length + FOOTER_TOTAL :]
    changed_vram = sum(a != b for a, b in zip(vram, output_vram))
    manifest: dict[str, Any] = {
        "schema": SCHEMA,
        "mode": mode,
        "source": {
            "outer_index": OUTER_INDEX,
            "inner_index": INNER_INDEX,
            "outer_sha256": OUTER_SHA256,
            "system_sha256": SYSTEM_SHA256,
            "vram_sha256": VRAM_SHA256,
        },
        "ownership": {
            "texture_count": len(catalog.textures),
            "material_count": len(catalog.materials),
            "shader_family_count": catalog.shader_family_count,
            "surface_count": len(catalog.surfaces),
            "draw_to_material_to_embedded_txtr_static_join": True,
            "selected_material_slots": list(texture.material_slots),
        },
        "target": {
            "selector": texture.selector,
            "texture_index": texture.index,
            "texture_id": f"0x{texture.texture_id:08x}",
            "format": texture.format_name,
            "width": texture.width,
            "height": texture.height,
            "video_offset": texture.video_offset,
            "payload_length": texture.payload_length,
            "input_size": list(input_size),
            "input_auto_resized": input_size != (texture.width, texture.height),
        },
        "texture": {
            "sha256_before": _sha256(original_texture),
            "sha256_after": _sha256(output_payload),
            "decoded_rgba_sha256_before": _sha256(original_rgba),
            "decoded_rgba_sha256_after": _sha256(output_rgba),
            "wanted_rgba_sha256": _sha256(wanted),
            "base_decode_back_metrics": archive_patch._rgba_metrics(  # type: ignore[attr-defined]
                wanted, output_rgba
            ),
            "levels": levels,
        },
        "iff": {
            "fixed_outer_allocation": len(rebuilt) == OUTER_LENGTH,
            "file_length_before": SOURCE_FILE_LENGTH,
            "file_length_after": new_file_length,
            "allocation_slack_after": len(tail),
            "block0_stored_exact": new_stored[0] == original_stored[0],
            "block1_h7a_shift": 10,
            "block1_h7a_roundtrip_exact": True,
            "block1_h7a_preservation": compression,
            "footer_sha256": _sha256(footer),
            "footer_exact": _sha256(footer) == FOOTER_SHA256,
            "tail_zero": not any(tail),
        },
        "verification": {
            "rebuilt_iff_reopened": True,
            "dram_material_graph_exact": True,
            "changed_inner_parts": [
                {"file_index": item, "part_index": part}
                for item, part in changed_parts
            ],
            "changed_vram_byte_count": changed_vram,
            "edit_within_selected_texture_allocation": True,
            "source_opened_read_only": True,
        },
        "backend": {
            "png": f"Pillow {PILLOW_VERSION}; RGBA + Lanczos resize/mips",
            "codec": (
                "project-native deterministic full-mip encoder for "
                f"{texture.format_name}"
            ),
            "xenos_layout": "packed full-mip transport",
            "h7a": "project-native retail-token-preserving bounded encoder",
        },
        "claims": {
            "offline_texture_ownership_proved": True,
            "full_declared_mip_chain_regenerated": mode == "changed",
            "runtime_visibility_proved": False,
            "xbox_360_hardware_proved": False,
        },
        "contains_replacement_bytes": False,
    }
    return rebuilt, manifest, texture


def write_output(
    game_root: Path,
    png_path: Path,
    texture_index: int,
    output_directory: Path,
) -> StadiumTextureReceipt:
    """Create a new directory holding only the copied/patched 1A and receipt."""

    game_root = Path(game_root).resolve(strict=True)
    png_path = Path(png_path).resolve(strict=True)
    output_directory = Path(output_directory)
    if os.path.lexists(output_directory):
        raise StadiumTextureError("stadium texture output directory must be new")
    if not output_directory.parent.is_dir() or output_directory.parent.is_symlink():
        raise StadiumTextureError("stadium texture output parent must be a real directory")
    try:
        output_directory.resolve(strict=False).relative_to(game_root)
    except ValueError:
        pass
    else:
        raise StadiumTextureError("stadium texture output must not be inside the source game")
    rebuilt, manifest, texture = build_patch(game_root, png_path, texture_index)
    os.mkdir(output_directory, 0o755)
    output_pack = output_directory / OUTPUT_PACK_NAME
    manifest_path = output_directory / MANIFEST_NAME
    try:
        _archive, entry = stadium_container._validate_archive(game_root)  # type: ignore[attr-defined]
        copied = archive_patch._write_copied_volume(  # type: ignore[attr-defined]
            game_root / OUTPUT_PACK_NAME,
            output_pack,
            entry,
            rebuilt,
        )
        manifest["copied_volume"] = copied
        archive_patch._write_new(  # type: ignore[attr-defined]
            manifest_path,
            (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
        if sorted(path.name for path in output_directory.iterdir()) != sorted(
            (OUTPUT_PACK_NAME, MANIFEST_NAME)
        ):
            raise StadiumTextureError("stadium texture output contains an unexpected file")
        return StadiumTextureReceipt(
            output_directory=output_directory,
            output_pack=output_pack,
            manifest_path=manifest_path,
            texture=texture,
            mode=str(manifest["mode"]),
            changed_vram_bytes=int(
                manifest["verification"]["changed_vram_byte_count"]
            ),
            manifest=manifest,
        )
    except Exception:
        if output_directory.is_dir() and not output_directory.is_symlink():
            shutil.rmtree(output_directory)
        raise


def main(argv: list[str] | None = None) -> int:
    """Run the same bounded copied-1A writer exposed by Stadium Studio."""

    parser = argparse.ArgumentParser(
        description="Replace one proved APF stadium embedded texture in a copied 1A."
    )
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--texture-index", type=int, required=True, choices=range(78))
    parser.add_argument("--png", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    receipt = write_output(
        args.game_dir, args.png, args.texture_index, args.output_dir
    )
    print(
        json.dumps(
            {
                "schema": SCHEMA,
                "mode": receipt.mode,
                "selector": receipt.texture.selector,
                "output_pack": str(receipt.output_pack),
                "manifest": str(receipt.manifest_path),
                "changed_vram_bytes": receipt.changed_vram_bytes,
            },
            sort_keys=True,
        )
    )
    return 0


__all__ = [
    "EDITABLE_FORMATS",
    "EmbeddedTexture",
    "MaterialBinding",
    "StadiumTextureCatalog",
    "StadiumTextureError",
    "StadiumTextureReceipt",
    "SurfaceBinding",
    "build_patch",
    "decoded_rgba",
    "export_png",
    "load_catalog",
    "stage_replacement_png",
    "write_output",
]


if __name__ == "__main__":
    raise SystemExit(main())

"""Read-only discovery of the TXTR descriptors stored inside an APF SCNE part.

The catalog indexes inner files, so every browser, preview, and export in the
product keys on an ``(outer, inner)`` pair.  APF's field scorebug art is not
stored that way: the seven ``scorebug_*`` SCNE records in ``global.iff`` carry
their own descriptor tables, and the pixels sit in each scene's VRAM part.  A
texture with no inner index could never become an :class:`ApfAsset`, which is
why the Scorebug workspace could describe the presentation inventory in prose
while showing none of its artwork.

``stadium_texture`` already walks this exact grammar -- count at ``+0x20``, a
self-relative pointer to ``0xE0``-byte descriptors at ``+0x24``, VRAM address
at ``+0x6C`` -- but it is deliberately pinned to the one authenticated stadium
package because it also *writes*.  This module is the read half only, lifted so
any scene can be looked at.  It decodes; it never stages, never patches, and
never claims a writer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import struct
from typing import Any, Iterable, Mapping, Sequence

from .backend import ensure_tools_importable
from .models import ApfAsset, ApfSource


ensure_tools_importable()
import apf_helmet_color_transport  # type: ignore  # noqa: E402
import apf_inner  # type: ignore  # noqa: E402
import apf_outer  # type: ignore  # noqa: E402
import apf_xenos_dxn_mip_layout  # type: ignore  # noqa: E402
import apf_xenos_dxt5a  # type: ignore  # noqa: E402


#: Descriptor-table grammar, shared with :mod:`.stadium_texture`.
TEXTURE_COUNT_FIELD = 0x20
TEXTURE_TABLE_FIELD = 0x24
TEXTURE_RECORD_SIZE = 0xE0
VRAM_ADDRESS_FIELD = 0x6C

SCENE_TYPE_NAME = "SCNE"

#: Nothing here is authored, so the only cap that matters is refusing to walk a
#: corrupt table into a multi-second loop.
MAX_SCENE_TEXTURES = 512


class SceneTextureError(ValueError):
    """A SCNE embedded-texture table failed its own structural grammar."""


@dataclass(frozen=True, slots=True)
class SceneTexture:
    """One TXTR descriptor embedded in a SCNE system part.

    ``key`` is a stable selector for a resource the catalog cannot address, so
    the GUI can remember a selection across a refresh without inventing a fake
    asset id.
    """

    outer_index: int
    inner_index: int
    scene_name: str
    index: int
    texture_id: int
    width: int
    height: int
    format_name: str
    video_offset: int
    payload_length: int
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return (
            f"apf:scene:{self.outer_index}:{self.inner_index}"
            f":texture:{self.index:03d}"
        )

    @property
    def location(self) -> str:
        return (
            f"outer {self.outer_index} / inner {self.inner_index} "
            f"/ embedded {self.index:02d}"
        )

    @property
    def dimensions(self) -> str:
        return f"{self.width}×{self.height}"

    @property
    def title(self) -> str:
        return f"{self.scene_name} · embedded {self.index:02d}"

    @property
    def vram_span(self) -> str:
        end = self.video_offset + self.payload_length
        return f"VRAM 0x{self.video_offset:05x}–0x{end:05x} ({self.payload_length:,} B)"


def _u32(data: bytes, offset: int, label: str) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise SceneTextureError(f"{label}: read leaves the SCNE system part")
    return struct.unpack_from(">I", data, offset)[0]


def descriptor_table_offset(system: bytes) -> int | None:
    """Byte offset of the embedded TXTR table, or ``None`` when there is none.

    A scene with no embedded art still stores a pointer, so the count is the
    field that decides whether the table exists at all.
    """

    if len(system) < TEXTURE_TABLE_FIELD + 4:
        return None
    if _u32(system, TEXTURE_COUNT_FIELD, "embedded texture count") == 0:
        return None
    raw = _u32(system, TEXTURE_TABLE_FIELD, "embedded texture table")
    if raw == 0:
        return None
    target = TEXTURE_TABLE_FIELD + raw - 1
    if not 0 <= target < len(system):
        raise SceneTextureError("embedded texture table leaves the SCNE system part")
    return target


def scene_textures(
    system: bytes,
    vram: bytes,
    *,
    outer_index: int,
    inner_index: int,
    scene_name: str,
) -> tuple[SceneTexture, ...]:
    """Every embedded TXTR descriptor this scene declares, in table order."""

    start = descriptor_table_offset(system)
    if start is None:
        return ()
    count = _u32(system, TEXTURE_COUNT_FIELD, "embedded texture count")
    if count > MAX_SCENE_TEXTURES:
        raise SceneTextureError(
            f"{scene_name}: embedded texture count {count} is out of range"
        )
    values: list[SceneTexture] = []
    for index in range(count):
        offset = start + index * TEXTURE_RECORD_SIZE
        raw = system[offset : offset + TEXTURE_RECORD_SIZE]
        if len(raw) != TEXTURE_RECORD_SIZE:
            raise SceneTextureError(
                f"{scene_name}: embedded TXTR descriptor table is truncated"
            )
        metadata = apf_inner.parse_txtr_metadata(raw)
        address = _u32(raw, VRAM_ADDRESS_FIELD, "embedded texture VRAM address")
        video_offset = address & ~0xFFF
        length = int(metadata["vc_base_data_length"]) + int(
            metadata["vc_mip_data_length"]
        )
        if length <= 0 or video_offset + length > len(vram):
            raise SceneTextureError(
                f"{scene_name}: embedded texture {index} leaves the scene VRAM part"
            )
        values.append(
            SceneTexture(
                outer_index=outer_index,
                inner_index=inner_index,
                scene_name=scene_name,
                index=index,
                texture_id=_u32(raw, 0, "embedded texture id"),
                width=int(metadata["width"]),
                height=int(metadata["height"]),
                format_name=str(metadata["format_name"]),
                video_offset=video_offset,
                payload_length=length,
                metadata=metadata,
            )
        )
    return tuple(values)


def texture_payload(texture: SceneTexture, vram: bytes) -> bytes:
    end = texture.video_offset + texture.payload_length
    if end > len(vram):
        raise SceneTextureError(
            f"{texture.title}: payload leaves the scene VRAM part"
        )
    return vram[texture.video_offset : end]


def decode_texture_rgba(
    texture: SceneTexture,
    payload: bytes,
    *,
    for_display: bool = False,
) -> tuple[int, int, bytes]:
    """Base-level RGBA for one embedded descriptor.

    Format routing mirrors :meth:`ApfAssetIO._decode_texture_rgba` so an
    embedded descriptor and an inner-file TXTR of the same format decode
    identically; a format neither one supports raises rather than guessing.
    """

    metadata = dict(texture.metadata)
    base_length = int(metadata["vc_base_data_length"])
    base = payload[:base_length]
    format_value = int(metadata.get("format", -1))
    if format_value == 49:  # DXN
        locations = apf_xenos_dxn_mip_layout.derive_layout(metadata)
        linear = apf_xenos_dxn_mip_layout.extract_linear_dxn(base, locations[0])
        rgba = apf_helmet_color_transport.decode_linear_dxn(linear, locations[0])
        width, height = locations[0].width, locations[0].height
    elif format_value == 59:  # DXT5A, alpha-only
        width = texture.width
        height = texture.height
        pitch = int(metadata.get("pitch_pixels", width))
        endian = int(metadata.get("endianness", 1))
        if not metadata.get("tiled", True):
            raise SceneTextureError(
                "PORTME: linear DXT5A base-level routing is unverified"
            )
        linear = apf_xenos_dxt5a.extract_linear_general(
            base, width, height, pitch, endian_mode=endian
        )
        alpha = apf_xenos_dxt5a.decode_linear_alpha_general(linear, width, height)
        rgba = apf_xenos_dxt5a.alpha_to_rgba_general(alpha, width, height)
    else:
        width, height, rgba = apf_inner.decode_txtr_base_rgba(metadata, base)
    if for_display:
        rgba, _ = apf_inner.force_opaque_alpha_for_display(rgba)
    return width, height, rgba


def _scene_parts(
    reader: Any, record: Any, blocks: dict[int, bytes], item: Any
) -> tuple[bytes, bytes]:
    parts: list[bytes] = []
    for part in item.parts:
        if part.block_index not in blocks:
            blocks[part.block_index] = apf_inner.decode_block(
                reader, record, part.block_index, 512 * 1024 * 1024
            )
        block = blocks[part.block_index]
        end = part.offset + part.length
        if part.offset < 0 or end > len(block):
            raise SceneTextureError(f"{item.name}: SCNE part exceeds its block")
        parts.append(block[part.offset : end])
    if not parts:
        raise SceneTextureError(f"{item.name}: SCNE record has no stored parts")
    return parts[0], (parts[1] if len(parts) > 1 else b"")


def read_scene_textures(
    source: ApfSource, assets: Sequence[ApfAsset]
) -> tuple[SceneTexture, ...]:
    """Walk several SCNE rows from one archive open.

    A scene whose table cannot be trusted is skipped rather than taking the
    whole listing down: the remaining components are still real, and the page
    reports the count it actually found.
    """

    wanted = [
        asset
        for asset in assets
        if asset.type_name == SCENE_TYPE_NAME and asset.inner_index is not None
    ]
    if not wanted:
        return ()
    by_outer: dict[int, list[ApfAsset]] = {}
    for asset in wanted:
        by_outer.setdefault(asset.outer_index, []).append(asset)

    archive = apf_outer.parse_archive(source.index_0a)
    values: list[SceneTexture] = []
    for outer_index, group in sorted(by_outer.items()):
        try:
            entry = archive.entries[outer_index]
        except IndexError as exc:
            raise SceneTextureError(f"No APF outer entry {outer_index}") from exc
        with apf_inner.ArchiveReader(archive) as reader:
            record = apf_inner.parse_iff(reader, entry)
            blocks: dict[int, bytes] = {}
            for asset in sorted(group, key=lambda item: item.inner_index or 0):
                assert asset.inner_index is not None
                try:
                    item = record.files[asset.inner_index]
                except IndexError as exc:
                    raise SceneTextureError(
                        f"Outer {outer_index} has no inner {asset.inner_index}"
                    ) from exc
                if item.type_name != SCENE_TYPE_NAME:
                    continue
                system, vram = _scene_parts(reader, record, blocks, item)
                try:
                    values.extend(
                        scene_textures(
                            system,
                            vram,
                            outer_index=outer_index,
                            inner_index=asset.inner_index,
                            scene_name=item.name,
                        )
                    )
                except (SceneTextureError, apf_inner.FormatError, ValueError):
                    continue
    return tuple(values)


def read_texture_payload(source: ApfSource, texture: SceneTexture) -> bytes:
    """Re-read one descriptor's exact VRAM bytes from the user's own game."""

    archive = apf_outer.parse_archive(source.index_0a)
    try:
        entry = archive.entries[texture.outer_index]
    except IndexError as exc:
        raise SceneTextureError(
            f"No APF outer entry {texture.outer_index}"
        ) from exc
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        try:
            item = record.files[texture.inner_index]
        except IndexError as exc:
            raise SceneTextureError(
                f"Outer {texture.outer_index} has no inner {texture.inner_index}"
            ) from exc
        if item.name != texture.scene_name or item.type_name != SCENE_TYPE_NAME:
            raise SceneTextureError("The selected scene record identity changed")
        system, vram = _scene_parts(reader, record, {}, item)
    current = scene_textures(
        system,
        vram,
        outer_index=texture.outer_index,
        inner_index=texture.inner_index,
        scene_name=texture.scene_name,
    )
    if texture.index >= len(current) or current[texture.index].texture_id != texture.texture_id:
        raise SceneTextureError("The selected embedded texture identity changed")
    return texture_payload(current[texture.index], vram)


def shared_texture_ids(textures: Iterable[SceneTexture]) -> frozenset[int]:
    """Texture ids that more than one descriptor in the listing points at.

    ``scorebug_infobar`` and ``scorebug_statbar`` both declare id
    ``0x5146477a``.  Presenting them as two independent slots would imply two
    independent edits, which is exactly the kind of overstatement this product
    must not make.
    """

    seen: set[int] = set()
    shared: set[int] = set()
    for texture in textures:
        if texture.texture_id in seen:
            shared.add(texture.texture_id)
        seen.add(texture.texture_id)
    return frozenset(shared)


__all__ = [
    "MAX_SCENE_TEXTURES",
    "SCENE_TYPE_NAME",
    "SceneTexture",
    "SceneTextureError",
    "TEXTURE_RECORD_SIZE",
    "decode_texture_rgba",
    "descriptor_table_offset",
    "read_scene_textures",
    "read_texture_payload",
    "scene_textures",
    "shared_texture_ids",
    "texture_payload",
]

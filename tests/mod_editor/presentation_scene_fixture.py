"""Synthetic presentation scene resources (beta 76 p2): raw MRKS and VC-LZ SCNE spans that the strict SCNE
parser and the stadium allocation contract accept, with embedded P8 textures of chosen sizes and mip counts.

No game data is involved: names, pixels and palettes are generated here. A scene has one descriptor per
texture and one material per descriptor (material names may repeat a texture, as the retail wipes do).
"""
from __future__ import annotations

from pathlib import Path
import random
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
for _extra in (ROOT, ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import nfl_txtr as txtr  # noqa: E402

TEXTURE_STRIDE = 0x20
MATERIAL_STRIDE = 0x80
DESCRIPTOR_SIZE = 0x54


def packed_format(width: int, height: int, mips: int) -> int:
    """X_D3DFORMAT word of a swizzled P8 2D texture (dimensions 2, format 0x0B, depth 1)."""

    return (0x09 | (2 << 4) | (0x0B << 8) | (mips << 16) | ((width.bit_length() - 1) << 20)
            | ((height.bit_length() - 1) << 24))


def chain_bytes(width: int, height: int, mips: int) -> int:
    return sum(max(1, width >> level) * max(1, height >> level) for level in range(mips))


def _utf16(text: str) -> bytes:
    return text.encode("utf-16le") + b"\0\0"


def _rel(field: int, target: int) -> int:
    """The SCNE self-relative pointer stored at ``field`` that resolves to ``target``."""

    return target - field + 1


def scene_decoded(kind: str, textures: list[tuple[int, int, int, list[str]]], *, name: str = "p2_scene",
                  seed: int = 7, palette_gap: int = 0) -> tuple[bytes, int]:
    """(decoded system + video bytes, system size) of one synthetic scene.

    ``textures`` holds (width, height, mip levels, material names) per descriptor. ``palette_gap`` puts that
    many bytes between a chain and its palette (a layout the stadium contract refuses)."""

    rng = random.Random(seed)
    names = [name] + [material for _w, _h, _m, materials in textures for material in materials]
    descriptor = 0x100 if kind == "MRKS" else 0x40
    textures_at = descriptor + DESCRIPTOR_SIZE + 0x0C
    materials = [(material, index) for index, (_w, _h, _m, mats) in enumerate(textures) for material in mats]
    materials_at = textures_at + TEXTURE_STRIDE * len(textures)
    names_at = materials_at + MATERIAL_STRIDE * len(materials)
    name_offsets, cursor, blob = {}, names_at, bytearray()
    for text in names:
        if text not in name_offsets:
            name_offsets[text] = cursor
            encoded = _utf16(text)
            blob += encoded
            cursor += len(encoded)
    system_bytes = (cursor + 0x7F) & ~0x7F
    system = bytearray(system_bytes)
    system[0x0C:0x10] = kind.encode("ascii")
    struct.pack_into("<i", system, 0x10, _rel(0x10, name_offsets[name]))
    if kind == "MRKS":
        struct.pack_into("<i", system, 0x14, _rel(0x14, 0x20))                 # 13: the wrapper descriptor
        struct.pack_into("<i", system, 0x20, _rel(0x20, descriptor))
    else:
        struct.pack_into("<i", system, 0x14, _rel(0x14, descriptor))
    struct.pack_into("<i", system, descriptor, _rel(descriptor, name_offsets[name]))
    struct.pack_into("<I", system, descriptor + 0x14, len(textures))
    struct.pack_into("<i", system, descriptor + 0x18, _rel(descriptor + 0x18, textures_at))
    struct.pack_into("<I", system, descriptor + 0x1C, len(materials))
    struct.pack_into("<i", system, descriptor + 0x20, _rel(descriptor + 0x20, materials_at))
    video = bytearray()
    for index, (width, height, mips, _materials) in enumerate(textures):
        chain = chain_bytes(width, height, mips)
        pixel = len(video)
        palette_at = pixel + chain + palette_gap
        video += bytes(rng.randrange(0, 24) for _ in range(chain)) + bytes(palette_gap)
        video += b"".join(bytes((rng.randrange(256), rng.randrange(256), rng.randrange(256), 255)) for _ in range(24))
        video += bytes(1024 - 24 * 4)
        struct.pack_into("<6I", system, textures_at + index * TEXTURE_STRIDE, 0, pixel, palette_at,
                         packed_format(width, height, mips), 0, 0x80000000)
    for index, (material, texture) in enumerate(materials):
        at = materials_at + index * MATERIAL_STRIDE
        struct.pack_into("<i", system, at, _rel(at, name_offsets[material]))
        struct.pack_into("<I", system, at + 0x08, 0x80000000)
        struct.pack_into("<I", system, at + 0x18, 0xFFFFFFFF)
        field = at + 0x30
        struct.pack_into("<i", system, field, _rel(field, textures_at + texture * TEXTURE_STRIDE))
    system[names_at:names_at + len(blob)] = blob
    return bytes(system) + bytes(video), system_bytes


def raw_span(decoded: bytes, system_bytes: int, kind: str = "MRKS") -> bytes:
    """An uncompressed resource span: wrapper (compression word 0, scratch 0) and the decoded bytes."""

    return txtr.HEADER.pack(kind.encode("ascii"), len(decoded), system_bytes, len(decoded) - system_bytes,
                            0, 0, 0, 0) + decoded


def compressed_span(decoded: bytes, system_bytes: int, *, tail: bytes = b"\x5a" * 9, margin: int = 256,
                    tag: int = 1, bits: int = 12) -> bytes:
    """A VC-LZ SCNE span shaped like the retail scenes: stream, opaque tail, and a scratch word that covers the
    stream's own in-place decode plus ``margin``."""

    stream, _info = txtr.compress_vc_lz(decoded, stream_tag=tag, offset_bits=bits, verify_roundtrip=True)
    stored = len(stream) + len(tail)
    minimum = txtr.minimum_vc_lz_overlap_scratch(stream, stored, len(decoded))
    scratch = ((max(minimum, stored - len(stream)) + margin + 15) // 16) * 16
    return txtr.HEADER.pack(b"SCNE", stored, system_bytes, len(decoded) - system_bytes,
                            txtr.COMPRESSED_SENTINEL, scratch, 0, 0) + stream + tail


def filler_chunk(index: int) -> bytes:
    """A small uncompressed chunk that keeps chunk numbering (not a scene)."""

    return txtr.HEADER.pack(b"Unif", 32, 0, 0, 0, 0, 0, 0) + bytes((index % 251,)) * 32


def outer_with(chunks: dict[int, bytes], count: int) -> tuple[bytes, dict[int, int]]:
    """An outer body of ``count`` chunks: the given spans at their indices, fillers elsewhere."""

    body, offsets = bytearray(), {}
    for index in range(count):
        if index in chunks:
            offsets[index] = len(body)
            body += chunks[index]
        else:
            body += filler_chunk(index)
    return bytes(body), offsets

"""Bounded APFe DDS/GTF base-level decoding; no game writes.

GTF fields are big endian: version/size/count at 0/4/8, texture id/data
offset/data size at 12/16/20, then a 24-byte CellGcmTexture at 24. Its
format/mipmap/dimension/cubemap bytes precede remap (u32), width/height/depth
(u16), location/pad, pitch/offset (u32). Actual APFe exports start pixels at
0x30, NOT a fixed 0x80. We honor the declared offset (including padded 0x80).
Only non-cube 2D textures and the explicitly implemented formats are accepted.
"""
from __future__ import annotations

from functools import lru_cache
import io
import struct

from PIL import Image

MAX_PIXELS = 4096 * 4096
MAX_TEXTURE_BYTES = 128 * 1024 * 1024


class TextureDecodeError(ValueError):
    pass


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise TextureDecodeError(message)


def _size(width: int, height: int) -> None:
    _require(0 < width <= 8192 and 0 < height <= 8192 and width * height <= MAX_PIXELS,
             f"Texture dimensions exceed bounds: {width}x{height}")


@lru_cache(maxsize=8)
def _lut16(masks: tuple[int, ...]) -> tuple[bytes, ...]:
    shifts = [(m & -m).bit_length() - 1 if m else 0 for m in masks]
    return tuple(bytes(((v & m) >> s) * 255 // (m >> s) if m else 255
                       for m, s in zip(masks, shifts)) for v in range(65536))


def _raw16(data: bytes, width: int, height: int, masks: tuple[int, ...], endian: str) -> Image.Image:
    _require(len(data) >= width * height * 2, "Truncated 16-bit texture")
    lut = _lut16(masks)
    pixels = b"".join(lut[v[0]] for v in struct.iter_unpack(endian + "H", data[:width * height * 2]))
    return Image.frombytes("RGBA", (width, height), pixels)


def _bc(data: bytes, width: int, height: int, kind: str) -> Image.Image:
    size = ((width + 3) // 4) * ((height + 3) // 4) * (8 if kind == "DXT1" else 16)
    _require(len(data) >= size, f"Truncated {kind} texture")
    # Reconstruct the small standard DDS header; Pillow's native BCn decoder
    # handles partial edge blocks and BC1 transparent selectors.
    header = bytearray(128)
    header[:4] = b"DDS "
    struct.pack_into("<7I", header, 4, 124, 0x81007, height, width, size, 0, 1)
    struct.pack_into("<II4s", header, 76, 32, 4, kind.encode("ascii"))
    struct.pack_into("<I", header, 108, 0x1000)
    with Image.open(io.BytesIO(bytes(header) + data[:size])) as image:
        return image.convert("RGBA")


def decode_dds(data: bytes) -> Image.Image:
    _require(128 <= len(data) <= MAX_TEXTURE_BYTES and data[:4] == b"DDS ", "Invalid DDS header/size")
    _require(struct.unpack_from("<I", data, 4)[0] == 124 and struct.unpack_from("<I", data, 76)[0] == 32,
             "Invalid DDS header lengths")
    height, width, pitch, depth = struct.unpack_from("<4I", data, 12)
    _size(width, height)
    _require(depth in (0, 1) and struct.unpack_from("<I", data, 112)[0] == 0, "DDS arrays/cubes/volumes are unsupported")
    flags = struct.unpack_from("<I", data, 80)[0]
    fourcc = data[84:88]
    if flags & 4 and fourcc == b"DX10":
        _require(len(data) >= 148, "Truncated DDS DX10 header")
        _dxgi, dimension, misc, arrays, _alpha = struct.unpack_from("<5I", data, 128)
        _require(dimension == 3 and arrays == 1 and not misc & 4, "DDS DX10 arrays/cubes/volumes are unsupported")
    if flags & 4 and fourcc in (b"DXT1", b"DXT3", b"DXT5"):
        return _bc(data[128:], width, height, fourcc.decode("ascii"))
    bits, *masks = struct.unpack_from("<5I", data, 88)
    if flags & 0x40 and not flags & 4 and bits in (16, 24, 32):
        row_bytes = width * (bits // 8)
        stride = pitch if struct.unpack_from("<I", data, 8)[0] & 8 else row_bytes
        _require(row_bytes <= stride <= row_bytes + 65536, "Invalid DDS pitch")
        _require(len(data) >= 128 + stride * height, "Truncated DDS pixels")
        raw = b"".join(data[128 + y * stride:128 + y * stride + row_bytes] for y in range(height))
        if bits == 16:
            allowed = {(0xF00, 0xF0, 0xF, 0xF000), (0xF800, 0x7E0, 0x1F, 0),
                       (0x7C00, 0x3E0, 0x1F, 0x8000)}
            _require(tuple(masks) in allowed, "Unsupported DDS 16-bit channel masks")
            return _raw16(raw, width, height, tuple(masks), "<")
        if tuple(masks[:3]) in ((0xFF0000, 0xFF00, 0xFF), (0xFF, 0xFF00, 0xFF0000)):
            _require(masks[3] in (0, 0xFF000000), "Unsupported DDS alpha mask")
            order = "BGR" if masks[0] == 0xFF0000 else "RGB"
            mode = "RGBA" if bits == 32 and masks[3] else "RGB"
            raw_mode = order + ("A" if masks[3] else "X") if bits == 32 else order
            return Image.frombytes(mode, (width, height), raw, "raw", raw_mode).convert("RGBA")
    try:
        with Image.open(io.BytesIO(data)) as image:
            return image.convert("RGBA")
    except (OSError, ValueError, NotImplementedError, ZeroDivisionError) as exc:
        raise TextureDecodeError(f"Unsupported DDS: {exc}") from exc


def parse_gcm_descriptor(data: bytes) -> dict[str, int]:
    _require(len(data) >= 24, "Truncated CellGcmTexture descriptor")
    fmt, mips, dimension, cube, remap, width, height, depth, location, pad, pitch, offset = struct.unpack_from(
        ">4BI3H2B2I", data)
    _size(width, height)
    _require(dimension == 2 and cube == 0 and depth == 1, "Only non-cube 2D GTF textures are supported")
    _require(1 <= mips <= 16 and location in (0, 1) and pad == 0, "Invalid GCM texture descriptor")
    return dict(format=fmt, mips=mips, remap=remap, width=width, height=height, pitch=pitch, offset=offset)


def _unswizzle(data: bytes, width: int, height: int, unit: int) -> bytes:
    _require(width & (width - 1) == 0 and height & (height - 1) == 0,
             "Swizzled raw GTF requires power-of-two dimensions")
    def spread(value: int, own: int, other: int, first: int) -> int:
        result = 0
        for bit in range(own):
            position = 2 * bit + first if bit < other else bit + other
            result |= ((value >> bit) & 1) << position
        return result
    xb, yb = width.bit_length() - 1, height.bit_length() - 1
    xs = [spread(x, xb, yb, 0) for x in range(width)]
    ys = [spread(y, yb, xb, 1) for y in range(height)]
    _require(len(data) >= width * height * unit, "Truncated swizzled GTF")
    return b"".join(data[(x | y) * unit:(x | y) * unit + unit] for y in ys for x in xs)


def decode_gcm(data: bytes, descriptor: dict[str, int]) -> Image.Image:
    d = descriptor
    width, height, fmt = d["width"], d["height"], d["format"] & ~0x60
    _size(width, height)
    # 0x20 selects linear layout; 0x40 is unnormalized coordinates.
    # Block-compressed RSX textures use raster block order in both cases.
    if fmt in (0x86, 0x87, 0x88):
        image = _bc(data, width, height, {0x86: "DXT1", 0x87: "DXT3", 0x88: "DXT5"}[fmt])
    else:
        unit = {0x81: 1, 0x82: 2, 0x83: 2, 0x84: 2, 0x85: 4}.get(fmt)
        _require(unit is not None, f"Unsupported RSX texture format 0x{fmt:02x}")
        if d["format"] & 0x20:
            pitch = d["pitch"] or width * unit
            _require(pitch >= width * unit and len(data) >= pitch * height, "Invalid linear GTF pitch/data")
            raw = b"".join(data[y * pitch:y * pitch + width * unit] for y in range(height))
        else:
            raw = _unswizzle(data, width, height, unit)
        if fmt == 0x85:
            image = Image.frombytes("RGBA", (width, height), raw, "raw", "ARGB")
        elif fmt == 0x81:
            image = Image.frombytes("L", (width, height), raw).convert("RGBA")
        else:
            masks = {0x82: (0x7C00, 0x3E0, 0x1F, 0x8000), 0x83: (0xF00, 0xF0, 0xF, 0xF000),
                     0x84: (0xF800, 0x7E0, 0x1F, 0)}[fmt]
            image = _raw16(raw, width, height, masks, ">")
    # GCM remap packs ARGB selectors at bits 0..7 and per-channel mode at
    # bits 8..15 (0=zero, 1=one, 2=remap).  0xAAE4 is identity.
    channels = image.split()
    argb = (channels[3], channels[0], channels[1], channels[2])
    mapped = []
    for channel in range(4):
        mode = (d["remap"] >> (8 + 2 * channel)) & 3
        _require(mode != 3, "Unsupported GCM remap mode")
        mapped.append(argb[(d["remap"] >> (2 * channel)) & 3] if mode == 2
                      else Image.new("L", image.size, 255 if mode == 1 else 0))
    return Image.merge("RGBA", (mapped[1], mapped[2], mapped[3], mapped[0]))


def decode_gtf(data: bytes) -> Image.Image:
    _require(48 <= len(data) <= MAX_TEXTURE_BYTES, "Invalid GTF size")
    version, size, count, texture_id, offset, length = struct.unpack_from(">6I", data)
    _require(version == 0x01080000 and count == 1, "Only single-texture APFe GTF version 0x01080000 is supported")
    _require(size in (len(data), len(data) - offset) and offset >= 48 and 0 < length <= len(data) - offset,
             "Invalid GTF data allocation")
    return decode_gcm(data[offset:offset + length], parse_gcm_descriptor(data[24:48]))

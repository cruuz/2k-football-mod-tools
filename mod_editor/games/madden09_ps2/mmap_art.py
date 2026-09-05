"""``MMAP`` — EA Tiburon's PlayStation 2 texture wrapper, decoded to pixels.

``MMAP`` is not a texture; it is a **small table-of-tables that describes
several**.  One member carries an *image* table (the logical textures), a
*surface* table (each image's mip levels, one row per level), a *palette*
table and an optional name table, and every one of those tables is addressed
by an offset in the 40-byte header.  Reading it as "a header then a bitmap"
is what makes the format look undecodable.

**Retail-free.**  This file carries the format's constants and nothing else:
no pixel, no palette entry and no texture name from any game.

---

## The header, byte by byte [M]

```
+0x00  "MMAP"
+0x04  u32   version          2 in most members, 1 in some UI containers
+0x08  bytes 00 01 02 03      a marker, in every member measured
+0x0C  u16   imageCount
+0x0E  u16   surfaceCount
+0x10  u32   paletteCount
+0x14  u32   imageTableOffset
+0x18  u32   surfaceTableOffset      40 whenever surfaceCount > 0
+0x1C  u32   paletteTableOffset
+0x20  u32   nameTableOffset         0 when there is no name table
+0x24  u32   extraTableOffset        0 when there is none
```

The surface table therefore begins at **+0x28**, immediately after the
header — which is why an earlier reading of these bytes recorded "a `u32`
header size of 40 at +0x18" and "`u16` width, `u16` height at +0x28".  Both
observations were right about the bytes and wrong about what they are: +0x18
is the surface table's *offset*, and the width and height at +0x28 are the
*first surface row's* first four bytes.  Likewise the "three ascending `u32`
sizes" at +0x1C/+0x20/+0x24 are the palette, name and attachment tables'
offsets, and the "`u32` payload size" at +0x14 is the image table's.
`ea_terf.parse_mmap_header` reads that partial view and is not contradicted by
this file; this one reads the tables.

**Only the surface table is at the front.**  The image, palette and name
tables sit at the *end* of a member, after the pixels: in `UNIFORMS.DAT`'s
first member the surface table is at byte 40 and the palette table at byte
331,728 of 356,820 [M].  So a member cannot be catalogued from a prefix; a
caller pays for the whole decode.

## The tables [M]

```
surface, 16 bytes:  u16 width, u16 height, u32 format, u32 byteSize, u32 offset
image,   12 bytes:  u16 paletteCount, u16 mipCount, u32 firstSurface, u32 firstPalette
palette, 12 bytes:  u16 kind, u16 format, u32 byteSize, u32 offset
name,    16 bytes:  NUL-terminated ASCII
```

A surface's `format` word is **two halves**: the low 16 bits are the pixel
layout and the high 16 bits are the codec its pixel run is stored under, using
EA's own codec ids — so a texture can be compressed *inside* a member that the
container already unpacked.

| pixel layout | meaning |
|---|---|
| 0 | 4-bit indexed, two pixels per byte, low nibble first |
| 1 | 8-bit indexed, one byte per pixel |

| surface codec | meaning |
|---|---|
| 0 | stored |
| 3 | `LZM1`, the byte-oriented LZ77 below |
| 4 | `IPU1`; refused by name — nothing here implements it |

## The palette [M]

Palette format 3 is RGBA8888, four bytes per entry.  A **256-entry palette is
CSM1-interleaved**, the PlayStation 2 GS's own CLUT storage order: within each
block of 32 entries the second group of 8 and the third group of 8 are
swapped.  Undoing that is the difference between a face in the right colours
and a face in false ones.

Alpha is the PS2 convention: 0..128, where 0x80 is fully opaque, so it is
scaled to 0..255 on the way out.

## What is proved, and how [M]

**Version 2 is proved; version 1 is not.**  Members of `PLYRFACE.DAT`,
`COACFACE.DAT`, `TATTOOS.DAT`, `UNIFORMS.DAT`, `UIS_PLYR.DAT`, `UIS_LOAD.DAT`,
`FIELDART.DAT` and `STADIUMS.DAT` on the retail disc were decoded and **looked
at**: player and coach faces come out as recognisable human faces with correct
skin tones, uniform members as jersey and trouser sheets with legible panels
and trim, the jersey-number font sheet as legible digits, and the 1491x32
name-plate strip as a legible alphabet — which is also what proves the stride
rule at a width that is not a power of two.  Two failure modes are visible
rather than subtle: a wrong stride gives a diagonal shear, and a 256-entry
palette left interleaved gives a recognisable image speckled with wrong
colours.  No decoded pixel is stored in this repository.

Version 1 members — all 1,188 of `UIS_MCFL.DAT` — store their pixels under EA
codec 4, `IPU1`, and **are not decoded here** [M].  They are refused by name.

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import List, Optional, Sequence, Tuple

from mod_editor.games._formats import ea_terf
from mod_editor.games.contract import Refusal

MMAP_MAGIC = ea_terf.MMAP_MAGIC
HEADER_SIZE = 40
SURFACE_STRIDE = 16
IMAGE_STRIDE = 12
PALETTE_STRIDE = 12
NAME_STRIDE = 16

#: Low half of a surface's format word: how its pixels are laid out.
PIXELS_INDEXED_4 = 0
PIXELS_INDEXED_8 = 1
PIXEL_LAYOUT_NAMES = {PIXELS_INDEXED_4: "4-bit indexed", PIXELS_INDEXED_8: "8-bit indexed"}

#: High half of a surface's format word: EA's codec id for its pixel run.
SURFACE_STORED = 0
SURFACE_LZM1 = 3
SURFACE_IPU1 = 4

#: The only palette format measured: RGBA, four bytes per entry.
PALETTE_RGBA8888 = 3
PALETTE_ENTRY_BYTES = 4

#: A 256-entry CLUT is stored in the PS2 GS's CSM1 interleave.
CSM1_ENTRIES = 256

#: PS2 alpha runs 0..128 with 0x80 fully opaque.
PS2_ALPHA_OPAQUE = 128


class MmapError(Refusal):
    """This member could not be decoded; the sentence names the fix."""


@dataclass(frozen=True)
class Surface:
    """One mip level: its size, its format word and where its pixels are."""

    index: int
    width: int
    height: int
    format_word: int
    byte_size: int
    offset: int

    @property
    def pixel_layout(self) -> int:
        return self.format_word & 0xFFFF

    @property
    def codec(self) -> int:
        return self.format_word >> 16

    @property
    def layout_name(self) -> str:
        return PIXEL_LAYOUT_NAMES.get(self.pixel_layout,
                                      f"unknown layout {self.pixel_layout}")


@dataclass(frozen=True)
class Palette:
    """One CLUT: its format, its length and where it is."""

    index: int
    kind: int
    format_id: int
    byte_size: int
    offset: int

    @property
    def entries(self) -> int:
        return self.byte_size // PALETTE_ENTRY_BYTES


@dataclass(frozen=True)
class Image:
    """One logical texture: its mip chain, its palettes and its name."""

    index: int
    name: str
    palette_count: int
    mip_count: int
    first_surface: int
    first_palette: int

    @property
    def decodable(self) -> bool:
        """Whether this entry has pixels at all.

        A member may carry an image row with ``mip_count == 0`` whose only job
        is to hold alternate palettes for another image -- a team's second kit
        recoloured from the same pixels, most likely [A].  That is a real
        entry, not a broken one, and it has nothing to draw.
        """

        return self.mip_count > 0 and self.palette_count > 0


@dataclass(frozen=True)
class MmapTexture:
    """A parsed ``MMAP`` member: its tables, and nothing decoded yet."""

    version: int
    images: Tuple[Image, ...]
    surfaces: Tuple[Surface, ...]
    palettes: Tuple[Palette, ...]
    length: int

    def image(self, index: int) -> Image:
        if not 0 <= index < len(self.images):
            raise MmapError(
                f"this member holds {len(self.images)} image(s); image {index} was "
                f"asked for. Choose one of 0..{max(len(self.images) - 1, 0)}."
            )
        return self.images[index]

    @property
    def decodable_images(self) -> Tuple[Image, ...]:
        return tuple(image for image in self.images if image.decodable)

    def base_surface(self, image: Image) -> Optional[Surface]:
        """The largest mip level of *image*, or ``None`` when it has none."""

        if not image.decodable:
            return None
        return self.surfaces[image.first_surface]

    def undecodable_reason(self, image: Image) -> Optional[str]:
        """Why *image* cannot be drawn, or ``None`` when it can.

        A catalogue row that says only "not exportable" is no use; every one of
        these is a different fact and the page should say which.
        """

        if image.mip_count == 0:
            return (f"a palette-only entry: it carries {image.palette_count} alternate "
                    f"CLUT(s) for another image in this member and has no pixels of its own")
        if image.palette_count == 0:
            surface = self.surfaces[image.first_surface]
            if surface.codec == SURFACE_IPU1:
                return ("stored under EA codec 4 (IPU1), the PlayStation 2 IPU's own format; "
                        "nothing here decodes it")
            return (f"not an indexed texture -- it declares no palette and pixel layout "
                    f"{surface.pixel_layout}; only indexed textures are decoded here")
        surface = self.surfaces[image.first_surface]
        if surface.codec == SURFACE_IPU1:
            return ("stored under EA codec 4 (IPU1), the PlayStation 2 IPU's own format; "
                    "nothing here decodes it")
        if surface.codec not in (SURFACE_STORED, SURFACE_LZM1):
            return (f"its pixel run is stored under EA codec {surface.codec}, which is neither "
                    f"stored nor LZM1")
        if surface.pixel_layout not in PIXEL_LAYOUT_NAMES:
            return f"pixel layout {surface.pixel_layout} is not one this decoder reads"
        return None


def _require(condition: object, message: str) -> None:
    if not condition:
        raise MmapError(message)


def lzm1_decompress(data: bytes, *, what: str = "the pixel run") -> bytes:
    """EA ``LZM1`` (codec 3) as a surface stores its pixel run [M].

    One byte of stream header, then byte-oriented LZ77: a control byte with the
    top bit set copies ``control & 0x7F`` literal bytes; a non-zero control byte
    below 0x80 is a match length followed by a little-endian ``u16``
    back-distance; ``0x00`` ends the stream.
    """

    out = bytearray()
    position = 1
    size = len(data)
    while position < size:
        control = data[position]
        position += 1
        if control & 0x80:
            run = control & 0x7F
            _require(position + run <= size,
                     f"{what} declares a {run}-byte literal run at offset {position} but only "
                     f"{size - position} byte(s) follow; the member is truncated.")
            out += data[position:position + run]
            position += run
        elif control == 0:
            return bytes(out)
        else:
            _require(position + 2 <= size,
                     f"{what} declares a match at offset {position - 1} whose 2-byte distance "
                     f"runs past the end of the member; the member is truncated.")
            distance = data[position] | (data[position + 1] << 8)
            position += 2
            _require(0 < distance <= len(out),
                     f"{what} reaches {distance} byte(s) back into a {len(out)}-byte window; "
                     f"this stream is not LZM1, or it is corrupt.")
            for _ in range(control):
                out.append(out[-distance])
    return bytes(out)


def deinterleave_csm1(entries: Sequence[Tuple[int, int, int, int]]
                      ) -> List[Tuple[int, int, int, int]]:
    """Undo the PS2 GS's CSM1 CLUT order for a 256-entry palette [M].

    Within every block of 32 entries the second group of 8 and the third group
    of 8 are swapped.  Skipping this leaves a recognisable image speckled with
    wrong-colour pixels, which is how it was found: the same face decoded both
    ways is a face either way, and only one of them is right.

    **A 16-entry CLUT is stored in order and must not be touched** [M];
    :func:`read_palette` applies this only at 256 entries.
    """

    out = list(entries)
    for index in range(len(entries)):
        if (index & 0x18) == 0x08:
            out[index] = entries[index + 8]
        elif (index & 0x18) == 0x10:
            out[index] = entries[index - 8]
    return out


def parse(payload: bytes) -> MmapTexture:
    """Read a decompressed ``MMAP`` member's tables, or refuse with a sentence."""

    _require(payload.startswith(MMAP_MAGIC),
             f"this member starts with {bytes(payload[:4])!r}, not {MMAP_MAGIC!r}, so it is not "
             f"an MMAP texture. Decompress the container member first: a packed member's stored "
             f"bytes never carry its format's magic.")
    _require(len(payload) >= HEADER_SIZE,
             f"this member is {len(payload)} byte(s); an MMAP header needs {HEADER_SIZE}. "
             f"The member is truncated.")
    version, = struct.unpack_from("<I", payload, 0x04)
    image_count, surface_count = struct.unpack_from("<HH", payload, 0x0C)
    (palette_count, image_offset, surface_offset,
     palette_offset, name_offset, _extra_offset) = struct.unpack_from("<IIIIII", payload, 0x10)
    # The surface table sits immediately after the header -- but only when
    # there is one.  Six members of the retail disc (one in UNIFORMS.DAT, five
    # in STADIUMS.DAT) are pure **palette banks**: surfaceCount 0, surface
    # table offset 0, and the palette table at +0x28 instead [M].  Demanding
    # +0x28 unconditionally refuses those six wrongly, which is how this check
    # was found to be too strong.
    _require(surface_count == 0 or surface_offset == HEADER_SIZE,
             f"this member declares {surface_count} surface(s) but puts its surface table at "
             f"+0x{surface_offset:X}, not the +0x{HEADER_SIZE:X} every measured member with "
             f"surfaces uses. Re-derive the header before trusting it.")

    def bounded(offset: int, size: int, what: str) -> None:
        _require(0 <= offset and offset + size <= len(payload),
                 f"this member's {what} runs to byte {offset + size} but the member is "
                 f"{len(payload)} byte(s); the member is truncated.")

    bounded(surface_offset, SURFACE_STRIDE * surface_count, "surface table")
    surfaces = []
    for index in range(surface_count):
        width, height, format_word, byte_size, offset = struct.unpack_from(
            "<HHIII", payload, surface_offset + SURFACE_STRIDE * index)
        surfaces.append(Surface(index, width, height, format_word, byte_size, offset))

    bounded(palette_offset, PALETTE_STRIDE * palette_count, "palette table")
    palettes = []
    for index in range(palette_count):
        kind, format_id, byte_size, offset = struct.unpack_from(
            "<HHII", payload, palette_offset + PALETTE_STRIDE * index)
        palettes.append(Palette(index, kind, format_id, byte_size, offset))

    bounded(image_offset, IMAGE_STRIDE * image_count, "image table")
    named = bool(name_offset) and name_offset + NAME_STRIDE * image_count <= len(payload)
    images = []
    for index in range(image_count):
        entry_palettes, mips, first_surface, first_palette = struct.unpack_from(
            "<HHII", payload, image_offset + IMAGE_STRIDE * index)
        name = ""
        if named:
            start = name_offset + NAME_STRIDE * index
            name = payload[start:start + NAME_STRIDE].split(b"\x00")[0].decode("latin-1")
        images.append(Image(index, name, entry_palettes, mips, first_surface, first_palette))

    for image in images:
        if image.mip_count:
            _require(image.first_surface + image.mip_count <= len(surfaces),
                     f"image {image.index} claims mip levels {image.first_surface}.."
                     f"{image.first_surface + image.mip_count - 1} but this member has "
                     f"{len(surfaces)} surface(s); its tables disagree with each other.")
        if image.palette_count:
            _require(image.first_palette + image.palette_count <= len(palettes),
                     f"image {image.index} claims palettes {image.first_palette}.."
                     f"{image.first_palette + image.palette_count - 1} but this member has "
                     f"{len(palettes)} palette(s); its tables disagree with each other.")
    return MmapTexture(version=version, images=tuple(images), surfaces=tuple(surfaces),
                       palettes=tuple(palettes), length=len(payload))


def read_palette(payload: bytes, palette: Palette, *,
                 deinterleave: bool = True) -> List[Tuple[int, int, int, int]]:
    """One CLUT's entries as RGBA tuples, in drawing order."""

    _require(palette.format_id == PALETTE_RGBA8888,
             f"this member's palette {palette.index} is format {palette.format_id}, not the "
             f"RGBA8888 ({PALETTE_RGBA8888}) every measured member uses. Decode it by hand "
             f"before trusting it.")
    _require(palette.offset + palette.byte_size <= len(payload),
             f"this member's palette {palette.index} runs past its end; the member is truncated.")
    raw = payload[palette.offset:palette.offset + palette.byte_size]
    entries = [(raw[i], raw[i + 1], raw[i + 2], raw[i + 3])
               for i in range(0, len(raw) - 3, PALETTE_ENTRY_BYTES)]
    if deinterleave and len(entries) == CSM1_ENTRIES:
        entries = deinterleave_csm1(entries)
    return entries


def surface_pixels(payload: bytes, surface: Surface) -> bytes:
    """One surface's index bytes, unpacking the surface codec if there is one."""

    _require(surface.offset + surface.byte_size <= len(payload),
             f"this member's surface {surface.index} runs past its end; the member is truncated.")
    data = payload[surface.offset:surface.offset + surface.byte_size]
    if surface.codec == SURFACE_STORED:
        return data
    if surface.codec == SURFACE_LZM1:
        return lzm1_decompress(data, what=f"surface {surface.index}")
    if surface.codec == SURFACE_IPU1:
        raise MmapError(
            f"this member's surface {surface.index} is stored under EA codec {SURFACE_IPU1} "
            f"(IPU1), which nothing here implements. Pick another texture; this one cannot be "
            f"exported until an IPU1 decoder exists."
        )
    raise MmapError(
        f"this member's surface {surface.index} is stored under EA codec {surface.codec}, which "
        f"is neither stored ({SURFACE_STORED}) nor LZM1 ({SURFACE_LZM1}). It cannot be decoded "
        f"until that codec is implemented."
    )


def _scale_alpha(value: int) -> int:
    return 255 if value >= PS2_ALPHA_OPAQUE else value * 255 // PS2_ALPHA_OPAQUE


def decode_rgba(payload: bytes, *, image: int = 0, level: int = 0,
                palette: Optional[int] = None,
                texture: Optional[MmapTexture] = None) -> Tuple[int, int, bytes]:
    """One mip level of one image, as ``(width, height, RGBA bytes)``.

    Level 0 is the largest.  *palette* picks one of the image's alternate
    CLUTs by absolute index; the default is the image's own first.
    """

    info = texture if texture is not None else parse(payload)
    _require(info.images,
             "this member declares no images; it carries palettes or metadata only, so there is "
             "nothing to decode.")
    entry = info.image(image)
    _require(entry.mip_count > 0,
             f"image {image} of this member declares no surfaces -- it is a palette-only entry "
             f"carrying {entry.palette_count} alternate CLUT(s) for another image. Choose an "
             f"image that has pixels.")
    _require(level < entry.mip_count,
             f"image {image} of this member has {entry.mip_count} mip level(s); level {level} "
             f"was asked for. Level 0 is the largest.")
    _require(entry.palette_count > 0,
             f"image {image} of this member declares no palette, so it is not an indexed "
             f"texture; only indexed textures are decoded here.")
    surface = info.surfaces[entry.first_surface + level]
    entries = read_palette(payload, info.palettes[
        entry.first_palette if palette is None else palette])
    data = surface_pixels(payload, surface)
    width, height = surface.width, surface.height
    layout = surface.pixel_layout

    if layout == PIXELS_INDEXED_8:
        _require(len(data) == width * height,
                 f"this member's {width}x{height} 8-bit surface unpacked to {len(data)} byte(s) "
                 f"and needs {width * height}; the stride rule does not hold for it.")
        _require(len(entries) >= 1, "this member's palette is empty; it cannot be drawn.")
        out = bytearray(width * height * 4)
        for position, index in enumerate(data):
            red, green, blue, alpha = entries[index] if index < len(entries) else (0, 0, 0, 0)
            out[position * 4:position * 4 + 4] = bytes((red, green, blue, _scale_alpha(alpha)))
        return width, height, bytes(out)

    if layout == PIXELS_INDEXED_4:
        _require(len(data) * 2 == width * height,
                 f"this member's {width}x{height} 4-bit surface unpacked to {len(data)} byte(s) "
                 f"and needs {width * height // 2}; the stride rule does not hold for it.")
        _require(len(entries) >= 16,
                 f"this member's 4-bit surface has a {len(entries)}-entry palette and needs 16.")
        out = bytearray(width * height * 4)
        position = 0
        for byte in data:
            for index in (byte & 0x0F, byte >> 4):
                red, green, blue, alpha = entries[index]
                out[position * 4:position * 4 + 4] = bytes((red, green, blue, _scale_alpha(alpha)))
                position += 1
        return width, height, bytes(out)

    raise MmapError(
        f"this member's surface {surface.index} uses pixel layout {layout}, which is neither "
        f"4-bit indexed ({PIXELS_INDEXED_4}) nor 8-bit indexed ({PIXELS_INDEXED_8}). It cannot "
        f"be exported until that layout is implemented."
    )


def encode_indexed(rgba: bytes, width: int, height: int, surface: Surface,
                   entries: Sequence[Tuple[int, int, int, int]]) -> bytes:
    """Index *rgba* against an existing palette, for a same-shape replacement.

    Nearest entry by squared RGB distance, alpha matched on the same scale the
    decoder used.  The palette is **not** rebuilt: a replacement rides the
    texture's own CLUT, so a colour it does not carry cannot be introduced.
    That is a real limit and the caller is told about it rather than getting a
    silently approximate image.
    """

    _require(len(rgba) == width * height * 4,
             f"this image is {len(rgba)} byte(s) of RGBA and {width}x{height} needs "
             f"{width * height * 4}.")
    _require(entries, "this texture's palette is empty; nothing can be indexed against it.")
    cache: dict = {}
    lookup = [(r, g, b, _scale_alpha(a)) for r, g, b, a in entries]
    indices = bytearray(width * height)
    for position in range(width * height):
        pixel = bytes(rgba[position * 4:position * 4 + 4])
        found = cache.get(pixel)
        if found is None:
            red, green, blue, alpha = pixel
            best, best_cost = 0, None
            for index, (pr, pg, pb, pa) in enumerate(lookup):
                cost = ((red - pr) ** 2 + (green - pg) ** 2 + (blue - pb) ** 2
                        + (alpha - pa) ** 2)
                if best_cost is None or cost < best_cost:
                    best, best_cost = index, cost
                    if cost == 0:
                        break
            found = cache[pixel] = best
        indices[position] = found
    layout = surface.pixel_layout
    if layout == PIXELS_INDEXED_8:
        return bytes(indices)
    if layout == PIXELS_INDEXED_4:
        _require(all(index < 16 for index in indices),
                 "a 4-bit surface can only carry palette indices 0..15 and this image needed "
                 "more; its palette has more entries than the surface can address.")
        packed = bytearray(len(indices) // 2)
        for position in range(0, len(indices) - 1, 2):
            packed[position // 2] = indices[position] | (indices[position + 1] << 4)
        return bytes(packed)
    raise MmapError(
        f"pixel layout {layout} cannot be written; only 4-bit and 8-bit indexed surfaces are "
        f"understood here."
    )


__all__ = [
    "CSM1_ENTRIES",
    "HEADER_SIZE",
    "IMAGE_STRIDE",
    "Image",
    "MMAP_MAGIC",
    "MmapError",
    "MmapTexture",
    "NAME_STRIDE",
    "PALETTE_ENTRY_BYTES",
    "PALETTE_RGBA8888",
    "PALETTE_STRIDE",
    "PIXELS_INDEXED_4",
    "PIXELS_INDEXED_8",
    "PIXEL_LAYOUT_NAMES",
    "PS2_ALPHA_OPAQUE",
    "Palette",
    "SURFACE_IPU1",
    "SURFACE_LZM1",
    "SURFACE_STORED",
    "SURFACE_STRIDE",
    "Surface",
    "decode_rgba",
    "deinterleave_csm1",
    "encode_indexed",
    "lzm1_decompress",
    "parse",
    "read_palette",
    "surface_pixels",
]

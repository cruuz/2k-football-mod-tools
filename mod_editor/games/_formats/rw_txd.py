"""RenderWare texture dictionaries with PlayStation 2 native rasters (``.rtd``).

NFL Blitz 2002 (``SLUS-20051``) and 2003 (``SLUS-20474``) keep every texture in a
RenderWare binary stream whose one top-level section is a **texture dictionary**,
id ``0x16``.  This module walks that stream, reads each ``TextureNative``'s PS2
raster, and decodes the ones whose layout is established.

The stream [S: RenderWare's published binary-stream grammar]::

    section     u32 id, u32 body bytes, u32 library version, then the body
    0x16        TextureDictionary : Struct(u16 textures, u16 device), N x 0x15
    0x15        TextureNative     : Struct(platform, flags), String name,
                                    String mask name, Struct raster, Extension
    raster      Struct(64-byte header), Struct(GIF-tagged GS upload)

The 64-byte raster header, decoded word by word against the GS registers the
same header carries [M]::

    +0   u32 width          +16  u64 TEX0        +48  u32 texel section bytes
    +4   u32 height         +24  u64 TEX1        +52  u32 palette section bytes
    +8   u32 depth (bpp)    +32  u32 MIPTBP1     +56  u32 GPU-aligned bytes
    +12  u32 raster format  +40  u32 MIPTBP2     +60  u32 (unnamed; 10 values)

What is measured, exhaustively, on both retail discs [M]:

=========================================================  ==========  ==========
identity                                                   2002        2003
=========================================================  ==========  ==========
``.rtd`` members whose one section accounts for the file   761 of 761  840 of 840
texture dictionaries read / rasters read                   761 / 10,420  840 / 11,828
``Struct(u16)`` texture count equals the rasters found     10,420      11,828
platform word is ``PS2\\0`` on every raster                 10,420      11,828
library version word is ``0x0401ffff`` on every dictionary 761         840
raster Struct == 64-byte header + one data section         10,420      11,828
``texel bytes + palette bytes == the data section``        10,420      11,828
TEX0's TW / TH / PSM agree with the header's w / h / depth 10,420      11,828
=========================================================  ==========  ==========

Depths present: 8-bit ``PSMT8`` 4,166 / 6,365, 4-bit ``PSMT4`` 6,231 / 5,436,
32-bit ``PSMCT32`` 23 / 27 [M].

**How the texels are stored, and which of them this decodes.**  The data section
is a GIF chain: an A+D packet that sets ``TRXPOS`` / ``TRXREG`` / ``TRXDIR``,
then an ``IMAGE``-mode tag whose payload is the GS upload itself.  The upload is
**not** the texture's linear pixels: an 8-bit texture is transferred as
``PSMCT32`` at half its width and half its height, and a 4-bit one as
``PSMCT16`` at the same halved size, so the disc bytes are the GS's own memory
image and have to be un-swizzled.

Which un-swizzle is right was **measured, not assumed** [M].  Candidate layouts
were scored on 30 rasters of the retail 2002 disc by the mean absolute
difference between horizontally adjacent decoded RGB values -- real art is
locally coherent and a wrong layout destroys that:

======================  =========================  ======
depth                   layout                     score
======================  =========================  ======
8-bit                   **PSMCT32 composition**    7.32
8-bit                   GS block image, inverted   15.93
8-bit                   raw linear                 24.26
4-bit                   half-width via 8-bit       18.75
4-bit                   published 4-bit routine    20.14
4-bit                   raw linear                 20.53
4-bit                   GS block image, inverted   28.16
======================  =========================  ======

The 8-bit answer beats the null by 232% and is taken.  **No 4-bit candidate
separates from the null** -- the best beats raw linear by 9% -- so a 4-bit
raster is listed with its size, format and identity and :func:`decode_rgba`
refuses it by name.  Guessing there would put a wrong picture on a page.

32-bit rasters are direct colour with no palette and are decoded from the same
GIF payload without any index step.

**PCSX2 replacement identities are derived, none confirmed.**  A decoded
raster's name is computed from its own bytes through
:mod:`~mod_editor.games._formats.pcsx2_texture_name`, whose GS block layout is
measured against 33 PCSX2 dumps of a different game.  No dump of either Blitz
disc exists here, so every identity this module returns is derived and is
labelled so.

Standard library only; importable without Qt.

**Evidence tags.**  **[M]** measured on the retail disc named; **[S]** sourced;
**[A]** assumed.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

from mod_editor.games._formats import pcsx2_texture_name as names
from mod_editor.games.contract import Refusal

__all__ = [
    "RwTxdError", "Section", "Raster", "Dictionary",
    "ID_STRUCT", "ID_STRING", "ID_EXTENSION", "ID_TEXTURE_NATIVE", "ID_TEXTURE_DICTIONARY",
    "SECTION_HEADER_BYTES", "RASTER_HEADER_BYTES", "PLATFORM_PS2",
    "walk", "read_dictionary", "read_palette", "decode_indices", "decode_rgba",
    "undecodable_reason", "replacement_identity", "build_synthetic_dictionary",
]

#: The RenderWare section ids this module names [S].
ID_STRUCT = 0x01
ID_STRING = 0x02
ID_EXTENSION = 0x03
ID_TEXTURE_NATIVE = 0x15
ID_TEXTURE_DICTIONARY = 0x16

#: ``u32 id, u32 body bytes, u32 library version`` [S].
SECTION_HEADER_BYTES = 12
#: The PS2 raster's fixed header, inside its own Struct [M].
RASTER_HEADER_BYTES = 64
#: The platform word a PS2 ``TextureNative`` carries, as four bytes [M].
PLATFORM_PS2 = b"PS2\x00"

#: GS pixel storage modes, by the header's bits-per-texel [S].
_PSM_FOR_DEPTH: Mapping[int, int] = {4: 20, 8: 19, 32: 0}
#: The GIF tag's FLG field: 0 packed, 1 REGLIST, 2 image [S].
_GIF_PACKED, _GIF_IMAGE = 0, 2

#: RenderWare raster-format flag bits this module reads [S].
_FORMAT_PAL8 = 0x2000
_FORMAT_PAL4 = 0x4000
_FORMAT_MIPMAP = 0x8000

#: A dictionary bigger than this is refused rather than walked; the largest on
#: either disc is 1.1 MB [M].
_MAX_MEMBER_BYTES = 64 << 20
#: A dictionary declaring more rasters than this is refused; the largest on
#: either disc declares 244 [M].
_MAX_RASTERS = 4096


class RwTxdError(Refusal):
    """This is not a PS2 RenderWare texture dictionary, or a raster is not decodable."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise RwTxdError(message)


@dataclass(frozen=True)
class Section:
    """One RenderWare section: its id, its body's span, and the library version."""

    id: int
    body_offset: int
    body_bytes: int
    version: int

    @property
    def end(self) -> int:
        return self.body_offset + self.body_bytes


def walk(data: bytes, start: int, end: int) -> Iterator[Section]:
    """The sections laid end to end between ``start`` and ``end``.

    Stops rather than raising when a declared length runs past ``end``: a
    stream's tail is the caller's business, and every identity this module
    checks is stated over what the walk did return.
    """

    position = start
    while position + SECTION_HEADER_BYTES <= end:
        section_id, body, version = struct.unpack_from("<3I", data, position)
        body_at = position + SECTION_HEADER_BYTES
        if body_at + body > end:
            return
        yield Section(section_id, body_at, body, version)
        position = body_at + body


def _children(data: bytes, section: Section) -> List[Section]:
    return list(walk(data, section.body_offset, section.end))


@dataclass(frozen=True)
class Raster:
    """One ``TextureNative``: its names, its size, and where its two GS uploads are."""

    index: int
    name: str
    mask_name: str
    width: int
    height: int
    depth: int
    raster_format: int
    tex0: int
    texel_bytes: int
    palette_bytes: int
    gpu_aligned_bytes: int
    header_word15: int
    #: Span of the whole data section (texel bytes then palette bytes).
    data_offset: int
    #: Span of the raster's 64-byte header, so a catalogue can name it.
    header_offset: int

    @property
    def psm(self) -> int:
        """The GS pixel storage mode TEX0 declares."""

        return (self.tex0 >> 20) & 0x3F

    @property
    def tex0_width(self) -> int:
        return 1 << ((self.tex0 >> 26) & 0xF)

    @property
    def tex0_height(self) -> int:
        return 1 << ((self.tex0 >> 30) & 0xF)

    @property
    def palette_entries(self) -> int:
        return (1 << self.depth) if self.depth in (4, 8) else 0

    @property
    def has_mipmaps(self) -> bool:
        return bool(self.raster_format & _FORMAT_MIPMAP)

    @property
    def texel_payload_offset(self) -> int:
        return self.data_offset

    @property
    def palette_payload_offset(self) -> int:
        return self.data_offset + self.texel_bytes


@dataclass(frozen=True)
class Dictionary:
    """A parsed ``.rtd``: the rasters, and the identities the file's own words assert."""

    name: str
    total_bytes: int
    library_version: int
    declared_textures: int
    rasters: tuple[Raster, ...]
    section_accounts_for_file: bool
    _data: bytes = b""

    def raster(self, index: int) -> Raster:
        for candidate in self.rasters:
            if candidate.index == index:
                return candidate
        raise RwTxdError(
            f"{self.name}: raster {index} is not in this dictionary; it holds "
            f"{len(self.rasters)}."
        )


def _gif_image_payload(data: bytes, start: int, span: int) -> Optional[Tuple[int, int]]:
    """``(offset, length)`` of the first ``IMAGE``-mode payload in a GIF chain."""

    position = start
    limit = start + span
    while position + 16 <= limit:
        low, _regs = struct.unpack_from("<QQ", data, position)
        nloop = low & 0x7FFF
        flag = (low >> 58) & 3
        registers = (low >> 60) & 0xF
        position += 16
        if flag == _GIF_IMAGE:
            return position, min(nloop * 16, limit - position)
        if flag != _GIF_PACKED:
            return None
        position += nloop * (registers or 16) * 16
    return None


def read_dictionary(data: bytes, name: str = "texture dictionary") -> Dictionary:
    """Parse a ``.rtd``, refusing anything whose own section words do not hold [M]."""

    data = bytes(data)
    _require(len(data) >= SECTION_HEADER_BYTES,
             f"{name}: a {len(data)}-byte file is shorter than a RenderWare section header.")
    _require(len(data) <= _MAX_MEMBER_BYTES,
             f"{name}: a {len(data)}-byte member is larger than this reader walks; the largest "
             f"texture dictionary on either Blitz disc is 1.1 MB.")
    top = next(iter(walk(data, 0, len(data))), None)
    _require(top is not None, f"{name}: no RenderWare section could be read from this member.")
    assert top is not None
    _require(top.id == ID_TEXTURE_DICTIONARY,
             f"{name}: the first section is id 0x{top.id:02x}, not the texture-dictionary id "
             f"0x{ID_TEXTURE_DICTIONARY:02x}; this is not a .rtd.")
    accounts = top.body_bytes + SECTION_HEADER_BYTES == len(data)

    children = _children(data, top)
    struct_sections = [child for child in children if child.id == ID_STRUCT]
    _require(struct_sections and struct_sections[0].body_bytes >= 2,
             f"{name}: the dictionary carries no Struct section declaring its texture count.")
    declared = struct.unpack_from("<H", data, struct_sections[0].body_offset)[0]
    _require(declared <= _MAX_RASTERS,
             f"{name}: this dictionary declares {declared} textures, more than the "
             f"{_MAX_RASTERS} this reader walks; it is not a Blitz texture dictionary.")

    rasters: List[Raster] = []
    for child in children:
        if child.id != ID_TEXTURE_NATIVE:
            continue
        parts = _children(data, child)
        _require(len(parts) >= 4,
                 f"{name}: TextureNative {len(rasters)} carries {len(parts)} sections; a PS2 "
                 f"one carries a Struct, two Strings and a raster Struct.")
        platform = data[parts[0].body_offset:parts[0].body_offset + 4]
        _require(platform == PLATFORM_PS2,
                 f"{name}: TextureNative {len(rasters)} declares platform "
                 f"{platform!r}, not {PLATFORM_PS2!r}; only the PlayStation 2 native raster "
                 f"is read here.")
        strings = [part for part in parts if part.id == ID_STRING]
        _require(len(strings) >= 2,
                 f"{name}: TextureNative {len(rasters)} carries {len(strings)} String sections; "
                 f"a PS2 one carries its name and its mask name.")
        structs = [part for part in parts if part.id == ID_STRUCT]
        _require(len(structs) >= 2,
                 f"{name}: TextureNative {len(rasters)} carries no raster Struct.")
        raster_struct = structs[1]
        inner = _children(data, raster_struct)
        _require(len(inner) >= 2 and inner[0].body_bytes == RASTER_HEADER_BYTES,
                 f"{name}: raster {len(rasters)} does not begin with a "
                 f"{RASTER_HEADER_BYTES}-byte header Struct; this is not the PS2 raster layout.")
        words = struct.unpack_from("<16I", data, inner[0].body_offset)
        tex0 = struct.unpack_from("<Q", data, inner[0].body_offset + 16)[0]
        width, height, depth, raster_format = words[0], words[1], words[2], words[3]
        texel, palette, aligned, word15 = words[12], words[13], words[14], words[15]
        _require(texel + palette == inner[1].body_bytes,
                 f"{name}: raster {len(rasters)} declares {texel} texel and {palette} palette "
                 f"bytes in a {inner[1].body_bytes}-byte data section; the header and the "
                 f"section disagree and nothing here is safe to read.")
        rasters.append(Raster(
            index=len(rasters),
            name=_string(data, strings[0]),
            mask_name=_string(data, strings[1]),
            width=width, height=height, depth=depth, raster_format=raster_format,
            tex0=tex0, texel_bytes=texel, palette_bytes=palette,
            gpu_aligned_bytes=aligned, header_word15=word15,
            data_offset=inner[1].body_offset, header_offset=inner[0].body_offset))
    return Dictionary(name, len(data), top.version, declared, tuple(rasters), accounts, data)


def _string(data: bytes, section: Section) -> str:
    raw = data[section.body_offset:section.end]
    return raw.split(b"\x00", 1)[0].decode("latin-1")


# --------------------------------------------------------------------------
# Decoding
# --------------------------------------------------------------------------

def _unswizzle8(gs: bytes, width: int, height: int) -> bytes:
    """GS memory image -> linear 8-bit indices; the ``PSMCT32`` composition [M].

    An 8-bit texture is uploaded as a ``PSMCT32`` rectangle of half its width and
    half its height, so the disc bytes are the GS's memory image and this is the
    inverse of that transfer.  Measured against three candidate layouts on the
    retail disc; this one is 3.3 times more coherent than reading the bytes
    linearly (see the module docstring).
    """

    out = bytearray(width * height)
    for y in range(height):
        block = (y & ~0xF) * width
        column = ((((y & ~3) >> 1) + (y & 1)) & 7) * width * 2
        swap = (((y + 2) >> 2) & 1) * 4
        parity = (y >> 1) & 1
        row = y * width
        for x in range(width):
            source = (block + (x & ~0xF) * 2 + column + ((x + swap) & 7) * 4
                      + parity + ((x >> 2) & 2))
            out[row + x] = gs[source] if source < len(gs) else 0
    return bytes(out)


def read_palette(dictionary: Dictionary, raster: Raster) -> List[Tuple[int, int, int, int]]:
    """The raster's CLUT in drawing order, RGBA, with the GS's own alpha scale.

    A 256-entry CLUT is stored in the GS's CSM1 interleave and is put back into
    drawing order here [S: the GS's CLUT storage]; a 16-entry one is not
    interleaved.  The GIF chain uploads the CLUT as a rectangle wider than the
    palette needs -- ``8 x 3`` for sixteen entries, ``16 x 16`` for 256 [M] --
    and the entries the texture unit reads are the first ``2 ** depth``.
    """

    _require(raster.palette_entries > 0,
             f"{dictionary.name}: raster {raster.index} is {raster.depth}-bit direct colour "
             f"and carries no palette.")
    found = _gif_image_payload(dictionary._data, raster.palette_payload_offset,
                               raster.palette_bytes)
    _require(found is not None,
             f"{dictionary.name}: raster {raster.index}'s palette section carries no "
             f"IMAGE-mode GIF tag; its CLUT cannot be read.")
    assert found is not None
    offset, length = found
    wanted = raster.palette_entries * 4
    _require(length >= wanted,
             f"{dictionary.name}: raster {raster.index} needs {wanted} palette bytes and its "
             f"upload carries {length}.")
    raw = dictionary._data[offset:offset + wanted]
    entries = [(raw[i * 4], raw[i * 4 + 1], raw[i * 4 + 2], raw[i * 4 + 3])
               for i in range(raster.palette_entries)]
    if len(entries) == 256:
        entries = _deinterleave_csm1(entries)
    return entries


def _deinterleave_csm1(entries: Sequence[Tuple[int, int, int, int]]
                       ) -> List[Tuple[int, int, int, int]]:
    """Undo the GS's CSM1 CLUT order for a 256-entry palette [S].

    Within each group of 32 the middle two groups of eight are exchanged.  This
    is the same rule :mod:`mmap_art` states for EA's PS2 art; it is a fact about
    the console, not about either publisher, and is written out here so a format
    package never imports another format package for four lines.
    """

    out = list(entries)
    for index in range(len(entries)):
        if (index & 0x18) == 0x08:
            out[index] = entries[index + 8]
        elif (index & 0x18) == 0x10:
            out[index] = entries[index - 8]
    return out


def undecodable_reason(raster: Raster) -> Optional[str]:
    """Why this raster is listed and not drawn, or ``None`` when it decodes."""

    if raster.depth == 8 or raster.depth == 32:
        return None
    if raster.depth == 4:
        return ("A 4-bit raster's GS upload layout is not established: seven candidate "
                "un-swizzles were scored on the retail disc and the best beat reading the "
                "bytes linearly by 9%, where the 8-bit answer beat it by 232%, so this "
                "reader lists a 4-bit raster and does not draw it.")
    return (f"A raster of {raster.depth} bits per texel is not one of the three depths "
            f"measured on either Blitz disc (4, 8 and 32).")


def decode_indices(dictionary: Dictionary, raster: Raster) -> bytes:
    """The raster's palette indices, one byte per texel, row-major.

    Refuses any raster :func:`undecodable_reason` names, in that function's own
    sentence.
    """

    reason = undecodable_reason(raster)
    _require(reason is None, f"{dictionary.name}: raster {raster.index}. {reason}")
    _require(raster.depth == 8,
             f"{dictionary.name}: raster {raster.index} is {raster.depth}-bit and carries no "
             f"palette indices.")
    found = _gif_image_payload(dictionary._data, raster.texel_payload_offset, raster.texel_bytes)
    _require(found is not None,
             f"{dictionary.name}: raster {raster.index}'s texel section carries no IMAGE-mode "
             f"GIF tag; its pixels cannot be read.")
    assert found is not None
    offset, length = found
    wanted = raster.width * raster.height
    _require(length >= wanted,
             f"{dictionary.name}: raster {raster.index} is {raster.width}x{raster.height} at "
             f"{raster.depth} bits, which needs {wanted} bytes, and its upload carries {length}.")
    return _unswizzle8(dictionary._data[offset:offset + wanted], raster.width, raster.height)


def decode_rgba(dictionary: Dictionary, raster: Raster) -> bytes:
    """The raster as RGBA bytes, row-major, or a refusal naming why it is not drawn."""

    reason = undecodable_reason(raster)
    _require(reason is None, f"{dictionary.name}: raster {raster.index}. {reason}")
    if raster.depth == 32:
        found = _gif_image_payload(dictionary._data, raster.texel_payload_offset,
                                   raster.texel_bytes)
        _require(found is not None,
                 f"{dictionary.name}: raster {raster.index}'s texel section carries no "
                 f"IMAGE-mode GIF tag; its pixels cannot be read.")
        assert found is not None
        offset, length = found
        wanted = raster.width * raster.height * 4
        _require(length >= wanted,
                 f"{dictionary.name}: raster {raster.index} needs {wanted} direct-colour bytes "
                 f"and its upload carries {length}.")
        return dictionary._data[offset:offset + wanted]
    indices = decode_indices(dictionary, raster)
    palette = read_palette(dictionary, raster)
    out = bytearray(len(indices) * 4)
    for position, index in enumerate(indices):
        entry = palette[index] if index < len(palette) else (0, 0, 0, 0)
        out[position * 4:position * 4 + 4] = bytes(entry)
    return bytes(out)


def replacement_identity(dictionary: Dictionary, raster: Raster) -> Optional[str]:
    """The PCSX2 replacement filename this raster's own bytes derive, or ``None``.

    Derived, never confirmed: no PCSX2 texture dump of either Blitz disc exists
    in this project, so the name is what the emulator's documented rules compute
    and no more.
    """

    if undecodable_reason(raster) is not None or raster.depth != 8:
        return None
    try:
        indices = decode_indices(dictionary, raster)
        palette = read_palette(dictionary, raster)
        level = names.TextureLevel(raster.width, raster.height, 8, indices)
        tex0 = names.tex0_hash([level])
        clut = names.clut_hash([tuple(entry) for entry in palette])
        bits = names.texture_bits(names.PSMT8,
                                  names.log2_exact(raster.width),
                                  names.log2_exact(raster.height))
    except (names.NameError, RwTxdError):
        return None
    return names.replacement_name(tex0, clut, bits)


# --------------------------------------------------------------------------
# A synthetic dictionary: what CI proves this on, with no game data
# --------------------------------------------------------------------------

def _section(section_id: int, body: bytes, version: int = 0x0401FFFF) -> bytes:
    return struct.pack("<3I", section_id, len(body), version) + body


def _swizzle8(indices: bytes, width: int, height: int) -> bytes:
    """The inverse of :func:`_unswizzle8`, so a builder can lay out known pixels."""

    out = bytearray(width * height)
    for y in range(height):
        block = (y & ~0xF) * width
        column = ((((y & ~3) >> 1) + (y & 1)) & 7) * width * 2
        swap = (((y + 2) >> 2) & 1) * 4
        parity = (y >> 1) & 1
        row = y * width
        for x in range(width):
            target = (block + (x & ~0xF) * 2 + column + ((x + swap) & 7) * 4
                      + parity + ((x >> 2) & 2))
            if target < len(out):
                out[target] = indices[row + x]
    return bytes(out)


def _gif_upload(payload: bytes, rect_width: int, rect_height: int) -> bytes:
    """An A+D packet then an IMAGE tag, in the shape both discs write [M]."""

    packet = struct.pack("<QQ", 3 | (1 << 60), 0x0E)
    packet += struct.pack("<QQ", 0, 0x51)
    packet += struct.pack("<QQ", (rect_height << 32) | rect_width, 0x52)
    packet += struct.pack("<QQ", 0, 0x53)
    padded = bytes(payload) + bytes((-len(payload)) % 16)
    packet += struct.pack("<QQ", (len(padded) // 16) | (1 << 15) | (2 << 58), 0)
    return packet + padded


def build_synthetic_dictionary(rasters: Sequence[Tuple[str, int, int, bytes,
                                                       Sequence[Tuple[int, int, int, int]]]]
                               ) -> bytes:
    """A PS2 texture dictionary carrying known 8-bit pixels, built here byte by byte.

    Each entry is ``(name, width, height, indices, palette)``; the indices are
    laid into the GS memory image with :func:`_swizzle8`, so a decode of the
    result must return them exactly.  Retail-free by construction: every byte
    comes from the caller or from this function.
    """

    body = _section(ID_STRUCT, struct.pack("<HH", len(rasters), 0))
    for name, width, height, indices, palette in rasters:
        _require(len(indices) == width * height,
                 f"{name}: {len(indices)} index byte(s) were given for a {width}x{height} "
                 f"texture, which needs {width * height}.")
        _require(len(palette) == 256,
                 f"{name}: an 8-bit synthetic raster needs a 256-entry palette and "
                 f"{len(palette)} were given.")
        stored = list(palette)
        for index in range(256):        # back into the GS's CSM1 order
            if (index & 0x18) == 0x08:
                stored[index + 8] = palette[index]
            elif (index & 0x18) == 0x10:
                stored[index - 8] = palette[index]
        clut = b"".join(bytes(entry) for entry in stored)
        texel_upload = _gif_upload(_swizzle8(indices, width, height), width // 2, height // 2)
        clut_upload = _gif_upload(clut, 16, 16)
        tex0 = ((names.PSMT8 << 20) | (max(1, width // 64) << 14)
                | (names.log2_exact(width) << 26) | (names.log2_exact(height) << 30))
        header = struct.pack("<4I", width, height, 8, _FORMAT_PAL8 | 0x0500)
        header += struct.pack("<Q", tex0) + struct.pack("<Q", 0)
        header += struct.pack("<4I", 0, 0, 0, 0)
        header += struct.pack("<4I", len(texel_upload), len(clut_upload),
                              width * height, 4032)
        raster = _section(ID_STRUCT, header) + _section(ID_STRUCT, texel_upload + clut_upload)
        native = _section(ID_STRUCT, PLATFORM_PS2 + struct.pack("<I", 0x1102))
        native += _section(ID_STRING, name.encode("latin-1").ljust(16, b"\x00"))
        native += _section(ID_STRING, bytes(4))
        native += _section(ID_STRUCT, raster)
        native += _section(ID_EXTENSION, b"")
        body += _section(ID_TEXTURE_NATIVE, native)
    body += _section(ID_EXTENSION, b"")
    return _section(ID_TEXTURE_DICTIONARY, body)

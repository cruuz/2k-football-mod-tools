"""PCSX2 texture-replacement names, **derived** from a texture's own bytes.

PCSX2 finds a replacement for a texture by a filename it builds while the
game draws::

    <tex0 hash>-<clut hash>-<bits>.png

The two hashes are XXH3-64.  The CLUT half is over the palette as the GS
holds it, in drawing order (a 256-entry CLUT de-interleaved from its CSM1
storage), 16 or 256 entries of four bytes.  The TEX0 half is over the
texture's **GS block image**: the emulator walks the texture's 256-byte
blocks in row-major block order and feeds each block's bytes -- laid out the
way the GS stores them, not the way the disc does -- into one hash state.
A texture smaller than a block, and a region-clamped draw, take a second
path instead: the emulator unswizzles the rectangle to one byte per texel and
hashes that.  With mipmapping on, the levels the draw can reach are fed into
the **same** state after the base, so one texture has one name per
``(base level, number of levels)`` pair the game happens to use.

This module re-expresses those rules so a module can name a texture from a
disc alone, and says when it cannot:

* a level whose width or height is not a power of two, because the GS ``TW`` /
  ``TH`` fields are logarithms and the hash would cover memory the disc does
  not carry;
* a level that is at least a block in one dimension and not a whole number
  of blocks in it, for the same reason;
* a region-clamped draw, whose rectangle offset is not in any file.

**What is measured, and what this rests on** [M].  On the owner's retail
Madden NFL 09 disc, against 33 PCSX2 texture dumps of the game running,
2,994 of the 3,024 disc images the pixel matcher had identified reproduce
their dumped TEX0 hash from the disc bytes through these rules -- 8-bit and
4-bit, block path and linear path, single levels and mip chains -- and the
dumped names the pixel matcher could not place are placed by hash alone
(the count is in the measured document).  The GS block
layout below is the one the dumps confirm; it was not taken from any other
project's tables.  ``docs/product/measured/madden09_ps2/`` carries the counts.

**What this does not claim.**  A derived name is the name PCSX2 *computes*;
nothing here has loaded a replacement pack, so a derived name is proved by
the dumps that agree with it and no further.  The CLUT half is derived only
where the palette the game draws with is one the member carries: some
textures are drawn with a CLUT the game builds at run time, and those are
named by their TEX0 half only.

Standard library only; importable without Qt.

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from mod_editor.games._formats import xxhash3_64
from mod_editor.games.contract import Refusal

__all__ = [
    "PSMT8", "PSMT4", "PSMT8H", "BLOCK_BYTES", "BLOCK_SIZE", "PSM_FOR_BITS", "BITS_FOR_PSM",
    "TextureLevel", "DerivedName", "ParsedName", "NameError",
    "block_offset_8", "block_nibble_4", "block_image", "hashed_stream",
    "tex0_hash", "tex0_hash_chains", "clut_hash", "texture_bits",
    "replacement_name", "parse_name", "derive_names", "log2_exact",
]

#: GS pixel storage modes for the two indexed formats a Madden 09 ``MMAP``
#: surface is stored in.  PCSX2 writes the PSM into the low six bits of the
#: name's ``bits`` word.
PSMT8 = 19
PSMT4 = 20

#: The GS's *high-byte* 8-bit mode: the index lives in the top byte of a
#: 32-bit word, so the surface is a ``PSMCT32`` one and its 256-byte blocks
#: interleave the index with three bytes of whatever else shares the page.
#: PCSX2 cannot hash those blocks meaningfully and takes its expansion path
#: instead, which is why a ``PSMT8H`` name is derived from the **linear**
#: texel stream at any size [M].  See :func:`hashed_stream`.
PSMT8H = 27

#: Every GS block is 256 bytes whatever the format [S].
BLOCK_BYTES = 256

#: Texels per block, by index width: 16x16 at 8 bits, 32x16 at 4 bits [S].
BLOCK_SIZE: Mapping[int, Tuple[int, int]] = {8: (16, 16), 4: (32, 16)}

PSM_FOR_BITS: Mapping[int, int] = {8: PSMT8, 4: PSMT4}
BITS_FOR_PSM: Mapping[int, int] = {PSMT8: 8, PSMT4: 4, PSMT8H: 8}

#: Index widths that also have a high-byte mode, and the mode they take.
HIGH_BYTE_PSM: Mapping[int, int] = {8: PSMT8H}

#: The two naming conventions a dump can be written under.  ``modern`` is stock
#: PCSX2, whose ``bits`` word carries no TCC; ``classic`` is the older grammar
#: PenguinScreen2 restores on request, with the draw's TCC in bit 14, so the
#: same texture drawn with and without alpha has two classic names and one
#: modern one.  A classic name with TCC clear is byte-identical to the modern
#: one, which is why every build parses it.
CONVENTION_MODERN = "modern"
CONVENTION_CLASSIC = "classic"

#: How the hashed byte stream of one level was produced.
PATH_BLOCKS = "blocks"
PATH_LINEAR = "linear"


class NameError(Refusal):  # noqa: A001 - the module's own refusal, on purpose
    """A name could not be derived; the sentence says why."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise NameError(message)


# --------------------------------------------------------------------------
# The GS block layout
# --------------------------------------------------------------------------
#
# A block is four 64-byte columns, each holding four rows of texels.  Within
# a column the texel order interleaves the four rows so that the GS can read
# a column as sixteen 32-bit words; the interleave alternates between two
# arrangements on every other pair of rows, and the alternation itself flips
# between odd and even columns.  The two functions below say exactly where a
# texel lands, and the dumps say they are right [M].


def _swap(y: int) -> int:
    """Whether row *y* uses the swapped arrangement: rows 2-3 of an even column, rows 0-1 of an odd one."""

    return ((y >> 1) & 1) ^ ((y >> 2) & 1)


def block_offset_8(x: int, y: int) -> int:
    """Byte offset of texel ``(x, y)`` inside a 256-byte 8-bit block, ``0 <= x, y < 16``."""

    return ((y >> 2) * 64 + (y & 1) * 8 + ((y >> 1) & 1) + ((x >> 3) & 1) * 2 + (x & 1) * 4
            + ((((x >> 1) & 3) ^ (_swap(y) << 1)) * 16))


def block_nibble_4(x: int, y: int) -> int:
    """Nibble offset of texel ``(x, y)`` inside a 256-byte 4-bit block, ``0 <= x < 32``, ``0 <= y < 16``.

    An even nibble is the low half of byte ``nibble >> 1``, an odd one the high
    half.
    """

    return ((y >> 2) * 128 + (y & 1) * 16 + ((y >> 1) & 1) + ((x >> 3) & 3) * 2 + (x & 1) * 8
            + ((((x >> 1) & 3) ^ (_swap(y) << 1)) * 32))


_TABLE_8 = tuple(tuple(block_offset_8(x, y) for x in range(16)) for y in range(16))
_TABLE_4 = tuple(tuple(block_nibble_4(x, y) for x in range(32)) for y in range(16))

#: ``(width, height, bits) -> for every output texel slot, the linear texel index``.
_PERMUTATIONS: Dict[Tuple[int, int, int], List[int]] = {}


def _permutation(width: int, height: int, bits: int) -> List[int]:
    key = (width, height, bits)
    cached = _PERMUTATIONS.get(key)
    if cached is not None:
        return cached
    block_w, block_h = BLOCK_SIZE[bits]
    slots_per_block = BLOCK_BYTES if bits == 8 else BLOCK_BYTES * 2
    table = _TABLE_8 if bits == 8 else _TABLE_4
    blocks_across = width // block_w
    out = [0] * (width * height)
    for block_y in range(height // block_h):
        for block_x in range(blocks_across):
            base = (block_y * blocks_across + block_x) * slots_per_block
            for row in range(block_h):
                line = (block_y * block_h + row) * width + block_x * block_w
                slots = table[row]
                for column in range(block_w):
                    out[base + slots[column]] = line + column
    if len(_PERMUTATIONS) > 64:
        _PERMUTATIONS.clear()
    _PERMUTATIONS[key] = out
    return out


def block_image(indices: Sequence[int], width: int, height: int, bits: int) -> bytes:
    """*indices* (one texel per entry, row-major) as the GS holds them: whole blocks, row-major.

    Refuses a size that is not a whole number of blocks: the emulator would
    hash bytes of memory the texture does not cover.
    """

    _require(bits in BLOCK_SIZE, f"an index width of {bits} bits is neither 8 nor 4.")
    block_w, block_h = BLOCK_SIZE[bits]
    _require(width % block_w == 0 and height % block_h == 0,
             f"a {width}x{height} {bits}-bit texture is not a whole number of "
             f"{block_w}x{block_h} blocks; its block image would include memory the "
             f"texture does not cover.")
    _require(len(indices) == width * height,
             f"{len(indices)} texel(s) were given for a {width}x{height} texture, which needs "
             f"{width * height}.")
    permutation = _permutation(width, height, bits)
    fetch = indices.__getitem__
    if bits == 8:
        return bytes(map(fetch, permutation))
    nibbles = list(map(fetch, permutation))
    return bytes((nibbles[position] & 0x0F) | ((nibbles[position + 1] & 0x0F) << 4)
                 for position in range(0, len(nibbles), 2))


def log2_exact(value: int, what: str = "a texture dimension") -> int:
    """``log2(value)`` for a power of two, or a refusal naming the value."""

    _require(value > 0 and (value & (value - 1)) == 0,
             f"{what} of {value} is not a power of two, and the GS describes a texture's "
             f"size as a power of two; a name cannot be derived for it.")
    return value.bit_length() - 1


def hashed_stream(indices: Sequence[int], width: int, height: int, bits: int,
                  *, psm: Optional[int] = None) -> Tuple[bytes, str]:
    """The bytes PCSX2 hashes for one level, and which of its two paths produced them.

    Smaller than a block in either dimension: the unswizzled rectangle, one
    byte per texel (the emulator's expansion path).  Otherwise the block image.

    ``psm=PSMT8H`` takes the linear path **at every size** [M].  A high-byte
    texture shares its 256-byte blocks with a 32-bit surface, so three of every
    four bytes of a block belong to something else and the emulator expands the
    rectangle rather than hashing memory it would have to invent.  Measured on
    the MVP Baseball 2005 dump: eighteen dumped names carry ``PSM`` 27 and the
    block reading reproduces none of them, while the linear reading reproduces
    every one, at 128x64, 128x128, 256x128, 256x256 and 512x256.
    """

    log2_exact(width, "a texture width")
    log2_exact(height, "a texture height")
    if psm == PSMT8H:
        _require(bits == 8, f"PSM {PSMT8H} carries an 8-bit index and this level is {bits}-bit.")
        _require(len(indices) == width * height,
                 f"{len(indices)} texel(s) were given for a {width}x{height} texture, which "
                 f"needs {width * height}.")
        return bytes(index & 0xFF for index in indices), PATH_LINEAR
    _require(psm in (None, PSM_FOR_BITS.get(bits)),
             f"PSM {psm} is not a mode this module derives a name for.")
    _require(bits in BLOCK_SIZE, f"an index width of {bits} bits is neither 8 nor 4.")
    block_w, block_h = BLOCK_SIZE[bits]
    if width < block_w or height < block_h:
        _require(len(indices) == width * height,
                 f"{len(indices)} texel(s) were given for a {width}x{height} texture, which "
                 f"needs {width * height}.")
        return bytes(index & 0xFF for index in indices), PATH_LINEAR
    return block_image(indices, width, height, bits), PATH_BLOCKS


@dataclass(frozen=True)
class TextureLevel:
    """One mip level: its size, its index width and its texels, row-major, one per entry."""

    width: int
    height: int
    bits: int
    indices: bytes

    @property
    def psm(self) -> int:
        return PSM_FOR_BITS[self.bits]


def tex0_hash(levels: Sequence[TextureLevel], *, psm: Optional[int] = None) -> int:
    """XXH3-64 over the levels' hashed streams, in order, as one state.

    PCSX2 feeds the base level and then each further level of the draw's LOD
    range into a single streaming state, which is the same value as one hash
    over the concatenation.
    """

    _require(len(levels) > 0, "a texture name needs at least one level to hash.")
    return xxhash3_64.xxh3_64(b"".join(hashed_stream(level.indices, level.width, level.height,
                                                     level.bits, psm=psm)[0] for level in levels))


def tex0_hash_chains(levels: Sequence[TextureLevel], *,
                     psm: Optional[int] = None) -> Dict[Tuple[int, int], int]:
    """``(base level, level count) -> TEX0 hash`` for every chain the game could draw.

    A texture with *n* levels has ``n (n + 1) / 2`` chains: any base level, and
    any number of levels from it down to the smallest.  Which ones a game uses
    depends on how far away it draws the texture, so a pack that wants to be
    found at every distance carries them all.
    """

    _require(len(levels) > 0, "a texture name needs at least one level to hash.")
    streams = [hashed_stream(level.indices, level.width, level.height, level.bits, psm=psm)[0]
               for level in levels]
    out: Dict[Tuple[int, int], int] = {}
    for base in range(len(streams)):
        joined = b""
        for count in range(1, len(streams) - base + 1):
            joined += streams[base + count - 1]
            out[(base, count)] = xxhash3_64.xxh3_64(joined)
    return out


def clut_hash(entries: Sequence[Tuple[int, int, int, int]]) -> int:
    """XXH3-64 over a palette in drawing order, four bytes an entry, 16 or 256 entries.

    The entries are the CLUT as the GS presents it to the texture unit -- a
    256-entry CLUT already de-interleaved from its CSM1 storage -- with alpha
    on the GS's own 0..128 scale, exactly as :mod:`mmap_art.read_palette`
    hands it back.
    """

    _require(len(entries) in (16, 256),
             f"a CLUT has 16 or 256 entries and this one has {len(entries)}.")
    raw = bytearray()
    for index, entry in enumerate(entries):
        _require(len(entry) == 4,
                 f"palette entry {index} has {len(entry)} channel(s); an entry is red, green, "
                 f"blue and alpha.")
        for value in entry:
            _require(0 <= int(value) <= 255,
                     f"palette entry {index} carries {value}, which is not a byte.")
            raw.append(int(value))
    return xxhash3_64.xxh3_64(bytes(raw))


def texture_bits(psm: int, tw: int, th: int, tcc: int = 0) -> int:
    """PCSX2's packed property word: ``PSM | TW << 6 | TH << 10 | TCC << 14``.

    The TEXA fields above bit 14 are zero for an indexed texture: PCSX2 only
    records them for a direct-colour format, and a Madden 09 ``MMAP`` surface
    is never one.
    """

    _require(0 <= psm < 64 and 0 <= tw < 16 and 0 <= th < 16 and tcc in (0, 1),
             f"psm {psm}, tw {tw}, th {th}, tcc {tcc} do not fit PCSX2's 6/4/4/1-bit fields.")
    return (psm & 0x3F) | (tw << 6) | (th << 10) | (tcc << 14)


def replacement_name(tex0: int, clut: Optional[int], bits: int, *,
                     region: Optional[Tuple[int, int]] = None,
                     mip: Optional[int] = None) -> str:
    """The filename PCSX2 looks for: hashes unpadded (``%llx``), ``bits`` eight digits."""

    parts = ["%x" % tex0]
    if clut is not None:
        parts.append("%x" % clut)
    if region is not None:
        parts.append("r%ux%u" % (int(region[0]), int(region[1])))
    parts.append("%08x" % bits)
    suffix = "-mip%u" % mip if mip else ""
    return "-".join(parts) + suffix + ".png"


_NAME = re.compile(
    r"^(?P<tex0>[0-9a-f]{1,16})(?:-(?P<clut>[0-9a-f]{1,16}))?"
    r"(?:-r(?P<rw>\d+)x(?P<rh>\d+))?"
    r"-(?P<bits>[0-9a-f]{8})(?:-mip(?P<mip>\d+))?\.png$"
)


@dataclass(frozen=True)
class ParsedName:
    """One PCSX2 filename, taken apart."""

    tex0: int
    clut: Optional[int]
    bits: int
    region: Optional[Tuple[int, int]]
    mip: Optional[int]

    @property
    def psm(self) -> int:
        return self.bits & 0x3F

    @property
    def tw(self) -> int:
        return (self.bits >> 6) & 0xF

    @property
    def th(self) -> int:
        return (self.bits >> 10) & 0xF

    @property
    def tcc(self) -> int:
        return (self.bits >> 14) & 1

    @property
    def width(self) -> int:
        return self.region[0] if self.region and self.region[0] else 1 << self.tw

    @property
    def height(self) -> int:
        return self.region[1] if self.region and self.region[1] else 1 << self.th


def parse_name(name: str) -> ParsedName:
    """Take a dumped or derived filename apart, or refuse one PCSX2 would never write.

    A palette-less name (``<tex0>-<bits>.png``) is accepted too: PCSX2 writes
    it for a direct-colour texture, and a parser that refused it would call a
    real dump ungrammatical.
    """

    match = _NAME.match(name)
    _require(match is not None,
             f"{name!r} is not a PCSX2 texture name: one is "
             f"<tex0>[-<clut>][-r<W>x<H>]-<bits>[-mipN].png.")
    assert match is not None
    clut = match.group("clut")
    return ParsedName(
        tex0=int(match.group("tex0"), 16),
        clut=int(clut, 16) if clut is not None else None,
        bits=int(match.group("bits"), 16),
        region=((int(match.group("rw")), int(match.group("rh"))) if match.group("rw") else None),
        mip=int(match.group("mip")) if match.group("mip") else None,
    )


@dataclass(frozen=True)
class DerivedName:
    """One name a texture would be looked up under, and the draw it belongs to."""

    name: str
    convention: str
    base_level: int
    level_count: int
    tcc: int
    tex0: int
    clut: int
    #: Which GS pixel mode the draw this name belongs to used.  A texture the
    #: game uploads as a high-byte surface has a different ``bits`` word *and*
    #: a different TEX0 hash, so it is a separate name for the same pixels.
    psm: int = PSMT8


def derive_names(levels: Sequence[TextureLevel],
                 palette: Sequence[Tuple[int, int, int, int]],
                 *, extra_psms: Sequence[int] = ()) -> Tuple[DerivedName, ...]:
    """Every name PCSX2 would look this texture up under, from its own bytes.

    One name per ``(base level, level count)`` chain and per convention:
    ``modern`` once, ``classic`` with TCC clear and set.  The modern name and
    the classic TCC-clear name are the same string; both are listed so a caller
    can pick by convention without knowing that.  The first entry is the one a
    single-answer caller wants: the full chain from the base level, modern.

    *extra_psms* adds the names a **second GS mode** would be looked up under.
    Which mode a game uploads an indexed texture in is the game's choice and no
    disc byte records it, so a caller whose dump has shown both asks for both
    rather than picking one: an 8-bit texture drawn as ``PSMT8H`` has neither
    the same ``bits`` word nor the same TEX0 hash as the same texture drawn as
    ``PSMT8``.  Default is empty, so nothing changes for a caller that has not
    measured a second mode.
    """

    _require(len(levels) > 0, "a texture name needs at least one level.")
    for number, level in enumerate(levels[1:], start=1):
        previous = levels[number - 1]
        _require(level.width * 2 == previous.width and level.height * 2 == previous.height,
                 f"level {number} is {level.width}x{level.height} after a "
                 f"{previous.width}x{previous.height} level; a mip chain halves each step.")
        _require(level.bits == previous.bits,
                 f"level {number} is {level.bits}-bit after a {previous.bits}-bit level; a "
                 f"chain keeps one format.")
    clut = clut_hash(palette)
    _require(len(palette) == (256 if levels[0].bits == 8 else 16),
             f"a {levels[0].bits}-bit texture draws from a "
             f"{256 if levels[0].bits == 8 else 16}-entry CLUT and this palette has "
             f"{len(palette)} entries.")
    modes: List[Optional[int]] = [None]
    for psm in extra_psms:
        _require(BITS_FOR_PSM.get(psm) == levels[0].bits,
                 f"PSM {psm} does not carry a {levels[0].bits}-bit index, so it is not a mode "
                 f"this texture could be drawn in.")
        if psm != levels[0].psm and psm not in modes:
            modes.append(psm)
    out: List[DerivedName] = []
    for mode in modes:
        chains = tex0_hash_chains(levels, psm=mode)
        order = sorted(chains, key=lambda key: (key[0], -key[1]))
        for base, count in order:
            level = levels[base]
            psm = level.psm if mode is None else mode
            tw, th = log2_exact(level.width), log2_exact(level.height)
            tex0 = chains[(base, count)]
            out.append(DerivedName(replacement_name(tex0, clut, texture_bits(psm, tw, th, 0)),
                                   CONVENTION_MODERN, base, count, 0, tex0, clut, psm))
        for base, count in order:
            level = levels[base]
            psm = level.psm if mode is None else mode
            tw, th = log2_exact(level.width), log2_exact(level.height)
            tex0 = chains[(base, count)]
            for tcc in (0, 1):
                out.append(DerivedName(
                    replacement_name(tex0, clut, texture_bits(psm, tw, th, tcc)),
                    CONVENTION_CLASSIC, base, count, tcc, tex0, clut, psm))
    return tuple(out)


def names_by_convention(derived: Iterable[DerivedName]) -> Dict[str, List[str]]:
    """``convention -> [names]`` in the order :func:`derive_names` produced them."""

    out: Dict[str, List[str]] = {}
    for item in derived:
        bucket = out.setdefault(item.convention, [])
        if item.name not in bucket:
            bucket.append(item.name)
    return out

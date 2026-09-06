"""EA ``SHPS`` — the image bank every EA BIG-based PS2 disc keeps art in.

``SHPS`` is EA's ``FSH`` "shape" bank as the PlayStation 2 titles write it: a
directory of **named** images, each of which is a short chain of blocks — the
pixels first, then the palette, then whatever metadata the artist's tool
attached.  MVP Baseball 2005 stores 16,355 of these banks inside its 211 EA
BIG archives; the EA Nation dashboard on every Madden and NCAA Football PS2
disc carries 37 more [M].  Uniforms, portraits, stadium art, menu art and
every logo on those discs arrive through this file.

The shape, and the two things a first reading gets wrong
--------------------------------------------------------

```
+0x00  "SHPS"                 (also ShpS / SHPI / SHPM / SHPP / SHPX)
+0x04  u32   declared size    the whole bank, and it matches [M]
+0x08  u32   image count
+0x0C  4 chars directory id   "G359" on MVP, "G355" on the Tiburon
                              dashboard banks; little-endian on both [M]
+0x10  count x { 4-char tag; u32 offset }     offsets from the bank's start

each block, at one of those offsets and chained from it:
+0x00  u8    code             what the block holds
+0x01  u24   size             this block only; 0 ends the chain
+0x04  u16   width
+0x06  u16   height
+0x08  u16 x 4                misc; zero in every pixel block measured [M]
+0x10  payload
```

1. **The block ``size`` covers the block, not the image.** An image's pixels,
   its palette and its metadata are separate blocks laid end to end, each with
   its own 16-byte header, and only the first is reached from the directory.
   A reader that treats the directory offset as "header then pixels then the
   next image" finds the palette where it expects the next texture.
2. **The last block in a chain declares size 0.** Walking by ``size`` alone
   loops forever on it; the chain ends there, and the bytes of that final
   block run to the next directory offset (or to the end of the bank).

The codes, as measured
----------------------

Every code below was confirmed by arithmetic rather than by a table: a pixel
block declares ``width``, ``height`` and a byte count, so
``(size - 16) / (width * height)`` says how many bytes a pixel takes, and a
palette block declares its entry count as its ``width``.  Codes this module
has not seen are **refused by name**, with their measured bytes-per-pixel in
the sentence, because "this reader cannot open it" and "there is nothing
there" must not render the same.

| code | block | measured, over 22,883 images of a 4,065-bank MVP sample [M] |
|---|---|---|
| ``0x02`` | 8-bit indexed pixels | 19,697 images, exactly 1.000 byte per pixel — except 265 whose payload is about four thirds of that, which is a whole mip chain, and 1 with a little padding |
| ``0x05`` | direct 32-bit RGBA pixels | 402 images, exactly 4.000 bytes per pixel, and **no palette block follows any of them**; every one of them is in the logo bank |
| ``0x21`` | 32-bit RGBA palette | 28,014 blocks, ``size == 16 + 4 * width``; ``width`` is 256 in all but a couple of thousand |
| ``0x0E`` | **refused** | 7,996 images, exactly 6 bytes per 4x4 block with a 256-entry palette — a fixed-rate compressed codec, see below |
| ``0x01`` | **refused** | 321 images, every one of them 1x1 with a 16-byte payload and a two-entry palette |
| ``0x69`` ``0x6F`` ``0x70`` ``0x7C`` | metadata / text attachments | 52,281 blocks, carried and never decoded |

## What is refused, and why that is not the same as empty

**Code ``0x0E`` is the disc's second art codec, and it is compressed.**  It is
not a corner case: it is every uniform, every portrait, every head texture,
every loading screen, all of the field art and the ballpark-builder art, and
about a fifth of the ballpark and model textures.  Three measurements settle
what it is and what it is not [M]:

* its rate is **exactly 6 bytes per 4x4 block of pixels** -- 0.375 bytes per
  pixel -- for all 7,996 images at every size from 64x64 to 1024x256, with no
  exception.  A variable-rate compressor cannot produce an exact constant
  ratio, so this is a fixed-rate codec;
* its bytes are **near-uniform at every position mod 6, 8 and 12** (mean about
  140, over 230 distinct values per column in a 1,024-sample image).  A plain
  indexed bitmap uses a subset of its palette and looks nothing like that, and
  a fixed-rate block codec with packed endpoints and selectors looks exactly
  like that;
* consequently the two re-readings that produce the right *number* of bytes --
  8-bit indexed at three eighths of the declared height, and 4-bit indexed at
  three quarters of it, in both nibble orders -- give the right colours and no
  coherent image [M].

So no rearrangement of these bits will ever decode them; decoding needs the
codec, which lives in the executable.  The reader names the code, quotes the
measurement, and hands back nothing.

**Code ``0x01``** is 321 one-pixel stubs.  A 16-byte payload for one pixel
proves only that a block has a minimum size; nothing about a real row layout
can be read off it, so it is refused rather than assumed to be 4-bit indexed.

## The palette's ``width`` is the entry count, and its payload is padded

Most palettes hold 256 entries, but 2,000-odd images on MVP carry a shorter
one, and those blocks' payloads are **rounded up** — a palette that declares
122 entries carries 124, one that declares 17 carries 24 [M].  The declared
width is the authority: across every short-palette image measured, the
largest pixel index in the image is *below* the declared width and never
reaches the padding (declared 122 / highest index 121, declared 80 / 79,
declared 17 / 16, declared 16 / 15) [M].  A reader that took the entry count
from the payload length instead would build a palette with junk on the end;
it would not show, and it would be wrong.

Palette alpha is EA's PlayStation 2 scale: **``0x80`` is fully opaque**, not
``0xFF`` [M]. :func:`decode_rgba` widens it to 0..255 unless asked for the raw
form, exactly as the ``MMAP`` decoder on the Madden side does — the two
formats are different wrappers over the same GS conventions.

The CSM1 interleave applies at **exactly 256 entries** and nowhere else [M].

Retail-free
-----------
Constants, offsets and refusal sentences only.  No pixel, no palette entry and
no bank name from any game appears in this file.

Standard library only; importable without Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

from mod_editor.games.contract import Refusal

#: Every spelling of the magic this family uses.  ``SHPS`` is what the PS2
#: discs measured here carry; the others are the same directory shape under
#: other EA tool versions and are accepted so a bank is never refused for its
#: spelling alone.
SHPS_MAGICS: Tuple[bytes, ...] = (b"SHPS", b"ShpS", b"SHPI", b"SHPM", b"SHPP",
                                  b"SHPX")

#: magic, u32 size, u32 image count, 4-char directory id.
SHPS_HEADER_SIZE = 16

#: One directory row: a 4-character tag and a u32 offset.
SHPS_ROW_SIZE = 8

#: Every block — pixels, palette or attachment — carries this header.
BLOCK_HEADER_SIZE = 16

#: A sanity bound on the image count, so a wrong-endian read is refused rather
#: than allocated for.  It is far above the largest bank measured [M].
MAX_IMAGES = 4096

#: 8-bit indexed pixels, one byte per pixel, palette in an attached block.
CODE_INDEXED8 = 0x02

#: Direct 32-bit RGBA pixels, four bytes per pixel, no palette block.
CODE_RGBA32 = 0x05

#: A 32-bit RGBA palette: ``width`` entries of four bytes.
CODE_PALETTE32 = 0x21

#: Blocks that carry text or tool metadata.  They are listed and their bytes
#: are available; nothing here interprets them.
CODE_ATTACHMENTS: Tuple[int, ...] = (0x69, 0x6F, 0x70, 0x7C)

#: Human names for the codes this module knows.  A code outside it is refused
#: by number, never silently treated as one of these.
CODE_NAMES: Dict[int, str] = {
    0x01: "1x1 stub",
    CODE_INDEXED8: "8-bit indexed",
    CODE_RGBA32: "32-bit RGBA",
    0x0E: "undecoded, 3 bits per pixel",
    CODE_PALETTE32: "32-bit RGBA palette",
    0x69: "attachment",
    0x6F: "text attachment",
    0x70: "text attachment",
    0x7C: "attachment",
}

#: What is known about the pixel codes this module refuses.  A refusal quotes
#: the note, so the next person starts from the measurement rather than from
#: "unsupported".
CODE_NOTES: Dict[int, str] = {
    0x01: ("every one of the 321 code-0x01 images measured is 1x1 with a "
           "16-byte payload and a two-entry palette, so nothing about its "
           "row layout has been proved and it is not guessed at"),
    0x0E: ("all 7,996 code-0x0e images measured carry exactly 6 bytes per 4x4 "
           "block of pixels at every size, and their bytes are near-uniform at "
           "every position mod 6, 8 and 12, which is a fixed-rate compressed "
           "codec rather than a bit-packed bitmap; no reinterpretation of the "
           "bits can decode it"),
}

#: Bytes per pixel for each pixel code this module decodes.
PIXEL_BYTES: Dict[int, int] = {CODE_INDEXED8: 1, CODE_RGBA32: 4}

#: Bytes per entry for each palette code this module decodes.
PALETTE_BYTES: Dict[int, int] = {CODE_PALETTE32: 4}

#: What the PlayStation 2 GS calls a fully opaque alpha in a 32-bit CLUT
#: entry.  Half of 255, not 255.
PS2_ALPHA_OPAQUE = 0x80

#: Palettes of exactly this many entries are stored in the GS's CSM1 order.
CSM1_ENTRIES = 256


class ShpsError(Refusal):
    """A bank could not be read; the message says what was wrong."""


class UnsupportedBlock(ShpsError):
    """A block shape this module deliberately does not decode."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise ShpsError(message)


def looks_like_shps(head: "bytes | memoryview") -> bool:
    """Does *head* begin an ``SHPS`` bank?  Magic only; no integers read."""
    return bytes(head[:4]) in SHPS_MAGICS


# --------------------------------------------------------------------------
# The bank
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Block:
    """One link of an image's block chain."""

    offset: int
    code: int
    #: What the block's own header declares.  **Zero on the last block of a
    #: chain**, where :attr:`bytes_available` is what there actually is.
    declared_size: int
    width: int
    height: int
    misc: Tuple[int, int, int, int]
    #: How many bytes lie between this block and whatever follows it.
    bytes_available: int

    @property
    def name(self) -> str:
        return CODE_NAMES.get(self.code, "code 0x%02x" % self.code)

    @property
    def is_pixels(self) -> bool:
        return self.code in PIXEL_BYTES

    @property
    def is_palette(self) -> bool:
        return self.code in PALETTE_BYTES

    @property
    def payload_bytes(self) -> int:
        size = self.declared_size or self.bytes_available
        return max(size - BLOCK_HEADER_SIZE, 0)

    def bytes_per_pixel(self) -> Optional[float]:
        """``(size - 16) / (width * height)``, or ``None`` when undefined.

        This is the measurement that names an unknown code: a block whose
        arithmetic gives exactly 1, 2 or 4 is a pixel block of that depth, and
        the number goes into the refusal so the next person does not have to
        re-derive it.
        """
        pixels = self.width * self.height
        if pixels <= 0:
            return None
        return self.payload_bytes / pixels


@dataclass(frozen=True)
class ShpsImage:
    """One directory entry: its tag, and the chain of blocks it starts."""

    index: int
    tag: str
    offset: int
    blocks: Tuple[Block, ...]

    @property
    def pixels(self) -> Optional[Block]:
        for block in self.blocks:
            if block.is_pixels:
                return block
        return None

    @property
    def palette(self) -> Optional[Block]:
        for block in self.blocks:
            if block.is_palette:
                return block
        return None

    @property
    def width(self) -> int:
        block = self.pixels or (self.blocks[0] if self.blocks else None)
        return block.width if block else 0

    @property
    def height(self) -> int:
        block = self.pixels or (self.blocks[0] if self.blocks else None)
        return block.height if block else 0

    @property
    def code(self) -> int:
        return self.blocks[0].code if self.blocks else -1

    @property
    def decodable(self) -> bool:
        pixels = self.pixels
        if pixels is None:
            return False
        if pixels.code == CODE_INDEXED8:
            return self.palette is not None
        return True

    @property
    def mip_bytes(self) -> int:
        """How many bytes the pixel block carries past its first level.

        A block whose payload is about four thirds of ``width * height *
        depth`` carries the whole mip chain, because the chain below level 0
        sums to a third of it.  255 of the 16,786 code-0x02 images measured
        do; the rest carry level 0 alone.  Level 0 is what is decoded either
        way, and this says whether there was more.
        """
        pixels = self.pixels
        if pixels is None or pixels.code not in PIXEL_BYTES:
            return 0
        level0 = pixels.width * pixels.height * PIXEL_BYTES[pixels.code]
        return max(pixels.payload_bytes - level0, 0)


class ShpsBank:
    """A parsed ``SHPS`` image bank.  Reads; never mutates its input."""

    def __init__(self, payload: "bytes | memoryview",
                 name: str = "this bank") -> None:
        data = bytes(payload)
        self.name = name
        self.data = data
        _require(
            len(data) >= SHPS_HEADER_SIZE,
            "%s is %d byte(s); an SHPS header alone is %d."
            % (name, len(data), SHPS_HEADER_SIZE),
        )
        magic = data[:4]
        _require(
            magic in SHPS_MAGICS,
            "%s starts with %r, which is not an SHPS bank. If it came out of "
            "an EA BIG archive, decompress the entry first: a RefPack-packed "
            "entry's stored bytes never carry its format's magic."
            % (name, magic),
        )
        self.magic = magic.decode("ascii")
        size_le, count_le = struct.unpack_from("<II", data, 4)
        size_be, count_be = struct.unpack_from(">II", data, 4)
        if self._plausible(count_le, size_le, len(data)):
            self.endian, self.declared_size, count = "little", size_le, count_le
        elif self._plausible(count_be, size_be, len(data)):
            self.endian, self.declared_size, count = "big", size_be, count_be
        else:
            raise ShpsError(
                "%s declares %d images little-endian and %d big-endian, and "
                "neither directory fits its %d bytes; this is not a bank this "
                "reader can walk." % (name, count_le, count_be, len(data))
            )
        self._order = "<" if self.endian == "little" else ">"
        self.image_count = count
        self.size_mismatch = self.declared_size - len(data)
        self.directory_id = data[12:16].decode("latin-1")
        offsets: List[Tuple[str, int]] = []
        for index in range(count):
            row = SHPS_HEADER_SIZE + SHPS_ROW_SIZE * index
            tag = data[row:row + 4].decode("latin-1").rstrip("\x00 ")
            offset, = struct.unpack_from(self._order + "I", data, row + 4)
            offsets.append((tag, offset))
        #: Where each image's chain has to stop: the next directory offset in
        #: **address** order, which is not always table order.
        bounds = sorted({offset for _tag, offset in offsets} | {len(data)})
        images: List[ShpsImage] = []
        for index, (tag, offset) in enumerate(offsets):
            limit = next((edge for edge in bounds if edge > offset), len(data))
            images.append(ShpsImage(index, tag, offset,
                                    tuple(self._walk(offset, limit, index))))
        self.images: Tuple[ShpsImage, ...] = tuple(images)

    @staticmethod
    def _plausible(count: int, size: int, length: int) -> bool:
        return (0 < count <= MAX_IMAGES
                and SHPS_HEADER_SIZE + SHPS_ROW_SIZE * count <= max(size, length))

    def _walk(self, offset: int, limit: int, index: int) -> Iterator[Block]:
        data = self.data
        position = offset
        seen = 0
        while position + BLOCK_HEADER_SIZE <= min(limit, len(data)):
            code = data[position]
            declared = int.from_bytes(
                data[position + 1:position + 4],
                "little" if self.endian == "little" else "big")
            width, height = struct.unpack_from(self._order + "HH", data,
                                               position + 4)
            misc = struct.unpack_from(self._order + "HHHH", data, position + 8)
            available = min(limit, len(data)) - position
            yield Block(position, code, declared, width, height, misc, available)
            if declared <= 0:
                return
            position += declared
            seen += 1
            _require(
                seen <= 64,
                "%s: image %d chains more than 64 blocks, which no measured "
                "bank does; the bank is damaged." % (self.name, index),
            )

    def __len__(self) -> int:
        return len(self.images)

    def __iter__(self) -> Iterator[ShpsImage]:
        return iter(self.images)

    def image(self, index: int) -> ShpsImage:
        if not 0 <= index < len(self.images):
            raise ShpsError(
                "image %d does not exist: %s has %d (0..%d)."
                % (index, self.name, len(self.images), len(self.images) - 1)
            )
        return self.images[index]

    def block_bytes(self, block: Block) -> bytes:
        """One block's payload, without its 16-byte header."""
        start = block.offset + BLOCK_HEADER_SIZE
        return self.data[start:start + block.payload_bytes]

    def undecodable_reason(self, index: int) -> Optional[str]:
        """Why image *index* cannot be decoded, or ``None`` when it can.

        One sentence, naming the code and what the block's own arithmetic says
        about it, so a census can quote the refusal instead of inventing one.
        """
        image = self.image(index)
        if not image.blocks:
            return ("image %d (%r) has no block at its directory offset +%d."
                    % (index, image.tag, image.offset))
        first = image.blocks[0]
        if not first.is_pixels:
            depth = first.bytes_per_pixel()
            note = CODE_NOTES.get(first.code)
            return ("image %d (%r) starts with block code 0x%02x, which this "
                    "reader does not decode; the block declares %dx%d in %d "
                    "byte(s), which is %s byte(s) per pixel%s."
                    % (index, image.tag, first.code, first.width, first.height,
                       first.payload_bytes,
                       "undefined" if depth is None else ("%.3f" % depth),
                       (" -- " + note) if note else ""))
        if first.code == CODE_RGBA32 and image.palette is not None:
            return ("image %d (%r) is direct 32-bit RGBA and carries a palette "
                    "block as well; no measured image does, so which one the "
                    "game reads is unknown." % (index, image.tag))
        if first.code == CODE_INDEXED8 and image.palette is None:
            codes = ", ".join("0x%02x" % block.code for block in image.blocks[1:])
            return ("image %d (%r) is 8-bit indexed and no palette block "
                    "follows it; the blocks after the pixels are %s."
                    % (index, image.tag, codes or "(none)"))
        expected = first.width * first.height * PIXEL_BYTES[first.code]
        if first.payload_bytes < expected:
            return ("image %d (%r) declares %dx%d, which needs %d byte(s), and "
                    "its block holds %d."
                    % (index, image.tag, first.width, first.height, expected,
                       first.payload_bytes))
        return None

    # -- census ------------------------------------------------------------

    def code_histogram(self) -> Dict[str, int]:
        """``{"0x02": n, ...}`` over every block of every image."""
        counts: Dict[str, int] = {}
        for image in self.images:
            for block in image.blocks:
                key = "0x%02x" % block.code
                counts[key] = counts.get(key, 0) + 1
        return counts

    def summary(self) -> Dict[str, object]:
        """Counts and shapes, with no pixel in it."""
        return {
            "name": self.name,
            "magic": self.magic,
            "endian": self.endian,
            "declared_size": self.declared_size,
            "length": len(self.data),
            "size_mismatch": self.size_mismatch,
            "directory_id": self.directory_id,
            "images": len(self.images),
            "codes": self.code_histogram(),
            "decodable": sum(1 for image in self.images if image.decodable),
        }


def parse(payload: "bytes | memoryview", name: str = "this bank") -> ShpsBank:
    """Parse a decompressed ``SHPS`` bank, or refuse with a sentence."""
    return ShpsBank(payload, name=name)


# --------------------------------------------------------------------------
# Pixels
# --------------------------------------------------------------------------

def deinterleave_csm1(entries: Sequence[Tuple[int, int, int, int]]
                      ) -> List[Tuple[int, int, int, int]]:
    """Undo the PlayStation 2 GS's CSM1 CLUT order for a 256-entry palette.

    Within every block of 32 entries the second group of 8 and the third group
    of 8 are swapped.  The GS stores a 256-entry CLUT that way; a palette read
    straight out of the file and used as-is produces an image that is
    recognisable and speckled with wrong colours, which is how the order was
    confirmed here.

    A palette of any other length is stored in order and must not be touched.
    """
    out = list(entries)
    for index in range(len(entries)):
        if (index & 0x18) == 0x08:
            out[index] = entries[index + 8]
        elif (index & 0x18) == 0x10:
            out[index] = entries[index - 8]
    return out


def _scale_alpha(value: int) -> int:
    return 255 if value >= PS2_ALPHA_OPAQUE else value * 255 // PS2_ALPHA_OPAQUE


def read_palette(bank: ShpsBank, block: Block, *, raw_alpha: bool = False
                 ) -> List[Tuple[int, int, int, int]]:
    """A palette block's entries as ``(r, g, b, a)``.

    A 256-entry palette is CSM1-deinterleaved; any other length is read in
    order.  Alpha is widened from the GS's 0..128 to 0..255 unless
    *raw_alpha* asks for the stored value — which is the form a PCSX2 texture
    dump carries, so a matcher pairing a dump with a bank asks for it.
    """
    if block.code not in PALETTE_BYTES:
        raise UnsupportedBlock(
            "block code 0x%02x is not a palette this reader knows; it knows %s."
            % (block.code, ", ".join("0x%02x" % code for code in PALETTE_BYTES))
        )
    stride = PALETTE_BYTES[block.code]
    payload = bank.block_bytes(block)
    count = block.width or (len(payload) // stride)
    _require(
        len(payload) >= count * stride,
        "%s: a %d-entry palette needs %d byte(s) and the block holds %d."
        % (bank.name, count, count * stride, len(payload)),
    )
    entries: List[Tuple[int, int, int, int]] = []
    for index in range(count):
        red, green, blue, alpha = payload[index * stride:index * stride + 4]
        entries.append((red, green, blue,
                        alpha if raw_alpha else _scale_alpha(alpha)))
    if count == CSM1_ENTRIES:
        entries = deinterleave_csm1(entries)
    return entries


def decode_rgba(bank: ShpsBank, index: int = 0, *, raw_alpha: bool = False,
                palette: Optional[int] = None) -> Tuple[int, int, bytes]:
    """One image, as ``(width, height, RGBA bytes)``.

    *palette* picks one of the image's palette blocks by position among its
    palettes; the default is the first, which is the only one every measured
    image has.  An image this reader cannot decode raises with the sentence
    :meth:`ShpsBank.undecodable_reason` gives — never a blank bitmap.
    """
    reason = bank.undecodable_reason(index)
    if reason is not None:
        raise UnsupportedBlock("%s: %s" % (bank.name, reason))
    image = bank.image(index)
    pixels = image.pixels
    assert pixels is not None  # undecodable_reason has already checked
    payload = bank.block_bytes(pixels)
    width, height = pixels.width, pixels.height
    if pixels.code == CODE_INDEXED8:
        palettes = [block for block in image.blocks if block.is_palette]
        chosen = palettes[palette or 0]
        clut = read_palette(bank, chosen, raw_alpha=raw_alpha)
        _require(
            bool(clut),
            "%s: image %d has an empty palette." % (bank.name, index),
        )
        count = width * height
        plane = payload[:count]
        # One byte-translation per channel beats a Python loop per pixel by
        # two orders of magnitude, and a whole-disc census decodes tens of
        # millions of pixels.  An index past the end of a short palette maps
        # to transparent black rather than raising: a short CLUT is the
        # image's problem, not the reader's.
        tables = [bytes(bytearray(
            (clut[value][channel] if value < len(clut) else 0)
            for value in range(256))) for channel in range(4)]
        out = bytearray(count * 4)
        for channel in range(4):
            out[channel::4] = plane.translate(tables[channel])
        return width, height, bytes(out)
    if pixels.code == CODE_RGBA32:
        count = width * height
        plane = payload[:count * 4]
        if raw_alpha:
            return width, height, bytes(plane)
        scale = bytes(bytearray(_scale_alpha(value) for value in range(256)))
        out = bytearray(plane)
        out[3::4] = plane[3::4].translate(scale)
        return width, height, bytes(out)
    raise UnsupportedBlock(
        "%s: image %d uses pixel code 0x%02x, which this reader lists and "
        "does not decode." % (bank.name, index, pixels.code)
    )


def encode_png(width: int, height: int, rgba: bytes) -> bytes:
    """RGBA bytes as a PNG file, with the standard library only.

    Pillow is not a dependency of a format package: a caller that has it may
    use it, and one that does not still gets a file it can open.
    """
    import binascii
    import zlib

    _require(
        len(rgba) == width * height * 4,
        "a %dx%d RGBA image is %d byte(s) and %d were given."
        % (width, height, width * height * 4, len(rgba)),
    )
    raw = bytearray()
    for row in range(height):
        raw.append(0)  # filter type 0
        start = row * width * 4
        raw += rgba[start:start + width * 4]

    def chunk(tag: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + tag + body
                + struct.pack(">I", binascii.crc32(tag + body) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
            + chunk(b"IEND", b""))


__all__ = [
    "BLOCK_HEADER_SIZE",
    "CODE_ATTACHMENTS",
    "CODE_INDEXED8",
    "CODE_NAMES",
    "CODE_NOTES",
    "CODE_PALETTE32",
    "CODE_RGBA32",
    "CSM1_ENTRIES",
    "MAX_IMAGES",
    "PALETTE_BYTES",
    "PIXEL_BYTES",
    "PS2_ALPHA_OPAQUE",
    "SHPS_HEADER_SIZE",
    "SHPS_MAGICS",
    "SHPS_ROW_SIZE",
    "Block",
    "ShpsBank",
    "ShpsError",
    "ShpsImage",
    "UnsupportedBlock",
    "decode_rgba",
    "deinterleave_csm1",
    "encode_png",
    "looks_like_shps",
    "parse",
    "read_palette",
]

"""EA Tiburon's PS2 on-disc container (``TERF``), shared by every EA game module.

Every large ``/DATA/*.DAT`` on a Madden or NCAA Football PS2 disc is one of
these: a four-chunk file holding a flat, indexed list of members.  Madden NFL
09's rosters, uniform art, stadium geometry, playbooks and speech banks all
arrive through it, so a module that reads this file reads the disc.

Provenance
----------
The container's shape was re-measured for this module against the retail
Madden NFL 09 (USA) disc (read-only, 107 containers, 47,769 members).  The two
member codecs are **re-expressed from the owner's** ``nfl-online-revival``
tools -- ``tools/lzh1.py`` (the ``LZH1`` and ``RLE1`` decoders, themselves
reversed from the Madden NFL 2004 and NCAA Football 2004 PS2 executables) and
``tools/madden_tdb.py`` (the container walk).  That repository ships no
licence, so nothing here is copied from it: the algorithms below are written
fresh from the documented grammar, and the equivalences that let them be
written more directly than the originals are noted where they are used.

What is measured, and what is not
---------------------------------
Measured on the retail disc, zero counter-examples across 107 containers:

* ``headerSize == max(16, alignment)``, where *alignment* is the ``u16`` at
  ``0x0C``;
* the ``DIR1`` and ``COMP`` chunks are each ``roundup(8 + 8 * count,
  alignment)`` bytes;
* the ``DATA`` chunk's declared size runs to exactly end-of-file;
* member offsets are relative to the offset of the ``DATA`` **tag** -- not to
  the start of its payload.  The natural reading is off by the 8-byte chunk
  header and corrupts every member;
* members are laid out in table order at ``alignment``-aligned offsets, and an
  **empty member still consumes one alignment unit**, so the next offset is
  ``roundup(off + max(size, 1), alignment)``.  323 of Madden 09's members are
  empty; a writer that packs them at zero width relocates everything after
  them;
* every inter-member gap (24,800 of them) and every file tail is zero-filled,
  and the file length is a whole number of alignment units.

Not established here, and refused rather than guessed: the meaning of the
version word ``02 02 00 05``; whether any checksum covers a container (no
field in the header, the directory or the chunk headers varies with content in
a way this module could find, and **the negative is only as good as that
search** -- nothing here has run a modified container through the game); and
codecs 2 (``HUFF``), 3 (``LZM1``) and 4 (``IPU1``), which the engine registers
and no member of any disc in this project's reach uses.

Standard library only; importable without Qt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import mmap
import struct
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from mod_editor.games.contract import Refusal

TERF_MAGIC = b"TERF"
DIR1_MAGIC = b"DIR1"
COMP_MAGIC = b"COMP"
DATA_MAGIC = b"DATA"
HSH1_MAGIC = b"HSH1"

#: Bytes 8..12 of the ``TERF`` chunk in every container measured.  Its meaning
#: is unknown; it is checked rather than interpreted.
VERSION_WORD = b"\x02\x02\x00\x05"

#: The chunk header both chunk kinds share: a 4-char tag and a total size.
CHUNK_HEADER_SIZE = 8

#: The smallest ``TERF`` header measured.  A container's header is
#: ``max(MIN_HEADER_SIZE, alignment)`` bytes, with no counter-example across
#: the 107 containers of the Madden 09 disc.
MIN_HEADER_SIZE = 16

#: The member-data alignment used by every Madden 09 container that carries a
#: database, a texture or geometry.  Other values seen on the same disc: 4
#: (the ``CAFE*``/``STRY*`` family), 16 (``SPCHFEDT``) and 2048 (``BGM``,
#: ``SOUNDDAT``, ``PLYRFACE``, ``COACFACE``).  It is read from the file, never
#: assumed; this constant is only the default a synthetic build uses.
DEFAULT_ALIGNMENT = 0x40

CODEC_STORED = 0
CODEC_RLE1 = 1
CODEC_HUFF = 2
CODEC_LZM1 = 3
CODEC_IPU1 = 4
CODEC_LZH1 = 5

#: EA's registered codec ids.  Ids and names come from the ``register_codec``
#: run present in every EA Tiburon PS2 executable in the owner's corpus.
CODEC_NAMES: Mapping[int, str] = {
    CODEC_STORED: "NONE (stored)",
    CODEC_RLE1: "RLE1",
    CODEC_HUFF: "HUFF",
    CODEC_LZM1: "LZM1",
    CODEC_IPU1: "IPU1",
    CODEC_LZH1: "LZH1",
}

#: The codecs this module can decode.  A member using any other one is refused
#: by name: "this reader cannot open it" and "there is nothing there" are
#: different answers and must not render the same.
CODECS_DECODED = (CODEC_STORED, CODEC_RLE1, CODEC_LZH1)

#: The codecs this module can *write*.  ``LZH1`` is decode-only: no encoder for
#: it exists in this project or in the owner's, so a COMP writer stores or
#: run-length-encodes instead.  Retail precedent for storing: Madden 09 ships
#: 270 of ``UNIFORMS.DAT``'s 725 members and 689 of ``STADIUMS.DAT``'s 1,355
#: as codec 0 *inside a COMP container*, so a stored member there is a shape
#: the shipped game already loads.
CODECS_ENCODED = (CODEC_STORED, CODEC_RLE1)


class TerfError(Refusal):
    """A container, member or stream is not what it claims.  One sentence."""


class TruncatedStream(TerfError):
    """A compressed stream ended mid-symbol.

    This is a refusal, never a short result.  A Huffman decoder fed zeros past
    the end of its input keeps emitting plausible symbols, so a reader that
    pads silently hands back bytes that look whole and are not.
    """


class Rle1Error(TerfError):
    """An ``RLE1`` stream is malformed, or decoded to the wrong length."""


class UnsupportedCodec(TerfError):
    """A member uses a codec this module does not implement."""


# --------------------------------------------------------------------------
# LZH1 (codec 5)
# --------------------------------------------------------------------------
#
# The grammar, as documented by the owner's reversing of Madden NFL 2004's
# codec descriptor 5: deflate's symbol alphabet with MSB-first bit packing and
# a trivially stored code-length table -- no code-length-code layer.
#
#   loop:
#     1 bit  -- 1 => end of stream (32 further bits follow and are ignored)
#     285 x 4 bits : code lengths for the literal/length alphabet (0..284)
#      30 x 4 bits : code lengths for the distance alphabet (0..29)
#     symbols until 256 (end of block), then loop
#
# Two simplifications, each provably equivalent to the reference decoder rather
# than a guess at it:
#
# * the reference special-cases length symbols with index < 8 and those with
#   zero extra bits.  For every index the alphabet can produce (0..27, since
#   the alphabet has 285 symbols) those branches compute exactly
#   ``LEN_BASE[i] + extra``, so the plain deflate formula is used.  Index 28
#   is unreachable and is refused rather than silently accepted.
# * the reference copies matches through a 32 KiB circular window.  That
#   window is by construction the last 32,768 bytes of output, so the copy is
#   taken from the output buffer directly; a distance reaching past the start
#   of the stream lands on window bytes never written, which are zero, and is
#   reproduced as zeros.

_LEN_BASE = (3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43,
             51, 59, 67, 83, 99, 115, 131, 163, 195, 227)
_LEN_EXTRA = (0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3,
              4, 4, 4, 4, 5, 5, 5, 0)
_DIST_BASE = (1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257,
              385, 513, 769, 1025, 1537, 2049, 3073, 4097, 6145, 8193, 12289,
              16385, 24577)
_DIST_EXTRA = (0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8,
               9, 9, 10, 10, 11, 11, 12, 12, 13, 13)

LZH1_WINDOW = 0x8000
LZH1_LITERAL_SYMBOLS = 285
LZH1_DISTANCE_SYMBOLS = 30
_MAX_CODE_LENGTH = 16


class _BitReader:
    """MSB-first bit reader.  Reading past the end is a refusal, not a zero."""

    __slots__ = ("_data", "_pos", "_bits", "_count", "_allow", "padded")

    def __init__(self, data: bytes, allow_truncation: bool = False) -> None:
        self._data = data
        self._pos = 0
        self._bits = 0
        self._count = 0
        self._allow = allow_truncation
        #: Bits invented past the end of the input; always 0 unless allowed.
        self.padded = 0

    def read(self, width: int) -> int:
        if width == 0:
            return 0
        while self._count < width:
            if self._pos < len(self._data):
                byte = self._data[self._pos]
            elif self._allow:
                byte = 0
                self.padded += 8
            else:
                raise TruncatedStream(
                    "LZH1 stream ran out after %d of %d byte(s): %d more bit(s) "
                    "were needed. The member is truncated or is not LZH1; this "
                    "reader will not pad it with zeros and return plausible "
                    "bytes." % (self._pos, len(self._data), width - self._count)
                )
            self._pos += 1
            self._bits = (self._bits << 8) | byte
            self._count += 8
        self._count -= width
        value = self._bits >> self._count
        self._bits &= (1 << self._count) - 1
        return value


class _Huffman:
    """Canonical Huffman table, decoded a bit at a time (MSB-first)."""

    __slots__ = ("_counts", "_first_code", "_first_index", "_symbols", "_max")

    def __init__(self, lengths: Sequence[int]) -> None:
        counts = [0] * (_MAX_CODE_LENGTH + 1)
        for length in lengths:
            if length:
                counts[length] += 1
        first_code = [0] * (_MAX_CODE_LENGTH + 1)
        first_index = [0] * (_MAX_CODE_LENGTH + 1)
        code = 0
        index = 0
        for length in range(1, _MAX_CODE_LENGTH + 1):
            code = (code + counts[length - 1]) << 1
            first_code[length] = code
            first_index[length] = index
            index += counts[length]
        symbols = [0] * index
        cursor = list(first_index)
        for symbol, length in enumerate(lengths):
            if length:
                symbols[cursor[length]] = symbol
                cursor[length] += 1
        self._counts = counts
        self._first_code = first_code
        self._first_index = first_index
        self._symbols = symbols
        self._max = index

    def decode(self, bits: "_BitReader") -> int:
        code = 0
        for length in range(1, _MAX_CODE_LENGTH + 1):
            code = (code << 1) | bits.read(1)
            count = self._counts[length]
            if count:
                offset = code - self._first_code[length]
                if 0 <= offset < count:
                    return self._symbols[self._first_index[length] + offset]
        raise TerfError(
            "LZH1 stream contains a bit pattern that is not a code in the "
            "block's Huffman table; the member is corrupt or is not LZH1."
        )


def lzh1_decompress(
    data: bytes,
    expected_size: Optional[int] = None,
    allow_truncation: bool = False,
    max_output: Optional[int] = None,
) -> bytes:
    """Decode a whole ``LZH1`` (codec 5) member.

    *expected_size* is the size the container declares.  A decode that ends at
    any other length raises: a short result that reads like a whole one is the
    defect this check exists to prevent.

    *max_output* stops as soon as that many bytes exist -- for a caller that
    wants only a magic out of a large member.  It suppresses the *expected_size*
    check, because a deliberate prefix is not a short decode.

    *allow_truncation* lets the reader pad past the end of a deliberately
    partial input; the bits invented are counted so a caller can still tell.
    """
    bits = _BitReader(data, allow_truncation=allow_truncation)
    out = bytearray()
    while True:
        if bits.read(1):
            bits.read(32)
            break
        literals = _Huffman([bits.read(4) for _ in range(LZH1_LITERAL_SYMBOLS)])
        distances = _Huffman([bits.read(4) for _ in range(LZH1_DISTANCE_SYMBOLS)])
        while True:
            if max_output is not None and len(out) >= max_output:
                return bytes(out[:max_output])
            symbol = literals.decode(bits)
            if symbol < 256:
                out.append(symbol)
                continue
            if symbol == 256:
                break
            index = symbol - 257
            if index >= len(_LEN_BASE):
                raise TerfError(
                    "LZH1 stream used length symbol %d, which the 285-symbol "
                    "alphabet cannot produce; the member is corrupt."
                    % symbol
                )
            length = _LEN_BASE[index] + bits.read(_LEN_EXTRA[index])
            code = distances.decode(bits)
            if code >= len(_DIST_BASE):
                raise TerfError(
                    "LZH1 stream used distance symbol %d, which the 30-symbol "
                    "alphabet cannot produce; the member is corrupt." % code
                )
            distance = _DIST_BASE[code] + bits.read(_DIST_EXTRA[code])
            if distance > LZH1_WINDOW:
                raise TerfError(
                    "LZH1 stream asked for a match %d byte(s) back, past the "
                    "codec's %d-byte window; the member is corrupt."
                    % (distance, LZH1_WINDOW)
                )
            start = len(out) - distance
            for step in range(length):
                position = start + step
                out.append(out[position] if position >= 0 else 0)
        if max_output is not None and len(out) >= max_output:
            return bytes(out[:max_output])
        if expected_size is not None and len(out) >= expected_size:
            break
    if max_output is not None:
        return bytes(out[:max_output])
    if expected_size is not None and len(out) != expected_size:
        raise TruncatedStream(
            "LZH1 member decoded to %d byte(s); the container declares %d. "
            "This reader will not hand back a result of the wrong length."
            % (len(out), expected_size)
        )
    return bytes(out)


# --------------------------------------------------------------------------
# RLE1 (codec 1)
# --------------------------------------------------------------------------

#: ``RLE1``'s escape byte, read out of NCAA Football 2004's decoder rather than
#: guessed from what "RLE" usually means: 33 = 0x21 = ASCII ``!``.
RLE1_ESCAPE = 0x21

#: The longest run one escape can express.  The count is a single byte.
RLE1_MAX_RUN = 0xFF


def rle1_decompress(
    data: bytes,
    expected_size: Optional[int] = None,
    max_output: Optional[int] = None,
) -> bytes:
    """Decode an EA ``RLE1`` (codec 1) member.

    The grammar is a literal byte, or ``0x21 <value> <count>`` for a run.  The
    decoder has no "literal 0x21" escape, so an encoder must emit a lone ``!``
    as a run of one -- and a stream that ends after a ``0x21`` is truncated,
    which this reader says rather than dropping the tail.
    """
    out = bytearray()
    position = 0
    size = len(data)
    while position < size:
        if max_output is not None and len(out) >= max_output:
            return bytes(out[:max_output])
        value = data[position]
        position += 1
        count = 1
        if value == RLE1_ESCAPE:
            if position + 2 > size:
                raise Rle1Error(
                    "RLE1 stream ends mid-escape: the 0x21 at offset %d needs a "
                    "value byte and a count byte and only %d follow it. The "
                    "member is truncated or is not RLE1."
                    % (position - 1, size - position)
                )
            value = data[position]
            count = data[position + 1]
            position += 2
        if count:
            out += bytes((value,)) * count
    if max_output is not None:
        return bytes(out[:max_output])
    if expected_size is not None and len(out) != expected_size:
        raise Rle1Error(
            "RLE1 member decoded to %d byte(s); the container declares %d. "
            "This reader will not hand back a short result that reads like a "
            "whole one." % (len(out), expected_size)
        )
    return bytes(out)


def rle1_compress(payload: bytes) -> bytes:
    """Encode *payload* as an EA ``RLE1`` (codec 1) stream.

    Written because ``LZH1`` has no encoder anywhere in this project or the
    owner's, which would otherwise leave every ``COMP`` container write-only in
    the stored codec.  The output is not claimed to be what EA's encoder would
    emit -- only to decode back to *payload* under :func:`rle1_decompress`,
    which :func:`build_terf` asserts on every member it writes.

    Note that ``RLE1`` is codec 1 and Madden NFL 09 uses only codecs 0 and 5,
    so writing an ``RLE1`` member into a Madden 09 container relies on the
    engine's registration of codec 1 rather than on retail precedent from that
    disc.  Storing (codec 0) has retail precedent and is what
    :func:`rewrite_member` uses.
    """
    out = bytearray()
    position = 0
    size = len(payload)
    while position < size:
        value = payload[position]
        run = 1
        while (run < RLE1_MAX_RUN and position + run < size
               and payload[position + run] == value):
            run += 1
        # An escape costs three bytes, so it only pays from a run of four --
        # except for 0x21 itself, which has no literal form at all.
        if run >= 4 or value == RLE1_ESCAPE:
            out.append(RLE1_ESCAPE)
            out.append(value)
            out.append(run)
        else:
            out += bytes((value,)) * run
        position += run
    return bytes(out)


def decompress_member(payload: bytes, codec: int,
                      expected_size: Optional[int] = None,
                      max_output: Optional[int] = None) -> bytes:
    """Decode one member's stored bytes under *codec*."""
    if codec == CODEC_STORED or not payload:
        if expected_size is not None and codec == CODEC_STORED and payload \
                and len(payload) != expected_size:
            raise TerfError(
                "stored member is %d byte(s) but its COMP entry declares %d; "
                "the container's two tables disagree."
                % (len(payload), expected_size)
            )
        return payload if max_output is None else payload[:max_output]
    if codec == CODEC_LZH1:
        return lzh1_decompress(payload, expected_size, max_output=max_output)
    if codec == CODEC_RLE1:
        return rle1_decompress(payload, expected_size, max_output=max_output)
    raise UnsupportedCodec(
        "member uses codec %d (%s), which this reader does not implement: it "
        "implements %s. Codecs 2 (HUFF), 3 (LZM1) and 4 (IPU1) are registered "
        "by the engine and used by no member of any disc measured. This is a "
        "refusal, not an empty member."
        % (codec, CODEC_NAMES.get(codec, "unknown"),
           ", ".join("%d = %s" % (c, CODEC_NAMES[c]) for c in CODECS_DECODED))
    )


# --------------------------------------------------------------------------
# Member formats
# --------------------------------------------------------------------------

#: First-level format ids, keyed by the magic of a member's **decompressed**
#: bytes.  Measured across Madden 09's 47,769 members; the stored magic of a
#: packed member says nothing about its format, so this is only ever applied
#: after decompression.
MEMBER_FORMAT_MAGICS: Tuple[Tuple[bytes, str], ...] = (
    (b"MMAP", "MMAP"),      # textures: faces, kits, tattoos, every UIS_*
    (b"SMF\x00", "SMF"),    # static geometry: fields, stadiums
    (b"DMF\x00", "DMF"),    # dynamic/animated models: players, coaches, fans
    (b"TERF", "TERF"),      # a nested container
    (b"QL01", "QL01"),      # the GAME.QKL / FE.QKL preload copies
    (b"HSH1", "HSH1"),      # the name-hash chunk (a chunk tag, seen as a head)
    (b"BIGF", "BIGF"),      # EA BIG archive
    (b"BIG4", "BIGF"),
    (b"SCHl", "SCHl"),      # EA audio stream
    (b"MPCh", "MPCh"),      # EA multi-stream audio
    (b"BNKl", "BNKl"),      # sound bank
    (b"FNTS", "FNTS"),      # font set
    (b"SKL1", "SKL1"),      # skeleton
    (b"1LKS", "SKL1"),      # ... and the byte-reversed spelling ANIMDATA uses
    (b"SEVT", "SEVT"),      # animation event table
    (b"EAGL", "EAGL"),      # EAGL scene/graph blob
    (b"SHPS", "SHPS"),      # EA image-bank family (FSH and its relatives)
    (b"ShpS", "SHPS"),
    (b"SHPM", "SHPS"),
    (b"SHPP", "SHPS"),
    (b"SHPX", "SHPS"),
    (b"\x7fELF", "ELF"),
)

#: What an EA TDB looks like.  ``"DB"`` alone is two bytes and coincidences
#: happen, so the test is the table count at ``+0x10``: a real database has a
#: plausible one.  The version bytes at ``+0x02`` are ``00 08`` as they sit on
#: the disc -- not ``08 00`` -- so they are deliberately *not* the test.
TDB_MAGIC = b"DB"
TDB_TABLE_COUNT_OFFSET = 0x10
TDB_MAX_TABLES = 4096
TDB_MINIMUM = TDB_TABLE_COUNT_OFFSET + 4

#: How many bytes a format id looks at.  It is the printable-text rule that
#: makes this load-bearing: over 8 bytes, 708 of Madden 09's members read as
#: text that are not; over 32 they do not, and the count then agrees with the
#: owner's census exactly.
IDENTIFY_HEAD = 32

FORMAT_EMPTY = "empty"
FORMAT_TDB = "TDB"
FORMAT_TEXT = "TEXT"


def identify_member(payload: bytes) -> Optional[str]:
    """Name the first-level format of a member's **decompressed** bytes.

    Returns ``None`` for a head no magic claims -- which is a measured answer
    ("6,675 of Madden 09's members look like nothing this table knows"), not a
    failure, and never the same thing as a member that could not be decoded.

    A packed member's *stored* bytes never carry its format's magic, so this
    must only ever be applied after decompression: 39 of Madden 09's 107
    containers change classification between the two.
    """
    if not payload:
        return FORMAT_EMPTY
    for magic, name in MEMBER_FORMAT_MAGICS:
        if payload.startswith(magic):
            return name
    if payload[:2] == TDB_MAGIC and len(payload) >= TDB_MINIMUM:
        tables, = struct.unpack_from("<I", payload, TDB_TABLE_COUNT_OFFSET)
        if 0 < tables <= TDB_MAX_TABLES:
            return FORMAT_TDB
    head = payload[:IDENTIFY_HEAD]
    if all(32 <= byte < 127 or byte in (9, 10, 13) for byte in head):
        return FORMAT_TEXT
    return None


# --------------------------------------------------------------------------
# MMAP -- the texture wrapper, header only
# --------------------------------------------------------------------------

MMAP_MAGIC = b"MMAP"

#: The size the header declares at ``+0x18`` in all 5,192 stored ``MMAP``
#: members measured on the Madden 09 disc.
MMAP_HEADER_SIZE = 40


@dataclass(frozen=True)
class MmapHeader:
    """The 40-byte ``MMAP`` wrapper, plus the first surface descriptor's size.

    Measured on 5,192 stored ``MMAP`` members of ``PLYRFACE``, ``UIS_PLYR``,
    ``TATTOOS``, ``UIS_MCFL`` and ``UIS_LOAD`` (Madden 09, USA):

    ==========  ====================================================
    ``version`` ``u32`` at ``+0x04``.  **2** in 4,004 members and
                **1** in 1,188 (all of ``UIS_MCFL``).  A census that
                sampled only ``GAMEDATA`` recorded "2 in every
                member"; version 1 exists.
    ``marker``  bytes ``00 01 02 03`` at ``+0x08`` in 5,192 of 5,192.
    ``header_size`` ``u32`` at ``+0x18``.  40 in 5,192 of 5,192.
    ``payload_size`` ``u32`` at ``+0x14``.  A size; its exact scope is
                not established -- it sits 12, 28 or 98 bytes short of
                the member for different container families.
    ``size_a`` / ``size_b`` / ``size_c``
                ``u32`` at ``+0x1C`` / ``+0x20`` / ``+0x24``, ascending.
    ``width`` / ``height``
                ``u16`` at ``+0x28`` / ``+0x2A``, i.e. the first four
                bytes *after* the declared header.  Nine distinct
                widths across the sample -- 64, 96, 112, 128, 256,
                320, 480, 512 -- which is what texture dimensions look
                like and nothing else in the header does.
    ==========  ====================================================

    **Pixel format, palette presence and mip count are not determined.**  The
    two ``u16`` at ``+0x2C``/``+0x2E`` take six distinct value pairs across the
    sample and the ``u32`` at ``+0x30`` equals ``width * height`` for the
    128x128 and 64x64 faces, which is consistent with 8-bit indexed pixels but
    is not proof of it.  Those bytes are handed back verbatim in
    :attr:`descriptor` for the uniform-art lane to decode; this parser does not
    guess at them and does not touch pixels.
    """

    version: int
    marker: bytes
    payload_size: int
    header_size: int
    size_a: int
    size_b: int
    size_c: int
    width: int
    height: int
    #: Every byte from the end of the declared header to ``+0x40``, verbatim.
    descriptor: bytes

    @property
    def dimensions(self) -> Tuple[int, int]:
        return (self.width, self.height)


#: The smallest member :func:`parse_mmap_header` can read: the 40-byte header
#: plus the four bytes of dimensions that follow it.
MMAP_MINIMUM = MMAP_HEADER_SIZE + 4


def parse_mmap_header(payload: bytes) -> MmapHeader:
    """Read the ``MMAP`` wrapper header out of a decompressed member."""
    if not payload.startswith(MMAP_MAGIC):
        raise TerfError(
            "member does not start with %r, so it is not an MMAP texture "
            "(it starts with %r). Decompress the member first: a packed "
            "member's stored bytes never carry its format's magic."
            % (MMAP_MAGIC, payload[:4])
        )
    if len(payload) < MMAP_MINIMUM:
        raise TerfError(
            "MMAP member is %d byte(s); its header plus the dimensions that "
            "follow it need %d. The member is truncated."
            % (len(payload), MMAP_MINIMUM)
        )
    version, = struct.unpack_from("<I", payload, 0x04)
    payload_size, = struct.unpack_from("<I", payload, 0x14)
    header_size, = struct.unpack_from("<I", payload, 0x18)
    size_a, size_b, size_c = struct.unpack_from("<III", payload, 0x1C)
    width, height = struct.unpack_from("<HH", payload, 0x28)
    return MmapHeader(
        version=version,
        marker=payload[0x08:0x0C],
        payload_size=payload_size,
        header_size=header_size,
        size_a=size_a,
        size_b=size_b,
        size_c=size_c,
        width=width,
        height=height,
        descriptor=payload[MMAP_HEADER_SIZE:0x40],
    )


# --------------------------------------------------------------------------
# The container
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Chunk:
    """One entry of the container's chunk chain."""

    tag: str
    offset: int
    size: int

    @property
    def end(self) -> int:
        return self.offset + self.size


@dataclass(frozen=True)
class Member:
    """One member's directory row: where it is, and how it is stored."""

    index: int
    #: Relative to the offset of the ``DATA`` **tag**, not to its payload.
    offset: int
    stored_size: int
    codec: int
    #: What the ``COMP`` chunk declares the member unpacks to.  Equal to
    #: :attr:`stored_size` when the container has no ``COMP`` chunk.
    decompressed_size: int

    @property
    def compressed(self) -> bool:
        return self.codec != CODEC_STORED

    @property
    def empty(self) -> bool:
        return self.stored_size == 0

    @property
    def codec_name(self) -> str:
        return CODEC_NAMES.get(self.codec, "unknown codec %d" % self.codec)


def _round_up(value: int, alignment: int) -> int:
    return ((value + alignment - 1) // alignment) * alignment


def _require(condition: object, message: str) -> None:
    if not condition:
        raise TerfError(message)


class TerfContainer:
    """A parsed ``TERF`` container.  Reads; never mutates its input."""

    def __init__(self, data: bytes, allow_size_mismatch: bool = False) -> None:
        _require(
            len(data) >= CHUNK_HEADER_SIZE and data[:4] == TERF_MAGIC,
            "not an EA TERF container: it starts with %r, not %r. This reader "
            "opens EA Tiburon PS2 disc containers (Madden and NCAA Football) "
            "only." % (bytes(data[:4]), TERF_MAGIC),
        )
        self._data = data
        header_size, = struct.unpack_from("<I", data, 4)
        _require(
            CHUNK_HEADER_SIZE <= header_size <= len(data),
            "TERF header declares itself %d byte(s) long, which does not fit "
            "in a %d-byte file." % (header_size, len(data)),
        )
        self.header_size = header_size
        self.version_word = bytes(data[8:12])
        alignment, member_count = struct.unpack_from("<HH", data, 12)
        _require(
            alignment > 0 and (alignment & (alignment - 1)) == 0,
            "TERF header declares member alignment %d, which is not a power of "
            "two; this is not a container this reader can walk." % alignment,
        )
        self.alignment = alignment
        self.member_count = member_count
        self.chunks: Tuple[Chunk, ...] = tuple(self._walk_chunks())
        by_tag: Dict[str, Chunk] = {}
        for chunk in self.chunks:
            by_tag.setdefault(chunk.tag, chunk)
        self._by_tag = by_tag
        for required in ("TERF", "DIR1", "DATA"):
            _require(
                required in by_tag,
                "TERF container has no %s chunk (its chain is %s); it is "
                "damaged or is a variant this reader does not know."
                % (required, " -> ".join(c.tag for c in self.chunks) or "empty"),
            )
        directory = by_tag["DIR1"]
        payload = by_tag["DATA"]
        #: What the container says its own length is, which is not always what
        #: holds it.  Six containers on the Madden 09 *Deluxe* disc are
        #: recorded in ISO9660 as 4 to 26,168 bytes shorter than this.
        self.declared_length = payload.end
        self.size_mismatch = payload.end - len(data)
        if self.size_mismatch and not allow_size_mismatch:
            raise TerfError(
                "the DATA chunk declares %d byte(s) from offset %d, so the "
                "container is %d byte(s) long, and it was handed %d. Read "
                "declared_length(head) bytes and pass those, or parse with "
                "allow_size_mismatch=True if the difference is expected."
                % (payload.size, payload.offset, payload.end, len(data))
            )
        self.data_offset = payload.offset
        self.data_size = payload.size
        table_bytes = CHUNK_HEADER_SIZE + 8 * member_count
        _require(
            directory.size >= table_bytes,
            "DIR1 chunk is %d byte(s) but the header declares %d members, "
            "which need %d." % (directory.size, member_count, table_bytes),
        )
        compression = by_tag.get("COMP")
        if compression is not None:
            _require(
                compression.size >= table_bytes,
                "COMP chunk is %d byte(s) but the header declares %d members, "
                "which need %d." % (compression.size, member_count, table_bytes),
            )
        self.compressed = compression is not None
        members: List[Member] = []
        for index in range(member_count):
            offset, stored = struct.unpack_from(
                "<II", data, directory.offset + CHUNK_HEADER_SIZE + 8 * index)
            if compression is None:
                codec, unpacked = CODEC_STORED, stored
            else:
                codec, unpacked = struct.unpack_from(
                    "<II", data,
                    compression.offset + CHUNK_HEADER_SIZE + 8 * index)
            start = self.data_offset + offset
            _require(
                0 <= start and start + stored <= len(data),
                "member %d runs from %d for %d byte(s), past the end of the "
                "%d byte(s) this reader was handed."
                % (index, start, stored, len(data)),
            )
            members.append(Member(index, offset, stored, codec, unpacked))
        self.members: Tuple[Member, ...] = tuple(members)
        self._cache: Dict[int, bytes] = {}

    # -- chunk chain -------------------------------------------------------

    def _walk_chunks(self) -> Iterable[Chunk]:
        data = self._data
        position = 0
        seen = 0
        while position + CHUNK_HEADER_SIZE <= len(data):
            tag = data[position:position + 4]
            size, = struct.unpack_from("<I", data, position + 4)
            if size < CHUNK_HEADER_SIZE:
                break
            try:
                name = bytes(tag).decode("ascii")  # tag may be a memoryview slice
            except UnicodeDecodeError:
                break
            yield Chunk(name, position, size)
            position += size
            seen += 1
            _require(
                seen <= 16,
                "TERF chunk chain has more than 16 links, which no measured "
                "container does; the file is damaged.",
            )

    def chunk(self, tag: str) -> Optional[Chunk]:
        return self._by_tag.get(tag)

    @property
    def chunk_chain(self) -> str:
        return " -> ".join(chunk.tag for chunk in self.chunks)

    # -- members -----------------------------------------------------------

    def __len__(self) -> int:
        return self.member_count

    def _check_index(self, index: int) -> Member:
        if not 0 <= index < self.member_count:
            raise TerfError(
                "member %d does not exist: this container has %d (0..%d)."
                % (index, self.member_count, self.member_count - 1)
            )
        return self.members[index]

    def stored(self, index: int) -> bytes:
        """Member *index* exactly as it sits in the file, still packed."""
        member = self._check_index(index)
        start = self.data_offset + member.offset
        return bytes(self._data[start:start + member.stored_size])

    def member(self, index: int, max_output: Optional[int] = None) -> bytes:
        """Member *index*, decompressed if the container stored it packed."""
        member = self._check_index(index)
        if max_output is None:
            cached = self._cache.get(index)
            if cached is not None:
                return cached
        try:
            unpacked = decompress_member(
                self.stored(index), member.codec,
                member.decompressed_size if max_output is None else None,
                max_output=max_output)
        except TerfError as error:
            raise type(error)("member %d: %s" % (index, error)) from error
        if max_output is None:
            self._cache[index] = unpacked
        return unpacked

    def member_format(self, index: int) -> Optional[str]:
        """The first-level format id of member *index*'s decompressed bytes."""
        return identify_member(self.member(index, max_output=IDENTIFY_HEAD))

    def format_histogram(self) -> Dict[str, int]:
        """``{format id: count}`` over every member, decompressed.

        An unclassified member is counted under ``"unclassified"``; a member
        that could not be decoded is counted under ``"undecodable"`` and is a
        different answer.
        """
        counts: Dict[str, int] = {}
        for index in range(self.member_count):
            try:
                name = self.member_format(index) or "unclassified"
            except TerfError:
                name = "undecodable"
            counts[name] = counts.get(name, 0) + 1
        return counts

    def codec_histogram(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for member in self.members:
            counts[member.codec_name] = counts.get(member.codec_name, 0) + 1
        return counts

    # -- layout ------------------------------------------------------------

    def expected_offset(self, index: int) -> int:
        """Where member *index* must sit if the container is laid out normally.

        The rule, measured with zero counter-examples across Madden 09: members
        follow one another in table order at ``alignment``-aligned offsets, and
        an **empty member still occupies one alignment unit**.
        """
        self._check_index(index)
        cursor = CHUNK_HEADER_SIZE
        for member in self.members[:index]:
            cursor = member.offset + max(member.stored_size, 1)
        return _round_up(cursor, self.alignment)

    def layout_violations(self) -> List[str]:
        """Every way this container departs from the measured layout rules.

        Empty when the container is ordinary.  A caller that intends to rewrite
        a member should check this first: a container that already breaks the
        rules will not survive being rebuilt from them.
        """
        problems: List[str] = []
        if self.version_word != VERSION_WORD:
            problems.append(
                "header version word is %r, not the %r every measured "
                "container carries" % (self.version_word, VERSION_WORD))
        if self.header_size != max(MIN_HEADER_SIZE, self.alignment):
            problems.append(
                "header is %d byte(s); alignment %d implies %d"
                % (self.header_size, self.alignment,
                   max(MIN_HEADER_SIZE, self.alignment)))
        table = _round_up(CHUNK_HEADER_SIZE + 8 * self.member_count,
                          self.alignment)
        for tag in ("DIR1", "COMP"):
            chunk = self._by_tag.get(tag)
            if chunk is not None and chunk.size != table:
                problems.append(
                    "%s chunk is %d byte(s); %d members at alignment %d imply "
                    "%d" % (tag, chunk.size, self.member_count, self.alignment,
                            table))
        cursor = CHUNK_HEADER_SIZE
        for member in self.members:
            want = _round_up(cursor, self.alignment)
            if member.offset != want:
                problems.append(
                    "member %d sits at +%d; the layout rule puts it at +%d"
                    % (member.index, member.offset, want))
            cursor = member.offset + max(member.stored_size, 1)
        end = _round_up(cursor, self.alignment)
        if self.data_size != end:
            problems.append(
                "DATA chunk is %d byte(s); its members end at %d"
                % (self.data_size, end))
        return problems


def parse_terf(data: "bytes | memoryview | mmap.mmap", allow_size_mismatch: bool = False) -> TerfContainer:
    """Parse *data* as an EA ``TERF`` container."""
    return TerfContainer(data, allow_size_mismatch=allow_size_mismatch)


def declared_length(data: bytes) -> int:
    """How long the container in *data* says it is, from its chunk chain alone.

    A caller reading out of a disc image uses this to decide how much to read:
    the ISO9660 directory record and the container do not always agree, and on
    the community's Madden 09 *Deluxe* disc six containers are recorded 4 to
    26,168 bytes short of what they actually carry.  Reading the directory's
    length there truncates the file and every member after the cut vanishes.

    Needs only the header and the chunk chain -- a few kilobytes -- so it can
    be answered from a ranged read before the whole container is fetched.
    """
    _require(
        len(data) >= CHUNK_HEADER_SIZE and data[:4] == TERF_MAGIC,
        "not an EA TERF container: it starts with %r, not %r."
        % (bytes(data[:4]), TERF_MAGIC),
    )
    position = 0
    for _ in range(16):
        if position + CHUNK_HEADER_SIZE > len(data):
            break
        tag = data[position:position + 4]
        size, = struct.unpack_from("<I", data, position + 4)
        if size < CHUNK_HEADER_SIZE:
            break
        if tag == DATA_MAGIC:
            return position + size
        position += size
    raise TerfError(
        "no DATA chunk was found in the first %d byte(s) of this container, so "
        "its length cannot be read from its chunk chain. Hand declared_length "
        "more of the file." % len(data)
    )


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


def build_terf(
    members: Sequence[bytes],
    chunk: str = "DATA",
    codecs: Optional[Sequence[int]] = None,
    alignment: int = DEFAULT_ALIGNMENT,
) -> bytes:
    """Build a container from *members*, reproducing the measured layout.

    *chunk* is ``"DATA"`` for a plain container or ``"COMP"`` for one that
    carries a per-member codec table.  ``"DATA"`` refuses a *codecs* argument:
    a plain container has nowhere to record one, and silently dropping it would
    write members the reader would then hand back still packed.

    *codecs* gives one id per member for a ``"COMP"`` container, defaulting to
    :data:`CODEC_STORED`.  Members are compressed here, so the caller passes
    plain payloads either way; every member written is decompressed again and
    compared before the container is returned.
    """
    _require(
        chunk in ("DATA", "COMP"),
        "chunk kind %r is not one this writer knows: pass \"DATA\" for a plain "
        "container or \"COMP\" for one with a codec table." % (chunk,),
    )
    _require(
        alignment > 0 and (alignment & (alignment - 1)) == 0,
        "alignment %d is not a power of two; every measured container uses 4, "
        "16, 64 or 2048." % alignment,
    )
    _require(
        len(members) <= 0xFFFF,
        "a TERF header records the member count in 16 bits, so it cannot hold "
        "%d members." % len(members),
    )
    if chunk == "DATA":
        _require(
            codecs is None,
            "a DATA container has no codec table, so it cannot carry the "
            "codecs given. Pass chunk=\"COMP\" to write compressed members.",
        )
        ids: List[int] = [CODEC_STORED] * len(members)
    else:
        ids = list(codecs) if codecs is not None else [CODEC_STORED] * len(members)
        _require(
            len(ids) == len(members),
            "%d codec(s) were given for %d member(s); a COMP container needs "
            "exactly one per member." % (len(ids), len(members)),
        )
    stored: List[bytes] = []
    for index, (payload, codec) in enumerate(zip(members, ids)):
        if codec == CODEC_STORED:
            packed = bytes(payload)
        elif codec == CODEC_RLE1:
            packed = rle1_compress(bytes(payload))
        else:
            raise UnsupportedCodec(
                "member %d asks for codec %d (%s), which this writer cannot "
                "produce: it writes %s. No LZH1 encoder exists in this project "
                "or in the source it was ported from, so an LZH1 member can be "
                "read and not written."
                % (index, codec, CODEC_NAMES.get(codec, "unknown"),
                   ", ".join("%d = %s" % (c, CODEC_NAMES[c])
                             for c in CODECS_ENCODED))
            )
        _require(
            decompress_member(packed, codec, len(payload)) == bytes(payload),
            "member %d did not survive its own round trip through codec %d; "
            "this writer will not ship a member it cannot read back."
            % (index, codec),
        )
        stored.append(packed)

    header_size = max(MIN_HEADER_SIZE, alignment)
    table_size = _round_up(CHUNK_HEADER_SIZE + 8 * len(members), alignment)

    offsets: List[int] = []
    cursor = CHUNK_HEADER_SIZE
    for packed in stored:
        offset = _round_up(cursor, alignment)
        offsets.append(offset)
        cursor = offset + max(len(packed), 1)
    data_size = _round_up(cursor, alignment)

    out = bytearray()
    out += TERF_MAGIC
    out += struct.pack("<I", header_size)
    out += VERSION_WORD
    out += struct.pack("<HH", alignment, len(members))
    out += b"\x00" * (header_size - len(out))

    directory = bytearray(DIR1_MAGIC + struct.pack("<I", table_size))
    for offset, packed in zip(offsets, stored):
        directory += struct.pack("<II", offset, len(packed))
    directory += b"\x00" * (table_size - len(directory))
    out += directory

    if chunk == "COMP":
        codec_table = bytearray(COMP_MAGIC + struct.pack("<I", table_size))
        for codec, payload in zip(ids, members):
            codec_table += struct.pack("<II", codec, len(payload))
        codec_table += b"\x00" * (table_size - len(codec_table))
        out += codec_table

    body = bytearray(DATA_MAGIC + struct.pack("<I", data_size))
    body += b"\x00" * (data_size - len(body))
    for offset, packed in zip(offsets, stored):
        body[offset:offset + len(packed)] = packed
    out += body
    return bytes(out)


def rewrite_member(container: bytes, index: int, payload: bytes) -> bytes:
    """Return *container* with member *index* replaced by *payload*.

    Every other member's bytes come through unchanged; the directory, the codec
    table if there is one, and the ``DATA`` chunk's declared size are updated,
    and the file keeps the layout rules the retail containers follow.  When the
    new payload occupies the same aligned slot as the old one, nothing after it
    moves and the result differs from the input only inside that slot.

    In a ``COMP`` container the replacement is written **stored** (codec 0),
    because no ``LZH1`` encoder exists.  That is a shape the shipped game
    already loads -- Madden 09 stores 270 of ``UNIFORMS.DAT``'s 725 members and
    689 of ``STADIUMS.DAT``'s 1,355 as codec 0 inside a ``COMP`` container --
    but it costs space, so a replacement bigger than the member it replaces
    grows the file.  A caller under a fixed allocation must check the result's
    length itself.
    """
    parsed = parse_terf(container)
    if not 0 <= index < parsed.member_count:
        raise TerfError(
            "member %d does not exist: this container has %d (0..%d). Nothing "
            "was changed."
            % (index, parsed.member_count, parsed.member_count - 1)
        )
    member = parsed.members[index]
    violations = parsed.layout_violations()
    if violations:
        raise TerfError(
            "this container does not follow the layout rules a rewrite "
            "rebuilds from, so rewriting it would move bytes this function "
            "cannot account for: %s. Nothing was changed." % violations[0]
        )
    if member.codec not in (CODEC_STORED, CODEC_LZH1, CODEC_RLE1):
        raise UnsupportedCodec(
            "member %d is stored with codec %d (%s), which this writer does "
            "not understand well enough to replace. Nothing was changed."
            % (index, member.codec, CODEC_NAMES.get(member.codec, "unknown"))
        )

    payload = bytes(payload)
    stored: List[bytes] = []
    codecs: List[int] = []
    for other in parsed.members:
        if other.index == index:
            stored.append(payload)
            codecs.append(CODEC_STORED)
        else:
            stored.append(parsed.stored(other.index))
            codecs.append(other.codec)

    alignment = parsed.alignment
    offsets: List[int] = []
    cursor = CHUNK_HEADER_SIZE
    for packed in stored:
        offset = _round_up(cursor, alignment)
        offsets.append(offset)
        cursor = offset + max(len(packed), 1)
    data_size = _round_up(cursor, alignment)

    out = bytearray(container[:parsed.data_offset])
    directory = parsed.chunk("DIR1")
    assert directory is not None
    base = directory.offset + CHUNK_HEADER_SIZE
    for slot, (offset, packed) in enumerate(zip(offsets, stored)):
        struct.pack_into("<II", out, base + 8 * slot, offset, len(packed))
    compression = parsed.chunk("COMP")
    if compression is not None:
        base = compression.offset + CHUNK_HEADER_SIZE
        for slot, (codec, packed) in enumerate(zip(codecs, stored)):
            size = (len(packed) if slot == index
                    else parsed.members[slot].decompressed_size)
            struct.pack_into("<II", out, base + 8 * slot, codec, size)

    body = bytearray(DATA_MAGIC + struct.pack("<I", data_size))
    body += b"\x00" * (data_size - len(body))
    for offset, packed in zip(offsets, stored):
        body[offset:offset + len(packed)] = packed
    out += body
    return bytes(out)


__all__ = [
    "CHUNK_HEADER_SIZE",
    "CODECS_DECODED",
    "CODECS_ENCODED",
    "CODEC_IPU1",
    "CODEC_HUFF",
    "CODEC_LZH1",
    "CODEC_LZM1",
    "CODEC_NAMES",
    "CODEC_RLE1",
    "CODEC_STORED",
    "COMP_MAGIC",
    "DATA_MAGIC",
    "DEFAULT_ALIGNMENT",
    "DIR1_MAGIC",
    "FORMAT_EMPTY",
    "FORMAT_TDB",
    "FORMAT_TEXT",
    "HSH1_MAGIC",
    "LZH1_WINDOW",
    "MEMBER_FORMAT_MAGICS",
    "MIN_HEADER_SIZE",
    "MMAP_HEADER_SIZE",
    "MMAP_MAGIC",
    "MMAP_MINIMUM",
    "Chunk",
    "Member",
    "MmapHeader",
    "RLE1_ESCAPE",
    "RLE1_MAX_RUN",
    "Rle1Error",
    "IDENTIFY_HEAD",
    "TDB_MAGIC",
    "TDB_MAX_TABLES",
    "TDB_MINIMUM",
    "TDB_TABLE_COUNT_OFFSET",
    "TERF_MAGIC",
    "TerfContainer",
    "TerfError",
    "TruncatedStream",
    "UnsupportedCodec",
    "VERSION_WORD",
    "build_terf",
    "declared_length",
    "decompress_member",
    "identify_member",
    "lzh1_decompress",
    "parse_mmap_header",
    "parse_terf",
    "rewrite_member",
    "rle1_compress",
    "rle1_decompress",
]

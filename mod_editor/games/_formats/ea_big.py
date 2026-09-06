"""EA ``BIG`` — the archive the non-Tiburon EA PlayStation 2 discs pack into.

``TERF`` is the container a Madden or NCAA Football PS2 disc streams from;
``BIG`` is the one EA's *other* PS2 studios use, and the one a Madden disc
still carries for its EA Nation dashboard.  MVP Baseball 2005 is built
entirely out of it: 211 archives holding 43,773 entries, with no ``TERF``
container and no bare ``TDB`` anywhere on the disc [M].  A module that reads
this file reads that disc.

Where ``TERF`` is a chunk chain with a positional directory, ``BIG`` is a flat
**named** archive: a 16-byte header, then one variable-length row per entry
carrying an offset, a size and a NUL-terminated name.  Entries are addressed
by name, they may be compressed one at a time with EA's public **RefPack**
LZ77, and an entry may itself be another ``BIG``.

Evidence tags
-------------
**[M]** measured by running this module (or the owner's read-only disc mapper)
against a disc this project can reach; **[S]** sourced; **[A]** assumed.

What is measured, and where
---------------------------
Across the five discs in reach — Madden NFL 06 / 08 / 09 (USA) and NCAA
Football 09 (USA) locally, MVP Baseball 2005 (USA) read over SSH — every
archive is ``BIGF``.  No ``BIG4`` and no RefPack-wrapped (``C0 FB``) archive
appears on any of them, so both are named by this reader and **refused rather
than guessed at** [M].

* the magic is ``"BIGF"`` at ``+0`` [M];
* the ``u32`` at ``+4`` is the archive's **total length** and it is stored
  **little-endian**, while every other integer in the header and in the entry
  table is **big-endian** [M].  That mixture is the single thing a first
  reading gets wrong, and it is why this reader measures the size word both
  ways and records which one matched (:attr:`BigArchive.size_endian`);
* the ``u32`` at ``+8`` is the entry count and the ``u32`` at ``+12`` is the
  number of bytes the header **and the entry table together** occupy, both
  big-endian [M];
* an entry row is ``u32 offset, u32 size`` (big-endian) followed by a
  NUL-terminated name.  Rows are packed end to end with no padding; the name
  length is not stored, so the table can only be walked forwards [M];
* entry payloads sit at the offsets the table gives, in table order, aligned
  outward from the end of the table.  The alignment is **not declared
  anywhere in the file** and is not assumed here: :meth:`BigArchive.alignment`
  reports the largest power of two that divides every payload offset, as a
  measurement rather than a rule [M];
* a compressed entry's stored bytes begin with a RefPack header; an entry is
  never marked compressed by the table, so it is the payload's own first two
  bytes that say so [M].  MVP Baseball 2005 stores 23,855 of its 43,773
  entries RefPack-packed [M]; the three archives on each Madden / NCAA disc
  store **none** [M].

Not established here, and refused rather than guessed
------------------------------------------------------
The bytes between the end of the entry table and the first payload (0 to a
little under one alignment unit) are not interpreted.  No checksum field
exists in the header and none was found: nothing here has run a rebuilt
archive through a game, so the absence of a checksum is a search that came up
empty, not a proof.  ``BIG4`` and the RefPack-wrapped archive are recognised
by magic and refused by name.  **There is no writer**: :func:`plan_entry_rewrite`
prices a bounded replacement and :func:`rewrite_entry` refuses, saying what a
writer would still need.

Standard library only; importable without Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Callable, Dict, Iterator, List, Optional, Sequence, Tuple, Union

from mod_editor.games.contract import Refusal
from mod_editor.games._formats import ea_terf

#: The archive magics this family uses.  Only ``BIGF`` appears on any disc in
#: reach; the other two are recognised so that a reader refuses them by name
#: instead of misreading their integers.
BIGF_MAGIC = b"BIGF"
BIG4_MAGIC = b"BIG4"

#: A whole archive stored as one RefPack stream.  ``0xC0 0xFB`` is a RefPack
#: header with the compressed-size flag set, not four ASCII characters; the
#: community name for the shape is "C0FB" all the same [S].
C0FB_HEAD = b"\xc0\xfb"

#: Header: magic, u32 length, u32 entry count, u32 header+table bytes.
BIG_HEADER_SIZE = 16

#: The fixed part of one entry row.  The name that follows is variable.
BIG_ROW_FIXED = 8

#: A sanity bound on the entry count.  MVP Baseball 2005's largest archive
#: declares 8,400 [M]; the cap is far above every measured archive and exists
#: only so a wrong-endian read is refused instead of allocating for it.
BIG_MAX_ENTRIES = 200_000

#: A sanity bound on the declared table size, for the same reason.
BIG_MAX_INDEX_BYTES = 64 << 20

#: How many bytes of an entry are enough to name its format.  The same 32 the
#: ``TERF`` reader uses, and for the same measured reason: over 8 bytes a
#: crowd of members read as text that are not.
IDENTIFY_HEAD = ea_terf.IDENTIFY_HEAD

#: RefPack's second header byte, in every stream of the family.
REFPACK_SIGNATURE = 0xFB

#: The bits of RefPack's first header byte.  ``0x01`` widens the size fields
#: from three bytes to four; ``0x80`` says a *compressed* size precedes the
#: decompressed one.  Bits ``0x3E`` are the family marker and read ``0x10``.
REFPACK_FLAG_LONG = 0x01
REFPACK_FLAG_COMPRESSED_SIZE = 0x80
REFPACK_FAMILY_MASK = 0x3E
REFPACK_FAMILY = 0x10

#: RefPack's window: an offset is stored biased by one and reaches back this
#: far at most (the four-byte opcode's 17-bit field).
REFPACK_MAX_OFFSET = 1 << 17

FORMAT_EMPTY = ea_terf.FORMAT_EMPTY
FORMAT_TEXT = ea_terf.FORMAT_TEXT
FORMAT_TDB = ea_terf.FORMAT_TDB

#: What :meth:`BigArchive.entry_format` says about an entry whose stored bytes
#: are a RefPack stream this reader could not finish.  It is a refusal, not a
#: format: "this reader cannot open it" and "there is nothing there" must not
#: render the same.
FORMAT_UNDECODABLE = "undecodable"

#: ... and about an entry whose decompressed head matches no known magic.  A
#: measured answer, not a failure.
FORMAT_UNCLASSIFIED = "unclassified"


class BigError(Refusal):
    """An archive could not be read; the message says what was wrong."""


class TruncatedArchive(BigError):
    """The archive claims bytes that were not handed to this reader."""


class RefpackError(BigError):
    """A RefPack stream ended early or addressed outside its own output."""


class UnsupportedArchive(BigError):
    """A recognised archive shape this reader deliberately does not open."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise BigError(message)


# --------------------------------------------------------------------------
# RefPack
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class RefpackHeader:
    """A RefPack stream's own header, as the format declares it.

    ``header_bytes`` is where the opcode stream starts, so a caller that
    wants to know only how large a packed entry unpacks to never touches the
    codec.
    """

    flags: int
    long_sizes: bool
    compressed_size: Optional[int]
    decompressed_size: int
    header_bytes: int


def is_refpack(head: "bytes | memoryview") -> bool:
    """Does *head* begin a RefPack stream?

    The test is the two header bytes and nothing else: the second byte is
    ``0xFB`` and the first carries the family marker ``0x10`` in bits
    ``0x3E``.  Two bytes is a weak test on its own, which is why every caller
    here follows it with :func:`refpack_header`, whose declared size has to
    fit the entry it came from.
    """
    head = bytes(head[:2])
    return (len(head) >= 2 and head[1] == REFPACK_SIGNATURE
            and (head[0] & REFPACK_FAMILY_MASK) == REFPACK_FAMILY)


def refpack_header(data: "bytes | memoryview") -> Optional[RefpackHeader]:
    """Read a RefPack stream's header, or ``None`` if *data* is not one.

    ``flags & 0x80`` puts a compressed size ahead of the decompressed one;
    ``flags & 0x01`` makes both four bytes wide instead of three.  Sizes are
    big-endian in every stream measured [M][S].
    """
    data = bytes(data[:16])
    if not is_refpack(data):
        return None
    flags = data[0]
    long_sizes = bool(flags & REFPACK_FLAG_LONG)
    width = 4 if long_sizes else 3
    position = 2
    compressed: Optional[int] = None
    if flags & REFPACK_FLAG_COMPRESSED_SIZE:
        if position + width > len(data):
            return None
        compressed = int.from_bytes(data[position:position + width], "big")
        position += width
    if position + width > len(data):
        return None
    decompressed = int.from_bytes(data[position:position + width], "big")
    position += width
    return RefpackHeader(flags=flags, long_sizes=long_sizes,
                         compressed_size=compressed,
                         decompressed_size=decompressed,
                         header_bytes=position)


def refpack_decompress(data: "bytes | memoryview",
                       expected_size: Optional[int] = None,
                       *, max_output: Optional[int] = None,
                       what: str = "this stream") -> bytes:
    """Decode one RefPack stream.

    RefPack is EA's public LZ77 variant [S].  After the header the stream is a
    sequence of opcodes in four shapes plus a terminator; each carries a count
    of *literal* bytes that follow it, and the first three also carry a
    back-reference (offset, length) into the output produced so far.

    ============  =========================================================
    ``0x00-0x7F``  two bytes: 0-3 literals, offset < 1,024, length 3-10
    ``0x80-0xBF``  three bytes: 0-3 literals, offset < 16,384, length 4-67
    ``0xC0-0xDF``  four bytes: 0-3 literals, offset < 131,072, length 5-1,028
    ``0xE0-0xFB``  one byte: 4-112 literals, in multiples of four, no copy
    ``0xFC-0xFF``  one byte: 0-3 literals, then the stream ends
    ============  =========================================================

    Pass *max_output* to stop as soon as that many bytes exist — how a caller
    identifies an entry's format without unpacking a 30 MB texture bank.  In
    that mode the caller may also hand over only the **front** of the stream,
    so running out of input is not an error: what was produced is returned.
    With *max_output* unset the whole stream must be present, the result must
    be exactly *expected_size* when one is given, and a stream that ends early
    or reaches back past the start of its own output is a
    :class:`RefpackError` rather than a short result.
    """
    payload = bytes(data)
    bounded = max_output is not None
    header = refpack_header(payload)
    if header is None:
        raise RefpackError(
            "%s does not begin with a RefPack header: its first two bytes are "
            "%s, and a RefPack stream's second byte is 0xFB with the family "
            "marker 0x10 in bits 0x3E of the first."
            % (what, payload[:2].hex(" ") or "(none)")
        )
    if expected_size is None:
        expected_size = header.decompressed_size
    limit = header.decompressed_size if max_output is None else min(
        header.decompressed_size, max_output)
    out = bytearray()
    position = header.header_bytes
    size = len(payload)

    class _OutOfInput(Exception):
        """The stream stopped mid-opcode.  Fatal unless the read is bounded."""

    def need(count: int) -> None:
        if position + count > size:
            raise _OutOfInput(count)

    def literals(count: int) -> None:
        nonlocal position
        need(count)
        out.extend(payload[position:position + count])
        position += count

    try:
        while position < size and len(out) < limit:
            opcode = payload[position]
            if opcode < 0x80:
                need(2)
                second = payload[position + 1]
                position += 2
                literals(opcode & 0x03)
                offset = ((opcode & 0x60) << 3) + second + 1
                length = ((opcode & 0x1C) >> 2) + 3
            elif opcode < 0xC0:
                need(3)
                second, third = payload[position + 1], payload[position + 2]
                position += 3
                literals(second >> 6)
                offset = ((second & 0x3F) << 8) + third + 1
                length = (opcode & 0x3F) + 4
            elif opcode < 0xE0:
                need(4)
                second, third, fourth = payload[position + 1:position + 4]
                position += 4
                literals(opcode & 0x03)
                offset = ((opcode & 0x10) << 12) + (second << 8) + third + 1
                length = ((opcode & 0x0C) << 6) + fourth + 5
            elif opcode < 0xFC:
                position += 1
                literals(((opcode & 0x1F) << 2) + 4)
                continue
            else:
                position += 1
                literals(opcode & 0x03)
                break
            start = len(out) - offset
            if start < 0:
                raise RefpackError(
                    "%s copies %d byte(s) from %d back, but only %d byte(s) "
                    "have been produced; the stream is damaged or is not "
                    "RefPack." % (what, length, offset, len(out))
                )
            if length <= offset:
                # The common case: source and destination do not overlap, so
                # one slice copy replaces a byte-at-a-time loop.  A whole-disc
                # census unpacks hundreds of megabytes through here.
                out += out[start:start + length]
            else:
                # An overlapping copy is a repeat with period *offset*, so it
                # is one multiplication rather than a loop.
                piece = bytes(out[start:start + offset])
                out += (piece * (-(-length // offset)))[:length]
    except _OutOfInput as short:
        if not bounded:
            raise RefpackError(
                "%s ends after %d byte(s) with an opcode still wanting %d "
                "more; the stream is truncated."
                % (what, size, int(short.args[0]))
            ) from None

    if max_output is not None:
        return bytes(out[:max_output])
    if len(out) != expected_size:
        raise RefpackError(
            "%s unpacked to %d byte(s) and its header declares %d; the stream "
            "and its own header disagree." % (what, len(out), expected_size)
        )
    return bytes(out)


# --------------------------------------------------------------------------
# The archive
# --------------------------------------------------------------------------

#: What a caller hands this reader: a bytes-like object (``bytes``,
#: ``memoryview``, ``mmap.mmap`` — anything sliceable), or a callable that
#: returns *size* bytes from an absolute offset.  The callable is how a disc
#: is read: an archive 122 MB into an ISO is opened without the ISO, or the
#: archive, being copied into memory.
RangeReader = Callable[[int, int], bytes]
BigSource = Union[bytes, bytearray, memoryview, RangeReader]


class _Window:
    """Bounded random access to the bytes one archive occupies."""

    __slots__ = ("_read", "base", "size")

    def __init__(self, source: "BigSource | _Window", base: int,
                 size: Optional[int]) -> None:
        if isinstance(source, _Window):
            # A nested archive: keep reading through the outer window rather
            # than copying the bytes it covers.
            self._read = source._read
            self.base = source.base + base
            self.size = int(source.size if size is None else size)
            return
        if callable(source):
            _require(size is not None,
                     "a ranged reader has no length of its own: pass size= "
                     "with the number of bytes the archive occupies.")
            self._read = source
        else:
            data = source
            available = len(data) - base
            if size is None:
                size = available
            _require(
                size <= available,
                "the archive is %d byte(s) from offset %d and only %d were "
                "handed to this reader." % (size, base, max(available, 0)),
            )

            def _slice(offset: int, length: int, _data=data) -> bytes:
                return bytes(_data[offset:offset + length])

            self._read = _slice
        self.base = base
        self.size = int(size or 0)

    def read(self, offset: int, length: int, what: str = "the archive") -> bytes:
        if length <= 0:
            return b""
        if offset < 0 or offset + length > self.size:
            raise TruncatedArchive(
                "%s wants %d byte(s) at +%d, past the %d byte(s) the archive "
                "occupies." % (what, length, offset, self.size)
            )
        chunk = self._read(self.base + offset, length)
        if len(chunk) < length:
            raise TruncatedArchive(
                "%s wants %d byte(s) at +%d and the source returned %d."
                % (what, length, offset, len(chunk))
            )
        return chunk

    def sub(self, offset: int, length: int) -> "_Window":
        window = _Window.__new__(_Window)
        window._read = self._read
        window.base = self.base + offset
        window.size = length
        return window


@dataclass(frozen=True)
class BigEntry:
    """One row of the entry table: where an entry is, and what it is called."""

    index: int
    #: Relative to the start of the archive, not to the end of the table.
    offset: int
    size: int
    name: str

    @property
    def end(self) -> int:
        return self.offset + self.size

    @property
    def empty(self) -> bool:
        return self.size == 0

    @property
    def extension(self) -> str:
        """The name's lower-case extension, or ``""`` when it has none."""
        tail = self.name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        return tail.rsplit(".", 1)[-1].lower() if "." in tail else ""


class BigArchive:
    """A parsed EA ``BIG`` archive.  Reads; never mutates its source."""

    def __init__(self, source: BigSource, *, size: Optional[int] = None,
                 base: int = 0, name: str = "this archive") -> None:
        self.name = name
        window = _Window(source, base, size)
        self._window = window
        self.length = window.size
        _require(
            window.size >= BIG_HEADER_SIZE,
            "%s is %d byte(s); an EA BIG archive's header alone is %d."
            % (name, window.size, BIG_HEADER_SIZE),
        )
        header = window.read(0, BIG_HEADER_SIZE, "the header")
        magic = header[:4]
        if magic == BIG4_MAGIC:
            raise UnsupportedArchive(
                "%s is a BIG4 archive. BIG4 stores its integers little-endian "
                "throughout, and no disc this reader has been measured "
                "against carries one, so it is refused by name rather than "
                "read with BIGF's mixed byte order." % name
            )
        if header[:2] == C0FB_HEAD:
            raise UnsupportedArchive(
                "%s is a whole archive stored as one RefPack stream (the "
                "C0 FB shape). Decompress it with refpack_decompress() and "
                "open the result; no disc measured here carries one, so this "
                "reader does not do it silently." % name
            )
        _require(
            magic == BIGF_MAGIC,
            "%s is not an EA BIG archive: it starts with %r, not %r."
            % (name, magic, BIGF_MAGIC),
        )
        self.format = magic.decode("ascii")
        declared_le, = struct.unpack_from("<I", header, 4)
        declared_be, = struct.unpack_from(">I", header, 4)
        entry_count, index_bytes = struct.unpack_from(">II", header, 8)
        if declared_le == window.size:
            self.size_endian, self.declared_size = "little", declared_le
        elif declared_be == window.size:
            self.size_endian, self.declared_size = "big", declared_be
        else:
            # Neither matched.  Little-endian is what every measured archive
            # uses, so that is what is reported, together with the mismatch --
            # a short rip is a fact about the source, not a reason to refuse.
            self.size_endian, self.declared_size = "little (declared)", declared_le
        self.size_mismatch = self.declared_size - window.size
        _require(
            0 < entry_count <= BIG_MAX_ENTRIES,
            "%s declares %d entries, which is not a count this reader will "
            "act on (1..%d). Reading the header with the wrong byte order "
            "produces exactly this." % (name, entry_count, BIG_MAX_ENTRIES),
        )
        _require(
            BIG_HEADER_SIZE <= index_bytes <= min(window.size, BIG_MAX_INDEX_BYTES),
            "%s declares a %d-byte header-and-table in a %d-byte archive."
            % (name, index_bytes, window.size),
        )
        self.entry_count = entry_count
        self.index_bytes = index_bytes
        self.entries: Tuple[BigEntry, ...] = tuple(
            self._read_table(window, entry_count, index_bytes))
        _require(
            len(self.entries) == entry_count,
            "%s declares %d entries and its table holds %d; the table is "
            "truncated or the name of entry %d has no terminator."
            % (name, entry_count, len(self.entries), len(self.entries)),
        )
        by_name: Dict[str, int] = {}
        duplicates = 0
        for entry in self.entries:
            if entry.name in by_name:
                duplicates += 1
            else:
                by_name[entry.name] = entry.index
        self._by_name = by_name
        #: How many names appear more than once.  Lookup by name returns the
        #: first; the count is exposed so a caller knows when that matters.
        self.duplicate_names = duplicates
        self._cache: Dict[int, bytes] = {}

    # -- the table ---------------------------------------------------------

    @staticmethod
    def _read_table(window: _Window, entry_count: int,
                    index_bytes: int) -> Iterator[BigEntry]:
        table = window.read(BIG_HEADER_SIZE, index_bytes - BIG_HEADER_SIZE,
                            "the entry table")
        position = 0
        for index in range(entry_count):
            if position + BIG_ROW_FIXED > len(table):
                return
            offset, size = struct.unpack_from(">II", table, position)
            position += BIG_ROW_FIXED
            terminator = table.find(b"\x00", position)
            if terminator < 0:
                return
            name = table[position:terminator].decode("latin-1")
            position = terminator + 1
            yield BigEntry(index, offset, size, name)

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self) -> Iterator[BigEntry]:
        return iter(self.entries)

    def index_of(self, name: str) -> int:
        """The index of the entry called *name*.

        Names are matched exactly as stored.  A miss is a refusal that says
        how many entries there are, never ``-1``.
        """
        try:
            return self._by_name[name]
        except KeyError:
            raise BigError(
                "%s has no entry called %r; it has %d (use entry names from "
                "iter_entries())." % (self.name, name, len(self.entries))
            ) from None

    def _check(self, index: int) -> BigEntry:
        if not 0 <= index < len(self.entries):
            raise BigError(
                "entry %d does not exist: %s has %d (0..%d)."
                % (index, self.name, len(self.entries), len(self.entries) - 1)
            )
        return self.entries[index]

    def entry(self, key: "int | str") -> BigEntry:
        """The table row for an entry, by index or by name."""
        return self._check(self.index_of(key) if isinstance(key, str) else key)

    # -- payloads ----------------------------------------------------------

    def stored(self, key: "int | str", *, limit: Optional[int] = None) -> bytes:
        """An entry exactly as it sits in the archive, still packed.

        *limit* reads only the first that many bytes, which is what makes a
        30 MB entry classifiable for the price of 1 KB.
        """
        entry = self.entry(key)
        if entry.size == 0:
            return b""
        want = entry.size if limit is None else min(entry.size, limit)
        return self._window.read(entry.offset, want,
                                 "entry %d (%r)" % (entry.index, entry.name))

    def is_compressed(self, key: "int | str") -> bool:
        """Do this entry's stored bytes begin a RefPack stream?

        The table carries no compression flag; the payload's own first two
        bytes are the only signal, so this reads them.
        """
        entry = self.entry(key)
        if entry.size < 2:
            return False
        return is_refpack(self.stored(entry.index, limit=2))

    def compression(self, key: "int | str") -> Optional[RefpackHeader]:
        """The entry's RefPack header, or ``None`` when it is stored plain."""
        entry = self.entry(key)
        if entry.size < 5:
            return None
        return refpack_header(self.stored(entry.index, limit=16))

    def member(self, key: "int | str", *,
               max_output: Optional[int] = None) -> bytes:
        """An entry's bytes, RefPack-decoded when the entry is packed.

        With *max_output* set, only that many bytes are produced and nothing
        is cached — the shape a census wants.  Without it the whole entry is
        decoded and kept, because a caller that asks twice usually means it.
        """
        entry = self._check(self.index_of(key) if isinstance(key, str) else key)
        if max_output is None:
            cached = self._cache.get(entry.index)
            if cached is not None:
                return cached
        if entry.size == 0:
            return b""
        header = self.compression(entry.index)
        if header is None:
            payload = self.stored(entry.index, limit=max_output)
        else:
            # RefPack has no block table, so a decode always starts at the
            # stream's front -- but a *bounded* decode only ever needs the
            # front, so a bounded read of the stored bytes is enough and a
            # 30 MB entry costs kilobytes to classify.
            stored_limit = (None if max_output is None
                            else max(1024, 4 * max_output + 32))
            payload = refpack_decompress(
                self.stored(entry.index, limit=stored_limit),
                header.decompressed_size, max_output=max_output,
                what="entry %d (%r) of %s" % (entry.index, entry.name, self.name))
        if max_output is None:
            self._cache[entry.index] = payload
        return payload

    def entry_format(self, key: "int | str") -> str:
        """Name an entry's first-level format, after decompression.

        Returns :data:`FORMAT_EMPTY` for a zero-length entry,
        :data:`FORMAT_UNCLASSIFIED` when no magic claims the head — a measured
        answer — and :data:`FORMAT_UNDECODABLE` when the entry is a RefPack
        stream this reader could not follow, which is a different answer and
        must not render the same.

        Classification is delegated to :func:`ea_terf.identify_member`, the
        same magic table the ``TERF`` reader uses, so that one head is never
        called ``SHPS`` on one disc and something else on another.
        """
        entry = self.entry(key)
        if entry.size == 0:
            return FORMAT_EMPTY
        try:
            head = self.member(entry.index, max_output=IDENTIFY_HEAD)
        except (BigError, IndexError):
            return FORMAT_UNDECODABLE
        return ea_terf.identify_member(head) or FORMAT_UNCLASSIFIED

    def iter_entries(self) -> Iterator[BigEntry]:
        """Every row of the table, in table order."""
        return iter(self.entries)

    def iter_members(self, *, max_output: Optional[int] = None
                     ) -> Iterator[Tuple[BigEntry, bytes]]:
        """``(row, bytes)`` for every entry, decompressed, in table order.

        With *max_output* this is a census pass: it never holds more than one
        entry's head at a time and never caches, so an archive far larger than
        memory walks in constant space.
        """
        for entry in self.entries:
            yield entry, self.member(entry.index, max_output=max_output)

    def nested(self, key: "int | str") -> "BigArchive":
        """Open an entry that is itself a ``BIG`` archive.

        A **stored** nested archive is opened in place through the same
        ranged reader, so nothing is copied; a **packed** one has to be
        decompressed first and is opened over those bytes.
        """
        entry = self.entry(key)
        label = "%s!%s" % (self.name, entry.name)
        if self.is_compressed(entry.index):
            return BigArchive(self.member(entry.index), name=label)
        return BigArchive(self._window.sub(entry.offset, entry.size),
                          size=entry.size, name=label)

    # -- layout ------------------------------------------------------------

    @property
    def table_end(self) -> int:
        """Where the entry table stops, per the header's own declaration."""
        return self.index_bytes

    def alignment(self) -> int:
        """The largest power of two that divides every non-empty offset.

        **Measured, not declared.**  Nothing in the header names an alignment,
        so this is a property of the archive in hand: 64 on the Madden and
        NCAA dashboard archives, and it is reported rather than enforced.
        Returns 1 when the offsets share no alignment at all.
        """
        common = 0
        for entry in self.entries:
            if entry.size:
                common |= entry.offset
        if common == 0:
            return 1
        return common & -common

    def slot_bytes(self, key: "int | str") -> int:
        """How many bytes an entry may occupy before the next one moves.

        The gap to the next payload in **offset order** (not table order —
        the two agree on every archive measured, and this does not depend on
        it), or to the end of the archive for the last one.
        """
        entry = self.entry(key)
        starts = sorted({other.offset for other in self.entries if other.size}
                        | {self.length})
        for start in starts:
            if start > entry.offset:
                return start - entry.offset
        return max(self.length - entry.offset, 0)

    def layout_notes(self) -> List[str]:
        """Every way this archive departs from the shape a rewrite assumes.

        Empty for an ordinary archive.  A caller that intends to replace an
        entry should read this first: an archive that already overlaps itself
        will not survive being rebuilt from the rules.
        """
        notes: List[str] = []
        if self.size_mismatch:
            notes.append(
                "the header declares %d byte(s) and the source holds %d"
                % (self.declared_size, self.length))
        ordered = sorted((e for e in self.entries if e.size),
                         key=lambda e: e.offset)
        previous: Optional[BigEntry] = None
        for entry in ordered:
            if entry.offset < self.index_bytes:
                notes.append(
                    "entry %d (%r) starts at +%d, inside the %d-byte table"
                    % (entry.index, entry.name, entry.offset, self.index_bytes))
            if entry.end > self.length:
                notes.append(
                    "entry %d (%r) runs to +%d, past the archive's %d bytes"
                    % (entry.index, entry.name, entry.end, self.length))
            if previous is not None and entry.offset < previous.end:
                notes.append(
                    "entry %d (%r) starts at +%d, inside entry %d (%r) which "
                    "ends at +%d" % (entry.index, entry.name, entry.offset,
                                     previous.index, previous.name, previous.end))
            previous = entry
        if self.duplicate_names:
            notes.append("%d entry name(s) appear more than once"
                         % self.duplicate_names)
        return notes

    # -- census ------------------------------------------------------------

    def format_histogram(self, *, follow_nested: bool = False) -> Dict[str, int]:
        """``{format id: count}`` over every entry, after decompression."""
        counts: Dict[str, int] = {}
        for entry in self.entries:
            name = self.entry_format(entry.index)
            counts[name] = counts.get(name, 0) + 1
            if follow_nested and name == "BIGF":
                try:
                    inner = self.nested(entry.index).format_histogram()
                except BigError:
                    counts["nested-refused"] = counts.get("nested-refused", 0) + 1
                    continue
                for key, value in inner.items():
                    counts["nested:" + key] = counts.get("nested:" + key, 0) + value
        return counts

    def extension_histogram(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for entry in self.entries:
            key = entry.extension or "(none)"
            counts[key] = counts.get(key, 0) + 1
        return counts

    def compressed_count(self) -> int:
        """How many entries store their bytes as a RefPack stream."""
        return sum(1 for entry in self.entries if self.is_compressed(entry.index))

    def summary(self) -> Dict[str, object]:
        """Counts, sizes and the layout verdict, with no entry bytes in it."""
        return {
            "name": self.name,
            "format": self.format,
            "size_endian": self.size_endian,
            "declared_size": self.declared_size,
            "length": self.length,
            "size_mismatch": self.size_mismatch,
            "entries": len(self.entries),
            "index_bytes": self.index_bytes,
            "alignment": self.alignment(),
            "duplicate_names": self.duplicate_names,
            "payload_bytes": sum(entry.size for entry in self.entries),
            "empty_entries": sum(1 for entry in self.entries if entry.empty),
            "layout_notes": self.layout_notes(),
        }


def parse_big(source: BigSource, *, size: Optional[int] = None, base: int = 0,
              name: str = "this archive") -> BigArchive:
    """Parse *source* as an EA ``BIG`` archive."""
    return BigArchive(source, size=size, base=base, name=name)


def declared_length(head: "bytes | memoryview") -> int:
    """What an archive's first 16 bytes say its total length is.

    For reading an archive out of a larger file before its length is known.
    The size word is little-endian in every ``BIGF`` measured; a caller that
    gets an implausible answer should read the header both ways with
    :class:`BigArchive`, which reports which one matched.
    """
    head = bytes(head[:BIG_HEADER_SIZE])
    _require(len(head) >= BIG_HEADER_SIZE,
             "an archive's length is declared in its first %d bytes and only "
             "%d were handed to this function." % (BIG_HEADER_SIZE, len(head)))
    _require(head[:4] == BIGF_MAGIC,
             "this is not a BIGF archive: it starts with %r." % head[:4])
    return struct.unpack_from("<I", head, 4)[0]


# --------------------------------------------------------------------------
# Building -- synthetic archives only, so the reader can be tested
# --------------------------------------------------------------------------

def build_big(entries: Sequence[Tuple[str, bytes]], *,
              alignment: int = 64) -> bytes:
    """Build a ``BIGF`` archive from ``(name, payload)`` pairs.

    This exists so the reader can be proved on bytes a test built, not on a
    disc a contributor may not own.  It reproduces the shape every measured
    archive has — mixed byte order, a variable-length table, payloads in
    table order aligned outward from the end of the table — and it is
    **not** a writer for a retail archive: see :func:`rewrite_entry`.
    """
    _require(alignment > 0 and (alignment & (alignment - 1)) == 0,
             "alignment %d is not a power of two." % alignment)
    _require(bool(entries), "a BIG archive has at least one entry.")
    table = bytearray()
    for name, _payload in entries:
        encoded = name.encode("latin-1")
        _require(b"\x00" not in encoded,
                 "entry name %r contains a NUL, which terminates a name." % name)
        table += b"\x00" * BIG_ROW_FIXED + encoded + b"\x00"
    index_bytes = BIG_HEADER_SIZE + len(table)
    cursor = ((index_bytes + alignment - 1) // alignment) * alignment
    offsets: List[int] = []
    for _name, payload in entries:
        offsets.append(cursor)
        cursor += max(len(payload), 0)
        cursor = ((cursor + alignment - 1) // alignment) * alignment
    total = cursor
    position = 0
    for index, (name, payload) in enumerate(entries):
        struct.pack_into(">II", table, position, offsets[index], len(payload))
        position += BIG_ROW_FIXED + len(name.encode("latin-1")) + 1
    out = bytearray(BIGF_MAGIC + struct.pack("<I", total)
                    + struct.pack(">II", len(entries), index_bytes) + table)
    out += b"\x00" * (total - len(out))
    for index, (_name, payload) in enumerate(entries):
        out[offsets[index]:offsets[index] + len(payload)] = payload
    return bytes(out)


# --------------------------------------------------------------------------
# Writing -- what a bounded writer would need, and why there is not one
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class EntryRewritePlan:
    """What replacing one entry would cost, priced without writing anything."""

    index: int
    name: str
    payload_bytes: int
    previous_stored_size: int
    #: The gap to the next payload: how far this entry may grow before
    #: anything after it moves.
    slot_bytes: int
    fits_slot: bool
    #: True when the entry the archive holds today is RefPack-packed, so a
    #: same-size replacement needs an encoder this module does not have.
    source_compressed: bool
    #: Everything a writer would still have to do, one sentence each.  Empty
    #: only when a same-size stored replacement would be a pure byte swap.
    blockers: Tuple[str, ...]
    note: str

    def as_dict(self) -> Dict[str, object]:
        return {
            "index": self.index,
            "name": self.name,
            "payload_bytes": self.payload_bytes,
            "previous_stored_size": self.previous_stored_size,
            "slot_bytes": self.slot_bytes,
            "fits_slot": self.fits_slot,
            "source_compressed": self.source_compressed,
            "blockers": list(self.blockers),
            "note": self.note,
        }


def plan_entry_rewrite(archive: BigArchive, key: "int | str",
                       payload: bytes) -> EntryRewritePlan:
    """Price replacing one entry's bytes.  Writes nothing.

    The bounded shape — the only one worth building first — replaces an
    entry **inside the slot it already owns**: the payload is at most
    ``slot_bytes`` long, the entry's ``size`` word in the table is rewritten,
    every other row keeps its offset, and the archive keeps its length.  That
    changes two byte ranges and no other entry moves.

    Anything larger relocates every payload after it and rewrites every row
    from that point on.  The plan says which case a caller is in, and
    :attr:`EntryRewritePlan.blockers` lists what is still missing either way.
    """
    entry = archive.entry(key)
    payload = bytes(payload)
    slot = archive.slot_bytes(entry.index)
    fits = len(payload) <= slot
    compressed = archive.is_compressed(entry.index)
    blockers: List[str] = []
    if not fits:
        blockers.append(
            "the replacement is %d byte(s) and entry %d owns %d: every entry "
            "after it would move and every table row after it would be "
            "rewritten, which no code here does."
            % (len(payload), entry.index, slot))
    if compressed:
        blockers.append(
            "entry %d is stored as a RefPack stream and there is no RefPack "
            "encoder here, so a replacement can only be written back "
            "uncompressed -- which is larger, and the game has never been "
            "watched loading a plain entry where the disc packed one."
            % entry.index)
    blockers.append(
        "no archive rebuilt by this project has been loaded by any game, so "
        "whether the header's length word, the table's offsets or something "
        "outside the archive is also checked is unmeasured.")
    if fits and not compressed:
        note = ("%d byte(s) into the %d-byte slot entry %d owns: a writer "
                "would change the entry's size word in the table and the "
                "bytes at +%d, and nothing else."
                % (len(payload), slot, entry.index, entry.offset))
    elif fits:
        note = ("%d byte(s) fit the %d-byte slot entry %d owns, but the disc "
                "stores that entry packed."
                % (len(payload), slot, entry.index))
    else:
        note = ("%d byte(s) do not fit the %d-byte slot entry %d owns."
                % (len(payload), slot, entry.index))
    return EntryRewritePlan(
        index=entry.index, name=entry.name, payload_bytes=len(payload),
        previous_stored_size=entry.size, slot_bytes=slot, fits_slot=fits,
        source_compressed=compressed, blockers=tuple(blockers), note=note,
    )


def rewrite_entry(archive: BigArchive, key: "int | str", payload: bytes) -> bytes:
    """Refuse to replace an entry, and say what a writer would need.

    There is no ``BIG`` writer in this project.  This function exists so that
    a caller reaching for one is answered by a sentence instead of by an
    ``AttributeError``, and so that the shape of the writer that *should* be
    built is written down where it will be read: see
    :func:`plan_entry_rewrite`, which prices the bounded case.
    """
    plan = plan_entry_rewrite(archive, key, payload)
    raise BigError(
        "this module reads EA BIG archives and does not write them. "
        "Replacing entry %d (%r) would need: %s Nothing was changed."
        % (plan.index, plan.name, " ".join(plan.blockers))
    )


__all__ = [
    "BIGF_MAGIC",
    "BIG4_MAGIC",
    "BIG_HEADER_SIZE",
    "BIG_MAX_ENTRIES",
    "BIG_MAX_INDEX_BYTES",
    "BIG_ROW_FIXED",
    "C0FB_HEAD",
    "FORMAT_EMPTY",
    "FORMAT_TDB",
    "FORMAT_TEXT",
    "FORMAT_UNCLASSIFIED",
    "FORMAT_UNDECODABLE",
    "IDENTIFY_HEAD",
    "REFPACK_FAMILY",
    "REFPACK_FAMILY_MASK",
    "REFPACK_FLAG_COMPRESSED_SIZE",
    "REFPACK_FLAG_LONG",
    "REFPACK_MAX_OFFSET",
    "REFPACK_SIGNATURE",
    "BigArchive",
    "BigEntry",
    "BigError",
    "BigSource",
    "EntryRewritePlan",
    "RangeReader",
    "RefpackError",
    "RefpackHeader",
    "TruncatedArchive",
    "UnsupportedArchive",
    "build_big",
    "declared_length",
    "is_refpack",
    "parse_big",
    "plan_entry_rewrite",
    "refpack_decompress",
    "refpack_header",
    "rewrite_entry",
]

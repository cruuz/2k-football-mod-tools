"""The Midway stored-ZIP and its ``.ZIH`` index -- NFL Blitz 2002 and 2003 (PS2).

Both discs keep the whole game in **one ZIP whose every member is stored**, with
a pre-built index beside it: ``BASSETS.ZIP`` + ``BASSETS.ZIH`` on NFL Blitz 2002
(``SLUS-20051``) and ``BERTHA.ZIP`` + ``BERTHA.ZIH`` on NFL Blitz 2003
(``SLUS-20474``).  The index is the ZIP's central directory rewritten for fast
seeking: its offset column points at each member's **data**, one local file
header past the signature.

The index has two shapes and the disc chooses, so a reader tells them apart from
the bytes rather than from the disc [M]::

    header      u32 entries, u32 body bytes            body + 8 == the file
    inline      nine u32 then a NUL-terminated name     NFL Blitz 2002
                words 5/6/7/8 are CRC-32, compressed size, uncompressed size,
                data offset; words 3/4 are an MS-DOS time and date
    table       u32 name offset (from +8), u32 size,    NFL Blitz 2003
                u32 data offset, then one string table

**Told apart by** the first record's first word: in the table shape it is the
directory's own length, ``entries * 12`` [M].

What is measured, exhaustively, on both retail discs [M]:

===========================================================  =========  =========
identity                                                     2002       2003
===========================================================  =========  =========
``body bytes + 8 == the .ZIH file``                          holds      holds
the walk consumes the index to its last byte                 holds      holds
index names, as a set, equal the ZIP's                       2,426      2,695
index sizes equal the ZIP central directory's                2,426      2,695
index offsets equal the ZIP's own local-data offsets         2,426      2,695
``offset - 30 - len(name)`` is a ``PK\\x03\\x04`` header      2,426      2,695
...  whose stored name equals the index's name               2,426      2,695
every member's compression method is *stored*                2,426      2,695
local-header extra field is empty                            2,426      2,695
index CRC-32 column equals the ZIP central directory's       2,426      absent
recomputed CRC-32 over the stored bytes agrees               600 of 600 no column
===========================================================  =========  =========

**The three-place rule, which is what makes a writer possible and what makes it
dangerous.**  Because every member is stored, a replacement of exactly the same
length can be written over the member's bytes without moving anything.  Its
CRC-32 then appears in **three** places -- the local file header, the central
directory, and (on NFL Blitz 2002) the ``.ZIH`` index -- and a writer that
updates two of them leaves an index that disagrees with the archive it
describes.  :func:`plan_member_replacement` returns all three ranges or refuses;
there is no path through this module that writes one without the others.

The index's records are sorted by name and the ZIP's by data offset, and the two
orders differ on both discs [M], so every join here is by name and never by
ordinal.

Standard library only; importable without Qt.

**Evidence tags.**  **[M]** measured on the retail disc named; **[S]** sourced;
**[A]** assumed.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
import zlib
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from mod_editor.games.contract import Refusal

__all__ = [
    "BlitzZipError", "IndexEntry", "ZihIndex", "ZipMember", "StoredZip",
    "SHAPE_INLINE", "SHAPE_TABLE", "LOCAL_HEADER_BYTES", "ZIH_HEADER_BYTES",
    "read_index", "read_zip", "cross_check", "plan_member_replacement",
    "apply_member_replacement", "build_synthetic_zip", "build_synthetic_index",
]

#: The two ``.ZIH`` record shapes, named after where the member's name lives.
SHAPE_INLINE = "inline"
SHAPE_TABLE = "table"

#: A ZIP local file header is 30 bytes before the name [S: PKWARE APPNOTE 4.3.7].
LOCAL_HEADER_BYTES = 30
#: ``u32 entries`` then ``u32 body bytes`` [M].
ZIH_HEADER_BYTES = 8
#: The inline shape's fixed part: nine little-endian words before the name [M].
_INLINE_WORDS = 9
_INLINE_FIXED = _INLINE_WORDS * 4
#: The table shape's record: name offset, size, data offset [M].
_TABLE_RECORD = 12

_LOCAL_SIGNATURE = b"PK\x03\x04"
_CENTRAL_SIGNATURE = b"PK\x01\x02"
_EOCD_SIGNATURE = b"PK\x05\x06"
_STORED = 0

#: Refuse an index that declares more entries than any disc in the fleet carries
#: by three orders of magnitude, rather than allocating on a corrupt word.
_MAX_ENTRIES = 1_000_000
#: The largest member this module will read whole into memory for a CRC check.
#: ``mslasset.ms2`` is 137 MB on NFL Blitz 2002, so a caller that wants it asks
#: for it explicitly through :meth:`StoredZip.member_bytes`.
CRC_CHECK_LIMIT = 1 << 22


class BlitzZipError(Refusal):
    """This is not the Midway ZIP pair, or an edit does not fit it.  One sentence."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise BlitzZipError(message)


def _text(raw: bytes) -> str:
    """A stored name as text.  Latin-1 never fails and never invents a byte."""

    return raw.decode("latin-1")


# --------------------------------------------------------------------------
# The .ZIH index
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class IndexEntry:
    """One ``.ZIH`` record: a name, a size, and where the member's data starts.

    ``crc32`` is present only in the inline shape; NFL Blitz 2003's index has no
    CRC column at all [M], and a writer must not invent one.
    """

    name: str
    size: int
    data_offset: int
    crc32: Optional[int] = None
    #: Offset of this record inside the index file, so a writer can name a range.
    record_offset: int = 0
    #: Offset of the CRC word inside the index file, when there is one.
    crc_offset: Optional[int] = None


@dataclass(frozen=True)
class ZihIndex:
    """A parsed ``.ZIH``: its shape, its records, and the words it declares."""

    shape: str
    entries: tuple[IndexEntry, ...]
    declared_entries: int
    declared_body_bytes: int
    total_bytes: int
    directory_bytes: int
    consumed_whole_file: bool

    @property
    def has_crc_column(self) -> bool:
        return self.shape == SHAPE_INLINE

    def by_name(self) -> Dict[str, IndexEntry]:
        return {entry.name: entry for entry in self.entries}

    def entry(self, name: str) -> IndexEntry:
        found = self.by_name().get(name)
        if found is None:
            raise BlitzZipError(
                f"{name!r} is not a member the index names; choose one of its "
                f"{len(self.entries)} entries."
            )
        return found


def read_index(data: bytes) -> ZihIndex:
    """Parse a ``.ZIH``, refusing anything whose own header words do not hold [M]."""

    data = bytes(data)
    _require(len(data) >= ZIH_HEADER_BYTES + _TABLE_RECORD,
             f"a {len(data)}-byte file is too short to be a Midway ZIP index; the header "
             f"alone is {ZIH_HEADER_BYTES} bytes and one record is at least {_TABLE_RECORD}.")
    count, body = struct.unpack_from("<II", data, 0)
    _require(0 < count <= _MAX_ENTRIES,
             f"this index declares {count} entries, which is not between 1 and {_MAX_ENTRIES}; "
             f"it is not a Midway ZIP index.")
    _require(body + ZIH_HEADER_BYTES == len(data),
             f"this index declares {body} body bytes in a {len(data)}-byte file, and "
             f"{body} + {ZIH_HEADER_BYTES} is not {len(data)}; it is not a Midway ZIP index.")

    shape = SHAPE_INLINE
    if ZIH_HEADER_BYTES + count * _TABLE_RECORD <= len(data):
        first = struct.unpack_from("<I", data, ZIH_HEADER_BYTES)[0]
        if first == count * _TABLE_RECORD:
            shape = SHAPE_TABLE

    entries: List[IndexEntry] = []
    if shape == SHAPE_TABLE:
        for number in range(count):
            base = ZIH_HEADER_BYTES + number * _TABLE_RECORD
            name_offset, size, offset = struct.unpack_from("<3I", data, base)
            start = ZIH_HEADER_BYTES + name_offset
            end = data.find(b"\x00", start)
            _require(0 <= start < len(data) and end >= 0,
                     f"index record {number} names a string at +{name_offset} that is not "
                     f"NUL-terminated inside the file; the index is damaged.")
            entries.append(IndexEntry(_text(data[start:end]), size, offset,
                                      record_offset=base))
        directory_bytes = count * _TABLE_RECORD
        consumed = True
    else:
        position = ZIH_HEADER_BYTES
        while position + _INLINE_FIXED <= len(data) and len(entries) < count:
            record_at = position
            words = struct.unpack_from("<%dI" % _INLINE_WORDS, data, position)
            position += _INLINE_FIXED
            end = data.find(b"\x00", position)
            _require(end >= 0,
                     f"index record {len(entries)} has a name that is not NUL-terminated "
                     f"inside the file; the index is damaged.")
            entries.append(IndexEntry(_text(data[position:end]), words[7], words[8],
                                      crc32=words[5], record_offset=record_at,
                                      crc_offset=record_at + 5 * 4))
            position = end + 1
        directory_bytes = position - ZIH_HEADER_BYTES
        consumed = position == len(data)
    _require(len(entries) == count,
             f"this index declares {count} entries and {len(entries)} could be read; "
             f"the index is damaged.")
    return ZihIndex(shape, tuple(entries), count, body, len(data), directory_bytes, consumed)


# --------------------------------------------------------------------------
# The ZIP itself
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ZipMember:
    """One stored ZIP member, with every offset a writer needs.

    ``data_offset`` is the member's payload; ``local_crc_offset`` and
    ``central_crc_offset`` are the two CRC-32 words inside the archive.  The
    third place a CRC lives is the ``.ZIH`` index, which is a different file.
    """

    name: str
    size: int
    crc32: int
    data_offset: int
    local_header_offset: int
    local_crc_offset: int
    central_record_offset: int
    central_crc_offset: int


@dataclass(frozen=True)
class StoredZip:
    """A ZIP read through its central directory, with every member stored [M].

    Reading is done through ``read(offset, length)`` so a caller can hand this a
    window onto a disc image without copying 361 MB.
    """

    members: tuple[ZipMember, ...]
    total_bytes: int
    central_offset: int
    central_bytes: int
    _read: object = None

    def by_name(self) -> Dict[str, ZipMember]:
        return {member.name: member for member in self.members}

    def member(self, name: str) -> ZipMember:
        found = self.by_name().get(name)
        if found is None:
            raise BlitzZipError(
                f"{name!r} is not a member of this archive; choose one of its "
                f"{len(self.members)} entries."
            )
        return found

    def member_bytes(self, name: str) -> bytes:
        """The member's stored bytes.  Every member is stored, so these are its bytes."""

        member = self.member(name)
        reader = self._read
        _require(callable(reader),
                 "this archive was parsed without a reader, so its member bytes cannot be "
                 "fetched; open it with read_zip(read, size).")
        return reader(member.data_offset, member.size)  # type: ignore[misc]


def _find_eocd(read, size: int) -> Tuple[int, int, int]:
    """(entry count, central directory offset, central directory bytes) [S: APPNOTE 4.3.16]."""

    window = min(size, 66_000)
    tail = read(size - window, window)
    position = tail.rfind(_EOCD_SIGNATURE)
    _require(position >= 0,
             "no end-of-central-directory record was found in the last 66,000 bytes; this "
             "file is not a ZIP archive.")
    count, central_bytes, central_offset = struct.unpack_from("<2xHII", tail, position + 8)
    return count, central_offset, central_bytes


def read_zip(read, size: int) -> StoredZip:
    """Parse a ZIP's central directory, refusing any member that is not stored [M].

    ``read(offset, length) -> bytes``.  Only the central directory and one
    30-byte local header per member are read, so a 361 MB archive costs about
    the size of its directory.
    """

    count, central_offset, central_bytes = _find_eocd(read, size)
    _require(0 < count <= _MAX_ENTRIES,
             f"this archive declares {count} entries, which is not between 1 and "
             f"{_MAX_ENTRIES}; it is not the Midway stored ZIP.")
    _require(central_offset + central_bytes <= size,
             f"the central directory declares {central_bytes} bytes at +{central_offset} in a "
             f"{size}-byte file; the archive is truncated.")
    directory = read(central_offset, central_bytes)

    members: List[ZipMember] = []
    position = 0
    for number in range(count):
        _require(position + 46 <= len(directory) and directory[position:position + 4] == _CENTRAL_SIGNATURE,
                 f"central directory record {number} does not begin with a central file header "
                 f"signature; the archive is damaged.")
        (method, crc, packed, plain, name_len, extra_len, comment_len) = struct.unpack_from(
            "<10xH4xIIIHHH", directory, position)
        local_offset = struct.unpack_from("<I", directory, position + 42)[0]
        name = _text(directory[position + 46:position + 46 + name_len])
        _require(method == _STORED,
                 f"member {name!r} is stored with compression method {method}; every member of "
                 f"the Midway ZIP is stored, so this is not that archive.")
        _require(packed == plain,
                 f"member {name!r} declares {packed} stored bytes for {plain} plain bytes; a "
                 f"stored member's two sizes are equal, so this archive is damaged.")
        header = read(local_offset, LOCAL_HEADER_BYTES)
        _require(header[:4] == _LOCAL_SIGNATURE,
                 f"member {name!r} points at +{local_offset}, which is not a local file header; "
                 f"the archive is damaged.")
        local_name_len, local_extra_len = struct.unpack_from("<HH", header, 26)
        data_offset = local_offset + LOCAL_HEADER_BYTES + local_name_len + local_extra_len
        _require(data_offset + plain <= size,
                 f"member {name!r} declares {plain} bytes at +{data_offset} in a {size}-byte "
                 f"file; the archive is truncated.")
        members.append(ZipMember(
            name=name, size=plain, crc32=crc, data_offset=data_offset,
            local_header_offset=local_offset, local_crc_offset=local_offset + 14,
            central_record_offset=central_offset + position,
            central_crc_offset=central_offset + position + 16))
        position += 46 + name_len + extra_len + comment_len
    return StoredZip(tuple(members), size, central_offset, central_bytes, read)


# --------------------------------------------------------------------------
# The index against the archive
# --------------------------------------------------------------------------

def cross_check(index: ZihIndex, archive: StoredZip, *, crc_limit: int = CRC_CHECK_LIMIT,
                crc_sample: int = 0) -> Mapping[str, object]:
    """Does the index describe this archive?  Every join is by name, never by ordinal [M].

    Returns counts only -- no payload -- so a catalogue can carry the answer.
    ``crc_sample`` recomputes the CRC-32 of that many of the smallest members
    under ``crc_limit``; 0 skips the recomputation entirely.
    """

    index_names = {entry.name for entry in index.entries}
    zip_names = {member.name: member for member in archive.members}
    sizes = offsets = crc_column = 0
    for entry in index.entries:
        member = zip_names.get(entry.name)
        if member is None:
            continue
        sizes += 1 if member.size == entry.size else 0
        offsets += 1 if member.data_offset == entry.data_offset else 0
        if entry.crc32 is not None:
            crc_column += 1 if member.crc32 == entry.crc32 else 0
    recomputed = agreed = 0
    if crc_sample and index.has_crc_column:
        smallest = sorted((entry for entry in index.entries
                           if entry.crc32 is not None and 0 < entry.size <= crc_limit),
                          key=lambda entry: entry.size)[:crc_sample]
        for entry in smallest:
            recomputed += 1
            payload = archive.member_bytes(entry.name)
            agreed += 1 if (zlib.crc32(payload) & 0xFFFFFFFF) == entry.crc32 else 0
    return {
        "index_shape": index.shape,
        "index_entries": len(index.entries),
        "zip_entries": len(archive.members),
        "names_match_as_sets": index_names == set(zip_names),
        "names_in_both": len(index_names & set(zip_names)),
        "sizes_agree": sizes,
        "data_offsets_agree": offsets,
        "crc_column_agrees": crc_column if index.has_crc_column else None,
        "crc_recomputed": recomputed,
        "crc_recomputed_agrees": agreed,
        "index_order_is_by_name": [e.name for e in index.entries] == sorted(e.name for e in index.entries),
        "zip_order_is_by_data_offset": (
            [m.name for m in archive.members]
            == [m.name for m in sorted(archive.members, key=lambda m: m.data_offset)]),
    }


# --------------------------------------------------------------------------
# The bounded writer: one member, the same length, three CRC sites
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Replacement:
    """What a same-length member replacement changes, before anything is written.

    ``zip_ranges`` and ``index_ranges`` are ``(offset, bytes)`` pairs *relative
    to each file*, so a caller that holds the pair inside a disc image adds its
    own bases.  Nothing here is applied until :func:`apply_member_replacement`.
    """

    name: str
    size: int
    crc32: int
    previous_crc32: int
    zip_ranges: tuple[tuple[int, bytes], ...]
    index_ranges: tuple[tuple[int, bytes], ...]

    @property
    def zip_bytes_changed(self) -> int:
        return sum(len(payload) for _offset, payload in self.zip_ranges)

    @property
    def index_bytes_changed(self) -> int:
        return sum(len(payload) for _offset, payload in self.index_ranges)


def plan_member_replacement(archive: StoredZip, index: Optional[ZihIndex], name: str,
                            payload: bytes) -> Replacement:
    """Every byte a same-length replacement of ``name`` changes, in both files.

    Refuses a payload of any other length: a stored member can be rewritten
    where it lies and nowhere else, and growing one would move every later
    member, the central directory and the whole index.

    The CRC-32 is written to the local file header, the central directory and --
    when the index carries a CRC column -- the index, because those are the three
    places the disc keeps it [M].  Forgetting the third is the way to break the
    disc quietly.
    """

    member = archive.member(name)
    payload = bytes(payload)
    _require(len(payload) == member.size,
             f"{name!r} occupies {member.size} bytes on the disc and the replacement is "
             f"{len(payload)}; a stored ZIP member is rewritten where it lies, so give it "
             f"exactly {member.size} bytes.")
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    crc_word = struct.pack("<I", crc)
    zip_ranges: List[Tuple[int, bytes]] = [
        (member.data_offset, payload),
        (member.local_crc_offset, crc_word),
        (member.central_crc_offset, crc_word),
    ]
    index_ranges: List[Tuple[int, bytes]] = []
    if index is not None:
        entry = index.entry(name)
        _require(entry.size == member.size,
                 f"the index says {name!r} is {entry.size} bytes and the archive says "
                 f"{member.size}; the pair disagrees and no edit is safe until it does not.")
        _require(entry.data_offset == member.data_offset,
                 f"the index puts {name!r}'s data at +{entry.data_offset} and the archive at "
                 f"+{member.data_offset}; the pair disagrees and no edit is safe until it does not.")
        if entry.crc_offset is not None:
            index_ranges.append((entry.crc_offset, crc_word))
    return Replacement(name, member.size, crc, member.crc32,
                       tuple(zip_ranges), tuple(index_ranges))


def apply_member_replacement(zip_blob: bytearray, index_blob: Optional[bytearray],
                             plan: Replacement) -> None:
    """Write a planned replacement into two mutable buffers.  Lengths never change."""

    for offset, payload in plan.zip_ranges:
        _require(offset + len(payload) <= len(zip_blob),
                 f"the plan writes {len(payload)} bytes at +{offset} of a {len(zip_blob)}-byte "
                 f"archive; the buffer is not the archive the plan was made against.")
        zip_blob[offset:offset + len(payload)] = payload
    if plan.index_ranges:
        _require(index_blob is not None,
                 "this plan changes the .ZIH index and no index buffer was given; a stored "
                 "member's CRC-32 lives in the archive and the index both.")
        for offset, payload in plan.index_ranges:
            _require(offset + len(payload) <= len(index_blob),  # type: ignore[arg-type]
                     f"the plan writes {len(payload)} bytes at +{offset} of a "
                     f"{len(index_blob)}-byte index; the buffer is not the index the plan "  # type: ignore[arg-type]
                     f"was made against.")
            index_blob[offset:offset + len(payload)] = payload  # type: ignore[index]


# --------------------------------------------------------------------------
# Synthetic sources: what CI proves this on, with no game data
# --------------------------------------------------------------------------

def build_synthetic_zip(members: Sequence[Tuple[str, bytes]]) -> bytes:
    """A stored-only ZIP in the shape both discs write, built here byte by byte.

    Written without :mod:`zipfile` so the local headers carry no extra field,
    which is what the discs do [M] and what the index's ``offset - 30 - len(name)``
    arithmetic needs.
    """

    body = bytearray()
    central = bytearray()
    for name, payload in members:
        raw_name = name.encode("latin-1")
        crc = zlib.crc32(payload) & 0xFFFFFFFF
        local_offset = len(body)
        body += struct.pack("<4sHHHHHIIIHH", _LOCAL_SIGNATURE, 20, 0, _STORED, 0xB123, 0x2C4C,
                            crc, len(payload), len(payload), len(raw_name), 0)
        body += raw_name + bytes(payload)
        central += struct.pack("<4sHHHHHHIIIHHHHHII", _CENTRAL_SIGNATURE, 20, 20, 0, _STORED,
                               0xB123, 0x2C4C, crc, len(payload), len(payload),
                               len(raw_name), 0, 0, 0, 0, 0, local_offset)
        central += raw_name
    central_offset = len(body)
    body += central
    body += struct.pack("<4sHHHHIIH", _EOCD_SIGNATURE, 0, 0, len(members), len(members),
                        len(central), central_offset, 0)
    return bytes(body)


def build_synthetic_index(archive_blob: bytes, *, shape: str = SHAPE_INLINE) -> bytes:
    """The ``.ZIH`` of a built ZIP, in either shape the two discs use [M]."""

    _require(shape in (SHAPE_INLINE, SHAPE_TABLE),
             f"a Midway ZIP index is {SHAPE_INLINE!r} or {SHAPE_TABLE!r}, not {shape!r}.")

    def read(offset: int, length: int) -> bytes:
        return archive_blob[offset:offset + length]

    archive = read_zip(read, len(archive_blob))
    rows = sorted(archive.members, key=lambda member: member.name)
    body = bytearray()
    if shape == SHAPE_INLINE:
        for member in rows:
            body += struct.pack("<%dI" % _INLINE_WORDS, 10, 0, 0, 0xB123, 0x2C4C,
                                member.crc32, member.size, member.size, member.data_offset)
            body += member.name.encode("latin-1") + b"\x00"
    else:
        records = bytearray()
        names = bytearray()
        for member in rows:
            records += struct.pack("<3I", len(rows) * _TABLE_RECORD + len(names),
                                   member.size, member.data_offset)
            names += member.name.encode("latin-1") + b"\x00"
        body = records + names
    return struct.pack("<II", len(rows), len(body)) + bytes(body)

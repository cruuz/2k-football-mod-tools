"""EA Tiburon's tabular database (``TDB``), shared by every EA game module.

Where the ``TERF`` container is the shelf, this is what sits on it: the format
every roster, team, playbook and season table on a Madden or NCAA Football PS2
disc is written in.  Madden NFL 09 carries it twice over -- as members of the
``/DATA/DB_TEAMS.DAT`` container and as the bare ``/DATA/STRMDATA.DB`` beside
it -- and the same layout carries the memory-card saves the game writes back.
A module that reads this reads the game's data, table by named table.

It is a small relational file: a header, a directory of four-character table
names, and per table a header, a directory of four-character field names with
their bit offsets and widths, then a fixed-stride array of **bit-packed**
records.  The schema is in the file, so nothing here is a table of names
someone wrote down; a caller asks for ``PLAY`` and the field ``PSPD`` and the
file says where those bits are.

Evidence tags, on every load-bearing claim.  **[M]** measured -- a read-only
pass was run over databases this box holds and the count is quoted.
**[S]** sourced -- a citation in *Sources* below.  **[A]** assumed -- inference,
not verified; treat as a question.

The measured corpus is 561 tables across five little-endian Madden PS2
databases held here (an 08 and an 09 roster save, and 08, 09 and 12 franchise
saves).  Counts below are over that corpus unless stated otherwise.

Little-endian only
------------------
Every multi-byte integer is little-endian [M].  Big-endian variants of this
same format exist on PS3, where the console's byte order also **reverses the
four-character names** -- ``PLAY`` is stored ``YALP`` [S].  This module does
not read them: it refuses on the table count, whose big-endian value overflows
the plausible range, and the refusal says so.  A caller that needs PS3 wants a
different reader, not a flag on this one.

What is measured, and what is not
---------------------------------
* ``lenBits == lenBytes * 8 - 1`` in 561 of 561 tables [M], so the "significant
  bits" word is one short of the stride rather than the last field's end.  It
  is reported and never used as a bound: the bound this reader enforces is the
  physical ``lenBytes * 8``.
* No field's ``bit_offset + bit_width`` reaches the end of its record, in
  73,000-odd field definitions [M].  A field that does is refused.
* ``STRING``, ``BINARY`` and ``FLOAT`` fields are byte-aligned and their widths
  are whole bytes, in 561 of 561 tables [M]; every ``FLOAT`` measured is 32
  bits wide [M].  ``UINT``/``SINT`` fields are the only ones that straddle byte
  boundaries, and the widest measured is 32 bits [M].
* Records begin immediately after the field directory **even when the table
  header declares indexes** [M].  Two tables per franchise save declare one and
  two indexes; in both the bytes after the field directory are the first
  record, and the table's extent exceeds its record array by exactly
  ``16 * indexCount`` bytes -- so the index blocks trail the records.  Their
  contents are not decoded [A] and nothing here depends on them.
* ``dbSize`` is the end of the last table's record array plus four [M] -- the
  four being the end-of-file CRC's slot.  It is **not** the file's length: the
  saves measured run 928 to 781,408 bytes past it, and the excess is padding a
  save container adds.  So ``dbSize`` is reported and never used as a bound.
* The version word at ``+0x02`` sits in the file as the bytes ``00 08`` in 5 of
  5 databases [M] -- the one place a multi-byte field is *not* little-endian,
  and the reason two readers of this format report "version 8" and "version
  2048" of the same file.  It is read here as the big-endian pair, so the
  answer is 8 [S].
* Not established: what ``unknown1`` at ``+0x04`` or the second word of a table
  header carry (both are constant across the corpus but nothing here knows
  their meaning) [A]; what a declared index block contains [A]; whether any
  ``FLOAT`` is ever narrower than 32 bits [A].

Bit order, which is the one thing a reader of this format gets wrong
--------------------------------------------------------------------
Fields are packed **least-significant-bit first, both within each byte and
within the field**: bit *p* of a record is bit ``p % 8`` of byte ``p // 8``,
counted from that byte's low end, and it contributes ``1 << p`` to a field
starting at bit 0 [M][S].  The reference implementations of this format walk
that one bit at a time; this module instead reads the whole record as one
little-endian integer and shifts, which is the *same* mapping by construction
-- ``int.from_bytes(record, "little")`` puts bit ``p % 8`` of byte ``p // 8``
at integer bit ``p`` -- and not a re-derivation of it.

The measurement, on a real roster table: under this order the first three
records of ``PLAY`` read as three players of one team with plausible overall,
speed, age, height and jersey values and a single shared team id; under
most-significant-bit-first ordering the same bytes give three different team
ids and a speed of 7 for everyone [M].  Documentation of this format that says
MSB-first is describing the big-endian platform variant or is simply wrong; it
is worth re-measuring before believing either.

``SINT`` fields are sign-extended here, so a set top bit reads negative.  The
type id says signed, a six-bit season-year field is documented as covering
-32..+31 [S], and career-yardage fields that can legitimately go negative are
typed this way.  **The reference readers do not sign-extend** [S]; for a field
whose top bit is set they hand back the raw magnitude and this module does not,
which is a difference worth knowing when comparing two dumps.

Checksums
---------
Four CRC-32/MPEG-2 sites are documented for this format -- a file-header CRC,
a prior-block and a header CRC per table, and one at end of file [S].  **None
of them is verified or recomputed here**: this module is a reader, the stored
values are surfaced as integers, and :func:`build_tdb` writes them as zeros.
A writer that intends a file the game will load must compute them itself.

Retail-free: everything here is a constant, an offset, a count or a
four-character field name.  No record payload, no string lifted from a game and
no digest of a game file appears in this module or its tests, and the tests
build every byte they read.

Sources
-------
* The owner's ``NCAA-Draft-Class-Editor`` (no licence file, so nothing is
  copied -- the code below is written from the documented grammar):
  ``CLAUDE.md`` for the byte-level layout, the four CRC sites, the ``02 00 00
  00`` franchise preamble and the six-bit season-year field's -32..+31 range;
  ``tools/parse_madden_tdb.py`` for the reference walk and the bit order, which
  its docstring records as established empirically against a roster table;
  ``NcaaDraftEditor.Compiler/MaddenTdb.cs`` for the same bit order in the
  writer that produced files the owner has loaded in the game, and for the PS3
  big-endian variant's reversed four-character names.
* The owner's ``nfl-online-revival``, ``tools/madden_tdb.py`` -- the same
  header walk applied to the *disc* side, Madden NFL 2004's ``DB_TEAMS.DAT``
  members, which is what makes the on-disc and in-save databases one format.
  Its docstring states the bit order in the same words.
* ``mod_editor/games/_formats/ea_terf.py`` in this repository, whose member
  classifier already probes for this format's magic and table count; the
  plausible-table-count ceiling here is deliberately the same number.

Standard library only; importable without Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Dict, List, Mapping, Sequence, Tuple, Union

from mod_editor.games.contract import Refusal

TDB_MAGIC = b"DB"

#: The file header: magic, version, an unknown word, the database size, a zero
#: word, the table count and the file-header CRC.
TDB_HEADER_SIZE = 24

#: One table-directory row: a four-character name and an offset.
TDB_TABLE_ENTRY_SIZE = 8

#: The per-table header that each directory offset points at.
TDB_TABLE_HEADER_SIZE = 40

#: One field definition: type, bit offset, four-character name, bit width.
TDB_FIELD_SIZE = 16

#: The version this format has carried in every database measured.  Stored as
#: the bytes ``00 08`` -- read big-endian, unlike every other multi-byte field.
TDB_VERSION = 8

#: What a franchise save prepends before the magic [S].  A preamble is detected
#: by finding the magic four bytes in, not by matching these bytes, so a
#: variant that prepends something else still opens; this constant is what a
#: writer puts back.
PREAMBLE = b"\x02\x00\x00\x00"

#: The largest table count this reader will believe.  Deliberately the same
#: ceiling ``ea_terf.identify_member`` uses to tell a database from two bytes
#: that happen to read ``DB``; the largest measured here is 185.
TDB_MAX_TABLES = 4096

#: Bytes a declared index block occupies, measured as the difference between an
#: indexed table's extent and its record array [M].  Nothing here reads one.
TDB_INDEX_SIZE = 16

FIELD_STRING = 0
FIELD_BINARY = 1
FIELD_SINT = 2
FIELD_UINT = 3
FIELD_FLOAT = 4

#: The five field types a field definition's first word can name.
FIELD_TYPE_NAMES: Mapping[int, str] = {
    FIELD_STRING: "STRING",
    FIELD_BINARY: "BINARY",
    FIELD_SINT: "SINT",
    FIELD_UINT: "UINT",
    FIELD_FLOAT: "FLOAT",
}

#: The types read through a byte slice rather than through the bit packer, and
#: which are therefore byte-aligned in every table measured.
BYTE_ALIGNED_TYPES = (FIELD_STRING, FIELD_BINARY, FIELD_FLOAT)

#: How wide a ``FLOAT`` is in every table measured.
FLOAT_WIDTH = 32

#: Record text is 8-bit and is decoded latin-1, never utf-8: EA stored bytes,
#: a name can carry an accented character, and a reader that raises on one has
#: turned a legible row into an error.
TEXT_ENCODING = "latin-1"

TdbValue = Union[int, float, str]


class TdbError(Refusal):
    """A database, table, field or record is not what it claims.  One sentence."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise TdbError(message)


def _read_bits(record: bytes, bit_offset: int, bit_width: int) -> int:
    """Pull one bit-packed field out of *record*, least-significant-bit first.

    Equivalent to the reference readers' per-bit loop rather than a different
    reading of the format: little-endian integer bit *p* **is** bit ``p % 8``
    of byte ``p // 8`` counted from that byte's low end, which is the mapping
    that loop walks.
    """
    if bit_width <= 0:
        return 0
    whole = int.from_bytes(record, "little")
    return (whole >> bit_offset) & ((1 << bit_width) - 1)


@dataclass(frozen=True)
class TdbField:
    """One field definition: where a value sits in a record, and how to read it."""

    name: str
    type_id: int
    bit_offset: int
    bit_width: int

    @property
    def type_name(self) -> str:
        return FIELD_TYPE_NAMES.get(self.type_id, "unknown type %d" % self.type_id)

    @property
    def byte_aligned(self) -> bool:
        return self.bit_offset % 8 == 0

    @property
    def bit_end(self) -> int:
        return self.bit_offset + self.bit_width


@dataclass(frozen=True)
class TdbTable:
    """One table's header and schema.  Rows are read through :class:`TdbDatabase`."""

    name: str
    #: Offset of the table header in the database, preamble excluded.
    offset: int
    record_bytes: int
    #: The stride in bits as the header declares it, which is ``record_bytes *
    #: 8 - 1`` in every table measured and is never used as a bound here.
    record_bits: int
    max_records: int
    current_records: int
    field_count: int
    index_count: int
    #: Stored CRC-32/MPEG-2 values, surfaced and never verified.
    prior_crc: int
    header_crc: int
    #: Offset of the first record, which follows the field directory whether or
    #: not the header declares indexes [M].
    records_offset: int
    fields: Tuple[TdbField, ...]

    @property
    def field_names(self) -> Tuple[str, ...]:
        return tuple(field.name for field in self.fields)

    def field(self, name: str) -> TdbField:
        """The field called *name*, or a refusal naming what this table has."""
        for candidate in self.fields:
            if candidate.name == name:
                return candidate
        raise TdbError(
            "table %s has no field %r; it has %d: %s. Field names are exactly "
            "four characters as the file spells them, so pass one of those."
            % (self.name, name, len(self.fields), ", ".join(self.field_names))
        )

    def __contains__(self, name: object) -> bool:
        return any(field.name == name for field in self.fields)


class TdbDatabase:
    """A parsed ``TDB``.  Reads; never mutates its input and never writes."""

    def __init__(self, data: bytes) -> None:
        data = bytes(data)
        preamble = self._find_magic(data)
        _require(
            preamble is not None,
            "not an EA TDB: the %r magic is at neither offset 0 nor offset %d "
            "(the file starts with %r). Hand this reader the database itself, "
            "not the save container or the TERF member that holds it."
            % (TDB_MAGIC, len(PREAMBLE), data[:8]),
        )
        assert preamble is not None  # for type checkers; _require has raised
        #: Bytes before the magic.  4 for a franchise save, 0 otherwise [S].
        self.preamble_bytes = preamble
        body = data[preamble:]
        _require(
            len(body) >= TDB_HEADER_SIZE,
            "EA TDB header needs %d byte(s) and this file has %d after its "
            "%d-byte preamble; the file is truncated."
            % (TDB_HEADER_SIZE, len(body), preamble),
        )
        self._body = body
        #: Read big-endian: the two bytes sit as ``00 08`` in every measured
        #: database, so a little-endian read of the same field returns 2048.
        self.version, = struct.unpack_from(">H", body, 0x02)
        self.unknown1, = struct.unpack_from("<I", body, 0x04)
        self.db_size, = struct.unpack_from("<I", body, 0x08)
        self.table_count, = struct.unpack_from("<I", body, 0x10)
        #: The file-header CRC as stored.  Surfaced, never verified.
        self.checksum, = struct.unpack_from("<I", body, 0x14)
        _require(
            0 < self.table_count <= TDB_MAX_TABLES,
            "EA TDB declares %d table(s), which is not a count a database has "
            "(1..%d). Either this is not a TDB, or it is a big-endian PS3 "
            "database, which this little-endian reader does not open."
            % (self.table_count, TDB_MAX_TABLES),
        )
        directory_end = TDB_HEADER_SIZE + self.table_count * TDB_TABLE_ENTRY_SIZE
        _require(
            directory_end <= len(body),
            "EA TDB declares %d table(s), whose directory needs %d byte(s), and "
            "the file holds %d; the file is truncated."
            % (self.table_count, directory_end, len(body)),
        )
        #: Table offsets are relative to the end of the table directory, not to
        #: the start of the file.
        self.directory_end = directory_end
        tables: List[TdbTable] = []
        for index in range(self.table_count):
            tables.append(self._read_table(index))
        self.tables: Tuple[TdbTable, ...] = tuple(tables)
        by_name: Dict[str, TdbTable] = {}
        for table in self.tables:
            by_name.setdefault(table.name, table)
        self._by_name = by_name

    # -- header ------------------------------------------------------------

    @staticmethod
    def _find_magic(data: bytes) -> Union[int, None]:
        for start in (0, len(PREAMBLE)):
            if data[start:start + len(TDB_MAGIC)] == TDB_MAGIC:
                return start
        return None

    @staticmethod
    def _name(raw: bytes, what: str, where: int) -> str:
        _require(
            all(32 <= byte < 127 for byte in raw),
            "the %s at offset %d is named %r, which is not four printable "
            "characters; the directory is being read at the wrong offset or "
            "the file is damaged." % (what, where, raw),
        )
        return raw.decode("ascii")

    def _read_table(self, index: int) -> TdbTable:
        body = self._body
        entry = TDB_HEADER_SIZE + index * TDB_TABLE_ENTRY_SIZE
        name = self._name(body[entry:entry + 4], "table", entry)
        relative, = struct.unpack_from("<I", body, entry + 4)
        start = self.directory_end + relative
        _require(
            0 <= start and start + TDB_TABLE_HEADER_SIZE <= len(body),
            "table %s says its header is at offset %d, and this file is %d "
            "byte(s); the file is truncated or its directory is not being read "
            "as offsets relative to the end of the directory."
            % (name, start, len(body)),
        )
        prior_crc, = struct.unpack_from("<I", body, start)
        record_bytes, record_bits = struct.unpack_from("<II", body, start + 8)
        max_records, current_records = struct.unpack_from("<HH", body, start + 20)
        field_count = body[start + 28]
        index_count = body[start + 29]
        header_crc, = struct.unpack_from("<I", body, start + 36)
        fields_at = start + TDB_TABLE_HEADER_SIZE
        records_at = fields_at + field_count * TDB_FIELD_SIZE
        _require(
            records_at <= len(body),
            "table %s declares %d field(s), whose directory would end at %d in "
            "a %d-byte file; the file is truncated."
            % (name, field_count, records_at, len(body)),
        )
        span = current_records * record_bytes
        _require(
            records_at + span <= len(body),
            "table %s declares %d record(s) of %d byte(s), which would end at "
            "%d in a %d-byte file; the file is truncated."
            % (name, current_records, record_bytes, records_at + span, len(body)),
        )
        fields: List[TdbField] = []
        for slot in range(field_count):
            base = fields_at + slot * TDB_FIELD_SIZE
            type_id, bit_offset = struct.unpack_from("<II", body, base)
            field_name = self._name(body[base + 8:base + 12], "field", base + 8)
            bit_width, = struct.unpack_from("<I", body, base + 12)
            _require(
                bit_offset + bit_width <= record_bytes * 8,
                "field %s of table %s covers bits %d..%d of a record that is "
                "%d byte(s) long; the field directory is being read at the "
                "wrong offset or the file is damaged."
                % (field_name, name, bit_offset, bit_offset + bit_width,
                   record_bytes),
            )
            fields.append(TdbField(field_name, type_id, bit_offset, bit_width))
        return TdbTable(
            name=name,
            offset=start,
            record_bytes=record_bytes,
            record_bits=record_bits,
            max_records=max_records,
            current_records=current_records,
            field_count=field_count,
            index_count=index_count,
            prior_crc=prior_crc,
            header_crc=header_crc,
            records_offset=records_at,
            fields=tuple(fields),
        )

    # -- tables ------------------------------------------------------------

    def __len__(self) -> int:
        return len(self.tables)

    @property
    def table_names(self) -> Tuple[str, ...]:
        return tuple(table.name for table in self.tables)

    def table(self, name: str) -> TdbTable:
        """The table called *name*, or a refusal naming what this database has."""
        found = self._by_name.get(name)
        if found is None:
            raise TdbError(
                "this database has no table %r; it has %d: %s. Table names are "
                "exactly four characters as the file spells them, so pass one "
                "of those." % (name, len(self.tables), ", ".join(self.table_names))
            )
        return found

    def _resolve_table(self, table: Union[str, TdbTable]) -> TdbTable:
        if isinstance(table, TdbTable):
            return table
        return self.table(table)

    @staticmethod
    def _resolve_field(table: TdbTable,
                       field: Union[str, TdbField]) -> TdbField:
        if isinstance(field, TdbField):
            _require(
                field.name in table and table.field(field.name) == field,
                "field %s does not belong to table %s, which has %d: %s. Pass a "
                "field this table declares, or its name."
                % (field.name, table.name, len(table.fields),
                   ", ".join(table.field_names)),
            )
            return field
        return table.field(field)

    # -- records -----------------------------------------------------------

    def record_bytes(self, table: Union[str, TdbTable], index: int) -> bytes:
        """Record *index* of *table*, exactly as it sits in the file."""
        resolved = self._resolve_table(table)
        _require(
            0 <= index < resolved.current_records,
            "table %s has no record %d: it holds %d (0..%d) of a possible %d."
            % (resolved.name, index, resolved.current_records,
               resolved.current_records - 1, resolved.max_records),
        )
        start = resolved.records_offset + index * resolved.record_bytes
        return self._body[start:start + resolved.record_bytes]

    def value(self, table: Union[str, TdbTable], index: int,
              field: Union[str, TdbField]) -> TdbValue:
        """One field of one record.

        ``UINT`` and ``SINT`` come back as ints -- ``SINT`` sign-extended, so a
        set top bit reads negative, which the reference readers do not do.
        ``FLOAT`` comes back as a float, ``STRING`` as text decoded latin-1 and
        cut at its first NUL, and ``BINARY`` as a lowercase hex string.
        """
        resolved = self._resolve_table(table)
        return self.decode(self._resolve_field(resolved, field),
                           self.record_bytes(resolved, index))

    def row(self, table: Union[str, TdbTable], index: int) -> Dict[str, TdbValue]:
        """Every field of record *index*, keyed by field name."""
        resolved = self._resolve_table(table)
        record = self.record_bytes(resolved, index)
        return {field.name: self.decode(field, record)
                for field in resolved.fields}

    @staticmethod
    def decode(field: TdbField, record: bytes) -> TdbValue:
        """Read *field* out of one raw *record*."""
        if field.type_id in (FIELD_UINT, FIELD_SINT):
            value = _read_bits(record, field.bit_offset, field.bit_width)
            if (field.type_id == FIELD_SINT and field.bit_width > 0
                    and value >> (field.bit_width - 1)):
                value -= 1 << field.bit_width
            return value
        _require(
            field.byte_aligned,
            "field %s is a %s at bit %d, which is not a byte boundary, and a "
            "%s is read as whole bytes; this reader cannot decode it. Read the "
            "record with record_bytes() and decode those bytes yourself."
            % (field.name, field.type_name, field.bit_offset, field.type_name),
        )
        start = field.bit_offset // 8
        if field.type_id == FIELD_FLOAT:
            _require(
                field.bit_width == FLOAT_WIDTH,
                "field %s is a %d-bit FLOAT and this reader knows only the "
                "%d-bit one that every measured table carries; read it with "
                "record_bytes() instead."
                % (field.name, field.bit_width, FLOAT_WIDTH),
            )
            return float(struct.unpack_from("<f", record, start)[0])
        raw = record[start:start + field.bit_width // 8]
        if field.type_id == FIELD_BINARY:
            return raw.hex()
        if field.type_id == FIELD_STRING:
            end = raw.find(b"\x00")
            if end >= 0:
                raw = raw[:end]
            return raw.decode(TEXT_ENCODING)
        raise TdbError(
            "field %s declares type %d, which is not one of the five this "
            "format defines (%s); the field directory is being read at the "
            "wrong offset or the file is damaged."
            % (field.name, field.type_id,
               ", ".join("%d=%s" % item for item in FIELD_TYPE_NAMES.items()))
        )

    # -- reporting ---------------------------------------------------------

    def summary(self) -> Dict[str, object]:
        """The database's own account of its shape, JSON-safe and payload-free.

        Names, counts, offsets and the stored CRCs -- nothing read out of a
        record, so this is safe to print, log or commit.
        """
        return {
            "version": self.version,
            "preamble_bytes": self.preamble_bytes,
            "db_size": self.db_size,
            "checksum": self.checksum,
            "table_count": self.table_count,
            "tables": [
                {
                    "name": table.name,
                    "offset": table.offset,
                    "record_bytes": table.record_bytes,
                    "record_bits": table.record_bits,
                    "current_records": table.current_records,
                    "max_records": table.max_records,
                    "field_count": table.field_count,
                    "index_count": table.index_count,
                    "prior_crc": table.prior_crc,
                    "header_crc": table.header_crc,
                    "fields": list(table.field_names),
                }
                for table in self.tables
            ],
        }


def parse_tdb(data: bytes) -> TdbDatabase:
    """Parse *data* as a little-endian EA ``TDB``."""
    return TdbDatabase(data)


def looks_like_tdb(head: bytes) -> bool:
    """Do these first bytes look like a ``TDB``, preamble or not?

    Magic plus a plausible table count, which is all that can be asked of a
    two-byte magic: ``DB`` alone happens by accident, an absurd table count
    does not.  Cheap enough for a census over every member of a container, and
    never a substitute for :func:`parse_tdb`, which is what says a file really
    opens.
    """
    for start in (0, len(PREAMBLE)):
        if head[start:start + len(TDB_MAGIC)] != TDB_MAGIC:
            continue
        if len(head) < start + TDB_HEADER_SIZE:
            continue
        count, = struct.unpack_from("<I", head, start + 0x10)
        if 0 < count <= TDB_MAX_TABLES:
            return True
    return False


# --------------------------------------------------------------------------
# The fixture builder
# --------------------------------------------------------------------------
#
# Not a game-file writer.  It exists so tests and synthetic sources can be
# built from the grammar instead of from a copy of somebody's save, and it
# writes all four CRC sites as zeros, which no game will load.  A real writer
# needs the CRC-32/MPEG-2 pass this module deliberately does not implement.


def _layout(fields: Sequence[Tuple[str, int, int]]) -> Tuple[List[TdbField], int]:
    """Place *fields* in order, padding to a byte boundary where the type needs it."""
    placed: List[TdbField] = []
    cursor = 0
    for spec in fields:
        _require(
            len(spec) == 3,
            "a field spec is (name, type_id, bit_width) and this one has %d "
            "item(s): %r." % (len(spec), spec),
        )
        name, type_id, bit_width = spec
        _require(
            type_id in FIELD_TYPE_NAMES,
            "field %s asks for type %r, and the format defines %s."
            % (name, type_id,
               ", ".join("%d=%s" % item for item in FIELD_TYPE_NAMES.items())),
        )
        _require(
            len(name) == 4,
            "field name %r is %d character(s); this format's names are exactly "
            "four." % (name, len(name)),
        )
        if type_id in BYTE_ALIGNED_TYPES:
            _require(
                bit_width % 8 == 0,
                "field %s is a %s and asks for %d bits; a %s is whole bytes, "
                "so use a multiple of 8."
                % (name, FIELD_TYPE_NAMES[type_id], bit_width,
                   FIELD_TYPE_NAMES[type_id]),
            )
            cursor += -cursor % 8
        placed.append(TdbField(name, type_id, cursor, bit_width))
        cursor += bit_width
    return placed, cursor


def _encode(field: TdbField, value: object) -> int:
    """One field's contribution to a record, as bits of a little-endian integer."""
    if field.type_id in (FIELD_UINT, FIELD_SINT):
        _require(
            isinstance(value, int) and not isinstance(value, bool),
            "field %s is a %s and was handed %r; pass an int."
            % (field.name, field.type_name, value),
        )
        number = int(value)  # type: ignore[arg-type]
        if field.type_id == FIELD_UINT:
            low, high = 0, (1 << field.bit_width) - 1
        else:
            low = -(1 << (field.bit_width - 1))
            high = (1 << (field.bit_width - 1)) - 1
        _require(
            low <= number <= high,
            "field %s is a %d-bit %s and %d does not fit in it (%d..%d); widen "
            "the field or pass a value in range."
            % (field.name, field.bit_width, field.type_name, number, low, high),
        )
        return (number & ((1 << field.bit_width) - 1)) << field.bit_offset
    width = field.bit_width // 8
    if field.type_id == FIELD_FLOAT:
        _require(
            field.bit_width == FLOAT_WIDTH,
            "field %s is a %d-bit FLOAT and this builder writes only the "
            "%d-bit one." % (field.name, field.bit_width, FLOAT_WIDTH),
        )
        raw = struct.pack("<f", float(value))  # type: ignore[arg-type]
    elif field.type_id == FIELD_STRING:
        text = value if isinstance(value, str) else str(value)
        try:
            raw = text.encode(TEXT_ENCODING, "strict")
        except UnicodeEncodeError as error:
            raise TdbError(
                "field %s is text and %r cannot be written as %s, which is the "
                "only encoding this format carries; use characters this "
                "encoding has." % (field.name, text, TEXT_ENCODING)
            ) from error
        _require(
            len(raw) <= width,
            "field %s holds %d byte(s) and %r needs %d; shorten the value or "
            "widen the field." % (field.name, width, text, len(raw)),
        )
        raw = raw.ljust(width, b"\x00")
    else:
        _require(
            isinstance(value, (bytes, bytearray)),
            "field %s is BINARY and was handed %r; pass bytes."
            % (field.name, value),
        )
        raw = bytes(value)  # type: ignore[arg-type]
        _require(
            len(raw) <= width,
            "field %s holds %d byte(s) and was handed %d; shorten the value or "
            "widen the field." % (field.name, width, len(raw)),
        )
        raw = raw.ljust(width, b"\x00")
    return int.from_bytes(raw, "little") << field.bit_offset


def build_tdb(tables: Sequence[Sequence[object]], *,
              version: int = TDB_VERSION) -> bytes:
    """Build a synthetic database.  **A fixture builder, not a game writer.**

    *tables* is a sequence of ``(name, fields, rows)`` -- or
    ``(name, fields, rows, max_records)`` -- where *fields* is a sequence of
    ``(name, type_id, bit_width)`` and *rows* is a sequence of mappings from
    field name to value.  A field a row omits is written as zero, empty text or
    zero bytes.

    Fields are laid out in the order given, packed with no padding except
    before a ``STRING``, ``BINARY`` or ``FLOAT``, which the format byte-aligns.
    The record stride is one byte past the last field, reproducing the measured
    ``lenBits == lenBytes * 8 - 1``.  Every CRC site is written as zero and the
    header's unknown word as zero, so what comes back round-trips through
    :func:`parse_tdb` with identical values and **no game will load it**.
    """
    #: (name, laid-out fields, rows, record stride, record slots)
    specs: List[Tuple[str, List[TdbField],
                      Sequence[Mapping[str, object]], int, int]] = []
    for spec in tables:
        _require(
            len(spec) in (3, 4),
            "a table spec is (name, fields, rows) or (name, fields, rows, "
            "max_records) and this one has %d item(s)." % len(spec),
        )
        name = spec[0]
        _require(
            isinstance(name, str) and len(name) == 4,
            "table name %r is not the four characters this format uses." % (name,),
        )
        fields, cursor = _layout(spec[1])  # type: ignore[arg-type]
        rows = spec[2]
        record_bytes = cursor // 8 + 1
        declared = spec[3] if len(spec) == 4 else len(rows)
        max_records = int(declared)  # type: ignore[arg-type]
        _require(
            max_records >= len(rows),
            "table %s declares room for %d record(s) and was handed %d."
            % (name, max_records, len(rows)),
        )
        _require(
            len(fields) <= 0xFF and max_records <= 0xFFFF,
            "table %s has %d field(s) and %d record slot(s); the header stores "
            "those in one byte and one 16-bit word."
            % (name, len(fields), max_records),
        )
        specs.append(  # type: ignore[arg-type]
            (name, fields, rows, record_bytes, max_records))

    directory_end = TDB_HEADER_SIZE + len(specs) * TDB_TABLE_ENTRY_SIZE
    blocks: List[bytes] = []
    offsets: List[int] = []
    cursor = 0
    for name, fields, rows, record_bytes, max_records in specs:
        offsets.append(cursor)
        block = bytearray()
        block += struct.pack("<I", 0)                      # priorCRC: zero
        block += struct.pack("<I", 0)                      # unknown
        block += struct.pack("<II", record_bytes, record_bytes * 8 - 1)
        block += struct.pack("<I", 0)                      # zero
        block += struct.pack("<HH", max_records, len(rows))
        block += struct.pack("<I", 0)                      # unknown
        block += bytes((len(fields), 0))                   # numFields, indexes
        block += struct.pack("<H", 0)                      # zero2
        block += struct.pack("<I", 0)                      # zero3
        block += struct.pack("<I", 0)                      # headerCRC: zero
        for field in fields:
            block += struct.pack("<II", field.type_id, field.bit_offset)
            block += field.name.encode("ascii")
            block += struct.pack("<I", field.bit_width)
        for row in rows:
            accumulator = 0
            for field in fields:
                if field.name in row:
                    accumulator |= _encode(field, row[field.name])
            block += accumulator.to_bytes(record_bytes, "little")
        block += bytes((max_records - len(rows)) * record_bytes)
        blocks.append(bytes(block))
        cursor += len(block)

    #: The measured relation: the declared size runs to the end of the last
    #: table's records plus the end-of-file CRC's four bytes.
    db_size = directory_end + cursor + 4
    out = bytearray()
    out += TDB_MAGIC
    out += struct.pack(">H", version)
    out += struct.pack("<I", 0)
    out += struct.pack("<I", db_size)
    out += struct.pack("<I", 0)
    out += struct.pack("<I", len(specs))
    out += struct.pack("<I", 0)                            # file-header CRC
    for (name, _fields, _rows, _stride, _max), offset in zip(specs, offsets):
        out += name.encode("ascii")
        out += struct.pack("<I", offset)
    for block in blocks:
        out += block
    out += struct.pack("<I", 0)                            # end-of-file CRC
    return bytes(out)


__all__ = [
    "BYTE_ALIGNED_TYPES",
    "FIELD_BINARY",
    "FIELD_FLOAT",
    "FIELD_SINT",
    "FIELD_STRING",
    "FIELD_TYPE_NAMES",
    "FIELD_UINT",
    "FLOAT_WIDTH",
    "PREAMBLE",
    "TDB_FIELD_SIZE",
    "TDB_HEADER_SIZE",
    "TDB_INDEX_SIZE",
    "TDB_MAGIC",
    "TDB_MAX_TABLES",
    "TDB_TABLE_ENTRY_SIZE",
    "TDB_TABLE_HEADER_SIZE",
    "TDB_VERSION",
    "TEXT_ENCODING",
    "TdbDatabase",
    "TdbError",
    "TdbField",
    "TdbTable",
    "TdbValue",
    "build_tdb",
    "looks_like_tdb",
    "parse_tdb",
]

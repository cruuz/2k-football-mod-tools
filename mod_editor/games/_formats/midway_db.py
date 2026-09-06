"""Midway's ``.dbs`` / ``.dbd`` database pair — the roster, team, playbook and asset tables of
NFL Blitz Pro and Blitz: The League.

A database is two members of one ``PAK `` object: a **schema** (``.dbs``) and its **data**
(``.dbd``).  Both are read to the byte on both discs — 311 of 311 data files on The League and
48 of 49 on Blitz Pro, the one refusal being a data file whose own schema is not on the disc [M].

The schema is a flat token stream::

    'D' name NUL                         the database
    'T' name NUL                         a table of fixed-width rows
    't' name NUL                         a string pool (NUL-separated strings)
    <type> name NUL  u16 param           a field of the current table
    NUL                                  end

Field types, with the width each takes in a row [M]:

| type | width | param |
|---|---|---|
| ``b`` ``B`` | 1 | ``bits | shift << 8`` when bit-packed, else 0 |
| ``w`` ``W`` | 2 | same |
| ``i`` ``I`` | 4 | same |
| ``f`` | 4 | 0 |
| ``s`` ``S`` | *param* | the string's fixed width in bytes |
| ``r`` | 4 | the index of the pool table this offset points into |
| ``q`` | 2 | same, for a 16-bit offset |

A bit-packed field whose ``shift`` is not zero shares the storage unit of the field before it:
``(6,0) (6,6) (5,12) (7,17) (7,24)`` is five ``i`` fields in one 32-bit word.  Upper-case types
mark what look like key columns [A]; they are read exactly like the lower-case ones.

The data file repeats, for every table in schema order (a data file may omit trailing tables)::

    char[32] database name   char[32] table name   u32 bytes   bytes of rows (or the pool)

and ends with a u32 trailer that is 0 on every file measured [M].  Strings are fixed-width and
NUL-terminated inside their width; the bytes after the NUL are whatever was in the writer's
buffer and are not zero.  A pool is NUL-separated with an empty string at offset 0; every
``r`` / ``q`` value measured lands on a string start in the pool its param names (28,639 values
on The League, 29,178 on Blitz Pro) [M].

Retail-free: :func:`build_schema` and :func:`build_data` synthesise a pair for the tests.
Standard library only; no Qt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import struct
from typing import Dict, Iterator, List, Optional, Sequence, Tuple, Union

from mod_editor.games.contract import Refusal

NAME_FIELD_BYTES = 32
TABLE_HEADER_BYTES = NAME_FIELD_BYTES * 2 + 4
TRAILER_BYTES = 4
FIXED_WIDTH = {"i": 4, "I": 4, "w": 2, "W": 2, "b": 1, "B": 1, "f": 4}
REF_WIDTH = {"r": 4, "q": 2}
STRING_TYPES = ("s", "S")
POOL_KIND = "t"
TABLE_KIND = "T"


def _require(condition: object, message: str) -> None:
    if not condition:
        raise Refusal(message)


def _name32(raw: bytes, at: int) -> str:
    return raw[at:at + NAME_FIELD_BYTES].split(b"\x00", 1)[0].decode("latin-1")


@dataclass(frozen=True)
class Field:
    type: str
    name: str
    param: int

    @property
    def is_string(self) -> bool:
        return self.type in STRING_TYPES

    @property
    def is_reference(self) -> bool:
        return self.type in REF_WIDTH

    @property
    def is_key(self) -> bool:
        return self.type in ("I", "W", "B", "S")

    @property
    def bits(self) -> int:
        return self.param & 0xFF if self.type in FIXED_WIDTH and self.param else 0

    @property
    def shift(self) -> int:
        return self.param >> 8 if self.type in FIXED_WIDTH and self.param else 0

    @property
    def shares_previous_unit(self) -> bool:
        return self.type in FIXED_WIDTH and self.param != 0 and self.shift != 0

    @property
    def width(self) -> int:
        """Bytes this field adds to the row (0 when it shares the previous field's unit)."""
        if self.is_string:
            return self.param
        if self.type in FIXED_WIDTH:
            return 0 if self.shares_previous_unit else FIXED_WIDTH[self.type]
        if self.type in REF_WIDTH:
            return REF_WIDTH[self.type]
        raise Refusal("field %s has type %r, which this reader does not know" % (self.name, self.type))


@dataclass
class TableSchema:
    name: str
    kind: str
    fields: List[Field] = field(default_factory=list)

    @property
    def is_pool(self) -> bool:
        return self.kind == POOL_KIND

    @property
    def row_width(self) -> int:
        return sum(f.width for f in self.fields)

    def offsets(self) -> List[int]:
        """Byte offset of every field inside a row; a shared bit-field repeats its unit's offset."""
        out: List[int] = []
        pos = 0
        unit_at = 0
        for f in self.fields:
            if f.shares_previous_unit:
                out.append(unit_at)
                continue
            unit_at = pos
            out.append(pos)
            pos += f.width
        return out


@dataclass
class Schema:
    database: str
    tables: List[TableSchema]
    consumed: int

    def table(self, name: str) -> Optional[TableSchema]:
        for t in self.tables:
            if t.name == name:
                return t
        return None

    def index_of(self, name: str) -> int:
        for i, t in enumerate(self.tables):
            if t.name == name:
                return i
        return -1


def parse_schema(raw: Union[bytes, memoryview], where: str = "the schema") -> Schema:
    raw = bytes(raw)
    pos = 0
    database: Optional[str] = None
    tables: List[TableSchema] = []
    current: Optional[TableSchema] = None
    while pos < len(raw) and raw[pos]:
        kind = chr(raw[pos])
        end = raw.find(b"\x00", pos + 1)
        _require(end > pos, "%s: a name at %d has no terminator" % (where, pos))
        name = raw[pos + 1:end].decode("latin-1")
        pos = end + 1
        if kind == "D":
            database = name
            continue
        if kind in (TABLE_KIND, POOL_KIND):
            current = TableSchema(name, kind)
            tables.append(current)
            continue
        _require(current is not None, "%s: field %s at %d precedes any table" % (where, name, pos))
        _require(pos + 2 <= len(raw), "%s: field %s has no parameter word" % (where, name))
        param = struct.unpack_from("<H", raw, pos)[0]
        pos += 2
        f = Field(kind, name, param)
        f.width  # refuses an unknown type by name
        current.fields.append(f)
    _require(database is not None, "%s names no database ('D' entry)" % where)
    for t in tables:
        if t.is_pool:
            _require(len(t.fields) == 1 and t.fields[0].is_string,
                     "%s: pool %s must have exactly one string field" % (where, t.name))
    return Schema(database or "", tables, pos)


@dataclass
class Table:
    schema: TableSchema
    raw: bytes

    @property
    def name(self) -> str:
        return self.schema.name

    @property
    def is_pool(self) -> bool:
        return self.schema.is_pool

    @property
    def row_width(self) -> int:
        return self.schema.row_width

    @property
    def row_count(self) -> int:
        return 0 if self.is_pool or not self.row_width else len(self.raw) // self.row_width

    # -- pools --------------------------------------------------------------
    def string_at(self, offset: int) -> str:
        _require(self.is_pool, "table %s is not a string pool" % self.name)
        _require(0 <= offset < len(self.raw) and (offset == 0 or self.raw[offset - 1] == 0),
                 "offset %d is not a string start in pool %s" % (offset, self.name))
        end = self.raw.find(b"\x00", offset)
        return self.raw[offset:end if end >= 0 else len(self.raw)].decode("latin-1")

    def strings(self) -> List[str]:
        _require(self.is_pool, "table %s is not a string pool" % self.name)
        return [s.decode("latin-1") for s in self.raw[:-1].split(b"\x00")] if self.raw else []

    # -- rows ---------------------------------------------------------------
    def row_bytes(self, index: int) -> bytes:
        _require(0 <= index < self.row_count, "table %s has %d rows; row %d does not exist" % (self.name, self.row_count, index))
        w = self.row_width
        return self.raw[index * w:(index + 1) * w]


@dataclass
class Database:
    name: str
    schema: Schema
    tables: List[Table]
    trailer: int

    def table(self, name: str) -> Table:
        for t in self.tables:
            if t.name == name:
                return t
        raise Refusal("database %s has no table %s" % (self.name, name))

    def has_table(self, name: str) -> bool:
        return any(t.name == name for t in self.tables)

    def row(self, table: Union[str, Table], index: int, *, resolve: bool = True) -> Dict[str, object]:
        """One row as a dict.  References become the pooled string when ``resolve`` is on."""
        t = self.table(table) if isinstance(table, str) else table
        _require(not t.is_pool, "table %s is a string pool; use strings()" % t.name)
        raw = t.row_bytes(index)
        out: Dict[str, object] = {}
        for f, at in zip(t.schema.fields, t.schema.offsets()):
            if f.is_string:
                out[f.name] = raw[at:at + f.param].split(b"\x00", 1)[0].decode("latin-1")
            elif f.type == "f":
                out[f.name] = struct.unpack_from("<f", raw, at)[0]
            elif f.type in FIXED_WIDTH:
                unit = int.from_bytes(raw[at:at + FIXED_WIDTH[f.type]], "little")
                out[f.name] = (unit >> f.shift) & ((1 << f.bits) - 1) if f.param else unit
            else:
                value = int.from_bytes(raw[at:at + REF_WIDTH[f.type]], "little")
                if resolve:
                    pool = self.tables[f.param] if f.param < len(self.tables) else None
                    out[f.name] = pool.string_at(value) if pool is not None and pool.is_pool else value
                else:
                    out[f.name] = value
        return out

    def rows(self, table: Union[str, Table], *, resolve: bool = True) -> Iterator[Dict[str, object]]:
        t = self.table(table) if isinstance(table, str) else table
        for i in range(t.row_count):
            yield self.row(t, i, resolve=resolve)

    def check_references(self) -> Dict[str, int]:
        """Every ``r``/``q`` value must land on a string start in the pool its param names."""
        counts = {"fields": 0, "values": 0, "on_string_start": 0, "param_not_a_pool": 0}
        for t in self.tables:
            if t.is_pool:
                continue
            for f, at in zip(t.schema.fields, t.schema.offsets()):
                if not f.is_reference:
                    continue
                counts["fields"] += 1
                pool = self.tables[f.param] if f.param < len(self.tables) else None
                if pool is None or not pool.is_pool:
                    counts["param_not_a_pool"] += 1
                    continue
                for i in range(t.row_count):
                    value = int.from_bytes(t.raw[i * t.row_width + at:i * t.row_width + at + REF_WIDTH[f.type]], "little")
                    counts["values"] += 1
                    if value < len(pool.raw) and (value == 0 or pool.raw[value - 1] == 0):
                        counts["on_string_start"] += 1
        return counts


def parse_data(raw: Union[bytes, memoryview], schema: Schema, where: str = "the data file") -> Database:
    """Walk a ``.dbd`` against its schema; every table is located and its byte count checked."""
    raw = bytes(raw)
    _require(len(raw) >= TABLE_HEADER_BYTES + TRAILER_BYTES, "%s is %d bytes; the shortest data file is %d" % (where, len(raw), TABLE_HEADER_BYTES + TRAILER_BYTES))
    dbname = _name32(raw, 0)
    _require(dbname == schema.database, "%s belongs to database %s; the schema is for %s" % (where, dbname, schema.database))
    pos = 0
    tables: List[Table] = []
    seen: List[str] = []
    while pos + TRAILER_BYTES < len(raw):
        _require(pos + TABLE_HEADER_BYTES <= len(raw), "%s: a table header at %d runs past the end" % (where, pos))
        _require(_name32(raw, pos) == dbname, "%s: the table at %d names database %s" % (where, pos, _name32(raw, pos)))
        tname = _name32(raw, pos + NAME_FIELD_BYTES)
        nbytes = struct.unpack_from("<I", raw, pos + NAME_FIELD_BYTES * 2)[0]
        pos += TABLE_HEADER_BYTES
        ts = schema.table(tname)
        _require(ts is not None, "%s: table %s is not in the schema for %s" % (where, tname, dbname))
        _require(tname not in seen, "%s: table %s appears twice" % (where, tname))
        _require(pos + nbytes <= len(raw), "%s: table %s declares %d bytes past the end" % (where, tname, nbytes))
        body = raw[pos:pos + nbytes]
        pos += nbytes
        if ts.is_pool:
            _require(nbytes == 0 or body[-1] == 0, "%s: pool %s does not end with a NUL" % (where, tname))
        else:
            width = ts.row_width
            _require(width > 0, "%s: table %s has no fields" % (where, tname))
            _require(nbytes % width == 0, "%s: table %s holds %d bytes, not a multiple of its %d-byte row" % (where, tname, nbytes, width))
        tables.append(Table(ts, body))
        seen.append(tname)
    _require(pos + TRAILER_BYTES == len(raw), "%s: %d bytes remain after the last table where the 4-byte trailer belongs" % (where, len(raw) - pos))
    trailer = struct.unpack_from("<I", raw, pos)[0]
    return Database(dbname, schema, tables, trailer)


def database_name(raw: Union[bytes, memoryview]) -> str:
    """The database a ``.dbd`` says it belongs to, from its first 32 bytes."""
    raw = bytes(raw)
    _require(len(raw) >= NAME_FIELD_BYTES, "a %d-byte file has no database name" % len(raw))
    return _name32(raw, 0)


# ---------------------------------------------------------------------------
# Synthetic pairs


def build_schema(database: str, tables: Sequence[Tuple[str, str, Sequence[Tuple[str, str, int]]]]) -> bytes:
    """``tables`` are ``(kind, name, fields)`` with fields ``(type, name, param)``."""
    out = bytearray(b"D" + database.encode("latin-1") + b"\x00")
    for kind, name, fields in tables:
        out += kind.encode("latin-1") + name.encode("latin-1") + b"\x00"
        for ftype, fname, param in fields:
            out += ftype.encode("latin-1") + fname.encode("latin-1") + b"\x00" + struct.pack("<H", param)
    out += b"\x00\x00\x00\x00"
    return bytes(out)


def build_data(database: str, tables: Sequence[Tuple[str, bytes]], *, trailer: int = 0) -> bytes:
    """``tables`` are ``(name, body bytes)``: rows already packed, or a NUL-separated pool."""
    out = bytearray()
    for name, body in tables:
        out += database.encode("latin-1").ljust(NAME_FIELD_BYTES, b"\x00")
        out += name.encode("latin-1").ljust(NAME_FIELD_BYTES, b"\x00")
        out += struct.pack("<I", len(body)) + body
    out += struct.pack("<I", trailer)
    return bytes(out)


def pack_row(table: TableSchema, values: Dict[str, object], pools: Optional[Dict[int, Dict[str, int]]] = None) -> bytes:
    """Pack one row for a synthetic data file (strings padded with NUL, references given as offsets)."""
    row = bytearray(table.row_width)
    for f, at in zip(table.fields, table.offsets()):
        value = values.get(f.name, 0)
        if f.is_string:
            raw = str(value).encode("latin-1")[:f.param]
            row[at:at + len(raw)] = raw
        elif f.type == "f":
            struct.pack_into("<f", row, at, float(value))
        elif f.type in FIXED_WIDTH:
            n = FIXED_WIDTH[f.type]
            unit = int.from_bytes(row[at:at + n], "little")
            if f.param:
                unit |= (int(value) & ((1 << f.bits) - 1)) << f.shift
            else:
                unit = int(value) & ((1 << (8 * n)) - 1)
            row[at:at + n] = unit.to_bytes(n, "little")
        else:
            row[at:at + REF_WIDTH[f.type]] = int(value).to_bytes(REF_WIDTH[f.type], "little")
    return bytes(row)


def build_pool(strings: Sequence[str]) -> Tuple[bytes, Dict[str, int]]:
    """A NUL-separated pool beginning with the empty string; returns the bytes and each string's offset."""
    out = bytearray(b"\x00")
    offsets = {"": 0}
    for s in strings:
        if s not in offsets:
            offsets[s] = len(out)
            out += s.encode("latin-1") + b"\x00"
    return bytes(out), offsets

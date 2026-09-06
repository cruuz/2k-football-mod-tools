"""EA's comma-separated tables -- the rosters MVP Baseball 2005 ships as text.

MVP Baseball 2005 (PS2) keeps its players, teams, organisations, managers,
schedules and tuning curves as plain text inside EA ``BIG`` archives
(``/DATA/DATABASE/DATABASE.BIG`` and its neighbours) [M].  Two grammars sit
side by side, and both are byte-exact once the line is kept as the disc wrote
it:

* **EA's indexed grammar** (every ``.dat`` in ``DATABASE.BIG``): the header is
  ``0 name,1 name,...,N name,;`` and every data line is
  ``<row id>,0 value,1 value,...,N value,;`` -- each field carries its own
  column number, a space, then the value, and the line ends with one field
  holding a semicolon [M].  18 tables, 2,923 / 1,432 / 128 / 36 rows.
* **plain CSV** (``PROGRESS.BIG``, ``SCHEDULE.BIG``, ``ROOKIE.BIG`` and the
  33 audio event tables): ``a,b,c`` with no row id, sometimes two header lines,
  sometimes blank or short lines [M].

Lines end in ``\\r\\n`` on every table measured and every file ends with one
[M]; this module keeps each line's own terminator rather than assuming it.

**Byte-exact by construction.**  A table is a list of lines; a cell edit
rebuilds only its own line from the fields the line was split into, joined by
the same commas, and leaves every other line's bytes untouched.  Serialising
an unedited table reproduces its input byte for byte, which is what the
independent verifier of a writer relies on.

Retail-free: nothing here carries a value from any disc.  Standard library
only; importable without Qt.

**Evidence tags.**  **[M]** measured on the retail SLUS-21135 disc.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict, List, Optional, Sequence, Tuple

from mod_editor.games.contract import Refusal

#: A field of the indexed grammar: the column number, one space, the value.
_INDEXED_FIELD = re.compile(r"^(\d+) (.*)$", re.S)

#: The trailer every indexed line ends with: one field holding a semicolon.
INDEXED_TRAILER = ";"


class CsvError(Refusal):
    """A table could not be read or an edit does not fit; the sentence says why."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise CsvError(message)


@dataclass
class Line:
    """One line: its fields, and the terminator it came with."""

    fields: List[str]
    terminator: str
    #: ``True`` when the line is in EA's numbered-field grammar.
    indexed: bool
    #: ``True`` when an indexed line's first field is a row id (a data row);
    #: the header has none.
    has_id: bool

    def render(self) -> str:
        return ",".join(self.fields) + self.terminator


class CsvTable:
    """A table read from *payload*, edited a cell at a time, written back exactly."""

    def __init__(self, payload: bytes, name: str = "this table") -> None:
        self.name = name
        text = bytes(payload).decode("latin-1")
        self.lines: List[Line] = []
        for raw in text.splitlines(keepends=True):
            body = raw
            terminator = ""
            for ending in ("\r\n", "\n", "\r"):
                if raw.endswith(ending):
                    body = raw[:-len(ending)]
                    terminator = ending
                    break
            fields = body.split(",")
            indexed, has_id = self._grammar(fields)
            self.lines.append(Line(fields, terminator, indexed, has_id))
        self.header_index: Optional[int] = None
        for number, line in enumerate(self.lines):
            if line.indexed and not line.has_id:
                self.header_index = number
                break
        if self.header_index is None:
            self.header_index = 0 if self.lines else None

    @staticmethod
    def _numbered(fields: Sequence[str]) -> bool:
        if not fields:
            return False
        for expected, field in enumerate(fields):
            match = _INDEXED_FIELD.match(field)
            if match is None or int(match.group(1)) != expected:
                return False
        return True

    @classmethod
    def _grammar(cls, fields: Sequence[str]) -> Tuple[bool, bool]:
        """``(indexed, has_id)``: the trailer is one ``;`` field, and the values are numbered from 0."""
        if len(fields) < 2 or fields[-1] != INDEXED_TRAILER:
            return False, False
        if cls._numbered(fields[:-1]):
            return True, False
        if len(fields) >= 3 and cls._numbered(fields[1:-1]):
            return True, True
        return False, False

    # -- reading -----------------------------------------------------------

    @property
    def indexed(self) -> bool:
        """Does this table use EA's numbered-field grammar?"""
        return any(line.indexed for line in self.lines)

    def columns(self) -> List[str]:
        """Column names from the header: the indexed names, or the plain first line."""
        if self.header_index is None:
            return []
        header = self.lines[self.header_index]
        if header.indexed:
            return self._strip_numbers(header.fields[:-1])
        return list(header.fields)

    @staticmethod
    def _strip_numbers(fields: Sequence[str]) -> List[str]:
        out = []
        for field in fields:
            match = _INDEXED_FIELD.match(field)
            out.append(match.group(2) if match else field)
        return out

    def data_line_numbers(self) -> List[int]:
        """Line numbers holding a data row: indexed rows with an id, or non-empty plain lines."""
        if self.header_index is None:
            return []
        out = []
        for number, line in enumerate(self.lines):
            if number <= self.header_index:
                continue
            if line.indexed:
                if line.has_id:
                    out.append(number)
            elif not self.indexed and any(field for field in line.fields):
                out.append(number)
        return out

    def row_count(self) -> int:
        return len(self.data_line_numbers())

    def row_id(self, line_number: int) -> str:
        """The row's own id (the first field of an indexed data row), else its line number."""
        line = self.lines[line_number]
        if line.indexed and line.has_id:
            return line.fields[0]
        return str(line_number)

    def values(self, line_number: int) -> List[str]:
        """The row's values, one per column, without the column numbers."""
        line = self.lines[line_number]
        if line.indexed:
            return self._strip_numbers(line.fields[1 if line.has_id else 0:-1])
        return list(line.fields)

    def cell(self, line_number: int, column: int) -> str:
        values = self.values(line_number)
        _require(0 <= column < len(values),
                 "%s line %d has %d column(s), so there is no column %d."
                 % (self.name, line_number, len(values), column))
        return values[column]

    # -- editing -----------------------------------------------------------

    def check_value(self, value: str) -> Optional[str]:
        """Why *value* cannot go into a cell, or ``None``."""
        if "," in value:
            return "a value cannot contain a comma: it would become another field."
        if "\r" in value or "\n" in value:
            return "a value cannot contain a line break: it would become another row."
        try:
            value.encode("latin-1")
        except UnicodeEncodeError:
            return "a value must be Latin-1 text; the disc's tables are single-byte."
        return None

    def set_cell(self, line_number: int, column: int, value: str) -> None:
        """Replace one cell.  Only that line is re-rendered; every other line keeps its bytes."""
        problem = self.check_value(value)
        _require(problem is None, "%s: %s" % (self.name, problem))
        _require(0 <= line_number < len(self.lines),
                 "%s has %d line(s), so there is no line %d."
                 % (self.name, len(self.lines), line_number))
        line = self.lines[line_number]
        if line.indexed:
            first = 1 if line.has_id else 0
            position = first + column
            _require(first <= position < len(line.fields) - 1,
                     "%s line %d has %d column(s), so there is no column %d."
                     % (self.name, line_number, len(line.fields) - 1 - first, column))
            match = _INDEXED_FIELD.match(line.fields[position])
            number = match.group(1) if match else str(column)
            line.fields[position] = "%s %s" % (number, value)
        else:
            _require(0 <= column < len(line.fields),
                     "%s line %d has %d column(s), so there is no column %d."
                     % (self.name, line_number, len(line.fields), column))
            line.fields[column] = value

    def render(self) -> bytes:
        return "".join(line.render() for line in self.lines).encode("latin-1")

    def summary(self) -> Dict[str, object]:
        """Counts and shape; no cell value."""
        return {
            "name": self.name,
            "lines": len(self.lines),
            "rows": self.row_count(),
            "columns": len(self.columns()),
            "indexed": self.indexed,
            "terminators": sorted({line.terminator for line in self.lines}),
        }


def parse_table(payload: bytes, name: str = "this table") -> CsvTable:
    return CsvTable(payload, name=name)


def build_indexed_table(columns: Sequence[str], rows: Sequence[Tuple[str, Sequence[str]]],
                        terminator: str = "\r\n") -> bytes:
    """A table in EA's indexed grammar, from ``(row id, values)`` pairs.  For tests."""
    lines = [",".join("%d %s" % (number, name) for number, name in enumerate(columns))
             + "," + INDEXED_TRAILER + terminator]
    for row_id, values in rows:
        _require(len(values) == len(columns),
                 "row %r has %d value(s) for %d column(s)."
                 % (row_id, len(values), len(columns)))
        lines.append(row_id + "," + ",".join("%d %s" % (number, value)
                                              for number, value in enumerate(values))
                     + "," + INDEXED_TRAILER + terminator)
    return "".join(lines).encode("latin-1")


def build_plain_table(rows: Sequence[Sequence[str]], terminator: str = "\r\n") -> bytes:
    """A plain CSV table, the shape ``PROGRESS.BIG`` uses.  For tests."""
    return "".join(",".join(row) + terminator for row in rows).encode("latin-1")


__all__ = ["CsvError", "CsvTable", "INDEXED_TRAILER", "Line", "build_indexed_table",
           "build_plain_table", "parse_table"]

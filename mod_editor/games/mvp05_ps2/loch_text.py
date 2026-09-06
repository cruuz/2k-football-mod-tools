"""EA's ``LOCH`` string file -- the UI text of MVP Baseball 2005, measured and written.

Three loose files carry every menu string: ``/DATA/FEENG.LOC`` (6,352
strings), ``/DATA/IGENG.LOC`` (1,584) and ``/DATA/MC_ENG.LOC`` (41) [M].  The
layout, measured on all three [M]::

    LOCH  u32 header size (20)  u32 1  u32 1  u32 offset of LOCL
    LOCI  u32 chunk size  u32 count  u32 0   count x (u16 id, u16 string index)
    LOCL  u32 chunk size  u32 0      u32 count  count x u32 offset (from LOCL)
          then the strings: UTF-16LE, NUL-terminated, in offset order

A string's **span** is the distance from its offset to the next offset in
address order (or to the chunk's end), and that is the bound a replacement
must fit: UTF-16LE plus its terminator, NUL-padded to the span, so nothing
after it moves.  Retail-free: no string from the disc is here.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Dict, List, Optional, Tuple

from mod_editor.games.contract import Refusal

from . import containers


class LochError(Refusal):
    """The file is not a LOCH, or an edit does not fit; the sentence says why."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise LochError(message)


@dataclass(frozen=True)
class LochString:
    index: int
    ids: Tuple[int, ...]
    #: Absolute offset of the string's first byte.
    offset: int
    #: Bytes from the string's start to the next string (or the chunk end).
    span: int
    text: str


class LochFile:
    """A parsed ``LOCH`` file; reads strings, replaces one inside its span."""

    def __init__(self, data: bytes, name: str = "this file") -> None:
        self.name = name
        self.data = bytes(data)
        d = self.data
        _require(len(d) >= 20 and d[:4] == containers.LOCH_MAGIC,
                 "%s does not start with LOCH; it is not one of this disc's string files." % name)
        header_size, _one, _two, locl_at = struct.unpack_from("<IIII", d, 4)
        _require(header_size == containers.LOCH_HEADER_SIZE and 20 <= locl_at <= len(d) - 16,
                 "%s declares a %d-byte header and its LOCL at %d, which does not fit %d bytes."
                 % (name, header_size, locl_at, len(d)))
        self.locl_at = locl_at
        self.ids: Dict[int, List[int]] = {}
        loci_at = header_size
        if d[loci_at:loci_at + 4] == containers.LOCI_MAGIC:
            loci_size, count, _zero = struct.unpack_from("<III", d, loci_at + 4)
            for number in range(count):
                position = loci_at + 16 + 4 * number
                if position + 4 > len(d):
                    break
                ident, index = struct.unpack_from("<HH", d, position)
                self.ids.setdefault(index, []).append(ident)
        _require(d[locl_at:locl_at + 4] == containers.LOCL_MAGIC,
                 "%s holds %r where its LOCL chunk should start." % (name, d[locl_at:locl_at + 4]))
        self.locl_size, _zero, self.count = struct.unpack_from("<III", d, locl_at + 4)
        _require(0 <= self.count <= 65536 and locl_at + 16 + 4 * self.count <= len(d),
                 "%s declares %d strings, which do not fit." % (name, self.count))
        self.locl_end = min(len(d), locl_at + self.locl_size)
        offsets = [struct.unpack_from("<I", d, locl_at + 16 + 4 * i)[0] + locl_at
                   for i in range(self.count)]
        bounds = sorted(set(offsets) | {self.locl_end})
        strings: List[LochString] = []
        for index, offset in enumerate(offsets):
            limit = next((edge for edge in bounds if edge > offset), self.locl_end)
            raw = d[offset:limit]
            end = 0
            while end + 1 < len(raw) and raw[end:end + 2] != b"\x00\x00":
                end += 2
            text = raw[:end].decode("utf-16-le", errors="replace")
            strings.append(LochString(index, tuple(self.ids.get(index, ())), offset,
                                      limit - offset, text))
        self.strings: Tuple[LochString, ...] = tuple(strings)

    def string(self, index: int) -> LochString:
        _require(0 <= index < len(self.strings),
                 "%s has %d strings (0..%d), so there is no string %d."
                 % (self.name, len(self.strings), len(self.strings) - 1, index))
        return self.strings[index]

    def check_text(self, index: int, text: str) -> Optional[str]:
        """Why *text* cannot replace string *index*, or ``None``."""
        entry = self.string(index)
        if "\x00" in text:
            return "a string cannot contain NUL; it ends the string."
        try:
            encoded = text.encode("utf-16-le")
        except UnicodeEncodeError as exc:
            return "the text cannot be encoded as UTF-16: %s" % exc
        need = len(encoded) + 2
        if need > entry.span:
            return ("that text is %d byte(s) of UTF-16 plus its terminator and string %d has "
                    "%d to give; shorten it by %d character(s)."
                    % (need, index, entry.span, -(-(need - entry.span) // 2)))
        return None

    def replace(self, index: int, text: str) -> Tuple[bytes, Tuple[int, int]]:
        """The file's bytes with string *index* replaced inside its span, and the range changed."""
        problem = self.check_text(index, text)
        _require(problem is None, "%s: %s" % (self.name, problem))
        entry = self.string(index)
        encoded = text.encode("utf-16-le") + b"\x00\x00"
        padded = encoded + bytes(entry.span - len(encoded))
        out = bytearray(self.data)
        out[entry.offset:entry.offset + entry.span] = padded
        return bytes(out), (entry.offset, entry.span)

    def summary(self) -> Dict[str, object]:
        return {"name": self.name, "bytes": len(self.data), "strings": len(self.strings),
                "ids": sum(len(v) for v in self.ids.values()), "locl_at": self.locl_at,
                "locl_size": self.locl_size}


def parse(data: bytes, name: str = "this file") -> LochFile:
    return LochFile(data, name=name)


__all__ = ["LochError", "LochFile", "LochString", "parse"]

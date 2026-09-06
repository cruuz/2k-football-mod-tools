"""Midway ``SEC `` section container — the plays, stadium scenes and character scenes of
Blitz: The League (1,104 members, 56,971 sections; NFL Blitz Pro carries none) [M].

```
+0x00  "SEC " as a little-endian u32 (' CES' in the bytes)
+0x04  u32  4                 version; 4 on every one measured
+0x08  u32  0
+0x0C  u32  0xCDCDCDCD        an uninitialised-memory fill the writer never cleared
+0x10  u32  sections
+0x14  u32  name-table bytes
+0x18  u32  total bytes       == the file (checked)
+0x1C  sections x { u32 kind; u32 offset; u32 size; u32 name offset }
       name table             NUL-separated, ``name-table bytes`` long
       padding to a 128-byte boundary
       sections               contiguous, each a multiple of 128 bytes, the last ending at total
```

Kind 4 sections are named ``*.rws`` (RenderWare streams); kind 2 sections carry bare names [M].
An **empty** container is 128 bytes: the 28-byte header with zero sections and a
``PAD128`` fill to the end [M] — 106 of The League's 1,104 are empty.

Retail-free: :func:`build_sec` synthesises one for the tests.  Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import List, Optional, Sequence, Tuple, Union

from mod_editor.games.contract import Refusal

SEC_TAG = b" CES"
HEADER_BYTES = 28
ENTRY_BYTES = 16
VERSION = 4
FILL = 0xCDCDCDCD
ALIGN = 128
EMPTY_BYTES = 128
PAD_PATTERN = b"PAD128"


def _require(condition: object, message: str) -> None:
    if not condition:
        raise Refusal(message)


def looks_like_sec(head: Union[bytes, memoryview]) -> bool:
    return bytes(head[:4]) == SEC_TAG


@dataclass(frozen=True)
class Section:
    kind: int
    offset: int
    size: int
    name_offset: int
    name: str


@dataclass
class SecContainer:
    version: int
    fill: int
    sections: List[Section]
    name_table_bytes: int
    total: int
    raw: bytes

    @property
    def is_empty(self) -> bool:
        return not self.sections

    @property
    def first_section_offset(self) -> Optional[int]:
        return self.sections[0].offset if self.sections else None

    def section_bytes(self, section: Section) -> bytes:
        return self.raw[section.offset:section.offset + section.size]

    def identities(self) -> dict:
        s = self.sections
        names_at = HEADER_BYTES + len(s) * ENTRY_BYTES
        return {
            "sections": len(s),
            "contiguous": all(s[i].offset + s[i].size == s[i + 1].offset for i in range(len(s) - 1)),
            "last_ends_at_total": (not s) or s[-1].offset + s[-1].size == self.total,
            "sizes_are_128_multiples": all(x.size % ALIGN == 0 for x in s),
            "first_section_follows_padded_names": (not s) or (names_at + self.name_table_bytes + ALIGN - 1) // ALIGN * ALIGN == s[0].offset,
            "kinds": sorted({x.kind for x in s}),
        }


def parse(raw: Union[bytes, memoryview], where: str = "the section container") -> SecContainer:
    raw = bytes(raw)
    _require(len(raw) >= HEADER_BYTES and raw[:4] == SEC_TAG, "%s does not begin with 'SEC ' as a little-endian word" % where)
    version, zero, fill, count, name_bytes, total = struct.unpack_from("<6I", raw, 4)
    _require(total == len(raw), "%s declares %d bytes for a %d-byte file" % (where, total, len(raw)))
    _require(version == VERSION, "%s is version %d; this reader knows version %d" % (where, version, VERSION))
    names_at = HEADER_BYTES + count * ENTRY_BYTES
    _require(names_at + name_bytes <= len(raw), "%s declares %d sections and %d name bytes, more than the file holds" % (where, count, name_bytes))
    names = raw[names_at:names_at + name_bytes]
    sections: List[Section] = []
    previous_end = (names_at + name_bytes + ALIGN - 1) // ALIGN * ALIGN
    for i in range(count):
        kind, offset, size, name_off = struct.unpack_from("<4I", raw, HEADER_BYTES + i * ENTRY_BYTES)
        _require(name_off < len(names) and (name_off == 0 or names[name_off - 1] == 0),
                 "%s: section %d names a string at %d, not a string start in the %d-byte name table" % (where, i, name_off, len(names)))
        end = names.find(b"\x00", name_off)
        name = names[name_off:end if end >= 0 else len(names)].decode("latin-1")
        _require(offset == previous_end, "%s: section %d (%s) starts at %d, not where the previous ended (%d)" % (where, i, name, offset, previous_end))
        _require(offset + size <= total, "%s: section %d (%s) runs past the end" % (where, i, name))
        sections.append(Section(kind, offset, size, name_off, name))
        previous_end = offset + size
    if count:
        _require(previous_end == total, "%s: the last section ends at %d, not at the file's %d" % (where, previous_end, total))
    return SecContainer(version, fill, sections, name_bytes, total, raw)


def build_sec(sections: Sequence[Tuple[int, str, bytes]] = ()) -> bytes:
    """A container of ``(kind, name, bytes)`` sections, each padded to 128; none gives the 128-byte empty form."""
    if not sections:
        head = SEC_TAG + struct.pack("<6I", VERSION, 0, FILL, 0, 0, EMPTY_BYTES)
        pad = (PAD_PATTERN * (EMPTY_BYTES // len(PAD_PATTERN) + 1))[:EMPTY_BYTES - len(head)]
        return head + pad
    names = bytearray()
    offsets: List[int] = []
    for _, name, _ in sections:
        offsets.append(len(names))
        names += name.encode("latin-1") + b"\x00"
    names_at = HEADER_BYTES + len(sections) * ENTRY_BYTES
    first = (names_at + len(names) + ALIGN - 1) // ALIGN * ALIGN
    table = bytearray()
    body = bytearray()
    cursor = first
    for (kind, _, data), name_off in zip(sections, offsets):
        padded = (len(data) + ALIGN - 1) // ALIGN * ALIGN
        table += struct.pack("<4I", kind, cursor, padded, name_off)
        body += data + bytes(padded - len(data))
        cursor += padded
    head = SEC_TAG + struct.pack("<6I", VERSION, 0, FILL, len(sections), len(names), cursor)
    return head + bytes(table) + bytes(names) + bytes(first - names_at - len(names)) + bytes(body)

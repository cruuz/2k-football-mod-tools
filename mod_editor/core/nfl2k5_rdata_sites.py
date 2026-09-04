"""Shared helper for executable patches that rewrite fixed ``.rdata`` spans in ``default.xbe``.

Several small patches are nothing but "replace these bytes at this virtual address": a reordered
pointer list, a descriptor list with a row added, a constant table. They all need the same three
things: the retail bytes pinned so a foreign executable is refused, ``retail | applied | foreign``
over every site at once, and the section SHA-1 digest recomputed after the write (the kernel checks
it at load). This module carries that once; each patch declares its sites.
"""

from __future__ import annotations

import struct
from typing import Mapping, Sequence

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest

IMAGE_BASE = 0x10000


class RdataSiteError(ValueError):
    """The executable does not carry the retail bytes the patch expects."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RdataSiteError(message)


def header_size(payload: bytes) -> int:
    return struct.unpack_from("<I", payload, 0x108)[0]


def offset_of(payload: bytes, va: int) -> int:
    """File offset of a virtual address (header or any section)."""

    try:
        if IMAGE_BASE <= va < IMAGE_BASE + header_size(payload):
            return va - IMAGE_BASE
        sections = _sections(payload)
    except (ValueError, struct.error) as exc:      # BumpStrengthError is a ValueError: not an XBE we know
        raise RdataSiteError(f"not a retail-shaped XBE: {exc}") from exc
    for section in sections:
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise RdataSiteError(f"VA 0x{va:x} is in no section")


def status(payload: bytes, sites: Sequence[tuple[str, int, bytes, bytes]]) -> str:
    """``sites`` = (label, va, retail_bytes, patched_bytes)."""

    states = set()
    try:
        for _label, va, before, after in sites:
            _require(len(before) == len(after), f"{_label}: retail and patched spans differ in length")
            off = offset_of(payload, va)
            got = payload[off: off + len(before)]
            states.add("retail" if got == before else "applied" if got == after else "foreign")
    except (RdataSiteError, ValueError, struct.error):
        return "foreign"
    if states == {"retail"}:
        return "retail"
    if states == {"applied"}:
        return "applied"
    return "foreign"


def apply(payload: bytes, sites: Sequence[tuple[str, int, bytes, bytes]], what: str) -> tuple[bytes, Mapping[str, object]]:
    state = status(payload, sites)
    if state == "applied":
        return payload, {"already_applied": True, "edits": [], "changed_bytes": 0}
    _require(state == "retail", f"{what} sites are {state}, not retail")
    buf = bytearray(payload)
    sections = _sections(payload)
    touched = set()
    edits = []
    for label, va, before, after in sites:
        off = offset_of(payload, va)
        buf[off: off + len(after)] = after
        touched.add(_section_for_offset(sections, off).index)
        edits.append({"label": label, "va": f"0x{va:x}", "file_offset": f"0x{off:x}", "bytes": len(after)})
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d: d + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    _require(status(patched, sites) == "applied", f"{what}: post-apply verification failed")
    return patched, {"edits": edits, "changed_bytes": sum(1 for a, b in zip(payload, patched) if a != b),
                     "sections_repinned": sorted(touched)}


__all__ = ["IMAGE_BASE", "RdataSiteError", "apply", "header_size", "offset_of", "status"]

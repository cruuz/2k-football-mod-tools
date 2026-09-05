"""EXPERIMENTAL / UNWITNESSED: the USA Xbox franchise completion gate only.

The signed imm8 comparison at 0x2480CB permits indices through 127 after
this patch. Index 128 still fails in retirement (stage 1). Calendar, DOB,
and other engine consumers are NOT repaired. No cave or runtime data is used.
See ASTRA_SEASON_CAP_REPORT.md for the full-engine specification and witnesses.
"""
from __future__ import annotations

import struct

from .nfl2k5_bump_strength import _sections, section_digest

GATE_VA = 0x2480CD
MAX_SEASON_INDEX = 127
SEASON_COUNT = MAX_SEASON_INDEX + 1
UI_LABEL = "Franchise runs to 128 seasons. Dates and ages after 2099 are not repaired yet."
CONTEXT_VA = 0x2480C6
# Getter, cmp eax,30, jle, stage getter/test and completion path, through ret.
RETAIL_CONTEXT = bytes.fromhex(
    "e8e5cde7ff83f81e7e27e8cbf9ffff83f801751dba6090e8008bcbe83a64f0ff"
    "8bcbe81363e2ff33c05f5e5d5b8be55dc3")
_INDEX = GATE_VA - CONTEXT_VA
PATCHED_CONTEXT = RETAIL_CONTEXT[:_INDEX] + b"\x7f" + RETAIL_CONTEXT[_INDEX + 1:]
CAVES = ()
RUNTIME_GLOBALS = ()


class SeasonCapError(ValueError):
    """Foreign or incomplete executable; no bytes changed."""


def _site(payload: bytes):
    sections = _sections(payload)
    matches = [s for s in sections if s.virtual_address <= CONTEXT_VA
               and CONTEXT_VA + len(RETAIL_CONTEXT) <= s.virtual_address + s.raw_size]
    if len(matches) != 1:
        raise SeasonCapError("season-cap context must occupy one file-backed section")
    section = matches[0]
    if section.raw_offset < 0 or section.raw_offset + section.raw_size > len(payload):
        raise SeasonCapError("truncated season-cap section")
    offset = section.raw_offset + CONTEXT_VA - section.virtual_address
    return section, offset


def status(payload: bytes) -> str:
    """retail / applied / foreign, including the unchanged branch/stage context."""
    try:
        _, off = _site(payload)
        got = payload[off:off + len(RETAIL_CONTEXT)]
        if got == RETAIL_CONTEXT:
            return "retail"
        if got == PATCHED_CONTEXT:
            return "applied"
    except (ValueError, struct.error, IndexError):
        pass
    return "foreign"


def apply(payload: bytes) -> tuple[bytes, dict[str, object]]:
    """Idempotent one-byte edit with the existing XBE section-digest scheme."""
    state = status(payload)
    if state == "foreign":
        raise SeasonCapError("season-cap sites are foreign; refusing")
    receipt: dict[str, object] = {
        "status": "applied", "experimental": True, "witnessed": False,
        "max_season_index": MAX_SEASON_INDEX, "season_count": SEASON_COUNT,
        "label": UI_LABEL, "calendar_repaired": False,
        "already_applied": state == "applied", "edits": [],
        "changed_bytes": 0, "sections_repinned": [],
    }
    if state == "applied":
        return bytes(payload), receipt
    section, start = _site(payload)
    off = start + _INDEX
    buf = bytearray(payload)
    buf[off] = MAX_SEASON_INDEX  # 83 /7 sign-extends imm8: FF would mean -1.
    digest_off = section.header_offset + 36
    buf[digest_off:digest_off + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    if status(patched) != "applied":
        raise SeasonCapError("season-cap post-apply verification failed")
    receipt.update({
        "edits": [{"label": "franchise_completion_limit", "va": hex(GATE_VA),
                   "file_offset": hex(off), "bytes": 1, "before": "1e", "after": "7f"}],
        "changed_bytes": sum(a != b for a, b in zip(payload, patched)),
        "sections_repinned": [section.index],
    })
    return patched, receipt

"""NFL Week 9 trade deadline for the 2026 franchise (b778-tr1).

Retail ESPN NFL 2K5 closes in-season trading long before the modern NFL does:

* the Player Trade screen refuses a proposal when ``FUN_00247d10``'s week
  counter has passed 6 (``cmp eax,6`` at 0x2B8BC3, block at 0x2B8BD2 with the
  native message "You cannot make a trade after the trade deadline.";
  displayed week = stored week + 1, so retail blocks from Week 8);
* the Front Office gates the TRADES and TRADING BLOCK rows with the same
  week counter through ``FUN_00247d10``: ``stage_table[8].byte5`` is 6, and
  ``week < 6`` keeps the rows visible. Retail therefore hides both rows from
  displayed Week 7, which is the "I cannot offer trades during the season"
  report from a 2026 franchise.

The 2026 SOFTDRINK season is 18 weeks, but it is otherwise the 2004 rules.
This owner keeps the native gate, wording and menu machinery and moves only
their week boundary to the modern NFL deadline: trades stay open through
displayed Week 9 and close from displayed Week 10.

Both edits are in-place immediates, so there is no cave, no allocation and no
save change:

* ``stage_table[8].byte5`` 6 -> 9 (``week < 9``: rows visible through stored
  week 8, displayed Week 9);
* ``cmp eax,6`` -> ``cmp eax,8`` at 0x2B8BC3 (allow stored week 0..8, block
  stored 9 = displayed Week 10).

The screen comparison and the menu predicate therefore agree exactly; retail
lets the screen through one week after the menu row has already gone. The
Trade Deadline setup option keeps its meaning: with it Off the predicate
returns open and the screen skips the check, so this patch changes nothing.

Touched sections (``.text`` for the screen guard, ``.data`` for the stage
table) have their XBE digests recomputed. Status is fail-closed: a mixed or
unrecognised image is ``foreign`` and ``apply`` refuses it.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

from .nfl2k5_bump_strength import _section_for_offset, _sections, section_digest

OWNER = "nfl2k5_trade_deadline"
DEADLINE_WEEK = 9                     # displayed (1-based) NFL week: Week 9 stays open
SCREEN_WEEK_LIMIT = DEADLINE_WEEK - 1  # stored week compared by ``cmp eax,8``
PREDICATE_WEEK_LIMIT = DEADLINE_WEEK   # stage byte: ``week < 9``
RETAIL_SCREEN_WEEK = 6
RETAIL_PREDICATE_WEEK = 6

SCREEN_VA = 0x002B8BC5                # immediate of ``cmp eax,6`` inside the trade screen guard
SCREEN_GUARD_VA, SCREEN_GUARD_RETAIL = 0x002B8BAB, bytes.fromhex(
    "a12401e600"        # mov eax,[0xe60124]  (Trade Deadline option)
    "85c0"              # test eax,eax
    "744c"              # je allow
    "e8f7bfe0ff"        # call 0xc4bb0 (stage)
    "83f808"            # cmp eax,8
    "750a"              # jne postseason check
    "e8adc2e0ff"        # call 0xc4e70 (week)
    "83f806"            # cmp eax,6
    "7f0a"              # jg block
)
STAGE_VA = 0x005151C5                 # stage table row 8 byte +5: ``week < byte``
STAGE_GUARD_VA, STAGE_GUARD_SIZE = 0x005151C0, 16
STAGE_GUARD_HEAD = bytes.fromhex("0c8fe800")
STAGE_GUARD_TAIL = bytes.fromhex("00000100000001000000")
STAGE_WEEKS_CHOICES = (0x11, 0x12)    # retail 17-week season, 2026 18-week season
STAGE_DEADLINE_CHOICES = (RETAIL_PREDICATE_WEEK, PREDICATE_WEEK_LIMIT)


class TradeDeadlineError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TradeDeadlineError(message)


@dataclass(frozen=True)
class Site:
    label: str
    va: int
    retail: bytes
    patched: bytes
    note: str

    @property
    def size(self) -> int:
        return len(self.retail)


def sites() -> tuple[Site, ...]:
    return (
        Site("trade_screen_week_limit", SCREEN_VA, bytes([RETAIL_SCREEN_WEEK]), bytes([SCREEN_WEEK_LIMIT]),
             "FUN_002b8b94: cmp eax,6 -> 8; the native pause stays open through stored week 8 (displayed Week 9)"),
        Site("stage_table_season_deadline", STAGE_VA, bytes([RETAIL_PREDICATE_WEEK]), bytes([PREDICATE_WEEK_LIMIT]),
             "stage table row 8 byte +5: the TRADES and TRADING BLOCK rows show while week < 9 (displayed Week 9)"),
    )


def _offset(payload: bytes, va: int, sections) -> int:
    header_size = int.from_bytes(payload[0x108:0x10C], "little")
    if 0x10000 <= va < 0x10000 + header_size:
        return va - 0x10000
    for section in sections:
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise TradeDeadlineError(f"VA 0x{va:x} is in no section")


def _read(payload: bytes, va: int, size: int, sections) -> bytes:
    off = _offset(payload, va, sections)
    return payload[off:off + size]


def _screen_state(payload: bytes, sections) -> str:
    guard = _read(payload, SCREEN_GUARD_VA, len(SCREEN_GUARD_RETAIL), sections)
    if guard == SCREEN_GUARD_RETAIL:
        return "retail"
    patched = bytearray(SCREEN_GUARD_RETAIL)
    patched[SCREEN_VA - SCREEN_GUARD_VA] = SCREEN_WEEK_LIMIT
    if guard == bytes(patched):
        return "applied"
    return "foreign"


def _stage_state(payload: bytes, sections) -> str:
    row = _read(payload, STAGE_GUARD_VA, STAGE_GUARD_SIZE, sections)
    if row[:4] != STAGE_GUARD_HEAD or row[6:STAGE_GUARD_SIZE] != STAGE_GUARD_TAIL or row[4] not in STAGE_WEEKS_CHOICES:
        return "foreign"
    deadline = row[5]
    if deadline == RETAIL_PREDICATE_WEEK:
        return "retail"
    if deadline == PREDICATE_WEEK_LIMIT:
        return "applied"
    return "foreign"


def status(payload: bytes) -> str:
    try:
        sections = _sections(payload)
        states = (_screen_state(payload, sections), _stage_state(payload, sections))
    except (TradeDeadlineError, ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError):
        return "foreign"
    if states == ("retail", "retail"):
        return "retail"
    if states == ("applied", "applied"):
        return "applied"
    return "foreign"


def apply(payload: bytes) -> tuple[bytes, dict]:
    """Patch a retail/applied XBE copy; refuse mixed, foreign or short images."""
    state = status(payload)
    _require(state != "foreign", "trade-deadline sites are foreign or mixed; refusing")
    if state == "applied":
        return payload, dict(owner=OWNER, status="already_applied", changed_bytes=0, file_growth=0,
                             deadline_week=DEADLINE_WEEK)
    sections = _sections(payload)
    buf = bytearray(payload)
    edits = []
    touched: set[int] = set()
    for site in sites():
        off = _offset(payload, site.va, sections)
        _require(bytes(buf[off:off + site.size]) == site.retail, f"trade-deadline site {site.label} is not retail")
        buf[off:off + site.size] = site.patched
        touched.add(_section_for_offset(sections, off).index)
        edits.append(dict(label=site.label, va=hex(site.va), before=site.retail.hex(), after=site.patched.hex()))
    for section in sections:
        if section.index in touched:
            digest_at = section.header_offset + 36
            buf[digest_at:digest_at + 20] = section_digest(bytes(buf), section)
    result = bytes(buf)
    _require(status(result) == "applied", "trade-deadline postcondition failed")
    return result, dict(owner=OWNER, status="applied", deadline_week=DEADLINE_WEEK,
                        screen_week_limit=SCREEN_WEEK_LIMIT, predicate_week_limit=PREDICATE_WEEK_LIMIT,
                        changed_bytes=sum(a != b for a, b in zip(payload, result)),
                        file_growth=len(result) - len(payload),
                        before_sha256=hashlib.sha256(payload).hexdigest(),
                        after_sha256=hashlib.sha256(result).hexdigest(),
                        sections_repinned=sorted(touched), edits=edits)


__all__ = ["DEADLINE_WEEK", "OWNER", "PREDICATE_WEEK_LIMIT", "RETAIL_PREDICATE_WEEK", "RETAIL_SCREEN_WEEK",
           "SCREEN_WEEK_LIMIT", "SCREEN_VA", "STAGE_VA", "Site", "TradeDeadlineError", "apply", "sites", "status"]

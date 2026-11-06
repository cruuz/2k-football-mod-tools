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

Two follow-up boundaries (b780-season1). The weekly advance and the weekly
inbox stories read the same stored week and still used the retail deadline,
so beta-78 through beta-80 builds (v0.7 to v0.9) kept trading open through
Week 9 while the game acted as if it had closed after Week 7:

* the pending-trade purge: with the option on, the Season case of the weekly
  advance (``FUN_00247d40``, before its week increment) clears the 15 pending
  trade offers (``0xE3C27C``, 60 bytes each, ``FUN_002bb660``) on every tick
  after stored week 6, the retail screen limit. The tick that ends displayed
  Week 8 already emptied the offer list for Week 9, the last open week (CPU
  offers made in that tick were cleared in the same tick). ``cmp eax,6`` ->
  ``cmp eax,8`` at 0x247E31: the purge starts with the tick after the last open
  week, as in retail;
* the "The Trade Deadline is upon us" inbox story (story 17, posted by
  ``FUN_0027eb80`` after the week increment) came when the new week was 5,
  the last week retail shows the trade rows (``week < 6``), so it arrived at
  Week 6, three weeks early. ``cmp eax,5`` -> ``cmp eax,8`` at 0x27ECF6: it
  comes at Week 9, the last week the rows show now.

``apply`` writes all four bytes on a retail image. ``repair_followups`` adds
the two follow-ups to an image a two-site version already moved (``status``
still reads the two original sites, so those images stay ``applied``).
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

# b780-season1 follow-ups: (label, context VA, retail context, immediate VA, retail, patched, note). The context is the
# complete retail instruction run around the compared immediate; only that one byte may differ.
PURGE_CONTEXT_VA = 0x00247E23
PURGE_CONTEXT_RETAIL = bytes.fromhex(
    "a12401e600"        # mov eax,[0xe60124]  (Trade Deadline option)
    "85c0"              # test eax,eax
    "742a"              # je skip
    "e83fd0e7ff"        # call 0xc4e70 (week)
    "83f806"            # cmp eax,6
    "7e20"              # jle skip (else FUN_002bb660 clears the 15 offers at 0xE3C27C)
)
PURGE_VA = 0x00247E33
STORY_CONTEXT_VA = 0x0027ECE7
STORY_CONTEXT_RETAIL = bytes.fromhex(
    "e8c45ee4ff"        # call 0xc4bb0 (stage)
    "83f808"            # cmp eax,8 (Season)
    "7522"              # jne next story
    "e87a61e4ff"        # call 0xc4e70 (week, already advanced)
    "83f805"            # cmp eax,5
    "7518"              # jne next story
    "833d2401e60001"    # cmp dword [0xe60124],1 (Trade Deadline option)
    "750f"              # jne next story
    "ba11000000"        # mov edx,0x11 (story 17, "The Trade Deadline is upon us. Will there be a deal?")
    "b93f000000"        # mov ecx,0x3f
    "e8adf6ffff"        # call 0x27e3c0 (post the story)
)
STORY_VA = 0x0027ECF8
RETAIL_PURGE_WEEK = 6
PURGE_WEEK_LIMIT = SCREEN_WEEK_LIMIT          # purge from the tick after the last open week (stored 9)
RETAIL_STORY_WEEK = RETAIL_PREDICATE_WEEK - 1
STORY_WEEK = PREDICATE_WEEK_LIMIT - 1         # the last week the trade rows show (stored 8, displayed Week 9)
FOLLOWUPS = (
    ("pending_trade_purge_week", PURGE_CONTEXT_VA, PURGE_CONTEXT_RETAIL, PURGE_VA, RETAIL_PURGE_WEEK, PURGE_WEEK_LIMIT,
     "FUN_00247d40 Season tick: cmp eax,6 -> 8; the pending trade offers are cleared from the tick after Week 9"),
    ("deadline_story_week", STORY_CONTEXT_VA, STORY_CONTEXT_RETAIL, STORY_VA, RETAIL_STORY_WEEK, STORY_WEEK,
     "FUN_0027eb80 story 17: cmp eax,5 -> 8; 'The Trade Deadline is upon us' comes at Week 9, the last open week"),
)


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


def followup_sites() -> tuple[Site, ...]:
    """The two b780-season1 follow-up immediates (one byte each, in ``.text``)."""
    return tuple(Site(label, va, bytes([retail]), bytes([patched]), note)
                 for label, _cva, _ctx, va, retail, patched, note in FOLLOWUPS)


def _followup_state(payload: bytes, sections, followup) -> str:
    _label, context_va, context, va, retail, patched, _note = followup
    got = bytearray(_read(payload, context_va, len(context), sections))
    at = va - context_va
    value = got[at]
    got[at] = context[at]
    if bytes(got) != context:
        return "foreign"
    return "retail" if value == retail else "applied" if value == patched else "foreign"


def followups_status(payload: bytes) -> str:
    """'retail' / 'applied' (both follow-ups) / 'partial' (one) / 'foreign' (a context byte differs)."""
    try:
        sections = _sections(payload)
        states = {_followup_state(payload, sections, f) for f in FOLLOWUPS}
    except (TradeDeadlineError, ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError):
        return "foreign"
    if "foreign" in states:
        return "foreign"
    return states.pop() if len(states) == 1 else "partial"


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


def _write(payload: bytes, selected) -> tuple[bytes, list, list]:
    sections = _sections(payload)
    buf = bytearray(payload)
    edits = []
    touched: set[int] = set()
    for site in selected:
        off = _offset(payload, site.va, sections)
        _require(bytes(buf[off:off + site.size]) == site.retail, f"trade-deadline site {site.label} is not retail")
        buf[off:off + site.size] = site.patched
        touched.add(_section_for_offset(sections, off).index)
        edits.append(dict(label=site.label, va=hex(site.va), before=site.retail.hex(), after=site.patched.hex()))
    for section in sections:
        if section.index in touched:
            digest_at = section.header_offset + 36
            buf[digest_at:digest_at + 20] = section_digest(bytes(buf), section)
    return bytes(buf), sorted(touched), edits


def apply(payload: bytes) -> tuple[bytes, dict]:
    """Patch a retail/applied XBE copy; refuse mixed, foreign or short images.

    A retail image gets the two boundaries and the two follow-ups; an image a two-site version already moved is left
    to ``repair_followups`` (this returns it unchanged, as before)."""
    state = status(payload)
    _require(state != "foreign", "trade-deadline sites are foreign or mixed; refusing")
    if state == "applied":
        return payload, dict(owner=OWNER, status="already_applied", changed_bytes=0, file_growth=0,
                             deadline_week=DEADLINE_WEEK)
    _require(followups_status(payload) == "retail", "trade-deadline follow-up sites are not retail; refusing")
    result, touched, edits = _write(payload, sites() + followup_sites())
    _require(status(result) == "applied", "trade-deadline postcondition failed")
    _require(followups_status(result) == "applied", "trade-deadline follow-up postcondition failed")
    return result, dict(owner=OWNER, status="applied", deadline_week=DEADLINE_WEEK,
                        screen_week_limit=SCREEN_WEEK_LIMIT, predicate_week_limit=PREDICATE_WEEK_LIMIT,
                        purge_week_limit=PURGE_WEEK_LIMIT, story_week=STORY_WEEK,
                        changed_bytes=sum(a != b for a, b in zip(payload, result)),
                        file_growth=len(result) - len(payload),
                        before_sha256=hashlib.sha256(payload).hexdigest(),
                        after_sha256=hashlib.sha256(result).hexdigest(),
                        sections_repinned=sorted(touched), edits=edits)


def repair_followups(payload: bytes) -> tuple[bytes, dict]:
    """Add the two follow-ups to an image whose deadline is already moved (idempotent; refuses anything else)."""
    _require(status(payload) == "applied", "the trade deadline is not moved on this image; refusing the follow-ups")
    state = followups_status(payload)
    _require(state in ("retail", "partial", "applied"), "trade-deadline follow-up sites are foreign; refusing")
    receipt = dict(owner=OWNER, purge_week_limit=PURGE_WEEK_LIMIT, story_week=STORY_WEEK)
    if state == "applied":
        return payload, dict(receipt, already_applied=True, changed_bytes=0, edits=[])
    sections = _sections(payload)
    pending = [site for site, followup in zip(followup_sites(), FOLLOWUPS)
               if _followup_state(payload, sections, followup) == "retail"]
    result, touched, edits = _write(payload, pending)
    _require(status(result) == "applied" and followups_status(result) == "applied",
             "trade-deadline follow-up postcondition failed")
    return result, dict(receipt, already_applied=False, changed_bytes=sum(a != b for a, b in zip(payload, result)),
                        sections_repinned=touched, edits=edits)


__all__ = ["DEADLINE_WEEK", "FOLLOWUPS", "OWNER", "PREDICATE_WEEK_LIMIT", "PURGE_VA", "PURGE_WEEK_LIMIT",
           "RETAIL_PREDICATE_WEEK", "RETAIL_PURGE_WEEK", "RETAIL_SCREEN_WEEK", "RETAIL_STORY_WEEK", "SCREEN_WEEK_LIMIT",
           "SCREEN_VA", "STAGE_VA", "STORY_VA", "STORY_WEEK", "Site", "TradeDeadlineError", "apply", "followup_sites",
           "followups_status", "repair_followups", "sites", "status"]

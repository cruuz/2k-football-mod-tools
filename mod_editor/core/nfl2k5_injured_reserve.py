"""Modern franchise injured reserve (b780 IR1). EXPERIMENTAL, late allocator owner; the Pro Bowl guard is in place.

Why (Noah, 2026-11-03, about 23:50): "Do the full modern IR now". His first ask: "an IR setup to keep players on the team
for franchise? Expand roster size for IR? Modern IR rules?"

What the game does today (retail and the v0.9 RC alike; HUNT6, IR_SCOPE.md)
---------------------------------------------------------------------------
* One table, 0xE421E0: 32 clubs x 5 player pointers. 0x246FF0 puts a player in the first free slot and takes him off
  the club (0x2BD900(club, player, 0, 0), not to free agency); the season rollover (0x246F90, from 0x247B40) brings
  every one back. So IR is season-ending and holds 5 per club.
* The CPU's weekly pass 0x2BE020 (week sim 0x247DCA, stages 8 and 9) needs player +0x28 bits 5..9, which no roster
  carries and the simulator never sets: in a simulated franchise the CPU never uses IR. It also walks the two Pro Bowl
  clubs (league slots 32, 33) in the postseason, and a placement there would write past the table into 0xE42460 (Q66).
* The payroll 0xC3F00 already adds 0x246F20, the salaries of the club's IR players, into club +0x124.

What this owner does
--------------------
* The Pro Bowl guard (Q66, every preset, also on its own: ``apply(payload, mode="guard")``): HUNT6's 34-byte rewrite of
  0x246FF0's head, ``cmp al, 0x20 / jae fail / imul ecx, eax, 20``: a league index of 32 or more places nobody.
* Modern IR (``mode="modern"``): a store of 20 entries per club in this owner's writable data (players stay with their
  club, off the 53), the 4-game minimum (the club's played games in the schedule grid, so a bye is not a game), 8
  returns a club a season, the CPU's long-injury rule (4 or more weeks out) and return rule, the user's IR button
  (place, or activate when the selected player is on IR), the franchise start (a roster's injured players with 4 or
  more weeks out start on IR), the rollover (everyone back, returns reset) and the save extension.
  Code: ``tools/injured_reserve/runtime.c`` (rules in its header). Hooks: the seven retail IR routines become jumps to
  the store's versions, the CPU pass, the IR button handler, the front office writer and loader tails, the franchise
  start. The retail table stays as a mirror of each club's first five entries, so its other readers (the practice
  squad's "listed" checks, the arena owner, the native writer) need no change.
* Save format: ``nfl2k5_injured_reserve_save`` (the high halves of the retail IR block; no size change).

Memory: 6,144 B code + 5,312 B data in the scale-out (``REQUESTS``). Not at 64 MB: the 64 MB profile is the legacy
layout, which has no room for it (``nfl2k5_memory_budget``); a 64 MB build keeps the 2004 IR with the guard.
"""
from __future__ import annotations

import hashlib
import struct

from . import nfl2k5_injured_reserve_code as runtime
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_injured_reserve"
EVIDENCE = "EXPERIMENTAL"
BUILD_CAPTION = "Modern injured reserve (franchise)"
HELP_TEXT = (
    "EXPERIMENTAL. Franchise injured reserve works like today's NFL: a player on IR stays with his club but off the "
    "53, so the club can sign someone; he must miss at least 4 games; each club can bring back up to 8 players a season "
    "(after that he stays out for the season). CPU clubs put players with long injuries on IR and bring them back when "
    "healthy. Up to 20 per club, IR salaries count against the cap, the season rollover brings everyone back. Saves "
    "keep working on older builds (they see up to 5 IR players a club). Off at 64 MB (2004 IR stays).")
GUARD_CAPTION = "Pro Bowl injured reserve guard"
GUARD_HELP = ("A fix: in the postseason the CPU's weekly injured reserve pass also walks the two Pro Bowl teams, and a "
              "placement there would write past the injured reserve list into other franchise data. With this fix "
              "nobody is placed for those teams. In place, no memory cost.")
MODES = ("guard", "modern")
CODE_SIZE = 6144
STORE_SIZE = 5312                    # struct store: 64-byte header + 32 x (4 + 20 x 8)
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", STORE_SIZE, 16))
CONFIG_AT = runtime.LABELS["ir_config"]
CONFIG_MAGIC, CONFIG_VERSION = 0x434D5249, 1    # "IRMC"
CAP, LEGACY_SLOTS, EXTENDED_CAP, MIN_GAMES, RETURNS, LONG_WEEKS = 20, 5, 102, 4, 8, 4

GUARD_VA = 0x246FF0
GUARD_RETAIL = bytes.fromhex("56578bf28bf98bcee8a3dce7ff8d0c80c1e1028b91f021e40085d274055f33c05ec3")
GUARD = bytes.fromhex("56578bf28bf98bcee8a3dce7ff3c20730c6bc81483b9f021e4000074055f33c05ec3")   # HUNT6, Q66

# (label, VA, retail bytes, entry label, opcode, length)
HOOKS = (
    ("count", 0x246E50, "56578bf133ff", "ir_count", 0xE9, 6),
    ("get", 0x246EC0, "56578bfa33f6", "ir_get", 0xE9, 6),
    ("clear", 0x246F00, "57b9a0000000", "ir_clear", 0xE9, 6),
    ("payroll", 0x246F20, "53568bf133db", "ir_payroll", 0xE9, 6),
    ("rollover", 0x246F90, "5355565733db", "ir_rollover", 0xE9, 6),
    ("place", 0x246FF0, "56578bf28bf9", "ir_place", 0xE9, 6),          # the guard's first six bytes (retail's too)
    ("user_action", 0x247070, "538bd9e808db", "ir_user_action", 0xE9, 6),
    ("find", 0x247110, "5356578bf98b", "ir_find", 0xE9, 6),
    ("weekly", 0x2BE020, "51e88a6be0ff", "ir_weekly", 0xE9, 6),
    ("save", 0x2D09FD, "be40cce300", "ir_save_stub", 0xE8, 5),
    ("load", 0x2D0F70, "c744241000000000", "ir_load_stub", 0xE8, 8),
    ("start", 0x13EEDA, "e8c15ff8ff", "ir_start_hook", 0xE8, 5),
)
STAMP = hashlib.sha256(runtime.CODE).hexdigest()[:16]
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, AttributeError)


class InjuredReserveOwnerError(ValueError):
    """Unsupported executable, foreign or mixed installation, or no room for the owner."""


def _require(ok, message):
    if not ok:
        raise InjuredReserveOwnerError(message)


def code_for(code_va: int, store_va: int) -> bytes:
    """The owned RX content: the template with its relocations applied and the config filled."""
    out = bytearray(runtime.CODE)
    for offset, kind, symbol, value in runtime.RELOCATIONS:
        _require(symbol == "code", "unexpected injured reserve relocation")
        target = code_va + value + struct.unpack_from("<i", out, offset)[0]
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", out, offset, target & 0xFFFFFFFF)
    struct.pack_into("<4I", out, CONFIG_AT, CONFIG_MAGIC, CONFIG_VERSION, store_va, 0)
    _require(len(out) <= CODE_SIZE, "the injured reserve runtime exceeds its allocation")
    return bytes(out).ljust(CODE_SIZE, b"\xcc")


def _rel32(source_end, target):
    return struct.pack("<i", target - source_end)


def sites(code_va: int) -> list[tuple[str, int, bytes, bytes]]:
    """Every executable edit of the modern install as (label, VA, retail bytes, patched bytes); the guard is
    separate (GUARD_VA) and the place hook's six bytes sit on top of it."""
    out = []
    for label, va, before, entry, opcode, length in HOOKS:
        patched = bytes([opcode]) + _rel32(va + 5, code_va + runtime.LABELS[entry]) + b"\x90" * (length - 5)
        out.append((label, va, bytes.fromhex(before), patched))
    return out


def allocations(payload: bytes) -> dict[str, dict]:
    if space.status(payload) != "applied":
        return {}
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    by = {r["kind"]: r for r in rows}
    _require(len(rows) == len(by) and set(by) <= {"code", "data"}, "foreign injured reserve allocation")
    return by


def _guard_state(image: XbeImage) -> str:
    raw = image.read(GUARD_VA, len(GUARD))
    if raw == GUARD_RETAIL:
        return "retail"
    if raw == GUARD:
        return "guard"
    if raw[6:] == GUARD[6:] and raw[:1] == b"\xe9" and raw[5:6] == b"\x90":
        return "hooked"
    return "foreign"


def _recognize(payload: bytes) -> str:
    image = XbeImage(payload)
    guard = _guard_state(image)
    rows = allocations(payload)
    if not rows:
        others = {("retail" if image.read(va, len(before)) == before else "foreign")
                  for _l, va, before, _p in sites(0) if va != GUARD_VA}
        _require(others == {"retail"} and guard in ("retail", "guard"), "foreign or partial injured reserve sites")
        return guard
    _require(set(rows) == {"code", "data"} and rows["code"]["size"] == CODE_SIZE and rows["data"]["size"] >= STORE_SIZE,
             "foreign injured reserve allocation")
    code_va, store_va = rows["code"]["va"], rows["data"]["va"]
    _require(guard == "hooked", "the Pro Bowl guard is missing under the modern install")
    for _label, va, _before, patched in sites(code_va):
        _require(image.read(va, len(patched)) == patched, f"injured reserve site {va:#x} is foreign")
    _require(image.read(code_va, CODE_SIZE) == code_for(code_va, store_va), "injured reserve code is foreign")
    return "applied"


def status(payload: bytes) -> str:
    """retail (2004 IR), guard (2004 IR + the Pro Bowl guard), applied (modern IR) or foreign."""
    try:
        return _recognize(payload)
    except _ERRORS:
        return "foreign"


def _repin(buf: bytearray) -> None:
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)


def apply(payload: bytes, mode: str = "modern") -> tuple[bytes, dict]:
    """Install the guard (mode "guard") or modern IR (mode "modern", which includes the guard). Idempotent; the guard
    asked of a modern install is already there (already_applied)."""
    _require(mode in MODES, f"injured reserve mode must be one of {MODES}")
    state = status(payload)
    _require(state != "foreign", "the source executable's injured reserve sites are foreign or partially patched")
    common = dict(owner=OWNER, mode=mode, experimental=True, runtime_witnessed=False)
    if state == "applied" or (mode == "guard" and state == "guard"):
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    before = payload
    edits = []
    if mode == "guard":
        image = XbeImage(payload)
        buf = bytearray(payload)
        off = image.offset(GUARD_VA, len(GUARD))
        buf[off:off + len(GUARD)] = GUARD
        edits.append(dict(label="probowl_guard", va=hex(GUARD_VA), before=GUARD_RETAIL.hex(), after=GUARD.hex()))
        _repin(buf)
        result = bytes(buf)
        _require(status(result) == "guard", "injured reserve guard postcondition failed")
        return result, dict(common, status="applied", changed_bytes=space.count_differing_bytes(before, result),
                            edits=edits)
    receipt = {}
    if not any(r["owner"] == OWNER for r in space.layout(payload)["allocations"]):
        if space.status(payload) == "retail":
            payload, receipt = space.apply(payload, REQUESTS, scaleout=True)
        else:
            _require(space.is_scaleout(payload), "modern injured reserve needs the scale-out allocator")
            payload, receipt = space.extend_scaleout(payload, REQUESTS)
    rows = allocations(payload)
    code_va, store_va = rows["code"]["va"], rows["data"]["va"]
    payload, _ = space.install_code(payload, OWNER, code_for(code_va, store_va))
    image = XbeImage(payload)
    buf = bytearray(payload)
    off = image.offset(GUARD_VA, len(GUARD))
    buf[off:off + len(GUARD)] = GUARD
    for label, va, retail, patched in sites(code_va):
        off = image.offset(va, len(patched))
        now = bytes(buf[off:off + len(patched)])
        _require(now == retail or (va == GUARD_VA and now == GUARD[:len(patched)]), f"injured reserve site {va:#x} is not retail")
        buf[off:off + len(patched)] = patched
        edits.append(dict(label=label, va=hex(va), before=retail.hex(), after=patched.hex()))
    _repin(buf)
    result = bytes(buf)
    _require(status(result) == "applied" and space.status(result) == "applied", "injured reserve postcondition failed")
    return result, dict(common, status="applied", code_va=hex(code_va), store_va=hex(store_va), stamp=STAMP,
                        before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=space.count_differing_bytes(before, result), file_growth=len(result) - len(before),
                        allocation=receipt, edits=edits,
                        reservations=[r for r in space.reservations(result) if r["owner"] == OWNER])


def store_va(payload: bytes) -> int | None:
    rows = allocations(payload) if status(payload) == "applied" else {}
    return rows["data"]["va"] if rows else None


__all__ = ["OWNER", "EVIDENCE", "BUILD_CAPTION", "HELP_TEXT", "GUARD_CAPTION", "GUARD_HELP", "MODES", "CODE_SIZE", "STORE_SIZE", "REQUESTS", "CAP",
           "LEGACY_SLOTS", "EXTENDED_CAP", "MIN_GAMES", "RETURNS", "LONG_WEEKS", "GUARD_VA", "GUARD_RETAIL", "GUARD",
           "HOOKS", "code_for", "sites", "allocations", "status", "apply", "store_va", "InjuredReserveOwnerError"]

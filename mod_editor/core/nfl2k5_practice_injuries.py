"""Franchise practice: injured players sit out, USA retail (b778 pi1).

Report (Noah's 10/21 stream, Titans franchise MyNFL3, v0.6.1): Carnell Tate is out for three more weeks, yet he lines up
in Free Practice started from the Coach's Desk.

How retail treats injuries (static disassembly of the USA executable plus a headless run of the released disc, b778 pi1):

- A player's injury lives in his roster record: ``+0x20`` bit 31 (injured), bits 22..29 (weeks out) and ``+0x24``
  bits 28..30 (status 0..4; 4 = out). The franchise code writes them; a franchise save carries them.
- Every game copies both rosters into the match arrays 0xB30C4C / 0xB321A0 (0x617E0, through the staging routine at
  0x61730). For each copy, 0x61845 / 0x61875 call 0x61540: it keeps the copy's injury only when the game mode
  ``[0xE5FF80]`` is 5, 6 or 7 (league games) or the league type ``[0xE576A0]`` (0x0C4B80) is 3, and the copy is
  injured (bit 31); otherwise it heals the copy (0x0E6680 clears the status, the weeks and the injured bit).
- The lineup slot filler 0x189360 asks 0x188440 whether a player may take a slot: a status above the threshold
  ``[0xE6019C]`` / ``[0xE601AC]`` (1 by default) is refused and the next player on the depth chart takes the slot.
  0x61860 afterwards heals injured copies again only if a side would otherwise have fewer than twelve healthy players.
- Practice is mode 0..2. So retail Practice always heals the match copies: an injured player practices. Retail can show
  this too (Practice from the main menu after quitting a franchise still has the franchise roster in memory); the
  Coach's Desk Practice row (``nfl2k5_franchise_practice``) made it the normal path inside a franchise.

This owner replaces the ten bytes ``call 0x0C4B80; cmp eax, 3; jne 0x61569`` at 0x61550 with a call into a small cave
and the same ``jne``. The cave answers the retail question (league type 3: keep) and adds one case: practice
(mode 0..2) while a season or franchise is loaded (league type not 0) keeps the injury as well. A kept injury then
behaves exactly as in a league game: 0x188440 benches a player whose status is above the threshold and the depth chart's
next healthy player lines up. Nothing is written to the roster: only the disposable match copies differ. Main-menu
practice with no franchise loaded, Basic Training, exhibitions, Anniversary moments and league games are unchanged.
"""
from __future__ import annotations

import hashlib
import struct

OWNER = "nfl2k5_practice_injuries"
CODE_SIZE = 32
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
BUILD_CAPTION = "Franchise practice: injured players sit out"
HELP_TEXT = ("Practice started from a franchise or season leaves injured players out, as a league game does: the next "
             "healthy player on the depth chart takes the spot. Retail heals every player for practice, so a starter "
             "who is out for weeks still practices. Practice from the main menu with no franchise loaded is unchanged. "
             "Nothing is saved to the roster.")
LEAGUE, MODE = 0xE576A0, 0xE5FF80                 # league type (0 = none loaded), game mode (practice 0..2)
KEEP_MODE = 0x00061540                             # FUN_00061540: keep or heal one match copy (esi)
HOOK = ("practice_injury_keep", 0x00061550, bytes.fromhex("e82b360600" "83f803" "750f"))  # call 0xc4b80; cmp eax,3; jne
HEAL_VA = 0x00061569                               # mov ecx, esi; jmp 0xe6680 (heal the copy)
GUARDS = (
    (0x00061540, 0x31, "a62adcbebe12113359424d9270a187b890a7a53270314b3b56766f5a943ad460"),   # keep or heal
    (0x000E6680, 0x22, "2114d6644ff8277581b02e560f927f7f215a023aeec26ab7d76627c07c7a53b6"),   # heal
    (0x000C4B80, 6, "ea571d62a509b72a0a8afeb1ce87e10afb9b23fe864a4f34521e3a467052a60a"),      # league type
    (0x00188440, 0x35, "f82fa028bb43e2e36de3d4b50b50c802a2485f6772d3426129cfbd99a75a1bb5"),   # slot eligibility
)
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError, OSError)


class PracticeInjuriesError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise PracticeInjuriesError(message)


def code_for(code_va):
    """The cave (CODE_SIZE bytes). Returns ZF set to keep the copy's injury (0x6155A then keeps it only if bit 31 is
    set, as retail), ZF clear to heal. Only EAX and the flags change; 0x6155A reloads EAX."""
    from .nfl2k5_draft_ai import _Asm
    a = _Asm(code_va)
    a.b("a1" + struct.pack("<I", LEAGUE).hex())                  # mov eax, [league type]   (retail 0x0C4B80)
    a.b("83f803")                                                # cmp eax, 3
    a.j8("74", "done")                                           # retail: league type 3 keeps (ZF set)
    a.b("85c0")                                                  # test eax, eax
    a.j8("74", "heal")                                           # nothing loaded: retail heals
    a.b("833d" + struct.pack("<I", MODE).hex() + "02")           # cmp dword [mode], 2
    a.j8("77", "heal")                                           # not practice (unsigned): retail heals
    a.b("39c0")                                                  # cmp eax, eax: ZF set, keep
    a.b("c3")
    a.label("heal")
    a.b("85e4")                                                  # test esp, esp: ZF clear, heal
    a.label("done")
    a.b("c3")
    body = a.assemble()
    require(len(body) <= CODE_SIZE, "practice injury cave exceeds its allocation")
    return body.ljust(CODE_SIZE, b"\xcc")


def sites(code_va=0):
    name, va, before = HOOK
    after = b"\xe8" + struct.pack("<i", code_va - va - 5)        # call cave
    after += b"\x75" + bytes([HEAL_VA - (va + 7)])                # jne 0x61569 (heal), as retail
    return [(name, va, before, after.ljust(len(before), b"\x90"))]


def allocation(payload):
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    require(len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"]) == ("code", CODE_SIZE, 16),
            "Missing or foreign practice injury allocation")
    return rows[0]


def _recognize(payload):
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    present = any(r["owner"] == OWNER for r in space.layout(payload)["allocations"])
    owned = allocation(payload) if present else None
    edits = sites(owned["va"] if owned else 0)
    states = set()
    for _name, va, before, after in edits:
        raw = image.read(va, len(before))
        states.add("retail" if raw == before else "applied" if owned and raw == after else "foreign")
    if owned:
        raw = image.read(owned["va"], CODE_SIZE)
        states.add("retail" if raw == b"\xcc" * CODE_SIZE else "applied" if raw == code_for(owned["va"]) else "foreign")
    require(states in ({"retail"}, {"applied"}), "Foreign or mixed practice injury site/code")
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for _, at, before, _ in edits:
            if va <= at and at + len(before) <= va + size:
                content[at - va:at - va + len(before)] = before
        require(hashlib.sha256(content).hexdigest() == digest, f"Foreign practice injury prerequisite at {va:#x}")
    return next(iter(states))


def status(payload):
    try:
        return _recognize(payload)
    except _ERRORS:
        return "foreign"


def apply(payload):
    """Install, or replay an identical installation."""
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_bump_strength import _sections, section_digest
    from .nfl2k5_cave_oracle import XbeImage
    try:
        state = _recognize(payload)
    except _ERRORS as exc:
        raise PracticeInjuriesError(f"foreign/mixed practice injury input: {exc}") from exc
    common = dict(owner=OWNER, runtime_witnessed=True, practice_modes=[0, 1, 2], roster_written=False)
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    before = payload
    allocation_receipt = {}
    if not any(r["owner"] == OWNER for r in space.layout(payload)["allocations"]):
        if space.status(payload) == "retail":
            payload, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
        else:
            require(space.is_scaleout(payload), "Franchise practice injuries need the scale-out allocator")
            payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
    code_va = allocation(payload)["va"]
    payload, _ = space.install_code(payload, OWNER, code_for(code_va))
    edits = sites(code_va)
    image = XbeImage(payload)
    buf = bytearray(payload)
    for _, va, old, new in edits:
        off = image.offset(va, len(old))
        require(bytes(buf[off:off + len(old)]) == old, f"practice injury site {va:#x} is not retail")
        buf[off:off + len(old)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(_recognize(result) == "applied" and space.status(result) == "applied",
            "practice injury postcondition failed")
    return result, dict(common, status="applied", code_va=hex(code_va),
                        before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=space.count_differing_bytes(before, result), file_growth=len(result) - len(before),
                        allocation=allocation_receipt,
                        edits=[dict(label=name, va=hex(va), before=old.hex(), after=new.hex()) for name, va, old, new in edits],
                        reservations=[r for r in space.reservations(result) if r["owner"] == OWNER])


__all__ = ["OWNER", "REQUESTS", "CODE_SIZE", "HOOK", "GUARDS", "BUILD_CAPTION", "HELP_TEXT", "code_for", "sites",
           "allocation", "status", "apply"]

"""SportsCenter news with modern injured reserve, and the news windows across a save and load (b81 sportscenter).

How SportsCenter finds its stories (static reading of the USA executable): the weekly show never reads a player's
injury fields. It reads the franchise news ledger, a 600-row ring
at 0xE3F070 (writer 0x2BFDF0, next-write cursor 0xE3F06C) that the game saves with the franchise. Two window starts
split it: 0xE3F064 ("this window", set by the rollover 0x2BFDD0 at the start of each weekly advance) and 0xE3F068 (the
window before). The injury segment's begin 0x21E2E0 builds its pages from:
  * kind-12 rows of this window (placed on injured reserve): the Injured Reserve page (list 0xC13C90, top five);
  * kind-10 rows of the last two windows (injuries, posted by the end-of-game merge through 0x247160): skipped when
    0x247110 finds the player in the retail 5-slot IR table 0xE421E0, otherwise filed under the club the segment finds
    by walking every club's active list (0x21E444..0x21E483) in the AFC, NFC and NFL lists or as the Major Injury.
Wingo's lines are event 181 of the wrapup director (dir_wrapup.iff); every recorded line of the Injured Reserve page
says the player is done for the season (lines.bin 3215-3231), because retail injured reserve was season-ending.

What breaks with modern injured reserve (nfl2k5_injured_reserve: up to 20 a club, a 4-game minimum, returns), and the
fix (R2, installed only when modern injured reserve is on, the owner's mode bit 0):
  R2a The IR page took every placement of the week, so a 4-week stint was called "done for the year". At 0x21E37D the
      kind-12 loop's score call (0x21DAF0) goes through a cave that keeps the game's score only when the game's own
      duration class 0x21DA50 is 2 or more (out for the playoffs, the season, or career); otherwise it returns the
      score the game gives an excluded player (-FLT_MAX, [0x4FA0B8]). Only season-ending placements reach that page.
  R2b The kind-10 loop's IR skip asked the 5-slot mirror only, so most modern IR players came back on the injury lists
      and a short stint never showed with its weeks. At 0x21E3FC the skip asks instead whether the player is on this
      week's IR page (list 0xC13C90, built just before); every other injured man is listed with his weeks out.
  R2c The IR owner takes a player off his club, so the club walk found nobody and left the last club walked in the
      entry (the wrong club and conference). At 0x21E47C, when the walk runs out, the cave puts back the row's own
      club (dword 2 of the kind-10 row, which 0x247160 always fills).
And, always (R3): the franchise loader restores the ledger cursor only (0x2D0EE3, inside the front-office reader
0x2D0CE0), never the two window starts it saved (F+0x3324, F+0x3328, written by 0x2D0938). After a cold load both are
0, so the windows ran from slot 0; loading a second franchise kept the first one's. At 0x2D0EE3 the cave restores the
cursor as before and both window starts when each is a ring slot (below 600); anything else keeps retail's behaviour.

One fixed page after the helmet side numbers page (nfl2k5_xbe_space.SPORTSCENTER_NEWS_VA), placed like the quarterback
pages: at its absolute address, never advancing the pool cursor, so the owner can be added in place after every other
owner and an owner a disc lacks can still be added after it. No new save field: the ledger, its cursor and both window
starts are already in every franchise save. States: retail, applied (either mode), foreign; ``apply`` switches the mode
in place when modern injured reserve was added or removed since (the same bytes a fresh install of that mode writes).
"""
from __future__ import annotations

import hashlib
import struct
from typing import Mapping

OWNER = "nfl2k5_sportscenter_news"
BUILD_KEY = "sportscenter_news"
BUILD_CAPTION = "SportsCenter news"
HELP_TEXT = ("SportsCenter's injury report knows modern injured reserve: only season-ending moves go on its Injured "
             "Reserve page, every other injured man is listed with his weeks out under his own club, and the week's "
             "news survives saving and loading the franchise.")
CODE_SIZE = 0x1000                                   # one fixed page (nfl2k5_xbe_space.SPORTSCENTER_NEWS_VA)
REQUESTS = ((OWNER, "code", CODE_SIZE, CODE_SIZE),)  # = nfl2k5_xbe_space.SPORTSCENTER_NEWS_REQUEST
MARKER = b"SCNEWS1\0"
MODE_IR = 1                                          # bit 0: R2 (modern injured reserve) installed

# The page: marker + mode at 0, then the caves.
OFF_MODE = 8
OFF_RELOAD = 0x20
OFF_IR_PAGE = 0x80
OFF_IR_SKIP = 0xC0
OFF_CLUB = 0x100

# --- the game's own code and data the caves use ---------------------------------------------------------------------
LEDGER_CURSOR, THIS_WINDOW, LAST_WINDOW = 0xE3F06C, 0xE3F064, 0xE3F068
SAVED_THIS_WINDOW, SAVED_LAST_WINDOW, SAVED_CURSOR = 0x3324, 0x3328, 0x332C   # front-office block offsets
RING = 600
FN_SCORE = 0x0021DAF0          # stdcall(club) with esi = player: st0 = list score, or -FLT_MAX when excluded
FN_DURATION_CLASS = 0x0021DA50  # stdcall(player): 0 weeks, 1 rest of regular season, 2 playoffs, 3 season, 4 career
EXCLUDED_SCORE = 0x004FA0B8    # -FLT_MAX, what 0x21DAF0 itself returns for an excluded player (0x21DC1F)
SEASON_ENDING_CLASS = 2
IR_PAGE_LIST, LIST_ENTRY, LIST_ENTRIES = 0x00C13C90, 12, 5
FN_TEAM_COUNT = 0x000C6430

# --- the sites (va, retail bytes) ------------------------------------------------------------------------------------
RELOAD_VA = 0x002D0EE3          # mov eax, [ebp+0x332C]; mov [0xE3F06C], eax
RELOAD_RETAIL = bytes.fromhex("8b852c330000a36cf0e300")
RELOAD_RESUME = RELOAD_VA + len(RELOAD_RETAIL)
IR_PAGE_VA = 0x0021E37D         # call 0x21DAF0 (the kind-12 loop's score)
IR_PAGE_RETAIL = bytes.fromhex("e86ef7ffff")
IR_SKIP_VA = 0x0021E3FC         # call 0x247110 (the kind-10 loop's IR skip; ecx = player)
IR_SKIP_RETAIL = bytes.fromhex("e80f8d0200")
CLUB_VA = 0x0021E47C            # call 0xC6430; cmp esi, eax  (the end of the club walk; then jl 0x21E450)
CLUB_RETAIL = bytes.fromhex("e8af7feaff3bf0")
CLUB_JL = (0x0021E483, bytes.fromhex("7ccb"))  # jl 0x21E450, kept

#: (va, size, sha256) of the retail code the caves rely on (outside the four sites); a different executable is refused
GUARDS = (
    (0x2D0EC0, 0x7F, "2d9c80cacee10c109b93cd98e1da45c15b09abf2ccf90603fb432ddda2d08e43"),   # loader: rows, cursor, rows
    (0x2D0938, 0x23, "07df9e9b9f02ac6d2ab12ea8a4480512d37544df122b14a97d0a2a17953bce3d"),   # saver: windows + cursor
    (0x2BFDD0, 0x17, "62734e6ca077c3ce595eaff1bb094e8e98710ec99ef2cdf77c25f9c985cf937f"),   # window rollover
    (0x2BFDF0, 0x73, "478f3d0a472078f333ab503f12d7733659d8a678385a41759072d9744c04dd0a"),   # ledger writer
    (0x21E2E0, 0x36C, "dd02dc5ba38cf9bc14095fff8022219497c40fce1400340fb948ed44830951e8"),  # injury segment begin
    (0x21DAF0, 0x13C, "ac7489d4b4d04873bb32cac10ed2b554689413938afb21531acbd6585cc7bba3"),  # list score
    (0x21DA50, 0x57, "163ec5a50d477238a25a33169b2b50091dff813d3d4bfe70f129d899ea6ab6ba"),   # duration class, to its
    # calendar compares (0x21DAA7.., which the 18-week season owner changes)
    (0x15EE40, 0xBD, "0fb9a09ac2ec0ed0d0042735d87c26908c90602fe81fc3e7b6f419fe2e5351d6"),   # list init / insert
)
_FAILURES = (ValueError, IndexError, KeyError, TypeError, struct.error, OverflowError, UnicodeError)


class SportsCenterNewsError(ValueError):
    pass


def _require(ok, message):
    if not ok:
        raise SportsCenterNewsError(message)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _p32(value):
    return struct.pack("<I", value & 0xFFFFFFFF).hex()


# ------------------------------------------------------------------------------------------------ the caves

def _reload(a):
    """R3. Entry from 0x2D0EE3 by jmp; ebp = the saved front-office block. eax, ecx and edx are dead here (the rows loop
    after the site writes each before it reads it); every other register is kept."""
    a.b("8b85" + _p32(SAVED_CURSOR))                 # mov eax, [ebp+0x332C]      (the displaced retail pair)
    a.b("a3" + _p32(LEDGER_CURSOR))                  # mov [0xE3F06C], eax
    a.b("8b8d" + _p32(SAVED_THIS_WINDOW))            # mov ecx, [ebp+0x3324]      this window's start, as saved
    a.b("8b95" + _p32(SAVED_LAST_WINDOW))            # mov edx, [ebp+0x3328]      the window before
    a.b("81f9" + _p32(RING))                         # cmp ecx, 600
    a.j8("73", "keep")                               # jae keep                   not a ring slot: retail behaviour
    a.b("81fa" + _p32(RING))                         # cmp edx, 600
    a.j8("73", "keep")
    a.b("890d" + _p32(THIS_WINDOW))                  # mov [0xE3F064], ecx
    a.b("8915" + _p32(LAST_WINDOW))                  # mov [0xE3F068], edx
    a.label("keep")
    a.jmp_abs(RELOAD_RESUME)


def _ir_page(a):
    """R2a. Called from 0x21E37D in place of 0x21DAF0 (stdcall, one argument, esi = the player, edi set by the caller)."""
    a.b("ff742404")                                  # push dword [esp+4]         the caller's argument
    a.call(FN_SCORE)                                 # st0 = the game's score
    a.b("56")                                        # push esi
    a.call(FN_DURATION_CLASS)                        # eax = the duration class (keeps ebx, esi, edi)
    a.b("83f8" + bytes([SEASON_ENDING_CLASS]).hex())  # cmp eax, 2
    a.j8("73", "keep")                               # jae keep                   season-ending: the IR page
    a.b("ddd8")                                      # fstp st(0)
    a.b("d905" + _p32(EXCLUDED_SCORE))               # fld dword [0x4FA0B8]       excluded, like 0x21DAF0's own
    a.label("keep")
    a.b("c20400")                                    # ret 4


def _ir_skip(a):
    """R2b. Called from 0x21E3FC in place of 0x247110 (ecx = the player): nonzero = skip him."""
    a.b("b8" + _p32(IR_PAGE_LIST))                   # mov eax, 0xC13C90          the IR page's list
    a.label("loop")
    a.b("3908")                                      # cmp [eax], ecx
    a.j8("74", "skip")
    a.b("83c0" + bytes([LIST_ENTRY]).hex())          # add eax, 12
    a.b("3d" + _p32(IR_PAGE_LIST + LIST_ENTRY * LIST_ENTRIES))  # cmp eax, 0xC13CCC
    a.j8("72", "loop")
    a.b("33c0")                                      # xor eax, eax               listed with his weeks out
    a.b("c3")                                        # ret
    a.label("skip")
    a.b("b801000000")                                # mov eax, 1                 on this week's IR page
    a.b("c3")                                        # ret


def _club(a):
    """R2c. Called from 0x21E47C in place of "call 0xC6430; cmp esi, eax": the same compare for the jl after it, and when
    the walk has run out ([esi] = club count) the row's own club ([row + 8]) instead of the last club walked. In the
    caller's frame [esp+0x10] is the entry's club and [esp+0x18] the row: here they are +4."""
    a.call(FN_TEAM_COUNT)                            # eax = club count
    a.b("3bf0")                                      # cmp esi, eax
    a.j8("7c", "done")                               # jl done                    still walking
    a.b("8b44241c")                                  # mov eax, [esp+0x1C]        the kind-10 row
    a.b("8b4008")                                    # mov eax, [eax+8]           its club
    a.b("85c0")                                      # test eax, eax
    a.j8("74", "flags")                              # no club on the row: retail (the last club walked)
    a.b("89442414")                                  # mov [esp+0x14], eax
    a.label("flags")
    a.b("3bf6")                                      # cmp esi, esi               "not less": the caller's jl falls out
    a.label("done")
    a.b("c3")                                        # ret


def code_for(code_va: int, mode: int) -> bytes:
    """The owned page (CODE_SIZE bytes, int3-padded) for this mode (bit 0: modern injured reserve)."""
    from .nfl2k5_draft_ai import _Asm
    _require(type(code_va) is int and code_va % CODE_SIZE == 0, "the SportsCenter news page must be page-aligned")
    _require(mode in (0, MODE_IR), "unknown SportsCenter news mode")
    page = bytearray(b"\xcc" * CODE_SIZE)
    page[0:8] = MARKER
    page[OFF_MODE:OFF_MODE + 4] = struct.pack("<I", mode)
    pieces = [(OFF_RELOAD, _reload, OFF_IR_PAGE)]
    if mode & MODE_IR:
        pieces += [(OFF_IR_PAGE, _ir_page, OFF_IR_SKIP), (OFF_IR_SKIP, _ir_skip, OFF_CLUB), (OFF_CLUB, _club, 0x140)]
    for offset, build, limit in pieces:
        a = _Asm(code_va + offset)
        build(a)
        blob = a.assemble()
        _require(offset + len(blob) <= limit, f"SportsCenter news cave at +{offset:#x} outgrew its slot")
        page[offset:offset + len(blob)] = blob
    return bytes(page)


def sites(code_va: int, mode: int) -> list[tuple[str, int, bytes, bytes]]:
    """(label, va, retail, applied) for every site this mode writes."""
    out = [("news_windows_on_load", RELOAD_VA, RELOAD_RETAIL,
            b"\xe9" + struct.pack("<i", code_va + OFF_RELOAD - RELOAD_VA - 5) + b"\x90" * 6)]
    if mode & MODE_IR:
        call = lambda va, offset: b"\xe8" + struct.pack("<i", code_va + offset - va - 5)
        out += [("ir_page_season_ending", IR_PAGE_VA, IR_PAGE_RETAIL, call(IR_PAGE_VA, OFF_IR_PAGE)),
                ("injury_list_ir_skip", IR_SKIP_VA, IR_SKIP_RETAIL, call(IR_SKIP_VA, OFF_IR_SKIP)),
                ("injury_list_row_club", CLUB_VA, CLUB_RETAIL, call(CLUB_VA, OFF_CLUB) + b"\x90\x90")]
    return out


ALL_SITES = ((RELOAD_VA, RELOAD_RETAIL), (IR_PAGE_VA, IR_PAGE_RETAIL), (IR_SKIP_VA, IR_SKIP_RETAIL),
             (CLUB_VA, CLUB_RETAIL))


# ------------------------------------------------------------------------------------------------ owner state

def _space():
    from . import nfl2k5_xbe_space as space
    return space


def modern_injured_reserve(payload: bytes) -> bool:
    """True when the executable carries modern injured reserve (the IR owner applied, or an earlier revision of it)."""
    from . import nfl2k5_injured_reserve as injured_reserve
    try:
        return injured_reserve.status(payload) in ("applied", "previous")
    except _FAILURES:
        return False


def allocation(payload: bytes) -> dict | None:
    space = _space()
    if space.status(payload) != "applied":
        return None
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    if not rows:
        return None
    _require(len(rows) == 1 and rows[0]["kind"] == "code" and rows[0]["size"] == CODE_SIZE
             and rows[0]["va"] == space.SPORTSCENTER_NEWS_VA, "foreign SportsCenter news allocation")
    return rows[0]


def _guards(payload: bytes) -> None:
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    for va, size, digest in GUARDS:
        blob = bytearray(image.read(va, size))
        for site, retail in ALL_SITES:
            if va <= site and site + len(retail) <= va + size and bytes(blob[site - va:site - va + len(retail)]) != retail:
                blob[site - va:site - va + len(retail)] = retail      # judge the retail code around our own sites
        _require(_sha(bytes(blob)) == digest, f"foreign SportsCenter news prerequisite at {va:#x}")


def _site_states(payload: bytes, code_va: int | None) -> dict[int, str]:
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    applied = {va: after for _l, va, _b, after in sites(code_va, MODE_IR)} if code_va is not None else {}
    out = {}
    for va, retail in ALL_SITES:
        raw = image.read(va, len(retail))
        out[va] = "retail" if raw == retail else "applied" if raw == applied.get(va) else "foreign"
    return out


def _state(payload: bytes) -> tuple[str, int | None, dict | None]:
    """(state, mode, allocation)."""
    from .nfl2k5_cave_oracle import XbeImage
    space = _space()
    _require(space.status(payload) != "foreign", "foreign XBE geometry, owner seal or section digest")
    _guards(payload)
    found = allocation(payload)
    states = _site_states(payload, found["va"] if found else None)
    if found is None or XbeImage(payload).read(found["va"], CODE_SIZE) == b"\xcc" * CODE_SIZE:
        _require(set(states.values()) == {"retail"}, "SportsCenter news sites changed without the owner's code")
        return "retail", None, found
    page = XbeImage(payload).read(found["va"], CODE_SIZE)
    _require(page[:8] == MARKER, "foreign SportsCenter news page")
    mode = struct.unpack_from("<I", page, OFF_MODE)[0]
    _require(mode in (0, MODE_IR) and page == code_for(found["va"], mode), "foreign SportsCenter news code")
    want = {va for _l, va, _b, _a in sites(found["va"], mode)}
    for va, state in states.items():
        _require(state == ("applied" if va in want else "retail"), "mixed SportsCenter news sites")
    return "applied", mode, found


def status(payload: bytes) -> str:
    """retail / applied / foreign for default.xbe."""
    try:
        return _state(payload)[0]
    except _FAILURES:
        return "foreign"


def read_settings(payload: bytes) -> dict:
    try:
        state, mode, found = _state(payload)
    except _FAILURES:
        return {"status": "foreign"}
    out = {"status": state}
    if state == "applied":
        out.update(mode=mode, modern_injured_reserve=bool(mode & MODE_IR), code_va=hex(found["va"]))
    return out


def wanted_mode(payload: bytes) -> int:
    return MODE_IR if modern_injured_reserve(payload) else 0


def reservations(payload: bytes) -> list[dict]:
    rows = [r for r in _space().reservations(payload) if r["owner"] == OWNER]
    return rows + [dict(owner=OWNER, start=hex(va), end=hex(va + len(retail)), size=len(retail),
                        basis="pinned live SportsCenter news site; not a cave") for va, retail in ALL_SITES]


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Install the owner (a fixed page, any install order) in the mode the executable calls for: R3 always, R2 when
    modern injured reserve is on. An install of the other mode is switched in place. Idempotent."""
    from . import nfl2k5_rdata_sites as rdata
    from .nfl2k5_cave_oracle import XbeImage
    space = _space()
    state, mode, found = _state(payload)
    want = wanted_mode(payload)
    common = {"owner": OWNER, "mode": want, "modern_injured_reserve": bool(want & MODE_IR),
              "experimental": True, "runtime_witnessed": False}
    if state == "applied" and mode == want:
        return payload, {**common, "status": "applied", "already_applied": True, "changed_bytes": 0, "edits": []}
    before = payload
    if state == "applied":
        # switch the mode in place: back to the retail sites and fill, then the wanted mode on the same page
        code_va = found["va"]
        back = [(label, va, after, retail) for label, va, retail, after in sites(code_va, mode)]
        payload, _ = rdata.apply(payload, back, OWNER + " mode switch")
        payload, _ = space.install_code(payload, OWNER, b"\xcc" * CODE_SIZE,
                                        previous=XbeImage(payload).read(code_va, CODE_SIZE))
    if found is None:
        if space.status(payload) == "retail":
            payload, _ = space.apply(payload, REQUESTS, scaleout=True)
        else:
            payload, _ = space.extend_scaleout(payload, REQUESTS)
        found = allocation(payload)
    _require(found is not None, "reserve the SportsCenter news allocation first")
    code_va = found["va"]
    with_code, code_receipt = space.install_code(payload, OWNER, code_for(code_va, want))
    result, site_receipt = rdata.apply(with_code, sites(code_va, want), OWNER)
    _require(status(result) == "applied" and _state(result)[1] == want, "SportsCenter news postcondition failed")
    return result, {**common, **site_receipt, "status": "applied", "already_applied": False,
                    "switched_from_mode": mode if state == "applied" else None,
                    "code_install": code_receipt, "code_va": hex(code_va),
                    "changed_bytes": space.count_differing_bytes(before, result) + abs(len(result) - len(before)),
                    "before_sha256": _sha(before), "after_sha256": _sha(result)}


def remove(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """The sites back to retail and the page back to its int3 fill (the reservation stays; nothing moves)."""
    from . import nfl2k5_rdata_sites as rdata
    from .nfl2k5_cave_oracle import XbeImage
    space = _space()
    state, mode, found = _state(payload)
    if state == "retail":
        return payload, {"owner": OWNER, "status": "retail", "already_retail": True, "changed_bytes": 0}
    before = payload
    code_va = found["va"]
    back = [(label, va, after, retail) for label, va, retail, after in sites(code_va, mode)]
    payload, _ = rdata.apply(payload, back, OWNER + " removal")
    payload, _ = space.install_code(payload, OWNER, b"\xcc" * CODE_SIZE,
                                    previous=XbeImage(payload).read(code_va, CODE_SIZE))
    _require(status(payload) == "retail", "SportsCenter news did not come off cleanly")
    return payload, {"owner": OWNER, "status": "retail", "already_retail": False,
                     "changed_bytes": space.count_differing_bytes(before, payload)}


__all__ = ["OWNER", "BUILD_KEY", "BUILD_CAPTION", "HELP_TEXT", "CODE_SIZE", "REQUESTS", "MARKER", "MODE_IR", "GUARDS",
           "SportsCenterNewsError", "code_for", "sites", "allocation", "status", "read_settings", "wanted_mode",
           "modern_injured_reserve", "reservations", "apply", "remove"]

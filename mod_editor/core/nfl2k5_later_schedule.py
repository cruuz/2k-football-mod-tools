"""Later franchise seasons keep the 2026 schedule's weekdays, kickoffs and Thanksgiving hosts (b780-season1, Q70).

EXPERIMENTAL / UNWITNESSED in game. Installed with the 128-season calendar (``nfl2k5_calendar_engine``), whose date
helpers it calls.

What the game does without it (static RE of the USA ``default.xbe``; the calendar engine's own hooks included)
---------------------------------------------------------------------------------------------------------------
The regular-season generator ``FUN_002bf270`` copies the schedule template into the 22 x 17 grid (``0xE57C40``) in
template order, its teams remapped by last season's finish through the division tables at ``0xACEE38`` and the
four-season division rotation at ``0xACEFB8``. Season 0 keeps the template as it is. From the second season on its tail
(``0x2BF474..0x2BF74B``) then

* swaps a whole week into the Thanksgiving week wherever Dallas and Detroit both play and moves their two games, home or
  away, into the week's first two slots;
* moves each week's best-ranked game (``FUN_002bf1b0``) into the week's last slot by swapping whole records;
* re-dates every slot by position: Sunday, the last slot Monday, the first two Thanksgiving slots Thursday, four
  late-season slots Saturday, keeping each record's own kickoff time.

So a 2027 franchise loses every Thursday night game (17 in the 2026 template, 0 after), plays Monday afternoon games,
gets two or three Sunday night games a week, and Dallas and Detroit often visit on Thanksgiving (HUNT1's
two-season run on the v0.9 RC).

What this owner does
--------------------
One 5-byte hook at ``0x2BF46F`` (the tail's ``call 0xC4EB0``) jumps to new code; the old tail and the four helpers only
it calls become dead, and four of those helpers hold the new code, each rewritten as a whole function from its entry
(the tail's own calls still land only on entries). Two of them (``FUN_002beb20`` / ``FUN_002beb40``) were also the
retail preseason generator's date writers; the calendar requires the template preseason, which replaced that generator,
so on every image this owner accepts the tail is their only caller:

* season 0 returns exactly as before;
* later seasons keep every grid position's template weekday and kickoff: each regular-season record's date moves by the
  whole number of weeks between this season's opening Thursday and the template's (the calendar engine's
  ``opening_day`` and ``add_days``), so Thursday, Saturday, Sunday night, Monday night, Christmas-week and
  Thanksgiving games stay where the template has them;
* Detroit and Dallas host the two Thanksgiving day games (the template's first two Thanksgiving-week slots, Detroit
  first): when one of them is away that week, it trades its whole season schedule with the division rival that hosts
  that week (every game of the two clubs swaps, so each still plays 17 games with one bye and the same home and road
  split), then its home game trades places with the Thanksgiving slot (teams only: the slot keeps its date and kickoff).

Nothing else changes: the remap, the division rotation and the postseason are the game's own.
"""

from __future__ import annotations

import hashlib
import struct

from . import nfl2k5_calendar_engine as calendar
from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_season_length as season
from .nfl2k5_bump_strength import _section_for_offset, _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage
from .nfl2k5_playoffs14 import _Asm

OWNER = "nfl2k5_later_schedule"
EVIDENCE = "EXPERIMENTAL"
BUILD_CAPTION = "Later franchise seasons keep the schedule's weekdays, kickoffs and Thanksgiving hosts"

GRID_VA, ROW_BYTES, SLOTS = 0x00E57C40, 0x88, 17
THANKSGIVING_ROW = 11                       # the opening Thursday is Thanksgiving minus 77 days in every season
THANKSGIVING_VA = GRID_VA + THANKSGIVING_ROW * ROW_BYTES
WEEKS_VA = 0x005151C4                       # regular-season rows (17 retail, 18 with the 2026 season)
DIVISIONS_VA = 0x00E576D4                   # u32 per league club index: its division
EMPTY = 7                                   # the grid's empty-cell type
SEASON_FN = 0x000C4EB0                      # -> eax = franchise season index
DONE_VA = 0x002BF74B                        # FUN_002bf270's epilogue (pop edi, esi, ebp, ebx; leave)
HOOK_VA = 0x002BF46F
HOOK_RETAIL = bytes.fromhex("e83c5ae0ff")   # call 0xC4EB0 (the later-season test)
# The Thanksgiving hosts, by league index (the template's team ordinals, alphabetical by nickname: 11 Cowboys, 18 Lions)
DETROIT, DALLAS = 18, 11
HOSTS = ((DETROIT, 0), (DALLAS, 1))         # (club, Thanksgiving-week slot): Detroit's early game, then Dallas

# whole dead functions rewritten from their entries (their only callers sit in the dead tail): (label, VA, size, retail)
REGIONS = (
    ("main", 0x002BF1B0, 192, "430b49e6728d2e3b2aeb5f231b6cefaa6020063657523a125030dae1b37cd0e8"),   # FUN_002bf1b0
    ("swap", 0x002BEAD0, 72, "3895f0df5eb796da2d200c22c1a9b9dc48e048d1546bf5d3a1677708a1e002c6"),    # FUN_002bead0
    ("move", 0x002BEB20, 24, "dfef3096d7c70339c2286babe31e7ad910cd148d74e5203ab9a8ddba8ddf7f57"),    # FUN_002beb20
    ("find", 0x002BEB40, 32, "2c11901e7fbfec6566e2c7573f7f5f3fc83c0c8d6ac3683e167423a10d31a451"),    # FUN_002beb40
)
# retail context the new code relies on, pinned by SHA-256 (the template copy, the later-season test, the epilogue)
GUARDS = (
    ("template copy", 0x002BF270, 0x1FF, "6bdb91065095b7d879e565e293d4c7b98c49345b34cbb1517b08125b50789ece"),
    ("later-season test", 0x002BF46F, 13, "2107cc82897065292b7a04bb9486fd1aa58ac1c068be8bed52d697e3aafdeccf"),
    ("epilogue", 0x002BF74B, 8, "97ec1ece7224f091ac138c6cc1aeebd03e17a90ed835e305f1dd8244cadcb632"),
)


class LaterScheduleError(ValueError):
    pass


def _require(ok, message):
    if not ok:
        raise LaterScheduleError(message)


def _u32(value: int) -> str:
    return struct.pack("<I", value & 0xFFFFFFFF).hex()


def _region(label):
    return next(r for r in REGIONS if r[0] == label)


def base_opening_days(base_year: int) -> int:
    """The template season's opening Thursday as days since 2000-01-01 (what the calendar's ``opening_day`` returns)."""
    return (calendar.opening_date(base_year) - calendar.EPOCH).days


def _find_code() -> bytes:
    """bl = club -> esi = its cell in the Thanksgiving week (0 when it has no game there)."""
    a = _Asm(_region("find")[1])
    a.b("be" + _u32(THANKSGIVING_VA))           # mov esi, Thanksgiving row
    a.b("6a11")                                 # push 17
    a.b("59")                                   # pop ecx
    a.label("cell")
    a.b("803e%02x" % EMPTY)                     # cmp byte [esi],7
    a.j8("74", "next")
    a.b("385e01")                               # cmp [esi+1],bl (home)
    a.j8("74", "found")
    a.b("385e02")                               # cmp [esi+2],bl (away)
    a.j8("74", "found")
    a.label("next")
    a.b("83c608")                               # add esi,8
    a.j8("e2", "cell")                          # loop cell
    a.b("33f6")                                 # xor esi,esi
    a.label("found")
    a.b("c3")
    return a.assemble()


def _move_code() -> bytes:
    """esi = a Thanksgiving-week cell, edi = target slot: the two cells trade teams (each keeps its date and kickoff)."""
    a = _Asm(_region("move")[1])
    a.b("8d04fd" + _u32(THANKSGIVING_VA))       # lea eax,[edi*8 + row]
    a.b("668b4e01")                             # mov cx,[esi+1]
    a.b("668b5001")                             # mov dx,[eax+1]
    a.b("66895601")                             # mov [esi+1],dx
    a.b("66894801")                             # mov [eax+1],cx
    a.b("c3")
    return a.assemble()


def _swap_code() -> bytes:
    """al = rival, bl = club: the two clubs trade every regular-season game (home and away bytes of every cell)."""
    a = _Asm(_region("swap")[1])
    a.b("5657")                                 # push esi; push edi
    a.b("be" + _u32(GRID_VA))                   # mov esi, grid
    a.b("0fb63d" + _u32(WEEKS_VA))              # movzx edi, byte [weeks]
    a.b("69ff" + _u32(ROW_BYTES))               # imul edi,edi,0x88
    a.b("81c7" + _u32(GRID_VA))                 # add edi, grid  (end of the regular-season rows)
    a.label("cell")
    a.b("668b5601")                             # mov dx,[esi+1]
    a.b("3ad3")                                 # cmp dl,bl
    a.j8("75", "home_other")
    a.b("8ad0")                                 # mov dl,al
    a.j8("eb", "home_done")
    a.label("home_other")
    a.b("3ad0")                                 # cmp dl,al
    a.j8("75", "home_done")
    a.b("8ad3")                                 # mov dl,bl
    a.label("home_done")
    a.b("3af3")                                 # cmp dh,bl
    a.j8("75", "away_other")
    a.b("8af0")                                 # mov dh,al
    a.j8("eb", "away_done")
    a.label("away_other")
    a.b("3af0")                                 # cmp dh,al
    a.j8("75", "away_done")
    a.b("8af3")                                 # mov dh,bl
    a.label("away_done")
    a.b("66895601")                             # mov [esi+1],dx
    a.b("83c608")                               # add esi,8
    a.b("3bf7")                                 # cmp esi,edi
    a.j8("72", "cell")                          # jb cell
    a.b("5f5e")                                 # pop edi; pop esi
    a.b("c3")
    return a.assemble()


def _main_code(opening_day: int, add_days: int, base_days: int) -> bytes:
    """The new tail: season 0 unchanged; later seasons place the Thanksgiving hosts, then move every date by whole weeks."""
    find, move, swap = (_region(n)[1] for n in ("find", "move", "swap"))
    a = _Asm(_region("main")[1])
    a.call(SEASON_FN)                           # the displaced call
    a.b("85c0")                                 # test eax,eax
    a.j8("75", "later")
    a.jmp_abs(DONE_VA)                          # season 0: the template's own dates, as retail
    a.label("later")
    a.b("bb" + _u32(HOSTS[0][0]))               # mov ebx, Detroit
    a.b("33ff")                                 # xor edi,edi (its slot)
    a.label("host")
    a.call(find)                                # esi = the club's Thanksgiving-week cell
    a.b("85f6")                                 # test esi,esi
    a.j8("74", "next")
    a.b("385e01")                               # cmp [esi+1],bl
    a.j8("74", "place")                         # already at home
    a.call_label("rival")                       # eax = the division rival hosting that week, or 0
    a.b("85c0")
    a.j8("74", "next")
    a.call(swap)                                # the two clubs trade schedules
    a.call(find)                                # the club's cell again (now at home)
    a.b("85f6")
    a.j8("74", "next")
    a.label("place")
    a.call(move)                                # its home game takes the Thanksgiving slot
    a.label("next")
    a.b("47")                                   # inc edi
    a.b("b3%02x" % HOSTS[1][0])                 # mov bl, Dallas
    a.b("83ff%02x" % len(HOSTS))                # cmp edi,2
    a.j8("72", "host")
    a.call(opening_day)                         # eax = this season's opening Thursday (days)
    a.b("2d" + _u32(base_days))                 # sub eax, the template's opening Thursday (a multiple of 7)
    a.b("8be8")                                 # mov ebp,eax
    a.b("be" + _u32(GRID_VA))                   # mov esi, grid
    a.b("0fb605" + _u32(WEEKS_VA))              # movzx eax, byte [weeks]
    a.b("69c0" + _u32(ROW_BYTES))               # imul eax,eax,0x88
    a.b("8db8" + _u32(GRID_VA))                 # lea edi,[eax + grid]
    a.label("date")
    a.b("803e%02x" % EMPTY)                     # cmp byte [esi],7
    a.j8("74", "date_next")
    a.b("8d4e03")                               # lea ecx,[esi+3] (month, day, year - 2000)
    a.b("8bd5")                                 # mov edx,ebp
    a.call(add_days)
    a.label("date_next")
    a.b("83c608")                               # add esi,8
    a.b("3bf7")                                 # cmp esi,edi
    a.j8("72", "date")
    a.jmp_abs(DONE_VA)
    a.label("rival")                            # bl = club -> eax = a division rival at home that week, or 0
    a.b("8b2c9d" + _u32(DIVISIONS_VA))          # mov ebp,[ebx*4 + divisions]
    a.b("be" + _u32(THANKSGIVING_VA))           # mov esi, Thanksgiving row
    a.b("6a11")                                 # push 17
    a.b("59")                                   # pop ecx
    a.label("rival_cell")
    a.b("803e%02x" % EMPTY)
    a.j8("74", "rival_next")
    a.b("0fb64601")                             # movzx eax, byte [esi+1] (the host)
    a.b("3bc3")                                 # cmp eax,ebx
    a.j8("74", "rival_next")
    a.b("3b2c85" + _u32(DIVISIONS_VA))          # cmp ebp,[eax*4 + divisions]
    a.j8("74", "rival_found")
    a.label("rival_next")
    a.b("83c608")
    a.j8("e2", "rival_cell")
    a.b("33c0")                                 # xor eax,eax
    a.label("rival_found")
    a.b("c3")
    return a.assemble()


def code_regions(opening_day: int, add_days: int, base_days: int) -> dict[str, bytes]:
    """label -> the complete bytes written into each region (code, then int3 to the region's end)."""
    blobs = {"main": _main_code(opening_day, add_days, base_days), "swap": _swap_code(), "move": _move_code(),
             "find": _find_code()}
    out = {}
    for label, _va, size, _digest in REGIONS:
        code = blobs[label]
        _require(len(code) <= size, f"the {label} code is {len(code)} bytes, over its {size}-byte function")
        out[label] = code + b"\xcc" * (size - len(code))
    return out


def _calendar_labels(payload: bytes) -> tuple[int, int, int]:
    """(opening_day, add_days, template opening days) of an installed 128-season calendar."""
    _require(calendar.status(payload) == "applied", "the 128-season calendar is not installed")
    base = season.read_year(payload)
    _require(base in calendar.SUPPORTED_BASE_YEARS, "unsupported calendar starting year")
    found = calendar._allocations(payload)
    _, labels = calendar.code_for(found["code"]["va"], found["read_only"]["va"], base)
    return labels["opening_day"], labels["add_days"], base_opening_days(base)


def _hook_bytes() -> bytes:
    return b"\xe9" + struct.pack("<i", _region("main")[1] - (HOOK_VA + 5))


def _guards_ok(image: XbeImage) -> bool:
    for _name, va, size, digest in GUARDS:
        blob = bytearray(image.read(va, size))
        if va <= HOOK_VA < va + size:
            blob[HOOK_VA - va:HOOK_VA - va + 5] = HOOK_RETAIL
        if hashlib.sha256(bytes(blob)).hexdigest() != digest:
            return False
    return True


def status(payload: bytes) -> str:
    """'retail' (every region and the hook as the game shipped), 'applied' (this owner's exact bytes), else 'foreign'."""
    try:
        image = XbeImage(payload)
        if not _guards_ok(image):
            return "foreign"
        hook = image.read(HOOK_VA, 5)
        regions = {label: image.read(va, size) for label, va, size, _ in REGIONS}
        if hook == HOOK_RETAIL and all(hashlib.sha256(regions[label]).hexdigest() == digest
                                       for label, _va, _size, digest in REGIONS):
            return "retail"
        if hook != _hook_bytes():
            return "foreign"
        expected = code_regions(*_calendar_labels(payload))
        return "applied" if all(regions[label] == expected[label] for label in regions) else "foreign"
    except (LaterScheduleError, ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError):
        return "foreign"


def apply(payload: bytes) -> tuple[bytes, dict]:
    """Install on an image that has the 128-season calendar; refuse anything not retail or applied."""
    state = status(payload)
    _require(state in ("retail", "applied"), f"the later-season schedule sites are {state}; refusing")
    opening_day, add_days, base_days = _calendar_labels(payload)
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False, thanksgiving_hosts=["DET", "DAL"],
                  template_opening_days=base_days, file_growth=0)
    if state == "applied":
        return payload, dict(common, already_applied=True, changed_bytes=0, edits=[])
    blobs = code_regions(opening_day, add_days, base_days)
    sections = _sections(payload)
    buf = bytearray(payload)
    touched, edits = set(), []
    writes = [("later_season_hook", HOOK_VA, _hook_bytes())] + [(label, va, blobs[label]) for label, va, _s, _d in REGIONS]
    for label, va, data in writes:
        off = rdata.offset_of(payload, va)
        buf[off:off + len(data)] = data
        touched.add(_section_for_offset(sections, off).index)
        edits.append(dict(label=label, va=hex(va), size=len(data)))
    for section in sections:
        if section.index in touched:
            at = section.header_offset + 36
            buf[at:at + 20] = section_digest(bytes(buf), section)
    result = bytes(buf)
    _require(status(result) == "applied", "later-season schedule postcondition failed")
    _require(calendar.status(result) == "applied", "the calendar no longer reads applied")
    return result, dict(common, already_applied=False, edits=edits, sections_repinned=sorted(touched),
                        changed_bytes=sum(a != b for a, b in zip(payload, result)),
                        before_sha256=hashlib.sha256(payload).hexdigest(),
                        after_sha256=hashlib.sha256(result).hexdigest())


__all__ = ["BUILD_CAPTION", "DALLAS", "DETROIT", "GUARDS", "HOOK_VA", "HOSTS", "OWNER", "REGIONS", "LaterScheduleError",
           "apply", "base_opening_days", "code_regions", "status"]

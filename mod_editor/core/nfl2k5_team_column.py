"""A TEAM column on the franchise Player Card's season-by-season stats (executable patch, xemu-only).

What the retail game does (``default.xbe``, static RE 2026-09-03).  The franchise Player Card is a
generic spreadsheet screen: ``FUN_00320b90`` (0x320B90) picks one of seven screen definitions in
``.rdata`` by the player's position byte, and each definition's spreadsheet struct points at a
zero-terminated list of column descriptor pointers (0xD8-byte column-list structs 0x535180,
0x535258, 0x535320, 0x5353E8, 0x5354A8, 0x535580; pointers from ``+0x9C``; the offensive line has no
table).  Rows are the seasons: the row builder ``FUN_00320c60`` keys them by "bank" 11..26 (11 = the
current season, 12 = last season, ...) plus bank 9 for ``Total:``.  The ``Yr`` column
(descriptor 0x535020) is a *string* column whose getter ``FUN_00320460`` is called with ecx = the
row's bank and returns a UTF-16 pointer; the stat columns are float getters.

Season stats live in a packed per-player dword stream (``player+0x2C`` into the roster object's
pool ``[0xB72918]+0x44``): bits 0..15 value, 16..22 field id, 23..27 season slot, 28 = deleted,
29 = postseason class, 30 = folded "pre" row, 31 = end of the player's stream.  Fields 0..86 are
stat counters; **no retail field is a team**; this patch uses 87 (team index + 1).

Revision 2 (b77 job F3, 2026-10-07).  Revision 1 (beta 57 .. 76.5) found the player's club in
``player+0x30`` and recorded the season's club at the season rollover.  **That field is never
populated**: it is 0 in every record of the disc ROST, 0 after the game's own relocation
(``FUN_000c0500`` / ``FUN_000e5e70`` never touch it), 0 for all 2,479 players of a real played
year-7 franchise save, and no roster mover writes it (``FUN_000c3ee0`` / ``FUN_000c4090`` add a
player to a club's pointer array, ``FUN_000c3a90`` / ``FUN_000c3eb0`` remove one; the game's own
"which club is he on" lookups, ``FUN_00321530`` and ``FUN_00241d10``, search the club arrays with
``FUN_000c4060``).  Consequences under revision 1, proved natively on the v0.5 executable and
roster: the current-season row read ``--`` for every one of the 2,619 players, and the rollover
cave stored nothing for any franchise-played season, so only history baked into the ROST
(``nfl2k5_team_history``, which reads the club arrays) ever showed a team.

Revision 2 keeps the column, its descriptor and the six list insertions and changes how a club is
found and when it is recorded:

* **club lookup** (``club_of``): search the club records 0..33 (32 clubs + the two user teams;
  a player is in at most one club array, counted bytes at ``team+0x11C``) with ``repne scasd``.
  Injured-reserve players are parked outside the arrays by the game and fall back to the recorded
  club; free agents and retired players have none.
* **recording per game** (``post`` cave): every user-played and simulated game ends in
  ``FUN_00135310`` -> ``FUN_00134dd0``, which loops over the club's players and calls the stat
  merge ``FUN_001334b0`` once each at 0x134E05.  A 7-byte hook right after that call (0x134E0A,
  ``mov ecx,ebx ; call 0x61b90`` -> ``jmp cave``) finds the club in ``esi`` and the player at
  ``[esi+ebp*4]`` and, when the player has a regular-season games entry for the current season,
  writes field 87 = club index + 1 into the current slot through the game's own writer
  (``FUN_0014f430``; an update in place after the first game, one dword per player-season).  The
  season therefore holds the club of the player's **last game** of that season: a trade, a signing
  or a release changes it from the next game on, and a released player keeps the club he played
  for.  A split season shows its LAST club (one value per row; the first club is not kept).
* **rollover cave**: the hook at 0x247C1B stays exactly where revision 1 put it so no other
  owner's view of ``FUN_00247b40`` moves, but the cave now only runs the displaced retail slot-count
  increment (nothing is recorded at the rollover any more).
* **getter**: bank 9 -> an empty string; bank 11 (the season in progress) -> the live club found
  in the club arrays, else the recorded field 87 of the current slot; older banks -> the field-87
  entry of that slot; ``--`` when there is no entry, it was folded into the "pre" row (bit 30), or
  the index is not a team of this roster.  It returns the club record's own persistent string,
  never the shared ``0xC901C8`` buffer.
* **column descriptor** (0xB0 bytes, a clone of ``Yr``: string format, frozen next to it, header
  ``L"TEAM"`` / ``L"Team Name"`` from the existing string pool) inserted as the second column of all
  six lists in place (the walkers read pointers until a zero word; the two full lists' terminators
  land on the next struct's zero first word).  MyCareer's MyPlayer card is the same native Player
  Card, so it shares all of this.

Everything lives in the unused tail of the dead ``FUN_00046ee0`` (0x47220..0x47420; the widescreen
cave owns the first 0x340 bytes of that function), plus the one 7-byte hook site.  Pattern-checked
against the retail bytes, ``.text`` digest recomputed.  A revision-1 image (the beta 57 .. 76.5 /
v0.5 layout) reads as ``applied`` (``revision()`` is 1, so every other owner that consults this
patch keeps recognising it) and ``apply()`` upgrades it in place.  Unwitnessed at runtime; the
caves are executed under unicorn on the patched image by
``tests/mod_editor/test_nfl2k5_team_column.py``.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Mapping

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest
from .nfl2k5_draft_ai import _Asm
from .nfl2k5_widescreen import CODE_CAVE_SIZE as _WIDESCREEN_CODE_CAVE_SIZE, CODE_VA as _WIDESCREEN_CODE_VA

IMAGE_BASE = 0x10000

# --- the game's own routines and globals (retail default.xbe) -----------------------------------
FN_FIND_ENTRY = 0x0014EE20      # (ecx=player, edx=field, [slot]) -> dword* of the live entry or 0; callee pops
FN_SET_CURRENT = 0x0014F430     # (ecx=player, edx=field, [value]) -> writes the current slot (0 deletes); callee pops
FN_NEXT_PLAYER = 0x00061B90     # (ecx = in-game player) -> the next one; the displaced call of the post-game loop
ROSTER_GLOBAL = 0x00B72918      # -> roster object: +0x18 team count, +0x1C team array (0x1F4 stride), +0x40/+0x44 pool
CLASS_GLOBAL = 0x00BD7F98       # history class: 0 regular season, 1 postseason (the post-game merge leaves it at 0; revision 1 forced it)
PLAYER_GLOBAL = 0x00C90248      # the Player Card's player
TEAM_STRIDE = 0x1F4
TEAM_ABBR_OFF = 0x108           # team + 0x108 -> UTF-16 abbreviation (the League Leaders TEAM column shows it)
TEAM_COUNT_OFF = 0x11C          # team + 0x11C -> byte, players in the club's pointer array (array at team + 0)
TEAM_FIELD = 87                 # the new history field id (0..86 are the retail stat fields)
CLUB_LIMIT = 34                 # club records searched: 0..31 = the 32 clubs, 32/33 = the two user teams

# --- hook 1: the slot-count increment inside FUN_00247b40 (unchanged since revision 1) -----------
HOOK_VA = 0x00247C1B
HOOK_RESUME_VA = 0x00247C34     # `mov ecx,[0xB72918]`: the per-player loop continues here
RETAIL_HOOK = bytes.fromhex("8b46248bc8c1e90841c1e10833c881e1001f000033c8894e24")   # 25 bytes
HOOK_SIZE = len(RETAIL_HOOK)
assert HOOK_VA + HOOK_SIZE == HOOK_RESUME_VA

# --- hook 2: the post-game merge loop of FUN_00134dd0 (revision 2) ------------------------------
# 00134e00 mov eax,[esi+ebp*4] ; push esi ; push ebx ; call 0x1334b0 (the per-player stat merge)
# 00134e0a mov ecx,ebx ; call 0x61b90        <- replaced by `jmp post ; nop ; nop`
# 00134e11 mov ebx,eax ; ...                 <- the cave jumps back here
POST_HOOK_VA = 0x00134E0A
POST_RESUME_VA = 0x00134E11
RETAIL_POST_HOOK = bytes.fromhex("8bcbe87fcdf2ff")      # mov ecx,ebx ; call 0x61b90
POST_HOOK_SIZE = len(RETAIL_POST_HOOK)
assert POST_HOOK_VA + POST_HOOK_SIZE == POST_RESUME_VA
assert POST_HOOK_VA + 2 + 5 + struct.unpack_from("<i", RETAIL_POST_HOOK, 3)[0] == FN_NEXT_PLAYER

# --- cave: the unused tail of dead FUN_00046ee0 -------------------------------------------------
CAVE_VA = 0x00047220
CAVE_SIZE = 0x200
assert CAVE_VA == _WIDESCREEN_CODE_VA + _WIDESCREEN_CODE_CAVE_SIZE, "must start right after the widescreen cave"
RETAIL_CAVE = bytes.fromhex(
    "2434d95c2424d94618d8442438d95c2428d9461cd844243cd95c242ce82f58feff8b46548b4e585051e84259feff"
    "d9442430d846208d4c2420d95c2420d94624d8442434d95c2424d94628d8442438d95c2428d9462cd844243cd95c"
    "242ce8ed57feff8b565c8b46505250e80059feffd94424308d4c2420d84630d95c2420d94634d8442434d95c2424"
    "d94638d8442438d95c2428d9463cd844243cd95c242ce8ab57feff8b4e5c8b56585152e8be58feffd9442430d846"
    "408d4c2420d95c2420d94644d8442434d95c2424d94648d8442438d95c2428d9464cd844243cd95c242ce86957fe"
    "ff8b4f20e8d158feff8b46548b4e505051e87458feffd9442440d847108d4c2420d95c2420d94714d8442444d95c"
    "2424d94718d8442448d95c2428d9471cd844244cd95c242ce81f57feff8b56548b46585250e83258feffd9442450"
    "d847108d4c2420d95c2420d94714d8442454d95c2424d94718d8442458d95c2428d9471cd844245cd95c242ce8dd"
    "56feff8b4e5c8b56505152e8f057feffd9442470d847108d4c2420d95c2420d94714d8442474d95c2424d94718d8"
    "442478d95c2428d9471cd844247cd95c242ce89b56feff8b465c8b4e585051e8ae57feffd9442460d847108d4c24"
    "20d95c2420d94714d8442464d95c2424d94718d8442468d95c2428d9471cd844246cd95c242ce85956feff8b065e"
    "8be55dc20c00"
)
assert len(RETAIL_CAVE) == CAVE_SIZE
# the revision-1 cave (beta 57 .. 76.5, v0.5): recognised by digest, replaced on upgrade
LEGACY_CAVE_SHA256 = "cd2cfb8042c563342428de0b2037096d572a0d037ad69c0ca9682fcced819e8d"
CODE_LIMIT = 0x140                      # the caves must fit before the strings
STR_EMPTY_VA = CAVE_VA + 0x140          # L""
STR_DASH_VA = CAVE_VA + 0x144           # L"--"
DESCRIPTOR_VA = CAVE_VA + 0x150         # the 0xB0-byte column descriptor (16-aligned)
DESCRIPTOR_SIZE = 0xB0
assert DESCRIPTOR_VA + DESCRIPTOR_SIZE == CAVE_VA + CAVE_SIZE

# --- the Yr column descriptor (cloned) and the six column lists (.rdata) ------------------------
YR_DESCRIPTOR_VA = 0x00535020
RETAIL_YR_DESCRIPTOR = bytes.fromhex(
    "08000000" "03000000" "60043200" "0a000100"     # string cell, 3, getter FUN_00320460, delegate cookie 0x1000A
    + "00" * 0x54                                    # +0x10..+0x63 unused by this descriptor
    + "01000000"                                     # +0x64 frozen (left pane)
    + "d0cc2700" "00000100" "2c35ea00" + "00" * 12   # +0x68 text {identity, 0x10000, L"Yr"}
    + "d0cc2700" "00000100" "3435ea00" + "00" * 12   # +0x80 text {identity, 0x10000, L"Year of Career Stats"}
    + "d0cc2700" "00000100" "00000000" + "00" * 12   # +0x98 text {identity, 0x10000, stat id 0}
)
assert len(RETAIL_YR_DESCRIPTOR) == DESCRIPTOR_SIZE
STR_TEAM_VA = 0x00EA8BB4        # L"TEAM" (the League Leaders header, retail string pool)
STR_TEAM_NAME_VA = 0x00EA8BC0   # L"Team Name"
TEXT_SOURCE_FN = 0x0027CCD0     # identity: the descriptor's text-source callback
LIST_SLOTS = 16                 # pointer words checked per list (15 slots + the next struct's zero word)
LIST_POINTERS_OFF = 0x9C
# (label, column-list struct VA, retail pointer words from +0x9C: Yr, stat columns..., zero terminators)
COLUMN_LISTS: tuple[tuple[str, int, tuple[int, ...]], ...] = (
    ("QB", 0x00535180, (0x535020, 0x5350D0, 0x533550, 0x533600, 0x533760, 0x5336B0, 0x533810, 0x5338C0,
                        0x533970, 0x5334A0, 0x533A20, 0x533AD0, 0x533B80, 0x533C30)),
    ("RB/FB", 0x00535258, (0x535020, 0x5350D0, 0x533A20, 0x533AD0, 0x533B80, 0x533C30, 0x533CE0, 0x533D90,
                           0x533E40, 0x533EF0)),
    ("WR/TE", 0x00535320, (0x535020, 0x5350D0, 0x533CE0, 0x533D90, 0x533E40, 0x533EF0, 0x533A20, 0x533AD0,
                           0x533B80, 0x533C30)),
    ("defense", 0x005353E8, (0x535020, 0x5350D0, 0x533FA0, 0x534050, 0x534310, 0x534100, 0x5341B0, 0x534260)),
    ("K", 0x005354A8, (0x535020, 0x5345D0, 0x534680, 0x534730, 0x5347E0, 0x534890, 0x534940, 0x5349F0,
                       0x534AA0, 0x5343C0, 0x534470, 0x534520, 0x534C00, 0x534B50)),
    ("P", 0x00535580, (0x535020, 0x534CB0, 0x534D60, 0x534E10, 0x534EC0, 0x534F70)),
)
for _label, _va, _pointers in COLUMN_LISTS:
    assert _pointers[0] == YR_DESCRIPTOR_VA and len(_pointers) <= LIST_SLOTS - 2, _label


class TeamColumnError(ValueError):
    """The TEAM-column patch cannot be applied to this executable."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TeamColumnError(message)


def _imm(value: int) -> str:
    return struct.pack("<I", value).hex()


def _code(club_of_va: int = CAVE_VA) -> tuple[bytes, dict[str, int]]:
    """All caves, assembled at CAVE_VA: rollover (entry CAVE_VA), post, club_of, getter.
    Returns (bytes, label offsets).  ``club_of_va`` is the target of the getter's one intra-cave call
    (a placeholder on the first pass; ``_build`` assembles twice)."""

    a = _Asm(CAVE_VA)
    # ---- rollover cave: called from HOOK_VA; it only runs the displaced retail increment of the
    #      slot count (esi = player, ebx/ebp/edi live; nothing is recorded at the rollover any more)
    a.label("rollover")
    a.b(RETAIL_HOOK.hex())
    a.b("c3")                           # ret (back into the NOPs after the hook)

    # ---- post cave: jumped to from POST_HOOK_VA inside the post-game loop of FUN_00134dd0, right
    #      after FUN_001334b0 merged this player's game.  Live: esi = the club record, ebp = the
    #      index in its player array, ebx = in-game player, edi = in-game team (all preserved);
    #      eax/ecx/edx are free.  Records field 87 = club index + 1 in the player's current slot
    #      when he has a regular-season games entry, then runs the displaced `mov ecx,ebx ;
    #      call 0x61b90` and resumes at POST_RESUME_VA.
    a.label("post")
    a.b("8bc6")                         # mov eax,esi                 ; the club record
    a.b("8b0d" + _imm(ROSTER_GLOBAL))   # mov ecx,[roster]
    a.b("2b411c")                       # sub eax,[ecx+0x1c]          ; club - team array base
    a.b("31d2")                         # xor edx,edx
    a.b("b9" + _imm(TEAM_STRIDE))       # mov ecx,0x1f4
    a.b("f7f1")                         # div ecx                     ; eax = club index (huge when below the array)
    a.b("83f8" + f"{CLUB_LIMIT:02x}")   # cmp eax,34
    a.j8("73", "post_out")              # jae post_out                ; not one of the 32 clubs / 2 user teams
    a.b("40")                           # inc eax                     ; value = index + 1 (0 would delete)
    a.b("50")                           # push eax                    ; [esp] = value
    a.b("8b0cae")                       # mov ecx,[esi+ebp*4]         ; the player
    a.b("8b4124")                       # mov eax,[ecx+0x24]
    a.b("c1e808")                       # shr eax,8
    a.b("83e01f")                       # and eax,0x1f                ; current slot = season count
    a.b("50")                           # push eax                    ; slot
    a.b("31d2")                         # xor edx,edx                 ; field 0 = games played
    a.call(FN_FIND_ENTRY)               # eax = this season's games entry, or 0 (the class is 0 after the merge)
    a.b("85c0")                         # test eax,eax
    a.j8("74", "post_skip")             # jz post_skip                ; did not play this season: nothing to record
    a.b("8b0cae")                       # mov ecx,[esi+ebp*4]
    a.b("ba" + _imm(TEAM_FIELD))        # mov edx,87
    a.b("ff3424")                       # push dword [esp]            ; the value again
    a.call(FN_SET_CURRENT)              # field 87 of the current slot := club index + 1 (callee pops)
    a.label("post_skip")
    a.b("58")                           # pop eax                     ; discard the value
    a.label("post_out")
    a.b("8bcb")                         # mov ecx,ebx                 ; the displaced instructions
    a.call(FN_NEXT_PLAYER)              # call 0x61b90
    a.jmp_abs(POST_RESUME_VA)           # jmp 0x134e11

    # ---- club_of: eax = player record -> eax = club index 0..33, or -1 (free agent, retired,
    #      injured reserve).  Preserves ebx/esi/edi; clobbers ecx/edx.
    a.label("club_of")
    a.b("565753")                       # push esi ; push edi ; push ebx
    a.b("8b15" + _imm(ROSTER_GLOBAL))   # mov edx,[roster]
    a.b("8b721c")                       # mov esi,[edx+0x1c]          ; club records
    a.b("bb" + _imm(CLUB_LIMIT))        # mov ebx,34                  ; clubs left to search
    a.label("club_next")
    a.b("0fb68e" + _imm(TEAM_COUNT_OFF))    # movzx ecx,byte [esi+0x11c] ; players in this club
    a.j8("e3", "club_skip")             # jecxz club_skip
    a.b("8bfe")                         # mov edi,esi                 ; its player pointer array starts at team+0
    a.b("f2af")                         # repne scasd                 ; search the counted pointers for eax
    a.j8("74", "club_found")            # je club_found
    a.label("club_skip")
    a.b("81c6" + _imm(TEAM_STRIDE))     # add esi,0x1f4
    a.b("4b")                           # dec ebx
    a.j8("75", "club_next")             # jnz club_next
    a.b("83c8ff")                       # or eax,-1                   ; not on a club
    a.j8("eb", "club_out")              # jmp club_out
    a.label("club_found")
    a.b("b8" + _imm(CLUB_LIMIT))        # mov eax,34
    a.b("2bc3")                         # sub eax,ebx                 ; index = 34 - clubs left
    a.label("club_out")
    a.b("5b5f5e")                       # pop ebx ; pop edi ; pop esi
    a.b("c3")                           # ret

    # ---- getter cave: ecx = row bank -> eax = UTF-16 pointer
    a.label("getter")
    a.b("83f909")                       # cmp ecx,9
    a.j8("75", "rows")                  # jne rows
    a.b("b8" + _imm(STR_EMPTY_VA))      # mov eax,L""                 ; the Total: row
    a.b("c3")                           # ret
    a.label("rows")
    a.b("8b15" + _imm(PLAYER_GLOBAL))   # mov edx,[player]
    a.b("85d2")                         # test edx,edx
    a.j8("74", "dash")                  # jz dash
    a.b("8b4224")                       # mov eax,[edx+0x24]
    a.b("c1e808")                       # shr eax,8
    a.b("83e01f")                       # and eax,0x1f                ; season count = the current slot
    a.b("83f90b")                       # cmp ecx,11
    a.j8("75", "past")                  # jne past
    a.b("50")                           # push eax                    ; current slot
    a.b("52")                           # push edx                    ; player
    a.b("8bc2")                         # mov eax,edx
    a.call(club_of_va)                  # eax = club index 0..33, or -1
    a.b("5a")                           # pop edx                     ; player
    a.b("59")                           # pop ecx                     ; current slot
    a.b("85c0")                         # test eax,eax
    a.j8("79", "have")                  # jns have                    ; he is on a club right now: show it
    a.b("8bc1")                         # mov eax,ecx                 ; no club: the recorded club of this season
    a.j8("eb", "lookup")                # jmp lookup
    a.label("past")
    a.b("2bc1")                         # sub eax,ecx
    a.b("83c00b")                       # add eax,11                  ; slot = count - bank + 11
    a.j8("78", "dash")                  # js dash
    a.label("lookup")
    a.b("50")                           # push eax                    ; slot
    a.b("8bca")                         # mov ecx,edx                 ; player
    a.b("ba" + _imm(TEAM_FIELD))        # mov edx,87
    a.call(FN_FIND_ENTRY)               # eax = the team entry of that slot, or 0
    a.b("85c0")                         # test eax,eax
    a.j8("74", "dash")                  # jz dash
    a.b("8b00")                         # mov eax,[eax]
    a.b("a900000040")                   # test eax,0x40000000         ; folded into the "pre" row
    a.j8("75", "dash")                  # jnz dash
    a.b("0fb7c0")                       # movzx eax,ax                ; club index + 1
    a.b("48")                           # dec eax
    a.j8("78", "dash")                  # js dash
    a.label("have")
    a.b("8b0d" + _imm(ROSTER_GLOBAL))   # mov ecx,[roster]
    a.b("3b4118")                       # cmp eax,[ecx+0x18]
    a.j8("73", "dash")                  # jae dash                    ; not a team of this roster
    a.b("69c0" + _imm(TEAM_STRIDE))     # imul eax,eax,0x1f4
    a.b("03411c")                       # add eax,[ecx+0x1c]          ; the team record
    a.b("8b80" + _imm(TEAM_ABBR_OFF))   # mov eax,[eax+0x108]         ; its abbreviation
    a.b("85c0")                         # test eax,eax
    a.j8("75", "ret")                   # jnz ret
    a.label("dash")
    a.b("b8" + _imm(STR_DASH_VA))       # mov eax,L"--"
    a.label("ret")
    a.b("c3")                           # ret
    code = a.assemble()
    return code, dict(a.labels)


def _build() -> tuple[bytes, dict[str, int]]:
    """Assemble twice: the first pass fixes the label offsets, the second resolves the one
    intra-cave call (getter -> club_of) with the real address."""

    _first, labels = _code()
    code, again = _code(CAVE_VA + labels["club_of"])
    _require(again == labels, "label drift between assembler passes")
    return code, labels


def cave_labels() -> dict[str, int]:
    """Label -> VA inside the cave (rollover, post, club_of, getter, ...)."""

    _code_bytes, labels = _build()
    return {name: CAVE_VA + off for name, off in labels.items()}


GETTER_VA = cave_labels()["getter"]
POST_VA = cave_labels()["post"]
CLUB_OF_VA = cave_labels()["club_of"]


def descriptor_bytes() -> bytes:
    """The TEAM column descriptor: the Yr descriptor with the getter, the header strings and stat id 0."""

    d = bytearray(RETAIL_YR_DESCRIPTOR)
    struct.pack_into("<I", d, 0x00, 8)                 # string cell (as Yr)
    struct.pack_into("<I", d, 0x08, GETTER_VA)          # getter delegate (cookie 0x1000A kept: ecx = bank)
    struct.pack_into("<I", d, 0x64, 1)                  # frozen next to Yr
    struct.pack_into("<I", d, 0x70, STR_TEAM_VA)        # abbr  L"TEAM"
    struct.pack_into("<I", d, 0x88, STR_TEAM_NAME_VA)   # long  L"Team Name"
    struct.pack_into("<I", d, 0xA0, 0)                  # stat id (unused by a string getter)
    for off in (0x68, 0x80, 0x98):
        _require(struct.unpack_from("<II", d, off) == (TEXT_SOURCE_FN, 0x10000), "descriptor text-source shape")
    return bytes(d)


def cave_bytes() -> bytes:
    """The 512-byte cave: all caves, int3 padding, the two strings, then the descriptor."""

    code, _labels = _build()
    _require(len(code) <= CODE_LIMIT, f"caves are {len(code)} bytes, over {CODE_LIMIT}")
    body = code + b"\xcc" * (CODE_LIMIT - len(code))
    strings = bytearray(DESCRIPTOR_VA - STR_EMPTY_VA)
    strings[STR_EMPTY_VA - STR_EMPTY_VA: STR_EMPTY_VA - STR_EMPTY_VA + 2] = b"\x00\x00"
    strings[STR_DASH_VA - STR_EMPTY_VA: STR_DASH_VA - STR_EMPTY_VA + 6] = "--".encode("utf-16-le") + b"\x00\x00"
    out = body + bytes(strings) + descriptor_bytes()
    _require(len(out) == CAVE_SIZE, "cave size drift")
    return out


PATCHED_HOOK = b"\xe8" + struct.pack("<i", CAVE_VA - (HOOK_VA + 5)) + b"\x90" * (HOOK_SIZE - 5)
PATCHED_POST_HOOK = b"\xe9" + struct.pack("<i", POST_VA - (POST_HOOK_VA + 5)) + b"\x90" * (POST_HOOK_SIZE - 5)


def list_words(pointers: tuple[int, ...], patched: bool) -> bytes:
    """The LIST_SLOTS pointer words of a column list: retail, or with the TEAM descriptor as column 2."""

    words = list(pointers)
    if patched:
        words = [words[0], DESCRIPTOR_VA, *words[1:]]
    words += [0] * (LIST_SLOTS - len(words))
    return struct.pack(f"<{LIST_SLOTS}I", *words)


def _header_size(payload: bytes) -> int:
    return struct.unpack_from("<I", payload, 0x108)[0]


def _offset(payload: bytes, va: int) -> int:
    if IMAGE_BASE <= va < IMAGE_BASE + _header_size(payload):
        return va - IMAGE_BASE
    for section in _sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise TeamColumnError(f"VA 0x{va:x} is in no section")


def _sites(payload: bytes, *, legacy: bool = False) -> list[tuple[str, int, bytes, bytes]]:
    """(label, file offset, retail bytes, patched bytes).  ``legacy`` leaves out the two sites whose
    revision-1 form differs (the cave, whose digest is checked separately, and the post hook,
    which revision 1 did not have)."""

    sites = [("hook", _offset(payload, HOOK_VA), RETAIL_HOOK, PATCHED_HOOK)]
    if not legacy:
        sites.append(("post_hook", _offset(payload, POST_HOOK_VA), RETAIL_POST_HOOK, PATCHED_POST_HOOK))
        sites.append(("cave", _offset(payload, CAVE_VA), RETAIL_CAVE, cave_bytes()))
    for label, va, pointers in COLUMN_LISTS:
        sites.append((f"list_{label}", _offset(payload, va + LIST_POINTERS_OFF),
                      list_words(pointers, False), list_words(pointers, True)))
    return sites


def _legacy_cave(payload: bytes) -> bool:
    off = _offset(payload, CAVE_VA)
    return hashlib.sha256(payload[off: off + CAVE_SIZE]).hexdigest() == LEGACY_CAVE_SHA256


def _classify(payload: bytes) -> str:
    """retail | revision2 | revision1 (beta 57 .. 76.5, the v0.5 disc: the +0x30 lookup) | foreign."""

    try:
        sites = _sites(payload)
        yr = _offset(payload, YR_DESCRIPTOR_VA)
    except (TeamColumnError, ValueError, struct.error):
        return "foreign"
    if payload[yr: yr + DESCRIPTOR_SIZE] != RETAIL_YR_DESCRIPTOR:
        return "foreign"
    states = set()
    for _label, off, before, after in sites:
        got = payload[off: off + len(before)]
        states.add("retail" if got == before else "applied" if got == after else "foreign")
    if states == {"retail"}:
        return "retail"
    if states == {"applied"}:
        return "revision2"
    # revision 1: hook + legacy cave + six lists applied, the post-game hook still retail
    if _legacy_cave(payload):
        legacy_states = set()
        for _label, off, before, after in _sites(payload, legacy=True):
            got = payload[off: off + len(before)]
            legacy_states.add("retail" if got == before else "applied" if got == after else "foreign")
        post = _offset(payload, POST_HOOK_VA)
        if legacy_states == {"applied"} and payload[post: post + POST_HOOK_SIZE] == RETAIL_POST_HOOK:
            return "revision1"
    return "foreign"


def status(payload: bytes) -> str:
    """retail | applied | foreign.

    ``applied`` covers both installed revisions on purpose: other owners (defensive try, the Player Card star,
    the allocator checks) only need the descriptor, the six lists and the hook site, which revision 1 and 2 share,
    and a v0.5 image must keep reading as installed for all of them.  ``revision()`` tells the two apart and
    ``apply()`` upgrades revision 1 in place."""

    state = _classify(payload)
    return "applied" if state in ("revision1", "revision2") else state


def revision(payload: bytes) -> int | None:
    """0 = retail, 1 = revision 1 (the +0x30 lookup, never recorded a franchise season), 2 = this revision,
    None = foreign."""

    return {"retail": 0, "revision1": 1, "revision2": 2}.get(_classify(payload))


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    state = _classify(payload)
    if state == "revision2":
        return payload, {"already_applied": True, "changed_bytes": 0}
    _require(state in ("retail", "revision1"), f"TEAM-column sites are {state}, not retail or an upgradeable revision 1")
    buf = bytearray(payload)
    sections = _sections(payload)
    touched = set()
    edits = []
    for label, off, before, after in _sites(payload):
        _require(len(before) == len(after), label)
        if state == "revision1" and label in ("hook", *(f"list_{n}" for n, _v, _p in COLUMN_LISTS)):
            continue            # revision 1 already carries these exact bytes
        buf[off: off + len(after)] = after
        touched.add(_section_for_offset(sections, off).index)
        edits.append({"label": label, "file_offset": f"0x{off:x}", "bytes": len(after)})
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d: d + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    _require(_classify(patched) == "revision2", "post-apply verification failed")
    changed = sum(1 for a, b in zip(payload, patched) if a != b)
    code, _labels = _build()
    receipt = {"edits": edits, "changed_bytes": changed, "sections_repinned": sorted(touched),
               "code_bytes": len(code), "cave_va": f"0x{CAVE_VA:x}", "getter_va": f"0x{GETTER_VA:x}",
               "post_va": f"0x{POST_VA:x}", "club_of_va": f"0x{CLUB_OF_VA:x}",
               "descriptor_va": f"0x{DESCRIPTOR_VA:x}", "field": TEAM_FIELD, "revision": 2}
    if state == "revision1":
        receipt["upgraded_from_revision"] = 1
    return patched, receipt


__all__ = ["TeamColumnError", "CAVE_SIZE", "CAVE_VA", "CLUB_LIMIT", "CLUB_OF_VA", "COLUMN_LISTS", "DESCRIPTOR_VA",
           "GETTER_VA", "HOOK_RESUME_VA", "HOOK_VA", "LEGACY_CAVE_SHA256", "PATCHED_HOOK", "PATCHED_POST_HOOK",
           "POST_HOOK_VA", "POST_RESUME_VA", "POST_VA", "RETAIL_CAVE", "RETAIL_HOOK", "RETAIL_POST_HOOK",
           "RETAIL_YR_DESCRIPTOR", "STR_DASH_VA", "STR_EMPTY_VA", "TEAM_FIELD", "YR_DESCRIPTOR_VA", "apply",
           "cave_bytes", "cave_labels", "descriptor_bytes", "list_words", "revision", "status", "CLASS_GLOBAL"]

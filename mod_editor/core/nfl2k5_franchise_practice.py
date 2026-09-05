"""Free Practice inside Franchise: a *Practice* row on the Coach's Desk (executable patch, xemu-only).

Retail ``default.xbe`` (study of 2026-09-04; every address is an Xbox virtual address):

* The franchise/season hub is the **Coach's Desk** screen, descriptor ``.rdata 0x522190``:
  ``+0x00`` title ``L"Coach's Desk"``, ``+0x04`` event-hook list ``0x521EE8``, ``+0x08`` screen
  handler ``cb_000F3E90``, ``+0x10`` **row table** ``0x521F20``, ``+0x18`` layout ``'coach_desk'``,
  ``+0x1C`` runtime state ``0xACF1A8``, ``+0x28`` screen id 7.
* A menu row is 0x34 bytes: ``+0x00`` type (**9** = action row, **3** = end of list), ``+0x04``
  label (UTF-16), ``+0x28`` activate callback (``__fastcall``, ``ecx`` = the screen manager),
  ``+0x2C`` visibility callback (0 = always visible).  The Coach's Desk has eleven rows
  (Schedule .. Quit) and its terminator sits at ``0x52215C``, immediately before the descriptor:
  **there is no spare row slot**.
* The event-hook list is pairs ``(event, record)`` closed by a zero dword; the dispatcher
  ``FUN_0006E4E0`` walks it, and inside one record it walks 0x24-byte slots (``+0x00`` kind,
  kind 3 calls ``+0x0C``) until a slot's kind is zero.  The Coach's Desk list is 52 bytes at
  ``0x521EE8`` and is followed by four bytes of padding, so **relocating it frees exactly the 56
  bytes 0x521EE8..0x521F1F -- room for one more row immediately before the retail table**.
* Practice is set up entirely by the **Scrimmage Settings** screen ``0x501834`` (hooks ``0x5016AC``:
  event 0xB -> Team Select, event 1 -> record ``0x501640`` whose slot A ``cb_00148B80`` picks two
  random teams and whose slot B ``cb_00148AD0`` sets Practice Type 0 = *Special Move*, calls
  ``FUN_000E33F0`` (game-mode word ``0xE5FF80``) and forces the ``s32`` practice field).  Its
  START handler is ``+0x30`` = ``FUN_00148B50``, which flags the game pending
  (``[mgr[0x10C]+0xA84] = 1``) and **pops twice** before ``jmp FUN_00064B10`` -- two pops because
  retail Practice is two pushes deep from Game Modes.
* The teams for a game are the globals ``0xE5FE68`` (away, setter ``FUN_00077AE0``) and
  ``0xE5FE6C`` (home, setter ``FUN_00077B20``); no retail instruction compares them.
* ``FUN_000C4D70`` is retail's own "the team the user coaches": it walks the human-controller array
  ``0xE5775C`` for the first non-zero entry and tail-calls ``FUN_000C4C50`` to turn the index into
  the team object (0 when nobody coaches).  Nine retail call sites use it.
* There is exactly one roster object in memory (``[0xB72918]``) and loading a franchise overwrites
  it, so a practice session started from inside a franchise already sees the franchise roster.

The patch adds one row and one cloned settings screen; **no retail instruction byte is modified**:

1. the 52-byte Coach's Desk hook list is copied into the cave (same six ``(event, record)``
   pairs, event 5 moved to the end -- see ``CAVE_HOOK_ORDER``) and ``0x522194`` repointed at the
   copy, which frees ``0x521EE8..0x521F1F``;
2. ``0x5221A0`` (the descriptor's row-table pointer) moves from ``0x521F20`` to ``0x521EEC``.
   The four mutually exclusive Schedule rows move back one slot, and the new Practice row
   occupies ``0x521FBC`` (type 9, retail label ``0xE9C3BC``, cave activation, always visible).
   The visible phase-specific Schedule is first and Practice second. The remaining seven
   retail rows and the terminator stay in place. This beta-61 ordering needs no new cave;
3. the row stub is the tail of the retail Front Office callback ``FUN_00142910``: start the fade
   (``FUN_001427A0``) and set the deferred "next screen" ``[0xAA2408]`` to a **clone of the
   Scrimmage Settings descriptor** kept in the cave;
4. the clone is byte-identical to ``0x501834`` except ``+0x04`` (its own hook list: Team Select on
   event 0xB exactly as retail, our record on event 1) and ``+0x30`` (its own START stub);
5. the enter stub calls retail ``cb_00148AD0`` first (practice defaults and the practice field),
   then ``FUN_000C4D70``; if the user coaches a team it becomes **both** sides
   (``FUN_00077AE0`` and ``FUN_00077B20``, each of which also installs that side's playbook name)
   and Practice Type becomes 1 = *Full Scrimmage* through ``FUN_000E33F0`` (game-mode word 1).  With
   no coached team the stub does nothing beyond the retail defaults;
6. the START stub is ``FUN_00148B50`` with **one** pop instead of two, because the franchise entry
   point is one push deep from the Coach's Desk.

Same team on both sides is deliberate: Full Scrimmage is mode 1, so the uniform builder
``FUN_000615A0`` takes the real-kit branch and dresses the away side in the ``a`` kit and the home
side in the ``h`` kit, and the lineup builder fills the offence from the offensive personnel group
and the defence from the defensive one -- your first-team offence against your first-team defence.
Practice is mode 1, and the stat/clock/injury paths are gated on mode >= 4, so a rep cannot write
season stats or injuries; the franchise season state (``0xE576A0..0xE57C40``) is written only by
franchise setters this path never calls, and the save is user-initiated.

The cave is 352 bytes at ``0x1D82D0..0x1D8430``: eleven identical 21-byte type-tag predicates
(``mov ecx,[eax+4]; mov eax,[ecx]; and eax,0xFF000000; sub eax,<tag>; neg eax; sbb eax,eax; inc eax;
ret``) each padded to 32 bytes, with **no reference of any kind** in the retail image -- no rel8,
rel32 or 0F8x branch target, and no dword in any section (aligned scan over all 23 sections) lands
inside it.  It holds only code and read-only tables: the patch has no mutable state, so nothing is
written into ``.text``.  Pattern-checked against the retail bytes, section digests recomputed,
idempotent, no resource or pack change at all.  **Unwitnessed in game.**
"""

from __future__ import annotations

import struct
from typing import Mapping

from . import nfl2k5_rdata_sites as rdata
from .nfl2k5_draft_ai import _Asm

IMAGE_BASE = 0x10000

# ---------------------------------------------------------------------------------------------
# The Coach's Desk
COACH_DESK_DESCRIPTOR_VA = 0x00522190
COACH_DESK_HOOKS_PTR_VA = COACH_DESK_DESCRIPTOR_VA + 0x04     # 0x522194
COACH_DESK_ROWS_PTR_VA = COACH_DESK_DESCRIPTOR_VA + 0x10      # 0x5221A0
COACH_DESK_HOOKS_VA = 0x00521EE8       # 52 bytes + 4 bytes of padding, ending at the row table
COACH_DESK_ROWS_VA = 0x00521F20        # eleven 0x34 rows, terminator (type 3) at 0x52215C
ROW_SIZE = 0x34
RETAIL_ROW_COUNT = 11
FREED_SPAN_VA = COACH_DESK_HOOKS_VA                 # 0x521EE8..0x521F1F, 56 bytes
FREED_SPAN_SIZE = COACH_DESK_ROWS_VA - COACH_DESK_HOOKS_VA
NEW_ROW_VA = COACH_DESK_ROWS_VA - ROW_SIZE          # 0x521EEC: expanded table start (Schedule)
SCHEDULE_ROW_COUNT = 4
PRACTICE_ROW_VA = NEW_ROW_VA + SCHEDULE_ROW_COUNT * ROW_SIZE  # 0x521FBC
# Complete retail records: preserve the phase gates with their labels/activation.
RETAIL_SCHEDULE_ROWS = b"".join(
    struct.pack("<13I", 9, label, *([0] * 8), 0x142880, visibility, 0)
    for label, visibility in (
        (0xE9A730, 0x2C01C0), (0xE9A744, 0x2C01F0),
        (0xE9A768, 0x2C0220), (0xE9A790, 0x2C0250)))
TERMINATOR_VA = COACH_DESK_ROWS_VA + RETAIL_ROW_COUNT * ROW_SIZE   # 0x52215C
ROW_TYPE_ACTION = 9
ROW_TYPE_TERMINATOR = 3
PRACTICE_LABEL_VA = 0x00E9C3BC         # the retail UTF-16 L"Practice" (the Practice submenu title)
PRACTICE_LABEL = "Practice"

RETAIL_COACH_DESK_HOOKS = bytes.fromhex(
    "04000000381d5200"      # event 4 -> record 0x521d38
    "05000000801d5200"      # event 5 -> record 0x521d80
    "06000000c81d5200"      # event 6 -> record 0x521dc8
    "08000000101e5200"      # event 8 -> record 0x521e10
    "01000000581e5200"      # event 1 -> record 0x521e58
    "02000000a01e5200"      # event 2 -> record 0x521ea0
    "00000000")             # terminator
HOOKS_SIZE = len(RETAIL_COACH_DESK_HOOKS)
RETAIL_FREED_SPAN = RETAIL_COACH_DESK_HOOKS + bytes(4)
assert HOOKS_SIZE == 0x34 and len(RETAIL_FREED_SPAN) == FREED_SPAN_SIZE == 56
HOOK_PAIRS = tuple(struct.unpack_from("<II", RETAIL_COACH_DESK_HOOKS, i) for i in range(0, HOOKS_SIZE - 4, 8))

# The copy carries the same six pairs, but the event-5 pair is moved to the end.  The dispatcher
# ``FUN_0006E4E0`` scans the list for the first pair whose event matches, and the six events are
# distinct, so the order is behaviourally irrelevant.  It matters to one of the shipped gates:
# ``tests/mod_editor/test_xbe_patch_memory_writes.py`` disassembles every changed .text span
# linearly, which decodes a cave's *data* as instructions, and in the retail order the bytes
# ``80 1d 52 00 | 06 00 00 00`` (the tail of record 0x521D80 followed by event 6) decode as
# ``sbb byte ptr [0x60052], 0`` -- a phantom absolute write into unmapped memory.  With the event-5
# pair last, those four bytes are always followed by the zero terminator, so any such decode
# addresses 0x52, below the image base, and the gate ignores it whatever the decode phase.
CAVE_HOOK_ORDER = (4, 6, 8, 1, 2, 5)

# ---------------------------------------------------------------------------------------------
# The Scrimmage Settings screen we clone (0x501834..0x501884; everything past +0x34 is retail zero)
SCRIM_DESCRIPTOR_VA = 0x00501834
SCRIM_DESCRIPTOR_SIZE = 0x50
RETAIL_SCRIM_DESCRIPTOR = bytes.fromhex(
    "b0d8e700"          # +0x00 title L"Scrimmage Settings"
    "ac165000"          # +0x04 hook list 0x5016ac                      <- replaced by ours
    "c03f0f00"          # +0x08 screen handler cb_000f3fc0
    "00000000"          # +0x0c
    "c8165000"          # +0x10 row table (Practice Type, Scrimmage Line, Yards To Go, AI, Power Pocket)
    "00000000"          # +0x14
    "e0d7e700"          # +0x18 layout name 'options'
    "0098ac00"          # +0x1c runtime state 0xac9800
    "44004002"          # +0x20 packed layout rect
    "52008d01"          # +0x24
    "55000000"          # +0x28 screen id 0x55
    "01000000"          # +0x2c "has a START handler"
    "508b1400"          # +0x30 START handler FUN_00148b50              <- replaced by ours
    + "00000000" * 7)   # +0x34..+0x4f
assert len(RETAIL_SCRIM_DESCRIPTOR) == SCRIM_DESCRIPTOR_SIZE
SCRIM_HOOKS_VA = 0x005016AC
SCRIM_TEAM_SELECT_RECORD_VA = 0x005015F8       # event 0xB: push the Team Select screen
RETAIL_TEAM_SELECT_RECORD_HEAD = bytes.fromhex("01000000408b1400")     # kind 1, cb_00148b40
SCRIM_ENTER_RECORD_VA = 0x00501640             # event 1: random teams (slot A) + defaults (slot B)
START_HANDLER_VA = 0x00148B50
RETAIL_START_HANDLER = bytes.fromhex("568bf18b860c010000c780840a000001000000e89858f2ff8bcee89158f2ff5ee99bbff1ff")
EVENT_ENTER = 1
EVENT_TEAM_SELECT = 0x0B
HOOK_KIND_SLOT_C = 3                           # kind 3 -> the dispatcher calls record +0x0c

# ---------------------------------------------------------------------------------------------
# Retail routines and globals the cave calls
PRACTICE_DEFAULTS_VA = 0x00148AD0     # cb_00148ad0: Practice Type 0, FUN_000e33f0, s32 practice field
RETAIL_PRACTICE_DEFAULTS_HEAD = bytes.fromhex("57e8faa7f1ffc705d401e60000000000")
COACHED_TEAM_VA = 0x000C4D70          # FUN_000c4d70(): the first human-coached team object, else 0
RETAIL_COACHED_TEAM = bytes.fromhex("e86bfeffff33c985c07e15eb038d49008b148d5c77e50085d27508413bc87cf033c0c3e9b8feffff")
CONTROLLED_TEAMS_VA = 0x00E5775C      # the per-team human-controller array FUN_000c4d70 walks
SET_TEAM_A_VA = 0x00077AE0            # FUN_00077ae0(ecx = team): [0xe5fe68] = team, + its playbook
RETAIL_SET_TEAM_A = bytes.fromhex("890d68fee5008b8910010000e90ffbffff")
SET_TEAM_B_VA = 0x00077B20            # FUN_00077b20(ecx = team): [0xe5fe6c] = team, + its playbook
RETAIL_SET_TEAM_B = bytes.fromhex("890d6cfee5008b8910010000e9fffbffff")
TEAM_A_VA = 0x00E5FE68
TEAM_B_VA = 0x00E5FE6C
PRACTICE_TYPE_APPLY_VA = 0x000E33F0   # FUN_000e33f0(): jump table on [0xe601d4] -> the mode word
RETAIL_PRACTICE_TYPE_APPLY_HEAD = bytes.fromhex("b904000000e8e6ebf7ffa1d401e600")  # stops before the 7-on-7 site
SCREEN_POP_VA = 0x0006E400            # FUN_0006e400(ecx = manager): pop one screen
RETAIL_SCREEN_POP_HEAD = bytes.fromhex("568bf18b860001000085c07e41")
GAME_START_VA = 0x00064B10            # FUN_00064b10(): load and start the pending game
RETAIL_GAME_START_HEAD = bytes.fromhex("e83b110c00")
FADE_VA = 0x001427A0                  # FUN_001427a0(out, in): start the menu fade, ret 8
RETAIL_FADE_HEAD = bytes.fromhex("558bec8b4d0c8b4508890d0424aa00")

NEXT_SCREEN_VA = 0x00AA2408           # the Coach's Desk update handler pushes this descriptor
MODE_VA = 0x00E5FF80                  # game-mode word: practice is 0/1/2, Basic Training 3, games 4+
PRACTICE_TYPE_VA = 0x00E601D4         # Scrimmage Settings -> Practice Type
PRACTICE_TYPE_FULL_SCRIMMAGE = 1
MANAGER_STATE_OFFSET = 0x10C          # manager + 0x10c -> the screen state block
GAME_PENDING_OFFSET = 0xA84           # state + 0xa84 = 1: "a game is pending"
FADE_OUT = 0x41500000                 # 13.0f, the pair every Coach's Desk row callback passes
FADE_IN = 0x41700000                  # 15.0f

# ---------------------------------------------------------------------------------------------
# The cave: eleven dead type-tag predicates at 0x1d82d0, 352 bytes, referenced by nothing.
# Verified 2026-09-04 on the retail image: no E8/E9 rel32, no 0F8x, no rel8 branch and no 4-aligned
# dword in ANY of the 23 sections lands anywhere in 0x1d82d0..0x1d8430.  The routine before it ends
# with `ret` at 0x1d82c0; the routine after it (0x1d8430) is left byte-for-byte retail.
CAVE_VA = 0x001D82D0
CAVE_SIZE = 0x160
CAVE_END_VA = CAVE_VA + CAVE_SIZE
NEXT_ROUTINE_VA = CAVE_END_VA
RETAIL_NEXT_ROUTINE = bytes.fromhex("8b48048b0125000000ff2d0000000ff7d81bc040c3")
_PREDICATE_TAGS = (0x01, 0x02, 0x2C, 0x31, 0x05, 0x06, 0x07, 0x30, 0x09, 0x0B, 0x08)
RETAIL_CAVE = bytes.fromhex("".join(
    f"8b48048b0125000000ff2d000000{tag:02x}f7d81bc040c3" + "90" * 11 for tag in _PREDICATE_TAGS))
assert len(RETAIL_CAVE) == CAVE_SIZE

HOOKS_OFFSET = 0x000          # 0x34: the relocated Coach's Desk hook list
SCRIM_HOOKS_OFFSET = 0x034    # 0x14: our clone's hook list
ENTER_RECORD_OFFSET = 0x048   # 0x28: the event-1 record (kind 3, callback at +0x0c, +0x24 = 0)
DESCRIPTOR_OFFSET = 0x070     # 0x50: the cloned Scrimmage Settings descriptor
CODE_OFFSET = 0x0C0           # the three stubs
SCRIM_HOOKS_SIZE = 0x14
ENTER_RECORD_SIZE = 0x28

CAVE_HOOKS_VA = CAVE_VA + HOOKS_OFFSET
CAVE_SCRIM_HOOKS_VA = CAVE_VA + SCRIM_HOOKS_OFFSET
CAVE_ENTER_RECORD_VA = CAVE_VA + ENTER_RECORD_OFFSET
CAVE_DESCRIPTOR_VA = CAVE_VA + DESCRIPTOR_OFFSET
CODE_VA = CAVE_VA + CODE_OFFSET
for _va in (CAVE_HOOKS_VA, CAVE_SCRIM_HOOKS_VA, CAVE_ENTER_RECORD_VA, CAVE_DESCRIPTOR_VA, CODE_VA):
    assert _va % 4 == 0, f"cave table 0x{_va:x} is not dword aligned"
assert HOOKS_OFFSET + HOOKS_SIZE <= SCRIM_HOOKS_OFFSET
assert SCRIM_HOOKS_OFFSET + SCRIM_HOOKS_SIZE <= ENTER_RECORD_OFFSET
assert ENTER_RECORD_OFFSET + ENTER_RECORD_SIZE <= DESCRIPTOR_OFFSET
assert DESCRIPTOR_OFFSET + SCRIM_DESCRIPTOR_SIZE <= CODE_OFFSET


class FranchisePracticeError(ValueError):
    """The Franchise-practice patch cannot be applied to this executable."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FranchisePracticeError(message)


def _imm(va: int) -> str:
    return struct.pack("<I", va).hex()


def _code() -> tuple[bytes, dict[str, int]]:
    """The row stub, the enter stub and the START stub."""

    a = _Asm(CODE_VA)

    # --- the Coach's Desk row: FUN_00142910's tail, with our descriptor as the deferred screen ---
    a.label("row")                                      # __fastcall(ecx = screen manager)
    a.b("68" + _imm(FADE_IN))                           # push 15.0f
    a.b("68" + _imm(FADE_OUT))                          # push 13.0f
    a.call(FADE_VA)                                     # call FUN_001427a0    (ret 8: the callee pops)
    a.b("c705" + _imm(NEXT_SCREEN_VA) + _imm(CAVE_DESCRIPTOR_VA))   # mov dword [0xaa2408], <clone>
    a.b("c3")                                           # ret

    # --- event 1 on the cloned screen: retail defaults, then my franchise team on both sides ----
    a.label("enter")                                    # __fastcall(ecx = screen manager)
    a.call(PRACTICE_DEFAULTS_VA)                        # call cb_00148ad0   type 0, mode 0, s32 field
    a.call(COACHED_TEAM_VA)                             # call FUN_000c4d70  eax = my team, 0 if none
    a.b("85c0")                                         # test eax, eax
    a.j8("74", "enter_done")                            # je enter_done      no coach: retail practice
    a.b("50")                                           # push eax
    a.b("8bc8")                                         # mov ecx, eax
    a.call(SET_TEAM_A_VA)                               # call FUN_00077ae0  away = my team
    a.b("59")                                           # pop ecx
    a.call(SET_TEAM_B_VA)                               # call FUN_00077b20  home = the same team
    a.b("c705" + _imm(PRACTICE_TYPE_VA)
        + struct.pack("<I", PRACTICE_TYPE_FULL_SCRIMMAGE).hex())    # mov dword [0xe601d4], 1
    a.call(PRACTICE_TYPE_APPLY_VA)                      # call FUN_000e33f0  -> [0xe5ff80] = 1
    a.label("enter_done")
    a.b("c3")                                           # ret

    # --- START: FUN_00148b50 with one pop (we are one push deep, not two) ----------------------
    a.label("start")                                    # __fastcall(ecx = screen manager)
    a.b("56")                                           # push esi
    a.b("8bf1")                                         # mov esi, ecx
    a.b("8b86" + struct.pack("<I", MANAGER_STATE_OFFSET).hex())              # mov eax, [esi+0x10c]
    a.b("c780" + struct.pack("<I", GAME_PENDING_OFFSET).hex() + "01000000")  # mov [eax+0xa84], 1
    a.call(SCREEN_POP_VA)                               # call FUN_0006e400  -> the Coach's Desk
    a.b("5e")                                           # pop esi
    a.jmp_abs(GAME_START_VA)                            # jmp FUN_00064b10

    code = a.assemble()
    return code, {name: CODE_VA + pos for name, pos in a.labels.items()}


CODE, CODE_LABELS = _code()
CODE_SIZE = len(CODE)
assert CODE_OFFSET + CODE_SIZE <= CAVE_SIZE, \
    f"franchise-practice cave code is {CODE_SIZE} bytes, over the {CAVE_SIZE - CODE_OFFSET} available"
ROW_CALLBACK_VA = CODE_LABELS["row"]
ENTER_STUB_VA = CODE_LABELS["enter"]
START_STUB_VA = CODE_LABELS["start"]


def practice_row() -> bytes:
    """The new 0x34-byte row: type 9, ``L"Practice"``, our activate stub, always visible."""

    row = bytearray(ROW_SIZE)
    struct.pack_into("<II", row, 0x00, ROW_TYPE_ACTION, PRACTICE_LABEL_VA)
    struct.pack_into("<I", row, 0x28, ROW_CALLBACK_VA)
    return bytes(row)


def clone_descriptor() -> bytes:
    """The Scrimmage Settings descriptor with our hook list at +0x04 and our START stub at +0x30."""

    desc = bytearray(RETAIL_SCRIM_DESCRIPTOR)
    struct.pack_into("<I", desc, 0x04, CAVE_SCRIM_HOOKS_VA)
    struct.pack_into("<I", desc, 0x30, START_STUB_VA)
    return bytes(desc)


def cave_hooks() -> bytes:
    """The Coach's Desk hook list, same six pairs, event-5 last (see ``CAVE_HOOK_ORDER``)."""

    by_event = {event: record for event, record in HOOK_PAIRS}
    _require(set(by_event) == set(CAVE_HOOK_ORDER), "the Coach's Desk hook events changed")
    out = b"".join(struct.pack("<II", event, by_event[event]) for event in CAVE_HOOK_ORDER) + bytes(4)
    _require(len(out) == HOOKS_SIZE, "the relocated hook list changed size")
    return out


def clone_hooks() -> bytes:
    """``{0x0b -> Team Select}, {1 -> our record}, {0}`` -- Team Select stays on the retail button."""

    return struct.pack("<5I", EVENT_TEAM_SELECT, SCRIM_TEAM_SELECT_RECORD_VA,
                       EVENT_ENTER, CAVE_ENTER_RECORD_VA, 0)


def enter_record() -> bytes:
    """A kind-3 hook record: the dispatcher calls ``+0x0c`` and stops on the zero kind at ``+0x24``."""

    rec = bytearray(ENTER_RECORD_SIZE)
    struct.pack_into("<I", rec, 0x00, HOOK_KIND_SLOT_C)
    struct.pack_into("<I", rec, 0x0C, ENTER_STUB_VA)
    return bytes(rec)


def cave_bytes() -> bytes:
    """Hook lists, the event record, the cloned descriptor and the code, int3-padded to 352 bytes."""

    body = bytearray(b"\xcc" * CAVE_SIZE)
    body[HOOKS_OFFSET: HOOKS_OFFSET + HOOKS_SIZE] = cave_hooks()
    body[SCRIM_HOOKS_OFFSET: SCRIM_HOOKS_OFFSET + SCRIM_HOOKS_SIZE] = clone_hooks()
    body[ENTER_RECORD_OFFSET: ENTER_RECORD_OFFSET + ENTER_RECORD_SIZE] = enter_record()
    body[DESCRIPTOR_OFFSET: DESCRIPTOR_OFFSET + SCRIM_DESCRIPTOR_SIZE] = clone_descriptor()
    body[CODE_OFFSET: CODE_OFFSET + CODE_SIZE] = CODE
    _require(len(body) == CAVE_SIZE, "cave layout error")
    return bytes(body)


def sites() -> list[tuple[str, int, bytes, bytes]]:
    """``(label, va, retail bytes, patched bytes)`` for every edited span."""

    return [
        ("coach_desk_hook_pointer", COACH_DESK_HOOKS_PTR_VA,
         struct.pack("<I", COACH_DESK_HOOKS_VA), struct.pack("<I", CAVE_HOOKS_VA)),
        ("coach_desk_row_pointer", COACH_DESK_ROWS_PTR_VA,
         struct.pack("<I", COACH_DESK_ROWS_VA), struct.pack("<I", NEW_ROW_VA)),
        ("coach_desk_practice_row", FREED_SPAN_VA, RETAIL_FREED_SPAN + RETAIL_SCHEDULE_ROWS,
         bytes(4) + RETAIL_SCHEDULE_ROWS + practice_row()),
        ("franchise_practice_cave", CAVE_VA, RETAIL_CAVE, cave_bytes()),
    ]


RETAIL_TERMINATOR_ROW = struct.pack("<I", ROW_TYPE_TERMINATOR) + bytes(ROW_SIZE - 4)

# Context that must be retail on any image we touch: the parts of the Coach's Desk descriptor we do
# NOT change, the retail rows around the new one, the screen we clone, every routine the cave calls,
# the label string, and the dead routine after the cave.  Deliberately excludes every byte any other
# studio patch edits (notably the 7-on-7 sites in FUN_000e33f0 from 0xe33ff on), so application
# order does not matter.
PINS: tuple[tuple[int, bytes], ...] = (
    (COACH_DESK_DESCRIPTOR_VA, bytes.fromhex("48a8e900")),                    # title L"Coach's Desk"
    (COACH_DESK_DESCRIPTOR_VA + 0x08, bytes.fromhex("903e0f0000000000")),     # handler cb_000f3e90
    (COACH_DESK_DESCRIPTOR_VA + 0x14,
     bytes.fromhex("0000000064a8e900a8f1ac004400400252008d010700000000000000")),
    (COACH_DESK_ROWS_VA + 10 * ROW_SIZE, bytes.fromhex("090000003ca8e900")),  # retail row 10, Quit
    (TERMINATOR_VA, RETAIL_TERMINATOR_ROW),
    (PRACTICE_LABEL_VA, PRACTICE_LABEL.encode("utf-16le") + b"\0\0"),
    (SCRIM_DESCRIPTOR_VA, RETAIL_SCRIM_DESCRIPTOR),
    (SCRIM_TEAM_SELECT_RECORD_VA, RETAIL_TEAM_SELECT_RECORD_HEAD),
    (START_HANDLER_VA, RETAIL_START_HANDLER),
    (PRACTICE_DEFAULTS_VA, RETAIL_PRACTICE_DEFAULTS_HEAD),
    (COACHED_TEAM_VA, RETAIL_COACHED_TEAM),
    (SET_TEAM_A_VA, RETAIL_SET_TEAM_A),
    (SET_TEAM_B_VA, RETAIL_SET_TEAM_B),
    (PRACTICE_TYPE_APPLY_VA, RETAIL_PRACTICE_TYPE_APPLY_HEAD),
    (SCREEN_POP_VA, RETAIL_SCREEN_POP_HEAD),
    (GAME_START_VA, RETAIL_GAME_START_HEAD),
    (FADE_VA, RETAIL_FADE_HEAD),
    (NEXT_ROUTINE_VA, RETAIL_NEXT_ROUTINE),
)


def _pins_are_retail(payload: bytes) -> bool:
    for va, expected in PINS:
        try:
            off = rdata.offset_of(payload, va)
        except (rdata.RdataSiteError, ValueError, struct.error):
            return False
        if payload[off: off + len(expected)] != expected:
            return False
    return True


def status(payload: bytes) -> str:
    """``retail``, ``applied`` or ``foreign`` (bytes match neither; refuse to touch)."""

    if not _pins_are_retail(payload):
        return "foreign"
    return rdata.status(payload, sites())


def _read_utf16(payload: bytes, va: int) -> str:
    if not va:
        return ""
    try:
        off = rdata.offset_of(payload, va)
    except (rdata.RdataSiteError, ValueError, struct.error):
        return ""
    out = []
    for i in range(off, min(off + 256, len(payload) - 1), 2):
        unit = payload[i] | (payload[i + 1] << 8)
        if unit == 0:
            break
        out.append(chr(unit))
    return "".join(out)


def read_rows(payload: bytes) -> list[dict[str, object]]:
    """Walk the Coach's Desk row table the way the game does: 0x34 strides until a type-3 row."""

    try:
        table = struct.unpack_from("<I", payload, rdata.offset_of(payload, COACH_DESK_ROWS_PTR_VA))[0]
    except (rdata.RdataSiteError, ValueError, struct.error) as exc:
        raise FranchisePracticeError(f"cannot read the Coach's Desk row pointer: {exc}") from exc
    rows: list[dict[str, object]] = []
    va = table
    while len(rows) <= 64:
        try:
            off = rdata.offset_of(payload, va)
        except (rdata.RdataSiteError, ValueError, struct.error) as exc:
            raise FranchisePracticeError(f"row 0x{va:x} is in no section: {exc}") from exc
        fields = struct.unpack_from("<13I", payload, off)
        rows.append({"va": f"0x{va:x}", "type": fields[0], "label_va": f"0x{fields[1]:x}",
                     "label": _read_utf16(payload, fields[1]),
                     "activate": f"0x{fields[10]:x}", "visibility": f"0x{fields[11]:x}"})
        if fields[0] == ROW_TYPE_TERMINATOR:
            return rows
        va += ROW_SIZE
    raise FranchisePracticeError("the Coach's Desk row table has no type-3 terminator")


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Return the patched XBE bytes plus a receipt; refuses anything but retail sites.

    An already-applied image is returned unchanged with ``already_applied``.
    """

    if not _pins_are_retail(payload):
        raise FranchisePracticeError(
            "the Coach's Desk, the Scrimmage Settings screen, the L\"Practice\" string or a routine "
            "the cave calls is not retail; refusing")
    try:
        patched, receipt = rdata.apply(payload, sites(), "Franchise-practice")
    except rdata.RdataSiteError as exc:
        raise FranchisePracticeError(str(exc)) from exc
    if not receipt.get("already_applied"):
        _require(status(patched) == "applied", "post-apply verification failed")
    return patched, {**receipt, **code_report()}


def code_report() -> dict[str, object]:
    return {
        "cave_va": f"0x{CAVE_VA:x}", "cave_end_va": f"0x{CAVE_END_VA:x}", "cave_size": CAVE_SIZE,
        "cave_code_bytes": CODE_SIZE, "cave_code_capacity": CAVE_SIZE - CODE_OFFSET,
        "cave_labels": {name: f"0x{va:x}" for name, va in CODE_LABELS.items()},
        "tables": {"coach_desk_hooks": f"0x{CAVE_HOOKS_VA:x}",
                   "clone_hooks": f"0x{CAVE_SCRIM_HOOKS_VA:x}",
                   "enter_record": f"0x{CAVE_ENTER_RECORD_VA:x}",
                   "clone_descriptor": f"0x{CAVE_DESCRIPTOR_VA:x}"},
        "row_va": f"0x{PRACTICE_ROW_VA:x}", "row_label": PRACTICE_LABEL,
        "row_label_va": f"0x{PRACTICE_LABEL_VA:x}", "row_position": "second, after the visible Schedule",
        "practice_squad_screen": False,
        "practice_type": PRACTICE_TYPE_FULL_SCRIMMAGE,
        "teams": {"away_setter": f"0x{SET_TEAM_A_VA:x}", "home_setter": f"0x{SET_TEAM_B_VA:x}",
                  "source": f"FUN_000c4d70 ([0x{CONTROLLED_TEAMS_VA:x}] -> FUN_000c4c50)"},
        "pops_on_start": 1,
        "retail_instruction_bytes_changed": 0,
        "runtime_verified": False,
    }


__all__ = ["DESCRIPTOR_OFFSET", "ENTER_RECORD_OFFSET", "ENTER_RECORD_SIZE", "EVENT_ENTER",
           "EVENT_TEAM_SELECT", "FADE_IN", "FADE_OUT", "GAME_PENDING_OFFSET", "HOOKS_OFFSET",
           "HOOKS_SIZE", "HOOK_KIND_SLOT_C", "MANAGER_STATE_OFFSET", "RETAIL_NEXT_ROUTINE",
           "RETAIL_ROW_COUNT", "RETAIL_TEAM_SELECT_RECORD_HEAD", "SCRIM_DESCRIPTOR_SIZE",
           "SCRIM_HOOKS_OFFSET", "SCRIM_HOOKS_SIZE", "SCRIM_ENTER_RECORD_VA",
           "CAVE_DESCRIPTOR_VA", "CAVE_END_VA", "CAVE_ENTER_RECORD_VA", "CAVE_HOOKS_VA",
           "CAVE_SCRIM_HOOKS_VA", "CAVE_SIZE", "CAVE_VA", "CODE", "CODE_LABELS", "CODE_OFFSET",
           "CODE_SIZE", "CODE_VA", "COACHED_TEAM_VA", "COACH_DESK_DESCRIPTOR_VA",
           "COACH_DESK_HOOKS_PTR_VA", "COACH_DESK_HOOKS_VA", "COACH_DESK_ROWS_PTR_VA",
           "COACH_DESK_ROWS_VA", "CONTROLLED_TEAMS_VA", "ENTER_STUB_VA", "FADE_VA",
           "FREED_SPAN_SIZE", "FREED_SPAN_VA", "FranchisePracticeError", "GAME_START_VA",
           "MODE_VA", "NEW_ROW_VA", "PRACTICE_ROW_VA", "RETAIL_SCHEDULE_ROWS", "SCHEDULE_ROW_COUNT",
           "NEXT_ROUTINE_VA", "NEXT_SCREEN_VA", "PINS", "PRACTICE_DEFAULTS_VA",
           "PRACTICE_LABEL", "PRACTICE_LABEL_VA", "PRACTICE_TYPE_APPLY_VA",
           "PRACTICE_TYPE_FULL_SCRIMMAGE", "PRACTICE_TYPE_VA", "RETAIL_CAVE", "RETAIL_COACH_DESK_HOOKS",
           "RETAIL_FREED_SPAN", "RETAIL_SCRIM_DESCRIPTOR", "RETAIL_START_HANDLER",
           "RETAIL_TERMINATOR_ROW", "ROW_CALLBACK_VA", "ROW_SIZE", "ROW_TYPE_ACTION",
           "ROW_TYPE_TERMINATOR", "SCREEN_POP_VA", "SCRIM_DESCRIPTOR_VA", "SCRIM_HOOKS_VA",
           "SCRIM_TEAM_SELECT_RECORD_VA", "SET_TEAM_A_VA", "SET_TEAM_B_VA", "START_HANDLER_VA",
           "START_STUB_VA", "TEAM_A_VA", "TEAM_B_VA", "TERMINATOR_VA", "apply", "cave_bytes",
           "CAVE_HOOK_ORDER", "HOOK_PAIRS", "cave_hooks",
           "clone_descriptor", "clone_hooks", "code_report", "enter_record", "practice_row",
           "read_rows", "sites", "status"]

"""Franchise draft on a broadcast clock, USA retail (b778 dr1).

Noah (10/22): "could you slow down the draft? ... it goes super fast straight to your pick. It should be more like every
team takes about a minute to make a pick, and there should be an option to click like advance to next pick or advance
to next user pick ... Perhaps there should also be an option to simulate your pick".

How retail runs the franchise draft screen ("NFL Draft", menu 0x537E38; static disassembly of the USA executable,
Unicorn runs of the native draft code on a real mid-draft franchise save, and headless runs of the released disc):

- The screen's frame handler 0x326C50 formats the on-the-clock timer ``[0xE3C0AC]`` (float seconds) as ``m:ss`` (the
  clock left of the bottom ticker) and, once the camera intro has played, calls the draft step 0x326980.
- 0x326980 first runs the clock 0x326490: the clock loses the frame time ``[menu+0x104]``; crossing 30.5 s shows "You
  Have 30 Seconds To Choose A Player"; below zero it shows "A Player Has Been Drafted For You" and makes the pick
  (0x325B90 pick, 0x325A50 next pick, 0x324ED0 board refresh). Every pick resets the clock to 210.5 s (0x325A20).
- Then, unless the draft is over (0x325D00: seven rounds or no players left, which ends the screen through 0x326530),
  it loops: while a CPU club is on the clock it picks AT ONCE (same three calls), so every CPU pick before the user's
  happens in one frame. When a user club comes on the clock after such picks it refreshes the PDA's recommended
  players (0x326600: 0x325D30 asks the CPU pick logic for six, then the board widgets). START is the native "CPU
  Complete Draft?" (``[0xC94480] = 1``: every pick, the user's included, becomes a CPU pick).
- Native buttons on the screen: A drafts the highlighted player (user on the clock), B leaves (mid-draft is kept),
  START is CPU Complete Draft, the triggers and Black / White page the board lists, the d-pad moves in the lists,
  the right stick turns to the other boards. Y (menu event 0x0D) and X (the generic help pop-up, empty here) do
  nothing on this screen.
- So the clock only ever runs for the user. The round, pick and clock are saved with the franchise (front-office
  block +0x700..+0x706, 0x2D0CE0), so a draft can be left, saved and resumed mid-draft.

This owner replaces the one call of the draft step (``call 0x326980`` at 0x326DBC, inside the frame handler) with a
call to a small cave, and the screen's draw handler pointer (0x537D34, 0x326250) with a cave routine that runs the
retail draw and then one line of help text. Nothing else in the executable changes; no state bytes: the cave keeps
all of its state in the game's own clock.

- CPU club on the clock: the clock is held to at most 60 s and runs down on the game's own timer, like the user's; at
  zero the cave makes that one pick with the same three native calls as retail (the ticker and the Draft Order
  Summary board show it). When the next club is a user club, the cave enters the retail step with its "picks were
  made" flag set, so the PDA recommendations refresh and a full roster still skips, exactly as retail does after its
  CPU loop.
- Y, CPU on the clock: Advance to Next Pick (the clock goes to zero: that pick is made now).
- X, CPU on the clock: Advance to Next User Pick (the clock is set back to its retail 210.5 s and the retail step runs:
  retail's instant CPU loop up to the user's next pick, or to the end of the draft).
- Y, user on the clock: Simulate My Pick (the clock goes to zero, so the retail clock does what it does when time runs
  out: "A Player Has Been Drafted For You" and the CPU pick logic chooses for the user). Ignored for the first 1.5 s
  of his clock, so a Y meant for the pick before cannot spend his pick.
- User on the clock: otherwise retail (3:30 clock, 30-second warning, PDA, boards), except that when his clock runs out
  the CPU clubs after him keep their 60 s each instead of all picking at once.
- The help line under the ticker names the buttons that act at that moment.
- CPU Complete Draft, the end of the draft, and every other screen are retail. The draft order, trades, the CPU pick
  logic (``nfl2k5_draft_ai``), the PDA's recommendations, signing and saves are not touched. MyCareer's draft has its
  own screen (``m3_draft_tick``) and the Fantasy Draft its own code (0x36Fxxx): both unchanged.
"""
from __future__ import annotations

import hashlib
import struct

OWNER = "nfl2k5_draft_clock"
CODE_SIZE = 608
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
BUILD_CAPTION = "Franchise draft: 60-second CPU picks (Y Next Pick / Sim My Pick, X Next User Pick)"
HELP_TEXT = ("The franchise draft no longer jumps straight to your pick: each CPU team is on the clock for 60 seconds "
             "(the game's own draft clock counts down) before it picks. While a CPU team is on the clock: Y = Advance "
             "to Next Pick, X = Advance to Next User Pick (the retail fast draft up to your next pick). While you are "
             "on the clock: Y = Simulate My Pick (the CPU picks for you). A line under the ticker shows the buttons. "
             "Your own clock, the PDA's recommended players, the boards, trades, CPU Complete Draft (START), the "
             "draft order and saves are unchanged.")

CPU_SECONDS = 60.0
RETAIL_CLOCK = 210.5                               # 0x325A20: every pick resets the clock to this
SIMULATE_AFTER = 209.0                             # Y simulates the user's pick only once his clock is below this
BUTTON_Y, BUTTON_X = 0x0800, 0x0400
BUTTONS = BUTTON_Y | BUTTON_X
CPU_TEXT = "Y  Advance to Next Pick      X  Advance to Next User Pick"
USER_TEXT = "Y  Simulate My Pick"
TEXT_X, TEXT_Y = 320.0, 456.0                      # centred, under the clock and ticker line

CLOCK, ROUND, AUTO = 0xE3C0AC, 0xE3C0A8, 0xC94480  # on-the-clock seconds (float), round 0..6, CPU Complete Draft
FRAME_TIME = 0x104                                 # [menu + 0x104]: this frame's seconds (float)
DRAFT_STEP = 0x00326980                            # retail draft step (clock, end check, CPU loop)
DRAFT_STEP_BODY = 0x00326986                       # after its push esi / push edi / mov esi, ecx / xor edi, edi
CLOCK_STEP = 0x00326490                            # retail clock (warning, time-out pick); uses esi = menu
PLAYERS_LEFT = 0x0031DD50                          # nonzero while undrafted players remain
ON_CLOCK = 0x003254D0                              # club record on the clock
HUMAN = 0x000C4D50                                 # nonzero for a user-controlled club (ecx = club)
PICK, NEXT_PICK, REFRESH = 0x00325B90, 0x00325A50, 0x00324ED0
PAD_ON, PAD_PRESSED, PAD_CONSUME = 0x000709B0, 0x00070A10, 0x00070A50
DRAW = 0x00326250                                  # the screen's retail draw handler (event 7)
TEXT = 0x0006BC30                                  # retail text draw (string, 0, x, y, 20, 240, 0, 0, font, colour)
FONT = 0x00A90ECC                                  # the menu font
HOOK = ("draft_step", 0x00326DBC, b"\xe8" + struct.pack("<i", DRAFT_STEP - 0x00326DBC - 5))
DRAW_SLOT = ("draft_draw", 0x00537D34, struct.pack("<I", DRAW))
GUARDS = (
    (0x00326980, 0x58, "4ca504820dff4e04f7e08b0ea7257f84e78e14dfd2a999fbf6bec99e6726d06d"),  # draft step to its user branch
    (0x00326490, 0x9D, "9fcb7957d94292839df32ec0aa71ac2da2e285129f14a96c0b4b994522604557"),  # retail clock
    (0x00325A20, 0x0B, "5c89680fc8141b24119f8504e399a27b49cfa942e1735d16ab054814ecb9a00b"),  # clock reset to 210.5
    (0x003254D0, 0x1B, "524ca478d36f9749995faf6b1321090a2bf6a8d9ed54e5051ac7b7902e2b3feb"),  # club on the clock
    (0x000709B0, 0x14, "5fc1b7b5070fa6b814a05291e0df39a5f4cd440da398de2402a21be8c2664582"),  # pad present
    (0x00070A10, 0x14, "05b42dd137ed22f8c377a2477079462a049450ed314b08fafc53ae8689c6c0f1"),  # pad pressed
    (0x00070A50, 0x46, "31c5450ffdb85461b2ebea6c0511c67ebe6cbcee1f15582b2c9d3dd2f08f349b"),  # pad consume
    (0x00537D00, 0x34, "5c58057db81af26d51df6d13ee636002801b6adeeaa2a1bfad49ed2410d6e31d"),  # draw slot's record
    (0x00326250, 0x182, "4be03d6b121fb7bf84c144e03f0360756e439815f3d93890d7f635fd9128f216"), # retail draw
    (0x0006BC30, 0x20, "020ed2adacd2ae57c02e7e76ab6b3b78e745df54e16226585ec7d2c2aed5b662"),  # text draw entry
)
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError, OSError)


class DraftClockError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise DraftClockError(message)


def _f(value):
    return struct.pack("<f", value).hex()


def _d(value):
    return struct.pack("<I", value).hex()


def code_for(code_va):
    """The cave bytes (CODE_SIZE) for an allocation at ``code_va``."""
    return _build(code_va)[0]


def draw_entry(code_va):
    """The cave's draw handler (the new draw slot value)."""
    return code_va + _build(code_va)[1]["draw"]


def _build(code_va, pad=None):
    """The cave: ``tick`` (at +0, called with ecx = the draft menu, as 0x326980), ``draw`` (the draw handler),
    ``turn``, ``buttons`` and the two UTF-16 help lines."""
    from .nfl2k5_draft_ai import _Asm
    a = _Asm(code_va)
    clock = _d(CLOCK)
    # ---- tick (ecx = menu, as the retail step it replaces; preserves esi, edi, ebx, ebp)
    a.b("56")                                          # push esi
    a.b("8bf1")                                        # mov esi, ecx (menu)
    a.b("833d" + _d(AUTO) + "00")                      # cmp dword [CPU Complete Draft], 0
    a.j8("75", "retail")                               # on: retail (every pick a CPU pick)
    a.j32("e8", "turn")                                # eax = -1 draft over, 0 CPU club on the clock, 1 user club
    a.b("85c0")
    a.j8("7c", "retail")                               # over: retail ends the draft
    a.j8("74", "cpu")
    a.j32("e9", "human")
    a.label("retail")
    a.b("8bce")                                        # mov ecx, esi
    a.b("5e")                                          # pop esi
    a.jmp_abs(DRAFT_STEP)
    # CPU club on the clock
    a.label("cpu")
    a.j32("e8", "buttons")
    a.b("a9" + _d(BUTTON_X))                           # test eax, X
    a.j8("74", "cpu_next")
    a.b("c705" + clock + _f(RETAIL_CLOCK))             # clock = 210.5 (no retail 30-second notice this frame)
    a.j8("eb", "retail")                               # retail: its instant CPU picks up to the user's next pick
    a.label("cpu_next")
    a.b("a9" + _d(BUTTON_Y))                           # test eax, Y
    a.j8("74", "cpu_clamp")
    a.b("c705" + clock + "00000000")                   # clock = 0: pick now
    a.label("cpu_clamp")
    a.b("813d" + clock + _f(CPU_SECONDS))              # cmp dword [clock], 60.0 (positive floats order as ints)
    a.j8("7e", "cpu_run")
    a.b("c705" + clock + _f(CPU_SECONDS))              # clock = 60.0 (a loaded save, a fresh pick)
    a.label("cpu_run")
    a.b("d905" + clock)                                # fld dword [clock]
    a.b("d8a6" + _d(FRAME_TIME))                       # fsub dword [esi + 0x104]
    a.b("d91d" + clock)                                # fstp dword [clock]
    a.b("813d" + clock + "00000080")                   # cmp dword [clock], 0x80000000
    a.j8("76", "done")                                 # not below zero (-0.0 is not, as in retail)
    a.b("8bce")                                        # mov ecx, esi
    a.call(PICK)                                       # the retail CPU loop body: pick, next pick, board refresh
    a.call(NEXT_PICK)
    a.call(REFRESH)
    a.label("post")
    a.j32("e8", "turn")
    a.b("85c0")
    a.j8("7c", "done")                                 # over: the next frame's retail step ends the draft
    a.j8("74", "next_cpu")                             # a CPU club is next: its 60 s show at once
    # A user club is next: the retail step with "picks were made" set (PDA refresh, full-roster skip).
    a.b("8bce")                                        # mov ecx, esi
    a.b("5e")                                          # pop esi
    a.b("56" "57" "8bf1")                              # push esi; push edi; mov esi, ecx (as 0x326980 begins)
    a.b("bf01000000")                                  # mov edi, 1
    a.jmp_abs(DRAFT_STEP_BODY)
    a.label("human")
    a.j32("e8", "buttons")
    a.b("a9" + _d(BUTTON_Y))                           # test eax, Y
    a.j8("74", "human_run")
    a.b("813d" + clock + _f(SIMULATE_AFTER))           # cmp dword [clock], 209.0: his clock has just started
    a.j8("7d", "human_run")                            # ignore (a Y meant for the pick before)
    a.b("c705" + clock + "00000000")                   # clock = 0: the retail time-out pick
    a.label("human_run")
    a.b("51")                                          # push ecx (scratch slot)
    a.b("d905" + clock)                                # fld dword [clock]
    a.b("d8a6" + _d(FRAME_TIME))                       # fsub dword [esi + 0x104]
    a.b("d91c24")                                      # fstp dword [esp]  (the float the retail clock stores)
    a.b("58")                                          # pop eax
    a.b("3d00000080")                                  # cmp eax, 0x80000000
    a.j32("0f86", "retail")                            # no time-out this frame: the retail step, as before
    a.call(CLOCK_STEP)                                 # retail clock: notice + the CPU pick logic picks for him
    a.j8("eb", "post")
    a.label("next_cpu")
    a.b("c705" + clock + _f(CPU_SECONDS))              # clock = 60.0 for the CPU club now on the clock
    a.label("done")
    a.b("5e" "c3")                                     # pop esi; ret
    # ---- draw (the screen's draw handler): the retail draw, then the help line for this moment
    a.label("draw")
    a.call(DRAW)
    a.b("833d" + _d(AUTO) + "00")                      # CPU Complete Draft: no line
    a.j8("75", "draw_out")
    a.j32("e8", "turn")
    a.b("85c0")
    a.j8("7c", "draw_out")                             # draft over: no line
    a.b("b9")                                          # mov ecx, CPU line
    a.items.append(("abs", "cpu_text"))
    a.j8("74", "draw_text")
    a.b("b9")                                          # mov ecx, user line
    a.items.append(("abs", "user_text"))
    a.label("draw_text")
    a.b("6aff")                                        # push colour 0xFFFFFFFF
    a.b("ff35" + _d(FONT))                             # push dword [menu font]
    a.b("6a00" "6a00")                                 # push 0; push 0
    a.b("68" + _f(240.0) + "68" + _f(20.0))            # push 240.0; push 20.0
    a.b("68" + _f(TEXT_Y) + "68" + _f(TEXT_X))         # push y; push x
    a.b("33d2")                                        # xor edx, edx
    a.call(TEXT)                                       # ret 0x20
    a.label("draw_out")
    a.b("c3")
    # ---- turn: eax = -1 when the draft is over (seven rounds or no player left), else 1 for a user club on the clock
    a.label("turn")
    a.b("833d" + _d(ROUND) + "07")                     # cmp dword [round], 7
    a.j8("7d", "over")
    a.call(PLAYERS_LEFT)
    a.b("85c0")
    a.j8("74", "over")
    a.call(ON_CLOCK)
    a.b("8bc8")                                        # mov ecx, eax
    a.call(HUMAN)
    a.b("f7d8" "1bc0" "f7d8")                          # neg eax; sbb eax, eax; neg eax  (0 or 1)
    a.b("c3")
    a.label("over")
    a.b("83c8ff" "c3")                                 # or eax, -1; ret
    # ---- buttons: eax = this frame's Y / X presses on any controller; they are consumed.
    a.label("buttons")
    a.b("53" "57")                                     # push ebx; push edi
    a.b("33db" "33ff")                                 # xor ebx, ebx; xor edi, edi
    a.label("pad")
    a.b("8bcf" "33d2")                                 # mov ecx, edi; xor edx, edx
    a.call(PAD_ON)
    a.b("85c0")
    a.j8("74", "pad_next")
    a.b("8bcf" "33d2")
    a.call(PAD_PRESSED)
    a.b("25" + _d(BUTTONS))                            # and eax, Y | X
    a.j8("74", "pad_next")
    a.b("0bd8")                                        # or ebx, eax
    a.b("50")                                          # push eax (mask)
    a.b("8bcf" "33d2")
    a.call(PAD_CONSUME)                                # ret 4
    a.label("pad_next")
    a.b("47")                                          # inc edi
    a.b("83ff08")                                      # cmp edi, 8
    a.j8("7c", "pad")
    a.b("8bc3")                                        # mov eax, ebx
    a.b("5f" "5b" "c3")
    # ---- the help lines (UTF-16, 2-byte aligned)
    a.label("strings")
    a.b("90" * (pad or 0))                             # keep the UTF-16 text 2-byte aligned
    a.label("cpu_text")
    a.b((CPU_TEXT + "\0").encode("utf-16-le").hex())
    a.label("user_text")
    a.b((USER_TEXT + "\0").encode("utf-16-le").hex())
    if pad is None:
        _assemble(a, code_va, check=False)
        return _build(code_va, (code_va + a.labels["strings"]) % 2)
    body = _assemble(a, code_va)
    require(len(body) <= CODE_SIZE, f"draft clock cave is {len(body)} bytes, more than its {CODE_SIZE}")
    return bytes(body).ljust(CODE_SIZE, b"\xcc"), dict(a.labels)


def _assemble(a, code_va, check=True):
    """``_Asm.assemble`` plus ("abs", label) items: a 4-byte absolute address of a label in this cave."""
    items, a.items = a.items, [b"\0\0\0\0" if isinstance(i, tuple) and i[0] == "abs" else i for i in a.items]
    body = bytearray(a.assemble())
    pos = 0
    for i, item in enumerate(items):
        if isinstance(item, tuple) and item[0] == "abs":
            body[pos:pos + 4] = struct.pack("<I", code_va + a.labels[item[1]])
        pos += a._size(a.items[i])
    a.items = items
    require(not check or (code_va + a.labels["cpu_text"]) % 2 == 0, "help text must be 2-byte aligned")
    return bytes(body)



def sites(code_va=0):
    name, va, before = HOOK
    slot, slot_va, slot_before = DRAW_SLOT
    return [(name, va, before, b"\xe8" + struct.pack("<i", code_va - va - 5)),
            (slot, slot_va, slot_before, struct.pack("<I", draw_entry(code_va) if code_va else 0))]


def allocation(payload):
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    require(len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"]) == ("code", CODE_SIZE, 16),
            "Missing or foreign draft clock allocation")
    return rows[0]


def _recognize(payload):
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    present = space.status(payload) == "applied" and any(
        r["owner"] == OWNER for r in space.layout(payload)["allocations"])
    owned = allocation(payload) if present else None
    edits = sites(owned["va"] if owned else 0)
    states = set()
    for _name, va, before, after in edits:
        raw = image.read(va, len(before))
        states.add("retail" if raw == before else "applied" if owned and raw == after else "foreign")
    if owned:
        raw = image.read(owned["va"], CODE_SIZE)
        states.add("retail" if raw == b"\xcc" * CODE_SIZE else "applied" if raw == code_for(owned["va"]) else "foreign")
    require(states in ({"retail"}, {"applied"}), "Foreign or mixed draft clock site/code")
    for va, size, digest in GUARDS:
        require(hashlib.sha256(image.read(va, size)).hexdigest() == digest,
                f"Foreign draft clock prerequisite at {va:#x}")
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
        raise DraftClockError(f"foreign/mixed draft clock input: {exc}") from exc
    common = dict(owner=OWNER, cpu_seconds=CPU_SECONDS, buttons=dict(next_pick="Y", next_user_pick="X",
                  simulate_my_pick="Y"), state_bytes=0)
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    before = payload
    allocation_receipt = {}
    if not any(r["owner"] == OWNER for r in space.layout(payload)["allocations"]):
        if space.status(payload) == "retail":
            payload, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
        else:
            require(space.is_scaleout(payload), "The draft clock needs the scale-out allocator")
            payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
    code_va = allocation(payload)["va"]
    payload, _ = space.install_code(payload, OWNER, code_for(code_va))
    edits = sites(code_va)
    image = XbeImage(payload)
    buf = bytearray(payload)
    for _, va, old, new in edits:
        off = image.offset(va, len(old))
        require(bytes(buf[off:off + len(old)]) == old, f"draft clock site {va:#x} is not retail")
        buf[off:off + len(old)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(_recognize(result) == "applied" and space.status(result) == "applied", "draft clock postcondition failed")
    return result, dict(common, status="applied", code_va=hex(code_va),
                        before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=space.count_differing_bytes(before, result), file_growth=len(result) - len(before),
                        allocation=allocation_receipt,
                        edits=[dict(label=name, va=hex(va), before=old.hex(), after=new.hex()) for name, va, old, new in edits],
                        reservations=[r for r in space.reservations(result) if r["owner"] == OWNER])


__all__ = ["OWNER", "REQUESTS", "CODE_SIZE", "HOOK", "GUARDS", "BUILD_CAPTION", "HELP_TEXT", "CPU_SECONDS", "code_for",
           "sites", "allocation", "status", "apply"]

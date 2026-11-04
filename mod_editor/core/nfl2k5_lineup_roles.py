"""Situational lineup roles: the third-down back on obvious passing downs, and the fullback fallback (b780 sub1).
EXPERIMENTAL / UNWITNESSED in a played game; proved with the game's own lineup code under Unicorn.

Noah (11/03): "If I make someone a third down back, they shouldn't be in every single play. The starting halfback
should have priority." and "Third down back should be for obvious passing situations".

How the game fills a formation. The lineup builder FUN_000E89F0 walks the eleven slots of the formation's personnel
group and asks the picker FUN_000E8790 (call at 0xE8B20) for each slot's (kind, ordinal). The picker reads the
ordinal's depth list (0xE7530), skips a player already placed (0xE7580) or one its gate refuses (the call at 0xE8864,
retail 0xE8340, injured or worn out), then falls back through other kinds (19 tiers, table 0x4F5A38).

Rule 1, the third-down back (needs the SPECIAL rows, whose 3DRB row is the running back side order from its second
place: RB ordinal 3, read through the game's own ordinal decoder; one-pool positions pair the RB orders as lists 1 and
15, and apply refuses an executable without that pairing). When the slot asks for the lead back (RB, ordinal 0), the user did not substitute that slot,
the club has the ball ([0xE60280]+0x1C is this lineup's team) and it is an obvious passing down (3rd or 4th down with
5 yards or more to go, or 2nd down with 10 or more: the down at [[0xE602EC]+4], the distance from the game's own
0x207950), the 3DRB is asked first. He plays if he is not already on the field and passes the picker's own gate. On a
CPU-run club ([0xE5775C + club*4] == 0; the MyCareer club counts as CPU) he must also be at least as good a receiver
(catch + route running) as the starter, because the 3DRB row there is shipped data; on a human club the user's pick
is honoured. In every other case, and whenever he cannot play, the native pick runs, so the starter keeps the slot.

Rule 2, the fullback fallback. With no fullback on the roster (thirteen 2026 clubs), the picker's next tier for an FB
slot is the RB list, which retail reads from its end: the deepest back. That tier now reads forward from the second
back (or the picker's own protection bound if it is higher), so RB2 takes the FB spot first; when the formation also
asks for the power back (an RB slot with ordinal 1: goal line, jumbo, heavy I) he is kept for that slot and the next
back goes to fullback; when no back is free, a TE (the next tier) plays fullback. Only a formation on the field (the builder's call at 0xE8B20) gets this order: the scheduled simulator's own lineup
(0x102472..) keeps retail's, so its calibrated carry lottery is unchanged (HUNT1, DB2). Every other fallback keeps the
retail order.

Rule 3, the gadget player (needs the SPECIAL rows, whose GAD row is the WR side order from its fourth place: WR
ordinal 7). The lineup builder is handed the called play (its second argument, from 0x18AD10 via 0x18A5D0). When a WR
slot of an offensive play takes a handoff in that play (the planner's own test: a 0x13 handoff node names the slot
and the slot's chain has a 0x16 node), the GAD row is asked first for that slot. He plays if he is not already on the
field and passes the picker's gate. A human club's pick is honoured. On a CPU-run club he must be at least as fast as
the slot's own pick (the native picker with the same arguments), because the GAD row there is shipped data. Every
other play keeps its receivers: the planner no longer writes a gadget ordinal into shared personnel groups (Q61).

Two sites, both 5-byte calls: the builder's call to the picker (0xE8B20) and the picker's list-length call at the top
of each tier (0xE87E9), outside the picker span the scheduled-sim tackle owner pins (0xE87F0..0xE8900, whose gate
calls it hooks). One late allocator owner holds the code. Settings: ``third_down``
(rule 1, on when the SPECIAL rows are on) is a byte in the code; rule 2 is always present.
"""
from __future__ import annotations

import hashlib
import struct
from typing import Mapping

from .nfl2k5_draft_ai import _Asm

OWNER = "nfl2k5_lineup_roles"
CODE_SIZE = 1024
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
BUILD_CAPTION = "Third-down back on passing downs, gadget player on gadget plays; RB2 fills a missing fullback (experimental)"
HELP_TEXT = ("EXPERIMENTAL. Your SPECIAL 3DRB comes in for the starting running back on obvious passing downs (3rd or 4th "
             "down with 5 yards or more to go, 2nd down with 10 or more) when he can play; the starter keeps every other "
             "snap. Your SPECIAL GAD comes in only on a play that hands the ball to a receiver (a reverse or an end "
             "around), at that receiver's spot. A CPU club uses its 3DRB only when he is at least as good a receiver as "
             "its starter, and its GAD only when he is at least as fast as the receiver he replaces. A club with no "
             "fullback now puts its second running back at fullback instead of its deepest one.")

PICKER = 0x000E8790
PICK_CALL = 0x000E8B20                      # in the lineup builder: call 0xE8790
FB_SITE = 0x000E87E9                        # the picker's list-length call at the top of each tier
FB_RETAIL = bytes.fromhex("e8b2edffff")     # call 0xE75A0
BOUND = 0x000E7640                          # the picker's protection bound for a fallback tier (called at 0xE88A2)
NEXT_TIER, PICKER_TAKE = 0x000E890A, 0x000E89AB   # next tier, success exit
GATE_CALL = 0x000E8864                      # the forward loop's gate call (a later owner may point it at its own guard)
LIST_LENGTH, LIST_READ, ALREADY_PLACED, ORDINAL = 0x000E75A0, 0x000E7810, 0x000E7580, 0x000E7530
SITUATION, OFFENSE, HUMAN, ROSTER_ROOT = 0x00E602EC, 0x00E60280, 0x00E5775C, 0x00B72918
TO_GO = 0x00207950
RB_KIND, FB_KIND, RB_RANK_LIST = 10, 11, 1
LIST_TABLE = 0x004F5930                     # (rank list, side list) per kind; one-pool positions pair RB as (1, 15)
YARD = 91.44
FIVE_YARDS, TEN_YARDS = 5 * YARD, 10 * YARD
CATCH, ROUTE, SPEED = 0x44, 0x3F, 0x36       # player record rating bytes
TEAM_SIZE = 0x1F4

# Pinned code the owner relies on (sha256 over the span; the gate call's rel32 is masked: another owner may own it).
GUARDS = (
    (0x000E8790, 0x260, "picker"),
    (0x000E89F0, 0x150, "lineup builder"),
    (0x000E7530, 0x34, "ordinal decoder"),
    (0x000E75A0, 0x37, "list length"),
    (0x000E7580, 0x19, "already placed"),
    (0x000E7810, 0x60, "list reader"),
    (0x00207950, 0x5B, "yards to go"),
)
GATE_MASKS = ((0x000E8865, 4), (0x000E88ED, 4))   # the two gate calls' rel32 inside the picker span


class LineupRolesError(ValueError):
    pass


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise LineupRolesError(message)


def _gate_target(payload: bytes) -> int:
    from .nfl2k5_cave_oracle import XbeImage
    raw = XbeImage(payload).read(GATE_CALL, 5)
    _require(raw[0] == 0xE8, "the picker's gate call is not a call")
    return GATE_CALL + 5 + struct.unpack_from("<i", raw, 1)[0]


def assemble(code_va: int, gate: int, *, third_down: bool = True) -> tuple[bytes, dict[str, int]]:
    """The owner's code at ``code_va`` and its label offsets: roles_pick (the builder's picker call) and fb_len (the
    picker's list-length call at the top of each tier). ``gate`` is the picker's own gate (its call at 0xE8864)."""
    a: list = []

    def b(hexs: str) -> None:
        a.append(bytes.fromhex(hexs))

    def j8(op: str, label: str) -> None:
        a.append(("j8", bytes.fromhex(op), label))

    def label(name: str) -> None:
        a.append(("label", name))

    def j32(op: str, label: str) -> None:
        a.append(("j32", bytes.fromhex(op), label))

    # ---------------------------------------------------------------- roles_pick: same arguments as the picker
    label("roles_pick")
    b("837c241809"); j32("0f84", "gad_entry")        # cmp dword [esp+0x18], 9    kind WR: rule 3
    b("837c24180a"); j32("0f85", "to_picker")        # cmp dword [esp+0x18], 10   kind RB
    b("837c241c00"); j32("0f85", "to_picker")        # cmp dword [esp+0x1c], 0    the lead back
    b("837c241400"); j32("0f85", "to_picker")        # cmp dword [esp+0x14], 0    not a user substitution
    b("803d"); a.append(("abs32", "flags")); b("00"); j32("0f84", "to_picker")   # rule 1 installed
    b("60")                                          # pushad: args at [esp+0x24..0x3c], ctx = saved ecx [esp+0x18]
    b("8b6c2418")                                    # mov ebp, [esp+0x18]      ctx
    b("a1" + struct.pack("<I", OFFENSE).hex()); b("85c0"); j32("0f84", "restore")
    b("8b401c" "3b4500"); j32("0f85", "restore")     # the club with the ball is this lineup's team
    a.append(("calllabel", "passing_down")); b("85c0"); j32("0f84", "restore")
    b("83ec04" "b80a000000" "ba03000000" "8bf4"); a.append(("call", ORDINAL))   # 3DRB = RB ordinal 3: list, [esp] row
    b("8bf8" "8bc8" "8bd5"); a.append(("call", LIST_LENGTH))  # edi = list; eax = its length
    b("5a" "3bc2"); j32("0f8e", "restore")           # edx = row; the row exists
    b("8b4c2414" "52" "55" "8bc7"); a.append(("call", LIST_READ))     # the 3DRB
    b("85c0"); j32("0f84", "restore")
    b("8bd8")                                        # ebx = the 3DRB
    b("8b4c2430" "8b74242c" "8bd3"); a.append(("call", ALREADY_PLACED))
    b("85c0"); j8("75", "restore")
    a.append(("calllabel", "is_human")); b("85c0"); j8("75", "gate")   # a human club's pick is honoured
    b("8b4c2414" "6a00" "55" "b801000000"); a.append(("call", LIST_READ))     # the starter: RB rank list row 0
    b("85c0"); j8("74", "gate")
    b("0fb64844" "0fb6503f" "03ca")                  # ecx = starter catch + route
    b("0fb64344" "0fb6533f" "03c2")                  # eax = 3DRB catch + route
    b("3bc1"); j8("7c", "restore")                   # CPU club: the starter is the better receiver, keep him
    label("gate")
    b("6a03" "ff74242c" "ff74242c" "8bcd" "8bd3")    # push 3, slot, a0; ecx = ctx, edx = player
    a.append(("call", gate)); b("85c0"); j8("74", "restore")
    b("895c241c" "61" "c21c00")                      # return the 3DRB (popad restores, eax = him)
    label("restore")
    b("61")
    label("to_picker")
    a.append(("jmpabs", PICKER))                     # the native pick with the same arguments and return address
    # ---------------------------------------------------------------- passing_down: eax = 1 on an obvious passing down
    label("passing_down")
    b("a1" + struct.pack("<I", SITUATION).hex()); b("85c0"); j8("74", "no")
    b("8b4804" "83f902"); j8("7c", "no")             # the down, 2..4
    b("83f904"); j8("7f", "no")
    b("55" "8bec" "83ec30" "83e4f0")                 # aligned scratch for the two rows the distance function copies
    b("894c2420" "8bcc" "8d542410"); a.append(("call", TO_GO))   # st0 = yards to go (game units)
    b("837c242002"); j8("75", "short")
    b("d81d"); a.append(("abs32", "ten")); j8("eb", "decide")
    label("short")
    b("d81d"); a.append(("abs32", "five"))
    label("decide")
    b("dfe0" "8be5" "5d" "f6c405"); j8("75", "no")   # below the line (or unordered): no
    b("b801000000c3")
    label("no")
    b("33c0c3")
    # ---------------------------------------------------------------- is_human: eax != 0 if the club is user-run
    label("is_human")
    b("a1" + struct.pack("<I", ROSTER_ROOT).hex()); b("85c0"); j8("74", "cpu")
    b("8b401c" "8b4d00" "2bc8"); j8("72", "cpu")     # ecx = this team - team table
    b("8bc1" "33d2" "b9f4010000" "f7f1" "85d2"); j8("75", "cpu")
    b("83f820"); j8("73", "cpu")
    b("8b0485" + struct.pack("<I", HUMAN).hex() + "c3")
    label("cpu")
    b("33c0c3")
    # ---------------------------------------------------------------- gad_entry: rule 3, the gadget player
    # The builder's second argument is the called play ([esp+0xa0] here: 0x18AD10 -> 0x18A5D0 -> 0xE89F0). Its slot
    # chains are absolute after loading (0x1915B0 reads [play+0xc+slot*8] + node*8). The planner's own test: this WR
    # slot's chain has a 0x16 node and some slot's 0x13 handoff names this slot (nfl2k5_special_roles._signals).
    label("gad_entry")
    b("837c241400"); j32("0f85", "to_picker")        # a user substitution keeps his man
    b("83bc24a000000000"); j32("0f84", "to_picker")  # no play: the native pick
    b("60" "8b6c2418" "8bb424c0000000")              # pushad; ebp = ctx; esi = the play
    b("8b4604" "c1e806" "a807"); j32("0f85", "gad_restore")   # an offensive play (family 0) only
    b("8b7c2428" "83ff0b"); j32("0f83", "gad_restore")        # edi = this slot
    b("8b4cfe08" "83e10f" "8b54fe0c")                # its node count and nodes
    label("gad_16")
    b("85c9"); j32("0f84", "gad_restore")
    b("803a16"); j8("74", "gad_carrier")             # it takes the ball
    b("83c208" "49"); j8("eb", "gad_16")
    label("gad_carrier")
    b("33db")
    label("gad_slot")
    b("83fb0b"); j32("0f83", "gad_restore")
    b("8b4cde08" "83e10f" "8b54de0c")
    label("gad_13")
    b("85c9"); j8("74", "gad_next")
    b("803a13"); j8("75", "gad_skip")
    b("0fb64204" "83e00f" "3bc7"); j8("74", "gad_gadget")    # a handoff to this slot
    label("gad_skip")
    b("83c208" "49"); j8("eb", "gad_13")
    label("gad_next")
    b("43"); j8("eb", "gad_slot")
    label("gad_gadget")                              # the GAD row: WR ordinal 7 (side row 3)
    b("83ec04" "b809000000" "ba07000000" "8bf4"); a.append(("call", ORDINAL))   # eax = list, [esp] = row
    b("5a" "8b4c2414" "52" "55"); a.append(("call", LIST_READ))
    b("85c0"); j32("0f84", "gad_restore")
    b("8bd8" "8b4c2430" "8b74242c" "8bd3"); a.append(("call", ALREADY_PLACED))
    b("85c0"); j32("0f85", "gad_restore")
    b("6a03" "ff74242c" "ff74242c" "8bcd" "8bd3"); a.append(("call", gate))
    b("85c0"); j32("0f84", "gad_restore")
    a.append(("calllabel", "is_human")); b("85c0"); j8("75", "gad_take")   # a human club's GAD is honoured
    # a CPU club (shipped data): the slot's own pick (the native picker, same arguments) unless the GAD is as fast
    b("8b542414" "8bcd" + "ff74243c" * 7); a.append(("call", PICKER))
    b("85c0"); j8("74", "gad_take")
    b("0fb64836" "0fb65336" "3bd1"); j8("7d", "gad_take")    # speed: GAD >= the slot's own pick
    b("8bd8")
    label("gad_take")
    b("895c241c" "61" "c21c00")
    label("gad_restore")
    b("61"); a.append(("jmpabs", PICKER))
    # ---------------------------------------------------------------- fb_len: the picker's list-length call (each tier)
    # Called from 0xE87E9 (retail: call 0xE75A0) with ecx = the tier's list, edx = ctx, ebx = the tier; picker frame
    # offsets are +4 while our return address (0xE87EE) is on the stack.
    label("fb_len")
    b("85db"); j32("0f84", "fb_native")              # tier 0: the requested kind's own list
    b("83f901"); j32("0f85", "fb_native")            # the RB rank list
    b("817c2428" + struct.pack("<I", PICK_CALL + 5).hex()); j32("0f85", "fb_native")   # a formation on the field only
    b("837c24400b"); j32("0f85", "fb_native")        # requested kind FB
    b("83c404")                                      # drop our return: the picker's own frame from here
    a.append(("call", LIST_LENGTH))                  # eax = the RB list length (ecx, edx unchanged)
    b("8bf0" "8944241c" "33c0" "39442438"); j8("75", "fb_bound")   # end = length; a user substitution: bound 0
    b("6a03" "ff74242c" "6a00" "8bdd" "8bc7"); a.append(("call", BOUND))   # the picker's own bound (as at 0xE8895)
    label("fb_bound")
    b("83f801"); j8("7d", "fb_row")                  # first row: that bound, at least 1 (never the starter)
    b("b801000000")
    label("fb_row")
    b("89442410")                                    # row = [esp+0x10]
    # skip = the power back when this formation also asks for him (an RB slot with ordinal 1, code 0x2A)
    b("33db" "8b44240c" "33c9")                      # ebx = 0; eax = the builder's category (saved ebx); ecx = 0
    label("fb_codes")
    b("807c08052a"); j8("74", "fb_power")            # cmp byte [eax+ecx+5], 0x2a
    b("41" "83f90b"); j8("72", "fb_codes")
    j8("eb", "fb_start")
    label("fb_power")
    b("83ec04" "b80a000000" "ba01000000" "8bf4"); a.append(("call", ORDINAL))   # the power back: RB ordinal 1
    b("5a" "8b4c2420" "52" "57"); a.append(("call", LIST_READ))
    b("8bd8")
    label("fb_start")
    b("53")                                          # push skip (picker frame offsets +4 while it is pushed)
    label("fb_loop")
    b("8b442414" "3b442420"); j8("7d", "fb_none")
    b("8b4c2424" "50" "57" "b801000000"); a.append(("call", LIST_READ))     # player at row
    b("85c0"); j8("74", "fb_next")
    b("3b0424"); j8("74", "fb_next")                 # the power back stays for his own slot
    b("8bd8" "8b4c2438" "8b742434" "8bd3"); a.append(("call", ALREADY_PLACED))
    b("85c0"); j8("75", "fb_next")
    b("8b442430" "8b4c242c" "6a03" "50" "51" "8bcf" "8bd3"); a.append(("call", gate))   # the picker's gate
    b("85c0"); j8("74", "fb_next")
    b("58"); a.append(("jmpabs", PICKER_TAKE))       # drop skip; the picker's success exit returns ebx
    label("fb_next")
    b("ff442414"); j8("eb", "fb_loop")
    label("fb_none")
    b("58"); a.append(("jmpabs", NEXT_TIER))         # nobody: the next tier (a tight end)
    label("fb_native")
    a.append(("jmpabs", LIST_LENGTH))                # every other tier: the native call, returning to 0xE87EE
    # ---------------------------------------------------------------- data
    label("five"); b(struct.pack("<f", FIVE_YARDS).hex())
    label("ten"); b(struct.pack("<f", TEN_YARDS).hex())
    label("flags"); b("01" if third_down else "00")
    return _link(a, code_va)


def _link(items: list, base: int) -> tuple[bytes, dict[str, int]]:
    size = {"j8": 2, "j32": 6, "abs32": 4, "calllabel": 5, "call": 5, "jmpabs": 5, "rel32abs": 4, "label": 0}
    pos, labels = 0, {}
    for item in items:
        if isinstance(item, bytes):
            pos += len(item)
        else:
            if item[0] == "label":
                labels[item[1]] = pos
            pos += size[item[0]]
    out = bytearray()
    for item in items:
        here = len(out)
        if isinstance(item, bytes):
            out += item
            continue
        kind = item[0]
        if kind == "label":
            continue
        if kind == "j8":
            rel = labels[item[2]] - (here + 2)
            _require(-128 <= rel <= 127, f"rel8 out of range for {item[2]}")
            out += item[1] + struct.pack("<b", rel)
        elif kind == "j32":
            out += item[1] + struct.pack("<i", labels[item[2]] - (here + 6))
        elif kind == "abs32":
            out += struct.pack("<I", base + labels[item[1]])
        elif kind == "calllabel":
            out += b"\xe8" + struct.pack("<i", labels[item[1]] - (here + 5))
        elif kind in ("call", "jmpabs"):
            out += (b"\xe8" if kind == "call" else b"\xe9") + struct.pack("<i", item[1] - (base + here + 5))
        elif kind == "rel32abs":
            out += struct.pack("<i", item[1] - (base + here + 4))
    _require(len(out) <= CODE_SIZE, f"lineup roles code ({len(out)} B) exceeds its allocation")
    return bytes(out).ljust(CODE_SIZE, b"\xcc"), labels


def code_for(code_va: int, gate: int, *, third_down: bool = True) -> bytes:
    return assemble(code_va, gate, third_down=third_down)[0]


def sites(code_va: int, gate: int = 0x000E8340) -> tuple[tuple[str, int, bytes, bytes], ...]:
    """(label, va, retail bytes, installed bytes) of the two hooks."""
    entry = assemble(code_va or 0x1000000, gate)[1]
    pick = b"\xe8" + struct.pack("<i", PICKER - PICK_CALL - 5)
    hook = b"\xe8" + struct.pack("<i", code_va + entry["roles_pick"] - PICK_CALL - 5)
    tier = b"\xe8" + struct.pack("<i", code_va + entry["fb_len"] - FB_SITE - 5)
    return (("roles_pick", PICK_CALL, pick, hook), ("fb_len", FB_SITE, FB_RETAIL, tier))


_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError)


def allocation(payload: bytes):
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    _require(len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"]) == ("code", CODE_SIZE, 16),
             "missing or foreign lineup roles allocation")
    return rows[0]


def _guard_digest(payload: bytes, va: int, size: int, edits) -> str:
    from .nfl2k5_cave_oracle import XbeImage
    content = bytearray(XbeImage(payload).read(va, size))
    for _label, at, before, _after in edits:
        if va <= at and at + len(before) <= va + size:
            content[at - va:at - va + len(before)] = before
    for at, width in GATE_MASKS:
        if va <= at and at + width <= va + size:
            content[at - va:at - va + width] = bytes(width)
    return hashlib.sha256(bytes(content)).hexdigest()


def read_settings(payload: bytes) -> dict[str, object]:
    """status (retail | applied | foreign) and third_down (rule 1 installed)."""
    try:
        from . import nfl2k5_xbe_space as space
        from .nfl2k5_cave_oracle import XbeImage
        image = XbeImage(payload)
        gate = _gate_target(payload)
        present = any(r["owner"] == OWNER for r in space.layout(payload)["allocations"])
        code_va = allocation(payload)["va"] if present else 0
        edits = sites(code_va, gate)
        states = set()
        for _label, va, before, after in edits:
            raw = image.read(va, len(before))
            states.add("retail" if raw == before else "applied" if present and raw == after else "foreign")
        third_down = None
        if present:
            raw = image.read(code_va, CODE_SIZE)
            matches = [flag for flag in (True, False) if raw == code_for(code_va, gate, third_down=flag)]
            states.add("applied" if matches else "retail" if raw == b"\xcc" * CODE_SIZE else "foreign")
            third_down = matches[0] if matches else None
        _require(states in ({"retail"}, {"applied"}), "foreign or mixed lineup roles sites")
        for va, size, name in GUARDS:
            _require(_guard_digest(payload, va, size, edits) == PINS[name], f"unknown {name} code at {va:#x}")
        state = next(iter(states))
        return {"status": state, "third_down": third_down if state == "applied" else None}
    except _ERRORS as exc:
        return {"status": "foreign", "reason": str(exc)}


def status(payload: bytes) -> str:
    return str(read_settings(payload)["status"])


def apply(payload: bytes, *, third_down: bool = True) -> tuple[bytes, dict[str, object]]:
    """Install (or replay) the owner. ``third_down`` installs rule 1; the fullback fallback is always present."""
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_bump_strength import _sections, section_digest
    from .nfl2k5_cave_oracle import XbeImage
    settings = read_settings(payload)
    _require(settings["status"] != "foreign", f"lineup roles: foreign input ({settings.get('reason', '')})")
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False, third_down=third_down)
    if settings["status"] == "applied":
        _require(settings["third_down"] == third_down, "lineup roles are installed with other settings; rebuild "
                                                       "from the source executable to change them")
        return payload, dict(common, status="applied", already_applied=True, changed_bytes=0, edits=[])
    rank_list, side_list = struct.unpack("<II", XbeImage(payload).read(LIST_TABLE + RB_KIND * 8, 8))
    _require(rank_list != side_list, "lineup roles need the paired running back orders (one-pool positions)")
    before = payload
    gate = _gate_target(payload)
    if space.status(payload) == "retail":
        payload, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
    else:
        _require(space.is_scaleout(payload), "lineup roles need the scale-out allocator")
        payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
    code_va = allocation(payload)["va"]
    payload, _ = space.install_code(payload, OWNER, code_for(code_va, gate, third_down=third_down))
    edits = sites(code_va, gate)
    image = XbeImage(payload)
    buf = bytearray(payload)
    for _label, va, old, new in edits:
        off = image.offset(va, len(old))
        _require(bytes(buf[off:off + len(old)]) == old, f"lineup roles site {va:#x} is not retail")
        buf[off:off + len(old)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    after = read_settings(result)
    _require(after["status"] == "applied" and after["third_down"] == third_down, "lineup roles postcondition failed")
    return result, dict(common, status="applied", already_applied=False, code_va=hex(code_va), gate=hex(gate),
                        changed_bytes=space.count_differing_bytes(before, result),
                        file_growth=len(result) - len(before), allocation=allocation_receipt,
                        edits=[dict(label=n, va=hex(v), before=o.hex(), after=w.hex()) for n, v, o, w in edits])


# sha256 of each guarded span on the retail executable (the two hooks and the gate calls' rel32 masked)
PINS: dict[str, str] = {
    "picker": "95c073764d2512364047f4c7fe2f54f9ecb78c88e961334bf176691ba7559ab8",
    "lineup builder": "b70d6c7814bdac79b84a33892a6f5e3f228af528859edf6684fb151353854a72",
    "ordinal decoder": "444625bef40176511f5c80956c39f2e1996476e3153c16a893aeb0216e6816ce",
    "list length": "2ac8eea080bb77cfb975f3df15d76c69888167b0256fa7c8cc98b90898a07af1",
    "already placed": "50b623f41418bc9cc5bf49b127e6420b91554e1d4e75701ca4906a7fdd55c2fc",
    "list reader": "da3f9906555709c4b213f23351a4188c3fe7488c2ac6d74aaa44584aec082ccf",
    "yards to go": "d3e699ec5309d41ba7e0cac523a986a92882dff07bb9efa02ecfbb6b12253335",
}

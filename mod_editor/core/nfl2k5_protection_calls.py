"""Protection calls: the user slides his offensive line at the line of scrimmage. EXPERIMENTAL.

Players asked for it (Discord #2k5-ideas: maffy_mafferson 9/05 "A way to slide the protection like in 2K8", THE1WAM
9/22, 7ET 9/23 "LOS Protection Calls ... The QB (User) can then adjust the protection", X_Ray 10/22 "L1 ... R1 ... ain't
doing shit" in the audible menu). Research: b77_session/reports/b780_r3-presnap_RESEARCH.md (P1); build: b780 p1-slide.

What retail does. NFL 2K5 already slides its pass protection by itself. Every tick of the set phase at the line (play
state 0xD; the snap moves it to 0xE, 0xB6F30) and of a live pass play (state 0xE, play kind 5) the block AI 0x23DBE0
calls 0x23BC40 = ``mov [0xC16BAC], 0; call 0x23B5B0;
jmp 0x23B6E0``. 0x23B6E0 counts the defenders in the box on each side of the ball and, with more than three, stores
``(count on the -x side - count on the +x side) * 137.16 cm``, clamped to +-274.32 cm (3 yd), in 0xC16BAC. Every
pass-set point (0x23ABB0 adds it to the set point's world x), the per-tick re-target 0x23D610, 0x23E550, 0x23F450 and
the slide-aware first target pick 0x2FA9C0 (through the getter 0x23A860) read that value. Nothing lets the player
choose it.

What this owner adds (two hooks, 288 bytes of code, a 16-byte RW state block; nothing allocates at run time):

* ``line_button`` replaces the first ten bytes of the at-line case for events 0x37..0x3B in 0x18FBE0 (0x18FE65, the
  human controller path; the event table path 0x18F8C0 carries CPU brain events and is not touched). In the audible
  menu (context 2) L sends 0x3A and R 0x3B. On the offense's own menu with the formation's three audibles (panel record
  0 open, count 3) retail looks up audible 3/4, finds none and closes the menu. Now L sets SLIDE LEFT, R sets SLIDE
  RIGHT, and the same button again clears the call (back to the game's own read); nothing is selected and the menu stays
  open. Every other press, and L/R on the five-play menus (defense, No Huddle, kicks), runs the retail bytes.
* ``snap_slide`` replaces 0x23BC40's tail jump: the retail automatic read runs first, unchanged, then, when the offense
  has a call for this play, 0xC16BAC becomes 274.32 cm toward the called side. The call belongs to the offense team that
  made it and to the play it was made on (the play log counter 0xE53804, which moves when a play ends), holds for every
  tick of that snap, and is dropped when the next play is set at the line. A call left over from a game that was quit before the snap is
  dropped too: the game tick 0xB71D10 restarts at 0 in every game (0x11A540), so the new game's tick is behind the
  call's. CPU offenses never make a call, so they keep the automatic read.

Direction. The set points are world coordinates: 0x1B8960 maps an authored offset with x_world = s * x + ball x, where
s = +1 when the offense attacks +z (the attacked goal z at [[[offense]+8]+0xC]+4 is positive) and -1 otherwise, and
authored +x is the offense's right (nfl2k5_play_codec). So a call to the offense's right is a world slide of
``s * +274.32`` and a call to the left ``s * -274.32``; ``RIGHT_IS_LOCAL_PLUS_X`` holds that sign and ``code_for``
writes the two values (no reassembly). Measured in the emulator (b780 p1-slide report).

State block: +0 offense team, +4 play log counter at the call, +8 call (0 none, 1 left, 2 right), +9 used on a live
snap, +12 game tick at the call. A later owner (the b780 p3 legend) may read it to show the call; it is zero in the
executable file.
"""
from __future__ import annotations

import hashlib
import struct

OWNER = "nfl2k5_protection_calls"
CODE_SIZE = 288
DATA_SIZE = 16
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16))
BUILD_CAPTION = "Protection calls: slide the line with L / R (audible menu)"
HELP_TEXT = ("EXPERIMENTAL. At the line, press Y to open the audible menu as usual, then press L to slide your pass "
             "protection to the left or R to slide it to the right. Press the same button again to go back to the "
             "game's own read. The call is for the next snap only: on a pass play the whole line slides its pass set "
             "3 yards (the game's largest slide) toward the side you called. Run plays are not changed. The "
             "computer's offense keeps the game's automatic slide, and L and R keep their audibles in the defense, "
             "No Huddle and kick menus.")
SYMBOLS = dict(slide_auto=0x0023B6E0, select_play=0x000FEFA0, case_resume=0x0018FE6F, case_done=0x0018FF1C)
SLIDE_CM = 274.32                   # the game's own maximum (retail constants 0x4EDD28 / 0x50A514)
RIGHT_IS_LOCAL_PLUS_X = True        # authored +x is the offense's right; see the module docstring
CALL_NONE, CALL_LEFT, CALL_RIGHT = 0, 1, 2
STATE_TEAM, STATE_PLAY, STATE_CALL, STATE_USED, STATE_TICK = 0, 4, 8, 9, 12
SLIDE_VA = 0x00C16BAC
PLAY_COUNTER_VA = 0x00E53804
GAME_TICK_VA = 0x00B71D10       # frames since the game started (0xAF2C0); 0 at every game start (0x11A540)
OFFENSE_VA = 0x00E60280
PANEL_VA = 0x00BA3178               # two 0x4C-byte audible panel records; +6 = count (3 offense audibles, 5 otherwise)
EVENT_L, EVENT_R = 0x3A, 0x3B       # context 2 (audible menu): L and R (0xA99EC0 + 2 * 0x6C)
HOOKS = (
    # (label, va, retail bytes, entry label)
    ("snap_slide", 0x0023BC4F, bytes.fromhex("e98cfaffff"), "snap_slide"),             # jmp 0x23B6E0
    ("line_button", 0x0018FE65, bytes.fromhex("8d51c98bcee831f1f6ff"), "line_button"),  # lea edx,[ecx-0x37]; mov ecx,esi; call 0xFEFA0
)
GUARDS = (          # (va, size, sha256 of the retail bytes), this owner's own site bytes masked back to retail
    (0x0023BC40, 0x14, "c971866a1c2f6bb82507bb74cfdbb715d501fd588eb281ac559f09d07f632111"),  # 0x23BC40, the per-tick slide call
    (0x0023BC32, 0x09, "7fbbb93cd553dee0aafd8869520a1bc81fdb80ae47e4f0ec343cae1ae63c6f5f"),  # 0x23B6E0 returns with ret 4
    (0x0018FE65, 0x1D, "187260fba82991e21f71cb5444b32d6db45f6d398ccd44ddadd505c2f4712c03"),  # the at-line case 0x37..0x3B
    (0x0018FF1C, 0x0A, "c6f3255e924bce31c553c2b9d5533480195e216bf442f5ef8cb7524ee0e3c871"),  # next controller
    (0x0018FF3C, 0x04, "c6b52bb78b8935621cb135ce00116b726891f091713ad13e86c6e9285e7bb402"),  # switch slot 3 -> 0x18FE65
    (0x0018FF9F, 0x02, "8655173af1ec080de2dae0c6d0a7a2da5ade8b2cf8117645da18b90aaefd0ee2"),  # events 0x3A, 0x3B -> slot 3
)
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError)


class ProtectionCallsError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise ProtectionCallsError(message)


def slide_values():
    """(k_slide[0], k_slide[1]): the world slide for a RIGHT call when the offense attacks +z, and the other one."""
    right = SLIDE_CM if RIGHT_IS_LOCAL_PLUS_X else -SLIDE_CM
    return right, -right


def world_slide(call, attacked_goal_z):
    """The value the owner stores in 0xC16BAC for ``call`` (1 left, 2 right) when the offense's goal z is given."""
    if call not in (CALL_LEFT, CALL_RIGHT):
        raise ValueError(call)
    k0, k1 = slide_values()
    return k0 if (call == CALL_RIGHT) == (attacked_goal_z > 0) else k1


def _rows(payload):
    from . import nfl2k5_xbe_space as space
    if space.status(payload) == "retail":
        return {}
    return {r["kind"]: r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER}


def allocations(payload):
    rows = _rows(payload)
    require(set(rows) == {"code", "data"} and rows["code"]["size"] == CODE_SIZE and rows["data"]["size"] == DATA_SIZE,
            "Missing or foreign protection-call allocations")
    return rows


def code_for(code_va, state_va):
    from . import nfl2k5_protection_calls_code as assembly
    symbols = dict(SYMBOLS, code=code_va, state=state_va)
    out = bytearray(assembly.CODE)
    for off, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", out, off)[0]
        if kind == 2:
            target -= code_va + off
        struct.pack_into("<I", out, off, target & 0xFFFFFFFF)
    k0, k1 = slide_values()
    struct.pack_into("<ff", out, assembly.LABELS["k_slide"], k0, k1)
    require(assembly.LABELS["code_end"] <= CODE_SIZE, "Protection-call code exceeds its RX allocation")
    return bytes(out).ljust(CODE_SIZE, b"\xcc")


def sites(code_va=0):
    from . import nfl2k5_protection_calls_code as assembly
    out = []
    for name, va, before, label in HOOKS:
        jump = b"\xe9" + struct.pack("<i", code_va + assembly.LABELS[label] - va - 5)
        out.append((name, va, before, jump.ljust(len(before), b"\x90")))
    return out


def _check_guards(image, edits):
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for _name, at, before, _after in edits:
            for i, byte in enumerate(before):
                if va <= at + i < va + size:
                    content[at + i - va] = byte
        require(hashlib.sha256(content).hexdigest() == digest, f"Foreign protection-call prerequisite at {va:#x}")


def _recognize(payload):
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    rows = _rows(payload)
    require(not rows or set(rows) == {"code", "data"}, "Partial protection-call allocations")
    owned = allocations(payload) if rows else None
    edits = sites(owned["code"]["va"] if owned else 0)
    states = set()
    for _name, va, before, after in edits:
        raw = image.read(va, len(before))
        states.add("retail" if raw == before else "applied" if owned and raw == after else "foreign")
    if owned:
        code_va, state_va = owned["code"]["va"], owned["data"]["va"]
        raw = image.read(code_va, CODE_SIZE)
        states.add("retail" if raw == b"\xcc" * CODE_SIZE else
                   "applied" if raw == code_for(code_va, state_va) else "foreign")
        require(image.read(state_va, DATA_SIZE) == bytes(DATA_SIZE), "Protection-call state block is not zero")
    require(states in ({"retail"}, {"applied"}), "Foreign or mixed protection-call sites/code")
    _check_guards(image, edits)
    return next(iter(states))


def status(payload):
    try:
        return _recognize(payload)
    except _ERRORS:
        return "foreign"


def read_settings(payload):
    return {"status": status(payload)}


def apply(payload):
    """Install, or replay an identical installation. Retail, or a sealed scale-out image without this owner."""
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_bump_strength import _sections, section_digest
    from .nfl2k5_cave_oracle import XbeImage
    try:
        state = _recognize(payload)
    except _ERRORS as exc:
        raise ProtectionCallsError(f"foreign/mixed protection-call input: {exc}") from exc
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False)
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    before = payload
    allocation_receipt = {}
    if not _rows(payload):
        if space.status(payload) == "retail":
            payload, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
        else:
            require(space.is_scaleout(payload), "Protection calls need the scale-out allocator")
            payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
    rows = allocations(payload)
    code_va, state_va = rows["code"]["va"], rows["data"]["va"]
    payload, _ = space.install_code(payload, OWNER, code_for(code_va, state_va))
    image = XbeImage(payload)
    buf = bytearray(payload)
    edits = sites(code_va)
    for _name, va, old, new in edits:
        off = image.offset(va, len(old))
        require(bytes(buf[off:off + len(old)]) == old, f"Protection-call site {va:#x} is not retail")
        buf[off:off + len(old)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(_recognize(result) == "applied" and space.status(result) == "applied",
            "Protection-call postcondition failed")
    return result, dict(common, status="applied",
                        before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=space.count_differing_bytes(before, result), file_growth=len(result) - len(before),
                        allocation=allocation_receipt, code_va=hex(code_va), state_va=hex(state_va),
                        slide_cm=SLIDE_CM, right_is_local_plus_x=RIGHT_IS_LOCAL_PLUS_X,
                        edits=[dict(label=name, va=hex(va), before=old.hex(), after=new.hex())
                               for name, va, old, new in edits],
                        reservations=[r for r in space.reservations(result) if r["owner"] == OWNER])


def main(argv=None):
    """``python3 -m mod_editor.core.nfl2k5_protection_calls status|apply source.xbe [--output out.xbe]``"""
    import argparse
    import json
    import os
    parser = argparse.ArgumentParser(description="Protection calls (slide the offensive line at the line). EXPERIMENTAL.")
    parser.add_argument("command", choices=("status", "apply"))
    parser.add_argument("source")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    fd = os.open(args.source, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    with os.fdopen(fd, "rb") as stream:
        payload = stream.read()
    if args.command == "status":
        print(json.dumps({"owner": OWNER, "status": status(payload)}))
        return 0
    if not args.output:
        parser.error("apply needs --output")
    result, receipt = apply(payload)
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o644)
    with os.fdopen(fd, "wb") as stream:
        stream.write(result)
    print(json.dumps({k: v for k, v in receipt.items() if k != "reservations"}, indent=1))
    return 0


__all__ = ["OWNER", "REQUESTS", "CODE_SIZE", "DATA_SIZE", "HOOKS", "GUARDS", "SYMBOLS", "SLIDE_CM",
           "RIGHT_IS_LOCAL_PLUS_X", "BUILD_CAPTION", "HELP_TEXT", "apply", "status", "read_settings", "allocations",
           "code_for", "sites", "slide_values", "world_slide", "main"]


if __name__ == "__main__":
    raise SystemExit(main())

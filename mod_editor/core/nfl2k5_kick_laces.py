"""Laces to the posts on field goals and points after (executable patch, xemu-only).

Retail (proved in the retail ``default.xbe``, study of 2026-09-04):

* the ball object (global ``0xE5FC00``: +0x00 holder, +0x14 transform) keeps its orientation as a
  quaternion ``(w, x, y, z)`` at transform +0x20 -- the layout the game's own product ``FUN_003ca150``
  (``ecx`` = out, ``edx`` = a, ``push`` b; ``out.w = a.w*b.w - a.xyz . b.xyz``, Hamilton order, the
  callee pops its argument) reads and writes;
* the ball mesh (pack 0 outer 3 chunk 88, Models key ``o3c88``) has its long axis on model Z and its
  laces on model +Y;
* the kickoff tee is a code constant (``.rdata`` 0x50D9A0, 45 degrees about X in ``FUN_001c9390``) and
  already puts the laces toward the target;
* the **hold** is not a constant: ``FUN_001ccfa0`` samples the holder's animation ball track every
  frame (``FUN_000df450``, packed quaternions in pack data), so which way the laces point during a
  place kick is baked into the hold clip. Its three orientation paths (one clip, a two-clip blend, no
  ball track = hand-bone chain x holder heading) all join at **0x1CD3FB** (``mov edx,[esp+0x14]; mov
  ecx,[edx]``) with ``esi`` = the ball transform.

The patch: the six join-point bytes become ``call cave; nop``. The cave (in the dead
``FUN_002979f0``, 0x2979F0..0x297A7E: no caller, no rel32/rel8 target, no push/mov immediate and
no aligned ``.rdata``/``.data`` pointer lands on any of its bytes) saves every register and the
flags, and only when the play is live (``[0xE602B8] == 0xE``) **and** the offence's chosen formation
is the Field Goal formation (``[[[0xE60280]+0xC]+8]``, the chain ``FUN_0013a0b0`` walks, guarded
against its ``-4`` "no play yet" sentinel; flags bits 8-13 == 12, exactly as ``nfl2k5_kick_rules``
reads it, so PAT and FG qualify while punts, kickoffs and scrimmage carries do not) multiplies the
ball quaternion in place by a 16-byte roll constant kept inside the cave through the game's own
``FUN_003ca150`` (``q <- q x r``: a rotation in the ball's own frame). The default roll is
``(0, 0, 0, 1)``, 180 degrees about the ball's long axis, so ``(w, x, y, z) <- (-z, y, -x, w)``: the
laces swing from the kicker's side to the posts. The general product costs 15 bytes more than a
hard-wired sign flip and shuffle; in exchange the 90-degree variant ``(0.7071, 0, 0, 0.7071)`` is a
data edit of those 16 bytes (``apply(..., roll=ROLL_90)``), for the case where the hold clip has the
laces sideways rather than backwards. The cave then replays the two replaced instructions (``mov
edx,[esp+0x18]``: the return address sits on the stack) and returns. It writes only to the ball
transform through ``esi`` and to the stack; nothing is written into ``.text``.

Cosmetic side effect: a fake field goal carries the rolled ball for that play only. Unwitnessed in
game.
"""

from __future__ import annotations

import math
import struct
from typing import Mapping, Sequence

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest
from .nfl2k5_draft_ai import _Asm

IMAGE_BASE = 0x10000

# --- the hook: the join point of the three held-ball orientation paths in FUN_001ccfa0 ----------
HOOK_VA = 0x001CD3FB
RETAIL_HOOK = bytes.fromhex("8b5424148b0a")            # mov edx,[esp+0x14] ; mov ecx,[edx]
HOOK_SIZE = len(RETAIL_HOOK)
HOOK_BEFORE_VA = 0x001CD3F6                            # call FUN_003ca990 (the no-track path's last step)
RETAIL_HOOK_BEFORE = bytes.fromhex("e895d51f00")
HOOK_AFTER_VA = 0x001CD401                             # test ecx,ecx ; je +0x17
RETAIL_HOOK_AFTER = bytes.fromhex("85c97417")
HOOK_JUMP_SOURCES = (0x001CD350, 0x001CD38F)           # jmp rel32 (two-clip blend), jmp rel8 (single clip)
BALL_QUAT_OFFSET = 0x20                                # transform +0x20: (w, x, y, z)

# --- the game's own routines and globals ----------------------------------------------------------
QUAT_MUL_VA = 0x003CA150                               # FUN_003ca150(ecx = out, edx = a, push b): out = a x b, ret 4
RETAIL_QUAT_MUL_HEAD = bytes.fromhex("8b442404d94204d808d94004d80adec1")
PLAY_STATE_VA = 0x00E602B8                             # dword: 0xE = live play (0x10 pre-snap, 0x12 dead ball)
LIVE_PLAY = 0x0E
POSSESSION_VA = 0x00E60280                             # team with the ball: +0xC play-call state, then +8 formation
NO_PLAY_SENTINEL = -4                                  # FUN_0013a0b0's "no play yet" value of [team+0xC]
FORMATION_FLAGS_OFFSET = 0x04                          # formation record +4: bits 8-13 = formation type
FG_FORMATION_TYPE = 12                                 # the Field Goal formation (PAT and FG alike)

# --- the cave: the dead FUN_002979f0 --------------------------------------------------------------
CAVE_VA = 0x002979F0
CAVE_SIZE = 0x8F                                       # 0x2979F0..0x297A7E: `ret 0xc` ends at 0x297A7E, nop pad, next routine 0x297A80
ROLL_OFFSET = 0x70                                     # the 16-byte roll quaternion, 16-byte aligned (0x297A60)
ROLL_VA = CAVE_VA + ROLL_OFFSET
ROLL_SIZE = 16
CAVE_END_VA = CAVE_VA + CAVE_SIZE
CAVE_PAD_VA = CAVE_END_VA                              # 0x297A7F: one retail nop, left alone
RETAIL_CAVE_PAD = bytes.fromhex("90")
NEXT_ROUTINE_VA = 0x00297A80
RETAIL_NEXT_ROUTINE_HEAD = bytes.fromhex("568bf2e8d8eaffff")
RETAIL_CAVE = bytes.fromhex(
    "5356578bfae866ebffff8bf00faff103f7e85aebffff0fafc18b5424148b7c24108b0da4ceac0003c2c1e60285ff7509"
    "8a940e09020000eb078a940e0a0200008b5c241885db75108a9c810902000088948109020000eb0e8a9c810a02000088"
    "94810a02000085ff7512a1a4ceac005f889c06090200005e5bc20c008b0da4ceac005f889c0e0a0200005e5bc20c00")
assert len(RETAIL_CAVE) == CAVE_SIZE

# roll quaternions (w, x, y, z), applied in the ball's own frame (about its long axis, model Z)
ROLL_180 = (0.0, 0.0, 0.0, 1.0)
ROLL_90 = (math.sqrt(0.5), 0.0, 0.0, math.sqrt(0.5))
DEFAULT_ROLL = ROLL_180


class KickLacesError(ValueError):
    """The kick-laces patch cannot be applied to this executable."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise KickLacesError(message)


def _f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def quat_bytes(roll: Sequence[float]) -> bytes:
    """``(w, x, y, z)`` -> 16 little-endian floats; must be a unit quaternion."""

    _require(len(roll) == 4, "a roll quaternion has four components (w, x, y, z)")
    w, x, y, z = (float(v) for v in roll)
    _require(all(math.isfinite(v) for v in (w, x, y, z)), "roll quaternion components must be finite")
    norm = math.sqrt(w * w + x * x + y * y + z * z)
    _require(abs(norm - 1.0) < 1e-5, f"roll quaternion must be unit length, |q| = {norm:.6f}")
    return struct.pack("<4f", w, x, y, z)


def quat_multiply(a: Sequence[float], b: Sequence[float]) -> tuple[float, float, float, float]:
    """Hamilton product ``a x b`` on ``(w, x, y, z)``, the order FUN_003ca150 computes."""

    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw)


def roll_angle_degrees(roll: Sequence[float]) -> float:
    """The rotation angle a unit quaternion encodes (0..360)."""

    w = max(-1.0, min(1.0, float(roll[0])))
    return math.degrees(2.0 * math.acos(w))


def _code() -> tuple[bytes, dict[str, int]]:
    """The cave's code (entered by the hook's ``call``; the return address is on the stack)."""

    imm = lambda va: struct.pack("<I", va).hex()  # noqa: E731
    a = _Asm(CAVE_VA)
    a.label("cave")
    a.b("60")                                           # pushad
    a.b("9c")                                           # pushfd
    a.b("833d" + imm(PLAY_STATE_VA) + f"{LIVE_PLAY:02x}")   # cmp dword [0xE602B8], 0xE   live play?
    a.j8("75", "done")                                  # jne done
    a.b("8b0d" + imm(POSSESSION_VA))                    # mov ecx, [0xE60280]        team with the ball
    a.b("85c9")                                         # test ecx, ecx
    a.j8("74", "done")
    a.b("8b490c")                                       # mov ecx, [ecx+0xc]         play-call state
    a.b("83f9" + struct.pack("<b", NO_PLAY_SENTINEL).hex())  # cmp ecx, -4           "no play yet"
    a.j8("74", "done")
    a.b("85c9")                                         # test ecx, ecx
    a.j8("74", "done")
    a.b("8b4908")                                       # mov ecx, [ecx+8]           formation record
    a.b("85c9")                                         # test ecx, ecx
    a.j8("74", "done")
    a.b("8b49" + f"{FORMATION_FLAGS_OFFSET:02x}")       # mov ecx, [ecx+4]           formation flags
    a.b("c1e908")                                       # shr ecx, 8
    a.b("83e13f")                                       # and ecx, 0x3f              formation type
    a.b("83f9" + f"{FG_FORMATION_TYPE:02x}")            # cmp ecx, 12                Field Goal formation?
    a.j8("75", "done")                                  # jne done
    a.b("68" + imm(ROLL_VA))                            # push roll                  b = the roll constant
    a.b("8d4e" + f"{BALL_QUAT_OFFSET:02x}")             # lea ecx, [esi+0x20]        out = ball quaternion
    a.b("8bd1")                                         # mov edx, ecx               a = ball quaternion
    a.call(QUAT_MUL_VA)                                 # call FUN_003ca150          q <- q x r (callee pops b)
    a.label("done")
    a.b("9d")                                           # popfd
    a.b("61")                                           # popad
    a.b("8b542418")                                     # mov edx, [esp+0x18]        replay (+4: the return address)
    a.b("8b0a")                                         # mov ecx, [edx]             replay
    a.b("c3")                                           # ret
    a.label("end")
    code = a.assemble()
    return code, {name: CAVE_VA + off for name, off in a.labels.items()}


CODE, CAVE_LABELS = _code()
CODE_SIZE = len(CODE)
assert CODE_SIZE <= ROLL_OFFSET, f"kick-laces cave code is {CODE_SIZE} bytes, over the {ROLL_OFFSET} before the roll constant"
assert ROLL_OFFSET + ROLL_SIZE <= CAVE_SIZE
assert ROLL_VA % 16 == 0

PATCHED_HOOK = b"\xe8" + struct.pack("<i", CAVE_VA - (HOOK_VA + 5)) + b"\x90"     # call cave ; nop
assert len(PATCHED_HOOK) == HOOK_SIZE


def cave_bytes(roll: Sequence[float] = DEFAULT_ROLL) -> bytes:
    """Code, int3 fill, the roll quaternion at +0x70, int3 fill to the end of the dead routine."""

    body = CODE + b"\xcc" * (ROLL_OFFSET - CODE_SIZE) + quat_bytes(roll)
    body += b"\xcc" * (CAVE_SIZE - len(body))
    _require(len(body) == CAVE_SIZE, "cave layout error")
    return body


def _header_size(payload: bytes) -> int:
    return struct.unpack_from("<I", payload, 0x108)[0]


def _offset(payload: bytes, va: int) -> int:
    if IMAGE_BASE <= va < IMAGE_BASE + _header_size(payload):
        return va - IMAGE_BASE
    for section in _sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise KickLacesError(f"VA 0x{va:x} is in no section")


def sites(roll: Sequence[float] = DEFAULT_ROLL) -> list[tuple[str, int, bytes, bytes]]:
    """``(label, va, retail bytes, patched bytes)`` for the hook and the cave."""

    return [("hold_join_hook", HOOK_VA, RETAIL_HOOK, PATCHED_HOOK),
            ("laces_cave", CAVE_VA, RETAIL_CAVE, cave_bytes(roll))]


# context that must be retail on any image we touch: the instructions around the hook, the game's
# quaternion product, and the padding / next routine after the dead host
PINS = ((HOOK_BEFORE_VA, RETAIL_HOOK_BEFORE), (HOOK_AFTER_VA, RETAIL_HOOK_AFTER),
        (QUAT_MUL_VA, RETAIL_QUAT_MUL_HEAD), (CAVE_PAD_VA, RETAIL_CAVE_PAD),
        (NEXT_ROUTINE_VA, RETAIL_NEXT_ROUTINE_HEAD))


def _pins_are_retail(payload: bytes) -> bool:
    for va, expected in PINS:
        off = _offset(payload, va)
        if payload[off: off + len(expected)] != expected:
            return False
    return True


def _cave_state(blob: bytes) -> str:
    """'retail', 'applied' (our code with any unit roll) or 'foreign' for the 143 cave bytes."""

    if blob == RETAIL_CAVE:
        return "retail"
    template = cave_bytes(DEFAULT_ROLL)
    if blob[:ROLL_OFFSET] != template[:ROLL_OFFSET] or blob[ROLL_OFFSET + ROLL_SIZE:] != template[ROLL_OFFSET + ROLL_SIZE:]:
        return "foreign"
    try:
        quat_bytes(struct.unpack("<4f", blob[ROLL_OFFSET: ROLL_OFFSET + ROLL_SIZE]))
    except KickLacesError:
        return "foreign"
    return "applied"


def status(payload: bytes) -> str:
    """'retail', 'applied' (any roll) or 'foreign' (bytes match neither; refuse to touch)."""

    try:
        if not _pins_are_retail(payload):
            return "foreign"
        hook = payload[_offset(payload, HOOK_VA):][:HOOK_SIZE]
        cave = payload[_offset(payload, CAVE_VA):][:CAVE_SIZE]
    except (KickLacesError, ValueError, struct.error):
        return "foreign"
    hook_state = "retail" if hook == RETAIL_HOOK else "applied" if hook == PATCHED_HOOK else "foreign"
    cave_state = _cave_state(cave)
    if hook_state == cave_state == "retail":
        return "retail"
    if hook_state == cave_state == "applied":
        return "applied"
    return "foreign"


def read_settings(payload: bytes) -> dict[str, object]:
    """The roll currently encoded (identity on a retail image)."""

    state = status(payload)
    if state != "applied":
        return {"status": state, "roll": (1.0, 0.0, 0.0, 0.0), "roll_degrees": 0.0}
    off = _offset(payload, ROLL_VA)
    roll = struct.unpack_from("<4f", payload, off)
    return {"status": state, "roll": roll, "roll_degrees": roll_angle_degrees(roll)}


def apply(payload: bytes, roll: Sequence[float] = DEFAULT_ROLL) -> tuple[bytes, Mapping[str, object]]:
    """Return the patched XBE bytes plus a receipt; refuses anything but retail sites.

    An applied image is returned unchanged with ``already_applied`` (whatever roll it carries).
    """

    wanted = quat_bytes(roll)
    state = status(payload)
    if state == "applied":
        return payload, {"already_applied": True, "edits": [], "changed_bytes": 0, **read_settings(payload)}
    _require(state == "retail", f"kick-laces sites are {state}, not retail; refusing")
    buf = bytearray(payload)
    sections = _sections(payload)
    touched: set[int] = set()
    edits = []
    for label, va, before, after in sites(roll):
        off = _offset(payload, va)
        _require(payload[off: off + len(before)] == before, f"{label}: retail bytes missing")
        buf[off: off + len(after)] = after
        touched.add(_section_for_offset(sections, off).index)
        edits.append({"label": label, "va": f"0x{va:x}", "file_offset": f"0x{off:x}", "bytes": len(after),
                      "before": before.hex() if label != "laces_cave" else f"<{len(before)} retail bytes>",
                      "after": after.hex() if label != "laces_cave" else f"<{len(after)} bytes>"})
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d: d + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    _require(status(patched) == "applied", "post-apply verification failed")
    back = read_settings(patched)
    _require(struct.pack("<4f", *back["roll"]) == wanted, "post-apply read-back of the roll failed")
    changed = sum(1 for a, b in zip(payload, patched) if a != b)
    return patched, {
        "edits": edits, "changed_bytes": changed, "sections_repinned": sorted(touched), "status": "applied",
        "hook_va": f"0x{HOOK_VA:x}", "hook_bytes": PATCHED_HOOK.hex(),
        "cave_va": f"0x{CAVE_VA:x}", "cave_size": CAVE_SIZE, "cave_code_bytes": CODE_SIZE,
        "cave_labels": {name: f"0x{va:x}" for name, va in CAVE_LABELS.items()},
        "roll_va": f"0x{ROLL_VA:x}", "roll": tuple(_f32(v) for v in roll), "roll_degrees": roll_angle_degrees(roll),
        "product": "FUN_003ca150 (q <- q x r, the game's own Hamilton product)",
        "gates": {"play_state": f"[0x{PLAY_STATE_VA:x}] == 0x{LIVE_PLAY:x}",
                  "formation": f"[[[0x{POSSESSION_VA:x}]+0xc]+8]+4 bits 8-13 == {FG_FORMATION_TYPE}, -4 sentinel guarded"},
    }


__all__ = ["BALL_QUAT_OFFSET", "CAVE_LABELS", "CAVE_SIZE", "CAVE_VA", "CODE", "CODE_SIZE", "DEFAULT_ROLL",
           "FG_FORMATION_TYPE", "HOOK_JUMP_SOURCES", "HOOK_SIZE", "HOOK_VA", "KickLacesError", "LIVE_PLAY",
           "NEXT_ROUTINE_VA", "NO_PLAY_SENTINEL", "PATCHED_HOOK", "PINS", "PLAY_STATE_VA", "POSSESSION_VA",
           "QUAT_MUL_VA", "RETAIL_CAVE", "RETAIL_HOOK", "ROLL_180", "ROLL_90", "ROLL_OFFSET", "ROLL_SIZE",
           "ROLL_VA", "apply", "cave_bytes", "quat_bytes", "quat_multiply", "read_settings", "roll_angle_degrees",
           "sites", "status"]

"""Defenders break on the thrown ball, USA retail. EXPERIMENTAL / UNWITNESSED.

When a pass is released (0x1CFA40) the game stores the ball's catch point at 0xBF0DF0 and
posts event 0x27 to every defender. Every man and zone coverage initializer maps that event to
behavior 37 (0x2E95F0); a man defender on the intended receiver always starts it, a zone
defender with probability 1 - Coverage (proved offline, see the b776 ai2 report). Retail then
sends him to a fixed spot, the receiver's position plus 0.25 s of his velocity at the throw, at
0.84 throttle, and he only plays the ball (action 0x61) once it is within 3 yd.

This owner changes two things inside behavior 37 and nothing else:

* the run-to point becomes the stored catch point when it is valid (0xBF0E08 == 1), the
  defender reacts to the intended receiver ([0xE3C000]), and the point is downfield of the
  line of scrimmage and within 25 yd of him (otherwise the retail point);
* the reaction task's navigation throttle immediate at 0x2E7463 becomes 1.0 (from 0.84).

The reaction lottery, its timer, the native play-the-ball and tackle decisions, catches and
interceptions are untouched. Settings are build-time only.
"""
from __future__ import annotations

import hashlib
import struct

OWNER = "nfl2k5_db_ball_play"
CODE_SIZE = 128
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
BUILD_CAPTION = "Defenders break on the thrown ball (experimental)"
HELP_TEXT = ("EXPERIMENTAL / UNWITNESSED. Off in every preset. After the throw, a defender who reacts to the pass "
             "(the man covering the target, or a zone defender who reads it) runs at full speed to where the ball "
             "will come down instead of jogging to where the receiver was heading. Expect more pass breakups and "
             "some more interceptions. Catching and interception chances are unchanged.")
POINT_HOOK = ("catch_point", 0x002E978C, bytes.fromhex("0f284424200f294620"))
THROTTLE_SITE = ("reaction_throttle", 0x002E7463, struct.pack("<f", 0.84), struct.pack("<f", 1.0))
SYMBOLS = dict(depth=0x002E5E30)
GUARDS = (
    (0x002E95F0, 561, "e046572f8aa824ec87facf9560cf7b63182ee1a767cdcf5e254819f184441f31"),   # behavior 37 init
    (0x002E7240, 623, "16e9d900086c9ed5e638af5c6cf4e8d05c950bded7ca41ea47fed7e28ef70deb"),   # reaction task
    (0x001F3A90, 35, "082a59750108a3c50e854cd9bc41cae4102863050a0b6eff44290b052c0215ef"),    # catch point clear
    (0x001F3AC0, 85, "de151ce878c5c75c258a265d1d3da9332bb3057812190700db2e7aa75b444bda"),    # catch point store
    (0x002E5E30, 72, "1cb65fa9ca08be4007077beeb218f3bd619898a5c8591f0b166081d11d3b3b5e"),    # downfield depth
    (0x001CFA40, 158, "038fca6c040989f10c40f6fce8a672cce8fa8a7dabdd2c9201d9e12757d49c6f"),   # release
    (0x004E4180, 4, "df3f619804a92fdb4057192dc43dd748ea778adc52bc498ce80524c014b81119"),
)
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError)


class DbBallPlayError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise DbBallPlayError(message)


def allocation(payload):
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    require(len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"]) == ("code", CODE_SIZE, 16),
            "Missing or foreign defender ball-play allocation")
    return rows[0]


def code_for(code_va):
    from . import nfl2k5_db_ball_play_code as assembly
    symbols = dict(SYMBOLS, code=code_va)
    out = bytearray(assembly.CODE)
    for off, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", out, off)[0]
        if kind == 2:
            target -= code_va + off
        struct.pack_into("<I", out, off, target & 0xFFFFFFFF)
    require(len(out) <= CODE_SIZE, "Defender ball-play code exceeds its RX allocation")
    return bytes(out).ljust(CODE_SIZE, b"\xcc")


def sites(code_va=0):
    from . import nfl2k5_db_ball_play_code as assembly
    name, va, before = POINT_HOOK
    call = b"\xe8" + struct.pack("<i", code_va + assembly.LABELS["point"] - va - 5)
    return [(name, va, before, call.ljust(len(before), b"\x90")), THROTTLE_SITE]


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
    require(states in ({"retail"}, {"applied"}), "Foreign or mixed defender ball-play sites/code")
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for _, at, before, _ in edits:
            if va <= at and at + len(before) <= va + size:
                content[at - va:at - va + len(before)] = before
        require(hashlib.sha256(content).hexdigest() == digest, f"Foreign defender ball-play prerequisite at {va:#x}")
    return next(iter(states))


def status(payload):
    try:
        return _recognize(payload)
    except _ERRORS:
        return "foreign"


def read_settings(payload):
    return {"status": status(payload)}


def apply(payload):
    """Install, or replay an identical installation."""
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_bump_strength import _sections, section_digest
    from .nfl2k5_cave_oracle import XbeImage
    try:
        state = _recognize(payload)
    except _ERRORS as exc:
        raise DbBallPlayError(f"foreign/mixed defender ball-play input: {exc}") from exc
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False)
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    before = payload
    allocation_receipt = {}
    if not any(r["owner"] == OWNER for r in space.layout(payload)["allocations"]):
        if space.status(payload) == "retail":
            payload, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
        else:
            require(space.is_scaleout(payload), "Defender ball play needs the scale-out allocator")
            payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
    code_va = allocation(payload)["va"]
    payload, _ = space.install_code(payload, OWNER, code_for(code_va))
    edits = sites(code_va)
    image = XbeImage(payload)
    buf = bytearray(payload)
    for _, va, old, new in edits:
        off = image.offset(va, len(old))
        require(bytes(buf[off:off + len(old)]) == old, f"Defender ball-play site {va:#x} is not retail")
        buf[off:off + len(old)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(_recognize(result) == "applied" and space.status(result) == "applied",
            "Defender ball-play postcondition failed")
    return result, dict(common, status="applied",
                        before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=space.count_differing_bytes(before, result), file_growth=len(result) - len(before),
                        allocation=allocation_receipt,
                        edits=[dict(label=name, va=hex(va), before=old.hex(), after=new.hex()) for name, va, old, new in edits],
                        reservations=[r for r in space.reservations(result) if r["owner"] == OWNER])


__all__ = ["OWNER", "REQUESTS", "GUARDS", "POINT_HOOK", "THROTTLE_SITE", "apply", "status", "read_settings",
           "allocation", "code_for", "sites"]

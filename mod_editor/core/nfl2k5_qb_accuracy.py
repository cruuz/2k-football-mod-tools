"""QB accuracy on short and on-the-run throws, USA retail. EXPERIMENTAL / UNWITNESSED.

The pass accuracy routine (0x2D9700, shared by human and CPU passers) turns its error sum into a miss distance D
(curve 0x50BE20 of throw distance plus error) and moves the target D along an error heading. Measured natively on
the b776 disc (b777 qb3 report): a set QB is exact to about 35 yd whatever his rating, but a QB on the move misses
drags, outs, slants and digs by 0.5-2.3 yd, nearly always AHEAD of the receiver along the QB's run (outs sail toward
the sideline), and that miss ignores Pass Accuracy (the rating only scales positive error sums; a human QB on the
run has a negative sum). CPU QBs on the run also throw knee-high, from the height error that rides with D.

This owner hooks the store of D (0x2D9F18). When the throw has a miss and is shorter than 40 yd it scales the miss
and its height error by the QB's own Pass Accuracy (k_acc curve in the cave: 0.55 -> 0.9, 0.7 -> 0.62,
0.8 -> 0.45, 0.9 -> 0.3, 1.0 -> 0.18), fully to 20 yd and fading to retail at 40 yd, and turns the error heading
180 degrees with probability 0.5 x that weight, so misses land behind the receiver as often as ahead. Ratings,
grades, ball flight, catching and interceptions are untouched; a throw with no miss (a set QB) is byte-for-byte
retail. Settings are build-time only.

It also makes screen passes lead the receiver (SCREEN_LEAD, one operand byte): retail aims a screen (route kind 9) at the
spot where the back is at the release, so a back still moving out to his screen spot turns and comes back for the ball
(Noah 10/20: "HB screen, he starts running backwards"); now the ball is led along his route, which ends at his spot.

b777 qb4 adds quick-throw placement (LEAD hook, same cave): when a moving receiver runs within 45 degrees of the throw
line (quick outs, flats, bubbles), the lead solver 0x2DA8E0 moves the target 1.5 yd sideways off his path toward the
QB (constant 0x4F0F74, 137.16 cm), so quick outs and flats arrive underneath him and he reaches back (Noah 10/20:
"the quick throws in this game never work. The receiver doesn't get the right catch animation"). None of the game's
68 side-catch running catch records reaches 1.5 yd sideways. The offset is now scaled by the target's depth past the
line: none up to 8 yd (and behind the line), fading back to retail by 10 yd, so intermediate and deep placement is
byte-for-byte retail. The shared constant is not touched.
"""
from __future__ import annotations

import hashlib
import struct

OWNER = "nfl2k5_qb_accuracy"
CODE_SIZE = 384
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
BUILD_CAPTION = "Accurate short throws and throws on the run (experimental)"
HELP_TEXT = ("EXPERIMENTAL. Quarterbacks stop overthrowing drags, outs, slants and digs, above all on the run: a miss "
             "on a throw under 40 yards now shrinks with the passer's own Pass Accuracy (a 90 passer misses by about a "
             "third of what he did, a 55 passer about as before) and lands behind the receiver as often as ahead of "
             "him. Screen passes lead the back toward his spot instead of pulling him backwards, and quick outs, flats "
             "and bubbles are thrown on the receiver's path instead of a yard and a half underneath him, so he can "
             "catch them in stride. Ratings and grades are unchanged; deep balls and throws from a set pocket keep "
             "their native accuracy and placement.")
HOOK = ("miss_store", 0x002D9F18, bytes.fromhex("d95c24148b5d08"), "place")
# b777 coordinator ask (screens): the route predictor 0x2266A0 (callers: the throw target 0x2F43E0 and the CPU QB read
# grid 0x19A3FA) returns a screen receiver's (route kind 9) CURRENT spot instead of leading him, so a back still moving
# to his screen spot has to come back for the ball. The kind-9 shortcut test "cmp edx, 9" (0x226832) gets an
# impossible operand (kinds are masked to 0..31), so kind 9 takes the predictor's ordinary path: he is led along his
# route segments, which end at his screen spot (1.5 yd behind the line). Stem-block kind 10 keeps the shortcut.
SCREEN_LEAD = ("screen_lead", 0x00226834, b"\x09", b"\x20")
# b777 qb4: the lead solver's placement tail (fld sin; fmul [0x4F0F74]; fadd x; fstp x; fld cos; ...; fstp z) at
# 0x2DAD97..0x2DADBB becomes a jmp to the cave's depth-scaled copy, which returns to 0x2DADBB.
LEAD = ("quick_lead", 0x002DAD97, bytes.fromhex("d9442434d80d740f4f00d8442450d95c2450d9442430d80d740f4f00d8442458d95c2458"),
        "lead")
SYMBOLS = dict(resume=0x002D9F1F, curve=0x001B0AE0, rng=0x00048B90, lead_resume=0x002DADBB)
GUARDS = (
    (0x002DA8E0, 1580, "2fa96051127785d54f6c44946bd3e12e0081c9cfd5a8a00a401423bedbb68c93"),   # lead solver (qb4)
    (0x002266A0, 1065, "e2801e152a366ce1276175628d2c40b801d0195a600ed16df846c32f3d10bc87"),   # route predictor
    (0x002D9700, 2970, "280d1b3ea95293545b304cea962c13058060f4fc170146918a140860383c3243"),   # accuracy routine
    (0x001B0AE0, 122, "11b02ee0ad143dd1a8ad979ef069c120ce71498014efd893b68a40aca8a7f6c5"),    # curve interpolator
    (0x00048B50, 105, "27476b10d12effcb7ebcdc155d01e15fdaf28b0d4a566b6e1c5bf1ac3f64959a"),    # native RNG
    (0x0050BDEC, 52, "d63a8f3b9f7e6221fb2dc1d5a21d8890a07328eabb93009a49665f433076d2d5"),     # Pass Accuracy factor curve
    (0x0050BE20, 44, "6e9d21819979887a38c05a833a09de5061c7255b1d0bed1bbdd0d5b65a10e525"),     # miss curve
)
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError)


class QbAccuracyError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise QbAccuracyError(message)


def allocation(payload):
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    require(len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"]) == ("code", CODE_SIZE, 16),
            "Missing or foreign QB accuracy allocation")
    return rows[0]


def code_for(code_va):
    from . import nfl2k5_qb_accuracy_code as assembly
    symbols = dict(SYMBOLS, code=code_va)
    out = bytearray(assembly.CODE)
    for off, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", out, off)[0]
        if kind == 2:
            target -= code_va + off
        struct.pack_into("<I", out, off, target & 0xFFFFFFFF)
    require(len(out) <= CODE_SIZE, "QB accuracy code exceeds its RX allocation")
    return bytes(out).ljust(CODE_SIZE, b"\xcc")


def sites(code_va=0):
    from . import nfl2k5_qb_accuracy_code as assembly
    edits = []
    for name, va, before, label in (HOOK, LEAD):
        jump = b"\xe9" + struct.pack("<i", code_va + assembly.LABELS[label] - va - 5)
        edits.append((name, va, before, jump.ljust(len(before), b"\x90")))
    return edits + [SCREEN_LEAD]


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
    require(states in ({"retail"}, {"applied"}), "Foreign or mixed QB accuracy site/code")
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for _, at, before, _ in edits:
            if va <= at and at + len(before) <= va + size:
                content[at - va:at - va + len(before)] = before
        require(hashlib.sha256(content).hexdigest() == digest, f"Foreign QB accuracy prerequisite at {va:#x}")
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
        raise QbAccuracyError(f"foreign/mixed QB accuracy input: {exc}") from exc
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False)
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    before = payload
    allocation_receipt = {}
    if not any(r["owner"] == OWNER for r in space.layout(payload)["allocations"]):
        if space.status(payload) == "retail":
            payload, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
        else:
            require(space.is_scaleout(payload), "QB accuracy needs the scale-out allocator")
            payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
    code_va = allocation(payload)["va"]
    payload, _ = space.install_code(payload, OWNER, code_for(code_va))
    edits = sites(code_va)
    image = XbeImage(payload)
    buf = bytearray(payload)
    for _, va, old, new in edits:
        off = image.offset(va, len(old))
        require(bytes(buf[off:off + len(old)]) == old, f"QB accuracy site {va:#x} is not retail")
        buf[off:off + len(old)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(_recognize(result) == "applied" and space.status(result) == "applied",
            "QB accuracy postcondition failed")
    return result, dict(common, status="applied",
                        before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=space.count_differing_bytes(before, result), file_growth=len(result) - len(before),
                        allocation=allocation_receipt,
                        edits=[dict(label=name, va=hex(va), before=old.hex(), after=new.hex()) for name, va, old, new in edits],
                        reservations=[r for r in space.reservations(result) if r["owner"] == OWNER])


__all__ = ["OWNER", "REQUESTS", "GUARDS", "HOOK", "LEAD", "SCREEN_LEAD", "apply", "status", "read_settings", "allocation", "code_for", "sites"]

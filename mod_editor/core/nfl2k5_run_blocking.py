"""Run blocking: blocks hold longer on running plays, rating against rating, USA retail. EXPERIMENTAL.

Noah (b776 playtest, 2026-10-20): "running the football is very hard. My offensive line just does not block very
well." The retail engaged-block code (b777-ol1 report, retail addresses):

* 0x233B50 starts an engagement; 0x2336E0 picks the paired block animation from the offense's share
  (0x233250 -> 0x232200: Strength and body weight as mass, Run Blocking against Run Coverage on a running play).
* 0x230320 is the start roll the four block choosers (0x232F40/F80/FC0, 0x233000) use: on a running play the
  defender wins on rand < curve(Run Coverage) + 0.25 - curve(Run Blocking) + 0.6 x leverage (+ 0.25 side term),
  curve 0x50B4C4 = (0, .1) (.3, .2) (.7, .7) (.9, 1.0) (1.0, 1.2).
* Every simulation tick 0x234640 asks 0x233040 whether the pair breaks up. On a running play (blocker state
  +0x18C & 7 not 1 or 2) the defender sheds (return 2) once his wanted heading has pointed away from the blocker
  (by more than 0x230A00's angle, about 90 degrees for a CPU defender) at full throttle for more than 0.05 s, the
  immediate at 0x23317A, the same for every lineman whatever his ratings. When the run has declared for a
  controlled ball carrier (latch 0x2F3AC0(455.2)), he sheds on any tick where rand < Run Coverage
  (0x2331C5): with Run Coverage 0.7 that is 70 % per tick.

This owner changes three things, all on running plays only (pass protection keeps every retail byte):

* start roll: the run branch adds 0.15 instead of 0.25 (the fadd at 0x23034F reads the owner's constant; the
  pass branch's own fadd at 0x230396 still reads 0.25);
* shed delay: clamp(0.30 + 0.60 x (Run Blocking of the blocker - Run Coverage of the defender), 0.08, 0.60)
  seconds instead of 0.05 s (call at 0x23317A, run branch only);
* shed after the run declares: the per-tick chance is Run Coverage / 25 instead of Run Coverage (call at
  0x2331C5 multiplies the native random number by 25).

Ratings are read through the native accessor 0x17B010 (fatigue and injuries included), so a good line still beats
a bad one and a great run defender still sheds sooner. Settings are build-time only.
"""
from __future__ import annotations

import hashlib
import struct

OWNER = "nfl2k5_run_blocking"
CODE_SIZE = 160
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
BUILD_CAPTION = "Run blocking: blocks hold longer on running plays"
HELP_TEXT = ("EXPERIMENTAL. On running plays the offensive line holds its blocks longer and wins the first "
             "contact a little more often, so backs find more lanes and more 10 and 20 yard runs. Ratings still "
             "decide it: Run Blocking against the defender's Run Coverage. Pass protection is unchanged. Retail: "
             "a defender sheds a run block 0.05 s after he turns toward the ball carrier, whatever the ratings.")
RETAIL_ROLL_ADD = 0x004E696C              # 0.25, shared by many readers
ROLL_HOOK = ("start_roll", 0x0023034F, bytes.fromhex("d8056c694e00"), "k_roll")
DELAY_HOOK = ("shed_delay", 0x0023317A, bytes.fromhex("c7442418cdcc4c3d"), "delay")
SHED_HOOK = ("shed_on_run", 0x002331C5, bytes.fromhex("e8c659e1ff"), "shed_rand")
SYMBOLS = dict(rating=0x0017B010, rand=0x00048B90)
# Tuning (seconds, rating units 0..1). The template holds the same values; code_for() writes these.
ROLL_ADD = 0.15
DELAY_BASE, DELAY_SLOPE, DELAY_MIN, DELAY_MAX = 0.30, 0.60, 0.08, 0.60
SHED_DIVISOR = 25.0
RETAIL_DELAY = 0.05
GUARDS = (
    (0x00230320, 0x1C7, "33d3890db9f73eb2b9c12362d71e1506aa7dbe88ad0bba8a70601a6ac8300678"),  # start roll
    (0x00233040, 0x206, "14efc366e02646094b8ff89a6138538fae51a4c6025b0675ec441cd9149b14ee"),  # shed decision
    (0x00048B90, 0x29, "093cf53c774b31825b84db51c0e070a603606c6f6b4cce2ee7a9381e9e9f004e"),   # native random
    (0x0050B4C4, 0x2C, "90e768a17aa688a51508e1788d755ace70812e67e3cfa4de24107df1a6a5c635"),   # start roll curve
    (0x004E696C, 4, "75e253f50979177eba47b2d0805ad36038789108924514d2a761a70de057d16f"),
)
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError)


class RunBlockingError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise RunBlockingError(message)


def allocation(payload):
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    require(len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"]) == ("code", CODE_SIZE, 16),
            "Missing or foreign run-blocking allocation")
    return rows[0]


def code_for(code_va):
    from . import nfl2k5_run_blocking_code as assembly
    symbols = dict(SYMBOLS, code=code_va)
    out = bytearray(assembly.CODE)
    for off, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", out, off)[0]
        if kind == 2:
            target -= code_va + off
        struct.pack_into("<I", out, off, target & 0xFFFFFFFF)
    for label, value in (("k_roll", ROLL_ADD), ("k_base", DELAY_BASE), ("k_slope", DELAY_SLOPE),
                         ("k_min", DELAY_MIN), ("k_max", DELAY_MAX), ("k_shed_inv", SHED_DIVISOR)):
        struct.pack_into("<f", out, assembly.LABELS[label], value)
    require(len(out) <= CODE_SIZE, "Run-blocking code exceeds its RX allocation")
    return bytes(out).ljust(CODE_SIZE, b"\xcc")


def sites(code_va=0):
    from . import nfl2k5_run_blocking_code as assembly
    name, va, before, label = ROLL_HOOK
    result = [(name, va, before, before[:2] + struct.pack("<I", (code_va + assembly.LABELS[label]) & 0xFFFFFFFF))]
    for name, va, before, label in (DELAY_HOOK, SHED_HOOK):
        call = b"\xe8" + struct.pack("<i", code_va + assembly.LABELS[label] - va - 5)
        result.append((name, va, before, call.ljust(len(before), b"\x90")))
    return result


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
    require(states in ({"retail"}, {"applied"}), "Foreign or mixed run-blocking sites/code")
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for _, at, before, _ in edits:
            if va <= at and at + len(before) <= va + size:
                content[at - va:at - va + len(before)] = before
        require(hashlib.sha256(content).hexdigest() == digest, f"Foreign run-blocking prerequisite at {va:#x}")
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
        raise RunBlockingError(f"foreign/mixed run-blocking input: {exc}") from exc
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False)
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    before = payload
    allocation_receipt = {}
    if not any(r["owner"] == OWNER for r in space.layout(payload)["allocations"]):
        if space.status(payload) == "retail":
            payload, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
        else:
            require(space.is_scaleout(payload), "Run blocking needs the scale-out allocator")
            payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
    code_va = allocation(payload)["va"]
    payload, _ = space.install_code(payload, OWNER, code_for(code_va))
    edits = sites(code_va)
    image = XbeImage(payload)
    buf = bytearray(payload)
    for _, va, old, new in edits:
        off = image.offset(va, len(old))
        require(bytes(buf[off:off + len(old)]) == old, f"Run-blocking site {va:#x} is not retail")
        buf[off:off + len(old)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(_recognize(result) == "applied" and space.status(result) == "applied",
            "Run-blocking postcondition failed")
    return result, dict(common, status="applied",
                        before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=space.count_differing_bytes(before, result), file_growth=len(result) - len(before),
                        allocation=allocation_receipt, code_va=hex(code_va),
                        edits=[dict(label=name, va=hex(va), before=old.hex(), after=new.hex()) for name, va, old, new in edits],
                        reservations=[r for r in space.reservations(result) if r["owner"] == OWNER])


__all__ = ["OWNER", "REQUESTS", "GUARDS", "ROLL_HOOK", "DELAY_HOOK", "SHED_HOOK", "apply", "status", "read_settings",
           "allocation", "code_for", "sites"]

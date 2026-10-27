"""Pass protection: beaten pass blockers hold their rusher for a rating-based delay. EXPERIMENTAL.

holtbolt (b778, 2026-10-24): "the difficulty makes pass rush incredibly easy for the player and the CPU, even
when you have great guards." The retail engaged-block tick 0x233040 ends a PASS block on the first tick its
heading test passes: the threshold store at 0x233162 writes 0, and the branch at 0x233178 skips the 0.05 s run
constant at 0x23317A, so a rusher who gets a step is free in one simulation tick whatever the ratings. The
start roll 0x230320 already uses Pass Blocking against Pass Rush on passes; the zero shed delay is what turns
every first-contact win into immediate pressure and makes the line's ratings (guards included) disappear.

This owner replaces the zero store with a call that computes, on pass plays only,

    clamp(k_base + k_slope * (Pass Blocking(blocker) - Pass Rush(defender)), k_min, k_max) seconds

through the game's own rating accessor 0x17B010. On run plays it writes 0, exactly as retail, so the retail
0.05 s constant (or b777-ol1's run-blocking owner at 0x23317A, when that owner is installed) is untouched.
Nothing else is changed: the pass start roll, the paired-block animation share, the run latch and the shed
random draw keep every retail byte.
"""
from __future__ import annotations

import hashlib
import struct

OWNER = "nfl2k5_pass_protection"
CODE_SIZE = 160
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
BUILD_CAPTION = "Pass protection: blocks hold longer on pass plays"
HELP_TEXT = ("EXPERIMENTAL. On pass plays a beaten blocker holds his rusher for a moment instead of the retail "
             "instant shed, so pressure arrives at a realistic time and the offensive line's Pass Blocking matters. "
             "Ratings decide it: Pass Blocking of the blocker against Pass Rush of the defender. Retail: on a pass "
             "play the first tick a rusher's heading test passes ends the block, whatever the ratings. Run blocking "
             "keeps every byte of the existing run-blocking option.")
HOOK = ("pass_delay", 0x00233162, bytes.fromhex("c744241800000000"), "pass_delay")
SYMBOLS = dict(rating=0x0017B010)
# Tuning (seconds, rating units 0..1). The template holds the same values; code_for() writes these.
DELAY_BASE, DELAY_SLOPE, DELAY_MIN, DELAY_MAX = 0.45, 0.65, 0.10, 0.80
RETAIL_DELAY = 0.0       # 0x233162 stores zero; the run constant at 0x23317A is skipped on passes
GUARDS = (
    (0x00233040, 0x206, "14efc366e02646094b8ff89a6138538fae51a4c6025b0675ec441cd9149b14ee"),  # shed decision
)
# 0x17B010 is not hash-guarded: the abilities runtime replaces its entry with a jump to its own copy of the
# accessor on the release disc, so its bytes are not a stable prerequisite. Every call still goes through
# the game's accessor and its own slider/fatigue terms.
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError)


class PassProtectionError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise PassProtectionError(message)


def allocation(payload):
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    require(len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"]) == ("code", CODE_SIZE, 16),
            "Missing or foreign pass-protection allocation")
    return rows[0]


def code_for(code_va):
    from . import nfl2k5_pass_protection_code as assembly
    symbols = dict(SYMBOLS, code=code_va)
    out = bytearray(assembly.CODE)
    for off, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", out, off)[0]
        if kind == 2:
            target -= code_va + off
        struct.pack_into("<I", out, off, target & 0xFFFFFFFF)
    for label, value in (("k_base", DELAY_BASE), ("k_slope", DELAY_SLOPE),
                         ("k_min", DELAY_MIN), ("k_max", DELAY_MAX)):
        struct.pack_into("<f", out, assembly.LABELS[label], value)
    require(len(out) <= CODE_SIZE, "Pass-protection code exceeds its RX allocation")
    return bytes(out).ljust(CODE_SIZE, b"\xcc")


def sites(code_va=0):
    from . import nfl2k5_pass_protection_code as assembly
    name, va, before, label = HOOK
    call = b"\xe8" + struct.pack("<i", code_va + assembly.LABELS[label] - va - 5)
    return [(name, va, before, call.ljust(len(before), b"\x90"))]


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
    require(states in ({"retail"}, {"applied"}), "Foreign or mixed pass-protection sites/code")
    # The b777-ol1 run-blocking owner hooks two bytes inside 0x233040 (its run delay at 0x23317A and its
    # shed draw at 0x2331C5). When that owner is present, treat its exact applied bytes as retail for this
    # guard, exactly as its own recognizer masks its edits. Pass protection composes with it by design.
    masked = list(edits)
    from . import nfl2k5_run_blocking as run_blocking
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == run_blocking.OWNER]
    if rows:
        masked.extend(run_blocking.sites(rows[0]["va"]))
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for _, at, before, _ in masked:
            if va <= at and at + len(before) <= va + size:
                content[at - va:at - va + len(before)] = before
        require(hashlib.sha256(content).hexdigest() == digest, f"Foreign pass-protection prerequisite at {va:#x}")
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
        raise PassProtectionError(f"foreign/mixed pass-protection input: {exc}") from exc
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False)
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    before = payload
    allocation_receipt = {}
    if not any(r["owner"] == OWNER for r in space.layout(payload)["allocations"]):
        if space.status(payload) == "retail":
            payload, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
        else:
            require(space.is_scaleout(payload), "Pass protection needs the scale-out allocator")
            payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
    code_va = allocation(payload)["va"]
    payload, _ = space.install_code(payload, OWNER, code_for(code_va))
    edits = sites(code_va)
    image = XbeImage(payload)
    buf = bytearray(payload)
    for _, va, old, new in edits:
        off = image.offset(va, len(old))
        require(bytes(buf[off:off + len(old)]) == old, f"Pass-protection site {va:#x} is not retail")
        buf[off:off + len(old)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(_recognize(result) == "applied" and space.status(result) == "applied",
            "Pass-protection postcondition failed")
    return result, dict(common, status="applied",
                        before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=space.count_differing_bytes(before, result), file_growth=len(result) - len(before),
                        allocation=allocation_receipt, code_va=hex(code_va),
                        edits=[dict(label=name, va=hex(va), before=old.hex(), after=new.hex()) for name, va, old, new in edits],
                        reservations=[r for r in space.reservations(result) if r["owner"] == OWNER])


__all__ = ["OWNER", "REQUESTS", "GUARDS", "HOOK", "apply", "status", "read_settings",
           "allocation", "code_for", "sites", "DELAY_BASE", "DELAY_SLOPE", "DELAY_MIN", "DELAY_MAX"]

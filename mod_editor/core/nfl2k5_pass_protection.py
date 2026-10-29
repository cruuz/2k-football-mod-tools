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

b779-pr1 adds the SIMULATED half of the same feature (Franchise sims, Game Cast, supersim), as eight in-place
edits that need no cave: in the sim's pass-play block ``0x108368..0x1084c0`` the sack/scramble chance is
``1 - clamp(0.875 + o, 0.825, 0.925) - 0.005*QB``, where ``o`` was drawn UNIFORMLY from ``[min(x,-0.1), max(x,0.1)]``
and ``x = Pass Block(team +0x9c) - Pass Rush(team +0xa0)`` plus noise.  ``x`` has a standard deviation of 0.04,
so 96.5% of simulated dropbacks ignored both lines completely.  The edit makes ``o = 0.5 * x`` (a deterministic
function of the two lines; half gain keeps the league total steady when a roster's line ratings differ from the
shipped roster's) and fixes the sacker draw ``0x103760``: its candidate weights ``c^3 / (sum over the 14
defensive slots + 0.1)`` gave seven defensive backs a combined 20% of all sacks (NFL: 5.6%).  The normaliser now
sums the eight front slots only (loop bound ``0x1c -> 0x16``, leftover constant 0.1 -> 0.25) and the candidate
list puts the defensive backs last, so a back gets only the leftover (about 5%, safeties first).  The
pass-rusher composite (category 4) weighs Speed and Agility up and Strength and Tackle down, which moves sacks
from big tackles to ends and linebackers (NFL share of sacks: ends 34%, linebackers 39%, tackles 18%).
"""
from __future__ import annotations

import hashlib
import struct

OWNER = "nfl2k5_pass_protection"
CODE_SIZE = 240
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
BUILD_CAPTION = "Pass rush and pass protection: ratings decide who wins (played and simulated games)"
HELP_TEXT = ("EXPERIMENTAL. Played games: on a pass play a beaten blocker holds his rusher for a moment instead of "
             "the retail instant shed, and how long depends on Pass Blocking against Pass Rush with some variance "
             "from play to play, so elite pass rushers get free and elite tackles hold up. Simulated games "
             "(franchise sims, Game Cast): the sack chance now follows the two lines' ratings instead of mostly a "
             "coin flip, and sacks go to the defensive line and linebackers by Pass Rush (defensive backs only "
             "rarely) as in the NFL. Run blocking keeps every byte of the existing run-blocking option.")
HOOK = ("pass_delay", 0x00233162, bytes.fromhex("c744241800000000"), "pass_delay")
SYMBOLS = dict(rating=0x0017B010)
# Tuning (seconds, rating units 0..1). The template holds the same values; code_for() writes these.
DELAY_BASE, DELAY_SLOPE, DELAY_MIN, DELAY_MAX = 0.60, 1.40, 0.10, 1.80
DELAY_SPREAD = 0.45      # each engagement draws its hold in mean * (1 - spread .. 1 + spread) from a per-play hash
RETAIL_DELAY = 0.0       # 0x233162 stores zero; the run constant at 0x23317A is skipped on passes
GUARDS = (
    (0x00233040, 0x206, "14efc366e02646094b8ff89a6138538fae51a4c6025b0675ec441cd9149b14ee"),  # shed decision
)
# --- b779-pr1: simulated games (in place; 0 code, 0 writable, 0 read-only bytes requested) ---
SIM_LIST_VA = 0x004F6B0C
SIM_LIST_RETAIL = (15, 18, 19, 21, 17, 16, 27, 20, 23, 24, 25, 22, 26, 28, -1)   # sacker candidates (slot ids)
SIM_LIST_NEW = (15, 18, 19, 21, 17, 16, 20, 22, 27, 28, 23, 24, 25, 26, -1)      # DL, LB, then backs last
SIM_GAIN_VA = 0x004E4184         # float 0.5 in retail .rdata: the lines' effect on the sack chance (retail: none)
SIM_NORM_VA = 0x004E696C         # float 0.25 (retail 0x4E6D5C = 0.1)
SIM_EDITS = (
    ("sim_event_chance", 0x00108398,
     bytes.fromhex("d94424188b4c2418d81d5c6d4e00894c2428dfe0f6c4417408c7442428cdcccc3dd905d86b4f00d85c2418"
                   "c7442418cdccccbddfe0f6c4057b04894c2418"),
     bytes.fromhex("d9442418d80d84414e00d95c24188b4c2418894c2428").ljust(0x3E, b"\x90")),
    ("sim_rusher_slots", 0x0010404C, bytes([0x1C]), bytes([0x16])),
    ("sim_rusher_leftover", 0x00104068, struct.pack("<I", 0x004E6D5C), struct.pack("<I", SIM_NORM_VA)),
    ("sim_rusher_list", SIM_LIST_VA, struct.pack("<15i", *SIM_LIST_RETAIL), struct.pack("<15i", *SIM_LIST_NEW)),
    # category 4 (the pass rusher composite): weights Pass Rush 0.4 stay; Speed 0.1 -> 0.2, Agility 0.1 -> 0.15,
    # Strength 0.2 -> 0.1, Tackle 0.2 -> 0.15, so ends and linebackers outweigh big tackles as in the NFL
    ("sim_rusher_speed", 0x00514E78, struct.pack("<f", 0.1), struct.pack("<f", 0.2)),
    ("sim_rusher_agility", 0x00514E80, struct.pack("<f", 0.1), struct.pack("<f", 0.15)),
    ("sim_rusher_strength", 0x00514E88, struct.pack("<f", 0.2), struct.pack("<f", 0.1)),
    ("sim_rusher_tackle", 0x00514E90, struct.pack("<f", 0.2), struct.pack("<f", 0.15)),
)
SIM_GUARDS = (          # (va, size, sha256 of the retail bytes): the pass-play block, the sacker draw, the normaliser
    (0x00108340, 0x180, "6dd48d900dd0e5db53e3da2f06fb5ed310bcce76dbdbeae68a7ca503f3e373f2"),
    (0x00103760, 0x0F2, "687d3b1ffbe23412b264c51348747fb8ba0a11ddfb49a25706429c5d60e27930"),
    (0x00103F61, 0x220, "962183d67eb47d7b99ff6152a4f2d95eb8454c4cea3c1b0b6d64f4ff33fc0c80"),
    (0x00514E50, 0x048, "9839d631c32d91bea828cfd8d86fe6f7d0916fbeef5771d979f4d404436b8313"),                  # the pass-rusher composite entry (count, weights, getters)
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
                         ("k_min", DELAY_MIN), ("k_max", DELAY_MAX),
                         ("k_floor", 1.0 - DELAY_SPREAD), ("k_scale", 2.0 * DELAY_SPREAD / 65535.0)):
        struct.pack_into("<f", out, assembly.LABELS[label], value)
    require(len(out) <= CODE_SIZE, "Pass-protection code exceeds its RX allocation")
    return bytes(out).ljust(CODE_SIZE, b"\xcc")


def sites(code_va=0):
    from . import nfl2k5_pass_protection_code as assembly
    name, va, before, label = HOOK
    call = b"\xe8" + struct.pack("<i", code_va + assembly.LABELS[label] - va - 5)
    return [(name, va, before, call.ljust(len(before), b"\x90"))]


def _recognize_owner(payload):
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


def sim_sites():
    return list(SIM_EDITS)


def _sim_state(payload):
    """'retail' or 'applied' for the six simulated-game edits; raises on any foreign byte."""
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    states = set()
    for _name, va, before, after in SIM_EDITS:
        raw = image.read(va, len(before))
        states.add("retail" if raw == before else "applied" if raw == after else "foreign")
    require(states in ({"retail"}, {"applied"}), "Foreign or mixed simulated pass-rush sites")
    for va, size, digest in SIM_GUARDS:
        content = bytearray(image.read(va, size))
        for _name, at, before, _after in SIM_EDITS:
            if va <= at and at + len(before) <= va + size:
                content[at - va:at - va + len(before)] = before
        require(hashlib.sha256(content).hexdigest() == digest, f"Foreign simulated pass-rush prerequisite at {va:#x}")
    return next(iter(states))


def _recognize(payload):
    """'retail', 'applied', or 'partial' (a v1 build: the played-game owner without the simulated edits)."""
    owner = _recognize_owner(payload)
    sim = _sim_state(payload)
    return owner if owner == sim else "partial"


def status(payload):
    try:
        return _recognize(payload)
    except _ERRORS:
        return "foreign"


def read_settings(payload):
    return {"status": status(payload)}


def _apply_owner(payload):
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_bump_strength import _sections, section_digest
    from .nfl2k5_cave_oracle import XbeImage
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
    return bytes(buf), allocation_receipt, code_va, edits


def _apply_sim(payload):
    from .nfl2k5_bump_strength import _sections, section_digest
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    buf = bytearray(payload)
    for _, va, old, new in SIM_EDITS:
        off = image.offset(va, len(old))
        require(bytes(buf[off:off + len(old)]) == old, f"Simulated pass-rush site {va:#x} is not retail")
        buf[off:off + len(old)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    return bytes(buf)


def apply(payload):
    """Install, or replay an identical installation.  Completes a 'partial' (v1) build in place."""
    from . import nfl2k5_xbe_space as space
    try:
        state = _recognize(payload)
    except _ERRORS as exc:
        raise PassProtectionError(f"foreign/mixed pass-protection input: {exc}") from exc
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False)
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    before = payload
    allocation_receipt, code_va, labels = {}, None, []
    if _recognize_owner(payload) == "retail":
        payload, allocation_receipt, code_va, edits = _apply_owner(payload)
        labels += [dict(label=name, va=hex(va), before=old.hex(), after=new.hex()) for name, va, old, new in edits]
    if _sim_state(payload) == "retail":
        payload = _apply_sim(payload)
        labels += [dict(label=name, va=hex(va), before=old.hex(), after=new.hex()) for name, va, old, new in SIM_EDITS]
    result = payload
    require(_recognize(result) == "applied" and space.status(result) == "applied",
            "Pass-protection postcondition failed")
    code_va = code_va if code_va is not None else allocation(result)["va"]
    return result, dict(common, status="applied",
                        before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=space.count_differing_bytes(before, result), file_growth=len(result) - len(before),
                        allocation=allocation_receipt, code_va=hex(code_va), edits=labels,
                        simulated_sacks=True,
                        reservations=[r for r in space.reservations(result) if r["owner"] == OWNER])


__all__ = ["OWNER", "REQUESTS", "GUARDS", "HOOK", "apply", "status", "read_settings",
           "allocation", "code_for", "sites", "sim_sites", "SIM_EDITS", "SIM_GUARDS", "DELAY_BASE", "DELAY_SLOPE", "DELAY_MIN", "DELAY_MAX"]

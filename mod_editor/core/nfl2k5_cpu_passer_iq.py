"""CPU quarterbacks throw on time and check down. EXPERIMENTAL / UNWITNESSED.

b780 a-passer (research: b77_session/reports/b780_r1-cpu_RESEARCH.md, design A1). Players asked for CPU quarterbacks
who check the ball down to the back and do not hold it for four seconds (Ju3tinYT 10/14 and 10/29, PGaither84 9/04).
The throwing motion is not the problem: every short and medium throw leaves the hand 1/3 s after the throw starts.
The wait comes from the CPU passer task 0x19BB60 and its read grid. Three things change, CPU passers only:

* **Checkdowns** (one hook, 0x199F23). Every target point of the CPU QB's read grid is scored by 0x19A7E0, whose field
  terms 0x199CE0 add the short-throw curve 0x50C494 of the distance from the QB to the target: -0.5 at 4 yd rising to
  0 at 15 yd. A wide-open back 5 yd away therefore scores about 0.82, below every retail pass threshold (0.975-1.2) and
  below the CPU QB skill tiers of average to elite starters (0.92-1.0), so a starter never checks down until he is
  about to be hit. The hook multiplies that one term by a factor: 1 until FADE_START seconds after the snap (or sooner,
  once the QB's first read cycle completed: the read advance 0x199100 raises 0xBE47FC when his read wraps back to
  the first row), then falling FADE_RATE per second to FLOOR, and FLOOR at once while the pocket pressure 0xBE47C0 is
  PRESSURE or more. Early in the play he still looks downfield; late in the play, or under pressure, an open back or
  tight end underneath becomes a valid target (the same back scores about 1.18 at the floor). Targets 15 yd or more
  from the QB keep the retail score exactly (the term is 0 there); the picker, its random term, the thresholds and
  every defender term are untouched. Rows are rescored when the QB looks at them (one read at a time), so the factor
  applies when he comes to the back in his progression; a back he looked at early keeps his early score until then.
* **Pump fakes** (three operands in 0x19BB60). A pump fake locked out every throw for 1.5 s (the holdoff 0xBE47EC is
  set to now + 1.5 at 0x19BFCF and 0x19C1C0; the throw press 0x19BAE0 and the forced throw 0x19C313 wait for it),
  whoever came open. The two adds now read the retail .rdata float 0.6 at 0x4EFE14 (81 readers, no writer) instead of
  the shared 1.5 at 0x4E6D0C, and the per-tick pump roll under heavy pressure is 1 in 60 instead of 1 in 20 (0x19C194).
* **Faster reads** (data, the read dwell curve 0x50C548 of Pass Read Coverage, read by 0x199100 and by the CPU QB reads
  owner's read window): 0 -> 1.0 s, 0.3 -> 0.8, 0.5 -> 0.6, 0.9 -> 0.35, 1.0 -> 0.25 (retail 2.0 / 1.0 / 0.5 / 0.4 /
  0.2). Weak readers no longer stare at one receiver for up to 2 s; every QB has time for about three reads inside
  the NFL's 2.4 s average pocket time.

Human passing, ball flight, catching and the defense are not changed. The owner is a late allocator owner (256 RX bytes,
16 RW bytes of per-play state) and composes with the CPU QB reads and CPU scrambles owners, whose verified hooks in the
QB tick it normalizes (and they normalize its sites). Settings are build-time only; turning it off needs a rebuild
from a clean base.
"""
from __future__ import annotations

import hashlib
import struct

OWNER = "nfl2k5_cpu_passer_iq"
CODE_SIZE, DATA_SIZE = 256, 16
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16))
BUILD_CAPTION = "CPU quarterbacks throw on time and check down (experimental)"
HELP_TEXT = ("EXPERIMENTAL / UNWITNESSED. CPU quarterbacks only. Early in a play the CPU quarterback still looks "
             "downfield; once he has been through his reads, after about two seconds, or as soon as the pocket "
             "collapses, an open back or tight end underneath becomes a real option, so he checks the ball down "
             "instead of holding it and taking the sack. A pump fake now stops him from throwing for 0.6 seconds "
             "instead of 1.5, he pump fakes less often under pressure, and every quarterback moves from one receiver "
             "to the next faster (weak readers the most). Downfield reads, the defense and human play are unchanged.")

# Tuning. The template holds the same values; code_for() writes these.
FADE_START = 2.0     # seconds after the snap; sooner when the first read cycle completed
FADE_RATE = 0.8      # factor lost per second after the fade starts (1.0 -> FLOOR in one second)
FLOOR = 0.2          # the short-throw penalty never drops below this share of retail (the checkdown-rate lever)
PRESSURE = 0.7       # pocket pressure (0xBE47C0) at which the factor drops to FLOOR at once
PUMP_HOLDOFF = 0.6   # seconds a pump fake blocks the throw (retail 1.5)
PUMP_CHANCE = 60     # one pump fake roll in N per QB tick under heavy pressure (retail 20)

HOOK = ("checkdown", 0x00199F23, bytes.fromhex("e8b86b0100"), "short")
SYMBOLS = dict(lerp=0x001B0AE0)
RETAIL_HOLDOFF_VA = 0x004E6D0C   # .rdata 1.5, shared by 112 readers
HOLDOFF_VA = 0x004EFE14          # .rdata 0.6, the compiler's constant (81 readers, never written)


def _curve(xs, ys):
    return struct.pack("<I", len(xs)) + b"".join(struct.pack("<ff", x, y) for x, y in zip(xs, ys))


DWELL_CURVE_VA = 0x0050C548
DWELL_X = (0.0, 0.3, 0.5, 0.9, 1.0)
RETAIL_DWELL_Y = (2.0, 1.0, 0.5, 0.4, 0.2)
DWELL_Y = (1.0, 0.8, 0.6, 0.35, 0.25)
RETAIL_DWELL_CURVE = _curve(DWELL_X, RETAIL_DWELL_Y)
DWELL_CURVE = _curve(DWELL_X, DWELL_Y)
EDITS = (
    ("pump_holdoff_target", 0x0019BFD1, struct.pack("<I", RETAIL_HOLDOFF_VA), struct.pack("<I", HOLDOFF_VA)),
    ("pump_holdoff_open", 0x0019C1C2, struct.pack("<I", RETAIL_HOLDOFF_VA), struct.pack("<I", HOLDOFF_VA)),
    ("pump_chance", 0x0019C194, struct.pack("<I", 20), struct.pack("<I", PUMP_CHANCE)),
    ("read_dwell_curve", DWELL_CURVE_VA, RETAIL_DWELL_CURVE, DWELL_CURVE),
)
# The CPU scramble owner's hook inside the QB tick (normalized when that owner is verified applied).
CPU_SCRAMBLES_HOOK = (0x0019C36C, bytes.fromhex("d80d6c694e00"))
# Everything entered or relied on, retail; the QB tick's neighbor hooks (CPU QB reads, CPU scrambles) and this owner's
# own sites are normalized before hashing.
GUARDS = (
    (0x00199CE0, 603, "d7035f0bccd579f437e185ea0f218feff98621722cbf5173b2ded7ab452520b9"),   # field terms (EBP = QB)
    (0x0019A7E0, 195, "c090d31a5529236597a83349d2b3955114af7099891e69a45eadc6aa66f07989"),   # point score (its only caller)
    (0x0050C494, 20, "b19639691c2c37c110594c6ebd32971fc67f35f6b8ce4818236eeb71ff500b01"),    # short-throw curve
    (0x0019BB60, 2510, "fdc6a3131d3475c3583cbbc91857d24c02599ef3b29772f8b3e9dedd15cb7aef"),  # QB tick (pump paths)
    (0x00199100, 185, "607067b3fa227818ffc1b4499a806a48743377994ba9c44a430fa81e850dc928"),   # read advance (0xBE47FC)
    (0x001B0AE0, 124, "85257e0d17fc30f87b44015e57a7951be3785ef634995aafaec65c9f5fc2bc7c"),   # curve interpolator
    (HOLDOFF_VA, 4, "8e215ece122cf70ebe3556a0318fa6c395d1766375c3edc080967e4a09592401"),     # float 0.6
)
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError)


class CpuPasserIqError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise CpuPasserIqError(message)


def allocations(payload):
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    require(len(rows) == 2 and {(r["kind"], r["size"], r["align"]) for r in rows} ==
            {(k, n, a) for _, k, n, a in REQUESTS}, "Missing or foreign CPU passer allocation")
    return {r["kind"]: r for r in rows}


def code_for(code_va, data_va):
    from . import nfl2k5_cpu_passer_iq_code as assembly
    symbols = dict(SYMBOLS, code=code_va, state=data_va)
    out = bytearray(assembly.CODE)
    for off, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", out, off)[0]
        if kind == 2:
            target -= code_va + off
        struct.pack_into("<I", out, off, target & 0xFFFFFFFF)
    for label, value in (("k_pressure", PRESSURE), ("k_start", FADE_START), ("k_rate", FADE_RATE),
                         ("k_floor", FLOOR), ("k_one", 1.0)):
        struct.pack_into("<f", out, assembly.LABELS[label], value)
    require(len(out) <= CODE_SIZE, "CPU passer code exceeds its RX allocation")
    return bytes(out).ljust(CODE_SIZE, b"\xcc")


def sites(code_va=0):
    """Every edit (label, va, retail bytes, installed bytes): the hook, then the in-place operands and the curve."""
    from . import nfl2k5_cpu_passer_iq_code as assembly
    name, va, before, label = HOOK
    call = b"\xe8" + struct.pack("<i", code_va + assembly.LABELS[label] - va - 5)
    return [(name, va, before, call)] + list(EDITS)


def _owned(payload):
    """(applied, edits) from this owner's own bytes, without its neighbors or prerequisites."""
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    present = any(r["owner"] == OWNER for r in space.layout(payload)["allocations"])
    owned = allocations(payload) if present else None
    edits = sites(owned["code"]["va"] if owned else 0)
    states = set()
    for _name, va, before, after in edits:
        raw = image.read(va, len(before))
        states.add("retail" if raw == before else "applied" if owned and raw == after else "foreign")
    if owned:
        c, d = owned["code"]["va"], owned["data"]["va"]
        require(image.read(d, DATA_SIZE) == bytes(DATA_SIZE), "Foreign initialized CPU passer state")
        raw = image.read(c, CODE_SIZE)
        states.add("retail" if raw == b"\xcc" * CODE_SIZE else "applied" if raw == code_for(c, d) else "foreign")
    require(states in ({"retail"}, {"applied"}), "Foreign or mixed CPU passer sites/code")
    applied = states == {"applied"}
    return applied, (edits if applied else [])


def normalized_sites(payload):
    """For neighbor recognizers: this owner's verified sites, or [] when every one of them is retail."""
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    if all(image.read(va, len(before)) == before for _, va, before, _ in sites(0)):
        return []
    applied, edits = _owned(payload)
    require(applied, "Foreign CPU passer neighbor")
    return edits


def _recognize(payload):
    from . import nfl2k5_cpu_qb_reads as reads
    from . import nfl2k5_cpu_scrambles as scrambles
    from .nfl2k5_cave_oracle import XbeImage
    applied, edits = _owned(payload)
    image = XbeImage(payload)
    neighbors = [(name, va, before, None) for name, va, before, _after in reads.normalized_sites(payload)]
    va, before = CPU_SCRAMBLES_HOOK
    if image.read(va, len(before)) != before:
        require(scrambles.status(payload) == "applied", "Foreign CPU scramble neighbor in the QB tick")
        neighbors.append(("cpu_scrambles_threshold", va, before, None))
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for _, at, before, _ in edits + neighbors:
            if va <= at and at + len(before) <= va + size:
                content[at - va:at - va + len(before)] = before
        require(hashlib.sha256(content).hexdigest() == digest, f"Foreign CPU passer prerequisite at {va:#x}")
    return "applied" if applied else "retail"


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
        raise CpuPasserIqError(f"foreign/mixed CPU passer input: {exc}") from exc
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False)
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    before = payload
    allocation_receipt = {}
    if not any(r["owner"] == OWNER for r in space.layout(payload)["allocations"]):
        if space.status(payload) == "retail":
            payload, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
        else:
            require(space.is_scaleout(payload), "CPU quarterbacks throw on time needs the scale-out allocator")
            payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
    owned = allocations(payload)
    c, d = owned["code"]["va"], owned["data"]["va"]
    payload, _ = space.install_code(payload, OWNER, code_for(c, d))
    edits = sites(c)
    image = XbeImage(payload)
    buf = bytearray(payload)
    for _, va, old, new in edits:
        off = image.offset(va, len(old))
        require(bytes(buf[off:off + len(old)]) == old, f"CPU passer site {va:#x} is not retail")
        buf[off:off + len(old)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(_recognize(result) == "applied", "CPU passer postcondition failed")
    require(space.status(result) == "applied", "CPU passer allocator postcondition failed")
    return result, dict(common, status="applied",
                        before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=space.count_differing_bytes(before, result), file_growth=len(result) - len(before),
                        allocation=allocation_receipt, code_va=hex(c), state_va=hex(d),
                        tuning=dict(fade_start=FADE_START, fade_rate=FADE_RATE, floor=FLOOR, pressure=PRESSURE,
                                    pump_holdoff=PUMP_HOLDOFF, pump_chance=PUMP_CHANCE, read_dwell=list(DWELL_Y)),
                        edits=[dict(label=name, va=hex(va), before=old.hex(), after=new.hex()) for name, va, old, new in edits],
                        reservations=[r for r in space.reservations(result) if r["owner"] == OWNER])


def main(argv=None):
    """Status of a default.xbe, or write the owner to a NEW file (an existing path is never overwritten)."""
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=BUILD_CAPTION + ". " + HELP_TEXT)
    parser.add_argument("--xbe", required=True, type=Path)
    parser.add_argument("--apply", action="store_true", help="write the owner to a new XBE")
    parser.add_argument("--output", type=Path, help="new file only; never overwrite an existing path")
    args = parser.parse_args(argv)
    if args.apply != (args.output is not None):
        parser.error("--apply and --output must be provided together")
    try:
        with args.xbe.open("rb") as stream:
            payload = stream.read(16 * 1024**2 + 1)
        if len(payload) > 16 * 1024**2:
            raise ValueError("Expected a supported executable, not a disc or archive")
        state = status(payload)
        if state == "foreign":
            raise ValueError("Foreign or mixed CPU passer bytes")
        if args.apply:
            result, receipt = apply(payload)
            created = False
            try:
                with args.output.open("xb") as stream:
                    created = True
                    stream.write(result)
            except BaseException:
                if created:
                    args.output.unlink(missing_ok=True)
                raise
            print(json.dumps(receipt, indent=2))
            return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps({"status": state, "experimental": True, "runtime_witnessed": False, "requests": REQUESTS,
                      "edits": [dict(label=name, va=hex(va), retail=old.hex()) for name, va, old, _ in sites(0)]},
                     indent=2))
    return 0


__all__ = ["OWNER", "REQUESTS", "CODE_SIZE", "DATA_SIZE", "HOOK", "EDITS", "GUARDS", "SYMBOLS", "BUILD_CAPTION",
           "HELP_TEXT", "FADE_START", "FADE_RATE", "FLOOR", "PRESSURE", "PUMP_HOLDOFF", "PUMP_CHANCE", "DWELL_X",
           "DWELL_Y", "RETAIL_DWELL_Y", "apply", "status", "read_settings", "normalized_sites", "allocations",
           "code_for", "sites", "main"]


if __name__ == "__main__":
    raise SystemExit(main())

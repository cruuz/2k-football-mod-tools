"""Defenders dive only for balls they can reach, USA retail. EXPERIMENTAL / UNWITNESSED.

A defender who reacts to a throw (behavior 37, the reaction task 0x2E7240) asks the ball-play decision 0x1F52C0 every
tick. Retail returns 2, "play the ball" (action 0x61: the leap, dive or swat), whenever the ball's path 0.3 to 0.6 s
ahead passes within 3 yards (0x4EDD28) of where he stands now and below his reach. It never looks at which way he is
moving or at the receiver: a corner 2 yards beside the throw who is running the other way still leaps, and a defender
behind the receiver leaps at a ball the receiver catches first. (The 0.6 s projection of his own run in that routine
only feeds a flag that is always zero.) Defenders break on the thrown ball (``nfl2k5_db_ball_play``) sends reactors
at full speed, so they enter that 3-yard window sooner and from farther away.

This owner changes only the 3-yard test (one call at 0x1F56FF), for CPU defenders:

* within a yard, or not CPU controlled, or a degenerate ball path: retail;
* receiver first: no leap when the closest point is more than 0.03 s of the ball's flight past the stored catch point
  (0xBF0DF0, valid flag 0xBF0E08, intended receiver [0xE3C000]), because the receiver gets the ball first;
* reach: beyond 1.5 yards he must be closing on the ball fast enough to cover the rest before it arrives
  (distance x (distance - 1.5 yd) < his velocity . (closest point - him) x the ball's time to that point).

When the test says no, the decision returns 0: he keeps running to his reaction point (the catch point with
``db_ball_play``) and the decision runs again next tick. The catch try within a yard (result 3), the reaction lottery,
the perception filter that decides who reacts, catching and interceptions are untouched. Settings are build-time only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

OWNER = "nfl2k5_dive_window"
CODE_SIZE = 416
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
BUILD_CAPTION = "Defenders leap only for balls they can reach (experimental)"
HELP_TEXT = ("EXPERIMENTAL / UNWITNESSED. A CPU defender who reacts to a pass no longer leaps or dives at a ball that "
             "will pass more than a yard and a half from him unless he is already moving toward it fast enough to get "
             "there, and no longer leaps at a ball the receiver will catch before it reaches him. He keeps running to "
             "the ball and plays the receiver at the catch instead. Catch tries within a yard are unchanged. Works "
             "with or without Defenders break on the thrown ball.")
HOOK = ("dive_window", 0x001F56FF,
        bytes.fromhex("d9442418" "d81d28dd4e00" "dfe0" "f6c405" "0f8abbfeffff"))   # fld; fcomp [3 yd]; fnstsw; test; jp
RETURN_ZERO = 0x001F55CF            # xor eax, eax; the decision's result 0 exit
SYMBOLS = {}
GUARDS = (
    (0x001F52C0, 1246, "8b56b7442d9e319dafed714f25aec04c2dab061d6f33ee5e2a1dadc12bfc7400"),   # ball-play decision
    # the reaction task's call to it and its result handling (db_ball_play's throttle push at 0x2E7462 is outside)
    (0x002E7272, 364, "f5679cff93bfa069f7f917e7aa57decb6658752beede9ff9587887f81821397e"),
    (0x001CC820, 618, "a13d11fe0a5d6559fb8c7268d751d3ba0e95690d8a223808e4ea9bb34267c90b"),    # ball predictor
    (0x001ADE10, 383, "11259352ee89977b3b173bea0656a2f61d93dc2eb0066547cf2b743f2d08c363"),    # closest point
    (0x001F3190, 52, "13c229b617a4d679543cb44c44c14f7a53fce4c26df3ad39b68e7d4f0a1f045a"),     # horizontal distance
    (0x004EDD28, 4, "49f300df7b25775c5f74fe898b1f86b0d96646ead4d9661ecdba6ff7029b3ca7"),      # 274.32 (3 yd)
    (0x004E72B8, 4, "f27e5089bb42d266a0b712a923da95489c291399ab2b75d45d7dbd22ffbae4de"),      # 91.44 (1 yd)
    (0x004EFE0C, 4, "45a6d738a7607576d3fe0862200bc67b10c12d5ed74167b4d5d5a708974c0f32"),      # 0.3
    (0x004E4180, 4, "df3f619804a92fdb4057192dc43dd748ea778adc52bc498ce80524c014b81119"),      # 0.0
)
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError)


class DiveWindowError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise DiveWindowError(message)


def allocation(payload):
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    require(len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"]) == ("code", CODE_SIZE, 16),
            "Missing or foreign defender dive-window allocation")
    return rows[0]


def code_for(code_va):
    from . import nfl2k5_dive_window_code as assembly
    symbols = dict(SYMBOLS, code=code_va)
    out = bytearray(assembly.CODE)
    for off, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", out, off)[0]
        if kind == 2:
            target -= code_va + off
        struct.pack_into("<I", out, off, target & 0xFFFFFFFF)
    require(len(out) <= CODE_SIZE, "Defender dive-window code exceeds its RX allocation")
    return bytes(out).ljust(CODE_SIZE, b"\xcc")


def sites(code_va=0):
    """call window; test eax, eax; jz 0x1F55CF (result 0); NOP to the end of the replaced 21 bytes."""
    from . import nfl2k5_dive_window_code as assembly
    name, va, before = HOOK
    call = b"\xe8" + struct.pack("<i", code_va + assembly.LABELS["window"] - va - 5)
    jz = b"\x0f\x84" + struct.pack("<i", RETURN_ZERO - (va + 5 + 2 + 6))
    return [(name, va, before, (call + b"\x85\xc0" + jz).ljust(len(before), b"\x90"))]


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
    require(states in ({"retail"}, {"applied"}), "Foreign or mixed defender dive-window site/code")
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for _, at, before, _ in edits:
            if va <= at and at + len(before) <= va + size:
                content[at - va:at - va + len(before)] = before
        require(hashlib.sha256(content).hexdigest() == digest, f"Foreign defender dive-window prerequisite at {va:#x}")
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
        raise DiveWindowError(f"foreign/mixed defender dive-window input: {exc}") from exc
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False)
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    before = payload
    allocation_receipt = {}
    if not any(r["owner"] == OWNER for r in space.layout(payload)["allocations"]):
        if space.status(payload) == "retail":
            payload, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
        else:
            require(space.is_scaleout(payload), "Defender dive window needs the scale-out allocator")
            payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
    code_va = allocation(payload)["va"]
    payload, _ = space.install_code(payload, OWNER, code_for(code_va))
    edits = sites(code_va)
    image = XbeImage(payload)
    buf = bytearray(payload)
    for _, va, old, new in edits:
        off = image.offset(va, len(old))
        require(bytes(buf[off:off + len(old)]) == old, f"Defender dive-window site {va:#x} is not retail")
        buf[off:off + len(old)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(_recognize(result) == "applied" and space.status(result) == "applied",
            "Defender dive-window postcondition failed")
    return result, dict(common, status="applied",
                        before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=space.count_differing_bytes(before, result), file_growth=len(result) - len(before),
                        allocation=allocation_receipt,
                        edits=[dict(label=name, va=hex(va), before=old.hex(), after=new.hex()) for name, va, old, new in edits],
                        reservations=[r for r in space.reservations(result) if r["owner"] == OWNER])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
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
            raise ValueError("Foreign or mixed defender dive-window bytes")
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
                      "hook": hex(HOOK[1])}, indent=2))
    return 0


__all__ = ["OWNER", "REQUESTS", "GUARDS", "HOOK", "apply", "status", "read_settings", "allocation", "code_for", "sites",
           "main"]


if __name__ == "__main__":
    raise SystemExit(main())

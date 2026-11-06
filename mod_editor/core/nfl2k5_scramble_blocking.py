"""Receivers and backs block for a quarterback who runs past the line, USA retail. EXPERIMENTAL.

Player request (Ptruji, Discord 10/23, +4): "It would be nice if when a qb scrambles the receivers and rbs would block
defenders down field." Research: b77_session/reports/b780_r5-coverage_RESEARCH.md section 2.8 (job CV7, design G2).

Retail (static disassembly of the USA executable and native Unicorn replays, b780 cv7 report): nothing tells the
receivers that the play changed when the quarterback runs. The CPU passer task 0x198540 makes him a ball carrier a
yard short of the line (0x198170, then 0x2E36F0, which posts no event); a human quarterback keeps his passer task.
The receivers' play script is still on its route legs, so they finish their routes and then stand.

This owner hooks the AI tick 0x214FC0 (its first instruction, ``mov eax, [0xE602B8]``; one call per simulation step,
before any player's task runs). While a play is live (state 14) on a down or a try (phase 4 or 3), a player holds the
ball (ball state 2), the holder is a quarterback (field role byte 0, the game's own slide test), no forward pass has
been thrown on the play (``[[0xE602EC]+0x1B0]``, the thrower the pass release 0xB6700 stores) and he is at least half
a yard past the line of scrimmage in his team's direction (the 0x198170 rule), every CPU-controlled tight end, wide
receiver, halfback or fullback of his team (field roles 8 to 11) who is not already in a block task (the game's own
test 0x23ABA0, task+0x90 == 5) and not engaged with another player (0x231EE0) gets the game's drive block, exactly
the way the game converts a blocker mid-play (0x23A010 and 0x23B040): clear the script wait bits 0x4000 / 0x40000 of
AI+0x420 and the block kind bits of L+0x18C, then 0x23F450 (block type 0, drive; (0, 0, 1, 0, 182.88, the team's
upfield heading, +inf), the arguments 0x23A010 uses). Each formation slot converts at most once a play (a 16-byte
state word, cleared whenever the play is not live), so a block the game itself ends (the runner passed him,
0x23AA40) is never re-armed. Human and CPU quarterbacks get the same rule (coordinator default 11/02).

One blocker per man: the game's own selector 0x2FAFF0 picks each target (it is ball-aware: no defender more than 3
yards behind the ball). When that man is already the target of a teammate's block task (task+0x40), the previous
target is kept if he is still free, else the nearest defender nobody has (not more than 3 yards behind the ball),
else the game's choice stands. The same check runs after every target refresh of these blocks: the block manager
0x23DBE0 calls the task's refresh pointer (task+0xA0, ECX = player), which these tasks point at the owner's
``refresh`` (the game's refresh 0x23CD60 first). No other player's block, and nothing on defense, changes.

Not changed: the quarterback, linemen, players already blocking, human-controlled teammates, plays with a forward
pass, kicks and returns. A quarterback who crosses the line and steps back keeps his receivers blocking (they never
go back to their routes on that play).
"""
from __future__ import annotations

import hashlib
import struct

OWNER = "nfl2k5_scramble_blocking"
CODE_SIZE = 816                   # 808 bytes of code and constants, rounded to the 16-byte alignment
DATA_SIZE = 16                    # the per-play slot mask (one dword) and padding
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16))
BUILD_CAPTION = "Receivers block for a scrambling QB (test)"
HELP_TEXT = ("EXPERIMENTAL. Off in every preset: a feel test for Noah. Retail: when the quarterback tucks the ball "
             "and runs past the line, his receivers keep running their routes. Patch: once a quarterback carrying the "
             "ball is half a yard past the line of scrimmage on a play with no pass thrown, his tight ends, wide "
             "receivers and backs who are not already blocking turn and block downfield, one blocker per defender, the "
             "way they block on a running play. Human and CPU quarterbacks get the same rule. Linemen, players already "
             "blocking and the defense are unchanged.")

HOOK = ("ai_tick", 0x00214FC0, bytes.fromhex("a1b802e600"), "tick")   # mov eax, [0xE602B8]
SYMBOLS = dict(installer=0x0023F450, native_refresh=0x0023CD60, engaged=0x00231EE0)
GUARDS = (
    (0x0023F450, 2642, "9989386b2c98f6fed17bba386f8a59aaf6f4cace72dc7400c17922d55b07ed35"),   # block installer
    (0x0023CD60, 259, "39f55d7d963b0dc7d55cf1311bfc130921f70c0276f480fa420226a805dc3c8b"),    # drive-block refresh
    (0x00231EE0, 26, "8418306dab1192c64de863033f5cc270da61b909227d6edd895b231e08db0ea4"),     # engaged-pair test
    (0x0023DBE0, 459, "5d611d2233bcb3700b53d41387ffda81417874d9246c85f564264edb02c7e2fc"),    # block manager (task+0xA0)
    (0x0023ABA0, 15, "7570626c576198fcafe2ae28cf6d02425467ce7145ee65d5d6bde6af27170de3"),     # block task test
    (0x00214FC0, 40, "347058da8f17c3190b3f255a58c76292ab6d472c6fb091a4b44290dc326b7ede"),     # AI tick head
    (0x004E4180, 4, "df3f619804a92fdb4057192dc43dd748ea778adc52bc498ce80524c014b81119"),      # 0.0f
)
# Pinned by tests: the field roles that convert (8 TE, 9 WR, 10 HB, 11 FB; nfl2k5_play_codec.POSITION_KINDS) and the
# distance past the line (half a yard, cm).
CONVERTED_ROLES = (8, 9, 10, 11)
PAST_LINE_CM = 45.72
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError, OSError)


class ScrambleBlockingError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise ScrambleBlockingError(message)


def code_for(code_va, state_va):
    """The relocated owner code: the committed template (tools/nfl2k5_scramble_blocking.S) at ``code_va``, its state
    word at ``state_va``."""
    from . import nfl2k5_scramble_blocking_code as assembly
    symbols = dict(SYMBOLS, code=code_va, state=state_va)
    out = bytearray(assembly.CODE)
    for off, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", out, off)[0]
        if kind == 2:
            target -= code_va + off
        struct.pack_into("<I", out, off, target & 0xFFFFFFFF)
    require(len(out) <= CODE_SIZE, f"scramble blocking code exceeds its allocation ({len(out)} > {CODE_SIZE})")
    return bytes(out).ljust(CODE_SIZE, b"\xcc")


def labels():
    from . import nfl2k5_scramble_blocking_code as assembly
    return dict(assembly.LABELS)


def sites(code_va=0):
    """Hook edits (label, va, retail, new): the AI tick's first instruction becomes a call into ``tick``."""
    name, va, before, label = HOOK
    return [(name, va, before, b"\xe8" + struct.pack("<i", code_va + labels()[label] - va - 5))]


def _allocations(payload):
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    code = [r for r in rows if r["kind"] == "code"]
    data = [r for r in rows if r["kind"] == "data"]
    require(len(rows) == 2 and len(code) == 1 and (code[0]["size"], code[0]["align"]) == (CODE_SIZE, 16),
            "Missing or foreign scramble blocking code allocation")
    require(len(data) == 1 and (data[0]["size"], data[0]["align"]) == (DATA_SIZE, 16),
            "Missing or foreign scramble blocking state allocation")
    return code[0], data[0]


def allocation(payload):
    """The code allocation (the receipt shape other late owners use)."""
    return _allocations(payload)[0]


def _recognize(payload):
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    present = any(r["owner"] == OWNER for r in space.layout(payload)["allocations"])
    code = data = None
    if present:
        code, data = _allocations(payload)
    edits = sites(code["va"] if code else 0)
    states = set()
    for _name, va, before, after in edits:
        raw = image.read(va, len(before))
        states.add("retail" if raw == before else "applied" if code and raw == after else "foreign")
    if code:
        raw = image.read(code["va"], CODE_SIZE)
        expected = code_for(code["va"], data["va"])
        states.add("retail" if raw == b"\xcc" * CODE_SIZE else "applied" if raw == expected else "foreign")
        require(image.read(data["va"], DATA_SIZE) == bytes(DATA_SIZE), "Foreign initial scramble blocking state")
    require(states in ({"retail"}, {"applied"}), "Foreign or mixed scramble blocking site/code")
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for _, at, before, _ in edits:
            if va <= at and at + len(before) <= va + size:
                content[at - va:at - va + len(before)] = before
        require(hashlib.sha256(content).hexdigest() == digest, f"Foreign scramble blocking prerequisite at {va:#x}")
    return next(iter(states))


def status(payload):
    try:
        return _recognize(payload)
    except _ERRORS:
        return "foreign"


def apply(payload):
    """Install, or replay an identical installation."""
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_bump_strength import _sections, section_digest
    from .nfl2k5_cave_oracle import XbeImage
    try:
        state = _recognize(payload)
    except _ERRORS as exc:
        raise ScrambleBlockingError(f"foreign/mixed scramble blocking input: {exc}") from exc
    common = dict(owner=OWNER, experimental=True)
    if state == "applied":
        code, data = _allocations(payload)
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[],
                             code_va=hex(code["va"]), state_va=hex(data["va"]))
    before = payload
    allocation_receipt = {}
    # A full build allocates this owner with the selected request set (nfl2k5_throw_tuning) before this step installs
    # the code; reuse that allocation (the sim realism owner's rule).
    if not any(r["owner"] == OWNER for r in space.layout(payload)["allocations"]):
        if space.status(payload) == "retail":
            payload, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
        else:
            require(space.is_scaleout(payload), "Scramble blocking needs the scale-out allocator")
            payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
    code, data = _allocations(payload)
    payload, _ = space.install_code(payload, OWNER, code_for(code["va"], data["va"]))
    edits = sites(code["va"])
    image = XbeImage(payload)
    buf = bytearray(payload)
    for _name, va, old, new in edits:
        off = image.offset(va, len(old))
        require(bytes(buf[off:off + len(old)]) == old, f"scramble blocking site {va:#x} is not retail")
        buf[off:off + len(old)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(_recognize(result) == "applied" and space.status(result) == "applied",
            "scramble blocking postcondition failed")
    return result, dict(common, status="applied", code_va=hex(code["va"]), state_va=hex(data["va"]),
                        before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=space.count_differing_bytes(before, result), file_growth=len(result) - len(before),
                        allocation=allocation_receipt,
                        edits=[dict(label=name, va=hex(va), before=old.hex(), after=new.hex()) for name, va, old, new in edits],
                        reservations=[r for r in space.reservations(result) if r["owner"] == OWNER])


def main(argv=None):
    """``python3 -m mod_editor.core.nfl2k5_scramble_blocking source.xbe new-copy.xbe``: write a patched copy."""
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description="Receivers block for a scrambling QB (experimental test).")
    parser.add_argument("source", type=Path, help="a user-owned USA default.xbe (retail or a verified scale-out image)")
    parser.add_argument("output", type=Path, help="the new copy to write (never the source)")
    args = parser.parse_args(argv)
    if args.output.resolve() == args.source.resolve():
        parser.error("write a new copy; the source is never changed")
    patched, receipt = apply(args.source.read_bytes())
    args.output.write_bytes(patched)
    print(json.dumps({k: v for k, v in receipt.items() if k != "reservations"}, indent=2))
    return 0


__all__ = ["OWNER", "REQUESTS", "CODE_SIZE", "DATA_SIZE", "HOOK", "GUARDS", "SYMBOLS", "CONVERTED_ROLES", "PAST_LINE_CM",
           "BUILD_CAPTION", "HELP_TEXT", "code_for", "labels", "sites", "allocation", "status", "apply", "main"]


if __name__ == "__main__":
    raise SystemExit(main())

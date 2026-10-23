"""Franchise: CPU clubs keep their stars when they clear cap room, USA retail. EXPERIMENTAL.

Report (b778 fa1, Noah's MyNFL3 on v0.6.1): Mahomes, Kittle, Stanley and eight other veterans were released
in one sweep before the 2027 preseason and sat in free agency all season. Noah (10/22): "make it so teams are
less likely to cut someone with a high overall, even if it saves them a lot of cap ... the Chiefs wouldn't cut
Mahomes".

The CPU release paths of a franchise (static disassembly of the USA executable, b778 fa1 report):

- 0x2BFAF0, the veteran cap cut. The offseason advance calls it for every club in stage 6 (0x247FE2..0x248002,
  after free agency and the draft) with years pro >= 10 and 210%. While payroll + 6000 >= cap it releases a
  veteran whose base salary (0xE6380) exceeds 2.1 x 0x2BD440(player, 0, 1, 1, years left) and whose dead money
  (0x13ED00) is below salary x years left. It weighs cap savings only: overall enters only through the value.
- 0x2BFBE0 (the 2026 economy's reconcile, at the rollover and when a club is over the cap) and 0x2BF9A0 (the cut
  to 53) release the lowest-rated players first and keep every position filled, so a star is never their target.
- 0x322790 decides whether an expiring contract is renewed: rating + 0.05 is the chance, and a CPU club renews a
  player rated over 0.87 even without room. Expiring contracts are not cuts and are left alone.

This owner hooks the veteran cap cut's value call (``call 0x2BD440`` at 0x2BFB67) with a call into a small cave:
a player whose native rating (0x246D80, edx=1, overall / 100) is above STAR_OVERALL, or a quarterback above
QB_OVERALL, is valued at 65535, which no salary can exceed 2.1 times, so the cut passes him by. Everyone else
goes on to 0x2BD440 with the caller's own arguments (the franchise economy passes market value since b778 fa1).
Clubs over the cap then shed depth and low-overall players through the reconcile, never their stars; older
declining veterans below the thresholds can still be released by the retail rule. Ratings are never changed.
"""
from __future__ import annotations

import hashlib
import struct

OWNER = "nfl2k5_star_retention"
CODE_SIZE = 64
DATA_OFFSET = CODE_SIZE - 8
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
STAR_OVERALL = 85          # any position: about 280 players of the v0.6.1 league (9 a club)
QB_OVERALL = 75            # quarterbacks: about 36 (the starters)
BUILD_CAPTION = "Franchise: CPU clubs keep their stars (experimental)"
HELP_TEXT = ("EXPERIMENTAL. When a CPU club clears cap room before the preseason, it no longer releases a player "
             f"rated over {STAR_OVERALL} overall or a quarterback over {QB_OVERALL}, however much money that would "
             "save. Clubs over the cap shed depth and low-overall players first; older declining veterans below "
             "those ratings can still be released. Expiring contracts, retirements and ratings are unchanged.")
RATING = 0x00246D80        # fastcall (player, edx=1): float overall / 100
VALUE = 0x002BD440         # the value the veteran cut compares with
HOOK = ("veteran_cut_value", 0x002BFB67, bytes.fromhex("e8d4d8ffff"))   # call 0x2BD440 inside 0x2BFAF0
ECONOMY_SURPLUS = (0x002BFB61, bytes.fromhex("6a01"), bytes.fromhex("6a00"))  # franchise economy revision 2
GUARDS = (
    (0x002BFAF0, 236, "beaa2d14440a4f43aee883aef9d3682d00204417226488de04181f61478cae59"),   # veteran cap cut
    (0x00247FD7, 62, "a1dfd9babaf3039cf3611dc8f3c74b6eb9febbee3bb19d8cedf507880cfc05e1"),    # stage-6 caller
)
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError, OSError)


class StarRetentionError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise StarRetentionError(message)


def code_for(code_va, star=STAR_OVERALL, qb=QB_OVERALL):
    """The cave (CODE_SIZE bytes; the two float thresholds in its last 8). Called in place of 0x2BD440 with the
    same registers and stack (ecx player, edx, three stack arguments, ret 0xC)."""
    from .nfl2k5_draft_ai import _Asm
    require(type(star) is int and type(qb) is int and 0 < qb <= 100 and 0 < star <= 100, "thresholds")
    a = _Asm(code_va)
    a.b("51")                                                    # push ecx
    a.b("52")                                                    # push edx
    a.b("ba01000000")                                            # mov edx, 1
    a.call(RATING)                                               # st0 = rating(player)
    a.b("5a")                                                    # pop edx
    a.b("59")                                                    # pop ecx
    a.b("52")                                                    # push edx
    a.b("ba" + struct.pack("<I", code_va + DATA_OFFSET).hex())   # mov edx, &star
    a.b("807935" + "00")                                         # cmp byte [ecx+0x35], 0  (QB)
    a.j8("75", "compare")
    a.b("ba" + struct.pack("<I", code_va + DATA_OFFSET + 4).hex())   # mov edx, &qb
    a.label("compare")
    a.b("d81a")                                                  # fcomp dword [edx]
    a.b("dfe0")                                                  # fnstsw ax
    a.b("5a")                                                    # pop edx
    a.b("f6c441")                                                # test ah, 0x41: rating <= threshold
    a.j8("75", "value")
    a.b("b8ffff0000")                                            # mov eax, 65535: never worth cutting
    a.b("c20c00")                                                # ret 0xC
    a.label("value")
    a.jmp_abs(VALUE)
    body = a.assemble()
    require(len(body) <= DATA_OFFSET, "star retention cave exceeds its allocation")
    return body.ljust(DATA_OFFSET, b"\xcc") + struct.pack("<ff", star / 100.0, qb / 100.0)


def sites(code_va=0):
    name, va, before = HOOK
    return [(name, va, before, b"\xe8" + struct.pack("<i", code_va - va - 5))]


def allocation(payload):
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    require(len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"]) == ("code", CODE_SIZE, 16),
            "Missing or foreign star retention allocation")
    return rows[0]


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
    require(states in ({"retail"}, {"applied"}), "Foreign or mixed star retention site/code")
    surplus_va, surplus_retail, surplus_economy = ECONOMY_SURPLUS
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for _, at, before, _ in edits:
            if va <= at and at + len(before) <= va + size:
                content[at - va:at - va + len(before)] = before
        if va <= surplus_va and surplus_va + 2 <= va + size:
            at = surplus_va - va
            if bytes(content[at:at + 2]) == surplus_economy:
                content[at:at + 2] = surplus_retail
        require(hashlib.sha256(content).hexdigest() == digest, f"Foreign star retention prerequisite at {va:#x}")
    return next(iter(states))


def status(payload):
    try:
        return _recognize(payload)
    except _ERRORS:
        return "foreign"


def read_settings(payload):
    out = {"status": status(payload)}
    if out["status"] == "applied":
        from .nfl2k5_cave_oracle import XbeImage
        star, qb = struct.unpack("<ff", XbeImage(payload).read(allocation(payload)["va"] + DATA_OFFSET, 8))
        out.update(star_overall=round(star * 100), qb_overall=round(qb * 100))
    return out


def apply(payload):
    """Install, or replay an identical installation."""
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_bump_strength import _sections, section_digest
    from .nfl2k5_cave_oracle import XbeImage
    try:
        state = _recognize(payload)
    except _ERRORS as exc:
        raise StarRetentionError(f"foreign/mixed star retention input: {exc}") from exc
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False, star_overall=STAR_OVERALL,
                  qb_overall=QB_OVERALL)
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    before = payload
    allocation_receipt = {}
    if not any(r["owner"] == OWNER for r in space.layout(payload)["allocations"]):
        if space.status(payload) == "retail":
            payload, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
        else:
            require(space.is_scaleout(payload), "CPU clubs keep their stars needs the scale-out allocator")
            payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
    code_va = allocation(payload)["va"]
    payload, _ = space.install_code(payload, OWNER, code_for(code_va))
    edits = sites(code_va)
    image = XbeImage(payload)
    buf = bytearray(payload)
    for _, va, old, new in edits:
        off = image.offset(va, len(old))
        require(bytes(buf[off:off + len(old)]) == old, f"star retention site {va:#x} is not retail")
        buf[off:off + len(old)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(_recognize(result) == "applied" and space.status(result) == "applied", "star retention postcondition failed")
    return result, dict(common, status="applied", code_va=hex(code_va),
                        before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=space.count_differing_bytes(before, result), file_growth=len(result) - len(before),
                        allocation=allocation_receipt,
                        edits=[dict(label=name, va=hex(va), before=old.hex(), after=new.hex()) for name, va, old, new in edits],
                        reservations=[r for r in space.reservations(result) if r["owner"] == OWNER])


__all__ = ["OWNER", "REQUESTS", "CODE_SIZE", "HOOK", "GUARDS", "STAR_OVERALL", "QB_OVERALL", "code_for", "sites",
           "allocation", "status", "read_settings", "apply"]

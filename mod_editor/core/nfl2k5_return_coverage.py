"""Coverage pursuit angles on kick and punt returns (USA retail XBE). EXPERIMENTAL.

Report (b778, rjawn 10/22): a 99-Speed returner scores two or more return
touchdowns a game by running around the coverage to the sideline. The far
chase task ``FUN_002E8F20`` (installed by ``FUN_002E9170`` with the ball
carrier as its task target) steers with ``FUN_000210B0(target.x - self.x,
target.z - self.z)``: it aims at the carrier's *current* position, not at an
intercept point. A fast carrier who cuts to the sideline therefore outruns a
pure-pursuit defender even when the defender has the angle.

This owner replaces only that bearing call (0x2E9148, five bytes) with a
bounded lead-pursuit aim, and only while the game's play-kind word says the
snap is a kick or punt:

    kind    = [E602BC]                                      game play kind
    gate    : kind in {1 safety kick, 2 kickoff, 6 punt}    else retail bearing
    human   : [[player+0xC]] == -1                          else retail bearing
    d       = distance(self, carrier)                       (cm)
    speed   = 237C70(self)                                  (cm/s)
    t       = min(d / speed, 1.0)                           (s)
    aim     = carrier position + carrier velocity * t
    aim.x   = clamp(aim.x, -2346.96, 2346.96)               (3 yd inside the sideline)
    bearing = 210B0(aim.x - self.x, aim.z - self.z)

``E602BC`` is written by the game's own play-entry classifier (0xB5550) from
the chosen play's family: family 6 (kickoff) sets 1 when phase 1
(safety kick) and 2 otherwise (normal kickoff), family 2 (punt) sets 6, family 0 (scrimmage run/pass) sets 4 or 5 and
family 4 (field goal) sets 3. A kickoff return (family 7), punt return
(family 3) or defense (family 1) leaves the kicking play's value in place, so
the word stays 1/2/6 through the return and is replaced when the next
scrimmage play is selected. Scrimmage pursuit therefore takes the retail
bearing byte for byte.

Everything else is retail: the task's own give-up/hand-off tests, the target
selection, the turn integrator, and the carrier's movement. The lead is
capped at one second and the aim is kept three yards inside the sideline so a
defender takes the outside angle without running out of bounds. A great
returner can still win a race to the corner.

The charted component replay in ``test_nfl2k5_return_coverage.py`` runs the
real 0x2E8F20 and 0x210B0 on retail and patched bytes; the game-level witness
is the emulator run named in the job report.
"""
from __future__ import annotations

import hashlib
import struct

OWNER = "nfl2k5_return_coverage"
CODE_SIZE = 192                    # 174 bytes of code, rounded to the 16-byte alignment
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
BUILD_CAPTION = "Return coverage takes pursuit angles (experimental)"
HELP_TEXT = (
    "EXPERIMENTAL. On kick and punt returns the CPU coverage players now aim at an "
    "intercept point ahead of the returner instead of at his current position, and "
    "keep that aim three yards inside the sideline so the outside contain can force "
    "him back in or out of bounds. The lead is capped at one second; a fast returner "
    "can still beat the angle. Human-controlled defenders are unchanged."
)

HOOK_VA = 0x002E9148
RETAIL_HOOK = bytes.fromhex("e8637fd3ff")          # call 0x210B0
BEARING = 0x000210B0
PLAY_KIND = 0x00E602BC      # game play kind: 1 safety kick, 2 kickoff, 3 FG, 4 pass, 5 run, 6 punt
KICK_KINDS = (1, 2, 6)
KIND_MASK = sum(1 << kind for kind in KICK_KINDS)  # 0x46
PURSUIT = 0x002E8F20
SPEED = 0x00237C70
CONTROL_OFFSET = 0x0C
SPEED_RATING = 0x1B4
C_BAND = 0x004EDD28        # 274.32 cm/s per Speed rating
C_BASE = 0x004F0F70        # 640.08 cm/s base
C_ZERO = 0x004E4180        # 0.0
C_ONE = 0x004E419C         # 1.0
C_SIDELINE_IN = 0x00510428 # +2346.96 (3 yd inside the sideline)
C_SIDELINE_IN_NEG = 0x00510424
CONSTANTS = ((C_BAND, 274.32), (C_BASE, 640.08), (C_ZERO, 0.0), (C_ONE, 1.0),
             (C_SIDELINE_IN, 2346.96), (C_SIDELINE_IN_NEG, -2346.96))
GUARDS = (
    (PURSUIT, 577, "632f16b27c7df60ec97c2a7fb68486e614d279ab546c5512eb93d45beaba909f"),
    (BEARING, 215, "992f601ec2f53fa33bbb4b5f0bad2c0e16b1efd5be83a5693710bdbf17990734"),
    (SPEED, 22, "cdeccafa56c472dc0902d17cd6c5ad0ed617f0365c5f9114ccb005d2189e515d"),
)
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError, OSError)


class ReturnCoverageError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise ReturnCoverageError(message)


def _imm(value):
    return struct.pack("<I", value).hex()


def code_for(code_va):
    """The 0x2E9148 bearing replacement. EDI = carrier, ESI = defender at the hook."""
    from .nfl2k5_draft_ai import _Asm
    a = _Asm(code_va)
    a.label("entry")
    a.b("a1" + _imm(PLAY_KIND))                          # mov eax,[E602BC] play kind
    a.b("89c1")                                          # mov ecx,eax
    a.b("b8" + _imm(KIND_MASK))                          # mov eax,0x46 (bits 1,2,6)
    a.b("0fa3c8")                                        # bt eax,ecx -> CF = kick/punt
    a.j8("72", "lead")                                   # jc lead
    a.label("retail")
    a.jmp_abs(BEARING)                                   # scrimmage/FG/other: retail aim
    a.label("lead")
    a.b("8b460c")                                        # mov eax,[esi+0xC] control block
    a.b("8338ff")                                        # cmp dword [eax],-1
    a.j8("75", "retail")                                 # human defender: retail aim
    a.b("8b4718")                                        # mov eax,[edi+0x18] carrier transform
    a.b("8b4e18")                                        # mov ecx,[esi+0x18] defender transform
    a.b("f30f104030")                                    # movss xmm0,[eax+0x30] carrier x
    a.b("f30f104838")                                    # movss xmm1,[eax+0x38] carrier z
    a.b("0f28d0")                                        # movaps xmm2,xmm0
    a.b("f30f5c5130")                                    # subss xmm2,[ecx+0x30]
    a.b("0f28d9")                                        # movaps xmm3,xmm1
    a.b("f30f5c5938")                                    # subss xmm3,[ecx+0x38]
    a.b("0f28e2")                                        # movaps xmm4,xmm2
    a.b("f30f59e4")                                      # mulss xmm4,xmm4
    a.b("0f28eb")                                        # movaps xmm5,xmm3
    a.b("f30f59ed")                                      # mulss xmm5,xmm5
    a.b("f30f58e5")                                      # addss xmm4,xmm5
    a.b("f30f51e4")                                      # sqrtss xmm4,xmm4 distance
    a.b("8b5610")                                        # mov edx,[esi+0x10] state
    a.b("f30f102d" + _imm(C_BAND))                        # movss xmm5,[274.32]
    a.b("f30f59aab4010000")                              # mulss xmm5,[edx+0x1B4]
    a.b("f30f582d" + _imm(C_BASE))                        # addss xmm5,[640.08]
    a.b("f30f5ee5")                                      # divss xmm4,xmm5 time
    a.b("f30f5d25" + _imm(C_ONE))                         # minss xmm4,[1.0]
    a.b("f30f106840")                                    # movss xmm5,[eax+0x40] carrier vx
    a.b("f30f59ec")                                      # mulss xmm5,xmm4
    a.b("f30f107048")                                    # movss xmm6,[eax+0x48] carrier vz
    a.b("f30f59f4")                                      # mulss xmm6,xmm4
    a.b("f30f58e8")                                      # addss xmm5,xmm0 aim x
    a.b("f30f58f1")                                      # addss xmm6,xmm1 aim z
    a.b("f30f5d2d" + _imm(C_SIDELINE_IN))                # minss xmm5,[+2346.96]
    a.b("f30f5f2d" + _imm(C_SIDELINE_IN_NEG))            # maxss xmm5,[-2346.96]
    a.b("f30f5c6930")                                    # subss xmm5,[ecx+0x30]
    a.b("f30f5c7138")                                    # subss xmm6,[ecx+0x38]
    a.b("f30f116c2404")                                  # movss [esp+4],xmm5
    a.b("f30f11742408")                                  # movss [esp+8],xmm6
    a.jmp_abs(BEARING)                                   # bearing(callee pops its two args)
    body = a.assemble()
    require(len(body) <= CODE_SIZE, f"return-coverage cave exceeds its allocation ({len(body)} > {CODE_SIZE})")
    return body.ljust(CODE_SIZE, b"\xcc"), dict(a.labels)


def sites(code_va=0):
    labels = code_for(code_va)[1]
    hook = b"\xe8" + struct.pack("<i", code_va - HOOK_VA - 5)
    return [("pursuit_aim", HOOK_VA, RETAIL_HOOK, hook)]


def mapping():
    return {
        "hook": hex(HOOK_VA), "pursuit_task": hex(PURSUIT), "bearing": hex(BEARING),
        "play_kind": hex(PLAY_KIND), "kick_kinds": list(KICK_KINDS),
        "lead_seconds_cap": 1.0, "sideline_margin_cm": 2346.96,
        "aim": "carrier position + carrier velocity * min(distance / 237C70(defender), 1.0)",
        "cpu_only": True, "carrier_and_turn_integrator": "retail",
        "presets": {"basic": False, "advanced": True, "experimental": True},
    }


def allocation(payload):
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    require(len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"]) == ("code", CODE_SIZE, 16),
            "Missing or foreign return-coverage allocation")
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
        states.add("retail" if raw == b"\xcc" * CODE_SIZE else "applied" if raw == code_for(owned["va"])[0] else "foreign")
    require(states in ({"retail"}, {"applied"}), "Foreign or mixed return-coverage site/code")
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for _, at, before, _ in edits:
            if va <= at and at + len(before) <= va + size:
                content[at - va:at - va + len(before)] = before
        require(hashlib.sha256(content).hexdigest() == digest, f"Foreign return-coverage prerequisite at {va:#x}")
    for va, value in CONSTANTS:
        require(abs(struct.unpack("<f", image.read(va, 4))[0] - value) < 1e-3 * max(1.0, abs(value)),
                f"Foreign return-coverage constant at {va:#x}")
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
        raise ReturnCoverageError(f"foreign/mixed return-coverage input: {exc}") from exc
    common = dict(owner=OWNER, experimental=True)
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    before = payload
    allocation_receipt = {}
    if not any(r["owner"] == OWNER for r in space.layout(payload)["allocations"]):
        if space.status(payload) == "retail":
            payload, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
        else:
            require(space.is_scaleout(payload), "return coverage needs the scale-out allocator")
            payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
    code_va = allocation(payload)["va"]
    payload, _ = space.install_code(payload, OWNER, code_for(code_va)[0])
    edits = sites(code_va)
    image = XbeImage(payload)
    buf = bytearray(payload)
    for _, va, old, new in edits:
        off = image.offset(va, len(old))
        require(bytes(buf[off:off + len(old)]) == old, f"return-coverage site {va:#x} is not retail")
        buf[off:off + len(old)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(_recognize(result) == "applied" and space.status(result) == "applied",
            "return-coverage postcondition failed")
    return result, dict(common, status="applied", code_va=hex(code_va),
                        before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=space.count_differing_bytes(before, result), file_growth=len(result) - len(before),
                        allocation=allocation_receipt,
                        edits=[dict(label=name, va=hex(va), before=old.hex(), after=new.hex())
                               for name, va, old, new in edits],
                        reservations=[r for r in space.reservations(result) if r["owner"] == OWNER])


__all__ = ["OWNER", "REQUESTS", "CODE_SIZE", "HOOK_VA", "RETAIL_HOOK", "GUARDS", "code_for", "sites", "allocation",
           "status", "apply"]

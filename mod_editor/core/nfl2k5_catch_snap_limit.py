"""CPU defenders cannot slide to the ball for a pick (catch snap limit), USA retail. EXPERIMENTAL, opt-in.

Report (SharkMagick, 10/09): "Db's and defenders in general will sometimes warp to parts of the field for picks. if we
could tone that down it might help with the interception problem." Research: job ai3-pickwarp (10/11, offline, no in-game
witness) and b780 r5-coverage section 2.4 / C1.

How a catch is aimed in the retail executable (static disassembly plus the native routines run in Unicorn):

- The catch selector 0x1E78A0 (ECX = the player, EDX = the request 0x55..0x57, one stack argument = a 20-dword plan
  record) picks a catch clip for the ball's flight and fills the record: ``[0]`` the clip descriptor (flags dword at
  +4, bits 8..9 = the clip family), ``[+0x10]`` / ``[+0x18]`` the planned sideways correction (cm) between where the clip
  would put the hands and where the ball will be, ``[+0x40]`` the "accepted" flag (the clip passed the reach cap). The
  cap is the catch-context reach curve (0x50AD3C) plus a 15 cm allowance for CPU teams, scaled for a big turn, so a
  planned correction can reach nearly a yard.
- A defender who commits (the catch action's begin 0x1E7B80 -> plan setup 0x1E57B0) stores that correction on the clip,
  and for the aligned clip family (family 1) the per-tick catch update 0x1E2CF0 calls the alignment helper 0x1A8940,
  which adds a fraction of the correction **straight to the world position**, with no check against his running speed.
  That slide is the "warp".
- A record with the accepted flag clear is retail's own non-catch answer: the selector returns 0, the AI tasks that
  asked (0x226F00, 0x225EB0 and the others) take their no-catch exit, and the begin callback runs the clip without
  the correction (nothing is stored on the clip, so nothing slides).

This owner changes two things for the same players, both only for a CPU-controlled defender on a forward pass in the air
(``[0xE602C0] == 4``, his team is not the team with the ball ``[0xE60280]``, ``[[player+0xC]] == -1``; a human-controlled
defender is untouched):

1. **Refuse the long slide.** At the single success exit of the selector (0x1E7B02, ``mov eax,[esp+0x18]; pop edi``),
   when the request is a real catch (0x55, 0x56 or 0x57; every AI caller and the begin callback ask with one of them),
   the selector accepted a plan (``record[0]`` set, ``record[+0x40]`` set) for an aligned clip (family 1) and the planned
   horizontal slide is longer than ``LIMIT_YARDS`` (half a yard; NaN and infinity count as too long), the plan is
   demoted to retail's own non-catch answer: ``record[+0x40] = 0``, ``record[+4] = 1.0`` (the rate retail's fallback
   record carries) and the selector returns 0. Every caller (the AI tasks that decide to go for the ball and the begin
   callback that starts the clip) then sees the ordinary "no aligned catch from here" result, so there is no new code path,
   no stale cached plan and no half-started action. He keeps running at the ball and can get his chance a tick later, if
   the same ball then needs a shorter slide (the selector's best plan moves from tick to tick: Unicorn measured 0.21, 0.56, 0.26
   yards on three neighbouring ticks for a defender standing still).
2. **Cap the slide that is stored.** The plan setup (0x1E57B0) already scales the stored slide down to the catch
   context's reach (0x50AD3C, 0.5 to 1 yard) plus a 15 cm allowance for a CPU team; that is the bound that lets a plan
   slide him nearly a yard. Its cap is in ``[esp+0x18]`` just before the comparison (0x1E5CCB). For a CPU defender on a
   forward pass the stub lowers that cap to ``LIMIT_CM`` when it is higher, so the retail scaling code itself
   limits the stored slide to half a yard. This covers a plan that was cached a tick earlier and is planned again by
   the begin callback (setup argument 1), where the ball has moved and the slide can be longer than the one the AI saw.

Dive and leap clips (other families, which move him with real velocity instead of a position add), receivers, kicks,
backward passes, human-controlled defenders and every other selector caller are byte-for-byte retail.

Proof level (b780 cv4-pick): unit tests on the exact bytes and on both stubs in Unicorn (gates, boundaries, NaN, x87
and register balance), and the game's own selector, setup, begin callback, animation sampler and alignment helper run
on the ai3 grid in Unicorn, on retail and on the released SOFTDRINK v0.8 executable. Not witnessed in the emulator or in
play: the reported warp itself was never reproduced (ai3), so this limits the mechanism the code shows, not a recorded
clip.

Allocation: one 224-byte late code owner (``nfl2k5_xbe_space.LATE_OWNERS``, last): the two limit constants (the
squared limit and the limit, as floats, cm) in its first eight bytes, then the two stubs. Idempotent, refuses foreign
bytes.
"""
from __future__ import annotations

import hashlib
import struct

OWNER = "nfl2k5_catch_snap_limit"
CODE_SIZE = 224                   # 8 bytes of constants + both stubs, rounded to the 16-byte alignment
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
LIMIT_YARDS = 0.5
CM_PER_YARD = 91.44
LIMIT_CM = LIMIT_YARDS * CM_PER_YARD
LIMIT_SQUARED = struct.unpack("<f", struct.pack("<f", LIMIT_CM * LIMIT_CM))[0]   # the float the selector stub compares against
LIMIT_BITS = struct.unpack("<I", struct.pack("<f", LIMIT_CM))[0]                  # the cap the setup stub stores
BUILD_CAPTION = "Limit CPU defender warps to the ball on picks (experimental)"  # b780-int: 60-character caption rule
HELP_TEXT = ("EXPERIMENTAL, off unless you turn it on. When a CPU defender goes up for a pass, the game slides him a "
             "short way sideways to line his hands up with the ball, outside his running speed, and that slide can be close "
             "to a full yard (the 'warp' on a pick). With this on, a CPU defender gets that help only up to half a yard. If "
             "the catch would need more, he does not go for it from there: he keeps running at the ball and can still go "
             "for it a moment later, if the catch then needs a shorter slide. Receivers, human-controlled players, kicks, "
             "dives and leaps are unchanged. Not yet tested in game.")

# The selector's success exit: ``mov eax,[esp+0x18]`` (the result) then ``pop edi``; the epilogue resumes at ``pop esi``.
HOOK = ("exit", 0x001E7B02, bytes.fromhex("8b4424185f"))
RESUME = 0x001E7B07
# The plan setup's reach cap: ``fstp [esp+0x18]`` (reach + allowance, cm) then ``fld [esp+0x18]`` for the squared compare.
CAP_HOOK = ("cap", 0x001E5CCB, bytes.fromhex("d95c2418d9442418"))
CAP_RESUME = 0x001E5CD3
HOOKS = (HOOK, CAP_HOOK)
GAME_BALL_KIND, GAME_OFFENSE_TEAM = 0x00E602C0, 0x00E60280     # ball kind (4 = forward pass, 3 = kicks and backward passes), team with the ball
# Routines the owner's claims rest on, byte-identical in retail and in every released SOFTDRINK executable (v0.8 checked):
# the selector with its jump tables, the clip-family selector, the aligned-clip candidate loop (the accepted flag and
# the correction vector), the plan setup (what an unaccepted record stores), the catch update and the alignment helper.
# The begin callback 0x1E7B80 is deliberately not pinned: the abilities owner may replace a call inside it.
GUARDS = (
    (0x001E78A0, 736, "8d2ab7f8b70421aef2d6f771ffaf480c5f839d103fe30a22ab2d34cbe6b33936"),   # selector + jump tables
    (0x001E7410, 689, "53e27654048d26be8ded21860dd1f152798f834798b22900ac21606f931dc299"),   # clip families
    (0x001E6600, 3595, "fad59095ba1df1eabba981f5d9b3f137b8e340b296905b961664e2732a745623"),  # aligned-clip candidates
    (0x001E57B0, 1636, "61a51ea610f11c45dfc5201bcf86d876f300071db6fb1c02e4be8f651de0c41e"),  # plan setup
    (0x001E2CF0, 554, "4b60c7e4904be98504290433bda543a6bdc4e878b0244776677e59705ddca8bd"),   # catch update
    (0x001A8940, 91, "eb910bc1db80a1ae362e04fd6679269f7f12f83e72f5ed15c4fd261a60cdb381"),    # alignment helper
)
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError, OSError)


class CatchSnapLimitError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise CatchSnapLimitError(message)


def _imm(value):
    return struct.pack("<I", value & 0xFFFFFFFF).hex()


def code_for(code_va):
    """The cave: the two limit constants first (``code_va`` is the squared limit, ``code_va + 4`` the limit), then the
    selector's exit stub and the setup's cap stub, each entered by its hook.

    Exit stub registers: EAX, ECX, EDX, the flags and two x87 slots (popped before the exit). On entry the selector's
    frame is live: ESI = the player, ``[ebp+8]`` = the plan record, ``[esp+0x10]`` = the request, ``[esp+0x18]`` = the
    result about to be returned, EDI / EBX / ESI still to be restored by the epilogue the stub resumes into.

    Cap stub: EAX, ECX, the flags and one x87 slot. On entry the setup's frame is live: ``[esp+0x10]`` = the player,
    ``[esp+0x18]`` = where the retail code stores the reach cap (ST0 holds it on entry, the displaced ``fstp``); after
    the comparison the retail code reloads EAX, ECX and EDX before reading them."""
    from .nfl2k5_draft_ai import _Asm
    a = _Asm(code_va)
    a.b(struct.pack("<f", LIMIT_SQUARED).hex())                   # +0: limit squared (cm squared)
    a.b(struct.pack("<f", LIMIT_CM).hex())                        # +4: limit (cm)
    a.label("exit")
    a.b("8b44241885c0"); a.j8("74", "out")                        # result = [esp+0x18]; nothing selected: retail
    a.b("8b4c241083e9" + "55" + "83f9" + "02"); a.j8("77", "out")  # request - 0x55 above 2: another request: retail
    #   (the probe path, request 0, reuses [esp+0x10] for a float; no real float reads 0x55..0x57, a denormal near 1e-43)
    a.b("833d" + _imm(GAME_BALL_KIND) + "04"); a.j8("75", "out")  # not a forward pass in the air: retail
    a.b("8b0d" + _imm(GAME_OFFENSE_TEAM) + "3b4e38"); a.j8("74", "out")   # his team has the ball: a receiver, retail
    a.b("8b4e0c8339ff"); a.j8("75", "out")                        # not CPU-controlled ([[player+0xC]] != -1): retail
    a.b("8b4d088b1185d2"); a.j8("74", "out")                      # ecx = record, edx = clip descriptor; none: retail
    a.b("837940" + "00"); a.j8("74", "out")                       # plan not accepted: it already slides nothing
    a.b("8b5204c1ea0883e203" + "83fa" + "01"); a.j8("75", "out")  # not the aligned clip family: velocity dives, retail
    a.b("d94110d8c8d94118d8c8dec1")                               # st0 = correction x^2 + correction z^2
    a.b("d81d" + _imm(code_va))                                   # compare with limit squared (and pop)
    a.b("dfe0f6c404"); a.j8("75", "refuse")                       # unordered (NaN): too long
    a.b("f6c441"); a.j8("75", "out")                              # at or under the limit: retail
    a.label("refuse")
    a.b("c7414000000000")                                         # record[+0x40] = 0: not accepted, nothing is stored on the clip
    a.b("c7410400" + "00803f")                                    # record[+4] = 1.0f: the rate retail's own fallback record has
    a.b("31c089442418")                                           # result = 0
    a.label("out")
    a.b("8b4424185f")                                             # the displaced mov eax,[esp+0x18] / pop edi
    a.jmp_abs(RESUME)
    a.label("cap")
    a.b("d95c2418")                                               # the displaced fstp [esp+0x18]: cap = reach + allowance
    a.b("833d" + _imm(GAME_BALL_KIND) + "04"); a.j8("75", "cap_out")      # not a forward pass in the air: retail
    a.b("8b442410" + "8b0d" + _imm(GAME_OFFENSE_TEAM) + "3b4838"); a.j8("74", "cap_out")   # eax = player; his team has the ball
    a.b("8b400c8338ff"); a.j8("75", "cap_out")                    # not CPU-controlled: retail
    a.b("d905" + _imm(code_va + 4))                               # st0 = limit
    a.b("d85c2418dfe0f6c441"); a.j8("74", "cap_out")              # limit above the cap (strictly): keep the retail cap
    a.b("c7442418" + _imm(LIMIT_BITS))                            # cap = limit: the retail scaling then limits the stored slide
    a.label("cap_out")
    a.b("d9442418")                                               # the displaced fld [esp+0x18]
    a.jmp_abs(CAP_RESUME)
    body = a.assemble()
    require(len(body) <= CODE_SIZE, f"catch snap caves exceed their allocation ({len(body)} > {CODE_SIZE})")
    return body.ljust(CODE_SIZE, b"\xcc"), dict(a.labels)


def sites(code_va=0):
    """Hook edits (label, va, retail, new). Each hook is a 5-byte jump to its stub, padded with NOPs to the displaced span."""
    labels = code_for(code_va)[1]
    return [(name, va, before, (b"\xe9" + struct.pack("<i", code_va + labels[name] - va - 5)).ljust(len(before), b"\x90"))
            for name, va, before in HOOKS]


def allocation(payload):
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    require(len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"]) == ("code", CODE_SIZE, 16),
            "Missing or foreign catch snap limit allocation")
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
    require(states in ({"retail"}, {"applied"}), "Foreign or mixed catch snap limit site/code")
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for _, at, before, _ in edits:
            if va <= at and at + len(before) <= va + size:
                content[at - va:at - va + len(before)] = before
        require(hashlib.sha256(content).hexdigest() == digest, f"Foreign catch snap limit prerequisite at {va:#x}")
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
        raise CatchSnapLimitError(f"foreign/mixed catch snap limit input: {exc}") from exc
    common = dict(owner=OWNER, experimental=True)
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    before = payload
    allocation_receipt = {}
    if not any(r["owner"] == OWNER for r in space.layout(payload)["allocations"]):
        if space.status(payload) == "retail":
            payload, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
        else:
            require(space.is_scaleout(payload), "The catch snap limit needs the scale-out allocator")
            payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
    code_va = allocation(payload)["va"]
    payload, _ = space.install_code(payload, OWNER, code_for(code_va)[0])
    edits = sites(code_va)
    image = XbeImage(payload)
    buf = bytearray(payload)
    for _, va, old, new in edits:
        off = image.offset(va, len(old))
        require(bytes(buf[off:off + len(old)]) == old, f"catch snap limit site {va:#x} is not retail")
        buf[off:off + len(old)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(_recognize(result) == "applied" and space.status(result) == "applied", "catch snap limit postcondition failed")
    return result, dict(common, status="applied", code_va=hex(code_va),
                        before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=space.count_differing_bytes(before, result), file_growth=len(result) - len(before),
                        allocation=allocation_receipt,
                        edits=[dict(label=name, va=hex(va), before=old.hex(), after=new.hex()) for name, va, old, new in edits],
                        reservations=[r for r in space.reservations(result) if r["owner"] == OWNER])


__all__ = ["OWNER", "REQUESTS", "CODE_SIZE", "HOOK", "CAP_HOOK", "HOOKS", "GUARDS", "LIMIT_YARDS", "code_for", "sites", "allocation",
           "status", "apply"]

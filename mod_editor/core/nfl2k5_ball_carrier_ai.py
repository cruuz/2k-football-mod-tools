"""CPU ball carriers stay in bounds; CPU quarterbacks slide past the sticks, USA retail. EXPERIMENTAL.

Report (b778, Noah's 10/21 stream): CPU ball carriers drift out of bounds with nobody forcing them ("why'd he go out of
bounds"), and CPU quarterbacks slide short of the first-down marker.

The retail ball-carrier AI (static disassembly of the USA executable, b778 ai5 report):

- 0x2E36F0 makes a player the ball carrier and installs the per-frame carrier task 0x2E2DA0. It sums a lateral push
  away from the defenders (0x2E2260), turns toward it at a limited rate, then passes the requested heading through the
  sideline filter 0x2E2780 before storing it (``[[player+0xC]+0x14]``).
- The sideline filter takes the heading's lateral part (sin) and forward part (cos) and scales the lateral part by
  ``w = clamp(|2392.68 - |x|| / 228.6, 0, 1)`` (cm): 1 more than 3 yards inside the sideline, 0 half a yard inside it,
  but, because of the absolute value, it grows again in the last half yard and outside. Then a clock term may be added
  to ``w`` (0x2E28EB..0x2E29E2: only when the team's clock urgency ``[[team+0xC]+0xC4]`` is above 0.5, not on 3rd or
  4th down short of the sticks, more than 3 s left: trailing by 4 or more, when a defender beats the carrier to the
  goal line; otherwise inside the opponent's 30). ``w >= 1`` returns the heading unchanged. So an outward push from
  pursuers keeps steering the carrier toward the line until his centre is half a yard from it, and from there the
  filter lets him drift out.
- The slide (carrier action 0x99, 0x2E3394..0x2E341A) needs a quarterback carrier (``[player+0x2C] == 0``), top threat
  ``>= 1.0``, facing upfield, a roll under ``1.25 - Scramble``, more than a yard past the line of scrimmage and
  0x291AE0. It never looks at the line to gain ``[[0xE602EC]+0x28]``.

This owner changes two decisions for CPU-controlled carriers only (controller marker ``[[player+0xC]] == -1``;
human-controlled players are untouched):

- ``sideline`` (jump at 0x2E29E6, the filter's final test): when the team's clock urgency is 0.5 or less (then retail
  adds no clock term), an OUTWARD lateral heading is scaled by ``(2346.96 - |x|) / 274.32`` instead of the retail weight
  (never more than the retail weight within 3 yards of the line): full lateral room more than 4 yards inside the sideline,
  none from 1 yard inside it outward (the retail tail counts a negative weight as 0: straight upfield). Inward
  headings, clock urgency above 0.5 (the retail clock logic, trailing or not) and human carriers run the retail code
  unchanged.
- ``slide`` (call at 0x2E340E, after every retail slide condition holds): short of the line to gain, the slide is kept
  only when the top threat reaches the quarterback before he can reach the sticks
  (``distance * own speed <= yards short * threat speed``, speeds from the retail 0x237C70; the top threat is the one
  retail itself required for the slide); at or past the line to gain the retail slide stands.

b780 cv2-runner: ``apply(payload, wide_sideline=True)`` installs the same caves with a wider outward taper for the
runner retune (``nfl2k5_runner_vision``, which makes CPU carriers react to where defenders are going): the outward
weight becomes ``(2346.96 - |x|) / (WIDE_BAND_YARDS * 91.44)``, full room only ``WIDE_BAND_YARDS + 1`` yards inside
the sideline and none from 1 yard in, so a runner who reads pursuit from inside turns upfield instead of bending to
the line. The float lives in the allocation's own padding (offset ``WIDE_BAND_OFFSET``); the request, the hooks and
every other byte are the standard install's. The carrier-task guard tolerates the runner retune's verified call
hook at 0x2E3072 (``nfl2k5_runner_vision.neighbor_edits``), as other owners do for a neighbour inside a pinned
routine.
"""
from __future__ import annotations

import hashlib
import struct

OWNER = "nfl2k5_ball_carrier_ai"
CODE_SIZE = 176                   # 165 bytes of code, rounded to the 16-byte alignment
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
BUILD_CAPTION = "CPU ball carriers stay in bounds; QBs slide past the sticks (experimental)"
HELP_TEXT = ("EXPERIMENTAL. CPU ball carriers stop drifting toward the sideline from 4 yards out and run straight "
             "upfield in the last yard, so they keep fighting for yards in bounds instead of stepping out. When the "
             "clock matters for their team late in a half they still play it like retail. A CPU quarterback short of "
             "the first-down line keeps running for the sticks and slides only when a defender will reach him first; "
             "past the line he slides as before. Human-controlled players are unchanged.")

SIDELINE_HOOK = ("sideline", 0x002E29E6, bytes.fromhex("d9442410d81d9c414e00"))   # fld [esp+0x10]; fcomp [1.0]
SLIDE_HOOK = ("slide", 0x002E340E, bytes.fromhex("e8cde6faff"))                  # call 0x291AE0
SIDELINE_RESUME = 0x002E29F0      # retail fnstsw right after the displaced test
SLIDE_CHECK, SPEED, DISTANCE, SCORE_DIFF = 0x00291AE0, 0x00237C70, 0x002E1E30, 0x00205F40
GAME_STATE, THREAT_INDEX, THREATS = 0x00E602EC, 0x00C8F204, 0x00C8F1A0
C_MARGIN, C_BAND, C_ONE, C_HALF = 0x00510428, 0x0050A528, 0x004E419C, 0x004E4184
HALF_BITS = 0x3F000000              # 0.5f: a positive float above it compares greater as a signed integer
WIDE_BAND_YARDS = 8.0               # b780 cv2-runner: with the runner retune, outward room fades from 9 yards in
WIDE_BAND_OFFSET = 168              # the wide band's float, in the padding after the 165 bytes of code
GUARDS = (
    (0x002E2780, 778, "ceff94910f98eeb5c7843c460bdf7ba84855d59ab110c1d977f2efc4bdb559ce"),   # sideline filter
    (0x002E2DA0, 2196, "3369e0cfea02df47bdf352b915a3eca1605a69bd396a5e8307223780d51e2a9b"),  # carrier task
    (0x00291AE0, 236, "af482b644e8d0eb46752acd3d7d7c96bfea06887eb6469563c0d0dba3c60346a"),   # retail slide check
    (0x00237C70, 22, "cdeccafa56c472dc0902d17cd6c5ad0ed617f0365c5f9114ccb005d2189e515d"),    # speed from rating
    (0x002E1E30, 60, "31fc263fcd73ededc2857634d0ba069259e91938836c4aa45e29637bb20d024c"),    # distance
    (0x00205F40, 13, "d54bba762b7c388fc96c30a8e018f448d84dc37dceb3a521af61cf475d9fe425"),    # score difference
    (0x002E0580, 25, "90a5b1475c2de02ca1952145e969543e7739cbf62f5b4505d4c940162c1c8a8d"),    # sqrt
)
CONSTANTS = ((C_MARGIN, 2346.96), (C_BAND, 0.003645), (C_ONE, 1.0), (C_HALF, 0.5))
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError, OSError)


class BallCarrierError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise BallCarrierError(message)


def _imm(value):
    return struct.pack("<I", value).hex()


def code_for(code_va, wide_sideline=False):
    """Both caves in one allocation. Only EAX, ECX, EDX, the flags and the retail frame's w / lateral / forward slots
    change; the x87 stack is left as found. ``wide_sideline``: the outward taper reads the band float stored at
    ``code_va + WIDE_BAND_OFFSET`` (1 / (WIDE_BAND_YARDS yards)) instead of the retail 1 / 3 yards."""
    from .nfl2k5_draft_ai import _Asm
    a = _Asm(code_va)
    a.label("retail")                                             # the two displaced retail instructions
    a.b(SIDELINE_HOOK[2].hex()); a.jmp_abs(SIDELINE_RESUME)
    # ---- sideline: entered by a jump from 0x2E29E6 in the retail frame: EBX = carrier, [esp+0x10] = w,
    # [esp+0x18] = lateral (sin), [esp+0x20] = the team's clock urgency (stored at 0x2E28F4), [esp+0x24] = forward
    a.label("sideline")
    a.b("8b430c8338ff"); a.j8("75", "retail")                     # CPU-controlled only ([[carrier+0xC]] == -1)
    a.b("817c2420" + _imm(HALF_BITS)); a.j8("7f", "retail")       # clock urgency > 0.5: the retail clock logic
    a.b("8b4b188b413033442418"); a.j8("78", "retail")             # x xor lateral: signs differ = heading inward
    a.b("d94130d9e1d82d" + _imm(C_MARGIN))                        # d = 2346.96 - |x| (cm)
    band = code_va + WIDE_BAND_OFFSET if wide_sideline else C_BAND
    a.b("d80d" + _imm(band) + "d95c2410")                         # w = d / 3 yd: 1 four yards in, 0 one yard in
    #                                                               (wide: d / 8 yd, 1 nine yards in)
    a.j8("eb", "retail")                                          # the retail test and tail: w >= 1 keeps the
    #                                                               heading, w < 0 counts as 0 (straight upfield)
    # ---- slide: called from 0x2E340E with ECX = EDI = the quarterback carrier, inside the carrier task's frame
    # (its [esp+0x1C], here [esp+0x20], is the +-1 field direction)
    a.label("slide")
    a.call(SLIDE_CHECK); a.b("85c0"); a.j8("74", "slide_out")     # the retail decision first
    a.b("8b570c833aff"); a.j8("75", "slide_out")                  # CPU-controlled only (the control block always
    #                                                               exists: retail writes it unconditionally)
    a.b("8b0d" + _imm(GAME_STATE) + "8b5718d94238d86128d84c2420")  # past = (z - line to gain) * direction
    a.b("d9eedff1"); a.j8("76", "allow")                          # at or past the line to gain: the retail slide
    a.b("d9e0a1" + _imm(THREAT_INDEX) + "8b0cc5" + _imm(THREATS) + "51")   # yards short; push the top threat
    a.call(SPEED); a.b("dec98bcf"); a.call(SPEED)                 # short * threat speed; own speed
    a.b("588bcf"); a.call(DISTANCE); a.b("dec9")                  # distance * own speed
    a.b("dff1ddd8"); a.j8("76", "allow_popped")                   # the threat gets there first: slide
    a.b("31c0c3")                                                 # otherwise keep running for the sticks
    a.label("allow"); a.b("ddd8c3")                               # EAX is still the retail 1
    a.label("allow_popped"); a.b("6a0158")
    a.label("slide_out"); a.b("c3")
    body = a.assemble()
    require(len(body) <= WIDE_BAND_OFFSET, f"ball-carrier caves exceed their allocation ({len(body)} > {CODE_SIZE})")
    out = bytearray(body.ljust(CODE_SIZE, b"\xcc"))
    if wide_sideline:
        out[WIDE_BAND_OFFSET:WIDE_BAND_OFFSET + 4] = struct.pack("<f", 1.0 / (WIDE_BAND_YARDS * 91.44))
    return bytes(out), dict(a.labels)


def sites(code_va=0):
    """Hook edits (label, va, retail, new). The sideline jump and the slide call enter their own labels."""
    labels = code_for(code_va)[1]
    sideline_va, slide_va = code_va + labels["sideline"], code_va + labels["slide"]
    name, va, before = SIDELINE_HOOK
    out = [(name, va, before, (b"\xe9" + struct.pack("<i", sideline_va - va - 5)).ljust(len(before), b"\x90"))]
    name, va, before = SLIDE_HOOK
    out.append((name, va, before, b"\xe8" + struct.pack("<i", slide_va - va - 5)))
    return out


def allocation(payload):
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    require(len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"]) == ("code", CODE_SIZE, 16),
            "Missing or foreign ball-carrier allocation")
    return rows[0]


def _neighbor_edits(payload):
    """b780 cv2-runner: the runner retune's call hook at 0x2E3072 inside the carrier task, as (va, retail bytes), only
    while that owner validates as exactly applied (it never calls back into this module)."""
    from . import nfl2k5_runner_vision as vision
    return vision.neighbor_edits(payload)


def _variant(payload):
    """(state, wide_sideline): wide_sideline is None unless the caves are installed."""
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    present = any(r["owner"] == OWNER for r in space.layout(payload)["allocations"])
    owned = allocation(payload) if present else None
    edits = sites(owned["va"] if owned else 0)
    states, wide = set(), None
    for _name, va, before, after in edits:
        raw = image.read(va, len(before))
        states.add("retail" if raw == before else "applied" if owned and raw == after else "foreign")
    if owned:
        raw = image.read(owned["va"], CODE_SIZE)
        if raw == b"\xcc" * CODE_SIZE:
            states.add("retail")
        elif raw in (code_for(owned["va"])[0], code_for(owned["va"], wide_sideline=True)[0]):
            states.add("applied")
            wide = raw == code_for(owned["va"], wide_sideline=True)[0]
        else:
            states.add("foreign")
    require(states in ({"retail"}, {"applied"}), "Foreign or mixed ball-carrier site/code")
    neighbors = _neighbor_edits(payload)
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for at, before in [(at, before) for _, at, before, _ in edits] + list(neighbors):
            if va <= at and at + len(before) <= va + size:
                content[at - va:at - va + len(before)] = before
        require(hashlib.sha256(content).hexdigest() == digest, f"Foreign ball-carrier prerequisite at {va:#x}")
    for va, value in CONSTANTS:
        require(abs(struct.unpack("<f", image.read(va, 4))[0] - value) < 1e-3 * max(1.0, abs(value)),
                f"Foreign ball-carrier constant at {va:#x}")
    return next(iter(states)), wide


def _recognize(payload):
    return _variant(payload)[0]


def wide_sideline(payload):
    """True / False for an installed owner (which outward taper), None otherwise (retail or foreign)."""
    try:
        return _variant(payload)[1]
    except _ERRORS:
        return None


def status(payload):
    try:
        return _recognize(payload)
    except _ERRORS:
        return "foreign"


def apply(payload, wide_sideline=False):
    """Install, or replay an identical installation (the same taper; the other taper is refused)."""
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_bump_strength import _sections, section_digest
    from .nfl2k5_cave_oracle import XbeImage
    wide_sideline = bool(wide_sideline)
    try:
        state, installed_wide = _variant(payload)
    except _ERRORS as exc:
        raise BallCarrierError(f"foreign/mixed ball-carrier input: {exc}") from exc
    common = dict(owner=OWNER, experimental=True, wide_sideline=wide_sideline)
    if state == "applied":
        require(installed_wide == wide_sideline, "CPU ball carriers is installed with the other sideline taper; "
                                                 "build from your unmodified retail dump")
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    before = payload
    allocation_receipt = {}
    if not any(r["owner"] == OWNER for r in space.layout(payload)["allocations"]):
        if space.status(payload) == "retail":
            payload, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
        else:
            require(space.is_scaleout(payload), "CPU ball carriers need the scale-out allocator")
            payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
    code_va = allocation(payload)["va"]
    payload, _ = space.install_code(payload, OWNER, code_for(code_va, wide_sideline)[0])
    edits = sites(code_va)
    image = XbeImage(payload)
    buf = bytearray(payload)
    for _, va, old, new in edits:
        off = image.offset(va, len(old))
        require(bytes(buf[off:off + len(old)]) == old, f"ball-carrier site {va:#x} is not retail")
        buf[off:off + len(old)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(_variant(result) == ("applied", wide_sideline) and space.status(result) == "applied",
            "ball-carrier postcondition failed")
    return result, dict(common, status="applied", code_va=hex(code_va),
                        before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=space.count_differing_bytes(before, result), file_growth=len(result) - len(before),
                        allocation=allocation_receipt,
                        edits=[dict(label=name, va=hex(va), before=old.hex(), after=new.hex()) for name, va, old, new in edits],
                        reservations=[r for r in space.reservations(result) if r["owner"] == OWNER])


__all__ = ["OWNER", "REQUESTS", "CODE_SIZE", "SIDELINE_HOOK", "SLIDE_HOOK", "GUARDS", "WIDE_BAND_YARDS", "code_for",
           "sites", "allocation", "status", "wide_sideline", "apply"]

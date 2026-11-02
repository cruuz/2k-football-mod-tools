"""CPU ball carriers read where defenders are going (cutbacks, less sideline drift), USA retail. EXPERIMENTAL.

Report (b780 r5-coverage; BT Zero 10/08-10/09, dk11 10/26): CPU ball carriers bend to the sideline and run up it, and
almost never cut back. The retail carrier steering (static disassembly and native Unicorn replays of the USA
executable, ``b77_session/reports/b780_r5-coverage_RESEARCH.md`` section 2.7):

- The ball-carrier task 0x2E2DA0 (handoffs, catches, QB scrambles, returns) calls the push routine 0x2E2260 once a
  tick (its only caller is the call at 0x2E3072). For every other player within 8 yards it adds a sideways push
  AWAY from him: bearing weight (table 0x50C7CC: front 1.1, 45 degrees 1.0, side 0.6, 135 degrees 0.1, behind 0)
  x distance weight (table 0x50C7F8: 0 yd 8.0 .. 8 yd 0) x player weight (defenders 2.0). The bearing is taken to the
  player's position 0.01 s ahead (``fmul [0x4E41A0]``, a constant shared with half the game), so where a defender
  is going never matters. Pursuit comes from inside, so the push points outside and the runner drifts to the
  sideline; an overrunning defender is still pushed against as if he stayed put, so the runner never cuts back
  behind him.

This owner gives CPU-controlled carriers (controller marker ``[[carrier+0xC]] == -1``) whose team's clock urgency
``[[team+0xC]+0xC4]`` is 0.5 or less (the same calm-clock rule as ``nfl2k5_ball_carrier_ai``) their own copy of
0x2E2260. The copy is made at build time from the user's own retail executable (it is checked byte for byte against
the retail routine; no game code ships with the Studio), its nine calls are relocated, and four things change:

- For every DEFENDER the bearing is taken from where the carrier will be to where the defender will be at their
  closest approach, looked ahead at most ``LOOKAHEAD`` seconds:
  ``t = clamp(-(dp . dv) / |dv|^2, 0, LOOKAHEAD)`` with ``dp``/``dv`` the defender's position/velocity minus the
  carrier's, and the bearing of ``dp + dv * t``. A man overrunning the play is seen outside where he is going, so
  the runner cuts back behind him; a chaser running stride for stride stays behind (no push); a defender coming
  head on is judged where he will meet the runner.
- Defenders use ``DEFENDER_BEARING`` instead of table 0x50C7CC (less push from men beside and behind the runner).
- Teammates (blockers) keep the retail look-ahead and table byte for byte, so blocking lanes work as retail.
- Distances, player weights, the blocker and "one-sided pursuit" rules are retail.

Human-controlled carriers and urgent clocks run the retail routine (its bytes are untouched); the only retail byte
change is the five-byte call at 0x2E3072. The wider sideline limit that keeps the cutback runner in bounds is
``nfl2k5_ball_carrier_ai``'s outward taper (its ``wide_sideline`` variant), applied together with this owner.
"""
from __future__ import annotations

import hashlib
import struct

OWNER = "nfl2k5_runner_vision"
CODE_SIZE = 1664                  # wrapper + the 1,312-byte owner copy + defender stub + constants, 16-byte aligned
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
BUILD_CAPTION = "CPU ball carriers see where defenders are going: cutbacks, less sideline drift (experimental)"
HELP_TEXT = ("EXPERIMENTAL. CPU ball carriers judge defenders by where they are going, not only where they are: "
             "a defender who overruns the play is avoided where he will be, so the runner cuts back behind him, "
             "and pursuit chasing from behind no longer pushes him to the sideline. From nine yards out his bend "
             "toward the sideline fades, so he turns upfield well before the line. Needs CPU ball carriers stay in "
             "bounds. When the clock matters for his team late in a half he plays it like retail. Human-controlled "
             "players are unchanged.")

HOOK = ("push_call", 0x002E3072, bytes.fromhex("e8e9f1ffff"))       # call 0x2E2260 in the carrier task
PUSH_VA, PUSH_SIZE = 0x002E2260, 0x520
PUSH_SHA256 = "45fa0d2205f0e3ec893023c20f94a0399dcae31ec94ea6ae41c046e2e48ada97"
# rel32 calls inside the routine (offsets from 0x2E2260): 0x210B0 x2, 0x23ABA0, 0x1B0AE0 x5, 0x2E0580, 0x76CB0
PUSH_CALLS = (0x109, 0x19D, 0x1C8, 0x2F5, 0x30B, 0x349, 0x362, 0x391, 0x3AC)
PLAYER_SITE = (0x09E, bytes.fromhex("8b46180f284030"))             # mov eax,[esi+0x18]; movaps xmm0,[eax+0x30]
PLAYER_RESUME = 0x0A5                                               # movaps [esp+0x60], xmm0
LOOKAHEAD_SITES = ((0x0B7, bytes.fromhex("d80da0414e00")),          # fmul [0.01]: velocity x
                   (0x0C5, bytes.fromhex("d80da0414e00")))          # fmul [0.01]: velocity z
LOOKAHEAD_EDIT = bytes.fromhex("d84c24746690")                     # fmul [esp+0x74]; xchg ax,ax
REFERENCE_SITES = ((0x0EB, bytes.fromhex("d8642448"), bytes.fromhex("d864247c")),   # fsub [carrier z] -> [esp+0x7C]
                   (0x0FB, bytes.fromhex("d8642440"), bytes.fromhex("d8642478")))   # fsub [carrier x] -> [esp+0x78]
TABLE_SITE = (0x2D9, bytes.fromhex("b9ccc75000"), bytes.fromhex("8b4c241490"))     # mov ecx,0x50C7CC -> [esp+0x14]
RETAIL_LOOKAHEAD, RETAIL_TABLE, OFFENSE = 0x004E41A0, 0x0050C7CC, 0x00E60280
URGENCY_HALF = 0x3F000000         # 0.5f: a positive float above it compares greater as a signed integer
LOOKAHEAD = 0.35                  # seconds
DEFENDER_BEARING = (1.1, 1.0, 0.3, 0.0, 0.0)   # 0, 45, 90, 135, 180 degrees from straight upfield (retail .6 / .1)
BEARING_POINTS = (0, 8192, 16384, 24576, 32768)
GUARDS = (
    (PUSH_VA, PUSH_SIZE, PUSH_SHA256),                                                          # the push routine
    (0x002E3040, 0x70, "19f7ce3dee58477128be031333eb3150f5a9f6f8dd2f35e711835f2a4bf7bf13"),     # the hooked call's context
    (0x0050C7C8, 0xA4, "68087c05c2917aef9f5aa2f072a1b23345039c8878ef40c640e250243cd0eaed"),     # push + gain tables
)
CONSTANTS = ((RETAIL_LOOKAHEAD, 0.01),)
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError, OSError)


class RunnerVisionError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise RunnerVisionError(message)


def _imm(value):
    return struct.pack("<I", value & 0xFFFFFFFF).hex()


def _f32(value):
    return struct.pack("<f", value).hex()


# Layout inside the allocation (offsets): constants first so every absolute operand is known before assembly.
C_LOOKAHEAD, C_TABLE, C_ENTRY = 0x00, 0x10, 0x40


def _code(code_va, push, *, mode="closest", lookahead=LOOKAHEAD, bearing=DEFENDER_BEARING):
    """The owner bytes at ``code_va`` from the retail push routine bytes ``push`` (1,312 bytes, checked)."""
    from .nfl2k5_draft_ai import _Asm
    require(len(push) == PUSH_SIZE and hashlib.sha256(push).hexdigest() == PUSH_SHA256,
            "the ball-carrier push routine is not retail")
    lookahead_va, table_va = code_va + C_LOOKAHEAD, code_va + C_TABLE
    consts = struct.pack("<f", lookahead).ljust(C_TABLE - C_LOOKAHEAD, b"\0")
    consts += b"".join(struct.pack("<ff", x, y) for x, y in zip(BEARING_POINTS, bearing))
    consts = consts.ljust(C_ENTRY, b"\0")

    def wrapper(copy_va):
        a = _Asm(code_va + C_ENTRY)
        a.label("entry")                                          # called from 0x2E3072: [esp+4] = carrier, ret 4
        a.b("8b442404" "8b480c" "8339ff"); a.j8("75", "retail")   # CPU-controlled only ([[carrier+0xC]] == -1)
        a.b("8b4838" "8b490c" "81b9c4000000" + _imm(URGENCY_HALF)); a.j8("7f", "retail")   # clock urgency > 0.5
        a.jmp_abs(copy_va)                                        # the owner copy returns (ret 4) to the task
        a.label("retail"); a.jmp_abs(PUSH_VA)
        return a

    size = len(wrapper(0).assemble())
    copy_off = (C_ENTRY + size + 15) & -16
    copy_va = code_va + copy_off
    stub_off = copy_off + PUSH_SIZE
    stub_va = code_va + stub_off
    w = wrapper(copy_va)
    entry = w.assemble()

    s = _Asm(stub_va)
    s.label("player")                                             # every other player, esp = the routine's frame
    s.b(PLAYER_SITE[1].hex())                                     # replay: eax = his transform, xmm0 = position
    s.b("8b4e38" "3b0d" + _imm(OFFENSE)); s.j32("0f84", "mate")   # the retail teammate test ([0xE60280] team)
    s.b("8b5318")                                                 # edx = carrier transform
    if mode == "retail":                                          # tests only: everyone takes the retail values,
        s.j32("e9", "mate")                                       # so the copy must equal 0x2E2260 bit for bit
    elif mode == "closest":
        s.b("d94040d86240" "d94048d86248" "d94030d86230" "d94038d86238")   # dz dx dvz dvx (him minus carrier)
        s.b("d8cad9c9d8cbdec1" "d9c9d8c8d9cad8c8dec2" "d9e0")            # -(dp . dv), |dv|^2
        s.b("d9eedff1"); s.j8("73", "now")                        # moving apart (or level): t = 0
        s.b("d9c1d80d" + _imm(lookahead_va) + "dff1"); s.j8("76", "far")   # closest approach beyond the look-ahead
        s.b("def1"); s.j8("eb", "have")                           # t = -(dp . dv) / |dv|^2
        s.label("now"); s.b("ddd8ddd8d9ee"); s.j8("eb", "have")
        s.label("far"); s.b("ddd8ddd8d905" + _imm(lookahead_va))
        s.label("have"); s.b("d95c2474")                          # [esp+0x74] = t
        s.b("d94240d84c2474d84230d95c2478")                       # [esp+0x78] = carrier x + vx t
        s.b("d94248d84c2474d84238d95c247c")                       # [esp+0x7C] = carrier z + vz t
    elif mode == "fixed":                                         # t = the look-ahead for every defender
        s.b("d94240d80d" + _imm(lookahead_va) + "d84230d95c2478")
        s.b("d94248d80d" + _imm(lookahead_va) + "d84238d95c247c")
        s.b("8b0d" + _imm(lookahead_va) + "894c2474")
    else:
        raise RunnerVisionError(f"unknown look-ahead mode {mode!r}")
    s.b("c7442410" + _imm(table_va))                              # defenders: the owner bearing table
    s.jmp_abs(copy_va + PLAYER_RESUME)
    s.label("mate")                                               # teammates: retail look-ahead, position, table
    s.b("8b4c2440894c2478" "8b4c2448894c247c" "8b0d" + _imm(RETAIL_LOOKAHEAD) + "894c2474")
    s.b("c7442410" + _imm(RETAIL_TABLE))
    s.jmp_abs(copy_va + PLAYER_RESUME)
    stub = s.assemble()

    copy = bytearray(push)
    for off in PUSH_CALLS:
        require(copy[off] == 0xE8, f"push routine call at +{off:#x} moved")
        target = PUSH_VA + off + 5 + struct.unpack_from("<i", copy, off + 1)[0]
        struct.pack_into("<i", copy, off + 1, target - (copy_va + off + 5))
    off, before = PLAYER_SITE
    copy[off:off + len(before)] = (b"\xe9" + struct.pack("<i", stub_va - (copy_va + off + 5))).ljust(len(before), b"\x90")
    for off, before in LOOKAHEAD_SITES:
        copy[off:off + len(before)] = LOOKAHEAD_EDIT
    for off, before, after in REFERENCE_SITES:
        copy[off:off + len(before)] = after
    off, before, after = TABLE_SITE
    copy[off:off + len(before)] = after

    body = consts + entry.ljust(copy_off - C_ENTRY, b"\xcc") + bytes(copy) + stub
    require(len(body) <= CODE_SIZE, f"runner vision code exceeds its allocation ({len(body)} > {CODE_SIZE})")
    labels = dict(entry=C_ENTRY, retail=C_ENTRY + w.labels["retail"], copy=copy_off, player=stub_off,
                  mate=stub_off + s.labels["mate"], lookahead=C_LOOKAHEAD, table=C_TABLE, end=len(body))
    return body.ljust(CODE_SIZE, b"\xcc"), labels


def code_for(code_va, push):
    return _code(code_va, push)


def sites(code_va=0):
    name, va, before = HOOK
    return [(name, va, before, b"\xe8" + struct.pack("<i", code_va + C_ENTRY - va - 5))]


def allocation(payload):
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    require(len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"]) == ("code", CODE_SIZE, 16),
            "Missing or foreign runner-vision allocation")
    return rows[0]


def _recognize(payload):
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    present = any(r["owner"] == OWNER for r in space.layout(payload)["allocations"])
    owned = allocation(payload) if present else None
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for _, at, before, _ in sites(0):
            if va <= at and at + len(before) <= va + size:
                content[at - va:at - va + len(before)] = before
        require(hashlib.sha256(content).hexdigest() == digest, f"Foreign runner-vision prerequisite at {va:#x}")
    for va, value in CONSTANTS:
        require(abs(struct.unpack("<f", image.read(va, 4))[0] - value) < 1e-6, f"Foreign runner-vision constant at {va:#x}")
    states = set()
    for _name, va, before, after in sites(owned["va"] if owned else 0):
        raw = image.read(va, len(before))
        states.add("retail" if raw == before else "applied" if owned and raw == after else "foreign")
    if owned:
        raw = image.read(owned["va"], CODE_SIZE)
        states.add("retail" if raw == b"\xcc" * CODE_SIZE else
                   "applied" if raw == code_for(owned["va"], image.read(PUSH_VA, PUSH_SIZE))[0] else "foreign")
    require(states in ({"retail"}, {"applied"}), "Foreign or mixed runner-vision site/code")
    return next(iter(states))


def status(payload):
    try:
        return _recognize(payload)
    except _ERRORS:
        return "foreign"


def neighbor_edits(payload):
    """Another owner's pinned-context view: this owner's installed hook read as the retail bytes it replaced, only
    while the whole owner reads applied (``nfl2k5_ball_carrier_ai`` hashes the carrier task 0x2E2DA0, which holds
    the hooked call). Never calls back into that owner."""
    if status(payload) != "applied":
        return []
    return [(va, before) for _name, va, before, _after in sites(allocation(payload)["va"])]


def apply(payload):
    """Install, or replay an identical installation."""
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_bump_strength import _sections, section_digest
    from .nfl2k5_cave_oracle import XbeImage
    try:
        state = _recognize(payload)
    except _ERRORS as exc:
        raise RunnerVisionError(f"foreign/mixed runner-vision input: {exc}") from exc
    common = dict(owner=OWNER, experimental=True)
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    before = payload
    allocation_receipt = {}
    if not any(r["owner"] == OWNER for r in space.layout(payload)["allocations"]):
        if space.status(payload) == "retail":
            payload, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
        else:
            require(space.is_scaleout(payload), "CPU runner vision needs the scale-out allocator")
            payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
    code_va = allocation(payload)["va"]
    image = XbeImage(payload)
    code, labels = code_for(code_va, image.read(PUSH_VA, PUSH_SIZE))
    payload, _ = space.install_code(payload, OWNER, code)
    edits = sites(code_va)
    image = XbeImage(payload)
    buf = bytearray(payload)
    for _, va, old, new in edits:
        off = image.offset(va, len(old))
        require(bytes(buf[off:off + len(old)]) == old, f"runner-vision site {va:#x} is not retail")
        buf[off:off + len(old)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(_recognize(result) == "applied" and space.status(result) == "applied", "runner-vision postcondition failed")
    return result, dict(common, status="applied", code_va=hex(code_va), labels=labels,
                        before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=space.count_differing_bytes(before, result), file_growth=len(result) - len(before),
                        allocation=allocation_receipt,
                        edits=[dict(label=name, va=hex(va), before=old.hex(), after=new.hex()) for name, va, old, new in edits],
                        reservations=[r for r in space.reservations(result) if r["owner"] == OWNER])


def mapping():
    return {"hook": hex(HOOK[1]), "push_routine": hex(PUSH_VA), "lookahead_seconds": LOOKAHEAD,
            "defender_bearing_weights": dict(zip(("0", "45", "90", "135", "180"), DEFENDER_BEARING)),
            "cpu_only": True, "calm_clock_only": True, "teammates_retail": True,
            "needs": "nfl2k5_ball_carrier_ai (wide_sideline)", "runtime_state_bytes": 0}


def main(argv=None):
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
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
            raise ValueError("Foreign or mixed ball-carrier steering bytes")
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
    print(json.dumps({"status": state, "experimental": True, "runtime_witnessed": False,
                      "requests": REQUESTS, **mapping()}, indent=2))
    return 0


__all__ = ["OWNER", "REQUESTS", "CODE_SIZE", "HOOK", "GUARDS", "code_for", "sites", "allocation", "status",
           "neighbor_edits", "apply", "mapping", "main"]


if __name__ == "__main__":
    raise SystemExit(main())

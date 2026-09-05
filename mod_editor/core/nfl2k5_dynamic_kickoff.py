"""Experimental, unwitnessed 2024/2025 dynamic kickoffs for the retail Xbox XBE.

Pair with kick_rules (35-yard tee) and the playbook kickoff_alignment tool.
No timer releases the hold: ground/player contact latches the first field class.
See ASTRA_KICKOFF_FIX_REPORT.md for the lineup clamp and pre-launch hold fix.

Runtime storage is ten previously unreferenced bytes on the writable shared
.rdata/.data page. 0xA69970 and 0xA69974..7F belong to other patches. Settings
are immediate operands in the patch and copied to that writable storage at
launch; no instruction writes to the code cave. The cave is hash-pinned, so
the distribution contains no copy of the displaced retail function.
"""
from __future__ import annotations

import hashlib
import struct
from typing import Mapping

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest
from .nfl2k5_draft_ai import _Asm

CAVE_VA = 0x2890F0
CAVE_SIZE = 1939
RETAIL_CAVE_SHA256 = "15d306fbdb8b915a5ebfbdbc92634553a644a409e50bfeec87b06d248f8f3d90"
PHASE = 0xE602B4
PLAY_STATE = 0xE602B8
CTX = 0xE602EC
BALL = 0xE5FC00
POSSESSION = 0xE60280
FLAGS = 0xA69969
AIM_PROB = 0xA6996A
TB_PROB = 0xA6996B
KICK_SPOT = 0xA6996C
TB_YARD = 0xA69971
TARGET_MIN = 0xA69972
TARGET_MAX = 0xA69973
STORAGE_RANGES = ((FLAGS, 7), (TB_YARD, 3))
# flags: first contact (bits 0..2), active, negative direction, CPU touchback
# preference, a controlled return has entered the field, force receiving 40.
NONE, LANDING, END_ZONE, SHORT, OUT = range(5)
ACTIVE, NEGATIVE, TAKE_TB, RETURNED, FORCE_40 = 8, 16, 32, 64, 128
GOAL = 0x4E72A0
LANDING_EDGE = 0x4F0F98
HALF_WIDTH = 0x4EE8E0
YARD = 0x4E72B8
RAND = 0x48BC0

# Each overwrite ends on a retail instruction boundary. JMP stubs replay the
# displaced instructions with the original stack, then jump to the continuation.
HOOKS = {
    "launch": (0x222CA0, bytes.fromhex("83ec205355")),
    "aim": (0x222E67, bytes.fromhex("d944243851")),
    "ground": (0xA06E0, bytes.fromhex("558bec83e4f0")),
    "touch": (0xB78C9, bytes.fromhex("a1ec02e600")),
    "dead": (0xB7BB0, bytes.fromhex("558bec83e4f0")),
    "plan": (0x1CD5D0, bytes.fromhex("56578bf98b470c")),
    "motion": (0x218010, bytes.fromhex("a10c1db700")),
    "position": (0x2CC4F0, bytes.fromhex("518b4114d94048")),
    "spot": (0xB65CC, bytes.fromhex("a18002e600")),
    "reset": (0x1C9399, bytes.fromhex("a1a0d95000")),
    "lineup": (0x183F60, bytes.fromhex("558bec83e4f0")),
}


class DynamicKickoffError(ValueError):
    """The executable or requested settings failed a patch precondition."""


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise DynamicKickoffError(message)


def _settings(touchback_yard=35, cpu_landing_probability=90,
              cpu_target_yards=(5, 15), cpu_touchback_probability=90):
    """Probabilities are integer percentages; target is uniform whole yard lines."""
    _require(type(touchback_yard) is int and touchback_yard in (30, 35),
             "touchback_yard must be 30 (2024) or 35 (2025)")
    for name, value in (("cpu_landing_probability", cpu_landing_probability),
                        ("cpu_touchback_probability", cpu_touchback_probability)):
        _require(type(value) is int and 0 <= value <= 100, f"{name} must be an integer percentage 0..100")
    _require(isinstance(cpu_target_yards, (tuple, list)) and len(cpu_target_yards) == 2,
             "cpu_target_yards must be a (minimum, maximum) pair")
    lo, hi = cpu_target_yards
    _require(type(lo) is int and type(hi) is int and 1 <= lo <= hi <= 20,
             "cpu_target_yards must satisfy 1 <= minimum <= maximum <= 20")
    return dict(touchback_yard=touchback_yard, cpu_landing_probability=cpu_landing_probability,
                cpu_target_yards=(lo, hi), cpu_touchback_probability=cpu_touchback_probability)


def _imm(n: int) -> str:
    return struct.pack("<I", n).hex()


def _code(settings):
    a = _Asm(CAVE_VA)
    imm = _imm
    def b(code): a.b(code)
    def label(name): a.label(name)
    def j(op, name): a.j32(op, name)
    def call(name): a.j32("e8", name)
    def save(): b("9c60")  # pushfd, pushad (36 bytes)
    def restore(): b("619d")
    def replay(name):
        va, original = HOOKS[name]
        b(original.hex())
        a.jmp_abs(va + len(original))
    def guard(done, live=False):
        b("833d" + imm(PHASE) + "02"); j("0f85", done)
        b("f605" + imm(FLAGS) + "08"); j("0f84", done)
        if live:
            b("833d" + imm(PLAY_STATE) + "0e"); j("0f85", done)
    def signed_z():  # ST0 := ball/contact z in kicking direction, balanced by caller
        b("d94208")  # fld [edx+8]
        b("f605" + imm(FLAGS) + "10")
        unique = "positive_" + str(len(a.items))
        j("0f84", unique); b("d9e0"); label(unique)
    def compare_pop(va):
        b("d81d" + imm(va) + "dfe0f6c441")  # fcomp, fnstsw ax, test ah, C0|C3
    def percent_roll(va):
        a.call(RAND)
        b("31d2b964000000f7f1")  # unsigned RNG % 100 -> edx
        b("0fb605" + imm(va) + "39c2")  # cmp edx,eax

    label("launch")
    save()
    b("c605" + imm(FLAGS) + "00")
    b("833d" + imm(PHASE) + "02"); j("0f85", "launch_done")
    b("8b74242c")  # original [esp+8] is kicker
    b("85f6"); j("0f84", "launch_done")
    b("8b462085c0"); j("0f84", "launch_done")
    # Query the retail Ball Action opcode (8) on BOTH normal and squib paths.
    b("6a0089e2526a008d881c040000ba08000000")
    a.call(0x1B8CA0)
    b("5a85c0"); j("0f84", "launch_done")
    b("83fa02"); j("0f84", "launch_done")  # declared onside
    b("a1" + imm(CTX) + "85c0"); j("0f84", "launch_done")
    b("8b50188915" + imm(KICK_SPOT))  # exact penalty-adjusted LOS float
    for name, va, value in (("aim_prob", AIM_PROB, settings["cpu_landing_probability"]),
                            ("tb_prob", TB_PROB, settings["cpu_touchback_probability"]),
                            ("tb_yard", TB_YARD, settings["touchback_yard"]),
                            ("target_min", TARGET_MIN, settings["cpu_target_yards"][0]),
                            ("target_max", TARGET_MAX, settings["cpu_target_yards"][1])):
        label("config_" + name)
        b("c605" + imm(va) + f"{value:02x}")
    b("c605" + imm(FLAGS) + "08")
    b("8b46388b40088b400cf7400400000080")  # direction's float sign bit
    j("0f84", "launch_positive")
    b("800d" + imm(FLAGS) + "10")
    label("launch_positive")
    percent_roll(TB_PROB); j("0f83", "launch_done")
    b("800d" + imm(FLAGS) + "20")
    label("launch_done"); restore(); replay("launch")

    label("reset")
    b("c605" + imm(FLAGS) + "00")  # mov does not change flags
    replay("reset")

    label("aim")
    save(); guard("aim_done")
    # Player controller id -1 is CPU. Also honor studio/player lock control.
    b("8b460c85c0"); j("0f84", "aim_done")
    b("8338ff"); j("0f85", "aim_done")
    b("8b4620f6808405000020"); j("0f85", "aim_done")
    percent_roll(AIM_PROB); j("0f83", "aim_done")
    a.call(RAND)
    b("0fb60d" + imm(TARGET_MAX) + "0fb61d" + imm(TARGET_MIN))
    b("29d94131d2f7f101da")  # selected receiving yard = lo + RNG % (hi-lo+1)
    b("b83200000029d050db0424d80d" + imm(YARD))  # (50-yard)*91.44
    b("f605" + imm(FLAGS) + "10"); j("0f84", "aim_positive")
    b("d9e0")
    label("aim_positive")
    b("d825" + imm(KICK_SPOT) + "d9e1")  # abs(target z - exact kick spot)
    b("d95c246083c404")  # original [esp+0x38], accounting for saved regs + temp
    b("c744243800200000")  # original [esp+0x14] elevation = 45 degrees
    b("31c0f605" + imm(FLAGS) + "10"); j("0f84", "aim_heading")
    b("b800800000")
    label("aim_heading"); b("8944243c")  # original [esp+0x18] heading, straight
    label("aim_done"); restore(); replay("aim")

    # Classifier uses the event position, not predicted landing or elapsed time.
    # Returning EAX does NOT mutate the first-contact history.
    label("classify")
    signed_z(); compare_pop(GOAL); j("0f84", "class_end")
    # Include the goal line itself in the end zone (ZF represented by C3).
    b("f6c440"); j("0f85", "class_end")
    b("d902d9e1"); compare_pop(HALF_WIDTH); j("0f84", "class_out")
    b("f6c440"); j("0f85", "class_out")
    signed_z(); compare_pop(LANDING_EDGE)
    b("f6c401"); j("0f85", "class_short")
    b("b801000000c3")
    label("class_end"); b("b802000000c3")
    label("class_short"); b("b803000000c3")
    label("class_out"); b("b804000000c3")

    label("contact")
    call("classify")
    b("f605" + imm(FLAGS) + "07"); j("0f85", "contact_done")
    b("0805" + imm(FLAGS))  # latch first class, never overwrite it
    label("contact_done"); b("c3")

    label("ground")
    save(); guard("ground_done", live=True)
    b("3b0d" + imm(BALL)); j("0f85", "ground_done")
    # EDX is the collision-resolved transform passed by 0x1C841F.
    call("contact")
    b("800d" + imm(TB_PROB) + "80")  # high bit: an actual ground contact occurred
    b("83f804"); j("0f84", "ground_invalid")
    b("0fb605" + imm(FLAGS) + "83e00783f803"); j("0f85", "ground_done")
    label("ground_invalid")
    b("f605" + imm(FLAGS) + "40"); j("0f85", "ground_done")
    b("800d" + imm(FLAGS) + "80")
    call("finish")
    label("ground_done"); restore(); replay("ground")

    label("touch")
    save(); guard("touch_done", live=True)
    b("a1" + imm(BALL) + "85c0"); j("0f84", "touch_done")
    b("8b5014"); call("contact")
    b("83f804"); j("0f84", "touch_invalid")
    b("0fb605" + imm(FLAGS) + "83e00783f803"); j("0f85", "touch_done")
    label("touch_invalid")
    b("f605" + imm(FLAGS) + "40"); j("0f85", "touch_done")
    b("800d" + imm(FLAGS) + "80")
    # Defer the whistle until the next dispatcher/dead event, so retail contact
    # bookkeeping completes before the next-play record is constructed.
    label("touch_done"); restore(); replay("touch")

    # 183F60 otherwise clamps the formation's +25-yard coverage target back
    # behind the tee at 184050. This runs BEFORE launch, so ACTIVE is not a
    # valid guard. Only normal kickoff coverage bypasses the retail clamp.
    label("lineup")
    save()
    b("8b41383b05" + imm(POSSESSION)); j("0f85", "lineup_go")
    call("aligned_roles"); b("85c0"); j("0f84", "lineup_go")
    restore(); b("c3")
    label("lineup_go"); restore(); replay("lineup")

    # State 12 is still lining up; 158C90 advances to 13 only when both teams
    # are ready. State 14 starts before the animation's 222CA0 ball launch.
    # Hold through that approach as well as flight, without freezing setup.
    label("held")
    b("a1" + imm(PLAY_STATE) + "83e80d83f801"); j("0f87", "held_no")
    b("f605" + imm(FLAGS) + "07"); j("0f85", "held_no")
    # EAX=1 only for the 19 coverage/setup slots of a normal kickoff. The
    # selected kicking formation is available before CTX+1C4 (last kicker).
    # Onside type 10 and safety phase 1 retain their retail behavior.
    label("aligned_roles")
    b("833d" + imm(PHASE) + "02"); j("0f85", "held_no")
    b("83791c01"); j("0f85", "held_no")
    b("83794800"); j("0f85", "held_no")
    b("80792e0b"); j("0f83", "held_no")
    b("8b15" + imm(POSSESSION) + "85d2"); j("0f84", "held_no")
    b("8b420c85c0"); j("0f84", "held_no")
    b("8b400885c0"); j("0f84", "held_no")
    b("8b400425003f00003d00080000"); j("0f85", "held_no")
    b("8b413839d0"); j("0f85", "held_receiving")
    b("80792e00"); j("0f84", "held_no")
    j("e9", "held_yes")
    label("held_receiving")
    b("3b02"); j("0f85", "held_no")
    b("80792e02"); j("0f82", "held_no")
    label("held_yes"); b("b801000000c3")
    label("held_no"); b("31c0c3")

    label("plan")
    save(); call("returner")
    # Restore the input ECX after any retail calls made by returner().
    b("8b4c2418"); call("held"); b("85c0"); j("0f84", "plan_go")
    restore(); b("c3")
    label("plan_go"); restore(); replay("plan")

    label("motion")
    save(); b("89f1"); call("held"); b("85c0"); j("0f84", "motion_go")
    # Skip both root motion and animation time; mark the animation as updated.
    b("8b4614c7405401000000")
    restore(); b("c3")
    label("motion_go"); restore(); replay("motion")

    label("position")
    save(); call("held"); b("85c0"); j("0f84", "position_go")
    # 28DFE0 snapshots the previous transform at +0..2F before each frame.
    # 28CC30 ends collision correction through this setter. Restore position,
    # orientation and velocity together, including human-selected coverage men.
    b("8b4c24188b71188d7e30b90c000000fcf3a5")
    restore(); b("c20800")
    label("position_go"); restore(); replay("position")

    label("returner")
    guard("return_done", live=True)
    b("f605" + imm(FLAGS) + "80"); j("0f85", "return_finish")
    b("a1" + imm(BALL) + "85c0"); j("0f84", "return_done")
    b("8b1085d2"); j("0f84", "return_loose")
    b("39ca"); j("0f85", "return_done")  # only actual holder's dispatcher
    j("e9", "return_player")
    label("return_loose")
    # A CPU deep returner may leave a grounded end-zone ball downed. Never
    # whistle an airborne, unfielded ball just because it crossed the goal line.
    b("f605" + imm(TB_PROB) + "80"); j("0f84", "return_done")
    b("80792e02"); j("0f83", "return_done")
    label("return_player")
    b("83791c01"); j("0f85", "return_done")
    b("8b15" + imm(CTX) + "8b92c401000085d2"); j("0f84", "return_done")
    b("8b52388b123b5138"); j("0f85", "return_done")  # receiving team
    b("8b5014"); call("contact")
    b("83f802"); j("0f84", "return_end")
    b("a1" + imm(BALL) + "833800"); j("0f84", "return_done")
    b("800d" + imm(FLAGS) + "40c3")  # field entered under possession
    label("return_end")
    b("f605" + imm(FLAGS) + "40"); j("0f85", "return_done")
    b("f605" + imm(FLAGS) + "20"); j("0f84", "return_done")
    b("8b410c85c0"); j("0f84", "return_done")
    b("8338ff"); j("0f85", "return_done")
    b("8b4120f6808405000020"); j("0f85", "return_done")
    label("return_finish"); call("finish")
    label("return_done"); b("c3")

    label("dead")
    save(); guard("dead_go", live=True)
    b("f605" + imm(FLAGS) + "40"); j("0f85", "dead_go")
    b("3b0d" + imm(BALL)); j("0f85", "dead_go")
    b("8b5114"); call("contact")
    b("f605" + imm(FLAGS) + "80"); j("0f85", "dead_finish")
    b("83f802"); j("0f84", "dead_finish")
    b("83f804"); j("0f85", "dead_go")
    b("800d" + imm(FLAGS) + "80")
    label("dead_finish"); call("finish")
    restore(); b("c3")
    label("dead_go"); restore(); replay("dead")

    # Use the retail touchback/dead-play transition, retaining kick ownership
    # bookkeeping. force-40 overrides the spot afterward. The short/OOB
    # announcement/penalty-choice UI remains a witness item, not a claim.
    label("finish")
    b("b80000803ff605" + imm(FLAGS) + "10"); j("0f84", "finish_positive")
    b("0d00000080")
    label("finish_positive")
    b("508b0d" + imm(CTX) + "89817c010000")
    b("83c40431c9")  # param_1=0 for next-spot builder through A0390
    a.call(0xA0390)
    b("c3")

    label("spot")
    save(); guard("spot_done")
    b("a1" + imm(CTX) + "83b87c01000000"); j("0f84", "spot_done")
    b("f605" + imm(FLAGS) + "40"); j("0f85", "spot_done")
    b("f605" + imm(FLAGS) + "80"); j("0f85", "spot_40")
    b("0fb615" + imm(FLAGS) + "83e20783fa01"); j("0f84", "spot_20")
    b("83fa02"); j("0f85", "spot_done")
    b("0fb615" + imm(TB_YARD)); j("e9", "spot_calc")
    label("spot_20"); b("ba14000000"); j("e9", "spot_calc")
    label("spot_40"); b("ba28000000")
    label("spot_calc")
    b("b93200000029d151db0424d80d" + imm(YARD))
    b("f605" + imm(FLAGS) + "10"); j("0f84", "spot_positive")
    b("d9e0")
    label("spot_positive")
    b("d95c244083c404")  # original [esp+0x18] after save + temp
    b("c744243400000000")  # original [esp+0x10] = centered x
    label("spot_done"); restore(); replay("spot")
    code = a.assemble()
    _require(len(code) <= CAVE_SIZE, f"dynamic kickoff code {len(code)} exceeds cave {CAVE_SIZE}")
    return code + b"\xcc" * (CAVE_SIZE - len(code)), {k: CAVE_VA + v for k, v in a.labels.items()}


def cave_labels() -> dict[str, int]:
    return _code(_settings())[1]


def cave_bytes(**kwargs) -> bytes:
    return _code(_settings(**kwargs))[0]


def _offset(payload: bytes, va: int, size: int) -> int:
    for section in _sections(payload):
        if section.virtual_address <= va and va + size <= section.virtual_address + section.raw_size:
            off = section.raw_offset + va - section.virtual_address
            _require(0 <= off <= len(payload) - size, f"truncated XBE at {va:#x}")
            return off
    raise DynamicKickoffError(f"VA {va:#x}+{size:#x} has no complete file-backed range")


def _hook_bytes(name, labels):
    va, original = HOOKS[name]
    return b"\xe9" + struct.pack("<i", labels[name] - va - 5) + b"\x90" * (len(original) - 5)


def _decode_settings(payload):
    labels = cave_labels()
    vals = {key: payload[_offset(payload, labels["config_" + key] + 6, 1)]
            for key in ("aim_prob", "tb_prob", "tb_yard", "target_min", "target_max")}
    return _settings(vals["tb_yard"], vals["aim_prob"],
                     (vals["target_min"], vals["target_max"]), vals["tb_prob"])


def _validate_storage(payload):
    # Both neighbours share page A69000 and both must be writable. The gap is
    # virtual padding, NOT the similarly numbered file-offset padding.
    ss = _sections(payload)
    for start, size in STORAGE_RANGES:
        page = start & ~0xFFF
        neighbours = [s for s in ss if s.virtual_address < page + 0x1000
                      and s.virtual_address + struct.unpack_from("<I", payload, s.header_offset + 8)[0] > page]
        _require(len(neighbours) == 2 and all(struct.unpack_from("<I", payload, s.header_offset)[0] == 7
                                            for s in neighbours), "runtime storage page is not writable")
        _require(all(not (s.virtual_address < start + size and
                          s.virtual_address + struct.unpack_from("<I", payload, s.header_offset + 8)[0] > start)
                     for s in ss), "runtime storage is no longer an unowned section gap")


def status(payload: bytes) -> str:
    try:
        _validate_storage(payload)
        off = _offset(payload, CAVE_VA, CAVE_SIZE)
        got = payload[off:off + CAVE_SIZE]
        labels = cave_labels()
        retail = hashlib.sha256(got).hexdigest() == RETAIL_CAVE_SHA256
        patched = False
        if not retail:
            try:
                patched = got == cave_bytes(**_decode_settings(payload))
            except (ValueError, struct.error, IndexError):
                pass
        expected = "retail" if retail else "applied" if patched else "foreign"
        if expected == "foreign":
            return expected
        for name, (va, original) in HOOKS.items():
            off = _offset(payload, va, len(original))
            if payload[off:off + len(original)] != (original if retail else _hook_bytes(name, labels)):
                return "foreign"
        return expected
    except (ValueError, struct.error, IndexError):
        return "foreign"


def read_settings(payload: bytes) -> dict[str, object]:
    state = status(payload)
    return {"status": state, **(_decode_settings(payload) if state == "applied" else {})}


def apply(payload: bytes, *, touchback_yard=35, cpu_landing_probability=90,
          cpu_target_yards=(5, 15), cpu_touchback_probability=90) -> tuple[bytes, Mapping[str, object]]:
    settings = _settings(touchback_yard, cpu_landing_probability, cpu_target_yards, cpu_touchback_probability)
    state = status(payload)
    _require(state != "foreign", "dynamic kickoff sites or storage layout are foreign; rebuild from a supported base")
    if state == "applied":
        _require(_decode_settings(payload) == settings, "dynamic kickoff already applied with different settings; rebuild from base")
        return payload, {"status": "already_applied", "changed_bytes": 0, **settings}
    code, labels = _code(settings)
    edits = [("cave", CAVE_VA, code)] + [(n, va, _hook_bytes(n, labels)) for n, (va, _) in HOOKS.items()]
    buf = bytearray(payload)
    sections = _sections(payload)
    touched = set()
    for _name, va, after in edits:
        off = _offset(payload, va, len(after))
        buf[off:off + len(after)] = after
        touched.add(_section_for_offset(sections, off).index)
    for section in sections:
        if section.index in touched:
            off = section.header_offset + 36
            buf[off:off + 20] = section_digest(bytes(buf), section)
    result = bytes(buf)
    _require(status(result) == "applied", "dynamic kickoff post-apply verification failed")
    return result, {"status": "applied", "experimental": True, **settings,
                    "changed_bytes": sum(x != y for x, y in zip(payload, result)),
                    "sections_repinned": sorted(touched),
                    "edits": [{"label": n, "va": hex(va), "bytes": len(data)} for n, va, data in edits]}

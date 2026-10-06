"""Opt-in ability-based charge cap and feedback for APF BASE and TU 1.1.

Xenia transport follows the fourth-down option. Flat-image apply/revert is
strict and in memory; neither the compressed XEX nor roster stats are changed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import tomllib

from .errors import ValidationError
from .apf2k8_playcall_patch import (
    IMAGE_BASE, IMAGE_SIZE, PROFILES, TITLE_ID, _Assembler, _branch, _d, _rl,
    check_image, export_patch,
)

DEFAULT_ENABLED = False
CLASSIFICATION = "EXPERIMENTAL"
FILENAME = "54540807-studio-charge-abilities.patch.toml"
NAME = "Ability-based charge cap (experimental, unwitnessed)"
CURRENT_REVISION = 4
CAVE = 0x84D0D100
LEGACY_CAVE_LIMIT = 0x84D0D180
CAVE_LIMIT_REV3 = 0x84D0D320
CAVE_LIMIT = 0x84D0D800
FEEDBACK_CAVE = CAVE + 0x50
MOVE_CAVE = LEGACY_CAVE_LIMIT
LATCH_FEEDBACK_CAVE = CAVE_LIMIT_REV3
LATCH_CONSUME_CAVE = 0x84D0D400
LATCH_DOWNGRADE_CAVE = 0x84D0D700
LATCH_START, LATCH_COUNT, LATCH_ENTRY_SIZE = 0x852D6800, 128, 12
LATCH_LIMIT = LATCH_START + LATCH_COUNT * LATCH_ENTRY_SIZE
CONSUME_HOOK, DOWNGRADE_HOOK = 0x848C4D74, 0x848C4D68
SHARED_MOVE_RETURN = 0x848E7F14
ROUTINE = 0x848C51C0
HOOK = 0x848C5288
RESUME = 0x848C52AC
QB_GATE = 0x848C5214
RETAIL_CAP = bytes.fromhex(
    "817d0044 816b0010 556b056c 2b0b0200 409a0010 "
    "2f1c0000 3b600001 419a0008 3b600000"
)
RETAIL_QB_GATE = bytes.fromhex(
    "817d0044 3b800001 816b0028 5569077a 2b090000 409a001c "
    "556b0738 2b0b0000 409a0010 816a0018 556b07b8 916a0018"
)
# BASE display family, independently matched in TU at +FD0 (not +E38).
# The packet's charge channel is unused during the active discharge ripple.
# Keep the consumed level there so both render callers, including interpolated
# snapshots, select the effect without dereferencing a live player pointer.
FEEDBACK_HOOK = 0x84AA6050
FEEDBACK_EDITS = (
    (0x84AA6100, 0xED9EFEFA, 0xED9E06F2),  # floor charge * 511; level 1 stays below .5
    (0x84AA66CC, 0x409A0014, 0x60000000),  # all tiers: min(charge / 2, 1)
    (0x84AA673C, 0x2F170001, 0xFF1DF000),  # fcmpu cr6,f29,f30 (full level-2 marker)
    (0x84AA6940, 0x419900B4, 0x60000000),  # outer ring follows charge, any tier
)
# Save Players coordinates, corroborated by the retail .string_ help text.
# QB arms use the same cap after the unchanged no-arm input gate.
CHARGED_ABILITIES = (
    ("ankle_breaker", 36, 3), ("arms_of_steel", 36, 2),
    ("battering_ram", 36, 1), ("cyclone", 36, 0),
    ("stop_on_a_dime", 37, 7), ("swim", 42, 0),
    ("bull_rush", 43, 7), ("club", 43, 6), ("rip", 43, 5),
    ("spin", 43, 4), ("laser_arm", 43, 3), ("rocket_arm", 43, 2),
    ("finesse", 44, 3), ("power", 44, 2), ("finesse_and_power", 44, 1),
)
WORD_MASKS = ((0x24, 0x0F800000), (0x28, 0x000001FC), (0x2C, 0x0E000000))

# (BASE site, TU delta, original pair, output register, roster register,
#  player register when the roster pointer must be reloaded, family).
# Only the output GPR and CR6 change. Each original pair feeds a zero test.
# The strength contact selectors and charge bonus helper use the same union.
MOVE_CHECKS = (
    (0x848E7F94, 0xE88, (0x896B0024, 0x556B07FE), 11, 11, 30, "finesse"),
    (0x848E7FA0, 0xE88, (0x816B0024, 0x556B2FFE), 11, 11, 30, "finesse"),
    (0x848C4BA4, 0xE38, (0x897E0024, 0x556B07FE), 11, 30, None, "finesse"),
    (0x848C4BEC, 0xE38, (0x817E0024, 0x556B0108), 11, 30, None, "finesse"),
    (0x848C4C18, 0xE38, (0x815E0024, 0x554A014A), 10, 30, None, "power"),
    (0x848C4C40, 0xE38, (0x817E0024, 0x556B018C), 11, 30, None, "power"),
    (0x848BA3CC, 0xE38, (0x816B0024, 0x556B018C), 11, 11, 31, "power"),
    (0x848BA3FC, 0xE38, (0x816B0024, 0x556B014A), 11, 11, 31, "power"),
)


def move_address(check, profile):
    address(ROUTINE, profile)
    return check[0] + (check[1] if profile == PROFILES[1] else 0)


def move_trampolines(profile):
    """Union the named move ability with Finesse/Power and their combination.

    Re-read the packed roster without changing it. No stack, CR0, LR, CTR,
    floating-point or extra GPR writes. Preserve the retail nonzero value on
    fallback; the added abilities return 1 to the existing zero comparison.
    """
    start = MOVE_CAVE
    result = []
    for check in MOVE_CHECKS:
        _, _, original, out, roster, player, family = check
        asm = _Assembler(start)
        masks = ((28, 28), (30, 30)) if family == "finesse" else ((29, 30),)
        for mb, me in masks:
            if player is not None:
                asm.emit(_d(32, out, player, 0x44))
            asm.emit(_d(34, out, roster, 0x2C))
            asm.emit(_rl(out, out, 0, mb, me))
            asm.emit(0x2B000000 | out << 16)  # cmplwi cr6,out,0
            asm.jump("qualified", "ne")
        if player is not None:
            asm.emit(_d(32, out, player, 0x44))
        for word in original:
            asm.emit(word)
        asm.jump("return")
        asm.label("qualified")
        asm.emit(_d(14, out, 0, 1))
        asm.label("return")
        asm.emit(_branch(start + len(asm.words) * 4, move_address(check, profile) + 8))
        code = asm.finish()
        result.append((check, start, code))
        start += len(code)
    if start > CAVE_LIMIT:
        raise ValidationError("Move ability checks exceed their reserved code space")
    return tuple(result)


def address(base, profile):
    if profile not in PROFILES:
        raise ValidationError("Choose BASE or Title Update 1.1")
    return base + (0xE38 if profile == PROFILES[1] else 0)


def feedback_address(base, profile):
    address(ROUTINE, profile)  # validate the profile
    return base + (0xFD0 if profile == PROFILES[1] else 0)


def feedback_trampoline(profile, revision=3):
    """Snapshot the consumed state using only dead r11, CR6 and output f30.

    r10 is the player state; f28=0, f18=1. State 4 is a consumed level 2,
    state 1 a consumed level 1. The caller already selected 0 <= timer < 10.
    The timer channel and medal bits remain untouched.
    """
    if revision >= 4:
        return latched_feedback_trampoline(profile)
    asm = _Assembler(FEEDBACK_CAVE)
    asm.emit(_d(32, 11, 10, 0x1A8))
    asm.emit(_rl(11, 11, 10, 29, 31))
    asm.emit(0x2B0B0004)  # cmplwi cr6,r11,4
    asm.emit(0xFFC0E090)  # fmr f30,f28 (no second-level discharge)
    asm.jump("return", "ne")
    asm.emit(0xFFC09090)  # fmr f30,f18
    asm.label("return")
    asm.emit(_branch(FEEDBACK_CAVE + len(asm.words) * 4,
                     feedback_address(FEEDBACK_HOOK + 4, profile)))
    return asm.finish()


def _save_scratch(asm, registers):
    """Preserve full Xenon GPRs and all CR fields without a callee or CTR use."""
    asm.emit(_d(37, 1, 1, -0x80))  # stwu r1,-128(r1)
    for i, register in enumerate(registers):
        asm.emit(_d(62, register, 1, 0x10 + i * 8))  # std
    asm.emit(0x7C000026 | registers[0] << 21)  # mfcr
    asm.emit(_d(36, registers[0], 1, 0x70))


def _restore_scratch(asm, registers):
    asm.emit(_d(32, registers[0], 1, 0x70))
    asm.emit(0x7C0FF120 | registers[0] << 21)  # mtcrf 255
    for i, register in enumerate(registers):
        asm.emit(_d(58, register, 1, 0x10 + i * 8))  # ld
    asm.emit(_d(14, 1, 1, 0x80))


def _load_address(asm, register, target):
    asm.emit(_d(15, register, 0, (target + 0x8000) >> 16))
    asm.emit(_d(14, register, register, target))


def _compare(asm, left, right):
    asm.emit(0x7F000040 | left << 16 | right << 11)  # cmplw cr6


def latched_feedback_trampoline(profile):
    """Read the captured action effect after native cleanup clears consumed bits.

    The fixed table is keyed by state and roster pointers. It never dereferences
    a stored pointer, and a missing or saturated-table key yields level 1.
    Only f30 changes; all GPRs, CR, LR, CTR, other FPRs and SP are preserved.
    """
    asm = _Assembler(LATCH_FEEDBACK_CAVE)
    registers = (6, 7, 8, 9, 10, 11)
    _save_scratch(asm, registers)
    asm.emit(0xFFC0E090)  # fmr f30,f28
    asm.emit(_d(32, 9, 29, 0x44))
    _load_address(asm, 7, LATCH_START)
    _load_address(asm, 8, LATCH_LIMIT)
    asm.label("scan")
    asm.emit(_d(32, 6, 7, 0))
    _compare(asm, 6, 10)
    asm.jump("next", "ne")
    asm.emit(_d(32, 6, 7, 4))
    _compare(asm, 6, 9)
    asm.jump("restore", "ne")
    asm.emit(_d(32, 6, 7, 8))
    asm.emit(0x2B060001)
    asm.jump("restore", "ne")
    asm.emit(0xFFC09090)  # fmr f30,f18
    asm.jump("restore")
    asm.label("next")
    asm.emit(_d(14, 7, 7, LATCH_ENTRY_SIZE))
    _compare(asm, 7, 8)
    asm.jump("scan", "lt")
    asm.label("restore")
    _restore_scratch(asm, registers)
    asm.emit(_branch(LATCH_FEEDBACK_CAVE + len(asm.words) * 4,
                     feedback_address(FEEDBACK_HOOK + 4, profile)))
    code = asm.finish()
    if LATCH_FEEDBACK_CAVE + len(code) > LATCH_CONSUME_CAVE:
        raise ValidationError("Charge latch feedback exceeds its reservation")
    return code


def latch_consume_trampoline(profile):
    """Capture full charge and the executed HB action before its native consume.

    The shared spin/juke entry consumes before dispatch changes its generic
    descriptor. Its saved caller LR identifies that entry; requested state
    IDs 0x1b..0x1f are spin, 0x20..0x22 are juke. The other native descriptor
    categories are 0x17 stiff arm, 0x19 shoulder charge and 0x1b stop.
    Other consumers retain their existing level decision. No gameplay field
    or roster byte is written. A full table refuses a new state key.
    """
    asm = _Assembler(LATCH_CONSUME_CAVE)
    registers = (5, 6, 7, 8, 9, 10, 11)
    _save_scratch(asm, registers)
    asm.emit(_d(32, 10, 3, 0x14))
    asm.emit(_d(32, 9, 3, 0x44))
    asm.emit(_d(14, 5, 0, 0))
    asm.emit(_d(32, 11, 10, 0xFC))
    # Positive finite IEEE-754 charge >= 2 exactly matches the native full
    # consume threshold. Reject negatives, infinities and NaNs conservatively.
    asm.emit(_d(15, 7, 0, 0x4000))
    asm.emit(0x7F000000 | 11 << 16 | 7 << 11)  # cmpw cr6
    asm.jump("store", "lt")
    asm.emit(_d(15, 7, 0, 0x7F80))
    _compare(asm, 11, 7)
    asm.jump("store", "ge")
    asm.emit(_d(14, 5, 0, 1))
    shared = SHARED_MOVE_RETURN + (0xE88 if profile == PROFILES[1] else 0)
    _load_address(asm, 7, shared)
    _compare(asm, 12, 7)
    asm.jump("category", "ne")
    asm.emit(_d(32, 6, 10, 0))
    asm.emit(0x2B06001B)
    asm.jump("category", "lt")
    asm.emit(0x2B060023)
    asm.jump("category", "ge")
    asm.emit(0x2B060020)
    asm.jump("spin", "lt")
    asm.jump("juke")
    asm.label("category")
    asm.emit(_d(32, 6, 10, 4))
    asm.emit(0x2B060000)
    asm.jump("store", "eq")
    asm.emit(_d(34, 6, 6, 0))
    for category, label in ((0x10, "juke"), (0x11, "spin"),
                            (0x17, "stiff"), (0x19, "shoulder"), (0x1B, "stop")):
        asm.emit(0x2B060000 | category)
        asm.jump(label, "eq")
    asm.jump("store")
    for label, own, union in (("spin", 1, 0xA), ("juke", 8, 0xA),
                              ("stiff", 4, 6), ("shoulder", 2, 6),
                              ("stop", 0, 0)):
        asm.label(label)
        if label == "stop":
            asm.emit(_d(34, 6, 9, 0x25))
            asm.emit(_d(28, 6, 6, 0x80))
        else:
            asm.emit(_d(34, 6, 9, 0x2C))
            asm.emit(_d(28, 6, 6, union))
            asm.emit(0x2B060000)
            asm.jump("store", "ne")
            asm.emit(_d(34, 6, 9, 0x24))
            asm.emit(_d(28, 6, 6, own))
        asm.emit(0x2B060000)
        asm.jump("store", "ne")
        asm.emit(_d(14, 5, 0, 0))
        asm.jump("store")
    asm.label("store")
    _load_address(asm, 7, LATCH_START)
    _load_address(asm, 8, LATCH_LIMIT)
    asm.label("scan")
    asm.emit(_d(32, 6, 7, 0))
    _compare(asm, 6, 10)
    asm.jump("write", "eq")
    asm.emit(0x2B060000)
    asm.jump("write", "eq")
    asm.emit(_d(14, 7, 7, LATCH_ENTRY_SIZE))
    _compare(asm, 7, 8)
    asm.jump("scan", "lt")
    asm.jump("restore")
    asm.label("write")
    # Publish an unqualified entry first. A reader interrupted by this writer
    # can lose a second-level frame, but cannot borrow an older actor's level.
    asm.emit(_d(14, 6, 0, 0))
    asm.emit(_d(36, 6, 7, 8))
    asm.emit(_d(36, 10, 7, 0))
    asm.emit(_d(36, 9, 7, 4))
    asm.emit(_d(36, 5, 7, 8))
    asm.label("restore")
    _restore_scratch(asm, registers)
    asm.emit(0x9181FFF8)  # displaced stw r12,-8(r1)
    asm.emit(_branch(LATCH_CONSUME_CAVE + len(asm.words) * 4,
                     address(CONSUME_HOOK + 4, profile)))
    code = asm.finish()
    if LATCH_CONSUME_CAVE + len(code) > LATCH_DOWNGRADE_CAVE:
        raise ValidationError("Charge consume latch exceeds its reservation")
    return code


def latch_downgrade_trampoline(profile):
    """Mirror a native 4->1 action downgrade in the visual latch only."""
    asm = _Assembler(LATCH_DOWNGRADE_CAVE)
    asm.emit(0x916A01A8)  # displaced native consumed-state store
    registers = (6, 7, 8, 9, 10, 11)
    _save_scratch(asm, registers)
    asm.emit(_d(32, 9, 3, 0x44))
    _load_address(asm, 7, LATCH_START)
    _load_address(asm, 8, LATCH_LIMIT)
    asm.label("scan")
    asm.emit(_d(32, 6, 7, 0))
    _compare(asm, 6, 10)
    asm.jump("next", "ne")
    asm.emit(_d(32, 6, 7, 4))
    _compare(asm, 6, 9)
    asm.jump("restore", "ne")
    asm.emit(_d(14, 6, 0, 0))
    asm.emit(_d(36, 6, 7, 8))
    asm.jump("restore")
    asm.label("next")
    asm.emit(_d(14, 7, 7, LATCH_ENTRY_SIZE))
    _compare(asm, 7, 8)
    asm.jump("scan", "lt")
    asm.label("restore")
    _restore_scratch(asm, registers)
    asm.emit(_branch(LATCH_DOWNGRADE_CAVE + len(asm.words) * 4,
                     address(DOWNGRADE_HOOK + 4, profile)))
    code = asm.finish()
    if LATCH_DOWNGRADE_CAVE + len(code) > CAVE_LIMIT:
        raise ValidationError("Charge downgrade latch exceeds its reservation")
    return code


def trampoline(profile):
    """Only r11, r27 and CR6 change, as in the displaced cap block.

    No stack, CR0, LR, CTR, floating-point or other GPR writes. Repeated
    pointer loads avoid borrowing an additional live register.
    """
    asm = _Assembler(CAVE)
    for offset, mb, me in ((0x24, 4, 8), (0x28, 23, 29), (0x2C, 4, 6)):
        asm.emit(_d(32, 11, 29, 0x44))
        asm.emit(_d(32, 11, 11, offset))
        asm.emit(_rl(11, 11, 0, mb, me))
        asm.emit(0x2B0B0000)  # cmplwi cr6,r11,0
        asm.jump("present", "ne")
    asm.emit(_d(14, 27, 0, 0))
    asm.jump("return")
    asm.label("present")
    asm.emit(_d(14, 27, 0, 1))
    asm.label("return")
    asm.emit(_branch(CAVE + len(asm.words) * 4, address(RESUME, profile)))
    return asm.finish()


def maximum_charge(record, *, qb_passing=False):
    """Authored decision preview; native tests execute the actual state machine."""
    if len(record) < 45:
        raise ValidationError("Charge preview requires packed roster bytes 0..44")
    if qb_passing and not record[43] & 0x0C:
        return 0
    return 2 if any(record[offset] & (1 << bit) for _, offset, bit in CHARGED_ABILITIES) else 1


@dataclass(frozen=True)
class PatchDocument:
    profile: object
    enabled: bool = DEFAULT_ENABLED
    revision: int = CURRENT_REVISION

    def __post_init__(self):
        if (self.profile not in PROFILES or type(self.enabled) is not bool
                or type(self.revision) is not int or self.revision not in (1, 2, 3, CURRENT_REVISION)):
            raise ValidationError("Choose a supported image and a boolean enable flag")

    @property
    def reservation_end(self):
        return CAVE_LIMIT if self.revision >= 4 else CAVE_LIMIT_REV3 if self.revision == 3 else LEGACY_CAVE_LIMIT

    @property
    def original_words(self):
        words = ((address(HOOK, self.profile), int.from_bytes(RETAIL_CAP[:4], "big")),)
        if self.revision == 1:
            return words
        words += ((feedback_address(FEEDBACK_HOOK, self.profile), 0xFFC0E090),) + tuple(
            (feedback_address(a, self.profile), old) for a, old, _ in FEEDBACK_EDITS
        )
        if self.revision >= 3:
            words += tuple((move_address(check, self.profile) + i * 4, word)
                           for check in MOVE_CHECKS for i, word in enumerate(check[2]))
        if self.revision >= 4:
            words += ((address(CONSUME_HOOK, self.profile), 0x9181FFF8),
                      (address(DOWNGRADE_HOOK, self.profile), 0x916A01A8))
            words += tuple((a, 0) for a in range(LATCH_START, LATCH_LIMIT, 4))
        return words

    @property
    def words(self):
        code = trampoline(self.profile)
        words = ((address(HOOK, self.profile), _branch(address(HOOK, self.profile), CAVE)),) + tuple(
            (CAVE + i, int.from_bytes(code[i:i + 4], "big")) for i in range(0, len(code), 4)
        )
        if self.revision == 1:
            return words
        feedback = feedback_trampoline(self.profile, self.revision)
        feedback_cave = LATCH_FEEDBACK_CAVE if self.revision >= 4 else FEEDBACK_CAVE
        if feedback_cave + len(feedback) > CAVE_LIMIT:
            raise ValidationError("Charge feedback exceeds its reserved code space")
        hook = feedback_address(FEEDBACK_HOOK, self.profile)
        words += ((hook, _branch(hook, feedback_cave)),) + tuple(
            (feedback_address(a, self.profile), new) for a, _, new in FEEDBACK_EDITS
        ) + tuple((feedback_cave + i, int.from_bytes(feedback[i:i + 4], "big"))
                  for i in range(0, len(feedback), 4))
        if self.revision >= 3:
            for check, cave, code in move_trampolines(self.profile):
                hook = move_address(check, self.profile)
                words += ((hook, _branch(hook, cave)),) + tuple(
                    (cave + i, int.from_bytes(code[i:i + 4], "big")) for i in range(0, len(code), 4))
        if self.revision >= 4:
            for site, cave, code in ((CONSUME_HOOK, LATCH_CONSUME_CAVE, latch_consume_trampoline(self.profile)),
                                     (DOWNGRADE_HOOK, LATCH_DOWNGRADE_CAVE, latch_downgrade_trampoline(self.profile))):
                hook = address(site, self.profile)
                words += ((hook, _branch(hook, cave)),) + tuple(
                    (cave + i, int.from_bytes(code[i:i + 4], "big")) for i in range(0, len(code), 4))
            words += tuple((a, 0) for a in range(LATCH_START, LATCH_LIMIT, 4))
        return words

    @property
    def receipt(self):
        result = {"schema": f"apf2k8_charge_abilities/v{self.revision}", "classification": CLASSIFICATION,
                "revision": self.revision, "feedback_follows_charge": self.revision >= 2,
                "move_ability_unions": self.revision >= 3,
                "profile": self.profile.name, "image_sha256": self.profile.sha256,
                "module_hash": self.profile.module_hash, "enabled": self.enabled,
                "routine": address(ROUTINE, self.profile), "hook": address(HOOK, self.profile),
                "gold_comparison": address(HOOK + 12, self.profile),
                "resume": address(RESUME, self.profile), "qb_gate": address(QB_GATE, self.profile),
                "qb_gate_preserved": True, "passing_mode_cap_replaced": True,
                "trampoline": CAVE, "reservation_end": self.reservation_end,
                "section": ".text", "reservation_section": "XEX code page 0x84D00000 (0x11), after .text virtual end",
                "retail_cap_bytes": RETAIL_CAP.hex(), "retail_qb_gate_bytes": RETAIL_QB_GATE.hex(),
                "word_masks": [list(row) for row in WORD_MASKS],
                "charged_abilities": [name for name, _, _ in CHARGED_ABILITIES],
                "writes": [{"address": a, "value": w} for a, w in self.words],
                "original_words": [{"address": a, "value": w} for a, w in self.original_words],
                "scope": ("Input charge state machine" + (" and charge feedback" if self.revision >= 2 else "")
                          + ("; Finesse/Finesse and Power qualify spin/juke; Power/Finesse and Power qualify stiff arm/shoulder charge" if self.revision >= 3 else "")
                          + ("; action-qualified visual latch survives native charge cleanup" if self.revision >= 4 else "")
                          + "; CPU bypass unchanged; gameplay UNWITNESSED.")}
        if self.revision >= 4:
            result["visual_latch"] = {"start": LATCH_START, "end": LATCH_LIMIT,
                                      "entries": LATCH_COUNT, "entry_size": LATCH_ENTRY_SIZE,
                                      "key": ["state pointer", "roster pointer"],
                                      "saturation": "new state keys show level-1 discharge",
                                      "native_gameplay_state_preserved": True}
        return result

    def as_toml(self):
        description = ("Level 2 requires a charged ability, at any tier. QB no-arm gate preserved. Gameplay UNWITNESSED."
                       if self.revision == 1 else
                       "Level 2 and its ring follow charge abilities at any tier; discharge follows consumed level. QB no-arm gate preserved. Gameplay UNWITNESSED."
                       if self.revision == 2 else
                       "Revision 3: Finesse or Finesse and Power qualify spin/juke; Power or Finesse and Power qualify stiff arm/shoulder charge. Charge and feedback follow abilities at any tier. QB no-arm gate preserved. Gameplay UNWITNESSED."
                       if self.revision == 3 else
                       "Revision 4: discharge retains the executed move's qualified charge after native cleanup. Finesse qualifies spin/juke; Power qualifies stiff arm/shoulder. Other native charge consumers keep their level decision. QB no-arm gate preserved. Gameplay UNWITNESSED.")
        lines = ['title_name = "All-Pro Football 2K8"', f'title_id = "{TITLE_ID}"',
                 f'hash = "{self.profile.module_hash}"', '', '[[patch]]', f'name = "{NAME}"',
                 f'desc = "{description}"',
                 'author = "2K Football Mod Tools"', f'is_enabled = {str(self.enabled).lower()}']
        for a, w in self.words:
            lines += ['', '[[patch.be32]]', f'address = 0x{a:08X}', f'value = 0x{w:08X}']
        return '\n'.join(lines) + '\n'


def parse_payload(payload):
    try:
        parsed = tomllib.loads(payload.decode("utf-8"))
        profile = next(p for p in PROFILES if p.module_hash == parsed["hash"])
        row, = parsed["patch"]
        for revision in (CURRENT_REVISION, 3, 2, 1):
            doc = PatchDocument(profile, row["is_enabled"], revision)
            if parsed == tomllib.loads(doc.as_toml()):
                return doc
        raise ValueError("Metadata or instructions differ from the canonical patch")
    except (UnicodeError, ValueError, TypeError, KeyError, StopIteration) as exc:
        raise ValidationError(f"Choose a canonical Studio charge-abilities patch: {exc}") from exc


def canonical_payload(payload):
    doc = parse_payload(payload)
    return doc.profile, doc.enabled


def _verify_latch_padding(image):
    pe = struct.unpack_from('<I', image, 0x3C)[0]
    count = struct.unpack_from('<H', image, pe + 6)[0]
    optional_size = struct.unpack_from('<H', image, pe + 20)[0]
    for i in range(count):
        at = pe + 24 + optional_size + 40 * i
        if image[at:at + 8].rstrip(b'\0') == b'.XBMOVIE':
            size, rva, raw_size = struct.unpack_from('<3I', image, at + 8)
            end = IMAGE_BASE + rva + max(size, raw_size)
            flags = struct.unpack_from('<I', image, at + 36)[0]
            if not flags & 0x80000000 or not end <= LATCH_START < LATCH_LIMIT <= (end + 65535) & ~65535:
                raise ValidationError("Charge latch is not in writable mapped XBMOVIE padding")
            if any(image[LATCH_START - IMAGE_BASE:LATCH_LIMIT - IMAGE_BASE]):
                raise ValidationError("Charge visual latch reservation is occupied")
            return
    raise ValidationError("Charge image has no writable XBMOVIE padding for the visual latch")


def audit_latch_reservations(image):
    """Read-only audit of pinned code/RW padding and direct executable references.

    Numeric collisions in non-code are disclosed separately. This does not
    prove the absence of arbitrary computed references or thread scheduling.
    """
    profile = check_image(image)
    _verify_latch_padding(image)
    pe = struct.unpack_from('<I', image, 0x3C)[0]
    count = struct.unpack_from('<H', image, pe + 6)[0]
    optional_size = struct.unpack_from('<H', image, pe + 20)[0]
    sections = []
    for i in range(count):
        at = pe + 24 + optional_size + 40 * i
        name = image[at:at + 8].rstrip(b'\0').decode('ascii')
        size, rva, raw_size = struct.unpack_from('<3I', image, at + 8)
        sections.append((name, IMAGE_BASE + rva, max(size, raw_size), struct.unpack_from('<I', image, at + 36)[0]))
    ranges = ((CAVE, CAVE_LIMIT), (LATCH_START, LATCH_LIMIT))
    text = next(row for row in sections if row[0] == '.text')
    text_end = text[1] + text[2]
    if not text[3] & 0x20000000 or not text_end <= CAVE < CAVE_LIMIT <= (text_end + 65535) & ~65535:
        raise ValidationError("Charge code is not in executable mapped text padding")
    for name, start, size, _ in sections:
        for lo, hi in ranges:
            if lo < start + size and start < hi:
                raise ValidationError(f"Charge reservation overlaps declared {name} section contents")
    if any(image[CAVE - IMAGE_BASE:CAVE_LIMIT - IMAGE_BASE]):
        raise ValidationError("Charge code reservation is occupied")
    direct, numeric = [], []
    for index, (word,) in enumerate(struct.iter_unpack('>I', image)):
        pc = IMAGE_BASE + index * 4
        if any(lo <= word < hi for lo, hi in ranges):
            numeric.append((pc, word))
            if text[1] <= pc < text_end:
                direct.append((pc, word, 'executable literal'))
        if not text[1] <= pc < text_end:
            continue
        op = word >> 26
        if op in (16, 18) and not word & 2:
            width = 26 if op == 18 else 16
            delta = word & ((1 << width) - 4)
            if delta & (1 << (width - 1)):
                delta -= 1 << width
            target = pc + delta
            if any(lo <= target < hi for lo, hi in ranges):
                direct.append((pc, target, 'relative branch'))
        if op == 15 and word >> 16 & 31 == 0:
            register = word >> 21 & 31
            high = (word & 0xFFFF) << 16
            for following in range(1, 5):
                off = index * 4 + following * 4
                if IMAGE_BASE + off >= text_end:
                    break
                tail = struct.unpack_from('>I', image, off)[0]
                tail_op, rt, ra = tail >> 26, tail >> 21 & 31, tail >> 16 & 31
                target = None
                if tail_op == 14 and rt == ra == register:
                    low = tail & 0xFFFF
                    target = (high + (low - 65536 if low & 0x8000 else low)) & 0xFFFFFFFF
                elif tail_op == 24 and rt == ra == register:
                    target = high | tail & 0xFFFF
                if target is not None and any(lo <= target < hi for lo, hi in ranges):
                    direct.append((pc, target, 'nearby address construction'))
    if direct:
        raise ValidationError(f"Charge reservations have executable direct references: {direct[:8]}")
    return {"profile": profile.name, "image_sha256": profile.sha256,
            "code_range": [CAVE, CAVE_LIMIT], "writable_range": [LATCH_START, LATCH_LIMIT],
            "writable_section": ".XBMOVIE", "declared_section_overlap": False,
            "direct_executable_references": direct, "numeric_collisions": numeric,
            "computed_references_proved_absent": False, "thread_scheduling_witnessed": False}


def verify_image(image, document):
    if check_image(image) != document.profile:
        raise ValidationError("Charge document and executable profiles differ")
    if len(image) != IMAGE_SIZE or any(image[CAVE - IMAGE_BASE:document.reservation_end - IMAGE_BASE]):
        raise ValidationError("Charge code reservation is occupied or image is truncated")
    if document.revision >= 4:
        _verify_latch_padding(image)
    for site, expected in ((HOOK, RETAIL_CAP), (QB_GATE, RETAIL_QB_GATE)):
        off = address(site, document.profile) - IMAGE_BASE
        if image[off:off + len(expected)] != expected:
            raise ValidationError(f"Charge instructions differ at {off + IMAGE_BASE:08X}")
    for site, expected in document.original_words:
        if image[site - IMAGE_BASE:site - IMAGE_BASE + 4] != expected.to_bytes(4, "big"):
            raise ValidationError(f"Charge instructions differ at {site:08X}")
    return document.receipt


def apply_image(image, document):
    """Apply to a decoded image in memory, after all preconditions pass."""
    verify_image(image, document)
    result = bytearray(image)
    if document.enabled:
        for a, w in document.words:
            struct.pack_into(">I", result, a - IMAGE_BASE, w)
    return bytes(result)


def revert_image(image, document):
    """Refuse partial/foreign patches and restore the exact pinned input."""
    if not document.enabled:
        verify_image(image, document)
        return bytes(image)
    result = bytearray(image)
    for a, w in document.words:
        off = a - IMAGE_BASE
        if result[off:off + 4] != w.to_bytes(4, "big"):
            raise ValidationError(f"Charge patch differs at {a:08X}; cannot revert")
    for a, _ in document.words:
        if CAVE <= a < document.reservation_end:
            struct.pack_into(">I", result, a - IMAGE_BASE, 0)
    for a, word in document.original_words:
        struct.pack_into(">I", result, a - IMAGE_BASE, word)
    verify_image(result, document)
    return bytes(result)


def write_patch(document, output):
    output = Path(output)
    receipt_path = output.with_suffix(output.suffix + ".receipt.json")
    if output.is_symlink() or receipt_path.is_symlink():
        raise ValidationError("Choose a regular patch output file")
    receipt = export_patch(document, output, {"input_paths": []})
    if parse_payload(output.read_bytes()) != document:
        raise ValidationError("Charge patch readback differs")
    saved = {k: v for k, v in receipt.items() if k != "output_path"}
    saved["output_file"] = output.name
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                     dir=output.parent, prefix=".apf-charge-", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(saved, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        if json.loads(temporary.read_text(encoding="utf-8")) != saved:
            raise ValidationError("Charge receipt readback differs")
        os.replace(temporary, receipt_path)
    finally:
        temporary.unlink(missing_ok=True)
    return receipt


def export_build(directory):
    """Called only by an opted-in APF build; emit both hash-keyed profiles."""
    receipts = []
    for profile in PROFILES:
        doc = PatchDocument(profile, True)
        target = Path(directory) / f"54540807-charge-abilities-{profile.name}.patch.toml"
        write_patch(doc, target)
        receipts.append({**doc.receipt, "file": target.name,
                         "patch_sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
    return {"patches": receipts, "runtime_status": "UNWITNESSED",
            "next_step": "Tools > Charged abilities: select the executable profile, enable and install, then restart Xenia. Uncheck the Build option and remove the installed patch to revert."}


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=[p.name for p in PROFILES], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--enable", action="store_true", help="Explicit opt-in; default is disabled")
    args = parser.parse_args(argv)
    doc = PatchDocument(next(p for p in PROFILES if p.name == args.profile), args.enable)
    print(json.dumps(write_patch(doc, args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
CURRENT_REVISION = 3
CAVE = 0x84D0D100
LEGACY_CAVE_LIMIT = 0x84D0D180
CAVE_LIMIT = 0x84D0D320
FEEDBACK_CAVE = CAVE + 0x50
MOVE_CAVE = LEGACY_CAVE_LIMIT
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


def feedback_trampoline(profile):
    """Snapshot the consumed state using only dead r11, CR6 and output f30.

    r10 is the player state; f28=0, f18=1. State 4 is a consumed level 2,
    state 1 a consumed level 1. The caller already selected 0 <= timer < 10.
    The timer channel and medal bits remain untouched.
    """
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
                or type(self.revision) is not int or self.revision not in (1, 2, CURRENT_REVISION)):
            raise ValidationError("Choose a supported image and a boolean enable flag")

    @property
    def reservation_end(self):
        return CAVE_LIMIT if self.revision >= 3 else LEGACY_CAVE_LIMIT

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
        return words

    @property
    def words(self):
        code = trampoline(self.profile)
        words = ((address(HOOK, self.profile), _branch(address(HOOK, self.profile), CAVE)),) + tuple(
            (CAVE + i, int.from_bytes(code[i:i + 4], "big")) for i in range(0, len(code), 4)
        )
        if self.revision == 1:
            return words
        feedback = feedback_trampoline(self.profile)
        if FEEDBACK_CAVE + len(feedback) > CAVE_LIMIT:
            raise ValidationError("Charge feedback exceeds its reserved code space")
        hook = feedback_address(FEEDBACK_HOOK, self.profile)
        words += ((hook, _branch(hook, FEEDBACK_CAVE)),) + tuple(
            (feedback_address(a, self.profile), new) for a, _, new in FEEDBACK_EDITS
        ) + tuple((FEEDBACK_CAVE + i, int.from_bytes(feedback[i:i + 4], "big"))
                  for i in range(0, len(feedback), 4))
        if self.revision >= 3:
            for check, cave, code in move_trampolines(self.profile):
                hook = move_address(check, self.profile)
                words += ((hook, _branch(hook, cave)),) + tuple(
                    (cave + i, int.from_bytes(code[i:i + 4], "big")) for i in range(0, len(code), 4))
        return words

    @property
    def receipt(self):
        return {"schema": f"apf2k8_charge_abilities/v{self.revision}", "classification": CLASSIFICATION,
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
                          + "; CPU bypass unchanged; gameplay UNWITNESSED.")}

    def as_toml(self):
        description = ("Level 2 requires a charged ability, at any tier. QB no-arm gate preserved. Gameplay UNWITNESSED."
                       if self.revision == 1 else
                       "Level 2 and its ring follow charge abilities at any tier; discharge follows consumed level. QB no-arm gate preserved. Gameplay UNWITNESSED."
                       if self.revision == 2 else
                       "Revision 3: Finesse or Finesse and Power qualify spin/juke; Power or Finesse and Power qualify stiff arm/shoulder charge. Charge and feedback follow abilities at any tier. QB no-arm gate preserved. Gameplay UNWITNESSED.")
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
        for revision in (CURRENT_REVISION, 2, 1):
            doc = PatchDocument(profile, row["is_enabled"], revision)
            if parsed == tomllib.loads(doc.as_toml()):
                return doc
        raise ValueError("Metadata or instructions differ from the canonical patch")
    except (UnicodeError, ValueError, TypeError, KeyError, StopIteration) as exc:
        raise ValidationError(f"Choose a canonical Studio charge-abilities patch: {exc}") from exc


def canonical_payload(payload):
    doc = parse_payload(payload)
    return doc.profile, doc.enabled


def verify_image(image, document):
    if check_image(image) != document.profile:
        raise ValidationError("Charge document and executable profiles differ")
    if len(image) != IMAGE_SIZE or any(image[CAVE - IMAGE_BASE:document.reservation_end - IMAGE_BASE]):
        raise ValidationError("Charge code reservation is occupied or image is truncated")
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

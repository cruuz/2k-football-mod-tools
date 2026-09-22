"""Opt-in ability-based charge cap for the pinned APF BASE and TU 1.1 images.

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
CAVE = 0x84D0D100
CAVE_LIMIT = 0x84D0D180
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


def address(base, profile):
    if profile not in PROFILES:
        raise ValidationError("Choose BASE or Title Update 1.1")
    return base + (0xE38 if profile == PROFILES[1] else 0)


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

    def __post_init__(self):
        if self.profile not in PROFILES or type(self.enabled) is not bool:
            raise ValidationError("Choose a supported image and a boolean enable flag")

    @property
    def words(self):
        code = trampoline(self.profile)
        return ((address(HOOK, self.profile), _branch(address(HOOK, self.profile), CAVE)),) + tuple(
            (CAVE + i, int.from_bytes(code[i:i + 4], "big")) for i in range(0, len(code), 4)
        )

    @property
    def receipt(self):
        return {"schema": "apf2k8_charge_abilities/v1", "classification": CLASSIFICATION,
                "profile": self.profile.name, "image_sha256": self.profile.sha256,
                "module_hash": self.profile.module_hash, "enabled": self.enabled,
                "routine": address(ROUTINE, self.profile), "hook": address(HOOK, self.profile),
                "gold_comparison": address(HOOK + 12, self.profile),
                "resume": address(RESUME, self.profile), "qb_gate": address(QB_GATE, self.profile),
                "qb_gate_preserved": True, "passing_mode_cap_replaced": True,
                "trampoline": CAVE, "reservation_end": CAVE_LIMIT,
                "section": ".text", "reservation_section": "XEX code page 0x84D00000 (0x11), after .text virtual end",
                "retail_cap_bytes": RETAIL_CAP.hex(), "retail_qb_gate_bytes": RETAIL_QB_GATE.hex(),
                "word_masks": [list(row) for row in WORD_MASKS],
                "charged_abilities": [name for name, _, _ in CHARGED_ABILITIES],
                "writes": [{"address": a, "value": w} for a, w in self.words],
                "scope": "Input charge state machine; CPU bypass unchanged; gameplay UNWITNESSED."}

    def as_toml(self):
        lines = ['title_name = "All-Pro Football 2K8"', f'title_id = "{TITLE_ID}"',
                 f'hash = "{self.profile.module_hash}"', '', '[[patch]]', f'name = "{NAME}"',
                 'desc = "Level 2 requires a charged ability, at any tier. QB no-arm gate preserved. Gameplay UNWITNESSED."',
                 'author = "2K Football Mod Tools"', f'is_enabled = {str(self.enabled).lower()}']
        for a, w in self.words:
            lines += ['', '[[patch.be32]]', f'address = 0x{a:08X}', f'value = 0x{w:08X}']
        return '\n'.join(lines) + '\n'


def parse_payload(payload):
    try:
        parsed = tomllib.loads(payload.decode("utf-8"))
        profile = next(p for p in PROFILES if p.module_hash == parsed["hash"])
        row, = parsed["patch"]
        doc = PatchDocument(profile, row["is_enabled"])
        if parsed != tomllib.loads(doc.as_toml()):
            raise ValueError("Metadata or instructions differ from the canonical patch")
        return doc
    except (UnicodeError, ValueError, TypeError, KeyError, StopIteration) as exc:
        raise ValidationError(f"Choose a canonical Studio charge-abilities patch: {exc}") from exc


def canonical_payload(payload):
    doc = parse_payload(payload)
    return doc.profile, doc.enabled


def verify_image(image, document):
    if check_image(image) != document.profile:
        raise ValidationError("Charge document and executable profiles differ")
    if len(image) != IMAGE_SIZE or any(image[CAVE - IMAGE_BASE:CAVE_LIMIT - IMAGE_BASE]):
        raise ValidationError("Charge code reservation is occupied or image is truncated")
    for site, expected in ((HOOK, RETAIL_CAP), (QB_GATE, RETAIL_QB_GATE)):
        off = address(site, document.profile) - IMAGE_BASE
        if image[off:off + len(expected)] != expected:
            raise ValidationError(f"Charge instructions differ at {off + IMAGE_BASE:08X}")
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
    result[CAVE - IMAGE_BASE:CAVE - IMAGE_BASE + len(trampoline(document.profile))] = bytes(len(trampoline(document.profile)))
    off = address(HOOK, document.profile) - IMAGE_BASE
    result[off:off + 4] = RETAIL_CAP[:4]
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

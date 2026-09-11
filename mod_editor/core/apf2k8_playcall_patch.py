"""Pinned, offline-verified APF pass-fetch TE bias experiment.

This does NOT claim to fix third-and-long. Live down/distance is not proved
at this hook. It applies unconditionally to offensive subtype 2/3/4 fetches
(short/medium/long pass classifiers). The usual CPU weighted picker uses a
different function; its untyped emergency fetch (-1) is unchanged.

The buffer contains MASTER play pointers, not SPLB entry pointers. Membership
is resolved in the current book's contiguous record prefix. A preferred play
must occur in a record whose primary category is advertised, is in word B,
and has a TE role in MASTER. This is eligibility, not a guarantee about the
later formation resolver or Subs. No game files are modified by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import struct
import tempfile

from .errors import ValidationError

IMAGE_BASE = 0x82000000
IMAGE_SIZE = 54_001_664
TITLE_ID = "54540807"
CAVE_START = 0x84D0E000
CAVE_LIMIT = 0x84D0F000
FRAME_SIZE = 0x200
PASS_SUBTYPES = (2, 3, 4)


@dataclass(frozen=True)
class ImageProfile:
    name: str
    sha256: str
    module_hash: str
    hook: int
    fetch_sha256: str


# Hashes are of flat decompressed images BEFORE Xenia resolves imports. The
# module hashes include its 334 syscall thunks (see tools/apf_playcall_audit.py).
PROFILES = (
    ImageProfile("base", "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf",
                 "5447E5428AA2D52A", 0x84869B20, "63cb56f27978d22cf5193451f1da41368f1c16db3cfc69738e381c94d4cd51b9"),
    ImageProfile("tu_1_1", "65f522ce1cdda42cf19c112e9ec07302e89c81e4148c9f22e6db5e03952f9457",
                 "CEA825F7C2012F5A", 0x8486A820, "d0994a6daf4d6e43c2210940e4cd67a22886d4261688a9d19b372e426e866561"),
)


def _d(op: int, rt: int, ra: int, imm: int) -> int:
    return op << 26 | rt << 21 | ra << 16 | (imm & 0xFFFF)


def _x(rt: int, ra: int, rb: int, xo: int) -> int:
    return 31 << 26 | rt << 21 | ra << 16 | rb << 11 | xo << 1


def _rl(rs: int, ra: int, shift: int, mb: int, me: int) -> int:
    return 21 << 26 | rs << 21 | ra << 16 | shift << 11 | mb << 6 | me << 1


def _branch(source: int, target: int) -> int:
    delta = target - source
    if delta & 3 or not -(1 << 25) <= delta < (1 << 25):
        raise ValidationError("PPC branch target is unaligned or out of range")
    return 0x48000000 | (delta & 0x03FFFFFC)


class _Assembler:
    def __init__(self, start: int):
        self.start = start
        self.words: list[int] = []
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str, str]] = []

    def emit(self, word: int) -> None:
        self.words.append(word)

    def label(self, name: str) -> None:
        if name in self.labels:
            raise ValidationError("Duplicate PPC label")
        self.labels[name] = self.start + len(self.words) * 4

    def jump(self, label: str, condition: str = "always") -> None:
        self.fixups.append((len(self.words), label, condition))
        self.emit(0)

    def finish(self) -> bytes:
        conditions = {"eq": (12, 26), "ne": (4, 26), "lt": (12, 24),
                      "ge": (4, 24), "gt": (12, 25)}
        for index, label, condition in self.fixups:
            source = self.start + index * 4
            target = self.labels[label]
            if condition == "always":
                self.words[index] = _branch(source, target)
            else:
                delta = target - source
                if delta & 3 or not -32768 <= delta <= 32764:
                    raise ValidationError("PPC conditional branch is out of range")
                bo, bi = conditions[condition]
                self.words[index] = 16 << 26 | bo << 21 | bi << 16 | (delta & 0xFFFC)
        return b"".join(struct.pack(">I", word) for word in self.words)


def assemble_cave(hook: int) -> bytes:
    """Leaf cave: preserve 64-bit scratch registers, CR, SP; never touch LR/CTR.

    New frame: saved GPRs +0x08..0xAF, CR +0xC0, preferred pointers
    +0x100..0x19F. Original candidate array is new SP+0x250. Commit only
    after the scan, so zero matches and malformed inputs preserve the buffer.
    """
    a = _Assembler(CAVE_START)
    e = a.emit
    addi = lambda rt, ra, v: e(_d(14, rt, ra, v))
    li = lambda rt, v: addi(rt, 0, v)
    lwz = lambda rt, ra, v: e(_d(32, rt, ra, v))
    stw = lambda rt, ra, v: e(_d(36, rt, ra, v))
    cmpi = lambda rt, v: e(_d(10, 24, rt, v))  # cmplwi cr6
    cmp = lambda ra, rb: e(_x(24, ra, rb, 32))  # cmplw cr6
    mr = lambda ra, rs: e(_x(rs, ra, rs, 444))
    # stdu r1,-0x200(r1); save before mfcr, preserving original r0 as well.
    e(_d(62, 1, 1, -FRAME_SIZE) | 1)
    saved = (0, *range(3, 13), *range(14, 24))
    for i, reg in enumerate(saved):
        e(_d(62, reg, 1, 8 + i * 8))
    e(_x(0, 0, 0, 19))  # mfcr r0
    stw(0, 1, 0xC0)
    cmpi(24, 0); a.jump("restore", "ne")
    cmpi(27, 2); a.jump("restore", "lt")
    cmpi(27, 4); a.jump("restore", "gt")
    cmpi(28, 1); a.jump("restore", "lt")
    cmpi(28, 40); a.jump("restore", "gt")
    cmpi(29, 0); a.jump("restore", "eq")
    lwz(15, 29, 0x7E0C)
    cmpi(15, 0); a.jump("restore", "eq")
    # Reject foreign MASTER layouts before indexing any category/formation.
    lwz(3, 15, 0x3C); cmpi(3, 28); a.jump("restore", "ne")
    lwz(3, 15, 0x34); cmpi(3, 163); a.jump("restore", "ne")
    lwz(3, 15, 0x38); cmpi(3, 586); a.jump("restore", "ne")
    addi(14, 1, FRAME_SIZE + 0x50)
    e(_d(15, 16, 15, 1)); addi(16, 16, -0x7F3C)  # MASTER+0x80C4
    lwz(17, 29, 0x7E04)
    li(18, 0); li(19, 0)  # candidate ordinal, preferred count
    a.label("candidate")
    e(_rl(18, 3, 2, 0, 29)); e(_x(20, 14, 3, 23))  # lwzx
    cmp(20, 16); a.jump("restore", "lt")
    e(_x(3, 16, 20, 40))  # delta = candidate - play base
    li(4, 100); e(_x(21, 3, 4, 459))  # divwu id,delta,100
    cmpi(21, 586); a.jump("restore", "ge")
    e(_d(7, 4, 21, 100)); cmp(3, 4); a.jump("restore", "ne")
    lwz(3, 20, 4); e(_rl(3, 3, 4, 28, 31)); cmpi(3, 0); a.jump("restore", "ne")
    lwz(3, 20, 8); e(_d(28, 3, 3, 0xA)); cmpi(3, 2); a.jump("restore", "ne")
    addi(22, 29, 0x70); li(23, 0)
    a.label("record")
    e(_d(40, 3, 22, 0)); e(_rl(3, 3, 0, 22, 31)); cmpi(3, 0x3FF)
    a.jump("next_candidate", "eq")  # runtime iteration ends at first empty
    lwz(3, 22, 0xA8)
    e(_rl(3, 4, 8, 24, 31)); cmpi(4, 163); a.jump("restore", "ge")
    cmpi(30, 0); a.jump("category", "eq")
    e(_d(7, 4, 4, 184)); e(_x(4, 4, 15, 266)); addi(4, 4, 0x244)
    cmp(4, 30); a.jump("next_record", "ne")
    a.label("category")
    e(_rl(3, 4, 15, 25, 31))  # (word A >> 17)&127
    cmpi(4, 28); a.jump("restore", "ge")
    li(5, 1); e(_x(5, 5, 4, 24))  # slw
    e(_x(5, 6, 17, 28)); cmpi(6, 0); a.jump("next_record", "eq")
    lwz(6, 22, 0xAC); e(_x(5, 6, 6, 28)); cmpi(6, 0); a.jump("next_record", "eq")
    e(_rl(4, 4, 4, 0, 27)); e(_x(4, 4, 15, 266)); addi(4, 4, 0x49)
    li(5, 11)
    a.label("role")
    e(_d(34, 6, 4, 0)); e(_rl(6, 6, 0, 27, 31)); cmpi(6, 8)
    a.jump("entries", "eq")
    addi(4, 4, 1); addi(5, 5, -1); cmpi(5, 0); a.jump("role", "ne")
    a.jump("next_record")
    a.label("entries")
    mr(4, 22); li(5, 84)
    a.label("entry")
    e(_d(40, 6, 4, 0)); e(_rl(6, 6, 0, 22, 31)); cmpi(6, 0x3FF)
    a.jump("next_record", "eq")
    cmp(6, 21); a.jump("preferred", "eq")
    addi(4, 4, 2); addi(5, 5, -1); cmpi(5, 0); a.jump("entry", "ne")
    a.label("next_record")
    addi(22, 22, 176); addi(23, 23, 1); cmpi(23, 176); a.jump("record", "lt")
    a.jump("next_candidate")
    a.label("preferred")
    e(_rl(19, 3, 2, 0, 29)); addi(4, 1, 0x100); e(_x(20, 4, 3, 151))
    addi(19, 19, 1)
    a.label("next_candidate")
    addi(18, 18, 1); cmp(18, 28); a.jump("candidate", "lt")
    cmpi(19, 0); a.jump("restore", "eq")
    li(3, 0); addi(4, 1, 0x100); mr(5, 14)
    a.label("copy")
    lwz(6, 4, 0); stw(6, 5, 0); addi(4, 4, 4); addi(5, 5, 4)
    addi(3, 3, 1); cmp(3, 19); a.jump("copy", "lt")
    mr(28, 19)
    a.label("restore")
    lwz(0, 1, 0xC0); e(0x7C0FF120)  # mtcrf 0xFF,r0
    for i, reg in enumerate(saved):
        e(_d(58, reg, 1, 8 + i * 8))
    e(_d(58, 1, 1, 0))  # original 64-bit SP/backchain
    e(0x3D608506)  # displaced lis r11,0x8506, same on BASE and TU
    e(_branch(CAVE_START + len(a.words) * 4, hook + 4))
    result = a.finish()
    if CAVE_START + len(result) > CAVE_LIMIT:
        raise ValidationError("TE cave exceeds its reserved zero padding")
    return result


def verify_cave(cave: bytes, hook: int) -> dict:
    """Independent decode, exhaustive direct branch checks, canonical identity."""
    try:
        from capstone import Cs, CS_ARCH_PPC, CS_MODE_64, CS_MODE_BIG_ENDIAN
    except ImportError as exc:
        raise ValidationError("Capstone is required to verify the PPC patch before export") from exc
    md = Cs(CS_ARCH_PPC, CS_MODE_64 | CS_MODE_BIG_ENDIAN)
    instructions = list(md.disasm(cave, CAVE_START))
    if len(instructions) * 4 != len(cave) or not cave:
        raise ValidationError("Cave contains an undecodable PPC instruction")
    destinations = []
    end = CAVE_START + len(cave)
    for insn in instructions:
        word = int.from_bytes(insn.bytes, "big")
        op = word >> 26
        if op in (16, 18):
            if word & 3:
                raise ValidationError("Cave must not link branches or use absolute branch operands")
            width = 26 if op == 18 else 16
            delta = word & ((1 << width) - 4)
            if delta & (1 << (width - 1)):
                delta -= 1 << width
            target = insn.address + delta
            if not (CAVE_START <= target < end and target % 4 == 0) and not (
                    insn.address == end - 4 and target == hook + 4 and op == 18):
                raise ValidationError(f"Cave branch leaves its allowed targets at {insn.address:#x}")
            destinations.append(target)
        if insn.mnemonic in ("bctr", "bctrl", "blr", "blrl", "mtctr", "mtlr"):
            raise ValidationError("Unexpected indirect control flow in leaf cave")
    if cave != assemble_cave(hook):
        raise ValidationError("Cave differs from the reviewed assembled implementation")
    return {"capstone_redecoded": True, "instruction_count": len(instructions),
            "branch_count": len(destinations), "all_branch_targets_checked": True,
            "cave_sha256": hashlib.sha256(cave).hexdigest()}


@dataclass(frozen=True)
class PlaycallPatch:
    profile: ImageProfile
    cave: bytes
    receipt: dict

    @property
    def words(self) -> tuple[tuple[int, int], ...]:
        return ((self.profile.hook, _branch(self.profile.hook, CAVE_START)),) + tuple(
            (CAVE_START + offset, int.from_bytes(self.cave[offset:offset + 4], "big"))
            for offset in range(0, len(self.cave), 4))

    def as_toml(self) -> str:
        # Do not permit a manually constructed/mutated payload to bypass verification.
        verify_cave(self.cave, self.profile.hook)
        if self.profile not in PROFILES:
            raise ValidationError("Unsupported image profile")
        lines = [f'title_name = "All-Pro Football 2K8"', f'title_id = "{TITLE_ID}"',
                 f'hash = "{self.profile.module_hash}"', "", "[[patch]]",
                 '    name = "TE bias for pass fetches (unwitnessed)"',
                 '    desc = "Pass subtypes 2/3/4 at any down; TE-compatible record membership; zero-match fallback. CPU weighted picker and Subs remain unchanged."',
                 '    author = "2K Football Mod Tools"', '    is_enabled = true',
                 f'    # Flat image SHA-256: {self.profile.sha256}',
                 '    # Enable only one patch owning 0x84D0E000..0x84D0EFFF.']
        for address, value in self.words:
            lines.extend(("", "    [[patch.be32]]", f"        address = 0x{address:08X}",
                          f"        value = 0x{value:08X}"))
        return "\n".join(lines) + "\n"


def check_image(image: bytes) -> ImageProfile:
    """One identity gate for game folders, decoded executables and expert PEs."""
    digest = hashlib.sha256(image).hexdigest()
    profile = next((p for p in PROFILES if p.sha256 == digest), None)
    if profile is None or len(image) != IMAGE_SIZE:
        accepted = "; ".join(f"{'retail BASE' if p.name == 'base' else 'Title Update 1.1'} {p.sha256}"
                             for p in PROFILES)
        raise ValidationError(
            f"Executable SHA-256 mismatch. Saw {digest} ({len(image)} bytes). "
            f"Accepts {accepted} ({IMAGE_SIZE} bytes each). "
            "Choose the original Xbox 360 game folder, or a supported flat image under the expert option.")
    return profile


def compile_patch(image: bytes) -> PlaycallPatch:
    profile = check_image(image)
    digest = profile.sha256
    hook_offset = profile.hook - IMAGE_BASE
    fetch = image[hook_offset - 0x148:hook_offset + 0x30]
    if hashlib.sha256(fetch).hexdigest() != profile.fetch_sha256:
        raise ValidationError("Pinned fetch function differs")
    if image[hook_offset:hook_offset + 4] != struct.pack(">I", 0x3D608506):
        raise ValidationError("Hook instruction differs")
    cave = assemble_cave(profile.hook)
    original = image[CAVE_START - IMAGE_BASE:CAVE_LIMIT - IMAGE_BASE]
    if len(original) != CAVE_LIMIT - CAVE_START or any(original):
        raise ValidationError("TE cave reservation is not zero-filled")
    verification = verify_cave(cave, profile.hook)
    hook_word = _branch(profile.hook, CAVE_START)
    if profile.hook + ((hook_word & 0x3FFFFFC) ^ 0x2000000) - 0x2000000 != CAVE_START:
        raise ValidationError("Hook branch failed independent target check")
    return PlaycallPatch(profile, cave, {
        "schema": "apf2k8_pass_fetch_te_bias/v1", "status": "unwitnessed",
        "image": profile.name, "image_sha256": digest, "module_hash": profile.module_hash,
        "hook": profile.hook, "hook_word": f"{hook_word:08X}", "cave_start": CAVE_START,
        "cave_size": len(cave), "cave_original_zero_sha256": hashlib.sha256(original).hexdigest(),
        "scope": "Unconditional offensive pass subtypes 2/3/4, every down; weighted picker untouched",
        "personnel_boundary": "TE-compatible primary record; later formation selection and substitutions unwitnessed",
        "down_distance_status": "Live down/distance not sufficiently proved for this hook",
        "verification": verification,
    })


def write_patch(image_path: Path, output_path: Path, *, title_update=None,
                content_roots=(), progress=None) -> dict:
    """Derive a player's image, then export verified TOML beside their build."""
    from .apf2k8_xex import derive_image

    image, source_receipt = derive_image(image_path, title_update=title_update,
                                        content_roots=content_roots, progress=progress)
    return export_patch(compile_patch(image), output_path, source_receipt)


def export_patch(patch: PlaycallPatch, output_path: Path, source_receipt: dict) -> dict:
    """Idempotent, atomic export; reparse TOML and compare every patch word."""
    import tomllib
    output_path = Path(output_path)
    if not output_path.name.casefold().endswith(".patch.toml"):
        raise ValidationError("Export to a separate .patch.toml file next to your build")
    for source in source_receipt["input_paths"]:
        path = Path(source)
        if (path.resolve() == output_path.resolve()
                or (output_path.exists() and path.samefile(output_path))):
            raise ValidationError("Export path must differ from the executable and Title Update inputs")
    payload = patch.as_toml().encode("utf-8")
    parsed = tomllib.loads(payload.decode("utf-8"))
    words = tuple((w["address"], w["value"]) for w in parsed["patch"][0]["be32"])
    if words != patch.words or parsed["hash"] != patch.profile.module_hash:
        raise ValidationError("Exported TOML did not reparse to the verified patch")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not output_path.exists() or output_path.read_bytes() != payload:
        fd, temporary = tempfile.mkstemp(prefix=".apf-playcall-", suffix=".tmp", dir=output_path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload); stream.flush(); os.fsync(stream.fileno())
            if Path(temporary).read_bytes() != payload:
                raise ValidationError("Patch file readback mismatch")
            os.replace(temporary, output_path)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return {**patch.receipt, "source": source_receipt, "output_path": str(output_path.resolve()),
            "toml_reparsed": True, "output_sha256": hashlib.sha256(payload).hexdigest()}


def status() -> str:
    return "unwitnessed — TE bias for pass fetches at every down; BASE and TU 1.1 pinned, no game witness"


if __name__ == "__main__":
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(write_patch(args.image, args.output), indent=2))

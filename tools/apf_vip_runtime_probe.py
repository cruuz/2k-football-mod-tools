#!/usr/bin/env python3
"""Execute APF's native opponent-VIP attachment prefix in isolated memory.

This is an offline research probe, not a patch or a gameplay witness. It stops
before the mode-specific setup and playback routines. No save or game is written.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import struct

IMAGE_BASE = 0x82000000
BINDINGS = 0x84D4F0C0
PRIMARY_SIZE = 0x1410
PLAYBACK_BASE = 0x84EB3F70
PLAYBACK_STRIDE = 0x3BD8
STACK_BASE, STACK, RETURN = 0x100000, 0x10F000, 0x100000


@dataclass(frozen=True)
class Profile:
    sha256: str
    start: int
    stop: int
    save_thunk: int
    bank: int
    side_zero: int
    attachment: int


PROFILES = {
    "base": Profile(
        "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf",
        0x8492F8C0, 0x8492F97C, 0x84BD6DEC, 0x85065D90,
        0x850F1218, 0x8519A820),
    "tu_1_1": Profile(
        "65f522ce1cdda42cf19c112e9ec07302e89c81e4148c9f22e6db5e03952f9457",
        0x84930788, 0x84930844, 0x84BD7DBC, 0x85065DA0,
        0x850F1248, 0x8519A850),
}


def read_image(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        if not 0 < os.fstat(stream.fileno()).st_size <= 128 * 1024 * 1024:
            raise ValueError("Decoded image exceeds the probe bound")
        return stream.read(128 * 1024 * 1024 + 1)


def identify(data: bytes) -> tuple[str, Profile]:
    digest = hashlib.sha256(data).hexdigest()
    for name, profile in PROFILES.items():
        if digest == profile.sha256:
            return name, profile
    raise ValueError("Expected an exact pinned BASE or TU 1.1 decoded APF image")


def attach_prefix(data: bytes, *, opponent_slot: int | None,
                  side_zero_human: bool, side_one_human: bool) -> dict:
    """Run actual PPC through initial side pointers with synthetic session flags.

    The tag-0 binding identifies the selected opponent VIP. Tag 1 is used by
    the profile-viewing menu. These tags are not home/away team numbers.
    """
    name, profile = identify(data)
    if opponent_slot is not None and (type(opponent_slot) is not int or
                                     not 0 <= opponent_slot < 8):
        raise ValueError("Use an ordinary loaded VIP slot 0..7, or None")
    if type(side_zero_human) is not bool or type(side_one_human) is not bool:
        raise ValueError("Session human-side flags must be booleans")
    import unicorn as u
    from unicorn import ppc_const as r
    cpu = u.Uc(u.UC_ARCH_PPC, u.UC_MODE_32 | u.UC_MODE_BIG_ENDIAN)
    cpu.mem_map(IMAGE_BASE, (len(data) + 4095) & ~4095)
    cpu.mem_write(IMAGE_BASE, data)
    cpu.mem_map(STACK_BASE, 0x10000)
    vip = 0 if opponent_slot is None else profile.bank + opponent_slot * PRIMARY_SIZE
    # Tag 1 points at a different slot, proving it cannot supply this prefix.
    cpu.mem_write(BINDINGS, struct.pack(">4I", 0, vip, 1, profile.bank + 7 * PRIMARY_SIZE))
    cpu.mem_write(profile.side_zero + 0x38, struct.pack(">I", int(side_zero_human)))
    cpu.mem_write(profile.side_zero + 0x48 + 0x38, struct.pack(">I", int(side_one_human)))
    cpu.reg_write(r.UC_PPC_REG_1, STACK)
    cpu.reg_write(r.UC_PPC_REG_LR, RETURN)
    executed = []

    def adapt_save(machine, pc, _size, _user):
        executed.append(pc)
        if pc == profile.save_thunk:
            # Only the Xenon shared 64-bit ABI save thunk is adapted for PPC32.
            # All profile selection and address arithmetic execute natively.
            sp = machine.reg_read(r.UC_PPC_REG_1)
            for reg in range(29, 32):
                value = machine.reg_read(r.UC_PPC_REG_0 + reg)
                machine.mem_write(sp - 0x10 - (31 - reg) * 8, struct.pack(">Q", value))
            machine.mem_write(sp - 8, struct.pack(">I", machine.reg_read(r.UC_PPC_REG_12)))
            machine.reg_write(r.UC_PPC_REG_PC, machine.reg_read(r.UC_PPC_REG_LR))

    cpu.hook_add(u.UC_HOOK_CODE, adapt_save)
    cpu.emu_start(profile.start, profile.stop, count=4096)
    if cpu.reg_read(r.UC_PPC_REG_PC) != profile.stop:
        raise AssertionError("Native attachment prefix exceeded its instruction bound")
    pointers = struct.unpack(">4I", bytes(cpu.mem_read(profile.attachment, 16)))
    expected = [0, 0]
    if vip and side_zero_human != side_one_human:
        expected[int(side_zero_human)] = PLAYBACK_BASE + opponent_slot * PLAYBACK_STRIDE
    if list(pointers[:2]) != expected or pointers[2:] != pointers[:2]:
        raise AssertionError("Native VIP side attachment differs from the recorded path")
    return {
        "schema": "apf_vip_attachment_prefix/v1", "profile": name,
        "image_sha256": profile.sha256,
        "evidence": "offline native PPC prefix; gameplay UNWITNESSED",
        "opponent_slot": opponent_slot,
        "human_side_flags": [side_zero_human, side_one_human],
        "primary_pointer": vip, "side_playback_pointers": list(pointers[:2]),
        "saved_side_playback_pointers": list(pointers[2:]),
        "entry": profile.start, "stop_before_mode_setup": profile.stop,
        "instructions": len(executed),
        "abi_adapter": "shared GPR29..31 save thunk only; no selection callee replaced",
        "limits": ["synthetic session flags", "mode setup after stop not executed",
                   "no motion, playcalling, or season gameplay asserted"],
        "game_files_touched": [],
    }


def sweep(data: bytes) -> dict:
    name, profile = identify(data)
    rows = [attach_prefix(data, opponent_slot=slot, side_zero_human=left,
                          side_one_human=right)
            for slot in (None, 0, 3, 7)
            for left, right in ((False, False), (False, True), (True, False), (True, True))]
    return {"schema": "apf_vip_attachment_sweep/v1", "profile": name,
            "image_sha256": profile.sha256, "cases": rows,
            "game_files_touched": [], "gameplay_witnessed": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = sweep(read_image(args.image))
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(f"PASS {result['profile']}: {len(result['cases'])} native attachment prefixes; gameplay UNWITNESSED")


if __name__ == "__main__":
    main()

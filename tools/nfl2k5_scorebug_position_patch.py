#!/usr/bin/env python3
"""Move the NFL 2K5 field scorebug to a chosen screen position (local research tool).

`FUN_000FCE70` places the scorebug root node from code constants: mode 0 (in-game) and
mode 2 (slid low) add x = [0x4E6D58] (120, a shared constant), mode 1 adds x = [0x4F6968]
(564: the game's own top-RIGHT placement, chosen by `FUN_000FC9C0` whenever the offense
drives toward the bug's side of the screen), and every mode adds y = [0x4F0F1C] (65).
This patch repoints those four `fadd dword ptr [imm32]` operands (0x0FCFFC, 0x0FD07B,
0x0FD0EB for x; 0x0FD15E for y) at two private floats stored in the XBE boot-logo bitmap
region (0x10A40 x, 0x10A44 y; the catch-slider cave uses 0x10A10..0x10A3F).  The .text
thunk tables are live; never use them.
Geometry (measured): the frame's left edge sits at x-105 and it is ~166 units wide; its top
sits at about y-41 and the tall pre-snap state ("Ball on ...") is ~150 units high, on a 640
wide screen.  Centred bottom = --x 342 --y 340.  Retail = --x 120 --y 65.  xemu-only (RSA
signature stale).  Copy-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_bump_strength as bs  # noqa: E402
from mod_editor.core import nfl2k5_throw_tuning as tt  # noqa: E402

X_SLOT = 0x00010A40   # boot-logo bitmap region (see nfl2k5_catch_slider)
Y_SLOT = 0x00010A44
# x sites: mode 0 (in-game, +120), mode 1 (drive toward the bug's side, +564 = the game's own
# right-side placement, NOT a mirror), mode 2 (slid low, +120).  All three read the private X.
X_SITES = ((0x000FCFFC, 0x004E6D58), (0x000FD07B, 0x004F6968), (0x000FD0EB, 0x004E6D58))
Y_SITES = (0x000FD15E,)
RETAIL_Y = bytes.fromhex("d805") + struct.pack("<I", 0x004F0F1C)
RETAIL_SLOTS = bytes.fromhex("73f7d373e3f7430f")  # retail logo bytes at 0x10A40


def va_to_off(payload: bytes, va: int) -> int:
    hdr = struct.unpack_from("<I", payload, 0x108)[0]
    if 0x10000 <= va < 0x10000 + hdr:
        return va - 0x10000
    for section in bs._sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise SystemExit(f"VA {va:#x} not in any section")


def apply(payload: bytes, x: float, y: float) -> tuple[bytes, dict]:
    buf = bytearray(payload)
    edits = []

    def put(va, before, after, label):
        off = va_to_off(payload, va)
        got = payload[off: off + len(before)]
        if got != before:
            raise SystemExit(f"{label}: bytes at {va:#x} are {got.hex()}, expected {before.hex()}")
        buf[off: off + len(after)] = after
        edits.append({"label": label, "va": f"{va:#x}", "before": got.hex(), "after": after.hex()})

    put(X_SLOT, RETAIL_SLOTS, struct.pack("<ff", x, y), "private floats")
    for site, retail_const in X_SITES:
        retail = bytes.fromhex("d805") + struct.pack("<I", retail_const)
        put(site, retail, bytes.fromhex("d805") + struct.pack("<I", X_SLOT), f"x@{site:#x}")
    for site in Y_SITES:
        put(site, RETAIL_Y, bytes.fromhex("d805") + struct.pack("<I", Y_SLOT), f"y@{site:#x}")
    sections = bs._sections(payload)
    hdr = struct.unpack_from("<I", payload, 0x108)[0]
    touched = {bs._section_for_offset(sections, va_to_off(payload, int(e["va"], 16))).index
               for e in edits if va_to_off(payload, int(e["va"], 16)) >= hdr}
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d: d + 20] = bs.section_digest(bytes(buf), section)
    return bytes(buf), {"edits": edits, "x": x, "y": y}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source"); ap.add_argument("target")
    ap.add_argument("--x", type=float, required=True); ap.add_argument("--y", type=float, required=True)
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    src, dst = Path(a.source), Path(a.target)
    if dst.exists() and not a.overwrite:
        raise SystemExit(f"target exists: {dst}")
    if tt.is_disc_image(src):
        fd = os.open(src, os.O_RDONLY)
        try:
            size = os.fstat(fd).st_size; off, length = tt.image_xbe_extent(fd, size); payload = os.pread(fd, length, off)
        finally:
            os.close(fd)
        patched, receipt = apply(payload, a.x, a.y)
        shutil.copyfile(src, dst)
        fd = os.open(dst, os.O_RDWR)
        try:
            for i in range(0, len(patched), 1 << 20):
                if payload[i:i + (1 << 20)] != patched[i:i + (1 << 20)]:
                    os.pwrite(fd, patched[i:i + (1 << 20)], off + i)
            os.fsync(fd); check = os.pread(fd, length, off)
        finally:
            os.close(fd)
        assert check == patched
        receipt["container"] = "xiso"
    else:
        payload = src.read_bytes(); patched, receipt = apply(payload, a.x, a.y); dst.write_bytes(patched); receipt["container"] = "xbe"
    receipt["changed_bytes"] = sum(1 for p, q in zip(payload, patched) if p != q)
    receipt["target_xbe_sha256"] = hashlib.sha256(patched).hexdigest()
    print(json.dumps(receipt, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

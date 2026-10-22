"""PROVED OFFLINE: the five retail library functions the 2026 economy (revision 3) uses as code windows
("roster_a".."roster_e" in assemble.py) are unreferenced in the pinned USA retail executable.

For every window [start, end) this checks, over every byte offset of every section of the image:
- no 4-byte value (absolute pointer, immediate, table entry, unaligned or not) lies inside the window;
- no rel32 call/jmp (E8/E9) or rel32 conditional jump (0F 80..8F) outside the window targets inside it;
- no rel8 short jump (70..7F, EB) outside the window targets inside it;
- the window starts after a return and alignment padding and its bytes match the pinned digest.
A computed address that never appears as an encoding cannot be excluded by a static scan; the same
standard admitted the practice-squad caves (tools/practice_squad/AUDIT.md). Usage: dead_code.py RETAIL_XBE
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402

WINDOWS = {  # start: (size, sha256 of the retail bytes)
    0x396F50: (448, "9ef09938fc4ad15399b0f2d82b8cb69e9fb9dbb3ddccff0ddef0d8c8b06c358b"),
    0x3B9F60: (400, "e11762e6b811b005ce4599cf3e5ad83dc308d7c60c267f13522ec0276b220eb1"),
    0x3D2890: (352, "144d399994dc288d29b729f8172ecba63d4ce22a1e66427b0f4e70426dc95565"),
    0x3BA4B0: (352, "ac9713c06a3ec301ddf29ec79afdc40699b72730df3ed8e17303809076ef8f97"),
    0x3975F0: (224, "3bfc5caea3ae7fb715b36e87d20e2e45d00d8da5d244823709af655fcdadbe9a"),
}


def references(payload: bytes, windows=WINDOWS) -> dict:
    image = XbeImage(payload)
    found = {hex(start): [] for start in windows}
    spans = [(start, start + size) for start, (size, _) in windows.items()]

    def inside(target, source):
        for lo, hi in spans:
            if lo <= target < hi and not lo <= source < hi:
                found[hex(lo)].append((hex(source), hex(target)))

    for section in image.sections:
        if not section.raw_size:
            continue
        data = image.read(section.start, section.raw_size)
        base = section.start
        # Absolute values: the top two bytes of every window address are 0x00 and 0x39/0x3B/0x3D.
        for lo, hi in spans:
            top = struct.pack("<H", lo >> 16)
            for m in re.finditer(re.escape(top), data):
                i = m.start() - 2
                if i >= 0:
                    inside(struct.unpack_from("<I", data, i)[0], base + i)
        for m in re.finditer(b"[\xe8\xe9]", data):
            i = m.start()
            if i + 5 <= len(data):
                inside((base + i + 5 + struct.unpack_from("<i", data, i + 1)[0]) & 0xFFFFFFFF, base + i)
        for m in re.finditer(b"\x0f[\x80-\x8f]", data):
            i = m.start()
            if i + 6 <= len(data):
                inside((base + i + 6 + struct.unpack_from("<i", data, i + 2)[0]) & 0xFFFFFFFF, base + i)
        for lo, hi in spans:
            if base <= lo < base + len(data):
                for i in range(max(0, lo - base - 130), min(len(data) - 1, hi - base + 130)):
                    if 0x70 <= data[i] <= 0x7F or data[i] == 0xEB:
                        inside((base + i + 2 + struct.unpack_from("<b", data, i + 1)[0]) & 0xFFFFFFFF, base + i)
    return found


def verify(payload: bytes) -> dict:
    image = XbeImage(payload)
    report = {}
    for start, (size, digest) in WINDOWS.items():
        body = image.read(start, size)
        before = image.read(start - 16, 16)
        if hashlib.sha256(body).hexdigest() != digest:
            raise ValueError(f"{start:#x}: retail bytes differ from the pin")
        tail = before
        changed = True
        while changed:
            changed = False
            for pad in (b"\x90", b"\xcc", b"\x8b\xff", b"\x8d\x49\x00", b"\x8d\x64\x24\x00",
                        b"\x8d\x9b\x00\x00\x00\x00", b"\x8d\xa4\x24\x00\x00\x00\x00"):
                if tail.endswith(pad):
                    tail, changed = tail[:-len(pad)], True
        if not tail or not (tail.endswith(b"\xc3") or tail[-3:-2] == b"\xc2"):
            raise ValueError(f"{start:#x}: not preceded by a return and padding")
        report[hex(start)] = {"size": size, "sha256": digest}
    refs = references(payload)
    bad = {k: v for k, v in refs.items() if v}
    if bad:
        raise ValueError(f"referenced windows: {bad}")
    return {"evidence": "PROVED OFFLINE", "windows": report, "references": 0}


if __name__ == "__main__":
    print(json.dumps(verify(Path(sys.argv[1]).read_bytes()), indent=2))

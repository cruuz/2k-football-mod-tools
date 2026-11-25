"""PROVED OFFLINE: the twenty-nine retail functions the team-building owner (nfl2k5_team_building) uses as code windows are
unreferenced in the pinned USA retail executable (a thirtieth, 0x2D82F0, is the economy's revision-9
window roster_v and is proven in tools/franchise_economy/dead_code.py), by the economy's own tests (tools/franchise_economy/dead_code.py):

- no 4-byte value anywhere in the image (headers and every section, every byte offset) lies inside a window;
- no rel32 call/jmp (E8/E9) or rel32 conditional jump (0F 80..8F) outside a window targets inside it;
- no rel8 jump (70..7F, EB) within 130 bytes outside a window targets inside it;
- each window starts after a return and alignment padding, and its bytes match the pinned digest;
- the entry point, the TLS callbacks and every kernel import are outside every window.

Two more tests, both added for these windows (beta 81 team-building lane):
- decode synchronisation (``boundary_votes``): a start found by the "return + padding" rule can sit inside an
  instruction, so the bytes before each window are decoded from every offset 24..96 bytes back; at least 90 percent of
  those decodes land exactly on the window's start with a return as the last instruction that is not padding, and the
  window decodes to its end. Function-shaped spans that failed this (seven of the twelve largest unreferenced spans)
  are not used.
- no other writer: none of the windows overlaps a span of the cave reservation inventory
  (data/nfl2k5_cave_reservations.json), an economy window, or a byte that any of 477 built executables of the beta 81
  lanes (2026-11-25) changed from retail (the lane's tb_find_dead.py and check, recorded in its REVIEW_ME.txt).

Usage: dead_code.py RETAIL_XBE
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402
from tools.franchise_economy import dead_code as economy  # noqa: E402

WINDOWS = {  # start: (size, sha256 of the retail bytes)
    0x11C150: (206, "6a0627a3815ee96afdd8042600e9c3209459c59f93e1a7e940403c22d77b0488"),
    0x137D50: (116, "5629b8bc65bfd01104d7a7d6e565e766af2b11d305fa47ed727c3cbf486e1d8f"),
    0x1B8DA0: (123, "7f96ea0c7d90472dcab5001487156e42a6a4af203369c7b8adbc6dec3a251b34"),
    0x21AF20: (187, "b0af97b9730e74566b72d3df0e79fb3a5a53e34d6661559974a1767f6da22c80"),
    0x256310: (110, "ac2bdb653311ff29fed2441178ee27015e4aa8f8da0aecd59520f32401694f61"),
    0x256380: (110, "7586a4270b8c21882af7b5fe1b46761fee1270000bca47920464dc658285ce84"),
    0x256460: (110, "150fd3d7e648d3099048d698bdf91fda8dfd802d6de2bef1621d04c0bf0368bf"),
    0x256540: (110, "2e26328787c3aa09a9ef691b129aeac5acfcacfa7ccc1156a5d5bef56badda23"),
    0x256620: (110, "c5b1617c97ffed62bf58c816c668338a9a68249e3591363bc08415e38e9f9bfe"),
    0x284E50: (129, "3b72966b30190a9f4e97ef8b7b8ed405f80610273f3fee13d93414f652849085"),
    0x28E1D0: (110, "44dcd10a8b2934698493f139c987e38b7dcef65cff5d1e76cb4a2519e24c39ce"),
    0x295D40: (125, "bac87fcda14a810b1ae8bb5a5622644af5de5ecec757fbbf9ee4f3a9d4ade5f0"),
    0x2A8CA0: (124, "df738c80c70f0ba748ba155313186612af9adb2d2f55a97f92007ac32cc58357"),
    0x2AC900: (110, "9180b1dfb4220a03c21748b4d3e3d96c496f68f4dee07eb455061419536dbf41"),
    0x2AC9E0: (110, "7b1fb662a5abd9a317a17a137753f9a7e39076142ee852a58c0bbbae1332b0b7"),
    0x2CE070: (139, "97e5ab81dc640153673b4fe9e28d69d7c85cf9ede6e887e2de34c1774e9246ea"),
    0x30D560: (116, "1c362b368dafe6e33e5a5636feedc72f84f584cf2fa03904557890526b58c623"),
    0x30D720: (116, "1c362b368dafe6e33e5a5636feedc72f84f584cf2fa03904557890526b58c623"),
    0x315E50: (110, "44dcd10a8b2934698493f139c987e38b7dcef65cff5d1e76cb4a2519e24c39ce"),
    0x342370: (114, "150409860c8ad33832bc493ef0144e9ea282ed63c389718470495cc9ae4219f1"),
    0x357890: (114, "150409860c8ad33832bc493ef0144e9ea282ed63c389718470495cc9ae4219f1"),
    0x382110: (112, "84611ff71826a4163b01c8c75fbcee24c0136b875d49694ae343cab7131d4ca9"),
    0x388820: (123, "f8479f7c678f3a1fb9283d7c4c177c935e1ba9b41e30fed5eba7e711094e811c"),
    0x396B40: (113, "8ea370535f73774d2ae07a8e89b1f989d89ef2cd0805b2227436bf0ccb4a60c9"),
    0x3C9FA0: (116, "55f0f3f333eebf2fa0f26c9fbac31df62a5f9d1a84e34e33befb680bb87405f1"),
    0x3E1A20: (192, "1a9eb7a465bc1658c937f5fa3379ca56a2fcd0e2ae741530f4006427730a3330"),
    0x3E9050: (122, "48e16eae9c5d58ccc0a70f077cc09c118f423867f1a477bd16eda309efd57c3d"),
    0x3F43B0: (117, "b5b94548eae653b94a6edfde69e22fba55bae2309aa716d163fcd3b2a75d3290"),
    0x3F6390: (123, "6865039eadb91cc7619c60cf38ed4b712dbb76b6cd59b8b1861be232a036e87c"),
}
PADDING = ("nop", "int3")


def _is_pad(ins) -> bool:
    if ins.mnemonic in PADDING or (ins.mnemonic == "mov" and ins.op_str == "edi, edi"):
        return True
    if ins.mnemonic != "lea" or "+" in ins.op_str or "*" in ins.op_str or "-" in ins.op_str:
        return False
    reg, mem = ins.op_str.split(", ", 1)
    return mem in (f"[{reg}]", f"dword ptr [{reg}]")


def boundary_votes(payload: bytes, start: int, size: int) -> tuple[int, int, int]:
    """(decodes landing on `start` after a return, decodes tried, window bytes decoded)."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    image = XbeImage(payload)
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    good = 0
    for back in range(24, 97):
        prev, landed = None, False
        for ins in md.disasm(image.read(start - back, back + 16), start - back):
            if ins.address >= start:
                landed = ins.address == start
                break
            if not _is_pad(ins):
                prev = ins
        good += landed and prev is not None and prev.mnemonic in ("ret", "retn")
    decoded = sum(ins.size for ins in md.disasm(image.read(start, size), start))
    return good, 73, decoded


def verify(payload: bytes, windows=None) -> dict:
    windows = WINDOWS if windows is None else windows
    image = XbeImage(payload)
    report = {}
    spans = [(start, start + size) for start, (size, _) in windows.items()]
    for start, (size, digest) in windows.items():
        body = image.read(start, size)
        if hashlib.sha256(body).hexdigest() != digest:
            raise ValueError(f"{start:#x}: retail bytes differ from the pin")
        good, tried, decoded = boundary_votes(payload, start, size)
        if good * 10 < tried * 9 or decoded != size:
            raise ValueError(f"{start:#x}: not a clean function start ({good}/{tried} decodes, {decoded}/{size} bytes)")
        for lo, hi in [(s, s + n) for s, (n, _) in economy.WINDOWS.items()]:
            if lo < start + size and start < hi:
                raise ValueError(f"{start:#x}: overlaps the economy window {lo:#x}")
        report[hex(start)] = {"size": size, "sha256": digest, "boundary_votes": f"{good}/{tried}"}
    outside = lambda va: not any(lo <= va < hi for lo, hi in spans)  # noqa: E731
    entry = struct.unpack_from("<I", payload, 0x128)[0]
    for key in (0xA8FC57AB, 0x94859D4B):
        if not outside(entry ^ key):
            raise ValueError("the XBE entry point is inside a window")
    tls = struct.unpack_from("<I", payload, 0x12C)[0]
    callbacks = struct.unpack("<I", image.read(tls + 12, 4))[0] if tls else 0
    k = 0
    while callbacks:
        cb = struct.unpack("<I", image.read(callbacks + 4 * k, 4))[0]
        if not cb:
            break
        if not outside(cb):
            raise ValueError("a TLS callback is inside a window")
        k += 1
    refs = economy.references(payload, windows)
    bad = {key: value for key, value in refs.items() if value}
    if bad:
        raise ValueError(f"referenced windows: {bad}")
    return {"evidence": "PROVED OFFLINE", "windows": report, "references": 0, "tls_callbacks": k}


def reservations_clear(windows=None) -> list[str]:
    """Windows overlapping a span of the cave reservation inventory (empty when clear)."""
    windows = WINDOWS if windows is None else windows
    spans = json.loads((ROOT / "data/nfl2k5_cave_reservations.json").read_text())["spans"]
    hits = []
    for start, (size, _) in windows.items():
        for s in spans:
            lo, hi = int(s["start"], 16), int(s["end"], 16)
            if lo < start + size and start < hi:
                hits.append(f"{start:#x} {s['owner']}")
    return hits


if __name__ == "__main__":
    print(json.dumps(verify(Path(sys.argv[1]).read_bytes()), indent=2))
    print("reservation overlaps:", reservations_clear())

#!/usr/bin/env python3
"""b778-ee1: assemble tools/b77/ee1_alien_prospect.S (GNU as + ld, linked at 0xE696E) into
data/nfl2k5_alien_prospect/code.json (bytes, symbols, the test-build patch point, the retail region pin) and pin the
shipped art in art.json. Authoring tool only: the Studio reads the JSON and never needs an assembler.

usage: ee1_build_code.py --retail-xbe default.xbe [--work DIR]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "tools" / "b77" / "ee1_alien_prospect.S"
DATA = ROOT / "data" / "nfl2k5_alien_prospect"
VA, END = 0xE696E, 0xE6D15
THRESH = 75657


def section_bytes(xbe: bytes, va: int, size: int) -> bytes:
    base = struct.unpack_from("<I", xbe, 0x104)[0]
    count, table = struct.unpack_from("<II", xbe, 0x11C)
    for i in range(count):
        _f, sva, _vs, raw, rsize = struct.unpack_from("<IIIII", xbe, table - base + i * 56)
        if sva <= va and va + size <= sva + rsize:
            return xbe[raw + va - sva:raw + va - sva + size]
    raise SystemExit(f"0x{va:x} is not file-backed")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--retail-xbe", required=True, type=Path)
    ap.add_argument("--work", type=Path)
    args = ap.parse_args()
    work = args.work or Path(tempfile.mkdtemp())
    work.mkdir(parents=True, exist_ok=True)
    subprocess.run(["as", "--32", "-o", str(work / "a.o"), str(SRC)], check=True)
    subprocess.run(["ld", "-m", "elf_i386", f"-Ttext=0x{VA:X}", "-o", str(work / "a.elf"), str(work / "a.o")], check=True)
    subprocess.run(["objcopy", "-O", "binary", str(work / "a.elf"), str(work / "a.bin")], check=True)
    code = (work / "a.bin").read_bytes()
    assert len(code) <= END - VA, len(code)
    symbols = {}
    for line in subprocess.run(["nm", str(work / "a.elf")], check=True, capture_output=True, text=True).stdout.splitlines():
        addr, kind, name = line.split()
        if kind in "tT" and name not in ("_start", "__bss_start", "_edata", "_end"):
            symbols[name] = f"0x{int(addr, 16):x}"
    alien = int(symbols["alien"], 16) - VA
    imm = code.find(b"\x3d" + struct.pack("<I", THRESH), alien)
    assert imm > 0 and code.count(struct.pack("<I", THRESH)) == 1
    retail = section_bytes(args.retail_xbe.read_bytes(), VA, END - VA)
    doc = {"schema": "nfl2k5_alien_prospect_code/v1", "va": VA, "end": f"0x{END:x}", "source": "tools/b77/ee1_alien_prospect.S",
           "code": code.hex(), "sha256": hashlib.sha256(code).hexdigest(), "symbols": symbols,
           "thresh_imm_offset": imm + 1, "retail_region_sha256": hashlib.sha256(retail).hexdigest()}
    (DATA / "code.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    art = {"schema": "nfl2k5_alien_prospect_art/v1",
           "note": "Fictional gray alien made for this mod: the draft headshot was generated with ChatGPT image generation "
                   "through the Codex CLI (Noah's subscription, built-in image_gen, no reference photo); the face, skull "
                   "and neck textures are that headshot projected onto the retail head mesh's UV layout and de-lit, "
                   "with a flat gray skull and neck; the helmet-on face (f) is darkened outside the face opening by a heavily "
                   "blurred mask measured from retail f/h pairs (tools: .b77-scratch/b778/ee1/art). No retail picture "
                   "is included.",
           "sha256": {k: hashlib.sha256((DATA / n).read_bytes()).hexdigest()
                      for k, n in (("portrait", "portrait.png"), ("f", "face_f.png"), ("h", "face_h.png"), ("n", "face_n.png"))}}
    (DATA / "art.json").write_text(json.dumps(art, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"bytes": len(code), "free": END - VA - len(code), "symbols": symbols}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

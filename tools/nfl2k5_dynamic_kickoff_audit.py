#!/usr/bin/env python3
"""Read-only retail reference audit for the dynamic kickoff cave and storage.

Prints addresses/counts/hashes only. It never saves retail bytes or boots a game.
This is a finite static audit, not a proof against arbitrary computed pointers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_dynamic_kickoff as dk
from mod_editor.core.nfl2k5_bump_strength import RETAIL_XBE_SHA256
from tools.xbe_info import Xbe


def audit(path: Path) -> dict:
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32

    xbe = Xbe(path)
    data = xbe.data
    if hashlib.sha256(data).hexdigest() != RETAIL_XBE_SHA256:
        raise ValueError("reference audit requires the pinned USA retail default.xbe")
    dk._validate_storage(data)
    lo, hi = dk.CAVE_VA, dk.CAVE_VA + dk.CAVE_SIZE
    refs = []
    branch_count = 0
    # No entry-point exemption. Scan all byte positions for long transfers in
    # game code and linked libraries, including functions missing from Ghidra.
    libraries = {".text", "D3D", "DSOUND", "WMADEC", "XGRPH", "XNET", "XONLINE",
                 "PSFD_I", "PSFD_B", "PSFD_P", "PSFD00", "XPP", "DOLBY", "XON_RD"}
    for s in xbe.sections:
        raw, size, base = s["raw_address"], s["raw_size"], s["virtual_address"]
        block = data[raw:raw + size]
        if s["name"] in libraries:
            for match in re.finditer(rb"[\xe8\xe9]|\x0f[\x80-\x8f]", block):
                off = match.start()
                width = len(match.group()) + 4
                if off + width > len(block):
                    continue
                branch_count += 1
                source = base + off
                target = (source + width + struct.unpack_from("<i", block, off + width - 4)[0]) & 0xFFFFFFFF
                if lo <= target < hi and not lo <= source < hi:
                    refs.append((hex(source), hex(target), "relative"))
        # All aligned dwords in all sections, including data tables and callbacks.
        for off in range(0, size - 3, 4):
            value = struct.unpack_from("<I", block, off)[0]
            source = base + off
            if lo <= value < hi and not lo <= source < hi:
                refs.append((hex(source), hex(value), "aligned word"))
        if s["name"] == ".text":
            # Also unaligned pointer immediates, conservatively ALL dwords in
            # game .text; this covers C7 with any displacement/ModRM form.
            for match in re.finditer(rb"(?=([\x00-\xff][\x90-\x98]\x28\x00))", block):
                value = struct.unpack("<I", match.group(1))[0]
                source = base + match.start()
                if lo <= value < hi and not lo <= source < hi:
                    refs.append((hex(source), hex(value), "unaligned text word"))
    # The predecessor ends with RET at 2890C4, then its jump table and eight
    # NOPs. The successor starts at 289890. The only raw rel8-like byte reaching
    # this cave is 2898A6 (the SECOND byte of FCHS), not a branch instruction.
    boundaries = ((0x2890C4, 0x2C, "31c9619a80eadc44680d4e7501d88a8549c909b7af0da81cbdc7d48e1d037aaf"),
                  (0x289883, 0x3D, "b217e2c52556e5c7fc64230f8f906db5748bd69d215b8d736505f85424eab3c6"))
    for start, size, pin in boundaries:
        off = xbe.va_to_offset(start, size)
        if hashlib.sha256(data[off:off + size]).hexdigest() != pin:
            raise ValueError(f"cave neighbour differs at {start:#x}")
    for start, end in ((lo - 128, lo), (hi, hi + 128)):
        off = xbe.va_to_offset(start, end - start + 1)
        for n in range(end - start):
            op = data[off + n]
            if op == 0xEB or 0x70 <= op <= 0x7F or 0xE0 <= op <= 0xE3:
                source = start + n
                target = source + 2 + struct.unpack_from("<b", data, off + n + 1)[0]
                if lo <= target < hi and source != 0x2898A6:
                    refs.append((hex(source), hex(target), "raw rel8 candidate"))
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    off = xbe.va_to_offset(0x289890, 0x30)
    for ins in md.disasm(data[off:off + 0x30], 0x289890):
        if ins.address == 0x2898A5 and (ins.mnemonic != "fchs" or ins.size != 2):
            raise ValueError("the excluded raw rel8 candidate is no longer the FCHS operand")
        if ins.mnemonic.startswith("j") or ins.mnemonic.startswith("loop"):
            target = ins.operands[0].imm
            if lo <= target < hi:
                refs.append((hex(ins.address), hex(target), "rel8 successor"))
    storage_refs = []
    # Every byte alignment in the entire file, not just typed instructions.
    for start, size in dk.STORAGE_RANGES:
        for va in range(start, start + size):
            for match in re.finditer(re.escape(struct.pack("<I", va)), data):
                storage_refs.append((hex(match.start()), hex(va)))
    result = {"retail_sha256": RETAIL_XBE_SHA256,
              "cave": {"start": hex(lo), "end_exclusive": hex(hi), "bytes": hi - lo,
                       "retail_sha256": dk.RETAIL_CAVE_SHA256, "external_references": refs},
              "long_branch_candidates_checked": branch_count,
              "storage": {"ranges": [[hex(a), n] for a, n in dk.STORAGE_RANGES],
                          "writable_shared_page": True, "address_literals": storage_refs},
              "limitations": "Aligned data pointers plus all text dwords and long branches; computed pointers are not exhaustively decidable."}
    if refs or storage_refs or dk.status(data) != "retail":
        raise ValueError(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xbe", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.xbe), indent=2))


if __name__ == "__main__":
    main()

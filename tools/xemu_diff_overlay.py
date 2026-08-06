#!/usr/bin/env python3
"""Overlay harness cmp -l diff onto o0308 0xB4 / NODE stakes.

Usage:
  bash tools/xemu_formation_fixture_harness.sh --diff > /tmp/diff.txt
  python3 tools/xemu_diff_overlay.py /tmp/diff.txt

Or after live saves:
  cmp -l /tmp/xemu-2k5-fixture/clean/eeprom.bin /tmp/xemu-2k5-fixture/FX/eeprom.bin | python3 tools/xemu_diff_overlay.py -

Maps file byte deltas to:
  - formation 0xB4 window 0x1A4-0x1E8 (body_off 0x20 + 0x134 + 0x70…)
  - aux 0x50 0x245c/0x24ac invariant
  - NODE chain 0x9adc / 0x9ae4 / 0x9aec

Stops guesswork: prints exactly which staked byte flipped.
"""
from __future__ import annotations
import pathlib, sys

# Stakes from docs/product/PLAY_*.md — must match probe
BODY_OFF = 0x20
FORMATION_BASE = 0x134
FORMATION_SIZE = 0xB4
NODE_BASE = 0x9adc
NODE_SIZE = 8
# file offset in the vc_53450030/0:106803200 slice = BODY_OFF + FIELD
STAKED = {
    # Body-relative (inspector: formation @0x134, node @0x9adc). For a raw PLAY slice
    # at 0x13390 body, cmp -l on the extracted slice uses these. For the
    # vc_53450030/0:106803200 container slice (wrapper 0x20 + body), add 0x20;
    # for eeprom container, locate PLAY blob first then apply this map.
    "FX/Y window start (body)": FORMATION_BASE + 0x70,      # 0x1A4 body, 0x1C4 slice
    "FX/Y window end (body)": FORMATION_BASE + 0xB4,        # 0x1E8 body, 0x208 slice
    "FX/Y window start (slice)": BODY_OFF + FORMATION_BASE + 0x70,
    "FX/Y window end (slice)": BODY_OFF + FORMATION_BASE + 0xB4,
    "NODE 0 body": NODE_BASE,                          # 0x9adc body, 0x9afc slice
    "NODE 0 slice": BODY_OFF + NODE_BASE,
    "NODE 1 body": NODE_BASE + 8,                      # 0x9ae4 body, 0x9b04 slice
    "NODE 1 slice": BODY_OFF + NODE_BASE + 8,
    "NODE FW insert body": NODE_BASE + 16,             # 0x9aec body, 0x9b0c slice
    "NODE FW insert slice": BODY_OFF + NODE_BASE + 16,
    "AUX 0x50 a body": 0x245c, "AUX 0x50 a slice": BODY_OFF + 0x245c,
    "AUX 0x50 b body": 0x24ac, "AUX 0x50 b slice": BODY_OFF + 0x24ac,
}

def parse_cmp_l(stream):
    diffs=[]
    for line in stream:
        line=line.strip()
        if not line or line.startswith("#") or line.startswith("-") or "vs clean" in line:
            continue
        # cmp -l: offset base8? Actually decimal byte index + octal values
        parts=line.split()
        if len(parts)>=3 and parts[0].isdigit():
            off=int(parts[0])  # 1-indexed byte offset in file slice
            # convert to 0-indexed body file offset
            diffs.append(off)
    return diffs

def classify(off0):
    hits=[]
    # FX/Y window — accept both body-relative and slice-relative
    if (STAKED["FX/Y window start (body)"] <= off0 < STAKED["FX/Y window end (body)"] or
        STAKED["FX/Y window start (slice)"] <= off0 < STAKED["FX/Y window end (slice)"]):
        base = STAKED["FX/Y window start (body)"] if off0 < STAKED["FX/Y window start (slice)"] else STAKED["FX/Y window start (slice)"]
        hits.append(f"FX/Y window 0x{off0:04x} (off {off0 - base:02x} in B4)")
    # NODE payloads — also both
    for key_body, key_slice, label in [
        ("NODE 0 body", "NODE 0 slice", "NODE0"),
        ("NODE 1 body", "NODE 1 slice", "NODE1 FT candidate"),
        ("NODE FW insert body", "NODE FW insert slice", "FW insert"),
    ]:
        if (STAKED[key_body]+2 <= off0 <= STAKED[key_body]+7) or (STAKED[key_slice]+2 <= off0 <= STAKED[key_slice]+7) or (STAKED[key_slice] <= off0 < STAKED[key_slice]+8 and "FW" in label):
            # tighten FT vs FW: NODE1 payload 2..7, FW whole 8-byte slot
            if "FW" in label and (STAKED[key_slice] <= off0 < STAKED[key_slice]+8 or STAKED[key_body] <= off0 < STAKED[key_body]+8):
                hits.append(f"{label} 0x{off0:04x}")
            elif "NODE" in label and (STAKED[key_body]+2 <= off0 <= STAKED[key_body]+7 or STAKED[key_slice]+2 <= off0 <= STAKED[key_slice]+7):
                hits.append(f"{label} payload 0x{off0:04x}")
    if not hits:
        hits.append(f"file 0x{off0:04x}")
    return hits

def main():
    src = sys.argv[1] if len(sys.argv)>1 else "-"
    stream = sys.stdin if src=="-" else pathlib.Path(src).open()
    diffs = parse_cmp_l(stream)
    if not diffs:
        print("No cmp -l deltas parsed — feed `cmp -l clean/eeprom.bin FX/eeprom.bin` or harness --diff output")
        print(f"Staked ranges: { {k: hex(v) for k,v in STAKED.items() } }")
        return 0
    for off in diffs[:40]:
        off0=off-1
        print(f"{off:6d} (0x{off0:04x}) -> {', '.join(classify(off0))}")
    if len(diffs)>40:
        print(f"... {len(diffs)-40} more")
    print(f"total deltas {len(diffs)} | staked: FX/Y body {STAKED['FX/Y window start (body)']:#x}-{STAKED['FX/Y window end (body)']:#x} slice {STAKED['FX/Y window start (slice)']:#x}-{STAKED['FX/Y window end (slice)']:#x} NODE1 {STAKED['NODE 1 body']+2:#x}-{STAKED['NODE 1 body']+7:#x} FW {STAKED['NODE FW insert body']:#x}+8")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

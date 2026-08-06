# Node opcode payload — offline length hypothesis for 0x01..0x1B

**Source:** `nfl2k5.resource.o0308.c0000.k504c4159` (ATL 39/254) and corpus 91,833 nodes. `NODE_SIZE=8` at `NODE_BASE=0x9adc` proved by probe `tools/nfl2k5_formation_coordinate_probe.py` (walk until `b1&0x02 TERM`). This file stakes the next verifiable claim: fixed 8-byte nodes, not variable.

## What varies offline

- Every `chain_start` (`0x01` 18k / `0x1B` 13k / `0x1A` 433) lands on `NODE_BASE + idx*8` with `b1&0b111==0` on first node.
- Every terminal has `b1&0x02 !=0`, regardless of opcode.
- Dumping `o0308` play 0 slot 0: `node0 1b 00 00 00 00 00 40 80` → `node1 0b 06 00 00 01 00 00 68 TERM` — exactly 2 ×8.

Hypothesis: All `0x01..0x1B` are 8-byte slots where byte0 is opcode, byte1 is flags/payload-type, bytes 2-7 are 6 bytes of operands (2× i16 coords + 2× u8 time/style, or similar). The `FW` fixture (add one waypoint without moving endpoints) should grow the chain by exactly one 8-byte node and leave the 12 endpoint `X/Y` bytes unchanged; `FT` (route-type without moving point) should flip exactly one of bytes 2-7 while keeping the `X/Y` pair stable.

## How to prove

1. Run `harness --run` headless on `o0308` play 0 WR1 slot 0, do `FW` (+1 waypoint) and save as `FW`, then `FT` (Curl→Slant) and save as `FT`.
2. `harness --diff` on the `vc_53450030/0:106803200` slice: `FW` should be `+8` bytes of chain (one node) vs `clean`; `FT` should be `±0` bytes but one operand byte diff vs `FX`/`FY`.
3. Place read watchpoints on that operand byte while the play is drawn (play-call UI) vs executed (on-field). A byte is a coordinate iff it moves `+2` in `FX` xor `FY` and is stable in `FT`; a byte is a style flag iff it flips in `FT` with zero `FX`/`FY` delta and is consumed in the draw path.

Until both the `+8` growth (FW) and the single-byte `FT` flip with watchpoint agree, no chain writer will be shipped — clone primitive (`play_formation_create`/`play_create`) remains the only writer, and it preserves chain bytes exactly via the 12 relative pointers.

## Repro (offline, no xemu)

```
PYTHONPATH=. python3 tools/nfl2k5_formation_coordinate_probe.py --book nfl2k5.resource.o0308.c0000.k504c4159 --play 0 --slot 0 --dump-nodes
PYTHONPATH=. python3 -m pytest tests/mod_editor/test_nfl2k5_formation_play_writer.py -q  # 3/3 pack-0 proof still
```

No retail payload is checked in — only offsets (`0x70-0xB4`, `0x9adc`), counts, and `uniq`/`sha256` sidecars.

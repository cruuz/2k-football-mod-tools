# Offline 0xB4 variance — formation coordinate window hypothesis

**Source:** `nfl2k5.resource.o0308.c0000.k504c4159` (ATL-like, 39 formations / 254 plays, `0x13390` body). Probe `tools/nfl2k5_formation_coordinate_probe.py` diffing formations 0 vs 1 (`Split Pro` vs `Split Twins`) + per-offset uniq across all 39.

**Tool:** `PYTHONPATH=. python3 tools/nfl2k5_formation_coordinate_probe.py --book nfl2k5.resource.o0308.c0000.k504c4159 --formation 0 --compare 1 --play 0 --slot 0 --dump-nodes`

## What varies

`FORMATION_SIZE = 0xB4` (180). High-variant bytes are **not** the header — they cluster at `0x70-0xB4` (68-byte window) with `uniq 11-28` across 39 formations, vs low-variant header `0x00-0x1F` (`uniq 1-8` except a few ids) and sentinel regions `0x20-0x6F` with flat/period-22 patterns.

Per-offset `uniq` (distinct byte values across 39 formations) — excerpt:

```
000:36 001:25 018:23 06c:11 070:17 072:28 074:18 078:20 080:26 082:19 090:24 09c:27 09e:29 ...
070-0xB4 window all uniq 11-29 (68 bytes)
AUX 0x50 per-offset uniq 6-32 but whole table is play-slot u16s + group bits 9-10 (already proved — not coordinates)
```

Full table is in probe stdout; the 0x70-0xB4 slice is the only contiguous 68-byte run where **every** offset is high-variant.

## Sample window

`0x70-0xB4` for first 5 formations (hex + i16 LE):

- f0 `Split Pro`: `37 fe b6 01 94 fb 00 00 2b ff 00 00 00 83 a5 fa 36 03 a5 fa 25 ff 2b ff 25 ff 00 72 5b 05 5b 05 62 fc ... b9 fd 0a fe 07 fe 1a ff 00 a1 fa 00 00 04 e8 ff 0a fe 2b ff 25 fd` → i16 `[-457,438,-1132,0,-213,0,-32000,-1371,822,-1371,-219,-213,-219,29184,1371,1371,-926,0,0,-207,-27904,-250,-252,-583,-502,-505,-230,-24320,250,1024,-24,-502,-213,-731]`
- f1 `Split Twins`: `37 fe c3 01 37 fe 00 00 25 ff ...` → `[-457,451,-457,0,-219,0,-32000,822,822,-1377,-219,-219,-201,29184,1371,1371,-944,0,0,-207,-27904,-250,-250,-609,-502,-502,-207,-24320,250,621,-30,-502,-219,-740]`
- f2 `Split Flip Pro`, f3 `Split Spread`, f4 `Split Jokers` — see probe dump for full 68-byte hex (variance is per-player, not per-formation id).

Window size `0x44 = 68`. Naive hypotheses:
- `11 players × 6 bytes = 66` (close, 2 slack)
- `11 × 4 = 44` (too small), `11×2×2 =44` (too small)
- So not a simple `x,y` i16 pair per player; may be `x,y` + orientation/role flag per player (≈6 bytes) or 11 slots include 2-byte padding.

**What AUX proves:** `0x50` aux at `0x245c`/`0x24ac` diffs only in the 36×u16 play-slot table + group bits; identical trailing 8 bytes. Coordinate bytes do **not** live in `0x50`.

## Blocking still

- No live FX (+2 X) vs FY (+2 Y) diff yet — xemu still `which xemu` not found on this host, so sign/scale/axis not proved. This file is the offline predictor; FX/FY will label each offset in `0x70-0xB4` as `X` / `Y` / `orient` / `flags` by linear `+2` delta.
- Node opcode operands (`0x01..0x1B`) still need `FT` (route type change without moving points) vs `FW` (add waypoint) isolation — also needs xemu save diff + watchpoints on play-call draw vs on-field exec.

## What this unlocks next

When xemu fixtures land, overlay:
- `FX-only` byte that scales ×2 when WR1 moves +4 X → `X coord`
- `FY-only` similarly → `Y coord`
- Byte that is identical in `FX`/`FY` but flips in `FT` → route style/opcode
- Bytes that grow by one node in `FW` → chain insert length

Until both the diff **and** the runtime watchpoint agree, no field canvas writes coordinates.

## Repro

```
PYTHONPATH=. python3 tools/nfl2k5_formation_coordinate_probe.py --book nfl2k5.resource.o0308.c0000.k504c4159 --formation 0 --compare 1 --dump-nodes
```

Add `--play 0 --slot 3` etc for node operand hypotheses. Raw dumps contain only private-cache-derived hex (no retail payload checked in).

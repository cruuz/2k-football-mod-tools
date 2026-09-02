# Formation + node opcode census — o0308 39/254 (ATL-like)

**Source:** `nfl2k5.resource.o0308.c0000.k504c4159` via `Nfl2k5UniversalAssetIndex` + `parse_playbook_resource`, `BODY_SIZE 0x13390`, `RESOURCE_HEADER_SIZE 0x20`. No retail bytes checked in — only per-offset `uniq` counts and opcode totals.

## Formation 0xB4 (180 bytes) — per-byte uniq across 39 formations

`off : uniq` where `uniq>1` — high uniq = candidate for player position / role variance, low uniq = header/flags/invariant:

- `00:36 01:25 02:2 05:13 06:14 07:13 08-0b:6 0c:5 0d:4 0e:8 0f:8 10:6 11:8 12:7 13:8 14:8 15:7 16:5 17:3`
- `18:23 1b:6 1c:9 1d:4 1e:8 1f:3 20:9 21:4 22:12 23:10 24:14 25:10 26:14 27:10`
- `29:5 2a:14 2b:7 2c:14 2d:6 2e:14 2f:7 30:7 31:6 32:8 33:6 34:10 35:7`
- `37:3 38:14 39:7 3a:13 3b:7 3c:13 3d:7 3e:6 3f:5 40:6 41:5 42:7 43:5`
- `45:5 46:11 47:6 48:12 49:6 4a:11 4b:5 4c:6 4d:6 4e:6 4f:6 50:6 51:6`
- `53:8 54:15 55:8 56:15 57:6 58:15 59:6 5a:9 5b:7 5c:10 5d:8 5e:12 5f:7`
- `61:8 62:15 63:7 64:17 65:8 66:16 67:7 68:9 69:8 6a:12 6b:7 6c:11 6d:7`
- `6f:12 70:17 71:8 72:28 (!) 73:11 74:18 75:11 76:13 77:9 78:20 79:9 7a:15 7b:9`
- `7d:10 7e:16 7f:10 80:26 81:11 82:19 83:10 84:12 85:8 86:19 87:9 88:17 89:9`
- `8b:11 8c:18 8d:10 8e:18 8f:9 90:24 91:8 92:11 93:9 94:12 95:9 96:16 97:9`
- `99:9 9a:18 9b:11 9c:27 9d:10 9e:29 (!) 9f:9 a0:14 a1:8 a2:22 a3:8 a4:23 a5:8`
- `a7:6 a8:12 a9:10 aa:28 (!) ab:11 ac:24 ad:11 ae:14 af:8 b0:23 b1:8 b2:21 b3:8`

Previously staked `0x70-0xB4` window (file `0x1A4-0x1E8`) overlaps census highs `72:28 80:26 9e:29 aa:28 ac:24` — so FX/FY `+2 LE i16` is expected among those ultra-high uniq slots, while prior `ff07×N` trailer at tail stays low uniq (not listed = 1) per earlier probe — `harness --run` will isolate exactly one of those highs.

## Node opcodes — 0x01..0x1B but census across 39×11 chains (this book, not whole corpus)

- `opcode total {1:2643 2:148 3:152 4:89 5:1 6:93 7:1 8:5 9:34 10:79 11:167 12:48 13:251 14:208 16:65 17:1217 18:836 19:47 20:25 21:81 22:47 23:25 24:32 26:20 27:641}` — dominant `0x01` then `0x11/0x12/0x1B`.
- `terminal by opcode {1:432 11:167 13:228 14:178 17:996 18:456 …}` — confirms `b1&0x02 TERM` fires on many opcodes, not just `0x0b` in play0 example (`1b00→0b06`). Every chain ends on TERM regardless of opcode.
- `NODE_SIZE 8` holds: `0x9adc` `NODE_BASE` walk hits TERM within 16 steps for all slots in this book.

## How this tightens next xemu run (no synthesis yet)

- FX/FY should each bump **one** of the `28/26/29`-uniq offsets by `+2 LE` while the other stays `0`; trailer bytes (uniq 1) must stay fixed — use `PLAY_FIXTURE_QUICKREF.md` row FX/FY.
- FW `+8` at `0x9aec` and FT flip at `0x9ae4+2..7` operate in same 8-byte node space whose high-frequency opcodes (`0x01/0x11/0x12`) are already proved TERM-capable — watchpoints on those 8 stake bytes remain valid.

Repro (offline):
```
PYTHONPATH=. python3 tools/nfl2k5_formation_coordinate_probe.py --book nfl2k5.resource.o0308.c0000.k504c4159 --formation 0 --compare 1 --play 0 --slot 0 --dump-nodes
PYTHONPATH=. python3 -m pytest tests/mod_editor/test_nfl2k5_formation_play_writer.py -q  # pack-0 3/3 still
```

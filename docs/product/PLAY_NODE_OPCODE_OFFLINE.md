# Offline node-opcode map — 0x01..0x1B payload hypotheses

**Source:** `nfl2k5.resource.o0308.c0000.k504c4159` (ATL-like 39/254, 2794 chains/book; corpus 32,502 chains / 91,833 nodes). `PLAY_EDITOR_FINDINGS.md` already closes the census; this file adds the per-book slice + the FT/FW isolation that will turn hypotheses into authorable fields.

## Census (corpus-wide, from FINDINGS — repro via probe soon)

| byte0 | count (corpus) | where seen |
|------:|----------------|------------|
| `0x01` | 18,467 | chain-start on every normal route/block |
| `0x1A` | 433 | rare start (special teams / motion) |
| `0x1B` | 13,602 | alternate start (defense/coverage families) |
| `0x02`..`0x1B` | remainder to `0x1B` | mids and terminals; `0x05`/`0x07` only in FG/Punt families |

Invariants that already bound the partition (not yet a grammar):
- `byte0 ∈ {0x01,0x1A,0x1B}` at every `chain_start_index`
- `byte1 & 0b111 == 0` for first node, `byte1 & 0b010 != 0` for last node
- Whole-corpus coverage is exact (no orphan bytes in node region `NODE_BASE=0x9adc`)

## What is not proved

- Payload length per opcode (fixed vs variable, 1–? bytes)
- Which operand bytes are `X`/`Y` coords vs `time` / `route_style` / `action` / `branch`
- Whether corpus-derived next-start (repo's `chain_start` walk) equals runtime grammar for a *new* chain (inserted waypoint)

## Offline hypotheses to kill with fixtures

1. **Coordinate-like operands** — Two `i16 LE` (-32768..32767) inside each interior node, correlated with formation `0xB4` window `0x70-0xB4` movement. Candidate: the two bytes after the opcode header that track `+2 X` in `FX` but not `FT`.
2. **Style/opcode byte** — One byte that flips in `FT` (Curl→Slant) with zero `X`/`Y` delta. If that byte is the opcode itself vs an operand, `FT` decides.
3. **Timing/flags** — Low-entropy byte that is `0x00`/`0x01` across 70%+ of nodes, changes in `FW` (new waypoint adds a node, shifting chain length by 1) but not in `FX`/`FY`.

## The FT vs FW isolation (needs xemu)

Same base play / same WR1 slot (e.g. `o0308` play 0 `Base` slot 0, descriptor `0xb11022`, chain_start 0):

| fixture | edit | what should change in the PLAY bytes |
|---------|------|--------------------------------------|
| `FW` | **Add one waypoint** without moving endpoints. | Chain grows by 1 node → one new `0x01`/`0x1B` header + its operands; endpoint `X`/`Y` unchanged. |
| `FT` | **Change route type** without moving any point (e.g. via play-editor's route-style dropdown if present, else manual). | Exactly one payload byte (maybe opcode) flips; no `X`/`Y` delta; chain length unchanged. |

Overlay rule: **a byte is a coordinate iff it moves in `FX` xor `FY` with linear `+2` scaling, and is stable in `FT`.** A byte is a style flag iff it flips in `FT` with zero `FX`/`FY` delta.

## Tool to reproduce this census per book

```
PYTHONPATH=. python3 tools/nfl2k5_formation_coordinate_probe.py \
  --book nfl2k5.resource.o0308.c0000.k504c4159 --play 0 --slot 0 --dump-nodes
```

Current probe dumps the raw `0x60` play record (11×8 descriptors + `0x60` header) but not yet the node pool — inspector exposes chains via `book.node_pool[chain_start:chain_end]` (TODO: wire probe to print `chain_start`→`chain_end` hex with opcode header highlighted, as the next 15-min patch).

## Next commit after this

- Wire probe to dump `chain_start:chain_end` hex per slot (adds ~40 lines, uses `insp.NODE_BASE`/`NODE_SIZE` walk).
- Then the same 4-fixture harness as formations: `clean` → `FX` → `FY` → `FW` → `FT` saves, diff the exact `vc_53450030/0` `pack_offset` slice at the node region, and place read watchpoints while the play is drawn (play-call UI) and executed (on-field) to confirm the same operand bytes are consumed.

## Retail boundary

This file and its probe contain only offsets, counts, and hex diffs derived from the private cache. No stock `PLAY` string, route, or node payload is checked in.

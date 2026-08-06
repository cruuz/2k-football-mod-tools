# PLAY formation-coordinate & node-opcode fixture spec

**Goal:** turn the 4-fixture plan in `PLAY_EDITOR_FINDINGS.md` (Best next spike) into a byte-exact harness that isolates formation X vs Y and node operand meaning before any field canvas invents a coordinate.

**Status:** offline clone primitive is pack-0 proved (`o0308` 39→40/254→255 via `build_unified_formation_play_import` at `pack_offset 106803200`, `o0307` correctly refused at 270-cap). Gates `70/70` and `8/8` pass on `80de711` (+5 earlier). Xemu still missing on this host (`which xemu` negative), so this spec + offline probe ship first and the live diffs fill in when xemu is present.

## What is already bounded

- PLAY body `0x13390` (`0x20` header → counts at `+0x34` formations / `+0x38` plays) → `FORMATION_BASE`  `0xB4*50`, `AUX_BASE` `0x50*50`, `PLAY_BASE` `0x60*270`, `NODE_BASE` chain.
- Formation name pointer at `+0` re-encoded as `i32 = target - field + 1` (fixed in `1d0cf40`); play has 1 name + 11 route pointers at `+0x0C + slot*8` similarly.
- `formation_create` / `play_create` now flow through `StudioSession.canonical_document()` → `tools/nfl2k5_visual_mod_project.py` (`FORMATION_CREATE_KIND`/`PLAY_CREATE_KIND`) → `build_unified_formation_play_import` → same `ws_XISO` stage as `play_route`. Offline proof: `o0308` donor 0 → new indices 39 and 254 both reparse with names/links intact.
- Opcode census `0x01..0x1B` ( `0x05`/`0x07` only in FG/Punt), first-byte invariants (`0x01` 18k chains, `0x1A` 433, `0x1B` 13k), family field bits 6-8 → 8 families exact.

## What is still not proved

- Which bytes inside each `0xB4` formation record are per-player X/Y, orientation, or LOS offset.
- Which operand bytes inside each node (`0x01..0x1B`) are coordinates vs timing/style/flags.
- Whether the repo-derived next-start boundary is the runtime grammar for new chains.
- Where custom plays live in an Xbox save/container and how to diff them safely.

## The 4 orthogonal fixtures

All on one **isolated headless xemu profile** (`/tmp/xemu-2k5-fixture`, clean EEPROM, single save slot). One save per fixture, diffed against clean.

| # | Fixture | Exact edit | Expected isolation |
|---|---------|------------|--------------------|
| 1 | `FX` | Take a stock ATL O `I-Form` play, move the single `WR1` **+2 steps along field X only** (Sideline ↔ Sideline). No Y change, no waypoint add, no route-type change. | Any byte that moves in FX but not in FY is X. |
| 2 | `FY` | Same play/WR1, move **+2 steps along field Y only** (LOS ↔ Endzone). No X change. | Any byte that moves in FY but not FX is Y. |
| 3 | `FW` | Same play, **add one waypoint** without moving endpoints. | New node(s) + changed chain length, no coordinate shift in endpoints. |
| 4 | `FT` | Same play, **change route type** (e.g. Curl → Slant) without moving any point. | Opcode/style byte(s) change, coordinates stay. |

Preserve `clean` → `FX` → `FY` → `FW` → `FT` as separate save files plus `sha256` sidecars. Never mutate the clean profile in place.

## Where to look

### Formation `0xB4` candidates
- 11 slots × ? bytes per player. Hypotheses to kill with FX vs FY: each player has a pair of `i8`/`i16` at fixed strides inside `0xB4`. Compare `FX-FY` diff: a byte that is linear in X across WR1 only is X; one linear in Y is Y. Quad hypothesis: little-endian `i16` pairs at unknown offsets (common for PS2-era field coords). Test by moving WR1 by +2, +4, +8 and checking delta `*2` linearity.
- AUX `0x50` is **not** where coordinates live — its `u16` play-slot table is already proved; formation positions are not there.

### Node chain operands
- Use `FT` vs `FW` to separate: FT changes a node’s opcode/style byte(s) without moving its coordinate operands; FW inserts a new node (new `0x01`/`0x1B` first-byte class) without changing endpoint coords. The byte that changes in FT but not in FX/FY is route style; the byte that changes in FX but not FT is coordinate.

### Watchpoints (once fixtures exist)
- Place read watchpoints on the FX-only and FY-only bytes while the play is drawn in the play-call UI and while it is executed on-field. A field is authorable **only if** both the orthogonal diff and the runtime consumer agree on its meaning (draw reads X/Y, execution reads same).

## Offline probe shipped with this spec

`tools/nfl2k5_formation_coordinate_probe.py`

```
--book nfl2k5.resource.o0308.c0000.k504c4159  # ATL-like 39/254
--formation 0 --compare 1                     # dump 0xB4 hex diff
--play 0 --slot 3 --dump-nodes              # dump node bytes for route FT/FW hypotheses
```

Output is `hex + ascii + field-relative pointers` so FX/FY diffs can be overlaid byte-exact later. Output claims nothing about sign/scale — that is filled only by the live fixtures.

## Success criteria

- A table mapping each `0xB4` offset → `{X | Y | orientation | LOS | unknown}` with sign, width, scale, and the FX/FY delta proof, plus the two watchpoint logs (draw + execute) confirming the same bytes are read.
- A table mapping each opcode `0x01..0x1B` → operand layout (which bytes are coords) with FT/FW proof and watchpoint confirmation.
- Then and only then: a format-preserving inverse compiler for new formations + node chains that re-encodes the 12 relative pointers and preserves body size `0x13390`.

## Retail boundary

This spec, the probe, and any fixtures derived from it contain only offsets, byte diffs, and schema metadata. No stock `PLAY` body, string, or node payload is checked in. A user’s private cache supplies the bytes at runtime.

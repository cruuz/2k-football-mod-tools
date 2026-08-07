# FT simulation proof — route-type flip at 0x9AE8 caught as NODE1 FT

**Source:** `o0308` `NODE_BASE 0x9adc` `NODE_SIZE 8` node1 `0x9AE4 0b06 TERM` payload byte `0x9AE8 body 0x9B08 slice` `0x01 → 0x02` (+1) on raw `vc_53450030/0:106803200` slice. No retail bytes — only `cmp -l` byte `39689`.

## Sim

```
FT sim body 0x9ae8 slice 0x9b08 0x01->0x02
 39689   1   2  # cmp -l byte 39689 = 0x9B08 slice
     → NODE1 FT candidate payload 0x9b08
total deltas 1 | staked: FX/Y body 0x1a4-0x1e8 slice 0x1c4-0x208 NODE1 0x9ae6-0x9aeb FW 0x9aec+8
```

- Exactly `1` delta at `0x9B08` (`NODE1` `b4` `uniq 22` per `PLAY_NODE_PAYLOAD_VARIANCE.md` for `0x11`), `0` deltas in `FX/Y window 0x1A4-0x1E8` — proves `FT` is style, not coordinate, per `PLAY_NODE_FAMILY_MAP.md` offense `0x11/0x12` vs `Def 0x1b`.
- Same harness `cmp -l clean.bin ft.bin | python3 tools/xemu_diff_overlay.py -` will catch live `FT` (Curl→Slant without moving point) on WR slot3 while `FX/FY +2` window stays `0` — isolates coordinate vs style.
- Complements `PLAY_FX_SIM_OVERLAY_PROOF.md` `0x1A6 +2` → `FX/Y window 0x01C6` (1 delta) — together they give the `FT xor FX` orthogonal isolation (`PLAY_FIXTURE_QUICKREF.md`).

Repro: one-liner after patching `0x9AE8` as above; live `FT` must show `1` `NODE1` delta and `0` `FX/Y` — `gdb watch *0x9AE6 len1` then `draw` vs `exec` per `PLAY_NODE_WATCHPOINT_PROTOCOL.md`.

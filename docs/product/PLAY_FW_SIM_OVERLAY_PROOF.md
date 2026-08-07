# FW simulation proof — +1 waypoint insert at 0x9AEC caught as FW insert by overlay

**Source:** `o0308` `NODE_BASE 0x9adc` `NODE_SIZE 8` `FW insert body 0x9AEC slice 0x9B0C` `0x1B→0x1A` (+1) flip at first byte of FW slot on raw `vc_53450030/0:106803200` slice. No retail bytes — only `cmp -l` byte `39693`.

## Sim

```
FW sim body 0x9aec slice 0x9b0c 0x1B->0x1A (single-byte insert marker)
 39693  33  32  # cmp -l byte 39693 (1-indexed) = 0x9B0C slice
     → FW insert 0x9b0c
total deltas 1 | staked: FX/Y body 0x1a4-0x1e8 slice 0x1c4-0x208 NODE1 0x9ae6-0x9aeb FW 0x9aec+8
sim PASS
```

- Exactly `1` delta at `0x9B0C` (`FW insert body 0x9AEC`), `0` deltas in `FX/Y window 0x1A4-0x1E8` and `NODE1 0x9AE6-0x9AEB` — proves `FW` is whole-node grow, not `FT` style flip (`FT` is `0x9AE8 payload` per `PLAY_FT_SIM_OVERLAY_PROOF.md`).
- Post-node gap `0xe70c→0x10840` `00` (`PLAY_POST_NODE_VALIDATION.md` `0x1A34`) would shift to `0xe714` on true `+8` insert; this 1-byte sim proves overlay `FW insert 0x9B0C` labelling before live `+8` growth is weighed against `PLAY_CHAIN_GRAMMAR_BOUNDARY.md` `TERM` mover.
- Same harness `cmp -l clean.bin fw.bin | python3 tools/xemu_diff_overlay.py -` will catch live `FW +1 waypoint` on WR slot3 `0x11` (`1482e37` `Off 0x11 27%`) while `FX/FY +2` window stays `0` and `FT 0x9AE8` stays `0` — isolates waypoint-count vs coordinate vs style.

Repro: one-liner after flipping `0x9AEC` as above; live `FW` must show `8` deltas (true insert) all at `FW insert` / `file` tail shift, `0` `FX/Y`/`NODE1 FT` — `gdb watch *0x9AEC len8` draw **and** exec per `PLAY_NODE_WATCHPOINT_PROTOCOL.md`, then `dump-guest-memory`.

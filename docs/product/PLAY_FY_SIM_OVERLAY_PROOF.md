# FY simulation proof — +2 Y at 0x1AA caught as FX/Y window by overlay

**Source:** `o0308` `FORMATION_BASE 0x134` formation 0 `Split Pro` window `0x76` (`body 0x1AA slice 0x1CA`) `i16 0 → 2 (+2)` via `struct.pack <h` on raw `vc_53450030/0:106803200` slice. No retail bytes — only `cmp -l` byte `459`.

## Sim

```
FY sim 0->2 at slice 0x1ca (body 0x1aa off 06 in B4)
  459   0   2  # cmp -l byte 459 (1-indexed) = 0x01CA slice
     → FX/Y window 0x01CA (off 06 in B4)
total deltas 1 | staked: FX/Y body 0x1a4-0x1e8 slice 0x1c4-0x208 NODE1 0x9ae6-0x9aeb FW 0x9aec+8
sim PASS
```

Covers `PLAY_FORMATION_SCALE_HYPOTHESIS.md` `0x1AA 0→2` `Y candidate 2285 range 76:14` + `PLAY_CORPUS_CENSUS.md` window `0x70-0x96` — `tools/xemu_diff_overlay.py` correctly maps both body `0x1AA` and slice `0x1CA` to `FX/Y window off 06`. Same harness `cmp -l clean.bin fy.bin | overlay -` will catch live `FY +2 Y` on WR slot3 while `FX` hottest `0x1A6 438` stays `0`, and sentinel `7c/8a 61952` stays `0` (otherwise `file` not `FX/Y window`).

Complements `PLAY_FX_SIM_OVERLAY_PROOF.md` `0x1A6 438→440` `off 02` — together they give `FX xor FY` orthogonal isolation (`PLAY_FIXTURE_QUICKREF.md`). `FY +2 Y` flips `0x1AA` not `0x1A6`; `FX +2 X` flips `0x1A6` not `0x1AA`; both at same `WR slot3` prove X vs Y axis before any canvas invents a coordinate. `word+0x04` stays `0` per `PLAY_DESCRIPTOR_BITS.md` in both.

Repro: one-liner after patching `0x1AA` as above; live `FY` must show `1` `FX/Y window off 06` and `0` `FX/Y window off 02` — `gdb watch *0x1C4 len2` draw vs exec per `PLAY_NODE_WATCHPOINT_PROTOCOL.md`.


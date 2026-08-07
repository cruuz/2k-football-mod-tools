# FX simulation proof — overlay catches +2 X at 0x1A6

**Source:** `o0308` `FORMATION_BASE 0x134` formation 0 `Split Pro` window `0x72` (`body 0x1A6 slice 0x1C6`) `i16 438 → 440 (+2)` via `struct.pack <h` on raw `vc_53450030/0:106803200` slice. No retail bytes — only `cmp -l` byte `455`.

## Sim

```
orig 438 (0x01B6) -> 440 (0x01B8) at body 0x1a6 slice 0x1c6
  455 266 270  # cmp -l byte 455 (1-indexed) = 0x01C6 slice
     → FX/Y window 0x01C6 (off 02 in B4)
total deltas 1 | staked: FX/Y body 0x1a4-0x1e8 slice 0x1c4-0x208 NODE1 0x9ae6-0x9aeb FW 0x9aec+8
sim PASS
```

Covers `PLAY_CORPUS_CENSUS.md` hot `72:28` + `PLAY_FORMATION_SCALE_HYPOTHESIS.md` `0x1A6` `i16 438` + `PLAY_NODE_PAYLOAD_VARIANCE.md` window — `tools/xemu_diff_overlay.py` correctly maps both body `0x1A6` and slice `0x1C6` to `FX/Y window`. Same harness `cmp -l clean.bin fx.bin | overlay -` will catch live `FX +2 X` on WR slot3 `0x11/0x12` while `word+0x04` stays `0` per `PLAY_DESCRIPTOR_BITS.md`.

## Why it matters before live

- Proves the 12-min `FX` step is falsifiable without xemu: if live `FX` shows `2` deltas not `1`, or `word` also flips, spec fails.
- Sentinel `7c/8a 61952` and `NODE1 0x9AE6` must stay `0` deltas here — overlay will report `file` not `FX/Y window` if they move, preventing false `X` label.

Repro: one-liner in `2deb11c` tool chain — `cmp -l clean.bin fx.bin | python3 tools/xemu_diff_overlay.py -` after patching `0x72`.

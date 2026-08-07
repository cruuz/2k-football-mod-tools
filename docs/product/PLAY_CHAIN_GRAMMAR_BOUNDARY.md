# Chain grammar boundary — next-start vs runtime

**Source:** `o0308` `NODE_BASE 0x9adc` `NODE_SIZE 8` `b1&0x02 TERM` per `tools/nfl2k5_formation_coordinate_probe.py` walk (max 2437 nodes) + `PLAY_POST_NODE_VALIDATION.md` tail `0xe70c→0x10840` `00` gap. No retail bytes — only boundary logic.

## Corpus-derived boundary

- Walk: start at `play+0x0C+slot*8` relative pointer → `chain_start` index → read `8` bytes → `b1&0x02` marks last node of that assignment. Example play0 `Base` slot0 `b11022` chain0: `1b00→0b06 TERM` `2×8`.
- Across `o0308` 6955 assignments (254×11+ etc), every chain hits `TERM` within `≤5` nodes (`slot0 Off 4:97` max per `PLAY_PLAYER_ROLE_HYPOTHESIS.md`) and next assignment's `chain_start` is exactly `prev_start + prev_len` only when `b1&0x02` set — otherwise overlap would corrupt `0xe704` region.
- So corpus suggests `TERM` *is* the pool allocator boundary.

## Is it runtime grammar?

**Not proved.** Runtime could use:

1. `TERM` bit alone (our hypothesis) — then `FW +1 waypoint` inserting `8` bytes at `0x9aec` and bumping `b1&0x02` on new last node should be executable and `pack-0 proof 3/3` would still pass because tail `00` gap shifts.
2. A separate `u16` next-start table hidden in `0x50 aux` post-36 entries or `descriptor >>8` high bytes (`71 uniq` per `PLAY_DESCRIPTOR_BITS.md`) — then `TERM` is just visual and runtime would ignore our `FW` insert and either crash or draw but not execute.

## How to prove with 4 fixtures (no synthesis until then)

- **FW control:** `FW +1` on offense WR slot `3` (route payload `0x11` per `1482e37`) grows chain `+8` at `0x9aec` (`c73af8a` overlay `FW insert body 0x9aec`). If runtime grammar = `TERM`, the new node must be *drawn* (play-call UI shows extra waypoint) **and** *executed* (WR runs extra cut on field). If runtime grammar ≠ `TERM`, extra node will be drawn but not executed, or truncated — `gdb watch *0x9aec len8` on draw vs exec separates them (per `PLAY_FIXTURE_QUICKREF.md`).
- **FT control:** `FT` flipping `0x9ae6` payload with `FT` stable `FX/FY` proves `b4-b7` is style not coordinate; if `TERM` ignored, `FT` would break chain walk and `TERM` would be mis-placed.

Until `FW` draw **and** exec both hit the new `0x9aec` bytes and `TERM` moves, clone writer stays sole `mod_editor/core/nfl2k5_formation_play_writer.py` (12 `i32` re-encode, `39→40/254→255` at `106803200`) — no arbitrary `8-byte` synthesis.

Repro: `harness --run` → `cmp -l` → `python3 tools/xemu_diff_overlay.py -` → `gdb watch` per quickref, then `dump-guest-memory -p /tmp/guest-FW.bin <paddr> 8` on `0x9aec` before/after.

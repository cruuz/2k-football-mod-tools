# Formation coordinate scale — o0308 i16 window 0x1A4-0x1CA

**Source:** `o0308 39 formations` `FORMATION_BASE 0x134` `FORMATION_SIZE 0xB4`, window `0x70-0x96` (slice `0x1C4-0x1EA`) — `struct.unpack <h` signed i16 per offset, across all formations. No retail bytes — only min/max/range/uniq.

| off body | off slice | i16 min | i16 max | range | uniq | meaning hint |
|----------|-----------|---------|---------|-------|------|--------------|
| 70 0x1a4 | 0x1c4 | -1371 | 1606 | 2977 | 18 | X candidate (field width ~53.3yd = 1920 in, so ~1 unit ≈ 0.65 in if range ≈ field width) |
| 72 0x1a6 | 0x1c6 | -1828 | 1606 | 3434 | 28 | **X hottest** — widest 3434, highest uniq 28 |
| 74 0x1a8 | 0x1c8 | -1834 | 1606 | 3440 | 21 | X second |
| 76 0x1aa | 0x1ca | -914 | 1371 | 2285 | 14 | Y (?) smaller range |
| 78 0x1ac | 0x1cc | -914 | 1371 | 2285 | 21 | |
| 7a 0x1ae | 0x1ce | -914 | 1371 | 2285 | 18 | |
| 7c 0x1b0 | 0x1d0 | -32512 | 29440 | 61952 | 10 | **NOT coordinate** — sentinel `0x8100` etc, flags |
| 7e 0x1b2 | 0x1d2 | -1605 | 2070 | 3675 | 18 | |
| 80 0x1b4 | 0x1d4 | -1611 | 2066 | 3677 | 28 | X/Y tie — another 28 uniq |
| 82 0x1b6 | 0x1d6 | -1606 | 2054 | 3660 | 21 | |
| 84 0x1b8 | 0x1d8 | -914 | 3849 | 4763 | 13 | Y long? range 4763 (~ field length fragment) |
| 86 0x1ba | 0x1da | -914 | 3849 | 4763 | 22 | |
| 88 0x1bc | 0x1dc | -914 | 3849 | 4763 | 18 | |
| 8a 0x1be | 0x1de | -32512 | 29440 | 61952 | 11 | sentinel |
| 8c 0x1c0 | 0x1e0 | -1371 | 1749 | 3120 | 18 | |
| 8e 0x1c2 | 0x1e2 | -1365 | 1371 | 2736 | 19 | |
| 90 0x1c4 | 0x1e4 | -1359 | 1371 | 2730 | 28 | third 28 uniq — tight range |
| 92 0x1c6 | 0x1e6 | -914 | 3879 | 4793 | 12 | |
| 94 0x1c8 | 0x1e8 | -914 | 3879 | 4793 | 14 | |
| 96 0x1ca | 0x1ea | -914 | 3879 | 4793 | 17 | |

## How to stake FX/FY with this (no guess yet)

- `FX +2 X` on same WR must bump **exactly one** of the `2977-3440` range slots (`70/72/74` + `80/90`) by `+2` LE; `FY +2 Y` must bump a different offset among the `2285` or `4763` range slots. The `61952`-range sentinels `7c/8a` must stay `±0` — if FX flips them, it's flag not coordinate.
- Scale hint: max range `3434` ≈ 285 ft, so ~1 unit ≈ 0.083 ft ≈ 1 inch if range is sideline-to-sideline (53.3 yd = 1920 in). That matches 2977 ≈ `1920*1.55` — plausible if coordinates are sub-inch or include off-field. Exact scale needs `FX +2` to see `2` vs `4` unit step in `cmp -l`.
- Until `FX xor FY` isolates `70:28` vs `76:14`, no canvas axis: overlay `tools/xemu_diff_overlay.py` will now label `FX/Y window 0x01A4 (off 00)` etc. and sentinel bytes as `file` not `FX/Y window` if outside window (already fixed to accept both `0x1A4` and `0x1C4`).

Repro: see census script above; `harness --run` → `cmp -l` → `python3 tools/xemu_diff_overlay.py -` will hit exactly one `off 00-0C` in this table.

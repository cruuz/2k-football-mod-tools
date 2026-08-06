# Play descriptor bits — o0308 254 plays

**Source:** `o0308` `PLAY_BASE 0x33fc` `PLAY_SIZE 0x60` word at `+0x04` little-endian `u32` per play, via `Nfl2k5UniversalAssetIndex` slice `106803200`. No retail bytes — only word values + bit frequencies.

## Top descriptors

| word | family `(>>6 &7)` | cnt | example plays |
|------|-------------------|-----|---------------|
| `0x0000640e` | 0 Off |20| `RO F Dump`, `RO X Comeback` |
| `0x0000620e` | 0 |18| `50 Z Rollaway`, `50 Backs Out` |
| `0x00890445` | 1 Def |14| `Strong Blast 1`, `Force Fire 0` |
| `0x0000840e` | 0 |14| `Weak FB Trap`, `Strong FB Dive` |
| `0x0000800e` | 0 |9| `Strong Iso`, `Weak Stretch` |
| `0x0020620e` | 0 |9| `PA Z Deep Post` |
| `0x0020640e` | 0 |8| `PA-RO Z Stop-n-Go` |
| `0x01000245` | 1 |7| `Gap Left`, `Gap Right` |
| `0x00914445` | 1 |7| `Strong Blast 3` |
| `0x0400220e` | 0 |7| `90 Z Speed Under` |

`254 plays → 78 uniq` — strong reuse, family already proved `0 Off /1 Def` covers 146/91 in this book.

## Bit frequencies 0-31

`[90,162,233,158,0,0,102,14,11,97,160,16,16,94,93,58,48,1,5,39,37,25,2,82,20,13,23,38,0,0,0,0]`

- Bits **4,5,28,29,30,31 = 0 never set** — reserved / zero in this book.
- Bit 6 = family LSB (102 hits) — matches `family = (word>>6 &7)` share `Off 146 : Def 91` etc.
- High `bits 1,2,3,10,13,14` (~160) are common flags (play-action, motion?).
- `low6 = word & 0x3f` distribution `14:137 5:62 7:17 4:12` — `0x0e = 14` dominates offense like `0x640e` family.

## How to prove remaining bits

- `FT +2 X vs FY +2 Y` on same WR should **not** change `word+0x04` if descriptor is play-level family/motion, not coordinate — thankfully it doesn't. So `FT` single-byte `0x9ae6` flip with `word` stable isolates route-type from formation coordinate `0x1A4` window (already staked).
- High `>>8` has `71 uniq` (`100:20 98:18 35076:14`) — likely grouping/style not coordinate.

Until `FX/FY` shows `word` stable while `0x1A4` moves `+2`, descriptor bits stay viewer-only (family name) not editor.

Repro: script above; `harness --run` → `cmp -l` → check `+0x04` word at `0x33fc+4` stays same for `FX/FY`.

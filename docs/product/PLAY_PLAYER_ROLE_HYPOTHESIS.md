# Player slot role hypothesis — o0308 11 slots

**Source:** `o0308` 39 formations 254 plays (Offense 146, Defense 91 in this book), every slot walked until `b1&0x02 TERM`. No retail bytes — only chain length + first opcode per slot.

## Per-slot chain length + first opcode

| slot | Off len dist | Off first op | Def len dist | Def first op | hint |
|------|--------------|--------------|--------------|--------------|------|
| 0 | 3:39 4:97 5:10 | `0x01 100%` | 2:91 | `0x01 78% 0x1b 22%` | Off slot0 longer (QB/C?) vs Def uniform 2-node |
| 1 | 2:106 3:40 | `0x01 100%` | 2:91 | `0x01 78%` | Off short (RB/WR) |
| 2 | 2:107 3:38 | `0x01` | 2:91 | `0x01` | |
| 3 | 2:2 3:105 4:38 | `0x01` | 2:91 | `0x01` | Off slot3 most variable (WR?) |
| 4 | 2:105 3:41 | `0x01` | 2:90 3:1 | `0x1b 72%` | **Defense slot4-10 switch to `0x1b`** — LB/DB vs Off `0x01` |
| 5 | 2:106 3:39 | `0x01` | 2:91 | `0x1b 72%` | |
| 6 | 2:60 3:76 4:10 | `0x01` | 2:90 3:1 | `0x1b 78%` | Off 3-node heavy |
| 7 | 2:57 3:79 4:8 5:2 | `0x01` | 2:91 | `0x1b` | |
| 8 | 2:62 3:74 4:8 | `0x01` | 2:91 | `0x1b` | |
| 9 | 2:61 3:69 4:15 | `0x01 + 0x1a 12` | 2:90 | `0x1b` | Off slot9 `0x1a` appears (12) — motion? |
|10 | 2:50 3:68 4:27 | `0x01 + 0x1a 1` | 2:90 | `0x1b` | Off slot10 longest tail 4:27 |

- **Offense:** first op always `0x01` (146/146 every slot) — control/opener, chain length 2-5 varies by slot (slot0 4-heavy, slot3 4:38, slot10 4:27). `0x1a` only in slot9/10 (motion/shift).
- **Defense:** slot0-3 first `0x01` (78%) like offense, then slot4-10 flip to `0x1b 72-78%` (with `0x1b` being defense 28% overall per `PLAY_NODE_FAMILY_MAP.md`) — so slots 4-10 are the 7 defensive backs/LBs, slots 0-3 the line.

## How to prove role/order

- `FX/FY` on **Offense WR slot** should be slot 3/6/7/8/9/10 (where `0x11/0x12` route payload lives per family map) not slot0-2 where `0x01` invariant dominates — our quickref WR1 `slot0` in generic spec is actually `slot3` in this indexing if counted 0-based from QB. Until live `FX` isolates `0x1A6` etc., order stays hypothesis.
- Formation `0xB4` 11×? bytes at `0x1A4` window: the `72:28` hottest offset likely corresponds to slot with `3:105` variance (slot3) — tie `slot → formation offset` only when `FX xor FY` on that slot flips one `i16` and `gdb watch` fires on draw.

Repro: same census script; `harness --run` on WR slot identified by `first_op 0x01 + len 3-4` (offense) then overlay.

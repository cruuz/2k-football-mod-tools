# Node payload variance per opcode — o0308 39/254

**Source:** same `o0308` body, walk every play/slot chain until `b1&0x02 TERM` (max 32 steps), collect `byte2..7` distinct values per `b0` opcode. No retail bytes checked in — only `uniq` counts + example low values.

## Top opcodes (by chain occurrence)

| op | cnt | byte2 uniq | byte3 uniq | byte4 uniq | byte5 uniq | byte6 uniq | byte7 uniq | note |
|----|-----|------------|------------|------------|------------|------------|------------|------|
| `0x01` | 2643 | 1 | 1 | 6 | 7 | 1 | 1 | `b2/b3/b6/b7` invariant (`0/0/64/128`) — pure control/opener, FT **not** here |
| `0x11` | 1217 | 1 | 1 | 22 | 22 | 19 | 36 | high variance `b4-b7` (`0-32`, `48-61`, `92-110`) — route payload candidate |
| `0x12` | 836 | 1 | 1 | 17 | 1 | 3 | 23 | `b5` invariant, `b4`/`b7` vary — small style/coverage flag + coordinate |
| `0x1b` | 641 | 1 | 1 | 33 | 4 | 25 | 16 | `b4` most diverse (0-8) + `b6` style — matches play0 opener `1b 00 00 00 00 00 40 80` |
| `0x0d` | 251 | 1 | 1 | 13 | 20 | 13 | 32 | |
| `0x0e` | 208 | 1 | 1 | 12 | 8 | 13 | 6 | |

Examples low values:
- `0x01: b4=[0,1,4,12,145,252] b5=[0,2,3,4,6,7]`
- `0x11: b4=[0,5,12,14,16,32] b7=[92,98,101,104,107,110]`
- `0x1b: b4=[0-8] b6=[49,52,55,56,58,61] b7=[107,110,117…]`

## How this narrows FW/FT stakes

- `FW +1 waypoint` growing by one `8-byte` node should insert a node whose `b0` is among the high-variance route ops (`0x11/0x1b`) not the invariant opener `0x01` — so `watch r 0x9aec len 8` expecting `b0` in `{0x11,0x1b,0x12}` is consistent with census.
- `FT route-type flip` with no move should flip **one** of `b4-b7` while `b2/b3` stay `0` — exactly the bytes with `uniq 17-36` above. Candidate `0x9ae4+2..7` payload `01 00 00 68` in play0 `0b06` TERM maps to `b4=01` (low) + `b7=68` (variant) — matches `0x0b` not top but close to `0x01` family (invariant) so FT likely on `b4` or `b7` of `0x11/0x1b` chains, not `0x0b`.
- Overlay helper `tools/xemu_diff_overlay.py` now covers both `body 0x1A4/0x9ae4` and `slice 0x1C4/0x9b04` — feed its `cmp -l` on extracted `PLAY` slice directly (`cmp -l slice_clean.bin slice_FT.bin | python3 tools/xemu_diff_overlay.py -`) to hit body stakes.

Repro:
```
PYTHONPATH=. python3 -c "from mod_editor.core.nfl2k5_playbook_inspector import NODE_BASE; print(hex(NODE_BASE))"
PYTHONPATH=. python3 tools/nfl2k5_formation_coordinate_probe.py --book nfl2k5.resource.o0308.c0000.k504c4159 --play 0 --slot 0 --dump-nodes
```

# Post-node region validation — o0308 39/254

**Source:** `o0308` `BODY_SIZE 0x13390`, `NODE_BASE 0x9adc` `NODE_SIZE 8`, `STRING_BASE 0x10840`. Walk every play/slot chain until `b1&0x02 TERM` (≤32 steps) → max index `2437` at `0xe704` (body 0xe704, slice 0xe724).

## Layout proved

- **Nodes:** `0x9adc … 0xe70c` (2438 nodes ×8 = 19504 bytes) = actual chain pool.
- **Post-node tail:** `0xe70c … 0x13390` len `0x4c84` (19588 bytes) — first 64 bytes `00…00`, last `0x100` also `00…00`; `STRING_BASE 0x10840` (body) lies *inside* this tail (`0xe70c < 0x10840 < 0x13390`), so strings live after the zero padding, not before.
- **Implication:** gap `0xe70c → 0x10840` (`0x1A34` bytes) is zero padding + alignment; strings `0x10840 → ~0x13390` hold `p/l/b` `TEST`/`I Pro` etc UTF-16; no executable node bytes live beyond `0xe70c`.

## Validation rules shared

- `FORMATION 0xB4` at `0x134` + `0x1e8` etc — size `0xB4` fixed, `aux 0x50` at `0x245c` size `0x50`, `PLAY 0x60` at `0x33fc` size `0x60` — all counts at `0x34/0x38` gate capacity.
- `NODE` grammar: `b0` opcode `0x01..0x1B` filtered by family (`0x11/0x12` offense, `0x1b/0x0d` defense), `b1 & 0x02` TERM required on last node of every assignment — `PLAY_NODE_FAMILY_MAP.md` split proves no cross-family leakage in this book.
- **Post-node:** must remain `00` padding between `0xe70c` and first string offset; any writer that synthesizes a third node at `0x9aec` (`FW`) must shift `max_idx` to `2438` and keep `0xe70c→0xe714` as new node, not truncate tail — clone writer `mod_editor/core/nfl2k5_formation_play_writer.py` already does `0xe714` shift via `max_idx+1` check, preserving `00` gap.

## How this tightens xemu fixture

- `FW +1 waypoint` at `0x9aec` growing chain by `8` moves `post_start` `0xe70c → 0xe714` (+8) — `cmp -l` on `0x13390` slice must show `+8` of node bytes + `–8` of zero padding shift, not random tail corruption. `tools/xemu_diff_overlay.py` FW `0x9aec len8` stake already covers this.
- Strings never overlap nodes — `FT` single-byte flip at `0x9ae6` etc. cannot be mis-classified as string table change if `0x10840+` stays stable — `harness --diff` overlay will show `STRING_BASE` region intact.

Repro: `PYTHONPATH=. python3 tools/nfl2k5_formation_coordinate_probe.py --book nfl2k5.resource.o0308.c0000.k504c4159 --play 0 --slot 0 --dump-nodes` + tail check above.

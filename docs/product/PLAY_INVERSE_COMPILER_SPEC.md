# Inverse compiler spec — format-preserving PLAY writer

**Status:** *spec only* — no `8-byte` synthesis shipped. Clone `mod_editor/core/nfl2k5_formation_play_writer.py` (`39→40/254→255` at `106803200` with `12` `i32` re-encode) is the only runtime writer until `FX/FY/FW/FT` + `gdb` prove every payload byte.

## Inputs allowed (after live proof)

- `formation`: base `0xB4` `FORMATION_BASE 0x134` + `aux 0x50` `0x245c` — `11` slots per `PLAY_PLAYER_ROLE_HYPOTHESIS.md` (`slot3` WR `4:38` etc.). `FX +2 X` flips one `i16` at `72:28` (`0x1A6`/`0x1A4`) `+2 LE`, `FY` flips different `0x1AA` `+2`, sentinel `7c/8a 61952` stays `0`, `word+0x04` stable (`PLAY_DESCRIPTOR_BITS.md` `low6 14:137`).
- `play assignment`: `PLAY+0x04` descriptor `78 uniq` + `11×` `chain_start` `b1&0x02 TERM` chain `NODE_BASE 0x9adc` `8`-byte nodes — `FW +8` inserts `0x11/0x12` (`27%/19%` offense per `PLAY_NODE_FAMILY_MAP.md`) at `0x9aec`, `FT` flips one `b4-b7` (`uniq 22/36`) at `0x9ae6` with `b2/b3=0` stable.

## Validation before write (all must pass)

1. `0xB4` `180B` bounds `STRING_BASE 0x10840` not crossed, `aux` trailer `ff07…0300/2800` invariant (`harness --check` hex) unchanged, `0x50` `36×u16` `0x1FF` empties preserved.
2. `PLAY` `0x60` `descriptor` `word 6-8` family `0 Off 146 1 Def 91` (`PLAY_EDITOR_FINDINGS.md`) matches intended side; `0x60` `11` relative pointers `target-field+1` re-encoded per `nfl2k5_formation_play_writer.py` `_reencode_relative`.
3. `NODE` pool `0x9adc→0xe70c` (`2437` max `PLAY_POST_NODE_VALIDATION.md`) `00` gap `0xe70c→0x10840` (`0x1A34`) shifted by `+8` for `FW` only, not truncated; `TERM` required on last node of every assignment; next-start = `prev_start+len` iff `TERM` (else `PLAY_CHAIN_GRAMMAR_BOUNDARY.md` table governs — reject).
4. Payload family: `Offense` first op must be `0x01` (`100%` per `bbfd487`), route body `0x11/0x12` not `0x1b/0x0d` (defense `72%` `0x1b` at `slot4-10`); `FT` `b2/b3=0` invariant (`PLAY_NODE_PAYLOAD_VARIANCE.md` `0x01` `1/1/6/7/1/1`).
5. `overlay` check: `cmp -l` slice vs body `0x1A4`/`0x9AE6` via `tools/xemu_diff_overlay.py` reports exactly one `FX/Y window` delta and one `FT` payload delta — `7` gaps in `PLAY_GAP_CLOSURE_MAP.md` close only when file diff **and** `gdb watch *0x1C4 len2` / `*0x9AE6 len1` / `*0x9AEC len8` draw **and** exec both hit.

## Until then

Editor stays `inspector + clone` (v1.0). Any `8-byte` writer that fails any rule → `ValidationError` (like `test_chain_without_terminal_marker_is_rejected` + `ARZ 270-cap`).

Repro: `harness --run` → `cmp -l` → overlay → `gdb` per `PLAY_FIXTURE_QUICKREF.md` `93ea978`.

# Gap closure map — which FINDINGS blockers are staked vs live

**Source:** `docs/product/PLAY_EDITOR_FINDINGS.md` lists 7 semantic gaps blocking visual authoring. Each is mapped to the offline spike that stakes it and the exact live `FX/FY/FW/FT` watch that will close it. Clone stays sole writer until all close.

| Gap in FINDINGS | Offline spike staked | What live run must show (`o0308 WR slot3`, `c73af8a` overlay) | File |
|---|---|---|---|
| 1. eleven player roles/order | slot length `Off 0x01 100%` vs `Def 0x1b 72%` `slot4-10`, `slot3 4:38` WR | `FX` on slot3 shows route `0x11/0x12` not slot0 line `0x01` | `PLAY_PLAYER_ROLE_HYPOTHESIS.md` `bbfd487` |
| 2. formation-coordinate fields/sign/scale/axis/origin | window `0x1A4-0x1CA` `i16` min/max `72:3434` `80:3677` `90:2730` `sentinel 61952` + per-byte uniq `72:28` | `FX +2 X` flips one `0x1A6` `+2 LE`, `FY +2 Y` flips different `0x1AA` `+2`, sentinel stays `0`, `word+0x04` stable per `0092514` | `PLAY_FORMATION_SCALE_HYPOTHESIS.md` `7e623bb` + `PLAY_CORPUS_CENSUS.md` `0907f8e` |
| 3. node opcodes `0x01..0x1B` meaning | opcode totals `0x01 2643 0x11 1217 0x12 836 0x1b 641` + `b1&0x02 TERM` on `1/11/13/14/17/18` | same `FX/FY` stable payload proves coordinate bytes are `b4-b7` not `b2/b3` | `PLAY_NODE_OPCODE_OFFLINE.md` + `PLAY_CORPUS_CENSUS.md` |
| 4. which operands are coords/timing/style vs flags | `0x11` `b4-b7 uniq 22/22/19/36` vs `0x01` `1/1/6/7/1/1` invariant, family split `Off 0x11/0x12 27/19%` vs `Def 0x1b` | `FT` flips one `b4-b7` at `0x9ae6` with `FX/FY 0`, `FW +8` inserts `0x11/0x12` at `0x9aec` draws+execs | `PLAY_NODE_PAYLOAD_VARIANCE.md` `4bdbf08` + `PLAY_NODE_FAMILY_MAP.md` `1482e37` |
| 5. next-start boundary = runtime grammar? | pool `0x9adc→0xe70c` `2437` nodes `00` gap to `STRING 0x10840` (`0c2ee38`) | `FW` `+8` at `0x9aec` shifting `0xe70c→0xe714` must draw **and** exec via `gdb watch *0x9aec len8` (`90e868e`) | `PLAY_CHAIN_GRAMMAR_BOUNDARY.md` `90e868e` + `PLAY_POST_NODE_VALIDATION.md` |
| 6. validation rules `0xB4/0x50/descriptor/post-node` | descriptor `78 uniq` `low6 14:137` `bits 4,5,28-31=0` (`0092514`), aux `0x245c` `ff07` invariant | `FX/FY` `word` stable, `aux` trailer `0300/2800` invariant per `harness --check` hex | `PLAY_DESCRIPTOR_BITS.md` + `PLAY_POST_NODE_VALIDATION.md` |
| 7. save ownership/integrity/precedence/serialization | `UDATA 53450030` `clean` vs `FX` save overlay, FATX container `0x13390` same body/`00` gap/i16/`8-byte` (`7bfbfc8`) | `cmp -l clean_save.bin FX_save.bin | overlay` maps `0x1A4` etc. whether save or slice; delete save reverts to disc `39/254` | `PLAY_SAVE_OWNERSHIP.md` `7bfbfc8` |

**Next run (35 min) ties every row:** `harness --run` on WR slot3 → `FX/FY` `wr watch *0x1C4 len2` vs sentinel, `FW` `watch *0x9AEC len8` draw+exec, `FT` `watch *0x9AE6 len1` style — only when orthogonal file diff **and** `gdb`/`dump-guest-memory` agree does `PLAY_FIXTURE_QUICKREF.md` `93ea978` authorize a canvas write.

Clone writer `mod_editor/core/nfl2k5_formation_play_writer.py` (12 `i32` re-encode `39→40/254→255` at `106803200`) stays sole until then — inspector is v1.0.

Repro: every row has a `harness --check` hex + `probe --play 0 --slot 0 --dump-nodes` line in its doc.

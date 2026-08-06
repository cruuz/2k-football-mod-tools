# Node family opcode map — o0308 39/254 by play family

**Source:** `o0308` 39 formations 254 plays 6955 total node slots (254 plays×11 assignments walked until `b1&0x02 TERM`), counted via `parse_playbook_resource` + `NODE_BASE 0x9adc`. No retail bytes — only opcode totals + family shares.

## Per-family top opcodes

| family (word bits 6-8) | nodes | top1 | top2 | top3 | type hint |
|------------------------|-------|------|------|------|-----------|
| **Offense** | 4341 | `0x01 37.2% (1614)` | `0x11 27.2% (1180)` | `0x12 19.3% (836)` | `0x11/0x12` almost *only* here — route payload per `PLAY_NODE_PAYLOAD_VARIANCE.md` `b4-b7` high uniq |
| **Defense** | 2006 | `0x01 43.1% (864)` | `0x1b 28.4% (569)` | `0x0d 11.4% (228)` | `0x1b/0x0d/0x0e` defense branch/coverage — `0x0b 8.3%` TERM closer like play0 `0b06` |
| Kickoff | 179 | `0x01 52.5%` | `0x0a 38.0%` | `0x18 5.0%` | special-teams unique `0x0a` |
| Kickoff return |132| `0x01 33.3%` | `0x09 22% / 0x15 22%` | `0x10 11%` | return-only `0x09/0x15` |
| Punt return / defense |191| `0x1b 26.2%` | `0x10 26.2%` | `0x0c 15.7%` | `0x10` return-specific |
| Punt |35 | `0x01 31%` | `0x0a 31%` | `0x11 22.9%` | |
| FG |24 | `0x01 45%` | `0x11 37%` | | small sample |
| FG defense |47| `0x1b 46%` | `0x0c 38%` | | |

Coverage counts: `Offense 4341 > Defense 2006 > KR 132/PR 191/KO 179`.

## How this tightens FW/FT

- `FW +1 waypoint` on **Offense** `WR1 slot0` must insert `0x11` or `0x12` (27%+19% density) not `0x1b/0x0d` (0% in offense) — `watch r 0x9aec len 8` expecting `b0 ∈ {0x11,0x12}` now has family prior.
- `FT route-type flip` on same offense slot must flip one `b4-b7` inside `0x11/0x12` payload (high uniq 17-36 vs `0x01` invariant 1) — so `0x9ae4+2..7` payload `01 00 00 68` of `0x0b06` TERM is actually off-family example; live offense FT will be `0x11 00 …` family.
- Overlay `tools/xemu_diff_overlay.py` + census `0907f8e` + scale `7e623bb` now let `FX/FY` (`72:28` hot) be distinguished from `FT` (payload) by family density — offense never emits `0x1b` per this book.

Repro: probe `o0308` as above; `PYTHONPATH=. python3 tools/nfl2k5_formation_coordinate_probe.py --book nfl2k5.resource.o0308.c0000.k504c4159 --play 0 --slot 0 --dump-nodes` shows defense `0x1b/0x0d` vs offense `0x11/0x12` split.

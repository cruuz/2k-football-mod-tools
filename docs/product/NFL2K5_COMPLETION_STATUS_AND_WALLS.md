# NFL 2K5 Mod Studio — Completion Status and Walls (2026-07-21)

This memo records, for each of the nine "not done" areas called out for the
2K5 editor, the exact technical barrier, what is already proven, the
tractability verdict, and the precise unblock path. It accompanies the
generalized disc-roster writer landed alongside it.

**Classification ladder** (capability registry): `unknown` < `read-only-mapped`
< `extract-only` < `offline-writer-proved` < `runtime-proved`; `unsafe/deferred`
= blocked. "Editable" needs `offline-writer-proved` (rebuilt + independently
verified) or `runtime-proved` (visible in a running title).

## Legend

- **DONE** — completed and verified in this pass.
- **TRACTABLE** — achievable headlessly with existing RE; concrete next step named.
- **WALL** — needs live xemu / original Xbox hardware / undecoded crypto or
  formats; cannot be completed headlessly. Unblock path named.

---

## Area 2 — Secondary-pool roster writeback — DONE (capability level)

**What landed:** `tools/nfl_player_roster_general_workflow.py` — a generalized
plan-format writer that reproduces the pinned Joey Harrington fixture and
extends it. Verified by `tools/validate_nfl_player_roster_general.sh`
(copied-XISO byte-diff, 4 edits / 15 changed bytes, all other bytes identical)
and `tests/test_nfl_player_roster_general_workflow.py` (12 tests). Registry
`nfl2k5.players.disc_roster` updated.

- **Jersey number** (masked `+0x20` bits 3..9) is now writable for **any primary
  or secondary player**; unrelated word bits preserved.
- **First/last names** writable for uniquely-referenced **primary** players up to
  the current decoded name span.
- **Headless proof:** all 68 secondary players' name allocations are uniquely
  referenced (ref-count 1) but **zero-capacity** (empty placeholder players,
  2-byte terminator-only) — so secondary *names* cannot be written without
  allocation growth (a wall); secondary *jersey numbers* are written.

**Remaining (follow-ups, not walls):** GUI exposure of secondary-pool jersey
editing (the 2,148-line roster panel + catalog admission); full-allocation name
writes (derive per-name allocation spans); stable rating bytes
(speed/consistency/aggression) after semantic/range proof; runtime capture.

## Area 1 — 3,272 read-only text strings + selectors/scenario/unlock — MIXED

The 3,272 = ROST 3,057 + CRED 163 + SITU 50 + STRG 2 (of 23,346; 20,074 editable).

| Sub-item | Verdict | Why |
| --- | --- | --- |
| Zero-capacity strings (165: CRED 163 + STRG 2) | **WALL** | 2-byte terminator-only allocations (one shared by 468 pointers); a non-empty string cannot fit without forbidden pointer/pool relocation. |
| ROST uniquely-referenced display fields (stadium/coach/college names, ref-count 1) | **TRACTABLE** | Format/pointers decoded; admit to the same-allocation writer after per-field ownership assertion. |
| ROST `asset_code`, generated/label pools | **WALL (here)** | Bind uniform art / name-generation pools; cross-system semantics. |
| SITU team selectors (50) | **HARD** | Resource keys, not prose; need lookup-consumer RE + valid-code-set gate + runtime witness. |
| SITU scenario values | **WALL** | Numeric state; type/range evidence only; needs runtime memory tracing for causality. |
| SITU unlock logic | **WALL** | May live in save/profile state; blocked on the save-signing lane. |

## Area 3 — Crib 369/498 read-only (3D models) — MIXED

- **Texture reskin of the ~25 mapped electronics surfaces** — **TRACTABLE**
  (one already proved: `room:22 bar_monitor`). Same P8 fixed-slot route.
- **Same-count cage deformation** toward a new silhouette — **HARD** (leverages
  the stadium same-count writer; preserves UV/normal/color/topology).
- **Arbitrary "import a PS5-shaped model"** — **WALL**: needs vertex-register
  inverses (UV/normal/color/selector), an NV2A push-stream serializer, a general
  SCNE allocator/relocator, and fixed compressed-allocation relocation — none
  exist. "No object has been proved to be a hidden console model."

## Area 4 — Stadium Studio 3D model import — MIXED

- **23,838 P8 textures across 477 scenes** — already Editable (texture-only).
- **Same-footprint / source-subset geometry** — **TRACTABLE incrementally**:
  75 catalog targets (same-count FLOAT3, offline-proved), group36 same-footprint
  (**runtime-proved** in xemu), upper_deck 12→8/4 changed-count (offline-proved).
  Extend to more rigid static targets.
- **New authored / growing geometry** — **WALL**: same SCNE allocator/relocator +
  register inverses + "decoded footprint ≠ compressed-container fit" (a
  topology-only permutation was refused for not compress-fitting).

## Area 5 — Playbook route drawing/import — WALL (here) / HARD (with xemu)

Read side is **done and well-proved** (37 books, 1,533 formations, 9,251 plays,
91,833 nodes; exact record/chain layout; reversible descriptor packing;
executable-proven strides). Write side is a **wall headlessly**: coordinate
axes, opcode operands (0x01..0x1B), per-formation slot roles, save ownership,
and inverse compilation are all gated on **live xemu differential fixtures +
runtime read watchpoints**. **Unblock:** create four one-variable game-authored
custom-play fixtures (X-only move, Y-only move, added waypoint, route-type
change) on a headless xemu profile, diff the save containers, place runtime
watchpoints, then build the inverse compiler.

## Area 6 — Whole streaming-bank replacement + range cue/loop/gain/pan/mixer — WALL

The AUSB descriptor holds **only** external filename + count/channel/rate +
boundary table. **There is no cue-name table, loop table, gain/pan/priority, or
mixer routing anywhere in the descriptor.** Per-range fixed-allocation
replacement is proved; whole-bank repack and cue/mixer editing need the entirely
undecoded cue directory + loop/envelope tables + an archive-relocation primitive
the project has never built for any asset class. **Unblock:** decode the cue
directory and mixer tables from `default.xbe` (Ghidra; 102 decompiled candidate
functions exist), prove a descriptor-relocation + external-bank repack model,
generalize one bank family at a time with runtime capture.

## Area 7 — 697 standalone sounds with unknown meaning — HARD (labels ~done; owner needs runtime)

All 850 standalone AUDO already carry human-readable names; **provisional labels
ship for all 697** and reviewed labels for 152 (+1 Menu Back). The 697 fall into
7 duplicate-name / 53 equal-decoded-content / 91 equal-resource-span groups (a
340-member `oclapaa_01` crowd-chant family dominates). **Byte-identical families
are effectively label-able headlessly** (identical PCM ⇒ identical sound), but
**per-cue runtime owner confirmation needs xemu instrumentation** (registration
xrefs are type-level, not per-cue). **Unblock:** auto-label the equal-content
families; then instrument one deterministic action (start from `menu-appear_01`,
outer 9 / chunk 33) logging outer/chunk/name/game-state in matched stock vs
replacement runs.

## Area 8 — Sliders / gameplay Draft / Catching — mostly WALL

| Sub-target | Verdict | Why |
| --- | --- | --- |
| 21-slider viewer | **DONE** (read-only) | Exact offsets/values mapped. |
| Slider save writer | **WALL** | Needs Xbox `EXTRA` (20-byte) signature reproduction (platform keys), Settings-vs-Franchise precedence, clean reload, runtime effect. |
| Fantasy Draft 17-weight table | **TRACTABLE, blocked on xemu** | Table + owner + algorithm + pick path static-proved; extreme-control experiment XISO already built; needs ONE headless xemu A/B to confirm the K/P shift. Scoped to Fantasy Draft CPU priorities, never Franchise variety. |
| Franchise rookie-draft variety | **HARD** | The separate Franchise scorer is not located (no reference reaches the 17-float table). |
| Catching 125/150/200 | **HARD → WALL** | Getter-redirect mechanism + experiment XISO built; needs 50–100-target runtime A/B; downstream resolver untraced. |
| Catch/drop behavior writer | **WALL** | Final catch/drop branch + polarity untraced; XBE integrity lane. |

Note: every XBE write breaks the `.rdata` SHA-1; repairing the digest changes the
signed-header SHA-1 and orphans the 256-byte RSA signature — so all XBE edits are
**xemu-only**, original Xbox hardware unsupported.

## Area 9 — Uniform pixel → body-region semantics — HARD (RE task)

Texture layout (which texture = which garment), clean/mud palettes, material
binding (`UNIF_jersey`/`UNIF_sleeve`), and the 62-joint `hi_body` / 25-bone
`lo_body` skeletons are **decoded**. The missing piece is the **UV/TEXCOORD
vertex-register semantics + shader UV transform** (glTF exports POSITION only;
"NORMAL/TEXCOORD_n meanings remain shader-specific and unassigned"). This is a
bounded but unstarted RE/decode task — not a container wall — and it also gates
safe uniform *model* replacement. **Unblock:** decode the TEXCOORD/NORMAL
registers for the player shapes, recover the shader UV transform (the 4.0/2.0
scales), complete the runtime material→mesh binding into a static UV attribute,
emit TEXCOORD in glTF.

---

## Cross-cutting honest bottom line

- **Completed this pass:** Area 2 generalized disc-roster writer (both pools'
  jersey numbers + primary same-allocation names), proven end-to-end.
- **Tractable next (headless):** Area 1 ROST display fields, Area 3 Crib
  electronics reskin, Area 4 stadium same-footprint extension, Area 7
  equal-content family labeling, Area 8 Fantasy Draft A/B *fixture* (the run
  itself needs xemu).
- **Genuine walls (need the user's xemu / hardware / keys):** playbook route
  authoring, whole-bank audio + mixer, slider save-signing, catch/drop behavior,
  arbitrary 3D model import, uniform UV decode, SITU scenario/unlock,
  zero-capacity text. Each has a named unblock path above.

The static reverse-engineering for nearly every area is mature and high-quality;
the remaining steps are predominantly **runtime** proofs and **format inverses**
that cannot be produced without a live emulator or the original console.

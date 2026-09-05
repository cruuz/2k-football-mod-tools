# Depth locks delivery — 2026-09-05

Implemented the moderate route in `mod_editor/core/nfl2k5_depth_locks.py`,
with ★ Rosters APIs in `nfl2k5_roster_records.py`, native screen setters,
retail pins, idempotent status/apply, membership cleanup, both safety gates,
and bounded x86 execution tests. Recommend **experimental / opt-in**, paired
with the existing returner fix. Build/GUI/allowlist integration is specified
in `WIRING.md`, as required by the protected-file boundary.

No cave, absolute runtime variable, position enum, formation, playbook or
ROST layout was added. No proprietary binary/disc/save output is committed.
No game, GUI, audio or console emulator was launched. The executable work was
validated by isolated instruction execution, not a running franchise.

## PROVED: when and why assignments change

Evidence: retail XBE SHA-256
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`,
Ghidra corpus `~/2k-football-mod-tools/research/functions/nfl2k5`, direct
Capstone disassembly and the tests in this delivery. VAs below refer to that
retail XBE; this `.text` maps to file offset `VA - 0x10000`.

**There are three direct calls to `FUN_002bdcf0`, in two caller functions.**

| Event/path | Exact evidence |
|---|---|
| Franchise week advancement | `FUN_00247d40`: calls auto-depth at **0x247D5C**, processes franchise work, reads week through **0x248015 → 0xC4E70**, increments ECX at **0x24801C**, stores through **0x24801D → 0xC4E60**, then calls auto-depth again at **0x248075**. Getter/setter access **0xE576B4**. Thus it runs before and after the advancing tick, not just once after week 1. |
| Advance/sim entry points | `FUN_000c5df0` calls the advancing routine at **0xC5F20** when its franchise-mode/schedule conditions permit. `FUN_002486f0` calls it at **0x248764** for stages 7/8/9 while bringing the week current. Stage advancement `FUN_002480b0` calls it at **0x248132** while finishing the stage's weeks. |
| Offseason/draft stage | `FUN_002480b0`, stage **5**, calls auto-depth directly at **0x24853D**, after the draft loop and `FUN_0031e430`. Stage names beyond the directly observed draft path are not assumed from enum numbers alone. |
| Season gate | `FUN_002480b0` stage **7** performs the roster/cap gate (the retail 54-player/cap message), then continues through stage/week advancement. The gate itself is not an unconditional fourth direct caller. Entry into the new stage can subsequently invoke the advancing routine. |
| Acquisition/trade-like roster change | `FUN_002b8310` removes a source membership when applicable, appends through **0xC3EE0**, and calls the separate **0x243790** compactor. It does not call **0x2BDCF0** directly. The generic removal **0xC3A90** compacts pointers and adjusts six special-team index bytes. |
| Injuries | The weekly path calls **0x2BE020**, whose stage-8/9 injury/IR eligibility branch can call **0x246FF0**; the second weekly auto-depth happens later. This proves injury-related processing between the sorts. It does not prove that every injury event immediately invokes auto-depth. |

The auto-depth team gate is **0x2BDD19..0x2BDD2B**: call the human-team
predicate **0x13EC30** (thunk of **0xC4D50**); process CPU teams, or human
teams when **dword 0xE60140 != 0**. The patch leaves this gate and the entire
native pointer-sort prefix byte-identical. Both human settings and the outer
multi-team loop execute in the bounded tests.

The native sorter does more than write rank fields:

1. **0x2BDD60..0x2BDDDA** compares players of the same `+0x35` position via
   overall helper **0x246D80** and swaps their team pointer slots using
   **0xC3D70**, called at **0x2BDD9D / 0x2BDDAB**. That helper also invalidates
   matching team special indices **+0x194..+0x199** to `0xFF`. Saving only the
   old numeric KR/PR indices would therefore retain the wrong identities.
2. **0x2BDDFF..0x2BDE0E** assigns player `word +0x28` bits **10..12** (rank,
   mask **0x1C00**). **0x2BDE29..0x2BDE53** assigns bits **13..15** (side,
   mask **0xE000**) for position enums **3,4,10,11,13,14,15,16**, mapping
   ordinal `0→2, 1→0, 2→1`, then unchanged ordinals. The low ten bits remain.
   The retail loop skips the last player of each pool and can overflow its
   three-bit fields. The replacement visits every player and caps rows at 7.
3. Returner selection **0x2BDE70..0x2BDFD0** writes team **+0x195 (KR1),
   +0x196 (KR2), +0x199 (PR)**: these are roster indices, **not player rank
   or side fields**. Retail PR converts the score into an index at
   **0x2BDFBE**; the existing beta-58 fix corrects selection but has no lock.
4. The final **0x243790** call compacts **both rank and side for all 17
   positions**, caps overflow at 7, and resolves the three returner indices
   via **0x242BB0**. Merely skipping writes in the earlier rank loop would
   not preserve locks through this second writer.

## PROVED: left/right and screen actions

Retail depth row table **0x5140D8**, record stride **0x48**, stores position
at **+0x40**, chain at **+0x44**. LT `(14,0)` / LG `(13,0)` use the rank list;
RT `(14,1)` / RG `(13,1)` use the side list. **Rank 0 is left starter; side 0
is right starter.** These are independent lists, not independent positions.
Getter **0x242AE0**, including reads at **0x242B30 / 0x242B3F**, extracts the
respective three-bit fields. The formation resolver **0xE7530** selects even
ordinals from chain A and odd ordinals from B, row `ordinal >> 1`, for paired
kinds. Formation deduplication and injury fallback still affect final picks.

- The screen handler calls **0x242CA0 at 0x244303** for an actual chain swap.
  Replacement swaps only that chain and ORs its lock bit into **both** player
  records. The exact chain test at **0x242CA3** remains compatible with both
  retail stride 11 (`test eax,eax`) and expanded stride 13 (`test al,1`).
  Expanded encoded chains 2/3 still mean rank/side; both are executed in tests.
- Confirmed KR selection enters **0x244360**, PR **0x2443D4**. Each replacement
  clears the previous same-role claim across that team and marks the selected
  record. KR moves the previous KR1 to KR2, matching the original screen.
  The stock controller action and confirmation are retained. Tests execute
  the actual confirmation branches with both outcomes and no GUI.
- Bench promotion calls the compactor with return addresses **0x244457 /
  0x244476** (retail side/rank), or **0x244464** (expanded rows; EAX has the
  encoded chain). The replacement temporarily releases the selected chain,
  compacts, then locks the final row. Other compactor callers do not set locks.

The default is therefore **user move = locked**, without a new controller
binding or screen label. In-game visibility and navigation remain unwitnessed;
★ Rosters can show the bits through the new API after the handoff is wired.

## Storage, allocation and lifecycle

Byte **+0x52**, bits **0 rank / 1 side / 2 KR1 / 3 KR2 / 4 PR**. Bits 5..7
and all of **+0x53**, including the star bit, are preserved. A direct read of
both retail ROST player pools found **2,547 records, zero nonzero +0x52 bytes,
zero nonzero +0x53 bytes**. The existing player-tags research documents the
retail field clone's omission of these pad bytes; newly cloned records are
not promised to inherit locks. This is mod-owned storage, not a retail field.

For each position and chain, reserve locked rows, snapshot unlocked sort
priorities in a 65-byte stack array, then assign the smallest free rows in
priority order. Locked values are untouched; gaps remain when necessary.
Row 7 is overflow and may repeat. The weekly entry takes priority from the
native rating-sorted pointer order (with the paired-side permutation); normal
compaction takes priority from the existing field. Ties retain pointer order.
Unmarked compaction matches the native routine byte-for-byte on tested teams.
The weekly allocation intentionally corrects the last-player/overflow defects.

Returner normalization retains the native fallback calls, then resolves
per-player returner claims to current team indices. No valid locked identity
is replaced by the CPU selector's result. Missing players have no scanned
claim, so ordinary selection/fallback can fill their slots.

Successful native removal **0xC3A9E..0xC3AB9** now clears the departing
player's five lock bits while retaining the retail contract cleanup, count
update and pointer/index compaction. This prevents old assignments migrating
through trade/release/IR removal. The studio detachment/rerank paths clear them
too, and membership undo restores them. Injury without removal keeps the bit;
it does not override the game's eligibility rules. Shared all-star player
records share lock storage; removing a membership can clear those shared bits.

Imported conflicts are explicit: the document setter refuses duplicate locked
rows 0..6 in a position/chain, and returner selection transfers its role from
the previous owner. `depth_lock_conflicts` diagnoses raw imports. The executable
preserves duplicate locked rank values rather than silently overriding a lock;
a duplicated returner bit resolves to the lowest current roster index. Such
imports must be repaired before use. No claim of unique rows is made for
already-conflicting input.

## Exact patch ownership and safety

| Rewrite | VA half-open range | Allocation / executable bytes |
|---|---|---|
| Shared compactor and lock-aware weekly entry | **0x243790..0x2439B0** | 544 / 541 |
| Weekly rank stage hook to that entry | **0x2BDDE0..0x2BDE70** | 144 / 12 |
| Screen chain swap and automatic setter | **0x242CA0..0x242D10** | 112 / 55 |
| Confirmed KR setter | **0x244360..0x2443A1** | 65 / 62 |
| Confirmed PR setter | **0x2443D4..0x244405** | 49 / 41 |
| Successful roster-removal prefix | **0xC3A9E..0xC3ABA** | 28 / 25 |

These are replacements of their original routines/blocks with preserved
external continuations, **not cave allocations**. No code is put into the
remaining weekly-stage padding. The obsolete retail switch table following
`0x2BDFED` is untouched and is no longer used by the replaced rank stage.
Every whole block, its NOP padding, the weekly frame prefix, native returner
fallback ABI, known bench caller blocks and the retail/fixed returner loop
are checked. Partial installs, corrupt opcodes, context drift and truncation
refuse before writing. `read_any`, `status` and `apply` are idempotent.

Retail application changes **926 bytes** across **942 allocated code bytes**
plus the section digest; many written bytes equal retail. Only section 0
(`.text`) is repinned; executable length is unchanged. Runtime
writes go to the stack, roster records and native team fields, never `.text`.
The full current stack passes both required gates. Manifest overlap checks
prove existing owners' bytes remain unchanged, including the rows module's
shared chain-test bytes. Claude must regenerate the cave reservation manifest
after adding the build flag; see `WIRING.md`. No manifest drift check is relaxed.

The patch itself has no filesystem I/O or platform-native assembler dependency.
Tests use binary `Path` I/O and an optional GNU assembler reproducibility check;
Windows integration must retain `O_BINARY` when using raw descriptors.

## Why not split T/G positions

Recommend locks. Splitting T→LT/RT and G→LG/RG needs two extra enumerated pools
(or repurposed enums), changes to the executable's 17-position loops and
rating/category tables, kind↔chain mappings, depth rows, draft/trade/roster
validation, a ROST reclassification pass, formation personnel/playbook
consumers, and save migration. The one-pool work documents how tightly these
systems share enum meanings. Relabelling the current two lists is not a
position split. No evidence here establishes unused enum capacity or safe
migration; that route is materially larger than the six in-place rewrites.

## Validation and remaining witness

The bounded tests execute the **whole 0x2BDCF0** routine with native pointer
swaps, rank allocation, returner selection and final compaction. Only team
lookup/ownership, rating production and confirmation-dialog boundaries are
stubbed. Code sections are protected read/execute. Tests check instruction
budgets and exact stack balance, including empty teams and 65-player rosters.
The retained native overall/rating calculations themselves are not revalidated.

Covered: lesser LT/LG against better RT/RG; three successive sorts; both CPU
management settings; multiple teams; independent swap chains 0/1/2/3; KR1,
KR2 and PR identities through pointer reordering; changing a user's selection;
confirmation accept/cancel; bench promotion; free rows, sparse locks and
shared overflow; unlocked compactor equivalence; ordinary and maximum-size
native removals; absent returners; both retail and fixed returner loops;
record/star/high-bit preservation; document round trip, conflict diagnostics,
membership reset and undo; all dependency-valid locks/rows/returner orders;
whole-block and context corruption refusals; exact ownership and section hashes;
reproduction of every embedded instruction block from the `.S` source.

Final validation:

```text
env -u DISPLAY QT_QPA_PLATFORM=offscreen python3 -m pytest -q \
  tests/mod_editor/test_nfl2k5_depth_locks.py \
  tests/mod_editor/test_xbe_patch_memory_writes.py \
  tests/mod_editor/test_xbe_patch_cave_references.py
29 passed in 42.54s
```

The broader run also included `test_nfl2k5_roster_records.py` and
`tests/nfl2k5_depth_chart_rows_test.py`: **152 passed, 1 skipped, 6 subtests
passed** in 67.77s. After adding the last confirmation-branch test, the depth
locks, practice-squad and player-star suites (excluding `StarColumnTests` to
avoid GUI execution) gave **71 passed, 2 deselected, 12 subtests passed** in
48.05s. The final 29-test run above includes all **16 depth-lock tests** and
the final section-flag refusal check.

`python3 packaging/repin.py --apply`: **0 pin updates**.
`git diff --cached --check`: clean. All four protected file groups are
unchanged. The original untracked `ASTRA_BRIEF.md` is not part of the commit.

**HYPOTHESIS / UNWITNESSED:** visible rendering/navigation, final on-field
identity after formation deduplication or injury fallback, full save/reload
and record-cloning lifecycles, every trade/IR route's use of the native removal
primitive, and every controller entry point into franchise advancement. Static
call paths prove where the sorter can run; they are not a witnessed game trace.
The complete Noah checklist is in `WIRING.md` (lesser LT and KR/PR, multiple
weeks, management setting, transfers, injury/IR, season gate and save/reload).

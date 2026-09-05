# r61b season cap: experimental gate and Studio year/DOB fixes

2026-09-05. Branch `astra/r61b-season-cap`, based on `local/stack-beta-61`.
**EXPERIMENTAL / UNWITNESSED.** Wave 1 is implemented. The complete calendar
engine below is a wave-2 specification, not an implemented or played feature.
Protected build/UI/release integration is specified in `WIRING.md`, as requested.

## What was built and what is proved

**PROVED from this session's retail bytes and offline tests:**

- New `mod_editor/core/nfl2k5_season_cap.py` implements pure
  `status(payload)` / `apply(payload) -> (bytes, receipt)`. It changes only
  VA **0x2480CD**, file offset **0x2380CD**, **1E -> 7F**, and repins section 0
  with the existing `section_digest` helper. The complete 49-byte context at
  0x2480C6..0x2480F7 is pinned, including the getter, signed `cmp eax,imm8`,
  `jle`, stage-1 test and completion path. Every other immediate (including FF),
  modified surrounding code, truncated section and malformed header is refused
  before mutation. Applying an already-applied patch returns identical bytes
  and an empty, zero-change receipt. No cave, runtime global or allocation exists.
- Retail `default.xbe` SHA-256 is
  `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
  The gate-only output, constructed in memory, has SHA-256
  `a099ad1d475b9c6c83d397f6b64dc5d7cc59cdaa6686155db0e439b3ee36b9f6`.
  Exactly **21 bytes** differ: the immediate and all 20 bytes of the .text
  section digest, from `72edb599858a06a0f88c6ae446907e3977f4fec6` to
  `2b03f793d69b7a49a8eac57e5ba66818bddc8175`. File size remains 11,948,032.
- The inspected gate passes indices <=127 and other stages, and refuses index
  128 at stage 1. FF sign-extends to -1, not 255. Index 0 is the first season.
  The old branch already passes index 30; an exact playable-season count cannot
  be inferred from this branch alone. The requested product label describes
  the target, with the experimental/unwitnessed qualification visible beside it:

  > Franchise runs to 128 seasons. Dates and ages after 2099 are not repaired yet.

- Both save year writers accept only integer indices 0..127 and modify exactly
  **save+0x91326**, preserving **save+0x91327** with nonzero sentinels, every other
  byte, file length, signing and container metadata. Readers preserve all raw
  u8 indices, including 128 and 255, so terminal saves can be inspected/re-signed.
  Neither writer manufactures index 128. The legacy API retains its existing
  refusal of a no-op year edit; the typed API retains its no-op behavior.
- The brief's u16 bug was actually in **`nfl2k5_save_writer.py`**, not
  `nfl2k5_save_rost.py`. That required core fix is included. Both 60-index edit
  limits are removed. +0x91324 and +0x91325 are now reported as separate
  `stage_weeks` and `week`; `season_ordinal` means `year_field + 1` rather than
  their incorrectly interpreted u16. The old offset alias remains for imports.
- Save readers/writers accept an explicit `base_year` (default 2004), propagated
  through loose/save-container/HDD-copy APIs. A save has no proved base-year
  marker, so a 2026 executable's caller must select 2026. Broad view validation
  is 100..9744, leaving room for all raw u8 values within Python's date domain;
  this does not advertise executable support for arbitrary starting years.
- `nfl2k5_roster_records.py` now reads live DOBs relative to the current calendar
  year, and writes **birth_year % 100** into the existing seven bits. The new
  formula is `current_year - (current_year - raw % 100) % 100`, choosing the
  unique birth in `[current_year - 99, current_year]`. Copies and save codecs
  retain context; invalid DOB edits refuse before changing month/day. This fixes
  the old setter, which encoded 2001 as 101 and rejected 2031 despite the getter
  claiming a 2054 range. The declared numeric upper bound is no longer 2027:
  the global domain is 1..9999, narrowed by the contextual century window.
- Both ROST readers infer current year only from the known full version-0
  franchise envelope, using its byte index and supplied base year. Bare ROST,
  disc images and arbitrary opaque suffixes require explicit `reference_year`
  when known. With no context, legacy 1955..2054 interpretation is retained,
  including old 100..127 encodings. All 128 raw encodings survive round trips;
  even assigning the same decoded DOB preserves the original representation.
- The owned Franchise tab shows **`season 31 = index 30`**, offers a build
  starting-year view setting, and keeps year edit journals indexed correctly
  when that setting changes or undo/redo runs. Index 127 edits save/reload;
  index 128/255 loads show the actual value with year editing disabled instead
  of silently clamping. The exact requested limitation text is present, with
  an additional 2053 game-DOB warning and “Editing this year does not simulate
  seasons.” No other GUI panel was edited.

**Inherited composition repair:** both mandatory XBE gates initially failed
before the new patch ran. `nfl2k5_depth_locks._context` assumed expanded rows
always meant stride 13, but this base branch's SPECIAL patch relocates its table
while retaining stride 11. The minimal context correction detects that table
separately and still demands the exact owner bench bytes and swap test. It
changes **no depth-lock runtime bytes**. Static inspection proves the bench
call still returns to **0x244464**, with encoded chain in EAX, as the existing
compactor expects. The new regression checks the call bytes, strict corruption
refusal and idempotence. Existing lock composition tests pass in both patch
orders. This necessary core change is outside the brief's named season files
but is not a protected file; it is documented rather than weakening/skipping
either mandatory gate. Claude must refresh the reservation source fingerprints.

**HYPOTHESIS / not established by these changes:** successful natural season
rollovers, correct in-game dates/DOBs over a century, a complete century archive,
balanced long-term economics, and all indirect engine consumers. No game was
played, emulated or fast-forwarded here. Changing an index does not execute the
intervening drafts, retirement, cap compounding, records or schedule generation.

## Wave 2: complete bounded 128-season engine

This is the requested **precise implementation specification**, derived from
`/home/noah/Desktop/2K5-8 Editors/SEASON_CAP_RESEARCH_2026-09-05.md`, especially
sections 2-4. Its engine addresses/widths are **PROVED in that memo**; the design,
size estimates and full-game behavior below are **HYPOTHESIS**. Only the wave-1
gate and the narrow SPECIAL compatibility evidence were rechecked here.

### Calendar contract and shared helper ABI

1. Keep the saved unsigned byte index and RAM dword **0xE576B8**. Let
   `Y = configured_base_year + index` in a full 32-bit register. Supported play
   indices remain 0..127; let retirement completion at 128 run deliberately.
   Support dates through the January/February following index 127 and terminal
   save inspection. For a 2026 start this is 2026..2154, encoded as 26..154;
   for 2004 it is 2004..2132, encoded as 4..132. No use of save+0x91327.
2. Internally pass full `(year, month, day)` values and a signed day number;
   convert only at record boundaries. Define `day_number` relative to
   **2000-01-01 = 0**, and weekday **Sunday = 0**, so
   `weekday = floor_mod(day_number + 6, 7)`. Leap rule is
   `Y % 4 == 0 and (Y % 100 != 0 or Y % 400 == 0)`. Handle negative day numbers
   with floor division/modulo for historical inputs. Validate month/day before
   conversion. Date addition and subtraction use the same ordinal conversion
   and inverse, not independent month-boundary implementations.
3. New current-franchise schedule dates encode **year - 2000**, without `%100`
   and without the retail 98/99 pivot. Check 0..255 on encode. Use the known
   month/day/year bytes at **schedule record +3/+4/+5** only for records whose
   caller/producer proves that layout. Preserve team, kickoff and flags fields.
   The save grid API currently calls +5 `slot_code`; settle each grid/template
   consumer's format at its pinned boundary before changing its interpretation.
   Do not globally reinterpret every 8-byte record or every byte +5 as a year.
4. Boundary wrappers must distinguish **new current-franchise schedule**,
   **template** and **historical/non-franchise** inputs. Template bytes need an
   explicit template base/season and month-crossing rule; historical formats
   keep their existing source-year context. A mode flag alone cannot identify a
   historical date shown inside Franchise. For legacy saves, classify provenance
   from the owning grid/template and build context; refuse ambiguous automatic
   migration rather than guess that byte 99 means 2099. Do not mass-rewrite old
   scores, event/history dates or save padding to add a discriminator.
5. Pure helpers use stack-local scratch, preserve the original caller's callee-
   saved registers/stack cleanup and any live flags at hooks. Wrappers convert
   the actual retail register ABI into full-year arguments. Pin complete
   displaced instructions, explicit continuations and all installed-owner
   alternatives before any mutation; partial/mixed combinations must refuse.
   No persistent data bytes are required by this design. ABI/overwrite lengths
   at each entry must be finalized from instructions, not a decompiler guess.

### Hook and consumer inventory

All addresses are Xbox VAs, not raw offsets. These are hook/consumer sites to
implement or audit, not reserved caves; existing-owner entry rewrites take
precedence over installing a second jump on top of an owner.

| Site | Required work / owner contract |
| --- | --- |
| 0x2480CB / 0x2480CD, branch 0x2480CE | Keep this gate and its retirement-stage test; no FF imm8 or widened save field. |
| 0xC4EB0 getter, 0xC4EA0 setter; load 0xC585F..0xC5868 / store 0xC538C..0xC5395 | Continue dword RAM / u8 disk contract; use getter to construct full Y, not a second persisted counter. |
| 0x247B44..0x247B50; 0x247CF7..0x247D01 | Preserve natural increment and stage-1 transition. No calendar hook may skip draft/roster lifecycle work. |
| 0x1C1880 | Replace faulty `/4 and not /200` leap predicate through context-aware wrappers. |
| 0x1C18B0 / 0x1C19F0 | Replace pivot-based weekday/day-number conversion; reconcile the latter's legacy 1999 epoch at call boundaries. |
| 0x1C1A90 / 0x1C1B30 / 0x1C1BB0 | Week-break, date increment/decrement; remove 99->0 and 0->99 wraps only on the new schedule path; use one Gregorian core. |
| 0x2BEB60, 0x2BEBD0 | Preserve rotation `(index + 2) % 4` and initial/later team order; separate matchup selection from redating. |
| **0x2BEC20..0x2BF1B0** | Preseason owner owns the entire 1,424-byte replacement span, currently 430 bytes of code. Modify that owner's generator to call the full-year helpers; its unused tail is not free allocation. Retail 0x2BEF6A is inside this overwritten region and cannot be an independent hook in the composed build. |
| 0x2BF5C0 and regular generator callers 0x2BF2AB / 0x2BF46F | Replace AL-only Thanksgiving/year anchors; pass full Y and encode once per emitted date. Preserve first/later-year roster work. |
| 0x2A7E50, template 0xACD6C8 (12 x 8) | Compose inside the installed `nfl2k5_playoffs14` builder; regenerate dates each year instead of copying fixed January/February days. 0x2A8284's year getter controls team parity, not date generation. |
| **0x145D20..0x145D90** (112 bytes) | Replace the existing fixed-century DOB formatter with a call/wrapper into moving-century decode, preserving the rotating display-buffer ABI; do not overlap another DOB owner. |
| 0x2BE6F0; seeds at 0x2BE808 / 0x2BE817 | Preserve generated `(index + configured rookie seed) % 100` births in player+0x18 bits 21..27; no width growth. |
| 0x247AC7, 0x1C1847, 0x24C7C1, 0x21B6FE | Existing configured-year operands for main/date/event display; feed the same full year and preserve month-crossing adjustment. |
| 0x3204AD, 0x3218A7 | Missing player-history bases: `base_year + 11`; getters 0x320460/0x321860 compute index + base + 11 - row bank. Preserve folded-row/team-column semantics. |
| 0x34771D, 0x3663ED and their format callsites | Missing future-year labels: replace index + horizon + 4 with full configured calendar year + horizon, and give these calls dedicated four-digit formats. Do not globally modify a shared `%02d` string. |
| 0x260A80 -> tail jump 0x260A8D; callback data 0xA8E554 | Close indirect consumer coverage before declaring all year labels repaired. The memo's 57 direct getter calls plus this tail jump are a starting inventory, not a proof no other callbacks exist. |

### Preseason, regular season, postseason and DOB behavior

Generate the calendar once per annual schedule, with the same full Y supplied
to all three phases. Select matchup templates using the existing rotation and
team-order policy, then assign dates from the actual year's anchors. Compute
Thanksgiving as the fourth Thursday of November with Gregorian weekday math;
never add a base-year byte in AL. Compute the year's opening-week anchor from
the configured schedule rule, then apply the existing per-game day/time offsets.
The 2026 configuration retains three preseason games over four preseason weeks,
18 regular-season grid weeks and the installed postseason layout, including its
bye spacing. Preserve the selected Thursday/Sunday/Monday/etc. slots and all
game-count, matchup, home/away, played-score and bye/filler invariants.

Derive each year's playoffs from that year's final regular-season week plus
the configured wild-card/divisional/conference/Super Bowl day offsets; all
January/February dates use Y+1. `playoffs14` owns the six wild-card games, seven
seeds per conference, first-round byes, row remapping and championship matchup.
Its builder must consume the same calendar helper. Keep the existing preseason,
regular and postseason stage extents and 22 x 17 grid; the gate needs no stage
table or save-size enlargement. Test first-year templates and generated later
years separately so a template year is never added to an already encoded year.

Use the moving-century DOB formula implemented in Studio for **live players**,
based on advancing Y, never the fixed start-year pivot. Keep modulo-100 rookie
births and reconstruct the unique year within the live 100-year window. For
an archived identity older than a century, use the history row's calendar
context if proved, or label the century unknown; a permanent century archive
requires another storage design. Experience drives the inspected retirement/
progression paths, so a display repair does not widen or repurpose experience.
Format main season/date lines, event dates, player history, future projections
and DOB consistently. Inventory all direct getter calls and the unresolved
callback path, and witness every visible label at the century boundary.

### Grown-section allocation and composition budget

Use the **grown-section allocator** for new helper code. This report certifies
no free cave address and allocates no section bytes. Proposed helper budget:

| Helper group | Estimated bytes |
| --- | ---: |
| Boundary year decode/encode | 64..128 |
| Leap predicate and month length | 64..128 |
| Gregorian ordinal and inverse | 160..320 |
| Weekday | 32..64 |
| Date add/subtract and week break | 128..256 |
| Moving-century DOB decode | 64..128 |
| **Shared helper total** | **512..1,024 (0.5..1 KiB)** |

These are estimates, **plus hooks and owner generator/formatter rewrites**, not
assembled lengths. Constants/format strings get explicitly allocated immutable
storage; helpers get executable/preloaded storage. Any future mutable state
must receive writable allocated storage, never .text. The proposed design uses
**zero new persistent data bytes** and stack scratch. Require allocator receipts
for every range, valid raw/virtual section sizes, loader flags, page alignment,
section digest repins and a current reservation manifest. `unknown` is never
`free`; reject overlap and stale sources. Reusing the preseason owner's 994-byte
tail or DOB owner's padding requires that owner's composed rewrite and proof,
not a claim that slack automatically belongs to this feature.

Composition obligations before a full-engine build:

- **Preseason owner:** one coordinated rewrite of 0x2BEC20..0x2BF1B0; full Y
  through anchors, date-add and encoding. Validate exact supported predecessor
  versions. Keep each phase's week counts and roster gates intact.
- **`nfl2k5_playoffs14` / season-length owner:** wire dates into their installed
  builder, preserving seeding, row thresholds, byes and current 2026 year sites.
  Upgrade the owned DOB formatter and year sites together, with atomic refusal
  of a half-upgraded calendar stack.
- **`nfl2k5_team_column` / team-history owner:** the two missing history labels
  must share the base year while respecting team field 87 and folded history
  rows. Retain history-pool compaction/folding, not 128 permanent detailed rows.
- **`nfl2k5_progression` owner:** preserve retirement decision, experience masks,
  curve clamps and yearly order. Experience is five bits, curves clamp at 20;
  the memo's bounded retirement path removes players before the experience
  rollover under its inspected conditions. League lifetime is a separate axis.
- **Practice-squad / `nfl2k5_practice_reserves` / depth-lock owners:** preserve
  annual IR restore, active/reserve eligibility, contract decrement, retirement
  removal/recycling and 380-prospect replenishment. Reserve-only players must
  reach the same lifecycle exactly once; verify no hook bypasses it. No new year
  data may borrow their record bits or allocated section state.
- Validate every combination in memory first, then run the memory-write and
  retail-reference gates on the final candidate and refresh the allocator's
  source/owner manifest. Do not call a current gate-only source “full calendar”.

Leave seven-year salary queues at seven entries; do not pass horizon 100 to
`0x13ECA0` with team deductions enabled. The memo's cap arithmetic fits signed
32-bit at index 127, but long-term economics remains unwitnessed. Preserve current
award-slot overwrites, the 600-entry event ring and bounded history folding.
These are rolling structures, not promised permanent 128-year archives.

## Tests run and results

All runs used Python 3 in this worktree, local inputs and temporary copies.
Qt runs used **`QT_QPA_PLATFORM=offscreen`**. No CPU emulator, console emulator,
GUI display, audio or network was used. Tests inspect or compose bytes; arithmetic
models are not execution witnesses. No retail XBE, save fixture or disc was written.

| Exact command | Result |
| --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_season_cap.py` | 7 passed |
| `python3 tests/mod_editor/test_nfl2k5_season_cap_saves.py` | 7 passed |
| `python3 tests/mod_editor/test_nfl2k5_franchise_save.py` | 13 passed |
| `python3 tests/mod_editor/test_nfl2k5_save_writer.py` | 17 run, 16 passed, 1 skipped |
| `python3 tests/mod_editor/test_nfl2k5_save_rost.py` | 9 passed |
| `python3 tests/mod_editor/test_nfl2k5_roster_records.py` | 108 run, 107 passed, 1 skipped |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_franchise_panel_qt.py` | 16 passed |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_roster_editor_panel_franchise.py` | 2 passed |
| `python3 tests/mod_editor/test_save_roster_import.py` | 12 passed |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 8 passed |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 9 passed |
| `python3 -m unittest tests.mod_editor.test_nfl2k5_depth_locks.RecordTests tests.mod_editor.test_nfl2k5_depth_locks.PatchTests` | 6 passed; only non-emulation classes selected |

**214 tests run: 212 passed, 2 skipped.** The save-writer suite expects a separate
legacy fixture at `/tmp/opencode/espn26/default.xbe`, absent here; the main roster
suite skips its absent shipped portrait catalogue. The available retail XBE and
real signed save tests did run. New tests are standalone `unittest` files and
retail-dependent cases skip with a precise path when that evidence is absent.
The existing depth-lock test file lacks a `__main__` runner, so the supplemental
command above explicitly ran its two offline classes; invoking the file alone
was not counted as testing it. No execution class was run.

Regression coverage includes all 128 editable indices at both 2004 and 2026
bases, nonzero +0x91327 sentinels, 128/255 read-only round trips, re-signing a
terminal save copy, opaque suffixes, strict rejection without mutation, every
seven-bit legacy birth encoding, birth/date century and leap sentinels, context
copy/edit/reload, GUI undo/redo and visible ordinal, and composition with all
five existing season/calendar groups. Both XBE gates enumerate the new owner.

During development the old GUI-caption assertions and a duplicate temporary
fixture directory were corrected for the new tests. The new SPECIAL ABI test
initially omitted the required EDGE/scheme prepasses; its fixture now applies
them in the production order. The final commands above passed. Raw validation
logs are left in uncommitted `.scratch/`; they are not runtime artifacts.

## Noah's required witness list

**Every item is pending.** Use a naturally advanced franchise on a composed
candidate and preserve originals, build receipt/XBE hash, base-year setting,
SAVEGAME.DAT/EXTRA pairs and before/after screenshots separately. Record both
ordinal and raw index. A Studio-edited index is useful for a boundary probe,
but does not count as a natural multi-year lifecycle witness.

1. **Seasons 30 -> 31 -> 32** (indices 29 -> 30 -> 31): save before postseason
   rollover, retain **index 30 retirement**, **index 31 retirement**, and
   **index 31 regular-season** saves. Check no premature completion dialog,
   correct next draft, a populated class and advancement after quit/reload.
2. **Season 50 (index 49)**, **season 100 (index 99)** and **index 100**: retain
   before-rollover, following-preseason and entered-regular-season saves. Reload
   each. Check year labels, active/reserve/IR rosters, retirement/replacement,
   prospect count/recycled identities, cap/contracts/dead cap, history rows and
   folded totals, standings, coaches, event log, records and annual award winners.
   For a 2026 start these are calendar years 2075, 2125 and 2126.
3. **2053** (2026 index 27): generated 2031-era prospects must display their
   actual century in Studio. The wave-1 executable still has the known fixed
   DOB-pivot defect. Record that limitation; require correct in-game DOBs only
   after the wave-2 formatter is installed.
4. **2098 -> 2099 -> 2100 -> 2101**, plus **2104** (2026 indices 72, 73, 74,
   75, 78): inspect month lengths, birthdays, weekday labels and pre/regular/
   playoff spacing, including December/January rollover. Require no February
   29 in 2100 and a valid leap day in 2104 for the full engine. Wave 1 does not
   repair these dates; byte 99 already decodes incorrectly at **2099**, despite
   the requested caption's “after 2099” wording. This is a known limitation.
5. **Index 127 / season 128**: complete it naturally, retain its last normal
   save and the rollover/terminal save. **Index 128 / season 129** must refuse
   deliberately in retirement, and the terminal save must reload without
   wrapping or masquerading as index 0. The Studio writer's refusal of index
   128 is separately tested; it is not a witnessed game refusal.
6. If offered together, repeat cap/contract milestone checks using the
   **four-times initial cap** setting, and repeat with progression/reserves/
   playoffs14 enabled. Preserve awards and recycled-player references across
   the transition. Do not substitute a 100-year forecast for annual progression.

## Delivery boundary and remaining gaps

No protected file was changed. The exact dispatcher kwarg/tuple/four status
dictionaries, BuildPlan/presets/receipts, PATCHES and NEEDS_IMAGE policy, <=60-char
Build caption, allowlist, closure imports, capability entry, host DOB context
and manifest regeneration are in `WIRING.md`. The existing unrelated handoff
there was preserved. Those are integration work assigned to Claude by the brief.

The wave-1 executable still has the fixed-century DOB bug by 2053 in a 2026
franchise, the 98/99 calendar pivot, faulty Gregorian helpers, fixed playoff
dates and missed year labels. The Studio century inference is valid for live
births in a 100-year window, not uncontextualized permanent historical identities.
The starting-year view setting is not persisted into an undocumented save byte;
the host/build context must supply it again on reload. No full engine, grown
allocation, natural rollover, emulator witness or century archive is claimed.

The brief and `.scratch` are excluded from commits. Shared git metadata accepted
staging, so the normal explicit-path commit is used; no bundle fallback is needed.
No push is authorized or performed. Final `git diff --check`, changed-Python
syntax checks, protected-file audit and parsing of the documented capability
row through the real registry loader all passed.

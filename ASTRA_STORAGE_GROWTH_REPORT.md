# r62 roster storage growth

Design recorded before implementation, 2026-09-05. EXPERIMENTAL / UNWITNESSED.

## Design decision

Implement the existing 82 stadiums in the Create a Team picker first. This is
the smallest storage primitive that can be certified from the available inputs:
an owned immutable 82-byte ID list and ten instruction operand edits. The
67-entry list has three readers, two search bounds, two preview modulo bounds,
one previous-preview offset, and two controller wrap bounds. The research memo
missed the preview and controller bounds and one reader in a Ghidra gap.
Preserve the first 67 IDs in their original order and append the missing 15.
Use an allocator code allocation for immutable bytes, as the existing boot
bitmap does. This needs no mutable state, new page, ROST growth or save version.
The existing stadium records and team +0x114 relative pointer remain authoritative.

Do not widen the 65-pointer prefix in place. Its next byte belongs to the team
nickname pointer. A 70-pointer prefix for 53 + 16 + eligible 17th would shift
every field from +0x104 onward by 20 bytes, give a 520-byte team stride, and
require 1,040 additional bytes for 52 records. The two relocators process 13
groups of five pointers; 14 groups is insufficient without moving all the
following fields and changing every stride, copy and consumer. Match buffers
and the front-office 32 x 65 x 3-byte table are independent constraints.

Prefer a future versioned reserve overflow block inside a grown ROST arena,
with primary-player indices and an explicit team association. Five u16 indices
per NFL team cost 320 bytes; a proposed 32-byte header makes 352. Indices need
remapping on player-pool compaction/reuse. This keeps the retail team fields and
match buffers stable but requires all reserve ownership, salary, retirement,
practice, rollover, promotion/demotion and import consumers to use the overflow.
An executable RW mirror alone cannot persist across save/reload and is not a
save-format solution. Unknown arena padding is not an allocation.

Grow the runtime allocation, disc resource framing and serialized save arena
together when that migration is implemented. A 0x92000 arena gives 4,096 new
bytes and 4,256 bytes over the retail 0x90F60 used body. The 352-byte overflow
fits; this size also leaves 3,904 bytes for other explicitly allocated records.
The current 0x91000 arena and every existing save offset remain in this patch.

More created teams require appended 500-byte records, unique team IDs, labels,
playbooks and an audited created-team predicate. Keep existing ordinals stable.
The two comparisons at 0x319377/0x31937D only recognize IDs 90/91; changing
them cannot allocate teams or extend franchise tables. With the proposed
352-byte reserve block, a 0x92000 arena can fit seven extra bare team records
(3,500 bytes), leaving 404 bytes for strings and other allocations. This is a
size budget, not permission to append seven fully configured teams. Expanding
the 32-team league is a separate schedule/front-office migration.

The Studio Reserves limit stays 12 because no 16/17-player runtime patch is
delivered. Installing the stadium patch must never enable larger reserves.
The precise remaining migration, consumer inventory, tests and witness list
follow. No emulator, GUI display, audio, network or push was used. All inputs
were read only; only this worktree was edited. The RC85 changelog and prior
ASTRA report set were reviewed; their historical capacity forecasts are
superseded by the shipped beta-61 two-RX-page allocator, not treated as new work.

## Implemented primitive and proof boundary

`nfl2k5_roster_storage.status(payload)` returns `retail`, `applied` or `foreign`.
`apply(payload)` returns immutable bytes and an exact receipt; identical replay
returns zero changes. The complete old/new state, allocation shape, code seal,
surrounding algorithms, old table and adjacent bytes, XBE geometry and every
section digest are checked before constructing output. Partial installs,
foreign instructions, a populated list without its readers and a missing owner
in an already allocated image refuse. The existing digest helpers repin output.

The new owner uses exactly **82 immutable bytes, alignment 16**, from the
existing RX allocation service; no branch targets it and no runtime write
targets it. This is the allocator's established immutable-data convention,
also used for the boot bitmap. It is not a cave or an allocation of retail
padding. The tiny allocator ordering extension puts this owner after all
beta-61 owners. Tests compare every earlier allocation dictionary verbatim.
Neither page count nor any previous owner address changes in the full union.

The original 67-byte list is retained exactly. Its first 67 indices also retain
their order in the new list. Appended IDs are:

```text
32 36 39 40 41 42 43 44 45 48 95 96 97 98 99
```

These are **IDs, not table ordinals or asset-code suffixes**. Both real saves
contain exactly the expected 82 unique IDs, in a different record order.
Nothing is inserted into the existing stadium resource or its string pools.
The patch is for the Create a Team picker; it does not claim to expand every
other venue-selection screen or import new stadium assets.

### Complete discovered stadium-list consumers

PROVED against SHA-256-pinned retail `default.xbe`
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
The byte-granular scan of all raw XBE sections found exactly three encoded
references to `0x531B70`. The full cursor-reference scan found fifteen uses of
`0xC8F7F0`; all are in the initialization, preview, search and controller paths
listed below. The census includes all their addresses, not only changed ones.

| Instruction VA | Consumer | Change |
| --- | --- | --- |
| `3191C2` | `3191B0`: ID to stadium-record lookup using root +10/+14, stride 128 and record +7C | Retarget list displacement |
| `3192C9` | `3192B0`: reopen selected team's stadium, compare its +114 record's ID | Retarget list displacement |
| `319340` | `319310`: selected logo's default stadium ID search | Retarget list displacement |
| `31926D` | `319250`: next-preview modulo divisor | 67 to 82 |
| `319289` | `319250`: previous-preview offset | 66 to 81 |
| `31928D` | `319250`: previous-preview modulo divisor | 67 to 82 |
| `3192D7` | `3192B0`: reopen search bound | 67 to 82 |
| `31934C` | `319310`: logo default search bound | 67 to 82 |
| `31A9CE` | Controller previous from zero | 66 to 81 |
| `31A9FD` | Controller next wrap | 67 to 82 |

The controller block and `3192B0` are absent from the supplied Ghidra function
ledger. Direct retail disassembly supplied those gaps. Original instruction
lengths, operation types, registers, conditionals and continuations remain.
`3192E0` still writes a **stadium record pointer** to team +114 and requests
the native preview. `319200` still resolves the preview by the record ID.
`319310` still copies the selected logo code and uses the existing 34-logo
table; its separate bound at `319397` remains 34. Created-team predicates at
`319377/31937D` stay unchanged. No mutable cursor is placed in executable code.

### Save and Studio contract

PROVED: the native loader at `241977..24198D` relocates team +114, and the
writer at `241AD3..241AE7` converts it back with `target - field + 1`.
Both remain byte-identical. A saved selection points to the existing stadium
record; neither the new executable list address nor the transient menu index
enters the save. Thus there is no new save layout to migrate for this primitive.

The shared typed stadium decoder resolves records inside the **declared ROST
arena**, preserving all 128 bytes, including the three unknown bytes after
the one-byte ID. The save codec and `RosterDocument` expose `stadiums` and
`team.stadium_index`, and reject interior, unrelated and out-of-arena stadium
references. NULL remains supported for synthetic/legacy teams without a venue.
`FranchiseSave.team_stadium(team)` reads the current composed buffer, avoiding
its cached roster document. Existing player editing, opaque prefix/suffix and
HMAC signing paths preserve the selected reference.

All 82 choices round-trip through both version-17 and version-0 synthetic
documents, with deliberately permuted IDs and nonzero unknown bytes. The
franchise fixture tests all 82 against a primed cache. Two preserved real saves
are decoded, assigned all 15 added choices, written to temporary signed ZIP
copies and reopened. Unrelated archive members and the complete franchise
suffix stay exact; source saves remain unchanged. These are **host-format
proofs**, not game-generated post-patch save witnesses. The game must still be
played, saved and reloaded for that lifecycle claim.

## Deferred 16/17-player reserve implementation

The following is a precise HYPOTHESIS/design, not an installed schema. It
explains what must be finished before raising the Studio limit.

1. Keep the 500-byte team and its first 65 pointers. Add a 352-byte owned block
   at **arena-root +0x91000**, entirely in newly allocated arena bytes, not in
   the old 160-byte residual. Layout: 32-byte header plus 32 NFL teams x five
   little-endian u16 primary indices; `FFFF` means empty. Proposed header:
   eight-byte magic; four u16 values (version, team count, overflow slots,
   entry size); u32 pool epoch, payload CRC, eligible-team mask, reserved word.
   Team association is the preserved NFL ordinal 0..31; no raw RAM pointer is
   persisted. Eligibility flags are a storage mechanism, not proof of eligibility
   policy. A user/engine eligibility decision must be specified separately.
2. Bump the team reserve metadata to version 2 only when that block is present.
   Count at +1F2 means total reserves. Native tail length is
   `min(reserves, 65 - active)`; any remainder uses at most five overflow
   entries. Enforce active <=65, active+reserves <=70, ordinary reserves <=16,
   eligible reserves <=17, and in-season active <=53. Offseason acquisitions
   must use the combined capacity, not assume five overflow entries make all
   combinations of 65 active plus 17 reserves possible. The existing season
   and promotion limits need no advertised expansion.
3. Replace all reserve-list access with one iterator over native and overflow
   identities. Removal/compaction fills the native tail first; promotion from
   overflow and demotion validate ownership/capacity before moving anything.
   Recompute metadata and integrity on one private transaction. Salary, FA
   exclusion, IR transfer, native append/remove, CPU trade/draft/auto-cut,
   retirement, expiry and rollover must use the same iterator. Rebuild the
   generated C/assembly runtime; changing only Python or a compare is unsafe.
4. Allocate **0x92000** bytes for the runtime arena. The new block ends at
   root+0x91160, leaving **0xEA0 = 3,744** newly allocated bytes. The earlier
   3,904-byte figure counts the old memo's 160 residual bytes too; it is not an
   approved allocation. For a version-17 template with root at body+0x40, the
   explicit offset design requires body length **0x911A0**, including the
   224-byte gap between the existing body end and the new block. Wrapped
   resource length is **0x911C0**. Rebuild pack 0 through the transactional
   archive writer; do not overwrite its next resource. Native install paths,
   allocation size, wrapper size and arena-copy bounds must all agree.
5. A runtime save then has inner declared length **0x92020**, wrapper+body
   **0x92040**, root still **0x320**, arena end **0x92320**, season end/front-office
   start **0x9A6FC**, total franchise size **0xB0CAC = 724,140 bytes**. The
   existing season block stays 0x83DC and front office stays 0x165B0 because
   counted active slots do not exceed 65. Migrate the prefix/arena/suffix
   together. Keep old versions readable; reject mixed markers/lengths before
   any edit. Sign the complete final payload with the existing container layer.
6. Every copy/export of the roster must carry the overflow block. Player-pool
   compaction/import requires a complete old-to-new primary-index map; retired
   or reused indices must clear ownership or advance the epoch under a defined
   lifecycle. Apply the same mapping to active, reserves, FA, IR and history
   references. A pool epoch alone cannot prove that a reused player is the
   same person. Native clear/retire hooks must participate.
7. Adapt Free Practice's disposable projection and salary/progression/healing
   consumers explicitly. Preserve 65-slot match copies unless their active
   count is deliberately expanded. Added reserves must not silently become
   game-day active players. Validate native load-save-load and ownership at
   53+16, 53+17, 52+17, all five overflow entries, retirement, draft, IR,
   season transitions and signed Studio round trips before enabling a limit.

The existing RW page has about 854 unallocated bytes before alignment and
other owners, but a 352-byte executable mirror does not solve persistence.
The roster arena already has runtime writable ownership; the future malloc
growth belongs there. A roster team table cannot be placed in RO storage:
native sorting, salary updates and statistics mutate it. Another RX page is
not a substitute for a saved RW roster allocation.

### Why a widened prefix is larger in scope

For 69 pointers, team size becomes **516 (0x204)**, +16 per record, +832 for
52 teams. For 70, it becomes **520 (0x208)**, +20 per record, +1,040 total.
Every tail field shifts; for 70, active count +11C becomes +130, metadata +19B
becomes +1AF, count/marker +1F2/+1F3 become +206/+207. Both 13x5 relocators
must become 14x5, and every fixed stride/copy consumer must agree. Merely
patching their loop counter would relocate nickname/abbreviation fields as
player pointers and corrupt the record.

`61730` copies two 500-byte match teams at B30864/B30A58; player buffers start
at B30C4C/B321A0 and are separated by 65x84 = 5,460 bytes. Team enlargement
requires new copy destinations and all their consumers even when active count
stays <=65. If active capacity itself becomes 70, each player buffer needs
420 extra bytes. The 32x65x3 front-office table would need 480 extra bytes and
its serializer/loader/size consumers would change to 0x16790. This is avoided
by the proposed reserve overflow. A 90/91-player camp is not covered by it.

## Deferred created teams and arena relocation

The two `cmp ax` sites classify IDs 90/91; they do not allocate slots. The
retail template contains 52 records, 36 team-label/playbook entries, and two
created slots. Additional records need collision-free IDs, labels, asset/logo
policy, ownership handling and selected-team/create/delete persistence. Preserve
all existing ordinals, especially teams 20/21/42 and stadium ordinal 33.

The 500*N budget at the beginning is a **net compaction budget only**. The
existing team table is followed by other live tables. Appending N records to
that physical location would overwrite them. There are two concrete choices:

| Layout strategy | Incremental bytes before new names/assets | Prerequisite |
| --- | ---: | --- |
| Compact/rebuild the whole arena and expand the team table in place in the rebuilt image | 500*N + 352 reserve block, plus layout alignment | Complete relocation schema for every moved table/string and inbound pointer |
| Retain old arena bytes; append a fresh contiguous team table and retire the old one | 500*(52+N) + 352 | Rebase every copied team's relative player/string/stadium/coach pointer and every inbound team reference |

Choose the second for an initial bounded created-team experiment once inbound
references are closed. For **eight extra teams** (ten created total), 60 records
need 30,000 bytes (0x7530). Start the reserve block at root+0x91000 and the
new team table at root+0x91160; table end is **root+0x98690**. A **0x99000**
arena adds 32,768 bytes and leaves **0x970 = 2,416** new bytes after the table
for explicitly owned names/labels. The version-17 body then needs at least
**0x986D0**, wrapped length **0x986F0**, before those additional strings.
Save declared length becomes **0x99020**, arena end/season start **0x99320**,
front-office start **0xA16FC**, final size **0xB7CAC = 752,812 bytes**.
These sizes assume the existing 32-team franchise structure and unchanged
front office; adding NFL league slots is a separate project.

The original table may remain as retired bytes for exact migration comparison,
but no live pointer may keep using it. Update root +18/+1C and all inbound
references, and revalidate strict active/reserve/FA/IR ownership. All-star aliases
retain their special ownership rules; `CLUB_TEAM_COUNT=34` in Studio cannot be
used to classify appended created teams by index. Prefer explicit kind/ID
classification once every consumer has been audited. Created IDs 90/91 must
join a versioned identity map or explicit list, not an unchecked numeric range.
`User A/User B` playbook labels and the creator's 42-minimum/54-signing rules
also need a policy. Do not confuse its 100-item selection workspace with a
100-player team capacity.

## Consumer inventory and remaining certification gap

The complete reproducible candidate inventory is
[`nfl2k5_roster_storage_census.json`](docs/mod_editor/nfl2k5_roster_storage_census.json).
It records each matched function address, shard and line, all shard SHA-256
values, the exact query expressions, Studio paths/lines/hashes and independent
decoded XBE sites, including `GHIDRA_GAP` entries. Reproduce with:

```sh
python3 tools/nfl2k5_roster_storage_audit.py \
  --corpus /home/noah/2k-football-mod-tools/research/functions/nfl2k5 \
  --xbe '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --json docs/mod_editor/nfl2k5_roster_storage_census.json
```

This is an exhaustive enumeration **for the listed lexical and decoded
queries**, not proof that every computed alias has been discovered. Constants
500/125, 65 and IDs 90/91 also occur in unrelated systems and libraries; those
candidates are retained rather than silently labeled team consumers. The
linear decode finds 334 +11C displacement candidates, compared with the memo's
342-site census. Its gaps/interpretation difference must be resolved before
certifying a prefix migration. No claim of a completely closed team-stride or
team-count call graph is made. That missing certification is the reason this
session implements the smaller stadium primitive instead of PS growth.

The principal semantic boundaries, beyond the per-site JSON enumeration, are:

| Area | Consumers requiring a migration audit |
| --- | --- |
| ROST root/table | `C0500/C0730` root relocation; `C0390/C0970/C09B0` and root-table consumers; count at root+18 and table at +1C |
| Allocation/install | `C1F00` writes 0x91000 at C1F2D/C1F3C; `C1EA0` and `C2040` size rejection/copy; descriptor/wrapper writers and total save sizing including `16AA10` |
| Team serialization | `2418C0/241A20` unconditional 65-pointer relocation plus eleven tail pointers; `241B70/241BD0` size/copy/string packing |
| Match projection | `61730`, `617E0`, `61B60/70/80/90`, `61C50/60`, `C3C60`; two fixed team copies and two 65-player pools |
| Active membership and caps | `C3A90` removal, `C3EE0` append, `C4098`; `247AF0`, `2BF950`, `2B8310`, `325B90`, `326545`, `326980`, `3242C0`, `34AAE3`, `36F830`, `36ECE0`, `3526C0` |
| Franchise and IR | `C5310/C5800`, `2D0790/2D0CE0`, `2D0780`; 32-team and 34-slot league arrays, five IR slots, roster-slot table E51F60, pointer/index helpers `2D0500/2D0540` |
| Reserve ownership/lifecycle | Existing generated `tools/practice_squad/runtime.c`: owner/listed/reserve_count/erase/insert; append/IR/trade-room; sign/release/promote/demote; cap, clear, retire and rollover hooks; `E64D0`, `2BD980`, `247B40`, injury processing `133C50/2BE020` |
| Created team UI | `319370` predicate, the creator's lookup/copy/create/delete callers, `319390` 34-logo lookup, `31A11F`, `31AC86`, `31AE20`, root-table count consumers and 36 label/playbook entries |
| Fixed ordinals | C015B, 844BF, C20E8, C21F7, 34BBC0, 77D45; team-42 offsets 354B86/354BA9 and stadium ordinal 33 |
| Studio records | `nfl2k5_roster_records`: TeamRecord, parsing, list readers/writers, capacity, membership, adoption/remap, JSON import and image writing |
| Studio save codecs | `nfl2k5_save_rost.TABLES`, 65-slot parser, framing/bare-body bounds; `nfl2k5_franchise_save` fixed offsets/size, `_team_slots`, IR, league-slot and front-office boundaries |
| Studio reserves | `nfl2k5_practice_squad`: `_record`, reserve_list/set/remap, repack_team, ownership validator, save validator and transactions; generated runtime module and C/assembly rebuild; `nfl2k5_practice_reserves` disposable 65-player projection |
| Other Studio consumers | Team history, career stats, prospect names, player tags, schedule writer, roster reclassify/import tooling, field/team text catalog and protected roster/franchise GUI limits; exact hits in the JSON |

No count is raised merely because its backing Python integer is unbounded.
The 32/34 team arrays, 65-slot native tables and 128-team codec sanity bound
have different meanings. A complete migration must distinguish them.

Final census covers **19,968 functions in 40 shards**. It retains 187
stride-candidate lines in 115 functions, 249 active-count lines in 138
functions, 327 root-reference lines in 109 functions, 135 created-ID lines
in 83 functions, 179 fixed-65 candidates in 105 functions, and 18 stadium
list/cursor lines in 11 functions. Independent retail decoding records 159
500/125-immediate candidates and 334 +11C operands. Four arena-immediate
matches include two unrelated branches to address 90F60; only C1F2D/C1F3C
are the proved arena-size stores. The Studio inventory covers 28 files.
The auditor's tests specifically prevent pointer writes beginning with `*`
from being discarded as comments. Empty/missing corpus input is an error.

## Validation and exact results

All feature and gate tests use standalone unittest. No guest instruction
execution or GUI test was run. The existing practice-squad suite's host storage
and patch classes were selected explicitly to exclude its execution class.

| Command | Final result |
| --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_roster_storage.py` | 11 passed; 29.785 s |
| `python3 tests/mod_editor/test_nfl2k5_roster_storage_audit.py` | 2 passed |
| `python3 tests/mod_editor/test_nfl2k5_save_rost.py` | 9 passed |
| `python3 tests/mod_editor/test_nfl2k5_franchise_save.py` | 13 passed |
| `python3 tests/mod_editor/test_nfl2k5_roster_records.py` | 108 run, 107 passed, 1 skipped for absent private catalog evidence |
| `python3 tests/mod_editor/test_rosters_reserves_abilities.py` | 13 passed |
| `python3 -m unittest tests.mod_editor.test_nfl2k5_practice_squad.StorageTests tests.mod_editor.test_nfl2k5_practice_squad.PatchTests` | 7 passed |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 26 passed, both complete owner orders; 50.415 s |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 30 passed, both complete owner orders; 113.521 s |
| `NFL2K5_CAVE_MANIFEST=.scratch/storage-manifest.json python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | 28 passed; 58.649 s |

Total above: **247 tests, 246 passed and one precise existing skip**.
Additional portable run with both `NFL2K5_RETAIL_EXTRACTION` and
`NFL2K5_SAVE_FIXTURES` set to `/nonexistent-storage-proof`: five public tests
passed, six evidence-dependent tests skipped. A fresh-process production
apply/status probe with Capstone, Unicorn and NumPy imports blocked passed.
Python compilation and `git diff --check` passed.

The capability handoff merged into a scratch copy of the registry passes
`validate_registry.py --registry .scratch/storage-registry.json --skip-file-checks`
with 84 capabilities. This validates the row/schema; protected product wiring
and packaging closure changes are explicitly deferred to `WIRING.md`, not
claimed to have shipped here. Census host fingerprints and the generated
manifest's final source-root fingerprints were checked against this worktree.

The following **real disposable image** manifest build passed:

```sh
python3 tools/nfl2k5_cave_oracle.py manifest \
  '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --xiso '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso' \
  --work-dir .scratch --json .scratch/storage-manifest.json
```

It recorded **8,262 reservations from 86 observed XBE writer calls**, including
the full ten instruction spans and the 82-byte list. The final composed XBE
SHA-256 is `77f90aab858727e10fe846e18be5da532487445d066f153e43c7a629a341f032`.
The new list occupies **VA 0x14D99A0..0x14D99F2**, raw
**0xB899A0..0xB899F2**, in the full beta-61 union. The final union owns
6,583 code/immutable bytes and retains 3,242 RW bytes. Raw XBE size remains
the established extended extent, **0xB8A000 = 12,099,584 bytes**.
The manifest builder read back the grown executable through the existing
streaming disc writer and verified section digests. Its temporary disc copies
were automatically removed. The protected shipped manifest is unchanged and
must be regenerated after Claude's wiring; its source-drift guard was retained.

New fixtures are under 1 MiB; the largest whole binary read is the approximately
12 MiB executable. The census streams C shards and the decoder iterator.
No tool or test added here loads an archive pack or disc into RAM. File handles
use context managers; temporary destinations resolve before use; the existing
save and image writers handle signing and transactional publication.

## HYPOTHESIS, known gaps and Noah's witness list

There is no played result in this report. Real kernel/preload behavior, preview
availability, asset loading for special venues, controller behavior and game
save/reload remain **UNWITNESSED**. The offline patch proves menu operands and
record identities, not that every special stadium supports every game mode.
Foreign/custom ROST tables missing a listed ID are outside the patch contract;
the native lookup still returns NULL for an absent record. Protected Build,
Gameplay Patches and packaging changes are a concrete handoff, not edited here.

Noah should record the build receipt/XBE hash, platform, team, stadium ID and
result for each witness:

1. Cold boot a disposable all-stadiums build, then a fully composed build.
   Check boot/logo, ordinary menus, SPECIAL and normal gameplay for regressions.
2. In Create a Team, visit all original 67 choices and all added IDs listed
   above. Confirm names, capacity, location, surface, dome and weather details.
   Check current and adjacent previews, waiting for asynchronous loads.
3. Move forward from slot 81 to 0 and backward from 0 to 81; hold both controls
   through several full cycles. Check no stale index, preview, crash or hang.
4. Choose an added stadium, leave/reopen the editor, change logos and reopen
   again. Verify the stored stadium is found and a logo's native default still
   selects the intended record. Keep the two existing created-team slots intact.
5. Save a roster and a franchise with added venue selections, exit the game,
   reload, open in Studio, edit one player, write a signed copy and reload that
   copy in the game. Confirm team +114 selection and unrelated franchise state.
6. Start and finish a game in each added venue, testing supported day/night,
   weather and presentation paths. Practice/special venues may lack ordinary
   game assets or previews; record failures explicitly rather than treating
   the presence of a ROST record as a played compatibility guarantee.
7. With existing 12-player reserves, run Free Practice, promote/demote, save
   and reload. Confirm the patch leaves reserve limits and ownership intact;
   a thirteenth reserve should still be refused by Studio.

16/17 reserves, more created teams and a closed migration of every native
team consumer are **not implemented**. Their layouts, byte budgets, known
consumers and required acceptance work are the deferred plans above, as the
brief permits after the smallest certified primitive is built.

## Delivery

Commit scope is the 16 explicit implementation/helper/test/evidence/report
paths, including this report and the additive `WIRING.md` handoff. No protected
file was edited. `ASTRA_BRIEF.md`, `.scratch/`, proprietary binaries, saved
fixtures and temporary disc images are excluded. No push is performed.

Final explicit-path staging was refused because the linked Git metadata could
not create `index.lock` on its read-only filesystem. The brief's authorized
fallback uses isolated Git metadata under `.scratch/r62-storage-growth.git`,
with the original `5f5b504` HEAD as parent and the same 16 explicit paths for
staging and committing. Delivery is **`.scratch/r62-storage-growth.bundle`**.
The original branch ref remains unchanged and the working files remain in place.

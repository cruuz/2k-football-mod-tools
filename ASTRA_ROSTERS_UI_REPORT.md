# Rosters beta-61 UI report, 2026-09-05

Implemented Locks, Reserves management and data-only Abilities in
`astra/r61-rosters-ui`, based on `e6784e70f185567899b4256a4b8ef492dd96c7dd`.
All three features remain **EXPERIMENTAL / UNWITNESSED**. No game, console
emulator, graphical display, audio or network was used. Qt ran offscreen.
No input save, extracted game file, disc image or other worktree was modified.

## What was built and decided

### Locks

The player grid has independent Rank / Side / KR1 / KR2 / PR checkboxes using
`document.set_depth_lock`, plus one Unlock action. Assignment fields remain on
the existing cards. T/G rank zero displays LT/LG; side zero displays RT/RG;
both labels can appear on the same player. The arrows still move pointers only.

Returner claim transfers capture every affected player for undo. Lock undo
preserves ability bits and unrelated lock roles. Save and roster JSON export
check `depth_lock_conflicts`; imported collisions require an explicit unlock
or assignment change. Row 7 retains its overflow semantics. Retail/unconfirmed
executables get an explanatory note; when a loaded disc supplies a recognized
patched executable, the note reports it. Save-only loads make no claim about
the executable. Returner claims resolve at the next patched sort.

A baseline integration defect was also repaired in `nfl2k5_depth_locks.py`:
expanded depth rows retain a position-table stride of 11 in this stack. The
old validator inferred bench/swap layout from that stride and refused the
existing composed patch. It now derives the layout from the exact pinned
bench bytes and selects the matching swap predicate independently. Both
layouts, idempotence and altered-byte refusal are tested; no span, cave or
mutable runtime allocation was added. The original handoff's protected build
integration remains in `WIRING.md`.

### Reserves and one composed save

Every NFL team has a selectable `Reserves · R` group, including zero, and its
label reads `TEAM · A active + R reserve`. Reserve players use the same cards,
search and position filters. Their ownership replaces the active depth ordinal.
Identity is `(pool, index)`; `reserve_owner` and per-team reserve indices remain
separate from `team.slots`, including through undo and re-decoding.

`RosterDocument` and `FranchiseSave` expose `promote_reserve(team, primary_index)`
and `demote_active(team, primary_index)`. Both delegate to the **same** copy-only
host transaction in `nfl2k5_practice_squad.py`:

1. Decode the fully composed version-0 save, resolve primary identities and
   validate the whole active / FA / reserve / IR ownership graph. Reject
   duplicate owners; exclude retail all-star display aliases. Check player
   flags, occupied slots, unused slots and known metadata before mutation.
2. Promotion requires the selected team's reserve and fewer than 53 active
   players, including offseason. Demotion requires exactly one active owner
   and fewer than 12 reserves. Enforce the 65-slot physical limit. Ordinary
   signing/transfers and IR returns account for hidden slots and phase limits.
   Existing ordinary move minimum-roster rules remain in force; reserve moves
   do not introduce a new position minimum or a cap-approval dialog.
3. Snapshot the identities and rebuild all 65 field-relative references on a
   private candidate. Create a valid empty tail, then call `set_reserve_list`
   with consistent team/pool coordinates and primary count. No release-to-FA
   intermediate is used. Contracts, statistics and future-cap fields retain
   their allocations; no global depth reranking is applied by reserve moves.
4. Demotion clears removal flags and departing depth claims, repairs all six
   special-team indices with the retail signed-byte rule and preserves ability
   bits. Both directions recompute team salary at +0x124, including the complete
   franchise IR charge. Reserve contracts remain available on promotion.
   Ordinary membership/IR rewrites preserve the combined list and recompute
   affected salaries when reserve storage is present.
5. Validate and re-decode the candidate, then publish it as one undoable change.
   The embedded roster and franchise pages share a chronological undo stack;
   franchise edits are applied once to the shared document. Standalone franchise
   journals replay on private candidates and retain edits on conflicts, refusing
   a write instead of dropping ownership operations. Final validation follows
   composition/replay. Re-decoding preserves player objects and known name-pool
   allocation bounds, so mixed name/ownership undo can recover freed strings.
6. Use the existing `SaveContainer.write` signing scheme and output-copy path.
   Reopen every written container, verify EXTRA, compare the payload and all
   members. Reserve moves disable Build & Share JSON export; direct exporter
   calls refuse them. Pure attribute edits retain the existing export path.

`remap_reserve_list` now accepts old read coordinates and new write coordinates.
A relocated active prefix must be supplied as `new_team_record`; the original
reserve tail is decoded first. Missing identity mappings refuse, explicit
`None` retires an identity, and index zero remains valid. Ordinary moves keep
indices stable. This editor does not compact/import a different player pool:
`adopt_body` refuses identity/offset relocation. A future pool importer must
provide the complete map and remap active, FA and IR references too.

Unknown metadata is an error. Legacy saves with nonzero unused slots can still
round-trip and receive ordinary edits; reserve transactions require strict
storage validation and refuse such layouts. A real older Franchise1 fixture
exercised that distinction. No automatic repair or empty-squad substitution
was introduced. Ordinary actions on a reserve explicitly require promotion
first; they cannot make the player a second team's active/free/IR owner.

### Abilities, data only

The Abilities card exposes Speedster, Right-Stick Moves and the five phase-2
move flags. It says **"no gameplay effect until the abilities runtime patch
ships"**. There is an explicit bulk action for the shown players and masked
undo. No rating clamp, ability-derived gameplay permission, tier preset or
runtime assignment pass is inferred from these stored flags.

Storage follows the memo: +0x52 masks 0x20/0x40/0x80 are Speedster / Right-Stick
Moves / Juke; +0x53 masks 0x02/0x04/0x08/0x10 are Spin / Truck / Hurdle /
Stiff-Arm. Locks at +0x52 bits 0-4, star at +0x53 bit 0, and future high flags
are preserved by named edits. The original `unknown_52` and `unknown_53_high`
codec keys, coverage and exact byte round trips are unchanged. CSV adds named
ability columns; sparse JSON uses the compatible raw keys; the save codec
accepts named ability edits. Full PlayerData backups retain their existing
whole-record semantics. Star status no longer rejects the shared ability byte.

## Evidence boundary

**PROVED:** synthetic and private f0/f1 version-0 host round trips; legal and
refused capacity/ownership operations; stable identity and masked fields;
reserve tails through ordinary moves and IR; atomic rejection of invalid
salary/metadata/ownership; mixed offscreen edit/undo/redo; signed-copy readback;
CSV/JSON compatibility; exact bit coverage; two static XBE safety suites.

**PROVED, bounded arithmetic:** 25,920 salary cases cover all eight curves,
lengths 1-15, every year including expiry, values 0/1/7/99/1234/65535 and bonus
fields 0/1/5/15. The Python helpers match a native x64 assembly adaptation of
SHA-pinned retail E6380/E6040/E6020/E3F10, including float32 stores, integer
shifts and truncation. The adaptation changes stack/pointer widths, not the
32-bit arithmetic. The committed optional test generates it from the user's
XBE in a temporary directory. It does not emulate a game/console or distribute
retail bytes. Portable numeric witnesses run without an XBE/compiler. A first
32-bit host probe was rejected by the environment's syscall filter; the x64
probe completed. No game-level salary witness is claimed.

**HYPOTHESIS / UNWITNESSED:** gameplay persistence through CPU management,
injuries, season transitions and native cloning/reuse; runtime ability effects;
visual/controller behavior in game. No native Reserve screen was added here.
Existing saves carry their own bits; rebuilding a disc does not migrate them.
Shared all-star records share locks/abilities. Recreated players and third-party
tools can discard padding bytes. No unrestricted pool relocation is claimed.

## Tests run

Each file below ran with plain `python3 tests/mod_editor/<file>.py`;
Qt commands additionally used `QT_QPA_PLATFORM=offscreen`. Results are final
runs after fixes. No guest-execution test class was run.

| File | Tests | Result |
| --- | ---: | --- |
| `test_rosters_reserves_abilities.py` | 13 | passed |
| `test_rosters_reserves_abilities_qt.py` | 7 | passed |
| `test_rosters_salary_native.py` | 1 | passed, 25,920 comparisons |
| `test_nfl2k5_roster_records.py` | 108 | 107 passed, 1 skipped |
| `test_nfl2k5_save_rost.py` | 9 | passed |
| `test_nfl2k5_franchise_save.py` | 13 | passed |
| `test_roster_editor_panel_qt.py` | 50 | 49 passed, 1 skipped |
| `test_roster_editor_panel_franchise.py` | 2 | passed |
| `test_franchise_panel_qt.py` | 13 | passed |
| `test_ux_rosters_words_qt.py` | 4 | passed |
| `test_nfl2k5_save_writer.py` | 17 | 16 passed, 1 skipped |
| `test_save_roster_import.py` | 12 | passed |
| `test_xbe_patch_memory_writes.py` | 8 | passed |
| `test_xbe_patch_cave_references.py` | 9 | passed |

Also ran:

```sh
python3 -m unittest tests.mod_editor.test_nfl2k5_practice_squad.StorageTests tests.mod_editor.test_nfl2k5_depth_locks.RecordTests tests.mod_editor.test_nfl2k5_depth_locks.PatchTests
```

That command passed 10 tests. Total: **276 tests, 273 passed, 3 precise skips**.
The skips are unavailable portrait/uniform catalog evidence and the save-writer
suite's missing configured retail-XBE fixture. `git diff --check` and Python compilation
passed. Logs are in `.scratch/`, excluded from the commit.

The initial XBE gate failures were reproduced with the committed practice-squad
implementation: its executable output was byte-identical to this branch's.
The shared pre-rows stack hash was
`f6c1c3116d3d9d8f83680f1a7a21d4b694b74e1ba686f646b0959acb90876a49`.
Bench VA 0x244405 matched the exact expanded 115-byte block while the stride
was 11. The focused layout fix above resolves both failing suites.

## Noah's required witnesses

None of these is recorded as completed by Noah.

### Reserve memo section 4, witnesses 1-3

1. Open copied existing and new franchises. Check 0, 1 and 12 reserves, correct
   names and counts, no duplicate listing in Free Agents/Other pools, and
   retained ownership after save/reopen.
2. Promote with 52 and 53 active; demote with 11 and 12 reserves. Exercise all
   65 physical slots offseason, blocked moves and the final visible row.
   Confirm refusals retain the selected identity, owner and undo history.
3. Combine a reserve move, name/attribute edit, release/sign and IR
   placement/return. Undo/redo, save/reopen and verify everything together.
   Try signing a reserve to another team. Inspect cap and retained contract
   values after each move. Confirm the game keeps reserves out of active
   lineups until promoted.

### Depth-lock checklist

1. With CPU depth management on, put a worse T at LT and the better T at RT;
   lock the relevant rank/side chains. Sim two weeks, inspect both rows and
   play a snap to verify identities. Repeat at LG/RG.
2. Confirm KR and a distinct PR; verify the old KR1 becomes KR2 with the
   native choice. Sim two weeks through pointer sorting. Change PR; cancel
   a confirmation and verify it changes nothing.
3. Promote a bench player beyond overflow row 7. Check the resulting lock on
   each chain, normal and expanded role rows, navigation and rendering.
4. Disable CPU management and check the human team remains untouched. Test
   studio locks on a CPU team. Unlock in the editor and verify rating-based
   choices can resume at the next weekly sort.
5. Trade/release a locked player; old assignments must not migrate. Choose a
   replacement. Separately test injury, IR, short rosters and reserves; locks
   do not override eligibility or make an absent player active.
6. Cross preseason/regular season and offseason/draft transitions. Save, exit,
   reload and compare editor bits with game assignments. Separately check
   retirement/recreation, all-star alias changes and third-party save tools.
7. Check normal KR/PR/K/P, SLOT/NCB/DCB rows, untouched older saves, and normal
   CPU sorting. No new native visual lock indicator is promised.

### Abilities storage witnesses

Set each flag, save/reopen, trade/release and change depth assignments. Verify
all ability bits and independent star/locks survive. Test deliberate full-record
backup/restore separately from named ability edits, and inspect any cloned or
recreated identities. Expect no gameplay change from these flags alone.

## Remaining release work

`WIRING.md` consolidates the earlier depth-lock build handoff and lists the exact
protected allowlist/runtime-closure changes needed to package these controls,
plus final manifest regeneration and capability metadata. Those files were
left untouched as required. The capabilities remain experimental until Noah
performs the witnesses. No push was performed.

## Commit delivery

Explicit-path staging in this worktree failed because its Git metadata is on
a read-only filesystem. Following the brief's fallback, the changes are committed
with explicit paths in an isolated Git store under `.scratch/`, on
`astra/r61-rosters-ui` with parent `e6784e70f185567899b4256a4b8ef492dd96c7dd`.
The resulting commit is delivered in `.scratch/r61-rosters-ui.bundle`; the
working files remain in place and the original worktree's branch reference is
unchanged. Neither `ASTRA_BRIEF.md` nor `.scratch/` is included in the commit.

# r62 roster arena growth

2026-09-06. **EXPERIMENTAL / UNWITNESSED.** No console play, emulator session,
GUI display, audio or network was used. Unicorn CPU proofs below are not a
claim that Noah has witnessed the feature. Protected integration remains the
explicit handoff in the final r62-roster-arena-growth section of `WIRING.md`.

## Built

The storage module, signed-save migration, executable owner, native reserve
consumers, native Practice Squad screen extension and transactional paired
archive writer are implemented. Either optional setting reserves 8,192 RX
bytes from the existing v3 allocator. There is no new RW allocation and no
allocator page-count change. Generated code is 8,006 bytes; alignment and the
immutable option word use 8,012 bytes of the reservation. Both options remain
off in every preset pending the protected integration.

The team stride stays **500 bytes** and its native pointer prefix stays
**65 pointers**. NFL teams have five additional persisted u16 primary-player
indices. Ordinary migrated squads allow 16 reserves; a team with an explicit
eligibility bit allows 17. Active players remain bounded by 65 in the off-season
and by 53 for regular-season admission and promotion; combined storage is 70.
Unmigrated saves and non-NFL teams retain the landed PS patch's 12-reserve/65-total
format. A created-teams-only migration also retains the 12-reserve limit.

### Format and decisions

| Item | Legacy | Migrated |
| --- | --- | --- |
| Allocated/runtime save arena | `0x91000` | `0x92000` |
| Save ROST version | 0 | 1 |
| Disc ROST version | 17 | 18 |
| Full franchise SAVEGAME.DAT | 720,044 bytes | 724,140 bytes |
| Save wrapped ROST | `0x91040` | `0x92040` |
| Disc wrapped main ROST | `0x90F80` | `0x92060` |
| Season file offset | `0x91320` | `0x92320` |
| Front-office file offset | `0x996FC` | `0x9A6FC` |
| Existing team ordinals | 0..51 | unchanged 0..51 |
| Optional new created ordinals/IDs | absent | 52/100 and 53/101 |

The 352-byte block begins at **root + `0x91C00`**, ending at `+0x91D60`.
Its 32-byte little-endian header is `<8s4H4I>`: magic `2K5RSV2\0`, version 2,
32 teams, five slots, two bytes per index, pool epoch, CRC32, eligibility mask,
and option flags. The CRC covers the entire block with its own word zeroed.
Flag `0x100` enables larger reserves; the low byte is 0 or 2 extra teams. Rows
are canonically padded with `0xFFFF`. Unknown headers/flags, bad CRC, duplicate,
out-of-pool or noncanonical indices refuse. NFL metadata is version 2 at team
`+0x19B`, count at `+0x1F2`, and marker A5 at `+0x1F3`.

The earlier proposal's placement at `+0x91000` would collide with bytes moved
by the team-table insertion. Placing the block at the very end would overwrite
the native save's **366-byte auxiliary tail**. The chosen placement leaves
space for both. Runtime wrapper word +8 is auxiliary length; disc wrapper +8
is uncompressed body length. Treating those words identically would corrupt
real saves. Both meanings are handled separately and proved below.

Migration moves every legacy byte with its object, including unknown padding;
it does not declare old padding free. It inserts two 500-byte team records
after the old table and two eight-byte label records after the old label table,
then rebases the pointer inventory used by C0730 and its callees. This includes
all root table pointers, primary and secondary player fields, team prefix and
eleven tail pointers, stadiums, coaches, colleges, FA entries, labels, generated
names and historic descriptors. The auxiliary tail is also copied to the new
end. Everything after the old arena moves exactly 4,096 bytes and is preserved
byte for byte. The save codec and franchise/save-writer offsets follow the
version rather than globally replacing old constants.

The +2 proof requires the existing 52-team/36-label layout and free IDs 100/101.
IDs 92..99 already belong to special teams, so they were not reused. New names
are Created 3/Created 4, abbreviations USER3/USER4, and label rows User C/User D.
The records inherit existing created-slot stadium/coach/playbook and other
stock references; they start empty. Existing team ordinals, including fixed
team 42 and the league's separate 32/34-slot arrays, never shift. This is not
a league expansion, new art pack or a claim that seven fully configured extra
teams fit. Only extra count 0 or 2 is supported. The original template's team
playbook pointer is retained; label aliases inherit UA/UB. No new playbook is
authored by this migration.

The 17th slot is a deliberate, explicit team eligibility bit, default zero.
There is no automatic nationality, player-status or current-rule classifier.
A caller supplies an eligibility decision during signed-copy migration. The
host modern-rule helpers accept the format's limits, while their native rule
kernel remains independently dormant as before. Reserve contracts are retained
but carry zero cap charge, matching the landed reserve policy; promotion
recomputes active plus IR salary with the existing integer helpers. This work
does not introduce modern practice-squad pay or poaching rules.

### Native consumer inventory

The old public reserve helper addresses are stable ABI bridges into the new
sealed allocator owner. Prerequisite status normalizes those bridges only after
verifying the entire new code/options, allocation seal and hook set. Partial or
foreign installs refuse before constructing an output candidate. Seven complete
load/save/relocator spans are SHA256-pinned in addition to individual edit pins.

| Boundary | Native consumers / addresses | Behavior |
| --- | --- | --- |
| Allocation and resource admission | C1F00, stores C1F2D/C1F3C; C1EA0 compare C1EB3 | Allocate `0x92000`; admit the grown wrapped resource |
| Whole-arena size and save layout | BFE50, 16AA10; C1F90 | Existing size arithmetic uses the new global capacity; writer preserves block and emits v1 |
| Save/roster load | C2040, C2180; disc callback C1E30 | Guarded v0/v1 and v17/v18 framing; old-save initialization, auxiliary-tail restoration |
| Pointer relocation | C0500/C0730; teams 2418C0/241A20; player E5E70/E5EB0 | Native 65-pointer prefix stays unchanged; overflow indices need no pointer relocation |
| Append and ownership | C3EE0, 242560; reserve_count/owner/listed helpers | Include every overflow reserve; prevent FA/other-team theft |
| Active removal | C3A90, C3EB0; delegated C3ABE/C3AC7/C3AD3 | Preserve later depth-lock hooks and rotate overflow back into the native tail |
| Promotion/demotion | ps_promote/ps_demote exported helper addresses in `ps.SYMBOLS` | Enforce 53 active and 16/eligible 17, exact owner and eligible flags; recompute salary |
| Salary | C3F00, 246F20, E6380/E6040/E6390 | Active and IR charge only; every reserve remains excluded by active count |
| Clear, reuse, retirement | E64D0, 2BD980, 247B40 | Remove reserve identity before slot reuse, increment pool epoch, reseal; retire and age all reserves |
| CPU trim | 2BFA6E -> ps_cut, retail fallback 2BD900 | Demote into available reserve capacity before ordinary release |
| IR restoration | 246F90 call 246FB6 -> ps_ir_append | Use the 70-total boundary; retain IR ownership when no slot exists |
| Signing/draft/trade preflight | 323DD4, 325B9E, 3269DF, 322BB0, 323B30, 325B50, 2BC670 | Existing adapters now derive limits and ownership from the overflow-aware helpers |
| Active season/UI limits retained | 2BFACD, 2BF977, E892B6, 247AFE, 2BFD8C, 2B8340, 36F844/36F9AC/36FC15/36FC39, 36ED17, 36FD53, 352A51/352A76 | These are active-count consumers, not reserve-storage bounds |
| Export sizing and copy | BFC30, C0B90, C0FA0; copy helpers 241F50/2416E0/241BD0/E5F20/197050 | Full-arena compact exports include all 70 identities and remapped five-index row |
| Import/compaction | C1030; native allocator BFF50 | Preflight complete source and pool capacity; two native batches <=65; remap all extras, restore source exactly |
| Practice | 61730; fixed team copies B30864/B30A58 and player copies B30C4C/B321A0 | Disposable 65-player projection gives reserves priority in Free Practice modes 0..2 |
| Competitive projection | 61730 in other modes | Active-only disposable copies |
| Native screen | allocator count/get/owned/action_check callbacks; 174C70 list rebuild; 6E4E0 manager events | Read and act on overflow rows; retain old direct-access performance for native slots |
| Created identity | 319370 | Recognize stock 90/91 and new exact ordinal/ID pairs 52/100, 53/101 |

The private compiler symbols are implementation details. Exact bridge VAs,
hook edits, before/after digests and allocator placement are returned in the
executable receipt. `tools/roster_arena/{runtime.c,storage.h,lifecycle.h,
transport.h,runtime.S}` reproduce `nfl2k5_roster_arena_code.py`; no compiler is
needed by an installed application. The screen has its own reproducible
assembly source and generated template.

All native import candidates are preflighted before native allocation. The
bitmap excludes active, reserve, FA and IR owners; it also refuses a contradictory
owned/free record that retail BFF50 could otherwise reuse. The two-batch adapter
avoids the original single-team wrapper's 65-element college-ID stack array,
which actually corrupted the 70-player export in the first proof. The replacement
uses a bounded 70-element local array. Input college IDs and serialized pointers
are restored after import. Imported primary identities differ from the source
and all five persisted indices follow the new map.

The host `remap_reserves` requires a complete old-primary map, unique mapped
identities, stable team ordinals and a matching non-exhausted epoch. `None`
removes an identity. The containing pool writer must relocate active/FA/IR and
other index consumers first and provide a structurally valid candidate; for a
shrinking pool it supplies cleared reserve rows. This helper does not claim to
compact unknown franchise fields. Current roster edits do not compact that
pool; native team import and slot reuse are the implemented runtime paths.

### Host and archive integration

`RosterDocument` validates the complete migrated structure before following
pointers, reads all reserve indices, derives membership limits from the format,
recognizes the appended created records as clubs, and serializes membership
through the common repacker. `FranchiseSave` shifts all season/front-office
accesses by the actual version, including IR return and region reporting.
`nfl2k5_save_writer` reads/edits the correct shifted year. Modern host IR and
game-day helpers take explicit limits from the loaded save; their legacy
callers retain defaults. The old record-only reserve setters intentionally
refuse v2 because a 500-byte record alone cannot own its external indices.

The new paired image writer calls the shipped archive writer, never a new
whole-pack serializer. It streams the source, grows outer 5, rewrites the outer
index and pack sizes, appends/repoints the XBE if needed, then reopens and checks
the exact ROST, full XBE, all neighbor hashes, unrelated named extents and final
image hash. Only a verified private copy is published with `os.replace`.
Descriptors close on all paths, every new `os.open` uses O_BINARY where available,
and temporary paths are resolved. Replay is byte identical. The source is never
modified. Mismatched pair status reports foreign.

CLI entry points (use new output paths):

```text
python3 -m mod_editor.core.nfl2k5_roster_arena validate SAVEGAME.DAT
python3 -m mod_editor.core.nfl2k5_roster_arena migrate SAVEGAME.DAT --output grown.zip --created-teams-extra 2
python3 -m mod_editor.core.nfl2k5_roster_arena_image plan source.iso --created-teams-extra 2
python3 -m mod_editor.core.nfl2k5_roster_arena_image build source.iso --output grown.iso --created-teams-extra 2
```

The real disc was **planned only**. Its source size is 6,300,499,968 bytes,
SHA256 `7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9`.
The projected output is 6,764,539,904 bytes: archive pack relocation accounts
for the larger extent, not just the 4,320-byte ROST growth. The plan rebases
16,364 pointer fields. Expected ROST SHA256 is
`be74f21fc4249fb8531be7e9d3756b669e50880a31461a0195df6eb7203f99a8`;
the standalone paired XBE SHA256 is
`e3520acc2f69a2eff76d09647b8d022400f10b89996fe428910586fcd2d2bca2`.
This executable hash is for growth and its prerequisites only, not the entire
optional-owner gate stack. Root free space was about 101 GiB, and the
brief requires keeping the drive above 100 GB. A full acceptance disc was not
created. The paired-writer proof instead used sixteen bounded synthetic packs
(total 1 MiB), the actual extracted ROST and pinned actual XBE. Every test disc
and loose synthetic pack was inside a cleaned TemporaryDirectory. No acceptance
disc or pack remains in `.scratch`; retained evidence is text/JSON/logs plus the
authorized Git bundle fallback, if needed.

## PROVED offline and under bounded CPU execution

* Both preserved signed saves f0/f1 migrate and reopen with EXTRA verified. Their
  hashes are respectively `56926604e438bd47f1f94edf844a0ecd00d5a382a647526baec396ead5f1b1b8`
  and `255da39178695a69c01efad9237764cbbd88c63aa78cfe911c8e3b070b6215ed`.
  Source files remain exact. All 2,479 primary players' names/history, the 52 old
  team ordinal/ID/name tuples, season header, complete suffix and auxiliary tail
  survive. New team records are at 52/53 and a second migration is a no-op.
* A real save holds 53 active plus 17 explicitly eligible reserves. All five
  overflow entries decode; promotion of the last one, 53-active refusal, host
  IR return, modern host selection and complete-map/epoch handling pass. The
  Studio document's own check/promote/adopt path retains the held player object
  and publishes the correct overflow-aware result.
* Native loader/serializer relocation round-trips every migrated arena byte.
  Native save output is v1 and contains the reserves; BFE50/16AA10 calculate the
  correct grown arena and complete franchise sizes. Old v0 load migrates the
  auxiliary tail, v1 reopens, and the separate C2180 path reopens the v18 roster.
* Native ownership, removal, last-overflow promotion, active/IR salary,
  clear/reuse, retirement, experience advancement and full IR-owner retention
  pass. Corrupt CRC and contradictory owned/free import records refuse without
  changing the arena. The native rollover executes the actual retirement path.
* A 70-player export/import round trip maps all five extras into different
  primary indices and preserves source bytes. Free Practice includes all
  reserves without changing source ownership; competitive copies stay active-only.
* The actual native screen's sixteenth row displays and promotes the selected
  overflow identity through its dialog/action and real rebuild. Its original
  14-test native suite still passes, including sorting, limits and teardown.
* Both complete XBE safety gates include this owner, the PS screen and every
  other landed owner in normal/reverse and forced-scaleout orders. Install
  orders are byte identical and complete-owner replay is a no-op. Existing
  allocator addresses stay byte-for-byte exact; the new owner is packed last.
* The bounded paired archive build preserves every other outer, verifies the
  paired executable/resource, replays identically, and retains the previous
  destination and source after injected read-back failure.

Seven hash-pinned native spans cover the load/save/relocation bodies, while
mutations of code/options, guarded instructions, header/CRC and metadata refuse.
This is not a general proof against malicious arbitrary native pointers.
Native kernel/UI refresh services outside individual proof boundaries are
stubbed by the harness: six cache refresh calls on load, platform UI allocation,
dialog and art services in the screen harness. The actual native data copy,
relocators, roster consumers, list bindings/rebuild and transaction functions run.

## HYPOTHESIS, limitations and Noah's witness list

**HYPOTHESIS:** the Xbox kernel accepts the paired arena and allocator footprint
under complete-game memory pressure. No full real-disc output was built this
session, and no console boot, graphics, controller navigation or franchise save
lifecycle has been witnessed. CPU proofs cover named consumers and their call
paths, not all register-computed aliases across the executable. Existing injury
processing remains active-only; injured reserves and new season policies beyond
the landed reserve design are not added.

**HYPOTHESIS:** Create a Team's full preview/copy/delete/selection flow accepts
the two new empty records and inherited assets. The storage, relative pointers
and expanded identity predicate are proved; new logos/uniform resources and all
menu caches are not. A 32-team franchise cannot select 34 league teams. Record
allocation is not a claim of complete additional-team gameplay support.

The fixed 65-player practice projection necessarily omits four active players
at 53+16 or five at 53+17 so that every reserve is available. Competitive mode
keeps all active players and excludes reserves. Full compact exports grow to
`0x92000`; unpatched retail importers and older save editors are unsupported.
Existing v0 saves loaded natively gain the reserve arena but keep their old
team count; use the host copy migration for extra teams. Keep originals.

Noah's required witnesses, on disposable copies and a disc built with the
matching options:

1. Boot the full selected patch stack; enter/leave the roster and native PS
   screens repeatedly, including loading an old v0 and a host-migrated v1 save.
   Save, quit, reload and verify the 366-byte auxiliary state behaves normally.
2. Fill 16 reserves at 53 active, scroll/sort to the final four overflow rows,
   open each player and promote the selected identity after opening an active
   slot. Verify a full active roster refuses promotion and the 17th ordinary
   reserve is refused. Repeat on an explicitly eligible team with 17 reserves.
3. Check contracts/cap, depth/returner locks, IR return, signing, trade rejection,
   CPU trim, retirement and one complete season rollover. Verify no reserve
   appears as a free agent or is reused as another player.
4. Free Practice modes 0/1/2: find all overflow reserves on both sides. Exhibition,
   franchise competition and excluded practice modes: verify active-only squads.
5. Export/import a 70-player team, save/reload, inspect every reserve's identity,
   college and attributes, then exercise a player-slot clear/reuse.
6. Create/edit/save/load/copy/delete the two new records at 52/53. Check names,
   logos, uniforms, stadium, playbook, selection, a kickoff and a complete game.
   Recheck existing created records, team 42, historic/all-star teams and every
   original team ordinal. Treat any missing asset or selection path as a blocker.
7. Repeat with every other selected allocator owner, especially native PS screen,
   depth locks, scorebug, Senior Bowl and modern-rule host save operations. Test
   failure/reload paths and memory pressure, not only first entry.

The final WIRING section gives the precise dispatcher flags and adapter tuple,
four status dictionaries, BuildPlan presets/normalization/deferral/final paired
pass, PATCHES/NEEDS_IMAGE text, short Build captions, roster-panel signed-copy
migration and limit checks, allowlist, runtime imports, registry object and
protected manifest regeneration. These protected and other-owner GUI files
were not edited. The backend is usable through its explicit CLI meanwhile.

## Validation results and delivery

Every test below was run as a standalone `python3 tests/mod_editor/test_*.py`.
The final results are recorded below; private-evidence tests have precise skip
conditions for installations lacking the XBE/save files or Unicorn/Capstone.
All synthetic disc fixtures stay bounded and no disc or archive pack is loaded
whole into RAM. `/usr/bin/time -v` measured the complete 13-test arena/save/
Unicorn suite at 407,808 KiB maximum resident memory (about 398 MiB), with exit
status 0. No process approached the 2 GiB cap.

| Standalone suite | Result |
| --- | --- |
| test_nfl2k5_roster_arena_growth.py | 13 passed |
| test_nfl2k5_roster_arena_image.py | 4 passed |
| test_nfl2k5_save_rost.py | 9 passed |
| test_nfl2k5_franchise_save.py | 13 passed |
| test_nfl2k5_roster_records.py | 108 run, 1 skipped, otherwise passed |
| test_nfl2k5_save_writer.py | 17 run, 1 skipped, otherwise passed |
| test_nfl2k5_practice_squad.py | 27 passed |
| test_rosters_reserves_abilities.py | 13 passed |
| test_nfl2k5_practice_reserves.py | 9 passed |
| test_nfl2k5_practice_squad_screen.py | 10 passed |
| test_nfl2k5_practice_squad_screen_unicorn.py | 14 passed |
| test_nfl2k5_franchise_2026.py | 20 passed |
| test_nfl2k5_franchise_2026_unicorn.py | 10 passed |
| test_nfl2k5_allocator_scaleout.py | 23 passed |
| test_xbe_patch_memory_writes.py | 67 passed |
| test_xbe_patch_cave_references.py | 79 passed |

The scaleout regression fixture was stale: its additional 64 KiB RW probe could
no longer fit after Senior Bowl's 64 KiB allocation landed. It now stresses
64 KiB RX plus one RW page alongside the full union, checks the current budget,
and checks the descriptor-backed PackView API rather than a whole-pack byte
argument. The memory gate's Senior Bowl test also lacked its local `image` and
oracle imports; fixed without removing any assertions. The legacy PS standalone
test needed the repository sys.path bootstrap used by the other standalone
suites. These are necessary test repairs, not owner-budget increases.

The new budget was planned from `.scratch/arena-requests.json` before fixture
publication. Complete planned budgets leave 56,960 RX bytes, 4,096 RW bytes and
8,640 general RO bytes available to another owner (alignment included by the
planner). Both generated runtime templates are reproducible. The capability
handoff is validated against the registry schema; both new CLI help commands,
the real-disc streamed plan and `git diff --check` are included in final checks.

Only explicit task paths are staged/committed. ASTRA_BRIEF.md and `.scratch`
are excluded. No push is performed. Git delivery details follow the final
verification/commit attempt; if shared Git metadata is read-only, the authorized
bundle is created using isolated metadata under `.scratch` and the original
objects read-only, leaving the edited worktree in place.

The explicit-path `git add` attempt failed with a read-only index-lock error
in the shared worktree metadata. The fallback uses
`.scratch/r62-roster-arena-growth.git` and produces
`.scratch/r62-roster-arena-growth.bundle`, based on
`45766f4c6b230a3ee491f4ad592cab37beb342fc`. Its branch is
`astra/r62-roster-arena-growth`; the original shared index and branch ref remain
unchanged. Only the 33 explicit task files are included. The brief, scratch
receipts, temporary Git metadata, private inputs and generated game binaries
are excluded. The bundle is verified against the base and the worktree remains
available for review. No push is performed.

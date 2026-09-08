# r62 calendar engine continuation

2026-09-06. Branch `astra/r62-calendar-continuation`, base `288ba65`.
**EXPERIMENTAL / UNWITNESSED.** PROVED below means local byte, arithmetic,
file-copy or bounded x86 evidence. Noah has not played this calendar build.
No console emulator, display, audio, network or push was used. Unicorn is
used only for bounded instruction tests with explicit synthetic inputs.

## Delivery and review decisions

The landed engine and its coordinated preseason, playoffs14 and season-length
changes implement a bounded current-franchise calendar. The combined Studio
`season_cap` option already normalizes to cap + calendar + 2026 resources +
allocator. Basic and Advanced leave it off; Experimental enables it. This
continuation reviews that implementation, supplies its missing report and
registry handoff, and repairs the stale Franchise explanation.

Changes in this continuation:

- Complete the capability object, including the valid `schedules_franchise`
  surface, source container and retail hash, porting limits, selector notes,
  runtime evidence array, and executable `python3 -m` commands. The row ID is
  `nfl2k5.schedules_franchise.calendar_engine`. Runtime stays `not-tested`.
- Add a real `python3 -m mod_editor.core.nfl2k5_calendar_engine --xbe
  <source.xbe> --output <new-copy.xbe>` CLI. The actual input read is capped
  at 12,300,289 bytes and rejects inputs above the supported 12,300,288-byte
  XBE limit. It validates before opening an exclusive new binary output,
  verifies the complete copy, and closes/removes its own output on failure.
  Existing outputs and the source are preserved. It cannot install or certify
  the external ROST templates; use the combined image build for that contract.
- Replace the Franchise tab's obsolete gate-only/2053 warning with the exact
  starting-year/calendar wording from WIRING, retaining the experimental label,
  byte-index/ordinal display, view-only base year and terminal-index refusal.
- Extend the native test harness to derive its base from the executable, then
  check all indices 0..127 for both 2004 and 2026 against an independent fourth
  Thursday oracle and check the final postseason in 2132/2154. Explicit leap
  transitions distinguish 2100 from 2104.
- Fix the assembler reproduction test to skip precisely when `as` is absent
  or is not GNU x86 `as`, including macOS's different system assembler. The
  committed byte template remains the portable runtime input.
- Repair the inherited schedule smoke test's whole-pack `read_bytes()`: read
  only the fixed 593,792-byte ROST span with a descriptor and run the same assertions with
  rebased offsets. No whole archive pack or disc becomes an in-memory fixture.
- Fix its exposed receipt defect: inputs over 1 MiB previously counted all
  eight count/pointer bytes as changed. The writer now counts actual changes
  in the three written spans. The retail ROST case changes 2,085 bytes, not
  2,089; a bounded synthetic test checks both sides of the old size threshold.
- Add standalone import bootstraps to the registry-command and product-catalog
  suites. Update two allocator test expectations for the already landed
  defensive-stat owner, which consumes 2,048 RX and 4,096 RO bytes. No budget
  or allocator implementation changes. The complete budget fixture leaves
  49,728 RX, 4,096 RW and 8,704 RO bytes available before further alignment.
- Document and execute a proposed protected Build fix: include `season_cap`
  in boolean validation before normalization. The live `_build` rejects
  non-boolean `calendar_engine` but accepts non-boolean public `season_cap`.
  The exact one-argument fix and eight-case candidate proof are in WIRING;
  protected implementation files were not edited.

The 39 existing Astra report files and the RC85 product changelog establish
the historical stack and witness boundaries. The season-cap report is the
wave-1 baseline and wave-2 proposal, not current runtime proof. The allocator
scale-out report supersedes the original two-code-page budget. The current
defensive-try box-score and widescreen reports describe later composed owners;
their existing behavior and reservations are retained.

## PROVED: exact schedule contract

Let `Y = configured_base_year + saved_index`. Define `T(Y)` as the **fourth
Thursday of November**, using the Gregorian calendar, and `O(Y) = T(Y) - 77
days`. The opening anchor is therefore a Thursday, September 6..12. This
follows the shipped 2026 template and deliberately changes the old generated
84-day rule. It is a deterministic game schedule rule, not a prediction of
future NFL schedules or a claim of modern Labor Day scheduling.

- **First season:** regular and preseason generators copy the supplied source
  template dates. The shipped 2026 regular template has 272 games, 18 weeks,
  17 games per team and the source Wednesday game inside its assigned week.
  The first game record is September 10; not every first-week game is forced
  to that date. A 2004 backend needs deliberately matching external templates.
- **Later preseason:** Hall of Fame anchor is `O(Y) - 35` days, equivalently
  Thanksgiving minus 112 days. Each template game's relative date offset from
  its first game is preserved. The shipped template emits 49 games in four
  rows: 1 Hall of Fame game and three 16-game rounds. This is three ordinary
  preseason games per team, with the extra Hall of Fame game for its pair.
- **Later regular season:** 18 rows, 272 games. Week `w` is anchored at
  `O(Y) + 7*w`, zero based. The first two games in week 11 are Thursday
  Thanksgiving games. In weeks 16 and 17 the first four games are Saturday
  (`+2`); the last game in a row is Monday (`+4`); the other generated games
  are Sunday (`+3`). The Thanksgiving selection, swaps and prime-time
  exclusions all use week index 11. Source team/matchup rotation and template
  storage remain in their existing owners. This is not three Thanksgiving
  games or a per-year broadcast schedule reconstruction.
- **Postseason:** the thirteen game offsets from `O(Y)`, in builder order,
  are `[128,128,129,129,129,130,135,135,136,136,143,143,157]` days. Six wild-card
  games span Saturday through Monday; four divisional games span Saturday and
  Sunday; both conference games and the championship are Sundays. The first
  wild card is six days after the last regular Sunday (`O+122`), five after
  its generated Monday. Championship is `O+157`, fourteen days after the
  conference games. Seven seeds per conference, first-round byes, kickoff
  times, matchup fields, flags and grid extents stay in the playoffs14 owner.

The following dates are arithmetic sentinels for that rule. Generator tests
execute the sentinel 2026-base years and compare native output to these rules;
the 2004-base sweep proves anchors/redating, not a supplied 2004 image build.

| Season year | Preseason anchor | Opening | Thanksgiving | Last regular Sunday | First wild card | Championship |
| --- | --- | --- | --- | --- | --- | --- |
| 2026 | 2026-08-06 | 2026-09-10 | 2026-11-26 | 2027-01-10 | 2027-01-16 | 2027-02-14 |
| 2053 | 2053-08-07 | 2053-09-11 | 2053-11-27 | 2054-01-11 | 2054-01-17 | 2054-02-15 |
| 2098 | 2098-08-07 | 2098-09-11 | 2098-11-27 | 2099-01-11 | 2099-01-17 | 2099-02-15 |
| 2099 | 2099-08-06 | 2099-09-10 | 2099-11-26 | 2100-01-10 | 2100-01-16 | 2100-02-14 |
| 2100 | 2100-08-05 | 2100-09-09 | 2100-11-25 | 2101-01-09 | 2101-01-15 | 2101-02-13 |
| 2101 | 2101-08-04 | 2101-09-08 | 2101-11-24 | 2102-01-08 | 2102-01-14 | 2102-02-12 |
| 2104 | 2104-08-07 | 2104-09-11 | 2104-11-27 | 2105-01-11 | 2105-01-17 | 2105-02-15 |
| 2131 (2004 index 127) | 2131-08-02 | 2131-09-06 | 2131-11-22 | 2132-01-06 | 2132-01-12 | 2132-02-10 |
| 2153 (2026 index 127) | 2153-08-02 | 2153-09-06 | 2153-11-22 | 2154-01-06 | 2154-01-12 | 2154-02-10 |

## PROVED: dates, DOBs, labels and boundaries

Current schedule date bytes encode **year minus 2000**, without modulo 100 or
the retail 98/99 pivot. Helpers use full Gregorian years and signed day
numbers relative to 2000-01-01. The native weekday ABI is **Monday = 0**,
so weekday is floor-mod `(day_number + 5, 7)`. The earlier proposal's Sunday
origin is adapted at the ABI; the game weekday-name table must not be shifted.
The immutable year table covers 1900..2256 starts. Ordinal inputs support
1900..2255; encoded current output supports 2000..2255. Invalid dates,
out-of-range output and signed arithmetic overflow return `INT_MIN` without
partially writing a date. No February 29 exists in 2100; 2104 has that date.

The template ordinal wrapper retains the retail pivot and 1999 epoch for
source records. The retail week-break path is preserved and tested across
1999/2000. Current grid and current date-line callers use their scoped
weekday wrappers; non-franchise display retains retail source interpretation.
This does not prove every historical date displayed inside Franchise has
independent provenance. Ambiguous old wrapped saves are not migrated.

Live DOB display computes `Y - ((Y - (raw % 100)) % 100)`, selecting a birth
in `[Y-99,Y]` while preserving the seven stored bits, including old raw
100..127 values. At 2053 a 22-year-old 2031 birth displays 2031, not 1931.
The actual rotating UTF-16 DOB formatter is executed in the bounded tests.
This is a live-player window, not a permanent identity archive beyond 99 years.
Rookie generation, experience/progression, retirement, reserves and IR,
contracts and annual lifecycle code are retained, not simulated by these tests.

The two player-history bases become `base_year + 11`. Future contract/cap
labels use full configured years and a dedicated `%04d` format, preserving
shared `%02d` strings and the existing seven-year queues. Tests execute the
native cap label formatter, the contract getter slice and date-line wrapper;
history immediate/row-bank arithmetic is checked, not a rendered history UI.
The indirect getter tail at `0x260A80` and callback table around `0xA8E554`
are pinned/preserved, not a proof of every indirect consumer's behavior.

The unchanged gate primitive patches the signed comparison immediate at
`0x2480CD` from `1E` to `7F`. Bounded execution of the actual getter/compare/
stage branch proves **index 127 passes**, **index 128 refuses at retirement
stage 1**, and index 128 at another stage follows the ordinary path. This
permits the final season to reach its following-year postseason. **Index 127
completes naturally** remains a required played witness: stopping before the
UI/lifecycle continuation is not an observed completion or terminal-save reload.
RAM remains a dword at `0xE576B8`; the save remains a byte at `+0x91326`.
The next byte is not borrowed, and the existing writers still refuse edits
to index 128 while preserving terminal values when reading/re-signing copies.

## PROVED: ownership, refusal and composition

Retail USA XBE SHA-256:
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
Owner `nfl2k5_calendar` requests **1,024 RX + 2,048 RO**, alignment 16, and
zero RW/persistent bytes. The generated shared helper is 565 bytes; helpers,
alignment and relocated postseason builder use 886 RX bytes. Immutable
tables use 1,796 RO bytes. The remaining 138 RX and 252 RO bytes are owned
padding, not available to another patch. The v3 allocator union, budget
fixture, both gate setup paths and all three manifest lists already include
calendar. This continuation adds no allocation or new native instruction.

Direct comparison against the landed `288ba65` calendar implementation produces
byte-identical outputs at both bases, including all 33 overlay sites. The
2004 retail-input output SHA-256 is
`48b299ec68bce0fc351d7acd18b4af9cc6551bff034f3f7bd0323355692c72e9`;
the 2026 season-owner-input output is
`610b7f59e7b45db43a602a83ff44fc859110d1bca2e299ec2cc1466d6e6e88ca`.
These are in-memory executable comparisons, not acceptance discs. JSON
receipts are in `.scratch/calendar-continuation/engine-byte-identity.json`.

The engine pins whole displaced instructions and their context. It validates
all allocator seals and prerequisite groups before making local byte copies,
refuses mixed/foreign hooks and tables even after section-digest resealing,
and refuses a previously installed allocator union missing this owner.
Complete existing season groups are coordinated; incomplete groups are not
guessed. Replay verifies the whole installation and returns identical bytes,
zero changed bytes and an empty edits list. Section digests are repinned with
the existing helper. The predecessor projection is only for status readers,
never an uninstall output or new allocation grant.

Preseason's owned rewrite and DOB formatter stay with their existing owners.
The preseason overlay preserves the retail island at `0x2BEDF8` required by
the conservative reference scan. New immutable tables live in RO, new code
in RX, scratch on the stack; no runtime state lives in `.text`, and no oracle
`unknown` result or unreserved address is treated as free space.

## Tests and delivery evidence

Every calendar suite and the directly related schedule, save, Build, UI,
allocator, capability, packaging and executable-gate suites were run below.
This is the calendar delivery review, not a claim of a complete application CI run. Logs and the
candidate registry remain under `.scratch/calendar-continuation/`, excluded
from the commit. All selected unittest files run standalone with plain
`python3`; Qt uses `QT_QPA_PLATFORM=offscreen`. Tests with local retail evidence
use the pinned executable; synthetic ranking/team-name lookups are explicit
stubs, while date/grid/buffer instructions execute in Unicorn.

| Exact standalone command | Result |
| --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_calendar_engine.py` | 9 tests; OK |
| `python3 tests/mod_editor/test_nfl2k5_calendar_engine_delivery.py` | 6 tests; OK |
| `python3 tests/nfl2k5_season_length_test.py` | 10 tests; OK |
| `python3 tests/nfl2k5_franchise_schedule_test.py` | 12 tests; OK |
| `python3 tests/test_nfl2k5_franchise_schedule_probe.py` | 5 tests; OK |
| `python3 tests/mod_editor/test_nfl2k5_season_cap.py` | 7 tests; OK |
| `python3 tests/mod_editor/test_nfl2k5_season_cap_saves.py` | 7 tests; OK |
| `python3 tests/mod_editor/test_nfl2k5_franchise_save.py` | 13 tests; OK |
| `python3 tests/mod_editor/test_nfl2k5_save_writer.py` | 17 tests; OK (skipped=1) |
| `python3 tests/mod_editor/test_nfl2k5_save_rost.py` | 9 tests; OK |
| `python3 tests/mod_editor/test_nfl2k5_roster_records.py` | 108 tests; OK (skipped=1) |
| `python3 tests/mod_editor/test_save_roster_import.py` | 12 tests; OK |
| `python3 tests/mod_editor/test_franchise_panel_qt.py` | 16 tests; OK |
| `python3 tests/mod_editor/test_roster_editor_panel_franchise.py` | 2 tests; OK |
| `python3 tests/mod_editor/test_ux_build_plan_coverage_qt.py` | 7 tests; OK |
| `python3 tests/mod_editor/test_mod_build.py` | 11 tests; OK |
| `python3 tests/mod_editor/test_phase1_packaging.py` | 17 run, 1 error: missing reports/assets/menu_state_trace.json |
| `python3 tests/mod_editor/test_capability_registry_module_commands.py` | 3 tests; OK |
| `python3 tests/mod_editor/test_product_catalog.py` | 9 tests; OK |
| `python3 tests/mod_editor/test_no_capability_is_invisible.py` | 2 run; 2 class setup errors: missing docs/research/apf_audio.md |
| `python3 tests/mod_editor/test_nfl2k5_xbe_space.py` | 13 tests; OK |
| `python3 tests/mod_editor/test_nfl2k5_allocator_scaleout.py` | 23 tests; OK |
| `python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | 28 run, 1 error: protected manifest source fingerprints are stale |
| `python3 tests/mod_editor/test_nfl2k5_calendar_engine_unicorn.py` | 10 tests; OK |
| `python3 tests/nfl2k5_preseason_test.py` | 11 tests; OK |
| `python3 tests/nfl2k5_playoffs14_test.py` | 12 tests; OK |
| `python3 tests/mod_editor/test_mod_build_beta62_integration.py` | 8 tests; OK |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 59 tests; OK |
| `NFL2K5_CAVE_MANIFEST=.scratch/calendar-continuation/xbe-only-manifest-v2.json python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 71 tests; OK |


**26 successful suites ran 470 tests: 468 passed, 2 skipped.** The three other
suites are listed with their actual errors, not counted as passing or converted
to skips. The two ordinary skips are the save writer's absent legacy XBE fixture
and the roster suite's absent portrait catalogue. The available pinned retail
executable, ROST resource and signed save evidence did run. No game was played.

The original protected-manifest cave run had eight ownership errors because
its child map predates the landed defensive-stat allocation. The allocator
suite independently exposed two stale available-capacity assertions, now
corrected to the committed request table. For the final cave run, the existing
Recorder observed the exact gate fixture's real writers in memory, then
`finish()` required complete changed-byte attribution. The final scratch
manifest records **83 writer calls, 9,445 reservations and 75 verified source
fingerprints**, with final XBE SHA-256
`9d7813d680054c0ffadc1a27ffb8629bc8831763042cf0eab5a01e147ebb6b71`.
The first scratch observer also wrapped the generic gameplay-lever helper and
thus double-attributed its two allocations; that harness was corrected to
observe the feature owners, as the production builder does. Its failed run is
retained separately and is not the final evidence.

The final observed manifest was generated with
`python3 .scratch/calendar-continuation/observe_xbe_manifest.py` and loaded
with the real `ReservationManifest(..., source_root=ROOT)` check. It has
`image_steps=[]` and explicitly describes an **XBE-only** fixture, not a disc
build. Both mandatory XBE suites pass the full owner composition in both
orders; the cave suite takes 257.173 s and peaks at 457,116 KiB RSS. The
production oracle's full-disc/source-fingerprint case still fails on the
protected stale JSON, which was not regenerated or patched here. That missing
production proof stays assigned to Claude; the private manifest does not
claim the required resource/experimental-disc build took place.

Additional exact commands and results:

| Command | Result |
| --- | --- |
| `python3 -m tests.mod_editor.test_nfl2k5_calendar_engine` | 9 passed, 12.413 s; the capability's literal validation command runs |
| `python3 tools/nfl2k5_calendar_engine_assemble.py --check` | PASS, invoked by the integrity suite; committed byte template reproduced |
| `python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json` | PASS, 36 requests, XBE 12,300,288 bytes; no build |
| `python3 mod_editor/capabilities/validate_registry.py` | REFUSED: existing `docs/research/apf_audio.md` absent |
| `python3 mod_editor/capabilities/validate_registry.py --registry .scratch/calendar-continuation/registry-candidate.json` | Same pre-existing missing-evidence refusal |
| `python3 mod_editor/capabilities/validate_registry.py --registry .scratch/calendar-continuation/registry-candidate.json --skip-file-checks` | PASS, 96 rows; actual product catalog has 58 Xbox NFL 2K5 entries and 12 sections |
| `python3 mod_editor/capabilities/validate_registry.py --registry .scratch/calendar-continuation/calendar-file-check.json` | PASS in file-check mode, exact calendar object plus 41 explicitly synthetic coverage rows |
| `QT_QPA_PLATFORM=offscreen python3 packaging/check_2k5_mod_studio_runtime.py` | REFUSED: reviewed target metadata directory absent |
| `git diff --check` and syntax parsing of all 11 changed Python files | PASS |
| Protected-file, staged-path and private-manifest source-fingerprint audits | PASS |

The final native calendar suite took 363.128 s inside unittest (439.431 s
including process teardown), with sampled peak RSS 371,703,808 bytes. The
largest sampled process was the oracle at 942,264,320 bytes, below 2 GB; no
memory stop fired. The schedule smoke now reads only 593,792 bytes, and its
new large-buffer receipt fixture adds just 1 MiB. No test in this review loaded
an entire archive pack or disc into RAM. Test logs, manifests and scratch source stayed under 5 MiB. Including the
final bundle and isolated Git metadata, scratch remains below the 200 MiB limit.


## Noah's required witness list

**Every item is pending.** Keep the exact build receipt/XBE hash, configured
base year, before/after SAVEGAME.DAT and EXTRA pairs and screenshots. Record
both raw index and ordinal. Edited-index boundary probes are useful but do
not establish natural drafts, retirement, economics or long-term progression.

1. Build the integrated combined 2026 image with its matching regular and
   preseason templates. Boot, enter Franchise, inspect preseason and regular
   week one, then save, quit and reload. Check the current grid, date line,
   birthday, contract projection, cap projection and history labels together.
2. Advance naturally through seasons 30 -> 31 -> 32 (indices 29 -> 30 -> 31).
   Retain index-30 retirement, index-31 retirement and index-31 regular saves.
   Confirm no premature completion, a populated next draft and reload/advance.
3. At **2053** (2026 index 27), check generated 2031-era rookie birth years in
   both game and Studio, alongside older live players and birthdays. The old
   fixed-pivot defect is repaired in the bounded formatter proof; it still
   needs a rendered gameplay witness.
4. Advance **2098 -> 2099 -> 2100 -> 2101** (indices 72..75), then **2104**
   (index 78). Check December/January, all three schedule phases, weekday
   labels, Thanksgiving week 11, postseason byes and birthday displays.
   Require **no February 29, 2100**, and a valid February 29, 2104 where a
   date path reaches it. Save/reload each transition without year wrapping.
5. At season 50/index 49, season 100/index 99 and index 100, retain retirement,
   next preseason and next regular saves. Check active/reserve/IR counts,
   retirement/replacement, the 380-prospect pool/recycled identities, coaches,
   contracts, cap/dead cap, folded history, records, event ring and awards.
   Repeat relevant economics checks with four-times initial cap when selected.
6. **Complete index 127 / season 128 naturally**, including postseason in
   2154 for a 2026 start. Keep the last normal save and the terminal rollover
   save. Require deliberate **index-128 retirement refusal**, then reload the
   terminal save without wrapping to index zero or offering a normal season
   129. For a deliberately matched 2004 build, the final postseason is 2132.
7. Repeat the milestone checks on the composed feature set actually offered:
   progression, practice squad/reserves, depth locks, playoffs14, abilities,
   Spy and other enabled allocator owners. Observe loader/memory behavior and
   ensure mode transitions, quit/reload and played-game cleanup remain sound.

## HYPOTHESIS and known gaps

Natural completion, Xbox loading, rendered dates and labels, save/reload
provenance, all indirect consumers, reserve lifecycle fairness and long-term
economics remain unproved. The feature preserves bounded history folding,
award overwrites, event-ring and salary-queue limits. It does not create a
128-year permanent archive, repair every historical identity's century or
automatically migrate ambiguous older saves. The 2004 executable helper path
is supported; a matched 2004 disc/template build is not supplied or witnessed.

The runtime registry merge and synchronized product counts belong to Claude's
protected integration handoff in `WIRING.md`. The scratch candidate proves
96 total rows, 58 Xbox NFL 2K5 rows, 37 APF rows, one PS2 row and 12 product
sections; it does not claim the live protected runtime gate has been rewired.
The calendar object passes the real validator's file-check mode inside an
explicit test coverage envelope. The complete original and candidate registries
both fail their separate file-check runs on missing historical APF evidence;
the full candidate's successful schema/catalog run uses `check_files=False`.
No dummy historical evidence or weakened production check is supplied.
Claude must regenerate the protected cave manifest and release closure on
the final integrated sources. This work does not enable a new preset flag.

The initial `df -h /` check reported 96G available; I conservatively used
100G in those same units for Noah's free-space target. No real-disc build was started, and no disc or pack
copy was placed under scratch. Only small logs/JSON and source delivery
artifacts are retained. No retail executable, save or game resource is part
of the commit or bundle.


## Commit delivery

The first explicit-path staging call succeeded, but the final staging/commit
operation could not create `index.lock` in the read-only shared Git metadata.
The brief's authorized fallback uses isolated metadata under
`.scratch/calendar-continuation.git`, the original `288ba65` as parent, and
the same 14 explicit paths for staging and committing. The verified delivery
is **`.scratch/r62-calendar-continuation.bundle`**; edited files remain here
and the shared branch is not advanced. The bundle commit includes the final
report, WIRING, capability object, CLI/UI and receipt repairs, and standalone
tests. `ASTRA_BRIEF.md`, `.scratch/`, protected implementation files, retail
data, executables and discs are excluded. The final disk check reported 102G
free. No source disc was modified and no push was performed. Registry/count/
boolean integration, historical evidence, reviewed release metadata and
production-manifest regeneration remain the concrete handoff in WIRING,
not claimed completed runtime checks.

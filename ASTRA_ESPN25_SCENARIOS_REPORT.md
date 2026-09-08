# ESPN 25th Anniversary scenarios and rosters, 2026-09-07

EXPERIMENTAL / UNWITNESSED. No game was played. No console, emulator, GUI display,
audio or network was used. Bounded Unicorn execution is native-code evidence,
not a gameplay witness.

## Outcome

Implemented the supported part of Noah's request: a hostable Anniversary roster
panel, strict CSV import using the existing Rosters data model, fixed-25 scenario
JSON authoring, source-specific plans/receipts, and a bounded transactional image
builder. The native tests prove that edited player fields reach the selected
historic team. Protected Studio mounting and build integration are specified in
the exact r64 section of `WIRING.md`; those protected files were not edited.

More than 25 is **conditionally feasible, not installable in this delivery**.
A 30-row table passes native relocation, accessor, menu-count and caption
callbacks. The two executable count constants and 32-bit completion/reward
mechanism are identified. Full menu paging and saved high completion bits are
not proved. Following Part B's explicit stopping condition, expansion stops at a
bounded authoring experiment and a concrete growth design. Production code
refuses expanded tables and does not modify any XBE or profile.

M1 research was committed as `1d94d5c` before implementation, followed by
`.scratch/M1_DONE`. `.scratch/M2_DONE` marks the built parts. Implementation,
tests, data metadata, this report and WIRING are committed with explicit paths.
Neither the brief nor scratch is committed. Nothing was pushed.

## Delivered surfaces

| File | Delivered behavior |
|---|---|
| `mod_editor/core/nfl2k5_espn25_scenarios.py` | Catalog, native-derived bindings, fixed-layout guards, RosterDocument adapter, strict CSV, scenario JSON, research table compiler, plans, status, image writer and CLI |
| `mod_editor/gui/espn25_panel_qt.py` | New hostable 53-player grid, moment/side selection, shared-use acknowledgment, CSV import/export, scenario JSON loading, validated plan save and signal |
| `data/nfl2k5_espn25_layout.json` | Sizes, identities, name-pool boundaries, original SITU allocations, known condition bundles and masked structural hashes; no retail player/scenario text |
| `data/nfl2k5_espn25_authoring.schema.json` | Bounded fixed-edit and research-append JSON schemas; backend additionally validates source-dependent constraints |
| `docs/mod_editor/nfl2k5_espn25_research.md` | M1 native evidence, field map, loader and count-growth decisions |
| `docs/mod_editor/nfl2k5_espn25_authoring.md` | CSV field map, JSON formats, CLI workflow, units, replay, distribution and compatibility limits |
| `docs/mod_editor/nfl2k5_espn25_capability.json` | Schema-valid registry object for protected integration; offline writer proved, runtime not tested |
| Three new standalone suites plus `tests/espn25_fixture.py` and `tests/espn25_native.py` | Portable synthetic coverage and precise private-evidence/Unicorn/PyQt5 skips |

The panel's `plan_ready` signal carries a saved path and validated plan for the
host to attach to `BuildPlan.espn25_plan`. There is no pretense that the protected
Rosters tab is already wired. The command-line workflow is usable now.

## Part A: what loads and what editing affects

**PROVED:** SITU +14/+18 are selector names and +1C/+20 are the corresponding
roster years. `20CB30` selects the row through `2CFD40`, loads home first, and
calls `20BD80` with name and year. That function matches the main ROST historical
descriptor table: root +58/+5C, 75 entries of 16 bytes. Descriptor +0 is u16 year,
+2 is a filename kit suffix, +4 holds the two UTF-16 team-code characters and
+0C is the relative selector pointer. Name comparison is case-insensitive.

`2D17B0` formats `h-%s-%d-%s-%d.iff`. CRC32 of the uppercase UTF-16LE filename
matches every one of the 75 distinct archive IDs. All are uncompressed ROST
resources in pack 0, outer 113..187, each with 53 primary players, zero secondary
players, one team and zero colleges. They are generic shared historic packages,
not current NFL rosters or private pools per moment. **50 sides use 35 files.**

`C1030` runs the real historic importer, including `C0500` relocation, live arena
allocation, player copies and team pointer-list construction. It resolves each
historic player's college index against the main college table. The new editor
therefore excludes college, membership and unknown-field writes. Player names,
numbers, positions, ratings and existing appearance/equipment fields use the
existing roster codec. No historical players were invented.

`2D13B0`/`2D1440` publish/return the loaded team; `77AE0` and `77B20` publish home
and away. The fallback team identity comes from `20C4E0`, with `oilers` mapped to
`titans` only in that fallback. SITU uniforms +58/+5C are independent of the
filename suffix; `E30E0`/`E3000` apply the away/home selections.

All resolved bindings below are zero-based moment indices and **pack-0 outer
indices**, not physical addresses. `inspect` reports the filename, archive ID,
year and selector for every side.

| Moment | Away ROST | Home ROST |
|---:|---:|---:|
| 0 | 125 | 133 |
| 1 | 155 | 157 |
| 2 | 141 | 139 |
| 3 | 157 | 163 |
| 4 | 141 | 158 |
| 5 | 183 | 126 |
| 6 | 149 | 171 |
| 7 | 169 | 142 |
| 8 | 126 | 171 |
| 9 | 159 | 183 |
| 10 | 129 | 187 |
| 11 | 172 | 124 |
| 12 | 177 | 113 |
| 13 | 124 | 172 |
| 14 | 118 | 153 |
| 15 | 181 | 129 |
| 16 | 140 | 129 |
| 17 | 181 | 118 |
| 18 | 129 | 140 |
| 19 | 136 | 118 |
| 20 | 134 | 130 |
| 21 | 167 | 182 |
| 22 | 167 | 147 |
| 23 | 154 | 174 |
| 24 | 135 | 162 |

Native moment 0 loads home `h-10-1966-packers-3.iff` (133) and away
`h-07-1971-cowboys-4.iff` (125), then constructs two separate live teams with
53 distinct player pointers each. A separate edited-resource trace observes
first/last `A/B`, number 12, position QB, speed 91, skin 2 and face 3 on the
imported away player. These are test substitutions, not historical content.

**Shared-use decision:** every roster import explicitly requires
`shared_resource: true`. The panel lists all affected moment sides and states
that the historic team outside Anniversary mode also changes. Two CSV imports
of one shared file in a single plan refuse. A combined JSON document binds CSV
to its final selector/year pairs. The panel refuses changing a team underneath
an already staged roster edit.

Private copies would require a cloned roughly 7..8 KiB ROST, a new archive
identity, a new 16-byte historical descriptor plus selector/filename strings in
the main ROST, and a proved fallback team identity. A selector rewrite alone is
insufficient. Main descriptor growth/new-entry installation and private copies
are deferred, not presented as finished features.

## Resolved scenario field map

Offsets are within each 108-byte record. Side Booleans use 0 away, 1 home;
the engine's two score/team objects use home side 0 and away side 1.

| Offset | Meaning and evidence | Authoring |
|---|---|---|
| 00,04,08,0C | Title, history, objective, date; existing SITU text consumers | Four fixed UTF-16 allocations via existing safe-text encoder |
| 10 | Stadium table ordinal, `20CC05..20CC2B`, stride 128 | 0..30 conservative range; main ROST actually has 82 records |
| 14,18 | Away/home historic selector | Existing validated name/year pairs, fixed text capacity |
| 1C,20 | Away/home roster year, `20BD80` | Actual roster selection, not display-only |
| 24 | Human side, `20CC59`, `27B32E`, `20C682` | 0 away, 1 home |
| 28 | Possession, `10C1BC..10C228` / `10BD9E..10BDC5` | 0 away, 1 home |
| 2C,34 | Away/home starting scores, `10C1B9..10C1DF`, `10BD86..10BD9C` | 0..99 |
| 30,38 | Historical final-score text, `2C5980` / `2C59B0` | 0..99 display values, not executable goals |
| 3C | Quarter index, `2C5AD0`, `10BDF1` | 0..3, stored as quarter 1..4 |
| 40 | Ball yards from midfield, `2C5CA0`, native 91.44 multiplier | -49..49; positive is away half |
| 44 | First-down distance, `10C207..10C250` | Positive 0.01..99 yards; direction follows possession |
| 48 | Down state, `2C5BB0`, `10BE95` switch | 0 kickoff, 1..4 ordinary downs |
| 4C | Clock seconds, `2C5B40` / `10BE48` | Finite 0..900 |
| 50,54 | Away/home timeouts, `10C1C6/1DF`, `10BDD9..10BDEE` | 0..3 |
| 58,5C | Away/home uniform choices, `20CBF5..20CC00` | Retained from source/template; no asset-validation claim |
| 60 | Weather preset input copied to E601D0 before `E3150` | Copy complete existing conditions bundle only |
| 64 | Environment/time input copied to E60184 | Complete bundle only; full meaning unproved |
| 68 | Signed input converted to float and stored at E5FFA4 | Complete bundle only; temperature-like interpretation/units are HYPOTHESIS |

The real moment-0 setup trace observes home 14, away 17, three timeouts each,
quarter 4, down 1, home possession, clock 290 seconds, ball
-1645.9200439453125 cm and first-down line -731.52001953125 cm. These match
-18 yards and 10 yards to gain times 91.44. Uniforms are home 3/away 5;
weather/environment/signed float inputs are 3/0/-13. An edited setup reaches
home 7/away 10, 75 seconds and away possession through the same native path.

The code replaces only declared archive open/wait/lookup/release, controller,
weather/presentation transitions and spatial-model/clock-control boundaries.
The real lookup, filename formatter, historic importer, player allocator,
relocator, numeric state writes, caption formatter and completion code execute.
Each invocation is capped at two million instructions; native strings and
resource reads are also bounded. The harness pins the complete USA XBE SHA-256.

`20C670` marks completion when the human side wins the ordinary mode-8 final
score comparison with the scenario flag clear. It does not interpret objective
prose or historical final-score fields. This does not prove the complete game-end
trigger or allow authors to create custom objective rules.

## Part B: feasibility per component and growth design

| Component | Verdict |
|---|---|
| `165EE0` and sibling registration callbacks | PROVED descriptor-driven; every record gets six fixups at stride 0x6C |
| `2CFC40` / `2CFCA0` | PROVED six biased-pointer fixups/inverse; 30-row round trip exact |
| `166000` registration | PROVED FourCC/callback registration, no local 25 limit |
| `2CFD00`, `2CFD20` | PROVED loaded descriptor count published/read at C8F0D8 |
| `2CFD40` accessor | PROVED base plus index times 108; **no bounds check** |
| `20C340` list count, callback pointer 529660 | PROVED constant 25, six-byte `b8 19 00 00 00 c3` |
| `20C350` list caption | PROVED native title/date formatting for all 30 rows with count callback changed in test memory |
| Full list capacity/paging, navigation/re-entry | UNPROVED; callback iteration is not a full UI paging witness |
| Completion mask BF18CC | PROVED dword; shifts alias index 32 to bit 0 |
| Profile `196DC0`/`196DD0`, member +125C | PROVED full-dword read/write, including bits 28/29 and FFFFFFFF |
| Serialized profile/save representation | UNPROVED high-bit persistence; no migration or widening installed |
| Reward `20C2BC..20C2E7` | PROVED 25-bit loop and reward 14; test-memory 30-bit loop waits for all 30 bits |
| SITU wrapper/body/collection | PROVED uncompressed first chunk of outer 22, siblings follow; growth preflight succeeds |

The menu-count research patch changes the complete six-byte span at 20C340 to
`b8 1e 00 00 00 c3`. The reward-loop research patch changes the complete
five-byte span at 20C2CA from `83 f9 19 7c f1` to `83 f9 1e 7c f1`. Tests clear
Unicorn's translated-code cache before executing changed code. These are
**test-memory substitutions only**, not an installable XBE patch/owner. No RX,
RW or RO allocation, request union, manifest entry or cave is introduced.

For 30 rows, keep original ordinals 0..24, append five records (540 bytes), move
and rebuild all six strings per record after the extended array, recalculate
biased pointers, update descriptor and wrapper count, and pad the body to 16
bytes. The wrapper +8 is **count**, not decoded memory size. Its original +4 is
29,104 body bytes. Original first chunk is 29,136 bytes; outer 22 is 128,976
bytes, including 99,840 bytes of later chunks.

The bounded research fixture compiled to a 30,416-byte first chunk and a
130,256-byte candidate collection after preserving those 99,840 sibling bytes.
The existing `nfl2k5_resource_growth.plan_pack0` accepted this collection against
the real pack with at most 1,048,576-byte reads. Pack-0 size would change from
193,710,080 to 193,712,128 bytes, exactly one 2,048-byte archive block. No pack
or disc was written. The writer's general limit is 32 MiB per replacement,
16-byte collection alignment; this compiler deliberately caps research bodies
at 256 KiB. The future outer/XDVDFS transaction must use the existing growth
writer, preserve all siblings and reject unrecognized allocation padding.
Compressed variants must be refitted with `nfl_vc_lz_fill`, preserving +14;
the delivered SITU/ROST paths are uncompressed and leave wrappers byte-identical.

Thirty fits the **in-memory** dword without widening, but that alone does not
establish save compatibility. Before installing a candidate, audit and witness
serialized bits 25..29 and full paging. Above 32 requires versioned persistent
storage and audited migration/readers, not an XBE-only variable. Existing saves
are untouched; expanded installation refuses for new and existing profiles.

## Receipts, guard and transaction evidence

Plans have resource identity, fixed size, complete before/after SHA-256 and
exact `offset/before/after` runs. Outer 22 is pinned even on roster-only edits,
and main historic descriptor content is pinned. Replay accepts only entirely
before or entirely after resource sets; a mixture or stale resource refuses
before mutation. A fully applied plan is a no-write success. The image pass
rechecks selected resources and the main roster after opening its writable
handle. It locates relocated packs through the existing OuterImage provider.

The guard excludes only supported player bits and the original player-name
pool, supported SITU scalars, the six fixed text allocations and known condition
bundles. It pins wrappers, other chunks, geometry, team pointer lists, college
indices, unknown player fields and other pools. Name targets stay in their pool;
referenced allocations cannot overlap. Shortening and reopening retain the
original name-pool edges and SITU allocations.

A bad CSV is applied to an isolated RosterDocument and discarded as a whole on
any codec log/error. Tests cover pool exhaustion, duplicate/ambiguous IDs,
unsupported college/membership fields, out-of-range values, partial edits
followed by invalid cells, stale/mixed plans, foreign geometry, changed wrappers
and siblings, escaping pointers, malformed JSON and short writes.

The relocated synthetic XDVDFS fixture is under 4 MiB, with its pack at sector
512. Tests use the real archive reader/writer, compare unaffected resources and
siblings, verify every resulting hash, replay, and inject an I/O failure. The
source remains ready, failed output remains absent, staging directories are
removed, and a later successful copy verifies as applied. A constructor-failure
handle check uses `os.replace`, including the Windows-sensitive close case.
An injected `fsync` failure also closes the writer's descriptor (verified with
`os.fstat`), removes the staging copy and leaves the output unpublished.
Tiny fixture tests mock free capacity for small CI runners and separately prove
low-space refusal. Production builds conservatively require 100 GiB free after
copying. No real-disc build was performed.

Private local receipts/logs, deliberately excluded from Git:

- `.scratch/espn25_inspect.json`: all 50 source bindings and field values.
- `.scratch/espn25_receipt.json` and `espn25_cli_plan.json`: real-resource
  in-memory authoring plans with exact byte receipts.
- `.scratch/espn25_growth_design.json`: streamed growth preflight, never installed.
- `.scratch/espn25_research_check.json`: 30-row CLI validation, installable false.
- `.scratch/espn25_*tests.log`, `espn25_gate_*.log`, and metrics files: test output.

Retail XBE SHA-256:
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
Pack-0 SHA-256 from streamed growth preflight:
`34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d`.
The 30-row research first-chunk SHA-256:
`c89a36f8349f85ceb37c035ae463e7ae0e27aa78163cd58e8ca7befdc7570077`.

## Exact verification

| Command | Result |
|---|---|
| `python3 tests/mod_editor/test_nfl2k5_espn25_scenarios.py` | 17 passed, 27.932 s; peak RSS 51,272 KiB |
| `python3 tests/mod_editor/test_nfl2k5_espn25_native.py` | 7 passed, 4.650 s; peak RSS 135,912 KiB |
| `python3 tests/mod_editor/test_nfl2k5_espn25_panel_qt.py` | 5 passed offscreen, 3.108 s; peak RSS 69,500 KiB |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 83 passed, 361.783 s |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 99 passed, 455.615 s |
| `python3 tests/mod_editor/test_nfl2k5_roster_records.py` | 108 run: 107 passed, 1 skipped, 12.698 s; peak RSS 188,152 KiB |
| `python3 tests/mod_editor/test_nfl2k5_espn25_scenarios.py ImageTests` | 4 passed, 13.758 s; final image-only recheck including main-resource revalidation, portable capacity checks and fsync-failure cleanup |
| `PYTHONPATH=. python3 tests/test_nfl2k5_safe_text_banks.py` | 9 passed, 1.623 s; existing encoder regression |

Both XBE gate files include ordinary and v3 scale-out owner composition in
**forward and reverse** order. They ran unchanged: there is no new executable
owner to register. New suites run standalone with plain Python; they do not
require pytest. Private-evidence, Unicorn and PyQt5 absence have precise skips.
The roster regression's single skip is its shipped 4,303-portrait catalogue,
which is absent in this checkout; it is unrelated to Anniversary editing.

Additional checks passed: module compilation; CLI `inspect`, `export-csv`,
`plan`, `status` (`ready`) and `research-check` (30, installable false); schema
validation of the capability object, authoring schema, fixed edit and five-row
research draft with Draft202012Validator; streamed real-pack growth preflight;
`git diff --check`. No protected packaging/registry files were modified or
claimed integrated. Their final runtime-closure checks belong to WIRING.
The in-memory registry candidate passes structural validation after insertion
in the required ID order. Its file audit stops on the
checkout's pre-existing missing `docs/research/apf_audio.md` in capability 0;
the new object's own schema and evidence-file checks passed. The protected
registry and missing unrelated evidence were not altered to hide that failure.

Initial tests exposed and fixed an imprecise expanded-schema error message and
Unicorn's cached pre-patch translations in the research harness. The existing
safe-text test outside `tests/mod_editor` initially lacked the repository import
path under plain Python; it was rerun with `PYTHONPATH=.`. No production bypass
was added for these checks.

## Noah's precise witness list and remaining gaps

1. After protected wiring, open a matching image, choose moment 1's away roster,
   supply a historical CSV and save/build a new copy. In the roster selection
   and on-field lineup, check name, number, position, a changed rating and each
   changed appearance item. Verify 53 players and ordinary substitutions.
2. Pick a historic file shared by multiple moments, inspect every listed use,
   and inspect that historic team outside Anniversary mode. Confirm the shared
   behavior matches the panel's statement. Verify an unrelated team remains
   unchanged. Private per-moment clones are not implemented.
3. Author starting scores, quarter, seconds, side, possession, down, field
   position and distance. Check the scoreboard, clock, field markers and first
   play. Copy a known conditions bundle and inspect the actual weather/time;
   record temperature units before exposing them as individual fields. Check
   uniform selections after every selector/year change.
4. Win, lose and tie with the human on each side. Confirm completion only on
   the ordinary win condition, return to the list, restart, and save/reload.
   Changing objective prose must not be represented as changing game logic.
5. **Before any expanded-table installer is built:** prepare a private reviewed
   candidate with the two complete pinned spans above, a 30-record collection,
   preserved siblings and the existing pack/XDVDFS transaction. Visit all rows
   1..30, cross every page boundary in both directions, select 26 and 30, back
   out and re-enter, and ensure selection/captions/completion icons agree.
   Callback tests do not replace this full list witness.
6. On both a disposable new profile and a copy of an existing profile, complete
   moments 26 and 30, save, exit/reboot, reload, and compare all prior moment
   flags, unlocked content and other profile fields. Confirm completing the
   original 25 alone no longer grants the all-moments reward, the full 30 grants
   reward 14 once as expected, and loss/tie does not add a bit. Supply before/
   after profile files for a serialized-storage audit. High-bit persistence and
   unrelated-state preservation are prerequisites, not delivered claims.
7. Version-18 main roster arena growth, arbitrary historic reclassification,
   foreign/compressed layouts, private clones and custom executable objectives
   remain unsupported. Bounds and source pins refuse them rather than infer
   compatibility. Expanding beyond 32 requires a separate save migration design.

No disposable acceptance image or pack remains. Scratch contains only small
research resources, JSON, CSV, notes and logs (under 1 MiB at final review,
well below 200 MiB). The main drive reported 102 GiB free before and 101 GiB after
acceptance. No whole disc/pack was materialized in memory; the largest measured
new test process was about 133 MiB RSS.

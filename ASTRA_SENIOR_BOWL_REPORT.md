# r62 Senior Bowl: preparation and dormant components

2026-09-06, branch `astra/r62-senior-bowl`, base
`f371972` (the supplied beta-62 stack).

**EXPERIMENTAL / UNWITNESSED. The requested native simulation MVP is NOT
complete.** This delivery is the data-only preparation tier plus bounded
native components. Native simulation, native persistence, live team cloning,
menu/results screens and scouting-card hooks remain unimplemented. They are
not merely waiting for protected UI wiring. The playable tier is specified,
not built. Do not enable either tier based on the passing component gates.

No questions were asked. Decisions and the precise remaining implementation
are documented in `docs/mod_editor/senior_bowl.md` and the final Senior Bowl
section of `WIRING.md`. The safe decision was to refuse native activation,
rather than overwrite unowned save bytes or claim that bypassing one stat
commit proves simulator isolation. No game/emulator, displayed GUI, audio,
network or push was used. Unicorn ran only bounded instruction fixtures;
Qt ran offscreen. Only this worktree was written.

## Delivered

- `mod_editor/core/nfl2k5_senior_bowl.py`: signed, bounded franchise reader;
  complete primary/ownership scan; reproducible 53+53 positional selection;
  current kit configuration; class fingerprints; independent 16 KiB event
  codec; stage/skip/recovery policy; separate scouting-line projection;
  atomic small event/project files; CLI; strict pure-byte dormant installer.
- `tools/nfl2k5_senior_bowl.S`, reproducible GNU-as assembler and checked-in
  `nfl2k5_senior_bowl_code.py`: original cdecl selection, stage policy,
  checksum/envelope-buffer save/reload components, and explicit simulation
  refusal. No retail hook calls them.
- `mod_editor/gui/senior_bowl_panel_qt.py`: own configuration/preview page,
  away/home/full eligible class tables, stable selection after sorting,
  four verified kit choices, seed, saved preview projects and missing-source
  handling. The Simulate button is disabled and says why. It reads its own
  signed SAVEGAME.DAT or a validated Studio-provided snapshot.
- Three standalone suites and a bounded fixture module. Both XBE gates now
  include the owner in their complete forward/reverse unions, inspect its
  full code writes and its named growth allocations, and demand exact replay.
  The actual budget fixture and all manifest observer/probe owner lists
  include it. A manifest unit test observes the real writer and requires its
  entire RX/RW allocations. The protected release JSON was not regenerated.
- A schema-valid preview capability handoff with `python3 -m` commands;
  complete protected BuildPlan/dispatcher/four-dictionary/Build/PATCHES/tab/
  closure/allowlist instructions. Those deliberately reject native activation.

No protected implementation file was changed. No proprietary resource, XBE,
save bytes, generated image, brief or scratch artifact is part of the commit.

## PROVED: selection, event and placement components

The RC85 changelog, allocator/Practice Squad/other relevant Astra report
constraints and full hub Senior Bowl memo informed the work. The scratch
prior-report inventory records each report's hash and relevant excerpts.
Read-only Ghidra shards were checked against actual retail instructions;
new byte observations are listed in the implementation document.

Retail XBE SHA-256:
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.

The reader verifies EXTRA before decoding exactly 720044 save bytes. It does
not recursively load a save archive, disc or pack. It scans every primary
record and checks active/reserve/FA/IR ownership. The memo's initial fixed
1937..2316 window is not used. Three read-only signed fixtures yielded:

| Fixture | Eligible prospects | Eligible index bounds | Squads |
| --- | ---: | --- | --- |
| f0 | 380 | 1937..2316 | 53 + 53 |
| f1 | 380 | 1937..2316 | 53 + 53 |
| Franchise1, later year | 317 | 1..2471 | 53 + 53 |

The memo observed 377 prospect-flagged records in Franchise1. This revision
excludes drafted/unallocated/already-owned records before counting eligible
participants, so 317 is an eligibility count, not a contradiction or a claim
that the raw flag count changed. Source SHA-256 and decoded bytes remain
unchanged by the previews. Synthetic tests additionally exercise all three
position schemes, veterans/drafted/owned/unallocated exclusions, duplicates,
recycled identities, invalid indices/positions, shortages and the 512-class
capacity refusal. Every selected team has the exact 53-player position quotas,
including a kicker and punter. **Actual eleven-personnel runtime selection,
cloned team depth and special-team assignments are not proved.**

Selection is deterministic for the saved seed and independent of input order.
No ratings or contracts are edited. One-pool pools OLB/ILB at code 11 and
refuses remaining eligible code-10 OLBs; EDGE remains 16. All eligible
nonparticipants remain in the preview/map. This revision allows up to 512
eligible prospects and 4096 primary records, with explicit refusal above
those bounds rather than truncation or veteran substitution.

Host event encoding is canonical and exactly 16384 bytes, containing version,
CRC-32, franchise/year/class identity, seed, settings, eligible map, 106
participant identities, quarters, team totals and 36 stat fields per player.
No runtime pointers are serialized. Host validation rejects semantic and
reserved-byte corruption even if CRC is recomputed. Running reloads as pending
with the same seed; terminal states remain terminal for their supplied year.
A new year requires an explicitly new record. These are component transitions,
not proof of the retail franchise's once-per-year routing. Preview projects
and development event files are separate artifacts, not Xbox save members.

`Event.scouting_line` returns a separate participant result only for a supplied
complete record. Nonparticipants and pending records return no line. Tests
use synthetic captured-result fixtures; **no retail simulation result was
produced**. Both host `simulate` and native `sb_simulate` refuse without a
state write or native simulator call. This refusal is not a sim-wrapper proof.

Default kits are 50A0 and 51H0. The four 50/51 home/away current-era outer
entries were read through the existing descriptor reader: exact memo sizes
and `Unif` prefixes agree. Only 64 bytes per package were read; no pack was
loaded wholesale. Filename identity follows the memo's independently
verified inventory. Appearance, contrast and jerseys in the game remain
unwitnessed. Other banks/eras are refused, not guessed.

## PROVED: bounded instructions, budget and installation

The assembled payload is **1180 bytes: 1163 instruction bytes and a 17-byte
quota table**. Allocation requests are **4096 RX + 65536 RW**, within the
assigned 16384/65536 cap. The actual budget fixture replaces the planned
16384 RX row with 4096. The full future-budget plan reports 64064 RX bytes,
4096 RW bytes and 12800 RO bytes available after alignment. The unused
12288 bytes of the original RX estimate have no implicit VA assignment.

Event state is +0, codec/selection staging +0x4000. Planned team/player/coach
workspace offsets are documented but no clone builder uses them yet. Disk RW
is entirely zero. Code and its immutable quota table are sealed RX; writable
state is a named fresh allocation, never `.text`, a retail cave or unknown
padding. No allocator implementation or page count changed.

The private cdecl routines preserve nonvolatile GPRs, stack cleanup and DF.
Selection consumes a normalized primary snapshot, not a live ROST root.
Native save/load are bounded memory copies with envelope CRC, expected
identity/year and recovery checks; **native semantic validation is incomplete**
and there is no file I/O. These limitations prevent them being wired into game
load or stage callbacks. All are explicitly documented in their source/API.
Unicorn maps the actual installed bytes RX and data RW, limits each call to
2.5 million instructions, and observes all writes. The refusal helper has a
three-instruction limit. No retail simulator or OS service is stubbed and
then presented as having executed; those services are simply not called.

`status` distinguishes retail/prepared, applied components and foreign/mixed
code/state. `apply` validates allocator seals/digests, literal retail
serializer/simulator pins and the whole initial state before returning any
mutation. Missing sealed request union, altered dependency bytes, changed
code and nonzero offline state refuse. Exact replay returns the same bytes
and zero changed bytes. The existing allocator handles growth and section
digests. Receipts say `native_event_available: false`, `retail_hooks: 0` and
`save_growth: 0`; component installation is not native activation.

Standalone realized component addresses were RX `0x14DA000`, RW `0x14F2000`;
other union layouts relocate them from actual allocator results. The resulting
XBE is 12300288 bytes, SHA-256
`2da324e4136042c529782f556e98c5e7f8dfee8a90cc4e6189c5950dbbc261f8`.
353257 bytes change/append, including the allocator's header/logo relocation;
retail `.text` stays byte-identical in the standalone component installation.
This XBE exists only transiently in bounded memory, not as a shipped file.

## Exact validation results

All final suites ran standalone with plain Python, and none skipped locally.
Precise skips exist for absent private XBE/saves, Unicorn, GNU assembler or Qt.
Logs are under `.scratch/senior-bowl/` and excluded from delivery.

| Command | Result |
| --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_senior_bowl.py` | 26 passed, 4.502 s; includes the manifest observer test and capability schema test |
| `python3 tests/mod_editor/test_nfl2k5_senior_bowl_unicorn.py` | 9 passed, 2.261 s |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_senior_bowl_panel_qt.py` | 5 passed, 0.091 s |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 63 passed, 164.121 s; peak RSS 271772 KiB |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 75 passed, 246.515 s; peak RSS 481288 KiB |
| `python3 tools/nfl2k5_senior_bowl_assemble.py --check` | Exact generated template match |
| `python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json --json` | Complete budget accepted |
| `python3 -m py_compile` on delivered Python files; `git diff --check` | Passed |

**178 tests passed, at the stated component scopes.** Both gates include
forward/reverse order and actual byte-identity comparisons for the complete
owner union. The manifest test is an observed-writer ownership test, not a
fresh complete real-disc release manifest. Full native MVP acceptance is not
green, and the broader release/build/packaging suite was not claimed run.

Initial test failures caught a 17-byte synthetic franchise ID, a Qt tuple
`findData` mismatch, a test's oversized `.text` extent and invalid draft
capability enum values. Those were corrected and the affected complete suites
rerun. The final native bytes matched host selection on all schemes/seeds and
all tested refusal/recovery cases. No prior-owner product code was changed to
make the tests pass.

No real-disc build or whole-pack copy was made. The main drive had
109302968320 free bytes at the initial bounded-input check; a later check
reported 102527156224. This task's scratch artifacts stayed under 1 MiB before
commit metadata. No large temporary image was created or left behind. The
measured gate processes were far below 2 GiB; inputs are bounded XBE/save/header
reads. No full-disc manifest build was started to consume the limited drive
headroom. Claude must regenerate the protected manifest on integration.

## Native gaps and exact implementation specification

The new audit located real save serializer/restore callers (0x16E4F5 and
0x16E7F8) and the final file write at 0x16E524, but did not prove optional
member/append acceptance, signature coverage, atomic save/recovery or load
identity. The retail season/substate fields and opaque save/team tails cannot
supply storage just because they exist. The host's atomic small-file writer
is not evidence for an Xbox save transport.

The retail simulator core 0x10B940 is separate from the scheduled wrapper's
0x1356D0 commit. Its private register/five-stack-word ABI and finalization
remain critical: 0x105060 writes through `[player+0x30]`, and 0x1047B0 reaches
0x251880. Avoiding 0x1356D0 alone cannot certify injury/fatigue/progression/
news/coach-stat isolation. This branch did not execute that full call tree.

`docs/mod_editor/senior_bowl.md` specifies the exact remaining sequence:
prove persistence first, implement the native primary/owner scan and isolated
team/player/coach clones, prove all personnel/specialists and simulator writes,
then install the stage-4 gate including automatic Combine advancement and
native menu/roster/result/scouting callbacks. The playable specification names
mode 4, setters/settings/controllers, the 0xEC65A played commit boundary,
finish/quit/cancel/overtime restoration, uniform-choice composition and budget
rules. Playable implementation remains deferred because the MVP prerequisites
are unproved, not because this branch exhausted its code budget.

## Noah's acceptance checklist (memo section 4)

Every item remains **UNWITNESSED**. Do not ask Noah to run the native items on
this preparation-only revision; finish the required implementation first.

1. Retirement/re-signing/free agency to Senior Bowl before Combine day 1,
   exactly once a year; simulate, skip, save pending, reload complete and
   proceed to Draft without consuming days/hours twice. Legacy mid-combine
   saves follow the skip policy. **Policy/codec components proved; no live
   routing or native save/sim proof.**
2. Both 53-player squads and full class, first/later seasons and one-pool,
   no veterans/duplicates/prospect loss/contract changes; sorting selects the
   same identity, all starters and specialists valid. **Host previews and
   normalized native selection proved; native clones/personnel/UI missing.**
3. Quarter scores, team/player lines, later reopening and native save/reload;
   decoded season/postseason/career totals, standings, schedules, awards/news,
   contracts, injuries, fatigue, progression and coaches unchanged. **Separate
   host codec/projection proved with synthetic results; actual simulation
   isolation and native persistence missing.**
4. See 50A0 versus 51H0, readable contrast/numbers/helmets, correct sides;
   change supported banks/era and verify jersey choice and created teams.
   **Configuration and package prefix/size evidence only; no field rendering.**
5. Play, finish, quit, cancel settings, overtime, return to Coach's Desk;
   next ordinary franchise game and stock Pro Bowl retain rosters, uniforms,
   commits and progression. **Playable tier is a written specification only.**
6. Participant Senior Bowl line in scouting, no invented nonparticipant
   result. Any later stock option must affect displayed report and CPU score
   consistently without rating edits. **Host projection exists; native
   scouting hook and stock influence are absent.**

For the delivered Studio preview, Noah can additionally check signed-source
open, later-year identities, both kit selectors, sorting and project reopen
after protected panel registration. No aspect is called witnessed here.

## Commit delivery

The normal explicit-path `git add` failed because the linked metadata cannot
create `index.lock` on the read-only filesystem. The authorized fallback uses
`.scratch/senior-bowl-commit/.git`, this same worktree, and the original HEAD
as parent. Both staging and commit name all 18 delivery paths explicitly.
Delivery is `.scratch/r62-senior-bowl.bundle`, with the original base as its
prerequisite. The shared branch metadata remains unchanged; all edited files
remain in place. The commit subject is `Add Senior Bowl preparation and dormant
native components; keep MVP disabled`. ASTRA_BRIEF.md, .scratch/, retail inputs
and every protected implementation/manifest file are excluded. No push.

# MyCareer mode 3

EXPERIMENTAL / UNWITNESSED. Native CPU fixtures are evidence of the named
boundaries, not evidence that Noah has played this mode.

The continuation after `39796f4` implements direct next-fixture routing,
proves native played-stat settlement and final-year rollover, and refreshes
the generic disc recipe to include Auto Save. It closes the null CPU role
failure and adds native frame, snap/event, turnover, timeout, halftime,
overtime, injury and substitution boundary proofs. M2b's automatic off-field
drive matrix remains incomplete. M3 is not installed or accepted; the
measured purchase-core capacity experiment below is not a working Upgrade
screen. This report includes the checks completed on September 8, 2026.

## M2a checkpoint: shared game completion

PROVED: generic MyCareer and Franchise Auto Save compose in either installation
order, retain exact receipts, and replay unchanged. Each owner first validates
the other owner's complete installation before accepting its exact shared
function edits. No arbitrary context bytes or partial installations are accepted.

The native played-result dispatcher commits through `1356C0/134140`, MyCareer's
`C5D9E` hook settles its award, and Auto Save's existing `C5DA9` hook queues the
save. Native postgame and week handling return to the Apartment. Two quiet
Apartment frames then enter Auto Save's appended `career_complete` callback
with ECX = manager and EDX = the owned Apartment descriptor. It reuses the
cached-slot transaction and existing retry suppression. No save occurs in the
per-frame player binder or while the live scene exists. The exact callable and
protected product changes are recorded in WIRING.md.

The original 1,027-byte Auto Save runtime prefix and its relocation records are
unchanged. Its code is 1,170 / 1,536 bytes. At the M2a checkpoint MyCareer's
machine code was 7,042 bytes; code plus immutable content was 7,918 bytes,
leaving 257 bytes before its format seal in the existing 8,192-byte RX
allocation. Current continuation sizes appear below. RW remains 4,096 bytes.

PROVED by the bounded shared callback fixture: successful native save once;
missing slot; allocation, deletion, creation, write and commit failure;
deferral for a live scene, busy storage or a child screen; return after two
quiet frames; no repeated transaction or notice on repeated frames. The
fixture substitutes the played-stat providers and uses an inactive career
footer. It proves this completion ABI, not a completed career match or real
played statistics. Those are M2b requirements.

Validation, all standalone with plain `python3`:

| Command suffix | Result |
| --- | --- |
| `tests/mod_editor/test_nfl2k5_franchise_autosave.py` | 7 passed, 9.034 s |
| `tests/mod_editor/test_nfl2k5_franchise_autosave_unicorn.py` | 15 passed, 8.363 s |
| `tests/mod_editor/test_nfl2k5_my_career_generic_build.py` | 5 passed, 9.780 s |
| `tests/mod_editor/test_nfl2k5_my_career_completion.py` | 6 passed, 26.934 s |
| `tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py` | 101 passed, 629.957 s |
| `tests/mod_editor/test_xbe_patch_memory_writes.py` | 83 passed, 805.111 s |
| `tests/mod_editor/test_xbe_patch_cave_references.py` | 99 passed, 929.594 s |
| `tools/nfl2k5_franchise_autosave_assemble.py --check` | Passed |
| `tools/mycareer_mode/build_runtime.py --check` | Passed |

`tools/nfl2k5_cave_oracle.py manifest` against the pinned retail XBE and XISO
wrote `.scratch/m2a-manifest.json`: 10,629 reservations from 123 observed XBE
writer calls. The two disposable oracle builds used its TemporaryDirectory
under `/tmp` and were deleted. Root free space after the run was 108,439,990,272
bytes. The protected release manifest was not changed. `git diff --check`
passed. The capability fragment test now replaces existing fragment IDs before
validating the merged registry, retaining its schema and file closure checks.

The blocking M2a checks above passed before M2b implementation began;
`.scratch/M2A_DONE` records that checkpoint.

## Integration observation

The brief describes the M2 product dispatcher as already wired. This checkout
still dispatches the setup-based legacy owner and requires a setup in the
protected build path. WIRING.md specifies the correction. This session does
not edit those protected files or claim that the current product UI selects
the generic mode.

## M2b: direct fixture, native statistics and season return

`mode_next_fixture` scans the native 22 x 17 fixture grid for status 0/1 and
the resolved career club, only in preseason/regular/postseason stages. Play
calls native `C79F0(week, slot, 0)` for that exact fixture, retains the native
postgame parent `4F19E8`, then opens Team Select. The Schedule game-card
screen is no longer in this route. An unassigned career cannot launch a
different club's game. When no own fixture is pending in the current week,
the hub displays `No game pending. Advancing.` and enters native `247D40`,
or `2480B0` at the stage limit. The original menu label remains Play next
game. This is not M3's separate calendar/Advance interface.

New pins cover `C79F0`, its `C73B0` fixture setup dependency, and both native
advance prologues. The stage pin excludes the season-limit owner's operand
at `2480CD`. These pins and the generated owner remain compatible with the
full stack and refuse mixed/foreign installations before mutation.

PROVED by `test_nfl2k5_my_career_played.py`:

- A native-created club-2 career selects its first own fixture at slot 7,
  with no Schedule card or other-fixture simulation before it. Back returns
  to Apartment. A real bye in the generated schedule dispatches Advance.
- The fixture constructs native match rosters, team/player stat objects and
  the play log through `617E0`, `87160`, `1D3060`, `1F1D10`, `1F1D70` and
  `CCE00`. A declared 20-byte completed-pass event enters unchanged native
  `1EDC60`. Native `CB240` reports one attempt, one completion and 17 yards.
- A supplied engine-end signal enters complete `C5D60 -> 1356C0/134140`,
  MyCareer settlement, `C74E0/C5DF0`, and the owned Apartment. The native
  primary player's season and career banks both contain those real writer
  outputs. MyPlayer opens and returns normally. Native save and a fresh CPU
  cold load preserve the stats, identity, 25 points and fixture watermark.
- Repeated settlement and frames cannot award twice. A benched completed
  fixture records its watermark but awards zero. No stat provider, result
  commit, history writer, award or postgame callback is replaced by a stub.

PROVED by `test_nfl2k5_my_career_week.py`: after the owned first game has
completed, the full native `247D40` advance simulates and commits the 15
other pending games in that week. The observed `C7A20` and `1356D0` pairs
exactly match those fixtures and exclude MyPlayer's completed fixture.
The next Play selects the earliest own game in week 1, with no additional
simulation. A benched result retains zero points. This run uses a fresh
native-created save/cold load and a bounded three-billion-instruction cap;
the long native history copy completes without replacing its writer.

PROVED by `test_nfl2k5_my_career_season.py`: a fresh native-created career,
with explicitly supplied prior result-grid inputs, runs native postseason
construction `2A7E50`, including both Pro Bowl donor teams. Its final NFL
fixture has a supplied 7-0 live team score and the real passing-event writer.
Native completion records the quarter scores and returns at week 21; native
advance processes the remaining week and the year boundary. The result is
year 1, stage 1, 32 clubs, the same MyPlayer/token, a usable Apartment/card,
25 points and the same once-only watermark. Another native save/cold load
preserves that result. The test does not simulate or play every prior game;
its earlier scores are declared preconditions, and no played Pro Bowl is
claimed. The native year transition itself is not substituted.

## M2b: CPU play selection, frames and rule boundaries

PROVED by `test_nfl2k5_my_career_cpu_choice.py`: the actual career fixture
launches with the career quarterback absent from both selected field units.
The complete pinned 78,768-byte ATL PLAY resource is parsed and loaded into
both native book slots through `161E30`; the native role operation table is
initialized by `164000`. Match personnel, clocks, actor phase-state, task
state, AI profiles and player state are initialized through their native
constructors. The actor constructor executes through `1DF8B8`, including
its spare-script pointer; the later animation-table constructors are outside
this fixture.

Complete `A11F0` and the native defense choice `20B820` execute, including
138 calls to the real `1A8E60` role interpreter and four native lineup
assignments. Both native selected-play flags contain bit 8 and both
play-call human predicates return zero. MyPlayer's match identity remains
bound, its field body remains absent, and no appearance or points are
fabricated. Actors/transforms/ball are declared synthetic scene inputs.
The only added choice-specific substituted function is sideline coach
placement `2CD170`; inherited frontend hardware/resource seams are listed
in `tests/nfl2k5_my_career_mode_fixture.py`.

PROVED by `test_nfl2k5_my_career_cpu_frame.py`: all 27 phases of complete
native `11A7C0` execute in order for 60 frames at 1/60 second. The native
clock falls from 300 to 299 seconds. Positions, velocities, motion scales,
25 pose quaternions and both sets of model matrices remain finite for all
22 actors. The fixture reads only three pinned resource spans from player
package 3: SCNE 113/114 and SKEL 116. Their real 25/62-bone hierarchy and
head/hand vectors support the actual native animation/aim path. Initial
three-key clips and collision spheres are synthetic; native `1E21D0`
constructs motion state, including its valid unbounded height envelope.
Four additional final audio-gain leaves are substituted. No frame phase is
replaced. The match remains in phase 12; this is not an automatic snap.

PROVED by `test_nfl2k5_my_career_cpu_turnover.py`: after native CPU choice,
declared ready-animation completion inputs reach phase 13. A supplied snap
event enters complete `9FF80 -> 9FE50/B6F30`, records center/quarterback
and reaches live phase 14. A supplied possession event runs native
`B9B50 -> B91A0/A09B0/1BB690`. Thirty native clock/control frames reduce
300 seconds to 299.5. A supplied dead-ball event enters complete `A0390`,
including `B7330/B9670/CDEF0/189080`; the native engine changes possession
on downs, resets to first down and creates one post-play event-log record.
Both sides then select native CPU plays and reach phase 12 again. The
fourth-down situation is explicitly supplied after the first play choice
and captured through native `A8680/1B9E70`; this does not prove a CPU
decision to go for it. No snap, possession, clock, rules, event/stat or
assignment callee is substituted.

PROVED by `test_nfl2k5_my_career_cpu_timeout.py`: with declared Q2/two
seconds/first down/field-goal-range/7-0 deficit inputs, the native CPU
decides to call timeout. `A00A0/55C70/B8810` execute exactly once, stop
the game clock at 1.98333 seconds and debit that side from three timeouts
to two while leaving the opponent's three intact. A supplied presentation
return event runs `89260 -> A2D40 -> A11F0/20B670`, followed by complete
native defense choice. Phase 12 and both CPU selections return without
another debit. The presentation's natural animation/timer completion is
not proved by this supplied callback.

PROVED by `test_nfl2k5_my_career_cpu_period.py`:

- Supplied Q2-expiry and previous-kickoff inputs enter real halftime
  `A2970/B8A60`. A bounded 2 MiB backing free-list lets native `F6070/12F030`
  obtain the 0x148000-byte heap and `DA4D0/48640` construct it; the allocator
  and drive-log constructors execute unchanged. A declared presentation
  completion then runs native `9F8C0/48640/B88C0/9F940`, releases the heap,
  changes ends/kicker, restores five minutes and three timeouts per side,
  and reaches Q3 and the next CPU choice.
- Supplied tied Q4-expiry inputs enter phase 21 and native overtime
  dispatch. Declared presentation completion enters `B8B30/9F780/B8160`
  and the coin-toss phase. The supplied toss callback `9F690(side, direction)`
  reaches native `B81C0/9F940`, Q5, five minutes, two timeouts per side
  for the actual Franchise match mode, and the next CPU choice. No full
  halftime show, toss UI or naturally played four quarters is claimed.

PROVED by `test_nfl2k5_my_career_cpu_injury.py`: a supplied injury event
uses the pinned retail descriptor returned by `13E270(0, 3)`. Native
`136B10/1369D0` apply the record, choose its seeded six-minute duration,
clear availability and set the injury-presentation subject. Real
`A0320/136D30` and `189080` accept declared presentation/post-play completion;
native depth refresh and the next CPU choice replace the opponent's
starting quarterback with a backup and reach phase 12. No Python write
changes that actor's roster binding. Five declared rest boundaries through
`136F80` restore availability; a declared Q3 elapsed-time input lets its
native `1365B0/E6680` path clear the injury. The collision probability
trigger and a full physically played recovery interval are not claimed.

All these tests start with a fresh native-created career, retain MyPlayer's
match identity, and assert zero field presence, zero appearance and zero
upgrade points. No cached research save is used by the committed tests.
The turnover proof also keeps the career quarterback absent after its
club gains possession, through the actual selected lineup.

Remaining HYPOTHESIS / unproved scope: automatic snap-animation initiation
through `30C2B0` with a complete animation-table/resource lifecycle; a whole
normal-speed CPU drive and return to MyPlayer's unit; the combined boundary
matrix across offense, defense, all positions and special teams. A separate
60-frame exploratory run with ready actors reached phase 13 but never
phase 14, so it is not accepted as a drive proof. The full-frame test and
event-boundary tests must not be represented as one naturally played drive.

The Apartment footer says `Select. Off field: CPU at normal speed`.
Supersim remains the read-only dependency with `RUNTIME_READY=False`; no
terminal Simulate To End action is used as a live skip. The existing
all-position control fixture proves ownership decisions, not the missing
complete drive matrix. No M2b acceptance marker is created.

## RX/RW accounting and M3 capacity experiment

All installed changes retain the same 8,192-byte RX and 4,096-byte RW owner.
`-fomit-frame-pointer` recovers 172 machine bytes from the M2a sources.
Direct routing and its unassigned-club guard add 237 machine bytes. The
result is 7,107 machine bytes, 8,118 bytes including strings/menu encoding,
57 spare bytes and the existing 17-byte seal. The current expanded menus
use 996 of their 1,024 RW bytes. No reservation table or owner was enlarged.

`tools/mycareer_mode/measure_m3.py` compiles a concrete purchase-core design
from `upgrade_candidate.c` in a temporary directory, then measures it using
the normal owner's relocation/menu builder. It never installs that code or
writes an executable. The candidate includes tier prices 10/15/25/40/60,
the rating cap, affordability, an identity/token/value/balance quote, cancel,
stale/replayed confirmation rejection, and a one-point rating/debit commit.
The candidate source is capacity research; it has no UI/caller and is not
claimed as a tested purchase feature.

| Measured design | Machine bytes | Required RX including seal | Shortfall |
| --- | ---: | ---: | ---: |
| Installed continuation | 7,107 | 8,135 | 0; 57 bytes spare |
| Continuation plus purchase core | 7,511 | 8,539 | 347 bytes |
| Uninstalled `-Oz` purchase-core alternative | 7,413 | 8,443 | 251 bytes |

The normal owner refuses that exact candidate. The reproducible receipt is
`docs/nfl2k5_my_career_m3_budget.json`. An additional `-Oz` compiler pass
still needs 251 extra bytes for that included design; it is not installed
or treated as equivalent runtime validation. This is an exact shortfall for the
included design, **a lower bound, not an exact size of all M3 or proof that
every possible compaction exceeds the budget**. Purchase UI/confirmation,
calendar, depth UI, request execution/logs, draft/Senior Bowl and texture
registration/drawing are excluded and require more code. Nine hub rows alone
would expand the existing menu RW representation to 1,204 bytes, exceeding
its current subrange by 180 bytes; a new internal RW arrangement is required
even while remaining inside the 4,096-byte owner.

Claude's reservation decision must account for those excluded implementations.
This continuation does not take another page, install incomplete transaction
code, or assert that 347 extra bytes would finish M3. Weekly participation
points already work; spending, trade/release requests, calendar/depth controls,
draft entry and hub art remain unimplemented. The draft action now accurately
states `Draft entry is not ready.` rather than promising an update.

## Refreshed generic disc and persistence receipts

`tools/mycareer_mode/build_disc.py` adds MyCareer and Franchise Auto Save to
the caller's complete allocation union before installing either owner. It
installs both and verifies each reports applied. Conflicting caller budgets
are left for the allocator to reject. The shared M2a completion ABI is
unchanged. Auto Save still respects the native enabled setting and requires
a successful manual Save or Load to establish its cached slot; it does not
choose a first slot or force the user's setting on.

`tools/mycareer_mode/check_discs.py` streams two sequential disposable retail
disc builds with minimal and full reservation unions, reads each relocated
XBE back, verifies both owners and unchanged replay, and deletes each image.
Two different native-created careers (clubs 2 and 3) cold-load on each
executable into their own Apartment; MyPlayer opens and returns. The four
loads run only after both acceptance images have been deleted.

`docs/nfl2k5_my_career_mode3_disc_receipts.json` contains source-image and
output-XBE hashes, allocation addresses, owner edit receipts, image cleanup
and four save hashes. Source image size is 6,300,499,968 bytes; both outputs were
6,312,800,256 bytes. XBE hashes are:

- Minimal: `9808e622cb0561147d1d4ed6c19cc216edde2cdb72d09ae3ea94c0232c2935aa`.
- Full union: `15875835e0112594b482a389887c19345bc1d4a4983ccce0d352dc8ccd2137c9`.

The check completed in 83.04 seconds with peak RSS 183,880 KiB. Root free
space was 107,563,315,200 bytes before the first build and 107,562,561,536
after the second was deleted; the recipe enforces the 100 GB reserve during
each build. No image/pack is loaded whole into RAM. Receipts explicitly
retain `m2_accepted=False`, `m3_accepted=False` and `hub_art_bound=False`.
The read-only art recipe is not falsely bound by changing the shared Crib
skybox. Its native hub TXTR registration/lifecycle remains unresolved.

## Continuation validation

All suites run standalone with plain `python3`, using precise missing-evidence
skips. The following completed runs had no skips:

| Test suffix | Passed | Seconds | Peak RSS KiB when measured |
| --- | ---: | ---: | ---: |
| `test_nfl2k5_my_career_played.py` | 4 | 43.803 | |
| `test_nfl2k5_my_career_week.py` | 1 | 366.655 | 167,508 |
| `test_nfl2k5_my_career_season.py` | 1 | 158.233 | 194,628 |
| `test_nfl2k5_my_career_cpu_choice.py` | 1 | 19.260 | 146,252 |
| `test_nfl2k5_my_career_cpu_frame.py` | 1 | 61.864 | 133,520 |
| `test_nfl2k5_my_career_cpu_period.py` | 2 | 35.411 | 169,576 |
| `test_nfl2k5_my_career_cpu_turnover.py` | 1 | 21.881 | 133,516 |
| `test_nfl2k5_my_career_cpu_injury.py` | 1 | 20.139 | 133,816 |
| `test_nfl2k5_my_career_cpu_timeout.py` | 1 | 19.554 | 135,988 |
| `test_nfl2k5_my_career_frontend.py` | 7 | 50.460 | |
| `test_nfl2k5_my_career_control.py` | 2 | 13.548 | |
| `test_nfl2k5_my_career_inline.py` | 8 | 11.112 | |
| `test_nfl2k5_my_career_completion.py` | 6 | 24.896 | |
| `test_nfl2k5_my_career_generic_build.py` | 5 | 14.208 | |
| `test_nfl2k5_my_career_creation_boundary.py` | 4 | 2.144 | |
| `test_nfl2k5_my_career_manifest.py` | 3 | 6.098 | |
| `test_nfl2k5_my_career_mode_routes.py` | 7 | 2.773 | |
| `test_nfl2k5_my_career_mode_audit.py` | 6 | 0.064 | |
| `test_nfl2k5_franchise_autosave.py` | 7 | 8.812 | |
| `test_nfl2k5_franchise_autosave_unicorn.py` | 15 | 7.821 | |
| `test_xbe_patch_memory_writes.py` | 83 | 767.021 | 338,944 |
| `test_xbe_patch_cave_references.py` | 99 | 888.771 | 525,280 |
| `test_nfl2k5_owner_pairwise_composition.py` | 101 | 590.530 | 179,312 |

Both runtime assembly `--check` commands pass. The scratch manifest command
against the pinned retail XBE/XISO writes 10,628 reservations from 123
observed writer calls to `.scratch/m2b-manifest.json`. Its disposable images
were deleted. The protected release manifest is unchanged. The first
continuation manifest attempt refused because a patch source changed during
generation; the complete second run passed after the source stopped changing.
Two frontend assertions initially retained the old draft-notice text and
were corrected; their complete rerun passed. Earlier frame probes exposed
invalid synthetic height bounds; running the real motion constructor fixed
the NaNs. Initial period assertions assumed the wrong cleanup callee and
three overtime timeouts; native evidence established heap cleanup `48640`
and Franchise overtime's two timeouts, and the full rerun passed. Earlier
turnover probes omitted the first-drive constructor and possession event;
both now execute natively. An injury probe's stale selected-play flags
required native `189080` post-play reset before the next selection. These
were fixture initialization defects, not runtime patches or waived failures.
The final two generated-runtime checks and capacity-receipt reproduction
passed again after the boundary tests; the budget JSON is byte-identical.
Final syntax/JSON checks and `git diff --check` passed. Every reported test
path exists and all protected files match the M2a checkpoint. Scratch holds
6.6 MiB and no image/pack; root free space at the final audit was
103,256,952,832 bytes. No acceptance image survives the disc check.

## Noah's witness list and unaccepted scope

No game/emulator boot, GUI display, audio, network or push occurred. Nothing
in this continuation is promoted to witnessed. Before a playable release:

1. Create and cold-load different careers on both allocator layouts; verify
   the visible identity, selected club, card tabs and inline saves.
2. Play the first own fixture, abandon/retry, finish with real stats, pass a
   bye, and complete the final season. Check usable Apartment return, exactly
   one award, year progression and cold reload after every route.
3. Establish a manual slot, enable Auto Save and finish games. Check successful,
   cancelled/failed storage, repeated return frames and the saved statistics.
4. Exercise both units, all supported positions, special teams, snap/clock,
   turnover, timeout, halftime/overtime, injury and substitution through full
   CPU drives and return to MyPlayer. This matrix still needs instruction
   proof as well as Noah's later gameplay witness.
5. Verify the footer fits. Calendar/depth/upgrades/requests, played Senior
   Bowl/draft, live Supersim return and bound hub art need implementation and
   their native proofs before their planned witness can be requested.

M2a remains complete. No M3_DONE, M3-complete bundle or CODEX_DONE marker is
justified by this delivery.

## Commit delivery

The explicit-path `git add` was refused because this checkout's Git index
is on a read-only filesystem. The requested fallback is
`.scratch/r64-mycareer-mode-3.bundle`, containing a continuation commit with
M2a `39796f4` as its parent. It is created using temporary writable Git
metadata and only the explicit code/test/report/receipt paths. The worktree
files remain in place; the brief and scratch contents are excluded from the
commit. The bundle is a reviewable continuation, not an M3 acceptance marker.
No branch metadata in the original checkout is changed and nothing is pushed.

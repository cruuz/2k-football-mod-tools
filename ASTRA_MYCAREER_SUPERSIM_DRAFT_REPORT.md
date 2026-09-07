# r64 MyCareer Supersim and draft start

EXPERIMENTAL / UNWITNESSED. Research and executable component prototypes on
`824cd2b`, isolated from the parallel MyCareer mode owner. No game boot,
emulator session, display, audio, network, disc build, save installation or
push was performed. Unicorn below means bounded execution of native x86
routines with declared input RAM, not a running-game witness.

## Verdict and decisions

**Supersim has a real native foundation. A correct return to live play is not
proved, so this revision does not install an off-field skip patch.** Retail
has both a pause-menu **Simulate To End** and a visual simulator with stepping,
speed, pause/resume and a play log. The earlier design's negative finding is
superseded. Native simulation can import several live scalars, run individual
ticks, and stop at possession/quarter/half boundaries. Its initialization
changes existing stat fields; its finalizer terminates a live match. A native
scenario restore helper writes the reverse scalar subset, but does not restore
the complete live game required by the brief.

The closest supported alternatives are the existing terminal pause action and
the existing visual simulator. Neither is advertised as returning MyPlayer to
the field. The delivered `nfl2k5_supersim` is a bounded host stop-policy and RAM
reader, with an explicit live-resume refusal, `RUNTIME_READY=False` and empty
`REQUESTS`. There is no pretend `apply()` that reports a working game feature.

**Choose the real prior-season route for draft entry.** Store the creation
recipe before bootstrapping the franchise; reserve a generated prospect only
after the final generator, before untouched Combine entry. Play the Senior
Bowl, then let native picks, rookie contracts and undrafted cleanup decide the
club. The two start choices are “Enter the draft” and “Sign as an undrafted
rookie”. The latter uses the parallel mode's choose-club/signing path. Draft
entry uses rookie year index 1; immediate UDFA entry uses index 0. Consequently
a configured 2026 base means a 2027 draft-route rookie season. Do not relabel
the native year byte or silently shift calendar/history bases to conceal that.

**PROVED in one continuous bounded run:** fresh retail roster -> all 268 native
regular/postseason fixture simulations and result commits -> one year rollover
-> retirement/re-signing/free agency -> year-index-1 Combine -> Draft entry.
The class still has 380 prospects and supports 53+53 squads; it is unchanged
by the final Combine-to-Draft transition. This proves the bootstrap route's
native data lifecycle, with frontend presentation excluded. It does not prove
the still-missing live Senior Bowl launch, career save/recovery or full-stack
calendar/roster integration.

**Senior Bowl v1 uses the retail generic NFL uniform template, bank 31.** The
authored 50/51 kits in the earlier report are a later option. The existing
event's side 0 is away and side 1 is home; native match/sim side 0 is home and
side 1 is away. The prototype explicitly maps `(1, 0)` between these orders.
The native filename builder produces `31h0.iff` and `31a0.iff`. The appearance
and free-agent-preview visual match still need Noah's witness.

**Draft outcomes remain uncertain.** Do not substitute a uniform club lottery
or promise a draft selection. Eight complete instruction trials with the same
created QB produced three clubs and five undrafted outcomes. Native cleanup
puts the undrafted player in free agency exactly once. Offer the supported
UDFA signing route if that happens. Senior Bowl scouting output has **zero
draft-stock effect in v1**: the existing projection is presentation, not an AI
input. A later stock modifier needs an explicit score hook and position-fair
validation; it must not inflate permanent ratings as a hidden workaround.

## Delivered components and replay

| File | Concrete behavior |
| --- | --- |
| `mod_editor/core/nfl2k5_supersim.py` | Fixed-span abstract-sim reader; next-possession, next-quarter, end-of-half stop policy; 1..1024 tick cap; last 32 ticker states; explicit cancel/budget/native-error/game-end results. No finalizer or live writer is called. |
| `mod_editor/core/nfl2k5_draft_start.py` | Two-choice route map, validated creation recipe, selected-prospect reservation, candidate-copy name/college/rating injection, stale class/career/year refusal, replay no-op, generic NFL team projection. No save writer or XBE installation. |
| `tests/nfl2k5_supersim_draft_fixture.py` | Pinned bounded XBE/ROST/signed-save inputs, native pointer fixup, instruction caps, RX-protected retail text and explicit leaf substitutions. |
| `tools/nfl2k5_supersim_draft_probe.py` | Independently regenerates code/data span digests and native stop, prospect-game, draft, fresh-start and whole-fixture evidence. `--prior-year` executes the longer season/offseason route. |
| `docs/nfl2k5_supersim_draft_receipts.json` | Derived pins, exact abstract snapshots, seed outcomes and native-component receipts. No retail artwork, roster body or executable is included. |
| `docs/nfl2k5_draft_start_prior_year.json` | Complete prior-year replay: every week/stage transition, 268 native sim/commit pairs, one rollover and stable class at draft entry. |
| `tests/mod_editor/test_nfl2k5_supersim.py` | Standalone stop-policy, native import/reverse/finalizer, deterministic stepping and 22-player frame proofs. |
| `tests/mod_editor/test_nfl2k5_draft_start.py` | Standalone every-position/scheme/side selection, injection isolation/refusal/replay, native clone/personnel/kit/stat isolation and draft-route proofs. |

Run from the repository root:

```sh
python3 tests/mod_editor/test_nfl2k5_supersim.py
python3 tests/mod_editor/test_nfl2k5_draft_start.py
python3 -m tools.nfl2k5_supersim_draft_probe --output .scratch/r64-replay.json
python3 -m tools.nfl2k5_supersim_draft_probe --prior-year --output .scratch/r64-prior-year.json
```

Tests precisely skip missing Unicorn, Capstone, the private pinned USA XBE,
the private retail roster or the signed f0 fixture. The ordinary tests do not
silently substitute a synthetic roster when private evidence is missing. The
long prior-year replay is an explicit development command, not a mandatory
ten-minute standalone test. Each fixture/tick is capped; no whole disc or pack
is loaded. The roster reader reads one bounded resource through the existing
archive reader. The receipt writer is the existing bounded atomic writer.

## A. Native simulation and live state

All addresses below are USA retail virtual addresses. The receipt pins both
the retail XBE hash and the named spans. They are research coordinates, not
free caves or allocations.

| Route | Evidence |
| --- | --- |
| `0xC7A20` | Scheduled-fixture sim. Calls the native sim/commit path; it is not the smallest simulator. |
| `0x10B9C0` | Scheduled core wrapper, live flag clear, then `0x1356D0` persistent fixture/stat commit. |
| `0x10B940` | Complete-game wrapper: initialize, repeatedly call `0x10B250` until 5 or -1, then `0x1053B0`. Five stack arguments, `ret 20`. |
| `0x10B280` | Initializer, ECX=home team, EDX=away team; six stack words: week, fixture slot, optional special-result flag, live-import flag, two optional configuration pointers. `ret 24`. Null configuration pointers select native defaults. The random special-result flag is disabled in these probes. |
| `0x10B250` | Native abstract-simulation tick. Dispatches through the 19 pointers at `0xA96930`, looping over callbacks that return zero. A returned tick can include more than one internal event. |
| `0x106480`, `0x1061F0` | Yardage/down/turnover/score and clock/period processing within native callbacks. |
| `0x103BC0`, `0x103A50`, `0xE7C50` | Team ratings, native depth/personnel construction and 33 personnel pointers per side. Native attribute getters execute; results are not supplied by Python. |
| `0x1053B0` | Terminal finalizer. If live-import flag `0xA971D0` is nonzero, sets `[0xE6028C]+0x10` to zero. Calls native team-stat finalization. |
| `0x10BD80` | Reverse **scenario** helper, ECX=88-byte/22-word scenario, EDX=skip-player-reset flag. Used by `0x10AEB0`/`0x10C040`; not a proved general Supersim return. |

The complete wrapper's **EDX** supplies the live flag; EAX does not. The live
wrapper `0x10B980` calls it with EAX=0, ECX=0, EDX=1 and then copies
`0xA971F0` into `0xE602C4`. Calling that wrapper for a next-drive skip would
still run to completion and finalize. In fresh simulation, offense is not
ready immediately after `0x10B280`; the first native kickoff/setup tick must
execute before reading a valid ownership snapshot.

The state models are related but distinct:

| Abstract sim | Live counterpart / meaning |
| --- | --- |
| `0xA96B68`, `0xA96E80`, stride `0x318` | Two sim-team summaries: original team, depth context, 33 personnel pointers, derived ratings and team-stat pointer at `+0x314`. |
| `0xA9719C`, `0xA971A0`, `0xA97198` | Sim offense, defense and opening receiver. Live team contexts are `0xE5FC20` / `0xE5FC60`, selected by `0xE60280` / `0xE602F0`. |
| `0xA971C0` | Abstract play kind; 0 is scrimmage. Kick/try transitions are separate from a scrimmage possession. |
| `0xA971E8` | Zero-based down; live down is `[0xE602EC]+4`, one based. |
| `0xA971F0`, `0xA971F8` | Zero-based quarter and remaining-quarter fraction. Live quarter is `0xE602C4`; clock is seconds at `[0xE6028C]+0x10`. |
| `0xA971FC`, `0xA97200` | Distance in yards, spot in yards from the opponent's end line. Live positions use field coordinates in cm. |
| `0xE53800`, `0xE53804` | Native log and count; play entries begin at `0xE53874`, up to 768 entries of 20 bytes. Native drive storage begins at `0xE57474`. |
| `0x250DD0` | Native score getter, ECX=side, EDX=category 0 for the game total. |

The global league/draft PRNG is `0xB12680`; the match PRNG is `0xE5FCA0`.
Both are seeded through real `0x48BE0`. Zero-filled PRNG RAM produced repeated
penalties in an exploratory trial and is not valid seeded evidence.

The abstract play decision is `0x106A30`, with late-clock/score strategy from
`0x105690`; it reads down, distance, spot, score difference, remaining time
and the sim-team configuration pointer at `+0xE0` (default table `0x4F6A20`).
Participant selections live at `0xA971A4/A8/AC`; native callbacks produce
yardage, clock use and log/stat updates. Attribute evaluation `0x246A80` uses
the table at `0xAC47C0`, real rating getters, height/weight and
`0x246990 -> 0x13E2B0` condition adjustment when the player `+0x28` mask
`0x3E0` is set. The `+0x50` consistency byte also participates; it is not a
proved live fatigue field. No import/export of the live per-player fatigue
state or current live PLAY/planner call was identified. The sim's abstract
play choices must not be described as replaying the same live playbook calls.
Complete injury and fatigue transfer remains an explicit blocker, even
though native availability/rating and weekly transaction code executes.

**PROVED live import prefix, with no substituted native helpers:** synthetic
live Q2, 123 seconds of a five-minute quarter, third-and-10, a positive field
direction and LOS z=914.4 cm becomes sim quarter 1, clock fraction 0.41, down 2,
distance 10, spot 40, with the expected offense and opening receiver. Import
uses `50 - direction * z / 91.44`. The test stops at `0x10B642` before team
initialization, making its prefix boundary explicit.

That same prefix executes `0x1F1CD0`, clearing 13 stat/category fields per
player through `0x1EC830`, and `0x1ECAF0`, resetting shared stat arrays. The
poisoned prior-stat test detects the change. This disproves an assumption that
live import preserves all accumulated state unchanged. It does not establish
which fields could later be safely merged or reconstructed.

**PROVED reverse scalar subset:** the complete unmodified `0x10BD80` writes
scores 7/10, timeouts 1/2, Q2, clock 123 seconds, third down, chosen offense,
LOS/first-down coordinates and opening receiver into synthetic live objects;
it also runs native depth rebuilds. The input scenario is supplied explicitly.
The test does not fabricate an inverse for every simulator field. In
particular, the initializer does not import a corresponding complete timeout
model merely because the scenario writer can set two timeout words.

**PROVED stop policy on real native plays:** from the pinned f0 clubs and seed
12345, after initial kickoff, next possession takes 4 ticks, next quarter 37,
and halftime 78. Both runs of each test are identical, with no finalizer or
native leaf substitution. The receipt includes scores, clock, down, spot and
log counts. The ticker contains native abstract snapshots, not invented prose
play descriptions. Reuse the visual simulator's native log formatter for a
future user-facing ticker. Cancellation/budget exhaustion are explicit states
that require caller rollback; they never authorize a live return.

Quarter/half boundary ticks can retain the preceding down/spot while the next
internal transition is pending. A terminal tick can briefly have a negative
clock fraction. The reader preserves that overrun rather than clamping away
the evidence. In overtime, the end-of-half request runs to native game end.
These are additional reasons not to copy a snapshot directly into live RAM.

### Pause and visual simulator search

The real pause descriptor is a 52-byte type-9 row at `0x4E8D08`, with text
pointer `0xE626C4` (“Simulate To End”) and action at row `+0x28` pointing to
`0x6EFE0`. The handler checks VIP/controller participation and can warn that
accumulated VIP stats/milestones will be lost; cancellation returns. The
accepted path includes `0x6EE50 -> 0x10B980`, then match completion calls
`0x111060`, `0x10EC10` and `0x64C00`. This is terminal simulation of a live game.
No next-possession/quarter/half pause action was found in these descriptors.

The visual-simulator popup tables at `0x4F63E0`, `0x4F6410`, `0x4F6440`
contain Begin Simulator, Sim To End, Resume Simulator and Return to Simulator.
`0xEC390` advances the native simulator, sometimes with a second tick for a
special event. `0xEC560` and the surrounding driver control stepping;
`0xEC570` handles the popup, with the terminal loop at `0xEC630`. Speed is
stored at `0xE60200`, with getter/inc/dec family `0x27B820..0x27B8C0` spanning
values 0..3. This is suitable native ticker/pause infrastructure.

**Correction to the Senior Bowl handoff:** `0xEC65A -> 0x1356D0` is the visual
simulator's persistent result commit, not the general played-game commit.
The played-franchise path is `0xC5D60`, including fixture flag update at
`0xC5D92`, result call `0xC5D99 -> 0x1356C0`, and `0x134140`. Both paths must
be excluded or redirected for an isolated Senior Bowl. Blocking only EC65A
does not protect a played exhibition's return path.

### Engine fast-forward candidate

`0x11A7C0` is an inner gameplay dispatcher, not the complete frame/render
boundary. The outer `0x64CD0` uses the game manager's delta at `+0x104`, pause
and speed handling and other clock/rule/presentation phases. Callers include
`0x13610` and `0x1124E0`. `0xE5FFA8` is a normal game-speed setting: 0 uses
0.9, 1 uses 1.0, other values use 1.1. Writing “4” there is not four-times
acceleration.

The reused 22-player kickoff fixture executes all 27 native inner phases,
including planning, pose/animation, collision and audio-phase entry. Four
ordinary 1/60 updates equal two groups of two. One 4/60 update produces
different player state and only one traversal of those phases. The inner
fixture's game clock remains 600 seconds. Hardware input, final audio
submission and the existing fixture's documented attribute leaves remain
substituted; their details live in `tests/nfl2k5_kickoff_frame.py` and its
inherited fixtures. This is neither an audio-muting implementation nor proof
that every frame phase is isolated from rendering.

**HYPOTHESIS:** a scheduler can run several complete fixed updates per rendered
frame, gate presentation/audio submission and stop at a settled play-call
boundary while native AI runs both sides. Controller detachment alone is
insufficient. Console CPU budget, renderer ownership, streaming, wall-clock
timers, frame-dependent randomness and emulator scheduling remain unmeasured.
No instruction probe establishes a safe 4x/8x real-time performance claim.

## B. Prior season, prospect game and draft

### Native route map

| Boundary | Native work that must execute |
| --- | --- |
| Fresh franchise | `0x13EE10`, native roster/league/salary setup. `0xE60120=0` omits preseason, calls `0x2BF270`, sets stage 8, and generates 380 prospects through `0x2BE940`. With preseason enabled, it starts stage 7 instead. |
| Hidden regular season | `0x247D40` advances native weeks, including CPU transactions and `0xC7CB0`/`0xC7A20` fixture work. Use native getters and stage boundaries, not a Python loop that invents standings. |
| Regular to postseason | `0x2480B0 -> 0x2A7E50`; retail postseason starts at absolute week 17 and ends at 22. The table's five postseason weeks are not an absolute week limit of five. |
| Postseason to next year | `0x2480B0 -> 0x2BDB00`, `0x13ED70`, cap work, then `0x247B40`: draft order, progression/ages, contracts/coaches and year increment, entering retirement stage 1. A zero-user-club franchise takes the native exit branch instead. |
| Offseason | Native stages 1 retirement, 2 re-signing, 3 free agency, then 4 Combine. `0x247B20` only installs stage/count/elapsed state; directly calling it with 4/5 does not initialize these prerequisites. |
| Final generator | `0x2BE940 -> 0x2BE900 -> 0x2BD390/0x2BE6F0`. Also called by `0x2BF8B0` at preseason-to-regular transition. Reserve only after the last applicable generation. |
| Senior Bowl gate | Hold untouched stage 4, four Combine days and unused hours. Both manual `0x2480B0` and automatic `0x2486F0` must respect the pending event. |
| Combine to draft | Native temporary-player cleanup `0x2BDA90`, draft reset `0x325A30`. This transition does not call the class generator. |
| Draft | `0x3254D0` resolves on-clock club using round `0xE3C0A8`, pick `0xE3C0A4` and seven 32-byte orders at `0xE3C0B4`. `0x325B90` chooses/signs; `0x325A50` advances; `0x325D00` detects completion. |
| Contracts / undrafted | `0x325B50 -> 0x322980`, native roster append `0xC3EE0`, transaction log and cap recomputation. Native negotiation remains an option. `0x31E430` clears leftover prospect flags and appends undrafted players through `0x242560`. |
| Rookie season | Follow native signing stage 6, preseason stage 7 and regular stage 8. Transfer the mode's user-club binding to the actual signed club; do not attach MyPlayer to the bootstrap club. |

The fresh-start proof uses the hash-pinned **retail ROST with zero prospects**,
not an existing franchise. The native initializer produces exactly 380
prospects, stage 8, 17 regular weeks, week 0, year 0, with no substituted
helpers. A subsequent complete `0xC7A20` runs 171 native ticks and one real
`0x1356D0` commit; its schedule row becomes `03150a0909040900`. That row is
fixture metadata, not an encoded 21-10 score. Only progress rendering at
`0x177990` is substituted; `0x24C380` is a small native simulation UI-state
writer and executes unchanged in the delivered proof.

Starting from the signed f0 save instead left 542 prospects after re-running
the initializer. That exploratory input is rejected as evidence of a fresh
start. The long probe also exposed the zero-user-club exit after completing
the regular season and postseason. Native club registration is `0xC4D30`
(ECX=team, EDX=nonzero user value); the bootstrap policy activates a temporary
club owner at postseason exit. The frontend/menu context is a separate ECX
argument to `0x2480B0`, not a roster pointer. No MyPlayer roster assignment is
performed at that boundary.

The completed long replay records `0xC7A20=268`, `0x1356D0=268`, and
`0x247B40=1`. After fresh initialization it observes no further call to
`0x2BE940` on this no-preseason path. It reaches stages 1, 2, 3, 4 and 5 in
year index 1, with 380 current prospects and unchanged class rows at draft
entry. A synthetic zero-depth menu context services the native pop no-op;
the only registered leaves are progress rendering and informational dialog
display. No informational dialog was encountered and unexpected decision
dialogs are an explicit test failure. There is no stub for sim, injury/weekly
transactions, retirement, contracts, draft order, progression or year rollover.
The full run needed a three-billion-instruction cap per native week/stage;
the earlier 1.5-billion cap stopped during the eleventh fixture's real stat
commit. These limits are laboratory execution budgets, not Xbox timing data.

**Offseason shortcut verdict:** no complete native “begin in offseason” route
was proved. The generic stage setter is not such a route. Reproducing class,
orders, contracts, salary queues, histories, coaches, schedule and all saved
state by forcing a few globals would create another franchise initializer.
The genuine preceding-season path is the supported research direction.

### Creation, selection and temporary rosters

Reservation selects an ordinal already chosen by `select_squads` for the
requested position and event side. This matters because `Event.validate()`
requires the exact selection implied by the saved class, positions and seed.
Replacing a participant after selection, or changing a prospect's position
to force inclusion, violates that codec. Tests cover every represented
position, both sides, and retail/edge/one-pool schemes; a retired OLB slot in
the one-pool scheme is not invented.

The host reference uses the existing name pool and college writer on a copy.
It retains the generated ordinal, position, eligibility and ownership; checks
the full class fingerprint, career identity and year before mutation; and
refuses late/changed/foreign input. Ordinary rating overrides are validated
1..99; style/packed channels are excluded. Source membership and other
players stay identical. Repeating the same recipe with the updated reservation
returns identical bytes. This is not a persistent native injection: the
parallel mode must store the recipe, ordinal/epoch and replay state in its
owned career state and apply its generator guard at the correct boundary.
No companion setup file is introduced by this work.

**PROVED native team construction:** take the native fixed-up NFL generic team
(retail ordinal 51, asset bank 31), create two caller-owned 500-byte donors,
replace only the pointer slots/count and stale returner selections, then run
`0x61730`. It copies all 53 records per side into native match pools
`0xB30C4C` / `0xB321A0`, updating `+0x34` to native side 1/2. Initially all
106 history pointers alias the source. They must not be treated as private
stat storage merely because player records were copied.

The full native simulator initialization subsequently rebinds all 106 stat
pointers. All 33 personnel pointers per side resolve to that side's cloned
53-player pool. Native uniform filename generation produces the two generic
NFL filenames. The complete prospect game and terminal stat finalization run
with the entire source franchise arena **read-only**, no substituted native
helpers and no persistent franchise result commit. Source arena digests
remain equal. This proves a native simulated prospect game can be isolated
for these inputs; it does not prove live-engine history/injury/coach isolation.

The old Senior Bowl v1 `Kit` validator accepts only banks 50/51. It currently
refuses bank 31. This prototype does not encode an authored kit and silently
call it generic. `WIRING.md` specifies the needed owner/codec change and side
mapping before an event can launch. The preview's older authored-kit defaults
are not the v1 career requirement.

**HYPOTHESIS live exhibition adapter:** run the ordinary exhibition setup and
loader with these donor squads, generic kit choices and MyPlayer's actual
native match side; bind player lock after roster cloning and depth rebuild;
return to a held career event at game completion. Native match clones, coach
state, history pointers, current controllers/settings and every completion
path need owned lifetime/restoration. Keep Senior Bowl statistics only in its
event/scouting record, not the NFL season or player career totals. Do not
resume the Combine from the visual-sim commit hook alone.

### Native drafting and stock

The installed `nfl2k5_draft_ai` replaces `0x31E0F0` in place. Its score uses
position-relative overall, club need, position value and CPU jitter of up to
roughly 0.06 on a 0..1 scale. Native contracts and ownership remain native.
Seed changes are not a uniform club lottery: team needs, class strength,
draft order, prior selections and changing roster capacity all participate.

The fixed-club first-pick probe returns 32 distinct candidates for seeds 1..32.
The stronger experiment runs all 224 picks and native undrafted cleanup with
the same created QB ordinal 2008, unchanged generated ratings and pinned f0
class/club state, with auto rookie signing (`0xE60134=1`):

| Seed | Outcome |
| ---: | --- |
| 1 | Undrafted; one native free-agent reference |
| 2 | Detroit Lions, overall pick 83 |
| 3 | Undrafted; one native free-agent reference |
| 4 | Undrafted; one native free-agent reference |
| 5 | Undrafted; one native free-agent reference |
| 6 | Dallas Cowboys, overall pick 108 |
| 7 | Undrafted; one native free-agent reference |
| 8 | New England Patriots, overall pick 214 |

These are bounded instruction results, not a probability estimate or a promise
about a different creation recipe. Native signing appends a player once and
clears the prospect flag; cleanup clears the undrafted prospect flag and adds
exactly one FA reference. Tests replay both a drafted and an undrafted seed.
The caller normally clears `0x10` before `0x325B50`; directly calling the
signing helper without the native pick path leaves an incorrect prospect flag.

A future Senior Bowl stock effect should be a saved, once-applied, bounded
position-relative selection-score adjustment for this identity. Test QB,
OL, defense, K/P, human autopick and CPU choices against class means and
team needs. Existing scouting-line text is not read by the draft AI, and
improving one shared event line alone cannot change the native pick.

## Integration, budget and remaining proof

No protected file or `nfl2k5_my_career*` file was changed. Neither reference
component installs bytes, so no allocator row, manifest list or gate union is
added. Both expose `REQUESTS=()`. This is the brief's explicit “no proved full
Supersim path” fallback, with working native components instead of an enabled
partial patch. Existing memory/reference gates were run on the complete
landed owner union in both orders.

The 41-request allocator plan fits 12,300,288 bytes and leaves 54,800 RX,
4,096 RW and 8,616 RO bytes available to new owners before alignment. No
part of that spare RW was claimed. Future work must first fit within the
existing Senior Bowl 65,536 RW and MyCareer 4,096 RW budgets, including event,
temporary donors, histories/coaches, recipe/identity, phase state and restoration.
The 2 MiB Unicorn arena is a **test fixture**, not a runtime allocator request.
Native working globals are used by native routines, not repurposed as caves.
No retail-reference-bearing span is claimed as free.

The long bootstrap and all native live return paths remain separate from
2026/calendar/18-week/playoffs14/modern-roster composition. Runtime testing
must use their native getters and matched ROST templates. The generic bank 31
and donor ordinal 51 are pinned-retail evidence; grown or reclassified rosters
need identity/asset lookup and current scheme validation, not a universal
hard-coded team ordinal. `nfl2k5_franchise_2026` remains a dormant rules owner;
this work does not assert that its modern roster rules suddenly enforce live.

The exact protected-file handoff is appended to `WIRING.md`. No Build toggle,
capability or preset is enabled by this revision. No external setup file or
save companion should be required by the eventual in-game creation flow.

## Noah's witness list and exact next execution work

Nothing below has been witnessed. First finish bounded execution evidence,
then ask Noah to play the completed experimental integration.

1. **Prove a full live-sim round trip.** At a settled live play-call boundary,
   capture both team/clock/LOS contexts, all match/player stat rows, play and
   drive logs, injuries/fatigue, pending penalties, timeout/clock-running state,
   first receiver, overtime state and the owned momentum state. Exercise
   no-op import/restore first. Every field outside a declared transient set
   must match. Current scalar-only `0x10BD80` proof does not satisfy this.
2. **Close cumulative stats and return flow.** Execute a real live play,
   import, simulate one possession, transfer only proved deltas and enter the
   real live play-call/setup flow. Prove no double participation, erased VIP
   stats, duplicated scores, extra drive, timeout reset or native finalizer.
   Then repeat from the other team/direction, with injury and pending penalty.
3. **Boundary matrix.** Offensive and defensive MyPlayers; punts, turnovers,
   safety/free kick, TD/try/onside transition, quarter flip, halftime kickoff,
   two-minute state, running/stopped clock, zero clock and overtime. Stop only
   after the appropriate transition is settled. Include cancelled/budgeted
   skips and repeat requests without advancing twice.
4. **If using engine acceleration, prove the outer scheduler.** Run complete
   fixed steps, separate rendering/input/audio submission, inspect native
   animation/camera/replay/streaming timers and require the same final state
   as ordinary updates. Benchmark console and emulator separately. Noah then
   checks stutter, sound bursts, frozen cameras and prompt/input timing.
5. **Noah's Supersim play test.** Start each side's off-field period, choose
   next possession/quarter/half, read the summary, and play the next snap.
   Compare scoreboard, play-by-play, box score, injuries, penalties, momentum
   and timeout counts before/after and after save/reload. Verify the untouched
   retail Simulate To End remains terminal and its VIP warning/cancel works.
6. **Noah's two start choices.** Create name, position, college and appearance
   entirely in game. Immediate UDFA signs with the selected club in index 0.
   Draft entry advances the hidden preceding year with understandable progress,
   cannot be broken by cancelling/reloading, and reaches the same saved class.
   Temporary franchise club ownership never becomes MyPlayer membership.
7. **Senior Bowl launch proof and witness.** Validate complete 53+53 squads,
   all normal/special personnel, generated names and the created player's
   position on both sides. Bind player lock only after native cloning. Noah
   checks generic NFL light/dark uniforms, helmets, numbers, no NFL donor
   players, and every supported player position. Authored kits are deferred.
8. **All event exits and persistence.** Finish, overtime, quit, retry, skip,
   pause, abort load and save/reload at each phase. A running event recovers as
   pending or restores the defined checkpoint; completion is recorded once.
   No partial live game is called “complete”. Both manual/automatic Combine
   advance paths hold the pending event. NFL records, injuries, clubs,
   controllers and the next ordinary game survive unchanged.
9. **Draft identity and club handoff.** The same named player/college survives
   the final generator, Senior Bowl, every native pick, contract negotiation
   or auto signing, and subsequent reload. Drafted players bind to their actual
   club once; undrafted players have one FA reference and can use UDFA signing.
   Full clubs, releases, IR/reserves, future class regeneration and later
   seasons must never recycle the protected identity into another player.
10. **Stack witness.** Use the 2026 roster/calendar, 18-week season, expanded
    playoffs, practice squad/modern rules, ability/depth locks, uniform-choice
    patch and MyCareer M2 together. Repeat ordinary franchise/Pro Bowl games
    afterward. Existing gates prove binary composition, not this gameplay.

## Validation record

- `test_nfl2k5_supersim.py`: **12 passed**, including native replay, scalar
  import/reverse, stat-reset counterexample, terminal-clock counterexample,
  overtime policy and the fixed-frame/large-delta comparison.
- `test_nfl2k5_draft_start.py`: **11 passed**, including all position/scheme
  selections, copy injection, native generic prospect game and complete
  drafted/undrafted replay.
- `test_xbe_patch_memory_writes.py`: **79 passed**, 305.539 seconds.
- `test_xbe_patch_cave_references.py`: **95 passed**, 388.814 seconds.
- Allocator plan: **PASS**, 41 requests, no allocation or image build performed.
- Default native receipt command: **PASS**, including all eight complete
  drafts, the full prospect game/finalizer with source memory read-only,
  fresh franchise initialization and a real fixture commit.
- `--prior-year`: **PASS**, 268 native sim/commit pairs, one rollover,
  year-1 stage-5 entry, 380 unchanged prospects and 53+53 selection. Its exact
  transitions are in `docs/nfl2k5_draft_start_prior_year.json`.
- All six new Python files compile; `git diff --check` passes. No protected
  implementation file changed. The final receipt incorporates the explicit
  away/home conversion and the extra terminal tick after regulation.
- Disk check before delivery: **109,491,802,112 bytes free on `/`**; scratch
  was 564 KiB before bundle metadata. No disc/pack copies or acceptance images
  were created. Scratch remains below 200 MB.

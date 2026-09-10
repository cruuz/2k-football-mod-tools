# NFL 2K5 accelerated clock: retail research, beta 65 job A

Research checkpoint, 2026-09-10. Branch `astra/b65-accel-clock`.
This checkpoint precedes any accelerated-clock XBE writer. Inspection used
Capstone against the local USA retail `default.xbe`, opened read-only. No
emulator, display, disc build, or network was used. No executable is included.

**PROVED below means inspected retail instructions, not a played-game witness.**
The proposed hook policy and its synthetic execution still require the bounded
native tests described below. Visible timing and game feel remain UNWITNESSED.

## Address mapping and evidence scope

Use `nfl2k5_cave_oracle.XbeImage.read()` for virtual addresses. The `.text`
addresses below map to file offsets VA minus `0x10000`; that shortcut does
**not** apply to all data sections. An early probe using that shortcut for
constants was discarded. Correct section-aware reads prove `0x4E4180` is
float 0, `0x4E6D58` is 120, `0x4E4188` is 300, and `0x4E6D4C` is 3.
The repository's `RETAIL_SHA256` pin and section parser are the inputs for
reproducible tests. Complete dependency hashes must be recorded by the writer.

## Timer implementation and lifecycle

| VA / field | Inspected retail behavior |
| --- | --- |
| `0xE6028C` | Pointer to game-clock timer; float seconds at object `+0x10`. |
| `0xE60294` | Pointer to play-clock timer; float seconds at object `+0x10`. |
| timer `+0x14` | Float rate, initialized to 1. |
| timer `+0x18` | Flags: mask 6 inhibits ticking; bit 8 selects increasing rather than decreasing time. |
| timer `+0`, `+4`, `+8`, `+0xC` | Child, parent, next, previous links used by the recursive timer tree. |
| `0xAF400` | Initializes timer links/time to zero, rate to 1, flags to 9. |
| `0xAF2F0` / `0xAF470` | Attach a timer to a parent; absent parent selects `0xB71CF0`. |
| `0xAF490` | Native timer tick. At `0xAF493`, `test al,6` skips the update when stopped/paused. Otherwise multiplies delta by rate, changes sign unless bit 8 is set, adds to `+0x10`, and updates children. `ret 4`. |
| `0xAF4F0` | Stops a timer: sets bit 2 and recursively pauses its subtree via `0xAF3B0`. |
| `0xAF3B0` | Sets bit 4 recursively. |
| `0xAF510` | Starts a timer by clearing bit 2; honors inherited pause bit 4. |
| `0xAF3D0` | Clears inherited pause recursively where local stop bit 2 allows it. |
| `0xAF310` | Returns true iff `(flags & 6) == 0`. |
| `0xAF320` | Direct signed adjustment of `+0x10`, respecting direction bit 8. It is not a play-call event. |
| `0xAF2C0` | Advances root `0xB71CF0`; stores frame delta at `0xB71D0C`, increments `0xB71D10`. |
| `0x11A7C0` | Shared native frame dispatcher. Calls `0xAF2C0` at `0x11A837`, then AI/presentation/simulation phases. Game speed comes from `0xE5FFA8`. |
| `0x55F0B..0x55F47` | Game setup assigns the timer globals. Game object `0xB28680`, play object `0xB286B8`, other clocks `0xB2869C`, `0xB286D4`, `0xB286F0`, `0xB2870C`. |
| `0x55F51` | Writes float 40 (`0x42200000`) to `0xE602AC`, the native play-clock reset amount. |
| `0x55F5B` | Stores float quarter length in `0xE602B0`. Existing overtime owner hooks this instruction: do not take it. |
| `0x55F61..0x55FBA` | Initializes/attaches game and play timers, clearing direction bit 8 on both for countdown. |
| `0xB6DC0` | Period reset: copies `[0xE602B0]` to game `+0x10` at `0xB6DCB`, and `[0xE602AC]` to play `+0x10` at `0xB6DD9`. |
| `0xB6DE0` | Stoppage reset: auxiliary `0xE602A0` gets 30; play timer gets float 25 at `0xB6DFD` and is stopped via `0xAF4F0`. |
| `0xB6E10` | Clears/stops the auxiliary stoppage timer. |
| `0xB6E30` | Normal reset: clears game-flags bit `0x800`, stops auxiliary timer, sets play clock from `0xE602AC` at `0xB6E5C`; starts it for phases 3/4, stops it otherwise. |
| `0xB6E80` | Starts play clock for phases 3/4 without resetting its value; otherwise stops it. Clears auxiliary stoppage timer. |
| `0xB6EB0` | Stops play clock, tail-calling `0xAF4F0`. |
| `0x157D20` | Clamps nonpositive play-clock seconds to zero. |
| `0x658B0`, `0x658C0`, `0x65D10` | Game pointer, play pointer, and raw play-seconds getters. |
| `0xFBB10` | Scorebug play-clock getter. Reads play `+0x10`, calls integer conversion `0xFB430`, rounds positive fractional seconds upward, clamps negative result to zero. An exact integer 20 displays 20. |

The normal reset is **40 seconds** and the separate stoppage reset is
**25 seconds**. Changing `0xE602AC` would only make a slider; it would neither
perform game-clock runoff nor wait for play selection. It is not the feature.

## Game state, stopped clock, and dead-ball restart

| VA / field | Inspected retail behavior |
| --- | --- |
| `0xE602C4` | Period: 1..4 regulation, 5+ overtime. |
| `0xE602B0` | Float length of the current period. |
| `0xE602B4` | Phase: 0 toss/pregame, 1 safety kick, 2 kickoff, 3 point after, 4 scrimmage. |
| `0xE602B8` | Play state: 11 between plays, 12 formation/lineup transition, 13 ready before snap, 14 live play. Other observed stoppage/presentation states include 9, 10, 18..21. |
| `0xE602C8`, `0xE602CC` | Presentation substate and its time, reset at state changes. |
| `0xE60280`, `0xE60284`, `0xE60288` | Offense/possession, defense, previous possession. |
| `0xE5FC20`, `0xE5FC60` | Native team objects. `team+0` opponent, `+4` players, `+0xC` play-selection state, `+0x30` controller pointer. |
| `0xE602EC` | Native game/play context. |
| `0xE602D4`, `0xE602D8`, `0xE602DC` | Current and prior native play descriptors. |
| `0xE602FC` | Native game flags. `0x400` saves permission to restart the game clock; `0x20` records the two-minute warning. |
| `0xB8F50` | Samples `(game.flags & 6)==0` into game-flags bit `0x400`, clears it on changed possession or previous descriptor `+0x80 != 0`, then stops both clocks. |
| `0xA0090` | Tail alias of `0xB8F50`; called by presentation dispatch at `0x1F7E64`. |
| `0x22EBED..0x22EBF3` | Copies context `+0x164` to play descriptor `+0x80`, subsequently used in stoppage/reset decisions. The complete semantic producer census of `+0x164` is still required. |
| `0xB90A0` / `0xB90D5..0xB911D` | After applying a dead-ball descriptor, unchanged possession and descriptor `+0x80==0` can select the normal 40 reset. Other paths stop game time, clear `0x400`, set `0x800`, and use the 25 reset. Also consults `0x136D40`. |
| `0xB7150` | Stoppage path saves restart permission, stops both clocks, transfers descriptor state. |
| `0xB7110` | Conditional stop rule: period 2 at <=120, period 4 at <=300. This is a native regulation-specific rule, not the requested accelerated-clock two-minute policy. |
| `0xB7200` | Restarts game clock only when `0x400` is set and phase is 4, then clears `0x400`. |
| `0xA1CD0` | Tail alias of `0xB7200`. Called at normal offensive play-call completion `0xB86E0`. |
| `0xB6F10` | Starts game clock if stopped except in phase 3; a snap/gameplay helper. |
| `0xB8BA0`, `0xB8C90` | Temporary clock hold/resume: save game/play running states in low bits of `0xE602FC`, stop both, and restore only saved permissions. |
| `0xB8810` | Timeout path stops both clocks and clears relevant low/restart flags. |
| `0xB9470..0xB9593` | Penalty/re-spot processing; may clear restart permission and calls `0xB7200` after applying the spot. |

A runoff must inspect the **actual game timer after the native restart decision**.
Testing only phase or a last-play type is insufficient. The timer mechanics
and descriptor consumer are proved; mapping every incomplete/out-of-bounds/
injury producer to that state is still an explicit research obligation.

## Play selected, huddle break, CPU and human

`0x9F360` is the shared team completion routine. It calls `0x189020` (sets
bit 1 of `[team+0xC]+0x24`), presentation helpers, then `0xB8650` at
`0x9F394`. Its `EBX` input distinguishes team paths, not a clock policy.

`0xB8650` receives the team in ECX, preserves it in EDI, and checks it against
`[0xE60280]`. Only the offense takes `0xB867F..0xB8693`, invoking state-change
notifications and storing state 12. Both teams can run `0xB1830` and
`0xB6E80`; only the offense passes the second possession check at `0xB86A5`
to `0xB86E0`, the call to `0xA1CD0` that restores the eligible game clock.
This is a candidate completion hook: run native `0xA1CD0` first, then decide
runoff, preserve its outputs, and return to `0xB86E5`.

| Path | Inspected chain |
| --- | --- |
| Shared completion | `0x9F360 -> 0xB8650 -> 0xB86E0 -> 0xA1CD0 -> 0xB7200`. |
| Offensive completion | `0xA2B60` sets EBX=1 and calls `0x9F360` at `0xA2B6B`. |
| Other-team completion | `0x9FE20` sets EBX=0 and calls `0x9F360`; `0xA2B8D` can invoke it for the opponent. |
| CPU choice | `0xA2AAE..0xA2AD9` checks offense controller pointers `+0x38`/`+0x30` are absent, calls `0x153170`. That helper calls native CPU selection `0x20B670` or `0x207440`, then `0xA2B60`. |
| Selection flags | `0x1889C0`/`0x1889E0` read selected-play bit 8 for offense/defense; `0x188A10`/`0x188A30` read completion bit 1. |
| Ready test | `0x1580F0` reads team selection flags `+0x24`, requires bit 2 (or defensive bit `0x20`). |
| Ready transition | `0x158C90` checks state 12 and calls `0x1580F0` for both teams. Only both-ready takes `0x158CBC`, then stores state 13 at `0x158CC1`. |
| Frame route to ready | `0x11A888 -> 0xE9210 -> 0x158CE0`; `0x158F1D` invokes `0x158C90` in state 12. |
| Audibles/re-lineup | `0xB87D0` can move state 13 back to 12. A hook on every 12->13 transition would require a per-snap latch. |

The human input path upstream of completion must be exercised as well as
the CPU route in bounded tests; merely changing a synthetic controller
pointer is weaker evidence than executing the two callers.

## Snap and delay of game

`0xB6F30` admits the snap only when `0xE602C0 != 1` and play state is 13.
It notifies state 14, copies descriptor history, and stores state 14 at
`0xB6FB3`. It then calls `0xB6EB0` at `0xB7010` to stop the play clock.
The return address of that call is `0xB7015`. This is a precise successful-
snap signal available from a wrapper on `0xB6EB0` without changing the snap
body. **The QB Spy owner already owns `0xB6FB3` and hashes the complete
`0xB6F30` body; do not place a second hook inside that body.**

`0xB2580` is the delay-of-game check. It requires enabled penalty global
`0xA89B60`, one of states 11/12/13, and play-clock `+0x10 <= 0`.
At `0xB25B8` it calls `0xB23F0` with the offensive team. State handlers
`0xB4500`, `0xB4530`, `0xB4560` call the check; when a violation is returned
they transition through `0xA0390`. `0xB45A0` handles snap-time rules separately.
The patch must never set play time to zero, change these branches, or call
the frame dispatcher with an enlarged delta.

## Two-minute warning and quarter boundary

`0x205F80` returns remaining time in the half: current game timer plus
`0xE602B0` in periods 1 and 3, current game timer alone otherwise, clamped
at zero. Thus overtime 5+ naturally returns its current period's remainder.
The requested runoff must bypass at <=120 in every half/OT period, and
must not subtract through a half end.

`0x157D40` uses integer remaining time from `0x157210`. Its warning test
checks configured quarter minutes `0xE6000C > 2`, remaining <=120,
period 2 or >=4, period length >120, and `0xE602FC & 0x20 == 0`.
Some live/stoppage states defer the warning; others call `0xA0190`.
`0xA01D7 -> 0x1588B0` sets flag bits `0x60`, stops game and play clocks,
clears the auxiliary timer, and sets presentation state `0x18`.

The zero-clock portion `0x157E22..0x157EAE` stores exactly zero, stops
the game timer, and calls native period-end handling `0xA2970` where its
state/phase guards allow it. A Q1/Q3 runoff may clamp to zero and leave
this logic in control. A runoff must not create a negative value or change
the period itself. Crossing the warning threshold from above 120 needs an
explicit policy; do not silently skip the warning.

`0xB8910` writes the new period then calls `0xB6DC0`. Game/period setup
`0x158110`, `0x158160`, `0x158320`, `0x158390` also calls that reset.
A period-reset hook can suppress runoff until the first successful snap.

## No-huddle / quick-snap path

The UTF-16 HUD string at `0xE6CBD0` is selected at `0xFF54D` when the
team's HUD row `0xBA3180 + index*0x4C` is nonzero. `0xFF120` returns that
row's mode, using native team index getter `0xFEDB0`.

This is more than a string reference: at `0x18F906` / `0x18F994` the
native play-selection input routines call `0xFF120`, compare against 1,
clear selection flags `0x1000` and 4, and **tail-call `0xA24B0`** instead
of the normal selection completion. `0x18F2D1..0x18F30F` is another caller.

`0xA24B0` chooses the supplied play or reuses `[offense+0xC]+0xC`, clears
flag `0x80`, calls `0x9F990` (installs selection), `0x1CEAC0`, `0x9FA80`,
and ends through `0x1FFD20`. It does not directly call `0xB8650`.
`0x189270 -> 0x189210` validates a prior scrimmage possession and routes
the repeat-play choice through `0xA24B0` at `0x189298`.
The player-task path `0x1FFDFB..0x1FFE02` also reuses the previous play
through that routine, for an uncontrolled team and selection flag `0x80`.

A wrapper at the `0xA24B0` entry can mark the current snap ineligible;
the successful-snap signal clears it for the following play. Native
no-huddle execution and its later ready/completion interactions must be
tested, not replaced by a host boolean named `no_huddle`.

## Owned space and proposed implementation boundary

The RC85 owned-space doctrine says the cave oracle certifies no unused
retail code. Use `nfl2k5_xbe_space` named allocations in the complete owner
union, not a guessed retail cave, and not writable `.text` data.

Candidate live sites, subject to oracle/interior-reference proof before writing:

- `0xB86E0`: completion call, after native permission to restart the clock.
- `0xB6EB0`: play-clock stop entry; clear latch only for return `0xB7015`.
- `0xB6DC0`: native period reset entry; suppress first snap of period.
- `0xA24B0`: no-huddle/repeat-selection entry; suppress this snap.

Plan separate owned RX code, RO option words (enabled and minimum seconds),
and RW per-snap latch. A timeout/review/injury/re-spot cannot clear the
latch; only a successful snap may do that. Retain all native stop/start
flags and delay-of-game rules. Code must be reparseable, byte-pattern
checked, digest-repinned, and idempotent. Production cave manifest and
Studio/build/registry edits are integrator-owned and belong in `WIRING.md`.

## Remaining proof obligations at this checkpoint

| Item | Status |
| --- | --- |
| Timer direction, rate, stop/pause and tick instructions | PROVED by retail inspection |
| Native 40 and 25 reset sites | PROVED by retail inspection |
| Shared offense completion, ready transition, successful-snap signal | PROVED control flow; bounded execution pending |
| Delay-of-game guard and call | PROVED by retail inspection |
| Two-minute flag and half-time getter | PROVED by retail inspection |
| HUD no-huddle input reaches distinct repeat-selection path | PROVED control flow; bounded execution pending |
| Every incomplete/OB/injury producer's stop semantics | Partial: timer/descriptor consumers pinned, producer census pending |
| Punt/FG/kneel classification | Pending retail play/header census; no guessed classification may be installed |
| Hook ownership/interior targets, option allocation | Pending oracle proof and named reservations |
| Off, running/stopped, 1:59, last-snap, CPU, no-huddle executions | Pending standalone native unittests |
| Rendered jump, actual cadence, full 15-minute play counts | UNWITNESSED; Noah must play |

This checkpoint authorizes no claim that an accelerated clock has shipped.

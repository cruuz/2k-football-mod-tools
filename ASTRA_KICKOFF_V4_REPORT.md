# r64 kickoff v4: hold from individual lineup completion

**EXPERIMENTAL/UNWITNESSED.** Based on stack `c450b2d5a344c8d796e16f2eed8a66fb349c8bf8`,
branch `astra/r64-kickoff-v4`, 2026-09-07. No console, display, audio or network
was used. Native instruction replay is bounded and uses synthetic objects.

Noah's supplied witness on disc bd was: "kickoff, they were still jittering
before the kick, but after the kick before it was caught they were perfectly
still, so its the pre kick that needs them to be still." He also said
"kickoff play art is perfect now." Those are the gameplay observations for
the prior stack. This revision has not been played by Noah.

The hold now includes completed players while the global game state is still
lining up. It also stops a separate late head-look interpolator, and preserves
native readiness when the hold replaces ready animation with fixed idle.
The kicker and both deep returners remain free. The brief's reference to
"seventeen" conflicts with its existing nineteen-role requirement: 22 minus
those three exceptions is nineteen. This revision retains ten coverage players
and nine setup blockers, without changing the existing role assignment.

## PROVED: the state boundary v3 did not test

The global phase at `E602B4` is 2 for normal kickoff; the global play state is
at `E602B8`. A separate per-player state lives at `player+20 -> +3E4`.
Calling all three concepts "ready" obscured the gap in the old fixture.

| Native stage | Global play state | Individual state | Hold behavior |
| --- | --- | --- | --- |
| Traveling or turning into lineup | 12 | 12 | Native movement remains free |
| Individual lineup completed, another player/team not ready | 12 | 13 | v3 did not hold; v4 holds eligible roles |
| Both teams ready, CPU delay and initial run-up commands | 13 | Usually 13 in the ready task | Existing v2/v3 body hold applies; v4 also fixes late head pose |
| Kick animation preparation, still before the ball launch | 14 | Native task dependent | Hold continues |
| Ball flight after opcode `08`/`222CA0` | 14 | Native task dependent | Hold continues until first contact |
| First ground or player contact | 14 in the replay | Native task dependent | First-contact latch releases all nineteen immediately |

The native kickoff setup arm of `B8650` writes global state 12 and calls
`1C9390` to set the ball on the tee. The existing reset hook at `1C9399`
therefore clears prior contact flags during that setup; it is not delayed
until launch. The original kickoff suite still passes its reset/relaunch
test. This call-order finding is a static native-code proof, separate from
the v4 frame fixture's explicitly supplied initial state 12.

`1853D0` checks the lineup arrival band and facing, then calls `183D30`.
`183D30 -> 2111D0` writes individual state 13 and stops setup input. Native
`185B50` starts a new lineup with individual state 12. The fixture supplies
players at their marks with arrival band 3; `183D00` still rechecks their
heading. It invokes the completion routine, rather than writing state 13.
The subsequent native `186160` ready task installs callback `183CD0`, targets
the formation point, and requests head tracking when the ball is far away.
Its `183CD0 -> 1ABCF0` wait does not change the global play state.

`18C1F0 -> 1881E0` aggregates team readiness. The kicking team uses `1FF940`
for every active player. The receiving team checks individual state 13, with
native human-selection exceptions. `158C90` changes the global state from 12
to 13 at instruction `158CC1` only after `1580F0` accepts both teams.
`B6F30` accepts state 13 and stores state 14 at `B6FB3`, before ball launch.
This is not necessarily the first approach step: the native `2F0DD0` run-up
task already requests positive movement while the global state is 13.
The full-frame replay executes `B6F30` completely, including its history copies
and clock work, with valid bounded objects.

There is no hold timer. Waiting longer in global 12 or 13 does not activate
the old hold early or release the new one. The earlier frame recorder began
by assigning global state 13 and had no completed lineup/readiness sequence.
That was a concrete coverage gap, despite its valid late-writer proofs.

The actual retail Kickoff Middle kicker chain begins `Start(1,4)` (wait for
ready), `Ball Action(2)` (kickoff), `Place Kick(0,0,457.2,45)`. Opcode 3's native
initializer `2D3E80` dispatches action 2 to `2F1D40`, which installs `2F15C0`
and stamps `B71D00` into task `+A4`. That callback first checks both teams with
`1580F0`, then requires elapsed time strictly greater than float `3FCCCCCD`
(1.6 seconds) for a CPU controller, or `3F8CCCCD` (1.1 seconds) for a human.
It then calls native meter preparation `2EE950`. A focused test executes the
real initializer and callback at the adjacent float values below, equal to
and above each threshold, and proves either unready team still blocks it.

With externally supplied latched meter completion, native `2F1550` installs
`2F0DD0` and that callback requests positive kicker throttle while global state
13 remains unchanged. Start preparation can later reach `B6F30` through
`30C2B0 -> 9FF80 -> 9FE50`. Thus the hold must cover both 13 and 14 during
the broader pre-launch period; neither launch nor the first approach command
is a release event.

The full-frame fixture's 72-frame ready wait is deliberately chosen input,
separate from that focused delay proof. It delivers the later start command
at the native `B6F30` ABI. Neither fixture reproduces the CPU's entire meter
choice or establishes the precise timing on Noah's disc.

## PROVED: writers and the additional readiness dependency

During global 12, the historical v3 executable runs its normal ready planner,
animation clock/key sampling, root/collision integration and pose spring.
The new counterexample uses the exact executable reconstructed from v3's
committed receipt. It retains every observed write, including intermediate
and unchanged writes, and each final watched byte. Changes include transforms,
sampled poses, animation clocks, spring state and both complete skeletons.

The expanded recorder also found an independent writer after body sampling:
`28F4F0 -> 28F310` selects a look target and writes mode 2 at `28F497`.
`1DFAA0 -> 1DF430` interpolates its quaternion using global `B71D0C` time,
writing `descriptor-state+B0..BF` at `1DF68A`. Then `1DF3B0` applies that
rotation to the skeleton. This can change the head and its bone matrix while
the body's transform and both clip clocks are fixed. Resetting it during
motion would be too early because the later target pass renews the request.

| Writer family | Native entry or observed PC | v4 control |
| --- | --- | --- |
| Ready planner/stance and selected human input | `1CD5D0`, `202160`, `1211E0`, `70AF0` | Completed global-12 players enter the existing scoped planner/motion hold |
| Fixed body sampling | `218010`, `31BEB0`, `DF9B0`, `DFA50`, `DFB40` | Native idle `50F4EC`, fixed clocks, completed blends, sampler dt zero |
| Root/collision changes | `2CC570`, `2CC4F0`, `1D8940`, `28D06D`, `28D081` | Existing v2/v3 guards now apply at individual completion |
| Turn/lean spring | `28E360 -> E0110` | Existing residual spring reset now starts at individual completion |
| Head-look target and interpolation | `28F497`, `1DF68A` | New `1DF430` guard selects mode 0 immediately before native head sampling |

The historical counterexample's three post-entry frames retain these actual
changing store PCs. Counts include every changed intermediate write; they
are not counts of visible movements or unique players.

| Watched field | Representative changing store PCs | Changed writes in three frames |
| --- | --- | ---: |
| Cached/current transform and heading | `28E014`, `2CC5CA`, `2CC5FA`, `28D06D`, `28D081` | 437 |
| Primary clock | `31B3D8`, `2D6ABC` | 95 |
| Secondary clock | `31B3E4`, `2D6ACC` | 95 |
| Sampled body pose | `DFC16`, `DFC29`, `DFC3C`, `DFC4F`, `3CA1C8` | 3,534 |
| Turn/lean spring | `E019C`, `E01A0`, `28E727`, `28E785`, `28E795` | 247 |
| Low skeleton, including its root | `31203`, `31206`, `3120A`, `3120E`, `3CA44B` | 34,639 |
| High skeleton, including its root | `31203`, `31206`, `3120A`, `3120E`, `92193` | 79,491 |
| Head rotation | `1DF68A`, `2176C4` | 81 |

Root watches alias their full skeleton ranges, so their stores are attributed
to the full skeleton in the event dictionary; both snapshots are retained.

The body sampler, both skeletal hierarchy passes, collision resolver and all
27 top-level frame phases still execute. Mode 0 uses the fixed clip's head;
the patch keeps the task's target intact, so native head tracking can resume
after contact. Non-player objects and missing player-state pointers are
rejected before the new global-12 player-state read.

Simply extending the old predicate would introduce another bug. Native
`1FF940` recognizes ready descriptors such as `50F1E4`, `50F1BC`, `50F308`
and `50F1D0` with their completion fields. Fixed idle `50F4EC` is not one of
them. If the kicking team's readiness bit has not latched, replacing those
descriptors can leave global state 12 stuck. The new `ready` wrapper returns
true only for an eligible held player. Free and out-of-scope players continue
through the displaced native query. A paired regression with that wrapper
removed proves the deadlock; the same inputs with the wrapper reach state 13.

## Implementation, allocation and unchanged behavior

Two complete, pinned instruction spans are added: `ready` at `1FF940..1FF946`
(`8b41108b5004`) and `head_pose` at `1DF430..1DF436` (`558bec83e4f0`). There are
eighteen hooks. Both backends compile the same assembler with relocated
addresses; no opcode search/rewrite relocation is introduced.

The code uses **1,935 of 1,939 reserved bytes**, with four trailing `CC` bytes.
Runtime storage remains **10 writable bytes**. No request, owner, cave size,
RW budget, PLAY resource or runtime data in `.text` was added. The allocator
union was planned using the existing fixture and all owners compose through
the existing helper. The legacy cave stays at `2890F0`; grown code and state
come from the existing kickoff owner in the union.

Space is recovered through equivalent instruction compaction: function-entry
wrappers save general registers while respecting the caller-clobbered EFLAGS
ABI; mid-function hooks keep flags where needed. Launch/block stack operands
account for the four-byte difference. Repeated signed-z transforms share a
balanced x87 helper. Probability remainders are 0..99 and compare directly
to their byte thresholds. Small first-contact classes use byte operations.
The blocker output writes and kind/hidden checks have equivalent compact
forms. Entry wrappers clear DF before string operations. The native nearest
selector, score/threshold ABI, contact semantics and fitted card are covered
by the prior suites and the new replay.

The fitted `diagram` instruction body is compared against historical v3 with
local branch addresses normalized, while retaining all external targets and
operands. Its mathematics and PLAY alignment/return data are unchanged.
The v2 card-fit and all 36 book receipt checks remain applicable. No new art
adjustment was made following Noah's positive witness.

Both backends remain idempotent and reject mixed/foreign bytes before
mutation. Historical v1/v2/v3 XBE patches deliberately report foreign; rebuild
from the supported base. Exact legacy/grown receipts include every executable
edit, section digest and allocator seal needed for byte-identical replay.
The two existing provider source hashes are repinned without changing trust
rules. Protected files were not edited. `WIRING.md` specifies the two new
live spans and source fingerprints for Claude's protected manifest refresh;
the tests use an exact ownership projection, not a cave exemption.

## Frame evidence and validation

`PreKickMachine` extends `tests/nfl2k5_kickoff_frame.py` without changing the
historical `FrameMachine` defaults. It watches the original transform, blend,
sampled-pose and low/high root fields, plus turn spring, both clocks, head
quaternion/mode, full 25-bone and 62-bone matrices, and individual lineup state.
It supplies diagonal decoded controller axes once for a coverage player and a
setup blocker. Native input gives both throttle 1 in the completed-lineup
window; later native routing can suppress coverage throttle before the hold.
Actual throttle values are retained for every frame, without overwriting
them or any position, pose, spring or clock between frames.

Each fixed case retains initial inputs, native completion, entry frame 0,
72 completed-lineup frames in state 12, 72 ready frames in state 13, 24 approach
frames, 72 flight frames and the first-contact release frame. Native state
transition writes are recorded separately with their PCs. The canonical idle
entry is visible in the receipt; no unreported settling frames are discarded.
The fixture delays the free players' completion handoff to keep global state
12 observable, and supplies the pending-event script operands explicitly.

The public evidence files are `docs/nfl2k5_kickoff_v4_receipts.json` and
`docs/nfl2k5_kickoff_v4_frames.json`. They contain exact executable receipts,
lossless dictionaries of writes/sequences/states, per-frame changes, native
state/descriptor values, controller observations and leaf calls. The normal
standalone tests independently execute the sequence and compare those receipts.
Historical v3 evidence files remain unchanged. The v3 suite replays its old
executables exactly, rejects them as foreign to the current compiler, and
checks current output against every historical final frame.

The historical counterexample changes all nineteen players' transforms,
sampled poses, low/high roots, turn springs, both clocks, head rotations and
complete skeletons on each of its three observed state-12 frames. Every one
of those watched fields stays byte-identical to entry frame 0 in all four v4
cases. The additional native handoff/launch packets are also identical for
the held players. The entry pose change and contact release remain visible.

| Case | Stable observed frames | Held-player writes retained | Free players moving | First-contact release |
| --- | ---: | ---: | --- | --- |
| Historical v3, positive direction | 0 of 3 | 233,095 | All 3, every frame | Counterexample ends before contact |
| Legacy, negative direction | 240 of 240 | 13,989,323 | All 3, every frame | Ground, all 19 on the same frame |
| Legacy, positive direction | 240 of 240 | 13,989,323 | All 3, every frame | Touch, all 19 on the same frame |
| Grown, negative direction | 240 of 240 | 13,989,323 | All 3, every frame | Ground, all 19 on the same frame |
| Grown, positive direction | 240 of 240 | 13,989,323 | All 3, every frame | Touch, all 19 on the same frame |

Each v4 case has 247 packets, including every observed frame and all explicit
handoffs. The counterexample has six. The 27 frame phases each execute 241
times before the release frame, and once more on release. The recorded state
stores are exactly `(E9210, 158CC1, 12, 13)` and `(0, B6FB3, 13, 14)`.

Reproduction uses the pinned retail XBE, then `kick_rules`, the current legacy
patch, the complete 38-request gate union with scale-out, and the relocated
patch. Allocation planning also passed against the committed 41-request
budget fixture:

```text
python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json
```

The plan reports a 12,300,288-byte XBE and no build. No request was added.
Executable and evidence SHA-256 identities are:

| Artifact | SHA-256 |
| --- | --- |
| Pinned retail XBE | `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9` |
| Legacy output | `9a1028223a584a14343d3150b1c1b2fadc129683bd466c2991ef5ba6c99bdd5f` |
| Grown output | `59005d5751c93729022c60d0adf493b3ccada3c0d1f06fc04cb4bd8c5587cacc` |
| v4 receipts JSON, 1,993,783 bytes | `b47fd08bff56641670fcdd9124ab09aac5479abc3b1f40fd045041b7f97df104` |
| v4 frames JSON, 51,849,198 bytes | `79f5c2630907c8a24793ff25b4506d28a1541621140b734f42599a3f8e4cd9a3` |

All commands below run from this worktree. Times are unittest's reported
seconds; peak RSS is `/usr/bin/time -v` in KiB. The XBE gates inherit all
checks in forward/reverse order for both allocator layouts and assert
byte-identical outputs between installation orders.

| Command | Result | Seconds | Peak RSS (KiB) |
| --- | --- | ---: | ---: |
| `python3 tests/mod_editor/test_nfl2k5_dynamic_kickoff.py` | 23 passed | 41.894 | 674,268 |
| `python3 tests/mod_editor/test_nfl2k5_kickoff_fixes.py` | 11 passed | 11.755 | 522,960 |
| `python3 tests/mod_editor/test_nfl2k5_kickoff_v2.py` | 12 passed | 28.464 | 742,432 |
| `python3 tests/mod_editor/test_nfl2k5_kickoff_v3.py` | 7 passed | 141.234 | 342,344 |
| `python3 -u tests/mod_editor/test_nfl2k5_kickoff_v4.py` | 8 passed | 912.454 | 514,528 |
| `python3 tests/nfl2k5_kickoff_alignment_test.py` | 7 passed | 0.462 | 35,840 |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 79 passed | 301.156 | 314,420 |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 95 passed | 387.336 | 503,708 |
| `python3 tests/mod_editor/test_provider_integrity.py` | 7 passed | 7.623 | 183,756 |
| `python3 -m unittest tests.mod_editor.test_providers` | 33 passed | 4.194 | 54,320 |

Evidence generation, `python3 -u tests/mod_editor/test_nfl2k5_kickoff_v4.py
--record`, passed all five cases in 901.82 wall seconds, peak RSS 497,792 KiB.
The standalone v4 run checks exact executable replay and public evidence
hashes in addition to independently reproducing the native traces. The
focused CPU/human delay test also passed separately at both threshold
boundaries and placements. All **282 final tests passed, with no skips**.
The v4 replay's wall time was 912.79 seconds. There are no changed runtime
algorithms after these recorded inputs/output hashes.

The unrelated existing provider test file does not insert the repository
root into `sys.path`, so its direct file invocation failed at import with
`ModuleNotFoundError: mod_editor`. The module invocation shown above ran all
33 tests successfully; the provider test file was not changed. Two obsolete
development runs were stopped after finding a stale sixteen-hook assertion
and a tuple/list comparison in historical evidence; the corrected final
gate and v3 suite results are the passing rows above.

The largest final test process peaked at **742,432 KiB RSS** (v2), below
the 2 GB limit. Evidence generation and every test read only the bounded
retail XBE or stream the required archive spans. No disc image or pack was
built, copied, loaded whole, or left for cleanup. At the final pre-commit
measurement, `/` had **107,545,034,752 bytes free (107.545 GB decimal)** and
`.scratch/` contained **96,882 bytes**, with no image/pack copies. Both disk
and scratch limits are satisfied. All thirteen delivery paths were checked
explicitly; protected files and historical receipts/PLAY resources are
unchanged, and `git diff --cached --check` passed.

## HYPOTHESIS and known gaps

The global-12 trigger gap and late head interpolation are proved native
mechanisms that can produce pre-kick movement. Which caused Noah's exact
jitter is **HYPOTHESIS**: his runtime states and retail animation assets were
not captured. His post-kick stillness witness is respected; this report does
not infer that every synthetic head-look request occurred on his disc.

Clips, low/high skeleton hierarchies, arrival counters, roster attributes and
collision spheres are synthetic. The largest collision radius deliberately
overlaps players. Hardware acquisition, presentation/audio notification and
selected attribute leaves remain explicit fixture boundaries; the native
planner, input decoder, full frame dispatcher, pose and collision code run.
The CPU's complete decision loop, retail clip selection diversity, GUI/GPU
interpolation and LOD switching are not gameplay proofs. The entry-frame
change from the outgoing pose to canonical idle can still need visual review.
The hold begins at native individual completion; no claim is made to freeze
players while they are traveling into formation.

## Noah's witness list

1. Rebuild the full stack with dynamic kickoff and its existing alignment and
   returns. Watch all ten coverage players and nine setup blockers from each
   player's completed lineup through the CPU kicker's delay and first approach
   step. Check feet, shoulder/body sway, heading and heads, close and distant.
2. In both directions, hold directional input on a coverage player and a setup
   blocker before the kick. They must remain still after completing lineup.
   Confirm the kicker and both deep returners stay free and every kickoff can
   advance from lineup to ready to approach, without a readiness deadlock.
3. Watch entry into idle and the first ground-contact and caught/touched-ball
   release frames. Check for a single visible snap, renewed jitter, late start,
   stuck blockers, head tracking and crowded collision/contact animations.
4. Repeat normal and squib kicks, landing-zone and near-the-1 catches, actual
   end-zone touchbacks, short and out-of-bounds kicks. Recheck nearest approaching
   blocks and both deep players' return branches. Check onside, safety kicks
   and ordinary scrimmage behavior.
5. Confirm the already-good Kickoff card in 4:3/widescreen, flipped and with
   different kicker depths, and the world art. Repeat after another kickoff,
   possession/direction changes and reset/new game, in legacy and grown builds.

## Delivery

Only the explicit implementation, tests, receipts, provider pins, this report
and `WIRING.md` are delivery paths. `ASTRA_BRIEF.md`, `.scratch/`, the retail
XBE, private corpus and archive resources are excluded. No push is performed.
The normal Git index is writable. Delivery uses an explicit-path `git add`
and `git commit --` for these thirteen paths; no bundle fallback is needed:

```text
WIRING.md
ASTRA_KICKOFF_V4_REPORT.md
mod_editor/core/nfl2k5_dynamic_kickoff.py
mod_editor/core/nfl2k5_dynamic_kickoff_relocated.py
mod_editor/core/providers.py
tests/nfl2k5_kickoff_frame.py
tests/nfl2k5_allocator_stack.py
tests/mod_editor/test_nfl2k5_kickoff_v3.py
tests/mod_editor/test_nfl2k5_kickoff_v4.py
tests/mod_editor/test_xbe_patch_memory_writes.py
tests/mod_editor/test_xbe_patch_cave_references.py
docs/nfl2k5_kickoff_v4_receipts.json
docs/nfl2k5_kickoff_v4_frames.json
```

The delivered commit ID is reported in the final response. Claude's protected
manifest refresh is the integration handoff recorded in `WIRING.md`.

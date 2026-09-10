# Beta 65 job B: live MyCareer Supersim

Branch: `astra/b65-supersim`, based on `c9d01941`. EXPERIMENTAL / UNWITNESSED.

**Shipped stage: bounded Stage 1, native presentation-skip requests at 1x.**
This is not the requested accelerated, headless CPU drive yet. It retains the
live game, its existing CPU ownership, every ordinary update and rendered
frame. It requests the native post-play, injury/timeout and period-presentation
skip paths when MyPlayer is absent, and supplies the ordinary skip button only
to the two automatic-replay screen consumers. Native readiness guards and
cleanup remain in charge. There is no abstract-simulator handoff.

The Apartment has an eighth row, **Supersim: Skip presentation / Off**. It uses
the existing seven-row scrolling list; scroll below Upgrades. Skip presentation
is the default inside an enabled in-game MyCareer, as this brief requested.
The studio's existing MyCareer option remains experimental and opt-in. B while
an eligible off-field presentation is being considered changes the session
choice to Off and suppresses that request. It retains the actual B input.
The row toggles the choice back on. This is a session choice, reset on new or
cold-loaded careers; the career save format is unchanged.

Stage 2 and its Stage 3 action/ticker/Fast forward row are **not installed**.
`nfl2k5_supersim.RUNTIME_READY` remains false, `REQUESTS` remains empty, and
`LIVE_STAGE=1`, `LIVE_UPDATES_PER_FRAME=1` describe the separate live-owner work.
Do not advertise a drive that “flies,” a headless engine, automatic prompt
coverage, or a guaranteed full-play-clock return for this build.

## Proof standard and inputs

Read `ASTRA_CONTEXT.md` first, the two requested hub reports, current runtime,
assembly, `fastforward_candidate.c`, and existing budgets. Historical mode 4
had 8192 RX; current M3 already owns 16384 RX plus two 4096 RW blocks. The old
capacity refusal is not a current safety argument. The incomplete candidate
now fits; its scheduling semantics still are not proved.

PROVED below means pinned retail instructions or bounded native execution,
with the stated fixture inputs. It never means witnessed in a running game.
Retail USA XBE SHA-256:
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
Private ROST/PLAY/FONT/LAYT/MRKS/SKEL evidence uses the existing pinned readers.
New tests use precise SkipTest when required private inputs or Unicorn/Capstone
are absent. No retail bytes, disc, emulator, display, audio device or network
were used as an output artifact.

## Frame boundary: what the research establishes

The normal frame is **0x74790..0x7489E**. `0x64CD0` is the running game's mixed
update callback, reached through descriptor `0x4E7EC0`, event table
`0x4E7E88`, event-6 command `0x4E7DF8` (callback pointer at +4), callback
`0x650A0`. This real descriptor path is also executed up to `0x64CD0` with
no substituted leaves. `0x13610` and `0x1124E0` are replay/highlight
screen callbacks which also call that update, not interchangeable frame loops.

| Phase | Evidence and status | Consequence |
| --- | --- | --- |
| Delta acquisition, 747A3 -> 74680 | PROVED pinned edge; native time acquisition is outside the inner dispatcher. | Repeating a caller that reads time is not a fixed-step scheduler. |
| Input, 747AF -> 74730 | PROVED bounded prefix executes native 48B50 on match RNG E5FCA0 before hardware input. | Once per ordinary frame; omitting it changes RNG cadence. Hardware polling is not proved headless. |
| Manager update, 747CC -> 6E6A0 | PROVED native stores delta at manager+104, dispatches event 6 through 6E4E0. Synthetic descriptor/no-op callbacks prove dispatch, not all screen bodies. | A separate update dispatch exists; its screen callback can still enter presentation. |
| Running update, 64CD0 | PROVED bounded orchestration: pause A83A14 zeros scaled delta to 11A7C0, while 8A840 and 124050 receive raw delta. Child bodies are explicit ABI leaves in this particular test. | Pause does not make all work simulation-only. 7A6E0/replay scale is distinct from the game-speed setting. |
| Inner dispatcher, 11A7C0 | PROVED all 27 phase bodies execute in the kickoff fixture; the table below names every substituted leaf actually reached. | Includes controller and audio boundaries. No blanket “pure simulation” label is justified. |
| Outer camera phase, 64E29 -> A5620 | PROVED complete kickoff outer trial reaches all 27 inner phases, then faults at 5F7BA through A5620 -> 5F760 -> 5F7A0 because the fixture has no camera scene. | Concrete coverage boundary, not a retail crash. An outer-update loop is not proved. |
| Modal update, 11EF60 -> 14E470 -> 14E070 | PROVED pinned calls in modal loop include 74680, 74730, 14D3F0, 6E6E0, 27CA0 and controller polling. The strings identify tips/lesson continuation. | The update can enter a nested timer/render/input loop. Automatic handling for all such prompts is unproved. |
| Render dispatch, 7483E -> 6E6E0 | PROVED native dispatch of events 9, 7, 8, separate from event 6; camera capture/restore are explicit leaves. Pinned game path 64F80 -> 64E80 -> 11A8F0 is presentation work. | A possible presentation gate, not an established safe omission. |
| Submission/present region, 7488D -> 27CA0 | PROVED pinned command-buffer writes and 25DE0 timing call. No GPU execution. | Not simulation; actual display/vblank completion and safe gate remain unproved. |
| Audio | PROVED inner 94AB0 reaches four declared audio-gain boundaries every tested update. A unique final device-submit boundary and queue capacity are unproved. | Cannot safely claim that skipping render mutes/gates audio. 74866 -> 12B520 was not established as audio submission. |

The committed `tools/nfl2k5_supersim_live_probe.py` emits span hashes and per-phase
counts in `tools/mycareer_mode/supersim_live_receipt.json`. The write counts include
stack and unchanged writes, not only changed football state. Tags follow the
latest entered phase, so dispatcher stack stores between phases retain that
tag; these are not exact function-body write totals. A phase with no
substituted leaf on this branch is not proved free of hardware/time calls on
every other play branch. The fixture retains controlled RNG and attribute/input
leaves and synthetic looping clips/skeletons. It does not prove a drive.

## Prompt and CPU ownership coverage

Mode 5 keeps the two native team controller counts CPU-owned. While absent,
native offensive selection `A11F0 -> 20B670` and defensive `20B820` select
real PLAY data. Existing tests cover choice, live inner frames, turnovers,
timeout debit, injury substitution/recovery, halftime and OT entry. They use
declared presentation-completion events. Sixty complete inner career frames
advance a supplied clock from 300 to about 299 seconds, while the supplied
looping lineup clips remain in state 12. This is not unattended snap/drive
acceptance and cannot rule out a wait later in the drive.

| Presentation/prompt | Native path and bounded result | Installed handling / remaining limit |
| --- | --- | --- |
| Post-play camera 20 | A2120 -> A23CE; installed hook on a real CPU-choice fixture runs native cleanup and returns camera/game state to 11 without changing the game-clock object. | Request when absent. Native readiness/transition tests remain live. |
| Automatic replay, 13610 | Poll at 13856; native 0x110 test and readiness predicates accept the supplied 0x100 button. Separate full 12FD0 proof changes replay state AFA078 3 -> 4 and refuses other states. | Only this poll is wrapped, only camera 20 and absent. Whole loaded replay completion remains unwitnessed. |
| Highlight, 1124E0 | Poll at 112DD9; bounded native consumer sets A97334=1 with the supplied skip button and connected-controller input. | Native transition remains in charge; whole screen lifecycle unproved. |
| Injury / timeout, camera 23 / 24 | A2120 -> A2219; active replay, elapsed >1 and native readiness required. At elapsed .5 request is refused; at 2, native cleanup queues camera 28 and negative transition time through 89780. | No direct completion flag write. Native injury substitution/timeout debit tests separately cover return after a declared event. |
| Period break, camera 25 | A2120 -> A2273; B8DB0 refuses early time, then clears E602CC when ready. | Request only; end-of-period completion B72C38 is still a declared input in the full CPU boundary fixture. |
| Halftime presentation, camera 27 | A2120 -> A2322; B8DB0/CEA30 readiness, native CECD0 cleanup. Tests clear B72C18/B665FC only when ready; supplied clock is unchanged. | A real halftime pool/menu and its complete exit still need a witness. Existing period proof supplies B72C30 and event 3. |
| Challenge, camera 26 | Separate native A22A0 case identified by pinned dispatch. | Excluded: choosing a challenge answer is not proved. No arbitrary A/B injection. |
| Initial/OT coin toss | CPU period proof calls native 9F690 with declared side/direction. | No automatic answer proved or installed. |
| Tips / lesson continuation | 11EF60 opens the native modal with a continue prompt; 14E070 owns a nested input/timer/render loop. | No auto-answer installed. Reaching this modal in an unattended career drive is unproved, not ruled out. |
| Pause / disconnected controller / other dialogs | Supersim admission rejects A83A14 pause; arbitrary modal callbacks are untouched. | No general unattended-dismissal proof. Controller reconnect and user decisions remain manual. |
| “CPU wait message” | Existing owned Apartment footer is text formatting, currently “Off field: CPU plays”; it is not a modal call. | This rules out that owned footer as a wait. No exhaustive native prompt inventory was established. |

`A2120` is the ordinary native skip-request routine called from native input
`125BC0` and actor/presentation code. Its skip lock at BA99D8 and replay guards
are retained. New code calls it only for camera states 20, 23, 24, 25 and 27.
The tests execute early and ready cases without replacing the skip body.
Synthetic active replay state is explicitly not a loaded movie/scene witness.
No new code writes football clocks, game-speed, phase, outcome, injury,
timeout debit or native completion flags directly.

## Next appearance and control boundary

The intended future contract is: after at least one absent interval, stop
before input/update can start MyPlayer's next snap, with current native
personnel and alignment settled and the native play clock at its full initial
value. Do not return merely because possession changed.

| Position codes | Intended appearance | Proved current predicate |
| --- | --- | --- |
| 0, 3, 7, 8, 9 | Offensive-unit snaps | `mode_human` uses offense mask 0x389 for scrimmage phase 4, together with identity/presence. |
| 4, 5, 6, 10, 11, 15, 16 | Defensive-unit snaps | Defense mask 0x18C70, together with identity/presence. |
| 1 (K), 2 (P) | Kicks/punts when the exact player is actually in native personnel | Native body membership, not possession. Special-team play calls remain CPU-owned. |
| 12, 13, 14 | Native offensive-line personnel | Identity binding exists for all 17 positions; these codes are outside the two human play-call masks. No new route/blocking controls are claimed. |

`mode_unit_present()` rebinds identity, then returns `S(24)==3 ? S(2568) : 0`.
It checks the exact linked on-field body, not simply the unit suggested by
position. Special-team exceptions and substitutions therefore require actual
personnel. The bounded test for all 17 positions on both sides supplies the
same body in states 11 through 16 and observes presence in all of them. Presence
alone is demonstrably not a pre-snap or full-clock predicate.

**The exact settled frame has not been proved.** Neither state 11 nor 12 alone
proves rendered alignment, play-clock initialization and no pending snap.
Full CPU clips, camera scene and huddle-to-snap execution are missing from the
available bounded fixture. Stage 1 simply stops issuing requests whenever the
normal identity predicate becomes present. It does not run extra updates, take
control away, advance a snap on behalf of MyPlayer, or promise a new handoff.

## Speed result and decision

The new fixture executes eight identical fixed inner updates grouped 1/2/4/8.
Every group produces the same watched player-state SHA-256 and eight visits
to each of the 27 phases. All four runs present **zero frames**, hold the
declared kickoff clock at 600 and substitute final audio-gain calls. Host
elapsed times in the receipt include Unicorn/Python instrumentation overhead;
they are not an Xbox speed measurement or proof of updates per rendered frame.

The first established obstacles are the incomplete outer camera scene, native
modal loops, per-update audio work and mismatched input/RNG cadence. No measured
animation failure threshold or audio-queue capacity exists. Grouping eight
inner updates without rendering cannot justify shipping even 2x.

Native speed setting `E5FFA8` is separately executed in a bounded prefix:
0 scales delta by .9, 1 by 1, and 2/4/8 all by 1.1. It is not an update-count
multiplier. The native outer input RNG prefix consumes different match PRNG
states with 8, 4, 2 or 1 input polls. A future scheduler must specify that
cadence; identical outcomes are not promised. **Shipped speed: 1x.**

Even at 1x, ending a presentation earlier may reduce the number of input/RNG
frames before the next play. The per-frame RNG draw is proved; resulting
drive/score differences are unmeasured. Off/Skip is a pacing/control comparison,
not a promise of identical football outcomes.

## Ownership and writer

Three pattern-checked call sites: 64D27 (retail no-op 89F40), 13856 and 112DD9
(native 70A10 polls). Complete skip routines/tables and both replay callers
are hash-guarded, with already-applied hook normalization. `status()` reparses
the generated owner, hooks and RW seals; apply replay is byte-identical.

Preference is the unused word `state+2696` in existing RW. Apartment row data
stays in existing M3 RW, immutable labels/code in RX. The native row builder
14FF80 refreshes cached labels after a toggle; this routine was already pinned.
The native selected row survives, and normal drawing re-establishes the
scrolling viewport. Old rows keep indices 0..6.

Final `supersim_budget.json`: 10954 machine-code bytes, 15316 content bytes,
17-byte seal, **1051 RX bytes spare**, 16384 RX / 8192 RW reserved. Relative to
the starting M3 owner, no request, other owner address, allocator region or
allocated file-size change. M3 menu data uses 1424 of its 1900-byte workspace.
The candidate
receipt `supersim_capacity.json` is capacity-only, never-installed/executed;
the old historical budgets remain intact. `measure_mode4.py` now understands
the already-expanded current owner instead of insisting the old candidate
must overflow. The incremental manifest tool now reports current RX/RW sizes.
`measure_m3.py` retains its historical 8192-byte before-layout when comparing
peer addresses; that before-layout is not this job's starting allocation.

`packaging/repin.py --apply` updated the two existing provider pins. Protected
registry/GUI/release files and release cave manifest are untouched. See the
**Beta 65 job B** section at the end of `WIRING.md` for integration.

## Noah's exact witness script

Use Claude's fresh build from the retail base with the existing in-game
MyCareer option enabled (no prepared-save setup). First check the eighth
Apartment row is visible when scrolled to, toggles Off/Skip presentation, and
remains selected. Test Skip presentation, then Off for comparison.

1. **QB:** create/sign/start a QB career, play into a defensive series. Put the
   controller down while absent. Record each replay/post-play cut and any
   stuck screen. Expected Stage 1 difference is shorter eligible presentation;
   live plays still run at 1x. At the next offensive appearance, check the
   alignment, play clock and first controller input. A drive that “flies” is
   the future Stage 2 acceptance criterion, not this build's claimed result.
2. **CB:** repeat with a CB while his offense drives. Check CPU choices on both
   sides, presentation skips and the first defensive snap. Record if a native
   prompt waits for input. No whole-drive unattended proof exists yet.
3. **K/P and special teams:** test kickoff, punt, field goal/PAT, blocked kick
   and a return. Check that an actual K/P appearance is retained and native
   kick control works; verify ordinary QB/CB appearances around the change of
   personnel. Do not infer membership from possession alone.
4. **Halftime/quarter/OT:** reach a quarter break and halftime while absent;
   verify timeout counts, receiver, score, quarter, clock and next play-call
   screen. Record any coin-toss or challenge decision needing input. In a tied
   game, check OT separately; auto-answering its toss is not shipped.
5. **Two-minute drill:** reach the last two minutes with MyPlayer absent.
   Check hurry-up, timeout debit, injury substitution and following snap. Then
   reach that situation with MyPlayer present and verify normal control. Do
   not accept a skipped snap as an intentional acceleration.
6. **Cancel/pause:** press B during an eligible off-field presentation. Later
   replays should return to ordinary behavior; the Apartment row should show
   Off. Pause and resume, checking that paused menus are not auto-dismissed.
7. **Save/load during the game:** inspect the game's offered native save route
   while paused. If a mid-game resume save is offered, use a separate slot,
   reload, compare score/clock/possession/personnel and control. Report if no
   such route exists; this job does not add or prove mid-game serialization.
   Also save/load through the ordinary career route: identity/XP/fixture should
   persist, the session choice resets to Skip presentation. No live state is
   exported/imported by Supersim.

All in-game observations above remain UNWITNESSED. A wait is evidence to record,
not permission to force a phase or complete the abstract simulator.

## Follow-up needed for Stage 2

Load the full native camera/clip/huddle scene into a bounded outer-frame fixture;
trace an uninterrupted CPU series and every modal, including challenge/toss and
controller waits. Identify device audio submission independently of gain/state
updates. Prove the first settled pre-snap personnel/clock boundary for each
position group, including substitutions and kicks, with stop-before-snap
assertions. Only then compare complete 2/4/8 fixed updates between actual
render/present phases, including audio depth and RNG policy. A future live
ticker may read E53800's native log and reuse the visual-simulator formatter;
the abstract simulator's EC390/EC570 driver cannot itself establish live resume.

## Validation

Final verification results and per-phase evidence are recorded below. Early
pre-refresh runs are superseded and are not counted as final-source gate results.

## Per-phase bounded inner evidence

Each row is PROVED only for eight updates of the declared kickoff fixture.
No declared boundary call on that branch is an observation; general phase
purity remains HYPOTHESIS. Counts include stack writes.

| Phase | Native entries | Writes observed | Declared substituted calls |
| --- | ---: | ---: | --- |
| `0xaf2c0` | 8 | 1096 | None reached on tested branch |
| `0x28dfe0` | 8 | 1072 | None reached on tested branch |
| `0x217c90` | 8 | 184 | None reached on tested branch |
| `0xa28c0` | 8 | 16 | None reached on tested branch |
| `0x75bd0` | 8 | 3032 | `0x17b010` × 352 |
| `0x5d830` | 8 | 410 | None reached on tested branch |
| `0x190d00` | 8 | 8 | None reached on tested branch |
| `0x18c1f0` | 8 | 136 | None reached on tested branch |
| `0x156a80` | 8 | 2408 | `0x63810` × 16, `0x65550` × 8 |
| `0x89ba0` | 8 | 31 | None reached on tested branch |
| `0xe9210` | 8 | 232 | None reached on tested branch |
| `0x214fc0` | 8 | 14828 | None reached on tested branch |
| `0xf7c10` | 8 | 216 | None reached on tested branch |
| `0x1e08d0` | 8 | 20795 | None reached on tested branch |
| `0x2180d0` | 8 | 433196 | None reached on tested branch |
| `0x28ecf0` | 8 | 2198536 | None reached on tested branch |
| `0x28cc30` | 8 | 8640 | None reached on tested branch |
| `0x1ccfa0` | 8 | 64 | None reached on tested branch |
| `0x28f4f0` | 8 | 2824 | None reached on tested branch |
| `0x1dfaa0` | 8 | 79872 | None reached on tested branch |
| `0x1d30f0` | 8 | 3408 | `0x17b010` × 176 |
| `0x17c2e0` | 8 | 24 | None reached on tested branch |
| `0xa7930` | 8 | 56 | None reached on tested branch |
| `0x1d1b80` | 8 | 32 | None reached on tested branch |
| `0x94ab0` | 8 | 496 | `0x1c3e10` × 8, `0x1c3e70` × 8, `0x1c3ed0` × 8, `0x1c3f30` × 8 |
| `0x5da70` | 8 | 56 | None reached on tested branch |
| `0x125bc0` | 8 | 42 | None reached on tested branch |

The attribute leaf is `17B010`; the input/accessor leaves are `63810` /
`65550`; the four `1C3E10..1C3F30` leaves are the existing fixture's audio-gain
boundary. Native pose/clip/planner phases themselves are not substituted.

| Updates per group | Groups | Total updates | Host seconds (instrumented) | Presented frames |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 8 | 8 | 8.191007 | 0 |
| 2 | 4 | 8 | 6.848325 | 0 |
| 4 | 2 | 8 | 7.122047 | 0 |
| 8 | 1 | 8 | 6.927631 | 0 |

All four watched-state hashes: `e4298527c86644aa369529a5e9add28b6b7833aeaa3666bac89669c37c831c3c`.
This equality covers the selected player fields, not every live global or a
completed game outcome. The inner fixture substitutes random draws; the
separate outer-prefix test runs the native match PRNG.

## Final verification results

**649 tests passed in 19 standalone suites, zero skips** with the private
retail evidence available. The composition suite includes **299 pairs in
598 installation orders**, plus 11 guard/refusal tests. No emulator was run.
Machine-readable commands, timings, source hashes and log hashes are in
`tools/mycareer_mode/supersim_validation.json`.

All commands below ran with `QT_QPA_PLATFORM=offscreen`,
`PYTHONHASHSEED=0`, and
`NFL2K5_CAVE_MANIFEST=$PWD/.scratch/supersim-final-manifest.json`. The
manifest is the conservative incremental development proof described in
`WIRING.md`, **not a regenerated release manifest**. Every unchanged
parent pin is checked; Claude must regenerate the protected release
manifest after integration.

| Exact standalone command | Tests | Seconds | Output |
| --- | ---: | ---: | --- |
| `python3 tests/mod_editor/test_nfl2k5_supersim_live.py` | 17 | 105.43 | OK |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 111 | 1278.339 | OK |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 123 | 1460.838 | OK |
| `python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | 29 | 284.471 | OK |
| `python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py` | 310 | 1898.83 | OK |
| `python3 tests/mod_editor/test_nfl2k5_my_career_mode5.py` | 4 | 281.198 | OK |
| `python3 tests/mod_editor/test_nfl2k5_my_career_control.py` | 2 | 14.49 | OK |
| `python3 tests/mod_editor/test_nfl2k5_my_career_cpu_choice.py` | 1 | 22.42 | OK |
| `python3 tests/mod_editor/test_nfl2k5_my_career_cpu_frame.py` | 1 | 57.542 | OK |
| `python3 tests/mod_editor/test_nfl2k5_my_career_cpu_period.py` | 2 | 42.677 | OK |
| `python3 tests/mod_editor/test_nfl2k5_my_career_cpu_timeout.py` | 1 | 19.3 | OK |
| `python3 tests/mod_editor/test_nfl2k5_my_career_cpu_injury.py` | 1 | 26.527 | OK |
| `python3 tests/mod_editor/test_nfl2k5_my_career_cpu_turnover.py` | 3 | 70.815 | OK |
| `python3 tests/mod_editor/test_nfl2k5_my_career_m3_budget.py` | 5 | 5.364 | OK |
| `python3 tests/mod_editor/test_nfl2k5_my_career_m3_menus.py` | 4 | 41.369 | OK |
| `python3 tests/mod_editor/test_nfl2k5_my_career_mode4.py` | 8 | 463.436 | OK |
| `python3 tests/mod_editor/test_nfl2k5_my_career_inline.py` | 8 | 12.633 | OK |
| `python3 tests/mod_editor/test_nfl2k5_my_career_frontend.py` | 7 | 57.183 | OK |
| `python3 tests/mod_editor/test_nfl2k5_supersim.py` | 12 | 8.772 | OK |

Peak observed per-process RSS: **908,280 KiB**, below 2 GiB.

Other checks:

```text
python3 tools/mycareer_mode/build_runtime.py --check
MyCareer mode runtime verified

python3 tools/mycareer_mode/measure_m3.py --output .scratch/final-budget-check.json
Receipt equals committed supersim_budget.json; 1,051 RX bytes spare.

python3 tools/mycareer_mode/measure_mode4.py --output tools/mycareer_mode/supersim_capacity.json
Exit 0; incomplete uninstalled candidate fits the current reservation.

python3 tools/nfl2k5_supersim_live_probe.py --output tools/mycareer_mode/supersim_live_receipt.json
Recorded bounded 1/2/4/8 grouping evidence; shipped speed remains 1x.

python3 packaging/repin.py --apply
Updated the existing mode.py and mode_code.py pins.
python3 packaging/repin.py
would apply 0 pin update(s)

NFL2K5_RETAIL_EXTRACTION=.scratch/no-retail-input python3 tests/mod_editor/test_nfl2k5_supersim_live.py
Ran 0 tests; OK (skipped=2), both classes identify absent private USA XBE.

git diff --check
Exit 0.
```

The read-only cave-oracle `space-proof` CLI also exited 0: no retail mapping
or manifest overlap and zero raw encodings into legacy grown pages. It retained
857 raw encoding candidates in the newer regions; those are an inventory, not
857 proved reachable references or a claim of unrestricted cave freedom. The
allocator reservations remain unchanged. The registry amendment from WIRING
was executed twice against a scratch copy: exactly one capability changed,
idempotently, retaining opt-in defaults and `runtime.status = not-tested`.

Early gate runs were interrupted after the option-label cache fix and replaced
by the final-source runs above. No production source changed during the final
suites. No protected file, retail image, external worktree or release output was
written. Branch commits are local only; no push.

# r64 kickoff v5: receiving stance and return assignments

2026-09-07. Branch `astra/r64-kickoff-v5`, base
`ae99298` and its already integrated kickoff v4. **EXPERIMENTAL / UNWITNESSED.**
Noah has not played this revision. No game, console emulator, GUI display,
audio, network, disc build, archive copy or push was used. Unicorn executed
bounded native instruction fixtures with the input boundaries below.

V5 preserves a completed player's selected stance without restarting its
animation lifecycle. Released return blockers refresh their nearest lane
target before native pursuit, and an empty target leaves the drive task
waiting with zero throttle. The implementation occupies **1,937 / 1,939 RX
bytes and the existing 10 RW bytes**, with nineteen pinned hooks. Both legacy
and relocated versions use the same compiler. No allocation was enlarged.

Noah's disc-bf witness established receiving-team leg jitter before the kick
and unsatisfactory blocking in v4. His earlier disc-bd witness established
stillness after the kick, and his positive play-card witness is retained.
Those observations do not identify a particular player state or animation.
The mechanisms below are native CPU proofs; attributing Noah's exact visible
symptom to them remains **HYPOTHESIS**.

## Receiving-side mechanism and the corrected fixture

**PROVED:** the old fixture left the locomotion callback at a synthetic RET.
Retail `1DEFA0` installs `2388D0` at descriptor-state `+40` when `E5FF80` is
nonzero. Its adjacent `+3C` points to private table storage, with spare storage
at `E3C014`. V5's `NativeSetupMachine`, extending `PreKickMachine`, supplies
that native callback and storage instead of the RET. It also corrects the
animation object's `+30` input: this is a cosine cache, not another pose
pointer. `2CC470` initializes the sine/cosine pair; `+34` retains the pose.

The concrete loop is:

1. V4's held-motion wrapper calls `1CD550(player, 50F4EC)` on every update.
   `50F4EC` is a locomotion descriptor with a lifecycle, not an inert pose.
2. Its `2132A0` initializer invokes `2388D0 -> 238660`. For individual player
   states 12 or 13, `2388D0` replaces the zero-speed table entry with `513DD0`.
   This is a type-3 descriptor transition back to the ready path.
3. `2FCAC0` dispatches through `1CD550` to the ready initializer `200D00`,
   then the stance path `1FE3C0 -> 1FFFE0`. The replay reaches ready descriptor
   `50F1BC` and embedded clip `6E2BE0` for the receiving setup blockers.
4. `1FFFE0` compares the player's team with receiving team `E60284` at
   `200271..20027E`. Only that side enters its bone-12 height search. The
   call at `2002E6` executes `218150 -> 2177A0`, including native bone
   decompression and adjustment. The observer at `2002EB` retains the actual
   sample time and returned XYZW bytes. Up to six samples precede the clip
   installation at `200349 -> 2D6B70`.

This is a receiving-only foot-sampling path reached even with the body clocks
subsequently reset to zero. Re-entering the ready lifecycle also renews clip
rates and channel installation. It does not establish a separate, unpatched
IK writer or a failure to arm the receiving hold. The native human-selection
exception remains in readiness; the selected setup blocker is still held.

Both teams use actual formation initialization `186240 -> 185B50`. The
initializer selects completion callback `185070` for slot 0 on each team and
`1853D0` for their other slots. The fixture supplies players at the authored
dynamic marks and valid arrival counters; the native callbacks recheck facing
and write individual state 13. Native Start initialization `1AE490` installs
their pending ready tasks. Kicker Start uses `(1,4)` and the supplied other
wait operands use `(1,3)`. These are explicit pending-event inputs, not a
claim that every full retail play chain or CPU meter decision is replayed.

The new foot observer exposed another missing fixture input during review:
`90570` normally loads mesh adjustment axes and bone indices at `B65B80`.
Zero-filled records caused `91890 -> 901E0 -> 1C2530` to normalize a zero
axis and produce NaNs. The final fixture supplies two nonzero unit axes and
valid distinct bone indices alongside its synthetic skeleton. Native
adjustment math still runs. Every recorded foot sample must now be finite;
the earlier NaN probe is discarded as evidence. The native ready clip is
retained, rather than replacing that routine or its result with a stub.

The recorder also follows both active channel pointers, in addition to the
historical physical-bank write watches. Native installation swaps those
pointers; observing only their original addresses could miss alternating
clip/time/rate changes. Every active clip, clock and rate is retained in the
final frame state. Native pose RNG construction uses seed `20260907`.

**V5 change:** the held-motion path clears movement input, sets the coherent
heading, completes blends and freezes the existing channels, without calling
`1CD550`. It retains the v3 root, collision, spring and v4 head-pose guards.
The ready-query wrapper still accepts completed held players while preserving
native readiness for the kicker and both deep returners. No timer arms or
releases the hold, and there is no position restore fighting an integrator.

**Selected rows of the recorded frame trace.** Counts are v4 / v5; the full 25 frames are in each receipt. Native call counts agree in both directions and both v5 placements. Active-channel change counts are among the nineteen held players, relative to the prior frame (frame 0 has no predecessor).

| Frame | Global state | Calls to `1CD550` | Bone-12 samples | Changed active primary channels |
| --- | --- | --- | --- | --- |
| 0 | 12 | 63 / 6 | 54 / 0 | 0 / 0 |
| 1 | 12 | 57 / 0 | 54 / 0 | 19 / 0 |
| 2 | 12 | 57 / 0 | 54 / 0 | 19 / 0 |
| 7 | 12 | 57 / 0 | 54 / 0 | 19 / 0 |
| 8 | 13 | 57 / 0 | 54 / 0 | 19 / 0 |
| 13 | 13 | 57 / 0 | 54 / 0 | 19 / 0 |
| 14 | 14 | 57 / 0 | 54 / 0 | 19 / 0 |
| 19 | 14 | 57 / 0 | 54 / 0 | 19 / 0 |
| 20 | 14 | 57 / 0 | 54 / 0 | 19 / 0 |
| 23 | 14 | 57 / 0 | 54 / 0 | 19 / 0 |
| 24 | 14 | 0 / 57 | 0 / 54 | 19 / 19 |

Before launch (frames 0..19), each of the nine receiving setup players makes 120 native foot queries in v4, for **1,080 total; v5 makes zero**. V4 makes 1,296 through the entire hold window; v5 makes zero until 54 on the contact frame. The six samples below are player 13, receiving slot 2, frame 2, phase `2180D0`, observed at `2002EB`. Their result bytes repeat on every pre-kick v4 frame; v5 has no corresponding query. XYZW are little-endian float32.

| Sample time (float32 bits) | Returned XYZW bytes |
| --- | --- |
| `00000000` | `aaf3813f9e8925431f74054200000000` |
| `3dcccccd` | `ce8d54409978204315d60e4200000000` |
| `3e4ccccd` | `c874c43f743f1c438715154200000000` |
| `3e99999a` | `d7ac27c0260c1843eb85184200000000` |
| `3ecccccd` | `0f89b4c0ea7913431fd51b4200000000` |
| `3f000000` | `0ad7ccc021c60e4313e91e4200000000` |

Player 13 retains clip `6E2BE0` and time zero during the hold. The active primary and secondary rate bits expose the repeated installation even though a zero-time final skeleton alone does not prove visible motion:

| Frame | V4 active rate bits | V5 active rate bits |
| --- | --- | --- |
| 0 | `3f769f2b` | `3f5c3d70` |
| 1 | `3f866748` | `3f5c3d70` |
| 2 | `3f5f2625` | `3f5c3d70` |
| 8 | `3f90639a` | `3f5c3d70` |
| 14 | `3f67d8e7` | `3f5c3d70` |
| 20 | `3f799cf1` | `3f5c3d70` |
| 23 | `3f85bc9e` | `3f5c3d70` |

Exact complete setup-trace SHA-256 values:

| Case | Trace SHA-256 |
| --- | --- |
| v4_-1 | `7023a8613d30a5c8024905459cc895f3542305e50df70415f0aa7ba1bc50ff64` |
| v4_+1 | `2bf0580827856a4a935d3a5dc87a21f0a2c3b2f1d8343cd91fdae7324441a74e` |
| legacy_-1 | `c8c71ad357ac24a76bbbb46b5569418e04e842a3e30b4a2717fcf8e2fe402d74` |
| legacy_+1 | `35ad1461ba3f3c0faaafab463fb6f96e2dcaf688a697e7dd133aea54905e7785` |
| grown_-1 | `bbe29835285285c766cc6f8c9347016d69c19732b520b5da5afb2d19b405c0ff` |
| grown_+1 | `e873829414be2a0b7c8cf066ae7552273185066ea3c1b7e85aed4b97f6b941e6` |

Frames 0 and 1 are both retained: the first establishes the held sample and
the second propagates it into the previous-transform cache. Frames 2 through
23 compare against that state, including both complete skeletons, head,
active channels and all historical watched fields. Only the sign of IEEE
zero in skeleton matrices is normalized for physical equality; the receipt
retains the original bits. This is not a discarded warm-up interval.

Free players complete at frame 8, causing native `E9210 -> 158C90` to write
global state 13 at `158CC1`. The supplied approach command executes `B6F30`
and writes 14 at `B6FB3` on frame 14. Launch is supplied at the existing
`222CA0` hook ABI on frame 20. Ground contact in the negative-direction case,
or player contact in the positive-direction case, releases all nineteen on
frame 24. The kicker and both deep returners change watched state on every
one of the 24 compared frame intervals.

The old executable's foot search also continues into this fixture's flight
window because these pending tasks retain individual state 13 until contact.
That is not a reconstruction of Noah's exact post-launch task events. V4's
separate CPU/human readiness-delay and approach proofs still run. The new
counterexample proves repeated receiving foot queries and channel restarts;
it does not claim that a final rendered skeleton visibly jitters with these
synthetic mesh inputs. The exact visual cause remains a witness question.

## Blocking model, failure and correction

The acceptance policy comes from the brief's desired dynamic-kickoff play:
setup blockers should take the nearest arriving coverage player in their
lane, either deep non-carrier should block coverage, and nobody should pass
an unblocked local coverage player while pursuing the distant kicker. This
is an AI quality policy, not a claim that the NFL mandates a target-scoring
formula or guarantees a successful block.

**PROVED before:** v2's mode-2 selector only applies after first contact in
live state 14. Native `2400B0 -> 23F450` can install a drive task before that
window, with a retail-selected kicker cached at task `+40`. The ordinary
`23CD60` refresh is separate from drive callback `23CE70`. The full replay
shows stale kicker pursuit at `23BE60`, including the second deep player.
It also exposes a second route: when no eligible target remains,
`23CE70` reaches `23CFCB -> 214B90`, replacing drive with the `23B040`
fallback. That fallback can pursue the kicker after the nearest selector
has correctly returned no coverage target.

**V5 correction:** the new six-byte pinned entry hook at `23CE70..23CE76`
refreshes through native `23CD60` before pursuit, including the first release
update. A null result sets throttle to zero and returns 0 while retaining
the drive task. A subsequent arriving player can resume it. Native paired
contacts bypass the refresh and continue their existing engagement.

The selector keeps the previous scope, finite-value rejection, 22-node walk
bound, slot-1..10 coverage filter, carrier/kicker exclusions, confidence 1.0,
and no deeper fallback. A candidate must be in front in receiving direction
and satisfy `(candidate - blocker) dot candidate_velocity <= 0`; a stationary
candidate is eligible on the first release frame. The score is now
`4*dx*dx + dz*dz`, so lateral distance costs twice as much as longitudinal
distance before squaring. This lane preference is a documented design choice.
Equal scores keep native list order. Existing task storage holds the target;
there is no new reservation or exclusive assignment table. SSE1 is retained.

The new complete-return fixture executes `11A7C0` and all 27 phases on every
frame. Native task scheduling, selection, pursuit `23BE60`, turning `2FC9F0`,
root integration, collision broadphase, eligibility and mutual pair creation
run. The nine setup blockers and the alternate deep man start actual drive
tasks. Neither their targets, positions nor contact pairs are supplied by
Python after initialization.

External input boundaries are explicit: coverage follows its lane, the
carrier runs straight, and the kicker remains stationary. A three-key run
asset supplies 15 cm per frame at full speed, with a separate stationary
band and 180-degree/second turning input. Collision radius is 45 cm. The
supplied catch occurs at the carrier's initial root; the ball position query
then aliases that root so it follows native movement. Hand/socket attachment,
another ball flight, scoring and officials are outside the fixture. Each
return ends at the carrier crossing the far goal line, with a 900-frame cap.
Each frame has a two-second execution timeout and must return at the exact
ABI with all phases in order. Either deep carrier, both directions and both
code placements are independently replayed.

Paired clip asset installation `30E000` and the stats notification `A1EC0`
remain declared leaves. Thus a native mutual pair proves engagement was
entered, not a completed retail block animation, block win or disengagement.
Roster/service leaves and synthetic mesh inputs remain as documented in the
earlier frame fixture. This is a continuous return decision/physics replay,
not a gameplay capture or an unrestricted simulation of an entire game.

All twelve cases reach the far goal line. KR1 denotes receiving slot 0 carrying (player 11); KR2 denotes slot 1 carrying (player 12). Direction is the kicking direction. These are fixture player IDs, not jersey numbers. Coverage IDs are 1..10 and kicker ID is 0.

| Case | Frames | Pursuits | Kicker pursuits | Lane mismatches | Roles paired with coverage | Local passes | Passes chasing kicker |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v4_-1_kr1 | 604 | 234 | 178 | 207 | 4 | 6 | 5 |
| v4_-1_kr2 | 580 | 217 | 158 | 187 | 4 | 6 | 5 |
| v4_+1_kr1 | 604 | 214 | 158 | 187 | 4 | 6 | 5 |
| v4_+1_kr2 | 580 | 217 | 158 | 187 | 4 | 6 | 5 |
| legacy_-1_kr1 | 604 | 67 | 0 | 0 | 5 | 4 | 0 |
| legacy_-1_kr2 | 580 | 70 | 0 | 0 | 5 | 4 | 0 |
| legacy_+1_kr1 | 604 | 67 | 0 | 0 | 5 | 4 | 0 |
| legacy_+1_kr2 | 580 | 70 | 0 | 0 | 5 | 4 | 0 |
| grown_-1_kr1 | 604 | 67 | 0 | 0 | 5 | 4 | 0 |
| grown_-1_kr2 | 580 | 70 | 0 | 0 | 5 | 4 | 0 |
| grown_+1_kr1 | 604 | 67 | 0 | 0 | 5 | 4 | 0 |
| grown_+1_kr2 | 580 | 70 | 0 | 0 | 5 | 4 | 0 |

**Exact per-role comparison, v4 → legacy v5.** Each grown-v5 case has the same per-role integer counts, target sets and contact peers as its legacy case; both full traces are retained separately. A lane mismatch compares the actual native pursuit with the eligible minimum score at that instant. A local pass means crossing an unpaired opponent within three lateral yards while the blocker advances. It can remain a miss even when no kicker is pursued. Pair peers include the kicker when v4 incorrectly engages him; `none` means no native pair. Closest distances are in cm, rounded to four decimals in the receipt.

**Direction -1, KR1 carries:**

| Player / role | Pursuits | Kicker pursuits | Lane mismatches | Coverage targets | Pair peers | Wait ticks | Local passes | Kicker passes | Closest coverage (cm) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 12 / alternate KR | 26 → 26 | 1 → 0 | 1 → 0 | 8 → 8 | 8 → 8 | 0 → 0 | 0 → 0 | 0 → 0 | 17.4299 → 17.4299 |
| 13 / setup 2 | 3 → 3 | 2 → 0 | 2 → 0 | 5 → 5 | 5 → 5 | 0 → 0 | 0 → 0 | 0 → 0 | 16.8545 → 9.8154 |
| 14 / setup 3 | 23 → 4 | 13 → 0 | 22 → 0 | 2 → 2 | none → none | 0 → 147 | 1 → 1 | 0 → 0 | 96.3183 → 96.3183 |
| 15 / setup 4 | 24 → 4 | 14 → 0 | 24 → 0 | 10 → 10 | none → 10 | 0 → 0 | 1 → 0 | 1 → 0 | 123.7643 → 59.9215 |
| 16 / setup 5 | 51 → 4 | 51 → 0 | 51 → 0 | none → 9 | 0 → none | 0 → 147 | 0 → 0 | 0 → 0 | 362.1994 → 287.0027 |
| 17 / setup 6 | 35 → 4 | 35 → 0 | 35 → 0 | none → 3 | none → none | 0 → 147 | 2 → 1 | 2 → 0 | 145.6615 → 91.8263 |
| 18 / setup 7 | 27 → 8 | 17 → 0 | 27 → 0 | 10 → 2 | none → none | 0 → 143 | 1 → 1 | 1 → 0 | 129.3786 → 93.3675 |
| 19 / setup 8 | 37 → 7 | 37 → 0 | 37 → 0 | none → 1 | none → 1 | 0 → 0 | 1 → 0 | 1 → 0 | 116.6449 → 45.1565 |
| 20 / setup 9 | 4 → 4 | 4 → 0 | 4 → 0 | none → 1 | 1 → none | 0 → 147 | 0 → 1 | 0 → 0 | 70.3962 → 103.935 |
| 21 / setup 10 | 4 → 3 | 4 → 0 | 4 → 0 | none → 4 | 4 → 4 | 0 → 0 | 0 → 0 | 0 → 0 | 64.2387 → 15.5783 |

**Direction -1, KR2 carries:**

| Player / role | Pursuits | Kicker pursuits | Lane mismatches | Coverage targets | Pair peers | Wait ticks | Local passes | Kicker passes | Closest coverage (cm) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 11 / alternate KR | 29 → 29 | 1 → 0 | 1 → 0 | 9 → 9 | 9 → 9 | 0 → 0 | 0 → 0 | 0 → 0 | 22.8693 → 22.8693 |
| 13 / setup 2 | 3 → 3 | 2 → 0 | 2 → 0 | 5 → 5 | 5 → 5 | 0 → 0 | 0 → 0 | 0 → 0 | 18.3161 → 12.5702 |
| 14 / setup 3 | 23 → 4 | 13 → 0 | 22 → 0 | 2 → 2 | none → none | 0 → 141 | 1 → 1 | 0 → 0 | 96.3183 → 96.3183 |
| 15 / setup 4 | 14 → 4 | 4 → 0 | 14 → 0 | 10 → 10 | none → 10 | 0 → 0 | 1 → 0 | 1 → 0 | 123.8502 → 59.9215 |
| 16 / setup 5 | 51 → 4 | 51 → 0 | 51 → 0 | none → 9 | 0 → none | 0 → 141 | 0 → 0 | 0 → 0 | 362.4176 → 287.0027 |
| 17 / setup 6 | 35 → 4 | 35 → 0 | 35 → 0 | none → 3 | none → none | 0 → 141 | 2 → 1 | 2 → 0 | 145.5538 → 91.8263 |
| 18 / setup 7 | 17 → 8 | 7 → 0 | 17 → 0 | 10 → 2 | none → none | 0 → 137 | 1 → 1 | 1 → 0 | 128.877 → 94.5444 |
| 19 / setup 8 | 37 → 7 | 37 → 0 | 37 → 0 | none → 1 | none → 1 | 0 → 0 | 1 → 0 | 1 → 0 | 116.8812 → 56.7631 |
| 20 / setup 9 | 4 → 4 | 4 → 0 | 4 → 0 | none → 1 | 1 → none | 0 → 141 | 0 → 1 | 0 → 0 | 70.439 → 90.5031 |
| 21 / setup 10 | 4 → 3 | 4 → 0 | 4 → 0 | none → 4 | 4 → 4 | 0 → 0 | 0 → 0 | 0 → 0 | 64.2387 → 13.6597 |

**Direction +1, KR1 carries:**

| Player / role | Pursuits | Kicker pursuits | Lane mismatches | Coverage targets | Pair peers | Wait ticks | Local passes | Kicker passes | Closest coverage (cm) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 12 / alternate KR | 26 → 26 | 1 → 0 | 1 → 0 | 8 → 8 | 8 → 8 | 0 → 0 | 0 → 0 | 0 → 0 | 17.9682 → 17.9682 |
| 13 / setup 2 | 3 → 3 | 2 → 0 | 2 → 0 | 5 → 5 | 5 → 5 | 0 → 0 | 0 → 0 | 0 → 0 | 10.9339 → 10.3133 |
| 14 / setup 3 | 23 → 4 | 13 → 0 | 22 → 0 | 2 → 2 | none → none | 0 → 147 | 1 → 1 | 0 → 0 | 96.3183 → 96.3183 |
| 15 / setup 4 | 14 → 4 | 4 → 0 | 14 → 0 | 10 → 10 | none → 10 | 0 → 0 | 1 → 0 | 1 → 0 | 123.7929 → 59.9215 |
| 16 / setup 5 | 51 → 4 | 51 → 0 | 51 → 0 | none → 9 | 0 → none | 0 → 147 | 0 → 0 | 0 → 0 | 362.2539 → 287.0027 |
| 17 / setup 6 | 35 → 4 | 35 → 0 | 35 → 0 | none → 3 | none → none | 0 → 147 | 2 → 1 | 2 → 0 | 145.6615 → 91.8263 |
| 18 / setup 7 | 17 → 8 | 7 → 0 | 17 → 0 | 10 → 2 | none → none | 0 → 143 | 1 → 1 | 1 → 0 | 129.2789 → 93.3674 |
| 19 / setup 8 | 37 → 7 | 37 → 0 | 37 → 0 | none → 1 | none → 1 | 0 → 0 | 1 → 0 | 1 → 0 | 116.6449 → 45.0927 |
| 20 / setup 9 | 4 → 4 | 4 → 0 | 4 → 0 | none → 1 | 1 → none | 0 → 147 | 0 → 1 | 0 → 0 | 70.3963 → 103.9351 |
| 21 / setup 10 | 4 → 3 | 4 → 0 | 4 → 0 | none → 4 | 4 → 4 | 0 → 0 | 0 → 0 | 0 → 0 | 64.2386 → 15.5178 |

**Direction +1, KR2 carries:**

| Player / role | Pursuits | Kicker pursuits | Lane mismatches | Coverage targets | Pair peers | Wait ticks | Local passes | Kicker passes | Closest coverage (cm) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 11 / alternate KR | 29 → 29 | 1 → 0 | 1 → 0 | 9 → 9 | 9 → 9 | 0 → 0 | 0 → 0 | 0 → 0 | 23.0232 → 23.0232 |
| 13 / setup 2 | 3 → 3 | 2 → 0 | 2 → 0 | 5 → 5 | 5 → 5 | 0 → 0 | 0 → 0 | 0 → 0 | 13.7764 → 13.1362 |
| 14 / setup 3 | 23 → 4 | 13 → 0 | 22 → 0 | 2 → 2 | none → none | 0 → 141 | 1 → 1 | 0 → 0 | 96.3183 → 96.3183 |
| 15 / setup 4 | 14 → 4 | 4 → 0 | 14 → 0 | 10 → 10 | none → 10 | 0 → 0 | 1 → 0 | 1 → 0 | 123.8789 → 59.9215 |
| 16 / setup 5 | 51 → 4 | 51 → 0 | 51 → 0 | none → 9 | 0 → none | 0 → 141 | 0 → 0 | 0 → 0 | 362.4406 → 287.0027 |
| 17 / setup 6 | 35 → 4 | 35 → 0 | 35 → 0 | none → 3 | none → none | 0 → 141 | 2 → 1 | 2 → 0 | 145.5538 → 91.8263 |
| 18 / setup 7 | 17 → 8 | 7 → 0 | 17 → 0 | 10 → 2 | none → none | 0 → 137 | 1 → 1 | 1 → 0 | 128.8341 → 94.5443 |
| 19 / setup 8 | 37 → 7 | 37 → 0 | 37 → 0 | none → 1 | none → 1 | 0 → 0 | 1 → 0 | 1 → 0 | 116.8812 → 56.68 |
| 20 / setup 9 | 4 → 4 | 4 → 0 | 4 → 0 | none → 1 | 1 → none | 0 → 141 | 0 → 1 | 0 → 0 | 70.4391 → 90.5032 |
| 21 / setup 10 | 4 → 3 | 4 → 0 | 4 → 0 | none → 4 | 4 → 4 | 0 → 0 | 0 → 0 | 0 → 0 | 64.2386 → 13.5287 |

The largest legacy/grown difference in recorded closest distance is 0.0000 cm. Exact positions, callback addresses, decisions, pursuits and waits are compared with their own placement receipt. Every one of the 27 frame phases executes 604 times in each KR1 case and 580 times in each KR2 case. The catch-frame counts and the later no-target waits are both included.

The target and kicker-chase defects are fixed in every recorded return.
Contact quality remains bounded: five of ten blocking roles form a coverage
pair, and four local passes without a pair remain. The same opponent can be
selected by multiple blockers. Receiving slot 9 loses its incidental v4
coverage pair and records one local miss; the improvement from four to five
coverage-paired roles is not an improvement for every individual blocker.
No change to native collision eligibility,
winning attributes or player speed is claimed. These remaining misses are
reported explicitly instead of treating target selection as proof that all
blocking now looks good.

## Allocation, compatibility and preserved proofs

The legacy RX reservation is `2890F0..289883`, with two trailing CC bytes.
RW remains `A69969..A69970` and `A69971..A69974`, excluding `A69970`. The
relocated owner retains `(code,1939,16)` and `(data,10,4)`. In the recorded
41-request gate union its code is `14BA2C0` and data is `14BB000`. Planning
the current 44-request budget fixture succeeds with XBE size 12,300,288 bytes.
No owner, budget row, page or runtime variable in RX was added.

Removing repeated initialization, sharing the receiving/scope predicates and
packing adjacent launch configuration stores funds the new hook. Settings
labels now identify their immediate bytes, and both settings readers use
those locations. The first packed store touches an owned kick-spot byte;
the complete saved kick-spot float immediately replaces it before any call
or branch can consume it. Both provider source fingerprints are refreshed.

`status` and `apply` remain idempotent and refuse mixed or foreign bytes
before mutation. All nineteen hooks are individually restored or corrupted
in negative tests. Every historical v1, v2, v3 and v4 executable is rebuilt
from its published receipts in both legacy and grown placement, verified
against its output hash, and refused by both current backends. There is no
partial upgrade of an old disc; rebuild from the supported retail base.

The existing v2 touchback/classifier, landing zone, all 36 fixed-span book
receipts and fitted-card tests pass. The stale-clip test retains the exact
historical v2 initializer proof and checks v5's new selected-channel hold.
The v3 silenced-writer tests pass unchanged. V4 still checks completed-lineup
holding, readiness, CPU/human delay boundaries, approach, head pose and first
contact. Its tests replay exact historical v4 bytes separately and compare
the current behavior fields; current compiler addresses and descriptor
lifecycle are not falsely presented as v4 executable identity.

No v2/v3/v4 receipts or frames were re-recorded or edited. V4's `--record`
path now refuses to overwrite its historical receipt with a later compiler,
following the existing v3 pattern. V5 evidence is generated only through
its own `python3 -u tests/mod_editor/test_nfl2k5_kickoff_v5.py --record` path.
Exact replay covers hook/cave edits, section digests and allocator seals.

Both XBE gates compose all existing owners in both installation orders and
both allocator configurations, including the current relocated kickoff.
Their tests check the new live hook. The existing union-manifest projection
adds that span only after verifying its retail bytes, exact installed jump
and ownership; unknown or foreign overlaps still refuse. The manifest
builder already includes this owner in its request union and owner lists.

Protected files are untouched. The section `# r64 kickoff v5, 2026-09-07`
in `WIRING.md` lists all nineteen pinned spans and the complete dispatcher,
BuildPlan, status, preset, caption, allowlist and runtime-import handoff.
Existing captions remain truthful and unchanged. Claude must regenerate
the protected reservation JSON and source fingerprints after integration.
The passing gate projection does not substitute for that product manifest.

## Exact receipts and validation

| Artifact | SHA-256 |
| --- | --- |
| retail_xbe_sha256 | `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9` |
| legacy_input_sha256 | `b5bcf6bd46246bd77ceff9a144f6ea5cb7fda67057115a5a29d9eb193ae0a49b` |
| legacy_output_sha256 | `37abeb21c6735cdb156294d72ee69c76dbd7e7cddafed92db84d7eb99ae119ca` |
| union_allocated_sha256 | `add60458841d2855684e07423483b03a9d5b0c51879437f305029ef520585618` |
| relocated_output_sha256 | `4912700f2359fd04ad2d4614cfcdde8c3c775ee81a9111a8e12598b5541c07dd` |

| Committed file | SHA-256 |
| --- | --- |
| mod_editor/core/nfl2k5_dynamic_kickoff.py | `07d5a7e20b763d4cf454c1ab5bb9d87a697663fceca141c15cdb7dae59e77a7a` |
| mod_editor/core/nfl2k5_dynamic_kickoff_relocated.py | `211063695451178000aa7088245ddef8c31973f08fad490341a378bf6e8a6b4f` |
| docs/nfl2k5_kickoff_v5_receipts.json | `e1eed06e2807e5bf7c49d1112ce88aaebb7ff79d0097913ef2af946dbc76f701` |
| docs/nfl2k5_kickoff_v3_receipts.json | `bbb5157f3a2274164cde1af8923a2e35164c5981eb0f589dca2981864fda3f3c` |
| docs/nfl2k5_kickoff_v4_receipts.json | `956c5060cd58393153a0db872e6294be68a9ad14e3e2af69e14d0f325b880971` |

The new receipt is 95,506,980 bytes (91.08 MiB), includes six setup cases and twelve continuous returns, and contains no complete executable, archive or disc. It stores exact bounded edit bytes, write events, deduplicated state snapshots, phase traces and return measurements. The historical receipt hashes above match the base commit unchanged.

**296 tests passed, zero failures and zero skips** in the final runs below. Times are unittest-reported seconds; RSS is the exact maximum KiB reported by `/usr/bin/time -v`. Logs are retained under `.scratch/`, outside the commit.

| Command | Passed | Seconds | Peak RSS (KiB) |
| --- | --- | --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_dynamic_kickoff.py` | 23 | 44.832 | 652,872 |
| `python3 tests/mod_editor/test_nfl2k5_kickoff_fixes.py` | 11 | 12.235 | 522,512 |
| `python3 tests/mod_editor/test_nfl2k5_kickoff_v2.py` | 12 | 29.659 | 698,356 |
| `python3 tests/mod_editor/test_nfl2k5_kickoff_v3.py` | 7 | 144.978 | 339,588 |
| `python3 tests/mod_editor/test_nfl2k5_kickoff_v4.py` | 8 | 907.904 | 515,348 |
| `python3 tests/nfl2k5_kickoff_alignment_test.py` | 7 | 0.482 | 36,096 |
| `python3 tests/mod_editor/test_provider_integrity.py` | 7 | 8.242 | 183,248 |
| `python3 -m tests.mod_editor.test_providers` | 33 | 4.260 | 53,876 |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 83 | 343.822 | 316,160 |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 99 | 436.971 | 506,928 |
| `python3 tests/mod_editor/test_nfl2k5_kickoff_v5.py` | 6 | 472.063 | 1,133,652 |

The final v5 recorder command `python3 -u tests/mod_editor/test_nfl2k5_kickoff_v5.py --record` completed with exit 0 in 7:22.15 wall time and 730,700 KiB peak RSS. The allocator plan command `python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json` reported PASS for all 44 requests and 12,300,288 output bytes. `git diff --check` and the explicit staged-path audit passed.

The final v5 replay checks its complete recorded setup and return states,
finite foot samples, exact executable replay, per-role targets, contact
peers, waits and all 27 phase counts. Focused native tests also cover lane
preference, retained waiting tasks, resumption on new arrival, callee-saved
registers and stack balance, and the native prologue outside the hook scope.
Absence of the private retail XBE or Unicorn/Capstone produces a precise
skip; the public receipt checks still run.

The earlier continuation logs are preserved in `.scratch/`. Superseded
probes include the missing ball/mesh inputs and the incomplete return
terminal setup; none is counted as final evidence. The first complete v5
suite exposed a v1 receipt-adapter error: its short hooks have exact `before`
bytes while its cave uses `before_sha256`. The adapter now verifies either
published representation, retaining both the allocated and output hashes.
The focused identity/refusal test then passed in 13.410 seconds, and the
complete v5 suite was rerun. The final test results
above are newly completed runs in this continuation. No failing test was
waived. The provider suite uses its existing module invocation because that
unmodified file does not bootstrap the repository path when run directly.

## Noah's witness list and remaining boundaries

1. Rebuild from retail with the existing dynamic kickoff, alignment and return
   options. In Practice and a game, watch the nine receiving setup blockers
   from individual lineup completion through ready, approach and flight.
   Check feet and knees close up and at both model LODs; look for a repeated
   shuffle, one-time pose snap or renewed head/root movement.
2. Confirm every kickoff advances to the approach. Repeat CPU and human
   kicking/receiving, hold directional input on a selected setup or coverage
   player, and leave the other team waiting. The nineteen held roles must
   stay still; the kicker and both deep returners must remain free.
3. Release on first ground contact and first player touch. Check immediate
   movement of all nineteen, facing, acceleration, collision and head
   tracking, including crowded bodies. Launch itself must not release them.
4. Return with each deep man, left/middle/right, both directions. Watch each
   setup blocker and the other deep man engage arriving coverage instead of
   chasing the kicker. Check missed local contacts, two blockers sharing a
   target, disengagement and a new arrival reaching a waiting blocker.
5. Recheck near-the-1 catches, true 2024/2025 touchbacks, landing-zone bounces,
   short/out-of-bounds kicks, normal/squib versus onside/safety, the next
   kickoff after possession changes, and ordinary scrimmage.
6. Keep the already accepted fitted Kickoff card under 4:3/widescreen, flip
   and different kicker depths. Compare legacy and relocated full-stack
   builds and record the exact XBE/receipt hash with any failure.

The exact leg-jitter cause on disc bf, visible stance quality, retail paired
animations, missed contacts under real ratings and traffic, controller/meter
timing, GPU/LOD behavior and game-loader acceptance remain UNWITNESSED.

## Delivery

After staging the executable changes, tests and receipt, root available space is **105,898,569,728 bytes** (105.899 GB); `.scratch/` contains **6,685,960 bytes**. The largest measured process, including the superseded full run, used **1,352,056 KiB** RSS, below the 2 GB process limit. No disc or archive was loaded whole, built or retained. The final witness check found no `.scratch/witness/NOTES.md`.

All protected paths and earlier receipt/frame files match the base commit. Both kickoff provider pins match their final source SHA-256 values. The only remaining integration action is the protected manifest/source-fingerprint regeneration specified in `WIRING.md`; Noah's gameplay checks remain the runtime witness.

Normal explicit-path staging succeeded, but the final commit was rejected:
Git could not create the linked worktree's `index.lock` on the read-only
filesystem. Delivery therefore uses the brief's authorized bundle fallback.
Isolated Git metadata under `.scratch/r64-kickoff-v5.git` uses the existing
object database read-only, starts from
`ae9929825c9cfa005313c22f15564eacd577c6f0`, and commits all fifteen paths
explicitly. The original branch is not advanced by this fallback.

`.scratch/r64-kickoff-v5.bundle` contains the resulting
`refs/heads/astra/r64-kickoff-v5` tip and requires the base commit above.
`git bundle verify`, an independent unbundle into temporary metadata, and
the imported commit's parent/path checks verify delivery. The worktree files
remain in place for review. The commit contains the two kickoff modules,
their provider pins, changed kickoff/allocator/gate tests, the new v5 test
and receipt, this report and `WIRING.md`. `ASTRA_BRIEF.md`, `.scratch/`,
protected files and private game/corpus data are excluded. No push is performed.

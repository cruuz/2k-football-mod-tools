# r63 kickoff v3: late collision and pose writers

**EXPERIMENTAL / UNWITNESSED.** Built in `astra/r63-kickoff-v3`, based on
`477443e`. Noah's only gameplay evidence for this investigation is his report
from disc `2026-09-07az`, containing v2 `5ac2359`: "kickoff play art looks
better but still jittery players before the kick." V3 has not been played.

The expanded native replay reproduced three omitted write paths. V3 stops
fresh collision displacement at its producer and removes residual collision
and turn-spring state before the native late passes. All nineteen held roles
then retain exactly the same watched bytes through sixty complete frames in
both directions and both code placements. The kicker and both deep returners
change position on every one of those sixty frames. Ground/player contact
releases all nineteen held roles on the first subsequent complete frame.

## PROVED: the writers outside v2's slice

The pinned USA XBE SHA-256 is
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
Research used its native instructions and the read-only Ghidra function corpus.
No console emulator, GUI, audio device, network or disc build was used.

1. **Residual separation:** `28CC30 -> 28C6C0 -> 28C5B0` decays the collision
   object's displacement at `+B0..BF` while its `+34` lifetime is positive.
   Later in `28CC30`, `28D06D` and `28D081` add that displacement directly to
   transform `+30/+38`. These writes bypass both `2CC4F0` and `2CC570`.
   A one-time seed of `(1, 0, -1, 0)` and lifetime `0.2` reproduces the problem
   without an overlapping pair. V2 coverage slot 1 starts at approximately
   `(1210, 914.4)` cm; after entry and two further frames its X/Z values are
   `(1210.373413, 914.026550)`, `(1210.488647, 913.911316)`, and
   `(1210.517456, 913.882507)`. The next frame's `28E014` snapshot propagates
   the changed coordinates. Pose construction precedes collision, so its root
   also lags that late position change by a frame.
2. **Fresh separation:** in approach/play state 14, native pair resolution
   reaches `1DA470 -> 1D8940`. `1D898D` and `1D8997` add X/Z directly and
   retain the impulse. A guard only at the later `28CE90` integration loop
   failed: these earlier direct additions had already moved the players.
   The committed additional counterexample uses the same dynamic alignment,
   enlarged synthetic collision spheres, and **no residual seed**. Its first
   three frames contain 53, 64 and 64 changed direct position additions across
   held players at these two PCs. This is why the final hook is at the producer.
3. **Residual pose:** `28ECF0 -> 28E360 -> E0110` integrates a separate integer
   turn spring at transform `+70..80`, using the full frame delta even when
   both animation clocks are zero. Its current value/velocity are integers at
   `+74/+78`; `+7C/+80` are float coefficients. Packed lean values are at
   `+6C/+6E`. A one-time current/velocity seed `(1800, -200)` with coefficients
   `(100, 20)` changes sampled quaternions and both skeleton roots at fixed
   world coordinates. The isolated spring and isolated impulse tests separate
   these mechanisms. In the combined v2 60-frame receipt, all nineteen sampled
   poses and roots change through frame 22; the seeded residual eventually
   settles. The fresh-collision counterexample establishes repeated additions
   independently of that finite residual.

These are native CPU counterexamples for documented synthetic inputs. They
identify real executable writers; they do not identify which one Noah's
particular game state activated.

## Implementation and scope

The sixteenth hook replaces the complete six-byte prologue at
`1D8940..1D8946`, pinned to `8b48248b5120`. EAX is the player, the function has
one stack argument, and the held path returns with `ret 4`. The wrapper saves
and restores registers and flags. Unheld players replay both original
instructions and continue at `1D8946`.

During held motion, after native idle descriptor/heading selection, v3 clears
transform `+68..7B` and preserves the spring coefficients. It also sets the
existing collision impulse lifetime `+34` to zero; `28C5B0` then clears the
old vector through its native expired-impulse branch. No player transform is
restored after an integrator writes it. The new producer guard prevents fresh
impulses from replacing that cleared state. Clearing a native impulse's
lifetime does **not** release the hold: only the existing first-contact latch
does so, and no elapsed-time condition was added to the held predicate.

The predicate is unchanged: normal type-8 kickoff, phase 2, ready/approach/live
states 13 or 14, no first-contact class, participating player, coverage slots
1..10 or receiving setup slots 2..10. Kicker slot 0 and receiving slots 0/1
remain free. Selected human coverage is held too. Setup state 12, safety,
onside, scrimmage, inactive players and contact release retain native behavior.
Nearest-block assignments, play-card compression and kickoff settings retain
their v2 behavior; the existing regression suites cover them.

Code uses **1,937 of 1,939 bytes**, with two CC padding bytes. The original
legacy allocation remains `2890F0`; the tested grown union places code at
`14BA2C0` and its existing ten writable bytes at `14BB000`. `REQUESTS`, owner,
RX/RW permissions and every allocation size are unchanged. Small equivalent
instruction encodings and existing branch relaxation fund the new guard;
classification boundaries, probabilities, spotting and both directions are
retested. There are no new runtime bytes in `.text` or new unreserved caves.

Historical v1/v2 executable bytes and partially restored v3 hooks refuse
before mutation. Both v3 placements are recognized and idempotent, with
section digests and allocator seals verified by exact receipt replay. Old v2
receipts remain unchanged and are replayed as historical evidence.

## Complete-frame fixture and observations

`tests/nfl2k5_kickoff_frame.py` executes `11A7C0` itself, with all 27 phase calls
in their exact order: clocks, transform snapshot, animation reset, game state,
attributes, scene bookkeeping, readiness, controller input, state transitions,
task scheduler, planning, motion, pose, collision, ball, look targets, head,
fatigue/accessories and final presentation bookkeeping. Every frame must return
at its native ABI within two million instructions. No phase is replaced by a
stub. Native decoder/blender `DF9B0/DFA50/DFB40`, height sampler `DF2F0`,
`217F90`, skeletal math/hierarchy, collision intersection and resolution run.

The fixture has all 22 linked player objects and team lists, dynamic book X/Z
coordinates translated by the 35-yard tee LOS, 25-bone low and 62-bone high
synthetic star hierarchies, looping three-key synthetic clips with nonzero root
motion, nonzero blend weights, and native block tasks installed for the nine
setup blockers. The ten coverage positions are near the receiving 40 and the
setup blockers near receiving 35-30. The fixed cases use radius-250 cm spheres
to force repeated overlap **without changing alignment positions**. This is
an adversarial collision fixture, not a claim about retail collision radii.
The residual v2 counterexample uses radius 30 cm.

Each fixed case executes 61 held frames including entry. Each reaches the
sampler, pose spring and hierarchy 1,342 times (22 players x 61 frames), native
block-task dispatch 135 times, sphere intersection 1,586 times, and pair
resolution `1DD720` 1,098 times. Both channel blend flags start set; the native
idle selection/hold completes them. The observed blend weights remain
bit-identical, including their nonzero seeded values.

Actual ABI leaves are hardware controller queries `63810/65550`, the roster
attribute lookup `17B010` returning 1, and audio gain submission
`1C3E10/1C3E70/1C3ED0/1C3F30`. The synthetic height callback returns 1.
`48BC0` is the existing deterministic RNG fixture, used once by launch.
The complete receipt gives every actual leaf count. Officials/presentation
actor pools and controller hardware input are empty. This is a complete
dispatcher traversal with bounded objects, not a captured running game.

The recorder watches every native write, including unchanged writes, to each
held transform `+00..5F`, both blend weights, all 25 sampled quaternions, and
the low/high skeleton roots. Events retain player, field, phase PC, writer PC,
offset, and before/after bytes. Lossless dictionaries share repeated events
and complete ordered frame sequences. Fields with no writes still have their
full bytes recorded in each final state.

Frame 0 is the first canonical idle entry, including removal of stale pose
state, and is retained in the trace. Frames 1..60 must equal frame 0 exactly.
Frames 1..20 are ready, 21..40 approach, and 41..60 launched flight. Frame 61
records the actual ground/player contact release. There is no hidden warmup,
per-frame repositioning, pose rewrite from Python or skipped failing frame.

| Case | Held frames compared | Changed held fields | Free players moving each frame | First release frame |
|---|---:|---:|---:|---:|
| Legacy, negative direction | 60 | 0 | 3/3 | 19/19 move |
| Legacy, positive direction | 60 | 0 | 3/3 | 19/19 move |
| Grown, negative direction | 60 | 0 | 3/3 | 19/19 move |
| Grown, positive direction | 60 | 0 | 3/3 | 19/19 move |

## Per-frame writer table

The [60-row table](docs/nfl2k5_kickoff_v3_frame_deltas.csv) lists every frame,
stage, v2 changed-player count for each watched field, v2 transform writer PCs,
and the maximum changed-player count across all four v3 cases. The latter is
zero in all sixty rows. The [full lossless trace](docs/nfl2k5_kickoff_v3_frames.json)
contains **1,666,351 writes** across the five entry/hold/release replays, in
5,342,632 bytes of JSON. No proprietary clip or skeleton assets are distributed.

| Writer PC(s) | Field / phase | What the replay establishes |
|---|---|---|
| `1D898D`, `1D8997` | Transform `+30/+38`, fresh collision | V2 repeated additions with forced overlap; new `1D8940` held guard stops the producer. |
| `28D06D`, `28D081` | Transform `+30/+38`, residual collision | V2 seeded impulse moves all 19 players; native expiry/clear removes the residual before integration. |
| `28E014` | Transform `+00..2F`, snapshot | Copies the previous current transform; fixed case writes the same bytes each frame. |
| `1A8A30` | Transform `+50`, heading | Canonical held heading, unchanged after entry in both directions. |
| `28E3DF/3E2/3F1/3FC/411/41D/43B/441/44B/451` | Transform velocity `+40..4F`, pose | Native repeated calculation. `28E3F1` can write negative zero; `28E43B` writes positive zero. Numerical delta is zero and the final bytes match. |
| `E0110` feeding `28E360` | Separate spring outside watched `+00..5F` | V2 residual changes pose independently of the clip clocks; v3 clears its input/current/velocity before the pass. |
| `DFC16/29/3C/4F` | Sampled quaternion output | Native decoder/blender writes remain; final sampled pose is byte-identical while held. |
| `3CA44B..3CA4C2`, `8E356..8E3A5`, `31203/206/20A/20E` | Low skeleton root | Native local-matrix construction, scaling and world conversion rebuild the buffer; corresponding final outputs match. Full trace lists each exact PC and offset. |
| `92193`, `31203/206/20A/20E` | High skeleton root | Native low-to-high/hierarchy output; same final bytes each held frame. |
| No writes during stable hold | Blend weights `+6C/+88` in animation object | Nonzero seeded values are recorded and remain unchanged; blend flags/clocks prevent decay. |

Intermediate signed-zero stores and local-to-world buffer rebuilds are
explicitly retained. They are not evidence of visible displacement by
themselves. "Zero deltas" means exact equality of corresponding final-frame
outputs, including every watched byte, not absence of native buffer writes.

## Receipts and validation

[Exact receipts](docs/nfl2k5_kickoff_v3_receipts.json) include every hook/cave
edit, section digest edit, allocator seal edit, allocation request, case
summary, trace digest, and the fresh-collision additions with no residual seed.

| Executable stage | SHA-256 |
|---|---|
| Kick-rules input | `b5bcf6bd46246bd77ceff9a144f6ea5cb7fda67057115a5a29d9eb193ae0a49b` |
| Legacy v3 | `adbb28c2443804c3dbc475c91461058bd3955c36333b86e572e5aabf9a3a3f85` |
| Complete union allocated | `d7d2333aa666164a9f903201baaef19f00f5256dc7215f0b253c1a1b64da5e15` |
| Relocated v3 | `3c5dade4ad33648e5fcad97e58f8d90b084265faf6f9d1b6d3e1c7e8b5a96121` |

Commands below were run standalone with plain Python; `/usr/bin/time` captured
elapsed time and maximum resident memory. Private evidence/dependency absence
has precise unittest skips; the lossless receipt integrity check is public.

| Command | Result | Time | Max RSS KiB |
|---|---|---:|---:|
| `python3 tests/mod_editor/test_nfl2k5_dynamic_kickoff.py` | 23 passed | 43.36 s | 671,112 |
| `python3 tests/mod_editor/test_nfl2k5_kickoff_v2.py` | 12 passed | 29.21 s | 721,720 |
| `python3 tests/mod_editor/test_nfl2k5_kickoff_v3.py --record` | five complete traces generated | 127.21 s | 296,516 |
| `python3 tests/mod_editor/test_nfl2k5_kickoff_v3.py` | 7 passed | 140.14 s | 301,236 |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 79 passed | 297.76 s | 313,948 |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py -f` | 95 passed | 380.60 s | 516,924 |
| `python3 tests/mod_editor/test_provider_integrity.py` | 7 passed | 7.24 s | 183,384 |

The first cave-gate attempt correctly refused the release manifest's camera
declaration from the smaller camera/calendar preset, which is outside that
manifest's final dormant-owner allocation. The test projection now reconstructs
the exact preset origin and retains strict owner/kind/size/alignment matching;
unknown owners still fail. The new live kickoff hook is added only after its
retail pin, composed jump and absence of foreign ownership are proved. The
protected manifest was never regenerated or edited here. A new negative test
initially omitted the separate music RO fixture; its final fixture matches the
gate and tests the unknown-owner rejection. Neither failure was waived.

All 223 tests passed, with no skips. Both XBE gates run the full owner union in
normal/reverse orders and both allocator configurations. The provider's two
changed backend source hashes
were repinned; its integrity rules and closure imports are unchanged.
Protected integration details and the required product-manifest regeneration
are in [WIRING.md](WIRING.md).

No whole disc image or archive pack was loaded. The largest measured test
process stayed below 0.7 GiB, well below 2 GiB; concurrent jobs remained well
below the 25 GiB task limit. No image/pack copy was made or retained. Final
disk and delivery details are recorded below.

## HYPOTHESIS, known gaps, and Noah's witness list

The observed collision/pose mechanisms can explain a freeze whose transform
looks stable in v2's sampler-only proof. Which mechanism caused Noah's exact
jitter remains a hypothesis: there is no captured runtime state from his disc.
The fixture's clips, skeleton hierarchy, roster attributes and collision
spheres are synthetic. Neutral/absent hardware input and empty presentation
pools limit the native paths reached. Retail assets, GPU interpolation/LOD,
paired contact chains and nonneutral human controller state still require a
gameplay witness. Tests prove bounded behavior, not that every possible state
or render path is static. This report does not promote the patch to witnessed.

Noah should check a freshly rebuilt v3 disc, in both kicking directions:

1. Watch all ten coverage players and nine setup blockers from lineup completion
   through ready, the kicker's approach and ball flight. Look for feet sliding,
   body sway, head/root flicker or alternating poses, including close camera
   and distant/LOD views. The initial change to idle is expected; repeated
   motion after it is the failure to report.
2. Confirm the kicker runs up and both deep returners can move throughout.
   Select a coverage/setup player and hold directional input before the kick;
   that player must stay held. Move each deep returner with human input.
3. On first ground contact and first caught/touched-ball contact, verify all
   nineteen release immediately, with no delayed start, snap or stuck blocker.
   Watch crowded/overlapping players and paired animations on the first return
   frames for side effects of discarding pre-contact impulses.
4. Repeat normal, squib, end-zone, landing-zone, short and out-of-bounds kicks;
   confirm prior touchback/spot behavior, close block targets and compressed
   play art remain correct. Check onside, safety kicks and scrimmage behavior.
5. Repeat after a possession/direction change, another kickoff and a reset/new
   game. Include both legacy and grown builds and the full composed stack.

## Delivery

Delivery consists of fifteen explicit paths: the two kickoff backends and
their provider hash pins, seven test and fixture files, three public evidence
files, this report and `WIRING.md`. Git staging succeeded on
`astra/r63-kickoff-v3`; the commit uses that exact path list. `ASTRA_BRIEF.md`,
`.scratch/`, all protected files and historical v2 receipts are excluded.
No push or gameplay/disc build is part of this delivery.

Final pre-commit capacity measurement: root filesystem free space
107,106,041,856 bytes (107.106 GB); scratch logs/scripts total 28,790 bytes,
below the 200 MB limit. The three public JSON/CSV evidence files total less
than 5.6 MB. There are no acceptance discs, archive packs or game executables
to clean up. The commit identifier is reported in the delivery response.

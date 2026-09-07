# Dynamic kickoff v2: fixed hold, nearest blocker, fitted card

**EXPERIMENTAL / UNWITNESSED.** Implements B2, C2 and D2 from `ASTRA_BRIEF.md`.
Parent: `331e04d33fcf8a57788821f9618eb3927383fbeb`, branch
`astra/r63-kickoff-v2`. Noah's observations are evidence about the prior build;
the revised build has not been played.

The shared dynamic kickoff compiler now holds a fixed native idle frame,
selects the nearest approaching coverage player for released return blockers,
and compresses the dynamic kickoff formation into the play-call card. Both
legacy and grown implementations use **1,938 / 1,939 code bytes**, with the
same **10 bytes of state**. No option, allocation request, writer order or
protected file changed. No `WIRING.md` change is needed: the existing build
already runs `xbe -> kickoff_alignment -> kickoff_returns`.

## B2: held-player jitter

**PROVED, pinned native instruction trace.** The frame dispatcher `11A7C0`
snapshots transforms through `28DFE0`, runs player planning, dispatches motion
through `2180D0 -> 218010`, and subsequently runs physics/collision. The
relevant competing writers are:

1. `28DFE0` copies the current transform at `+30..5F` to `+00..2F`.
2. `218010 -> 31BEB0` advances clip time, selects keys through `DF8B0`, and
   applies animation root movement through callback `2CC570`. A second height
   callback is possible when animation-state `+8C & 0x800` is set.
3. The prior wrapper restores the saved 48-byte transform after sampling.
4. The prior `2CC4F0` position wrapper copies the earlier frame position back
   again when collision supplies a proposed position.

Replaying the committed v1 receipt reconstructs its exact XBE SHA-256. With a
bounded three-key looping clip, eight native frames select keys **1,0,1,0,...**,
at times **1/60,0,1/60,0,...**. `2CC570` writes alternating x/z/height/heading
values, then the wrapper restores them. End-of-frame position alone passes
the old test while these internal changes and sampled-key changes persist.
The exact per-write PCs, old/new bits and frame samples are in the receipt.

**Implemented and PROVED.** Held motion enters native descriptor `50F4EC`
with zero speed and normal opposing-team heading. It completes both channel
blends, fixes both channel clocks at zero, and passes zero elapsed time into
the native sampler. The sampler and animation-updated bookkeeping still run.
Held root callbacks return without integration; held collision position
callbacks return without copying a snapshot. There is no restore competing
with either integrator. Native clip installation `2D6B70 -> 31C180 -> 31BD40`
also executes in the stale-clip test, including a stale running clip already
in the idle descriptor and an unfinished blend.

The tests execute all **19 held slots**, both directions, CPU and selected
human control, ready state 13, approach state 14 before launch, and flight
after launch. Each stage runs six frames: **1,368 held frames** across the two
XBE placements. Every position/heading remains bit-identical; a memory-write
observer records **zero value-changing writes** to the current 48-byte
transform. Ground or player contact resumes advancing keys, root integration
and the native position setter. The kicker, two deep receiving slots, lineup
state 12, onside, safety and scrimmage retain their existing scope behavior.

**HYPOTHESIS / boundary.** This reproduces a concrete mechanism capable of
the reported jitter; it does not identify Noah's exact loaded clip. Bone
decompression and final skeletal blending are explicit leaves. No GPU image
or complete multi-player physics scene was rendered. Visual stillness and
the first visible release frame remain gameplay witness items.

## C2: nearest approaching coverage and actual engagement

**PROVED, native selection counterexample.** `2400B0` decodes the Block Leg
operands and `23F450` initializes its task. Drive type 0 uses selector mode 2
and callback `23CE70`; lead type 4 uses mode 3 and callback `23F100`.
`2FAFF0` is a weighted role/stance/direction/history contest, not a nearest
distance search. The local relative flag and zero offset already supply the
blocker's current position. They do not impose nearest-target selection.

In both field directions, the prior code chooses the opponent **1,000 cm**
away over one **500 cm** away and returns primary confidence **0.0**. This
executes the real selector, `239C10`, `239C40`, `23A3E0`, task-stack management
and stance/history paths, which the previous session had doubled. Native lead
refresh `23A630` then clears its primary pointer because that score is below
its approximately **0.85** threshold. Drive does not have the same confidence
gate, but can still pursue the farther assignment. These are concrete
counterexamples, not a claim to have reconstructed Noah's exact roster state.

**Decision.** PLAY operands alone do not express the required nearest rule.
All nine setup blockers keep their immediate local drive leg. Both deep
players retain their original receive/run branch; the non-carrier alternate
now uses **drive type 0**, replacing lead type 4. Every generated block is
`[type=0, time=0, relative=1, end=0, turn=2, x=0, z=0, group=0]`.

The native selector hook applies only to an active normal kickoff in live
state 14 after first contact, receiving-team on-field slots 0..10, excluding
the current carrier, and only mode 2. Kicking-team identity comes from the
saved kicker, so a possession change does not reverse the opponent set.
Other cases replay the pinned retail prologue.

The scoped rule walks the kicking team's player list, excludes the kicker
and hidden/off-field slots, and considers only coverage slots 1..10:

- The man must be in front of the blocker in the receiving team's field
  direction, including the same z line.
- `(candidate position - blocker position) dot candidate velocity <= 0` in
  x/z defines approaching. Zero velocity is eligible on the first release
  frame. Receding and non-finite candidates are rejected.
- Minimum squared x/z distance wins; equal distances preserve list order.
  There is no deeper fallback or exclusive assignment reservation.
- Primary confidence is 1.0. A null primary means no eligible coverage man.
  The walk stops after 22 entries even if a damaged list cycles.

Native `23CD60` ordinarily keeps its old target within a 137.16 cm switching
margin. The scoped selector updates the existing drive task's primary too,
so that exception cannot retain a farther man. The test moves a competitor
80 cm closer and executes the native refresh to verify the switch. Distance
instructions use **SSE1**, matching the retail instruction set; a Capstone
regression excludes SSE2 from the generated cave.

**PROVED beyond leg existence.** In **80 cases** (ten blockers, either deep
carrier, two field directions, two XBE placements), native decode and task
initialization select the geometric nearest opponent, mode 2, callback
`23CE70`, confidence 1.0 and collision eligibility bit `0x8`. The real drive
callback produces pursuit input. Supplying the touching pair at the collision
broadphase boundary then executes:

`1DA980 -> 234070 -> 233B50 -> 2336E0 -> 23CE70 -> 23A900`.

Both players receive mutual paired-opponent pointers at animation-state
`+D0`; their descriptors satisfy native `231EE0`; collision flags gain
`0x2` (combined `0xA`); the engaged drive update sets player-state `+580 & 8`.
The full history, stance, contact eligibility, facing checks, attribute
evaluation, animation choice and pairing code execute. Paired clip asset
installation `30E000` and stats notification `A1EC0` are leaves. Neither the
target selector nor the contact result is doubled.

**HYPOTHESIS / boundary.** Contact is supplied at 50 cm separation; the test
does not run a full broadphase or prove every moving player reaches contact
in a crowded live return. Native attributes, eligibility, block wins/losses,
timing and multiple blockers choosing the same opponent still affect play.
The revised rule guarantees the selected eligible target in the tested
native path, not a successful block animation on every attempted collision.

## D2: all eleven circles within the card

Noah's supplied screenshot shows the ten coverage numbers above the stadium
card and only kicker 11 in its art. **Type correction:** the offending
`Kickoff` formation is native type **8**. Type **9** is `Kick Return`.
The earlier type-9/13 discussion described a different compressor branch.
The positive dynamic coverage depth is 2,286 cm, versus retail -914 cm.

**Implemented and PROVED.** Hook `1802BB` is reached only in diagram mode,
after retail x compression. It recognizes type 8 and the aligned first
coverage row (`formation+30 == 0x08EE`), and only transforms depth requests:

`diagram z = formation z / 8 - 640.080017 cm`.

The scaling retains the kicker/coverage ordering and centers the formation
within the native kickoff camera. Retail lateral compression is retained.
World mode and lateral-only queries replay unchanged. The card is independent
of the kickoff's live latch and works before a play is launched.

The harness executes native camera construction `144360`, the card viewport
update `2BB00`, activation `2AC80`, diagram setup `1807F0`, circle style
`165760`, then the complete eleven-player loop:

`181010 -> 17FE60 -> 180120 -> 1650A0 -> 2AB40 -> 1644D0`.

It captures the finished quad transform and four vertices at GPU submission.
The native radius is **15 pixels**. Every vertex, not just the circle center,
must lie inside the supplied card-art rectangle. Tests cover four full/split
card rectangles, kicker run-ups 1/5/15 yards, flip, native camera modes with
and without a play, video modes 0/2, and both legacy/grown XBE placements,
with and without **widescreen v3**. Paired 4:3/v3 outputs are identical.

For the full-card fixture `[64,300,576,440]`, all final circle quads lie within
`x=218.296..420.672, y=349.239..398.440`. The old coverage quads start at
`y=288.432`, crossing its top edge. This is a native-coordinate regression
fixture; it does not claim pixel-identical reproduction of Noah's camera.
The supplied viewport begins at the boundary after `144BA0` has clamped the
card rectangle. Device setup/query and final GPU submission are leaves.

Across the 36 private books, **1,510 formation records** reduce to **603
distinct named records**. All their diagram coordinates are byte-identical
to retail, plus the newly aligned type-9 return formation. Only the dynamic
type-8 record changes. Existing world-route/widescreen regression tests pass.

## Pins, PLAY data, receipts and limits

New complete-instruction pins:

| Hook | VA | Retail bytes |
|---|---|---|
| Root motion | `2CC570` | `83 ec 1c 56 8b 42 10` |
| Block target | `2FAFF0` | `55 8b ec 83 e4 f0` |
| Diagram depth | `1802BB` | `8b 45 0c 85 c0` |

Fifteen hooks share the existing compiler and reserved cave. Runtime state
remains writable data; temporaries use the stack. No new cave, owner or
allocator budget is taken. The existing allocator union already includes
this owner. Both gates inspect the new hooks, the unchanged allocation
limits, immutable code and current full-stack composition. The protected
release reservation manifest remains for its normal maintainer regeneration.

The fixed-span writer still appends **78 private nodes per book**, **2,808
total**, in all 36 normal-return books. Each resource stays `0x133B0` bytes.
The return writer changes **19,217 bytes total** relative to its input;
alignment edits are recorded separately. Other plays and both carrier
branches remain byte-identical. The streaming writer validates every book
before writing; all-resource idempotence and mixed/foreign refusal pass.
Previous v1 XBE bytes and old lead-branch PLAY outputs are refused before
mutation. **Rebuild the older experimental disc from the supported base.**

[Exact receipts](docs/nfl2k5_kickoff_v2_receipts.json) contain all hook/cave
bytes and offsets, source/result hashes, section digest edits, allocator seal
metadata edits, 36 alignment-then-return resource transactions, and the
native synthetic frame/target/contact/card measurements. Receipt replay is
tested byte-for-byte. The grown receipt allocates the current complete
request union and installs this owner at RX `14BA2C0`, RW `14BB000`; it is
not a claim that a final disc was built. The gates separately compose every
owner in both installation orders and allocator modes.

Retail input SHA-256:
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
The legacy cave's original SHA pin is unchanged. The receipt records the
final derived XBE hashes; no private executable, complete PLAY resource,
pack or disc is included.

## Validation

Final standalone results are recorded below. Private inputs were opened
read-only; the largest input loaded was the approximately 12 MB XBE. Each
process stayed below the 2 GB test limit. No console emulator, GUI, audio, network,
disc build, archive mutation or push was used.

| Command | Result | Time | Peak RSS |
|---|---|---|---|
| `python3 tests/mod_editor/test_nfl2k5_dynamic_kickoff.py` | 23 passed | 42.830 s | 640,948 KiB |
| `python3 tests/mod_editor/test_nfl2k5_kickoff_fixes.py` | 11 passed | 11.262 s | 530,252 KiB |
| `python3 tests/mod_editor/test_nfl2k5_kickoff_v2.py` | 12 passed | 28.754 s | 795,012 KiB |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 79 passed | 291.177 s | 314,332 KiB |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 91 passed | 375.159 s | 473,024 KiB |

`git diff --check` passes. Allocator planning used
`python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json`;
no requests changed. Final disk and delivery checks are recorded below.

Disk available at the final check was **108,020,760,576 bytes** (108.02 GB,
100.6 GiB). `.scratch` contained approximately **0.64 MB** of scripts, notes
and logs. No temporary disc or pack was created. The brief and supplied
witness screenshot are unchanged local inputs and are excluded from the
explicit-path commit, as is `.scratch`. No protected path is in the change.
The five suites total **216 passing tests**, with no skips in this workspace.
Delivery uses an explicit-path commit on `astra/r63-kickoff-v2`; nothing is
pushed. The report, exact receipt, three core modules and five test files are
the complete ten-file change.

## Noah's witness list

1. Rebuild with dynamic kickoff, alignment and the return writer. In practice
   and a game, watch all coverage/setup players from ready stance through
   approach and flight, in both directions. Confirm no jitter, sideways pose
   or release pop; verify kicker and both deep returners can move normally.
2. Field the ball with each deep player. For left/middle/right returns, watch
   every setup blocker and the other deep player take the nearest approaching
   coverage man. Confirm they make visible contact instead of passing him for
   a deeper man or the kicker. Include crowded traffic and a human selection.
3. Open the Kickoff card in 4:3 and widescreen v3, then flip it and try short
   and long kicker run-ups. Confirm all eleven numbered circles remain inside
   the art and are readable. Check Kick Return, onside, safety and ordinary
   offense/defense cards for unchanged layout.
4. Recheck first contact, in-field catches near the receiving 1, true end-zone
   touchbacks, grounded/end-zone decisions, and short/out-of-bounds kicks.
   Confirm lineup and the next normal play still reset/release correctly.

Visual crowd behavior, complete collision traversal, animations and gameplay
outcomes remain **UNWITNESSED** until Noah plays this revision.

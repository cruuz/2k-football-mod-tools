# r64 kickoff v6: native touchback presentation

2026-09-08. Branch `astra/r64-kickoff-touchback`, base `45c0544a`.
**EXPERIMENTAL / UNWITNESSED correction.** Noah's 2026-09-07 disc-bh witness
established that v5's stance and blocking were good. This revision addresses
his missing knee animation and inappropriate return commentary. It has not
been played by Noah.

V6 occupies **1,939 / 1,939 code bytes, the existing 10 state bytes, and
twenty pinned hooks**. Both legacy and relocated installations use the same
compiler. There is no new option, enlarged reservation, new runtime asset,
archive edit or allocator budget change.

## Root cause: native replay, not an inferred visual diagnosis

**PROVED:** v5's returner wrapper at the native player planner `1CD5D0`
classifies the held ball in the end zone and directly invokes its `finish`
helper, which calls `A0390`. The native `B7230` transition writes play state
14 to 18 and builds the spot on the catch frame. The held-player predicate
excludes the two deep receiving slots, so their frozen stance is not the
cause. The release path does not call a commentary enqueue API.

The native post-catch selector `2EE1F0` can already have installed task
`2EE090` when this happens. V5 preempts **execution of the kneel task**, not
necessarily that earlier selector. In the recorded counterexample, the
selector runs, v5 whistles on frame 0, and no kneel initializer or kneel
clip event executes. A later poll of `2EE090` after the whistle returns
because the play is already dead. This establishes the classifier/early
whistle mechanism among the brief's three proposed causes.

**PROVED retail sequence:** `2EE090` waits for the catch animation's busy
bit to clear, clears the previous task through `1ABCD0`, and requests action
`0x63` (99 decimal). The planner selects descriptor `5103A0`. Its `222C20`
initializer installs retail clip `71CA7C` or `71CAB0` through the real
`2D6B70`. These embedded kneel clips have 23 bones and 19 keys at 15 fps.
The sampler, both skeleton passes and native event decoder execute; no
synthetic kneel clip, substituted event, injected whistle or advanced clock
is used. Event `0x5F` has time `66064 / 65536 = 1.008056640625` seconds.
It dispatches `305580 -> A1920 -> B7550 -> A1A20 -> A0390`. Native event
`0x3A` (kneel) and `0x5B` (touchback) precede the play-state transition.

**PROVED commentary mechanism:** earlier frame fixtures disabled the event
producer with `B6FF64 = -1`. V6's fixture initializes a real play-event record
with `A82E0` and runs the real `A7930 -> 1E91F0` producer and
`A7B40 -> A7AD0 -> A7A40 -> A7690` ring writes. Deliberate clear-lane geometry
makes native `1BB3B0` count zero defenders ahead, exposing event `0x33`.
A separate, explicitly supplied deferred-contact input calls native
`1E8FA0`. While ball mode is 2, its announcement waits; `1E91F0` processes
that pending input **before** checking whether the play is live. V5 thus
queues `0x0D` after its immediate whistle. These are native producers, not
an unconditional announcement added to the owner's release code.

**HYPOTHESIS:** associating Noah's exact "off to the races" recording with
one particular event ID. No audio device, waveform, phrase catalog or game
was used. The replay proves event production and ordering for its stated
inputs; spoken wording and final rendered presentation require Noah's witness.

## Correction and allocation

For an eligible CPU end-zone catch, the owner tail-calls native `2EE090`
instead of `finish`. Existing receiving-team, actual-holder, CPU probability,
human controller, lock and already-returned guards remain. The native task
waits for the catch lock, and the native clip event supplies the whistle.
The busy-catch counterexample remains live without entering the kneel clip
or requesting an early whistle.

The new five-byte hook at `A7930..A7935` pins retail `e9bb181400`.
Its displaced instruction is a relative jump, so the wrapper explicitly
jumps to `1E91F0` when out of scope. It preserves the one-stack-argument ABI.
During an active normal kickoff, it defers the whole per-frame return
commentary producer while the ball is in the receiving end zone and has
never entered the field under possession. It also guards the post-whistle
pending contact. The separate possession, kneel and touchback producers
continue. Native next-play initialization clears the pending contact with
`1E8E20`; it does not leak into the next record.

An uncaught kick that actually contacts the ground in the end zone now ends
at the ground callback, independently of a CPU kneel roll or human controller.
An airborne ball crossing the goal line remains live. The first-contact
history still controls direct versus landing-zone touchback placement, and
the `RETURNED` latch prevents a later loose-ball contact in the end zone
from undoing a controlled return. The field-of-play eligibility guard still
rejects a touchback even when the retail kneel descriptor would allow one.

Sharing invalid-contact classification, removing the obsolete loose-ball
poll/ground-marker bit, combining equivalent flag tests and compacting the
finish tail calls funds the additional hook. No bytes outside the existing
reservations were taken. Legacy code remains `2890F0..289883`; state remains
`A69969..A69970` and `A69971..A69974`, excluding the neighboring byte at
`A69970`. Relocated requests remain code 1939/alignment 16 and data
10/alignment 4. Every runtime absolute write is checked against writable
storage; the code pages are protected against writes during native replay.

## Full-frame evidence and preserved behavior

`tests/mod_editor/test_nfl2k5_kickoff_v6.py` runs standalone and records
`docs/nfl2k5_kickoff_v6_receipts.json`. Each frame must enter and finish
`11A7C0`, execute all 27 phases in order and return with the correct stack.
The compact receipt retains every frame's state, descriptor, position,
height, clip clock, full low-skeleton hash and actual event-ring contents,
plus lifecycle events, state writes, next-play records and exact XBE edits.

The contact is an explicit fixture input during the ball-update phase:
`B78C0` completes touch bookkeeping, `DDCD0 -> 26A4A0` attaches the ball and
runs `A0870`, and `2EE1F0` selects the next native task. Ground cases execute
the complete `A06E0` callback with its real stack argument. The original
phase then runs in full. The supplied post-whistle advance on a subsequent
frame calls `22EB70 -> 22EA20 -> 22DF90 -> 22E3A0` and `A82E0`; the receiving
team gets a scrimmage record, first down and the correct spot. This proves
the next-play **record**, not a rendered huddle, play-call screen or snap.

| Replay | Result |
| --- | --- |
| Retail catch six yards deep | Native kneel begins on frame 1; whistle on frame 61; next first down at the 20. Clear-lane and pending-contact events are visible in this adversarial input. |
| Exact historical v5, same catch | Whistle on frame 0; no kneel clip; pending `0x0D` after the whistle; next first down at the 35. |
| V6 catches one and six yards deep, both directions and allocations | Native kneel begins on frame 0; whistle on frame 60 after the real clip event; next-play record on frame 61 at the 35. No `0x0D` or `0x33` in the queue. |
| V6 uncaught end-zone ground contact, both directions and allocations | State 18 on contact frame 0; next-play record on frame 1 at the 35; no attachment, kneel clip or return-start event. |
| Catch at the 3 and at the 1, both directions and allocations | Ninety complete frames of forward return, more than ten yards gained, no touchback or premature whistle. Every recorded frame, native event and pose matches the same replay of historical v5. Native return announcement `0x33` remains enabled. |

The twenty-six recorded cases include retail/v5 counterexamples, eight v6
caught touchbacks, four uncaught touchbacks and twelve v5/v6 field returns.
Additional tests cover a busy catch animation, out-of-scope commentary and
its stack ABI, a rejected CPU kneel roll with CPU/human control of an
uncaught ball, mixed/foreign patches and exact installed-byte replay.

V2 through v5 tests remain green. V5's immutable setup receipt still compares
every state and write; only the two unchanged motion/head writer PCs are
named relative to their wrappers because v6 moves those instructions by
five bytes. Native PCs, write values, ordering, counts, pose states, readiness
and foot traces remain exact. Its twelve continuous-return cases still
match their complete saved receipts. All ten historical v1 through v5
legacy/grown executables are reconstructed against their published hashes
and refused by both current backends. V5's recorder now refuses to overwrite
its historical artifact with a newer compiler. No old receipt was rewritten.

## Boundaries and integration

The inherited v5 fixture supplies synthetic locomotion clips, skeletons,
rosters and decoded controller intent. Coverage starts behind the carrier
to stress the real clear-lane announcement, rather than reconstructing
Noah's particular on-field geometry. Ball catch/ground contact and the
post-whistle advance are supplied inputs. Catch/attachment, task selection,
kneel animation, event timing, whistle, placement and next-play construction
are native. The existing unrelated asset/service leaves remain, including
`B7330`'s cutscene path. The event queue runs without an audio listener.
This is bounded Unicorn instruction execution, not a console-emulator or
runtime gameplay witness. No GUI, audio, network, disc/pack build or push was
used, and no process loaded a whole disc or archive.

All protected files remain untouched. `WIRING.md` specifies the new hook,
manifest regeneration, existing dispatcher tuples/kwargs and four status
dicts, BuildPlan/preset behavior, Retail/Patch text, image requirement,
caption, allowlist and runtime imports. The existing provider source hash
was refreshed so its integrity boundary recognizes this owner. The manifest
builder's owner/union lists already cover the relocated owner; only the
existing test projection needed the extra pinned live span.

The protected manifest is stale by design until Claude integrates and
regenerates it. Besides this changed kickoff source, its ESPN-scenario and
roster-record source pins are already stale on HEAD; both source files are
unchanged here. The latter is an additional base discrepancy beyond the
one named in the brief. The stock oracle refuses rather than accepting those
pins. Both complete XBE gates pass with their existing strictly checked
allocation/hook projection; this does not replace the product manifest.

## Noah's three-situation witness list

1. Catch a normal kickoff in the end zone with a CPU returner, in each
   direction. Confirm the catch finishes, a visible knee goes down, the
   whistle follows the animation, and return-start commentary does not play.
   Confirm the next possession and configured direct-touchback spot.
2. Catch at the 3, and repeat at the 1. Confirm a normal return, v5's still
   stances and nearby blocks, appropriate return commentary, and no touchback
   awarded for a ball fielded in the field of play.
3. Let an untouched kickoff land in the end zone. Confirm an immediate
   touchback by rule without a forced catch/kneel or return-start commentary,
   including with human control selected, and the correct next-play spot.

## Exact artifacts

| Artifact | SHA-256 |
| --- | --- |
| `retail_xbe_sha256` | `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9` |
| `legacy_input_sha256` | `b5bcf6bd46246bd77ceff9a144f6ea5cb7fda67057115a5a29d9eb193ae0a49b` |
| `legacy_output_sha256` | `9b0481a73c03f43bc3b1162d21dd7a51f32e668464c83110a741984c24618164` |
| `union_allocated_sha256` | `90bf322edd7c338d85f4a368de3eb903cd24daed613d9a1f716e86277622c998` |
| `relocated_output_sha256` | `d029109252501bcb2a592f8c76168846b6104d765472dc06cfe55a4fcf92b239` |
| `mod_editor/core/nfl2k5_dynamic_kickoff.py` | `0f2a618ce8ad2443a472145fa69a7d06e0f78af1e9f7ce211ed9b35b00e6a6e7` |
| `mod_editor/core/nfl2k5_dynamic_kickoff_relocated.py` | `211063695451178000aa7088245ddef8c31973f08fad490341a378bf6e8a6b4f` |
| `docs/nfl2k5_kickoff_v6_receipts.json` | `771183fcb8747677aad56d7fc6133d5f139fdc2874c8d3ab1c4c8a397d3e6863` |

The new receipt is **359,186 bytes** and contains **26 cases / 1,649 complete frames**. Old v1-v5 receipt blob hashes match HEAD unchanged.

## Exact validation commands and final results

Each row was run as a separate bounded process, with `/usr/bin/time -v`
recording peak RSS. Final logs and timing files remain in `.scratch/`.

| Command | Passed | Seconds | Peak RSS (KiB) |
| --- | --- | --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_dynamic_kickoff.py` | 23 | 44.738 | 665,860 |
| `python3 tests/mod_editor/test_nfl2k5_kickoff_fixes.py` | 11 | 11.965 | 526,348 |
| `python3 tests/mod_editor/test_nfl2k5_kickoff_v2.py` | 12 | 27.961 | 724,392 |
| `python3 tests/mod_editor/test_nfl2k5_kickoff_v3.py` | 7 | 142.256 | 345,340 |
| `python3 tests/mod_editor/test_nfl2k5_kickoff_v4.py` | 8 | 964.153 | 520,836 |
| `python3 tests/mod_editor/test_nfl2k5_kickoff_v5.py` | 6 | 478.026 | 1,303,336 |
| `python3 tests/mod_editor/test_nfl2k5_kickoff_v6.py` | 9 | 132.238 | 705,464 |
| `python3 tests/nfl2k5_kickoff_alignment_test.py` | 7 | 0.481 | 35,328 |
| `python3 tests/mod_editor/test_provider_integrity.py` | 7 | 8.089 | 183,316 |
| `PYTHONPATH=. python3 tests/mod_editor/test_providers.py` | 33 | 4.365 | 57,048 |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 91 | 360.171 | 317,492 |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 103 | 444.019 | 508,644 |

**317 tests passed in these suites, zero failures or skips.** Peak single-process RSS was 1,303,336 KiB, below 2 GB.

`python3 -u tests/mod_editor/test_nfl2k5_kickoff_v6.py --record` completed
with exit 0, eight successful native proof methods, 2:13.14 wall time and
705,484 KiB peak RSS. The subsequent standalone suite additionally checks
the public receipt and replays every recorded case against it.

`python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json`
completed with exit 0 and a 12,300,288-byte output plan; existing kickoff
allocations and all other owner requests are retained.

`python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` ran 28 tests in
110.740 seconds: 27 passed and one raised the expected source-drift refusal
at the changed kickoff source. Peak RSS was 910,320 KiB. The three stale
source hashes and required protected-manifest regeneration are documented
above and in WIRING. This gate was not bypassed or reported as passing.

`python3 tests/mod_editor/test_nfl2k5_kickoff_v5.py --record` deliberately
refused with exit 1 and "Current compiler is not v5; preserve the historical
v5 receipt". A subsequent blob-hash audit confirmed all old receipts
unchanged. The base provider test requires `PYTHONPATH=.` for direct file
invocation; its initial bare invocation failed on its existing import path,
then the command in the table passed. No provider test source was changed.

Development runs exposed obsolete immediate-whistle/human-loose-ball
expectations, the old nineteen-hook count, incomplete task/controller/ring
fixture inputs and a tuple/list comparison after JSON serialization. Those
were corrected and the final suites rerun. The final v5 rerun also validates
the shared `begin_catch` fixture refactor. Production behavior was not
replaced by fixture state writes to make the kneel or whistle pass.

Final `git diff --check`, staged-path/protected-file audits and Python
compilation passed. No active commit hooks are installed. Delivery uses
explicit-path staging and commit on the requested branch; `ASTRA_BRIEF.md`
and `.scratch/` are excluded. No push was performed.

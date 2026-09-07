# Read-option controls v2, 2026-09-06

EXPERIMENTAL / UNWITNESSED. Basic, Advanced and Experimental presets remain off.
Noah has not played this revision. No game, console emulator, GUI display, audio
or network was used. Unicorn results below are bounded instruction proofs.

Built on `a1cd0d9` in `astra/r62-read-option-controls`. This extends the landed
`nfl2k5_read_option_runtime` owner and its paired PLAY compiler. It adds a native
human read cue, snap-based selection of an unblocked replacement EDGE, a window
counted in simulation updates, CPU hysteresis, and a receiver press carried
through the native RPO pass initializer. Native Shotgun Zone read/RPO authoring
is now available in the core helper so Noah's requested witness plays can be
compiled. Protected product integration is specified in `WIRING.md`.

**Allocation and installation decision.** Grow the existing owner; no
`nfl2k5_read_option_ext` or second feature flag. Rebuild from the supported base
with the complete revised allocator request union before installing any owner.
The old 960 RX / 64 RO allocation and partial v2 allocations refuse before
mutation. They cannot be upgraded in place. The existing 64-byte `RDO1` table
still holds at most two reads. An empty table leaves this owner dormant.

| Kind | Requested bytes | Alignment | Content |
| --- | ---: | ---: | --- |
| RX | 2,048 | 16 | Five entry points and shared helpers; assembled code plus final alignment uses all 2,048 bytes |
| RW | 256 | 16 | Current mesh identity, sampling, receiver latch and eleven snap assignment records |
| RO | 88 | 16 | Existing 64-byte paired identity table plus HUD anchor/scale and CPU policy constants |

This fits the authorized 2,048 / 256 / 256 ceiling. The committed beta-62 budget
fixture now contains these actual rows. The stack helper and manifest builder
already enumerate this owner and use its live `REQUESTS`; their existing union
therefore includes v2 without another owner or duplicate installation. Both
gates explicitly require installed `model_version=2`.

Observed allocations in the complete dormant-owner manifest were RX
`0x14de240` (raw `0xb8e240`), RW `0x14f3600` (raw `0xba3600`), and RO
`0x1508e00` (raw `0xbb8e00`). These are allocator observations, not hardcoded
runtime addresses. The composed XBE remains 12,300,288 bytes. Runtime state is
outside `.text`; RX and RO are immutable. All five hooks overwrite complete
pinned live instructions, preserve their displaced behavior, and have no
interior retail entry or foreign owner overlap in either installation order.

| Hook | Retail VA | Pinned bytes | Continuation |
| --- | --- | --- | --- |
| Conditional update | `0x1af191` | `d94760d81d80414e00` | `0x1af19a`, or native result at `0x1af210` |
| HUD | `0x646a1` | `e80a5a0900` | `0x646a6`, after calling native `0xfa0b0` |
| Pass initializer | `0x19c849` | `c70660bb1900` | `0x19c84f` |
| Snap | `0xb6fbd` | `8935c802e600` | `0xb6fc3` |
| New play reset | `0x1ad9c3` | `b95a000000` | `0x1ad9c8` |

`status`/`apply` validate allocation geometry, owner seals, initial RW zeros,
exact code/table/prompt bytes, every hook and dependency hashes before writing.
Successful apply repins section digests through the existing helpers. Replay is
byte-identical; omitted settings retain the installed table and changed explicit
settings require a rebuild. Mixed/foreign hooks, initial state and RO bytes
refuse. The table still binds book, play offset/name and both participant
scripts to exact PLAY/compiler receipts before installation, then rechecks the
bounded relocated identities at runtime.

QB spy has full-body dependency guards around the neighboring native snap and
reset routines. Its inspector now accepts the disjoint v2 hook spans only after
the entire read-option installation passes its own sealed validation. It then
normalizes those exact spans for its original hashes. No guard is dropped.
This compatibility change must ship with v2. The memory gate also had an
existing Senior Bowl test with undefined `image`/`absolute_writes`; restoring
that test's local imports/image construction allowed its assertions to run.

**Controls and lifecycle decision.** A matched native mesh condition owns 21
distinct updates of the native since-snap clock, starting with its first live
condition update. This is a simulation-update count, not a rendered-frame count
or an absolute 0.35-second deadline. At 60 updates/second it is nominally that
duration; animation contact timing remains unproved. Duplicate clock values do
not advance the window or sample input/EDGE movement. Input is accepted on
updates 1 through 20; update 21 commits the already latched decision. A release
at expiry cannot retroactively give. A missing clock waits; invalid, backward
or stale clock values abandon to carrying, as do a dead phase or lost ball.

The human uses the retail physical snap-button column in supported controller
layouts and running contexts: hold through expiry to keep, release in time to
give. Once release is latched, re-pressing does not cancel it. An RPO receiver
rising edge while still holding snap latches pass and survives a later snap
release. Receiver slots 7/B and 8/X are supported; slot 6 shares the snap button
and remains refused. No authored read means ordinary native code continues.

New private state records actor, task, PLAY descriptor, roster identity, clock,
frame count, controller, confidence, crash latch, selected EDGE and pending
receiver. Eleven actor/roster/assignment triples start at RW offset 64, stride
12. The snap hook clears all 256 bytes before taking the actual defense list
snapshot; native new-play reset clears it again and executes the normal native
cache reset. HUD/pass gates recheck phase, ball owner, actor, clock, roster,
assignment, controller and current task/node. Consuming the pass latch clears
it, so a second initializer cannot replay the press.

The tagged native conditional task's real argument at `+0x44` carries pending
and committed decisions; this is not unused memory. The native back result
cache keeps its existing wait/release/take meaning. Native branch advancement
and handoff/carry/pass tasks remain responsible for ball movement. The patch
does not write ball ownership directly.

**EDGE decision.** CPU reads search at most eleven snap actors, with at most
fifteen native script nodes and eleven offensive blocker targets per candidate.
A candidate must still be an active member of the opposing team, retain the
snap roster and assignment pointers, have actual roster role DE (16) or OLB
(10), and have rush opcode 11 in a bounded relocated native PLAY script. It
must be within 2.5 yards of the line and on the authored mesh side. This uses
actual snap assignments, not the authoring fixture's personnel labels.

A valid authored defender is preferred. If absent, blocked or invalid, select
the outermost valid unblocked play-side candidate. With
`compile_intent_table(pairs, use_authored_edge=False)`, the explicit slot-255
sentinel means no authored runtime defender; selection starts with the snap
assignments. The data-tier opponent fixture still validates the native graph.
All existing pairing checks remain in force.

An offensive task targeting the candidate makes it blocked; the QB's own read
target is excluded from that check. This is a conservative assignment-target
test, not a claim that collision/contact engagement has been decoded. A
replacement resets confidence. Each distinct update saturates confidence from
0 to 3 for sustained crash samples and back toward 0 for wide samples. Crash
enters at 3 and leaves at 0. A single twitch cannot establish crash, and one
wide sample cannot erase established crash. The landed finite position/velocity
checks, 0.2-second projection and 2.5-yard lateral bound remain. No valid EDGE
falls back to give; an RPO crash can request its ready receiver.

**Native HUD proof.** The corpus and pinned retail bytes identify the existing
UTF-16 `passicons` atlas literal at `0xe6c234`, loader `0xf9f40`, ready flag
`0xa94ea0`, material `0xa950c0`, and icon draw helper `0xf97f0`. At the live HUD
call site the wrapper executes original `0xfa0b0` and invokes icon index 0 at
pixel anchor `(360, 96, 0)`, native large scale 15. The native UV path uses the
first atlas glyph: `(0,0), (.25,0), (0,.5), (.25,.5)`. Its existing readiness
gate suppresses drawing when the atlas is unavailable. The cue is suppressed
before the window, for CPU controllers, after commitment and after lifecycle
identity changes. Registers, flags and x87 state are preserved around the added
HUD work. The native pixel path is separate from the widescreen world-marker
compensation audited by the landed widescreen work.

Unicorn executes the installed wrapper, native loader checks, icon helper and
UV/vertex preparation. GPU submission functions `0x2d2a0`, `0x2cb90`, `0x2cb50`
and `0x2ca00` are recorded at their actual stack-cleanup boundaries. This proves
the native first-glyph submission and suppression rules. Its visible artwork,
clarity, placement and behavior in every display mode remain Noah's witness.

**Native RPO proof.** The mesh press reaches actual branch advancement
`0x1b8a20`, selection `0x1b8790`, pass-node decoding `0x1b84e0`, and the full
pass initializer `0x19c740`. That initializer clears the receiver and changes
the control context, so merely setting its old task target is insufficient.
The scoped tail hook restores a still-ready pending receiver and selects the
native throw-request callback `0x19bae0`. It preserves ordinary `0x19bb60` if
the target became unready, and consumes the latch once.

Fixtures then execute the native slot getter `0x1907d0`, receiver readiness
`0x19b800`, strength-store helper `0x199260`, and throw-command store to
controller `+0x1c`: `0x42` for B or `0x43` for X. The task allocator boundary
`0x2c9ab0` supplies the fixture's existing task. Aim calculation `0x198c20`
returns a synthetic x87 value through its real ABI. These two boundaries and
GPU submission are explicit fixtures; the input reader, pass initializer,
receiver checks and native command store execute retail instructions. No
flight, animation, contact, catch or complete slant play is proved here.

If the receiver is unready at commitment the mesh gives. If readiness changes
after commitment, the pass initializer follows its ordinary native behavior;
there is no late ball transfer or retry of the consumed press.

**Shotgun recipes.** `make_option_design` now accepts native Shotgun alignment
with an HB in slot 10 and HB/FB/WR/TE in slot 9 for Zone read and RPO. Existing
native I-form behavior is preserved. A WR/TE in slot 9 uses the existing
receiver-block assignment rather than the fullback-follow assignment. Native
positions and personnel remain intact. Empty Shotgun and Shotgun Speed option
are refused. Speed option remains its existing native/data-only lane.

The reproducible `shotgun_reads()` helper in the new standalone controls test
uses MIN `Gun: Doubles Right`, authoring `SD Gun Zone Read` at play 134 and
`SD Gun RPO Slant` at play 31. It calls the existing fixed-span formation/play
writer with exact receipts. The 78,768-byte resource length and native formation
links are unchanged; the two recipes add 59 script nodes. Both held keep and
released give execute against these compiled Shotgun scripts in Unicorn. The
RPO initializer is exercised for both supported receiver buttons. These names
are build/witness recipes, not automatically installed stock plays.

**Validation, all standalone.** Every listed test process exited 0 with no
skips. Times are unittest elapsed seconds; RSS is `/usr/bin/time -v` maximum
resident KiB. Gate/oracle commands use
`NFL2K5_CAVE_MANIFEST=.scratch/read-option-controls/manifest.json`.

| Exact command | Result | Seconds | Peak RSS KiB |
| --- | --- | ---: | ---: |
| `python3 tests/mod_editor/test_nfl2k5_read_option_controls.py` | 15 passed | 15.479 | 325,920 |
| `python3 tests/mod_editor/test_nfl2k5_read_option_runtime.py` | 10 passed | 7.363 | 282,604 |
| `python3 tests/mod_editor/test_nfl2k5_read_option_unicorn.py` | 14 passed | 14.578 | 239,616 |
| `python3 tests/mod_editor/test_nfl2k5_read_option.py` | 15 passed | 9.904 | 222,464 |
| `python3 tests/mod_editor/test_nfl2k5_qb_spy_runtime.py` | 10 passed | 60.124 | 285,716 |
| `python3 tests/mod_editor/test_nfl2k5_qb_spy_unicorn.py` | 16 passed | 6.332 | 410,364 |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 67 passed | 192.064 | 335,564 |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 79 passed | 277.507 | 453,588 |
| `python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | 28 passed | 76.279 | 898,036 |

Both XBE gates exercise the landed owner union in forward and reverse order,
including scale-out subclasses, byte-identical order results, owner replay,
full-width writable targets and complete-hook reference ownership. The memory
check permits only owned RW absolute writes plus the displaced native snap
store at `0xe602c8`; indirect task/caller writes retain native writable objects.
The active two-read tests supplement the complete stack's dormant empty table.

`python3 tools/nfl2k5_read_option_runtime_assemble.py --check` passed.
`python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json`
passed with the revised real requests. All ten changed Python modules passed
`py_compile`; `git diff --check` passed. The updated capability object passed
the unmodified registry validator's full merged structural checks (96 entries)
and its own evidence/backend/validation command file checks. The whole
registry's file-check mode still stops at the pre-existing missing
`docs/research/apf_audio.md`; no validator or unrelated capability was weakened.

The real manifest build called `nfl2k5_cave_manifest.build_manifest` with the
pinned extracted XBE and user-owned XISO. It completed in 282.225 seconds, peak
RSS 803,224 KiB, producing 9,501 spans, 106 observed writer calls and 112 source
fingerprints. All 112 fingerprints match the current sources. The existing
builder records that the seven-on-seven book writer refuses an already
depth-role-transformed PRACTICE resource; the XBE owner union and both gates
still complete. No protected canonical manifest was regenerated.

Before the disposable build, free space was 108,054,306,816 bytes and the disc
was 6,300,499,968 bytes. The preflight also required more than 100 GB to remain
after the disc copy and a 100 MB margin, exceeding the 40 GB refusal floor.
The builder's resolved `TemporaryDirectory` deleted the disc on completion;
free space afterward was 108,043,821,056 bytes. No image or pack copy is under
`.scratch/`. The final scratch inventory was 2,412,561 bytes before source-only
Git delivery, with no image/pack copies. The highest measured process RSS was
898,036 KiB (under 0.9 GiB); no tool loaded a whole disc or archive pack into
memory.

| Evidence | SHA-256 |
| --- | --- |
| Pinned retail USA XBE | `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9` |
| Assembled, unrelocated runtime code | `f4a823f39cbf437fe79a4b5de9cfbab4e586674520af2199a90f1190403b5097` |
| Paired Shotgun PLAY | `05dff027256cd863c50442c9ef15d62175219be40c3b00219d2673ee6523136d` |
| Shotgun automatic-EDGE table | `2fb51240be023296c824ce432e088feea0cbf9c38e891343921d3476f82dfd26` |
| Complete dormant-owner stack XBE | `77491e59559e448860dec906c04474be31db38abfcf848ce19b3ee26bb3a79ca` |
| Private regenerated manifest | `3624fdd0a5712ec201bffe6177f845f5d2cfa2689f5b7f2fbd494b67fee9dd79` |

Only source, recipes, tests and documentation are delivery content. The local
manifest, logs, hashes and budget output remain under
`.scratch/read-option-controls/` and are not staged.

**PROVED.** Exact paired PLAY compilation including supported native Shotgun;
allocation/rebuild refusals and byte-identical replay; five pinned hooks in the
complete stack in both orders; native HUD submission only for a valid human
window; snap-based authored/automatic/replacement EDGE selection with blocked,
absent, coverage, deep, wrong-side and substituted candidates; update-count
deadline and duplicate suppression; confidence hysteresis; native lifecycle
clearing; held keep/released give decisions; receiver press through the full
native pass initializer to its native throw-command store.

**HYPOTHESIS / known gaps.** The 21-update mesh duration feels right in a real
game; the first native glyph reads clearly as the snap cue; the conservative
block target predicts actual engagement; real Shotgun exchange/carry/throw
animations and defense produce the intended football result. No boot or Noah
witness establishes any of those. This does not add arbitrary table capacity,
slot-6 RPO input, empty Shotgun, pitch/contain responsibility rewrites or a
general collision-based unblocked detector. Replay, pause/resume, substitutions,
audibles, no-huddle and split-screen need the witness coverage below. Product
dispatch, BuildPlan, GUI, release closure and the canonical manifest are handed
off through `WIRING.md` because those files are protected.

**Noah's witness list, after protected wiring.** Use an explicit opt-in build
from the pinned base, with the paired MIN `Gun: Doubles Right` recipes above
and the revised owner union. Preserve the build/table receipts with the result.

1. Shotgun Zone read: hold the snap button through the visible window. Confirm
   the QB keeps, the back releases without a second ball, and the cue disappears
   at the decision. Repeat toward both sides and across supported layouts.
2. Shotgun Zone read: release while the cue is live. Confirm a clean handoff and
   the back carrying. Release near either side of the deadline; verify a late
   release does not reverse a committed keep and re-press does not cancel give.
3. CPU Zone read: make the play-side EDGE crash, then stay wide. Confirm sustained
   crash gives a QB keep and sustained width gives the back the ball. Add one
   brief twitch in each direction; observe that it does not flip an established
   read. Record defense/front, direction and what the EDGE actually did.
4. Block or remove the authored defender while a valid play-side DE/OLB rushes
   unblocked. Confirm the replacement is the read. Repeat with automatic EDGE
   selection and with no eligible candidate. Check that a covered OLB, interior
   tackle or opposite-side edge is not silently substituted.
5. Shotgun RPO slant: hold snap and press the authored B receiver during the
   cue. Confirm the slant receives a normal native pass attempt, with no pitch,
   late handoff or stuck QB. Repeat for X, a late press, release without pressing,
   an unready target and CPU crash. Record throw animation, target and result;
   a completed native command alone is not an on-field witness.
6. Observe cue artwork, size and position on the real display, normal/widescreen
   output and supported multiplayer views. It must appear only for the human
   controlling the reading QB, only during the live window, and never over CPU
   plays, replay, menus or unrelated stock plays. Check an unavailable atlas
   does not break the ordinary HUD.
7. Run consecutive snaps, dead balls, possession changes, controller changes,
   substitutions, audibles, no-huddle, pause/resume and replay. Confirm neither
   cue nor queued receiver survives into another play. Repeat with QB spy and
   the full intended patch stack enabled. Confirm all three presets keep the
   feature off and a disabled build retains ordinary stock option behavior.

Witness status remains UNWITNESSED until Noah reports these observations.

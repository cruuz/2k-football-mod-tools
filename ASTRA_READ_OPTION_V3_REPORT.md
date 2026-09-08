PROVED: the paired MIN 155/157 records engage, but v2 runs its read hook after native quarterback movement and allows native human-input priority to bypass the condition callback, so a pending read does not hold the quarterback at the mesh.

# Read option v3, 2026-09-08

**EXPERIMENTAL / UNWITNESSED.** Base: `5704832d83672028ed0966424d5f1ec71f690661`,
branch `astra/r64-read-option-v3`. No game boot, display, audio or network was
used. Noah's September 8 report concerns the previous build; he has not played
these changes. Bounded native instruction execution is evidence of the paths
described here, not a rendered gameplay witness.

## Diagnosis and exact final-book identity

**PROVED:** this is a native timing/control-priority failure. The baseline
reproducer loaded the shipped pack through the real compiler, applied the
position-pool and depth-role writers, resolved the final receipt pairs and
installed their table. Both I Jokers records matched. Native `0x1AF870`
initialized condition argument 13 (`task+0x44 = 0x41500000`) and movement
throttle `task+0x34 = 1.0`. Running the complete condition callback at
`0x1AEF80` called native movement `0x1ADF90` before reaching v2's hook at
`0x1AF191`. On its first sample the read was still pending (`0xFFFFFFFF`,
sample count 1), but the movement call had already received throttle 1.0.
The earlier small fixture entered at the old hook, after that movement.

The native per-frame dispatcher at `0x214FC0` has another relevant branch:
human command/stick priority can win before the task callback. Holding or
releasing snap therefore did not itself create a stationary mesh. V3 has to
protect both this dispatch and the movement inside the callback.

The baseline final resource SHA-256 was
`c180ed3ad11b901eef35d0c275a29cf85cf192938cc242d252fd0a51d1f83962`.
Its two records were:

```text
155 7f641256246e000017fc6c78e43a460cf2c3e7fa0a010000
157 7f641256e46e0000102db027e43a460ceb6d1ac90a010700
```

The v2 counter allowed 21 distinct clock samples, about one third of a second
at 60 Hz. Duplicate-clock suppression already existed. The reproduced
first-sample movement does not require that counter to expire. Native give
and take branches also exist; merely reaching a Boolean branch was not proof
of their approach, handshake or eventual ball transfer. The old back wait
target was additionally three yards *behind the QB*, because its mode is
QB-relative. Its effect on Noah's actual collision/animation sequence remains
**HYPOTHESIS**; no captured machine state from his disc was available.

**PROVED, v3 final resource:**
`5d03682a9444331a611a5ec79aee81ed011ec8d3e5810d01ec6682eecb473dd4`.
The native PLAY loader and the installed lookup/hash instructions execute
against both native relocated buffers, after all final-book writers:

| Play | Descriptor offset | Buffer 0 descriptor | Buffer 1 descriptor | Native name hash | Native QB script hash |
| --- | --- | --- | --- | --- | --- |
| MIN I Jokers 155, SD Zone Read EXPERIMENTAL | `0x6E24` | `0xB7C864` | `0xB8FBF4` | `0xFAE7C3F2` | `0x786CFC17` |
| MIN I Jokers 157, SD RPO EXPERIMENTAL | `0x6EE4` | `0xB7C924` | `0xB8FCB4` | `0xC91A6DEB` | `0x27B02D10` |

Both have book hash `0x5612647F`, back script hash `0x60CEE39A`, back slot 10
and authored EDGE slot 1. Original authoring fixture slots 2/6 remain receipt
history, not the live read targets. RPO uses receiver slot 7; Zone Read has no
receiver. Table SHA-256:
`fb0d3d290771ef6f6653dc4f6edc50a6c25de4a3555a47a11f264066d205064c`.

```text
155 7f641256246e000017fc6c789ae3ce60f2c3e7fa0a010000
157 7f641256e46e0000102db0279ae3ce60eb6d1ac90a010700
```

Local diagnostic inputs/results are in `.scratch/read-option-v3/baseline.log`,
`probe.py`, the saved v2 assembly/template, and `frames.json`. The committed
frame suite regenerates the v3 identity evidence; scratch files are excluded
from the commit/bundle.

## What changed

1. **A real timed hold.** The first live condition sample sets a deadline one
   second later in the existing private RW state. Only distinct game-clock
   values sample input; the deadline, not an update count, ends the window.
   The hook now precedes native movement and clears the QB's interpreted
   throttle and command while pending. Raw held/rising controller state is
   preserved for the read. The native dispatcher routes only the paired,
   live, ball-owning QB condition to its task before human priority can win.
   Other assignments take the displaced retail path.
2. **Approved controls.** Hold snap for the whole window to keep. A release
   during the window is sticky and gives at its end; reholding does not undo
   it. A quick snap tap or no input after snapping defaults to give. Left
   stick cannot cancel the mesh. Input at or after expiry cannot change the
   latched choice. HELP_TEXT, authoring notice and saved pack explain these
   controls in plain words, including Retail/Patch and experimental status.
3. **Back approaches the held QB.** The existing five-node back script keeps
   its wait, fake/release, take and carry branches. Its mode-6 wait target is
   authored half a yard beside the QB with zero additional depth. Retail
   operand decoding quantizes that lateral target to 60 world units, about
   0.66 yard. Native steering confirms it is beside him, not three yards back.
   The five-node QB script and fixed resource spans are retained.
4. **Native give and keep.** Give advances QB node 2 to 4 and back node 1 to 3.
   Native opcode initialization, approach, paired animation selection and
   ownership operations run. Zone Read keep enters native carry at node 3.
   RPO keep uses the native terminal carrying exit at node 2, bypassing its
   pass node; the native interpreter flag becomes `0x800000`. The following
   full frame accepts held snap plus stick with the ball still on the QB.
5. **Native RPO request.** Hold snap and press the named receiver during the
   window. The ready receiver is queued until mesh expiry. Native pass
   initialization consumes it once and immediately runs native `0x19BAE0`,
   before the next human-priority frame can erase the request. The complete
   frame reaches native command `0x42` for the B receiver, with no give branch.
   Native readiness and unsupported snap/receiver-button overlap checks remain.
6. **A cue on the actual EDGE.** Humans and CPUs use the same live unblocked
   EDGE resolver and snap assignment snapshot. The HUD modifies only that
   defender's existing native world-marker queue row, setting the snap-button
   icon, then lets native projection/atlas drawing proceed. The icon is no
   longer anchored at a fixed screen coordinate. It ends with the mesh.
   CPU prediction and three-sample confidence hysteresis are unchanged.

`softdrink_option.2k5book` was re-authored through `option_pack`, compiled and
validated through `apply_pack_to_resource`, then serialized with `save_pack`.
Pack version is `1.0.1`, SHA-256
`53658e2032ee2b5e79d84e84e6c8aa658cbd66c4c26bef461657525ef7e1e48e`.
It still replaces eight plays, including exactly two reads, in a 78,768-byte
MIN resource. Native speed-option recipes remain outside the runtime table.
Gun Zone Read 134 is separately authored through the existing Gun: Doubles
Right recipe and paired after the same final writers; it is not an extra
third shipped-table entry. Table capacity remains two.

## Full-frame proof and its limits

The new standalone `test_nfl2k5_read_option_frames.py` starts each update at
native `0x214FC0`, not inside the added hook. It loads the final PLAY through
the real loader, samples a post-snap QB/back pose at their mesh assignments,
runs native argument decoding/initialization, executes the callback dispatcher
and steering, and follows native interpreter advancement. Each frame has a
100,000-instruction ceiling. The suite contains nine tests and emits 24
case traces when `NFL2K5_READ_OPTION_FRAME_TRACE` is set.

**PROVED:** for both I Jokers plays, samples at 0.05, 0.08, 0.30, 0.55, 0.80
and 1.00 seconds retain QB node 2, back node 1, pending cache `0xFFFFFFFF`,
zero QB throttle and QB ball ownership, even with full stick input. With the
first sample at 0.05, the stored float deadline is `1.0499999523162842`.
This is one second from condition entry, not one second from an independently
measured rendered snap animation.

| Replay | Native result |
| --- | --- |
| Release at 0.08, release at 0.55, or no input; each on 155 and 157 | Give at expiry, QB/back nodes 4/3, cache 1, then actual native ownership transfer to the back |
| Hold through expiry; each on 155 and 157 | Keep, cache 0, native carrying exit; next full frame at 1.10 accepts stick throttle 1 with QB ownership |
| RPO receiver press at 0.45 while holding snap | Pass node 3, back release node 2, target slot 7, native command `0x42`, one consumed target latch |
| Gun Zone Read 134, release/no input and hold | Same timed hold; native give transfer or native keep respectively |
| CPU crash, wide edge and one-sample twitch, both field directions | Sustained crash keeps; wide/twitch gives; both human and CPU resolver identify the same EDGE |
| 15/30/60 Hz, duplicate timestamps, a stalled update crossing expiry | One-second deadline at all rates; duplicate input and late input cannot rewrite the choice |
| Selected EDGE at two projected positions, wrong actor, expired window | Native icon follows the selected row; no icon on the other actor or after expiry |

For give, native `0x1B85A0` supplies the real opcode-to-initializer mapping:
give opcode 19 -> `0x300B00`, take opcode 22 -> `0x2E41F0`. The native
`0x300860`/`0x300810` and `0x2E4030`/`0x2E3DD0` callbacks complete partner
readiness and enter paired handoff selection `0x313A00`. They choose native
animation descriptor `0x531A08`, link QB/back partners and set give/take flags
`0x80`/`0x88`, without a toss or fake transfer. The supplied exchange event
then executes native `0x313520`, detach `0xDDCA0` -> `0x26A4C0`, and attach
`0xDDCD0` -> `0x26A4A0`. Ball owner becomes the back, QB ball pointer becomes
zero, and back ball pointer becomes the ball. Repeating the event cannot
attach twice. Tests never write those outcomes to make the assertions pass.

For pass, `0x19C740`, `0x19BAE0`, `0x1907D0`, `0x19B800` and `0x199260`
execute. This proves native throw-request dispatch; it does not prove the
subsequent rendered throw, flight or catch. For the cue, native `0xFA270`,
the matrix projection path and native atlas drawer `0xF97F0` execute against
an identity camera. Two different world samples produce different projected
heads and four icon vertices each. Production queue population was inspected
at `0x75D90`; it queues visible active players through `0xFA270`.

**Fixture boundaries, not gameplay witnesses:** collision-free actor positions
are sampled inputs. The test moves actors to native approach targets instead
of integrating contact physics. Task allocation uses a preallocated arena;
animation asset loading, transition bookkeeping, model-bone facing, actor
scheduling and the independent defensive prepass are explicit ABI boundaries.
The animation exchange event is supplied, not generated by a loaded asset's
clock. Its trace time near 1.0667 is therefore not a measured handoff duration.
Post-detach/post-attach notifications and handoff statistics at `0xA0910`,
`0xA0870`, `0xA0CC0` are boundaries; ball ownership-list operations themselves
execute. Aim calculation at `0x198C20` supplies an x87 result with native
cleanup. GPU submission is recorded. The fixture does not boot the game or
replay the full snap animation, collisions, asset streaming or control-switch
notifications. A readable animation blend, successful human control transfer
to the back, live camera visibility and actual defense remain **HYPOTHESIS**
until Noah's witness run.

## Reservation, refusal and integration

| Live hook | Retail bytes replaced | Continuation |
| --- | --- | --- |
| Tick `0x1AF009` | `d944241cd81d0ca55000` (10 bytes) | Retail `0x1AF013` or existing result path `0x1AF210` |
| Frame priority `0x21516A` | `8b44243033f6` (6 bytes) | Retail `0x215170` or native task branch `0x215367` |
| HUD `0x646A1` | `e80a5a0900` (5 bytes) | `0x646A6`, native HUD still called |
| Pass initializer `0x19C849` | `c70660bb1900` (6 bytes) | `0x19C84F` |
| Snap `0xB6FBD` | `8935c802e600` (6 bytes) | `0xB6FC3` |
| Reset `0x1AD9C3` | `b95a000000` (5 bytes) | `0x1AD9C8` |

**PROVED:** generated instructions occupy exactly 2,048 RX bytes. The existing
reservation remains **2,048 RX / 256 RW / 88 RO**, alignment 16; shortfall is
**zero**. RW uses 48 bytes of live state and eleven 12-byte snapshot records
beginning at offset 64, ending at 196. RO remains the 64-byte table plus the
existing 24-byte constant layout; four obsolete fixed-HUD floats are unused
and the final two CPU policy floats remain active. No runtime data is placed
in `.text`, no unreserved cave is claimed, and the live request union already
includes this owner. The budget plan passes all 44 requests.

Pinned dependency guards add the frame-priority and native HUD-loop slices;
existing guards were not relaxed. Status/apply still refuse changed hooks,
native dependencies, code, table, RW initialization and incomplete/mixed owner
installations before mutation, repin section digests and replay byte-exactly.
Existing installed v1/v2 bytes require a rebuild from the supported base.
The two XBE gates change only their expected model version to 3. Pairwise
test labels retain `read_option_v2`, but import the current live v3 module and
unchanged reservation. They exercise both orders and exact replay.

All protected implementation files remain unchanged. `WIRING.md` gives the
required protected manifest regeneration, the stale extra wizard geometry
label replacement, and the existing capability-object merge. It also records
the dispatcher tuple/kwargs, all four status dictionaries, BuildPlan and all
three presets off, PATCHES/NEEDS_IMAGE, 40-character Build caption, allowlist
paths and runtime import closure. Existing panels already import HELP_TEXT.
The capability remains `runtime.status=not-tested`, opt-in and experimental.

## Commands and results

Every suite was launched standalone with `python3 tests/mod_editor/<file>`
under `/usr/bin/time -v`. Qt used `QT_QPA_PLATFORM=offscreen`. Oracle and owner
manifest/gate runs used
`NFL2K5_CAVE_MANIFEST=.scratch/read-option-v3/manifest.json`. The frame run also
used `NFL2K5_READ_OPTION_FRAME_TRACE=.scratch/read-option-v3/frames.json`.
The pairing build run explicitly enabled `NFL2K5_PAIRING_REAL_BUILD=1` and
passed `-v` so its exact skip reasons were recorded.

| Standalone file | Result | Test seconds |
| --- | --- | --- |
| `test_nfl2k5_read_option_frames.py` | 9 PASS | 12.133 |
| `test_nfl2k5_read_option_unicorn.py` | 14 PASS | 18.000 |
| `test_nfl2k5_read_option_controls.py` | 15 PASS | 15.641 |
| `test_nfl2k5_read_option_runtime.py` | 10 PASS | 6.898 |
| `test_nfl2k5_read_option_screen_hooks_compose.py` | 9 PASS | 58.518 |
| `test_nfl2k5_read_option.py` | 15 PASS | 9.800 |
| `test_nfl2k5_read_option_qt.py` | 7 PASS | 1.069 |
| `test_nfl2k5_play_intents.py` | 18 PASS | 28.541 |
| `test_nfl2k5_play_intents_build.py -v` | 3 PASS, 2 SKIP (disk floor) | 19.020 |
| `test_nfl2k5_playbook_pack.py` | 36 PASS, 1 SKIP (private uniform catalog absent) | 1.248 |
| `test_nfl2k5_owner_pairwise_composition.py` | 101 PASS | 584.339 |
| `test_nfl2k5_cave_oracle.py` | 28 PASS | 199.144 |
| `test_nfl2k5_music_playlist_manifest.py` | 2 PASS | 3.859 |
| `test_nfl2k5_screen_hooks_manifest.py` | 3 PASS | 3.865 |
| `test_nfl2k5_my_career_manifest.py` | 3 PASS | 6.038 |
| `test_nfl2k5_guardian_overlay.py` | 6 PASS | 6.913 |
| `test_nfl2k5_defensive_try_manifest.py` | 3 PASS | 4.142 |
| `test_xbe_patch_memory_writes.py` | 91 PASS | 793.977 |
| `test_xbe_patch_cave_references.py` | 103 PASS | 917.349 |

Total across these 19 standalone suites: **476 PASS, 3 SKIP, zero failures**
(479 tests). Both XBE gates cover normal/reverse and scale-out owner orders.

The defensive-try manifest fixture had ignored `NFL2K5_CAVE_MANIFEST` and
loaded the protected stale artifact. Its only change is to honor that same
environment override for both reads. Without an override its strict default
and unrelated-source drift refusal remain unchanged. Final table results above
include the corrected run. No source fingerprint was recertified by hand.

Additional checks: `python3 tools/nfl2k5_read_option_runtime_assemble.py --check`
passes; `python3 tools/nfl2k5_xbe_space.py plan --requests
tests/fixtures/nfl2k5_allocator_beta62_requests.json` passes. The in-memory
replacement of the existing capability passes the full 116-entry schema;
all nine distinct evidence/backend paths and both `python3 -m` commands for
the changed capability resolve. Full-registry `check_files=True` has the
same pre-existing failure before and after replacement: missing
`docs/research/apf_audio.md` in the first unrelated entry. The report does not
claim that whole-registry file gate passed. `git diff --check` and
`git diff --cached --check` pass. The final audit checks the exact 18-path
change set, Python syntax, all 144 current source fingerprints, and the final
capability's paths and command resolution; all pass.

The scratch manifest was generated by this exact successful command:

```sh
python3 tools/nfl2k5_cave_oracle.py manifest \
  '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --xiso '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso' \
  --work-dir /tmp --json .scratch/read-option-v3/manifest.json
```

It streamed disposable real-disc builds in `TemporaryDirectory`, deleted the
first image before the second probe, then removed both on exit. It recorded
10,778 reservations, 125 XBE writer calls and 144 source fingerprints; section
digests verified. Wall time was 314.66 seconds, peak RSS 790,088 KiB. Preset
XBE SHA-256: `bad3c5ffdd0c2d882086a88ef4ebaf8547cc746abbc6210f112164923dbeceab`.
Stack XBE SHA-256: `4e5f6ea05069adfaca972e8bd748519d1111ce25a82c80f8138340ca00e9e528`.
The read owner in this manifest probe has an empty, dormant intent table.
Active paired-play proof comes from the final-resource and frame suites, not
from a claimed paired-play disc acceptance.

The two optional paired-disc acceptances requested 113,112,999,936 free bytes
to preserve 100 GB across the writer's two-image peak. They found
108,216,913,920 and 108,216,668,160 respectively and correctly skipped. No
space guard was lowered. Those full paired read-only and read-plus-spy disc
acceptances remain unperformed. The bounded real-resource final pairing and
verification test did pass. No full disc/archive was loaded into RAM.
The largest measured process was the oracle unittest suite at 909,320 KiB
RSS (about 888 MiB), below the 2 GB limit. Final scratch contents total about
3.0 MiB, with no XBE, disc or archive pack. The owned `nfl2k5-oracle-*` and
`read-option-pairing-*` temporary directories are absent. The final root-space
audit reports 108,182,044,672 free bytes; observed disposable-build free-space
samples stayed above 100 GB. All acceptance images were deleted before this
report was finalized.

## Noah's exact witness list

Rebuild from the supported base after the WIRING integration and protected
manifest regeneration. Select the option pack and explicit Read option mesh
controls opt-in. Record build/pack identity and confirm the final summary says
two paired read plays. Keep the feature EXPERIMENTAL / UNWITNESSED until these
checks are recorded:

1. MIN, I Jokers, **SD Zone Read EXPERIMENTAL (155)**: snap with a quick tap
   and release; then separately hold about half a second and release; then
   snap and supply no further input. In every case the QB must hold the mesh
   for about one second, the back must approach beside him, a hand-to-hand
   exchange must occur, the back must become the controlled ball carrier and
   the QB must complete his fake without taking off at the snap.
2. On 155, hold snap continuously through the full window. The QB must pull
   the ball, the back must fake/release, and left stick must control the QB
   afterward. Repeat release and keep with full forward/back/side stick held
   from the snap; it must not preempt the mesh. Releasing then reholding
   during the window must still give.
3. MIN, I Jokers, **SD RPO EXPERIMENTAL (157)**: repeat all three give cases
   and held keep. Hold snap and press the named receiver (B in the tested
   layout) around half a second into the mesh. Confirm the actual native
   throw animation, ball flight and receiver outcome, with no give/double
   action or QB auto-run. Also check an unavailable receiver and a button
   pressed after expiry. Record controller layout and game mode.
4. Author/install **SD Gun Zone Read (134), Gun: Doubles Right** through the
   supported recipe and rebuild its final paired table. Repeat quick-release
   give, mid-window release, no input, held keep and stick interference.
   Watch shotgun snap-to-mesh timing, collision, approach and exchange.
5. On both field directions and supported camera/aspect settings, confirm the
   snap-button cue stays on the actual unblocked play-side EDGE during the
   human window, follows his movement and disappears on commitment. Test a
   blocked/replaced authored defender, substitutions and an off-camera EDGE.
   The marker requires a visible queued actor and ready native icon atlas;
   there is no fixed-screen fallback.
6. CPU-run reads against an EDGE that crashes, stays wide and briefly twitches:
   verify the same defender is read, sustained crash produces keep, wide
   produces give, and a brief twitch does not flip the choice. Verify real
   blocks leave that defender readable; the runtime does not rewrite defense.
7. Repeat consecutive downs, hurry-up, new play, audible, timeout, pause/resume,
   possession change, fumble/tackle during the window and human/CPU takeover.
   There must be no stale cue, target, frozen QB, duplicate transfer or input
   carried into an unrelated play. Repeat with QB spy and screen hooks enabled.
8. Check untagged native speed options still pitch/keep normally. Record any
   failure with play index, field direction, controller layout, input timing,
   defender, camera and build identity, including whether the ball ever left
   the QB's hand. Visual mesh quality and the feel of the one-second tuning
   require Noah's assessment.

## Delivery

Normal explicit-path staging succeeded. Delivery uses `git add <18 explicit
paths>` followed by `git commit -- <the same 18 paths>` on this worktree branch;
no bundle fallback is needed when the commit succeeds. `ASTRA_BRIEF.md`,
`.scratch/`, generated XBE/disc data and protected files are excluded. No push
is authorized or performed. The final commit identity is reported separately
so this report does not attempt to embed its own commit hash.

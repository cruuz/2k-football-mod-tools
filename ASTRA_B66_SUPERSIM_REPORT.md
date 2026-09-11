# Beta 66 job A: full live MyCareer Supersim

Branch: `astra/b66-supersim`. Implementation commit: `830f23e4`. Request: Noah, "i want full supersim". User report:
andrethealchemist, Discord 2026-09-10, "My career Super Sim hasn't worked for me."

## Delivered behavior

The MyCareer owner now installs the Stage 2 live scheduler and Stage 3 native UI:
**up to eight complete engine updates per presented frame**, one hardware poll,
native CPU ownership while waiting, native presentation skips, muted draining
audio, a score/quarter/clock/last-play ticker, and a settled pre-snap handoff with
the native initial play clock. This is an eight-update scheduling cap, not a
measured eightfold console speedup. Every in-game behavior is **UNWITNESSED**.

Apartment > Settings offers **Supersim: Off / Skip presentation / Fast forward**.
Fast forward is the default for newly created enabled careers. Historical
zero-filled footers retain Skip presentation. B cancels to Off/normal speed.
The Apartment's **Sim to next appearance** action launches the next native
scheduled fixture and arms the wait, including its first appearance.

MyCareer remains EXPERIMENTAL and an explicit opt-in in presets. This branch
changes the default within a newly enabled career only. The Studio Settings
panel, registry text, changelog and release cave manifest are protected by
`ASTRA_CONTEXT.md`. Their exact integration is supplied in `WIRING.md`; those
protected files have not been silently edited. A scratch projection of the
panel passed offscreen worker, signed export and read-back checks.

**Final bounded acceptance passed: all 29 live tests, both XBE gates, the cave
oracle and the 335-case owner pairwise matrix.** Derived results and source
hashes are recorded in `tools/mycareer_mode/supersim_b66_receipt.json`.

## Research closure in the requested order

| Research | Status and bounded evidence | Installed behavior / limits |
| --- | --- | --- |
| Complete outer camera/clip/huddle update | PROVED: native 64CD0 executes all 27 football phases and A5620 without the former 5F7BA fault. A55A0 constructs the native camera objects; 2C04A performs native post-device viewport initialization from declared 640x480 hardware dimensions. Scene/ball pools, full 1DF860 clip/phase constructors, retail 25/62-bone hierarchies and SKEL vectors execute in the correct order. | Skeleton assets must precede 1DF860's hand-reference sampling. The reversed order produced NaN center offsets and invalid plays; it is corrected. The fixture declares model handles, initial looping clips, collision spheres and empty CPU play-call SCNE descriptors, relocated through 2F140. It is not a full stadium asset loader. |
| Uninterrupted CPU series | PROVED: the final installed N=8 loop completed 3 native plays in 3,376 updates / 422 polls / 422 counted presents; 23,223 match RNG draws. All 27 phases complete on every update, with three separate snap-to-dead-ball sequences. No football phase is stubbed. | Native main-frame 747CC calls the scheduler, which repeats complete manager event 6 through 6E6A0 and 64CD0. Present 27CA0 is counted at the original main-frame call site. No abstract stat import/finalizer is installed. |
| Challenge, initial/OT toss, tips, disconnect, pause | PROVED installed guards: camera 26, phase E602B4=0, BB6CB4 tips, paused/ended game, invalid/other manager, disconnected controller and B each suppress acceleration. The 14E070 prologue clears the fast/audio flag before its blocking native loop. | All retain native prompts at 1x. No speculative challenge or toss answer is synthesized. B or disconnect sets Off and cancels the wait. A modal can take ordinary time until answered. |
| Audio submission/queue | PROVED: 3DA90 source admission, 3E7C0's 64-source pool, the complete 3DBC0 worker and 3CF20 retirement execute. Both gain banks are invalidated on mute/unmute; the device sees -10000 gain while fast. Eight ticks against a full pool reject extra admission without growth. Advancing the device cursor retires all 64 sources, invokes each cleanup callback once and makes slots reusable. | The worker remains live; it is not skipped. Hook 3E94D wraps it, temporarily sets master gain A70830 to zero, then restores it. Device cursors and final device calls are declared ABI inputs/leaves. This proves the exercised native pool, not every possible console driver or unseen upstream queue. |
| Input/RNG cadence | PROVED: one native 74730 input phase per presented frame and one poll at 710E0. Extra updates explicitly consume the baseline 48B50(E5FCA0) draw that the omitted input phases would have consumed. Fixed eight-update traces grouped 1/2/4/8 have equal match RNG/phase/world-transform hashes, with 8/4/2/1 polls and presents. | N=8 is the largest tested candidate; N=2 and N=4 pass the bounded cadence comparison. N=8 additionally runs the extended series. No claim beyond eight or of console wall-clock performance. |
| Settled appearance | PROVED: actual CB alignment returns after 418 updates, native K after 4, P after 5, and a native injury replacement QB after 379. Every actor is native-ready at task phase 13, full play clock 40, no queued event 28, and the selected entity receives controller zero. | Both native CPU snap decision entries, 2D37E0 and 2ED020, are held during the wait. Global phase 13 alone was insufficient: the first actor can enter it before the other 21 finish aligning. The installed predicate requires all 22 active actors, native 1FF940 readiness, task phase 13, no pending snap event and no post-request QB task. |
| Position groups / substitutions / special teams | PROVED: native selected personnel cover all codes 0 through 16 across scrimmage, kickoff and punt lineups. A native injury replaces the chosen QB record before a new animated handoff. Already settled native lineups admit the selected identity with zero extra updates before its next presented frame. | Scenario identities are selected from actual native personnel, not injected into the lineup. This matrix reuses settled native lineups; it is not 17 independently played careers. K/P membership comes from the native personnel picker. The P lineup uses declared native phase 1 (free punt) with a fourth-down context; the injury event is also a declared input. Ordinary fourth-down go-for-it choice and collision injury probability are not inferred. |
| Alignment drawing / ticker | PROVED: the native 6E6E0 render dispatcher returns, visits and registers all 22 settled players, and reaches GPU command submission. Native player-marker FONT setup and glyph paths execute. The ticker separately executes 150620 for all 13 log kinds, native font metrics, bounded line wrapping and glyph generation with a buffer canary. | GPU command submission is counted; there is no rasterizer/display. Optional preplay-help captions (Hot Route / LB Shift etc.) have an absent B9CCC0 font binding in this scene and are explicitly omitted. The full stadium, all optional overlays and actual pixels remain UNWITNESSED. |

The native ball phase E602C0 is an enum: initial setup is 0, a dead-ball restart
is 2, and E9320 records a snap with 1. The first replacement assertion wrongly
required zero; native injury reset legitimately leaves 2. The corrected fixture
allows only 0 or 2 at handoff and retains all readiness/event assertions.

The first complete live-file run passed the native series and settled CB
predicate but failed its controller assertion. That assertion incorrectly read
BD8210, the first controller object in the native pool, for a CB using a later
object. The native binder uses `[actor+0xC]`, then stores the actor in port zero's
BE4D60 mapping. The corrected proof checks both those actual links, including
the all-position matrix. No runtime change was needed for this fixture error.

## Engine policy and outcome honesty

The scheduler keeps the existing raw frame delta and repeats full engine
updates. Rendering events and main-frame input polling remain outside the
inner loop. A return is checked after each complete update and before the
next one. A boundary already settled on entry gets a zero-update presented
handoff. Unexpected present personnel during a live play drops acceleration to
1x while retaining the wait for a future settled boundary. Unknown manager and
modal paths also run at 1x.

The fixed-input cadence equality is deliberately narrow. The native match RNG
at E5FCA0 executes; the inherited general entropy service at 48BC0 still returns
zero in the fixture. Real input timing, general entropy, asynchronous audio and
wall-clock services can change outcomes. Fast forward does **not** promise the
same score or plays as a real 1x run. A zero-update handoff frame still performs
its normal input phase and baseline RNG draw; that is another deliberate
difference from continuous 1x simulation. The first measured audio capacity limit is
the native 64-source pool; admission rejects further sources rather than
overflowing it. Console throughput and responsiveness are Noah witness items. An additional
research check at the retail slow-frame value 1/15 second returned the actual
kicker after one inner update; twelve subsequent neutral-input updates stayed
pre-snap at normal speed. This is supplementary bounded evidence, not a
full-drive acceptance at every possible frame delta.

## PROVED / HYPOTHESIS boundary

| Statement | Classification |
| --- | --- |
| Complete native updates, automatic CPU snaps/plays in the bounded scene, N=8 cadence, installed prompt guards, native audio pool retirement, settled actual personnel and native ticker glyph submission | PROVED, within each fixture's declared scene/device inputs and final acceptance below. |
| Eightfold effective speed on an Xbox/emulator, smooth ticker pixels, all stadium/model assets, hardware audio behavior and real controller feel | HYPOTHESIS / UNWITNESSED until Noah's witness. No emulator was run. |
| Identical final score, injuries, play choices and timing to an interactive 1x run | Not promised. Only the fixed-input bounded match-RNG/transform equivalence is proved. |
| Every possible driver queue, every formation or arbitrary modded prompt/scene behaves identically | HYPOTHESIS. Pinned native prerequisite checks and normal-speed modal/manager guards bound installation; hardware and content breadth remain witness work. |
| A full live game can be restored from the old abstract simulator or from a native abandon/restart save route | Not implemented or claimed. The existing abstract resume refusal remains. |

## Ownership and save compatibility

Only MyCareer's RX request grows: **16,384 -> 20,480 bytes**. RW stays **8,192**
(two named 4,096-byte allocations). Current content is **17,919 bytes**, machine
code **12,736 bytes**, with **2,544 RX bytes spare** before the format tag. The
allocator chooses the owner's placement; the budget proof confirms all peer
allocations and total file size stay unchanged. The owner is never expanded by
moving another owner. `tools/mycareer_mode/supersim_budget.json` is regenerated;
earlier M3/settings budget receipts remain historical.

Footer byte 82 mask 0x0A encodes Off=0x02, Skip=0x00, Fast=0x08. Both Supersim
bits set is rejected. FPF bit 0 and star-off bit 2 survive. All 12 valid settings
combinations match the native encoder and host codec; invalid reserved patterns
refuse. Export validates the source signature, changes the footer/checksum,
writes a separate signed SaveContainer and verifies read-back. Transient wait
and fast flags are cleared on native load; they are not serialized.

Changed native prerequisites reject before any code installation. Full-stack
recognition validates the already installed dynamic-kickoff 1FF940 wrapper and
defensive-try formatter branch before normalizing their exact shared bytes.
It does not mask arbitrary foreign edits. Retail and installed apply/status
are idempotent in the native writer tests.

`mod_editor/core/nfl2k5_supersim.py` now reports RUNTIME_READY=True, LIVE_STAGE=3,
LIVE_UPDATES_PER_FRAME=8 and an explicit unwitnessed status. Its old abstract
simulator helper still refuses live resume; this scheduler never invokes it.

## Validation

All commands use the pinned private USA retail files read-only. Retail/Unicorn
absence is an explicit SkipTest; Capstone/FONT/PLAY/SKEL absence has precise
fixture skips. No retail bytes are committed, no emulator or display is run,
and no audio is played. `QT_QPA_PLATFORM=offscreen` is used for Qt.

Final source checks:

| Command (repository root) | Result |
| --- | --- |
| `python3 tools/mycareer_mode/build_runtime.py --check` | PASS, MyCareer mode runtime verified. |
| `python3 tools/mycareer_mode/measure_m3.py --output tools/mycareer_mode/supersim_budget.json` | PASS, 20,480 RX / 8,192 RW, 2,544 RX spare, peers unchanged. |
| `python3 tools/mycareer_mode/measure_mode4.py --output .scratch/b66-mode4-budget-final.json` | PASS. |
| `PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_my_career_m3_budget.py` | 5 tests, 3.960s, OK. |
| `PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_my_career_mode4.py` | 8 tests, 441.781s, OK. |
| `PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_my_career_settings.py` | 9 tests, 28.484s, OK, including native Fast forward save/cold relocation and transient reset. |
| `PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_supersim.py` | 12 tests, 8.063s, OK. |
| `PYTHONPATH=. python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 115 tests, 1314.832s, OK. |
| `NFL2K5_CAVE_MANIFEST=.scratch/b66-manifest.json PYTHONPATH=. python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 127 tests, 1497.919s, OK. |
| `NFL2K5_CAVE_MANIFEST=.scratch/b66-manifest.json PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | 29 tests, 315.056s, OK. |
| `NFL2K5_CAVE_MANIFEST=.scratch/b66-manifest.json PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_my_career_manifest.py` | 3 tests, 6.398s, OK. |
| `PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py` | 335 tests, 1850.057s, OK. |
| `PYTHONPATH=. python3 -u tests/mod_editor/test_nfl2k5_supersim_live.py -v` | 29 tests, 3240.525s, OK. |
| `python3 packaging/repin.py --apply` | Pins refreshed; last check applied 0 updates. |
| `git diff --check` | PASS. |

The full live-file receipt includes the uninterrupted series, cadence hashes,
all-position admissions, animated handoffs, native substitution and render
counts. No gate or test was patched to bypass a failure. The scratch manifest bootstrap only
allows this owner's authorized 16,384 -> 20,480 growth, checks peer overlap,
and then derives final reservations from actual observed writer output.

The broad MyCareer subject sweep executed every standalone MyCareer test file
and dynamic kickoff (30 files, 170 tests). Its only two initial failures were the protected
16 KiB manifest expectation and the old mode4 code-size assertion. The updated
mode4 file passed all 8 tests; the scratch-manifest owner file passed all 3.
The table above records the final reruns for those files and the XBE gates.

The scratch manifest was generated by
`python3 tools/mycareer_mode/refresh_settings_manifest.py --output .scratch/b66-manifest.json`.
It contains 12,731 spans and 125 observed forward steps, SHA-256
`0bbe6d7b1e619a90c1508d603c7965cf3815eb370f2b0daed2e9da319354e174`.
It retains historical resource-build reservations and clearly labels itself
an XBE projection. It is **not** a beta-66 disc/release build receipt. Claude
must regenerate the protected release manifest from the integrated build.

## Noah's exact witness script

Use a clean beta-66 build with MyCareer explicitly enabled. Record the build
hash, platform, career position, quarter/clock, last ticker play and controller
behavior for each case. Keep a save copy before starting.

1. Create a new QB career. Open Apartment > Settings and confirm Supersim:
   Fast forward. Cycle Off, Skip presentation, Fast forward and verify the
   displayed choice after leaving/reopening Settings. Start a game. Play the
   opening offensive appearance normally. When the defense takes the field,
   verify both teams play CPU football, the ticker keeps changing, eligible
   replays/huddles skip and fast-forward audio is muted. Note real seconds and
   game-clock seconds; do not assume the console achieves an eightfold speedup.
2. On the QB's next offensive appearance, verify the formation is settled,
   MyPlayer is selected, the play clock starts full (normally 40), and the ball
   is still unsnapped. Wait briefly, then snap manually. Verify stick/buttons
   work, sound resumes, and no CPU snap was queued before control returned.
3. Create/load a CB career. Let the offense's drive fast forward. Verify a
   moving ticker, then a settled defensive appearance and full play clock
   before the offense snaps. Move the CB and verify player lock remains correct.
   Repeat with a substitution or injury replacement when available.
4. Create/load K and P careers. Verify kickoff, PAT/field-goal and punt personnel
   use actual membership: wait when not selected, and return before the kick
   approach or snap when selected. Test a normal offense/defense player on a
   special-teams unit as well. Verify kick controls and audio return normally.
5. During an absent-unit fast-forward segment, press B. Verify immediate normal
   speed, restored sound, no frozen screen, and the saved Supersim choice Off.
   Re-enable Fast forward in Settings and try the Apartment's Sim to next
   appearance action on the next scheduled game.
6. Across halftime, verify native presentation/prompts remain responsive and
   second-half possession/kickoff are correct. In a two-minute/no-huddle drive,
   verify timeouts and the game clock work and the return never follows a snap.
   If a challenge, tip/lesson, pause or controller prompt appears, verify normal
   speed and a usable native prompt. Disconnect/reconnect the controller once.
7. Reach overtime with a tied game. Verify the OT toss runs at normal speed,
   its native choice can be answered, then fast forward resumes for the absent
   unit and returns at the next settled appearance. Verify score/quarter/clock
   and the ticker's last play remain consistent with the native game.
8. During a game, use the game's supported save/exit route and reload the saved
   career. Verify the Supersim choice survives, transient fast-forward/wait UI
   is not stuck, and the next eligible absent segment and appearance work.
   Do not interpret a native abandon/restart route as live-game state restore.
   Also export a different Supersim choice through Studio Settings to a signed
   copy, load it, and confirm the original save was not changed.

Record any unresponsive prompt, stale ticker, audible backlog, wrong player,
short clock, early/late return, or snap before input is available. These are
release witness failures, not acceptable interpretations of the bounded proof.

## Integration / commit

Protected changes are concrete in `WIRING.md`. No push or disc build is made.
This job is committed with explicit paths on `astra/b66-supersim`. Claude must
apply the protected Studio, registry and changelog wiring and regenerate the
release manifest before publishing beta 66. Noah's in-game witness remains open.

The final Studio export projection passed all three saved choices, worker
disablement, invalid-save handling, signed copy read-back and original-source
preservation. Its command was `QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3
.scratch/b66_panel_verify.py`; the protected panel hash stayed unchanged.

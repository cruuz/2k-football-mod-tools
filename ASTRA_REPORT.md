# Beta 65 A — Accelerated Clock

Branch: `astra/b65-accel-clock`. Research checkpoint: `088bca77`. Implementation checkpoint: `6f8616d0`.
Verifier/ownership hardening: `4996765f`.

The build-time XBE writer and bounded native proofs are delivered. After a huddled offensive play call,
the patch writes the selected minimum to the native play timer and subtracts the actual difference from
a running native game timer. Human and CPU completion use the same hook. The default is **Off / 20 s**;
all five choices, 25 / 20 / 15 / 10 / 5, execute successfully. The seven specifically requested cases are
separate passing unittests.

**This branch ships the build-time backend, not an in-game Game Settings row.** Studio/BuildPlan,
registry, packaging and production-manifest integration are assigned to Claude by `ASTRA_CONTEXT.md` and
specified in the fresh `WIRING.md`. The candidate registry row, changelog bullet and getting-started
paragraph are written. Preset classification is **ADVANCED, opt-in**, with Off in every preset. The brief
allows Advanced On/20 after the seven proofs, but I have retained Off pending Noah's game witness.

No emulator, display, network, audio, push or disc build was used. Retail was opened read-only. No retail
XBE, PLAY resource or executable output is committed. Private input is the pinned USA `default.xbe`, SHA-256
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.

## PROVED versus HYPOTHESIS / UNWITNESSED

| Claim | Evidence and limit |
| --- | --- |
| PROVED: native clock objects, float seconds, stop/pause/direction flags | Retail disassembly plus executed native timer tick, stop and resume. |
| PROVED: 40 s normal reset and 25 s stoppage reset | Executed `B6E30` and `B6DE0`; no replacement of the native reset amount. |
| PROVED: incomplete-pass clock stop | Actual ball-ground/incompletion/stop-request chain executed through `AF4F0`; scene leaves supplied. |
| PROVED: offense play completion and shared CPU/human hook | Executed accepted human selection continuation and CPU selected-play completion; both enter `B86E0`. |
| PROVED: distinct both-ready transition and successful-snap signal | Native ready predicates and snap through its play-clock stop execute. |
| PROVED: Off wrapper equivalence | Engine store sequence, resulting bytes, GPRs, flags, SIMD and FP controls match retail for completion, both callers and no-huddle. Dead stack return addresses differ by construction. |
| PROVED: running 600/40 ->580/20; stopped 600/40 ->600/20 | Actual compiled hook executed against synthetic native timer/team objects. |
| PROVED: 119 s bypass and 15 s half-ending snap bypass | Separate mandatory tests; 0/15/119/120 also tested in periods 2, 4, 5 and 6. |
| PROVED: quick-snap/no-huddle bypass | Actual previous-play installation through `A24B0`, then a later completion, leaves both timers unchanged. |
| PROVED: one acceleration per snap | Repeated completion after native 25/40 resets and play-clock stops cannot rearm the latch; an actual successful snap can. A rejected snap cannot. |
| PROVED: scorebug input is exactly the chosen integer | Patched timer read by native `FBB10` returns 20; a subsequent normal tick counts down normally. Rendering remains UNWITNESSED. |
| PROVED: native delay-of-game still owns zero | Completion does not reach its penalty call; after 20 seconds of native ticking, `B2580` reaches `B23F0`. |
| PROVED: quarter clamp and native warning/end dispatch | Q1/Q3 15 s clamps to 0 without modifying period, then reaches `A2970`. A 139 ->119 runoff reaches the native warning entry. |
| PROVED: kickoff/quarter-start/special-play exclusions | Native phase and period-reset inputs execute; selected PLAY family and knee/spike flags are pinned by retail playbook census. |
| PROVED: complete written-byte verification and ownership | All hooks, relocations, code padding, RO words, zero offline RW state and allocator seals are reparsed; forged code/options/neighboring owner refuse. |
| PROVED: kick-rules composition | Its independently verified PAT audible call at `A24E7` is the sole neighbor normalized in the no-huddle function hash; both orders and native bypass tested. |
| HYPOTHESIS / UNWITNESSED: every real stoppage presentation follows the supplied timer state | The patch reads native flags, rather than inferring each cause from a guessed descriptor. Timeout/review/injury/penalty scene sequences have not been played end-to-end. |
| HYPOTHESIS / UNWITNESSED: visible huddle-break timing, scorebug jump and warning presentation | The selector/completion instructions and getter are proved; the full rendered game is not. |
| HYPOTHESIS / UNWITNESSED: realistic play counts at 15-minute quarters | CPU and human clock arithmetic are proved; full-game cadence and counts must be measured. |
| NOT DELIVERED HERE: rendered Studio controls and in-game settings row | Exact Studio handoff is in `WIRING.md`; optional in-game row stage was not attempted. |

## Implementation and address ledger

`mod_editor/core/nfl2k5_accelerated_clock.py` provides `status()`, `apply()`, `verify()`, `describe()`,
`encode_options()`, allocation requests and reservations. A second application is byte-identical and
reports zero changed bytes; omitted settings preserve a verified installed choice. Changing that choice
requires a rebuild from the base. The standalone default explicitly installs Off/20. Studio integration
skips the writer entirely when Off; that product path still requires Claude's wiring tests.

`tools/nfl2k5_accelerated_clock.S` is the source for 487 instruction bytes in the generated
`nfl2k5_accelerated_clock_code.py`. The GNU assembler tool is used only in development. Runtime code saves
GPRs/EFLAGS, XMM0..3 and MXCSR, and does not touch the x87 stack. It changes only the two native timer
seconds fields and its own latch. The disabled wrappers do not change the latch. Native timer flags,
quarter length, play-clock reset constant and period remain under the game and their existing owners.

The complete gate union places the following requests at these incidental addresses. The writer resolves
every address from the sealed allocation directory; these values are not hard-coded in the writer:

| Owned kind | VA in complete gate union | Bytes | Meaning |
| --- | --- | ---: | --- |
| RX code | `0x014DA540` | 1,024 | 487 instruction bytes, remaining bytes pinned `CC` padding |
| RW data | `0x014F2000` | 4 | Per-snap latch; zero in the on-disk XBE |
| RO options | `0x01507000` | 8 | Little-endian uint32 enabled at +0, minimum seconds at +4 |

Four pattern-checked live sites, all with no external retail target in the overwritten interior:

| Hook VA | Size | Native meaning / continuation |
| --- | ---: | --- |
| `0xB86E0` | 5 | Offensive completion calls the wrapper. Wrapper first executes native `0xA1CD0 ->0xB7200`; returns to `0xB86E5`. |
| `0xB6EB0` | 6 | Play-clock stop entry. Clears latch only for return `0xB7015` from successful snap call `0xB7010`; resumes `0xB6EB6 ->0xAF4F0`. |
| `0xB6DC0` | 5 | Period reset suppresses first snap; displaced quarter-length load, resumes `0xB6DC5`. |
| `0xA24B0` | 7 | No-huddle/previous-play entry suppresses this snap; displaced push/load, resumes `0xA24B7`. |

Every native routine body pinned by the writer, with byte lengths, is listed here. Only the four exact
hooks and the fully verified kick-rules neighbor are normalized before hashing:

| VA | Bytes | Dependency |
| --- | ---: | --- |
| `0xB8650` | 305 | Offense completion and start of lineup |
| `0xB6EB0` | 11 | Native play-clock stop |
| `0xB6DC0` | 29 | Period timer reset |
| `0xA24B0` | 134 | No-huddle/previous play |
| `0xB7200` | 41 | Conditional game-clock restart |
| `0xAF490` | 84 | Timer tick |
| `0xAF4F0` | 55 | Stop/start entry region |
| `0x205F80` | 85 | Half-remaining convention, including OT |
| `0xB2580` | 70 | Delay-of-game guard |
| `0x158C90` | 70 | Both-teams-ready transition |
| `0x1580F0` | 31 | Team-ready predicate |
| `0xFBB10` | 90 | Play-clock scorebug getter |

Additional native addresses used directly by the logic or its proof:

| VA / object offset | Meaning |
| --- | --- |
| `0xE6028C`, `0xE60294`; timer +`0x10`, +`0x14`, +`0x18` | Game/play timer pointers; float seconds, rate, flags. Stop/pause mask 6; direction bit 8. |
| `0xE602B0`, `0xE602AC` | Float period length and native normal reset 40. |
| `0xE602C4`, `0xE602B4`, `0xE602B8`, `0xE602C0` | Period, phase, play state, ball state. |
| `0xE60280`, `0xE60284`, `0xE60288` | Offense, defense, prior possession. |
| team +`0xC`, selection +`0xC`, PLAY +4 | Current selected PLAY and header flags. Mask `0x4001C0` excludes game runoff on specials/knee/spike. |
| team +`0x30`, +`0x38`; selection +`0x24` | Controller pointers and native selection/ready flags used by the bounded callers. |
| `0xE602FC` | Saved restart permission `0x400`; warning-seen `0x20`; native temporary hold/resume flags. |
| `0x153170`, `0xA2B60`, `0x9F360` | CPU selected-play completion to shared completion. |
| `0x153B62`, `0x153B64`, `0xA2B70` | Accepted human selection continuation, its call, bounded return boundary. |
| `0x189020`, `0x1889C0`, `0x1889E0`, `0x188A10`, `0x188A30` | Selection/complete flag producers and predicates. |
| `0x158CC1`, `0xB87D0` | Ready state store; audible can return 13 ->12, which is why ready alone is not the runoff signal. |
| `0xB6F30`, `0xB6FB3`, `0xB7010`, `0xB7015` | Successful snap path, QB-spy-owned live state store, native stop call/return. QB-spy's site is unchanged. |
| `0xB6DE0`, `0xB6DFD`, `0xB6E30`, `0xB6E5C`, `0xB6E80` | Native 25/40 reset and play-clock start paths. |
| `0xAF510`, `0xAF3B0`, `0xAF3D0`, `0xAF310`, `0xAF320` | Start, inherited pause/unpause, running query and direct signed adjustment. |
| `0xB8F50`, `0xB90A0`, `0xB7150`, `0xB7110`, `0xB8810`, `0xB8BA0`, `0xB8C90` | Native dead-ball permission, reset selection, late-OB rules, timeout and temporary holds. |
| `0xB7F60`, `0xB7FCF`, `0xB7FD6`, `0xB6920`, `0xB7FEC` | Forward-pass ground branch and incomplete event. |
| `0xA0390`, `0xA03D7`, `0xB7230`, `0xB7268`, `0xB7275`, `0xB727A` | Incomplete stop request through timer stop and proof boundary. |
| `0xB665B8`, `0xB71D10`, `0xA89B60`, `0xE6000C` | Frame-once stop guard, timer frame counter, penalties enabled, quarter-length setting. |
| `0xB23F0`, `0xB1C70`, `0xB25B8` | Delay penalty producer, penalty-code constructor and call. |
| `0x157D20`, `0x157D40`, `0x157210`, `0xA0190`, `0x1588B0` | Play clamp, warning/period dispatcher, game seconds getter and warning entry. |
| `0x157E22..0x157EAE`, `0xA2970`, `0xB8910` | Native zero-clock, period-end and new-period flow. |
| `0xFBB10`, `0xFB430`, `0x4E4180`, `0x4E6D58` | Scorebug getter/conversion, float zero and native 120-second threshold. |
| `0xFF120`, `0xFEDB0`, `0xFF54D`, `0xBA3180`, `0xE6CBD0` | Native no-huddle HUD mode, team index, display selector, row table and string. |
| `0x18F906`, `0x18F994`, `0x18F2D1..0x18F30F`, `0x189298`, `0x1FFDFB..0x1FFE02` | Human/previous-play/CPU quick-call routes to the no-huddle entry. |
| `0x9F990`, `0x18B8D0`, `0x1CEAC0`, `0x9FA80`, `0x1FFD20`, `0xBF0E88` | Native previous-play selection/install/lineup and repeat-play state flag. |
| `0xA24E7`, `0x1AFCDE`, `0x1AFCC0..0x1AFDEC` | Existing kick-rules no-huddle call, audible stub and complete cave. |
| `0xE602EC`, `0xE602D4`, `0xE602D8`, `0xE602DC`, `0xE5FC00` | Native context, descriptor history and ball pointers supplied in the fixture. |
| `0xE60290`, `0xE60298`, `0xE6029C`, `0xE602A0` | Auxiliary native timer pointers supplied in the fixture. |
| `0xE5FC20`, `0xE5FC60`, `0xE5FC28`, `0xE5FC68`, `0xE5FF80` | Retail teams, player-list pointers and match mode supplied in the fixture. |
| `0x55F0B..0x55FBA`, `0xAF400`, `0xAF2F0`, `0xAF470`, `0xB71CF0` | Timer setup and hierarchy. Quarter-length writer `0x55F5B` remains with overtime. |
| `0xAF2C0`, `0xB71D0C`, `0x11A7C0`, `0x11A837`, `0x11A888`, `0xE9210`, `0x158CE0`, `0x158F1D` | Frame tick and downstream ready dispatch, proved by inspection; full frame not emulated here. |

The complete research ledger, including reset and descriptor-producer instruction addresses, is
`docs/research/nfl2k5_accelerated_clock_research.md`. Its first section is preserved as a pre-writer
checkpoint; the later closure sections record completed obligations.

## Bounded native scope

`tests/nfl2k5_accelerated_clock_native.py` loads the retail/patched sections into Unicorn and enforces
their page permissions. Synthetic timers, teams, selection, descriptors and ball objects occupy
`0x02000000..0x0200FFFF`; bounded stack/return pages occupy `0x03000000..0x0301FFFF`. Every run must reach
its specified return or boundary within 20,000 instructions. No predicted host runoff function is used.

The human case supplies the accepted-selection continuation; the CPU case starts with native selected
flag 8 and executes the real completion dispatcher. This proves the common completion path, not a full
controller input loop, CPU random play selection or 22 animated players. Ready predicates, timer routines,
selection installation, snap descriptor copies and clock stop run natively.

Explicit scene/presentation/player-install leaves are stubbed at `11E920`, `AF260`, `DDCA0`,
`13A730`, `206570`, `1CF2F0`, `94A00`, `1D1A90`, `89590`, `7D7A0`, `1B2E40`, `875E0`, `119470`, `59370`,
`18EC30`, `FC340`, `188A60`, `189F00`, `B1740`, `17AF00`, `13A0B0`, `156640`, `1B67C0`, `1D57A0`,
`1B9E70`, `1D0430`, `7B9E0`, `2077C0`, `11E7E0`, `72160`, `1B2560`, `A0FF0`, `874E0`, `FEF50`,
`9FC30`, `1B1300`, `190730`, `1CEAC0`; the in-bounds fixture supplies `B5750=0`. The formation scalar
`204F10` returns a balanced x87 zero through `0200F000`. The quarter-end test supplies the `9F8E0`
notification and stops at `A2970`. `1B1300` also stops its presentation timer at `BE5024`; that auxiliary
side effect is outside the bounded snap proof. The warning test stops on arrival at `1588B0`; neither
scene is rendered.

The final-two-minute condition is evaluated at completion. A call starting at 2:19 with a 20-second
runoff reaches 1:59 and native warning dispatch. A call starting at 2:00 or less does not accelerate.
The patch does not replace or reschedule the warning routine. This edge needs Noah's explicit witness.
Native stopped/resume rules remain authoritative; special-team/knee/spike classification additionally
prevents game runoff. No real timeout/review/injury UI scenario is claimed as executed by these tests.

## Validation commands and results

All tests are plain standalone unittest commands. Private retail tests use SkipTest when the exact USA
file is absent; native tests also skip without Unicorn, and the reference inventory skips without Capstone.

```text
python3 tools/nfl2k5_accelerated_clock_assemble.py --check
Accelerated clock template verified

python3 tests/mod_editor/test_nfl2k5_accelerated_clock.py -v
Ran 40 tests in 46.824s — OK

python3 tests/mod_editor/test_nfl2k5_accelerated_clock_manifest.py -v
Ran 5 tests in 9.742s — OK

python3 tests/mod_editor/test_nfl2k5_accelerated_clock_manifest.py --write-projection .scratch/b65-accelerated-clock-manifest.json
Wrote bounded projection, not a disc-build manifest

python3 tests/mod_editor/test_nfl2k5_cave_oracle.py -v
Ran 29 tests in 358.346s — OK

python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py -v -k accelerated_clock
Ran 25 tests in 136.087s — OK (recheck after kick-rules neighbor validation)

python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py -v
Ran 335 tests in 2068.403s — OK

NFL2K5_CAVE_MANIFEST=.scratch/b65-accelerated-clock-manifest.json python3 tests/mod_editor/test_xbe_patch_memory_writes.py -v
Ran 115 tests in 1273.216s — OK

NFL2K5_CAVE_MANIFEST=.scratch/b65-accelerated-clock-manifest.json python3 tests/mod_editor/test_xbe_patch_cave_references.py -v -f
RUNNING — final result to be recorded before handoff

python3 packaging/repin.py --apply
applied 0 pin update(s)
```

The first full-stack gate run refused the independently owned kick-rules call at `A24E7`. The fix
validates that entire owner and normalizes exactly its call for the no-huddle hash. It introduces no
ownership exemption. Regression tests reject both a corrupted kick-rules cave and a forged call alone.
The production cave manifest is protected; the gate projection observes the real allocator and this
writer and the gates' synthetic music metadata, retains unchanged historical ownership and refuses stale
inherited source fingerprints. The synthetic music step keeps inherited music reservations attached to
their actual allocation in the projected layout; no inherited owner is discarded to make the gate pass.
Claude must regenerate the production manifest after central wiring and repinning.

The candidate capability object was inserted into an in-memory copy of the canonical registry and passed
`mod_editor.capabilities.validate_registry.validate_data(..., check_files=True)`. The protected registry
was not modified. CLI `status` on retail reports `retail`, `enabled: false`, minimum 20 and
`runtime_witnessed: false`. Malformed compressed allocator data reports `foreign` and both apply/verify
refuse with ValueError. The public help text keeps the build choice and in-game witness limit visible.

## Noah's exact witness list

1. **Build and default.** Use the integrated Gameplay checkbox **Accelerated clock (Madden style)**.
   Confirm a fresh project and Basic/Advanced/Experimental presets show Off, minimum 20 s. Make a fresh
   Off build and an On/20 build from the same base. Select 15-minute quarters in the game. The Off build
   should have normal clock behavior. There is no new in-game settings row.
2. **Human, running clock.** Run or complete a pass in bounds well before two minutes. Huddle and choose
   the next play. Watch the play clock jump directly to 20 on offensive play-call completion. If it was
   40 immediately before the hook and the game clock 10:00, expect 20 and 9:40. If you spent time choosing
   a play, use the actual pre-jump value P: the game clock loses P−20, not a fixed 20 seconds. It must never
   rewind a play clock already below the selected minimum.
3. **Stopped clock.** Repeat after an incompletion, out of bounds, a timeout, an injury, accepted penalty
   and change of possession. While the native game clock is stopped, only the play clock may jump. Record
   early-half versus late-half OB behavior separately because native restart permission is retained.
4. **CPU offense.** Let the CPU call several huddled plays after both in-bounds and incomplete outcomes.
   Confirm the same play-clock jump, equal running-clock runoff, and no movement of a stopped clock.
5. **Two-minute control.** In Q2 and Q4, call plays at 2:00, 1:59 and 0:15. Neither clock may jump from
   acceleration. Repeat in OT's final two minutes. From just above two minutes, watch the runoff lead into
   the native warning, then confirm the next snap has no acceleration. Record the exact displayed warning
   time and any extra menu/lineup transition. A half-ending snap must never disappear from runoff.
6. **No-huddle.** Use the game's quick-snap/no-huddle previous-play choice after a completed in-bounds
   play. Neither timer may accelerate, including a subsequent lineup/completion transition. Test human
   hurry-up and observe the CPU's late-half hurry-up. Then return to an ordinary huddle after a real snap:
   one acceleration should be available again.
7. **Reset polish.** Call timeout after a play-clock jump; repeat with a penalty re-spot/replay review or
   injury. No second accelerated subtraction may happen before an actual snap, even if the native play
   clock resets to 25/40. After the next successful snap and huddled call, acceleration should resume.
8. **Specials and periods.** Watch kickoff after a score and the first snap of each quarter: neither gets
   accelerated runoff. Punt/FG/PAT/knee/spike may shorten the play clock, but never subtract game time.
   Near 0:15 in Q1/Q3, confirm a larger permitted runoff ends at 0:00 and native quarter transition happens
   once, with no negative time or next-quarter subtraction. Q2/Q4/OT final-two-minute snaps are protected.
9. **Minima and delay.** Rebuild with 25, 15, 10 and 5; confirm the exact scorebug number, then natural
   countdown. Deliberately wait through zero on one snap: only native delay of game should fire. Selecting
   the option or calling a play must not itself cause the penalty.
10. **Pacing.** Play a complete On/20 game at 15-minute quarters. Record offensive snaps for each side,
    possession time, no-huddle usage and any repeated jump. Compare an Off game with similar play calling.
    Realistic counts and Madden-like feel cannot be certified from the synthetic clock proof.

## Remaining integration work

Claude: apply `WIRING.md`, register the supplied row, include and pin the new runtime modules, regenerate
the production cave manifest and run offscreen Studio/packaging integration checks. Noah: run the witness
list above. No optional in-game settings implementation or release/push is included in this branch.

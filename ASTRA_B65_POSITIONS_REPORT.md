# Beta 65 job C: position choices and MyCareer controls

Branch: `astra/b65-positions`; implementation commit `614b5c8c`. No push, emulator, GUI display, audio playback or network. Retail inputs were read-only. **Implemented:** EDGE/LB creation and template fixes, additional native chooser coverage, the Contracts-editor composition fix, corrected per-position evidence, and native regression tests. **Protected integration:** the Studio picker, Build compatibility row, registry and RC89 bullets are specified in `WIRING.md`; those protected source files were not edited. “Run your own routes” was not installed: a safe body-specific FPF control selector was not proved.

Noah reports that QB MyCareer works. That is the only user gameplay witness supplied. The new build and all other positions remain **UNWITNESSED**. Decoded input, a dispatched command and a completed football action are distinct evidence levels.

## Part 1 — what changed

`nfl2k5_position_pools.py` owns the new native cycles, template records, remaining LB labels and trade-needs compaction. `nfl2k5_edge_rename.py` owns the seventh long-name consumer. No parallel patch, owner allocation, runtime `.text` data, or camera/control-mode flag was added. All writes accept exact retail/applied patterns and recompute touched section digests, including `.text`. Apply/replay is idempotent.

The pools default is now the compact profile. Its Create Player callbacks cycle `0..9,11..16`, in both directions, and wrap without a blank entry. MyCareer's in-game Create MyPlayer and the enabled Edit Player Position row use those same callbacks. With pools off, these two functions and all 51 template-rating records are byte-identical to retail; the separate EDGE rename option still owns its requested text changes.

### Native sites

| Consumer | VA / writer | Change or retained coverage |
|---|---|---|
| Create Player/MyPlayer/Edit Player next | `0x345560`, 48 bytes / pools | Skip retired enum 10; preserve dirty flag `0xCB8820`, record pointer `0xCB8B14`, position byte `+0x35`, and native wrap |
| Same, previous | `0x345590`, 48 bytes / pools | Reverse skip and wrap; whole callbacks and alignment tails checked |
| Create Player private long-name table | `0x555AE0`, entry 16 at `0x555B20` / EDGE | **Seventh consumer**; accessor `0x345540`; point to shared `Edge Rusher` at `0xE69DDC` |
| General abbreviation | `0x4F2710` / EDGE | Enum 16 -> EDGE |
| Group-16 abbreviation | `0x4F26C8` / EDGE | Merged-group DE -> EDGE |
| HUD abbreviation | `0x4F6928` / EDGE | DE -> EDGE |
| Depth abbreviation | `0xAAB800` / EDGE | DE -> EDGE |
| Franchise abbreviation | `0xAC2698` / EDGE | DE -> EDGE |
| Play-call SWAP legend | `0xA89938` -> header `0x10C88` / EDGE | `SWAP EDGE`, abbreviation at `0x10CA2` |
| Singular long names | `0xE69DDC`, `0xE83C44`, `0xEABD70`, `0xEAD424` / EDGE | All four `Defensive End` allocations -> `Edge Rusher` |
| Plural long names | `0xE69F8C`, `0xEA40EC`, `0xEA44E0`, `0xEA4720`, `0xEA9B60`, `0xEAB418`, `0xEAB62C`, `0xEAB9B8`, `0xEADA3C`, `0xEAE8AC`, `0xEAF53C`, `0xEB3ABC`, `0xEB5818`, `0xEBBFB8` / EDGE | All fourteen `Defensive Ends` allocations -> `Edge Rushers` |
| CAP / trade-needs / depth LB long names | `0xEABCFC`, `0xEAD468`, `0xE83CAC` / pools | `Inside Linebacker` -> `Linebacker` |
| Complete Create Player template table | `0x5561B8`, **51** records × `0x74` | Correct the old 36-record/12-position census; native indexing is `3*position+variant` |
| EDGE templates | Rows 48–50, `0x557778`, `0x5577EC`, `0x557860` / pools | Three complete label-pointer/28-rating records; preserve native indexing |
| EDGE template labels | `0xEAC6E4`, `0xEAC700`, `0xEAC71C` / pools | Reuse retired OLB template label allocations for Power/Speed/Balanced EDGE |
| LB template labels | `0xEAC738`, `0xEAC754`, `0xEAC770` / pools | Run Stop/Coverage/Balanced LB; native ILB ratings retained |
| Separate trade-needs modal | Base `0x557EC8`; changed slice `0x557ED8`, 64 bytes / pools | Remove `{Outside Linebacker,10}`, compact label/enum pairs, preserve two terminal zero pairs; count drops 9 -> 8 |
| Defensive depth slots | Retail table `0x5140D8`, stride `0x48`; current relocated table supported | EDGE on exterior slots; enum-15 interior 3-4 slots now DT / LEFT or RIGHT DEFENSIVE TACKLE, replacing remaining DE labels. MIKE/WILL/SAM identify separate lineup roles |
| Play-call LB swaps | Existing pools kind/enum/package writers | Live LB enum 11 and appropriate LB swap slots; `LB2` identifies the additional linebacker slot, not an OLB position choice |

**Correction to the premise about a missed “Defensive End” literal:** the seventh consumer is real, but its old string `0xEABD70` was already among the rename module's four singular shrink sites. An exhaustive case-insensitive UTF-16 census of the pinned XBE found four singular and fourteen plural allocations, all previously covered; the new pointer makes the private CAP consumer explicit. It would be incorrect to report a seventh previously unpatched literal. The remaining demonstrated sources of DE wording were the pool-owned 3-4 labels and the **Studio** picker: `my_career_panel_qt.py` loops through 17 retail labels and calls `position_name/position_long_name` without the selected scheme. The latter is protected and has exact wiring instructions.

All native position filter tables are already pattern-checked complete pointer lists. The compact profile removes the enum-10 page pointer, shifts the remaining entries, and terminates twice. It does not leave a disabled/empty OLB row or remove unrelated empty groups such as Fullbacks.

| Selector | Table VA |
|---|---|
| Combine | `0x53B514` |
| Rookie / draft preparation | `0x53B65C` |
| Rookie scouting | `0x53B79C` |
| Free agency | `0x53E7E4` |
| Player Contracts | `0x5403CC` |
| Pro Bowl votes | `0x54A254` |
| Progression | `0x5515A4` |
| Opposition | `0x552F14` |
| Rosters | `0x554D64` |
| Player Trade | `0x559B04` |
| Trading Block | `0x559C44` |
| NFL Draft | `0x55FD94` |
| Choose Player | `0x5714BC` |
| Player Comparison | `0x5803FC` |
| Team Needs | `0x582CE4` |
| Trade Comparison | `0x5887DC` |

Native selector count `0x170910`, previous `0x174CE0`, next `0x174CB0`, ordinal lookup `0x174D30`, and page binding `0x174140` retain their earlier bounded proofs. The additional trade modal has its own null-terminated eight-byte-pair counter at `0x14D4A0`, now executed on both retail and compact tables. `0x348E33` captures the modal's enum result; `0x348E5A` writes that enum, rather than using the display ordinal as a position.

`docs/mod_editor/nfl2k5_b65_positions_evidence.json` records **every declared EDGE and pools write site's VA, length and before/after SHA256**, plus the native input evidence. It contains metadata, not retail payloads. Existing `ASTRA_OLB_ROW_REPORT.md` and `docs/mod_editor/nfl2k5_olb_row_evidence.json` retain the detailed filter callback/reference census.

### Templates and compatibility

| Live EDGE template | Source | Speed | Agility | Pass rush | Tackle | Strength |
|---|---|---:|---:|---:|---:|---:|
| Power EDGE | Native DE Pass Rush DL, row 49 | 70 | 65 | 88 | 80 | 70 |
| Speed EDGE | Native Coverage OLB, row 31 | 82 | 75 | 70 | 75 | 65 |
| Balanced EDGE | Floor-average of native balanced DE/OLB rows 50/32 | 67 | 65 | 72 | 82 | 72 |

These are merged native archetypes, not a claim of gameplay balancing. All 28 rating slots are written by the existing native function `0x343460`; native `-1` slots mean 75, not “leave unchanged.” The three native OL styles and three DT styles also exist. MyCareer's old fallback wrote 65 across C/G/T/DT/DE attributes because the earlier census stopped too soon. The inline runtime now forwards every valid position to the native template writer. It retains the invalid-position guard and stays within its existing budgets: 14,858 content bytes in the 16,384-byte RX reservation, with two existing 4,096-byte RW blocks.

The Contracts editor also checks a hash covering `0x345540..0x3455B2`. Initial gate runs correctly rejected the changed cycles. `nfl2k5_franchise_edit_player._recognize` now verifies the **complete** pools installation and both complete cycle patterns, then normalizes only their overlap for that prerequisite hash. Both installation orders are tested; foreign cycles still refuse. Modern scheme/EDGE recognition similarly accepts DT labels only in the exact matching pool layout.

The explicit old API profile `roster_has_olb=True` can still restore OLB filter rows for old/custom saves. That is **not** the EDGE-only product profile. Native count/getters (`0xC3CB0/0xC3D30`, `0x242670/0x242520`) still query enum 10 separately. Removing its row does not reclassify those players. `WIRING.md` retires the GUI compatibility override and makes the final Build scan fail on any remaining enum-10 player or incomplete scan. All 76 disc roster resources must pass after their final edits. Later external saves need reclassification; no runtime save migration was implemented.

## Part 2 — per-position PROVED / HYPOTHESIS

Pins are reproducible with:

```bash
PYTHONPATH=. python3 tools/nfl2k5_my_career_position_evidence.py '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe'
```

The USA XBE SHA256 is `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`. The tool pins 26 native spans, including all three controller layouts' 21 × 27 command tables at `0xA99EC0` (layout stride 2268, context stride 108). Whole-table SHA256: `17610a4f79595587f8b0648749f1f5fe946c92ea9ef37f22d6f69248b5d0758e`.

| Group | PROVED in this session / supplied witness | Still HYPOTHESIS or UNWITNESSED | Shipped behavior |
|---|---|---|---|
| QB | Noah reports successful QB play. Context 3 pre-snap; QB context 6 in `0x1D0F20`; carrier contexts 8/10. Native button decode and body-to-port restore execute. Three native templates | All formations, snap timing, passing/scramble transitions on this new build | Existing QB binder, native behavior and Standard/Far MyPlayer camera |
| HB / FB | Context 9 off ball, context 10 for carrier through `0x1569E0`; stick and off-ball commands decoded with FPF off, for both back codes. Three templates each | Whether pre-handoff AI owns mesh locomotion, or stick overrides it; reliable handoff/catch. No separate safe “human back” selector proved | Existing native context/behavior; no snap-time context override |
| WR | Context 9 decodes analog and `0x67/0x68`; native dispatcher calls corresponding handlers with the receiver body and FPF off; carrier context 10. Three WR templates | Route AI vs stick authority; complete catch animation/timing and possession. A decoded catch-related request is insufficient proof | Existing behavior; “Run your own routes” withheld |
| TE | Same off-ball input path and post-possession context; Catching/Blocking/Balanced templates | Manual route, catch and block behavior through different assignments | Existing native context/behavior |
| C / G / T | Binder/camera, analog and command decode accept all three codes. All nine OL templates apply natively | Neither steering of world position nor a pass-set/run-block button action was established. This investigation cannot even certify “steering only” | Existing MyPlayer camera plus native blocking behavior; this is the conservative blocker-view fallback, **not a proved automatic-block animation feature** |
| DT / EDGE | Identity retained for a defender other than the requested/default selected body. Post-snap context 11. In engaged behavior `0x02000000`, context-16 command 6 and right-stick input reach native `0x2324F0` and update move state `+0x124`; another behavior clears the command without that write. Three DT/EDGE templates | Pre-snap physical alignment, successful rush/shed animations, tackle outcomes and entire turnover plays | Existing defensive behavior and switch guards; EDGE templates when pools is on |
| LB / legacy OLB | Both IDs bind; contexts 4/5 pre-snap, 11 post-snap and 16 engaged; switch guards tested. LB templates. OLB retired from new creation under pools | Actual shift, coverage-drop, blitz and shed motion | Native behavior; only LB/EDGE choices in pools creation |
| CB / FS / SS | Both team sides and all three IDs bind; native defensive contexts and switch guards apply | Coverage movement, swat/interception timing and complete turnover sequences | Existing native defense; no nearest-player handoff through covered guards |
| K / P | Context 2 decodes kick commands. Existing bounded inline tests execute `0x1891B0`: K/P and special-team cases use CPU play-call ownership. Absent MyPlayer detaches input | Rendered kick meter and kick result. “Only appears on kicks” is **not proved**: field presence comes from the active identity/formation, not a K/P-only phase restriction; unusual substitutions/holders can differ | CPU calls; input binds only when MyPlayer's active body exists |

### What the native input proofs establish

`0x1563F0` walks active entities, clears transient input, and calls `0x1211E0` only when the body's controller ID is not -1. The new harness executes retail controller-cache reads, stick math and `0x120A20` command decoding. A cached stick `(0.6, 0.8)` produces magnitude `1.0` and heading `0xE5C8` for every position and ports 0, 3 and 7. Context 9 plus cache mask `0x400` decodes `0x67`; mask `0x800` decodes `0x68`. FPF stays zero. Unbound and inactive bodies receive no new command. These are cache masks, not claimed Xbox button names.

`0x1565F0 -> 0x120880 -> 0x120730` restores the body's context to just its port at `0xA9B960 + port*44`, clears transient command state and reconstructs the layout-dependent mask. All three layouts, eight ports and contexts 2/3/4/5/6/8/9/10/11/15/16 are exercised. The existing kick-context exit special case remains native; the general restore test intentionally starts outside that case.

At phase 14, `0x1569E0` selects 9 for offense with entity word `+0 == 0`, 10 for offense with nonzero word `+0`, and 11 for the other team. It contains no position-code or FPF predicate. `0xAF000` sets alignment contexts 3/4 by team. This corrects the earlier contract: **9 is not exclusively QB control, and 16 is not the entire defender-control path.** Context 6 includes the QB passing command family `0x41..0x45`; 8/10 include carrier commands; 16 includes engaged move commands `6..9`.

`0x18EC40` dispatches the body's command via `0xAABEF8 + command*4`. In the bounded off-ball case, `0x67 -> 0x18FAC0` updates native state and requests command 4; `0x68 -> 0x18DF00` requests `0x5A` or `0x55` depending on the supplied animation/ball state. Animation bookkeeping is stubbed in those tests. No completed catch, mesh, route or blocking animation is asserted. Engaged move testing executes the actual accumulator `0x2324F0`, including its native right-stick read; right-stick up with command 6 sets state bit `0x80` only when the behavior tag matches. Pre-snap shift commands decode, but their formation/animation result was not executed.

The bounded phase fixtures available in this tree do not provide a witnessed full snap/route/mesh animation pipeline; prior CPU-frame fixtures remain in lineup state 12. Extending a synthetic input-block proof into a claim that the AI yields locomotion would be unjustified. The unresolved boundaries are the position behavior/locomotion and animation consumers after these context/dispatch stages, not controller binding.

### FPF and switch decisions

At FPF exhibition entry `0x2C1FC0`, direct stores are `0xE5FF80=4`, `0xE5FFE4=1`, saved prior `0xE5FF8C -> 0xACF610`, and `0xE5FF8C=1`; entry proceeds to flow 7. The bounded entry test stubs UI/audio/team-selection services and verifies those writes without changing the receiver body/context. `0x627C0` is the global FPF predicate; `0x627E0` reads the global flag. Receiver-selection code around `0x1B7A90` also checks the global FPF predicate and focused-body getter `0x7A630`. No receiver-local flag set by this entry was found. These facts do **not** prove that no such mode exists elsewhere. They rule out treating the exhibition entry's global flag as a proved MyPlayer-only route switch. FPF route-running ability does not justify globally enabling its camera and team-control path.

Covered controller changes are guarded at assign `0x156870`, automatic selection `0x1A7970`, team reset `0x1A77A0`, manual selection `0x1A85E0`, and transfer `0x1A70E0` (plus the existing attachment/copy hooks). Automatic requests also arise from the per-port walker `0x1A7AE0 -> 0x1A7970` at `0x1A7BAC`; `0xA08B7` is another automatic request after a context transition. `0x1A7970` eventually transfers at `0x1A7AA6`. Manual selection goes through `0x1A83B0`; in phase 14 it selects the ball/possession-sensitive offense/defense path `0x1A74A0/0x1A8360`, then transfers at `0x1A862F`. The automatic routine itself selects controller candidates; it should not be mislabeled a pure nearest-distance function.

All seven defensive codes were tested with another body holding/requesting the port: each covered guard re-resolves identity and restores only MyPlayer. The existing tests also preserve held input on an unchanged binding and detach on absence, duplicate identity or a malformed/cyclic entity list. **No control-jump case was observed in those bounded entries.** The exact nearest-to-ball event sequence and complete live turnovers remain unwitnessed; the transfer guard covers the identified destination path, not a claim that every event has been played.

## Noah's witness script

Use a fresh career per group, the intended pools build, FPF off, and Standard then Far camera. Use the current controller preset's labels for Snap, Catch, Dive, Switch Player, Rush/Shed, Swat and Kick; the offline cache-mask proof does not establish a universal physical-button mapping. Compare an untouched baseline attempt with an input attempt on the same play in Practice. Record position, play, phase, button/stick, indicator target, movement/result, and whether the next snap recovers.

1. **Pickers/templates:** with pools on, cycle both directions twice in Create Player and Create MyPlayer. Expect 16 choices, exactly EDGE and LB, no OLB/DE/ILB. Visit all three EDGE styles, then C/G/T/DT; ratings must vary by the native style, not be all 65. With pools off, expect all 17 retail position codes and native templates. Visit every selector in the sites table, including both trade screens, Team Needs' modal and Pro Bowl. Expect no retired row or cursor stop on a blank item. Check empty Fullbacks still exists, and SWAP shows EDGE/LB slots.
2. **QB:** let the CPU choose/complete its play-call phase as the current mode allows, press the configured Snap button, throw to two different icons, then scramble on another play. Expect the indicator and camera to stay on QB after the throw; Switch Player must not transfer control to a receiver. Confirm Noah's known QB behavior survives this build.
3. **HB/FB:** on a handoff, first leave the stick neutral from snap to mesh. Repeat with the stick held away from the designed mesh **before possession**. If the back changes path, pre-handoff steering works; if both runs reach the same mesh, AI still owns that stage. After possession, move left/right and use the configured runner move. Repeat on a pass/block assignment and a backfield route. A missed handoff, frozen back or ball-carrier switch is a failure to record, not evidence of manual-route support.
4. **WR/TE:** on a straight route, leave the stick neutral on one snap, then hold across the drawn route on the next. Observe whether the body changes route before the pass. On a target, press the preset's Catch button near arrival; compare neutral/button attempts. Expect the identity indicator to remain on the same player after the throw, catch/incompletion and next snap. For TE repeat a blocking assignment. Mark manual routes and catching separately: one working does not prove the other.
5. **C/G/T:** watch a neutral-stick pass and run first. Repeat with left/right stick input before and after engagement; try the preset's available block/rush controls one at a time. Record whether there is actual steering, a block animation choice, or only native auto-blocking. The shipped claim is camera/identity plus native behavior; there is no proved manual pass-set button. The fallback target is a useful MyPlayer blocker view with native auto-block, without disturbing the other linemen.
6. **DT/EDGE/LB:** choose a player away from the ball/default selection. Before snap move the stick and try the current preset's alignment/shift controls. After snap steer toward/away from the assignment, engage and try each rush/shed move. Expect input to stay on MyPlayer when another defender approaches the ball. Force/observe a catch, scramble, fumble, interception, score and kickoff; press Switch Player in each available phase. Record any jump with exact event and original/new player.
7. **CB/FS/SS:** begin on the far side, steer a coverage drop, then use Swat/Catch on a targeted pass. Verify the camera/indicator does not jump to a teammate nearer the receiver. Repeat a run, interception return and an incompletion. If the unit shifts instead of only MyPlayer moving, record that separately from direct alignment control.
8. **K/P:** remain neutral during normal offense/defense and watch who calls the kick/punt. On field goal, PAT, kickoff and punt, use the preset's kick controls through the meter. Expect CPU play calls and control only while MyPlayer's active body is present. Note any holder, return, fake, onside or unusual formation appearance; do not assume it is impossible. Verify the following scrimmage play leaves input detached when MyPlayer is absent.
9. **All groups:** bench/substitute or injure MyPlayer, change unit/possession, save/cold reload, and resume another fixture. Expect no replacement to inherit input. Return to ordinary Franchise and verify native team switching and position choices appropriate to its installed options.

## Validation

All commands use the repo as `PYTHONPATH`; Qt uses `QT_QPA_PLATFORM=offscreen`. Tests run standalone with `unittest`. No new test embeds a retail executable or resource body.

| Command | Result |
|---|---|
| `python3 tests/nfl2k5_edge_rename_test.py` | 13 passed |
| `python3 tests/nfl2k5_position_pools_test.py` | 26 passed |
| `python3 tests/mod_editor/test_nfl2k5_position_choices.py` | 11 passed |
| `python3 tests/mod_editor/test_nfl2k5_roster_records.py` | 108 run, OK, 1 skipped |
| `python3 tests/mod_editor/test_nfl2k5_olb_row.py` | 13 passed |
| `python3 tests/mod_editor/test_nfl2k5_my_career.py` | 13 passed |
| `python3 tests/mod_editor/test_nfl2k5_my_career_frontend.py` | 7 passed |
| `python3 tests/mod_editor/test_nfl2k5_my_career_panel.py` (offscreen) | 4 passed |
| `python3 tests/mod_editor/test_nfl2k5_my_career_control.py` | 2 passed; all 17 positions, both team sides and CPU-call cases |
| `python3 tests/mod_editor/test_nfl2k5_my_career_unicorn.py` | 18 passed |
| `python3 tests/mod_editor/test_nfl2k5_my_career_position_inputs.py` | 9 passed |
| `python3 tests/mod_editor/test_nfl2k5_my_career_m3_budget.py` | 5 passed |
| `python3 tests/mod_editor/test_nfl2k5_my_career_mode5.py` | 4 passed; 17-position starter/depth restore, native practice and navigation |
| `python3 tests/mod_editor/test_nfl2k5_franchise_edit_player.py` | 12 passed |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 111 tests, 1286.379s, OK |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 123 tests, 1453.530s, OK |
| `python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py` | 310 tests, 1909.576s, OK |
| `NFL2K5_CAVE_MANIFEST=.scratch/b65-positions/manifest.json python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | 29 tests, 343.663s, OK; fresh full manifest |
| `python3 packaging/repin.py --apply` | Seven existing provider pins updated; final replay reports `applied 0 pin update(s)` |
| `git diff --check` | Clean |

The first XBE gate runs failed at the Contracts-editor prerequisite hash; that composition failure is fixed and covered by a new regression. The first full manifest build correctly refused because writer/evidence sources changed during generation. The second full disposable build succeeded after freezing those sources. Its manifest records 12,623 reservations from 137 writer calls and 24 image steps, with all section digests verified and every recorded source pin matching. Its SHA256 is `d072d824781f683e3965666669a1479965cb3d15231453f671ddc048087722b6`.

The full manifest was generated with:

```bash
PYTHONPATH=. python3 tools/nfl2k5_cave_oracle.py manifest \
  '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --xiso '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso' \
  --work-dir /tmp --json .scratch/b65-positions/manifest.json
```

The XBE gates used the protected default manifest and current writers; the separate oracle run used the freshly observed full manifest above, including source-drift verification. The protected release manifest remains untouched and must be regenerated by Claude after all jobs and WIRING land. Local logs live in uncommitted `.scratch/b65-positions/`; they are not release assets.

Remaining work for integration/witness is explicit: protected Studio/Build/registry/RC89 wiring, release-manifest regeneration, and Noah's per-position live witness. Neither a manual route mode nor a universal “every position works fine” claim ships from this evidence.

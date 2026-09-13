# Beta 69 J3: MyCareer

Branch: `astra/b69-j3-mycareer`, base `922c009d`. Every new in-game outcome is
**UNWITNESSED**. Native instruction execution and offscreen Qt checks are
bounded proofs, not console or display acceptance. No emulator, GUI display,
audio device, network, disc build or read-option edit was used.

## Witness input and scope

andrethealchemist says, **“Wow! Everything I asked for was fixed in beta 68!”**
That is an in-game confirmation of his beta-68 fixes, including Supersim
persistence and the PAT choice. His new report is narrower: after Fast forward
returns his unit, “my 1st down play is already selected for me” and “I'm not
able to choose my plays until after the first snap.” Do not reclassify the
beta-68 work as unconfirmed merely because this new transition was wrong.

THE1WAM: **“I lowkey don't think we should be able to pick the plays in MyCareer
imo”**. Noah: **“Depends on position. QB should. But I can make it an option
where you never choose you just execute”**. THE1WAM: **“Yea make it only for QBs
and ILBs”**. The saved option implements that commitment. Its default preserves
the existing caller behavior; the other choices require an explicit selection.

Read the supplied `THE1WAM_TEMPLATE.txt` as design input. Creation tiers and
aliases of existing CAP templates fit the existing writer. The event/drill
flow, performance goals and scouting screens are roadmap items below.

## Instruction-level first-play finding

**PROVED:** The beta-68 series reproduced this sequence on one native match:
possession changes; `A11F0` begins play calling; at `A1412` MyPlayer has no
currently assigned actor in the new lineup, so the MyCareer consumer hook
returns CPU eligibility; `A1419` calls `1531F0`; native selection assigns the
returning unit and MyPlayer's actor. The team's call context at `team+0x0C`,
offset `0x24`, already has bit `0x08` set. `1891B0` tests that bit at
`1891F3..1891FE` and reports no human call pending.

The scheduler's absent-unit call is therefore still in force after the binder
finds MyPlayer. `mode_unit_present`/`mode_human` are consumer eligibility,
not a cancellation of an already completed call. The old resume path cleared
the wait and restored the controller/full play clock, but left that native
call-complete bit untouched. This explains why the second play was selectable.

**Change:** At the existing bounded, unsnapped, settled hand-back, preserve the
beta-68 clock restoration and rebind. For a human caller, latch the validated
side in owned transient RW, clear only its call-complete bit, close the stale
native menu with `ACB90`, and enter `9FBE0`, the same screen entry called at
`A143A`. Its native `ACA80`/`AC480`/`AC7E0` path establishes the menu and port.
The latch keeps human selection eligible while native personnel is rebuilt;
it expires after the accepted call's new personnel settles (or play advances),
not merely when its choice bit is written. Otherwise a transient absent actor
could rearm wait and disable the controller again. It is not serialized. Coach policy
retains the native selected call and restores the execution controller.

The original checks for 22 active ready actors, native pre-snap state 13,
no queued event 28, full play clock and valid identity remain. Mid-play
membership, injury substitutions, pending snap tasks and modal prompts retain
their existing guards. The saved Supersim word at `state+2696` is never changed
by this hand-back. B/cancel and next-CPU-snap rearming remain beta-68 behavior.

The brief's source references need one distinction at base `922c009d`:
`runtime.c:151` is the consumer-only eligibility comment. Line 513 is the
creation club-menu overlay comment about restoring parent templates on resume;
it is not the on-field Fast-forward hand-back. The native trace above reaches
`mode_ff_ready` at line 269 and its settled branch at line 290, so the fix belongs there. The creation
resume overlay does not cancel or own a completed match play call.

**Harness boundary:** `tests/nfl2k5_b69_series.py` extends the b66/b661/b68 series.
It adds empty loaded play-call background scenes at the same asset boundary as
the older empty overlays, restores the actual `771F0`/`77200` match port mapper,
and supplies a human play selection to native `207440`, called by the menu at
`AE66E`/`AE645`. This executes native selection, personnel assignment, controller
binding and the subsequent snap. `A31E0`, used by the earlier PAT boundary
probe, is a reselection path and is not a complete ordinary menu-selection
input. The new proof uses the normal callback. It does not claim cursor pixels
or physical controller navigation. Ready-animation completion, fourth-down
situation, snap/dead-ball events and game completion are declared inputs;
outer updates, possession, lineup and save callees are not substituted.

The defensive Coach series exposed a latent fixture input defect: the b68
ready-animation input stored clip address `63C8C0` directly at descriptor
`+D4`. Native `1FE0CD..1FE0E3` expects a pointer slot there, read the clip's
`00540017` header as an address, and eventually stopped at `DED13` in the
quaternion sampler. The b69 helper now supplies the same declared clip through
a pointer slot. Native selection, sampler and all 27 frame phases remain live.
This is a corrected harness boundary, not a production animation fix. The
final policy proof observes execution control after an ordinary presented
frame, requires native pre-snap state 13 at that point, then supplies a snap
and observes state 14. It no longer calls `rebind` explicitly to satisfy its
controller assertion.

The old all-position settled-clock/render probe now explicitly chooses Coach
for that contract. The separate beta-69 human series checks menu reentry; this
does not replace or weaken its injury, readiness, cadence or renderer checks.

## Saved caller option

Apartment Settings has a fifth existing-list row:

| Choice | Policy | Native play selection |
| --- | --- | --- |
| You call every play | 0, default | Existing beta-68 scrimmage unit/PAT eligibility |
| By position | 1 | QB on offense; native ILB code 11 on defense |
| Coach calls the plays | 2 | Existing absent-unit CPU selector, also for present units |

One-pool LB is native code 11. OLB/EDGE are not defensive signal callers.
The default preserves beta 68's position mask, including its existing C/G/T
and K/P exclusions. Those positions retain the coach's call; this is an
existing eligibility limit of the requested retail/default label. The existing home/away control regression passes unchanged.
The option changes selection eligibility, leaving the MyPlayer binder and
position input handlers responsible for pre-snap control and execution.
Audibles remain whatever the native position/state accepts; their physical
availability is **HYPOTHESIS / UNWITNESSED** until the script below is played.

Footer byte 82 bits 5..6 store 0/1/2; value 3 and bit 7 are invalid. Existing
FPF, Supersim, star and stat-line bits remain intact. The native word is
`state+2736`. Old zero-filled settings decode to policy 0. Nonzero caller/tier fields require
a beta-69 reader; older readers correctly reject their formerly reserved bits. Host read/change
and signed separate-copy export reparse the result, as does native save/load.
The proposed studio page reads and writes both caller and Supersim together.
Its exact protected patch and registry rows are in `WIRING.md`. Three offscreen
wiring tests exercise the page controls, signed export and effective Build
dependencies; the last captures the proposed Build recipe before disc preflight
and proves it uses the frozen setup without reading the file again.

The optional CB extension initially stopped at the malformed clip-slot input
explained above. With that input corrected, native sampling completes, but
this supplied scenario still does not return the selected CB identity at the
asserted boundary (`missing hand-backs: []`); it is not an accepted hand-back
case. The required defensive possession matrix uses ILB. CB caller eligibility
is covered in the complete position matrix, while a CB possession and actual
controller use remain witness work. No animation callee or personnel selector
was stubbed to manufacture a return.

## Prospect tiers and templates

| Tier | Starting native OVR | Initial depth place | Stored career-goal label |
| --- | --- | --- | --- |
| Original creation | Existing template | Existing behavior | Original career goals |
| 1st Day | 74 | Backup; Slot WR / Nickel CB | Highest tier career goals |
| 2nd Day | 70 | Third string; fourth WR / CB | Middle tier career goals |
| 3rd Day | 64 | Third string; fifth WR / CB | Low tier career goals |
| Undrafted | 59 | Last at that position | Lowest tier career goals |

The studio writer takes `prospect_tier`; Original creation is byte-identical
to its historical path. Tier/goal identity is in checkpoint word +212 and
the setup receipt. Prepared Undrafted records use rank 7 while their draft
destination is unknown. The existing depth-lock companion must be enabled for
tiered prepared builds; the exact dependency is in WIRING. This is a rank
placement, not a guarantee of a roster spot, draft round or playing time.

The in-game entry has an available fifth list slot. It cycles Original, 1st
Day, 2nd Day, 3rd Day, Undrafted without a new screen or shifting the existing
Draft/Undrafted/Load/Quit indices. CAP completion calibrates ratings, then the
existing draft/signing path places the player. The tier is footer byte 83 and
runtime word +2744; 0..4 are valid. Native Undrafted placement counts the
destination's actual same-position group. Routine launches retain the initial
place; the existing explicit Start MyPlayer action can subsequently promote.
Goal labels are recorded metadata, not implemented goal scoring.

**PROVED:** Native unboosted integer OVR is `246D90(player, 0)`. The host model
interprets its weighting/threshold data and matches the native result across
51 CAP templates, three body-size cases and five tier values (765 combinations),
plus 300 deterministic varied-rating records. Bounded one-point skill sweeps
hit the requested integer OVR, preserve style and identity bytes, and refuse an
unreachable goal. Native refusal rolls back the CAP record, names and unused
FA tail with a cause/next-step notice. Eight native creation/placement/save and
cold-reload cases cover four tiers for QB and CB. Tier values are not an average
of the attribute grid or an estimated roster-editor overall.

Prototype mapping: Scrambling QB → native template 1; Gunslinger QB → Pocket
template 0; Balanced QB → template 2; Pocket QB → template 0. Gunslinger is an
explicit alias, not a fourth invented native rating template. The historical
Pocket default stays selected. Other positions expose their existing three
CAP styles; one-pool EDGE uses Power EDGE 0, Speed EDGE 1, Balanced EDGE 2.
The template names only QB's proposed four prototypes, so no fourth style was
invented for other positions. The in-game native CAP style selector stays its
existing three choices.

For the template's other positions, the prototype labels map directly to these
existing CAP rows (variant 0 / 1 / 2, followed by global template indices):

| Position | Existing prototype labels | CAP indices |
| --- | --- | --- |
| HB | Finesse / Power / Balanced | 21 / 22 / 23 |
| WR | Speed / Hands / Balanced | 9 / 10 / 11 |
| TE | Catching / Blocking / Balanced | 27 / 28 / 29 |
| EDGE, one-pool | Power / Speed / Balanced | 48 / 49 / 50 |
| DT | Run Stop DL / Pass Rush DL / Balanced DL | 45 / 46 / 47 |
| OLB | Run Stop / Coverage / Balanced | 30 / 31 / 32 |
| ILB, one-pool LB | Run Stop / Coverage / Balanced | 33 / 34 / 35 |
| FS | Cover / Physical / Balanced | 15 / 16 / 17 |
| SS | Cover / Physical / Balanced | 18 / 19 / 20 |
| CB | Cover / Physical / Balanced | 12 / 13 / 14 |

## Roadmap feasibility for Noah's reply

| Template item | Existing footing and required native prerequisite |
| --- | --- |
| Senior Bowl goals and points | Senior Bowl roster/data tier exists, including MyPlayer preparation, **without simulation**. Needs owned event entry/return, player transport, isolated stats and a committed result before awarding the 200/300/400 passing and 50/75/100 rushing goals, maximum 6 points. A six-minute starter game is not implemented. |
| Combine 40-yard dash | Basic Training remnants on 2K5 are **unowned**. Needs a pinned drill scene, safe entry/exit, exact 40-yard start/finish measurement, clock ownership, two-attempt reset and a saved best result. Only then apply the supplied points bands and speed caps. |
| 40-time table | The design specifies 4.34–4.35 → 95 speed down through 4.81–4.82 → 75, with its intermediate bands. A result must be rounded/canonicalized before lookup; times below 4.34 or above 4.82 and ties need explicit design rules. No invented timing or speed award is shipped. |
| Pass Skeleton | Needs owned practice/drill launch, four attempt boundaries at midfield, isolated passing yards/completions and an immutable completed result. The design's yards/percentage rewards plus dash rewards total at most 11 Combine points. Training remnants alone prove none of that. |
| Pro Day | Reuses the future measured drills, then needs one chosen-drill state, attempt budget, best-result replacement rules and idempotent save/return. Undrafted exclusion from Combine/Senior Bowl also needs that event progression state. |
| Apply Ratings | Existing XP purchase/save machinery is useful. Needs a separate earned-event ledger, attribute-group permissions, speed cap enforcement and an atomic debit/result commit so reload/reentry cannot mint points. Current participation XP is not a Combine award. |
| Draft Advisory | Needs a read-only snapshot of the native draft-AI team needs/ranking at the actual draft stage, safe labels and refresh/invalidation after signings. The six example teams cannot be presented as live scouting facts. Existing draft advancement/pick tracking can later consume the advisory result. |

## Verification

All suites run standalone with `PYTHONPATH=.`, `QT_QPA_PLATFORM=offscreen`,
`PYTHONHASHSEED=0` and
`NFL2K5_CAVE_MANIFEST=.scratch/j3/verified-manifest.json`.
The runner `tools/mycareer_mode/validate_m3.py` records exact per-file commands,
exit codes, test counts, timing, peak RSS and hashes of the production sources,
manifest and logs. It rejects a source change during a suite. The final portable
receipt is `tools/mycareer_mode/b69_validation.json`.

The final unintegrated run covers **46 standalone suites**. Forty-five return
OK, including the generic-build suite with its one existing free-space skip.
The provider suite has the one expected integration failure described above;
the proposed provider changes pass all seven tests. All four XBE gates and
the required native hand-back/creation proofs pass without skips.

| Standalone command (`PYTHONPATH=.` and environment above) | Final output |
| --- | --- |
| `python3 tests/mod_editor/test_beta66_supersim_wiring.py` | `Ran 3 tests in 0.348s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_accelerated_clock.py` | `Ran 40 tests in 43.041s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_b661_transition.py` | `Ran 11 tests in 623.941s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_b68_game_composition.py` | `Ran 3 tests in 559.176s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | `Ran 29 tests in 441.671s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career.py` | `Ran 13 tests in 20.003s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_b69_wiring.py` | `Ran 3 tests in 1.067s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_completion.py` | `Ran 6 tests in 33.177s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_control.py` | `Ran 2 tests in 15.132s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_cpu_choice.py` | `Ran 1 tests in 24.460s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_cpu_frame.py` | `Ran 1 tests in 77.882s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_cpu_injury.py` | `Ran 1 tests in 21.866s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_cpu_period.py` | `Ran 2 tests in 36.792s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_cpu_timeout.py` | `Ran 1 tests in 27.664s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_cpu_turnover.py` | `Ran 3 tests in 109.779s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_creation_boundary.py` | `Ran 4 tests in 2.139s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_draft.py` | `Ran 6 tests in 1543.571s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_frontend.py` | `Ran 7 tests in 82.453s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_generic_build.py` | `Ran 5 tests in 13.503s; OK (skipped=1)` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_inline.py` | `Ran 8 tests in 19.660s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_m3_budget.py` | `Ran 5 tests in 4.338s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_m3_menus.py` | `Ran 4 tests in 39.479s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_manifest.py` | `Ran 3 tests in 11.254s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_mode4.py` | `Ran 8 tests in 619.946s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_mode5.py` | `Ran 4 tests in 401.901s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_mode_audit.py` | `Ran 6 tests in 0.136s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_mode_routes.py` | `Ran 7 tests in 3.028s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_panel.py` | `Ran 4 tests in 0.268s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_playcalling.py` | `Ran 3 tests in 717.029s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_played.py` | `Ran 4 tests in 71.241s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_position_inputs.py` | `Ran 9 tests in 26.799s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_prospects.py` | `Ran 5 tests in 379.485s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_season.py` | `Ran 1 tests in 231.655s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_settings.py` | `Ran 10 tests in 43.374s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_signing.py` | `Ran 6 tests in 75.567s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_unicorn.py` | `Ran 18 tests in 19.752s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_upgrades.py` | `Ran 4 tests in 371.268s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_my_career_week.py` | `Ran 1 tests in 539.765s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py` | `Ran 388 tests in 2709.848s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_practice_reserves.py` | `Ran 9 tests in 33.615s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_roster_arena_growth.py` | `Ran 13 tests in 49.420s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_supersim.py` | `Ran 12 tests in 11.369s; OK` |
| `python3 tests/mod_editor/test_nfl2k5_supersim_live.py` | `Ran 34 tests in 3190.940s; OK` |
| `python3 tests/mod_editor/test_provider_integrity.py` | `Ran 7 tests in 14.181s; FAILED (failures=1), pending protected pin/count wiring` |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | `Ran 127 tests in 2206.297s; OK` |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | `Ran 115 tests in 1947.348s; OK` |

| MyPlayer | Saved choice | Hand-backs | Native menu opened | Snap / next Fast forward | Post-game Supersim / caller |
| --- | --- | ---: | --- | --- | --- |
| QB | You call every play | 2 | Yes | 14 / 8 updates | 2 / 0 |
| QB | By position | 2 | Yes | 14 / 8 updates | 2 / 1 |
| QB | Coach calls the plays | 2 | Coach call retained | 14 / 8 updates | 2 / 2 |
| HB | By position | 1 | Coach call retained | 14 / 8 updates | 2 / 1 |
| ILB | You call every play | 2 | Yes | 14 / 8 updates | 2 / 0 |
| ILB | By position | 2 | Yes | 14 / 8 updates | 2 / 1 |
| ILB | Coach calls the plays | 2 | Coach call retained | 14 / 8 updates | 2 / 2 |

Every hand-back in this table has native controller port 0 bound to MyPlayer.
Supersim value 2 is Fast forward; caller values are 0/1/2 as listed above.

Generation and measurement commands:

```sh
python3 tools/mycareer_mode/build_runtime.py --check
python3 tools/nfl2k5_my_career_assemble.py --check
PYTHONPATH=. python3 tools/mycareer_mode/measure_m3.py --output tools/mycareer_mode/b69_budget.json
PYTHONPATH=. python3 tools/mycareer_mode/refresh_gate_manifest.py \
  'extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --base-revision 922c009d --output .scratch/j3/verified-manifest.json
PYTHONPATH=. python3 tools/mycareer_mode/reproduce_b69_handback.py
PYTHONPATH=. MOD_STUDIO_NO_UPDATE_CHECK=1 python3 tools/mycareer_mode/verify_b69_provider_wiring.py
python3 packaging/repin.py --apply
git diff --check
```

Both generated-code checks passed. The scratch manifest conservatively adds
128 observed retail reservations; it does not claim a disc build. Root free
space showed `78G` in `df -h /`; no disc or large private input was copied. The existing `test_generic_disc_recipe_relocates_only_xbe_and_keeps_neighbour`
test is skipped by its unchanged guard: “100 GB root reserve plus bounded
fixture space required.” No other recorded suite has a skip. Registry schema validation passes with both proposed rows
sorted into the existing document; every new evidence/module path exists.
The full inherited evidence-file check stops at absent
`docs/research/apf_audio.md`, which must be provisioned during integration.
The unintegrated provider integrity suite fails its exact import closure
(`271 != 272`) because the new helper's pin and the count update belong to the
integration handoff. Applying exactly those two proposed changes in memory
passes all seven provider tests; `WIRING.md` specifies both.
This remains a pending integration check. The in-memory proof retains the
exact import-closure assertion and source-tampering refusals.

The beta-68 negative control, using `922c009d`'s actual writer and generated
runtime in the same b69 series, fails at the first returning caller predicate:
`first-play caller differs from saved policy`. Its trace includes the CPU
selector call and the subsequent call-complete bit. The final series retains
those native callees and asserts the corrected menu, selection, controller,
snap, next absent-unit acceleration and post-game words.

The old Supersim wiring regression expected bits 5 and 6 to be reserved.
Its refusal cases now cover caller value 3 and bit 7, while the new exhaustive
settings test validates all 72 valid combinations and native save/load. No
production failure is hidden by a new skip or an omitted frame phase.

Installed content is 20,168 bytes plus the 17-byte format tag in the
20,480-byte RX allocation: 295 bytes spare. Machine code is 15,792 bytes. Against
beta 68, content grows by 1,387 bytes and code by 884 bytes. The hand-back and caller policy alone add 424 RX content bytes (312 machine-code
bytes) over beta 68; prospect creation adds a further 963 content bytes
(572 machine-code bytes). Four new RW words use 16 bytes of existing spare state. **No allocation request, owner address,
peer allocation or executable file size changes.** The final budget receipt
is `tools/mycareer_mode/b69_budget.json`.

**Claude: regenerate the release/settings cave manifest.** The four local
gates use `.scratch/j3/verified-manifest.json`, produced from the pinned `922c009d`
parent plus observed owned writes, preserving every old reservation. It records
the changed MyCareer sources and the new prospect helper. It is explicitly not
a regenerated disc manifest. Protected manifest/GUI/registry/build/allowlist
files are left for integration. Provider pins are repinned before commits.

## Exact in-game witness scripts

andrethealchemist:

1. Build generic MyCareer with the integrated beta-69 owner. Load the career
   that reproduced the first-play issue. In Apartment Settings verify Fast
   forward and You call every play, then save and reload once.
2. Play MyPlayer's unit, let the other unit take possession and Fast forward.
   At the first returning scrimmage play, verify the native play-call screen
   appears before any snap and responds to the connected controller. Choose
   a visibly different play. Verify MyPlayer is controllable before the snap
   and through the play.
3. Repeat the other-unit Fast forward → returning-unit menu → choice → snap
   sequence a second time in the same game. Verify Fast forward re-arms on the
   next absent unit's snap after both hand-backs.
4. Press B during an absent-unit sequence. Verify it cancels that sequence,
   leaves the saved choice Fast forward, and resumes on the next CPU snap.
   Check the beta-68 PAT kick/two-point choice and the following kickoff too.
5. Finish the game. Apartment Settings must still read Fast forward and You
   call every play. Save, cold reload and check both words again. Record the
   Build summary, position, side, possession, chosen play and any failed step.

THE1WAM (with Noah for the public option commitment):

1. Use an offensive QB and HB, and defensive ILB/LB and CB. For each, choose
   You call every play, By position and Coach calls the plays in turn. Save
   and cold reload each value; change it once from the studio export too and
   confirm the in-game row matches, then change it in-game and read it in Studio.
2. For each value play a full possession, including its first play after the
   other unit's Fast forward. Default should show the normal play choice;
   By position should show it for QB/ILB and supply the coach's call for HB/CB;
   Coach should supply every call. In all cases verify movement/position input
   before the snap, native audibles where available, and control during the
   play. Verify another hand-back and unchanged settings after the game.
3. Create each tier through Studio and through the fifth in-game entry row.
   Complete CAP, inspect the final player card for 74/70/64/59, and inspect
   the initial depth place from the table. Include WR and CB special cases.
   Check Gunslinger/Pocket share native style 0, Scrambling is 1, Balanced is 2.
4. Save/reload, launch another fixture and check tier/place remain. Try the
   explicit Start MyPlayer action separately. Record any native depth sorting
   or roster-limit behavior. The career record/export must retain the tier's
   goal label. Do not expect Senior Bowl simulation, Combine/Pro Day drills,
   performance-point awards or Draft Advisory in this build.

## Commit delivery

The workspace's `.git` metadata and original branch ref are read-only in this
session. Commits therefore use writable private metadata at `.scratch/j3/delivery.git`,
with the worktree unchanged and the branch named `astra/b69-j3-mycareer`.
Commit `ed6b2a0c` contains the implementation; `5a2836dd` contains native proofs
and integration helpers. The final report/validation commit follows all four
green gates and a last repin. These three commits are delivered in
`ASTRA_J3.bundle`, based on `922c009d`. No push was attempted.

Claude can import the commits without depending on this private metadata:

```sh
git fetch /path/to/ASTRA_J3.bundle astra/b69-j3-mycareer
git log --oneline 922c009d..FETCH_HEAD
```

Apply the three commits in order to the integration stack, then complete WIRING
and regenerate the release/settings manifest. The original worktree branch
ref could not be moved under this session's filesystem restrictions.

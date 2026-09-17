# Beta 71.1 S10: native visibility correction; played root cause unresolved

**PROVED:** the sprite owner incorrectly treated pending event requests as draw visibility. The corrected owner uses native binding/slide visibility, including event fade-out. **The proposed lost draw-path clear is disproved in the bounded native sequence. This is a validated visibility correction, not proof that the persistent in-game blank label has been fixed.** The actual values in the witnessed blank frame remain unavailable. A history counterexample below prevents an unconditional claim that every pre-snap state must display down text in the current compact event layout.

Branch `astra/b71-s10-down-label-cause`, based on `a3f18036230e386c63b26ee7ec95606753d7eea8`. Commits use explicit file paths in `.scratch/astra-b71-s10.git`; the worktree's original Git administration and HEAD remain untouched. Bundle: `.scratch/astra-b71-s10.bundle`, with that S9 head as prerequisite. No push, emulator, GUI, network, disc build, retail mutation, full pack/disc copy or global process-name kill was performed. Heavy commands use `run_logged.py`: the child starts in a new session and its supervisor remains alive until the time/exit receipt is written. Scratch remained below 200 MB. No subagents were used.

Read: `ASTRA_CONTEXT.md`, `BETA71_TRIAGE.md`, S9's root report (retained in `reports/b71_s10/INHERITED_S9_REPORT.md`), the S5 report at `reports/b71_s6/INHERITED_ASTRA_REPORT.md`, `FABLE_B71_S8_REPORT_2026-09-16.md`, the C owner, Python dispatch/static writer, compiler, renderer and retained disassemblies. The specific S10 brief authorizes scorebug edits despite the older context's general exclusion. The supplied image names were absent from this worktree; their copies in `/home/noah/Desktop/2K5-8 Editors/beta71_evidence/` were inspected read-only. The local `disc_n_1.png` copy shows a kickoff formation; the other supplied capture clearly shows a blank plate at the line. This does not dismiss the pre-snap witness.

## A: every identified request writer, and why hiding a material does not lose a clear

USA XBE virtual addresses. The six element records have canonical origins `0xA959C8 + i*0x70`; their names/material names sit at origin minus 8/minus 4. Indices: 0 down, 1 play clock, 2 hang time, 3 FLAG, 4 ball-on, 5 FUMBLE. Score slabs have separate score-animation records at `0xA9594C` and `0xA95984`; they are not additional owners of these four event request words.

Full executable-section Capstone census plus unaligned raw-reference census: `writers.log`, `writer_references.json`, `scan_writers.py`. All direct request constants resolve into FC9C0. The only additional writers in the HUD's record aliases are the startup loop and timer loop below. This is an audit of the pinned executable and known record aliases, not a proof against arbitrary memory corruption.

| Word | Retail direct writer PCs | Condition / value |
|---|---|---|
| `A95AE0` hang time | `FCB14` | Sets 1 for play kind 10, subphase 14, no flag condition. |
| | `FCB2B` | Clears if the fumble slide is above its closed position in that path. |
| | `FCBA4`, `FCBEF` | Clear on the special kind-12 branch and general branch respectively. |
| `A95B50` FLAG | `FCACC` | Writes the computed boolean every nonzero game phase: play object `+160`, or valid nonempty `+90` record indicated by `+98`. Both absent writes zero. |
| `A95BC0` ball-on | `FCB67` | Clears on the kind-10/subphase-14 path. |
| | `FCBD0` | Sets 1 for kind 12, phase != 3, subphase 12/13, no flag. |
| | `FCC40` | Sets 1 when general down conditions permit and `BA2F14` is set, or recent histories differ during subphase 12/13. |
| | `FCC53` | Clears when those conditions do not request ball-on. |
| | `FCCBD` | Sets 1 when the final `ABE90` query is true. |
| `A95C30` FUMBLE | `FCC77` | Tentatively sets 1 in subphase 14 with the FLAG slide closed. |
| | `FCC7F` | Clears when that predicate fails or play object `+198` is zero. Early kind-10/kind-12 branches do not visit this writer. |
| `A95A00` down | `FCB37`, `FCC48` | Clear on the kind-10 live branch or failed general down predicate. |
| | `FCBAA`, `FCC28` | Set 1 on the eligible kind-12 or general scrimmage branch. |

General retail down predicate at `FCBDD..FCC48`: FLAG and FUMBLE slides are closed, `E602FC & 0x8000` is clear, game phase `E602B4 == 4`, subphase `E602B8 != 14`. The eligible kind-12 branch is an explicit exception. Phase zero returns before rewriting these words. Floating comparisons are executed natively in the sequence.

The shipped scorebar-v3 tail is also audited, not confused with retail. It binds `EBP=A95BB0` and keeps event semantics at relocated PCs:

| Word | Shipped PCs (value) |
|---|---|
| hang time | `FCAFB` (1); `FCB0F`, `FCB3C`, `FCB56` (0) |
| FLAG | `FCACA` (computed 0/1) |
| ball-on | `FCB15`, `FCBA4` (0); `FCB42`, `FCB9C`, `FCBD6` (1) |
| FUMBLE | `FCBBF` (1); `FCBC7` (0) |
| down | `FCBDC` (1 at the common nonzero-phase finalizer) |

See `disasm-shipped-visibility.log`. That existing static tail forces the middle's down/play-clock requests on; S10 does not change it.

Three common request-writing instructions apply to **all six** elements:

- `FCD5D`: startup initializes `[EDI+3C]` to zero (`EDI=A959C4+i*70`). This runs during scene binding. `FCD69/FCD77` set/clear binding availability from node/material lookup success.
- `FCEF6`: the update loop sets `[ECX-18]` to 1 while a timed request is active (`ECX=A95A18+i*70`) and the binding is available.
- `FCF19`: clears that request when elapsed time reaches the deadline; `FCF1C` clears the timer flag. `FC730` only schedules it, writing timer flag/elapsed/deadline at `FC739/FC743/FC74D`. No formatter or draw call is required.

The slide integration and material hidden-bit write at `FCF1F..FCF8C` consume the request. They run before the hooked FC9C0 call at `FCFA2`. Material hidden bits do **not** gate this update. Binding availability does gate the timer/integrator; all six bindings are available in the shipped-scene native sequence. Re-materialing hang time onto the spare slab preserves this path. `FC360` submits the scene and walks text elements but writes none of these request words. The formatters do not clear them either.

`timers_literals.json` executes native FC730/FCE70 for each of the six records and observes every timed request clear at `FCF19` **without any draw call**. `baseline_sequence.json` runs the pre-fix shipped scene/owner through kickoff, ball-on, pre-snap and flag: after the gameplay latch is cleared and native predicates stop requesting the event, the request words clear and down glyphs return. Therefore A's specific “hiding stopped a retail draw clear, causing a permanent stale request” mechanism is not reproduced and is inconsistent with the traced code.

`disc_n_native_bindings.json` independently repeats a bounded 225-frame sequence with **disc n's actual XBE, appended scene and textures**, read directly from its ISO without exporting those retail inputs. Its installed owner is byte-identical to the pinned S9 owner at its actual allocation; both hook targets are verified. Static HUD/widescreen replay is asserted byte-identical. The audit normalizes only those verified hooks in a validation copy; executed owner/hook bytes stay intact. All six bindings remain 1 throughout kickoff, ball-on, recovery, FLAG and recovery. Both pre-snap recoveries yield `[1,1,0,0,0,0]` and five white down glyphs. The first attempt was refused by the baseline harness's deliberate installed-hook guard; the corrected probe explicitly verifies the installed owner before using it. This proves that even disc n's actual hidden/re-materialed scene does not lose a draw-path clear under these inputs. It remains a HUD fixture with supplied world predicates, not captured gameplay.

## B: A95A00 is a request, not visibility

`A95A00` is down record `A959C8 + 38`, the requested target for the animation update. It is neither a material-hidden bit nor binding availability. Its writers are listed above. The binding is `A95A20` (`+58`); the current slide is float `A95A04` (`+3C`); closed is float `A959F4` (`+2C`); open is `A959F8` (`+30`). The callback is `A959CC` and material pointer is `A95A0C`.

The retail text draw gate at `FC3C0..FC3D5` checks binding availability and compares **current slide to closed position**, not the request. Its callback call is at `FC416`. The corrected regression observes entry to that actual native branch independently of the owner's code. The shipped static tail's `FCBDC` forces A95A00 to 1 in a nonzero phase, so a static override making it false cannot explain a normal phase-4 blank frame. No sprite setup/static override writes it to zero. Native startup, timer expiration, or phase-zero retention are distinct, documented cases. Hiding a material does not change A95A00.

## C: a missed history input, and the causal limit

`FC330` sets `BA2F14`; `FC340` clears it; setup `FC1B1` also clears it. Caller `A09F7` tail-calls FC330 when `[ESI+38] != [E60288]`; `9F4BA` tail-calls FC340 after its gameplay transition work. These calls are independent of the HUD draw path. The main sequence calls the real latch entry points, with the higher-level world scheduling explicitly outside the fixture.

There is a second ball-on source. `FCA4A..FCA7F` compares the two latest valid history records at `+20`. `A7940` reads the latest index from `B6FF64`; `A7970` checks the five-slot ring's sequence identity at `B6E7F0 + (index%5)*4B0` and returns its data at `+10`. Earlier previews replaced the history count with zero.

`history_probe.json` restores and executes the **real A7940/A7970 readers** with sampled ring entries. With different team values, a cleared BA2F14, phase 4/subphase 12, the shipped native path repeatedly yields `[1,1,0,0,1,0]`. FC360 enters both down and ball-on elements and formats `Ball at Midfield`. With equal history values, the requests become `[1,1,0,0,0,0]` and five down glyphs return. This is an omitted fixture input, not a lost clear. The snapshot field's actual values during the witnessed blank frame have not been supplied.

The native formatter produces `Pregame`/`Overtime` in phase 0, `Safety Kick` in 1, `Kickoff` in 2, `Point After` in 3, and `1st & 10` in phase 4. Non-down literals have no label tokens and deliberately emit no down glyphs. No alternate phase-4 literal was discovered; the numeric/Inches/GOAL sweep below exercises the real formatter. These observations do not prove that the witnessed game's phase was correct.

A separate pre-existing formatter limitation appeared in the initial sequence's default 13:10 clock: source 5 calls FC100, which returns an empty string for times >=600 seconds (`FC10B..FC138`); retail uses FC150 for that range. The final sequence uses a five-minute period matching the supplied capture. This observation is not a down-label cause and S10 does not alter the clock formatter.

**Root-cause status: UNPROVED for the persistent played symptom.** The old owner's request-based early return is a proved defect, but both a held latch and differing history entries also legitimately keep an event drawable. The corrected compact layout still prioritizes that visible event. It would be false to claim this change guarantees down text in every imaginable pre-snap state, or that it reproduces the witness of a blank plate with no event text. Resolving that remaining distinction needs the blank frame's phase/subphase, history indices/values, six requests/slides/bindings, native event draws, and live down quad colours/UVs. No speculative request clear or guessed phase timeout was added.

## Implemented correction

- `tools/scorebug_sprite/runtime.c`: `element_visible()` implements FC360's binding/current-slide gate. Its negated `<=` also retains the native unordered floating comparison behavior. Down uses its own computed visibility; event suppression uses the same computed gate for indices 2–5. The owner no longer reads the four event request words to decide down visibility and never clears gameplay requests.
- The compact layout keeps the S5 event replacement policy: drawable events occupy the down plate. Pending-but-closed or unavailable events no longer suppress it; closing events keep it hidden until their current slide is closed. This is deliberately distinguished from raw retail's ability to draw down and ball-on at separate positions.
- `mod_editor/core/nfl2k5_scorebug_sprite.py`: down's table visibility address changes from request `A95A00` to binding `A95A20`. The C slide check completes the native gate. Runtime revision becomes 10; generated engine and provider hashes are regenerated.
- S9 submission order, equal sprite depth, atlas/UVs, preview renderer, custom-layout ordering and layout JSON remain intact. The only scene byte change is its binding-address byte at `0x4244`.

The first candidate relied solely on event plates covering the down glyphs. A differential raster found 66 changed pixels underneath ball-on at 4:3 because the plate has translucent pixels. That candidate was corrected to use computed event visibility before the final owner commit. The first direct C-engine regression also exposed a test caller ABI mistake (cdecl arguments were not popped); its native caller was corrected. The failed logs remain in the ledger, along with the initially mistyped prepared-builder function-name check. The initial suite supervisor retains its nonzero aggregate result from the old C-caller test; the corrected final per-suite receipts are authoritative. Failed intermediate runs are not counted as passing validation.

## Final native sequence and images

`native_sequence.json`: one retained machine per aspect, 14 stages × 65 frames × two aspects = **1,820 native update frames**, with per-frame requests, slides, bindings, colours and request-writing PCs. No request/slide/binding/material/colour word is reset between stages. Native FC330/FC340 latch calls and sampled gameplay fields/predicate returns drive the transitions. This is a bounded HUD sequence, not a full kickoff/physics/AI simulation.

Sequence: kickoff/hang-time, ball-on, deliberately held-latch pre-snap counterexample, latch-clear recovery with downs 1–4, FLAG, recovery with downs 1–4, FUMBLE, recovery. On both aspects, settled event stages have zero label glyphs/pixels; recovery stages have five white glyphs. FC360's actual element branch and native event formatter output are captured. A differential raster removes only down colours and compares otherwise identical frames, establishing visible down contribution versus hidden event states. The history counterexample is retained separately, not silently converted into a passing pre-snap state.

| Stage | Requests [down,clock,hang,flag,ball,fumble] | Final down glyphs | Down pixels, 4:3 / 16:9 |
|---|---|---:|---:|
| kickoff | `[1, 1, 1, 0, 0, 0]` | 0 | 0 / 0 |
| ball_on | `[1, 1, 0, 0, 1, 0]` | 0 | 0 / 0 |
| latched_pre_snap | `[1, 1, 0, 0, 1, 0]` | 0 | 0 / 0 |
| after_kickoff_down_1 | `[1, 1, 0, 0, 0, 0]` | 5 | 343 / 263 |
| after_kickoff_down_2 | `[1, 1, 0, 0, 0, 0]` | 5 | 334 / 257 |
| after_kickoff_down_3 | `[1, 1, 0, 0, 0, 0]` | 5 | 342 / 260 |
| after_kickoff_down_4 | `[1, 1, 0, 0, 0, 0]` | 5 | 355 / 266 |
| flag | `[1, 1, 0, 1, 0, 0]` | 0 | 0 / 0 |
| after_flag_down_1 | `[1, 1, 0, 0, 0, 0]` | 5 | 343 / 263 |
| after_flag_down_2 | `[1, 1, 0, 0, 0, 0]` | 5 | 334 / 257 |
| after_flag_down_3 | `[1, 1, 0, 0, 0, 0]` | 5 | 342 / 260 |
| after_flag_down_4 | `[1, 1, 0, 0, 0, 0]` | 5 | 355 / 266 |
| fumble | `[1, 1, 0, 0, 0, 1]` | 0 | 0 / 0 |
| after_fumble | `[1, 1, 0, 0, 0, 0]` | 5 | 342 / 260 |

- [50-state contact sheet](reports/b71_s10/states_contact_sheet.png), regenerated with the final owner.
- [Post-kickoff 1st down, 4:3](reports/b71_s10/after_kickoff_down_1_43_display.png) / [16:9](reports/b71_s10/after_kickoff_down_1_169_display.png).
- [Post-FLAG 4th down, 4:3](reports/b71_s10/after_flag_down_4_43_display.png) / [16:9](reports/b71_s10/after_flag_down_4_169_display.png).
- [FLAG, 4:3](reports/b71_s10/flag_43_display.png) / [16:9](reports/b71_s10/flag_169_display.png).

The separate final sweep covers four downs × numeric distances 0–99 plus four GOAL states, at both aspects (808 states), using the native formatter and owner. `label_sweep.json`, `states.json` and `volume.json` retain receipts. CPU execution plus a software raster is **PROVED** within the stated fixture. Actual GPU behavior and the played fix are **UNWITNESSED**.

## Integration and prepared disc

**Both owner and scene bytes changed.** Owner RX allocation stays 4,096 bytes; RW stays 128 bytes. No new hook, allocation, literal, static XBE write site or reservation is introduced. The generated C engine and wrapper emission change; the scene's one-byte table change occurs at both aspects. All 34 texture chunks, raw material records, command descriptors/buffers, geometry, glyph metrics and S9 order remain identical to a3f18036. Appended resources remain 323,808 bytes, zero appended FONT, one 20,352-byte decoded scene and 47 quads. Exact hashes/ranges are in `scene_byte_audit.json`.

Owner `code_for(0,0)` before SHA-256: `3ac2cc0192032ad2b3b295e97ce0ad7a7c00a89807b2b95eb50ba71c6e8025f4`; after: `c6d5f106c5ab8adcb13b088b6aefe0b81361aa9e7e1cd0cb2c8207ca30b36165`. Changed owner bytes at this relocation: 1053.

`build_runtime.py --check` passes; toolchain versions are in `toolchain-gcc.log` and `toolchain-ld.log`. Compiler pins were regenerated; retained legacy compiler pins do not change. Provider hashes were updated with `packaging/repin.py --apply` before each code commit.

**Hotfix integration must regenerate the cave manifest and rerun the manifest/XBE memory-write/cave-reference/pairwise gates on the integrated tree.** S10 intentionally leaves the protected manifest unchanged. Its source-fingerprint audit reports changed runtime, sprite compiler and generated engine. This job does not claim those combined-tree gates passed. No capability row, protected GUI, build dispatcher or packaging-check edit was needed.

`reports/b71_s10/build_testdisc71.py` is prepared, AST/syntax checked, and **was not imported or run**. Its plan function is AST-identical to S9's, retaining Advanced plus scorebug/runtime, modern colour, modern Arrowhead and widescreen. Name: **NFL 2K5 MOD TEST 2026-09-16q (down label cause fix)**. The requested name does not change the evidence status: this is still a candidate with an unresolved played cause. Evidence paths use b71_s10. No disc/patch archive/build-folder operation occurred.

## Validation and command ledger

The table lists the latest result per standalone suite, including all scorebug/scorebar suites, the root layout/project suites, provider integrity, product catalog, phase1 packaging, build/Qt and allocator/space checks. Earlier runs importing the intermediate owner were rerun against final sources. Precise skips are retained in individual logs.

Latest suite results: 38 suites, 390 tests, 16 explicit skips; failed latest suites: [].

| Suite log | Tests | Skips | Seconds | Exit |
|---|---:|---:|---:|---:|
| [verified-test_apf_scorebug_workspace_qt](reports/b71_s10/verified-test_apf_scorebug_workspace_qt.log) | 11 | 0 | 0.713 | 0 |
| [final-test_build_panel_qt](reports/b71_s10/final-test_build_panel_qt.log) | 13 | 0 | 3.449 | 0 |
| [final-test_mod_build](reports/b71_s10/final-test_mod_build.log) | 13 | 0 | 2.265 | 0 |
| [final-test_nfl2k5_allocator_scaleout](reports/b71_s10/final-test_nfl2k5_allocator_scaleout.log) | 23 | 0 | 824.896 | 0 |
| [verified-test_nfl2k5_scorebar_rim](reports/b71_s10/verified-test_nfl2k5_scorebar_rim.log) | 8 | 0 | 13.614 | 0 |
| [verified-test_nfl2k5_scorebar_v3](reports/b71_s10/verified-test_nfl2k5_scorebar_v3.log) | 9 | 0 | 101.246 | 0 |
| [verified-test_nfl2k5_scorebug_assets](reports/b71_s10/verified-test_nfl2k5_scorebug_assets.log) | 8 | 1 | 148.794 | 0 |
| [verified-test_nfl2k5_scorebug_author](reports/b71_s10/verified-test_nfl2k5_scorebug_author.log) | 12 | 0 | 6.293 | 0 |
| [down-sequence-clock-fixture-final](reports/b71_s10/down-sequence-clock-fixture-final.log) | 2 | 0 | 39.72 | 0 |
| [verified-test_nfl2k5_scorebug_draw_order](reports/b71_s10/verified-test_nfl2k5_scorebug_draw_order.log) | 5 | 0 | 26.715 | 0 |
| [verified-test_nfl2k5_scorebug_exact](reports/b71_s10/verified-test_nfl2k5_scorebug_exact.log) | 8 | 0 | 86.885 | 0 |
| [verified-test_nfl2k5_scorebug_fonts](reports/b71_s10/verified-test_nfl2k5_scorebug_fonts.log) | 10 | 5 | 8.76 | 0 |
| [verified-test_nfl2k5_scorebug_freeze](reports/b71_s10/verified-test_nfl2k5_scorebug_freeze.log) | 7 | 0 | 241.783 | 0 |
| [verified-test_nfl2k5_scorebug_freeze_v2](reports/b71_s10/verified-test_nfl2k5_scorebug_freeze_v2.log) | 7 | 0 | 328.645 | 0 |
| [verified-test_nfl2k5_scorebug_ingame](reports/b71_s10/verified-test_nfl2k5_scorebug_ingame.log) | 11 | 0 | 15.591 | 0 |
| [final-test_nfl2k5_scorebug_ingame_fix](reports/b71_s10/final-test_nfl2k5_scorebug_ingame_fix.log) | 9 | 0 | 127.311 | 0 |
| [final-test_nfl2k5_scorebug_mnf](reports/b71_s10/final-test_nfl2k5_scorebug_mnf.log) | 10 | 0 | 11.969 | 0 |
| [final-test_nfl2k5_scorebug_mnf_v3](reports/b71_s10/final-test_nfl2k5_scorebug_mnf_v3.log) | 7 | 0 | 48.931 | 0 |
| [final-test_nfl2k5_scorebug_native](reports/b71_s10/final-test_nfl2k5_scorebug_native.log) | 4 | 0 | 132.302 | 0 |
| [final-test_nfl2k5_scorebug_projection](reports/b71_s10/final-test_nfl2k5_scorebug_projection.log) | 14 | 0 | 56.54 | 0 |
| [final-test_nfl2k5_scorebug_resources](reports/b71_s10/final-test_nfl2k5_scorebug_resources.log) | 6 | 0 | 298.602 | 0 |
| [final-test_nfl2k5_scorebug_runtime](reports/b71_s10/final-test_nfl2k5_scorebug_runtime.log) | 12 | 0 | 121.569 | 0 |
| [final-test_nfl2k5_scorebug_source_art](reports/b71_s10/final-test_nfl2k5_scorebug_source_art.log) | 13 | 3 | 0.467 | 0 |
| [final-test_nfl2k5_scorebug_sprite](reports/b71_s10/final-test_nfl2k5_scorebug_sprite.log) | 19 | 0 | 95.507 | 0 |
| [final-test_nfl2k5_scorebug_template](reports/b71_s10/final-test_nfl2k5_scorebug_template.log) | 19 | 0 | 9.829 | 0 |
| [final-test_nfl2k5_scorebug_template_release](reports/b71_s10/final-test_nfl2k5_scorebug_template_release.log) | 5 | 0 | 0.556 | 0 |
| [final-test_nfl2k5_scorebug_unified_adapter](reports/b71_s10/final-test_nfl2k5_scorebug_unified_adapter.log) | 5 | 0 | 0.168 | 0 |
| [final-test_nfl2k5_scorebug_v10_ingame](reports/b71_s10/final-test_nfl2k5_scorebug_v10_ingame.log) | 11 | 0 | 9.219 | 0 |
| [final-test_nfl2k5_scorebug_v10_projection](reports/b71_s10/final-test_nfl2k5_scorebug_v10_projection.log) | 14 | 0 | 29.536 | 0 |
| [final-test_nfl2k5_scorebug_versions](reports/b71_s10/final-test_nfl2k5_scorebug_versions.log) | 4 | 0 | 9.757 | 0 |
| [final-test_nfl2k5_xbe_space](reports/b71_s10/final-test_nfl2k5_xbe_space.log) | 13 | 1 | 34.619 | 0 |
| [final-test_phase1_packaging](reports/b71_s10/final-test_phase1_packaging.log) | 23 | 0 | 2.177 | 0 |
| [final-test_product_catalog](reports/b71_s10/final-test_product_catalog.log) | 9 | 0 | 0.163 | 0 |
| [final-test_provider_integrity](reports/b71_s10/final-test_provider_integrity.log) | 8 | 0 | 10.451 | 0 |
| [final-test_scorebug_sprite_preview_qt](reports/b71_s10/final-test_scorebug_sprite_preview_qt.log) | 2 | 0 | 23.14 | 0 |
| [final-test_scorebug_studio_panel_qt](reports/b71_s10/final-test_scorebug_studio_panel_qt.log) | 11 | 0 | 7.445 | 0 |
| [final-nfl2k5_scorebug_layout_test](reports/b71_s10/final-nfl2k5_scorebug_layout_test.log) | 15 | 6 | 1.45 | 0 |
| [final-nfl2k5_scorebug_mod_project_test](reports/b71_s10/final-nfl2k5_scorebug_mod_project_test.log) | 10 | 0 | 1.389 | 0 |

Exact persisted experiment/check/commit commands follow, with UTC start, elapsed seconds, exit code and full logs. `commands.json` additionally records UTC end times and argv arrays. Exploratory navigation/read commands at session start were not separately timed; no fabricated timings are supplied. The initial un-supervised detached launch did not survive its sandbox session; the writer census was rerun under the retained supervisor and has a complete receipt.

| UTC start | Seconds | Exit | Command | Log |
|---|---:|---:|---|---|
| 2026-09-17T00:05:28.223044+00:00 | 0.725 | 0 | `python3 reports/b71_s9/disassemble.py fc9c0:fcfba fc190:fc200 fbd00:fc010` | [disasm-update](reports/b71_s10/disasm-update.log) |
| 2026-09-17T00:05:58.045864+00:00 | 0.23 | 0 | `python3 reports/b71_s9/disassemble.py fcfa7:fd500` | [disasm-tail](reports/b71_s10/disasm-tail.log) |
| 2026-09-17T00:06:23.817257+00:00 | 13.422 | 0 | `python3 reports/b71_s10/scan_writers.py` | [writers](reports/b71_s10/writers.log) |
| 2026-09-17T00:07:06.536441+00:00 | 0.231 | 0 | `python3 reports/b71_s9/disassemble.py fc330:fc360` | [disasm-latch](reports/b71_s10/disasm-latch.log) |
| 2026-09-17T00:07:35.411018+00:00 | 21.717 | 0 | `python3 reports/b71_s10/scan_calls.py` | [callers](reports/b71_s10/callers.log) |
| 2026-09-17T00:07:36.590956+00:00 | 30.198 | 0 | `python3 reports/b71_s10/probe_sequence.py` | [baseline-sequence](reports/b71_s10/baseline-sequence.log) |
| 2026-09-17T00:07:54.893855+00:00 | 0.231 | 0 | `python3 reports/b71_s9/disassemble.py 9f410:9f4d0 a0980:a0a10 fc700:fc760` | [disasm-event-calls](reports/b71_s10/disasm-event-calls.log) |
| 2026-09-17T00:08:32.029530+00:00 | 0.233 | 0 | `python3 reports/b71_s9/disassemble.py 9f200:9f410` | [disasm-latch-context](reports/b71_s10/disasm-latch-context.log) |
| 2026-09-17T00:08:47.043499+00:00 | 31.681 | 0 | `python3 reports/b71_s10/probe_bindings.py` | [bindings](reports/b71_s10/bindings.log) |
| 2026-09-17T00:11:07.501099+00:00 | 0.108 | 0 | `python3 tools/scorebug_sprite/build_runtime.py` | [build-owner](reports/b71_s10/build-owner.log) |
| 2026-09-17T00:11:07.637104+00:00 | 0.105 | 0 | `python3 tools/scorebug_sprite/build_runtime.py --check` | [owner-reproducible](reports/b71_s10/owner-reproducible.log) |
| 2026-09-17T00:11:07.769458+00:00 | 20.832 | 0 | `python3 packaging/repin.py --apply` | [repin-first](reports/b71_s10/repin-first.log) |
| 2026-09-17T00:11:20.450445+00:00 | 37.963 | 0 | `python3 reports/b71_s10/regenerate_pins.py` | [compiler-pins](reports/b71_s10/compiler-pins.log) |
| 2026-09-17T00:11:21.596848+00:00 | 770.697 | 0 | `python3 reports/b71_s10/prove_states.py` | [prove-states](reports/b71_s10/prove-states.log) |
| 2026-09-17T00:12:48.677024+00:00 | 36.362 | 1 | `python3 tests/mod_editor/test_nfl2k5_scorebug_down_visibility.py -v` | [down-visibility](reports/b71_s10/down-visibility.log) |
| 2026-09-17T00:12:57.276022+00:00 | 1468.005 | 1 | `python3 reports/b71_s10/run_final_suites.py` | [all-suites](reports/b71_s10/all-suites.log) |
| 2026-09-17T00:12:57.310867+00:00 | 1.404 | 0 | `python3 tests/mod_editor/test_apf_scorebug_workspace_qt.py -v` | [final-test_apf_scorebug_workspace_qt](reports/b71_s10/final-test_apf_scorebug_workspace_qt.log) |
| 2026-09-17T00:12:57.311402+00:00 | 13.754 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebar_rim.py -v` | [final-test_nfl2k5_scorebar_rim](reports/b71_s10/final-test_nfl2k5_scorebar_rim.log) |
| 2026-09-17T00:12:57.311965+00:00 | 98.191 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebar_v3.py -v` | [final-test_nfl2k5_scorebar_v3](reports/b71_s10/final-test_nfl2k5_scorebar_v3.log) |
| 2026-09-17T00:12:58.714986+00:00 | 148.685 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_assets.py -v` | [final-test_nfl2k5_scorebug_assets](reports/b71_s10/final-test_nfl2k5_scorebug_assets.log) |
| 2026-09-17T00:13:11.065448+00:00 | 6.325 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_author.py -v` | [final-test_nfl2k5_scorebug_author](reports/b71_s10/final-test_nfl2k5_scorebug_author.log) |
| 2026-09-17T00:13:17.391122+00:00 | 36.107 | 1 | `python3 tests/mod_editor/test_nfl2k5_scorebug_down_visibility.py -v` | [final-test_nfl2k5_scorebug_down_visibility](reports/b71_s10/final-test_nfl2k5_scorebug_down_visibility.log) |
| 2026-09-17T00:13:53.498820+00:00 | 25.888 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_draw_order.py -v` | [final-test_nfl2k5_scorebug_draw_order](reports/b71_s10/final-test_nfl2k5_scorebug_draw_order.log) |
| 2026-09-17T00:14:02.040102+00:00 | 26.062 | 1 | `python3 reports/b71_s10/prove_sequence.py` | [native-sequence](reports/b71_s10/native-sequence.log) |
| 2026-09-17T00:14:19.386803+00:00 | 84.595 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_exact.py -v` | [final-test_nfl2k5_scorebug_exact](reports/b71_s10/final-test_nfl2k5_scorebug_exact.log) |
| 2026-09-17T00:14:23.553599+00:00 | 39.807 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_down_visibility.py -v` | [down-visibility-corrected](reports/b71_s10/down-visibility-corrected.log) |
| 2026-09-17T00:14:35.503606+00:00 | 8.588 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_fonts.py -v` | [final-test_nfl2k5_scorebug_fonts](reports/b71_s10/final-test_nfl2k5_scorebug_fonts.log) |
| 2026-09-17T00:14:44.091381+00:00 | 243.036 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_freeze.py -v` | [final-test_nfl2k5_scorebug_freeze](reports/b71_s10/final-test_nfl2k5_scorebug_freeze.log) |
| 2026-09-17T00:14:58.367540+00:00 | 18.785 | 0 | `python3 reports/b71_s10/audit_scene_bytes.py` | [byte-audit](reports/b71_s10/byte-audit.log) |
| 2026-09-17T00:15:27.400701+00:00 | 326.935 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_freeze_v2.py -v` | [final-test_nfl2k5_scorebug_freeze_v2](reports/b71_s10/final-test_nfl2k5_scorebug_freeze_v2.log) |
| 2026-09-17T00:15:43.982542+00:00 | 14.698 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_ingame.py -v` | [final-test_nfl2k5_scorebug_ingame](reports/b71_s10/final-test_nfl2k5_scorebug_ingame.log) |
| 2026-09-17T00:15:48.082028+00:00 | 0.115 | 0 | `python3 tools/scorebug_sprite/build_runtime.py` | [build-owner-final](reports/b71_s10/build-owner-final.log) |
| 2026-09-17T00:15:48.225659+00:00 | 0.113 | 0 | `python3 tools/scorebug_sprite/build_runtime.py --check` | [owner-reproducible-final](reports/b71_s10/owner-reproducible-final.log) |
| 2026-09-17T00:15:48.388411+00:00 | 21.146 | 0 | `python3 packaging/repin.py --apply` | [repin-visibility-final](reports/b71_s10/repin-visibility-final.log) |
| 2026-09-17T00:15:58.680783+00:00 | 127.311 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_ingame_fix.py -v` | [final-test_nfl2k5_scorebug_ingame_fix](reports/b71_s10/final-test_nfl2k5_scorebug_ingame_fix.log) |
| 2026-09-17T00:16:34.022129+00:00 | 38.312 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_down_visibility.py -v` | [down-visibility-final](reports/b71_s10/down-visibility-final.log) |
| 2026-09-17T00:16:35.170532+00:00 | 126.141 | 0 | `python3 reports/b71_s10/prove_sequence.py` | [native-sequence-final](reports/b71_s10/native-sequence-final.log) |
| 2026-09-17T00:16:36.336998+00:00 | 18.855 | 0 | `python3 reports/b71_s10/audit_scene_bytes.py` | [byte-audit-final](reports/b71_s10/byte-audit-final.log) |
| 2026-09-17T00:17:23.672975+00:00 | 20.229 | 0 | `python3 reports/b71_s10/probe_timers_literals.py` | [timers-literals](reports/b71_s10/timers-literals.log) |
| 2026-09-17T00:17:41.905320+00:00 | 11.004 | 0 | `python3 packaging/repin.py --apply` | [repin-before-code-commit](reports/b71_s10/repin-before-code-commit.log) |
| 2026-09-17T00:17:52.941604+00:00 | 0.073 | 0 | `git --git-dir=.scratch/astra-b71-s10.git --work-tree=. commit -m 'Gate sprite down glyphs on native element visibility' -- tools/scorebug_sprite/runtime.c mod_editor/core/nfl2k5_scorebug_runtime.py mod_editor/core/nfl2k5_scorebug_sprite.py mod_editor/core/nfl2k5_scorebug_sprite_code.py mod_editor/core/providers.py tests/mod_editor/test_nfl2k5_scorebug_down_visibility.py docs/mod_editor/sprite_scorebug.md docs/mod_editor/2k5_mod_studio_changelog.md` | [commit-code](reports/b71_s10/commit-code.log) |
| 2026-09-17T00:18:05.992256+00:00 | 11.969 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_mnf.py -v` | [final-test_nfl2k5_scorebug_mnf](reports/b71_s10/final-test_nfl2k5_scorebug_mnf.log) |
| 2026-09-17T00:18:17.961418+00:00 | 48.931 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_mnf_v3.py -v` | [final-test_nfl2k5_scorebug_mnf_v3](reports/b71_s10/final-test_nfl2k5_scorebug_mnf_v3.log) |
| 2026-09-17T00:18:26.384579+00:00 | 0.235 | 0 | `python3 reports/b71_s9/disassemble.py a7900:a79e0` | [disasm-history](reports/b71_s10/disasm-history.log) |
| 2026-09-17T00:18:47.128117+00:00 | 132.302 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_native.py -v` | [final-test_nfl2k5_scorebug_native](reports/b71_s10/final-test_nfl2k5_scorebug_native.log) |
| 2026-09-17T00:18:53.989995+00:00 | 0.244 | 0 | `python3 reports/b71_s9/disassemble.py a73b0:a7940` | [disasm-history-write](reports/b71_s10/disasm-history-write.log) |
| 2026-09-17T00:19:06.893029+00:00 | 56.54 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_projection.py -v` | [final-test_nfl2k5_scorebug_projection](reports/b71_s10/final-test_nfl2k5_scorebug_projection.log) |
| 2026-09-17T00:19:41.118194+00:00 | 25.084 | 0 | `python3 reports/b71_s10/probe_history.py` | [history-probe](reports/b71_s10/history-probe.log) |
| 2026-09-17T00:19:42.308202+00:00 | 0.099 | 1 | `python3 reports/b71_s10/verify_prepared_disc.py` | [prepared-disc](reports/b71_s10/prepared-disc.log) |
| 2026-09-17T00:20:03.433866+00:00 | 298.602 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_resources.py -v` | [final-test_nfl2k5_scorebug_resources](reports/b71_s10/final-test_nfl2k5_scorebug_resources.log) |
| 2026-09-17T00:20:08.504653+00:00 | 0.03 | 0 | `python3 reports/b71_s10/verify_prepared_disc.py` | [prepared-disc-final](reports/b71_s10/prepared-disc-final.log) |
| 2026-09-17T00:20:08.563644+00:00 | 771.702 | 0 | `python3 reports/b71_s10/prove_states.py` | [prove-states-final](reports/b71_s10/prove-states-final.log) |
| 2026-09-17T00:20:39.871035+00:00 | 478.194 | 0 | `python3 reports/b71_s10/rerun_final_sources.py` | [final-source-reruns](reports/b71_s10/final-source-reruns.log) |
| 2026-09-17T00:20:39.904590+00:00 | 0.713 | 0 | `python3 tests/mod_editor/test_apf_scorebug_workspace_qt.py -v` | [verified-test_apf_scorebug_workspace_qt](reports/b71_s10/verified-test_apf_scorebug_workspace_qt.log) |
| 2026-09-17T00:20:39.904931+00:00 | 13.614 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebar_rim.py -v` | [verified-test_nfl2k5_scorebar_rim](reports/b71_s10/verified-test_nfl2k5_scorebar_rim.log) |
| 2026-09-17T00:20:39.905480+00:00 | 101.246 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebar_v3.py -v` | [verified-test_nfl2k5_scorebar_v3](reports/b71_s10/verified-test_nfl2k5_scorebar_v3.log) |
| 2026-09-17T00:20:40.618413+00:00 | 148.794 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_assets.py -v` | [verified-test_nfl2k5_scorebug_assets](reports/b71_s10/verified-test_nfl2k5_scorebug_assets.log) |
| 2026-09-17T00:20:53.519617+00:00 | 6.293 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_author.py -v` | [verified-test_nfl2k5_scorebug_author](reports/b71_s10/verified-test_nfl2k5_scorebug_author.log) |
| 2026-09-17T00:20:54.335895+00:00 | 121.569 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_runtime.py -v` | [final-test_nfl2k5_scorebug_runtime](reports/b71_s10/final-test_nfl2k5_scorebug_runtime.log) |
| 2026-09-17T00:20:59.430645+00:00 | 0.467 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_source_art.py -v` | [final-test_nfl2k5_scorebug_source_art](reports/b71_s10/final-test_nfl2k5_scorebug_source_art.log) |
| 2026-09-17T00:20:59.812883+00:00 | 39.637 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_down_visibility.py -v` | [verified-test_nfl2k5_scorebug_down_visibility](reports/b71_s10/verified-test_nfl2k5_scorebug_down_visibility.log) |
| 2026-09-17T00:20:59.897774+00:00 | 95.507 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_sprite.py -v` | [final-test_nfl2k5_scorebug_sprite](reports/b71_s10/final-test_nfl2k5_scorebug_sprite.log) |
| 2026-09-17T00:21:39.449856+00:00 | 26.715 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_draw_order.py -v` | [verified-test_nfl2k5_scorebug_draw_order](reports/b71_s10/verified-test_nfl2k5_scorebug_draw_order.log) |
| 2026-09-17T00:22:06.165174+00:00 | 86.885 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_exact.py -v` | [verified-test_nfl2k5_scorebug_exact](reports/b71_s10/verified-test_nfl2k5_scorebug_exact.log) |
| 2026-09-17T00:22:13.497617+00:00 | 0.154 | 0 | `python3 reports/b71_s10/disassemble_shipped_visibility.py` | [disasm-shipped-visibility](reports/b71_s10/disasm-shipped-visibility.log) |
| 2026-09-17T00:22:21.152179+00:00 | 8.76 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_fonts.py -v` | [verified-test_nfl2k5_scorebug_fonts](reports/b71_s10/verified-test_nfl2k5_scorebug_fonts.log) |
| 2026-09-17T00:22:29.912293+00:00 | 241.783 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_freeze.py -v` | [verified-test_nfl2k5_scorebug_freeze](reports/b71_s10/verified-test_nfl2k5_scorebug_freeze.log) |
| 2026-09-17T00:22:35.404844+00:00 | 9.829 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_template.py -v` | [final-test_nfl2k5_scorebug_template](reports/b71_s10/final-test_nfl2k5_scorebug_template.log) |
| 2026-09-17T00:22:45.234509+00:00 | 0.556 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_template_release.py -v` | [final-test_nfl2k5_scorebug_template_release](reports/b71_s10/final-test_nfl2k5_scorebug_template_release.log) |
| 2026-09-17T00:22:45.791046+00:00 | 0.168 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_unified_adapter.py -v` | [final-test_nfl2k5_scorebug_unified_adapter](reports/b71_s10/final-test_nfl2k5_scorebug_unified_adapter.log) |
| 2026-09-17T00:22:45.959504+00:00 | 9.219 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_v10_ingame.py -v` | [final-test_nfl2k5_scorebug_v10_ingame](reports/b71_s10/final-test_nfl2k5_scorebug_v10_ingame.log) |
| 2026-09-17T00:22:55.178588+00:00 | 29.536 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_v10_projection.py -v` | [final-test_nfl2k5_scorebug_v10_projection](reports/b71_s10/final-test_nfl2k5_scorebug_v10_projection.log) |
| 2026-09-17T00:22:55.905388+00:00 | 9.757 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_versions.py -v` | [final-test_nfl2k5_scorebug_versions](reports/b71_s10/final-test_nfl2k5_scorebug_versions.log) |
| 2026-09-17T00:23:04.933530+00:00 | 39.727 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_down_visibility.py -v` | [down-gate-transitions-final](reports/b71_s10/down-gate-transitions-final.log) |
| 2026-09-17T00:23:05.662234+00:00 | 23.14 | 0 | `python3 tests/mod_editor/test_scorebug_sprite_preview_qt.py -v` | [final-test_scorebug_sprite_preview_qt](reports/b71_s10/final-test_scorebug_sprite_preview_qt.log) |
| 2026-09-17T00:23:06.134849+00:00 | 0.002 | 0 | `gcc --version` | [toolchain-gcc](reports/b71_s10/toolchain-gcc.log) |
| 2026-09-17T00:23:06.172226+00:00 | 0.007 | 0 | `ld --version` | [toolchain-ld](reports/b71_s10/toolchain-ld.log) |
| 2026-09-17T00:23:06.207628+00:00 | 0.221 | 0 | `python3 -c 'from mod_editor.core import nfl2k5_scorebug_runtime as r, nfl2k5_scorebug_sprite_code as e; c,l=r.code_for(0,0); print(dict(allocation=len(c),data=r.DATA_SIZE,engine=len(e.CODE),last_entry=l["update"],revision=r.REVISION))'` | [owner-size](reports/b71_s10/owner-size.log) |
| 2026-09-17T00:23:09.412343+00:00 | 328.645 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_freeze_v2.py -v` | [verified-test_nfl2k5_scorebug_freeze_v2](reports/b71_s10/verified-test_nfl2k5_scorebug_freeze_v2.log) |
| 2026-09-17T00:23:24.715385+00:00 | 7.445 | 0 | `python3 tests/mod_editor/test_scorebug_studio_panel_qt.py -v` | [final-test_scorebug_studio_panel_qt](reports/b71_s10/final-test_scorebug_studio_panel_qt.log) |
| 2026-09-17T00:23:28.802991+00:00 | 1.45 | 0 | `python3 tests/nfl2k5_scorebug_layout_test.py -v` | [final-nfl2k5_scorebug_layout_test](reports/b71_s10/final-nfl2k5_scorebug_layout_test.log) |
| 2026-09-17T00:23:30.252964+00:00 | 1.389 | 0 | `python3 tests/nfl2k5_scorebug_mod_project_test.py -v` | [final-nfl2k5_scorebug_mod_project_test](reports/b71_s10/final-nfl2k5_scorebug_mod_project_test.log) |
| 2026-09-17T00:23:31.642412+00:00 | 10.451 | 0 | `python3 tests/mod_editor/test_provider_integrity.py -v` | [final-test_provider_integrity](reports/b71_s10/final-test_provider_integrity.log) |
| 2026-09-17T00:23:32.160621+00:00 | 0.163 | 0 | `python3 tests/mod_editor/test_product_catalog.py -v` | [final-test_product_catalog](reports/b71_s10/final-test_product_catalog.log) |
| 2026-09-17T00:23:32.324015+00:00 | 2.177 | 0 | `python3 tests/mod_editor/test_phase1_packaging.py -v` | [final-test_phase1_packaging](reports/b71_s10/final-test_phase1_packaging.log) |
| 2026-09-17T00:23:33.050370+00:00 | 15.591 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_ingame.py -v` | [verified-test_nfl2k5_scorebug_ingame](reports/b71_s10/verified-test_nfl2k5_scorebug_ingame.log) |
| 2026-09-17T00:23:34.501918+00:00 | 2.265 | 0 | `python3 tests/mod_editor/test_mod_build.py -v` | [final-test_mod_build](reports/b71_s10/final-test_mod_build.log) |
| 2026-09-17T00:23:36.766978+00:00 | 3.449 | 0 | `python3 tests/mod_editor/test_build_panel_qt.py -v` | [final-test_build_panel_qt](reports/b71_s10/final-test_build_panel_qt.log) |
| 2026-09-17T00:23:40.216236+00:00 | 824.896 | 0 | `python3 tests/mod_editor/test_nfl2k5_allocator_scaleout.py -v` | [final-test_nfl2k5_allocator_scaleout](reports/b71_s10/final-test_nfl2k5_allocator_scaleout.log) |
| 2026-09-17T00:23:42.094217+00:00 | 34.619 | 0 | `python3 tests/mod_editor/test_nfl2k5_xbe_space.py -v` | [final-test_nfl2k5_xbe_space](reports/b71_s10/final-test_nfl2k5_xbe_space.log) |
| 2026-09-17T00:23:44.694124+00:00 | 11.689 | 0 | `python3 packaging/repin.py --apply` | [repin-before-regression-commit](reports/b71_s10/repin-before-regression-commit.log) |
| 2026-09-17T00:23:56.412754+00:00 | 0.044 | 0 | `git --git-dir=.scratch/astra-b71-s10.git --work-tree=. commit -m 'Cover pending, closing and unavailable native event elements' -- tests/mod_editor/test_nfl2k5_scorebug_down_visibility.py` | [commit-regression](reports/b71_s10/commit-regression.log) |
| 2026-09-17T00:26:59.511201+00:00 | 0.15 | 0 | `python3 -m mod_editor.capabilities.validate_registry` | [registry-strict-early](reports/b71_s10/registry-strict-early.log) |
| 2026-09-17T00:26:59.756956+00:00 | 0.02 | 0 | `git --git-dir=.scratch/astra-b71-s10.git --work-tree=. diff a3f18036 --check` | [diff-check](reports/b71_s10/diff-check.log) |
| 2026-09-17T00:29:29.279959+00:00 | 0.041 | 0 | `python3 -c 'import ast; from pathlib import Path; files=list(Path("reports/b71_s10").glob("*.py")); [ast.parse(p.read_text(),filename=str(p)) for p in files]; print(len(files), "report scripts parsed; prepared disc not imported")'` | [report-script-syntax](reports/b71_s10/report-script-syntax.log) |
| 2026-09-17T00:29:29.350636+00:00 | 0.057 | 0 | `python3 reports/b71_s10/write_report.py` | [partial-report](reports/b71_s10/partial-report.log) |
| 2026-09-17T00:30:03.344734+00:00 | 0.244 | 0 | `python3 reports/b71_s9/disassemble.py fc100:fc190` | [disasm-clock](reports/b71_s10/disasm-clock.log) |
| 2026-09-17T00:30:29.690892+00:00 | 39.72 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_down_visibility.py -v` | [down-sequence-clock-fixture-final](reports/b71_s10/down-sequence-clock-fixture-final.log) |
| 2026-09-17T00:30:30.862967+00:00 | 132.104 | 0 | `python3 reports/b71_s10/prove_sequence.py` | [native-sequence-clock-fixture-final](reports/b71_s10/native-sequence-clock-fixture-final.log) |
| 2026-09-17T00:31:09.440215+00:00 | 10.803 | 0 | `python3 packaging/repin.py --apply` | [repin-before-clock-fixture-commit](reports/b71_s10/repin-before-clock-fixture-commit.log) |
| 2026-09-17T00:31:20.274157+00:00 | 0.043 | 0 | `git --git-dir=.scratch/astra-b71-s10.git --work-tree=. commit -m 'Use the witnessed five-minute period in the native sequence fixture' -- tests/mod_editor/test_nfl2k5_scorebug_down_visibility.py` | [commit-clock-fixture](reports/b71_s10/commit-clock-fixture.log) |
| 2026-09-17T00:32:11.096851+00:00 | 12.717 | 0 | `python3 reports/b71_s10/scan_writers.py` | [writers-final](reports/b71_s10/writers-final.log) |
| 2026-09-17T00:33:07.571794+00:00 | 31.483 | 0 | `python3 reports/b71_s10/probe_sequence.py` | [baseline-sequence-pinned](reports/b71_s10/baseline-sequence-pinned.log) |
| 2026-09-17T00:36:44.485558+00:00 | 13.778 | 1 | `python3 reports/b71_s10/probe_disc_n_bindings.py` | [disc-n-native-bindings](reports/b71_s10/disc-n-native-bindings.log) |
| 2026-09-17T00:37:25.113317+00:00 | 0.157 | 0 | `python3 -m mod_editor.capabilities.validate_registry` | [registry-strict](reports/b71_s10/registry-strict.log) |
| 2026-09-17T00:40:23.206956+00:00 | 20.254 | 0 | `python3 reports/b71_s10/probe_disc_n_bindings.py` | [disc-n-native-bindings-final](reports/b71_s10/disc-n-native-bindings-final.log) |
| 2026-09-17T00:40:24.371059+00:00 | 0.065 | 0 | `python3 reports/b71_s10/check_delivery_inputs.py` | [delivery-inputs-final](reports/b71_s10/delivery-inputs-final.log) |
| 2026-09-17T00:41:21.872525+00:00 | 22.468 | 0 | `python3 reports/b71_s10/probe_disc_n_bindings.py` | [disc-n-native-bindings-verified](reports/b71_s10/disc-n-native-bindings-verified.log) |
| 2026-09-17T00:41:46.114959+00:00 | 0.061 | 0 | `python3 reports/b71_s10/write_report.py` | [final-report](reports/b71_s10/final-report.log) |
| 2026-09-17T00:42:38.913396+00:00 | 0.057 | 0 | `python3 reports/b71_s10/check_delivery_inputs.py` | [delivery-inputs-verified](reports/b71_s10/delivery-inputs-verified.log) |

Final evidence/report commits and bundle creation/verification are recorded in `.scratch/delivery_commands.json` and `.scratch/delivery.json`, so the report does not contain its own commit or bundle hash. The delivery performs an independent fetch into another private Git directory and checks that its head equals the delivered branch.

## Remaining witness / unresolved requirement

Do not mark the sustained played-game missing-label cause solved from this bundle. The native sequence proves request clearing and the corrected computed-visibility contract, but it does not prove the unknown live inputs of the reported frame. In particular, a valid visible ball-on event can coexist with retail down visibility during pre-snap; the compact replacement layout intentionally prioritizes that event. Thus the brief's unconditional “label visible on every pre-snap down” is **not proved** for all native inputs. The history probe is the concrete counterexample. A captured blank-frame state or a separately specified change to that event replacement policy is required to close the causal gap. No emulator was opened to manufacture a witness.

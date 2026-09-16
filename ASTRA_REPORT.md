# Beta 71.1 S9: sprite down-label investigation and ordering candidate

The compiler and preview now use explicit submission order for overlapping sprite layers. **The proposed plate-over-label cause is disproved for the supplied release scene in the bounded native trace. The missing label witnessed in game remains unexplained and the candidate is UNWITNESSED in game.** The old scene already submits the plate before the label, and its label remains visible when the old preview's software depth rejection is removed. This work does not claim that a game capture has been fixed.

Branch: `astra/b71-s9-down-label`, based exactly on `02bbadd184e85498a441d3be71e70f8de94b9b0a`. All commits use `.scratch/astra-b71-s9.git` and explicit paths. The worktree's normal Git administration is read-only; its original HEAD remains untouched. The private object store borrows base objects read-only. Delivery bundle: `.scratch/astra-b71-s9.bundle` (base commit is a prerequisite). No push, emulator, GUI, network or test-disc build was performed. No full disc or pack was copied and retail inputs were not modified; existing allocator tests use disposable XBE fixtures. Heavy work uses `run_logged.py`, which starts each child in a new session and supervises it until its receipt is written. Scratch usage stays below 200 MB.

Read: `ASTRA_CONTEXT.md`, `BETA71_TRIAGE.md`, the brief, the S8 report, the compiler/layout/owner/scene writer, and S5/S6 evidence. The requested root S5/S6 report filenames are absent from this release tree; the retained S5 report is `reports/b71_s6/INHERITED_ASTRA_REPORT.md`, and S6's report generator and proof/build scripts supply its retained evidence. The specific S9 brief authorizes the scorebug files despite the older general context's exclusion.

## Retail submission proof

Addresses below are USA retail XBE virtual addresses. SCNE offsets are relative to the decoded scene base. These are disassembly/native CPU facts, not a claim to have executed NV2A.

- `FBC70(scene, name)` is a lookup, not a renderer or sorter. At `0xFBC70` it reads `[scene+0x1C]`; at `0xFBC82` it reads `[scene+0x20]`; `0xFBC8A` compares the name, `0xFBC97` advances by `0x80`, and the return path returns that record. See `reports/b71_s9/disasm-hud.log:3`, `reports/b71_s9/disasm-hud.log:12`, `reports/b71_s9/disasm-hud.log:20`. Raw records begin at SCNE `0x1C0` and are a name/binding table. Their array order is **not** submission order.
- `FC360` activates the HUD camera (`0xFC3A7 -> 0x2AC80`) and calls the scene instance drawer at `0xFC3B2 -> 0x21860`, before the FONT loops: `reports/b71_s9/disasm-hud.log:64`. `21860` supplies the instance's shape/matrices/material table and calls `243D0` at `0x218B6`: `reports/b71_s9/disasm-scene.log:41`.
- `243D0` walks the SHAP descriptor table, `[SHAP+0x70]`, using the unsigned count at `SHAP+0x54`. At `0x24540` it takes the descriptor's `u16` material index, multiplies by 128 and adds the material table. At `0x24555` it tests `[material+8]&1`, skipping hidden materials: `reports/b71_s9/disasm-submit.log:104`, `reports/b71_s9/disasm-submit.log:111`.
- The material binder call at `0x24656` precedes submission. `0x248E1` reads the descriptor's word count at `+0x7C`; the command pointer is at `+0x78`. `0x248F0..0x248FC` copies successive words unchanged into the selected GPU command stream. `0x2491C` supports another linked material (`material+0x1C`); all eleven captured links are null. `0x2492F` advances the descriptor by `0x80` and `0x2493E` loops. See `reports/b71_s9/disasm-submit-tail.log:220`, `reports/b71_s9/disasm-submit-tail.log:226`, `reports/b71_s9/disasm-submit-tail.log:239`, `reports/b71_s9/disasm-submit-tail.log:244`.
- All captured materials share shader hash `0xD30E3557`. The bounded execution of the actual `243D0` loop uses one RAM command context; it executes material selection, visibility, descriptor traversal and the word-copy loop. Shader/texture binding, declaration upload and one palette helper are explicit boundaries. The final trace compares every visible command block, byte-for-byte and in sequence, to the emitted stream (208 words): `reports/b71_s9/submission-fixed-byte-proof.log`. No descriptor or index sorting is substituted by the harness.
- There is **no depth sort in this path**. There is also **no proof that depth testing is disabled**. Real material-state routine `0x2FC80` emits NV097 method `0x354 = 0x203` (LEQUAL) and `0x35C = 1` (depth write), captured in both submission traces. Its encoder is at `reports/b71_s9/disasm-render-state.log:11`. Depth-enable method `0x30C` is controlled elsewhere: `reports/b71_s9/disasm-depth-enable.log:53` derives it from a render-target argument; `reports/b71_s9/disasm-depth-enable.log:124` writes the initialization value. The live game's pass/depth-surface binding has not been captured. Thus “no sort” is proved, while the lead's “no depth test” premise is unproved. The old preview used per-pixel world-z LEQUAL rejection, not a literal z sort.

The native command order is therefore **SHAP descriptor order, then that descriptor's push-buffer order**, within the captured shader context. Sorting the raw SCNE material array would be another wrong preview model.

## Exact location of the shipped plate and label

The eleven push-buffer batches have the following fixed storage/binding identities. Batch numbers are the JSON `material` preferences; raw SCNE indices are different.

| Batch | Raw SCNE index | Material name | Buffer offset | Word capacity | Quad capacity |
|---:|---:|---|---:|---:|---:|
| 0 | 5 | bscore_buga | 0x2230 | 17 | 4 |
| 1 | 0 | bscore_buga1 | 0x2274 | 17 | 4 |
| 2 | 1 | bscore_buga2 | 0x22B8 | 17 | 4 |
| 3 | 2 | cscore_buga | 0x22FC | 20 | 5 |
| 4 | 4 | dscore_buga | 0x234C | 17 | 4 |
| 5 | 3 | hscore_buga | 0x2390 | 17 | 4 |
| 6 | 9 | yscore_buga | 0x23D4 | 53 | 16 |
| 7 | 7 | yscore_buga1 | 0x24A8 | 50 | 15 |
| 8 | 10 | zscore_buga | 0x2570 | 28 | 8 |
| 9 | 6 | score_buga (renamed brand material) | 0x25E0 | 16 | 4 |
| 10 | 8 | zz_ESPN_bug1 | 0x2620 | 16 | 4 |

The release table at SCNE `0x1CB0` submits batches `0,1,2,3,4,5,6,7,8,9,10`. The plate is vertices `20..23`, first quad in batch 4; the pointer is `24..27`. Label slots are vertices `140..171`, after the six timeout slots in batch 7. The plate material record is SCNE `0x3C0`, with its release descriptor at `0x1EB0`; the label material record is `0x540`, with its descriptor at `0x2030`. Thus **the plate is submitted before the label**. See `inspect-shipped.log` and `submission-shipped-restored.log`. Raw material tint is `0xFFFFFFFF`, visibility is on, atlas descriptors agree, and UV affine fields agree. The no-depth release raster still shows the label: [release painter crop](reports/b71_s9/shipped_submission_crop.png). It does expose the red play-clock cell covering its digits and the home wing covering its logo; those are ordering defects hidden by the old software depth model.

The actual disc n image was read with bounded reads, not copied or rebuilt. Its 4,096-byte owner matches the release owner. Its decoded scene SHA-256 is `e7fbe22e03ea114259f4505507d1614bb9d3327a9590ddc3250a7678b07a2c9f`; it predates the watermark and its down field starts at vertex 136. `FC7D0`, `FBC70` and `243D0` match retail. Its `FC9C0` differs by the already-installed persistent scorebar tail in `nfl2k5_scorebar_v3.py`, also installed by the native preview. That difference is not a newly discovered bug. See `disc-n-readback.log`, `disc-n-visibility-diff.log` and `disc-n-submission-order.log`. The actual disc n descriptor walk also places plate vertices 20–23 in batch 4 before label vertices 136–167 in batch 7.

The three supplied disc n captures were inspected, including the blank navy plate in `disc_n_3.png`. Kickoff and ball-on phases can legitimately suppress the down label, but that does not explain or dismiss the pre-snap witness. Newer evidence checked in the folder was software preview output, not a new played capture.

## Native owner, UVs and visibility

The owner source dispatches source 7 through `FC7D0` at `tools/scorebug_sprite/runtime.c:79`. It first clears unused colors, checks `0xA95A00`, then suppresses the field for active event requests `0xA95AE0`, `0xA95B50`, `0xA95BC0`, `0xA95C30`: `tools/scorebug_sprite/runtime.c:91`. Glyph positions/UVs and visible colors are written at `tools/scorebug_sprite/runtime.c:114`.

For 1st & 10, the release native capture writes the token sequence `1, st, space, &, space, 1, 0`; the five nonspace glyphs are `0xFFFFFFFF`, the spaces and final unused slot have zero color. First-corner packed UVs are `(27391,11008)`, `(-12544,22271)`, `(27391,7808)`, `(27391,11008)`, `(-256,-2176)` for the five visible glyphs. These are actual owner-written values, not host text composition. `visibility-shipped.log` also executes the real `FC9C0` pre-snap path and obtains request words `[1,1,0,0,0,0]`; the live fixture has the same five glyphs. After-play, kickoff, flag and fumble fixtures suppress them as designed. Gameplay predicates are substituted explicitly; their real values during the witnessed blank frame remain unknown.

Every nonempty label cell survives the alpha-aware P8 conversion with maximum alpha 255 and opaque pixels. All 34 texture chunks are identical before/after. The palette-zero-alpha and material-tint candidates are ruled out **for these compiled/native fixture states**, not for an unrecorded in-game memory state. Exact per-token coverage is in `scene_byte_audit.json`.

## Change

- `mod_editor/core/nfl2k5_scorebug_sprite.py:166` builds precedence constraints for overlapping layers, fits atomic fields first into compatible always-visible atlas batches, and topologically orders the draw descriptors. Static plates can move under capacity pressure; logo/event texture and visibility bindings stay fixed. A bounded search rejects unsatisfiable layouts. Dynamic footprints use native anchors, widths and raised-glyph bounds. Equal layers retain declaration order where they overlap.
- The supplied layout now explicitly uses `layer_order: increasing-z`; its old depths are mapped by `new_z = -20 - old_z`, preserving foreground/background intent. Legacy folders without the property keep the old decreasing-z convention. Within each batch, quads are written in layer order. Native field vertex slots remain contiguous.
- The new default descriptor order is batches `3,4,7,0,1,2,9,5,6,8,10`, raw material indices `2,4,7,5,0,1,6,3,9,10,8`. The plate and label descriptors move to `0x1D30` and `0x1DB0` respectively. SCNE material records and buffer storage addresses stay fixed. Moving a descriptor rebases its one-based field-relative `+0x78` pointer: `mod_editor/core/nfl2k5_scorebug_sprite.py:373`.
- Layout z is now compile-time order only. Static and owner-generated sprite vertices use the same quantized GPU z. Equal depth agrees with the material's LEQUAL state as well as with a pass that disables depth testing. No render-state bit, shader, XBE hook or owner ABI was changed. Retained native event text still follows scene submission. FLAG's dark label is already baked into its yellow plate, so that label/plate is one atomic quad rather than two separately ordered glyph draws.
- Preview reads the real SHAP descriptors and push buffers, including relocated pointers, at `tools/nfl2k5_scorebug_projection.py:728`. Sprite preview has no software depth correction. Historical non-sprite diagnostics retain their explicitly labeled LEQUAL model. The regression deliberately moves the plate after the glyphs and requires the preview to lose every white label pixel; the old preview fails that check.

## Proof and previews

**PROVED:** 808 native label states: four downs × distances 0–99, plus four GOAL states, at both aspects. Possession alternates KC/DAL to exercise crimson/navy. Every state runs the owner and actual formatter, checks request visibility, token UVs and white vertex color, and counts visible label pixels in a submission-order raster. Minimum white-ink count: **100 HUD pixels**. The sweep uses a cropped canvas at the same HUD scale, with annotations outside the measured strip; it does not resize glyphs to manufacture ink. Field-boundary queries for goal-to-go are explicit fixture boundaries.

The full 50-state contact sheet uses S8's display model: all 640×448 HUD pixels fill the target display, after the native widescreen contraction. FLAG is separately checked for yellow plate pixels and dark label pixels at both aspects. Standard, every down, Inches, GOAL, scores, clocks, timeouts and retained event states are included.

- [50-state contact sheet](reports/b71_s9/states_contact_sheet.png)
- [1st & 10, 4:3](reports/b71_s9/standard_43_display.png) and [16:9](reports/b71_s9/standard_169_display.png)
- [GOAL, 4:3](reports/b71_s9/goal_43_display.png) and [16:9](reports/b71_s9/goal_169_display.png)
- [FLAG, 4:3](reports/b71_s9/flag_43_display.png) and [16:9](reports/b71_s9/flag_169_display.png)
- Machine-readable receipts: `label_sweep.json`, `states.json`, `volume.json`, `scene_byte_audit.json`.

**PROVED volume:** 323,808 appended bytes at each aspect, unchanged; 34 TXTR, one SCNE, zero FONT, 47 quads. Limit remains strictly below 400,000 bytes. Scene length stays 20,352 decoded bytes. The scene changes 133 bytes at 4:3 and 133 at 16:9. Changed ranges and hashes are recorded in the audit; raw material records and texture chunks are identical. The later custom-anchor check changes no default appendix byte.

**UNWITNESSED:** actual GPU depth-surface/enable state at the reported frame, hardware blending/sampling/cache behavior, gameplay predicate values at that frame, intro/runtime memory behavior, and whether disc p fixes the reported missing label. CPU-native plus software raster is not an emulator or played-game witness. The lead should not mark the original symptom resolved from these previews alone.

## Integration and prepared disc

`reports/b71_s9/build_testdisc71.py` is prepared, syntax/AST checked, and **was not run or imported**. Its plan function is AST-identical to S6/disc n: Advanced preset with Scorebug, runtime, modern colour, modern Arrowhead and widescreen enabled. Name: **NFL 2K5 MOD TEST 2026-09-16p (down label fix)**. It retains the S6 readbacks and patch-archive handling. The current release's colour-strength default remains in force. No disc or patch archive was created or deleted.

The owner, generated C engine, static XBE writer and persistent scorebar writer are unchanged. Owner `code_for(0,0)` SHA-256: `3ac2cc0192032ad2b3b295e97ce0ad7a7c00a89807b2b95eb50ba71c6e8025f4`; `build_runtime.py --check` passes. Compiler pins were regenerated (retained legacy compiler pins remain identical); sprite hashes are in `volume.json`/`scene_byte_audit.json`. `packaging/repin.py --apply` refreshes provider hashes.

**Manifest refresh required:** `nfl2k5_cave_manifest.source_fingerprints()` at `mod_editor/core/nfl2k5_cave_manifest.py:247` observes changed `mod_editor/core/nfl2k5_scorebug_sprite.py` and `tools/nfl2k5_scorebug_projection.py`. Scene descriptor order, push-buffer order in the brand batch and sprite depth/table values change. No new cave, reservation, owner byte or XBE write is introduced. The protected cave manifest was deliberately left for hotfix integration, which must regenerate it and rerun XBE cave/memory/pairwise gates on the combined tree. No registry capability or protected GUI/dispatcher/packaging-check edit is needed. This supersedes S9-relevant statements in the inherited root `WIRING.md` without rewriting that older handoff.

Played retest: 1st & 10 with both teams possessing, downs 2–4, numeric/Inches/GOAL distances, transition through FLAG/ball-on, both display aspects, with play-clock digits, ticks, logos and watermark visible. If the label is still missing, capture the four event-request words, `0xA95A00`, the field's live colors/UVs and bound descriptor during the blank frame. A further owner change should follow that evidence.

## Validation ledger

The final runner completed **37 standalone suites, 387 reported tests, 16 explicitly reported skips**, plus strict registry validation (176 capabilities). The final custom-anchor regression suite adds its separate five-test rerun. Exact skip reasons remain in the individual logs.

Each verification/forensic run below has its exact argv, UTC timestamps, elapsed seconds and exit status in the adjacent `.result.json`; stdout/stderr is in the linked log. Environment: `PYTHONPATH` is the worktree and `QT_QPA_PLATFORM=offscreen`. The table records failed investigative attempts as well as final successes. Routine read/edit tool calls and initial private-Git setup were not stopwatch-wrapped; no timing is invented for them.

The first delivery whitespace check also rejected trailing padding on disassembled no-operand instructions. Log trailing whitespace was normalized without changing addresses, instruction text, hashes, line numbers or test results; that failed check is retained in `.scratch/delivery_commands.json`.

Two corrected harness failures are retained: `submission-shipped` initially hit an unmapped read because the preview's stubbed `28110` was not restored; `submission-shipped-restored` fixes that boundary. `prove-states` passed its 400 numeric states at 4:3 then expected mixed-case “Goal” instead of the owner's existing uppercase “GOAL”; `prove-states-final` corrects that expectation and completes both aspects. Neither failure required a game-code change. Initial orphan-style shell launches did not survive the sandbox PID namespace; subsequent heavy runs use the detached-child supervisor.

| UTC start | Seconds | Exit | Exact command | Output |
|---|---:|---:|---|---|
| 2026-09-16T23:08:18.058110+00:00 | 0.782 | 0 | `python3 reports/b71_s9/disassemble.py fbc70:fbcbe fc360:fc760` | [disasm-hud](reports/b71_s9/disasm-hud.log) |
| 2026-09-16T23:08:23.482813+00:00 | 0.227 | 0 | `python3 reports/b71_s9/disassemble.py 21860:218ff 2ac80:2ae80 21000:21860` | [disasm-scene](reports/b71_s9/disasm-scene.log) |
| 2026-09-16T23:08:30.063510+00:00 | 0.223 | 0 | `python3 reports/b71_s9/disassemble.py 243d0:245c0` | [disasm-submit](reports/b71_s9/disasm-submit.log) |
| 2026-09-16T23:08:36.796829+00:00 | 0.235 | 0 | `python3 reports/b71_s9/disassemble.py 245b9:249b0` | [disasm-submit-tail](reports/b71_s9/disasm-submit-tail.log) |
| 2026-09-16T23:09:15.479159+00:00 | 0.243 | 0 | `python3 reports/b71_s9/disassemble.py 24160:243d0 28110:28160` | [disasm-material](reports/b71_s9/disasm-material.log) |
| 2026-09-16T23:09:29.067116+00:00 | 0.225 | 0 | `python3 reports/b71_s9/disassemble.py 2fc80:2fe60` | [disasm-render-state](reports/b71_s9/disasm-render-state.log) |
| 2026-09-16T23:09:36.846807+00:00 | 17.155 | 0 | `python3 reports/b71_s9/inspect_scene.py` | [inspect-shipped](reports/b71_s9/inspect-shipped.log) |
| 2026-09-16T23:10:11.916121+00:00 | 0.23 | 0 | `python3 reports/b71_s9/disassemble.py fc7d0:fc9c0 fc9c0:fccd0` | [disasm-down-state](reports/b71_s9/disasm-down-state.log) |
| 2026-09-16T23:10:30.354441+00:00 | 0.225 | 0 | `python3 reports/b71_s9/disassemble.py 2fe60:30100` | [disasm-render-state-tail](reports/b71_s9/disasm-render-state-tail.log) |
| 2026-09-16T23:11:05.721132+00:00 | 28.002 | 0 | `python3 reports/b71_s9/probe_visibility.py` | [visibility-shipped](reports/b71_s9/visibility-shipped.log) |
| 2026-09-16T23:11:39.605552+00:00 | 0.221 | 0 | `python3 reports/b71_s9/disassemble.py 2b5b0:2b890` | [disasm-camera-state](reports/b71_s9/disasm-camera-state.log) |
| 2026-09-16T23:12:01.660505+00:00 | 0.223 | 0 | `python3 reports/b71_s9/disassemble.py 285e0:28710 29040:29140 22520:225c0` | [disasm-depth-enable](reports/b71_s9/disasm-depth-enable.log) |
| 2026-09-16T23:12:41.968501+00:00 | 16.662 | 1 | `python3 reports/b71_s9/probe_submission.py` | [submission-shipped](reports/b71_s9/submission-shipped.log) |
| 2026-09-16T23:13:11.233488+00:00 | 19.112 | 0 | `python3 reports/b71_s9/probe_order_raster.py` | [raster-shipped](reports/b71_s9/raster-shipped.log) |
| 2026-09-16T23:13:21.193687+00:00 | 16.622 | 0 | `python3 reports/b71_s9/probe_submission.py` | [submission-shipped-restored](reports/b71_s9/submission-shipped-restored.log) |
| 2026-09-16T23:15:30.779011+00:00 | 0.274 | 0 | `python3 reports/b71_s9/inspect_disc_n.py` | [disc-n-readback](reports/b71_s9/disc-n-readback.log) |
| 2026-09-16T23:15:57.814057+00:00 | 0.301 | 0 | `python3 reports/b71_s9/inspect_disc_n.py` | [disc-n-visibility-diff](reports/b71_s9/disc-n-visibility-diff.log) |
| 2026-09-16T23:25:35.798916+00:00 | 91.135 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_sprite.py -v` | [sprite-first](reports/b71_s9/sprite-first.log) |
| 2026-09-16T23:26:49.302483+00:00 | 25.601 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_draw_order.py -v` | [draw-order-first](reports/b71_s9/draw-order-first.log) |
| 2026-09-16T23:28:39.404747+00:00 | 503.163 | 1 | `python3 reports/b71_s9/prove_states.py` | [prove-states](reports/b71_s9/prove-states.log) |
| 2026-09-16T23:28:46.674105+00:00 | 17.175 | 0 | `python3 reports/b71_s9/probe_submission.py` | [submission-fixed](reports/b71_s9/submission-fixed.log) |
| 2026-09-16T23:28:46.694531+00:00 | 17.337 | 0 | `python3 reports/b71_s9/inspect_scene.py` | [inspect-fixed](reports/b71_s9/inspect-fixed.log) |
| 2026-09-16T23:29:15.608065+00:00 | 39.161 | 0 | `python3 reports/b71_s9/regenerate_pins.py` | [regenerate-pins](reports/b71_s9/regenerate-pins.log) |
| 2026-09-16T23:30:13.938975+00:00 | 0.366 | 0 | `python3 reports/b71_s9/verify_delivery_inputs.py` | [delivery-inputs](reports/b71_s9/delivery-inputs.log) |
| 2026-09-16T23:30:29.702386+00:00 | 20.744 | 0 | `python3 packaging/repin.py --apply` | [repin-apply](reports/b71_s9/repin-apply.log) |
| 2026-09-16T23:31:20.524021+00:00 | 1447.288 | 0 | `python3 reports/b71_s9/run_final_suites.py` | [final-suites](reports/b71_s9/final-suites.log) |
| 2026-09-16T23:31:20.557427+00:00 | 1.366 | 0 | `python3 tests/mod_editor/test_apf_scorebug_workspace_qt.py -v` | [final-test_apf_scorebug_workspace_qt](reports/b71_s9/final-test_apf_scorebug_workspace_qt.log) |
| 2026-09-16T23:31:20.557870+00:00 | 13.25 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebar_rim.py -v` | [final-test_nfl2k5_scorebar_rim](reports/b71_s9/final-test_nfl2k5_scorebar_rim.log) |
| 2026-09-16T23:31:20.558372+00:00 | 97.703 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebar_v3.py -v` | [final-test_nfl2k5_scorebar_v3](reports/b71_s9/final-test_nfl2k5_scorebar_v3.log) |
| 2026-09-16T23:31:21.923221+00:00 | 145.502 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_assets.py -v` | [final-test_nfl2k5_scorebug_assets](reports/b71_s9/final-test_nfl2k5_scorebug_assets.log) |
| 2026-09-16T23:31:33.808342+00:00 | 6.294 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_author.py -v` | [final-test_nfl2k5_scorebug_author](reports/b71_s9/final-test_nfl2k5_scorebug_author.log) |
| 2026-09-16T23:31:40.102635+00:00 | 25.566 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_draw_order.py -v` | [final-test_nfl2k5_scorebug_draw_order](reports/b71_s9/final-test_nfl2k5_scorebug_draw_order.log) |
| 2026-09-16T23:32:05.668690+00:00 | 84.113 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_exact.py -v` | [final-test_nfl2k5_scorebug_exact](reports/b71_s9/final-test_nfl2k5_scorebug_exact.log) |
| 2026-09-16T23:32:13.181586+00:00 | 17.326 | 0 | `python3 reports/b71_s9/probe_submission.py` | [submission-fixed-byte-proof](reports/b71_s9/submission-fixed-byte-proof.log) |
| 2026-09-16T23:32:58.261934+00:00 | 8.482 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_fonts.py -v` | [final-test_nfl2k5_scorebug_fonts](reports/b71_s9/final-test_nfl2k5_scorebug_fonts.log) |
| 2026-09-16T23:33:06.744539+00:00 | 242.154 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_freeze.py -v` | [final-test_nfl2k5_scorebug_freeze](reports/b71_s9/final-test_nfl2k5_scorebug_freeze.log) |
| 2026-09-16T23:33:10.977342+00:00 | 0.152 | 0 | `python3 tools/scorebug_sprite/build_runtime.py --check` | [owner-reproducible](reports/b71_s9/owner-reproducible.log) |
| 2026-09-16T23:33:20.678352+00:00 | 10.623 | 0 | `python3 packaging/repin.py --apply` | [repin-before-code-commit](reports/b71_s9/repin-before-code-commit.log) |
| 2026-09-16T23:33:29.781911+00:00 | 331.136 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_freeze_v2.py -v` | [final-test_nfl2k5_scorebug_freeze_v2](reports/b71_s9/final-test_nfl2k5_scorebug_freeze_v2.log) |
| 2026-09-16T23:33:47.425710+00:00 | 14.753 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_ingame.py -v` | [final-test_nfl2k5_scorebug_ingame](reports/b71_s9/final-test_nfl2k5_scorebug_ingame.log) |
| 2026-09-16T23:34:02.179104+00:00 | 127.992 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_ingame_fix.py -v` | [final-test_nfl2k5_scorebug_ingame_fix](reports/b71_s9/final-test_nfl2k5_scorebug_ingame_fix.log) |
| 2026-09-16T23:34:12.183301+00:00 | 19.675 | 0 | `python3 reports/b71_s9/audit_scene_bytes.py` | [scene-byte-audit](reports/b71_s9/scene-byte-audit.log) |
| 2026-09-16T23:34:30.817088+00:00 | 0.066 | 0 | `git --git-dir=.scratch/astra-b71-s9.git --work-tree=. commit -m 'Order sprite scorebug submissions by overlapping layout layers' -- data/nfl2k5_scorebug_sprite/layout.json docs/mod_editor/2k5_mod_studio_changelog.md docs/mod_editor/sprite_scorebug.md mod_editor/core/nfl2k5_scorebug_sprite.py mod_editor/core/providers.py tools/nfl2k5_scorebug_projection.py tools/scorebug_sprite/author_default.py tests/mod_editor/test_nfl2k5_scorebug_draw_order.py` | [commit-code](reports/b71_s9/commit-code.log) |
| 2026-09-16T23:36:10.171900+00:00 | 12.416 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_mnf.py -v` | [final-test_nfl2k5_scorebug_mnf](reports/b71_s9/final-test_nfl2k5_scorebug_mnf.log) |
| 2026-09-16T23:36:22.587826+00:00 | 49.566 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_mnf_v3.py -v` | [final-test_nfl2k5_scorebug_mnf_v3](reports/b71_s9/final-test_nfl2k5_scorebug_mnf_v3.log) |
| 2026-09-16T23:36:33.300498+00:00 | 772.324 | 0 | `python3 reports/b71_s9/prove_states.py` | [prove-states-final](reports/b71_s9/prove-states-final.log) |
| 2026-09-16T23:37:08.898602+00:00 | 132.712 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_native.py -v` | [final-test_nfl2k5_scorebug_native](reports/b71_s9/final-test_nfl2k5_scorebug_native.log) |
| 2026-09-16T23:37:12.153887+00:00 | 56.324 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_projection.py -v` | [final-test_nfl2k5_scorebug_projection](reports/b71_s9/final-test_nfl2k5_scorebug_projection.log) |
| 2026-09-16T23:38:08.477970+00:00 | 298.817 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_resources.py -v` | [final-test_nfl2k5_scorebug_resources](reports/b71_s9/final-test_nfl2k5_scorebug_resources.log) |
| 2026-09-16T23:38:33.966077+00:00 | 27.356 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_draw_order.py -v` | [draw-order-anchor-final](reports/b71_s9/draw-order-anchor-final.log) |
| 2026-09-16T23:39:00.918068+00:00 | 123.309 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_runtime.py -v` | [final-test_nfl2k5_scorebug_runtime](reports/b71_s9/final-test_nfl2k5_scorebug_runtime.log) |
| 2026-09-16T23:39:16.682462+00:00 | 22.501 | 0 | `python3 packaging/repin.py --apply` | [repin-anchor-final](reports/b71_s9/repin-anchor-final.log) |
| 2026-09-16T23:39:21.610552+00:00 | 0.495 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_source_art.py -v` | [final-test_nfl2k5_scorebug_source_art](reports/b71_s9/final-test_nfl2k5_scorebug_source_art.log) |
| 2026-09-16T23:39:22.105863+00:00 | 95.957 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_sprite.py -v` | [final-test_nfl2k5_scorebug_sprite](reports/b71_s9/final-test_nfl2k5_scorebug_sprite.log) |
| 2026-09-16T23:39:32.258617+00:00 | 19.302 | 0 | `python3 reports/b71_s9/audit_scene_bytes.py` | [scene-byte-audit-final](reports/b71_s9/scene-byte-audit-final.log) |
| 2026-09-16T23:40:05.805152+00:00 | 0.062 | 0 | `git --git-dir=.scratch/astra-b71-s9.git --work-tree=. commit -m 'Check sprite field overlaps at native anchors' -- mod_editor/core/nfl2k5_scorebug_sprite.py mod_editor/core/providers.py tests/mod_editor/test_nfl2k5_scorebug_draw_order.py` | [commit-anchor](reports/b71_s9/commit-anchor.log) |
| 2026-09-16T23:40:58.063251+00:00 | 9.699 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_template.py -v` | [final-test_nfl2k5_scorebug_template](reports/b71_s9/final-test_nfl2k5_scorebug_template.log) |
| 2026-09-16T23:41:04.227573+00:00 | 0.552 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_template_release.py -v` | [final-test_nfl2k5_scorebug_template_release](reports/b71_s9/final-test_nfl2k5_scorebug_template_release.log) |
| 2026-09-16T23:41:04.780263+00:00 | 0.17 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_unified_adapter.py -v` | [final-test_nfl2k5_scorebug_unified_adapter](reports/b71_s9/final-test_nfl2k5_scorebug_unified_adapter.log) |
| 2026-09-16T23:41:04.950352+00:00 | 9.004 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_v10_ingame.py -v` | [final-test_nfl2k5_scorebug_v10_ingame](reports/b71_s9/final-test_nfl2k5_scorebug_v10_ingame.log) |
| 2026-09-16T23:41:07.762521+00:00 | 28.978 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_v10_projection.py -v` | [final-test_nfl2k5_scorebug_v10_projection](reports/b71_s9/final-test_nfl2k5_scorebug_v10_projection.log) |
| 2026-09-16T23:41:13.954882+00:00 | 9.595 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_versions.py -v` | [final-test_nfl2k5_scorebug_versions](reports/b71_s9/final-test_nfl2k5_scorebug_versions.log) |
| 2026-09-16T23:41:23.550280+00:00 | 22.107 | 0 | `python3 tests/mod_editor/test_scorebug_sprite_preview_qt.py -v` | [final-test_scorebug_sprite_preview_qt](reports/b71_s9/final-test_scorebug_sprite_preview_qt.log) |
| 2026-09-16T23:41:36.740861+00:00 | 7.305 | 0 | `python3 tests/mod_editor/test_scorebug_studio_panel_qt.py -v` | [final-test_scorebug_studio_panel_qt](reports/b71_s9/final-test_scorebug_studio_panel_qt.log) |
| 2026-09-16T23:41:44.045732+00:00 | 1.436 | 0 | `python3 tests/nfl2k5_scorebug_layout_test.py -v` | [final-nfl2k5_scorebug_layout_test](reports/b71_s9/final-nfl2k5_scorebug_layout_test.log) |
| 2026-09-16T23:41:45.482381+00:00 | 1.34 | 0 | `python3 tests/nfl2k5_scorebug_mod_project_test.py -v` | [final-nfl2k5_scorebug_mod_project_test](reports/b71_s9/final-nfl2k5_scorebug_mod_project_test.log) |
| 2026-09-16T23:41:45.657665+00:00 | 10.127 | 0 | `python3 tests/mod_editor/test_provider_integrity.py -v` | [final-test_provider_integrity](reports/b71_s9/final-test_provider_integrity.log) |
| 2026-09-16T23:41:46.822495+00:00 | 0.153 | 0 | `python3 tests/mod_editor/test_product_catalog.py -v` | [final-test_product_catalog](reports/b71_s9/final-test_product_catalog.log) |
| 2026-09-16T23:41:46.975821+00:00 | 2.128 | 0 | `python3 tests/mod_editor/test_phase1_packaging.py -v` | [final-test_phase1_packaging](reports/b71_s9/final-test_phase1_packaging.log) |
| 2026-09-16T23:41:49.104076+00:00 | 2.201 | 0 | `python3 tests/mod_editor/test_mod_build.py -v` | [final-test_mod_build](reports/b71_s9/final-test_mod_build.log) |
| 2026-09-16T23:41:51.305136+00:00 | 3.338 | 0 | `python3 tests/mod_editor/test_build_panel_qt.py -v` | [final-test_build_panel_qt](reports/b71_s9/final-test_build_panel_qt.log) |
| 2026-09-16T23:41:54.643659+00:00 | 813.008 | 0 | `python3 tests/mod_editor/test_nfl2k5_allocator_scaleout.py -v` | [final-test_nfl2k5_allocator_scaleout](reports/b71_s9/final-test_nfl2k5_allocator_scaleout.log) |
| 2026-09-16T23:41:55.784777+00:00 | 35.0 | 0 | `python3 tests/mod_editor/test_nfl2k5_xbe_space.py -v` | [final-test_nfl2k5_xbe_space](reports/b71_s9/final-test_nfl2k5_xbe_space.log) |
| 2026-09-16T23:46:15.873402+00:00 | 0.366 | 0 | `python3 reports/b71_s9/inspect_disc_n.py` | [disc-n-submission-order](reports/b71_s9/disc-n-submission-order.log) |
| 2026-09-16T23:46:59.305770+00:00 | 0.023 | 0 | `git --git-dir=.scratch/astra-b71-s9.git --work-tree=. diff 02bbadd1 --check` | [diff-check](reports/b71_s9/diff-check.log) |
| 2026-09-16T23:55:27.652549+00:00 | 0.149 | 0 | `python3 -m mod_editor.capabilities.validate_registry` | [registry-strict](reports/b71_s9/registry-strict.log) |
| 2026-09-16T23:56:36.751365+00:00 | 0.027 | 0 | `python3 reports/b71_s9/summarize_validation.py` | [validation-summary](reports/b71_s9/validation-summary.log) |
| 2026-09-16T23:56:36.900735+00:00 | 10.644 | 0 | `python3 packaging/repin.py --apply` | [repin-before-evidence-commit](reports/b71_s9/repin-before-evidence-commit.log) |
| 2026-09-16T23:57:03.664978+00:00 | 0.028 | 0 | `python3 reports/b71_s9/summarize_validation.py` | [validation-summary-final](reports/b71_s9/validation-summary-final.log) |
| 2026-09-16T23:57:03.810001+00:00 | 0.044 | 0 | `python3 reports/b71_s9/write_report.py` | [write-report](reports/b71_s9/write-report.log) |
| 2026-09-16T23:58:28.181027+00:00 | 10.638 | 0 | `python3 packaging/repin.py --apply` | [repin-before-evidence-cleanup](reports/b71_s9/repin-before-evidence-cleanup.log) |

The final suite runner includes every standalone scorebug/scorebar suite, both root layout/project suites, provider integrity, product catalog, phase1 packaging, build/Qt, allocator/space, and strict registry validation. Individual logs record test counts and any precise skips. The new anchor regression is rerun separately against final sources; the byte audit confirms the default payload exercised by the sweep and earlier suites is unchanged.

Commits present when this report was generated:

```text
aa55a8b70f556b727b4bdb55d40c7714f949d46a Order sprite scorebug submissions by overlapping layout layers
d99fe965a5936810bf8d4084cf52e18078899a80 Check sprite field overlaps at native anchors
7cb8aed592efad73593a0cf27e8b5ca1172f1653 Record S9 native draw-order proof and hotfix candidate validation
```

The evidence/report commit and final bundle verification are recorded after this report is committed in `.scratch/delivery_commands.json` (exact argv, time and exit status) and `.scratch/delivery.json` (head and bundle SHA-256). This avoids embedding a commit hash or bundle checksum inside itself. The normal Git worktree may still display changes because commits intentionally live only in the private Git directory.

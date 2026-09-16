"""Assemble the S9 handoff from command receipts and native evidence."""
from pathlib import Path
import json,re,shlex,subprocess
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
BASE='02bbadd184e85498a441d3be71e70f8de94b9b0a'
def read(name):return json.loads((OUT/name).read_text())
def line(path,text):
 for i,s in enumerate((ROOT/path).read_text().splitlines(),1):
  if text in s:return f'`{path}:{i}`'
 raise ValueError((path,text))
def cite(name,text):return line('reports/b71_s9/'+name,text)
rows=sorted((json.loads(p.read_text()) for p in OUT.glob('*.result.json')),key=lambda r:r['start_utc'])
for name in ('prove-states-final','final-suites','draw-order-anchor-final','scene-byte-audit-final','repin-anchor-final','owner-reproducible','delivery-inputs'):
 assert next(r for r in rows if r['name']==name)['exit_code']==0,name
sweep=read('label_sweep.json');audit=read('scene_byte_audit.json');inputs=read('delivery_inputs.json');states=read('states.json');validation=read('validation_summary.json')
assert sweep['count']==808 and len(states)==50
commits=subprocess.check_output(['git','--git-dir=.scratch/astra-b71-s9.git','--work-tree=.','log','--reverse','--format=%H %s',BASE+'..HEAD'],cwd=ROOT,text=True).strip()
text=f'''# Beta 71.1 S9: sprite down-label investigation and ordering candidate

The compiler and preview now use explicit submission order for overlapping sprite layers. **The proposed plate-over-label cause is disproved for the supplied release scene in the bounded native trace. The missing label witnessed in game remains unexplained and the candidate is UNWITNESSED in game.** The old scene already submits the plate before the label, and its label remains visible when the old preview's software depth rejection is removed. This work does not claim that a game capture has been fixed.

Branch: `astra/b71-s9-down-label`, based exactly on `{BASE}`. All commits use `.scratch/astra-b71-s9.git` and explicit paths. The worktree's normal Git administration is read-only; its original HEAD remains untouched. The private object store borrows base objects read-only. Delivery bundle: `.scratch/astra-b71-s9.bundle` (base commit is a prerequisite). No push, emulator, GUI, network or test-disc build was performed. No full disc or pack was copied and retail inputs were not modified; existing allocator tests use disposable XBE fixtures. Heavy work uses `run_logged.py`, which starts each child in a new session and supervises it until its receipt is written. Scratch usage stays below 200 MB.

Read: `ASTRA_CONTEXT.md`, `BETA71_TRIAGE.md`, the brief, the S8 report, the compiler/layout/owner/scene writer, and S5/S6 evidence. The requested root S5/S6 report filenames are absent from this release tree; the retained S5 report is `reports/b71_s6/INHERITED_ASTRA_REPORT.md`, and S6's report generator and proof/build scripts supply its retained evidence. The specific S9 brief authorizes the scorebug files despite the older general context's exclusion.

## Retail submission proof

Addresses below are USA retail XBE virtual addresses. SCNE offsets are relative to the decoded scene base. These are disassembly/native CPU facts, not a claim to have executed NV2A.

- `FBC70(scene, name)` is a lookup, not a renderer or sorter. At `0xFBC70` it reads `[scene+0x1C]`; at `0xFBC82` it reads `[scene+0x20]`; `0xFBC8A` compares the name, `0xFBC97` advances by `0x80`, and the return path returns that record. See {cite('disasm-hud.log','000fbc70')}, {cite('disasm-hud.log','000fbc82')}, {cite('disasm-hud.log','000fbc97')}. Raw records begin at SCNE `0x1C0` and are a name/binding table. Their array order is **not** submission order.
- `FC360` activates the HUD camera (`0xFC3A7 -> 0x2AC80`) and calls the scene instance drawer at `0xFC3B2 -> 0x21860`, before the FONT loops: {cite('disasm-hud.log','000fc3b2')}. `21860` supplies the instance's shape/matrices/material table and calls `243D0` at `0x218B6`: {cite('disasm-scene.log','000218b6')}.
- `243D0` walks the SHAP descriptor table, `[SHAP+0x70]`, using the unsigned count at `SHAP+0x54`. At `0x24540` it takes the descriptor's `u16` material index, multiplies by 128 and adds the material table. At `0x24555` it tests `[material+8]&1`, skipping hidden materials: {cite('disasm-submit.log','00024540')}, {cite('disasm-submit.log','00024555')}.
- The material binder call at `0x24656` precedes submission. `0x248E1` reads the descriptor's word count at `+0x7C`; the command pointer is at `+0x78`. `0x248F0..0x248FC` copies successive words unchanged into the selected GPU command stream. `0x2491C` supports another linked material (`material+0x1C`); all eleven captured links are null. `0x2492F` advances the descriptor by `0x80` and `0x2493E` loops. See {cite('disasm-submit-tail.log','000248e1')}, {cite('disasm-submit-tail.log','000248f0')}, {cite('disasm-submit-tail.log','0002491c')}, {cite('disasm-submit-tail.log','0002492f')}.
- All captured materials share shader hash `0xD30E3557`. The bounded execution of the actual `243D0` loop uses one RAM command context; it executes material selection, visibility, descriptor traversal and the word-copy loop. Shader/texture binding, declaration upload and one palette helper are explicit boundaries. The final trace compares every visible command block, byte-for-byte and in sequence, to the emitted stream (208 words): `reports/b71_s9/submission-fixed-byte-proof.log`. No descriptor or index sorting is substituted by the harness.
- There is **no depth sort in this path**. There is also **no proof that depth testing is disabled**. Real material-state routine `0x2FC80` emits NV097 method `0x354 = 0x203` (LEQUAL) and `0x35C = 1` (depth write), captured in both submission traces. Its encoder is at {cite('disasm-render-state.log','0002fc92')}. Depth-enable method `0x30C` is controlled elsewhere: {cite('disasm-depth-enable.log','00028699')} derives it from a render-target argument; {cite('disasm-depth-enable.log','000290b7')} writes the initialization value. The live game's pass/depth-surface binding has not been captured. Thus “no sort” is proved, while the lead's “no depth test” premise is unproved. The old preview used per-pixel world-z LEQUAL rejection, not a literal z sort.

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

The owner source dispatches source 7 through `FC7D0` at {line('tools/scorebug_sprite/runtime.c','else if(source==7)')}. It first clears unused colors, checks `0xA95A00`, then suppresses the field for active event requests `0xA95AE0`, `0xA95B50`, `0xA95BC0`, `0xA95C30`: {line('tools/scorebug_sprite/runtime.c','if(f->source==7')}. Glyph positions/UVs and visible colors are written at {line('tools/scorebug_sprite/runtime.c','pos[0]=(j&1)')}.

For 1st & 10, the release native capture writes the token sequence `1, st, space, &, space, 1, 0`; the five nonspace glyphs are `0xFFFFFFFF`, the spaces and final unused slot have zero color. First-corner packed UVs are `(27391,11008)`, `(-12544,22271)`, `(27391,7808)`, `(27391,11008)`, `(-256,-2176)` for the five visible glyphs. These are actual owner-written values, not host text composition. `visibility-shipped.log` also executes the real `FC9C0` pre-snap path and obtains request words `[1,1,0,0,0,0]`; the live fixture has the same five glyphs. After-play, kickoff, flag and fumble fixtures suppress them as designed. Gameplay predicates are substituted explicitly; their real values during the witnessed blank frame remain unknown.

Every nonempty label cell survives the alpha-aware P8 conversion with maximum alpha 255 and opaque pixels. All 34 texture chunks are identical before/after. The palette-zero-alpha and material-tint candidates are ruled out **for these compiled/native fixture states**, not for an unrecorded in-game memory state. Exact per-token coverage is in `scene_byte_audit.json`.

## Change

- {line('mod_editor/core/nfl2k5_scorebug_sprite.py','def _allocate_layers')} builds precedence constraints for overlapping layers, fits atomic fields first into compatible always-visible atlas batches, and topologically orders the draw descriptors. Static plates can move under capacity pressure; logo/event texture and visibility bindings stay fixed. A bounded search rejects unsatisfiable layouts. Dynamic footprints use native anchors, widths and raised-glyph bounds. Equal layers retain declaration order where they overlap.
- The supplied layout now explicitly uses `layer_order: increasing-z`; its old depths are mapped by `new_z = -20 - old_z`, preserving foreground/background intent. Legacy folders without the property keep the old decreasing-z convention. Within each batch, quads are written in layer order. Native field vertex slots remain contiguous.
- The new default descriptor order is batches `{','.join(map(str,audit['False']['material_order']))}`, raw material indices `2,4,7,5,0,1,6,3,9,10,8`. The plate and label descriptors move to `0x1D30` and `0x1DB0` respectively. SCNE material records and buffer storage addresses stay fixed. Moving a descriptor rebases its one-based field-relative `+0x78` pointer: {line('mod_editor/core/nfl2k5_scorebug_sprite.py','descriptors=[bytes')}.
- Layout z is now compile-time order only. Static and owner-generated sprite vertices use the same quantized GPU z. Equal depth agrees with the material's LEQUAL state as well as with a pass that disables depth testing. No render-state bit, shader, XBE hook or owner ABI was changed. Retained native event text still follows scene submission. FLAG's dark label is already baked into its yellow plate, so that label/plate is one atomic quad rather than two separately ordered glyph draws.
- Preview reads the real SHAP descriptors and push buffers, including relocated pointers, at {line('tools/nfl2k5_scorebug_projection.py','def submission_batches')}. Sprite preview has no software depth correction. Historical non-sprite diagnostics retain their explicitly labeled LEQUAL model. The regression deliberately moves the plate after the glyphs and requires the preview to lose every white label pixel; the old preview fails that check.

## Proof and previews

**PROVED:** {sweep['count']} native label states: four downs × distances 0–99, plus four GOAL states, at both aspects. Possession alternates KC/DAL to exercise crimson/navy. Every state runs the owner and actual formatter, checks request visibility, token UVs and white vertex color, and counts visible label pixels in a submission-order raster. Minimum white-ink count: **{sweep['minimum_white_pixels']} HUD pixels**. The sweep uses a cropped canvas at the same HUD scale, with annotations outside the measured strip; it does not resize glyphs to manufacture ink. Field-boundary queries for goal-to-go are explicit fixture boundaries.

The full 50-state contact sheet uses S8's display model: all 640×448 HUD pixels fill the target display, after the native widescreen contraction. FLAG is separately checked for yellow plate pixels and dark label pixels at both aspects. Standard, every down, Inches, GOAL, scores, clocks, timeouts and retained event states are included.

- [50-state contact sheet](reports/b71_s9/states_contact_sheet.png)
- [1st & 10, 4:3](reports/b71_s9/standard_43_display.png) and [16:9](reports/b71_s9/standard_169_display.png)
- [GOAL, 4:3](reports/b71_s9/goal_43_display.png) and [16:9](reports/b71_s9/goal_169_display.png)
- [FLAG, 4:3](reports/b71_s9/flag_43_display.png) and [16:9](reports/b71_s9/flag_169_display.png)
- Machine-readable receipts: `label_sweep.json`, `states.json`, `volume.json`, `scene_byte_audit.json`.

**PROVED volume:** 323,808 appended bytes at each aspect, unchanged; 34 TXTR, one SCNE, zero FONT, 47 quads. Limit remains strictly below 400,000 bytes. Scene length stays 20,352 decoded bytes. The scene changes {audit['False']['scene_changed_byte_count']} bytes at 4:3 and {audit['True']['scene_changed_byte_count']} at 16:9. Changed ranges and hashes are recorded in the audit; raw material records and texture chunks are identical. The later custom-anchor check changes no default appendix byte.

**UNWITNESSED:** actual GPU depth-surface/enable state at the reported frame, hardware blending/sampling/cache behavior, gameplay predicate values at that frame, intro/runtime memory behavior, and whether disc p fixes the reported missing label. CPU-native plus software raster is not an emulator or played-game witness. The lead should not mark the original symptom resolved from these previews alone.

## Integration and prepared disc

`reports/b71_s9/build_testdisc71.py` is prepared, syntax/AST checked, and **was not run or imported**. Its plan function is AST-identical to S6/disc n: Advanced preset with Scorebug, runtime, modern colour, modern Arrowhead and widescreen enabled. Name: **NFL 2K5 MOD TEST 2026-09-16p (down label fix)**. It retains the S6 readbacks and patch-archive handling. The current release's colour-strength default remains in force. No disc or patch archive was created or deleted.

The owner, generated C engine, static XBE writer and persistent scorebar writer are unchanged. Owner `code_for(0,0)` SHA-256: `{inputs['owner_sha256']}`; `build_runtime.py --check` passes. Compiler pins were regenerated (retained legacy compiler pins remain identical); sprite hashes are in `volume.json`/`scene_byte_audit.json`. `packaging/repin.py --apply` refreshes provider hashes.

**Manifest refresh required:** `nfl2k5_cave_manifest.source_fingerprints()` at {line('mod_editor/core/nfl2k5_cave_manifest.py','def source_fingerprints')} observes changed `mod_editor/core/nfl2k5_scorebug_sprite.py` and `tools/nfl2k5_scorebug_projection.py`. Scene descriptor order, push-buffer order in the brand batch and sprite depth/table values change. No new cave, reservation, owner byte or XBE write is introduced. The protected cave manifest was deliberately left for hotfix integration, which must regenerate it and rerun XBE cave/memory/pairwise gates on the combined tree. No registry capability or protected GUI/dispatcher/packaging-check edit is needed. This supersedes S9-relevant statements in the inherited root `WIRING.md` without rewriting that older handoff.

Played retest: 1st & 10 with both teams possessing, downs 2–4, numeric/Inches/GOAL distances, transition through FLAG/ball-on, both display aspects, with play-clock digits, ticks, logos and watermark visible. If the label is still missing, capture the four event-request words, `0xA95A00`, the field's live colors/UVs and bound descriptor during the blank frame. A further owner change should follow that evidence.

## Validation ledger

The final runner completed **{validation['suites']} standalone suites, {validation['tests']} reported tests, {validation['skips']} explicitly reported skips**, plus strict registry validation (176 capabilities). The final custom-anchor regression suite adds its separate five-test rerun. Exact skip reasons remain in the individual logs.

Each verification/forensic run below has its exact argv, UTC timestamps, elapsed seconds and exit status in the adjacent `.result.json`; stdout/stderr is in the linked log. Environment: `PYTHONPATH` is the worktree and `QT_QPA_PLATFORM=offscreen`. The table records failed investigative attempts as well as final successes. Routine read/edit tool calls and initial private-Git setup were not stopwatch-wrapped; no timing is invented for them.

The first delivery whitespace check also rejected trailing padding on disassembled no-operand instructions. Log trailing whitespace was normalized without changing addresses, instruction text, hashes, line numbers or test results; that failed check is retained in `.scratch/delivery_commands.json`.

Two corrected harness failures are retained: `submission-shipped` initially hit an unmapped read because the preview's stubbed `28110` was not restored; `submission-shipped-restored` fixes that boundary. `prove-states` passed its 400 numeric states at 4:3 then expected mixed-case “Goal” instead of the owner's existing uppercase “GOAL”; `prove-states-final` corrects that expectation and completes both aspects. Neither failure required a game-code change. Initial orphan-style shell launches did not survive the sandbox PID namespace; subsequent heavy runs use the detached-child supervisor.

| UTC start | Seconds | Exit | Exact command | Output |
|---|---:|---:|---|---|
'''
for row in rows:
 command=shlex.join(row['argv']).replace('|','\\|')
 text+=f"| {row['start_utc']} | {row['seconds']} | {row['exit_code']} | `{command}` | [{row['name']}](reports/b71_s9/{row['name']}.log) |\n"
text+='\nThe final suite runner includes every standalone scorebug/scorebar suite, both root layout/project suites, provider integrity, product catalog, phase1 packaging, build/Qt, allocator/space, and strict registry validation. Individual logs record test counts and any precise skips. The new anchor regression is rerun separately against final sources; the byte audit confirms the default payload exercised by the sweep and earlier suites is unchanged.\n\nCommits present when this report was generated:\n\n```text\n'+commits+'\n```\n\nThe evidence/report commit and final bundle verification are recorded after this report is committed in `.scratch/delivery_commands.json` (exact argv, time and exit status) and `.scratch/delivery.json` (head and bundle SHA-256). This avoids embedding a commit hash or bundle checksum inside itself. The normal Git worktree may still display changes because commits intentionally live only in the private Git directory.\n'
(ROOT/'ASTRA_REPORT.md').write_text(text)
(ROOT/'ASTRA_LAST_MESSAGE.md').write_text('''Implemented and committed the sprite submission-order candidate on `astra/b71-s9-down-label` in `.scratch/astra-b71-s9.git`.

The shipped plate already precedes the label; the proposed overdraw cause is disproved in the bounded trace. The witnessed in-game disappearance remains unexplained and the candidate remains UNWITNESSED in game.

Deliverables: `.scratch/astra-b71-s9.bundle`, `ASTRA_REPORT.md`, native command/UV/alpha proofs and the 50-state contact sheet in `reports/b71_s9/`. All final requested suites and strict validation pass; 808 native label states pass at both aspects. Append stays 323,808 bytes. The test-disc p builder is prepared only. No push, emulator or disc build.

Integration must refresh the cave manifest's changed source fingerprints and rerun the combined XBE gates. Owner machine code is unchanged.

ASTRA_DONE
''')
print('wrote ASTRA_REPORT.md and ASTRA_LAST_MESSAGE.md;',len(rows),'command receipts')

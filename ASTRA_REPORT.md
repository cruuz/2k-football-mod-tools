# b72-s3: diagnostic foundation, not a beta 72.1 candidate

Base: `6944f5626b17f2ec6c1b56d854c0d00ecc55cc9e`. Bundle branch: `b72-s3`.

**The requested rebuild is incomplete. Do not build a candidate disc from this job.** Step 1 has not reproduced the dark label, so the production template, layout, compiler and runtime remain unchanged. No in-game repair is claimed. The tools explicitly report failed calibration.

The report motivating this work says: "this 1st and 10 issue has been present for a while" and "color accents must be team specific. why is there pink on the raiders?" The screenshots contradict the previous implication that a passing preview and ESPN matcher establish in-game readability. They do not.

## Step 1: measurements and bounded proof

The comparison tool normalizes the screenshots to 1920 by 1080 and measures the fixed down-label region. These are whole-region min / median / max luminance values, not glyph-core measurements. The middle screenshot's exact event state is uncertain; `field_goal_setup` is an explicit diagnostic assumption.

| Capture | Supplied measurement | New screenshot measurement | Current software preview |
| --- | --- | --- | --- |
| Raiders ball, 112349 | 19 / 27 / 67 | 19 / 28.77 / 64.86 | 24.83 / 82.43 / 255 |
| Field goal setup, 112501 | 19 / 25 / 90 | 19 / 26.56 / 63.35 | 0 / 68.23 / 255 |
| Lions ball, 112603 | 18 / 22 / 74 | 18.86 / 22.77 / 70.80 | 7.22 / 53.59 / 255 |

The screenshot measurement itself agrees within 15 except the field-goal maximum, where different crop alignment loses the brightest pixel. **None of the previews reproduces the screenshot within 15.** Bright label ink is absent from all three measured screenshot regions and present in the previews. This is a failed calibration result, not a repaired preview.

Evidence lives in `reports/b72_s3/*_comparison.json`, `baseline_geometry.json`, `disc_probe.json`, and `native_order_{False,True}.json`.

| Candidate cause | What was actually checked | Conclusion |
| --- | --- | --- |
| Plate submitted after label | Executed retail `0x243D0` descriptor traversal and push-buffer copying in Unicorn, for both aspects, using compiled scene descriptors. Native functions are hash guarded. | Plate material `dscore_buga` submits before label `yscore_buga1`. The simple reversed-order hypothesis is not supported by this fixture. |
| Possession tint reaches label | Native owner output, material tint and label vertex colors; read back after the native text walk too. | Label vertices and its material tint are `0xFFFFFFFF` in the tested fixtures. No scene bytes change during that text walk. This does not establish live GPU state. |
| Modern colour changes appended HUD | Read only the appended HUD range from the supplied disc-o `.2k5patch`, compared each of its 35 component hashes with this compiler, then replayed its patched executable in memory. | All 35 components match. Modern colour did not alter that appended atlas or scene. The software replay remains bright. Other global renderer effects are not excluded. |
| Descriptor / format / LOD | Compiled texture descriptors, shared atlas bindings and native texture relocation. Label and other sprite text share the atlas. | No cause established. Actual GPU sampler and shader execution remain unmodeled. |
| Copied native slide/fade color | Owner code and settled native label vertices, plus retained existing visibility tests. | The owner copies visibility decisions, not the game's label color. Tested visible glyph colors are opaque white. Untested live transition state is not excluded. |

The descriptor walk's visible order is body, wings/brand, plate/rims, home logo, label/ticks, score/clock fields, away logo. Hidden event materials also appear in the descriptor walk. All sampled active world depths equal `99.9936990737915`. Native render-state encoding at `0x2FC80` emits depth comparison `0x203`, LEQUAL, not LESS. The register interpretation is checked against [xemu's NV2A register definitions](https://raw.githubusercontent.com/xemu-project/xemu/master/hw/xbox/nv2a/nv2a_regs.h).

This proves CPU submission order in a bounded fixture. It does not prove the final composited image. Shader setup `0x315C0`, material binding `0x24160` and matrix upload `0x22950` are named boundaries in the new tracer. The existing `tools/nfl2k5_scorebug_projection.py:native_text_draw` replaces scene submit `0x21860`; `render_native` implements software texture sampling and source-alpha blending. That unmodeled GPU boundary is the concrete remaining gap. The dark-label root cause is **unproved**. No artificial label-darkening multiplier was fitted to the screenshots.

## Delivered tools and limitations

`tools/scorebug_sprite/render.py` supports named teams, named or JSON states, possession and both aspects. `--all-teams` renders the current 32 NFL runtime inputs and writes a contact sheet with measurement metadata. Its terminal and JSON say calibration failed. It is not the calibrated command requested by acceptance.

`tools/scorebug_sprite/compare_ingame.py` writes per-field differences and a typed Jev request. Saved MCP responses can be supplied with `--jev-response`; `--jev-live` uses the SDK outside the sandbox. Suggested JSON keys are inspection targets, never automatic changes. The three supplied captures were compared. Their judge verdict cannot agree with a proven cause because there is no proven cause.

The five Jev modules are under `tools/scorebug_sprite/jev/`, with shared descriptor and budget code. No pixels go to Jev. Code performs measurements, arithmetic, thresholds and accept/reject decisions. Confidence thresholds are explicit, but the model probabilities have not been empirically calibrated against a human-labeled truth set.

| Tool | Live work | What code kept or rejected | Remaining work |
| --- | --- | --- | --- |
| Broadcast miner | 200 frames, stratified across the every-tenth-frame subset of the 30,044-frame reel, in ten MCP batches of 20 | 40 clean, confident descriptors accepted: 7 normal, 30 first-and-ten, 2 short-yardage, 1 third-and-long. 160 retained as rejected. | Banner templates, reliable absence examples, clock-state inference, red-zone evidence and a complete state taxonomy. |
| Layout search | One `jev_next_input` diagnostic proposal | Jev proposed a larger label at 0.16 confidence, goal probability 0.01, should-act false. Calibration gate rejected search before any mutation. | Real measured search and equal-step random baseline curves, followed by confirmed convergence. There are no actual optimization curves in this job. |
| Accent chooser | Two phrasings for 52 slots, then 64 refreshed NFL calls after the authoritative file arrived; 168 accent calls total | Final candidates have palette provenance and white-text contrast at least 4.5. 42 slots require review. Raiders picked `#646464`, a darker variant of official silver, for wing/rim/plate; wash follows wing. | Apply a neutral template and build-time tints; bind extra slots; measure logo fitting. Supplied shade disputes remain visible in metadata. |
| Screenshot judge | Three calls, one per supplied screenshot | Down-label mismatch classified `missing_element`, with confidence 0.83, 0.79 and 0.89. Prompt explicitly distinguishes missing bright ink from an unproved occlusion cause. | A causal verdict after native/GPU evidence proves the cause. Current answers are not independent causal proof. |
| Design rubric | Three before-state scores | Scores 0.47, 0.41 and 0.50 on the 0 to 4 rubric, with confidence 0.61, 0.65 and 0.59. | After-state scores and full hierarchy, overlap, team-identity verification. |

Every MCP result is retained in `reports/b72_s3/jev_calls.jsonl`. There are 186 MCP receipts, including 200 batch states: 376 total judged states/calls. Local receipt cost and the conservative shared-log delta are recorded separately in `reports/b72_s3/jev_usage.json`; both are below the $3 cap. Shared usage can include other jobs, so its entire delta is conservatively charged against this job's guard.

Jev did not identify a verified rendering cause. Its initial routing answer favored template colors at only 0.28 confidence while splitting probability between template and native work; that was insufficient evidence and did not control the investigation. The accent phrasings disagree in several cases, so those choices are review candidates. No live accent choice required a contrast override; the malicious foreign-color rejection is a synthetic regression test, not a claim that Jev actually proposed pink. A code audit found no direct contradictions between Jev state labels and the explicitly confident down labels supplied in the pilot; this narrow check does not establish visual correctness. The pilot descriptor initially labeled the clock using a bright-ink convention even though this layout uses dark clock text. That code defect was corrected after the pilot and is explicitly a limitation of those retained pilot decisions. Do not treat those decisions as a calibrated benchmark.

The outside-sandbox full miner replay is shipped, with per-request hashes that refuse mismatched resume journals. It has not been run. Improve the descriptor limitations before spending on the full reel. See `tools/scorebug_sprite/jev/README.md` for commands.

## Team source and authoring status

The final 32 NFL candidate palettes use the supplied authoritative `data/nfl2k5_scorebug_sprite/team_colors_official_2026.json`, which arrived during the run. Its palette entries and web citations are retained and pinned. Packaging rejected one absolute host path in a source citation; that citation was made repository-relative. `official_source_normalization.json` records the original and packaged hashes, and an assertion verified that this normalization did not change any Jev request. The file resolves current shade choices using cited league/team sources and records disputes. Code excludes `logo_detail_only` colors from large fills, retains each chosen source citation, and flags a chosen low-confidence source shade for review. This job uses that supplied research; it does not claim independent verification of every cited page.

The initial retail-palette run is retained under `reports/b72_s3/accents/`. The refreshed 64 NFL judgments and final 52-slot swatch sheet are under `reports/b72_s3/official_accents/`. Extra-slot answers are reused only for unchanged retail inputs, with per-team answer provenance recorded. Actual equal-hex choices are treated as agreement even when their variant identifiers differ. No live pick violated the contrast gate.

Extra-slot source: the pinned retail primary/secondary color table at `0x4E7FE0..0x4E88A0`, stride `0x1C`, SHA-256 `0713d8ca89333142d86dad04904d4804ea76687301a50df7265b5407302036e6`, plus roster slot metadata. Historical slots inherit their asset-code palette. USER1, USER2, UDC, LAL, CES, BFM and LAD use an explicitly marked neutral fallback because they lack valid source colors. Custom teams must supply their own primary/secondary colors to replace that fallback.

`team_accents.json` covers 52 slots, but it is inactive review data. `logo_fit` entries are generic defaults, not fitted results. Variants are documented RGB lighter/darker transforms of an allowed source color. Wash uses the chosen wing color. The supplied `TEAM_COLOURS_NOTE.md` remains an unedited input; the authoritative JSON is included as a required dataset.

The original template still contains KC/DEN colors, and the original layout remains the active source. A no-foreign-tint test over actual renders is therefore not claimed. The added test proves provenance and contrast of candidate JSON only. The final review swatches are `reports/b72_s3/official_accents/contact_sheet.png`; the production baseline sheets deliberately still show existing defects.

## Validation and size

`match_espn.py` was run without `--reuse`: **95 PASS / 0 FAIL / 9 IMPOSSIBLE**. It is unchanged-reference evidence, not in-game validation. Detailed residuals and images are in `reports/b72_s3/match/`.

Both products were staged into temporary directories, then their release and runtime closure checks executed from the staged trees. Closure checks are rerun after making the supplied palette file's host citation repository-relative; the final receipts are in `closures.json`. The release check itself was not changed. Temporary stages were removed. Nothing was published, no installer or disc was built, and no manifest was regenerated.

New modules and metadata are declared in `packaging/release-allowlist.txt`, as explicitly authorized by this brief. `packaging/scorebug_replication_pins.py` pins them; `packaging/repin.py --apply` refreshes those pins. No protected check implementation was changed. No registry or application-panel wiring is proposed.

The appended GAMEDATA remains **323,808 bytes**, delta **0 bytes**, with **76,192 bytes** headroom against 400,000. The tools and candidate JSON do not change game resources. No all-team, both-aspect repaired glyph-core/contrast table exists because there is no repaired output. Baseline measurements must not be relabeled as acceptance results.

The baseline-only 32-team, both-aspect measurement table is `reports/b72_s3/baseline_readability.md`. Every row has calibration FAIL. It must not be confused with the missing repaired-output acceptance table.

Full validation receipts and timings are in `reports/b72_s3/checks/`. The command list is reproducible through `run_checks.py` and `run_closures.py` in that private report directory. `VALIDATION.md` records the final pass/failure inventory, including timeouts and paths over 100 seconds. The required test gate is not green if any such row remains. The separate allocator run with a 600-second outer limit passed all 7 tests in 466.192 seconds; that result does not override its 420-second gate failure. A 60-second faulthandler diagnostic locates the allocator delay in `nfl2k5_xbe_space.py:244` (`_digest`), through `_validate_scaleout`, while the unchanged allocator test composes its complete owner stack in `setUpClass`. See `beta61_timeout_location.log`. No allocator code was changed. Historical s1 receipts independently record 426.389 seconds for the allocator file, 388.082 for roster storage, 120.533 for scorebug assets, 199.155 for freeze, and 259.889 for freeze v2. Those earlier timings also exceed the new 100-second requirement; they do not waive this job's gate. See `previous_timings.json`.

## Integration and witness gate

Do not integrate this as a completed scorebug rebuild. The next technical step is to extend the native material/shader/sampler audit across the named GPU boundary, or supply a captured render-state trace from the already witnessed failure, then make the preview reproduce the measured dark label. The subsequent neutral-template, per-team build-time tint, extra-slot binding and SD glyph work remains necessary. Full Jev search, random control and after-rubric remain necessary too.

After that work passes offline gates, the integrator builds a test disc. Required witness screens: Lions at Raiders with each team possessing; Chiefs matchup; a dark-color team such as Baltimore; all of these at 4:3 and 16:9; normal 1st-and-10, later downs, and field-goal/event transitions. All proposed future in-game results remain UNWITNESSED until those screens are played and approved.

The sandbox cannot write this worktree's shared Git metadata. Commits and branch `b72-s3` therefore live in `.scratch/b72-s3.git`, using the existing object store read-only, and are delivered as the verified `.scratch/astra-b72-s3.bundle`. The launcher checkout remains on its original branch/base. No push or release steps were taken.

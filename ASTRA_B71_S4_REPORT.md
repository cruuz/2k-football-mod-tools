# Beta 71 S4 — painted ESPN bar

## Result

The painted v4 implementation is delivered on the private branch `astra/b71-s4-painted-bar`, based on the completed S3 HEAD `464423f0889581182f4a6de53971ecab23be19d5`.

**Boundary acceptance is proved; visual equality is not.** Every measured region, native text box and thresholded text-ink box is within one HUD pixel in 4:3 and widescreen. The append is **410,624 bytes**, 2,944 bytes below v3. The code emits **1,380 bytes** inside the existing 1,408-byte RX allocation, with 128 bytes of RW state. `compare().exact_match` remains **false** in both aspects; this is not an exact ESPN image match.

All requested standalone suites, strict registry validation and both detached XBE gates passed on the final implementation.

Compare the actual output: [4:3, ESPN above / native below at 2×](reports/b71_s4/compare_43.png), [widescreen at 2×](reports/b71_s4/compare_wide.png), [event and matchup contact sheet](reports/b71_s4/states_contact_sheet.png). The supplied `bar_compare_espn_vs_s3_render_2x.png` was inspected before editing.

## The six residuals

1. **Painted body and ramps.** `atlas_mnf()` paints at twice source resolution, then downsamples tiles into a same-name **256×512 P8** `score_buga` atlas. The frame tile is 256×110, stretched over the 1,041×110 source rectangle; this horizontal storage limit remains visible in fine edges. Body RGB is (37,37,37), with an r=8 silhouette, two-source-pixel top rim (60,64,70) and bottom rim (13,20,28). Two neutral white alpha ramps are tinted by the owner and blend smoothly to the charcoal inner wing edge. Score-panel slabs are gone: score digits sit over the same flat body. The housing, capsule, red-cell silhouette and plate are painted tiles.
2. **Plate and label.** Plate 837..1083 × 947..983; a separate top-centre triangle uses the same tintable white mask. The complete v3 primary/near-black-secondary table stays. Roboto Condensed Bold is rasterized at 64 pixels (46-pixel cap, twice the target 23), retained as a checked-in mask sheet, and downsampled into existing ASCII cells in slot 9. Digits, ordinal letters, ampersand, Goal/and letters and space remain available to native formatting. The font authoring source and SHA are in `painted_label_2x.json`; no installed font is required at runtime.
3. **Capsule.** White 839..1019 × 999..1039 and red (215,0,51) cell 1019..1082 × 999..1040. A 41-source-pixel painted backing covers the capsule; the white region bottom is therefore 0.413 HUD pixel below its 40-pixel reference box. Quarter is dark (30,30,30), with raised smaller capitals; clock is black bold; play-clock digits are white. Native countdown and visibility remain, with the existing below-five-seconds red pulse. Hidden play clock removes its digit/pulse layer; the painted red backing remains.
4. **Scores and ticks.** Private large-score cells are now 26×48 texels, with 53-source-pixel draw height and RGB (225,225,225). Compact multi-digit cells share those UVs and remain clear of the plate for 28, 100 and 999. Three bright (246,246,246) 20-source-pixel ticks use native timeout callbacks with 10-pixel gaps. Their ink lands within one HUD pixel of the requested y=1032..1038 boxes.
5. **Logos.** One shared 64×64 logo cell per team replaces separate home/away textures. The v3 aspect fit is retained in a 200×107 source quad; DEN is enlarged to fill that height. The original small source marks still limit edge quality. Both DEN at KC and NO at DEN were rendered in both aspects; NO uses its gold secondary possession plate.
6. **Retail states.** Native flag, score-event (FUMBLE), hang-time, ball-on and hidden play-clock states were rendered individually at both aspects. Their slabs sample flat charcoal and their native text remains readable. `all_events` intentionally overlays incompatible labels and is diagnostic only. Native formatting, callback ABI, missing-FONT fallback, score ranges, timeouts and urgency cases are covered by active native suites.

## Native routes and allocation

The appended same-name atlas wins the ordinary HUD resource lookup. The original 64×64 static fallback atlas remains in its fixed span. Slot 9 uses an appended same-name `FirstPersonComic` FONT, preserving the retail root/boot-loop lookup; quarter uses appended `core_bug`. Their live descriptor references are field-relative, including a backwards range-table reference resolved with x86 32-bit wrapping. No parallel invented FONT record replaces the native loader.

The scene stays in its **4,800-byte compressed span** with retail wrapper/scratch size retained by the fill compressor. Existing NV2A command spans are rewritten to plain quads (13 quads plus the pointer triangle across 11 submeshes). The steady visible bar has 19 triangles. Retail nine-slice indices and score slabs no longer draw. SHAPE UV scale/bias is normalized to (0.5,0.5,0.5,0.5), avoiding the retail 64-pixel correction sampling a neighbouring white atlas texel on event slabs.

Material ownership: `cscore_buga` draws body, housing and capsule; `yscore_buga` / `yscore_buga1` draw tintable away/home masks; `zscore_buga` / `hscore_buga` draw shared logos; `dscore_buga` draws plate and pointer. The spare `score_buga` material owns the red pulse cell. Native event materials retain separate charcoal quads. Hang time owns the spare event slab, preserving its formatter and visibility.

Both sides resolve the canonical `sbXXh0` resource. Per-team plate and wing ARGB words occupy unused TXTR header padding immediately before the native descriptor (descriptor −8 / −4), sealed by full compiler hashes. Setup caches them in RW state and updates the masks and possession plate. This removes inline colour tables and keeps the owner in the established legacy allocation. Missing HUD/FONT lookups retain native score and clock callbacks; private codepoints are installed only after successful slot-9 lookup.

Score ranges are U+0080..0089 (large) and U+0090..0099 (compact), clock U+00B0..00B9 and play clock U+00C0..00C9. Native clock formatters still produce the values before remapping. Event ASCII remains available. The owner setup and update displaced calls execute once, with their original ABI.

### Exact volume

| Appended component | Count × bytes | Total bytes | Native heap bytes |
| --- | ---: | ---: | ---: |
| Shared 64×64 team TXTR | 32 × 5,280 | 168,960 | 172,032 |
| Neutral 32×32 TXTR | 1 × 2,208 | 2,208 | 2,304 |
| Painted 256×512 P8 atlas | 1 × 132,256 | 132,256 | 132,352 |
| Slot-9 FirstPersonComic FONT, 256×256 | 1 × 80,160 | 80,160 | 80,256 |
| core_bug quarter FONT, 128×128 | 1 × 27,040 | 27,040 | 27,136 |
| **Total** | **34 TXTR + 2 FONT** | **410,624** | **414,080** |

The pack grows by **411,648 bytes** after sector alignment. V3 appended 413,568 bytes: v4 saves **2,944 bytes (0.71%)**. The payload stays in the historically viable ~0.4 MB class. This is a byte/loader-allocation proof, not a played-game peak-memory or freeze guarantee.

## Measurements

Reference: `frame_012001.jpg`, 1920×1080, SHA-256 `01622a78b6778f089e4b242c8deda42833b10ae123150ed5bc8989dc483929d7`. The corrected S4 boxes supersede the older broad v3 comparison rectangles. Source coordinates map to the active 640×448 HUD with y inset 16; widescreen additionally contracts x around 320 by 27/32. Boundary errors below are HUD pixels, not pixels of the enlarged comparison sheet.

`prove_v4.py` executes the native callbacks and scene transforms, then calls `compare()` with `MNF_V4_COMPARE_REGIONS` and the requested text boxes. Software raster output is measured independently for text ink. [measurements.json](reports/b71_s4/measurements.json) includes full native boxes, thresholded ink boxes and source-restored ink boxes.

### Per-region boundary error and RGB MAE

| Region | 4:3 boundary | Wide boundary | 4:3 RGB MAE | Wide RGB MAE |
| --- | ---: | ---: | ---: | ---: |
| centre_pill | 0.005273 | 0.005273 | 42.503 | 42.540 |
| clock_strip | 0.004964 | 0.004189 | 32.807 | 32.417 |
| frame_rim | 0.006285 | 0.006285 | 40.227 | 39.743 |
| housing | 0.005273 | 0.005273 | 29.650 | 29.048 |
| left_panel | 0.006285 | 0.006285 | 33.642 | 33.431 |
| play_clock_cell | 0.004344 | 0.003666 | 14.979 | 13.848 |
| pointer | 0.006285 | 0.006285 | 41.700 | 36.708 |
| right_panel | 0.006285 | 0.006285 | 53.753 | 53.281 |
| white_capsule | 0.413169 | 0.413169 | 39.046 | 38.606 |

The separate away/home logo quads have maximum boundary error of 0.005534 HUD pixel. [logo_fit.json](reports/b71_s4/logo_fit.json) records the source hashes and transparent-cell bounds: DEN, KC and NO each fill 107 source pixels vertically, with fitted widths 178.125, 165.625 and 87.5. The uniform fit is rounded to the 64×64 texel grid. These cell bounds are distinct from a claim of exact photographed logo contours.

Mean region RGB MAE: **36.479 / 35.514** (4:3 / wide). The comparison threshold is 8; neither image passes it. Full-frame containment is empty and every visible triangle has consistent winding. The reference still differs in bevel/reflection detail, plate colour (the requested v3 team table is retained), mark contours, text shapes and sampled edges. These differences must not be described as an exact ESPN match.

### Text boundaries

Each row reports the greatest coordinate error for the native quad and measured raster ink. Source rectangles use exclusive right/bottom edges.

| Text | Requested source box | 4:3 native / ink HUD error | Wide native / ink HUD error |
| --- | --- | ---: | ---: |
| away_score | [736, 965, 776, 1018] | 0.333597 / 0.666667 | 0.281472 / 0.296296 |
| away_ticks | [717, 1032, 796, 1038] | 0.333323 / 0.666667 | 0.325939 / 0.422222 |
| clock | [920, 1006, 1000, 1033] | 0.696309 / 0.696296 | 0.696309 / 0.696296 |
| down | [898, 955, 1021, 978] | 0.851852 / 0.666667 | 0.851852 / 0.437500 |
| home_score | [1138, 965, 1180, 1018] | 0.333105 / 0.666667 | 0.281058 / 0.296296 |
| home_ticks | [1120, 1032, 1198, 1038] | 0.333333 / 0.666667 | 0.325939 / 0.422222 |
| play_clock | [1042, 1009, 1057, 1028] | 0.666667 / 0.666667 | 0.562500 / 0.937500 |
| quarter | [850, 1009, 892, 1028] | 0.451852 / 0.666667 | 0.451852 / 0.570370 |

| Text | Source-restored ink, 4:3 | Source-restored ink, wide | Max HUD error, 4:3 / wide |
| --- | --- | --- | ---: |
| away_score | [736, 965, 773, 1017] | [737, 965, 774, 1017] | 1.000000 / 0.562500 |
| away_ticks | [717, 1032, 798, 1039] | [719, 1032, 796, 1039] | 0.666667 / 0.562500 |
| clock | [921, 1007, 999, 1035] | [920, 1007, 999, 1035] | 0.829630 / 0.829630 |
| down | [899, 955, 1020, 980] | [899, 955, 1020, 980] | 0.829630 / 0.829630 |
| home_score | [1141, 965, 1178, 1017] | [1139, 965, 1180, 1017] | 1.000000 / 0.414815 |
| home_ticks | [1119, 1032, 1200, 1039] | [1120, 1032, 1198, 1039] | 0.666667 / 0.414815 |
| play_clock | [1044, 1008, 1058, 1027] | [1045, 1008, 1059, 1027] | 0.666667 / 0.843750 |
| quarter | [850, 1010, 891, 1030] | [850, 1010, 892, 1030] | 0.829630 / 0.829630 |

### Per-text RGB MAE

These use the same rounded HUD reference rectangles as `compare()`, including the background inside each ink bounding box. No glyph segmentation or alignment adjustment is applied. [text_rgb_mae.json](reports/b71_s4/text_rgb_mae.json) seals the rendered image hashes.

| Text | 4:3 RGB MAE | Wide RGB MAE |
| --- | ---: | ---: |
| away_score | 34.472 | 32.800 |
| away_ticks | 48.556 | 46.348 |
| clock | 90.504 | 89.806 |
| down | 67.260 | 67.482 |
| home_score | 31.718 | 32.066 |
| home_ticks | 50.291 | 43.323 |
| play_clock | 63.333 | 60.500 |
| quarter | 46.214 | 43.964 |

## Regeneration and tests

Compiler pins were regenerated after the final UV correction: [compiler_pins.json](reports/b71_s4/compiler_pins.json), `pins-uv.log`. `packaging/repin.py --apply` refreshed provider seals. The unified visual provider now seals the assets module used for arbitrary atlas dimensions; its product allowlist includes that module and the two authored label files. The strict provider count is 286.

The S3 `refresh_manifest.py` recipe observed the complete forward XBE stack from the A5 manifest, retaining historical retail reservations and excluding the shared rules helper from duplicate ownership. The final manifest has **13,095 spans**, with **138 observed calls**. SHA-256: `0a182996cecebcc5efacedb1fd3b04949fb59a612a2167b9d2fb9c1af6dfbcb6`. Scorebug owner code is `0x14BAA60..0x14BAFE0`; RW data is `0x14BB010..0x14BB090` in this union. The projection records `release_manifest=false`, `disc_built=false`, `runtime_witnessed=false`, `production_regeneration_required=true`; inherited disc fields are historical. External production packaging must regenerate its disc receipt.

Both XBE gates were launched **detached** using `setsid nohup`, redirected logs and stdin `/dev/null`, then polled. A foreground shell waited for each detached child to keep the sandbox session alive. No `pkill -f` was used. Their full classes cover both installation orders, allocation scale-out and oracle checks.

### Final standalone results

The `-delivery` driver runs every standalone scorebug suite plus provider integrity, product catalog and phase1 packaging in independent offscreen Python processes. It records source hashes before and after. Strict validation retains default file checks. Earlier runs remain diagnostic; only this final frozen-source run and the named final gates are the delivery verdict.

| Command | Exit | Tests | Skips | Seconds |
| --- | ---: | ---: | ---: | ---: |
| [test_apf_scorebug_workspace_qt-delivery](reports/b71_s4/test_apf_scorebug_workspace_qt-delivery.log) | 0 | 11 | 0 | 0.604 |
| [test_nfl2k5_scorebug_assets-delivery](reports/b71_s4/test_nfl2k5_scorebug_assets-delivery.log) | 0 | 8 | 1 | 150.732 |
| [test_nfl2k5_scorebug_author-delivery](reports/b71_s4/test_nfl2k5_scorebug_author-delivery.log) | 0 | 12 | 0 | 6.704 |
| [test_nfl2k5_scorebug_exact-delivery](reports/b71_s4/test_nfl2k5_scorebug_exact-delivery.log) | 0 | 8 | 0 | 78.833 |
| [test_nfl2k5_scorebug_fonts-delivery](reports/b71_s4/test_nfl2k5_scorebug_fonts-delivery.log) | 0 | 10 | 5 | 8.912 |
| [test_nfl2k5_scorebug_freeze-delivery](reports/b71_s4/test_nfl2k5_scorebug_freeze-delivery.log) | 0 | 7 | 0 | 238.596 |
| [test_nfl2k5_scorebug_freeze_v2-delivery](reports/b71_s4/test_nfl2k5_scorebug_freeze_v2-delivery.log) | 0 | 7 | 0 | 333.344 |
| [test_nfl2k5_scorebug_ingame-delivery](reports/b71_s4/test_nfl2k5_scorebug_ingame-delivery.log) | 0 | 11 | 0 | 16.023 |
| [test_nfl2k5_scorebug_ingame_fix-delivery](reports/b71_s4/test_nfl2k5_scorebug_ingame_fix-delivery.log) | 0 | 9 | 0 | 140.809 |
| [test_nfl2k5_scorebug_mnf-delivery](reports/b71_s4/test_nfl2k5_scorebug_mnf-delivery.log) | 0 | 10 | 0 | 12.488 |
| [test_nfl2k5_scorebug_mnf_v3-delivery](reports/b71_s4/test_nfl2k5_scorebug_mnf_v3-delivery.log) | 0 | 7 | 0 | 54.573 |
| [test_nfl2k5_scorebug_native-delivery](reports/b71_s4/test_nfl2k5_scorebug_native-delivery.log) | 0 | 4 | 0 | 152.177 |
| [test_nfl2k5_scorebug_projection-delivery](reports/b71_s4/test_nfl2k5_scorebug_projection-delivery.log) | 0 | 14 | 0 | 65.083 |
| [test_nfl2k5_scorebug_resources-delivery](reports/b71_s4/test_nfl2k5_scorebug_resources-delivery.log) | 0 | 6 | 0 | 307.742 |
| [test_nfl2k5_scorebug_runtime-delivery](reports/b71_s4/test_nfl2k5_scorebug_runtime-delivery.log) | 0 | 12 | 0 | 180.567 |
| [test_nfl2k5_scorebug_source_art-delivery](reports/b71_s4/test_nfl2k5_scorebug_source_art-delivery.log) | 0 | 13 | 3 | 0.974 |
| [test_nfl2k5_scorebug_template-delivery](reports/b71_s4/test_nfl2k5_scorebug_template-delivery.log) | 0 | 19 | 0 | 12.228 |
| [test_nfl2k5_scorebug_template_release-delivery](reports/b71_s4/test_nfl2k5_scorebug_template_release-delivery.log) | 0 | 5 | 0 | 0.977 |
| [test_nfl2k5_scorebug_unified_adapter-delivery](reports/b71_s4/test_nfl2k5_scorebug_unified_adapter-delivery.log) | 0 | 5 | 0 | 0.328 |
| [test_nfl2k5_scorebug_v10_ingame-delivery](reports/b71_s4/test_nfl2k5_scorebug_v10_ingame-delivery.log) | 0 | 11 | 0 | 14.083 |
| [test_nfl2k5_scorebug_v10_projection-delivery](reports/b71_s4/test_nfl2k5_scorebug_v10_projection-delivery.log) | 0 | 14 | 0 | 35.786 |
| [test_nfl2k5_scorebug_versions-delivery](reports/b71_s4/test_nfl2k5_scorebug_versions-delivery.log) | 0 | 4 | 0 | 12.658 |
| [test_scorebug_studio_panel_qt-delivery](reports/b71_s4/test_scorebug_studio_panel_qt-delivery.log) | 0 | 11 | 0 | 7.685 |
| [nfl2k5_scorebug_layout_test-delivery](reports/b71_s4/nfl2k5_scorebug_layout_test-delivery.log) | 0 | 15 | 6 | 2.296 |
| [nfl2k5_scorebug_mod_project_test-delivery](reports/b71_s4/nfl2k5_scorebug_mod_project_test-delivery.log) | 0 | 10 | 0 | 1.912 |
| [test_provider_integrity-delivery](reports/b71_s4/test_provider_integrity-delivery.log) | 0 | 7 | 0 | 15.476 |
| [test_product_catalog-delivery](reports/b71_s4/test_product_catalog-delivery.log) | 0 | 9 | 0 | 0.204 |
| [test_phase1_packaging-delivery](reports/b71_s4/test_phase1_packaging-delivery.log) | 0 | 23 | 0 | 2.872 |
| [registry-strict-delivery](reports/b71_s4/registry-strict-delivery.log) | 0 | — | 0 | 0.307 |
| [registry-strict-final-evidence](reports/b71_s4/registry-strict-final-evidence.log) | 0 | — | 0 | 0.158 |
| [xbe-memory-final](reports/b71_s4/xbe-memory-final.log) | 0 | 119 | 0 | 1732.185 |
| [xbe-cave-references-final](reports/b71_s4/xbe-cave-references-final.log) | 0 | 131 | 0 | 1958.445 |
| [owner-pairwise-final](reports/b71_s4/owner-pairwise-final.log) | 0 | 506 | 0 | 3180.792 |
| [cave-oracle-final](reports/b71_s4/cave-oracle-final.log) | 0 | 29 | 0 | 455.759 |

Final reported unittest cases including gates: **1067**, including **15 skips**. Frozen-source driver complete: **True**.

Skips retain the established precise boundaries: read-only Storage for the assets disc-copy transaction; five historical private-font-v8 cases; missing source-art fixtures; and historical layout image/glTF fixtures. Active current-font/native suites run. These skipped cases are not boot or disc evidence.

Exploratory failures are retained in the command ledger. An initial larger owner exceeded the full legacy allocator capacity; caching colours from logo header padding reduced it to 1,380 bytes. A manifest attempt detected source edits during observation and was rerun after freezing code. Later suite failures were obsolete separate-away-resource and FONT-state assertions, a missing-font callback guard, provider closure and missing ignored registry evidence. The final tests assert the new shared resources, native fallback callbacks and preserved event sampling. No gate assertions or registry file checks were relaxed. A misspelled cave-gate filename exited before execution; the correctly named detached gate supersedes it.

Strict registry validation initially lacked the same 75 ignored evidence files as S3. Real copies were restored from the existing read-only checkout, checked against S3 hashes: **2,063,157 bytes**. [evidence_hydration.json](reports/b71_s4/evidence_hydration.json) records them. These baseline ignored files are neither staged nor bundled.

## Registry, RC96 and prepared builder

The existing runtime capability row now describes v4 resource counts, measured boundaries, failed exact-pixel acceptance and evidence links. Runtime status remains `not-tested`, experimental and off in every preset. The RC96 bullet is anonymous and states the software-render/played-game limits.

[build_testdisc71.py](reports/b71_s4/build_testdisc71.py) follows the S3 builder pattern: `softdrink_advanced` preset, `scorebug`, `scorebug_runtime`, `modern_color`, `widescreen` all true. Prepared output:

`NFL 2K5 MOD TEST 2026-09-15j (painted bar + colour + widescreen)`

**The builder was not run, including `--plan-only`.** It was parsed/compiled and its literal name/options checked without importing or executing it; [builder_prepared.json](reports/b71_s4/builder_prepared.json) seals the file. The builds folder is read-only here. When run externally, it checks output access, refuses an existing named output, preserves patches, applies the inherited three-test-image retention policy, checks resource/XBE/477-colour-bundle/widescreen readback, and removes an incomplete disc on failure.

Import the bundle into the integration checkout before running the builder so external receipts record the delivered source head. No disc, patch archive or disc readback receipt was generated in this task.

## PROVED / UNWITNESSED

**PROVED:** authored atlas/FONT compilation and full hashes; same-name native resource binding; owner ABI, fallback, state and formatter execution; exact byte budgets; fixed scene span; corrected native boundaries and measured ink within one HUD pixel; both aspect transforms; individual event renders; multi-digit clearance; final passing suites and XBE gates as listed.

**NOT ACHIEVED:** pixel equality to the ESPN crop. The side-by-side is the review artifact, and RGB MAE remains above acceptance. It would be incorrect to call this the same image or to attribute remaining differences to untested GPU filtering.

**UNWITNESSED:** an actual intro/coin toss/kickoff load, peak memory during the intro, played-game transitions and visibility, GPU filtering, real score/timeout/possession changes and event animation. No emulator was opened. These require the external test build and a played match.

## Commits and delivery

The ordinary worktree `.git` and shared repository remain untouched. All commits use enumerated explicit paths in `.scratch/private.git`, branch `astra/b71-s4-painted-bar`. Implementation commits include `d74418b8` and `52cd8348`; later test/evidence/report commits are in the bundle. No push.

Bundle: `.scratch/astra-b71-s4.bundle`, prerequisite **`464423f0889581182f4a6de53971ecab23be19d5`**, the actual completed S3 worktree HEAD. The shared S3 branch name was stale, so the prerequisite uses that exact commit. The external delivery receipt in `.scratch/b71-s4-delivery.json` records the final head, bundle size and SHA after verification. Retail inputs remain read-only; no retail native FONT/TXTR/XBE/pack/disc binaries are bundled. Scratch usage is below 200 MB.

## Command ledger

[command_ledger.json](reports/b71_s4/command_ledger.json) contains exact argv, UTC start/end, duration and exit status for recorded compilation, proof and verification commands. Each named log retains complete output. Read-only discovery, patching, private-git setup, detached shell wrappers and report assembly are also in the session tool transcript. Failed exploratory runs are explicitly superseded, not erased.

| Name | UTC start | Seconds | Exit | Exact command |
| --- | --- | ---: | ---: | --- |
| [initial-render](reports/b71_s4/initial-render.log) | 2026-09-15T21:57:39.460927+00:00 | 5.896 | 0 | `python3 -c 'from pathlib import Path;from nfl2k5_scorebug_exact import Build;p=Path("extracted/ESPN NFL 2K5 (USA)/vc_53450030/0");b=Build(p,p.parents[1]/"default.xbe");g=b.render(Path("reports/b71_s4/initial.png"),runtime=True,matchup=("DEN","KC"),score_values=(7,7),previous_scores=(7,7),quarter=2,game_seconds=273,play_seconds=4,down=3);import json;Path("reports/b71_s4/initial.json").write_text(json.dumps(g));b.close()'` |
| [second-render](reports/b71_s4/second-render.log) | 2026-09-15T21:59:47.122414+00:00 | 6.07 | 0 | `python3 -c 'from pathlib import Path;from nfl2k5_scorebug_exact import Build;p=Path("extracted/ESPN NFL 2K5 (USA)/vc_53450030/0");b=Build(p,p.parents[1]/"default.xbe");g=b.render(Path("reports/b71_s4/second.png"),runtime=True,matchup=("DEN","KC"),score_values=(7,7),previous_scores=(7,7),quarter=2,game_seconds=273,play_seconds=4,down=3);import json;Path("reports/b71_s4/second.json").write_text(json.dumps(g));b.close()'` |
| [proof-v4](reports/b71_s4/proof-v4.log) | 2026-09-15T22:01:21.671849+00:00 | 57.818 | 1 | `python3 reports/b71_s4/prove_v4.py` |
| [pins](reports/b71_s4/pins.log) | 2026-09-15T22:01:35.262086+00:00 | 40.246 | 0 | `python3 reports/b71_s4/regenerate_pins.py` |
| [proof-density](reports/b71_s4/proof-density.log) | 2026-09-15T22:03:53.752094+00:00 | 61.787 | 1 | `python3 reports/b71_s4/prove_v4.py` |
| [pins-density](reports/b71_s4/pins-density.log) | 2026-09-15T22:04:59.768687+00:00 | 39.582 | 0 | `python3 reports/b71_s4/regenerate_pins.py` |
| [mnf-contract](reports/b71_s4/mnf-contract.log) | 2026-09-15T22:05:10.323110+00:00 | 11.777 | 1 | `python3 tests/mod_editor/test_nfl2k5_scorebug_mnf.py` |
| [mnf-native](reports/b71_s4/mnf-native.log) | 2026-09-15T22:05:22.127326+00:00 | 36.748 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_mnf_v3.py` |
| [proof-current](reports/b71_s4/proof-current.log) | 2026-09-15T22:06:05.912566+00:00 | 77.424 | 0 | `python3 reports/b71_s4/prove_v4.py` |
| [repin-preflight](reports/b71_s4/repin-preflight.log) | 2026-09-15T22:07:01.797004+00:00 | 19.955 | 0 | `python3 packaging/repin.py --apply` |
| [proof-text-fit](reports/b71_s4/proof-text-fit.log) | 2026-09-15T22:08:32.713562+00:00 | 77.928 | 0 | `python3 reports/b71_s4/prove_v4.py` |
| [pins-final](reports/b71_s4/pins-final.log) | 2026-09-15T22:08:33.864082+00:00 | 39.993 | 0 | `python3 reports/b71_s4/regenerate_pins.py` |
| [manifest](reports/b71_s4/manifest.log) | 2026-09-15T22:09:32.388896+00:00 | 0.448 | 1 | `python3 reports/b71_s4/refresh_manifest.py` |
| [repin-release](reports/b71_s4/repin-release.log) | 2026-09-15T22:09:32.925801+00:00 | 19.945 | 0 | `python3 packaging/repin.py --apply` |
| [test_nfl2k5_scorebug_assets-release](reports/b71_s4/test_nfl2k5_scorebug_assets-release.log) | 2026-09-15T22:09:34.131369+00:00 | 144.48 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_assets.py` |
| [test_apf_scorebug_workspace_qt-release](reports/b71_s4/test_apf_scorebug_workspace_qt-release.log) | 2026-09-15T22:09:34.131540+00:00 | 1.297 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_apf_scorebug_workspace_qt.py` |
| [test_nfl2k5_scorebug_author-release](reports/b71_s4/test_nfl2k5_scorebug_author-release.log) | 2026-09-15T22:09:35.457739+00:00 | 6.359 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_author.py` |
| [test_nfl2k5_scorebug_exact-release](reports/b71_s4/test_nfl2k5_scorebug_exact-release.log) | 2026-09-15T22:09:41.844574+00:00 | 75.64 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_exact.py` |
| [manifest-full](reports/b71_s4/manifest-full.log) | 2026-09-15T22:09:53.425779+00:00 | 11.554 | 1 | `python3 reports/b71_s4/refresh_manifest.py` |
| [xbe-memory](reports/b71_s4/xbe-memory.log) | 2026-09-15T22:09:54.576804+00:00 | 40.661 | 1 | `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` |
| [test_nfl2k5_scorebug_fonts-release](reports/b71_s4/test_nfl2k5_scorebug_fonts-release.log) | 2026-09-15T22:10:57.511927+00:00 | 8.39 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_fonts.py` |
| [test_nfl2k5_scorebug_freeze-release](reports/b71_s4/test_nfl2k5_scorebug_freeze-release.log) | 2026-09-15T22:11:05.928933+00:00 | 235.356 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_freeze.py` |
| [test_nfl2k5_scorebug_freeze_v2-release](reports/b71_s4/test_nfl2k5_scorebug_freeze_v2-release.log) | 2026-09-15T22:11:58.638941+00:00 | 322.774 | 1 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_freeze_v2.py` |
| [pins-compact](reports/b71_s4/pins-compact.log) | 2026-09-15T22:13:13.067189+00:00 | 42.562 | 0 | `python3 reports/b71_s4/regenerate_pins.py` |
| [native-compact](reports/b71_s4/native-compact.log) | 2026-09-15T22:13:14.212751+00:00 | 43.925 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_mnf_v3.py` |
| [owner-compact](reports/b71_s4/owner-compact.log) | 2026-09-15T22:13:58.164892+00:00 | 114.555 | 1 | `python3 tests/mod_editor/test_nfl2k5_scorebug_runtime.py` |
| [repin-compact](reports/b71_s4/repin-compact.log) | 2026-09-15T22:15:01.079453+00:00 | 20.441 | 0 | `python3 packaging/repin.py --apply` |
| [test_nfl2k5_scorebug_ingame-release](reports/b71_s4/test_nfl2k5_scorebug_ingame-release.log) | 2026-09-15T22:15:01.314231+00:00 | 14.68 | 1 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_ingame.py` |
| [manifest-compact](reports/b71_s4/manifest-compact.log) | 2026-09-15T22:15:15.516370+00:00 | 335.752 | 1 | `python3 reports/b71_s4/refresh_manifest.py` |
| [test_nfl2k5_scorebug_ingame_fix-release](reports/b71_s4/test_nfl2k5_scorebug_ingame_fix-release.log) | 2026-09-15T22:15:16.022269+00:00 | 126.134 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_ingame_fix.py` |
| [xbe-memory-compact](reports/b71_s4/xbe-memory-compact.log) | 2026-09-15T22:15:16.689169+00:00 | 1593.524 | 0 | `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` |
| [proof-release](reports/b71_s4/proof-release.log) | 2026-09-15T22:15:17.852508+00:00 | 81.033 | 0 | `python3 reports/b71_s4/prove_v4.py` |
| [test_nfl2k5_scorebug_assets-sealed](reports/b71_s4/test_nfl2k5_scorebug_assets-sealed.log) | 2026-09-15T22:16:21.436034+00:00 | 146.822 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_assets.py` |
| [test_apf_scorebug_workspace_qt-sealed](reports/b71_s4/test_apf_scorebug_workspace_qt-sealed.log) | 2026-09-15T22:16:21.437307+00:00 | 0.648 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_apf_scorebug_workspace_qt.py` |
| [test_nfl2k5_scorebug_author-sealed](reports/b71_s4/test_nfl2k5_scorebug_author-sealed.log) | 2026-09-15T22:16:22.114991+00:00 | 6.56 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_author.py` |
| [provider-check](reports/b71_s4/provider-check.log) | 2026-09-15T22:16:22.530719+00:00 | 8.066 | 1 | `python3 tests/mod_editor/test_provider_integrity.py` |
| [test_nfl2k5_scorebug_exact-sealed](reports/b71_s4/test_nfl2k5_scorebug_exact-sealed.log) | 2026-09-15T22:16:28.705288+00:00 | 77.779 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_exact.py` |
| [contract-compact](reports/b71_s4/contract-compact.log) | 2026-09-15T22:16:30.625992+00:00 | 12.305 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_mnf.py` |
| [test_nfl2k5_scorebug_mnf-release](reports/b71_s4/test_nfl2k5_scorebug_mnf-release.log) | 2026-09-15T22:17:21.440581+00:00 | 12.375 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_mnf.py` |
| [test_nfl2k5_scorebug_mnf_v3-release](reports/b71_s4/test_nfl2k5_scorebug_mnf_v3-release.log) | 2026-09-15T22:17:22.185702+00:00 | 45.355 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_mnf_v3.py` |
| [test_nfl2k5_scorebug_native-release](reports/b71_s4/test_nfl2k5_scorebug_native-release.log) | 2026-09-15T22:17:33.843799+00:00 | 130.321 | 1 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_native.py` |
| [test_nfl2k5_scorebug_fonts-sealed](reports/b71_s4/test_nfl2k5_scorebug_fonts-sealed.log) | 2026-09-15T22:17:46.516145+00:00 | 8.684 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_fonts.py` |
| [test_nfl2k5_scorebug_freeze-sealed](reports/b71_s4/test_nfl2k5_scorebug_freeze-sealed.log) | 2026-09-15T22:17:55.228206+00:00 | 245.016 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_freeze.py` |
| [test_nfl2k5_scorebug_projection-release](reports/b71_s4/test_nfl2k5_scorebug_projection-release.log) | 2026-09-15T22:18:07.569006+00:00 | 56.75 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_projection.py` |
| [provider-closure](reports/b71_s4/provider-closure.log) | 2026-09-15T22:18:35.819342+00:00 | 8.286 | 0 | `python3 tests/mod_editor/test_provider_integrity.py` |
| [phase1-closure](reports/b71_s4/phase1-closure.log) | 2026-09-15T22:18:44.135592+00:00 | 2.089 | 0 | `python3 tests/mod_editor/test_phase1_packaging.py` |
| [test_nfl2k5_scorebug_freeze_v2-sealed](reports/b71_s4/test_nfl2k5_scorebug_freeze_v2-sealed.log) | 2026-09-15T22:18:48.286838+00:00 | 336.001 | 1 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_freeze_v2.py` |
| [test_nfl2k5_scorebug_resources-release](reports/b71_s4/test_nfl2k5_scorebug_resources-release.log) | 2026-09-15T22:19:04.346805+00:00 | 178.911 | 1 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_resources.py` |
| [test_nfl2k5_scorebug_runtime-release](reports/b71_s4/test_nfl2k5_scorebug_runtime-release.log) | 2026-09-15T22:19:44.194282+00:00 | 119.309 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_runtime.py` |
| [proof-uv](reports/b71_s4/proof-uv.log) | 2026-09-15T22:20:05.507952+00:00 | 82.233 | 0 | `python3 reports/b71_s4/prove_v4.py` |
| [pins-uv](reports/b71_s4/pins-uv.log) | 2026-09-15T22:20:06.659697+00:00 | 41.725 | 0 | `python3 reports/b71_s4/regenerate_pins.py` |
| [repin-uv](reports/b71_s4/repin-uv.log) | 2026-09-15T22:20:58.450618+00:00 | 21.547 | 0 | `python3 packaging/repin.py --apply` |
| [test_nfl2k5_scorebug_source_art-release](reports/b71_s4/test_nfl2k5_scorebug_source_art-release.log) | 2026-09-15T22:21:43.531699+00:00 | 0.495 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_source_art.py` |
| [test_nfl2k5_scorebug_template-release](reports/b71_s4/test_nfl2k5_scorebug_template-release.log) | 2026-09-15T22:21:44.055363+00:00 | 9.777 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_template.py` |
| [test_nfl2k5_scorebug_template_release-release](reports/b71_s4/test_nfl2k5_scorebug_template_release-release.log) | 2026-09-15T22:21:53.861894+00:00 | 0.536 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_template_release.py` |
| [test_nfl2k5_scorebug_unified_adapter-release](reports/b71_s4/test_nfl2k5_scorebug_unified_adapter-release.log) | 2026-09-15T22:21:54.428037+00:00 | 0.163 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_unified_adapter.py` |
| [test_nfl2k5_scorebug_v10_ingame-release](reports/b71_s4/test_nfl2k5_scorebug_v10_ingame-release.log) | 2026-09-15T22:21:54.620107+00:00 | 9.023 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_v10_ingame.py` |
| [test_nfl2k5_scorebug_ingame-sealed](reports/b71_s4/test_nfl2k5_scorebug_ingame-sealed.log) | 2026-09-15T22:22:00.274604+00:00 | 15.06 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_ingame.py` |
| [native-final](reports/b71_s4/native-final.log) | 2026-09-15T22:22:02.319794+00:00 | 50.792 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_mnf_v3.py` |
| [test_nfl2k5_scorebug_v10_projection-release](reports/b71_s4/test_nfl2k5_scorebug_v10_projection-release.log) | 2026-09-15T22:22:03.285914+00:00 | 28.69 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_v10_projection.py` |
| [test_nfl2k5_scorebug_versions-release](reports/b71_s4/test_nfl2k5_scorebug_versions-release.log) | 2026-09-15T22:22:03.672540+00:00 | 9.822 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_versions.py` |
| [test_scorebug_studio_panel_qt-release](reports/b71_s4/test_scorebug_studio_panel_qt-release.log) | 2026-09-15T22:22:13.525503+00:00 | 7.365 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_scorebug_studio_panel_qt.py` |
| [test_nfl2k5_scorebug_ingame_fix-sealed](reports/b71_s4/test_nfl2k5_scorebug_ingame_fix-sealed.log) | 2026-09-15T22:22:15.362249+00:00 | 127.525 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_ingame_fix.py` |
| [nfl2k5_scorebug_layout_test-release](reports/b71_s4/nfl2k5_scorebug_layout_test-release.log) | 2026-09-15T22:22:20.921009+00:00 | 1.388 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/nfl2k5_scorebug_layout_test.py` |
| [nfl2k5_scorebug_mod_project_test-release](reports/b71_s4/nfl2k5_scorebug_mod_project_test-release.log) | 2026-09-15T22:22:22.337558+00:00 | 1.329 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/nfl2k5_scorebug_mod_project_test.py` |
| [repin-final](reports/b71_s4/repin-final.log) | 2026-09-15T22:22:22.483444+00:00 | 21.642 | 0 | `python3 packaging/repin.py --apply` |
| [test_provider_integrity-release](reports/b71_s4/test_provider_integrity-release.log) | 2026-09-15T22:22:23.694544+00:00 | 6.159 | 1 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_provider_integrity.py` |
| [test_nfl2k5_scorebug_assets-final](reports/b71_s4/test_nfl2k5_scorebug_assets-final.log) | 2026-09-15T22:22:23.701077+00:00 | 149.481 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_assets.py` |
| [test_apf_scorebug_workspace_qt-final](reports/b71_s4/test_apf_scorebug_workspace_qt-final.log) | 2026-09-15T22:22:23.701856+00:00 | 0.602 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_apf_scorebug_workspace_qt.py` |
| [test_nfl2k5_scorebug_author-final](reports/b71_s4/test_nfl2k5_scorebug_author-final.log) | 2026-09-15T22:22:24.334100+00:00 | 6.493 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_author.py` |
| [test_product_catalog-release](reports/b71_s4/test_product_catalog-release.log) | 2026-09-15T22:22:29.884703+00:00 | 0.177 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_product_catalog.py` |
| [test_phase1_packaging-release](reports/b71_s4/test_phase1_packaging-release.log) | 2026-09-15T22:22:30.091568+00:00 | 2.159 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_phase1_packaging.py` |
| [test_nfl2k5_scorebug_exact-final](reports/b71_s4/test_nfl2k5_scorebug_exact-final.log) | 2026-09-15T22:22:30.855421+00:00 | 78.327 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_exact.py` |
| [registry-strict-release](reports/b71_s4/registry-strict-release.log) | 2026-09-15T22:22:32.280361+00:00 | 0.134 | 1 | `/usr/bin/python3 -m mod_editor.capabilities.validate_registry` |
| [manifest-final](reports/b71_s4/manifest-final.log) | 2026-09-15T22:23:11.423363+00:00 | 339.029 | 0 | `python3 reports/b71_s4/refresh_manifest.py` |
| [xbe-memory-final](reports/b71_s4/xbe-memory-final.log) | 2026-09-15T22:23:12.498575+00:00 | 1732.185 | 0 | `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` |
| [proof-final](reports/b71_s4/proof-final.log) | 2026-09-15T22:23:13.665625+00:00 | 81.882 | 0 | `python3 reports/b71_s4/prove_v4.py` |
| [test_nfl2k5_scorebug_fonts-final](reports/b71_s4/test_nfl2k5_scorebug_fonts-final.log) | 2026-09-15T22:23:49.211808+00:00 | 8.808 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_fonts.py` |
| [test_nfl2k5_scorebug_freeze-final](reports/b71_s4/test_nfl2k5_scorebug_freeze-final.log) | 2026-09-15T22:23:58.048201+00:00 | 244.487 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_freeze.py` |
| [test_nfl2k5_scorebug_mnf-sealed](reports/b71_s4/test_nfl2k5_scorebug_mnf-sealed.log) | 2026-09-15T22:24:22.917066+00:00 | 12.136 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_mnf.py` |
| [test_nfl2k5_scorebug_mnf_v3-sealed](reports/b71_s4/test_nfl2k5_scorebug_mnf_v3-sealed.log) | 2026-09-15T22:24:24.318934+00:00 | 51.172 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_mnf_v3.py` |
| [test_nfl2k5_scorebug_native-sealed](reports/b71_s4/test_nfl2k5_scorebug_native-sealed.log) | 2026-09-15T22:24:35.084326+00:00 | 132.325 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_native.py` |
| [test_nfl2k5_scorebug_freeze_v2-final](reports/b71_s4/test_nfl2k5_scorebug_freeze_v2-final.log) | 2026-09-15T22:24:53.210851+00:00 | 337.908 | 1 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_freeze_v2.py` |
| [test_nfl2k5_scorebug_projection-sealed](reports/b71_s4/test_nfl2k5_scorebug_projection-sealed.log) | 2026-09-15T22:25:15.521873+00:00 | 58.246 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_projection.py` |
| [test_nfl2k5_scorebug_resources-sealed](reports/b71_s4/test_nfl2k5_scorebug_resources-sealed.log) | 2026-09-15T22:26:13.803453+00:00 | 178.9 | 1 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_resources.py` |
| [test_nfl2k5_scorebug_runtime-sealed](reports/b71_s4/test_nfl2k5_scorebug_runtime-sealed.log) | 2026-09-15T22:26:47.440489+00:00 | 118.87 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_runtime.py` |
| [test_nfl2k5_scorebug_ingame-final](reports/b71_s4/test_nfl2k5_scorebug_ingame-final.log) | 2026-09-15T22:28:02.567484+00:00 | 15.108 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_ingame.py` |
| [test_nfl2k5_scorebug_ingame_fix-final](reports/b71_s4/test_nfl2k5_scorebug_ingame_fix-final.log) | 2026-09-15T22:28:17.706788+00:00 | 127.728 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_ingame_fix.py` |
| [test_nfl2k5_scorebug_source_art-sealed](reports/b71_s4/test_nfl2k5_scorebug_source_art-sealed.log) | 2026-09-15T22:28:46.341859+00:00 | 0.527 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_source_art.py` |
| [test_nfl2k5_scorebug_template-sealed](reports/b71_s4/test_nfl2k5_scorebug_template-sealed.log) | 2026-09-15T22:28:46.898263+00:00 | 9.605 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_template.py` |
| [test_nfl2k5_scorebug_template_release-sealed](reports/b71_s4/test_nfl2k5_scorebug_template_release-sealed.log) | 2026-09-15T22:28:56.531710+00:00 | 0.536 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_template_release.py` |
| [test_nfl2k5_scorebug_unified_adapter-sealed](reports/b71_s4/test_nfl2k5_scorebug_unified_adapter-sealed.log) | 2026-09-15T22:28:57.097646+00:00 | 0.164 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_unified_adapter.py` |
| [test_nfl2k5_scorebug_v10_ingame-sealed](reports/b71_s4/test_nfl2k5_scorebug_v10_ingame-sealed.log) | 2026-09-15T22:28:57.289488+00:00 | 8.911 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_v10_ingame.py` |
| [test_nfl2k5_scorebug_v10_projection-sealed](reports/b71_s4/test_nfl2k5_scorebug_v10_projection-sealed.log) | 2026-09-15T22:29:06.229918+00:00 | 28.648 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_v10_projection.py` |
| [test_nfl2k5_scorebug_versions-sealed](reports/b71_s4/test_nfl2k5_scorebug_versions-sealed.log) | 2026-09-15T22:29:12.733493+00:00 | 9.74 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_versions.py` |
| [test_scorebug_studio_panel_qt-sealed](reports/b71_s4/test_scorebug_studio_panel_qt-sealed.log) | 2026-09-15T22:29:22.508015+00:00 | 7.252 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_scorebug_studio_panel_qt.py` |
| [nfl2k5_scorebug_layout_test-sealed](reports/b71_s4/nfl2k5_scorebug_layout_test-sealed.log) | 2026-09-15T22:29:29.790744+00:00 | 1.44 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/nfl2k5_scorebug_layout_test.py` |
| [nfl2k5_scorebug_mod_project_test-sealed](reports/b71_s4/nfl2k5_scorebug_mod_project_test-sealed.log) | 2026-09-15T22:29:31.261400+00:00 | 1.374 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/nfl2k5_scorebug_mod_project_test.py` |
| [test_provider_integrity-sealed](reports/b71_s4/test_provider_integrity-sealed.log) | 2026-09-15T22:29:32.669398+00:00 | 9.018 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_provider_integrity.py` |
| [test_product_catalog-sealed](reports/b71_s4/test_product_catalog-sealed.log) | 2026-09-15T22:29:34.917285+00:00 | 0.157 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_product_catalog.py` |
| [test_phase1_packaging-sealed](reports/b71_s4/test_phase1_packaging-sealed.log) | 2026-09-15T22:29:35.105979+00:00 | 2.156 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_phase1_packaging.py` |
| [registry-strict-sealed](reports/b71_s4/registry-strict-sealed.log) | 2026-09-15T22:29:41.719032+00:00 | 0.138 | 1 | `/usr/bin/python3 -m mod_editor.capabilities.validate_registry` |
| [test_nfl2k5_scorebug_mnf-final](reports/b71_s4/test_nfl2k5_scorebug_mnf-final.log) | 2026-09-15T22:30:25.466041+00:00 | 11.959 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_mnf.py` |
| [xbe-caves-final](reports/b71_s4/xbe-caves-final.log) | 2026-09-15T22:30:28.069742+00:00 | 0.015 | 2 | `python3 tests/mod_editor/test_xbe_patch_caves.py` |
| [test_nfl2k5_scorebug_mnf_v3-final](reports/b71_s4/test_nfl2k5_scorebug_mnf_v3-final.log) | 2026-09-15T22:30:31.149000+00:00 | 50.529 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_mnf_v3.py` |
| [test_nfl2k5_scorebug_native-final](reports/b71_s4/test_nfl2k5_scorebug_native-final.log) | 2026-09-15T22:30:37.453874+00:00 | 131.517 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_native.py` |
| [xbe-cave-references-final](reports/b71_s4/xbe-cave-references-final.log) | 2026-09-15T22:30:38.313768+00:00 | 1958.445 | 0 | `python3 tests/mod_editor/test_xbe_patch_cave_references.py` |
| [registry-strict-hydrated](reports/b71_s4/registry-strict-hydrated.log) | 2026-09-15T22:31:15.222295+00:00 | 0.159 | 0 | `python3 -m mod_editor.capabilities.validate_registry` |
| [test_nfl2k5_scorebug_projection-final](reports/b71_s4/test_nfl2k5_scorebug_projection-final.log) | 2026-09-15T22:31:21.707142+00:00 | 57.253 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_projection.py` |
| [test_apf_scorebug_workspace_qt-delivery](reports/b71_s4/test_apf_scorebug_workspace_qt-delivery.log) | 2026-09-15T22:32:09.564437+00:00 | 0.604 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_apf_scorebug_workspace_qt.py` |
| [test_nfl2k5_scorebug_assets-delivery](reports/b71_s4/test_nfl2k5_scorebug_assets-delivery.log) | 2026-09-15T22:32:09.565251+00:00 | 150.732 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_assets.py` |
| [test_nfl2k5_scorebug_author-delivery](reports/b71_s4/test_nfl2k5_scorebug_author-delivery.log) | 2026-09-15T22:32:10.197840+00:00 | 6.704 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_author.py` |
| [test_nfl2k5_scorebug_exact-delivery](reports/b71_s4/test_nfl2k5_scorebug_exact-delivery.log) | 2026-09-15T22:32:16.934458+00:00 | 78.833 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_exact.py` |
| [test_nfl2k5_scorebug_resources-final](reports/b71_s4/test_nfl2k5_scorebug_resources-final.log) | 2026-09-15T22:32:18.991884+00:00 | 204.176 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_resources.py` |
| [test_nfl2k5_scorebug_runtime-final](reports/b71_s4/test_nfl2k5_scorebug_runtime-final.log) | 2026-09-15T22:32:49.002511+00:00 | 117.777 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_runtime.py` |
| [registry-strict-v4](reports/b71_s4/registry-strict-v4.log) | 2026-09-15T22:32:55.559372+00:00 | 0.155 | 0 | `python3 -m mod_editor.capabilities.validate_registry` |
| [test_nfl2k5_scorebug_fonts-delivery](reports/b71_s4/test_nfl2k5_scorebug_fonts-delivery.log) | 2026-09-15T22:33:35.797172+00:00 | 8.912 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_fonts.py` |
| [test_nfl2k5_scorebug_freeze-delivery](reports/b71_s4/test_nfl2k5_scorebug_freeze-delivery.log) | 2026-09-15T22:33:44.742529+00:00 | 238.596 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_freeze.py` |
| [test_nfl2k5_scorebug_freeze_v2-delivery](reports/b71_s4/test_nfl2k5_scorebug_freeze_v2-delivery.log) | 2026-09-15T22:34:40.329279+00:00 | 333.344 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_freeze_v2.py` |
| [test_nfl2k5_scorebug_source_art-final](reports/b71_s4/test_nfl2k5_scorebug_source_art-final.log) | 2026-09-15T22:34:46.809013+00:00 | 0.472 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_source_art.py` |
| [test_nfl2k5_scorebug_template-final](reports/b71_s4/test_nfl2k5_scorebug_template-final.log) | 2026-09-15T22:34:47.310438+00:00 | 9.623 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_template.py` |
| [test_nfl2k5_scorebug_template_release-final](reports/b71_s4/test_nfl2k5_scorebug_template_release-final.log) | 2026-09-15T22:34:56.964121+00:00 | 0.538 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_template_release.py` |
| [test_nfl2k5_scorebug_unified_adapter-final](reports/b71_s4/test_nfl2k5_scorebug_unified_adapter-final.log) | 2026-09-15T22:34:57.530452+00:00 | 0.163 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_unified_adapter.py` |
| [test_nfl2k5_scorebug_v10_ingame-final](reports/b71_s4/test_nfl2k5_scorebug_v10_ingame-final.log) | 2026-09-15T22:34:57.723019+00:00 | 9.075 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_v10_ingame.py` |
| [test_nfl2k5_scorebug_v10_projection-final](reports/b71_s4/test_nfl2k5_scorebug_v10_projection-final.log) | 2026-09-15T22:35:06.833076+00:00 | 28.641 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_v10_projection.py` |
| [test_nfl2k5_scorebug_versions-final](reports/b71_s4/test_nfl2k5_scorebug_versions-final.log) | 2026-09-15T22:35:35.504659+00:00 | 9.704 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_versions.py` |
| [test_scorebug_studio_panel_qt-final](reports/b71_s4/test_scorebug_studio_panel_qt-final.log) | 2026-09-15T22:35:43.201338+00:00 | 7.464 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_scorebug_studio_panel_qt.py` |
| [nfl2k5_scorebug_layout_test-final](reports/b71_s4/nfl2k5_scorebug_layout_test-final.log) | 2026-09-15T22:35:45.238758+00:00 | 1.398 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/nfl2k5_scorebug_layout_test.py` |
| [nfl2k5_scorebug_mod_project_test-final](reports/b71_s4/nfl2k5_scorebug_mod_project_test-final.log) | 2026-09-15T22:35:46.667041+00:00 | 1.334 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/nfl2k5_scorebug_mod_project_test.py` |
| [test_provider_integrity-final](reports/b71_s4/test_provider_integrity-final.log) | 2026-09-15T22:35:48.030617+00:00 | 8.504 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_provider_integrity.py` |
| [test_product_catalog-final](reports/b71_s4/test_product_catalog-final.log) | 2026-09-15T22:35:50.698794+00:00 | 0.154 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_product_catalog.py` |
| [test_phase1_packaging-final](reports/b71_s4/test_phase1_packaging-final.log) | 2026-09-15T22:35:50.884028+00:00 | 2.131 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_phase1_packaging.py` |
| [registry-strict-final](reports/b71_s4/registry-strict-final.log) | 2026-09-15T22:35:56.567056+00:00 | 0.151 | 0 | `/usr/bin/python3 -m mod_editor.capabilities.validate_registry` |
| [test_nfl2k5_scorebug_ingame-delivery](reports/b71_s4/test_nfl2k5_scorebug_ingame-delivery.log) | 2026-09-15T22:37:43.371656+00:00 | 16.023 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_ingame.py` |
| [repin-contracts](reports/b71_s4/repin-contracts.log) | 2026-09-15T22:37:52.427846+00:00 | 11.891 | 0 | `python3 packaging/repin.py --apply` |
| [test_nfl2k5_scorebug_ingame_fix-delivery](reports/b71_s4/test_nfl2k5_scorebug_ingame_fix-delivery.log) | 2026-09-15T22:37:59.426491+00:00 | 140.809 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_ingame_fix.py` |
| [cave-oracle-final](reports/b71_s4/cave-oracle-final.log) | 2026-09-15T22:39:06.899647+00:00 | 455.759 | 0 | `python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` |
| [owner-pairwise-final](reports/b71_s4/owner-pairwise-final.log) | 2026-09-15T22:39:06.922991+00:00 | 3180.792 | 0 | `python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py` |
| [test_nfl2k5_scorebug_mnf-delivery](reports/b71_s4/test_nfl2k5_scorebug_mnf-delivery.log) | 2026-09-15T22:40:13.709618+00:00 | 12.488 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_mnf.py` |
| [test_nfl2k5_scorebug_mnf_v3-delivery](reports/b71_s4/test_nfl2k5_scorebug_mnf_v3-delivery.log) | 2026-09-15T22:40:20.271219+00:00 | 54.573 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_mnf_v3.py` |
| [test_nfl2k5_scorebug_native-delivery](reports/b71_s4/test_nfl2k5_scorebug_native-delivery.log) | 2026-09-15T22:40:26.240029+00:00 | 152.177 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_native.py` |
| [test_nfl2k5_scorebug_projection-delivery](reports/b71_s4/test_nfl2k5_scorebug_projection-delivery.log) | 2026-09-15T22:41:14.877164+00:00 | 65.083 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_projection.py` |
| [test_nfl2k5_scorebug_resources-delivery](reports/b71_s4/test_nfl2k5_scorebug_resources-delivery.log) | 2026-09-15T22:42:19.993994+00:00 | 307.742 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_resources.py` |
| [test_nfl2k5_scorebug_runtime-delivery](reports/b71_s4/test_nfl2k5_scorebug_runtime-delivery.log) | 2026-09-15T22:42:58.469344+00:00 | 180.567 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_runtime.py` |
| [layout-skip-details](reports/b71_s4/layout-skip-details.log) | 2026-09-15T22:45:21.978257+00:00 | 2.563 | 0 | `env NFL2K5_SCOREBUG_EMULATION_TEST=1 python3 tests/nfl2k5_scorebug_layout_test.py -v` |
| [source-art-skip-details](reports/b71_s4/source-art-skip-details.log) | 2026-09-15T22:45:21.994111+00:00 | 0.997 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_source_art.py -v` |
| [test_nfl2k5_scorebug_source_art-delivery](reports/b71_s4/test_nfl2k5_scorebug_source_art-delivery.log) | 2026-09-15T22:45:59.108114+00:00 | 0.974 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_source_art.py` |
| [test_nfl2k5_scorebug_template-delivery](reports/b71_s4/test_nfl2k5_scorebug_template-delivery.log) | 2026-09-15T22:46:00.146410+00:00 | 12.228 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_template.py` |
| [test_nfl2k5_scorebug_template_release-delivery](reports/b71_s4/test_nfl2k5_scorebug_template_release-delivery.log) | 2026-09-15T22:46:12.413719+00:00 | 0.977 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_template_release.py` |
| [test_nfl2k5_scorebug_unified_adapter-delivery](reports/b71_s4/test_nfl2k5_scorebug_unified_adapter-delivery.log) | 2026-09-15T22:46:13.444696+00:00 | 0.328 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_unified_adapter.py` |
| [test_nfl2k5_scorebug_v10_ingame-delivery](reports/b71_s4/test_nfl2k5_scorebug_v10_ingame-delivery.log) | 2026-09-15T22:46:13.829371+00:00 | 14.083 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_v10_ingame.py` |
| [test_nfl2k5_scorebug_v10_projection-delivery](reports/b71_s4/test_nfl2k5_scorebug_v10_projection-delivery.log) | 2026-09-15T22:46:27.962762+00:00 | 35.786 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_v10_projection.py` |
| [test_nfl2k5_scorebug_versions-delivery](reports/b71_s4/test_nfl2k5_scorebug_versions-delivery.log) | 2026-09-15T22:47:03.790315+00:00 | 12.658 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_nfl2k5_scorebug_versions.py` |
| [test_scorebug_studio_panel_qt-delivery](reports/b71_s4/test_scorebug_studio_panel_qt-delivery.log) | 2026-09-15T22:47:16.480711+00:00 | 7.685 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_scorebug_studio_panel_qt.py` |
| [nfl2k5_scorebug_layout_test-delivery](reports/b71_s4/nfl2k5_scorebug_layout_test-delivery.log) | 2026-09-15T22:47:24.210373+00:00 | 2.296 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/nfl2k5_scorebug_layout_test.py` |
| [nfl2k5_scorebug_mod_project_test-delivery](reports/b71_s4/nfl2k5_scorebug_mod_project_test-delivery.log) | 2026-09-15T22:47:26.556581+00:00 | 1.912 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/nfl2k5_scorebug_mod_project_test.py` |
| [test_provider_integrity-delivery](reports/b71_s4/test_provider_integrity-delivery.log) | 2026-09-15T22:47:27.785956+00:00 | 15.476 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_provider_integrity.py` |
| [test_product_catalog-delivery](reports/b71_s4/test_product_catalog-delivery.log) | 2026-09-15T22:47:28.517901+00:00 | 0.204 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_product_catalog.py` |
| [test_phase1_packaging-delivery](reports/b71_s4/test_phase1_packaging-delivery.log) | 2026-09-15T22:47:28.762747+00:00 | 2.872 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s4/tests/mod_editor/test_phase1_packaging.py` |
| [registry-strict-delivery](reports/b71_s4/registry-strict-delivery.log) | 2026-09-15T22:47:43.331218+00:00 | 0.307 | 0 | `/usr/bin/python3 -m mod_editor.capabilities.validate_registry` |
| [text-rgb-final](reports/b71_s4/text-rgb-final.log) | 2026-09-15T23:04:30.216710+00:00 | 0.354 | 0 | `python3 reports/b71_s4/measure_text_rgb.py` |
| [repin-evidence](reports/b71_s4/repin-evidence.log) | 2026-09-15T23:05:58.619708+00:00 | 11.182 | 0 | `python3 packaging/repin.py --apply` |
| [registry-strict-final-evidence](reports/b71_s4/registry-strict-final-evidence.log) | 2026-09-15T23:19:06.074136+00:00 | 0.158 | 0 | `python3 -m mod_editor.capabilities.validate_registry` |
| [delivery-check](reports/b71_s4/delivery-check.log) | 2026-09-15T23:32:17.856546+00:00 | 0.359 | 0 | `/usr/bin/python3 reports/b71_s4/check_delivery.py` |
| [repin-delivery](reports/b71_s4/repin-delivery.log) | 2026-09-15T23:32:18.245757+00:00 | 10.083 | 0 | `/usr/bin/python3 packaging/repin.py --apply` |

# Beta 66 job G: Coach Edwards' number sheets

Core repair is implemented. The final synthetic matrix replaces all 60 requested jersey and arm digits; the previous encode policy overflowed 22 of those slots. Registration, cleanup, bounded encoding and fallback reasons are shared by preview, Check my images and the build. Encoded preview spans equal independently reopened writes from the real project build dispatch for every tested slot. The protected GUI changes are a complete, offscreen-tested patch in [WIRING.md](WIRING.md#beta-66-job-g-coach-edwards-number-sheets-rc90), not edits to the protected files.

**PROVED offline, UNWITNESSED in game.** Coach's original sheet was not supplied. The screenshot descriptions establish a mixed authored/retail build and motivate the probes; they do not identify every pixel operation that produced his particular halo. No emulator, display, audio, network, disc build or push was used. Retail packs and XBE were opened read-only. Reports contain measurements, hashes and original synthetic artwork, never exported retail textures or mesh vertices.

## Git delivery and integration

Base is `36cfbf605c83b0744412bb2675f6f35d832bde3b`, beta-66 stack, requested branch `astra/b66-digits`. A normal explicit-path commit failed because Git could not create `/home/noah/2k-football-mod-tools/.git/worktrees/astra-b66-digits/index.lock`: **Read-only file system**. The environment forbids permission escalation. No shared metadata was changed.

The commits are therefore preserved on `astra/b66-digits` in **`.astra-git` inside this worktree**, with the same base and worktree. Inspect using `git --git-dir=.astra-git log --oneline`. The first core commit is `9ca4b51a`; the following commit contains the mip-border correction, evidence, regression updates and integration handoff. The ordinary shared worktree ref still points at the base. [commits.bundle](reports/coach_digits/commits.bundle) carries the complete change series against that base. It is generated after the final commit so it includes the report itself, and is intentionally not recursively committed into itself.

Claude can fetch the bundle into the writable integration repository, inspect `FETCH_HEAD`, then cherry-pick `36cfbf605c83b0744412bb2675f6f35d832bde3b..FETCH_HEAD`. Apply `tests/fixtures/coach_digit_wiring.patch` using the WIRING instructions, repin the integrated GUI/facade, regenerate the cave reservation manifest for changed pinned writers, and run the release gates. This job adds no XBE patch sites or gameplay preset. The existing `nfl2k5.uniforms.all_visual` capability owns the repair. The new core module must be added to the protected release allowlist as specified in WIRING.

## Inputs, method and evidence

The report is Coach Edwards to SOFTDRINKTV, September 10, 2026 at 22:53: “It seems to take some numbers and not others” and “the numbers are slightly oversized and/or bleeding.” The seven named images remain in the read-only evidence folder; the analysis uses the supplied descriptions, not invented visual observations.

The extracted pack index is `extracted/ESPN NFL 2K5 (USA)/vc_53450030/0` (193,710,080 bytes). The live-number compatibility report SHA-256 is `d122c1e7de4fbad42c725969dce3473fc16a100e75d68ae5fb5d64077f536cd4`. The pinned retail XBE SHA-256 is `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`. Missing compatibility/catalog metadata was supplied from the local shipped RC62 archive, under ignored `reports/assets`; no retail texture input was copied. Production template and provider hash checks remain enabled.

[coach_digit_cases.py](tests/fixtures/coach_digit_cases.py) constructs original geometric digits, with no external font. Each glyph fills a 64x64 cell, has a roughly 3px light outline, blurred alpha, navy fill, deterministic ±4-channel noise and a slight gradient, encoded as straight-alpha RGBA. This is a reproducible example of the reported kind of art, not a reconstruction of Coach's font. All four sheet layouts contain exactly those cells.

[slot_tables.md](reports/coach_digits/slot_tables.md) gives **every requested per-tier VC-LZ size for all 60 jersey/arm slots**, all 90 measured retail registrations including helmets, and every resulting registration box and scale. [measurements.json](reports/coach_digits/measurements.json) adds palette counts, partial-alpha bands, per-mip border alpha, selected tiers and side-by-side render hashes. [materials.json](reports/coach_digits/materials.json) contains 42 number-submesh sampler/UV measurements. [synthetic_comparison.png](reports/coach_digits/synthetic_comparison.png) shows the old 16-colour decoded synthetic art and new encoded synthetic art at 64/32/16/8px. Actual build/retail pairs were also rendered together entirely in memory, with comparison hashes retained; retail pixels are not saved into the repository.

## Root cause 1: independent compressed allocations produce mixed digits

The old digit ladder was 256, 128, 64, 32, 16. Each digit has a separate fixed compressed allocation. Repeated flat regions and indices compress well; thousands of slightly different shades, soft-alpha values and larger filled areas do not. The physical palette still allocates 256 BGRA8888 entries. Reducing the number of distinct entries affects compressed entropy, not that allocation. A low palette count alone cannot predict whether a texture fits.

The experiment uses actual retail system bytes, index-chain dimensions, pre-palette padding and compression settings. Old-tier columns are **actual unbounded compressor lengths**, compared to `stored_size`. The production bounded compressor appropriately aborts an overflow instead of spending time completing it; it does not report a made-up overflow length.

| Slot | Stored bound | Retail encoded | Retail used colours base/chain | Old 256 / 128 / 64 / 32 / 16 bytes | New bytes |
|---|---:|---:|---:|---|---:|
| 26A0 jersey 0 | 1392 | 1384 | 23 / 79 | 5253 / 3818 / 3171 / 2466 / 1627 | 1335 |
| 26A0 jersey 1 | 976 | 966 | 10 / 52 | 7026 / 4828 / 3422 / 2822 / 1790 | 756 |
| 26A0 jersey 5 | 1568 | 1564 | 23 / 95 | See full table; 16-colour result 1574 | 1548 |
| 26A0 arm 5 | 1584 | 1570 | 23 / 95 | See full table; 16-colour result 1579 | 1553 |
| 26A0 jersey 7 | 1648 | 1645 | 26 / 106 | 3990 / 3120 / 2123 / 1793 / 1243 | 1078 |
| 06H0 arm 1 | 464 | 457 | 13 / 33 | 2561 / 1904 / 1216 / 974 / 712 | 426 |

Retail decoded payloads recompress to their recorded consumed lengths for these measurements. Across all 90 retail samples, the base uses 10–61 distinct colours and the chain 33–202. For example, Seattle 0 fits with 79 chain colours while the noisy authored version fails even with 16. The larger flat margins and coherent retail indices matter more than a palette-count rule alone.

| Set and family | Synthetic digits still overflowing at old 16-colour floor |
|---|---|
| 26A0 jersey | 0, 1, 5, 6, 8, 9 |
| 26A0 arm | 0, 1, 6, 8, 9 |
| 06H0 jersey | 1 |
| 06H0 arm | 0, 1 |
| 26A3 jersey | 0, 1, 6, 8 |
| 26A3 arm | 0, 1, 6, 8 |

That is 22/60 failures. The Seattle jersey example reproduces the reported pattern: 2, 3, 4 and 7 fit, while 0, 1, 5, 6, 8 and 9 remain retail. It also demonstrates why the same 5 can fit the arm allocation and fail the jersey allocation. Coach's 127 and 114 rows were per-slot fallbacks over larger projects, not evidence of 127 invalid PNGs.

`QualityBudgetError` is intentionally caught for digit families in `kept_retail_record`, leaving that one original slot unchanged while building the others. This explains a retail 5 next to an authored 7, or unchanged shoulder digits, without an atlas corruption theory. The fallback remains, but its exact retail texture, badge, reason and import count now agree before the build.

**Correction to the initial premise:** on this beta-66 base, `preview_digit_sheet` already decoded the retail span on `QualityBudgetError`. I did not find a current code path that substitutes the authored preview after that exception. The RC89 screenshot description, including its still-encoding footer, is insufficient to prove the exact earlier UI state. Current weaknesses were the unconditional “Import all ten digits” button, text-only fallback, and missing retail/composite context. Those are addressed explicitly; the report does not claim to have reproduced an unobserved RC89 rendering race.

## Root cause 2: canvas scaling is not glyph registration

`resize_cell` resized the entire cell to the target canvas. It did not fit the nontransparent glyph to the target's original glyph box. A 64x64 edge-filled cell remains edge-filled at 64x64 and becomes a 32x32 edge-filled glyph for a 32x32 slot, with zero margins and baseline at the last canvas row.

Registration is measured with visible alpha >=16 and opaque alpha >=240. Boxes are half-open; baseline means the exclusive bottom of the visible glyph, not an inferred font metric. The report also retains alpha >0 bounds so faint retail noise is observable. Aspect is visible width/height.

| Representative retail digit | Canvas | Visible box | Margins L/T/R/B | Opaque box | Baseline | Aspect |
|---|---|---|---|---|---:|---:|
| 26A0 jersey or arm 5 | 64x64 | [13,1,50,63] | 13/1/14/1 | [13,1,50,63] | 63 | 0.5968 |
| 26A0 jersey 1 | 64x64 | [20,1,44,63] | 20/1/20/1 | [20,1,44,63] | 63 | 0.3871 |
| 06H0 jersey 0 | 64x64 | [17,4,47,61] | 17/4/17/3 | [18,4,46,60] | 61 | 0.5263 |
| 06H0 arm 0 | 32x32 | [9,2,22,29] | 9/2/10/3 | [10,3,21,29] | 29 | 0.4815 |
| 06H0 arm 1 | 32x32 | [10,2,19,29] | 10/2/13/3 | [11,3,18,28] | 29 | 0.3333 |
| 26A0 helmet 0 | 32x32 | [7,1,26,31] | 7/1/6/1 | [7,1,25,31] | 31 | 0.6333 |

Before any model projection, the square source is **64/37 = 1.730 times the width** and 64/62 = 1.032 times the height of Seattle 5. For 06H0 arm 0 it is 32/13 = 2.462 times the width and 32/27 = 1.185 times the height. Merely matching 640x64 input dimensions cannot establish correct rendered size.

The catalog comment actually says **380 of 6,340 arm digits** are 32x32; 200 helmet digits are 64x64. Dimensions remain selected per target, never guessed from the family. All ten digits in each of the three families and sets are tabulated in the linked evidence.

New default math: take the cleaned source's visible bounds, compute `scale = min(retail_box_width/source_width, retail_box_height/source_height)`, floor the scaled dimensions, centre in the measured box, and keep at least one transparent base texel on every side. Record source, retail, chosen and resulting boxes plus scale. Example: the deliberately square Seattle 5 becomes 37x37 at `[13,13,50,50]`, scale 0.578125, inside the retail 37x62 box. It is shorter than retail because the input aspect is square. The importer does not stretch a wide numeral into a tall one. A properly tall font fits the retail height. As authored preserves the expert's base placement and does not take the extra shrink rescue.

### Model/material evidence

The body scenes at outer 3, chunks 113 (`lo_body`, offset `0xd0850`) and 114 (`hi_body`, offset `0xf1af0`) contain real indexed number meshes. The inspector reads their command batches, register-6 NORMSHORT2 UVs and shape constants. The retained model decoder documents the vertex shader's `oT0 = v6 * c[-89].xy + c[-89].zw`, without a V flip.

The digit material binder at VA `0x8e8d0` stores the selected texture pointer at material +0x30 (`0x8e8f0`), sets U scale 4.0 at +0x20 (`0x8e8f3`) and V scale 2.0 at +0x24 (`0x8e8fa`). Selection at `0x8e910` dispatches jersey/helmet/arm families 0xc/0xd/0xe and binds separate digit textures. The draw path at `0x307fc..0x3083a` folds those scales and offsets into the shader constant. The inspector pins the relevant instruction bytes against the XBE hash.

This is **not one universal inset sampling rectangle**:

* `lo_body NUMBER_M`: U −0.119555..1.115593, V −0.035183..1.262708. The adjacent NUMBER_L/R portions differ, and `hi_body` differs slightly. Jersey meshes cover the texture and extend beyond it.
* `lo_body NUMBER_shoulder_A_M`: U −0.176856..1.156523, V −0.066243..1.118691. `NUMBER_sleeve_B_M` extends to U −0.407877..1.255362, V −0.331433..1.558819. Arm-family regions can extend substantially beyond the texture.
* Helmet submeshes in `lo_body` sample a narrower U envelope, 0.158307..0.842881, and nearly the full V envelope, 0.002738..0.996624. This is measured mesh mapping, not a digit-specific correction for an edge-filled font. There are no helmet submeshes in the measured hi_body scene.

Every one of the 42 number materials has address word **0x133 at +0x50**, U=3 and V=3. The emitter at `0x31fa0` reads these nibbles at `0x32043` and `0x32052`, builds the stage address word and emits method `0x1b08` (header `0x00081b08`) at `0x320c7`. That is NV2A clamp-to-edge U/V, not wrap. Blend word +0x74 is **0x03030302**, source SRC_ALPHA (0x302), destination ONE_MINUS_SRC_ALPHA (0x303), with add blend. This supports straight-alpha filtering/compositing in the offline renderer. These are pinned static material/emission facts, not witnessed GPU execution or lighting.

There is no constant “game drawn size” in screen pixels independent of camera, projection and body pose. The 24px 57 composite is explicitly an estimated screen view over the current jersey's dominant opaque base colour, supplied by the facade handoff. Native mip comparisons and 12/24px assumed LOD views complement it. The preview does not claim to reproduce a camera or every mesh boundary.

## Root cause 3: border coverage and transparent RGB can smear or darken outlines

Three independent mechanisms can contribute to Coach's described larger or doubled outline:

1. **Authored opaque border plus clamp addressing.** Out-of-range UVs repeat the edge texel. An edge-filled cell therefore smears outside its intended registration. No neighboring atlas digit is required. The synthetic clamp probe using U −0.12..1.12 and V −0.03..1.26 produces a visible border before registration and clear pixels afterwards.
2. **Area mips refill an originally clear border.** A tall glyph with a one-texel clear base margin has top/bottom border alpha **0, 128, 191, 223** at 64, 32, 16, 8px under ordinary area reduction. The measured Seattle retail 0 has **0, 0, 0, 0**. All 90 sampled retail textures have zero-alpha borders at every stored level. The new digit preparation explicitly preserves a clear border in every smaller level, then extends edge RGB through those transparent texels. The same tall probe now has **0, 0, 0, 0**. This closes the distance-dependent clamp-smear path which base registration alone would miss. The full matrix checks all decoded border texels at every level, not just the base.
3. **Straight-alpha interpolation into transparent black.** Existing digit area filtering was already premultiplied, but alpha-zero mip texels and the old palette policy collapsed hidden RGB to black. A straight-alpha sampler interpolates RGB and alpha separately, so the interpolated RGB darkens before the alpha blend. The controlled single-colour probe at all four mip levels produces maximum straight-RGB channel error **210 before alpha compositing** under the old palette, and **0** after edge-colour extension and preserved transparent palette RGB. The independent registered-glyph test bounds error by **2** through 256/32/16/12/8-entry tiers, allowing rounding. See [halo.json](reports/coach_digits/halo.json), [mip_borders.json](reports/coach_digits/mip_borders.json) and [synthetic_halo.png](reports/coach_digits/synthetic_halo.png).

**Excluded as current root causes:** `_majority_downsample` is retained for nameplates, not the current digit path. Digit `resize_cell` and `make_digit_mips` already use premultiplied resampling. The one shared chain palette is required by the format; its old transparent-black policy contributes to the filter problem, but sharing itself is not corruption. Material sampling is clamp, not texture wrap. The sampled materials use ordinary straight-alpha blending; no evidence established an exotic alpha-blend bug. An AI-generated double outline or already premultiplied source RGB cannot be diagnosed from the screenshot descriptions. Those exact source-art causes remain HYPOTHESIS, and the preview warns that intentionally dark RGB cannot be automatically distinguished from a premultiplied PNG mistake.

## Implementation and outcomes

`nfl2k5_digit_art.py` owns one preparation and fit policy. It binds alpha below 16 to zero and at/above 240 to 255, merges nearby RGB shades (maximum 12-channel cleanup distance), recognises two-tone regions plus their resample blends, limits the base soft edge to one texel, resizes in premultiplied float colour, and floods nearest edge RGB into transparent pixels. Every smaller mip keeps a clear border. Quantisation preserves transparent RGB alternatives, opaque anchors and alpha classes in one shared BGRA8888 palette.

The existing ladder remains the first choice. Clean one/two-tone art can try **12 and 8** entries after 16, provided both visible regions survive the actually used base indices. Complex art never takes that exception. Match retail size may then try an additional **0.94 or 0.88** scale, recorded explicitly. As authored never takes this shrink. Outline erosion was deliberately rejected: it can change the font and erase the only contrast. Two-tone input cannot be accepted as a one-colour blob. Exhaustion keeps the retail span and supplies the same reason everywhere:

> kept retail: the authored digit could not fit its N-byte texture slot after cleanup and the recognisable-art fit ladder. Simplify the fill and outline, then preview again.

The main 60-slot study needs no last-resort shrinking or sub-16 tier: **55 fit at the initial 256-entry limit, five at 64**, using 27–147 actual palette entries. Separate synthetic boundary tests genuinely select tier 12 at a 1287-byte bound, tier 8 at 1264 bytes, and a modest registration reduction at 1200 bytes. Those are synthetic compressed allocations, not invented retail slots.

`nfl_live_numbers_nameplate_png_import.build_import` and preflight both call that policy using the actual validated retail template. Preflight has a separate kept-retail outcome; it no longer claims that a digit-budget fallback stops the build. Without the loaded retail registration/template it reports unmodelled rather than predicting a fit against zero-filled stand-ins. Successful predictions use the writer's exact outcome words and decoded hash.

The preview calls the actual writer, then decodes what it returned. Every row includes its retail comparison; kept-retail rows use the original retail texture and an amber badge. Receipts include the chosen box, source scale, any extra scale, cleanup and fit attempts. The button property returns, for example, `Import 7 digits, 3 kept retail`. A forced three-slot exhaustion test verifies the displayed texture hash, exact reason, fallback count and project receipt against the original retail spans. Non-budget failures still stop the sheet before staging.

The normal Team Kit transaction remains atomic with one Undo action. Registration mode travels in the PNG text key `nfl2k5_digit_registration`; absent metadata defaults to retail registration. A resave that strips it returns to the default and needs another preview. Session/source locking and frozen PNG snapshots keep the accepted art stable while the user reviews it. The project compiler remains the source of the real write path; tests reopen written windows independently and compare their SHA-256 to preview receipts, preserving guards before and after the fixed span.

The protected patch adds the third registration chooser, count caption, explanatory note, Uniforms help, facade jersey-colour lookup, release allowlist and runtime import smoke check. It is applied and executed **in memory** by the new offscreen wiring test. Getting Started, the number-sheet guide and RC90 changelog were edited directly. `build_feedback.py` already transports each receipt message into the completion dialog, so it needed no duplicate policy or protected build-panel edits.

## Validation and remaining witness

The new synthetic tests use original art only. Retail-dependent tests read registration/templates and skip with a specific path when unavailable. The all-60 matrix ran here, through preview, actual `build_one_import`, actual `write_all`, reopen/decode and preflight. It does not require copying an ISO. A ten-digit Seattle jersey preview took 4.421 seconds in this environment; see [timing.json](reports/coach_digits/timing.json). UI work remains on its existing asynchronous task path.

The older full-ISO classes could not run because `reports/assets/nfl2k5_resource_chunks_v2.json` and the old tests' root-level XISO path are absent. The Titans fixture-specific case and two full-XISO bounded-palette cases also skip. This is not a claim that those full-disc tests passed. Their standalone suites pass the available cases, with exact skips in the logs. Legacy tests which deliberately relied on resave noise remaining unfit now inject budget exhaustion to test fallback independently of a bug that cleanup fixed. Their full-disc branch is still unwitnessed here.

Initial exploratory GUI-suite runs failed during setup for missing metadata reports (`nfl2k5_create_team_field_art_inventory.json`, then `scorebug_presentation_audit.json`). Supplying the archived metadata made both suites pass; no production validation was relaxed. Pin tests also correctly rejected intermediate edited hashes before repinning. `packaging/repin.py --apply` is run after pinned edits and immediately before each commit. The final test transcripts are retained below and in `reports/coach_digits/tests`.

Noah or Coach must still build with the integrated UI and play the result. Check back 57, front and shoulder 58, shoulder 38, all ten digits in each chosen family, and close/broadcast distances on white, navy and neon jerseys. Verify both regions, correct baseline/spacing, and the absence of outline smear as LOD changes. The measured UV/sampler facts and byte equality are PROVED; final lit, animated, camera-projected appearance is UNWITNESSED.

## What to tell Coach Edwards

Your report exposed two separate size problems and a misleading import summary. Each number has its own small compressed slot, so noisy art could replace some digits while leaving others original. Filling the whole cell also made the numbers larger, and the small texture levels could spread colour beyond their clear border. The new importer cleans up small colour variations, fits each number inside its original box and keeps the smaller levels clear at the edges. The preview shows the actual build result beside the original and counts any numbers that must stay retail. Use a transparent sheet with one fill colour, one outline colour and a margin. We have verified the encoded results offline, but still need you or Noah to check them in play.

## FAQ for release notes

**Why did some numbers stay old, look too large, or bleed?** Each digit has a different compressed limit. Noisy or oversized art could fit one slot and fail the next, leaving mixed original and custom numbers. A glyph touching the cell edge could also smear when the game filtered it. The importer now cleans the art, fits it to the original number box and keeps clear borders in the smaller textures. The preview shows any remaining original digits clearly. Start with a transparent sheet, one flat fill and one outline colour, and leave a margin. AI output needs this cleanup too.

## Exact research commands and outputs

```text
PYTHONPATH=. python3 tools/inspect_coach_digit_slots.py --output reports/coach_digits/measurements.json
```

The tool emits one authored/encoded-byte line per slot, followed by the summary stored in `measurements.json`; every emitted byte count is in the complete slot table. It additionally renders every encoded/retail pair at 64/32/16/8 pixels, retaining hashes and synthetic-only PNGs.

```text
PYTHONPATH=. python3 tools/inspect_coach_digit_materials.py --output reports/coach_digits/materials.json
Pinned retail XBE. Measured 42 number submeshes in lo_body and hi_body; all U/V address nibbles are 3.

PYTHONPATH=. python3 tools/inspect_coach_digit_halo.py --output reports/coach_digits
Old maximum RGB channel delta: 210
New maximum RGB channel delta: 0
Tall glyph mip borders: {'ordinary_area_border_alpha': [0, 128, 191, 223], 'retail_margin_border_alpha': [0, 0, 0, 0]}

git apply --check tests/fixtures/coach_digit_wiring.patch
(exit 0, no output; protected files unchanged)
```

## Exact standalone test commands and final outputs

All 16 standalone suites exited 0, reporting 155 tests. The five skip reports include two class-level skips; exact reasons are below. Each command is a separate Python process. The full `-v` transcripts, including all test names, are in [tests/results.json](reports/coach_digits/tests/results.json) and individual `.log` files in that folder.

```text
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_2k5_bounded_vclz_palette.py -v
----------------------------------------------------------------------
Ran 7 tests in 3.064s

OK (skipped=2)
```

```text
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_2k5_check_my_images.py -v
----------------------------------------------------------------------
Ran 21 tests in 9.943s

OK
```

```text
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_2k5_digit_dimensions_per_target.py -v
----------------------------------------------------------------------
Ran 10 tests in 1.498s

OK (skipped=1)
```

```text
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_2k5_vclz_bounded_importers.py -v
----------------------------------------------------------------------
Ran 16 tests in 0.435s

OK
```

```text
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_b66_coach_digits.py -v
----------------------------------------------------------------------
Ran 14 tests in 52.425s

OK
```

```text
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_b66_coach_wiring.py -v
----------------------------------------------------------------------
Ran 5 tests in 1.082s

OK
```

```text
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_beta66_d1_images.py -v
----------------------------------------------------------------------
Ran 6 tests in 1.252s

OK
```

```text
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_hotfix63_digit_budget.py -v
----------------------------------------------------------------------
Ran 10 tests in 13.801s

OK (skipped=1)
```

```text
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_digit_sheet.py -v
----------------------------------------------------------------------
Ran 3 tests in 0.371s

OK
```

```text
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_digit_sheet_quality.py -v
----------------------------------------------------------------------
Ran 13 tests in 7.054s

OK (skipped=1)
```

```text
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_import_preflight.py -v
----------------------------------------------------------------------
Ran 17 tests in 15.401s

OK
```

```text
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_uniform_catalog.py -v
----------------------------------------------------------------------
Ran 5 tests in 0.240s

OK
```

```text
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_number_sheet_quality_wiring.py -v
----------------------------------------------------------------------
Ran 6 tests in 0.815s

OK
```

```text
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_team_kit_bundle.py -v
----------------------------------------------------------------------
Ran 7 tests in 1.676s

OK
```

```text
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_team_kit_product_integration.py -v
----------------------------------------------------------------------
Ran 7 tests in 10.005s

OK
```

```text
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_uniform_bundle_cross_project.py -v
----------------------------------------------------------------------
Ran 8 tests in 2.054s

OK
```

Actual skip messages from the final run:

```text
test_2k5_digit_dimensions_per_target: The actual 33 Titans PNGs satisfy the editor's import contract. ... skipped 'private extracted NFL 2K5 fixture is absent'
test_nfl2k5_digit_sheet_quality: setUpClass (__main__.RetailDigitQualityTests) ... skipped 'Private retail digit evidence absent: /home/noah/2k-worktrees/astra-b66-digits/reports/assets/nfl2k5_resource_chunks_v2.json, /home/noah/2k-worktrees/astra-b66-digits/ESPN NFL 2K5 (USA).xiso.iso'
test_hotfix63_digit_budget: setUpClass (__main__.BackendKeepsRetailTests) ... skipped 'Private retail digit evidence absent: /home/noah/2k-worktrees/astra-b66-digits/reports/assets/nfl2k5_resource_chunks_v2.json'
test_2k5_bounded_vclz_palette: test_high_colour_art_fits_quality_floor_and_reopens_from_composed_xiso_window (__main__.Real1568ByteComposedBuildTests.test_high_colour_art_fits_quality_floor_and_reopens_from_composed_xiso_window) ... skipped 'private retail XISO/index inputs are unavailable'
test_2k5_bounded_vclz_palette: test_original_random_rgba_fixture_refuses_excessive_colour_loss (__main__.Real1568ByteComposedBuildTests.test_original_random_rgba_fixture_refuses_excessive_colour_loss) ... skipped 'private retail XISO/index inputs are unavailable'
```

Final slot-study summary:

```json
{"slots": 90, "synthetic_slots": 60, "old_overflow": 22, "new_kept_retail": 0, "seconds": 123.944}
```

# Beta 71 S6: sprite scorebug pass 2

S6 corrects the residual logo fringe, possession plate, round ends, rim and wing
finish in the PNG/JSON sprite design and shared texture compiler. The append
remains **323,808 bytes**, exactly S5's total: 34 TXTRs and one enlarged SCNE,
with **zero FONT resources**. The separate light notch brings the quad count to
46 and fits inside existing scene padding. The native owner instructions,
allocator layout and complete stack XBE are byte-identical to S5.

The private branch is `astra/b71-s6-sprite-pass2`, based on S5
`0520e2e1df15818fe86494a13b7c55966d2a039c`. Private Git metadata is in
`.scratch/b71-s6-git`; the shared worktree Git metadata was read only. Delivery
is `.scratch/astra-b71-s6.bundle`. Explicit-path commits and independent bundle
fetch verification are recorded in `.scratch/b71-s6-delivery.json`.

**PROVED:** decoded textures, native loading/owner execution, field coverage,
software raster measurements, freeze-class resource volume and integration
checks. **UNWITNESSED:** console GPU sampling, played intro, live gameplay and
full display appearance. No disc build, xemu session or push was performed.

## Design and cause

1. **Logo edges.** `nfl2k5_scorebug_exact.mnf_panel` previously composited onto
   transparent black, leaving all 1,907 DEN and 1,431 KC zero-alpha panel texels
   with black RGB. The source PNGs themselves have 2,724 and 2,206 black
   transparent pixels. The old RGBA median cut also changed 377 DEN and 393 KC
   opaque texels into partial coverage. It did not make zero-alpha texels
   nonzero; the before diagnostic records zero such changes. Pillow's RGBA
   resize already premultiplies, so black contamination was not proved to arise
   solely in that resize. It survived canvas placement and palette conversion
   into the straight-RGBA bilinear sampling path; faint resampling tails made
   its dashed outline visible.

   `nfl2k5_scorebug_assets.alpha_bleed` extends visible RGB six texels into
   transparent space before resizing and again after placement; `resample_logo`
   explicitly filters RGBa, removes faint ringing and bounds fractional coverage
   to the one-texel silhouette boundary. The atlas packer bleeds each cell too.
   `quantize_alpha_aware` separates transparent, opaque, white-mask and coloured
   feather entries, measures feather colour in premultiplied RGBA, and never
   dithers. It keeps low-alpha white ramps continuous. Both logos now have zero
   changed alpha endpoints and zero feather texels outside that boundary band.
   All palette slots were already resident, so using up to 256 instead of 128
   colours adds no bytes. Historical non-MNF texture authors retain their
   original quantizer. Shared MNF pins were regenerated from the current builder.

2. **Plate and pointer.** `template.png` has a neutral luminance gradient with
   soft inner edge shading and a darker lower lip. The source plate is
   [837,947,1083,983]. JSON's optional `plate_tints` supplies KC's broadcast
   crimson tint; other teams retain their existing primary/secondary choices.
   The [951,942,965,947] pointer is a separate light, untinted, downward notch.
   The measured top and bottom strips below exclude white label ink.

3. **Capsule and play-clock cell.** The left capsule and right red cell are
   filtered to their HUD footprint in the PNG, preserving curved edge coverage
   during bilinear sampling. Their boxes stay [839,999,1019,1039] and
   [1019,999,1082,1040]. Both decoded end masks are vertically symmetric, have
   transparent corners, full centre coverage and a feather. The red fill is
   (215,0,51). The digit's [1042,1009,1057,1028] ink target and anchor 1049.5
   stay fixed. Comparing the isolated native digit to the full bar loses **zero
   coverage** at both aspects: no other material clips it. Its native centre
   error is below 0.003 HUD px. No owner draw-order patch was needed.

4. **Body and wings.** The body keeps the r=8 silhouette, gains a stronger
   two-source-pixel top rim over the soft highlight, reaches charcoal near
   (37,37,37) in the middle and retains its dark two-pixel bottom rim. Wing
   masks fade by (1-x)^1.5; their top alpha admits the rim and their bottom alpha
   admits the dark border. Both decoded P8 column profiles are monotonic from
   the outer team colour to body colour, with no inner seam. Additional columns from the actual native raster, with
   logos/text hidden only for that diagnostic, have zero channel reversals at
   both aspects. Black-background
   crops isolate the new rounded corners from the screenshot's existing rails.

5. **Widescreen and states.** The native 27/32 x contraction is retained and
   undone for display-restored comparisons. Logo, round-end and corner quads
   have the same restored dimensions at both aspects within
   0.000000 source pixels.
   Every S5 state was rerendered: DEN/KC, NO/DEN, scores 0/7/28/100, 0:07,
   play clocks 3/4/12, all downs, OT, Inches, Goal, timeouts 0..3, FLAG, FUMBLE,
   hang time, ball on, score slabs and hidden play clock. The ordinary bar uses
   no FONT draws. Event callbacks and their inherited formatting remain; FUMBLE
   hides the play-clock digit and the score slabs leave sprite scores attached
   to the root. These are native state fixtures, not played-game captures.

## Measured comparison

| Region | ESPN RGB | S5 RGB | S6 RGB |
| --- | --- | --- | --- |
| plate_top | [187.48, 14.94, 63.3] | [232.5, 23.25, 55.25] | [180.0, 10.0, 59.25] |
| plate_bottom | [165.82, 8.51, 54.2] | [228.0, 24.0, 55.33] | [162.42, 10.62, 54.33] |
| body_top_rim | [32.0, 38.2, 32.2] | [55.5, 60.4, 54.85] | [63.75, 69.0, 65.35] |
| body_highlight | [46.8, 59.52, 91.84] | [49.66, 49.8, 49.8] | [52.84, 52.92, 53.2] |
| body_middle | [37.0, 37.0, 37.0] | [34.3, 34.3, 34.3] | [37.3, 37.3, 37.3] |
| body_bottom_rim | [47.55, 46.05, 56.25] | [11.0, 12.35, 16.75] | [11.55, 13.3, 17.6] |
| red_cell | [214.73, 0.0, 53.24] | [214.81, 1.42, 52.14] | [214.81, 1.42, 52.14] |

The exact sample rectangles and the separate 16:9 measurements are in
`finish-proof.json`. Frame/JPEG rim samples include the photograph's rail
placement and tinted reflection; they are not substituted for the requested
neutral design colours. The sprite render remains softer than the broadcast
photograph at the native 640x480 HUD sampling limit. The legacy RGB comparator
continues to report a mismatch; no pixel-identical claim is made.

| Logo | Mean dark RGB sampling error, S5 | S6 | S5 95th percentile | S6 |
| --- | ---: | ---: | ---: | ---: |
| DEN | 1.819 | 1.462 | 7.107 | 6.173 |
| KC | 5.551 | 0.378 | 24.894 | 2.250 |

This samples decoded P8 with straight versus premultiplied bilinear filtering
at identical fractional positions; it isolates dark sampling error, not a
photographic similarity score. The extra hidden-RGB ablation preserves every
alpha byte while replacing zero-alpha RGB, separately demonstrating that cause.
The source marks remain 64x64; this pass does not invent higher-resolution detail.

Standard static boundaries: **0.006285 HUD px** maximum error. Dynamic
boundaries: **0.166789 HUD px**. Visible glyph ink: **0.829630 HUD px**.
All visible fields across 50 captures remain within their boxes with maximum
containment error **0.006836 HUD px**.
Setup/update recorded 166 / 2283
writes and zero writes outside the allowlist. Native tests preserve GPRs, flags,
x87, MXCSR and XMM state, call displaced routines once, reparse all resources,
retain retail HUD bytes and refuse foreign code/data/resources. The custom
PNG/JSON design proof still changes position, size and colour with identical
owner instructions.

## Review artifacts

- [ESPN / S5 / S6 at 4:3, 2x](reports/b71_s6/espn_s5_s6_43_2x.png)
- [ESPN / S5 / S6 at 16:9, 2x](reports/b71_s6/espn_s5_s6_169_2x.png)
- [All 50 state/aspect crops](reports/b71_s6/states_contact_sheet.png)
- [DEN edges at 4x](reports/b71_s6/DEN_edge_compare_43_4x.png) and [16:9](reports/b71_s6/DEN_edge_compare_169_4x.png)
- [KC edges at 4x](reports/b71_s6/KC_edge_compare_43_4x.png) and [16:9](reports/b71_s6/KC_edge_compare_169_4x.png)
- [Decoded wing column profiles](reports/b71_s6/wing_column_profiles.png)
- [Clean background, 4:3](reports/b71_s6/clean_background_43_2x.png) and [16:9](reports/b71_s6/clean_background_169_2x.png)
- [Day background, 4:3](reports/b71_s6/day_43.png) and [16:9](reports/b71_s6/day_169.png)
- [Decoded P8 atlas](reports/b71_s6/atlas.png), [finish measurements](reports/b71_s6/finish-proof.json), [native geometry/ink](reports/b71_s6/measurements.json)

The ESPN/S5 comparison and both disc-i shine screenshots requested in the brief
were opened and reviewed. Screenshots used as preview backgrounds are preserved;
any uncovered pixels of an earlier bar remain visible. The separate black
background proof avoids that confound when reviewing the new rims and corners.

## Resource and integration proof

| Component | Count | Bytes each | Total |
| --- | ---: | ---: | ---: |
| Team logo TXTR | 32 | 5,280 | 168,960 |
| Neutral logo TXTR | 1 | 2,208 | 2,208 |
| P8 atlas TXTR, 256x512 | 1 | 132,256 | 132,256 |
| Scene with layout | 1 | 20,384 | 20,384 |
| FONT | 0 | 0 | 0 |
| **Append** | **35** | | **323,808** |

Native heap-rounded sum: 327,168 bytes. Sector pack growth: 323,584 bytes.
The hard sprite limit is 400,000 bytes; the oversized profile refusal is tested.
This is a freeze-class volume proof, not a witnessed intro peak-memory trace.

Provider pins and legacy compiler pins are regenerated. Provider integrity,
product catalog, phase1 packaging and strict registry validation run without
skipping file checks. The 75 inherited private evidence inputs were verified as
independent copies against their inventory (2,063,157 bytes); they are not in
commits or the bundle. The existing runtime registry row includes S6 evidence;
no capability rows were added. The RC96 bullet and design documentation describe
the finish and retain experimental, off-by-default and UNWITNESSED status.

The brief's registry, packaging-pin and cave-projection requirements include
direct edits to protected `mod_editor/capabilities/registry.v1.json`,
`packaging/check_2k5_mod_studio_release.py` (the template-catalog digest only),
and `data/nfl2k5_cave_reservations.json`. Those edits are complete; no deferred
wiring is needed.

The cave projection observes the complete current writer stack. It seals
339 current source files, preserves every S5 allocation,
and produces the same stack XBE SHA-256:
`472862f4eac5420137f97529fe3c27b5f000f0ab6a005bd1d8a14d46c753bd60`.
Both XBE gates, cave oracle and owner-pair matrix were run detached against the
final seals even though owner instructions did not change. Duplicate historical projection payloads were compacted below the 8 MiB
reader bound; the complete top-level write ledger, reservations, source seals
and XBE identity were proved unchanged. The projection is
explicitly not a release-disc receipt; inherited disc fields remain historical
and production regeneration is required when a disc is built.

`reports/b71_s6/build_testdisc71.py` is prepared with disc m's
`softdrink_advanced` plan and the five enabled options: scorebug,
scorebug_runtime, modern_color, modern_arrowhead and widescreen. Its name is
**NFL 2K5 MOD TEST 2026-09-16n (sprite scorebug pass 2 + everything)**.
`verify_builder.py` imports and checks the immutable plan without calling the
builder. The builds directory is untouched. No disc or patch export was run.

## Completed checks

All **40 required suites** have passing latest results:
**1162 tests, 16 explicit skips**. Missing: none.
The skips retain their exact reasons in the suite logs; they cover historical
retired mechanisms, unavailable private developer inputs and read-only storage
for a full-disc transaction. Native sprite loading, owner, raster and geometry
checks are not skipped. Gameplay, intro and GPU appearance still require a
played witness at both aspects, including possessions, timeouts and all events.

| Check | Tests | Skips | Seconds | Exit |
| --- | ---: | ---: | ---: | ---: |
| [test_apf_scorebug_workspace_qt](reports/b71_s6/final-test_apf_scorebug_workspace_qt.log) | 11 | 0 | 1.463 | 0 |
| [test_build_panel_qt](reports/b71_s6/final-test_build_panel_qt.log) | 13 | 0 | 3.354 | 0 |
| [test_mod_build](reports/b71_s6/final-test_mod_build.log) | 13 | 0 | 2.13 | 0 |
| [test_nfl2k5_allocator_scaleout](reports/b71_s6/final-test_nfl2k5_allocator_scaleout.log) | 23 | 0 | 821.091 | 0 |
| [test_nfl2k5_cave_oracle](reports/b71_s6/gate-test_nfl2k5_cave_oracle.log) | 29 | 0 | 355.728 | 0 |
| [test_nfl2k5_owner_pairwise_composition](reports/b71_s6/gate-test_nfl2k5_owner_pairwise_composition.log) | 506 | 0 | 2872.036 | 0 |
| [test_nfl2k5_scorebar_rim](reports/b71_s6/final-test_nfl2k5_scorebar_rim.log) | 8 | 0 | 14.159 | 0 |
| [test_nfl2k5_scorebar_v3](reports/b71_s6/final-test_nfl2k5_scorebar_v3.log) | 9 | 0 | 100.715 | 0 |
| [test_nfl2k5_scorebug_assets](reports/b71_s6/final-test_nfl2k5_scorebug_assets.log) | 8 | 1 | 148.199 | 0 |
| [test_nfl2k5_scorebug_author](reports/b71_s6/final-test_nfl2k5_scorebug_author.log) | 12 | 0 | 6.3 | 0 |
| [test_nfl2k5_scorebug_exact](reports/b71_s6/sealed-test_nfl2k5_scorebug_exact.log) | 8 | 0 | 86.154 | 0 |
| [test_nfl2k5_scorebug_fonts](reports/b71_s6/final-test_nfl2k5_scorebug_fonts.log) | 10 | 5 | 8.884 | 0 |
| [test_nfl2k5_scorebug_freeze](reports/b71_s6/final-test_nfl2k5_scorebug_freeze.log) | 7 | 0 | 242.333 | 0 |
| [test_nfl2k5_scorebug_freeze_v2](reports/b71_s6/sealed-test_nfl2k5_scorebug_freeze_v2.log) | 7 | 0 | 330.688 | 0 |
| [test_nfl2k5_scorebug_ingame](reports/b71_s6/final-test_nfl2k5_scorebug_ingame.log) | 11 | 0 | 14.66 | 0 |
| [test_nfl2k5_scorebug_ingame_fix](reports/b71_s6/final-test_nfl2k5_scorebug_ingame_fix.log) | 9 | 0 | 126.344 | 0 |
| [test_nfl2k5_scorebug_mnf](reports/b71_s6/final-test_nfl2k5_scorebug_mnf.log) | 10 | 0 | 11.974 | 0 |
| [test_nfl2k5_scorebug_mnf_v3](reports/b71_s6/final-test_nfl2k5_scorebug_mnf_v3.log) | 7 | 0 | 49.02 | 0 |
| [test_nfl2k5_scorebug_native](reports/b71_s6/final-test_nfl2k5_scorebug_native.log) | 4 | 0 | 131.24 | 0 |
| [test_nfl2k5_scorebug_projection](reports/b71_s6/final-test_nfl2k5_scorebug_projection.log) | 14 | 0 | 58.007 | 0 |
| [test_nfl2k5_scorebug_resources](reports/b71_s6/sealed-test_nfl2k5_scorebug_resources.log) | 6 | 0 | 288.703 | 0 |
| [test_nfl2k5_scorebug_runtime](reports/b71_s6/final-test_nfl2k5_scorebug_runtime.log) | 12 | 0 | 119.768 | 0 |
| [test_nfl2k5_scorebug_source_art](reports/b71_s6/final-test_nfl2k5_scorebug_source_art.log) | 13 | 3 | 0.472 | 0 |
| [test_nfl2k5_scorebug_sprite](reports/b71_s6/sealed-test_nfl2k5_scorebug_sprite.log) | 13 | 0 | 78.494 | 0 |
| [test_nfl2k5_scorebug_template](reports/b71_s6/final-test_nfl2k5_scorebug_template.log) | 19 | 0 | 9.932 | 0 |
| [test_nfl2k5_scorebug_template_release](reports/b71_s6/sealed-test_nfl2k5_scorebug_template_release.log) | 5 | 0 | 0.55 | 0 |
| [test_nfl2k5_scorebug_unified_adapter](reports/b71_s6/final-test_nfl2k5_scorebug_unified_adapter.log) | 5 | 0 | 0.165 | 0 |
| [test_nfl2k5_scorebug_v10_ingame](reports/b71_s6/final-test_nfl2k5_scorebug_v10_ingame.log) | 11 | 0 | 9.028 | 0 |
| [test_nfl2k5_scorebug_v10_projection](reports/b71_s6/final-test_nfl2k5_scorebug_v10_projection.log) | 14 | 0 | 28.835 | 0 |
| [test_nfl2k5_scorebug_versions](reports/b71_s6/final-test_nfl2k5_scorebug_versions.log) | 4 | 0 | 9.846 | 0 |
| [test_nfl2k5_xbe_space](reports/b71_s6/final-test_nfl2k5_xbe_space.log) | 13 | 1 | 34.063 | 0 |
| [test_phase1_packaging](reports/b71_s6/sealed-test_phase1_packaging.log) | 23 | 0 | 2.111 | 0 |
| [test_product_catalog](reports/b71_s6/sealed-test_product_catalog.log) | 9 | 0 | 0.154 | 0 |
| [test_provider_integrity](reports/b71_s6/sealed-test_provider_integrity.log) | 8 | 0 | 9.98 | 0 |
| [test_scorebug_sprite_preview_qt](reports/b71_s6/sealed-test_scorebug_sprite_preview_qt.log) | 2 | 0 | 10.038 | 0 |
| [test_scorebug_studio_panel_qt](reports/b71_s6/final-test_scorebug_studio_panel_qt.log) | 11 | 0 | 7.388 | 0 |
| [test_xbe_patch_cave_references](reports/b71_s6/gate-test_xbe_patch_cave_references.log) | 131 | 0 | 1735.277 | 0 |
| [test_xbe_patch_memory_writes](reports/b71_s6/gate-test_xbe_patch_memory_writes.log) | 119 | 0 | 1548.162 | 0 |
| [nfl2k5_scorebug_layout_test](reports/b71_s6/final-nfl2k5_scorebug_layout_test.log) | 15 | 6 | 1.429 | 0 |
| [nfl2k5_scorebug_mod_project_test](reports/b71_s6/final-nfl2k5_scorebug_mod_project_test.log) | 10 | 0 | 1.319 | 0 |

## Exact detached command ledger

`run_logged.py` starts each command in a new process session, captures its log
and waits in a supervisor. The tool yields while it runs, so progress remains
visible. An initial orphan-only launch did not survive the sandbox's process
namespace lifetime; it produced no proof and was replaced with this supervised
detached pattern. No process-name kill was used. Times below are UTC. Source
reads and short authoring edits were not benchmark runs; final Git commands and
bundle verification are in the private delivery receipt.

Failed and superseded attempts remain visible: an initial import-path fix, one
one-level RGB rounding expectation, the initial sampling-error threshold,
stale shared-MNF pins, and projections that correctly refused source edits
during observation. The final checks use regenerated pins and current source
seals. Native/XBE tests and strict registry file checks remain enabled.

| Log | Started UTC | Seconds | Exit | Exact argv |
| --- | --- | ---: | ---: | --- |
| [before](reports/b71_s6/before.log) | 2026-09-16T06:06:36.790066+00:00 | 7.58 | 0 | `python3 reports/b71_s6/inspect_before.py` |
| [preview-first](reports/b71_s6/preview-first.log) | 2026-09-16T06:10:03.825102+00:00 | 25.991 | 0 | `python3 -c 'import sys; sys.path.insert(0,"reports/b71_s6"); import prove_previews as p; p.STATES=p.STATES[:2]; p.main()'` |
| [preview-round](reports/b71_s6/preview-round.log) | 2026-09-16T06:11:41.169122+00:00 | 19.898 | 0 | `python3 -c 'import sys; sys.path.insert(0,"reports/b71_s6"); import prove_previews as p; p.STATES=p.STATES[:1]; p.main()'` |
| [sprite-first](reports/b71_s6/sprite-first.log) | 2026-09-16T06:12:48.277022+00:00 | 75.485 | 1 | `python3 tests/mod_editor/test_nfl2k5_scorebug_sprite.py -v` |
| [previews](reports/b71_s6/previews.log) | 2026-09-16T06:14:25.466475+00:00 | 160.811 | 0 | `python3 reports/b71_s6/prove_previews.py` |
| [finish](reports/b71_s6/finish.log) | 2026-09-16T06:16:10.578888+00:00 | 4.693 | 1 | `python3 reports/b71_s6/prove_finish.py` |
| [manifest](reports/b71_s6/manifest.log) | 2026-09-16T06:16:23.067182+00:00 | 0.567 | 1 | `python3 reports/b71_s6/refresh_manifest_projection.py` |
| [manifest-current](reports/b71_s6/manifest-current.log) | 2026-09-16T06:17:07.295363+00:00 | 333.928 | 1 | `python3 reports/b71_s6/refresh_manifest_projection.py` |
| [finish-current](reports/b71_s6/finish-current.log) | 2026-09-16T06:17:08.445184+00:00 | 17.063 | 0 | `python3 reports/b71_s6/prove_finish.py` |
| [final-test_apf_scorebug_workspace_qt](reports/b71_s6/final-test_apf_scorebug_workspace_qt.log) | 2026-09-16T06:17:18.546619+00:00 | 1.463 | 0 | `python3 tests/mod_editor/test_apf_scorebug_workspace_qt.py -v` |
| [final-test_nfl2k5_scorebar_rim](reports/b71_s6/final-test_nfl2k5_scorebar_rim.log) | 2026-09-16T06:17:18.547056+00:00 | 14.159 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebar_rim.py -v` |
| [final-test_nfl2k5_scorebar_v3](reports/b71_s6/final-test_nfl2k5_scorebar_v3.log) | 2026-09-16T06:17:18.547728+00:00 | 100.715 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebar_v3.py -v` |
| [final-test_nfl2k5_scorebug_assets](reports/b71_s6/final-test_nfl2k5_scorebug_assets.log) | 2026-09-16T06:17:20.009725+00:00 | 148.199 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_assets.py -v` |
| [final-test_nfl2k5_scorebug_author](reports/b71_s6/final-test_nfl2k5_scorebug_author.log) | 2026-09-16T06:17:32.706692+00:00 | 6.3 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_author.py -v` |
| [final-test_nfl2k5_scorebug_exact](reports/b71_s6/final-test_nfl2k5_scorebug_exact.log) | 2026-09-16T06:17:39.007456+00:00 | 63.376 | 1 | `python3 tests/mod_editor/test_nfl2k5_scorebug_exact.py -v` |
| [owner-bounds](reports/b71_s6/owner-bounds.log) | 2026-09-16T06:18:30.632083+00:00 | 15.533 | 0 | `python3 reports/b71_s6/prove_owner_bounds.py` |
| [custom-design](reports/b71_s6/custom-design.log) | 2026-09-16T06:18:31.810635+00:00 | 8.392 | 0 | `python3 reports/b71_s6/prove_custom_design.py` |
| [final-test_nfl2k5_scorebug_fonts](reports/b71_s6/final-test_nfl2k5_scorebug_fonts.log) | 2026-09-16T06:18:42.384035+00:00 | 8.884 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_fonts.py -v` |
| [final-test_nfl2k5_scorebug_freeze](reports/b71_s6/final-test_nfl2k5_scorebug_freeze.log) | 2026-09-16T06:18:51.268146+00:00 | 242.333 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_freeze.py -v` |
| [final-test_nfl2k5_scorebug_freeze_v2](reports/b71_s6/final-test_nfl2k5_scorebug_freeze_v2.log) | 2026-09-16T06:18:59.263150+00:00 | 53.428 | 1 | `python3 tests/mod_editor/test_nfl2k5_scorebug_freeze_v2.py -v` |
| [final-test_nfl2k5_scorebug_ingame](reports/b71_s6/final-test_nfl2k5_scorebug_ingame.log) | 2026-09-16T06:19:48.209387+00:00 | 14.66 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_ingame.py -v` |
| [final-test_nfl2k5_scorebug_ingame_fix](reports/b71_s6/final-test_nfl2k5_scorebug_ingame_fix.log) | 2026-09-16T06:19:52.691495+00:00 | 126.344 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_ingame_fix.py -v` |
| [final-test_nfl2k5_scorebug_mnf](reports/b71_s6/final-test_nfl2k5_scorebug_mnf.log) | 2026-09-16T06:20:02.869616+00:00 | 11.974 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_mnf.py -v` |
| [final-test_nfl2k5_scorebug_mnf_v3](reports/b71_s6/final-test_nfl2k5_scorebug_mnf_v3.log) | 2026-09-16T06:20:14.844186+00:00 | 49.02 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_mnf_v3.py -v` |
| [previews-final](reports/b71_s6/previews-final.log) | 2026-09-16T06:20:17.693053+00:00 | 162.41 | 0 | `python3 reports/b71_s6/prove_previews.py` |
| [final-test_nfl2k5_scorebug_native](reports/b71_s6/final-test_nfl2k5_scorebug_native.log) | 2026-09-16T06:21:03.864849+00:00 | 131.24 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_native.py -v` |
| [compiler-pins](reports/b71_s6/compiler-pins.log) | 2026-09-16T06:21:15.285408+00:00 | 0.093 | 1 | `python3 reports/b71_s6/regenerate_pins.py` |
| [compiler-pins-current](reports/b71_s6/compiler-pins-current.log) | 2026-09-16T06:21:34.705017+00:00 | 38.55 | 0 | `python3 reports/b71_s6/regenerate_pins.py` |
| [final-test_nfl2k5_scorebug_projection](reports/b71_s6/final-test_nfl2k5_scorebug_projection.log) | 2026-09-16T06:21:59.035602+00:00 | 58.007 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_projection.py -v` |
| [previews-release](reports/b71_s6/previews-release.log) | 2026-09-16T06:22:51.881309+00:00 | 164.711 | 0 | `python3 reports/b71_s6/prove_previews.py` |
| [final-test_nfl2k5_scorebug_resources](reports/b71_s6/final-test_nfl2k5_scorebug_resources.log) | 2026-09-16T06:22:53.601968+00:00 | 286.168 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_resources.py -v` |
| [final-test_nfl2k5_scorebug_runtime](reports/b71_s6/final-test_nfl2k5_scorebug_runtime.log) | 2026-09-16T06:22:57.042645+00:00 | 119.768 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_runtime.py -v` |
| [manifest-final](reports/b71_s6/manifest-final.log) | 2026-09-16T06:23:12.684386+00:00 | 336.259 | 1 | `python3 reports/b71_s6/refresh_manifest_projection.py` |
| [final-test_nfl2k5_scorebug_source_art](reports/b71_s6/final-test_nfl2k5_scorebug_source_art.log) | 2026-09-16T06:23:15.105082+00:00 | 0.472 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_source_art.py -v` |
| [final-test_nfl2k5_scorebug_sprite](reports/b71_s6/final-test_nfl2k5_scorebug_sprite.log) | 2026-09-16T06:23:15.577809+00:00 | 78.136 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_sprite.py -v` |
| [finish-release](reports/b71_s6/finish-release.log) | 2026-09-16T06:24:21.173205+00:00 | 17.461 | 0 | `python3 reports/b71_s6/prove_finish.py` |
| [final-test_nfl2k5_scorebug_template](reports/b71_s6/final-test_nfl2k5_scorebug_template.log) | 2026-09-16T06:24:33.714298+00:00 | 9.932 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_template.py -v` |
| [final-test_nfl2k5_scorebug_template_release](reports/b71_s6/final-test_nfl2k5_scorebug_template_release.log) | 2026-09-16T06:24:43.646237+00:00 | 0.552 | 1 | `python3 tests/mod_editor/test_nfl2k5_scorebug_template_release.py -v` |
| [final-test_nfl2k5_scorebug_unified_adapter](reports/b71_s6/final-test_nfl2k5_scorebug_unified_adapter.log) | 2026-09-16T06:24:44.198418+00:00 | 0.165 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_unified_adapter.py -v` |
| [final-test_nfl2k5_scorebug_v10_ingame](reports/b71_s6/final-test_nfl2k5_scorebug_v10_ingame.log) | 2026-09-16T06:24:44.363871+00:00 | 9.028 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_v10_ingame.py -v` |
| [final-test_nfl2k5_scorebug_v10_projection](reports/b71_s6/final-test_nfl2k5_scorebug_v10_projection.log) | 2026-09-16T06:24:53.392039+00:00 | 28.835 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_v10_projection.py -v` |
| [final-test_nfl2k5_scorebug_versions](reports/b71_s6/final-test_nfl2k5_scorebug_versions.log) | 2026-09-16T06:24:56.811295+00:00 | 9.846 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_versions.py -v` |
| [release-test_nfl2k5_scorebug_exact](reports/b71_s6/release-test_nfl2k5_scorebug_exact.log) | 2026-09-16T06:25:00.558351+00:00 | 85.508 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_exact.py -v` |
| [release-test_nfl2k5_scorebug_freeze_v2](reports/b71_s6/release-test_nfl2k5_scorebug_freeze_v2.log) | 2026-09-16T06:25:00.581213+00:00 | 330.767 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_freeze_v2.py -v` |
| [final-test_scorebug_sprite_preview_qt](reports/b71_s6/final-test_scorebug_sprite_preview_qt.log) | 2026-09-16T06:25:06.657451+00:00 | 10.094 | 0 | `python3 tests/mod_editor/test_scorebug_sprite_preview_qt.py -v` |
| [final-test_scorebug_studio_panel_qt](reports/b71_s6/final-test_scorebug_studio_panel_qt.log) | 2026-09-16T06:25:16.751611+00:00 | 7.388 | 0 | `python3 tests/mod_editor/test_scorebug_studio_panel_qt.py -v` |
| [final-nfl2k5_scorebug_layout_test](reports/b71_s6/final-nfl2k5_scorebug_layout_test.log) | 2026-09-16T06:25:22.227266+00:00 | 1.429 | 0 | `python3 tests/nfl2k5_scorebug_layout_test.py -v` |
| [final-nfl2k5_scorebug_mod_project_test](reports/b71_s6/final-nfl2k5_scorebug_mod_project_test.log) | 2026-09-16T06:25:23.656398+00:00 | 1.319 | 0 | `python3 tests/nfl2k5_scorebug_mod_project_test.py -v` |
| [final-test_provider_integrity](reports/b71_s6/final-test_provider_integrity.log) | 2026-09-16T06:25:24.139845+00:00 | 9.901 | 0 | `python3 tests/mod_editor/test_provider_integrity.py -v` |
| [final-test_product_catalog](reports/b71_s6/final-test_product_catalog.log) | 2026-09-16T06:25:24.976273+00:00 | 0.155 | 0 | `python3 tests/mod_editor/test_product_catalog.py -v` |
| [final-test_phase1_packaging](reports/b71_s6/final-test_phase1_packaging.log) | 2026-09-16T06:25:25.131431+00:00 | 2.157 | 0 | `python3 tests/mod_editor/test_phase1_packaging.py -v` |
| [final-test_mod_build](reports/b71_s6/final-test_mod_build.log) | 2026-09-16T06:25:27.288462+00:00 | 2.13 | 0 | `python3 tests/mod_editor/test_mod_build.py -v` |
| [final-test_build_panel_qt](reports/b71_s6/final-test_build_panel_qt.log) | 2026-09-16T06:25:29.419036+00:00 | 3.354 | 0 | `python3 tests/mod_editor/test_build_panel_qt.py -v` |
| [final-test_nfl2k5_allocator_scaleout](reports/b71_s6/final-test_nfl2k5_allocator_scaleout.log) | 2026-09-16T06:25:32.773222+00:00 | 821.091 | 0 | `python3 tests/mod_editor/test_nfl2k5_allocator_scaleout.py -v` |
| [final-test_nfl2k5_xbe_space](reports/b71_s6/final-test_nfl2k5_xbe_space.log) | 2026-09-16T06:25:34.041218+00:00 | 34.063 | 0 | `python3 tests/mod_editor/test_nfl2k5_xbe_space.py -v` |
| [compiler-pins-feather](reports/b71_s6/compiler-pins-feather.log) | 2026-09-16T06:26:23.165812+00:00 | 38.547 | 0 | `python3 reports/b71_s6/regenerate_pins.py` |
| [previews-sealed](reports/b71_s6/previews-sealed.log) | 2026-09-16T06:30:06.686465+00:00 | 163.833 | 0 | `python3 reports/b71_s6/prove_previews.py` |
| [sealed-test_nfl2k5_scorebug_sprite](reports/b71_s6/sealed-test_nfl2k5_scorebug_sprite.log) | 2026-09-16T06:30:07.865720+00:00 | 78.494 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_sprite.py -v` |
| [sealed-test_nfl2k5_scorebug_exact](reports/b71_s6/sealed-test_nfl2k5_scorebug_exact.log) | 2026-09-16T06:30:07.866087+00:00 | 86.154 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_exact.py -v` |
| [sealed-test_nfl2k5_scorebug_freeze_v2](reports/b71_s6/sealed-test_nfl2k5_scorebug_freeze_v2.log) | 2026-09-16T06:30:07.866541+00:00 | 330.688 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_freeze_v2.py -v` |
| [manifest-sealed](reports/b71_s6/manifest-sealed.log) | 2026-09-16T06:30:27.737979+00:00 | 337.023 | 0 | `python3 reports/b71_s6/refresh_manifest_projection.py` |
| [art-pin](reports/b71_s6/art-pin.log) | 2026-09-16T06:30:44.341251+00:00 | 0.028 | 0 | `python3 reports/b71_s6/refresh_art_pin.py` |
| [sealed-test_nfl2k5_scorebug_resources](reports/b71_s6/sealed-test_nfl2k5_scorebug_resources.log) | 2026-09-16T06:31:26.360504+00:00 | 288.703 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_resources.py -v` |
| [sealed-test_nfl2k5_scorebug_template_release](reports/b71_s6/sealed-test_nfl2k5_scorebug_template_release.log) | 2026-09-16T06:31:34.020131+00:00 | 0.55 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_template_release.py -v` |
| [sealed-test_provider_integrity](reports/b71_s6/sealed-test_provider_integrity.log) | 2026-09-16T06:31:34.570581+00:00 | 9.98 | 0 | `python3 tests/mod_editor/test_provider_integrity.py -v` |
| [sealed-test_product_catalog](reports/b71_s6/sealed-test_product_catalog.log) | 2026-09-16T06:31:44.550537+00:00 | 0.154 | 0 | `python3 tests/mod_editor/test_product_catalog.py -v` |
| [sealed-test_phase1_packaging](reports/b71_s6/sealed-test_phase1_packaging.log) | 2026-09-16T06:31:44.704876+00:00 | 2.111 | 0 | `python3 tests/mod_editor/test_phase1_packaging.py -v` |
| [sealed-test_scorebug_sprite_preview_qt](reports/b71_s6/sealed-test_scorebug_sprite_preview_qt.log) | 2026-09-16T06:31:46.816004+00:00 | 10.038 | 0 | `python3 tests/mod_editor/test_scorebug_sprite_preview_qt.py -v` |
| [finish-sealed](reports/b71_s6/finish-sealed.log) | 2026-09-16T06:34:02.002966+00:00 | 17.665 | 0 | `python3 reports/b71_s6/prove_finish.py` |
| [owner-bounds-sealed](reports/b71_s6/owner-bounds-sealed.log) | 2026-09-16T06:34:02.018423+00:00 | 15.397 | 0 | `python3 reports/b71_s6/prove_owner_bounds.py` |
| [builder-final](reports/b71_s6/builder-final.log) | 2026-09-16T06:34:02.039388+00:00 | 0.267 | 0 | `python3 reports/b71_s6/verify_builder.py` |
| [validators-plan](reports/b71_s6/validators-plan.log) | 2026-09-16T06:34:02.340647+00:00 | 0.297 | 0 | `python3 tools/validate_all_mod_editor_capabilities.py --list` |
| [registry-final](reports/b71_s6/registry-final.log) | 2026-09-16T06:35:37.547353+00:00 | 0.153 | 0 | `python3 -m mod_editor.capabilities.validate_registry` |
| [gate-test_xbe_patch_memory_writes](reports/b71_s6/gate-test_xbe_patch_memory_writes.log) | 2026-09-16T06:36:04.761630+00:00 | 1548.162 | 0 | `python3 tests/mod_editor/test_xbe_patch_memory_writes.py -v` |
| [gate-test_xbe_patch_cave_references](reports/b71_s6/gate-test_xbe_patch_cave_references.log) | 2026-09-16T06:36:04.762363+00:00 | 1735.277 | 0 | `python3 tests/mod_editor/test_xbe_patch_cave_references.py -v` |
| [projection-compaction](reports/b71_s6/projection-compaction.log) | 2026-09-16T06:37:34.167526+00:00 | 0.542 | 0 | `python3 reports/b71_s6/compact_projection.py` |
| [projection-identity](reports/b71_s6/projection-identity.log) | 2026-09-16T06:37:34.740736+00:00 | 0.222 | 0 | `python3 reports/b71_s6/prove_projection_identity.py` |
| [registry-strict](reports/b71_s6/registry-strict.log) | 2026-09-16T06:39:13.864781+00:00 | 0.148 | 0 | `python3 -m mod_editor.capabilities.validate_registry` |
| [finish-native-profile](reports/b71_s6/finish-native-profile.log) | 2026-09-16T06:41:14.347687+00:00 | 19.4 | 0 | `python3 reports/b71_s6/prove_finish.py` |
| [gate-test_nfl2k5_cave_oracle](reports/b71_s6/gate-test_nfl2k5_cave_oracle.log) | 2026-09-16T07:01:52.924157+00:00 | 355.728 | 0 | `python3 tests/mod_editor/test_nfl2k5_cave_oracle.py -v` |
| [gate-test_nfl2k5_owner_pairwise_composition](reports/b71_s6/gate-test_nfl2k5_owner_pairwise_composition.log) | 2026-09-16T07:05:00.040155+00:00 | 2872.036 | 0 | `python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py -v` |

ASTRA_DONE

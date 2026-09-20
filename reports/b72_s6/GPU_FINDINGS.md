# b72-s6: capture gap proved, dark-label cause unresolved

The supplied 13:55:49 sample cannot establish the cause: it contains **zero draws of the appended scorebug atlas**. It contains 60,972 method events, 788 closed BEGIN/END pairs, one unmatched initial END, and no surface/clear/flip boundary events. The claim that this 0.1-second window covers several whole frames is not supported by its contents. There is no cause-specific runtime fix in this branch and no successful within-15 pixel reproduction.

This job nevertheless establishes that the atlas and palette are intact in the captured RAM, recovers useful earlier live HUD state from the same session, and proves a second capture limitation in xemu's logger. It preserves s5's team colours and all runtime bytes.

## Evidence and trace coverage

[Input identities](input_identities.json) record SHA-256 and length for the read-only inputs. The supplied sample is exactly bytes `[13976229,18742095)` of the original session `trace.log` in the same capture directory. [Sample summary](sample_summary.json), [all 788 draw identifiers](sample_draws.csv), and [complete observed draw state](sample_draw_states.json.gz) are reproducible with `analyze_capture.py`. Decompress the latter with Python's `gzip`; it contains method state, last-write line numbers, program memory, constants and geometry events for every observed draw. Unobserved state is absent, never defaulted to zero.

The stock logger intentionally suppresses **all NV097_ARRAY_ELEMENT16 parameter values**. Its separate abbreviation event gives only a run count and was not enabled in this capture. Consequently 395 sample BEGIN/END pairs have no logged geometry values. They must not be called empty draws. This behavior is present both in the supplied local source at `pgraph/pgraph.c:525-550` and in [the exact installed commit's logger](https://raw.githubusercontent.com/xemu-project/xemu/fc24584ce88f0915ad7f04775bb7712c2e3f49ee/hw/xbox/nv2a/pgraph/pgraph.c). Enabling `nv2a_pgraph_method_abbrev` alone will not recover indices.

The stdout log identifies xemu 0.8.136 as commit `fc24584ce88f0915ad7f04775bb7712c2e3f49ee`, dated June 14. The supplied local source is September 14 commit `f9b14039e5bb56ae2d8f028e31e7cc19f13f7e12`. These are different revisions. The installed revision's logger and transform upload semantics were checked against its upstream source and agree for the issues above. Its complete GL shader/cache implementation was not checked byte-for-byte. [Source receipt](xemu_source.json) keeps that limitation explicit.

## Additional earlier window recovered

The original session trace, found alongside the RAM, contains six sprite-atlas draws in its earlier **13:55:28** window, bytes `[8084087,13756572)`. Windows were parsed independently, without carrying state across disabled intervals. [Earlier draw inventory](earlier_draws.csv) and [full HUD snapshots](earlier_hud_draws.json) retain this separate provenance.

The later RAM contains the relocated sprite scene at physical `0x01e75900`, CPU pointer `0x81e75900`. Its vertex arrays are position `0x01e77f60`, colour `0x01e78620`, UV `0x01e78624`, and transform index `0x01e78628`. Those match the earlier trace. Its serialized index batches match disc p exactly. The eight visible RAM descriptors match the earlier eight-draw sequence and texture changes:

| Earlier draw | BEGIN / END lines in full trace | Inferred material | Role |
|---|---|---|---|
| 388 | 157435 / 157436 | cscore_buga | Housing and capsule |
| 389 | 157451 / 157452 | score_buga | Static accent geometry |
| 390 | 157467 / 157468 | dscore_buga | Body, down plate and pointer |
| 391 | 157478 / 157479 | hscore_buga | Team logo |
| 392 | 157489 / 157490 | yscore_buga1 | Down label and timeout ticks |
| 393 | 157500 / 157501 | yscore_buga | Scores, clock, quarter and play clock |
| 394 | 157511 / 157512 | zscore_buga | Team logo |
| 395 | 157522 / 157523 | zz_ESPN_bug1 | Brand |

This is a strongly corroborated correspondence, **not proof of the earlier index stream**: the trace omitted indices and the RAM snapshot is later. Material names and inferred indices are marked accordingly. The RAM positions and UVs identify the live down glyph vertices 140, 144, 152, 160 and 164, with hidden spaces 148 and 156; the score digits begin at 52 and 64. [RAM descriptor evidence](ram_scene_batches.json) and [glyph probes](model_probe.json) retain the values. No CPU virtual address was blindly treated as a physical address.

## Resource integrity

The disc-p ISO path recorded in xemu's configuration is no longer present. Its saved `.2k5patch` is present and was opened read-only. Pack 0 starts 5,870 sectors into `operations/file-0000.bin`; the version-2 file-growth metadata was respected. The atlas extracted from that actual build, not just a reconstruction, matches RAM in every byte:

| Region | Physical address | Bytes | SHA-256 | Changed bytes |
|---|---|---:|---|---:|
| Swizzled 256x512 P8 indices | 0x01e55480 | 131072 | 964f45b1cd7f9c3516f29307c4ad456bed1b25e51f0c3fc54f2ef658571c23dd | 0 |
| BGRA palette | 0x01e75480 | 1024 | c941f988309430391a56af7603a22996eebc73062f0e580bcdc41c6e77eada3f | 0 |

[Comparison receipt](ram_build_comparison.json), [decoded generated atlas](ram_atlas.png). The comparison also agrees with the s3 baseline compiler. The RAM file ends at `0x03877000`, leaving 7,901,184 top bytes absent; all these texture, palette and scene ranges are present. This proves intact guest bytes at dump time. It does not prove xemu's host texture cache held these bytes when a failing fragment ran, or that bytes were unchanged across the earlier window.

## Observed fragment state and failed reproduction

[Full method comparison](gpu_methods.md) includes all observed texture units, register-combiner stages and constants, final combiner, blend, alpha test, fog, mask, vertex state and write provenance. Writes before the first sprite array setup are marked as preceding-game state. This describes trace chronology, not a recovered CPU call stack. There is no separate TFACTOR method; its possible effects reside in the captured combiner constants.

The inferred label and score draws have **identical observed state dictionaries**, including texture offset/format/palette/filter, combiners, blend and alpha test. Both execute the same 13-instruction vertex program as s5. Both have `c6=(0.5,0.5,0.5,0.5)` and `c7=(0.5,0.5,0.5,0.5)`. Final constants are zero. The colour instruction reads c6; c5's earlier changes do not explain this result. White label vertices remain `0xffffffff`; score vertices are `0xfffdfdfd`.

The live filter is `0x02063f00`, versus fixture `0x02062000`: LOD bias -1 instead of 0. Both use linear filtering, and the atlas has one mip. The GL upload sets `GL_TEXTURE_MAX_LEVEL=levels-1` (`pgraph/gl/texture.c:734-735` in the supplied source). The model now accepts these two explicitly checked settings while still refusing unsupported filters and incomplete vertex programs. This difference cannot select a darker mip from these bytes.

The exact RAM regions now run through the shared P8 swizzle/palette decoder and observed fragment pipeline. At opaque glyph texel centres, all five label glyphs predict luminance 255, and both score glyphs predict 253. The table below measures explicit screenshot interiors in display coordinates; it is not a pixel-aligned raster comparison:

| Screenshot | Label interior min / mean / max | Score maxima | Model label core | Reproduction |
|---|---|---|---|---|
| shot_6_xemu_window.png | 18.45 / 19.66 / 32.79 | 253 / 253 | 255 | FAIL / unavailable exact raster |
| noah_screenshot_135542_49ers_at_bills.png | 18.45 / 19.66 / 32.79 | 253 / 253 | 255 | FAIL / unavailable exact raster |

The second screenshot is translated +32,+17 in desktop coordinates; its play clock is 27, versus 19 in the later grab. Rectangles and measurements are recorded in [model_probe.json](model_probe.json). The label-core versus measured-interior difference is over 222, but that number is not offered as a matched-pixel calibration error. There is no fitted gain, bias or invented darkening multiplier.

The known fragment expression still cannot explain the dark label. Raster coverage, rejection, host cached data/shader behavior and later overdraw remain unresolved alternatives. The remaining unknowns include depth-test enable, shade mode, logic-op enable/op, DMA objects, target/viewport/AA state at the earlier HUD, generated shader uniforms and render-target history. Another arbitrary state reset would not be a proved cause fix.

## Decision and unchanged runtime

The reproduction gate fails. No runtime, scene, template, team palette or label placement change is made. A fixed all-team >=200 core / >=4.5:1 gate cannot be certified without the missing reproduction. Existing all-slot native tint checks, native order and 71.1 visibility regressions remain in the validation inventory. They do not become an in-game readability claim.

The RX owner remains 4,086/4,096 bytes with 10 bytes spare; RW remains 128 bytes; appended resources remain 324,832/400,000 bytes. [Budget and unchanged-source receipt](budgets.json). The only product changes are diagnostic parsing and exact-RAM decoding/filter support, plus declarations, pins and synthetic/native regression coverage. Provider closure size remains 301.

[Next capture instructions](NEXT_CAPTURE.md) specify the exact missing data and bounded tracing. [Validation](VALIDATION.md) records outcomes and inherited limitations. No emulator, test disc, installer or release was launched or built, and no new in-game result is claimed. The integrator owns any test disc, and shipping remains contingent on the player's approval.

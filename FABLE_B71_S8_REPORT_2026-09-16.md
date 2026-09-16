# Beta 71 S8: sprite scorebug on the real display, a yellow FLAG plate and the ESPN MNF watermark (Claude Fable, 2026-09-16)

Branch `fable/b71-s8-widescreen-flag-watermark` from the S6 head 563e14e4. EXPERIMENTAL; the option stays off in every
preset. Native layout, ownership and volume checks are proved; the played-game picture is UNWITNESSED.

## 1. Why the logos looked squeezed in game, and the fix

The layout is authored in 1920x1080 broadcast pixels. Rows were mapped through the 448-line viewport
(`16 + y*448/1080`) and columns through `x/3`, i.e. one layout column per three broadcast pixels, for both displays.
That mapping only holds if the 640x448 HUD is stretched straight to 1920x1080. It is not:

- the game presents its 640x448 HUD target scaled to the whole picture (this is what the emulator shows; measured on
  the disc n screenshot, `reports/b71_s8/display_model.json`);
- at 4:3 a HUD column is 640/1440 of the picture width against 448/1080 of its height, so a HUD pixel is 0.93 as wide as
  it is tall;
- with the widescreen option (`nfl2k5_widescreen.py`, docstring lines 5-8 and `pillarbox_x`), HUD x is contracted by
  27/32 about column 320 and the 640 columns then fill a 16:9 picture, so a HUD pixel ends up 1.05 as wide as tall.

The preview code had modelled the contraction and then "undone" it for the comparisons, so the pictures the lead saw
were restored to source coordinates while the disc drew the bar 16 percent narrower than tall at 16:9 (and 20 percent
at 4:3). Fix (`mod_editor/core/nfl2k5_scorebug_sprite.py`, `DISPLAY`, `x_scale`, `hud_box`, `scene_box`,
`contracted`, `display_box`): the compiler lays the scene out for the display the disc is built for. One layout column
is `640 / picture_width / contraction` HUD pixels (0.3951 at 16:9, 0.4444 at 4:3), so one broadcast pixel is one
display pixel on a 16:9 picture and the bar keeps its proportions on both. The aspect is threaded from the build plan
(`mod_build.py` passes `widescreen=plan.widescreen` to `runtime_apply_in_place`, through `runtime_image_plan`,
`compile_runtime_collection` and `compile_collection`); `pack_status` recognises a collection built for either display;
the Studio preview compiles both and now also writes a display-space image of the modelled picture (`*_display.png`).

Predicted on-screen aspect (width/height) of the layout boxes, before (S6, x/3) and after (S8):

| Region | Display | Source | Before | After |
| --- | --- | ---: | ---: | ---: |
| bar | 4:3 | 9.464 | 7.098 | 9.464 |
| bar | 16:9 | 9.464 | 7.985 | 9.464 |
| capsule | 4:3 | 4.500 | 3.375 | 4.500 |
| capsule | 16:9 | 4.500 | 3.797 | 4.500 |
| plate | 4:3 | 6.833 | 5.125 | 6.833 |
| plate | 16:9 | 6.833 | 5.766 | 6.833 |
| away and home logo | 4:3 | 1.869 | 1.402 | 1.869 |
| away and home logo | 16:9 | 1.869 | 1.577 | 1.869 |

Check against the disc n screenshot (`~/Downloads/ksnip_20260916-043627.png`, a 1129x673 capture of the 16:9 mode):
the KC arrowhead's white area measures 82x66 px, aspect 1.242; the model predicts 1.216 for the S6 disc on that
window and 1.442 after the fix (1.528 on a true 16:9 picture). The window itself is 1.68:1, not 1.78:1, which squeezes
everything by a further 6 percent: xemu's `display.ui.fit` in `~/.var/app/app.xemu.xemu/data/xemu/xemu/xemu.toml`
should be `scale` (letterbox) rather than `stretch`, or the window resized to 16:9.

One difference remains that is not the display chain: ESPN draws the arrowhead 198x105 (1.886) inside its 200x107 box,
i.e. wider than the official mark's own proportions, while our logo texture keeps the mark's true proportions (165x108,
1.528, in the 16:9 display render). Matching that needs a logo-fit decision (stretch to the box), not a chain change.

Proof images: `reports/b71_s8/espn_vs_s8_169_2x.png` (ESPN frame above, the 16:9 display render below, one source pixel
per display pixel), `reports/b71_s8/s8_43_2x.png`, `reports/b71_s8/standard_{43,169}_display.png`; copies in the hub
`beta71_evidence/bar_compare_espn_vs_s8_sprite_169_2x.png` and `bar_s8_sprite_43_2x.png`.

## 2. FLAG in yellow

The FLAG event quad (retail material 2) now draws a new atlas cell `flag`: the plate pill in broadcast yellow (255,204,0)
with the plate's shading and a dark (26,26,26) bold FLAG label baked in (`tools/scorebug_sprite/author_default.py`).
The retail formatter at 0xFBE90 copies the literal at 0xE6C464 ("FLAG"), which the element draw loop colours from the
element record at runtime (0xA95B28 is written every frame), so the white text cannot be recoloured by a static edit.
The literal is blanked instead: `nfl2k5_scorebug_runtime.LITERALS` gains `0xE6C464: ("FLAG", "\0\0\0\0")`, ten bytes for
ten, the only reference to that literal in the executable (file offset 0xEBE91). This is an XBE data write in the same
`.string_` class as the existing GOAL literal, so **owner-visible XBE bytes change** and the A8 integration must
regenerate the cave manifest and rerun the XBE gates after merging. Preview: `reports/b71_s8/flag_s8_169_2x.png`
(hub `beta71_evidence/flag_s8_169_2x.png`); the native FLAG state draws no retail glyphs
(`test_updates_values_hide_unused_slots_and_keep_retail_events`).

## 3. ESPN MNF watermark, an exact replica from the stills

Not the game's `espn_logo`/`espn_bug`/`nfllogo_01` textures: the mark is lifted from the broadcast frames. Over 999
frames (every 30th from frame_000101) the mark is present in 944; the per-pixel temporal minimum of luminance over those
frames lifts the static translucent overlay off its darkest background (black level 0.0), alpha = min/255, coverage =
alpha / p95(alpha). Measured: box [1655,35,1869,64] on the 1080p frame (214x29 with 2 px margins, letters 210x25),
opacity 0.714 (median over the mark 0.655), colour (255,251,241). Proportions and letterforms are the still's own; nothing
is redrawn. `reports/b71_s8/watermark_still_vs_cell_4x.png` shows a 4x crop of frame_012001 beside the cell rendered on
charcoal (hub `beta71_evidence/watermark_still_vs_s8_cell_4x.png`); `reports/b71_s8/watermark_espn_vs_s8_2x.png` shows
the still's top right beside the 16:9 display render.

Structure, the first of a family: `layout.json` gains a `brand` group. Each brand row has its own untinted coverage
cell, a box, material, `pin`, `opacity` and a `source` record (frames, method, black level, measured opacity, colour).
The compiler multiplies the cell's alpha by the row's opacity when packing, treats the row as a static layer, and
`pin: "top-right"` slides the box to the last drawable HUD column of the display it compiles for, 12 source pixels in:
right edge 1758 at 16:9 (HUD 550.7..635.3) and 1668 at 4:3. The mark rides the always-visible wing material 9 (the body
material's push buffer was full at five quads), so it appears exactly when the bar does. The atlas stays 256x512 P8;
the appended payload is unchanged at **323,808 bytes** (34 textures, one 20,352-byte scene with 47 quads, no FONT).

A note for the lead: the stills carry "ESPN MNF" (Monday Night Football); a plain ESPN or an ESPN NFL mark is another
brand row lifted the same way when a broadcast still with that mark is available.

## Files

- `mod_editor/core/nfl2k5_scorebug_sprite.py`: display model, per-display compile, brand rows, pinned layers,
  display-space preview output; `nfl2k5_scorebug_resources.py`, `nfl2k5_scorebug_ingame.py`, `mod_build.py`: the
  `widescreen` keyword; `nfl2k5_scorebug_runtime.py`: the FLAG literal.
- `tools/scorebug_sprite/author_default.py` (regenerates `data/nfl2k5_scorebug_sprite/{template.png,layout.json}`
  byte-for-byte; the reviewed PNG catalog entry and its hash in `packaging/check_2k5_mod_studio_release.py` updated).
- Tests: `tests/mod_editor/test_nfl2k5_scorebug_sprite.py` (display model, brand pin, flag cell, literal, per-display
  boxes and events), the two build-integration stubs accept the new keyword.
- Registry row `nfl2k5.scorebug_presentation.runtime` summary and evidence; RC96 changelog bullet; `repin.py --apply`.

## Checks (logs in `reports/b71_s8/logs/`)

| Suite | Tests | Result | Seconds |
| --- | ---: | --- | ---: |
| test_nfl2k5_scorebug_sprite (final run after the quad-count fix) | 17 | OK | 85 |
| test_scorebug_sprite_preview_qt | 2 | OK | 21 |
| test_nfl2k5_scorebug_mnf | 10 | OK | 12 |
| test_nfl2k5_scorebug_runtime | 12 | OK | 99 |
| test_nfl2k5_scorebug_exact | 8 | OK | 84 |
| test_nfl2k5_scorebug_resources (final run after the stub fix) | 6 | OK | 283 |
| test_nfl2k5_scorebug_assets | 8 | OK | 181 |
| test_nfl2k5_scorebug_mnf_v3 | 7 | OK | 47 |
| test_nfl2k5_scorebug_native | 4 | OK | 98 |
| test_provider_integrity | 8 | OK | 10 |
| test_product_catalog | 9 | OK | 0 |
| test_phase1_packaging | 23 | OK | 2 |
| test_beta61_integration + test_mod_build_beta62_integration (stubs accept the keyword) | 13 | OK | 221 |

The first chained runs of the sprite and resources suites failed on stale expectations only (the 46-quad count and a
test stub that did not accept the new keyword); both were fixed in the tests and rerun green.

Strict registry validation: MOD_CAPABILITY_REGISTRY_VALIDATION_PASS, 176 capabilities, file checks on. Compiler pins regenerated (no change to the mnf probe pins). PNG catalog
hash re-pinned. Owner code bytes unchanged; XBE data changes by the ten literal bytes (gates are A8's to rerun).

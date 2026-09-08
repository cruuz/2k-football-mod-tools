# ESPN scorebar template (Fable, 2026-09-07)

A modular, repaintable template for the in-game ESPN scorebar in ESPN NFL 2K5, drawn
from new art: Noah's SVG lineage (`docs/scorebug_svg`) re-laid to the game's 476 x 48
bar with the ESPN mark on the left. Nothing here comes from the disc's `espn1`,
`nflShield1` or `score_buga` art. The folder is the input to the studio's scorebar
compiler (the v10 job); this file describes the contract, not the compiler.

```
scorebug_bar_master.svg   the bar, one named group per layer (repaint here)
team_block_template.svg   the away / home block with team-colour bindings
teams.json                32 palettes (primary, secondary, text on primary)
layout.json               THE CONTRACT: rectangles, text anchors, atlas, palette
build.py                  exports everything below from the three files above
layers/1x, layers/2x      one full-canvas RGBA PNG per layer (476x48 and 952x96)
teams/1x, teams/2x        <ABBR>_away.png / <ABBR>_home.png for all 32 teams
atlas/                    a packed P8 proof (atlas_1x.png), tile map, palette report
preview_640x480.png       the bar on a field, 4:3 HUD, stand-in text
preview_2x.png            the same at 2x
compare.png               this bar / supplied target / static v9, all at 2x
previews/                 team matchups, all 32 teams, widest strings, zoom crops
reference/                copies of target_NO_MIA.png and after_v9_640x480.png
```

## What the bar is

One 476 x 48 frame inside the HUD rails `[84, 381, 560, 429]` at 640 x 480.
Cells, left to right (bar-local x):

| cell | x | contents |
| --- | --- | --- |
| ESPN mark | 0..104 | darker tone, 96 x 24 mark at (4,12), 1 px separator |
| away block | 104..222 | colour band 104..130, abbreviation 132..172, score 174..218 |
| centre | 222..358 | red down banner 226..354 x 3..21 over the clock pill 228..352 x 25..45 |
| home block | 358..476 | score 362..406, abbreviation 408..448, colour band 450..476 |

The clock pill splits into quarter 228..264, game clock 264..318, play clock 318..352.
`hud = bar + (84, 381)`.

## Which file to repaint

| you want to change | edit | exported to |
| --- | --- | --- |
| frame, rim, gloss, mark-cell tone | `layer_frame` in the master SVG | `layers/*/frame.png` |
| the ESPN mark | `layer_espn_mark` (paths from `espn_nfl_watermark.svg`) | `layers/*/espn_mark.png` |
| neutral away / home panel | `layer_away_block`, `layer_home_block` | `layers/*/away_block.png`, `home_block.png` |
| the dark wells behind the scores | `layer_score_cells` | `layers/*/score_cells.png` |
| the red down-and-distance banner | `layer_down_cell` | `layers/*/down_cell.png` |
| the quarter / clock / play-clock pill | `layer_clock_quarter_cell` | `layers/*/clock_quarter_cell.png` |
| timeout dashes (off by default) | `layer_timeout_marks` | `layers/*/timeout_marks.png` |
| team colours, band width, rail | `team_block_template.svg` + `teams.json` | `teams/*/<ABBR>_{away,home}.png` |

You can also skip the SVG and paint the 1x PNGs in `layers/1x` directly: each is the
full 476 x 48 canvas, transparent outside its layer, and the compiler reads those.
Whatever you edit, keep the layer inside its `rect_bar` in `layout.json`; the game
draws each layer where that file says and stretches nothing.

Rebuild after editing (needs inkscape 1.x, Pillow, numpy):

```sh
python3 docs/scorebug_template_fable/build.py            # everything
python3 docs/scorebug_template_fable/build.py --skip-teams
```

The `guides` group in the master SVG (hidden) shows the eight live-text cells. Turn it
on in Inkscape while you paint, it is never exported.

## Size and palette rules

* 1x is the truth: 476 x 48 px, one pixel per HUD unit at 640 x 480. 2x (952 x 96) is
  for editing comfort and is downsampled by nobody: the compiler reads 1x.
* The bar is one P8 texture: at most 256 distinct RGBA colours across every layer
  that shares it. v9 found that 256-colour atlases overflow the retail VC-LZ overlap
  scratch and 128 fits, so `layout.json` sets `palette_target` 128 and `build.py`
  reduces to that (median cut on opaque pixels, no dithering). The default set as
  built lands well under it; `atlas/palette_report.json` has the exact counts.
* Team blocks are separate textures, one palette each (selected at runtime by the
  hook, see below). `build.py` reduces each 1x block to 128 colours too.
* Keep gradients short and avoid photographic textures; every distinct colour costs a
  palette slot. Alpha is per palette entry, so semi-transparent art costs slots too.
* Text cells must stay clear. The game's own font draws on top of the art; busy art
  under white or yellow text makes it unreadable on a TV.
* The atlas tile spec in `layout.json` shows how the frame packs as a left cap (106
  px, keeps the mark-cell tone), an 8 px stretched body and a 14 px right cap, and how
  the neutral blocks pack as 8 px stretched strips. If you paint horizontal detail into
  the neutral blocks or the frame body, tell the compiler to store them `exact`.

## How the game text overlays the cells

`layout.json` -> `text` lists the eight live fields. Each has an HUD `x`, a baseline
`y`, an alignment, a colour, a max character count and the intended cap height:

| field | anchor (x, baseline) | align | cap | longest |
| --- | --- | --- | --- | --- |
| away abbreviation | 216, 413 | left | 13 | 4 chars |
| away score | 280, 413 | centre | 16 | 3 digits |
| home score | 468, 413 | centre | 16 | 3 digits |
| home abbreviation | 532, 413 | right | 13 | 4 chars |
| down and distance | 374, 398 | centre | 11 | `4th & Inches` |
| quarter | 330, 421 | centre | 10 | `OT2` |
| game clock | 375, 421 | centre | 11 | `15:00` |
| play clock | 419, 421 | centre | 10 | `:40` |

Everything is white; the possession abbreviation keeps the retail yellow word. The
score flip animation pivots on the score cell centre (280, 404) and (468, 404). The
four auxiliary event strings (FLAG, FUMBLE, hang time, ball position) point at the
banner cell and replace the down text while shown; the two-line ball-position string
will overrun into the pill unless the formatter is changed. If the FONT objects cannot
scale to the listed cap heights, the cells were sized for the native 14 to 16 px
glyphs: each centre row is 20 px tall.

`preview_*.png` draw the text with Arial Bold as a stand-in. The game's face is its
own; expect the real thing to be a touch wider and squarer.

## How the studio compiles the folder

The compiler (being built from `scorebug-v10.md`) is expected to:

1. Read `layout.json`. Reject the folder with a plain message if any layer PNG is not
   476 x 48 (1x) or if a layer or team block exceeds 256 colours after its own
   reduction, or if a layer has pixels outside its `rect_bar`.
2. Take the layers in `packing_order` (also the draw order), crop each to its
   `rect_bar`, pack them into one P8 atlas (the tile spec is the suggested cut) and
   quantize to `palette_target`. `atlas/atlas_1x.png` + `atlas/atlas.json` are a
   worked example of exactly that.
3. Refit the atlas through the VC-LZ span with the retail wrapper `+0x14` unchanged
   (the v9 rule) and place the meshes: both frame copies (`yscore_buga` /
   `yscore_buga1`) at the frame `rect_hud`, both mark copies at the mark `rect_hud`,
   the score parents 23 / 26 at the block rects, the down tab collapsed with its text
   anchor moved to the banner, the play-clock / quarter / clock anchors moved to the
   pill. Timeout marks are drawn only when `enabled` is true.
4. Write the live-text anchors and colour words from `text` into the scene / XBE
   fields, contract nothing for widescreen (the wide hook does the 27/32 X contraction
   itself), and keep the v9 containment predicate green at 4:3 and wide.
5. Leave `teams/` alone in the static path (both blocks neutral), and hand the folder
   to the runtime job for per-team selection.

The static path today cannot pick a team block per matchup: the binder selects one
atlas for all 32 identities. `teams/` is delivered for the runtime owner, which
selects the away block through `zscore_buga` on parent 23 and the home block through
`hscore_buga` on parent 26 (`TEAM_MATERIAL_HOOK` in the v9 report). Each block is its
own texture and palette, so the pair adds no colours to the shared atlas.

## What was matched and what was not

`compare.png` puts this bar over the supplied `target_NO_MIA.png` crop and the static
v9 bar. Note that all four `target_*.png` files are labelled "TARGET WITH STAGED LOGOS /
FONT APPROXIMATION"; they are the staged mockup, not a broadcast capture. The layout
they encode (colour-graded team panels, big white scores, three dashes, red banner
over a clock strip) is the same as Noah's SVG master, so that lineage set the look:

* matched: bar size and rails, one-piece dark frame with a fine rim and top gloss,
  recessed red banner with rounded corners and highlight, rounded clock pill with
  dividers, team colour bands fading to dark before the text, three angled marks.
* deliberately different: the ESPN mark is in the left cell (game constraint) instead
  of a top-right watermark, so the away panel sits next to the mark rather than at the
  bar's end; the clock pill is dark with white text (the game writes white text, and
  the SVG master chose a dark strip) rather than the mockup's white strip; there are
  no team logos, only abbreviations, because the game draws those as text.
* not matched: the broadcast typeface. Live text is the game's own font; the preview
  uses Arial Bold. Timeouts are decorative until the runtime job binds them.

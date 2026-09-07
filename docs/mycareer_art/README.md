# MyCareer apartment hub art (Fable, 2026-09-07)

Authored art for the MyCareer hub ("the apartment"), to the native constraints in
`ASTRA_MYCAREER_MODE_DESIGN.md`, section "ASSET REQUEST LIST for the Fable art
agent". Nothing here is a game pixel: `build.py` draws every texture from scratch
(procedural plaster, a dusk skyline, flat-shaded props) and the two mockups compose
them the way the hub would. The Crib room materials named in the design were studied
for style only; see "Style sources" below.

```
build.py                    renders everything below, deterministically (seeded grain)
mycareer_apartment.png      512x512 RGBA hub background, opaque, 7 P8 mips in game
mycareer_panels.png         256x128 RGBA panel backing atlas, 5 mips
mycareer_calendar.png       128x128 RGBA calendar icon atlas, 5 mips
mycareer_focus.png          128x32 RGBA focus-row highlight, 1 mip (provisional)
hub_mockup_640x480.png      the composed hub at 4:3, for Noah to react to
hub_mockup_wide.png         the composed hub at 16:9 (side art, unstretched UI)
manifest.json               object, tile, icon and crop rectangles the checker verifies
art_check.json              the checker's report for the committed PNGs
previews/                   the P8 result at mip 0 and each full mip chain, per asset
```

Regenerate and verify:

```sh
python3 docs/mycareer_art/build.py                          # rewrites the PNGs and manifest.json
python3 tools/mycareer_art_check.py                         # JSON report, exit 1 on any failure
python3 tools/mycareer_art_check.py --reference             # pure-Python quantize_levels mapping (slower, same result)
python3 tools/mycareer_art_check.py --preview-dir docs/mycareer_art/previews --json docs/mycareer_art/art_check.json
python3 -m pytest tests/mod_editor/test_mycareer_art.py -q
```

Needs Pillow and numpy. The mockups use Arial Bold as the retail-font stand-in
(DejaVu Sans Bold if it is absent); the game's own face is squarer and a touch wider.

## Layout contract

Virtual UI is 640x480: content inside x 36..604, y 28..452; nine menu rows of 26 px at
x 44..302 from y 142; summary panel at x 332..596; controller footer at y 432.

* **4:3** shows the centred 512x384 crop of the texture (rows 64..448) at 0.8 texture
  px per UI unit. UI (x, y) lands on texture (0.8x, 64 + 0.8y). The menu column is
  therefore texture x 35..242, rows 178..365; the summary column x 266..477.
* **Wide** shows the centred 512x288 crop (rows 112..400) scaled 1.667x to 854x480,
  with the unstretched 640x480 UI centred on it (the wide hook contracts characters
  itself). The UI then covers texture x 90..422, so x 0..90 and 422..512 are side art.

The texture is composed for both: the hero band (jersey, window, drape, lamp) sits at
rows 112..300 to the right of the title; the left third is held in shadow for the menu
text; the floor band under the columns carries the gear; rows 0..64 and 448..512 are
never shown at 4:3 and only continue the ceiling and floor.

| object (texture px, half open) | rect | crop class |
| --- | --- | --- |
| window (dusk skyline, lit stadium) | 336,116 .. 466,276 | core |
| framed jersey (mahogany frame, black mat) | 250,112 .. 310,180 | core |
| sofa with a football | 262,292 .. 430,392 | core |
| television on a stand, dark corner | 10,246 .. 88,356 | core |
| floor gear (duffel, helmet, football, cleats) | 36,352 .. 264,400 | core |
| side table with a plant | 438,268 .. 480,356 | core |
| drape (one panel, pulled left) | 316,98 .. 332,302 | accent |
| pop-art helmet canvas | 474,106 .. 510,156 | accent (clipped at 4:3's right edge) |
| floor lamp (the warm key light) | 476,160 .. 514,374 | accent (pole runs past the wide crop) |

"Core" objects must sit inside the wide crop and the 4:3 crop; the checker enforces it.

## Native results

All four textures decode through the repo's strict PNG reader, are non-interlaced 8-bit
RGBA, build their full mip chain with the same round-half-up RGBA box rule as the
Crib and live-helmet importers, and quantize to one shared palette with the repo's
median cut over the whole chain (`nfl_tset_png_import.median_cut_palette`, 1,024
palette bytes, BGRA). The vectorised index mapping in the checker is proved
byte-identical to `quantize_levels` by the test; `--reference` runs the original.

| asset | mips (index bytes) | chain colours | palette entries | max / p99.5 channel error | RMS |
| --- | --- | ---: | ---: | --- | ---: |
| mycareer_apartment.png | 512,256,128,64,32,16,8 (349,504) | 31,410 | 254 | 43 / 21 | 2.99 |
| mycareer_panels.png | 256x128 .. 16x8 (43,648) | 436 | 256 | 2 / 1 | 0.19 |
| mycareer_calendar.png | 128 .. 8 (21,824) | 478 | 256 | 12 / 7 | 0.56 |
| mycareer_focus.png | 128x32 (4,096) | 33 | 33 | 0 / 0 | 0.00 |

The apartment's worst single-pixel errors are anti-aliased edges where cool and warm
hues meet (window mullions, the jersey frame's inner edge); 99.5% of chain pixels are
within 21 levels. Banding is measured as the difference between the 7x7 box-blurred
luma of the original and of the P8 result inside the smooth regions (a hard 20-level
band reads as about 10 here): sky 5.0 max / 4.0 p99, wall 2.0 / 1.0, floor 3.0 / 2.0,
limits 8 / 6. The dusk gradient carries a sigma 6 grain on purpose: without it the
shared palette gives the sky about ten entries and the gradient steps visibly
(measured 13 / 5); with it the steps dissolve into a photographic grain like the
Crib's own skybox.

Calm zones for the runtime text (4:3 mapping): menu column mean luma 85 (limit 96),
99th percentile 161 (limit 170), mean gradient 2.6 (limit 7); summary column mean
gradient 6.3 (limit 12); footer band mean luma 45, gradient 2.8.

## Panel atlas

Tiles are 9-slice friendly: corners and edges keep their pixels, the middle stretches.
Padding between tiles is at least 4 px and stays fully transparent.

| tile | rect | kind | 9-slice inset | use |
| --- | --- | --- | ---: | --- |
| summary_opaque | 4,4 .. 132,100 | opaque navy card, red accent bar, top rule | 12 | player summary |
| opponent_translucent | 140,4 .. 252,60 | alpha 176 navy, 1 px border | 8 | next opponent / calendar strip |
| balance_translucent | 140,68 .. 252,116 | alpha 168 warm dark, gold bottom rule | 8 | upgrade balance |
| ribbon_translucent | 4,108 .. 132,124 | alpha 140 black ribbon | 4 | footer / row separators |

## Calendar atlas

32 px cells on a 4x4 grid, 3 px transparent margin inside each cell, dark keyline on
every glyph so it reads on any background. Each icon is a distinct silhouette; the
checker refuses any pair whose alpha masks overlap more than IoU 0.80 (worst pair is
played/request at 0.76).

| icon | cell | shape |
| --- | --- | --- |
| played | 0,0 .. 32,32 | filled circle with a check mark |
| upcoming | 32,0 .. 64,32 | tilted football with laces |
| bye | 64,0 .. 96,32 | bold rounded dash |
| practice | 96,0 .. 128,32 | striped cone |
| request | 0,32 .. 32,64 | envelope |
| current | 32,32 .. 64,64 | hollow ring, drawn around the current week's icon |
| milestone | 64,32 .. 96,64 | five-point star |

## Focus row

Red-orange gradient fill with a lighter centre band, a 2 px gold rim and a 1 px dark
keyline inside it, rounded ends. Columns 12..116 are identical, so the row can be
stretched to any width (the mockup stretches it to 258x26) without distortion; keep
the end caps at their native size if the native template allows a 9-slice. One mip is
authored because the asset request asks for one; if the slot Astra assigns needs more,
the checker's `SPECS` entry is the only place to change and the chain will regenerate.

## Style sources (looked at, not copied)

`crib_scene_texture:room:2` (plaster wall and ceiling), `room:22` (bar monitor),
`room:31` and `room:32` (ESPN and Crib screens), `room:37` and `room:38` (pop-art
football paintings), `crib_scene_texture:skybox_day:0` and `skybox_night:0` (the
skyline), `framed_jersey:0` (the mahogany frame). The apartment borrows their
vocabulary: grey plaster warmed by a lamp, a dark CRT with its screen off, a framed
shirt in a red-brown frame with a black mat, a small flat-colour pop-art canvas, and a
purple dusk over a skyline with lit windows. Every pixel is drawn by `build.py`.

## Mockups

Both mockups use placeholder strings (a fictional rookie, MARCUS REED, QB #12, and a
week-3 fixture) in the retail-font stand-in, the panel tiles 9-sliced to size, the
calendar icons at 20 px in the opponent tile, and the focus row on the first menu
row. The game draws its own font and strings; the mockups show placement and look only.

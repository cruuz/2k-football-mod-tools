# MyCareer apartment hub art (Fable, 2026-09-07)

Art for the MyCareer hub ("the apartment"), to the native constraints in
`ASTRA_MYCAREER_MODE_DESIGN.md`, section "ASSET REQUEST LIST for the Fable art
agent". The backdrop is a real ESPN NFL 2K5 texture, the skyline the Crib's windows
look out on, recomposed for the hub slot. The three atlases are drawn by `build.py`.

```
build.py                        renders the atlases, composes the backdrop and mockups, writes manifest.json
backdrop_recipe.json            THE BACKDROP: which game texture, where it sits, how it is continued and shaded
backdrop_recipe_alt_day.json    review alternate, the same view by day
backdrop_recipe_alt_framed.json review alternate, the skyline framed in the Crib's plaster and mahogany
mycareer_panels.png             256x128 RGBA panel backing atlas, 5 mips (committed)
mycareer_calendar.png           128x128 RGBA calendar icon atlas, 5 mips (committed)
mycareer_focus.png              128x32 RGBA focus-row highlight, 1 mip, provisional (committed)
mycareer_apartment.png          512x512 RGBA backdrop, 7 P8 mips in game (LOCAL, composed from your disc)
hub_mockup_640x480.png          the composed hub at 4:3 (LOCAL)
hub_mockup_wide.png             the composed hub at 16:9, side art, unstretched UI (LOCAL)
manifest.json                   layer, tile, icon and crop rectangles plus backdrop provenance
art_check.json                  the checker's report for the current files
previews/                       the P8 result at mip 0 and each mip chain (apartment previews LOCAL)
```

LOCAL means composed on your machine and ignored by git: this repository carries no
retail pixels, only the recipe and the Studio's own decoder path.

Regenerate and verify:

```sh
python3 docs/mycareer_art/build.py                          # atlases + backdrop + mockups (needs the source cache)
python3 docs/mycareer_art/build.py --recipe docs/mycareer_art/backdrop_recipe_alt_framed.json --out /tmp/framed
python3 tools/mycareer_art_check.py                         # JSON report, exit 1 on any failure
python3 tools/mycareer_art_check.py --reference             # pure-Python quantize_levels mapping (slower, same result)
python3 tools/mycareer_art_check.py --preview-dir docs/mycareer_art/previews --json docs/mycareer_art/art_check.json
python3 -m pytest tests/mod_editor/test_mycareer_art.py -q
```

The backdrop needs the Studio's private source cache for your disc (open the XISO in
Mod Studio once, or point `NFL2K5_SOURCE_CACHE_ROOT` at it). Without it `build.py`
still renders the atlases and says so; the backdrop tests skip. Needs Pillow and numpy;
the mockups use Arial Bold as the retail-font stand-in (DejaVu Sans Bold if absent).

## The backdrop

`crib_scene_texture:skybox_night:0` (asset `nfl2k5.crib.scene.c0006.t000`, 512x256 P8,
six mips, outer package 4248) is the night skyline the Crib's windows look out on, a
photograph of San Francisco with lit windows and a purple dusk sky. It is decoded from
your disc through `mod_editor.core.nfl2k5_crib.Nfl2k5CribIO`, which checks the pixels
against the catalog's pinned hash, and composed by `build.py` from the recipe:

* placed at native scale in texture rows 112..368 (the whole width), so it fills the
  wide crop's centre and sits centred in the 4:3 crop;
* continued above (rows 0..112) and below (368..512) with its own edge rows, blurred
  along x and eased toward near black (`extend`): the sky simply darkens upward, the
  band under the window reads as shadow, and the footer sits on plain dark;
* the left third held in shadow (`shade`: 0.30 at the left edge easing to 1.0 by
  x 330) so white menu text reads over the lit windows;
* sigma 1.0 grain, which the photograph mostly supplies already.

No pixel is drawn. The recipe carries the selector, the asset id, the rectangle and
these three treatments; `manifest.json` records the same provenance after each build.

Why this asset: no pre-rendered room or menu backdrop exists in the game. A census of
all 57,208 TXTR chunks by video size found no 512x512 multi-mip texture at all, and the
six 512x512 single-mip ones are the air hockey, dart and paper football text atlases
and the VIP registration screen. Decoding every TXTR-headed package (1,023 of them)
and viewing every texture 256x192 or larger found team logos, the coach's office
wall-photo and diploma atlases, player heads, number sheets and the ESPN shield.
The Crib's own textures are materials (plaster, wood, bar counter, paintings,
screens) plus the two skyboxes; the skybox is the only full-frame photographic still
with a room meaning, and it is exactly the old Crib view Noah asked for.

## Layout contract

Virtual UI is 640x480: content inside x 36..604, y 28..452; nine menu rows of 26 px at
x 44..302 from y 142; summary panel at x 332..596; controller footer at y 432.

* **4:3** shows the centred 512x384 crop of the texture (rows 64..448) at 0.8 texture
  px per UI unit. UI (x, y) lands on texture (0.8x, 64 + 0.8y). The menu column is
  therefore texture x 35..242, rows 178..365; the summary column x 266..477.
* **Wide** shows the centred 512x288 crop (rows 112..400) scaled 1.667x to 854x480,
  with the unstretched 640x480 UI centred on it (the wide hook contracts characters
  itself). The UI then covers texture x 90..422, so x 0..90 and 422..512 are side art.

The skyline layer (rows 112..368) is the one core object; the checker requires it inside
both crops. Rows 0..64 and 448..512 are never shown at 4:3 and only continue sky and
shadow.

## Native results

All four textures decode through the repo's strict PNG reader, are non-interlaced 8-bit
RGBA, build their full mip chain with the same round-half-up RGBA box rule as the
Crib and live-helmet importers, and quantize to one shared palette with the repo's
median cut over the whole chain (`nfl_tset_png_import.median_cut_palette`, 1,024
palette bytes, BGRA). The vectorised index mapping in the checker is proved
byte-identical to `quantize_levels` by the test; `--reference` runs the original.

| asset | mips (index bytes) | chain colours | palette entries | max / p99.5 channel error | RMS |
| --- | --- | ---: | ---: | --- | ---: |
| mycareer_apartment.png (night skyline) | 512..8, 7 levels (349,504) | 21,548 | 256 | 12 / 6 | 1.44 |
| mycareer_panels.png | 256x128 .. 16x8 (43,648) | 436 | 256 | 2 / 1 | 0.19 |
| mycareer_calendar.png | 128 .. 8 (21,824) | 478 | 256 | 12 / 7 | 0.56 |
| mycareer_focus.png | 128x32 (4,096) | 33 | 33 | 0 / 0 | 0.00 |

Banding is measured as the difference between the 7x7 box-blurred luma of the original
and of the P8 result inside the smooth regions (a hard 20-level band reads as about
10): sky 2.0 max / 1.0 p99, top extension 2.0 / 1.0, bottom extension 2.0 / 1.0,
limits 8 / 6. The photograph's own grain is why a 256-entry palette holds it so well.

Calm zones for the runtime text (4:3 mapping): menu column mean luma 22 (limit 96),
99th percentile 70 (limit 170), mean gradient 8.1 (limit 9); summary column mean
gradient 14.0 (limit 16, it sits under an opaque card and tiles of at least 65%
opacity); footer band mean luma 3, gradient 1.5.

## Panel atlas

Tiles are 9-slice friendly: corners and edges keep their pixels, the middle stretches.
Padding between tiles is at least 4 px and stays fully transparent.

| tile | rect | kind | 9-slice inset | use |
| --- | --- | --- | ---: | --- |
| summary_opaque | 4,4 .. 132,100 | opaque navy card, red accent bar, top rule | 12 | player summary |
| opponent_translucent | 140,4 .. 252,60 | alpha 176 navy, 1 px border | 8 | next opponent / calendar strip |
| balance_translucent | 140,68 .. 252,116 | alpha 168 warm dark, gold bottom rule | 8 | upgrade balance |
| ribbon_translucent | 4,108 .. 132,124 | alpha 140 black ribbon | 4 | footer / row separators, or a menu backing |

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

## Alternates

Two more recipes exist for Noah to compare, built with
`build.py --recipe ... --out <folder> --mockup-prefix alt_...`. They are not the
deliverable and do not pass the strict calm-column limits: the day skyline is too
bright for white text even shaded, and the framed variant (the skyline seen through a
window in the Crib's own plaster wall, `room:2` tiled, with the Crib's mahogany frame
material `framed_jersey:0` nine-sliced as the frame) is a little busier under the menu
than the limit allows. Both use real textures only.

## Mockups

Both mockups use placeholder strings (a fictional rookie, MARCUS REED, QB #12, and a
week-3 fixture) in the retail-font stand-in, the panel tiles 9-sliced to size, the
calendar icons at 20 px in the opponent tile, and the focus row on the first menu
row. The game draws its own font and strings; the mockups show placement and look only.

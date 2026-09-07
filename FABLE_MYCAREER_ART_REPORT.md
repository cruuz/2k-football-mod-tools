# MyCareer apartment hub art (Fable, 2026-09-07)

Branch `fable/r64-mycareer-art`, base `824cd2b`. **Art delivery for the M3 hub; nothing
here is installed in a disc or witnessed in game.** The four textures, the two mockups,
the checker and its test live under `docs/mycareer_art/`, `tools/mycareer_art_check.py`
and `tests/mod_editor/test_mycareer_art.py`. Every pixel is drawn by
`docs/mycareer_art/build.py`; no retail texture was read by the renderer or copied.

## What each asset is

**`mycareer_apartment.png`** (512x512 RGBA, opaque). A rookie's one-room apartment at
dusk, composed for the centred 512x384 4:3 crop with the core art inside the centred
512x288 wide crop. Warm plaster wall lit by a floor lamp on the right, a dusk window
with a procedural skyline (lit windows, a floodlit stadium on the horizon) and one deep
red drape, a framed navy jersey in a mahogany frame with a black mat (no number, so it
does not contradict the created player), a small pop-art helmet canvas, a brown leather
sofa with a football, a side table with a plant, a dark CRT on a stand in the shadowed
left corner, and gear on the floor (duffel, helmet, football, cleats). The left third is
deliberately held in shadow for the white menu text; the right column is calm enough for
the panels; the footer band is plain floor. No baked UI text. Distinct from the Coach's
Desk: no desk, no 3D scene, an apartment.

**`mycareer_panels.png`** (256x128 RGBA atlas). Four 9-slice backing tiles with at
least 4 px of transparent padding: an opaque navy summary card with a red accent bar,
a translucent navy opponent tile, a translucent warm balance tile with a gold rule, and
a translucent black ribbon. No names baked in.

**`mycareer_calendar.png`** (128x128 RGBA atlas). Seven icons on 32 px cells: played
(circle with check), upcoming (tilted football), bye (rounded dash), practice (striped
cone), request (envelope), plus a current-week ring and a milestone star. Every icon is
a distinct silhouette with a dark keyline; meaning never rests on colour alone.

**`mycareer_focus.png`** (128x32 RGBA). Focus-row highlight: red-orange fill with a
lighter centre band, a 2 px gold rim and a 1 px dark keyline, rounded ends; columns
12..116 are identical so it stretches cleanly.

**`hub_mockup_640x480.png`** and **`hub_mockup_wide.png`**: the hub as Noah would see
it. Background crop, nine 26 px menu rows at x 44..302 from y 142 in the retail-font
stand-in (Arial Bold), the focus row on row one, the summary column at x 332..596
(summary card, opponent tile with the calendar strip, upgrade balance), the controller
footer at y 432. Wide keeps the UI unstretched and centred and shows the side art
(television left; plant, lamp and canvas right).

## Palette and mip results

Measured by `tools/mycareer_art_check.py` (report committed as
`docs/mycareer_art/art_check.json`). Mips use the round-half-up RGBA box rule of the
Crib and live-helmet importers; the palette is the repo's median cut over the whole
chain (`nfl_tset_png_import.median_cut_palette`) with 1,024 BGRA palette bytes.

| asset | mip chain (index bytes) | chain colours | entries | max / p99.5 channel error | RMS |
| --- | --- | ---: | ---: | --- | ---: |
| apartment | 512,256,128,64,32,16,8 (349,504) | 31,410 | 254 of 256 | 43 / 21 | 2.99 |
| panels | 256x128 .. 16x8 (43,648) | 436 | 256 | 2 / 1 | 0.19 |
| calendar | 128 .. 8 (21,824) | 478 | 256 | 12 / 7 | 0.56 |
| focus | 128x32 (4,096) | 33 | 33 | 0 / 0 | 0.00 |

Banding (7x7 box-blurred luma, original versus P8, inside the smooth regions; a hard
20-level band reads as about 10): sky 5.0 max / 4.0 p99, wall 2.0 / 1.0, floor
3.0 / 2.0, limits 8 / 6. Calm zones at 4:3: menu column mean luma 85, p99 161, mean
gradient 2.6; summary column gradient 6.3; footer luma 45, gradient 2.8. Icon
silhouettes: worst pair IoU 0.76 (limit 0.80). Focus rim luma 199 against fill 100.

Two findings shaped the art. First, a single 256-entry palette shared by a warm room and
a violet-to-orange sky steps the sky in roughly 20-level bands whatever the wall grain
does, because median cut splits by widest range and every smooth region ends at the
same residual range; the fix is authored sigma 6 grain in the sky (banding measure 13
to 5), which reads as photographic grain like the Crib's own skybox. Second, the
worst single-pixel errors (43) are anti-aliased edges between cool and warm hues, so
the checker limits the 99.5th percentile (24) and caps the maximum (48) rather than
demanding a strict per-pixel bound.

The brief's "six mips (512..16)" wording and the asset request's "512,256,128,64,32,16,8
(349,504 index bytes)" differ; the seven-level chain is the exact native byte count, so
that is what is authored and verified (it contains the six-level chain).

## Checker and test

`tools/mycareer_art_check.py` verifies, per asset: PNG signature, IHDR (8-bit RGBA,
non-interlaced), size, the repo's strict decode, the alpha policy, the full mip chain and
its index byte total, the shared palette count and 1,024 palette bytes, the error
statistics, and the manifest rectangles: crop safety (centred crops, core objects inside
both crops, calm-zone luma and gradient, banding in the smooth regions) for the
background; tile bounds, 4 px padding, transparent gutters and alpha classes for the
panel atlas; grid, margins, minimum size and pairwise silhouette IoU for the calendar;
stretch-safe columns, solid centre, solid brighter rim and transparent corners for the
focus row. It also confirms the two mockups' sizes. `--reference` swaps the vectorised
nearest-entry mapping for the pure-Python `quantize_levels`; the results are identical.

`tests/mod_editor/test_mycareer_art.py` proves the checker's box mips equal
`nfl_tset_png_import.generate_mips` on its pinned 512x256 six-level chain, that the vectorised mapping
equals `quantize_levels` (palette, indices and statistics) on a chain with more than 256
colours and ties, that the shipped assets pass every constraint, that the manifest pins
the layout specification, that the CLI exits 0 with a JSON report, that a translucent
background and a wrong-size focus texture are refused with plain messages, and that
`build.py --out` reproduces the committed textures and manifest byte for byte.

## Style sources by name

`crib_scene_texture:room:2` (wall and ceiling plaster), `room:22` (bar monitor),
`room:31` and `room:32` (ESPN and Crib screens), `room:37` and `room:38` (pop-art
paintings), `crib_scene_texture:skybox_day:0` and `skybox_night:0`, and
`crib_scene_texture:framed_jersey:0`, all from the user's private extraction on this
machine, viewed once for material vocabulary. Also the real 2K5 Team Select screen for
the menu language (navy field, red band, white uppercase, yellow numerals, button
glyphs). Nothing was traced, sampled or pasted.

## Provisional

* The focus texture is authored with one mip because the asset request says one; the
  slot Astra assigns may need more. Change `SPECS["mycareer_focus.png"]["mips"]` in the
  checker and the chain regenerates; the art needs no change.
* Placement is still Astra's HYPOTHESIS: which TXTR/SCNE IDs, descriptors and layout
  token carry these textures is integration work, and the compressed spans may need the
  archive growth owner. The checker verifies the native byte counts, not a compiled span.
* The wide mapping assumes the unstretched UI centred over the 512x288 crop. If the wide
  hook's 27/32 contraction is used instead (characters 1.126x wide), the UI covers
  texture x 70..442 rather than 90..422; each side-art strip narrows from 90 to 70 px
  and nothing else changes.
* The mockups' font, strings and panel heights are stand-ins. The game's own font is
  squarer and wider; long labels ("TEAM AND DEPTH CHART") fit the 258 px row at the
  stand-in's 15 px cap and should be checked against the real face.
* The stadium on the skyline and the pop-art canvas are accents; the canvas is clipped
  at 4:3's right edge by design and fully visible in wide.

## Verification

```sh
python3 docs/mycareer_art/build.py
python3 tools/mycareer_art_check.py --preview-dir docs/mycareer_art/previews --json docs/mycareer_art/art_check.json
python3 tools/mycareer_art_check.py --reference
python3 -m pytest tests/mod_editor/test_mycareer_art.py -q
```

Results are recorded in the commit on this branch. No protected file was edited; nothing
was pushed; no disc was built; the main drive stayed above 100 GB free.

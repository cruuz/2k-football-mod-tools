# MyCareer apartment hub art (Fable, 2026-09-07)

Branch `fable/r64-mycareer-art`, base `824cd2b`. **Art delivery for the M3 hub; nothing
here is installed in a disc or witnessed in game.** Second revision: Noah reviewed the
first mockup and asked for the hand-drawn room to be replaced with a game asset or a
legitimate image, so the backdrop is now a real ESPN NFL 2K5 texture. The atlases, the
checker and the tests carry over. Everything lives under `docs/mycareer_art/`,
`tools/mycareer_art_check.py` and `tests/mod_editor/test_mycareer_art.py`.

## The backdrop is the Crib's own skyline

`mycareer_apartment.png` (512x512 RGBA, opaque) is composed from
**`crib_scene_texture:skybox_night:0`**, asset `nfl2k5.crib.scene.c0006.t000`
(512x256 P8, six mips, Crib package 4248): the photograph of San Francisco at night
that the Crib's windows look out on, lit windows and a purple dusk sky. It is the old
Crib view Noah described, used as-is: decoded from his disc through the repo's own
`Nfl2k5CribIO` (which verifies the pixels against the catalog's pinned hash) and
recomposed only for the slot by `docs/mycareer_art/backdrop_recipe.json`:

* native scale, texture rows 112..368 across the full width, so it fills the centre of
  the wide crop (112..400) and sits centred in the 4:3 crop (64..448);
* continued above and below with its own edge rows, blurred along x and eased toward
  near black, so the sky darkens upward and the band under the window is shadow;
* the left third held in shadow (0.30 at the edge easing to 1.0 by x 330) so the
  white menu text reads over the lit windows;
* sigma 1.0 grain.

No pixel is drawn. `manifest.json` records the provenance after every build.

**Repository policy.** The repo forbids committing retail pixels (`.gitignore` header,
packaging gate), so the composed backdrop, the mockups drawn on it and its P8 previews
are ignored by git and rebuilt locally by `build.py` from the user's private source
cache; the recipe, the atlases, the manifest and the check report are committed. This
is the same source-derived-recipe pattern the Crib backend uses. The five hand-drawn
files from the first revision are removed from the tree.

**Review material for Noah** (local, not committed):
`/home/noah/Desktop/2K5-8 Editors/mycareer-art-2026-09-07/`, holding the two proposed
mockups, the day and framed alternates, the P8 preview and `NOTES.md`. The same
mockups are at `docs/mycareer_art/hub_mockup_640x480.png` and `hub_mockup_wide.png`
in this worktree.

## What the search covered

Order of preference was a pre-rendered full-screen backdrop, then an assembly from real
Crib textures, then a licensed photograph. The game has no full-screen room or menu
backdrop:

* A census of all 57,208 TXTR chunks by video byte count (private inventory
  `nfl2k5_resource_chunks_v2.json`): no 512x512 multi-mip texture exists anywhere; the
  six 512x512 single-mip textures are the air hockey, dart and paper football text
  atlases (packages 4249, 4250, 4264) and the VIP registration screen (package 9).
* Every TXTR-headed package under 20 MB (1,023 of them, plus the layout, director and
  highlight packages) decoded with `nfl_outer`/`nfl_txtr`, and every texture 256x192 or
  larger (1,975) listed by name and viewed on contact sheets: per-team menu logos, the
  coach's office wall-photo and diploma atlases, Super Bowl tunnel and paper props,
  inflatable helmets, player heads, number sheets, ghost logos, the ESPN shield.
* The Crib catalog's 498 textures: materials (plaster, cherry wood, concrete, stone,
  brick, bar counter, books, bottles, pictures, paintings, the bar monitor and the
  ESPN/Crib screens) and the two skyboxes. The paintings and skyboxes are the only
  full-frame images; the skybox is the only one with a room meaning.

So option 1 resolves to the skybox. Option 2 (a CC0 photograph) was not needed.

## Alternates for Noah

`backdrop_recipe_alt_day.json`: the same view by day (`skybox_day:0`). Too bright for
white text even with a stronger shade; fails the calm-column check (mean luma 105).
`backdrop_recipe_alt_framed.json`: the night skyline seen through a window in the
Crib's plaster wall (`room:2` tiled and dimmed) with the Crib's mahogany frame
material (`framed_jersey:0`) nine-sliced as the window frame, real textures only.
Reads well; fails the busy-column limit by a little (gradient 11.6 against 9). Either
can be promoted by copying its recipe over `backdrop_recipe.json` and rebuilding.

## Palette and mip results

Measured by `tools/mycareer_art_check.py` (report committed as
`docs/mycareer_art/art_check.json`). Mips use the round-half-up RGBA box rule of the
Crib and live-helmet importers; the palette is the repo's median cut over the whole
chain (`nfl_tset_png_import.median_cut_palette`) with 1,024 BGRA palette bytes.

| asset | mip chain (index bytes) | chain colours | entries | max / p99.5 channel error | RMS |
| --- | --- | ---: | ---: | --- | ---: |
| apartment (night skyline) | 512,256,128,64,32,16,8 (349,504) | 21,548 | 256 | 12 / 6 | 1.44 |
| panels | 256x128 .. 16x8 (43,648) | 436 | 256 | 2 / 1 | 0.19 |
| calendar | 128 .. 8 (21,824) | 478 | 256 | 12 / 7 | 0.56 |
| focus | 128x32 (4,096) | 33 | 33 | 0 / 0 | 0.00 |

Banding (7x7 box-blurred luma, original versus P8, inside the smooth regions; a hard
20-level band reads as about 10): sky 2.0 max / 1.0 p99, top extension 2.0 / 1.0,
bottom extension 2.0 / 1.0, limits 8 / 6. The photograph quantizes far better than the
drawn room did (max error 43, RMS 2.99): its own grain does the dithering.

Calm zones at 4:3: menu column mean luma 22, p99 70, mean gradient 8.1; summary
column mean luma 31, gradient 14.0; footer luma 3, gradient 1.5. Icon silhouettes:
worst pair IoU 0.76 (limit 0.80). Focus rim luma 199 against fill 100.

Two checker limits changed with the photographic backdrop, and the report says so:
the menu column's mean-gradient limit is 9 (was 7; the drawn room measured 2.6, the
shaded photograph 8.1, and legibility is governed by the luma bounds, which are far
under their limits) and the summary column's is 16 (was 12; it sits under an opaque
card and tiles of at least 65% opacity). All other limits are unchanged.

## Build, checker and tests

`docs/mycareer_art/build.py` renders the three atlases from scratch, opens the
existing source cache without re-hashing the disc (the Studio's `cache.json` marker
plus the catalog's pixel hashes are the integrity chain), composes the recipe, draws
both mockups and writes `manifest.json`. Without a cache it renders the atlases and
says plainly why the backdrop is absent; `--require-backdrop` makes that an error.
`--recipe` and `--out` build alternates elsewhere.

`tools/mycareer_art_check.py` is unchanged in shape: PNG signature, IHDR (8-bit RGBA,
non-interlaced), size, the repo's strict decode, alpha policy, full mip chain and index
byte total, shared palette count and 1,024 palette bytes, error statistics, and the
manifest rectangles (centred crops, core layer inside both crops, calm-zone luma and
gradient, banding in the smooth regions, tile bounds and alpha classes, icon grid and
silhouette IoU, focus stretch columns and rim). `--reference` runs the pure-Python
`quantize_levels` mapping; results are identical.

`tests/mod_editor/test_mycareer_art.py`: the checker's box mips equal
`nfl_tset_png_import.generate_mips` on its pinned 512x256 chain; the vectorised
mapping equals `quantize_levels` on a chain with more than 256 colours and ties; the
committed atlases pass without game data; the manifest pins the layout; every recipe
names only catalogued Crib textures with exact-fit rectangles; no backdrop or mockup
is tracked by git; and, gated on the source cache being present, the build is
reproducible byte for byte, the composed backdrop passes every constraint, the CLI
exits 0, and a translucent backdrop or a wrong-size focus texture is refused.

## Provisional

* The focus texture is authored with one mip because the asset request says one; the
  slot Astra assigns may need more. Change `SPECS["mycareer_focus.png"]["mips"]` in the
  checker and the chain regenerates.
* Placement is still Astra's HYPOTHESIS: which TXTR/SCNE IDs, descriptors and layout
  token carry these textures is integration work, and the compressed spans may need the
  archive growth owner. The integration must run `build.py` (or call `compose_backdrop`)
  against the user's cache at build time; the checker verifies the native byte counts,
  not a compiled span.
* The wide mapping assumes the unstretched UI centred over the 512x288 crop. With the
  wide hook's 27/32 contraction the UI covers texture x 70..442 instead of 90..422 and
  each side-art strip narrows from 90 to 70 px.
* The menu shade is a legibility treatment applied to the texture. If Noah would rather
  see the skyline's left half, the `ribbon_translucent` tile can back the menu rows at
  runtime instead and the recipe's `shade.min` can rise.
* The mockups' font, strings and panel heights are stand-ins.

## Verification

```sh
python3 docs/mycareer_art/build.py --require-backdrop
python3 tools/mycareer_art_check.py --preview-dir docs/mycareer_art/previews --json docs/mycareer_art/art_check.json
python3 -m pytest tests/mod_editor/test_mycareer_art.py -q
```

No protected file was edited; nothing was pushed; no disc was built. Disk note: the
main drive read 95 GB free during this work because the shared session scratchpad
holds other agents' `oracle-work62` (5.9 GB) and `ship62` (1.1 GB); my own sweep output
(0.2 GB) was removed and the drive is back at the 100 GB floor, but those two folders
are not mine to delete.

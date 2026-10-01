PROVED OFFLINE: this catalog contains 83 residual sponsor items on one home atlas, 19 special slots and SoFi's neutral s40. It contains no generated fan art, player selection, roster input, or event-field identity. The fourteen board-kit venues listed in `design.json` are excluded.

PROVED OFFLINE: `nfl2k5_model_fan_art.py` reads the build's existing u4 art root. Twelve model writers use that shared final texture step for 13 venues. It reuses u4's manifest validation, rectangles, masters, weather composition, mip generation and P8 quantizer. No u4 PNG is copied into this catalog. Base model pins stay unchanged; the build receipt pins each composed model stretch against its original pinned parent.

PROVED OFFLINE: `design.json` records sponsor sizes, source RGBA hashes, replacement rectangles, type and installed font hashes. `venues/*/manifest.json` pins the native PNG and 4x master. Authored images are transparent outside reviewed rectangles. The venue-art pass composes them after the team's existing art. Whole-texture P8 quantization can slightly change colors outside a rectangle; unrelated texture allocations and geometry stay unchanged.

DESIGN: sponsor words follow u4's approved sections 4c and 10d: MOTOROLA to NFL NETWORK; Reebok to PLAY 60 (NFL+ in rows of three); ESPN VIDEOGAMES and ESPN THE MAGAZINE to ESPN; Visual Concepts to NFL+; PLAYERS INC to NFLPA; PLAY FOOTBALL to NFL FLAG. The approved corporate cloth policy also replaces TEAM NFL, Coaches Association and SEGA. Existing Riddell, Gatorade, Wilson, ESPN, SportsCenter and ESPN Radio panels are retained.

PROVED OFFLINE: st3's logo sweep adds 23 items for logo-only cells that the OCR list could not read: the Motorola batwing, the Reebok vector, the Players Inc mark, the ESPN VIDEOGAMES and ESPN THE MAGAZINE lockups and the Visual Concepts logo, on 15 special slots. The s36 wall decals sit on a see-through texture over the wall band, so their rows take `bg: clear`: the rectangle turns transparent, keeps the colour retail stores under alpha 0 so filtered edges fringe to the wall, and the type is cut out on it. An empty text with `clear` removes a mark.

PROVED OFFLINE: SoFi's neutral s40 keeps the retail cloth atlas, and its ESPN VIDEOGAMES cloth takes the same ESPN item as s42 and s55. The venue-art pass never writes s40, so `MODEL_NEUTRAL` routes the item through the model fan step instead. `nfl2k5_model_fan_art.neutral_plan` plans it on the retail dry-day texture, and `paint_bundle` paints it on the finished SoFi model inside each s40 bundle's stadium span, under the same art-root switch as club fan art. SoFi's geometry and model pins are unchanged. The composed stretch is accepted through its build receipt, as club fan art is.

PROVED OFFLINE: the one home residual is Chicago's small ESPN publishing panels outside u4's sponsor rectangles. The top of Cincinnati's Reebok vector above u4's rectangle moved to u4's venue table (st3, job/b76-st7b 6b9c5d4b, the same PNG, over the team's art) when tier 3 put Paycor Stadium on the board kit. Baltimore, Detroit, Philadelphia and Tennessee candidates already repainted by u4 receive no new items. All remaining catalog items serve special/event/created-team slots without a u4 club manifest.

DESIGN: regenerate only with the same pinned retail source textures and installed fonts:

```sh
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
python3 tools/nfl2k5_residual_sponsor_art.py \
  --retail '/path/to/extracted/ESPN NFL 2K5 (USA)' \
  --review '/path/to/review'
python3 fb/catalog_art.py
```

PROVED OFFLINE: the generator uses installed Roboto Black and Roboto Condensed Bold through u4's existing authoring helpers. No fonts or untouched retail image regions are distributed. `special_venues.json` carries selectors and SHA-256s for all nine variants of each special slot; it adds no field or league-mark target.

DESIGN: run `fb/run_checks.sh`, `fb/prove_fans.py` and `fb/prove_sponsors.py` in the private job environment to reproduce the tests, byte comparisons and review sheets. These scripts use one process under a 1.8 GiB virtual-memory cap when launched by the documented job commands. Do not regenerate any base model pin for this change. Main must regenerate the candidate cave reservation manifest after integration because its tracked source files change.

# Allegiant Stadium (experimental)

Build option `modern_allegiant`, off in every preset. It writes the Las Vegas Raiders' Allegiant Stadium (Paradise, NV,
opened 2020; MANICA and HNTB) into the Raiders' venue record s20 (retail Network Associates Coliseum, Oakland), all nine
bundles (day, afternoon and night; dry, rain and snow), and names the s20 row Allegiant Stadium.

## What it writes

- **The stadium scene**, built from scratch with the static SCNE builder (`mod_editor/core/nfl2k5_scne_builder.py`):
  the charcoal bowl in four stacks, its heights measured on three solved photo poses (the 2022 Las Vegas Bowl from the
  south stand, 7 field and goalpost points at 2.4 px; the 2021 Kickoff Classic from the north end and from the
  south-west corner): the lower bowl's ribbon at 16 to 17 m, the north club tier's top at 25.6 m (the lanai deck), the
  side upper decks up to about 57 m, the south end's shallow upper section under the board. Crowd billboards in the
  retail convention, cut at every aisle, and the ribbons on the fascias.
- **The roof**: the fixed ETFE roof over the whole building, its dark steel ring from 60 m at the outline to 66 m (the
  floodlights hang on its inner edge), the ETFE dome to 72 m.
- **The lanai** at the north end: the curved glass on the drum's north face from the deck to 46.1 m with the Strip's
  towers beyond it, the black header with the name up to the roof's ring, the deck and its side walls, and the Al Davis
  memorial torch (its top 39.6 m, from the 2022 photo).
- **The boards** on the `jumbo_tron` material the game draws its live feed into (a crop of the feed at the picture's own
  aspect, never stretched): the south primary board between its stat panels (the game's digits on them) with the name
  over it, and the two north boards over the corner seats, triangulated as mirror images on the 2022 photo (38 x 14.6
  m each, the published 5,978 sq ft, turned 42 degrees in toward the field). Seats under a board stop below it.
- **Outside**, on the OpenStreetMap outline: the black glass drum with its white light lines, the glass where the lanai
  is its face, the LED mesh on the east face toward I-15 and the name; the plazas, lots, roads and neighbours, the
  Strip's towers (the Luxor as its pyramid) and the ranges round the valley. The cityscape chunk is collapsed (the
  surroundings live in the stadium scene). The sideline props (one away piece nudged in from x 51.0), pylons, yard
  markers, banners and digits stay from retail; the field-level cloths take the 2026 league sheet. The scene fits the
  retail stored span of every bundle and decodes smaller than retail; nothing on the disc moves.
- **The intro cameras**: five new shots on s20's own camera channels (each wants 0 where its camera carries no
  component), two of them outside.
- **The field**: natural grass mown in 5-yard bands (the retail grass quad's UVs remapped in place), the grass outside
  the field of play, and, when the 2026 venue art folder is given (the Build's `modern_venues_2026`), the Raiders' 2026
  end zones (each end on its own retail textures) and midfield composed over clean grass.
- **The s20 row**: Allegiant Stadium, Las Vegas, NV, capacity 65,000; the indoor word becomes 1 (the roof is fixed: no
  rain or snow falls, SoFi's precedent); the grass word and the climate are retail.

With the option on, the 2026 venue art (`modern_venues_2026`) leaves s20 to it.

## Sources

- Facts: Wikipedia "Allegiant Stadium" (fetched 2026-09-25); Sports Video Group (2024-01-24) for the boards' areas.
- Plan: OpenStreetMap way 691478555 and its neighbours, the Strip's towers from Overpass (ODbL 1.0), in
  `data/nfl2k5_allegiant_model/footprint.json` (four landmark heights INFERRED from their published heights).
- Photos: Wikimedia Commons (the 2021 Vegas Kickoff Classic, the 2022 Las Vegas Bowl, the torch, the exteriors 2019 to
  2024), three of them with solved camera poses (reference only).
- Art: `tools/nfl2k5_allegiant_model_art.py`, deterministic; plain type only, no logos or players.

## Edition pack

`tools/nfl2k5_allegiant_model_pack.py SOURCE MASTERS OUT [--art-root DIR]` writes the 4x pack manifest keyed on the
model's own scene layout; build it against the catalog of the disc that will be played.

EXPERIMENTAL and UNWITNESSED in game.

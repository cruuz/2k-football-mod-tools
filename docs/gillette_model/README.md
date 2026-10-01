# Gillette Stadium (experimental)

Build option `modern_gillette`, off in every preset. It writes the New England Patriots' Gillette Stadium (Foxborough,
MA; opened 2002, Populous) as it stands after the 2021 to 2023 north end renovation into the Patriots' venue record s16
(the retail 2002 Gillette Stadium), all nine bundles (day, afternoon and night; dry, rain and snow), and gives the s16
row the town's own spelling and today's capacity.

## What it writes

- **The stadium scene**, built from scratch with the static SCNE builder (`mod_editor/core/nfl2k5_scne_builder.py`):
  the bowl as the 2002 building keeps it (its extent read from the retail scene): both sidelines the 100 level, the club
  tier with the suites over it and the tall upper deck; both ends one 100 level. Crowd billboards in the retail
  convention, cut at every aisle, and the ribbons on the fascias.
- **The north end since 2023**: the convex board (60 x 370 ft, 22,200 sq ft, Daktronics) over the north stands on its
  new structure, between its stat wings, the name over it as plain type, and the lighthouse (218 ft) on the north plaza
  behind it. The board's heights are a design reading of the photos (not yet measured on a solved pose).
- **The south board** (the 2010 board, 41.5 x 164 ft) over the south stands between its stat panels, the game's digits
  on them. Both boards are on the `jumbo_tron` material the game draws its live feed into (a crop of the feed at the
  picture's own aspect, never stretched, at a loop gain of about 1). Seats under a board stop below it.
- **Outside**: the light banks on the sideline upper decks, the building's walls with the name on the north facade; the
  surroundings from the shared environment kit (`mod_editor/core/nfl2k5_stadium_environment.py`, st3) outside the plaza:
  the lots with their parked cars, the roads, parks, water, trees and blocks from OpenStreetMap, the far ground to the
  haze and the horizon band at 1,800 m (the terrain's ridges and the tall buildings round the site). The cityscape chunk
  is collapsed (the surroundings live in the stadium scene). The sideline props, pylons, yard markers, banners and
  digits stay from retail; the field-level cloths take the 2026 league sheet. The scene fits the retail stored span of
  every bundle and decodes smaller than retail; nothing on the disc moves.
- **The intro cameras**: five new shots on s16's own camera channels (each wants 0 where its camera carries no
  component), two of them outside.
- **The field**: the playing surface in 5-yard bands (the retail grass quad's UVs remapped in place), the surface
  outside the field of play, and, when the 2026 venue art folder is given (the Build's `modern_venues_2026`), the
  Patriots' 2026 end zones and midfield composed over the clean surface. s16 lays both end zones on the same three
  textures, so each end's panels are split onto their own halves of them (the Mercedes-Benz model's method). With
  Modern playing surfaces on (run after it), the surface takes that option's 2026 turf for s16.
- **The s16 row**: Gillette Stadium, Foxborough, MA (the stadium's address; retail spells it Foxboro), capacity 64,628;
  the indoor word stays 0 (open air); the grass word and the climate are retail (the grass word is Noah's call and
  stays retail; Modern playing surfaces draws the turf).

With the option on, the 2026 venue art (`modern_venues_2026`) leaves s16 to it and lends it the Patriots' field art.

## Sources

- Facts: Wikipedia "Gillette Stadium" (fetched 2026-09-28); Daktronics (2023-08-04) for the north board.
- Plan: OpenStreetMap (the pitch, bearing 160.4 degrees, the building; ODbL 1.0) in
  `data/nfl2k5_gillette_model/footprint.json`; the surroundings (Patriot Place among them) in the kit's layout
  `data/nfl2k5_stadium_environment/s16.json` (OpenStreetMap, ODbL 1.0; the Terrain Tiles elevation set); the Esri World
  Imagery orthophoto for the plan of the north end (measured only, nothing of it is shipped).
- Photos: Wikimedia Commons (2023 to 2025), reference only.
- Art: `tools/nfl2k5_gillette_model_art.py`, deterministic; plain type only, no logos or players.

## Edition pack

`tools/nfl2k5_gillette_model_pack.py SOURCE MASTERS OUT [--art-root DIR]` writes the 4x pack manifest keyed on the
model's own scene layout; build it against the catalog of the disc that will be played.

EXPERIMENTAL and UNWITNESSED in game.

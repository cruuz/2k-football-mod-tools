# Lambeau Field (experimental)

Build option `modern_lambeau`, off in every preset. It writes the Green Bay Packers' Lambeau Field (Green Bay, WI;
opened 1957; the 2001 to 2003 renovation, the 2012 to 2013 south end zone expansion, the 2023 end zone boards) into the
Packers' venue record s10 (the retail 2004 Lambeau Field), all nine bundles (day, afternoon and night; dry, rain and
snow), and gives the s10 row today's capacity.

## What it writes

- **The stadium scene**, built from scratch with the static SCNE builder (`mod_editor/core/nfl2k5_scne_builder.py`):
  one continuous bowl of aluminium bleachers from the field wall (46 rows on the sidelines, 56 at the north end, 40 at
  the south end), the suites' glass over the sideline bowls, and the south end zone expansion (2012 to 2013: 7,500 seats,
  Wikipedia) as two upper tiers over the south bowl with its glass row. Crowd billboards in the retail convention, cut at
  every aisle, and the ribbons on the fascias. The heights are a design reading of the retail scene and the photos (no
  photo of the bowl since 2016 on Commons gives a solved pose).
- **The end zone boards** (2023, FOX 11 and Sports Video Group: 48 ft high by about 220 ft wide, behind each end zone,
  Daktronics) on the `jumbo_tron` material the game draws its live feed into (a crop of the feed at the picture's own
  aspect, never stretched, at a loop gain of about 1), each between two stat panels, the game's digits on the south
  board's; their deep green backs carry the name as plain type over the gates. The north board stands on the rooftop
  viewing terrace's structure (2012), the south one over the upper tiers. The side scoreboards (75 x 7.5 ft) hang on the
  suites' fascias over midfield. Seats under a board stop below it.
- **The lights**: the LED lights (2018) on four masts a side over the sideline roofs and two banks on the south upper
  tiers' roofs (the 2016 panorama).
- **Outside**: the white roofs round the bowl out to the brick and green walls on a design outline read off the
  orthophoto, the tower gates (2013) at the north and south ends with the name, the atrium's block on the east side; the
  surroundings from the shared environment kit (`mod_editor/core/nfl2k5_stadium_environment.py`, st3) outside the plaza:
  the lots with their parked cars, the roads, parks, water, trees and blocks from OpenStreetMap, the far ground to the
  haze and the horizon band at 1,800 m (the terrain's ridges and the tall buildings round the site). The cityscape chunk
  is collapsed (the surroundings live in the stadium scene). The sideline props, pylons, yard markers, banners and
  digits stay from retail; the field-level cloths take the 2026 league sheet. The scene fits the retail stored span of
  every bundle and decodes smaller than retail; nothing on the disc moves.
- **The intro cameras**: five new shots on s10's own camera channels (each wants 0 where its camera carries no
  component), two of them outside.
- **The field**: natural grass mown in 5-yard bands (the retail grass quad's UVs remapped in place), the grass outside
  the field of play, and, when the 2026 venue art folder is given (the Build's `modern_venues_2026`), the Packers' 2026
  end zones (each end on its own retail textures) and midfield composed over clean grass. With Modern playing surfaces
  on (run after it), the grass takes that option's palette for s10.
- **The s10 row**: its strings stay (Lambeau Field, Green Bay, WI; the 2026 venue names leave it), capacity 81,441
  (Wikipedia); the indoor word stays 0 (open air), the grass word and the climate are retail.

With the option on, the 2026 venue art (`modern_venues_2026`) leaves s10 to it and lends it the Packers' field art.

## Sources

- Facts: Wikipedia "Lambeau Field" (fetched 2026-09-28); packers.com (2012-05-15) for the 2012 boards; FOX 11
  (2023-04-03) and Sports Video Group (2023-10-18) for the 2023 boards and the side scoreboards; the seating guides for
  the Packers' bench on the west side.
- Plan: OpenStreetMap (the pitch, way 145797338, bearing 179.8 degrees; ODbL 1.0) in
  `data/nfl2k5_lambeau_model/footprint.json`; the surroundings (Titletown and the Resch Center among them) in the kit's
  layout `data/nfl2k5_stadium_environment/s10.json` (OpenStreetMap, ODbL 1.0; the Terrain Tiles elevation set); the Esri
  World Imagery orthophoto for the bowl's and the building's plan (measured only, nothing of it is shipped).
- Photos: Wikimedia Commons (2015 to 2025), reference only.
- Art: `tools/nfl2k5_lambeau_model_art.py`, deterministic; plain type only, no logos or players.

## Edition pack

`tools/nfl2k5_lambeau_model_pack.py SOURCE MASTERS OUT [--art-root DIR]` writes the 4x pack manifest keyed on the
model's own scene layout; build it against the catalog of the disc that will be played.

EXPERIMENTAL and UNWITNESSED in game.

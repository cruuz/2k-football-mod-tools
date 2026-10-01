# Mercedes-Benz Stadium (experimental)

Build option `modern_mercedes_benz`, off in every preset. It writes the Atlanta Falcons' Mercedes-Benz Stadium (Atlanta,
opened 2017; HOK) into the Falcons' venue record s01 (retail Georgia Dome), all nine bundles (day, afternoon and night;
dry, rain and snow), and names the s01 row Mercedes-Benz Stadium.

## What it writes

- **The stadium scene**, built from scratch with the static SCNE builder (`mod_editor/core/nfl2k5_scne_builder.py`):
  the red bowl in four stacks, its heights measured on two solved photo poses (the 2018 Peach Bowl from the west end's
  300 level on the axis, goalposts and far corners at 2.9 px; and from the north side's 300 level, 20 yard-line and
  sideline crossings at 3.0 px): the lower bowl's top at 13 m, the ribbon at 17 m, the club glass to 20.5 m, the 300
  level from 22 m; the east end's stands to 21.7 m under the window. Crowd billboards in the retail convention, cut at
  every aisle, and the LED ribbons on the fascias.
- **The Halo** (58 x 1,100 ft, Wikipedia), its bottom 57.7 m (measured): a ring round the roof's opening, twelve panels,
  the live feed on six (the `jumbo_tron` material at the picture's own aspect, never stretched) and the club graphics
  between them, the game's digits in a dark window on the two graphics panels over the sidelines and the club layout
  (ATL, RISE UP, FALCONS as type) on the other four. Seen from inside, u runs with the angle round the ring (the game's
  screen right is cross(view, up), where its digits read), so the feed and the graphics read as drawn.
- **The roof**: from below, the fixed roof's dark steel round the opening and the eight-panel pinwheel closed (the web of
  steel over the translucent panels), the floodlights round the opening's edge; from above, the silver-grey petals
  turning over the roofline in facets, each from its own corner height, up to the white ring round the opening, which
  stands proud of them (pass 3), and the pinwheel's dark panels on their white steel rising from the ring's top. The
  underside's outer edge keeps inside the petals (pass 3: on the outline it cut through their chords as dark streaks in
  the exterior shots).
- **The window to the city** at the east end: the glass (about 86 m wide, its top about 58 m) between two dark towers,
  the bridge across it with the venue's name, the tall column board at its side and the Mercedes-Benz star on its black
  panel under the glass; downtown's towers beyond it.
- **Outside**, on the OpenStreetMap outline (pass 3, on main's notes from the pair lab's exterior frames and the
  photos): eight irregular units, each a silver-grey metal petal hanging tip-down between two top corners with glass
  rising tip-up either side of it, the units of different widths (the south-west one the widest, then the north-east
  one), each corner at its own height and lean so the roofline rises and falls, each petal's tip at its own height; the
  glass band round the concourses on the units' chords in large panes; the east face turned over as the photos show it
  (the window is the glass); the Mercedes-Benz star on the big south-west petal and on the south-east one, the venue's
  sign on the north-east and north-west ones; the plaza; downtown and Midtown's towers of 60 m and more (the farthest
  drawn along their bearings at 1,700 m, the same size seen from the stadium); the surroundings from the shared
  environment kit (`mod_editor/core/nfl2k5_stadium_environment.py`, st3) outside the plaza: the lots with their parked
  cars, the roads, parks, water, trees and blocks from OpenStreetMap, the far ground to the haze and the horizon band at
  1,800 m (the terrain's ridges). And a sky backdrop round everything (s01 has no cityscape and its retail bundles carry
  no sky: the pair lab's exterior shots showed black over the building; the SoFi model's method and radius). DESIGN
  heights and widths. The sideline props, pylons, yard markers, banners and digits stay from retail; the field-level
  cloths take the 2026 league sheet. The scene fits the retail stored span of every bundle and decodes smaller than
  retail; nothing on the disc moves.
- **The intro cameras**: five new shots on s01's own camera channels (each wants 0 where its camera carries no
  component), two of them outside.
- **The field**: turf in 5-yard bands (the retail turf quad's UVs remapped in place), the turf outside the field of play,
  and, when the 2026 venue art folder is given (the Build's `modern_venues_2026`), the Falcons' 2026 end zones and
  midfield composed over clean turf (s01 lays both ends on the same three textures).
- **The s01 row**: Mercedes-Benz Stadium, Atlanta, GA, capacity 71,000; the indoor word stays 1 (the roof is modelled
  closed); the surface word and the climate are retail.

With the option on, the 2026 venue art (`modern_venues_2026`) leaves s01 to it.

## Sources

- Facts: Wikipedia "Mercedes-Benz Stadium" (fetched 2026-09-27); job u8's surfaces table (FieldTurf CORE).
- Plan: OpenStreetMap way 536744534 (93 m tall), downtown and Midtown's towers from Overpass (ODbL 1.0), in
  `data/nfl2k5_mercedes_benz_model/footprint.json`; the surroundings in the kit's layout
  `data/nfl2k5_stadium_environment/s01.json` (OpenStreetMap, ODbL 1.0; the Terrain Tiles elevation set; its band leaves
  out the towers within 4 km, which the model draws). The field's frame is the outline's own mirror axes.
- Photos: Wikimedia Commons (the 2018 and 2019 Peach Bowls, the 2025 CFP final, the 2024 interiors, the Super Bowl LIII
  aerials, the exteriors) and the Falcons' 2025 bird's-eye galleries for the sidelines (reference only).
- Marks: the Mercedes-Benz star from the official vector (Commons `Mercedes-Benz_Star_2022.svg`, from the Mercedes-Benz
  Group site) and the venue's sign from its own logo's wordmark (en.wikipedia `Mercedes-Benz_Stadium_logo.svg`, from
  mercedesbenzstadium.com), both rendered with Inkscape and pinned by SHA-256 in the art tool, never redrawn.
- Art: `tools/nfl2k5_mercedes_benz_model_art.py`, deterministic; plain type otherwise, no club logos or players.

## Edition pack

`tools/nfl2k5_mercedes_benz_model_pack.py SOURCE MASTERS OUT [--art-root DIR]` writes the 4x pack manifest keyed on the
model's own scene layout; build it against the catalog of the disc that will be played.

EXPERIMENTAL and UNWITNESSED in game.
